/**
 * Değerlendirme adımlarını orkestratörün yaptığı çağrılar olarak okur: her adım bir araç
 * (deterministik kod), model (tespit / VLM) ya da agent (LLM kararı) çağrısıdır.
 * Yalnızca gelen adımların `data`'sından türetilir; adım sözleşmesi `backend/app/agent/events.py`.
 */
import type { ReportFinding, RiskLevel, StepEvent } from "@/lib/api/types"
import { RISK, VERDICT, reportSource } from "@/lib/labels"

export type CallKind = "tool" | "model" | "agent"

export type SubCall = {
  text: string
  /** Operatörün dikkatini isteyen alt sonuç (çelişki, ayrışma, reddedilen ayar). */
  warn?: boolean
  tags?: string[]
}

export type OrchestratorCall = {
  key: string
  kind: CallKind
  name: string
  args: string
  result: string
  /** Cevabı veren model ya da yöntem (ör. `glm/glm-5.3-flash`, "LLM + kural"). */
  by?: string
  children: SubCall[]
  durationMs?: number
}

type Data = Record<string, unknown>

const list = (d: Data, key: string): Data[] => (Array.isArray(d[key]) ? (d[key] as Data[]) : [])

const levelLabel = (level: unknown) => RISK[level as RiskLevel]?.label.toLocaleLowerCase("tr-TR") ?? String(level)

/** Gözcü (GLM'in tespit edilmeyen araca bakışı) ve yakındaki tespit notları gerekçe metninde gelir. */
function reportTags(f: ReportFinding): string[] {
  const tags: string[] = []
  if (f.reasoning.includes("görsel incelemede")) tags.push("gözcü: görsel bakış")
  if (f.reasoning.includes("olası aynı araç")) tags.push("yakında tespit")
  return tags
}

function reportChild(f: ReportFinding): SubCall {
  const rule = f.rule_verdict && f.rule_verdict !== (f.detail_verdict ?? f.verdict) ? f.rule_verdict : null
  const tags = reportTags(f)
  if (f.needs_review) tags.unshift(`kural ayrıştı${rule ? `: ${VERDICT[rule as keyof typeof VERDICT] ?? rule}` : ""} → operatör`)
  else if (f.rule_verdict) tags.unshift("kural onayladı")
  if (f.dangerous_reassurance) tags.unshift("tehlikeli güvence")
  return {
    text: `#${f.claim_id} ${reportSource(f.source)}${f.track_id ? ` · ${f.track_id}` : ""} → ${VERDICT[f.verdict]}`,
    warn: f.verdict === "contradicts" || f.needs_review || f.dangerous_reassurance,
    tags,
  }
}

function toCall(step: StepEvent): OrchestratorCall {
  const d = step.data as Data
  const base = { key: `${step.step_no}`, result: step.summary, children: [] as SubCall[] }
  switch (step.name) {
    case "goruntu":
      return { ...base, kind: "tool", name: "goruntu_baglami", args: String(d.image_id ?? "") }
    case "tespit":
      return {
        ...base,
        kind: "model",
        name: "tespit_modeli.detect",
        args: `görüntü`,
        by: "araç tespit modeli",
      }
    case "konum":
      return { ...base, kind: "tool", name: "piksel_to_konum", args: `${list(d, "locations").length} kutu` }
    case "eslesme":
      return {
        ...base,
        kind: "tool",
        name: "track_eslestir",
        args: `${list(d, "matches").length} tespit, eşik 5 m`,
        by: "Hungarian",
      }
    case "hareket":
      return {
        ...base,
        kind: "tool",
        name: "risk_motoru.hareket",
        args: `${Object.keys((d.motions as Data | undefined) ?? {}).length} track`,
      }
    case "raporlar": {
      const findings = list(d, "findings") as unknown as ReportFinding[]
      return {
        ...base,
        kind: "agent",
        name: "rapor_dogrulama_agent",
        args: `${findings.length} iddia`,
        by: findings.length ? "LLM + kural ikinci görüşü" : undefined,
        children: findings.map(reportChild),
      }
    }
    case "risk":
      return { ...base, kind: "tool", name: "risk_motoru.seviye", args: `${list(d, "contacts").length} temas` }
    case "karar": {
      const contacts = list(d, "contacts")
      const model = typeof d.model === "string" ? d.model : null
      return {
        ...base,
        kind: "agent",
        name: "karar_agent",
        args: `${contacts.length} temas`,
        by: model ?? `yedek: kural özeti`,
        result: model ? step.summary.replace(`${model}: `, "") : step.summary,
        children: contacts
          .filter((c) => c.adjustment_reason)
          .map((c) => ({
            text: `${c.track_id ?? "kayıt dışı"} → ${levelLabel(c.final_level)} · ${String(c.adjustment_reason)}`,
            warn: Boolean(c.adjustment_rejected),
            tags: [c.adjustment_rejected ? `motor reddetti: ${String(c.adjustment_rejected)}` : "motor onayladı"],
          })),
      }
    }
    default:
      return { ...base, kind: "tool", name: step.name, args: "" }
  }
}

/** Gelen adımlardan orkestratörün çağrı izi: her adım bir çağrı. */
export function orchestratorCalls(steps: StepEvent[], durations: number[] = []): OrchestratorCall[] {
  return steps.map((step, i) => ({ ...toCall(step), durationMs: durations[i] }))
}
