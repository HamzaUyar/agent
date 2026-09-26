"use client"

import type { Brief, ImageDetail } from "@/lib/api/types"
import { formatConfidence } from "@/lib/format"
import { RISK, vehicleClass } from "@/lib/labels"
import { cn } from "@/lib/utils"
import { keyedContacts, toPixel } from "@/lib/temas"
import { useOperasyon } from "@/store/operasyon"

const TONE = {
  low: "border-risk-dusuk text-risk-dusuk",
  medium: "border-risk-orta text-risk-orta",
  high: "border-risk-yuksek text-risk-yuksek",
  critical: "border-risk-kritik text-risk-kritik",
} as const

const pct = (value: number, total: number) => `${(value / total) * 100}%`

/**
 * Kare üzerinde tespitler: kutu sınıf, güven ve track'le; zayıf tespit kesikli kutu; kaçırılmış
 * Temas'ın kutusu yok, track konumunda bir işaretle gösterilir. Konumlar karenin yüzdesi olarak
 * verilir, önizleme hangi boyutta olursa olsun hizalı kalır.
 */
export function TespitKatmani({ brief, image }: { brief: Brief; image: ImageDetail }) {
  const { width_px: W, height_px: H } = image
  const selectedKey = useOperasyon((s) => s.selectedContactKey)
  const selectContact = useOperasyon((s) => s.selectContact)

  return (
    <ul aria-label="Tespitler" className="absolute inset-0">
      {keyedContacts(brief).map(({ key, contact }) => {
        const level = contact.final_level
        const name = contact.track_id ?? "track yok"
        if (contact.bbox) {
          const [x, y, w, h] = contact.bbox
          const label = `${vehicleClass(contact.label)} ${
            contact.confidence != null ? formatConfidence(contact.confidence) : ""
          } · ${name}`
          return (
            <li
              key={key}
              className="absolute"
              style={{ left: pct(x, W), top: pct(y, H), width: pct(w, W), height: pct(h, H) }}
            >
              <button
                type="button"
                aria-pressed={key === selectedKey}
                aria-label={`${label} · ${RISK[level].label}${contact.is_weak ? " · zayıf tespit" : ""}`}
                onClick={() => selectContact(key)}
                className={cn(
                  "absolute inset-0 border-2",
                  TONE[level],
                  contact.is_weak && "border-dashed",
                  key === selectedKey && "ring-2 ring-secim ring-offset-1 ring-offset-zemin",
                )}
              >
                <span className="absolute -top-4 left-0 rounded-sm bg-zemin/85 px-1 text-[10px] leading-4 whitespace-nowrap text-metin">
                  {RISK[level].shape} {label}
                </span>
              </button>
            </li>
          )
        }
        // Kaçırılmış temas: kutu yok; track'in çekim anındaki konumu.
        const p = toPixel(image, contact.location.lat, contact.location.lon)
        return (
          <li key={key} className="absolute" style={{ left: pct(p.x, W), top: pct(p.y, H) }}>
            <button
              type="button"
              aria-pressed={key === selectedKey}
              aria-label={`${name} · kaçırılmış temas, kutu yok · ${RISK[level].label}`}
              onClick={() => selectContact(key)}
              className={cn(
                "absolute size-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-dashed",
                TONE[level],
                key === selectedKey && "ring-2 ring-secim ring-offset-1 ring-offset-zemin",
              )}
            >
              <span aria-hidden className="absolute inset-0 flex items-center justify-center text-xs font-bold">
                ⃠
              </span>
              <span className="absolute top-5 left-1/2 -translate-x-1/2 rounded-sm bg-zemin/85 px-1 text-[10px] leading-4 whitespace-nowrap text-metin">
                {RISK[level].shape} {name} (kutu yok)
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

/** Karenin altındaki özet: "2 tespit · 1 track'le eşleşti · kaçırılmış: T0032". */
export function TespitOzeti({ brief }: { brief: Brief }) {
  const detected = brief.contacts.filter((c) => c.kind !== "missed")
  const matched = brief.contacts.filter((c) => c.kind === "matched").length
  const missed = brief.contacts.filter((c) => c.kind === "missed")
  return (
    <p className="text-xs text-metin-ikincil">
      {detected.length} tespit · {matched} track&apos;le eşleşti
      {missed.length > 0 && (
        <>
          {" · "}
          <span className="text-metin">
            kaçırılmış: {missed.map((c) => c.track_id).join(", ")} (model görmedi)
          </span>
        </>
      )}
    </p>
  )
}
