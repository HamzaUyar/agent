# Operasyon ekranı: tasarım kararları

> Bu dosya `../MASTER.md`'yi (ui-ux-pro-max çıktısı, 26 Eylül) **geçersiz kılar**. MASTER'da kalan ama burada reddedilen öneriler uygulanmaz.
> Kaynaklar: ui-ux-pro-max `--design-system "real-time operations monitoring console dark"` (variance 3, motion 2, density 8), dar sorgular (`severity status color blind`, `drawer panel focus trap`, `real-time status stale`), PDF 2 · Arayüz Fikirleri (Konsept A), `.scratch/operasyon-ekrani/spec.md`.
> Token'ların tek kaynağı `app/globals.css`.

## Kabul edilenler
- **Stil:** Minimalism & Swiss. Sade kartlar, net hiyerarşi, ızgara. Efekt yok; geçişler 150–250 ms. Hareket azaltma tercihinde geçişler kapalı.
- **Tema:** Koyu (varsayılan; karanlık oda, projektör) ve açık. Anahtar üst çubuğun en sağında; seçim tarayıcıda saklanır ve sayfa boyanmadan önce uygulanır. Tema yalnızca anlamlı token katmanını değiştirir.
- **Zemin:** Nötr, hafif serin tonlar; mor ve neon yok. İki tema ayrı tasarlandı (biri ötekinin tersi değil): zemin < yüzey < kart katmanları her temada ayrışır.
  | | Koyu | Açık |
  |---|---|---|
  | Zemin / yüzey / kart | `#0e1217` / `#151a21` / `#1c222b` (antrasit, saf siyah değil) | `#eceff3` / `#f7f8fa` / `#ffffff` |
  | Çizgi / güçlü çizgi (form denetimi) | `#2e3743` / `#647082` | `#d6dce3` / `#858f9c` |
  | Metin / ikincil / soluk | `#e7ebf0` / `#b4beca` / `#8a95a3` | `#121821` / `#3c4654` / `#5b6573` |

  Soluk metin bile her yüzeyde ≥ 4.5:1.
- **Yoğunluk:** Yüksek (dashboard). Gövde 14 px, en küçük yazı 12 px.
- **Erişilebilirlik:**
  - Bilgi yalnızca renkle verilmez.
  - Odak göstergesi 2 px, `--odak` renginde, 2 px boşluklu.
  - Canlı durumlar tek bir anlamlı `role="status"` mesajıyla duyurulur (çıplak sayı değil).

## Reddedilenler
| Öneri | Neden |
|---|---|
| Kalıp: "Real-Time / Operations Landing" (hero, metrikler, CTA) | Bu bir pazarlama sayfası değil, tek ekranlı operasyon aracı. Yerleşim Konsept A. |
| Vurgu rengi yeşil `#22C55E` | Yeşil düşük risk seviyesinin rengi; vurgu olarak karışır. |
| Hazır "Financial / Ride Hailing Dashboard" paletleri (lacivert-slate, `#2563EB` vurgu) | Vurgu mavisi seçimle, lacivert zemin "AI paneli" görünümüyle çakışır; palet anlamlardan türetildi. |
| Font Cinzel + Josefin Sans | Gayrimenkul/lüks için önerilmiş, okunabilirliği düşük. |
| GSAP scroll reveal | Kaydırılan bir sayfa yok; operasyon ekranında dikkat dağıtır. |
| Glassmorphism, neon, bilim-kurgu efektleri | PDF 2 kararı: okunabilirliği düşürür. |

## Kararlar
- **Font:** Atkinson Hyperlegible, metin için. İlk sorgunun erişilebilirlik odaklı önerisi. JetBrains Mono, koordinat, saat ve kimlikler için.
- **Renk = anlam.** Her renk ailesinin tek görevi var; bir renk iki şey anlatmaz.
  | Renk | Görevi | Kullanılmadığı yer |
  |---|---|---|
  | Mavi `--secim` (koyu `#6aa5f7`, açık `#1c62d4`) | Kullanıcının seçtiği veri: kare kartı, zaman akışındaki kare, ayak izi, seçili temas; odak halkası | Eylem düğmeleri, etkin sekme, bölge |
  | Mürekkep `--birincil` | Birincil eylem düğmesi (tek), etkin sekme / zemin anahtarı / çekmece sekmesi, ipucu | Veri |
  | Kırmızı → yeşil `--seviye-*` | Yalnızca risk seviyesi | Rota, kutu, hata (hata nötr kart + simge) |
  | Camgöbeği / mor / gül / limon `--sinif-*` | Yalnızca araç sınıfı (otomobil / minibüs / kamyon / otobüs); tipi bilinmeyen nötr | Seviye, seçim |
  | Nötr kesikli `--bolge-*` | Yaklaşık bölge alanı | — |
  | Soluk mono `--metin-soluk` | Koordinat, saat, halka etiketi, metaveri | — |
