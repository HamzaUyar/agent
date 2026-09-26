# Spec: Görüntü Değerlendirme Agent'ı (Aşama 2)

Status: ready-for-agent

## Problem Statement

Üssü koruyan operatör gün boyu sekiz bölgeden drone görüntüsü, araçların hareket kayıtları ve sahadan serbest metin raporlar alıyor. Bu üç kaynak birbirine bağlı gelmiyor: görüntünün hangi hareket kaydına ve hangi rapora karşılık geldiği yazmıyor. Operatörün bu bağlantıyı elle kurması için şunları yapması gerekiyor:

- bir görüntüdeki araçları tek tek bulmak,
- bunları haritaya oturtmak,
- hangi hareket kaydına ait olduklarını çıkarmak,
- ilgili raporları aramak.

Raporların bir kısmı yanlış, bir kısmı kasıtlı yanıltıcı, bir kısmı ilgisiz. Özellikle "bölgede dost unsurlar var" türünden sahte bir rapor gerçek bir tehdidi gizleyebilir. Operatörün şu soruya hızlı, gerekçeli ve güvenilir bir cevaba ihtiyacı var: "Bu görüntüdeki durum üs için ne kadar riskli, neden, ve ne yapmalıyım?"

## Solution

Operatör 40 görüntüden birini seçer. Sistem görüntüyü **çekim anı** itibarıyla değerlendirir ve adımlarını canlı olarak gösterir:

1. araçları tespit eder,
2. tespitleri gerçek koordinatlara çevirir,
3. çekim anındaki track'lerle eşleyerek **Temas**ları oluşturur,
4. her temasın son iki saatlik hareketini analiz eder,
5. ilgili **Rapor**ları bulur ve her **İddia**yı kendi bulgularıyla karşılaştırır,
6. kod tabanlı kurallarla bir temel **Risk seviyesi** hesaplar,
7. LLM bu seviyeyi gerekçesiyle en fazla bir kademe ayarlar.

Sonuçta Türkçe, askeri brifing üslubunda bir **Brief** üretilir. Brief şunları içerir: görüntü seviyesi, temas bulguları, rapor kararları, **Önerilen eylem**, her bulgunun **Kesinlik** etiketi ve kaynaklar.

Brief'ten sonra operatör takip soruları sorabilir ("T0122 nereden geldi?", "12:35 raporu neden reddedildi?"). Sohbet agent'ı bunları salt okuma araçlarıyla cevaplar. LLM çalışmazsa sistem, kod tabanlı seviyeyle bir **otomatik özet** üretir. Değerlendirme hiçbir koşulda çekim anından sonraki veriyi kullanmaz.

## User Stories

### Görüntü seçimi ve akış
1. Operatör olarak veri setindeki 40 görüntüyü bölgesi ve çekim saatiyle listelenmiş görmek istiyorum, böylece değerlendireceğim kareyi hızlıca seçebilirim.
2. Operatör olarak bir görüntüyü seçip değerlendirmeyi başlatmak istiyorum, böylece o karedeki durumun riskini öğrenebilirim.
3. Operatör olarak değerlendirmenin adımlarını gerçekleştikçe görmek istiyorum, böylece sistemin neye dayanarak karar verdiğini izleyebilirim.
4. Operatör olarak her adımın kısa bir özetini ve kilit sayılarını görmek istiyorum (ör. "T0122 · <1 m"), böylece ara sonuçları doğrulayabilirim.
5. Operatör olarak daha önce değerlendirilmiş bir görüntüyü açtığımda son sonucun hemen gelmesini istiyorum, böylece beklemem.
6. Operatör olarak bir görüntüyü yeniden değerlendirmeyi tetikleyebilmek istiyorum, böylece kural ya da model değişikliğinden sonra güncel sonucu görebilirim.
7. Operatör olarak veri setinde olmayan bir görüntünün kabul edilmemesini istiyorum, böylece konumu ve saati bilinmeyen bir kare yanıltıcı bir karar üretmez.

