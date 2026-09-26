# Spec: Operasyon Ekranı — harita, görüntü seçimi, risk analizi, temas incelemesi

Status: ready-for-agent

## Problem Statement

Backend bir Görüntü'yü çekim anı itibarıyla değerlendirip gerekçeli bir Brief üretiyor. Ama operatörün bunu kullanabileceği bir ekran yok: bugün değerlendirme ancak komut satırından başlatılıyor ve sonuç ham JSON olarak okunuyor. Operatör şunları göremiyor:

- Üs'ün, Bölge'lerin ve seçtiği Görüntü'nün haritadaki yeri.
- Günün 40 Görüntü'sünden hangisinin ne zaman ve nerede çekildiği, hangisinin daha önce değerlendirildiği ve hangi seviyede çıktığı.
- Değerlendirmenin adım adım ilerleyişi. LLM 45 saniyeye kadar sürebiliyor; ekranda bir şey görünmezse sistem donmuş gibi algılanıyor.
- Temas'ların çekim anındaki konumu, nereden geldikleri ve Üs'e göre eğilimleri.
- Bir Temas'ın neden o seviyede çıktığı: kural gerekçeleri, LLM ayarı ve ona bağlı Rapor kararları.
- Brief hakkında takip sorusu sorma imkânı.

Jüri puanının "Ürün ve UX" ile "Sunum ve Demo" bölümleri bu ekranla kazanılıyor. Case, sistemin en az 1–2 Görüntü üzerinde canlı çalışmasını istiyor.

## Solution

Tek sayfalık bir operasyon ekranı (PDF 2 · Konsept A):

- Üstte ince bir **durum çubuğu** var.
- Ortada sayfanın yaklaşık %60'ını kaplayan, kenarlarında boşluk bulunan çerçeveli bir **harita paneli** var.
- Altta iki şeritli bir **zaman akışı** var.
- Ayrıntılar kenarlardan açılan **çekmecelerde**. Sağda "Risk & Temaslar" (Temaslar ve Brief sekmeleri), solda "Görüntü" ve "Sohbet".

Operatörün yolu:

1. Ekran açılır. Haritada Üs, 1 ve 3 km halkaları, 8 Bölge merkezi ve her birinin yaklaşık bölge alanı görünür. Henüz analiz yoktur.
2. Operatör bir Görüntü seçer. Bunu Görüntü çekmecesindeki önizleme ızgarasından ya da alt zaman akışından yapabilir. Seçilen karenin önizlemesi büyür, haritada ayak izi çizilir ve harita o bölgeye yaklaşır.
3. "Risk analizini başlat" düğmesine basar. Adımlar üst çubukta ve Risk & Temaslar çekmecesinde canlı akar.
4. Brief gelir. Üst çubukta Görüntü seviyesi ve önerilen eylem görünür. Haritaya şunlar eklenir: Temas'lar, track'i olan Temas'ların rotaları, duraklamaları, son yönü ve eğilimi. Görüntü çekmecesinde tespit kutuları görünür.
5. Operatör bir Temas'a tıklar. Tıklama listeden, haritadaki işaretten ya da görüntüdeki kutudan olabilir. Harita, görüntü ve çekmece aynı Temas'a odaklanır. Detay kartı tespiti, eşleşmeyi, hareketi, seviye gerekçesini ve bağlı Rapor kararlarını gösterir.
6. "Bu temas hakkında sor" düğmesi, Sohbet çekmecesini hazır sorulu açar. Cevap, çağrılan araçlarla birlikte akar.

Ekran bir karar destek aracıdır: operatörün kararını kaydetmez. Çekim anından sonrası hiçbir panelde gösterilmez (ADR-0001).

## User Stories

### Açılış ve harita

