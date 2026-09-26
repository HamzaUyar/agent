import { SeviyeSimgesi } from "@/components/operasyon/seviye-rozeti"
import { RISK, RISK_LEVELS, VEHICLE_CLASS } from "@/lib/labels"

const TONES = Object.entries(VEHICLE_CLASS) as [keyof typeof VEHICLE_CLASS & string, string][]

function Baslik({ children }: { children: string }) {
  return (
    <li className="mt-1.5 border-t border-cizgi pt-1.5 text-[11px] font-bold tracking-wider text-metin-soluk uppercase">
      {children}
    </li>
  )
}

/**
 * Harita lejantı. Bölge alanının yaklaşık olduğu burada ve Bölge tooltip'inde açıkça yazar.
 * Değerlendirme varsa her görsel kanal ayrı açıklanır: renk = araç sınıfı, çizgi = takip durumu,
 * baklava dolgusu = seviye. O zaman harita Temas'lara yaklaştığı için lejant katlanmış başlar
 * (üstlerini örtmesin), başlığından açılır.
 */
export function Lejant({ withContacts = false }: { withContacts?: boolean }) {
  return (
    <details
      key={withContacts ? "temaslar" : "sahne"}
      open={!withContacts}
      aria-label="Lejant"
      className="group absolute bottom-3 left-3 z-10 max-h-[calc(100%-1.5rem)] max-w-80 overflow-y-auto rounded-md border border-cizgi bg-yuzey px-3 py-2 text-xs text-metin-ikincil shadow-golge-yuksek"
    >
      <summary className="font-bold text-metin select-none group-open:mb-1">Lejant</summary>
      <ul className="grid gap-1">
        <li className="flex items-center gap-2">
          <span aria-hidden className="harita-lejant__us" />
          Üs
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden className="h-0 w-4 border-t-[1.5px] border-metin-ikincil" />
          Üsse 1 km ve 3 km mesafe halkaları
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden className="harita-lejant__ayak-izi" />
          Seçili görüntünün kapladığı alan
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden className="harita-lejant__dilim harita-lejant__dilim--secili" />
          Seçili görüntünün bölgesi
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden className="harita-lejant__dilim" />
          Yaklaşık bölge alanı: Üs&apos;ten yön dilimi (kesin sınır değil)
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden className="harita-lejant__bolge" />
          Bölge merkezi
        </li>
        {withContacts && (
          <>
            <Baslik>Renk: araç sınıfı</Baslik>
            <li className="flex flex-wrap gap-x-3 gap-y-1">
              {TONES.map(([tone, label]) => (
                <span key={tone} className="flex items-center gap-1">
                  <span aria-hidden className={`sinif-renk sinif--${tone}`} />
                  {label}
                </span>
              ))}
              <span className="flex items-center gap-1">
                <span aria-hidden className="sinif-renk sinif--diger" />
                tip bilinmiyor
              </span>
            </li>
            <Baslik>Çizgi: takip durumu</Baslik>
            <li className="flex items-center gap-2">
              <span aria-hidden className="harita-lejant__temas" />
              <span>Eşleşmiş temas (tespit + track)</span>
              <span className="text-metin-soluk">düz</span>
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden className="harita-lejant__temas harita-lejant__temas--unregistered" />
              <span>Kayıt dışı temas (track yok)</span>
              <span className="text-metin-soluk">kesikli</span>
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden className="harita-lejant__temas harita-lejant__temas--missed" />
              <span>Kaçırılmış temas (tespit yok)</span>
              <span className="text-metin-soluk">noktalı</span>
            </li>
            <li className="flex items-center gap-2">
              <span aria-hidden className="harita-lejant__secili" />
              Seçili temas
            </li>
            <Baslik>Seviye: baklava dolgusu</Baslik>
            <li className="flex flex-wrap gap-x-3 gap-y-1">
              {[...RISK_LEVELS].reverse().map((l) => (
                <span key={l} className="flex items-center gap-1">
                  <SeviyeSimgesi level={l} />
                  {RISK[l].label}
                </span>
              ))}
            </li>
            <Baslik>Hareket</Baslik>
            <li className="flex items-center gap-2">
              <span aria-hidden className="h-0 w-4 border-t-[2.5px] border-metin-ikincil" />
              Rota, çekim anına kadar (renk = sınıf) · ok: son yön
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
