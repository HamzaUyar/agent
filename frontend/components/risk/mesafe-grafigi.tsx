import { formatDistance } from "@/lib/format"
import type { DistancePoint } from "@/lib/temas"

const W = 280
const H = 64
const PAD = 4

/**
 * Üs'e mesafenin çekim anına kadarki mini grafiği. Saat varsa x ekseni saat, yoksa (eski önbellek
 * kaydı) nokta sırası. Aşağı inen çizgi yaklaşma demektir.
 */
export function MesafeGrafigi({ series }: { series: DistancePoint[] }) {
  if (series.length < 2) return null
  const max = Math.max(...series.map((p) => p.meters))
  const min = Math.min(...series.map((p) => p.meters))
  const span = max - min || 1
  const points = series
    .map((p, i) => {
      const x = PAD + (i / (series.length - 1)) * (W - 2 * PAD)
      const y = PAD + ((p.meters - min) / span) * (H - 2 * PAD)
      return `${x.toFixed(1)},${(H - y).toFixed(1)}`
    })
    .join(" ")
  const first = series[0]
  const last = series.at(-1)!
  const timed = first.time !== null && last.time !== null
  const summary = timed
    ? `Üsse mesafe ${first.time}'da ${formatDistance(first.meters)}, ${last.time}'da ${formatDistance(last.meters)}`
    : `Üsse mesafe ${formatDistance(first.meters)}'den ${formatDistance(last.meters)}'ye (saat bilgisi yok)`

  return (
    <figure className="mt-1 flex flex-col gap-0.5">
      <svg role="img" aria-label={summary} viewBox={`0 0 ${W} ${H}`} className="h-16 w-full" preserveAspectRatio="none">
        {/* Nötr mürekkep: mavi seçim, renkler sınıf/seviye için ayrılmış. */}
        <polyline points={`${PAD},${H} ${points} ${W - PAD},${H}`} fill="var(--kart-vurgu)" stroke="none" />
        <polyline points={points} fill="none" stroke="var(--metin-ikincil)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
      </svg>
      <figcaption className="flex justify-between font-mono text-[11px] text-metin-soluk">
        <span>
          {timed ? first.time : "başlangıç"} · {formatDistance(first.meters)}
        </span>
        <span>
          {timed ? last.time : "çekim anı"} · {formatDistance(last.meters)}
        </span>
      </figcaption>
    </figure>
  )
}