1. Operatör olarak, ekran açıldığında Üs'ü, 8 Bölge'yi ve 1/3 km halkalarını tek bakışta görmek istiyorum; böylece sahneyi bir kare seçmeden önce tanırım.
2. Operatör olarak, haritanın açılışta Üs'ü ve bütün Bölge merkezlerini kapsayacak şekilde ortalanmasını istiyorum; böylece kaydırmadan genel resmi görürüm.
3. Operatör olarak, zeminde gerçek bir uydu görüntüsü görmek ve sokak haritasına geçebilmek istiyorum; böylece yolları ve yerleşimleri tanırım.
4. Operatör olarak, internet yokken haritanın düz koyu zemine düşmesini ve katmanların çalışmaya devam etmesini istiyorum; böylece demo ağ sorunundan etkilenmez.
5. Operatör olarak, her Bölge'nin adını ve yaklaşık alanını görmek istiyorum; böylece temasların hangi bölgede olduğunu sezgisel olarak anlarım.
6. Operatör olarak, Bölge alanının hem lejantta hem tooltip'te "yaklaşık alan" diye işaretlenmesini istiyorum; böylece onu kesin bir sınır sanmam.
7. Operatör olarak, haritanın sayfanın yalnızca bir bölümünü kaplamasını ve çekmeceler açıldığında daralıp kaybolmamasını istiyorum; böylece ayrıntıya bakarken konumu kaybetmem.
8. Operatör olarak, zeminin kaynağını (atıf) haritanın köşesinde görmek istiyorum; böylece lisans koşulları karşılanır.

### Görüntü seçimi

9. Operatör olarak, veri setindeki 40 Görüntü'yü küçük önizlemelerle bir ızgarada görmek istiyorum; böylece kareyi gözle seçebilirim.
10. Operatör olarak, her önizleme kartında görüntü kimliğini, Bölge'yi, çekim anını ve daha önce değerlendirildiyse son seviyeyi görmek istiyorum; böylece öncelikli kareyi bulurum.
11. Operatör olarak, ızgarayı Bölge'ye ve seviyeye göre filtreleyebilmek istiyorum. Seviye filtresinde "Değerlendirilmedi" seçeneği de olmalı; böylece belirli bir alana ya da riskli karelere odaklanırım.
12. Operatör olarak, ızgarayı çekim anına göre sıralayabilmek istiyorum; böylece günün akışını izlerim.
13. Operatör olarak, kendi dosyamı yükleyemeyeceğimi açıkça bilmek istiyorum; çünkü konumu ve çekim anı bilinmeyen bir kare değerlendirilemez.
14. Operatör olarak, alt zaman akışında günün 40 karesini çekim anına göre dizili ve seviye şekliyle görmek istiyorum; böylece günün genel resmini tek şeritte görürüm.
15. Operatör olarak, zaman akışındaki bir kareye tıklayınca aynı seçimin yapılmasını istiyorum; böylece iki yoldan da seçebilirim.
16. Operatör olarak, üst şeritteki bütün karelerin her zaman seçilebilir olmasını istiyorum; böylece seçili kareden sonraki karelere de geçebilirim.
17. Operatör olarak, seçtiğim karenin önizlemesini büyük görmek istiyorum; böylece sahneyi incelerim.
18. Operatör olarak, seçtiğim karenin ayak izini (4 köşe) haritada görmek ve haritanın o bölgeye yaklaşmasını istiyorum; böylece karenin nerede çekildiğini anlarım.
19. Operatör olarak, bir kare seçmenin analizi kendiliğinden başlatmamasını istiyorum; böylece önce kareye bakıp sonra karar veririm.
20. Operatör olarak, üst çubukta seçili karenin kimliğini, Bölge'sini ve çekim anını görmek istiyorum; kare seçili değilse "Zaman akışından bir kare seçin" yazmalı.

### Risk analizi

