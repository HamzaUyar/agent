"use client"

import { Info, TriangleAlert, X } from "lucide-react"
import type { ReactNode } from "react"

import { SeviyeRozeti } from "@/components/operasyon/seviye-rozeti"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import type { Brief, ContactFinding, ReportFinding } from "@/lib/api/types"
import { formatConfidence, formatDegrees, formatDistance, formatSpeed } from "@/lib/format"
import { CARGO, certaintyLabel, EFFECT, reportSource, TREND, VERDICT, vehicleClass, vehicleTone } from "@/lib/labels"
import { cn } from "@/lib/utils"
import { contactName, distanceSeries } from "@/lib/temas"
import { useOperasyon } from "@/store/operasyon"

import { MesafeGrafigi } from "./mesafe-grafigi"
import { TurRozeti } from "./temas-listesi"

function Bolum({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="flex flex-col gap-1 border-t border-cizgi pt-2">
      <h4 className="text-xs font-bold tracking-wider text-metin-soluk uppercase">{title}</h4>
      {children}
    </section>
  )
}

function Satir({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[8.5rem_1fr] gap-2 text-xs">
      <dt className="text-metin-soluk">{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

/** Seçili Temas'ın detay kartı: tespit, eşleşme, hareket, seviye ve bağlı Rapor kararları. */
export function TemasKarti({ brief, contact }: { brief: Brief; contact: ContactFinding }) {
  const selectContact = useOperasyon((s) => s.selectContact)
  const zones = useOperasyon((s) => s.zones)
  const m = contact.motion
  const reasons = contact.level_reasons ?? []
  const reports = contact.track_id ? (brief.report_findings ?? []).filter((r) => r.track_id === contact.track_id) : []

  return (
    <article
      aria-label={`Araç: ${contactName(contact)}`}
      className="flex flex-col gap-2 rounded-md border border-secim bg-kart p-3 shadow-golge ring-1 ring-secim"
    >
      <header className="flex flex-wrap items-center gap-2">
        <span
          aria-hidden
          className={cn("sinif-renk", `sinif--${contact.kind === "missed" ? "diger" : vehicleTone(contact.effective_label ?? contact.label)}`)}
        />
        <h3 className="font-mono text-base font-bold">{contactName(contact)}</h3>
        <TurRozeti kind={contact.kind} />
        <SeviyeRozeti level={contact.final_level} />
        <Button
          variant="ghost"
          size="icon-xs"
          className="ml-auto"
          aria-label="Araç seçimini kaldır"
          onClick={() => selectContact(null)}
        >
          <X />
        </Button>
      </header>

      <Bolum title="Tespit">
        <dl className="flex flex-col gap-1">
          {contact.kind === "missed" ? (
            <p className="text-xs">Tespit yok: track karede ama tespit modeli bu aracı görmedi; tipi bilinmiyor.</p>
          ) : (
            <>
              <Satir label="Sınıf">
                {vehicleClass(contact.label)}
                {contact.effective_label && contact.effective_label !== contact.label && (
                  <> (riskte {vehicleClass(contact.effective_label)} sayıldı)</>
                )}
              </Satir>
              {contact.confidence != null && <Satir label="Güven">{formatConfidence(contact.confidence)}</Satir>}
            </>
          )}
          {contact.type_conflict && (
            <Satir label="Tip çelişkisi">
              {(contact.observed_labels ?? []).map((o) => `${o.image_id}: ${vehicleClass(o.label)}`).join(" · ")}
            </Satir>
          )}
          {contact.visual && (
            <Satir label="Görsel doğrulama">
              {contact.visual.is_vehicle ? "araç" : "araç değil"}
              {contact.visual.color && ` · ${contact.visual.color}`}
              {contact.visual.cargo && ` · ${CARGO[contact.visual.cargo] ?? contact.visual.cargo}`}
              <span className="text-metin-soluk"> ({contact.visual.model})</span>
            </Satir>
          )}
          <Satir label="Kesinlik">
            {certaintyLabel(contact.certainty)}
            {contact.is_weak && " · zayıf tespit (track'le eşleştiği için araç sayıldı)"}
          </Satir>
        </dl>
      </Bolum>

      <Bolum title="Eşleşme">
        {contact.track_id ? (
          <dl className="flex flex-col gap-1">
            <Satir label="Track">
              <span className="font-mono">{contact.track_id}</span>
            </Satir>
            {contact.match_distance_m != null && (
              <Satir label="Eşleşme mesafesi">{formatDistance(contact.match_distance_m)}</Satir>
            )}
            {contact.second_candidate && (
              <Satir label="İkinci aday">
                <span className="font-mono">{contact.second_candidate.track_id}</span> ·{" "}
                {formatDistance(contact.second_candidate.distance_m)}
              </Satir>
            )}
            {contact.is_ambiguous && (
              <p role="note" className="flex gap-1.5 rounded border border-cizgi-guclu bg-kart-vurgu px-2 py-1 text-xs">
                <Info aria-hidden className="mt-px size-3.5 shrink-0 text-metin-ikincil" />
                Belirsiz eşleşme: eşik içinde birden fazla track var; en yakını seçildi.
              </p>
            )}
            {contact.position_estimated && (
              <p className="text-xs text-metin-ikincil">
                Çekim anında kayıt yok; konum son iki noktadan ileri kestirildi.
              </p>
            )}
          </dl>
        ) : (
          <p className="text-xs">Kayıt dışı temas: track yok, hareket geçmişi bilinmiyor (park hâlinde olabilir).</p>
        )}
      </Bolum>

      {m && (
        <Bolum title="Hareket">
          <dl className="flex flex-col gap-1">
            <Satir label="Üsse mesafe">
              {m.distance_to_base_30min_ago_m != null && <>30 dk önce {formatDistance(m.distance_to_base_30min_ago_m)} → </>}
              şimdi {formatDistance(m.distance_to_base_m)} · <strong>{TREND[m.trend]}</strong>
            </Satir>
            <Satir label="Hız">
              son {formatSpeed(m.recent_speed_mps)} · ortalama {formatSpeed(m.avg_speed_mps)}
            </Satir>
            <Satir label="Yön">{m.heading_deg != null ? formatDegrees(m.heading_deg) : "belirsiz"}</Satir>
            <Satir label="Duraklamalar">
              {m.stops?.length
                ? m.stops.map((s) => `${s.start} (${s.minutes} dk, ${s.zone})`).join(" · ")
                : "yok"}
            </Satir>
            <Satir label="Geçilen bölgeler">{m.zones_passed?.join(" → ") || "—"}</Satir>
          </dl>
          {zones.status === "ready" && m.route && m.route.length > 1 && (
            <MesafeGrafigi series={distanceSeries(m.route, zones.data.base, brief.capture_time)} />
          )}
        </Bolum>
      )}

      <Bolum title="Seviye">
        <p className="flex items-center gap-2 text-xs">
          temel <SeviyeRozeti level={contact.base_level} /> → nihai <SeviyeRozeti level={contact.final_level} />
          {contact.verified_friend && <Badge variant="outline">doğrulanmış dost</Badge>}
        </p>
        {reasons.length > 0 && (
          <ul className="list-disc pl-5 text-xs text-metin-ikincil">
            {reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        )}
        {contact.adjustment_reason && (
          <p className="text-xs">
            <span className="font-bold">LLM ayarı: </span>
            {contact.adjustment_reason}
          </p>
        )}
        {contact.adjustment_rejected && (
          <p className="text-xs">
            <span className="font-bold">Reddedilen öneri: </span>
            {contact.adjustment_rejected}
          </p>
        )}
      </Bolum>

      <Bolum title="Rapor kararları">
        {!contact.track_id ? (
          <p className="text-xs text-metin-ikincil">
            Bu araca rapor bağlanamıyor: raporlar aracın rapor saatindeki track konumuyla eşleştiriliyor,
            kayıt dışı temasın track&apos;i yok.
          </p>
        ) : reports.length === 0 ? (
          <p className="text-xs text-metin-ikincil">Bu araca bağlı rapor yok.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {reports.map((r) => (
              <RaporKarari key={r.claim_id} report={r} />
            ))}
          </ul>
        )}
      </Bolum>
    </article>
  )
}

/**
 * Rapor kararı seviye değildir: seviye renkleri kullanılmaz. Çelişkili = dolu mürekkep (dikkat),
 * tutarlı = düz çerçeve, doğrulanamaz/ilgisiz = kesikli soluk.
 */
const VERDICT_TONE: Record<ReportFinding["verdict"], string> = {
  contradicts: "border-metin bg-metin text-zemin",
  consistent: "border-metin-ikincil text-metin",
  unverifiable: "border-dashed border-cizgi-guclu text-metin-soluk",
  irrelevant: "border-dashed border-cizgi-guclu text-metin-soluk",
}

function RaporKarari({ report }: { report: ReportFinding }) {
  const effect = EFFECT[report.effect]
  return (
    <li className="flex flex-col gap-1 rounded border border-cizgi bg-yuzey p-2 text-xs">
      <span className="flex flex-wrap items-center gap-2">
        <span className="font-mono">{report.report_time}</span>
        <span className="text-metin-soluk">{reportSource(report.source)}</span>
        <Badge variant="outline" className={cn("rounded", VERDICT_TONE[report.verdict])}>
          {report.verdict === "contradicts" && <TriangleAlert aria-hidden />}
          {VERDICT[report.verdict].toLocaleUpperCase("tr-TR")}
        </Badge>
        <span>
          riske etkisi: {effect.symbol} {effect.label}
        </span>
      </span>
      <q className="text-metin-ikincil italic">{report.text}</q>
      <span>
        <span className="font-bold">Gerekçe: </span>
        {report.reasoning}
      </span>
    </li>
  )
}
