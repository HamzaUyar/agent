"use client"

import { ArrowDownUp, Play, RotateCcw } from "lucide-react"
import { useEffect, useMemo, useState } from "react"

import { SeviyeRozeti } from "@/components/operasyon/seviye-rozeti"
import { Button } from "@/components/ui/button"
import type { ImageSummary, RiskLevel } from "@/lib/api/types"
import { RISK, RISK_LEVELS } from "@/lib/labels"
import { cn } from "@/lib/utils"
import { useOperasyon } from "@/store/operasyon"

import { Onizleme } from "./onizleme"

const NOT_EVALUATED = "degerlendirilmedi"
type LevelFilter = RiskLevel | typeof NOT_EVALUATED | ""

/**
 * Görüntü çekmecesi: veri setindeki 40 Görüntü'den seçim (dosya yükleme yok: konumu ve çekim
 * anı bilinmeyen bir kare değerlendirilemez), seçili karenin önizlemesi ve analizi başlatma.
 */
export function GoruntuCekmecesi() {
  const images = useOperasyon((s) => s.images)
  const loadImages = useOperasyon((s) => s.loadImages)
  const selectedImageId = useOperasyon((s) => s.selectedImageId)
  const selectImage = useOperasyon((s) => s.selectImage)
  const [zone, setZone] = useState("")
  const [level, setLevel] = useState<LevelFilter>("")
  const [newestFirst, setNewestFirst] = useState(false)

  useEffect(() => {
    if (useOperasyon.getState().images.status === "idle") void loadImages()
  }, [loadImages])

  const all = useMemo(() => (images.status === "ready" ? images.data : []), [images])
  const zones = useMemo(() => [...new Set(all.map((i) => i.zone))].sort((a, b) => a.localeCompare(b, "tr")), [all])
  const shown = useMemo(() => {
    const filtered = all.filter(
      (i) =>
        (!zone || i.zone === zone) &&
        (!level || (level === NOT_EVALUATED ? !i.last_risk_level : i.last_risk_level === level)),
    )
    return newestFirst ? [...filtered].reverse() : filtered
  }, [all, zone, level, newestFirst])

  return (
    <div className="flex flex-col gap-3">
      <SeciliKare />

      <p className="text-xs text-metin-soluk">
        Yalnızca veri setindeki görüntüler değerlendirilebilir: konumu ve çekim anı bilinmeyen bir kare
        değerlendirilemez.
      </p>

      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-xs text-metin-soluk">
          Bölge
          <select
            value={zone}
            onChange={(e) => setZone(e.target.value)}
            className="rounded-md border border-cizgi bg-kart px-2 py-1 text-sm text-metin"
          >
            <option value="">Tümü</option>
            {zones.map((z) => (
              <option key={z} value={z}>
                {z}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-metin-soluk">
          Son seviye
          <select
            value={level}
            onChange={(e) => setLevel(e.target.value as LevelFilter)}
            className="rounded-md border border-cizgi bg-kart px-2 py-1 text-sm text-metin"
          >
            <option value="">Tümü</option>
            {[...RISK_LEVELS].reverse().map((l) => (
              <option key={l} value={l}>
                {RISK[l].shape} {RISK[l].label}
              </option>
            ))}
            <option value={NOT_EVALUATED}>Değerlendirilmedi</option>
          </select>
        </label>
        <Button variant="outline" size="sm" onClick={() => setNewestFirst((v) => !v)}>
          <ArrowDownUp />
          {newestFirst ? "Çekim anı: yeniden eskiye" : "Çekim anı: eskiden yeniye"}
        </Button>
      </div>

      {images.status === "loading" && <p className="text-metin-soluk">Görüntüler yükleniyor…</p>}
      {images.status === "error" && (
        <div role="alert" className="text-sm">
          Görüntü listesi alınamadı. <span className="text-metin-soluk">{images.message}</span>
          <Button className="ml-2" size="xs" variant="outline" onClick={() => void loadImages()}>
            Tekrar dene
          </Button>
        </div>
      )}
      {images.status === "ready" && (
        <>
          <p className="text-xs text-metin-soluk" aria-live="polite">
            {shown.length} / {all.length} görüntü
          </p>
          <ul aria-label="Görüntüler" className="grid grid-cols-[repeat(auto-fill,minmax(9.5rem,1fr))] gap-2">
            {shown.map((image) => (
              <li key={image.image_id}>
                <GoruntuKarti
                  image={image}
                  selected={image.image_id === selectedImageId}
                  onSelect={() => selectImage(image.image_id)}
                />
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

function GoruntuKarti({ image, selected, onSelect }: { image: ImageSummary; selected: boolean; onSelect: () => void }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      aria-label={`${image.image_id} · ${image.zone} · ${image.capture_time}${
        image.last_risk_level ? ` · son seviye ${RISK[image.last_risk_level].label}` : " · değerlendirilmedi"
      }`}
      className={cn(
        "flex w-full flex-col overflow-hidden rounded-md border bg-kart text-left",
        selected ? "border-secim ring-2 ring-secim" : "border-cizgi hover:border-metin-soluk",
      )}
    >
      <Onizleme imageId={image.image_id} alt="" lazy className="aspect-video w-full bg-yuzey object-cover" />
      <span className="flex flex-col gap-0.5 p-1.5 text-xs">
        <span className="font-mono text-metin">{image.image_id}</span>
        <span className="truncate text-metin-ikincil">{image.zone}</span>
        <span className="flex items-center justify-between gap-1">
          <span className="font-mono text-metin-soluk">{image.capture_time}</span>
          {image.last_risk_level ? (
            <SeviyeRozeti level={image.last_risk_level} />
          ) : (
            <span className="text-metin-soluk">değerlendirilmedi</span>
          )}
        </span>
      </span>
    </button>
  )
}

/** Seçili karenin büyük önizlemesi ve analiz düğmesi. */
function SeciliKare() {
  const selectedImageId = useOperasyon((s) => s.selectedImageId)
  const images = useOperasyon((s) => s.images)
  const detail = useOperasyon((s) => s.imageDetail)
  const evaluation = useOperasyon((s) => s.evaluation)
  const startEvaluation = useOperasyon((s) => s.startEvaluation)

  if (!selectedImageId) {
    return <p className="text-metin-soluk">Kare seçilmedi. Aşağıdan ya da zaman akışından bir kare seçin.</p>
  }
  const summary = images.status === "ready" ? images.data.find((i) => i.image_id === selectedImageId) : undefined
  const streaming = evaluation?.status === "streaming"
  const hasResult = evaluation?.status === "done"
  const aspect = detail.status === "ready" ? `${detail.data.width_px} / ${detail.data.height_px}` : "16 / 9"

  return (
    <section aria-label="Seçili karenin önizlemesi" className="flex flex-col gap-2">
      <div className="relative overflow-hidden rounded-md border border-cizgi bg-yuzey" style={{ aspectRatio: aspect }}>
        <Onizleme
          imageId={selectedImageId}
          alt={`${selectedImageId} drone karesi`}
          className="absolute inset-0 h-full w-full object-contain"
        />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-mono font-bold">{selectedImageId}</span>
        {summary && (
          <>
            <span className="text-metin-ikincil">{summary.zone}</span>
            <span className="font-mono text-metin-ikincil">{summary.capture_time}</span>
          </>
        )}
      </div>
      {!hasResult && (
        <Button onClick={() => void startEvaluation(false)} disabled={streaming}>
          <Play />
          {streaming
            ? "Değerlendiriliyor…"
            : summary?.last_risk_level
              ? "Sonucu aç (önbellek)"
              : "Risk analizini başlat"}
        </Button>
      )}
      {hasResult && (
        <Button variant="outline" onClick={() => void startEvaluation(true)}>
          <RotateCcw />
          Yeniden değerlendir
        </Button>
      )}
    </section>
  )
}