- **Birincil eylem mavi değil:** mavi yalnızca seçimdir. Düğme hiyerarşisi: birincil (mürekkep dolgu) · ikincil (`outline`, çerçeveli kart) · hayalet (simge düğmeleri) · yıkıcı. Her birinde üzerine gelme, basılı (1 px iniş), devre dışı (%45) ve odak (2 px `--odak`, 2 px boşluk) durumu var; seçim halkası boşluksuzdur, odaktan böyle ayrılır.
- **Risk skalası:** Bütün seviyeler aynı baklava ailesi (operatör kararı korunur), ama renk tek kanal değil: **baklavanın dolgusu seviyeyle artar** (düşük boş · orta yarı dolu · yüksek dolu · kritik dolu + dış halka · değerlendirilmedi kesikli gri; `.seviye-simge`, `.seviye--<level>`). Rozetin vurgusu da artar: düşük yalnız çerçeve, orta/yüksek açık dolgu, kritik tam dolgu. Yanında her zaman kelime ya da erişilebilir ad. `◆` karakteri metin içeriğinde kalır, şekli CSS çizer.
  | Seviye | Koyu | Açık |
  |---|---|---|
  | Düşük (yeşil) | `#5cc58c` | `#2d7a4c` |
  | Orta (amber) | `#e3bf4e` | `#876500` |
  | Yüksek (turuncu) | `#f29450` | `#ad4f08` |
  | Kritik (kırmızı) | `#f47272` | `#c42b2b` |

  Açık temada her seviye rengi kendi açık dolgusunda ve beyaz kartta ≥ 4.5:1. Kırmızı yalnızca kritik için; rapor kararı "çelişkili" de kırmızı değil (mürekkep dolgu + uyarı simgesi).
- **Görsel kanallar (görüntü kutusu, harita noktası, temas satırı, lejant aynı dili konuşur):**
  - Renk = araç sınıfı.
  - Çizgi = takip durumu: düz = eşleşmiş (tespit + track), kesikli = kayıt dışı (track yok), noktalı = kaçırılmış (tespit yok; tipi bilinmez, nötr).
  - Baklava dolgusu = seviye (etikette/rozette).
  - Seçim = mavi halka/çerçeve (haritada ve listede); görüntüde kalın çizgi + beyaz/siyah çift hale, diğer kutular soluklaşır.
- **Tespit kutuları (görüntü üzerinde):** sınıf renginde, siyah kılıflı (her fotoğraf zemininde ayrışır). Zayıf tespit ince çizgi ve etikette "zayıf". Etiket koyu yarı saydam çip; seçili kutuda sınıf renginde dolu. Katman temadan bağımsız, koyu token'larla çizilir.
- **Harita zemini:** Sokak zemini iki temada da OpenFreeMap `positron` vektör stili; katmanları `--harita-*` token'larıyla stil JSON'unda yeniden boyanır (CSS filtresi yok). Açık tema: sıcak açık gri kara, beyaz kılıflı yollar, düşük doygunlukta su ve yeşil alan, belirgin yapı blokları. Koyu tema: antrasit kara, karadan ayrışan yollar, belirgin ana yollar, koyu çelik mavisi su. Yol kalkanları ve tek yön okları gizli, büyük yerleşim adları soluk. Zemin her zaman verimizin gerisinde kalır.
- **Harita önem sırası:** seçili temas (mavi halka, kalın rota) > temaslar (sınıf renkli nokta ve rota) > ayak izi (mavi, düz, kalın) > seçili bölge (koyu dolgu, kalın kesikli) > diğer bölgeler (çok hafif dolgu, ince kesikli) > Üs halkaları (ince, soluk) > metaveri (duraklama, rota saatleri: küçük soluk mono) > zemin. Bir temas seçiliyken diğer rotalar soluklaşır ve yalnızca seçili temasın saat/duraklama etiketleri çizilir.
- **Bölge alanları:** Üs merkezli pasta dilimleri; 1 km halkasından başlar. Backend kareyi en yakın Bölge merkezine atadığı için Bölge dışa doğru sınırsızdır; dilimler merkezden komşu merkez aralığı kadar uzanır (veri setinin en uzak karesi dahil) ve seçili karenin köşelerini her durumda kapsar. Üs simgesi kare (baklava seviyenin simgesi).
- **Açılır seçim (Bölge, Son seviye):** yerel `<select>` yerine Radix Select (`components/ui/select.tsx`); yerel menü seçeneklere renk veremiyordu. Seviye seçenekleri rozetin kendisidir; kapalı kutu seçili rozeti gösterir. Açık listedeyken tuşlar (harfle arama, oklar, Esc) genel kısayollara gitmez.
- **Zaman akışı:** kare işareti seviye baklavası (dolgulu), değerlendirilmemiş kare ince nötr çentik; üzerine gelince nötr dolgu, seçili kare mavi halka. Seçili karenin şeridinde çekim anı mürekkep çizgi, sonrası taralı ve kapalı; rota noktaları ve duraklama seçili temasın sınıf renginde, rapor işareti kare (baklava değil).
- **Rozetler:**
  - "Önbellek": `--veri-bayat`, gri.
  - "Otomatik özet": `--otomatik-ozet`, kum rengi. Sarı değil, çünkü orta seviyeyle karışır.
