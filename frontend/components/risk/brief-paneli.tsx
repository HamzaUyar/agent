"use client"

import type { ReactNode } from "react"

import { SeviyeRozeti } from "@/components/operasyon/seviye-rozeti"
import { Badge } from "@/components/ui/badge"
import type { AttentionFinding, Brief, ReportFinding } from "@/lib/api/types"
import { ATTENTION_REASON, vehicleClass, vehicleTone } from "@/lib/labels"
import { attentionLabels, bySeverity, contactName, type KeyedContact } from "@/lib/temas"
import { cn } from "@/lib/utils"
import { useOperasyon } from "@/store/operasyon"

import { RaporKarari } from "./temas-karti"
import { TurRozeti } from "./temas-listesi"

/** Metinde gösterilen dikkat maddesi: doğrulanmış; "dikkat gerekmiyor" yalnızca seviyeyi düşürdüyse. */
const shown = (a: AttentionFinding) => a.accepted && (a.reason !== "dikkat_gerekmiyor" || a.level_accepted === true)

/** Çelişkili rapor önce: operatörün bilmesi gereken güvenilmez iddia. */
const VERDICT_ORDER: Record<ReportFinding["verdict"], number> = {
  contradicts: 0,
  consistent: 1,
  unverifiable: 2,
  irrelevant: 3,
}

type TemasMaddesi = KeyedContact & { label: string; items: AttentionFinding[] }

function Bolum({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="flex flex-col gap-1.5">
      <h3 className="text-xs font-bold tracking-wider text-metin-soluk uppercase">{title}</h3>
      {children}
    </section>
  )
}

/**
 * Brief: LLM raporu yapısında. Önce karar kartı (seviye + önerilen eylem), sonra durum
 * değerlendirmesi (LLM özeti), dikkat gerektiren araçlar (kutu kutu, LLM yorumu ve kodun doğruladığı
 * veri), rapor değerlendirmesi; en sonda katlanır reddedilen öneriler, kaynaklar ve model bilgisi.
 */
