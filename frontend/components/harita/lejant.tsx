/** Harita lejantı. Bölge alanının yaklaşık olduğu burada ve Bölge tooltip'inde açıkça yazar. */
export function Lejant() {
  return (
    <section
      aria-label="Lejant"
      className="absolute bottom-3 left-3 z-10 rounded-md border border-cizgi bg-yuzey/90 px-3 py-2 text-xs text-metin-ikincil"
    >
      <ul className="grid gap-1">
        <li className="flex items-center gap-2">
          <span aria-hidden className="harita-lejant__us" />
          Üs
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden className="h-0 w-4 border-t border-metin" />
          Üsse 1 km ve 3 km mesafe halkaları
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden className="harita-lejant__bolge" />
          Bölge merkezi
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden className="size-3 rounded-full border border-dashed border-metin-ikincil" />
          Yaklaşık bölge alanı (kesin sınır değil)
        </li>
      </ul>
    </section>
  )
}