### Tespit ve konumlandırma
8. Operatör olarak görüntüdeki araçların sınıfını, güvenini ve kutusunu görmek istiyorum, böylece modelin ne bulduğunu bilirim.
9. Operatör olarak her tespitin gerçek enlem ve boylamını görmek istiyorum, böylece aracı haritada konumlandırabilirim.
10. Operatör olarak görüntünün hangi bölgede olduğunu ve üsse uzaklığını görmek istiyorum, böylece kareyi sahada nereye koyacağımı bilirim.
11. Operatör olarak güveni çok düşük kutuların yok sayılmasını istiyorum, böylece gürültü yüzünden yanlış alarm almam.
12. Operatör olarak orta güvenli bir kutunun ancak bir track'le eşleşirse temas sayılmasını istiyorum, böylece zayıf ama gerçek araçlar kaybolmaz, sahte kutular da alarm üretmez.
13. Operatör olarak zayıf tespitlerin brief'te "zayıf" kesinliğiyle işaretlenmesini istiyorum, böylece o bulguya ne kadar güveneceğimi bilirim.

### Eşleştirme ve temaslar
14. Operatör olarak her tespitin çekim anında ona en yakın track'le eşleşmesini istiyorum, böylece aracın tipini hareket geçmişiyle birleştirebilirim.
15. Operatör olarak eşleşmenin mesafesini ve varsa ikinci en yakın adayı görmek istiyorum, böylece eşleşmenin sağlamlığını değerlendirebilirim.
16. Operatör olarak eşik mesafesi içinde birden fazla track olduğunda "belirsiz eşleşme" uyarısı görmek istiyorum, böylece yanlış bir araca hareket geçmişi atanmış olabileceğini bilirim.
17. Operatör olarak track'i olmayan bir tespitin "kayıt dışı temas" olarak işaretlenmesini istiyorum, böylece kayıt dışı araçları fark ederim.
18. Operatör olarak çekim anında karenin alanında olduğu halde tespit edilmemiş bir track'in "kaçırılmış temas" olarak gösterilmesini istiyorum, böylece model hatasını ya da gizlenmiş bir aracı gözden kaçırmam.
19. Operatör olarak çekim saati 5 dakikalık adımlara denk gelmese bile doğru track konumuyla karşılaştırma yapılmasını istiyorum, böylece zaman kayması yüzünden eşleşme kaybolmaz.
20. Operatör olarak aynı temasın çekim anından önceki karelerde farklı tipte görüldüğünü bilmek istiyorum, böylece tip belirsizliğinden haberdar olurum.
21. Operatör olarak tip çelişkisi olduğunda risk hesabında daha riskli tipin kullanılmasını istiyorum, böylece belirsizlik tehdidi küçümsemez.

### Hareket analizi
22. Operatör olarak her temasın son iki saatteki rotasını görmek istiyorum, böylece nereden geldiğini bilirim.
23. Operatör olarak temasın üsse olan mesafesinin zaman içindeki değişimini görmek istiyorum, böylece üsse yaklaşıp yaklaşmadığını anlarım.
24. Operatör olarak temasın son dönemdeki ve ortalama hızını, yönünü görmek istiyorum, böylece ne kadar hızlı hareket ettiğini bilirim.
25. Operatör olarak uzun duraklamaların (süre ve yer) listelenmesini istiyorum, böylece keşif ya da bekleme davranışlarını fark ederim.
26. Operatör olarak temasın hangi bölgelerden geçtiğini görmek istiyorum, böylece rotayı sahadaki adlarla konuşabilirim.
27. Operatör olarak hareket analizinin yalnızca çekim anına kadarki veriyle yapılmasını istiyorum, böylece karar o anki gerçekçi bilgiye dayanır.