21. Operatör olarak, "Risk analizini başlat" düğmesiyle değerlendirmeyi başlatmak istiyorum.
22. Operatör olarak, daha önce değerlendirilmiş bir karede düğmenin "Sonucu aç (önbellek)" demesini istiyorum; böylece sonucun hızlı geleceğini bilirim.
23. Operatör olarak, her adımın numarasını, adını ve özetini geldiği anda üst çubukta ve Risk & Temaslar çekmecesinde görmek istiyorum; böylece sistemin ne yaptığını izlerim.
24. Operatör olarak, adım listesinin önceden sabitlenmiş değil, gelen olaylardan oluşmasını istiyorum; böylece backend adımları değişse de ekran doğru kalır.
25. Operatör olarak, 15 saniyeyi aşan beklemede "Model yanıtı bekleniyor (en fazla 45 sn)" mesajını görmek istiyorum; ekranın hiçbir anda boş kalmaması gerekir.
26. Operatör olarak, önbellekten gelen sonuçta bir "önbellek" rozeti ve "Yeniden değerlendir" düğmesi görmek istiyorum; böylece sonucun eski olabileceğini bilir ve tazeleyebilirim.
27. Operatör olarak, Brief LLM yerine kurallarla yazıldıysa "otomatik özet" rozetini ve sebebini görmek istiyorum; böylece gerekçenin sınırlı olduğunu bilirim.
28. Operatör olarak, Brief'i yazan modeli görmek istiyorum; böylece kaynağını bilirim.
29. Operatör olarak, değerlendirme hata verirse ya da görüntü bulunamazsa kısa bir Türkçe mesaj ve "Tekrar dene" düğmesi görmek istiyorum.
30. Operatör olarak, değerlendirme sürerken başka bir kare seçersem eski akışın iptal edilmesini ve haritanın temizlenmesini istiyorum; böylece iki karenin sonucu karışmaz.
31. Operatör olarak, Brief geldiğinde üst çubukta Görüntü'nün risk seviyesini (renk, şekil ve kelime) ve önerilen eylemi görmek istiyorum; böylece ilk üç saniyede durumu anlarım.
32. Operatör olarak, Brief geldiğinde Risk & Temaslar çekmecesinin kendiliğinden göz atma hâlinde açılıp özet sayıları göstermesini istiyorum (ör. "5 temas").
33. Ekran okuyucu kullanan bir operatör olarak, canlı adımların sesli duyurulmasını istiyorum.

### Harita üzerinde Temas'lar ve hareket

34. Operatör olarak, her Temas'ı çekim anındaki konumunda görmek istiyorum.
35. Operatör olarak, Temas türünü (eşleşmiş, kayıt dışı, kaçırılmış) işaretin çizgisinden ve dolgusundan ayırt etmek istiyorum.
36. Operatör olarak, Temas seviyesini renk, şekil ve kelimeyle ayırt etmek istiyorum: ● düşük, ■ orta, ▲ yüksek, ◆ kritik. Seviye hiçbir yerde yalnızca renkle verilmemeli.
37. Operatör olarak, track'i olan Temas'ların rotasını ve rota noktalarının saatlerini görmek istiyorum; böylece aracın nereden geldiğini görürüm.
38. Operatör olarak, duraklamaları saatleri, süreleri ve yerleriyle haritada görmek istiyorum.
39. Operatör olarak, Temas'ın son yönünü haritada bir okla ve eğilimini ("yaklaşıyor / uzaklaşıyor / duruyor / geçiyor") metinle görmek istiyorum; böylece nereye gittiğini çekim anına kadarki veriyle anlarım.
40. Operatör olarak, çekim anından sonraki hiçbir konumun ya da tahmini rotanın çizilmemesini istiyorum (ADR-0001).
41. Operatör olarak, yönü bilinmeyen Temas'ta ok görmemek ama "yön belirsiz" yazısını görmek istiyorum.
42. Operatör olarak, eski bir önbellek kaydında rota saatleri yoksa rotanın saatsiz çizilmesini istiyorum; böylece ekran hata vermez.

### Görüntü üzerinde tespitler

43. Operatör olarak, Görüntü çekmecesinde karenin üzerinde tespit kutularını sınıf, güven ve track kimliğiyle görmek istiyorum.
44. Operatör olarak, zayıf tespitleri kesikli kutuyla görmek istiyorum; böylece güvenin düşük olduğunu bilirim.
45. Operatör olarak, kaçırılmış Temas'ları kutusuz bir konum işaretiyle görmek istiyorum; böylece modelin görmediği ama track'in orada olduğu aracı fark ederim.

### Temas incelemesi

