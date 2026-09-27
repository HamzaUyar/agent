"use client"

import { Bot, Cpu, Loader2, Wrench, type LucideIcon } from "lucide-react"

import { orchestratorCalls, type CallKind, type OrchestratorCall } from "@/lib/orkestrator"
import { cn } from "@/lib/utils"
import type { Evaluation } from "@/store/operasyon"

const KIND: Record<CallKind, { icon: LucideIcon; label: string; chip: string }> = {
  tool: { icon: Wrench, label: "araç", chip: "border-cizgi-guclu text-metin-ikincil" },
  model: { icon: Cpu, label: "model", chip: "border-cizgi-guclu text-metin-ikincil border-dashed" },
  agent: { icon: Bot, label: "agent", chip: "border-birincil bg-birincil text-birincil-uzeri" },
}

const seconds = (ms: number) =>
  ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toLocaleString("tr-TR", { maximumFractionDigits: 1 })} sn`

/** Orkestratörün çağrı özeti: kaç çağrı, kaçı agent. */
export function callCounts(evaluation: Evaluation) {
  const calls = orchestratorCalls(evaluation.steps)
  return { total: calls.length, agents: calls.filter((c) => c.kind === "agent").length }
}

/**
 * Değerlendirme, orkestratörün sırayla yaptığı araç, model ve agent çağrıları olarak gösterilir.
 * Önbellekten oynatılan değerlendirmede süre yazılmaz (ölçülen süre gerçek çalışma değildir).
 */
export function OrkestratorIzi({ evaluation }: { evaluation: Evaluation }) {
  const calls = orchestratorCalls(evaluation.steps, evaluation.cached ? [] : evaluation.stepDurations)
  return (
    <ol className="relative flex flex-col gap-2 border-l border-cizgi pl-3 font-mono text-xs">
      {calls.map((call) => (
        <Cagri key={call.key + call.name} call={call} />
      ))}
      {evaluation.status === "streaming" && (
        <li className="flex items-center gap-2 text-metin-soluk">
          <Loader2 aria-hidden className="size-3.5 animate-spin" />
          {evaluation.slow ? "Model yanıtı bekleniyor (en fazla 45 sn)" : "Orkestratör sonraki çağrıyı yapıyor…"}
        </li>
      )}
    </ol>
  )
}

function Cagri({ call }: { call: OrchestratorCall }) {
  const kind = KIND[call.kind]
  const Icon = kind.icon
  return (
    <li className="relative">
      <span
        aria-hidden
        className={cn(
          "absolute top-0.5 -left-[1.2rem] grid size-3.5 place-items-center rounded-full border bg-kart",
          call.kind === "agent" ? "border-birincil text-birincil" : "border-cizgi-guclu text-metin-soluk",
        )}
      >
        <Icon className="size-2.5" />
      </span>
      <div className="flex flex-wrap items-baseline gap-x-1.5">
        <span className={cn("rounded border px-1 text-[10px] leading-4 uppercase", kind.chip)}>{kind.label}</span>
        <span className="font-bold text-metin">
          {call.name}
          <span className="font-normal text-metin-soluk">({call.args})</span>
        </span>
        {call.durationMs !== undefined && (
          <span className="ml-auto text-[10px] text-metin-soluk">{seconds(call.durationMs)}</span>
        )}
      </div>
      {call.by && <div className="text-[11px] text-metin-soluk">↳ {call.by}</div>}
      <div className="font-sans text-metin-ikincil">→ {call.result}</div>
      {call.children.length > 0 && (
        <ul className="mt-1 flex flex-col gap-0.5 border-l border-dashed border-cizgi-guclu pl-2">
          {call.children.map((child, i) => (
            <li key={i} className={cn("text-[11px]", child.warn ? "text-metin" : "text-metin-ikincil")}>
              {child.warn && <span className="text-seviye-yuksek">▲ </span>}
              {child.text}
              {child.tags?.map((tag) => (
                <span
                  key={tag}
                  className="ml-1 rounded border border-cizgi px-1 font-sans text-[10px] whitespace-nowrap text-metin-soluk"
                >
                  {tag}
                </span>
              ))}
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}