### Raporlar
28. Operatör olarak çekim anından önceki iki saat içinde, görüntünün ya da temasın yakınında geçen raporların otomatik bulunmasını istiyorum, böylece ilgili raporları kendim aramam.
29. Operatör olarak aynı bölgeyi adıyla anan raporların da dikkate alınmasını istiyorum, böylece koordinat vermeyen raporlar kaçmaz.
30. Operatör olarak her iddianın tutarlı, çelişkili, doğrulanamaz ya da ilgisiz olarak sınıflandırılmasını istiyorum, böylece raporlara ne kadar güveneceğimi bilirim.
31. Operatör olarak bir raporun koordinatının, temasın **rapor saatindeki** track konumuyla karşılaştırılmasını istiyorum, böylece zaman ve konum tutarsızlığı olan sahte raporlar yakalanır.
32. Operatör olarak rapordaki araç tipinin tespitle karşılaştırılmasını istiyorum (ör. "ağır araç" ile truck), böylece tip uyuşmazlıkları görünür.
33. Operatör olarak rapor renk ya da yük belirtiyorsa bunun görüntüden kontrol edilmesini istiyorum, böylece "mavi araç" gibi iddialar doğrulanır ya da çürütülür.
34. Operatör olarak zamanı belirsiz raporların ("dün gece", "gün içinde") brief'te "doğrulanamaz" olarak görünmesini ama riski etkilememesini istiyorum, böylece dikkate alındıklarını bilirim ama karar bozulmaz.
35. Operatör olarak raporların riski yükseltebilmesini istiyorum, böylece sahadaki uyarılar hesaba katılır.
36. Operatör olarak bir raporun riski ancak belirttiği bütün özellikler kendi bulgularımızla tuttuğunda düşürebilmesini istiyorum, böylece sahte bir rapor tehdidi gizleyemez.
37. Operatör olarak yalnızca resmi kaynaklı dostluk iddialarının riski düşürebilmesini istiyorum, böylece üçüncü taraf kaynaklar tehdidi örtemez.
38. Operatör olarak doğrulanmış bir dost temasın "doğrulanmış dost" olarak ve dayanak raporuyla gösterilmesini istiyorum, böylece neden düşük risk verildiğini bilirim.
39. Operatör olarak kısmen uyan dostluk iddialarında "dostluk iddiası doğrulanamadı" notu görmek istiyorum, böylece iddiaya körü körüne güvenmem.
40. Operatör olarak çekim anından sonraki raporların değerlendirmeye girmemesini istiyorum, böylece karar o an elde olan bilgiye dayanır.

### Risk kararı
41. Operatör olarak her temasın kod kurallarıyla hesaplanmış bir temel risk seviyesi almasını istiyorum, böylece aynı durum her zaman aynı sonucu verir.
42. Operatör olarak temel seviyenin hangi kurala dayandığını görmek istiyorum (ör. "yaklaşıyor, ağır araç, 1,6 km"), böylece kararı denetleyebilirim.
43. Operatör olarak LLM'in seviyeyi en fazla bir kademe ve gerekçe yazarak değiştirebilmesini istiyorum, böylece kuralların kaçırdığı bağlam eklenir ama karar kontrolden çıkmaz.
44. Operatör olarak LLM seviyeyi değiştirdiyse bunu ve gerekçesini açıkça görmek istiyorum, böylece temel seviye ile nihai seviyeyi ayırt edebilirim.
45. Operatör olarak LLM'in seviyeyi ancak somut ve doğrulanmış bir kanıta dayanarak düşürebilmesini istiyorum, böylece ikna edici ama sahte bir bağlam riski azaltamaz.
46. Operatör olarak görüntünün risk seviyesinin içindeki en yüksek temas seviyesi olmasını istiyorum, böylece en tehlikeli temas seyrelmez.
47. Operatör olarak kaçırılmış temasların riskinin, tipi bilinmeden yalnızca hareketten hesaplanmasını istiyorum, böylece görülmeyen araçlar da değerlendirilir.
48. Geliştirici olarak risk eşiklerini tek bir ayar dosyasından değiştirebilmek istiyorum, böylece gerçek veriye göre kodu değiştirmeden ayar yapabilirim.