46. Operatör olarak, Risk & Temaslar çekmecesinde Temas'ları seviyeye göre sıralı görmek istiyorum.
47. Operatör olarak, düşük seviyeli Temas'ların katlanır bir grupta durmasını istiyorum (ör. "19 kayıt dışı temas, en yakını 0,8 km"); böylece liste gürültüye boğulmaz.
48. Operatör olarak, her satırda tür rozetini, sınıfı (otomobil, minibüs, kamyon, otobüs), track kimliğini, Üs'e mesafeyi, seviyeyi ve kesinliği görmek istiyorum.
49. Operatör olarak, bir Temas'a listeden, haritadaki işaretten ya da görüntüdeki kutudan tıkladığımda üç görünümün aynı Temas'a odaklanmasını istiyorum. Harita rotayı vurgulayıp yaklaşmalı, görüntü kutuyu vurgulamalı, çekmece detay kartını açmalı.
50. Operatör olarak, detay kartında tespiti görmek istiyorum: sınıf, güven ve zayıf olup olmadığı.
51. Operatör olarak, detay kartında eşleşmeyi görmek istiyorum: track, eşleşme mesafesi, ikinci aday ve belirsiz eşleşme uyarısı.
52. Operatör olarak, detay kartında hareketi görmek istiyorum: 30 dk önce ve şimdi Üs'e mesafe, son ve ortalama hız, yön, duraklamalar ve geçilen Bölge'ler.
53. Operatör olarak, Üs'e mesafenin çekim anına kadarki değişimini küçük bir grafikte görmek istiyorum; böylece yaklaşmayı gözle doğrularım.
54. Operatör olarak, detay kartında seviyenin temelden nihaiye nasıl değiştiğini görmek istiyorum: kural gerekçeleri, LLM'in kabul edilen ayarı ve reddedilen önerisi.
55. Operatör olarak, detay kartında bu Temas'a bağlı Rapor kararlarını görmek istiyorum: karar, riske etkisi (↑ yükseltir · ↓ düşürür · – yok) ve gerekçe; böylece hangi raporun neden reddedildiğini anlarım.
56. Operatör olarak, kayıt dışı bir Temas'a hiçbir raporun bağlanamadığını açıkça görmek istiyorum; böylece boş listeyi "rapor yok" diye yanlış okumam.
57. Operatör olarak, Temas'ın doğrulanmış dost olup olmadığını ya da tip çelişkisi taşıdığını görmek istiyorum.
58. Operatör olarak, Brief sekmesinde Görüntü'nün tamamı için Brief metnini, önerilen eylemi, kaynakları ve otomatik özet bayrağını görmek istiyorum.

### Sohbet

59. Operatör olarak, detay kartının altındaki "Bu temas hakkında sor" düğmesiyle Sohbet çekmecesini hazır dolu bir soruyla açmak istiyorum. Track'li Temas'ta soru "T0122 nereden geldi?" gibi olmalı; kayıt dışı Temas'ta "Üsse 0,8 km'deki kayıt dışı otomobil hakkında ne biliyoruz?" gibi.
60. Operatör olarak, hazır soruyu göndermeden önce düzenleyebilmek istiyorum.
61. Operatör olarak, çağrılan araçları sırayla ve cevabı yazan modeli görmek istiyorum; böylece cevabın neye dayandığını bilirim.
62. Operatör olarak, sohbetin yalnızca tamamlanmış bir değerlendirmede açılmasını istiyorum.
63. Operatör olarak, sohbet hata verirse kısa bir Türkçe mesaj ve "Tekrar dene" düğmesi görmek istiyorum.
64. Operatör olarak, soru alanının 1–2000 karakter sınırını görmek istiyorum.

### Alt zaman akışı (seçili kare)

65. Operatör olarak, seçili karenin son iki saatini alt şeritte görmek istiyorum: seçili Temas'ın rota saatleri, duraklamaları ve bağlı rapor saatleri; böylece olayları zamana oturturum.
66. Operatör olarak, bu şeritte çekim anından sonrasının gri ve kapalı olmasını istiyorum (ADR-0001).

### Çekmeceler ve klavye

