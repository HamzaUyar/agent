"use client"

import type { Brief, ContactFinding } from "@/lib/api/types"
import { reportSource, VERDICT, vehicleTone } from "@/lib/labels"
import { cn } from "@/lib/utils"
import { contactName, keyedContacts } from "@/lib/temas"
import { useOperasyon } from "@/store/operasyon"

/** Şerit, çekim anından iki saat öncesinden başlar (backend'in hareket penceresi). */
const WINDOW_MIN = 120
/** Çekim anından sonra gösterilen gri ve kapalı pay. */
const AFTER_MIN = 20

const toMin = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number)
  return h * 60 + m
}
const toHhmm = (total: number) =>
  `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(((total % 60) + 60) % 60).padStart(2, "0")}`

/**
 * Zaman akışı · seçili karenin son iki saati: seçili Temas'ın rota saatleri, duraklamaları ve bağlı
 * rapor saatleri. Çekim anından sonrası gri ve kapalıdır (ADR-0001).
 */
export function SeciliKareSeridi() {
  const images = useOperasyon((s) => s.images)
  const selectedImageId = useOperasyon((s) => s.selectedImageId)
  const brief = useOperasyon((s) =>
    s.evaluation?.status === "done" && s.evaluation.brief?.image_id === s.selectedImageId ? s.evaluation.brief : null,
  )
  const selectedKey = useOperasyon((s) => s.selectedContactKey)

  const summary = images.status === "ready" ? images.data.find((i) => i.image_id === selectedImageId) : undefined
  if (!summary) return null

  const capture = toMin(summary.capture_time)
  const start = capture - WINDOW_MIN
  const end = capture + AFTER_MIN
  const pos = (t: number) => `${((t - start) / (end - start)) * 100}%`
  const ticks = Array.from({ length: WINDOW_MIN / 30 + 1 }, (_, i) => start + i * 30)
  const contact = brief ? keyedContacts(brief).find((k) => k.key === selectedKey)?.contact : undefined

  return (
    <section aria-label="Seçili karenin son iki saati" className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between text-xs">
        <h2 className="font-bold tracking-wider text-metin-soluk uppercase">
          Seçili kare · son 2 saat ({toHhmm(start)}–{summary.capture_time})
        </h2>
        <span className="text-metin-soluk">
          {contact ? `${contactName(contact)} için` : brief ? "Ayrıntı için bir temas seçin" : ""}
        </span>
      </div>
      <div className="relative mx-2 h-12">
        <div aria-hidden className="absolute top-4 right-0 left-0 border-t border-cizgi-guclu/70" />
        {/* Çekim anından sonrası: taralı ve kapalı (ADR-0001). */}
        <div
          className="absolute inset-y-0 right-0 flex items-center justify-center overflow-hidden rounded-sm border border-dashed border-cizgi bg-[repeating-linear-gradient(135deg,var(--kart-vurgu)_0_4px,transparent_4px_8px)] text-[10px] leading-3 text-metin-soluk"
          style={{ left: pos(capture) }}
          title="Çekim anından sonrası gösterilmez"
        >
          <span className="rounded-sm bg-yuzey px-0.5 text-center">çekim anından sonrası yok</span>
        </div>
        {/* Çekim anı: seçili karenin "şimdi"si; mürekkep çizgi ve üstte işaret (mavi seçim değil). */}
        <span
          className="absolute top-0 h-7 w-0.5 -translate-x-1/2 bg-metin before:absolute before:-top-0.5 before:left-1/2 before:size-2 before:-translate-x-1/2 before:rotate-45 before:bg-metin"
          style={{ left: pos(capture) }}
          aria-label={`Çekim anı ${summary.capture_time}`}
          role="img"
        />
        {contact && <TemasOlaylari brief={brief!} contact={contact} start={start} capture={capture} pos={pos} />}
        {ticks.map((t) => (
          <span
            key={t}
            aria-hidden
            className="absolute bottom-0 -translate-x-1/2 font-mono text-[11px] text-metin-soluk"
            style={{ left: pos(t) }}
          >
            {toHhmm(t)}
          </span>
        ))}
      </div>
    </section>
  )
}

function TemasOlaylari({
  brief,
  contact,
  start,
  capture,
  pos,
}: {
  brief: Brief
  contact: ContactFinding
  start: number
  capture: number
  pos: (t: number) => string
}) {
  const inWindow = (t: number) => t >= start && t <= capture
  const clamp = (t: number) => Math.min(capture, Math.max(start, t))
  const route = (contact.motion?.route ?? []).filter((p) => p.time && inWindow(toMin(p.time)))
  const stops = (contact.motion?.stops ?? []).filter((s) => toMin(s.start) <= capture && toMin(s.end) >= start)
  const tone = contact.kind === "missed" ? "diger" : vehicleTone(contact.effective_label ?? contact.label)
  const reports = contact.track_id
    ? (brief.report_findings ?? []).filter((r) => r.track_id === contact.track_id && inWindow(toMin(r.report_time)))
    : []

  return (
    <ul aria-label="Olaylar" className={cn("absolute inset-x-0 top-0 h-8", `sinif--${tone}`)}>
      {route.map((p) => (
        <li
          key={`r-${p.time}`}
          aria-label={`Rota noktası ${p.time}`}
          className="absolute top-3.5 size-1.5 -translate-x-1/2 rounded-full bg-[var(--sinif)]"
          style={{ left: pos(toMin(p.time!)) }}
        />
      ))}
      {stops.map((s) => (
        <li
          key={`d-${s.start}`}
          aria-label={`Duraklama ${s.start} · ${s.minutes} dk`}
          className="absolute top-2.5 h-3.5 rounded-sm border border-[color:var(--sinif)] bg-[color-mix(in_srgb,var(--sinif)_18%,transparent)]"
          style={{ left: pos(clamp(toMin(s.start))), width: `calc(${pos(clamp(toMin(s.end)))} - ${pos(clamp(toMin(s.start)))})` }}
        >
          <span className="absolute -top-3 left-0 font-mono text-[10px] whitespace-nowrap text-metin-ikincil">
            duraklama {s.start}
          </span>
        </li>
      ))}
      {reports.map((r) => (
        <li
          key={`p-${r.claim_id}`}
          aria-label={`Rapor ${r.report_time} · ${reportSource(r.source)} · ${VERDICT[r.verdict]}`}
          className="absolute top-2 size-3 -translate-x-1/2 rounded-[2px] border-2 border-metin bg-yuzey"
          style={{ left: pos(toMin(r.report_time)) }}
        >
          <span className="absolute top-3 left-3 font-mono text-[10px] whitespace-nowrap text-metin">
            rapor {r.report_time}
          </span>
        </li>
      ))}
    </ul>
  )
}