### Brief
49. Operatör olarak brief'in başlığında görüntü, bölge, çekim saati ve risk seviyesini görmek istiyorum, böylece sonucu tek bakışta anlarım.
50. Operatör olarak her temas için kısa bir bulgu satırı görmek istiyorum (tip, mesafe, hareket, eşleşme), böylece temasları hızlıca karşılaştırabilirim.
51. Operatör olarak her bulgunun yanında bir kesinlik etiketi görmek istiyorum (kesin / olası / zayıf / doğrulanamadı), böylece neyin bilindiğini, neyin tahmin olduğunu ayırabilirim.
52. Operatör olarak rapor kararlarının gerekçeleriyle listelenmesini istiyorum, böylece hangi raporun neden kabul ya da ret edildiğini bilirim.
53. Operatör olarak seviyeye bağlı sabit bir önerilen eylem görmek istiyorum (izlemeye devam / takibe al / birim yönlendir / alarm ve durdurma), böylece ne yapacağımı hemen bilirim.
54. Operatör olarak brief'in kullandığı kaynakları görmek istiyorum (tespit modeli, köşe koordinatları, track kimliği, rapor), böylece kararın izini sürebilirim.
55. Operatör olarak brief'in Türkçe ve önce sonuç veren kısa bir üslupta yazılmasını istiyorum, böylece hızlı karar verebilirim.
56. Arayüz geliştiricisi olarak brief'i yapılandırılmış veri olarak da almak istiyorum, böylece seviyeyi, temasları ve rotaları görsel olarak çizebilirim.

### Sohbet
57. Operatör olarak brief'ten sonra takip sorusu sorabilmek istiyorum, böylece ayrıntıya inebilirim.
58. Operatör olarak bir temasın hareket geçmişini sorabilmek istiyorum, böylece rotayı ayrıntılı görebilirim.
59. Operatör olarak bir konum, bölge ya da zaman aralığındaki raporları sorabilmek istiyorum, böylece bağlamı genişletebilirim.
60. Operatör olarak bir raporun neden kabul ya da reddedildiğini sorabilmek istiyorum, böylece kararı sorgulayabilirim.
61. Operatör olarak bir temasın başka karelerde de görünüp görünmediğini sorabilmek istiyorum, böylece temasın geçmişini birleştirebilirim.
62. Operatör olarak sohbetten başka bir görüntünün değerlendirmesini başlatabilmek istiyorum, böylece akışı kesmeden devam edebilirim.
63. Operatör olarak sohbet agent'ının da çekim anından sonrasını görmemesini istiyorum, böylece sohbet kararla çelişen bilgi sızdırmaz.
64. Operatör olarak sohbet agent'ının veriyi değiştirememesini istiyorum, böylece sohbet kayıtları bozamaz.
65. Operatör olarak sohbet cevaplarının da Türkçe, kısa ve önce sonuç veren üslupta olmasını istiyorum, böylece brief ile tutarlı olsun.

### Dayanıklılık ve izlenebilirlik
66. Operatör olarak LLM çalışmazsa kod tabanlı seviyeyle üretilmiş ve "otomatik özet" etiketli bir brief almak istiyorum, böylece demo ya da operasyon durmaz.
67. Operatör olarak birincil model başarısız olursa yedek modelin denenmesini istiyorum, böylece tek bir sağlayıcıya bağımlı kalmam.
68. Geliştirici olarak hangi görevde hangi modelin kullanıldığını ayar dosyasından değiştirebilmek istiyorum, böylece kod değişmeden model seçebilirim.
69. Mentör olarak her değerlendirmenin adımlarını, girdilerini, çıktılarını, kullanılan modeli ve süresini kayıtlı görmek istiyorum, böylece kararın izini sürebilirim.
70. Mentör olarak bir değerlendirmede hangi raporların dikkate alındığını ve hangilerinin reddedildiğini sonradan inceleyebilmek istiyorum, böylece sistemin sahte raporlara karşı davranışını görebilirim.
71. Geliştirici olarak elle etiketlenmiş yaklaşık 10 görüntülük bir değerlendirme setini tek komutla çalıştırmak istiyorum, böylece kural ya da prompt değişikliğinin doğruluğu bozup bozmadığını görürüm.
72. Sunumcu olarak değerlendirme setindeki başarıyı sayıyla gösterebilmek istiyorum (doğru seviye, yakalanan sahte rapor), böylece jüriye somut kanıt sunarım.