67. Operatör olarak, çekmeceleri kenardaki sekmeye tıklayarak ya da tutamaçtan sürükleyerek açmak istiyorum.
68. Operatör olarak, çekmecelerin kapalı, göz atma, yarım ve tam hâllerinin olmasını istiyorum; bir Temas'a tıklayınca Risk & Temaslar yarım açılmalı.
69. Operatör olarak, aynı anda en fazla bir sağ ve bir sol çekmecenin açık olmasını istiyorum; Görüntü ve Sohbet birbirinin yerine geçmeli.
70. Operatör olarak, çekmeceler açıkken haritayla etkileşmeye devam etmek istiyorum; arka plan kararmamalı.
71. Klavye kullanan bir operatör olarak, çekmeceleri kısayollarla açmak (R Risk & Temaslar, B Brief, G Görüntü, S Sohbet), Esc ile kapatmak ve odağın çekmeceye taşınıp kapanınca geri dönmesini istiyorum.
72. Klavye kullanan bir operatör olarak, ←/→ ile zaman akışında önceki/sonraki kareye geçmek istiyorum.

### Dil ve biçim

73. Operatör olarak, bütün metinleri Türkçe ve alan dilindeki terimlerle görmek istiyorum: Üs, Bölge, Görüntü, Çekim anı, Temas, Kayıt dışı temas, Kaçırılmış temas, Rapor kararı, Kesinlik. "Araç", "hedef" ve "resim" kullanılmamalı.
74. Operatör olarak, sayıları Türkçe biçimde görmek istiyorum (1,6 km · 0,8 km · 6,2 m/s).
75. Hareket hassasiyeti olan bir operatör olarak, hareket azaltma tercihim açıkken rota animasyonlarının kapalı olmasını istiyorum.

## Implementation Decisions

### Mimari
- Next.js App Router, TypeScript, Tailwind ve shadcn/ui. Tek bir operasyon sayfası var.
- Tarayıcı yalnızca Next.js ile konuşur. `/api/*` istekleri rewrite ile FastAPI'ye (`:8000`) yönlenir, backend'de CORS yok.
- **API katmanı ayrı bir modül.** Bileşenler `fetch` bilmez. Modül şunlardan oluşur:
  - JSON uçları için tipli bir istemci (`GET /zones`, `GET /images`, `GET /images/{id}`, görüntü dosyası adresi).
  - SSE uçları için ortak bir akış okuyucu (`POST /evaluations`, `POST /evaluations/{run_id}/chat`). `EventSource` POST desteklemediği için `fetch` ve `ReadableStream` kullanılır; olaylar satır satır ayrıştırılır. `AbortSignal` ile iptal edilebilir.
- **Tipler OpenAPI'den üretilir** (`openapi-typescript`, backend'in `/openapi.json`'ı). Elle tip ya da uydurma alan yazılmaz. SSE olay yükleri OpenAPI'de tanımlı olmadığı için tek bir modülde, backend koduna birebir karşılık gelen tiplerle tanımlanır:
  - `run {run_id, image_id, cached}`
  - `step` → `StepEvent`
  - `brief` → `Brief`
  - değerlendirme `error {run_id, message}`
  - sohbet `tool {name, arguments, result}`, `answer {content, model}`, `error {message}`
- **Tek bir seçim deposu (Zustand)** şunları tutar:
  - seçili Görüntü,
  - aktif değerlendirme: durum (boşta / akıyor / tamam / hata), gelen adımlar, `run_id`, önbellek bayrağı, Brief,
  - seçili Temas anahtarı,
  - çekmecelerin hâli (sol / sağ; kapalı / göz atma / yarım / tam; aktif sekme),
  - harita zemini (uydu / sokak).
- **Temas anahtarı:** Track'li Temas'larda `track_id`, kayıt dışı Temas'larda Brief'teki `contacts[]` içindeki sırası. Yalnızca o değerlendirme boyunca geçerlidir; yeni bir değerlendirme ya da kare seçimi anahtarı sıfırlar.
- **Kare değişince** aktif akış iptal edilir; değerlendirme, Temas seçimi ve harita katmanları temizlenir.

