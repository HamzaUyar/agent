import { VEHICLE_CLASS } from "@/lib/labels"

const TONES = [...Object.entries(VEHICLE_CLASS), ["diger", "tip bilinmiyor"]] as const

/**
 * Harita lejantı: sol altta her zaman duran küçük kutu, yalnızca araç sınıfı renkleri (haritadaki
 * nokta, rota ve iz çizgileri ile görüntüdeki kutuların rengi). Diğer kodlamalar (seviye baklavası,
 * takip çizgisi, bölge) rozetlerde, ipuçlarında ve İz analizi kartında açıklanır.
 */
export function Lejant() {
  return (
    <section
      aria-label="Lejant"
      className="pointer-events-auto absolute bottom-3 left-3 z-10 rounded-md border border-cizgi bg-yuzey/95 px-2.5 py-1.5 text-[11px] text-metin-ikincil shadow-golge"
    >
      <h3 className="sr-only">Araç sınıfı renkleri</h3>
      <ul className="grid grid-cols-[auto_auto] gap-x-3 gap-y-0.5">
        {TONES.map(([tone, label]) => (
          <li key={tone} className="flex items-center gap-1.5">
            <span aria-hidden className={`sinif-renk sinif--${tone}`} />
            {label}
          </li>
        ))}
      </ul>
    </section>
  )
}