### Veri hazırlığı
73. Geliştirici olarak 2. aşama veri paketini tek komutla veritabanına yüklemek istiyorum, böylece veri geldiğinde hemen çalışabilirim.
74. Geliştirici olarak yükleme sırasında her görüntünün kapladığı alanın, merkezinin ve bölgesinin hesaplanmasını istiyorum, böylece değerlendirme sırasında tekrar hesap gerekmez.
75. Geliştirici olarak raporların bir kere LLM ile iddialara ayrıştırılıp saklanmasını istiyorum, böylece her değerlendirmede tekrar ayrıştırma olmaz.
76. Geliştirici olarak gerçek veri gelmeden önce brief'teki örneklerden üretilmiş sahte veriyle çalışabilmek istiyorum, böylece geliştirme veriyi beklemez.
77. Geliştirici olarak yükleme sonunda veri tutarlılığı raporu görmek istiyorum (meta'sı eksik görüntü, 5 dakikalık adıma denk gelmeyen çekim saati, track ve rapor sayıları), böylece açık soruları hemen kapatırım.
78. Geliştirici olarak tespit modeli hazır olana kadar sahte bir tespit bileşeniyle, hazır olunca gerçek modelle çalışabilmek istiyorum, böylece model ekibini beklemem.

## Implementation Decisions

### Modüller
- **Veri yükleme:** Veri paketindeki görüntü meta'sını, bölgeleri, üssü, track'leri ve raporları okuyup veritabanına yazar. Her görüntünün kapladığı alanı, merkezini ve en yakın bölgesini hesaplar. Sonunda bir tutarlılık raporu basar.
- **Sahte veri üretici:** Referans örnekten tutarlı bir veri paketi üretir: img_000860 (14:10, Doğu Yolu, truck, merkez piksel 756,301), T0122 (<1 m), T0032 (41 m), 12:35 resmi raporu, üçüncü taraf "dost unsur" raporu ve bölgeler.
- **Rapor ayrıştırıcı:** Çevrimdışı çalışır. Her raporu bir ya da daha fazla iddiaya ayırır: konum türü, koordinat, bölge, araç tipi, sayı, renk, davranış, iddia türü, zaman ifadesi, doğrulanabilirlik. Hızlı bir LLM'den yapılandırılmış çıktı alır.
- **Tespit arayüzü:** Görüntüyü alır, tespit listesi döndürür. İki gerçekleştirimi var: sahte (sabit kutular) ve gerçek (1. aşama modeli). Hangisinin kullanılacağı ayarla seçilir.
- **Görsel doğrulayıcı (VLM):** Yalnızca gerektiğinde çağrılır: temasla ilgili bir iddia renk veya yük belirtiyorsa, ya da tespit zayıfsa. Renk, yük ve "gerçekten araç mı" sonucunu döndürür.
- **Konumlandırma:** Pikseli köşe koordinatlarıyla doğrusal oranlayarak koordinata çevirir; kare kuzeye hizalı kabul edilir. Mesafe, yön ve en yakın bölgeyi hesaplar.
- **Hareket analizi:** Bir track ve bir "şimdi" anı alır. Yalnızca o ana kadarki noktaları kullanır; nokta yoksa iki adım arasını interpolasyonla bulur. Rota, üsse mesafe serisi, son dönem ve ortalama hız, yön, duraklamalar, geçilen bölgeler ve eğilim (yaklaşıyor / uzaklaşıyor / sabit / geçiyor) döndürür. Görüntüden bağımsızdır (Kol B).
- **Eşleştirici:** Tespitleri, çekim anındaki track konumlarıyla en yakın komşu yöntemiyle eşler. Eşik ve ikinci aday bilgisini tutar. Temasları üretir: eşleşmiş, kayıt dışı, kaçırılmış. Zayıf tespit ve belirsiz eşleşme kurallarını uygular.
- **Rapor değerlendirici:** Aday iddiaları seçer: çekim anından önceki 2 saat, görüntü alanına ya da temasın rapor saatindeki konumuna ~500 m yakınlık, ya da bölge adı. Her iddiayı konum-zaman, tip ve renk açısından karşılaştırır ve bir rapor kararı ile bir kesinlik verir.
- **Risk kuralları:** Temas başına temel seviyeyi hesaplar ve dayandığı sinyalleri döndürür. Tip katsayısını, tip çelişkisinde riskli tipi seçmeyi ve asimetrik rapor etkisini uygular. Eşikler bir ayar dosyasındadır.
- **Karar ayarlayıcı ve brief yazarı:** Temel seviyeyi ve bütün sinyalleri en güçlü akıl yürütme modeline verir. Model temas başına en fazla bir kademe ayar ve gerekçe döndürür, ardından brief metnini yazar. Kod bu ayarı doğrular: bir kademeden fazlasını ya da kanıtsız bir düşürmeyi reddeder.
- **Otomatik özet:** LLM yoksa ya da başarısız olursa temel seviyeyle bir şablondan brief üretir.
- **Değerlendirme servisi:** Yukarıdaki adımları sabit sırayla çalıştıran orkestratör; bir LangGraph grafı. Her adımı bir olay olarak yayar ve kaydeder. Önbellek davranışı: aynı görüntü için son sonucu döndürür, açıkça istenirse yeniden hesaplar.
- **Sohbet agent'ı:** Brief sonrası tool-calling yapan agent. Beş salt okuma aracı var: temas geçmişi, rapor arama, rapor kararının açıklaması, görüntü değerlendirme başlatma, track'in diğer görüntülerde aranması. Bütün araçlar, aktif değerlendirmenin çekim anıyla sınırlıdır.
- **Model yönlendirme:** Görev ile model eşlemesi bir ayar dosyasında, çağrılar LiteLLM üzerinden. Varsayılanlar: rapor ayrıştırma Haiku 4.5; VLM ve sohbet Sonnet 5; karar ve brief Opus 5.5; her görev için yedek GLM.
- **Değerlendirme seti koşucusu:** Elle etiketlenmiş görüntüleri çalıştırır; seviye doğruluğunu, eşleşme doğruluğunu ve çelişkili raporların yakalanma oranını raporlar.

### Temel kurallar
- **Çekim anı sınırı (ADR-0001):** Her sorgu ve araç "çekim anı ve öncesi" filtresi taşır.
- **Hibrit karar ve asimetrik rapor güveni (ADR-0002):** Raporlar riski serbestçe yükseltir. Düşürmek için belirttikleri bütün özelliklerin tutması gerekir; dostluk iddialarında yalnızca resmi kaynak riski düşürebilir.
- **Tespit güveni:** ≥ 0,50 normal; 0,25–0,50 zayıf (yalnızca track'le eşleşirse temas); < 0,25 yok sayılır.
- **Temel seviye tablosu** (ilk uyan geçerli; eşikler ayarlanabilir):
  - *Kritik:* yaklaşıyor ve < 1 km; ya da ağır araç (truck/bus), yaklaşıyor ve < 2 km.
  - *Yüksek:* yaklaşıyor ve < 3 km; ya da temasla ilgili bir rapor kendi track'iyle çelişiyor.
  - *Orta:* yaklaşıyor; ya da ≥ 30 dk duraklama ve < 3 km; ya da kayıt dışı temas ve < 1 km (ADR-0003; önceki kural: kayıt dışı ≥ orta, < 2 km yüksek).
  - *Düşük:* diğer bütün durumlar, doğrulanmış dost dahil.
  - "Yaklaşıyor": son 30 dakikada üsse mesafe > 300 m azalmış.
- **Görüntü seviyesi:** Temaslar içindeki en yüksek seviye.
- **Önerilen eylem:** Seviyeye sabit olarak bağlı; LLM yalnızca hedefi (bölge, temas) doldurur.
- **Kesinlik etiketleri:** kesin / olası / zayıf / doğrulanamadı.

### API sözleşmesi (arayüz için)
- **Görüntü listesi:** kimlik, bölge, çekim saati, son değerlendirmenin seviyesi (varsa).
- **Değerlendirme başlatma:** görüntü kimliği ve isteğe bağlı "yeniden hesapla" bayrağı alır. Adım olaylarını sunucudan akış (SSE) olarak yayar. Her olayda adım adı, sırası, kısa özet ve adıma özgü yapılandırılmış veri bulunur. Son olay yapılandırılmış brief'tir.
- **Değerlendirme okuma:** Kayıtlı bir değerlendirmeyi bütün adımları ve brief'iyle döndürür.
- **Sohbet:** değerlendirme kimliği ve mesaj alır; cevabı ve çağrılan araçları akış olarak döndürür.
- **Yapılandırılmış brief:** görüntü, bölge, çekim anı, görüntü seviyesi, önerilen eylem, "otomatik özet mi" bayrağı. Temas listesinde her temas için şunlar bulunur: tür (eşleşmiş / kayıt dışı / kaçırılmış), tip, güven, konum, track, eşleşme mesafesi ve ikinci aday, belirsizlik bayrağı, hareket özeti ve rota, temel ve nihai seviye, LLM ayar gerekçesi, kesinlik. Ayrıca rapor kararları (iddia, karar, gerekçe, kesinlik), kaynaklar ve brief metni.

### Şema değişiklikleri (mevcut Supabase şemasına eklemeler)
- **Değerlendirmeler tablosu:** yapılandırılmış brief'i saklayacak bir JSON alanı, "otomatik özet" bayrağı.
- **Tespitler tablosu:** zayıf tespit bayrağı.
- **Eşleşmeler tablosu:** belirsiz eşleşme bayrağı.
- **Risk değerlendirmeleri tablosu:** temel seviye, nihai seviye ve LLM ayar gerekçesi ayrı alanlar; ayrıca kesinlik.
- **Rapor değerlendirmeleri tablosu:** kesinlik alanı.
- **Yeni sohbet mesajları tablosu:** değerlendirme kimliği, rol, içerik, araç çağrıları, zaman.

## Testing Decisions

- **İyi bir test**, yalnızca dışarıdan görünen davranışı doğrular: verilen görüntü ve veri için dönen brief'in seviyesini, temaslarını, rapor kararlarını ve olay sırasını. İç fonksiyon çağrılarını, ara veri yapılarını ya da prompt metnini test etmez.
- **Ana test noktası, değerlendirme servisidir.** Tespit arayüzü, LLM istemcisi ve veri deposu yerine sahte bileşenler konur. Bellekteki sahte veri deposu referans örnekten kurulur. Test edilecek senaryolar:
  - img_000860'ın koordinatı (39.92531, 32.87183), T0122 eşleşmesi ve ~1,6 km mesafe.
  - Yaklaşan ağır araç → kritik.
  - Çekim anından sonraki track ya da raporun etkisiz kalması (ADR-0001).
  - Üçüncü taraf dostluk iddiasının riski düşürememesi; resmi ve tam uyan iddianın düşürebilmesi (ADR-0002).
  - Kısmen uyan dostluk iddiasının seviyeyi değiştirmemesi.
  - Rapor saatindeki track konumuyla çelişen raporun "çelişkili" çıkması.
  - Zayıf tespitin eşleşince temas, eşleşmeyince yok sayılması.
  - Belirsiz eşleşme bayrağı.
  - Kayıt dışı ve kaçırılmış temasların üretilmesi.
  - Farklı karelerde tip çelişkisinde riskli tipin seçilmesi.
  - Görüntü seviyesinin temasların en yükseği olması.
  - LLM'in iki kademe ayar ya da kanıtsız düşürme önerisinin reddedilmesi.
  - LLM hatasında otomatik özet ve yedek modele geçiş.
  - Önbellek ve yeniden hesaplama.
  - Zamanı belirsiz raporun doğrulanamaz çıkıp riski etkilememesi.
- **İkinci test noktası, sohbet agent'ının araçlarıdır.** Aynı sahte veri deposu üzerinde, her aracın doğru veriyi döndürdüğü ve çekim anından sonrasını göstermediği doğrulanır.
- **Tek başına testler istisnadır:** Yalnızca hesabın kendisinin karmaşık olduğu yerlerde (interpolasyon, yön hesabı) küçük ek testler yazılır. Konumlandırma, hareket analizi ve eşleştirici ayrıca test edilmez; ana test noktasından test edilir.
- **HTTP/SSE katmanı** ince bir katman olduğu için ayrıca test edilmez.
- **Gerçek LLM ve gerçek model** birim testlerinde kullanılmaz; bunların doğruluğu elle etiketlenmiş değerlendirme setiyle ölçülür.
- **Önceki örnek:** Kod tabanında henüz test yok. Bu testler ilk örnek olacak; referans değerleri organizatörlerin uçtan uca demosundan gelir.

## Out of Scope

- Frontend (Next.js arayüzü): bu spec yalnızca API sözleşmesini tanımlar; arayüz ayrı bir iş.
- Günün durum tablosu ve 40 görüntünün toplu risk sıralaması: tek görüntü akışı bittikten sonra ele alınacak ek özellik.
- Zaman kaydırıcılı risk haritası ve track riskinin önceden hesaplanması.
- Çekim anından sonrasını gösteren "geriye dönük inceleme" görünümü.
- Veri setinde olmayan görüntülerin yüklenmesi.
- Kimlik doğrulama ve kullanıcı yönetimi.
- Tespit modelinin eğitimi ya da iyileştirilmesi (1. aşama ekibinin işi).
- Bölge sınırlarının (çokgen) hesaplanması; bölge yalnızca merkezle temsil edilir.
- Rapor iddiaları için embedding ve anlamsal arama (embedding modeli ve boyutu belirlenene kadar).
- Eğik çekim açısı için perspektif düzeltmesi; doğrusal dönüşüm kabul edildi, eşleşme eşiği bu hatayı tolere eder.

## Further Notes

- **Veri henüz gelmedi.** 2. aşama verisi yarın dağıtılacak. Bütün geliştirme sahte veriyle yapılacak; gerçek veri gelince yükleme ve tutarlılık raporu ilk adım.
- **Gerçek veride kontrol edilecek açık sorular:**
  - 12:35 raporunun T0122'nin o saatteki konumuyla uyuşup uyuşmadığı. Organizatör demosu bu raporu "uyumlu" sayıyor, ama bizim zaman ve konum karşılaştırmamız çelişki gösterebilir.
  - Çekim saatlerinin 5 dakikalık adımlara denk gelip gelmediği.
  - Veri boyutu.
- **Mevcut durum:** Supabase şeması (15 tablo, PostGIS, pgvector, RLS) kurulu ve bağlantı test edildi. Backend iskeleti boş dosyalardan oluşuyor.
- **Alan dili ve kararlar:** Alan dili `CONTEXT.md`'de, mimari kararlar ADR-0001 ve ADR-0002'de. Bu spec ikisiyle de uyumlu.
- **Canlı demo:** 1–2 görüntüde uçtan uca çalışmalı. Demo görüntüleri değerlendirme setinden, doğrulanmış sonucu olanlar arasından seçilecek.