### Harita
- Harita, sağlayıcıdan bağımsız bir arayüzün arkasındadır. Arayüzün sorumlulukları:
  - görünümü bir alana sığdırmak ya da bir noktaya yaklaşmak,
  - zemini seçmek (uydu / sokak / düz),
  - adlandırılmış veri katmanlarını GeoJSON olarak ayarlamak,
  - bir özelliği vurgulamak,
  - tıklanan özelliğin kimliğini bildirmek.
- Gerçek uygulama MapLibre GL ile yapılır ve yalnızca tarayıcıda yüklenir (sunucu tarafında render edilmez).
- **Zemin kaynakları** anahtar gerektirmez:
  - sokak: OpenFreeMap,
  - uydu: Esri World Imagery (atıf zorunlu).
  - Varsayılan zemin uydudur. Zemin yüklenemezse düz koyu zemine düşülür; veri katmanları kendi GeoJSON kaynaklarıyla çalışmaya devam eder.
- **Katmanlar:**
  - Üs ve 1/3 km halkaları.
  - Bölge merkezleri, adları ve yaklaşık bölge alanı. Yarıçap, en yakın komşu Bölge merkezine olan mesafenin yarısıdır.
  - Seçili karenin ayak izi. Poligonun köşe sırası: sol üst, sağ üst, sağ alt, sol alt.
  - Temas'lar: tür çizgi ve dolguyla, seviye renk, şekil ve etiketle.
  - Rotalar, rota noktası saatleri, duraklamalar ve son yön oku.
- **Koordinat sırası:** Backend `[lat, lon]` ve `{lat, lon}` döndürür, MapLibre `[lon, lat]` bekler. Dönüşüm tek bir yardımcıda yapılır.
- **İlk görünüm:** Üs ve 8 Bölge merkezini kapsayan sınır kutusu, kenar boşluğuyla.

### Hesaplar (istemci)
- Haversine uzaklık, yaklaşık bölge yarıçapı ve Üs'e mesafe serisi tek bir coğrafya yardımcısında toplanır. Mesafe serisi rota noktalarından ve Üs koordinatından çıkar. Bunlar deterministik görüntüleme hesaplarıdır; risk hesabı yapılmaz, seviye ve bulgular backend'den gelir.
- Rota saati `null` ise (eski önbellek kaydı) mesafe grafiğinin x ekseni sıra numarası olur ve saat etiketleri çizilmez.

### Biçim ve dil
- Sayılar `Intl` ile `tr-TR` biçiminde gösterilir:
  - mesafe 1 km'nin altında `m`, üstünde bir ondalıklı `km`,
  - hız `m/s`,
  - saatler backend'den geldiği gibi `SS:DD`.
- **Etiket eşlemeleri** tek bir modülde:
  - tür: matched → eşleşmiş, unregistered → kayıt dışı temas, missed → kaçırılmış temas
  - sınıf: car → otomobil, van → minibüs, truck → kamyon, bus → otobüs
  - seviye: düşük / orta / yüksek / kritik, şekiller ● ■ ▲ ◆
  - kesinlik: kesin / olası / zayıf / doğrulanamadı
  - eğilim: yaklaşıyor / uzaklaşıyor / duruyor / geçiyor / bilinmiyor
  - rapor kararı: tutarlı / çelişkili / doğrulanamaz / ilgisiz
  - etki: ↑ yükseltir / ↓ düşürür / – yok
- Önerilen eylem backend'in `recommended_action` metnidir.

### Değerlendirme akışı
- "Risk analizini başlat" `POST /evaluations {image_id}` çağırır, "Yeniden değerlendir" aynı çağrıyı `recompute: true` ile yapar.
- Karenin `last_risk_level`'ı doluysa düğme metni "Sonucu aç (önbellek)" olur.
- Olay sırası `run → step… → brief`, ya da `error`.
- Akış başlamadan dönen 404'ün gövdesi `{detail}`'dir ve akış içindeki `error` olayıyla aynı hata durumuna düşer.
- 15 saniye içinde yeni olay gelmezse bekleme mesajı gösterilir.
- Brief geldiğinde sağ çekmece göz atma hâline geçer.