export function BriefPaneli({ brief }: { brief: Brief }) {
  const attention = brief.attention ?? []
  const byLabel = new Map<string, AttentionFinding[]>()
  for (const a of attention.filter(shown)) byLabel.set(a.contact, [...(byLabel.get(a.contact) ?? []), a])

  const labels = [...attentionLabels(brief)].map(([label, k]): TemasMaddesi => ({
    ...k,
    label,
    items: byLabel.get(label) ?? [],
  }))
  // Kuralların orta ve üstü verdiği temas LLM seçmese de dikkat listesinde kalır.
  const needs = (t: TemasMaddesi) => t.items.length > 0 || t.contact.final_level !== "low"
  const main = labels.filter(needs).sort(bySeverity)
  const calm = labels.filter((t) => !needs(t)).sort(bySeverity)
  const rejected = attention.filter((a) => a.rejection)
  const reports = [...(brief.report_findings ?? [])].sort((a, b) => VERDICT_ORDER[a.verdict] - VERDICT_ORDER[b.verdict])

  return (
    <article aria-label="Brief" className="flex flex-col gap-4">
      <section
        aria-label="Karar"
        className={cn(
          `seviye--${brief.risk_level}`,
          "flex flex-col gap-2 rounded-md border border-l-4 border-cizgi border-l-[color:var(--sv)] bg-kart p-3 shadow-golge",
        )}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <SeviyeRozeti level={brief.risk_level} className="text-sm" />
          <span className="font-mono text-xs text-metin-soluk">
            {brief.image_id} · {brief.zone} · {brief.capture_time} · {brief.contacts.length} araç
          </span>
        </div>
        <p className="text-[0.9375rem] leading-snug">
          <span className="text-xs font-bold tracking-wider text-metin-soluk uppercase">Önerilen eylem</span>
          <br />
          <span className="font-bold text-metin">{brief.recommended_action}</span>
        </p>
      </section>

      <Bolum title="Durum değerlendirmesi">
        {brief.summary ? (
          <p className="rounded-md border border-cizgi bg-kart p-2 leading-relaxed">{brief.summary}</p>
        ) : (
          <p className="text-xs text-metin-soluk">
            {brief.is_fallback
              ? "LLM değerlendirmesi yok; seviyeler kurallarla verildi."
              : `LLM özeti gösterilmedi${brief.summary_rejected ? `: ${brief.summary_rejected}` : ""}.`}
          </p>
        )}
      </Bolum>

      <Bolum title={`Dikkat gerektiren araçlar (${main.length})`}>
        {main.length === 0 ? (
          <p className="text-xs text-metin-soluk">Dikkat gerektiren araç yok.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {main.map((t) => (
              <TemasKutusu key={t.key} item={t} />
            ))}
          </ul>
        )}
        {calm.length > 0 && (
          <details className="rounded-md border border-cizgi bg-kart">
            <summary className="px-2 py-1.5 text-xs text-metin-ikincil select-none hover:text-metin">
              {calm.length} araç dikkat gerektirmiyor
            </summary>
            <ul className="flex flex-col gap-2 p-1">
              {calm.map((t) => (
                <TemasKutusu key={t.key} item={t} />
              ))}
            </ul>
          </details>
        )}
      </Bolum>

      {reports.length > 0 && (
        <Bolum title={`Rapor değerlendirmesi (${reports.length})`}>
          <ul className="flex flex-col gap-2">
            {reports.map((r) => (
              <RaporKarari key={r.claim_id} report={r} about={r.track_id ?? undefined} />
            ))}
          </ul>
        </Bolum>
      )}

      {rejected.length > 0 && (
        <details aria-label="Reddedilen LLM önerileri" className="rounded-md border border-cizgi bg-kart px-2 py-1.5">
          <summary className="text-xs font-bold tracking-wider text-metin-soluk uppercase select-none">
            Reddedilen LLM önerileri ({rejected.length})
          </summary>
          <ul className="mt-2 list-disc pl-5 text-xs text-metin-ikincil">
            {rejected.map((a, i) => (
              <li key={`${a.contact}-${i}`}>
                <span className="font-mono">{a.contact}</span>: {a.rejection}
              </li>
            ))}
          </ul>
        </details>
      )}

      <details aria-label="Kaynaklar" className="rounded-md border border-cizgi bg-kart px-2 py-1.5">
        <summary className="text-xs font-bold tracking-wider text-metin-soluk uppercase select-none">
          Kaynaklar ({brief.sources.length})
        </summary>
        <ul className="mt-2 list-disc pl-5 text-xs text-metin-ikincil">
          {brief.sources.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      </details>

      <details aria-label="Model" className="rounded-md border border-cizgi bg-kart px-2 py-1.5">
        <summary className="text-xs font-bold tracking-wider text-metin-soluk uppercase select-none">Model</summary>
        <div className="mt-2 text-xs">
          {brief.is_fallback ? (
            <Badge variant="outline" className="border-otomatik-ozet text-otomatik-ozet">
              otomatik özet{brief.fallback_reason ? `: ${brief.fallback_reason}` : ""}
            </Badge>
          ) : (
            brief.model && <Badge variant="outline" className="font-mono">LLM: {brief.model}</Badge>
          )}
        </div>
      </details>
    </article>
  )
}

/**
 * Aracın (Temas) rapordaki kutusu: kimlik, sınıf, takip durumu ve seviye; dikkat nedenleri; LLM'in yorumu
 * ve altında kodun doğruladığı veri. LLM maddesi yoksa kuralların gerekçesi gösterilir.
 */
function TemasKutusu({ item: { key, contact, items } }: { item: TemasMaddesi }) {
  const selectContact = useOperasyon((s) => s.selectContact)
  const setRiskTab = useOperasyon((s) => s.setRiskTab)
  const label = contact.effective_label ?? contact.label
  const name = contactName(contact)

  return (
    <li
      className={cn(
        `seviye--${contact.final_level}`,
        "flex flex-col gap-1.5 rounded-md border border-l-[3px] border-cizgi border-l-[color:var(--sv)] bg-kart p-2 text-xs",
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span aria-hidden className={cn("sinif-renk", `sinif--${contact.kind === "missed" ? "diger" : vehicleTone(label)}`)} />
        <span className="font-mono text-[13px] font-bold">{name}</span>
        <span className="text-metin-ikincil">{vehicleClass(label)}</span>
        <TurRozeti kind={contact.kind} />
        <span className="ml-auto flex items-center gap-1">
          {contact.base_level !== contact.final_level && (
            <>
              <SeviyeRozeti level={contact.base_level} />→
            </>
          )}
          <SeviyeRozeti level={contact.final_level} />
        </span>
      </div>

      {items.length > 0 ? (
        <ul className="flex flex-col gap-1.5">
          {items.map((a, i) => (
            <li key={`${a.reason}-${i}`} className="flex flex-col gap-0.5">
              <Badge variant="outline" className="w-fit rounded">
                {ATTENTION_REASON[a.reason]}
              </Badge>
              {a.comment && <p className="leading-relaxed text-metin">{a.comment}</p>}
              {a.text && (
                <p className="text-metin-soluk">
                  <span className="sr-only">Veri: </span>
                  {a.text}
                </p>
              )}
            </li>
          ))}
        </ul>
      ) : (
        (contact.level_reasons ?? []).length > 0 && (
          <ul className="list-disc pl-5 text-metin-ikincil">
            {(contact.level_reasons ?? []).map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        )
      )}

      <button
        type="button"
        className="w-fit text-metin-ikincil underline-offset-2 hover:text-metin hover:underline"
        onClick={() => {
          selectContact(key)
          setRiskTab("temaslar")
        }}
      >
        {name} ayrıntısı
      </button>
    </li>
  )
}
