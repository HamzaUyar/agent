"use client"

import type { Brief, ImageDetail } from "@/lib/api/types"
import { formatConfidence } from "@/lib/format"
import { RISK, vehicleClass, vehicleTone } from "@/lib/labels"
import { cn } from "@/lib/utils"
import { keyedContacts, toPixel } from "@/lib/temas"
import { useOperasyon } from "@/store/operasyon"

/**
 * Kutu görsel dili (harita ve temas listesiyle aynı):
 *   renk        araç sınıfı (`--sinif-*`)
 *   çizgi       takip durumu: düz = track'le eşleşti, kesikli = kayıt dışı (track yok),
 *               noktalı daire = kaçırılmış (tespit yok, tipi bilinmez → nötr)
 *   kalınlık    zayıf tespit ince çizgi (+ etikette "zayıf")
 *   seviye      etiketteki baklava (dolgusu seviyeyle artar) ve erişilebilir ad
 *   seçim       kalın çizgi + beyaz/siyah çift hale; diğer kutular soluklaşır
 * Siyah kılıf her fotoğraf zemininde ayrışmayı sağlar.
 */
const CASING = "shadow-[0_0_0_1px_var(--tespit-kutu-kilif),inset_0_0_0_1px_var(--tespit-kutu-kilif)]"
const SELECTED_HALO =
  "shadow-[0_0_0_1px_var(--tespit-kutu-kilif),0_0_0_3px_var(--tespit-kutu-secili-hale),0_0_0_4px_var(--tespit-kutu-kilif),inset_0_0_0_1px_var(--tespit-kutu-kilif)]"

const box = ({ selected, dimmed, weak, dashed }: { selected: boolean; dimmed: boolean; weak?: boolean; dashed?: boolean }) =>
  cn(
    "border-[color:var(--sinif)] transition-[opacity,border-width,box-shadow] duration-150",
    selected ? cn("border-3", SELECTED_HALO) : cn(weak ? "border-[1.5px]" : "border-2", CASING, "hover:border-3"),
    dashed && "border-dashed",
    dimmed && "opacity-55 hover:opacity-100",
  )

/** Etiket çipi: koyu yarı saydam zemin; seçili kutuda sınıf renginde dolgu. */
const chip = (selected: boolean) =>
  cn(
    "pointer-events-none absolute rounded-sm px-1 text-[10px] leading-4 font-bold whitespace-nowrap",
    selected
      ? "bg-[var(--sinif)] text-[color:var(--zemin)] [--sv-bosluk:var(--sinif)]"
      : "bg-[var(--tespit-etiket-zemin)] text-metin [--sv-bosluk:var(--zemin)]",
  )

const pct = (value: number, total: number) => `${(value / total) * 100}%`

/**
 * Kare üzerinde tespitler: kutu sınıf, güven ve track'le; kaçırılmış Temas'ın kutusu yok, track
 * konumunda bir işaretle gösterilir. Konumlar karenin yüzdesi olarak verilir, önizleme hangi boyutta
 * olursa olsun hizalı kalır. Katman fotoğrafın üstünde olduğu için temadan bağımsız koyu token'larla
 * çizilir (`dark`).
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
        const selected = key === selectedKey
        const dimmed = selectedKey !== null && !selected
        if (contact.bbox) {
          const [x, y, w, h] = contact.bbox
          const label = `${vehicleClass(contact.label)} ${
            contact.confidence != null ? formatConfidence(contact.confidence) : ""
          } · ${name}`
          const tone = vehicleTone(contact.effective_label ?? contact.label)
          return (
            <li
              key={key}
              className={cn("absolute", `sinif--${tone}`, selected ? "z-20" : "hover:z-10")}
              style={{ left: pct(x, W), top: pct(y, H), width: pct(w, W), height: pct(h, H) }}
            >
              <button
                type="button"
                aria-pressed={selected}
                aria-label={`${label} · ${RISK[level].label}${contact.is_weak ? " · zayıf tespit" : ""}`}
                onClick={() => selectContact(key)}
                className={cn(
                  "peer absolute inset-0 rounded-[2px] focus-visible:outline-offset-4",
                  box({ selected, dimmed, weak: contact.is_weak, dashed: !contact.track_id }),
                )}
              />
              <span
                aria-hidden
                className={cn(
                  chip(selected),
                  "-top-4.5 left-0 flex items-center gap-0.5",
                  dimmed && "opacity-55 peer-hover:opacity-100",
                )}
              >
                <span className={cn("seviye-simge [--sv-boyut:7px]", `seviye--${level}`)}>{RISK[level].shape}</span>
                {label}
                {contact.is_weak && <span className="font-normal opacity-80">· zayıf</span>}
              </span>
            </li>
          )
        }
        // Kaçırılmış temas: kutu yok; track'in çekim anındaki konumu, noktalı nötr daire.
        const p = toPixel(image, contact.location.lat, contact.location.lon)
        return (
          <li
            key={key}
            className={cn("absolute sinif--diger", selected ? "z-20" : "hover:z-10")}
            style={{ left: pct(p.x, W), top: pct(p.y, H) }}
          >
            <button
              type="button"
              aria-pressed={selected}
              aria-label={`${name} · kaçırılmış temas, kutu yok · ${RISK[level].label}`}
              onClick={() => selectContact(key)}
              className={cn(
                "peer absolute size-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-dotted text-[var(--sinif)]",
                box({ selected, dimmed }),
                "border-dotted",
              )}
            >
              <span aria-hidden className="absolute inset-0 flex items-center justify-center text-xs font-bold">
                ⃠
              </span>
            </button>
            <span
              aria-hidden
              className={cn(chip(selected), "top-3 left-1/2 flex -translate-x-1/2 items-center gap-0.5", dimmed && "opacity-55")}
            >
              <span className={cn("seviye-simge [--sv-boyut:7px]", `seviye--${level}`)}>{RISK[level].shape}</span>
              {name} (kutu yok)
            </span>
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