### Çekmeceler
- shadcn `Sheet`, modal olmayan kipte kullanılır: arka plan kararmaz, harita etkileşimli kalır.
- **Genişlikler:** göz atma ~56 px, yarım ~%30, tam ~%55. Harita paneli açık çekmecenin genişliği kadar daralır.
- **Kenarlar:**
  - Sağ: Risk & Temaslar (sekmeler: Temaslar · Brief).
  - Sol: Görüntü veya Sohbet, aynı anda yalnızca biri.
- **Kısayollar:** R, B, G, S, Esc ve ←/→. Yazı alanı odaktayken devre dışı kalırlar. Odak yönetimi erişilebilirlik kurallarına uyar.
- Ayrı bir Raporlar çekmecesi bu özelliğin kapsamında değil. Rapor kararları Temas detay kartında gösterilir.

### Sohbet
- `POST /evaluations/{run_id}/chat {message}` çağrılır. `tool` olayları "çağrılan araç" satırları olarak, `answer` cevap ve model olarak gösterilir.
- Sohbet geçmişi yalnızca istemci belleğinde tutulur, çünkü geçmişi okuyan bir uç yok. Sayfa yenilenince sıfırlanır.
- Hazır soru Temas türüne göre üretilir: track'li Temas'ta `track_id` ile, kayıt dışı Temas'ta sınıf ve Üs'e mesafeyle.

### Tasarım sistemi (Aşama 0)
- **Görsel dil:**
  - Koyu nötr zemin, tek vurgu rengi: seçim için amber.
  - Kırmızı yalnızca kritik seviye için.
  - Metin sans, koordinat / saat / kimlik monospace.
  - Glassmorphism, neon ve bilim-kurgu efektleri yok.
- **Token katmanları** üç tane: ham değerler → anlamlı değerler → bileşen değerleri.
- **Anlamlı token adları:** `risk-dusuk/orta/yuksek/kritik`, `secim`, `veri-bayat`, `cekmece-*`, `harita-paneli-*`, `ust-cubuk`, `zaman-akisi`.
- **Kontrast:** WCAG AA. En küçük yazı 12 px.

### Backend
- Backend değişmez. B1 uçları kullanılır: `/zones`, `/images/{id}`, `/images/{id}/file` ve rota saatleri.

## Testing Decisions

- **İyi bir test**, yalnızca kullanıcının gördüğü davranışı doğrular: ekranda hangi metin, rozet ve öğelerin göründüğünü, hangi etkileşimin hangi görünümü değiştirdiğini ve hangi isteğin hangi gövdeyle gittiğini. Bileşenlerin iç durumunu, depo yapısını ya da CSS sınıflarını test etmez.
- **Ana test noktası sayfanın tamamıdır** (Vitest + Testing Library). Operasyon sayfası render edilir. API, backend sözleşmesine birebir uyan MSW işleyicileriyle taklit edilir: JSON uçları ve SSE akışları. Akışlarda olaylar parça parça ve gecikmeli gönderilebilir.
  - **Veri:** Veri, B1 testlerindeki referans örnekten gelir. img_000860, 14:10, Doğu Yolu. T0122 kaçırılmış ya da eşleşmiş temas, üsse ~1,6 km, yaklaşıyor. 12:35 raporu çelişkili. Buna kayıt dışı ve düşük seviyeli temaslar eklenir.
  - **Senaryolar:**
    - Açılış: Üs, 8 Bölge, "yaklaşık alan" lejantı; henüz analiz yok.
    - 40 karelik ızgara, filtre ve sıralama. Zaman akışından seçim, ızgaradan seçimle aynı sonucu verir.
    - Kare seçimi: ayak izi, bölgeye yaklaşma, üst çubuk.
    - Analiz akışı: adımların geliş sırasıyla görünmesi, bekleme mesajı, önbellek rozeti ve yeniden değerlendirme (`recompute: true` gövdesi), otomatik özet rozeti, hata ve 404'te "Tekrar dene".
    - Akış sürerken başka kare seçilince eski akışın iptali.
    - Brief sonrası: üst çubukta seviye (şekil + kelime) ve eylem; Temas işaretleri, rotalar, duraklamalar, yön ve eğilim; çekim anından sonrası yok.
    - Görüntü üzerinde kutular: zayıf tespit kesikli, kaçırılmış temas kutusuz.
    - Temas listesi sıralaması ve düşüklerin katlanması.
    - Üç yoldan Temas seçimi ve üç görünümün senkronu.
    - Detay kartının bütün bölümleri; rota saati `null` iken grafik.
    - Kayıt dışı Temas'ta "bağlı rapor yok" notu.
    - "Bu temas hakkında sor": hazır soru, `tool` ve `answer` olayları, sohbet hatası.
    - Klavye: kısayollar, Esc, ←/→.
    - Türkçe sayı biçimi.
