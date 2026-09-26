import { RISK, RISK_LEVELS } from "@/lib/labels"

/**
 * Harita lejantı. Bölge alanının yaklaşık olduğu burada ve Bölge tooltip'inde açıkça yazar.
 * Değerlendirme varsa Temas türleri, seviye şekilleri, rota ve duraklama da açıklanır; o zaman
 * harita Temas'lara yaklaştığı için lejant katlanmış başlar (üstlerini örtmesin), başlığından açılır.
 */
export function Lejant({ withContacts = false }: { withContacts?: boolean }) {
  return (
    <details
      key={withContacts ? "temaslar" : "sahne"}
      open={!withContacts}
      aria-label="Lejant"
      className="group absolute bottom-3 left-3 z-10 max-w-80 rounded-md border border-cizgi bg-yuzey/90 px-3 py-2 text-xs text-metin-ikincil"
    >
      <summary className="cursor-pointer font-bold text-metin select-none group-open:mb-1">Lejant</summary>
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
        {withContacts && (
          <>
            <li className="mt-1 flex flex-wrap gap-x-2 border-t border-cizgi pt-1">
              Seviye:
              {RISK_LEVELS.map((l) => (
                <span key={l} className={`harita-isaret--${l}`}>
                  {RISK[l].shape} <span className="text-metin-ikincil">{RISK[l].label}</span>
                </span>
              ))}
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden className="harita-lejant__temas harita-isaret--matched" />
              Eşleşmiş temas (tespit + track)
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden className="harita-lejant__temas harita-isaret--unregistered" />
              Kayıt dışı temas (track yok)
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden className="harita-lejant__temas harita-isaret--missed" />
              Kaçırılmış temas (tespit yok)
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden className="h-0 w-4 border-t-2 border-metin-ikincil" />
              Rota, çekim anına kadar (renk = seviye) · ok: son yön
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden className="harita-lejant__duraklama" />
              Duraklama (saat · süre)
            </li>
          </>
        )}
      </ul>
    </details>
  )
}
