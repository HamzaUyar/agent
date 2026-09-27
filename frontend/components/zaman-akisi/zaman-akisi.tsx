"use client"

import { ChevronUp } from "lucide-react"

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
 * şekliyle. Başlangıçta katlı (ince çubuk); chevron açar/kapar. Her kare her zaman seçilebilir;
 * ←/→ panel kapalıyken de önceki/sonraki kare.
 */
export function ZamanAkisi() {
  const images = useOperasyon((s) => s.images)
  const selectedImageId = useOperasyon((s) => s.selectedImageId)
  const selectImage = useOperasyon((s) => s.selectImage)
  const openLeft = useOperasyon((s) => s.openLeft)
  const open = useOperasyon((s) => s.timelineOpen)
  const setOpen = useOperasyon((s) => s.setTimelineOpen)
  const summary = images.status === "ready" ? images.data.find((i) => i.image_id === selectedImageId) : undefined

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
      className="flex flex-col border-t border-cizgi bg-[var(--zaman-akisi-zemin)] px-6"
    >
      {/* Kapalıyken yalnızca bu ince çubuk: başlık, seçili kare, kare sayısı ve aç/kapa. */}
      <div className="flex h-10 items-center gap-3 text-xs">
        <button
          type="button"
          aria-expanded={open}
          aria-controls="gunun-goruntuleri"
          onClick={() => setOpen(!open)}
          className="-ml-2 flex items-center gap-1.5 rounded-md px-2 py-1 font-bold tracking-wider text-metin-ikincil uppercase transition-colors hover:bg-kart-hover hover:text-metin"
        >
          <ChevronUp
            aria-hidden
            strokeWidth={1.75}
            className={cn("size-4 transition-transform duration-200", open && "rotate-180")}
          />
          <h2>Günün görüntüleri</h2>
        </button>
        {list.length > 0 && <span className="text-metin-soluk">{list.length} kare</span>}
        {summary && (
          <span className="font-mono text-metin-ikincil">
            <span className="font-bold text-metin">{summary.image_id}</span> · {summary.zone} · {summary.capture_time}
          </span>
        )}
        <span className="ml-auto text-metin-soluk">
          <kbd className="rounded border border-cizgi bg-kart px-1 font-mono text-metin-ikincil">←</kbd>{" "}
          <kbd className="rounded border border-cizgi bg-kart px-1 font-mono text-metin-ikincil">→</kbd> önceki / sonraki kare
        </span>
      </div>
      {/* Yükseklik geçişi: 0fr ↔ 1fr; kapalıyken içerik erişilebilirlik ağacından da çıkar. */}
      <div
        id="gunun-goruntuleri"
        inert={!open}
        aria-hidden={!open}
        className={cn(
          "grid transition-[grid-template-rows] duration-200 ease-out",
          open ? "grid-rows-[1fr]" : "grid-rows-[0fr]",
        )}
      >
        <div className="flex min-h-0 flex-col gap-1 overflow-hidden">
          {images.status === "error" && <p className="text-xs text-metin-soluk">Görüntü listesi alınamadı.</p>}
          {list.length > 0 && (
            <div className="relative mx-2 h-12 shrink-0">
              <div aria-hidden className="absolute top-4 right-0 left-0 border-t border-cizgi-guclu/70" />
              {hours.map((h) => (
                <span
                  key={`c-${h}`}
                  aria-hidden
                  className="absolute top-3 h-2 w-px bg-cizgi-guclu"
                  style={{ left: `${((h - start) / (end - start)) * 100}%` }}
                />
              ))}
              <ol aria-label="Görüntüler, çekim anına göre" className="seviye-canli absolute inset-x-0 top-0 h-8">
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
                          "flex h-8 w-4 items-center justify-center rounded-sm text-sm leading-none transition-colors [--sv-bosluk:var(--yuzey)]",
                          selected
                            ? "bg-secim-zemin ring-2 ring-secim [--sv-bosluk:var(--secim-zemin)]"
                            : "hover:bg-kart-vurgu hover:ring-1 hover:ring-cizgi-guclu",
                        )}
                      >
                        {/* Seviye: baklava (dolgu seviyeyle artar). Değerlendirilmemiş kare: ince nötr çentik. */}
                        {level ? (
                          <SeviyeSekli level={level} className="[--sv-boyut:10px]" />
                        ) : (
                          <span aria-hidden className="h-2.5 w-0.5 rounded bg-cizgi-guclu" />
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
          <div className="pb-2">
            <SeciliKareSeridi />
          </div>
        </div>
      </div>
    </section>
  )
}
