"use client"

import { SeviyeSekli } from "@/components/operasyon/seviye-rozeti"
import type { ImageSummary } from "@/lib/api/types"
import { RISK } from "@/lib/labels"
import { cn } from "@/lib/utils"
import { useOperasyon } from "@/store/operasyon"

import { SeciliKareSeridi } from "./secili-kare-seridi"

const minutes = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number)
  return h * 60 + m
}
const hhmm = (total: number) => `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`

/**
 * Zaman akışı · günün Görüntü'leri: bütün kareler çekim anına göre bir saat ekseninde, son seviyelerinin
 * şekliyle. Her kare her zaman seçilebilir; ←/→ önceki/sonraki kare.
 */
export function ZamanAkisi() {
  const images = useOperasyon((s) => s.images)
  const selectedImageId = useOperasyon((s) => s.selectedImageId)
  const selectImage = useOperasyon((s) => s.selectImage)
  const openLeft = useOperasyon((s) => s.openLeft)

  const list = images.status === "ready" ? images.data : []
  const start = list.length ? Math.floor(minutes(list[0].capture_time) / 60) * 60 : 0
  const end = list.length ? Math.ceil((minutes(list.at(-1)!.capture_time) + 1) / 60) * 60 : 60
  const pos = (t: string) => `${((minutes(t) - start) / (end - start)) * 100}%`
  const hours = Array.from({ length: (end - start) / 60 + 1 }, (_, i) => start + i * 60)

  function select(image: ImageSummary) {
    selectImage(image.image_id)
    // Önizleme ve analiz düğmesi Görüntü çekmecesinde; sol kenar boşsa onu aç.
    if (useOperasyon.getState().left.panel === null) openLeft("goruntu")
  }

  return (
    <section
      aria-label="Zaman akışı"
      className="flex min-h-[var(--zaman-akisi-yukseklik)] flex-col justify-center gap-1 border-t border-cizgi bg-[var(--zaman-akisi-zemin)] px-6 py-2"
    >
      <div className="flex items-baseline justify-between text-xs">
        <h2 className="font-bold tracking-wider text-metin-soluk uppercase">Günün görüntüleri</h2>
        <span className="text-metin-soluk">
          <kbd className="font-mono">←</kbd> <kbd className="font-mono">→</kbd> önceki / sonraki kare
        </span>
      </div>
      {images.status === "error" && <p className="text-xs text-metin-soluk">Görüntü listesi alınamadı.</p>}
      {list.length > 0 && (
        <div className="relative mx-2 h-12">
          <div aria-hidden className="absolute top-4 right-0 left-0 border-t border-cizgi" />
          <ol aria-label="Görüntüler, çekim anına göre" className="absolute inset-x-0 top-0 h-8">
            {list.map((image) => {
              const selected = image.image_id === selectedImageId
              const level = image.last_risk_level
              return (
                <li key={image.image_id} className="absolute top-0 -translate-x-1/2" style={{ left: pos(image.capture_time) }}>
                  <button
                    type="button"
                    onClick={() => select(image)}
                    aria-pressed={selected}
                    aria-label={`${image.image_id} · ${image.zone} · ${image.capture_time} · ${
                      level ? `son seviye ${RISK[level].label}` : "değerlendirilmedi"
                    }`}
                    title={`${image.image_id} · ${image.zone} · ${image.capture_time}${level ? ` · ${RISK[level].label}` : ""}`}
                    className={cn(
                      "flex h-8 w-4 items-center justify-center rounded-sm text-sm leading-none",
                      selected ? "bg-secim-zemin ring-2 ring-secim" : "hover:bg-kart",
                    )}
                  >
                    {level ? (
                      <SeviyeSekli level={level} />
                    ) : (
                      <span aria-hidden className="h-3 w-0.5 rounded bg-metin-soluk" />
                    )}
                  </button>
                </li>
              )
            })}
          </ol>
          {hours.map((h) => (
            <span
              key={h}
              aria-hidden
              className="absolute bottom-0 -translate-x-1/2 font-mono text-[11px] text-metin-soluk"
              style={{ left: `${((h - start) / (end - start)) * 100}%` }}
            >
              {hhmm(h)}
            </span>
          ))}
        </div>
      )}
      <SeciliKareSeridi />
    </section>
  )
}
