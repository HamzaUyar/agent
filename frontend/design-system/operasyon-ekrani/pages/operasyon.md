# Operasyon ekranı: tasarım kararları

> Bu dosya `../MASTER.md`'yi (ui-ux-pro-max çıktısı, 26 Eylül) **geçersiz kılar**. MASTER'da kalan ama burada reddedilen öneriler uygulanmaz.
> Kaynaklar: ui-ux-pro-max `--design-system "real-time operations monitoring console dark"` (variance 3, motion 2, density 8), dar sorgular (`severity status color blind`, `drawer panel focus trap`, `real-time status stale`), PDF 2 · Arayüz Fikirleri (Konsept A), `.scratch/operasyon-ekrani/spec.md`.
> Token'ların tek kaynağı `app/globals.css`.

## Kabul edilenler
- **Stil:** Minimalism & Swiss. Sade kartlar, net hiyerarşi, ızgara. Efekt yok; geçişler 150–250 ms. Hareket azaltma tercihinde geçişler kapalı.
- **Zemin:** Koyu lacivert-nötr (`#0a101c` zemin, `#0f172a` yüzey, `#1b2336` kart, `#3a465c` çizgi). Metin `#f1f5f9`, soluk metin `#94a3b8`.
- **Yoğunluk:** Yüksek (dashboard). Gövde 14 px, en küçük yazı 12 px.
- **Erişilebilirlik:**
  - Bilgi yalnızca renkle verilmez.
  - Odak göstergesi 2 px, `--secim` renginde.
  - Canlı durumlar tek bir anlamlı `role="status"` mesajıyla duyurulur (çıplak sayı değil).

## Reddedilenler
| Öneri | Neden |
|---|---|
| Kalıp: "Real-Time / Operations Landing" (hero, metrikler, CTA) | Bu bir pazarlama sayfası değil, tek ekranlı operasyon aracı. Yerleşim Konsept A. |
| Vurgu rengi yeşil `#22C55E` | Yeşil "güvenli" gibi okunur ve risk skalasıyla karışır. |
| Font Cinzel + Josefin Sans | Gayrimenkul/lüks için önerilmiş, okunabilirliği düşük. |
| GSAP scroll reveal | Kaydırılan bir sayfa yok; operasyon ekranında dikkat dağıtır. |
| Glassmorphism, neon, bilim-kurgu efektleri | PDF 2 kararı: okunabilirliği düşürür. |

## Kararlar
- **Font:** Atkinson Hyperlegible, metin için. İlk sorgunun erişilebilirlik odaklı önerisi. JetBrains Mono, koordinat, saat ve kimlikler için.
- **Seçim rengi:** Gök mavisi `#38bdf8`. PDF 2 amber öneriyordu, ama amber orta (sarı) ve yüksek (turuncu) seviyeyle karışıyor. Seçim tek vurgu rengi.
- **Risk skalası:** Renk, şekil ve kelime birlikte kullanılır.
  | Seviye | Renk | Şekil |
  |---|---|---|
  | Düşük | `#8b9bb4` | ● |
  | Orta | `#e3b341` | ■ |
  | Yüksek | `#f0883e` | ▲ |
  | Kritik | `#f85149` | ◆ |

  Kırmızı yalnızca kritik için. Kesinlik ayrı bir metin etiketidir.
- **Rozetler:**
  - "Önbellek": `--veri-bayat`, gri.
  - "Otomatik özet": `--otomatik-ozet`, mor. Sarı değil, çünkü orta seviyeyle karışır.
- **Token adları:** `--risk-dusuk/orta/yuksek/kritik`, `--secim`, `--veri-bayat`, `--otomatik-ozet`, `--ust-cubuk-*`, `--harita-paneli-*`, `--cekmece-*`, `--zaman-akisi-*`.
  - Üç katman: `--ham-*` → anlamlı → bileşen.
  - shadcn değişkenleri anlamlı katmana bağlıdır.
- **Çekmeceler:** shadcn `Sheet` kullanılmadı. Sheet ekranın üstüne açılan bir katman, haritayı daraltmaz. Çekmeceler sayfa düzeninin parçası olan paneller.
  - Genişlikler: göz atma 56 px, yarım %30, tam %55.
  - Kenar başına tek çekmece.
  - Esc en son açılanı kapatır. Odak başlığa taşınır, kapanınca açan öğeye döner.