- **Harita test sınırı:** MapLibre jsdom'da çalışmaz. Haritanın sağlayıcıdan bağımsız arayüzü testlerde, çizilen katmanları ve vurguları kaydeden bir sahte uygulamayla değiştirilir. Sayfa testleri harita davranışını bu kayıt üzerinden doğrular: hangi katmanda hangi özellikler var, neye yaklaşıldı, ne vurgulandı. Haritadaki tıklama da bu sahte uygulamadan tetiklenir. Böylece sayfa testlerinde kullanılan tek ek test noktası harita arayüzü olur.
- **Tek başına testler istisnadır.** Yalnızca hesabın karmaşık olduğu yerlerde küçük ek testler yazılır: coğrafya yardımcısı (haversine, yaklaşık yarıçap, mesafe serisi, koordinat sırası), SSE ayrıştırıcı (parçalı satırlar, çok satırlı `data`, iptal) ve Türkçe sayı biçimi.
- **Uçtan uca (Playwright)** testler az ve demo odaklıdır:
  - Gerçek MapLibre ile sayfa açılır ve zemin yüklenemediğinde düz zemine düşülür.
  - Backend açıkken img_000860 demo akışı koşar: kare seç → adımlar akar → seviye görünür → T0122 detayı → sohbet cevabı.
- **Önceki örnek:** Frontend'de henüz test yok; bunlar ilk örnek olacak. Backend'deki karşılığı, sahte depo ve sahte tespitle değerlendirme servisini uçtan uca test eden `tests/test_evaluation.py` ile salt veri uçlarını HTTP seviyesinde test eden `tests/test_data_api.py`. Referans değerler aynıdır.

## Out of Scope

- Operatör kararının ya da eylem onayının kaydı; bunun için backend'de uç yok.
- Dosya yükleme ve veri setinde olmayan görüntüler.
- Ayrı Raporlar çekmecesi ve rapor filtreleri. Rapor kararları yalnızca Temas detay kartında gösterilir.
- Sohbet geçmişinin sayfa yenilemeden sonra geri gelmesi.
- Çekim anından sonrasını gösteren "geriye dönük inceleme" görünümü (ADR-0001).
- Mobil ve dar ekran yerleşimi; hedef, demo için masaüstü ve projektör.
- Çekmece durumunun tarayıcı belleğinde saklanması.
- Backend değişiklikleri: kayıt dışı Temas'lara rapor bağlama, Temas kimliği alanı, rota noktalarına mesafe alanı.

## Further Notes

- **Önbellek ısıtma:** Demo öncesinde demo görüntüleri `recompute: true` ile yeniden değerlendirilmeli. B1'den önce kaydedilmiş brief'lerde rota saatleri `null`.
- **img_000860 gerçek sonucu:** Ekibin modeli kamyonu görmüyor. T0122 kaçırılmış temas olarak yüksek çıkıyor, 12:35 raporu çelişkili. Referans örnekteki kamyon senaryosu (eşleşmiş, kritik) ise sahte veriyle test ediliyor. Ekran iki durumu da doğru göstermeli.
- **Bilinen risk (R15):** Raporlar yanlış araca bağlanabiliyor. Detay kartında rapor kararının hangi Temas'a bağlandığı ve gerekçesi görünür; sunumda bu dürüstçe anlatılmalı.
- **Geliştirme ortamı:** Frontend geliştirilirken backend'in açık olması gerekmez; sayfa MSW ile de çalışabilir. Demo ve uçtan uca testler için backend `:8000`'de açık olmalı.
