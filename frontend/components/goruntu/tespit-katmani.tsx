"use client"

import type { Brief, ImageDetail } from "@/lib/api/types"
import { formatConfidence } from "@/lib/format"
import { RISK, vehicleClass } from "@/lib/labels"
import { cn } from "@/lib/utils"
import { keyedContacts, toPixel } from "@/lib/temas"
import { useOperasyon } from "@/store/operasyon"

/** Seviye yalnızca etiketteki baklavada; kutunun kendisi seviyeden bağımsız tek renk. */
const LEVEL_TEXT = {
  low: "text-risk-dusuk",
  medium: "text-risk-orta",
  high: "text-risk-yuksek",
  critical: "text-risk-kritik",
} as const

/** Kutu: siyah kılıflı beyaz (her zeminde seçilir); seçili kutu çelik mavisi ve kalın. */
const HALO = "shadow-[0_0_0_1px_var(--tespit-kutu-kilif),inset_0_0_0_1px_var(--tespit-kutu-kilif)]"
const box = (selected: boolean) =>
  cn(
    HALO,
    selected
      ? "border-3 border-[color:var(--tespit-kutu-secili)] text-[var(--tespit-kutu-secili)]"
      : "border-2 border-[color:var(--tespit-kutu)] text-[var(--tespit-kutu)]",
  )

const pct = (value: number, total: number) => `${(value / total) * 100}%`

/**
 * Kare üzerinde tespitler: kutu sınıf, güven ve track'le; zayıf tespit kesikli kutu; kaçırılmış
 * Temas'ın kutusu yok, track konumunda bir işaretle gösterilir. Konumlar karenin yüzdesi olarak
 * verilir, önizleme hangi boyutta olursa olsun hizalı kalır. Katman fotoğrafın üstünde olduğu için
 * temadan bağımsız koyu token'larla çizilir (`dark`).
 */
export function TespitKatmani({ brief, image }: { brief: Brief; image: ImageDetail }) {
  const { width_px: W, height_px: H } = image
  const selectedKey = useOperasyon((s) => s.selectedContactKey)
  const selectContact = useOperasyon((s) => s.selectContact)

  return (
    <ul aria-label="Tespitler" className="dark absolute inset-0">
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
              className={cn("absolute", key === selectedKey && "z-10")}
              style={{ left: pct(x, W), top: pct(y, H), width: pct(w, W), height: pct(h, H) }}
            >
              <button
                type="button"
                aria-pressed={key === selectedKey}
                aria-label={`${label} · ${RISK[level].label}${contact.is_weak ? " · zayıf tespit" : ""}`}
                onClick={() => selectContact(key)}
                className={cn("absolute inset-0", box(key === selectedKey), contact.is_weak && "border-dashed")}
              >
                <span className="absolute -top-4 left-0 rounded-sm bg-zemin/85 px-1 text-[10px] leading-4 whitespace-nowrap text-metin">
                  <span aria-hidden className={LEVEL_TEXT[level]}>
                    {RISK[level].shape}
                  </span>{" "}
                  {label}
                </span>
              </button>
            </li>
          )
        }
        // Kaçırılmış temas: kutu yok; track'in çekim anındaki konumu.
        const p = toPixel(image, contact.location.lat, contact.location.lon)
        return (
          <li
            key={key}
            className={cn("absolute", key === selectedKey && "z-10")}
            style={{ left: pct(p.x, W), top: pct(p.y, H) }}
          >
            <button
              type="button"
              aria-pressed={key === selectedKey}
              aria-label={`${name} · kaçırılmış temas, kutu yok · ${RISK[level].label}`}
              onClick={() => selectContact(key)}
              className={cn(
                "absolute size-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-dashed",
                box(key === selectedKey),
              )}
            >
              <span aria-hidden className="absolute inset-0 flex items-center justify-center text-xs font-bold">
                ⃠
              </span>
              <span className="absolute top-5 left-1/2 -translate-x-1/2 rounded-sm bg-zemin/85 px-1 text-[10px] leading-4 whitespace-nowrap text-metin">
                <span aria-hidden className={LEVEL_TEXT[level]}>
                  {RISK[level].shape}
                </span>{" "}
                {name} (kutu yok)
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
