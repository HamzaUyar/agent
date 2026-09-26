# Operasyon ekranı: tasarım kararları

> Bu dosya `../MASTER.md`'yi (ui-ux-pro-max çıktısı, 26 Eylül) **geçersiz kılar**. MASTER'da kalan ama burada reddedilen öneriler uygulanmaz.
> Kaynaklar: ui-ux-pro-max `--design-system "real-time operations monitoring console dark"` (variance 3, motion 2, density 8), dar sorgular (`severity status color blind`, `drawer panel focus trap`, `real-time status stale`), PDF 2 · Arayüz Fikirleri (Konsept A), `.scratch/operasyon-ekrani/spec.md`.
> Token'ların tek kaynağı `app/globals.css`.

## Kabul edilenler
- **Stil:** Minimalism & Swiss. Sade kartlar, net hiyerarşi, ızgara. Efekt yok; geçişler 150–250 ms. Hareket azaltma tercihinde geçişler kapalı.
- **Tema:** Koyu (varsayılan; karanlık oda, projektör) ve açık. Anahtar üst çubuğun en sağında; seçim tarayıcıda saklanır ve sayfa boyanmadan önce uygulanır. Tema yalnızca anlamlı token katmanını değiştirir.
- **Zemin:** Nötr tonlar; lacivert-gri ve mor yok ("AI paleti" görünümünden kaçınıldı).
  | | Koyu | Açık |
  |---|---|---|
  | Zemin / yüzey / kart | `#101214` / `#16191c` / `#22262a` (grafit) | `#ecebe6` / `#f6f5f1` / `#ffffff` (kâğıt) |
  | Çizgi | `#43484e` | `#c9c6be` |
  | Metin / soluk metin | `#eeece7` / `#8e8c86` | `#1c1d1f` / `#63666a` |
- **Yoğunluk:** Yüksek (dashboard). Gövde 14 px, en küçük yazı 12 px.
- **Erişilebilirlik:**
  - Bilgi yalnızca renkle verilmez.
  - Odak göstergesi 2 px, `--secim` renginde.
  - Canlı durumlar tek bir anlamlı `role="status"` mesajıyla duyurulur (çıplak sayı değil).

## Reddedilenler
| Öneri | Neden |
|---|---|
| Kalıp: "Real-Time / Operations Landing" (hero, metrikler, CTA) | Bu bir pazarlama sayfası değil, tek ekranlı operasyon aracı. Yerleşim Konsept A. |
| Vurgu rengi yeşil `#22C55E` | Yeşil düşük risk seviyesinin rengi; vurgu olarak karışır. |
| Font Cinzel + Josefin Sans | Gayrimenkul/lüks için önerilmiş, okunabilirliği düşük. |
| GSAP scroll reveal | Kaydırılan bir sayfa yok; operasyon ekranında dikkat dağıtır. |
| Glassmorphism, neon, bilim-kurgu efektleri | PDF 2 kararı: okunabilirliği düşürür. |

## Kararlar
- **Font:** Atkinson Hyperlegible, metin için. İlk sorgunun erişilebilirlik odaklı önerisi. JetBrains Mono, koordinat, saat ve kimlikler için.
- **Seçim rengi:** Çelik mavisi (koyu `#5aa2dc`, açık `#1f66a3`). PDF 2 amber öneriyordu, ama amber orta (sarı) ve yüksek (turuncu) seviyeyle karışıyor. Seçim tek vurgu rengi.
- **Risk skalası:** Bütün seviyeler aynı simgeyi (◆ baklava) kullanır; seviye renkle ve kelimeyle verilir. Dar yerlerde (zaman akışı) kelime erişilebilir ad ve ipucundadır. Açık temada renkler beyaz zeminde okunacak kadar koyudur.
  | Seviye | Koyu | Açık |
  |---|---|---|
  | Düşük (yeşil) | `#4cb963` | `#257a38` |
  | Orta (sarı) | `#f2c230` | `#9a7400` |
  | Yüksek (turuncu) | `#f28a2e` | `#b85a0c` |
  | Kritik (kırmızı) | `#f0514a` | `#c0272d` |

  Kırmızı yalnızca kritik için. Kesinlik ayrı bir metin etiketidir. (Önceki karar: seviye başına ayrı şekil ve gri düşük; operatör isteğiyle değişti.)
- **Tespit kutuları (görüntü üzerinde):** Seviyeden bağımsız tek renk: siyah kılıflı beyaz, her zeminde seçilir. Seçili kutu çelik mavisi `#5aa2dc` ve kalın. Seviye etiketteki renkli baklavada. Katman fotoğrafın üstünde olduğu için temadan bağımsız koyu token'larla çizilir.
- **Harita:** Varsayılan zemin sokak (OpenFreeMap; koyu temada `dark`, açık temada gri tonlu `positron` stili; renkli sokak haritası seviye renkleriyle karışır). Bölge alanları Üs merkezli pasta dilimleri: her Bölge, Üs'ten bakınca merkezine en yakın yön aralığını alır; dilimler 1 km halkasından başlar (Üs dairesi boş kalır). Komşu dilimler sırayla açık/koyu dolgu, sınır kesikli (kesin sınır değil); seçili karenin Bölge dilimi seçim renginde.
- **Rozetler:**
  - "Önbellek": `--veri-bayat`, gri.
  - "Otomatik özet": `--otomatik-ozet`, kum rengi. Sarı değil, çünkü orta seviyeyle karışır.
- **Token adları:** `--risk-dusuk/orta/yuksek/kritik`, `--secim`, `--veri-bayat`, `--otomatik-ozet`, `--tespit-kutu*`, `--harita-kilif`, `--harita-duz-zemin`, `--ust-cubuk-*`, `--harita-paneli-*`, `--cekmece-*`, `--zaman-akisi-*`.
  - Üç katman: `--ham-*` → anlamlı → bileşen.
  - shadcn değişkenleri anlamlı katmana bağlıdır.
- **Çekmeceler:** shadcn `Sheet` kullanılmadı. Sheet ekranın üstüne açılan bir katman, haritayı daraltmaz. Çekmeceler sayfa düzeninin parçası olan paneller.
  - Genişlikler: göz atma 56 px, yarım %30, tam %55.
  - Solda yalnız Görüntü çekmecesi (Sohbet kaldırıldı). Risk analizi başlayınca Risk & Temaslar kapalıysa yarım açılır.
  - Kenar başına tek çekmece.
  - Esc en son açılanı kapatır. Odak başlığa taşınır, kapanınca açan öğeye döner.