- **Token adları:** `--zemin/--yuzey/--kart/--kart-vurgu/--kart-hover`, `--cizgi/--cizgi-guclu`, `--metin/-ikincil/-soluk`, `--birincil*`, `--secim*`, `--odak`, `--hata`, `--seviye-<level>[-zemin]`, `--sinif-<car|van|truck|bus|diger>`, `--bolge-*`, `--harita-*`, `--golge*`, `--veri-bayat`, `--otomatik-ozet`, `--tespit-*`, bileşen token'ları `--ust-cubuk-*`, `--harita-paneli-*`, `--cekmece-*`, `--zaman-akisi-*`.
  - Üç katman: `--ham-*` → anlamlı → bileşen.
  - shadcn değişkenleri anlamlı katmana bağlıdır.
- **Kenar ikon rayı:** Kenar sekmeleri aynı çizgi kalınlığında lucide ikonları (18 px, çizgi 1,75); adı ve kısayolu Radix ipucunda, erişilebilir ad metinle aynı. Etkin ikon ters renk (mürekkep) + çekmeceye bakan kenarda ince çizgi; mavi kullanılmaz. Sol: Görüntü (`Image`, G). Sağ, yukarıdan: İz analizi (`Route`, I), Risk & Araçlar (`ShieldAlert`, R). Brief'in ayrı kenar düğmesi yok (Risk & Araçlar içindeki sekme, B kısayolu). Kapalı Risk ikonunda son Brief'in seviye baklavası görünür.
- **Çekmeceler:** shadcn `Sheet` kullanılmadı; çekmeceler sayfa düzeninin parçası olan paneller, harita onlar kadar daralır.
  - Genişlik serbest: tutamaç işaretçiyi yakalar, genişlik imleci anında izler (sürüklerken geçiş yok), bırakıldığı yerde kalır ve taraf başına saklanır. En az 280 px, en fazla ekranın %50'si ve haritaya en az 400 px kalacak kadar. Tutamaç çekmecenin içinde (haritaya taşmaz), klavyede ←/→ 16 px, Home/End sınırlar. Genişlet düğmesi (ya da tutamaca çift tık) geniş görünüm ↔ son genişlik. Dar "göz atma" hâli kaldırıldı (ikon rayı o işi görür).
  - Kenar başına tek çekmece. Esc önce İz analizi vurgusunu, sonra en son açılan çekmeceyi kapatır. Odak başlığa taşınır, kapanınca açan öğeye döner.
- **Günün görüntüleri:** başlangıçta katlı: 40 px çubukta başlık, kare sayısı, seçili kare; chevron açar (yükseklik geçişi 200 ms). Kapalı içerik `inert`. ←/→ kapalıyken de kare değiştirir. Durum saklanır.
- **Lejant:** sol altta her zaman görünen küçük kutu, yalnızca araç sınıfı renkleri. Diğer kodlamalar rozet ve ipuçlarında.
- **Uydu/Sokak:** sol üstte, yakınlaştırma düğmelerinin yanında; sağ üst İz analizi kartının.
- **İz analizi:** haritanın sağ üstünde, haritayı daraltmayan opak kart (320 px, en fazla haritanın %45 genişliği / %60 yüksekliği). Sıra: seviye süzgeci (çoklu seçim + Hepsi, sayılı; seçili anahtar rozet dilinde ve işaretli) → track sayısı ("50 / 226 track · şu an 18 araç") → büyük saat → yoğunluk göstergeli zaman çizgisi → Oynat/Duraklat · Sıfırla · hız (0,5×–4×; 1× = saniyede 5 dk) → vurgulanan track ("Görüntüye git").
  - Hazır hâli: filtreli bütün track'ler tam yolla, hareketsiz; çizgi sınıf renginde, 1,25 px, %40 opak.
  - Oynatma: yalnızca kaydı o anı kapsayan araçlar; baş noktası sınıf renginde nokta + seviye baklavası (tuvalde, tema token'larından); 15 dk kuyruk. Kayıtlar arası doğrusal ara konum; kaydın dışında araç yok.
  - Vurgu: kalın ve opak, diğerleri %12. Açıkken seçili Görüntü'nün temasları ve rotaları soluk.
  - Oynatma döngüsü (`requestAnimationFrame`) katmanı doğrudan haritaya yazar; depoya yalnızca dakika değişince yazılır.
- **Araçlar listesi:** satır = track · sınıf karesi (dolgu sınıf, çerçeve çizgisi takip durumu) · seviye rozeti · üsse mesafe. Üstte "Tespit güvenilirliği" özeti (Yüksek/Orta/Düşük kesinlik sayıları, süzgeç). Aynı araca verilmiş ikinci sınıf (kutusu IoU ≥ 0,7 örtüşen, düşük güvenli tespit) görüntüde çizilmez, listede soluk ve açıklamalı.
- **Tespit kutuları:** çerçeve kutunun içinde (kutu hiçbir zaman modelin alanından büyük görünmez); gösterilen kısa kenar 16 px'ten küçükse 1 px çizgi, iç kılıf yok.
- **Brief:** karar kartı (seviye + önerilen eylem + kare özeti) → paragraflara bölünmüş değerlendirme → katlanır Kaynaklar ve Model.
