# Spec: İz analizi, ikonlu kenar gezinmesi ve panel düzeni

Status: resolved

## Problem Statement

Operasyon ekranı çalışıyor, ama operatör günlük kullanımda şu sorunlarla karşılaşıyor:

- **Kenar sekmeleri kalabalık ve tekrarlı.** Kenarda dikey yazılı "Görüntü", "Risk & Temaslar" ve "Brief" düğmeleri var. Brief'e hem ayrı bir kenar sekmesinden hem de Risk & Temaslar içindeki sekmeden ulaşılıyor.
- **Çekmece genişliği öngörülemiyor.** Tutamaç bazen tutmuyor. Bırakınca panel dört sabit genişlikten birine atlıyor. Sürüklerken genişlik geç geliyor. Kapatıp açınca ayarlanan genişlik kayboluyor.
- **Görüntü çekmecesinde gereksiz metin var.** "Yalnızca veri setindeki görüntüler değerlendirilebilir…" açıklaması akışa katkı vermeden yer kaplıyor.
- **Küçük araçlarda kutu araçtan büyük görünüyor.** Kare çekmeceye sığdırılınca küçük bir araç birkaç piksele iniyor. Kutunun sabit kalınlıktaki çerçevesi, kılıfı ve seçim halesi aracın kendisinden büyük kalıyor. Model kutuyu büyütmüyor, frontend de koordinatı büyütmüyor; büyüklük çizim kalınlığından geliyor.
- **Aynı araç iki renkte görünüyor.** Model sınıf başına bastırma yapmış, sınıflar arası yapmamış. Kayıtlı 264 kutudan 14 çift aynı aracı iki ayrı sınıfla işaretliyor (IoU 0,91–1,0; örn. van 0,61 + truck 0,36). Görüntüde üst üste iki renkli kutu çıkıyor.
- **"Temaslar" adı operatöre içeriği anlatmıyor.** Liste satırlarında "kesinlik: kesin" gibi sütunlar ve tür rozeti kalabalık yapıyor. "Burada kaç tane güvenilir sonuç var?" sorusu tek bakışta cevaplanamıyor.
- **Brief tek parça, yoğun bir metin.** Seviye, eylem, gerekçe ve kaynaklar aynı ağırlıkta.
- **"Günün görüntüleri" şeridi her zaman açık.** Haritadan sürekli yer alıyor.
- **Track verisinin tamamı görülemiyor.** Operatör yalnızca seçili Görüntü'nün Temas'larının rotalarını görebiliyor. Veri setinde 226 Track var, günün hareketinin bütününü görmenin ve zaman içinde oynatmanın yolu yok.
- **Lejant kalabalık.** Açılıp kapanan, uzun bir kutu, haritanın köşesini örtüyor.

## Solution

Yerleşim korunur (üst çubuk, çerçeveli harita paneli, kenar çekmeceleri, alt zaman akışı). Değişenler:

1. **İkonlu kenar rayı.** Kenar sekmeleri aynı çizgi kalınlığındaki ikonlara dönüşür. Her ikonun ipucu adını ve kısayolunu söyler, etkin olan ters renkle belli olur.
   - Sol ray: **Görüntü**.
   - Sağ ray, yukarıdan aşağı: **İz analizi**, **Risk & Araçlar**.
   - Brief'in ayrı kenar düğmesi kalkar; Brief, Risk & Araçlar içindeki "Araçlar ↔ Brief" sekmesiyle açılır.
2. **Serbest ve kalıcı çekmece genişliği.** Tutamaç her zaman tutar. Genişlik imleci anında izler, bırakıldığı yerde kalır ve taraf başına tarayıcıda saklanır. Genişliğin alt ve üst sınırı var, harita hiçbir zaman tamamen kapanmaz. Tutamaç klavyeyle de çalışır. Dar "göz atma" hali kalkar; ikon rayı o işi görür.
3. **Görüntü çekmecesi sadeleşir.** Açıklama metni kalkar, başka hiçbir şey değişmez.
4. **Tespit kutusu aracın gerçek alanını gösterir.** Çerçeve kutunun dışına taşmaz, çizgi kalınlığı küçük kutularda incelir. Seçim halesi küçük kutuyu büyütmez.
5. **Bir araç, tek kutu, tek sınıf.** Görüntüde üst üste binen kutulardan yalnızca en yüksek güvenli sınıfınki çizilir. Çizilmeyen kutuya ait Temas, Araçlar listesinde "aynı araç, düşük güvenli ikinci sınıf" olarak soluk gösterilir; bilgi kaybolmaz. Backend'in tespit, eşleşme ve seviye hesabı değişmez.
6. **"Temaslar" arayüzde "Araçlar" olur.** Etkilenen yerler: kenar ikonu ipucu, çekmece başlığı "Risk & Araçlar", sekme "Araçlar", liste "7 araç", göz atma özeti, ilgili düğmeler. Alan dili ve kod "Temas" olarak kalır.
7. **Araçlar listesi sadeleşir.**
   - Satırda kalanlar: kimlik, sınıf rengi ve adı, seviye rozeti, üsse mesafe. Takip durumu sınıf karesinin çizgisinde (düz / kesikli / noktalı).
   - Satırdan kalkanlar: "kesinlik" ve tür rozeti.
   - Listenin üstünde bir **tespit güvenilirliği özeti** var: "Yüksek kesinlik 5 · Orta kesinlik 2 · Düşük kesinlik 0". Her sayı listeyi o gruba süzen bir anahtar.
   - Detay kartında "Zayıf tespit" satırı "Kesinlik" satırına birleşir.
8. **Brief okunabilir hale gelir.** Hiçbir bilgi kaybolmaz; ayrıntılar aşağıdaki kararlarda.
9. **"Günün görüntüleri" katlanır başlar.** İnce başlık çubuğunda seçili kare, saati ve kare sayısı ile bir chevron görünür. Açılışı yumuşak bir geçişle olur. ←/→ kısayolu kapalıyken de çalışır. "Seçili kare · son 2 saat" şeridi bu panelin içindedir.
10. **İz analizi.** Sağ rayın en üstündeki ikon, harita panelinin sağ üst köşesinde küçük, opak bir kart açar. Kart haritayı daraltmaz. Kartta:
    - seviye filtresi (çoklu seçim + "Hepsi"),
    - filtreye uyan track sayısı,
    - saat göstergesi ve zaman çizgisi,
    - oynat / duraklat / sıfırla,
    - hız seçimi.

    Uydu/Sokak anahtarı sol üste, yakınlaştırma düğmelerinin yanına taşınır.
11. **Lejant sadeleşir.** Sol alt köşede her zaman duran, katlanmayan küçük bir kutu olur. Yalnızca araç sınıfı renklerini gösterir: otomobil, minibüs, kamyon, otobüs, tip bilinmiyor.

## User Stories

### Kenar gezinmesi ve çekmeceler

1. Operatör olarak, kenar düğmelerini yazı yerine anlaşılır ikonlar olarak görmek istiyorum; böylece kenarlar daha az yer kaplar ve harita genişler.
2. Operatör olarak, bir ikonun üzerine geldiğimde ya da klavyeyle odakladığımda adını ve kısayolunu gösteren bir ipucu görmek istiyorum; böylece ikonun ne yaptığını tahmin etmek zorunda kalmam.
3. Operatör olarak, açık panelin ikonunu ters renkle ve belirgin bir göstergeyle görmek istiyorum; böylece hangi panelin açık olduğunu tek bakışta anlarım.
4. Operatör olarak, ikonların açık ve koyu temada aynı okunabilirlikte olmasını istiyorum; böylece tema değişince arayamayayım.
5. Operatör olarak, Görüntü ikonunun solda, İz analizi ve Risk & Araçlar ikonlarının sağda olmasını istiyorum; böylece yerleşim alıştığım düzende kalır.
6. Operatör olarak, Brief'e yalnızca Risk & Araçlar içindeki sekmeden ulaşmak istiyorum; böylece aynı içeriğe iki ayrı kapıdan girmem.
7. Operatör olarak, "B" kısayolunun Risk & Araçlar'ı Brief sekmesinde açmaya devam etmesini istiyorum; böylece alışkanlığım bozulmaz.
8. Operatör olarak, bir ikona tıklayınca panelin açılmasını, açıkken tekrar tıklayınca kapanmasını istiyorum; böylece tek düğmeyle ikisini de yaparım.
9. Operatör olarak, çekmecenin tutamacını her tuttuğumda sürüklemenin başlamasını istiyorum; böylece "bazen tutmuyor" hissi olmaz.
10. Operatör olarak, sürüklerken çekmece kenarının imlecimi gecikmeden izlemesini istiyorum; böylece istediğim genişliği tam ayarlarım.
11. Operatör olarak, bıraktığım genişliğin olduğu gibi kalmasını istiyorum; böylece panel sabit bir genişliğe atlamaz.
12. Operatör olarak, çekmeceyi kapatıp açtığımda son genişliğin geri gelmesini istiyorum. Bu, sayfayı yenilesem de geçerli olmalı; böylece her seferinde yeniden ayarlamam.
13. Operatör olarak, çekmecenin belli bir genişlikten daha dar ya da daha geniş olamamasını istiyorum; böylece içerik bozulmaz ve harita hiçbir zaman tamamen kapanmaz.
14. Operatör olarak, sürükleme sırasında haritanın ve metinlerin seçilmemesini, sürüklemenin harita üzerinde kopmamasını istiyorum; böylece sürükleme başka bir etkileşime dönüşmez.
15. Operatör olarak, dokunmatik ekranda da tutamacı sürükleyebilmek istiyorum; böylece sahadaki tablette de çalışır.
16. Klavye kullanan operatör olarak, tutamaca odaklanıp ok tuşlarıyla genişliği değiştirebilmek istiyorum; böylece fare olmadan da ayarlarım.
17. Operatör olarak, genişlet/daralt düğmesinin geniş görünüm ile son ayarladığım genişlik arasında geçiş yapmasını istiyorum; böylece geniş görünüme hızlı geçip geri dönerim.
18. Operatör olarak, çekmece daralırken ya da genişlerken içeriğin kırılmadan yeniden akmasını istiyorum; böylece dar genişlikte de okurum.
19. Operatör olarak, çekmece genişliği değişince haritanın odağını (seçili kare ya da temas) korumasını istiyorum; böylece baktığım yer kaymaz.

### Görüntü çekmecesi ve tespit kutuları

20. Operatör olarak, Görüntü çekmecesinde gereksiz açıklama metni görmemek istiyorum; böylece önizleme ve filtreler daha üstte kalır.
21. Operatör olarak, küçük ve uzaktaki bir aracın kutusunun aracın kendisi kadar olmasını istiyorum; böylece hangi aracın işaretlendiğini karıştırmam.
22. Operatör olarak, kutu çerçevesinin kutunun içine çizilmesini istiyorum; böylece çerçeve kalınlığı kutuyu dışa doğru büyütmez.
23. Operatör olarak, seçili küçük bir kutunun yine seçili olduğunu açıkça görmek, ama kutunun büyümemesini istiyorum; böylece seçim gösterimi komşu araçları örtmez.
24. Operatör olarak, düşük güvenli bir tespitin daha ince çizgiyle çizilmesini istiyorum; böylece güvenilirliği ayırt ederim.
25. Operatör olarak, aynı araç için modelin iki sınıf önerdiği yerde yalnızca en yüksek güvenli sınıfın kutusunu ve rengini görmek istiyorum; böylece bir araç üzerinde iki renk görmem.
26. Operatör olarak, çizilmeyen ikinci sınıf önerisinin Araçlar listesinde "aynı araç, düşük güvenli ikinci sınıf" diye soluk görünmesini istiyorum; böylece görüntü ile liste çelişmez ve model çıktısını kaybetmem.
27. Operatör olarak, kutu etiketinin sınıfı, güveni ve track kimliğini göstermeye devam etmesini istiyorum; böylece bir tespiti hızlıca tanırım.

### Risk & Araçlar

28. Operatör olarak, sağ panelin ve listenin adını "Risk & Araçlar" / "Araçlar" olarak görmek istiyorum; böylece içinde ne olduğunu hemen anlarım.
29. Operatör olarak, bu adın ikon ipucunda, çekmece başlığında, sekmede, liste başlığında ve göz atma özetinde aynı olmasını istiyorum; böylece terimler arasında çevirmek zorunda kalmam.
30. Operatör olarak, bir araç satırında kimliği, sınıfını, seviyesini ve üsse mesafesini görmek istiyorum; böylece öncelikleri hızla sıralarım.
31. Operatör olarak, satırda "kesinlik" ve tür rozeti metni görmemek istiyorum; böylece satırlar kısa ve taranabilir olur.
32. Operatör olarak, takip durumunu satırdaki sınıf karesinin çizgi biçiminden (düz / kesikli / noktalı) anlamak istiyorum; böylece harita ve görüntüyle aynı dili okurum.
33. Operatör olarak, listenin üstünde kaç sonucun yüksek, orta ve düşük kesinlikte olduğunu gösteren bir özet görmek istiyorum; böylece "kaç güvenilir sonuç var?" sorusunu tek bakışta cevaplarım.
34. Operatör olarak, özetteki bir kesinlik grubuna tıklayınca listenin o gruba süzülmesini, tekrar tıklayınca süzmenin kalkmasını istiyorum; böylece düşük kesinlikli sonuçları ayrıca inceleyebilirim.
35. Operatör olarak, kesinlik etiketlerini "Yüksek kesinlik", "Orta kesinlik", "Düşük kesinlik", "Doğrulanamadı" olarak okumak istiyorum; böylece ne anlama geldiklerini tahmin etmem.
36. Operatör olarak, seçili aracın detay kartında kesinliği tek satırda, zayıf tespit bilgisiyle birlikte görmek istiyorum; böylece aynı bilgiyi iki satırda okumam.
37. Operatör olarak, seviye rozetlerinin ve seviye sıralamasının aynı kalmasını istiyorum; böylece risk bilgisi sadeleşmeden etkilenmez.

### Brief

38. Operatör olarak, Brief'in en üstünde görüntü seviyesini ve önerilen eylemi büyük bir özet kartında görmek istiyorum; böylece kararın özünü ilk saniyede okurum.
39. Operatör olarak, özet kartında görüntü kimliğini, Bölge'yi, çekim anını ve araç sayısını görmek istiyorum; böylece hangi karenin Brief'ini okuduğumu bilirim.
40. Operatör olarak, Brief metninin paragraflara ve varsa madde listelerine bölünmüş, rahat satır aralığıyla gösterilmesini istiyorum; böylece uzun metni takip ederim.
41. Operatör olarak, "Kaynaklar"ı ve LLM/otomatik özet bilgisini katlanır bir bölümde görmek istiyorum; böylece gerektiğinde açarım ama sürekli yer kaplamaz.
42. Operatör olarak, Brief'teki hiçbir bilginin kaybolmamasını istiyorum; böylece sadeleşme bir şeyi saklamaz.

### Günün görüntüleri

43. Operatör olarak, "Günün görüntüleri" şeridinin başlangıçta kapalı gelmesini istiyorum; böylece harita daha büyük görünür.
44. Operatör olarak, kapalı şeritte seçili kareyi, saatini ve kare sayısını görmek istiyorum; böylece açmadan nerede olduğumu bilirim.
45. Operatör olarak, şeridi bir chevron düğmesiyle açıp kapatmak istiyorum; böylece gerektiğinde günün akışına bakarım.
46. Operatör olarak, şeridin yumuşak bir geçişle açılıp kapanmasını istiyorum. Hareket azaltma tercihim varsa geçiş olmamalı; böylece değişimi izlerim ama rahatsız olmam.
47. Operatör olarak, şerit kapalıyken de ←/→ ile önceki/sonraki kareye geçebilmek istiyorum; böylece kısayol her zaman çalışır.
48. Operatör olarak, "Seçili kare · son 2 saat" şeridinin bu panelle birlikte açılıp kapanmasını istiyorum; böylece alt alan tek bir birim gibi davranır.

### İz analizi: açma, filtre ve sayılar

49. Operatör olarak, sağ rayın en üstündeki "İz analizi" ikonuyla küçük bir panel açmak istiyorum; böylece günün bütün track'lerine tek tıkla ulaşırım.
50. Operatör olarak, İz analizi panelinin haritanın sağ üst köşesinde küçük ve opak bir kart olarak açılmasını istiyorum. Harita daralmamalı, kartın dışındaki alan etkileşimli kalmalı; böylece haritayı kullanmaya devam ederim.
51. Operatör olarak, İz analizi ile Risk & Araçlar'ın aynı anda açık olabilmesini istiyorum; böylece bir aracı hem listede hem hareketinde incelerim.
52. Operatör olarak, panelde Kritik, Yüksek, Orta ve Düşük seviye anahtarlarını ve bir "Hepsi" anahtarını görmek istiyorum; böylece hangi riskleri gördüğümü seçerim.
53. Operatör olarak, birden fazla seviyeyi aynı anda seçebilmek istiyorum (örn. Kritik + Orta); böylece ilgilendiğim riskleri birlikte görürüm.
54. Operatör olarak, "Hepsi"ye basınca bütün seviyelerin seçilmesini, bütün seviyeleri tek tek seçince "Hepsi"nin de seçili görünmesini istiyorum; böylece iki yol da aynı sonucu verir.
55. Operatör olarak, seçili anahtarların seviye rozetleriyle aynı görsel dilde, dolu ve işaretli, seçili olmayanların ise sönük görünmesini istiyorum; böylece hangi riskleri gördüğümü yanılmadan anlarım.
56. Operatör olarak, her seviye anahtarının yanında o seviyedeki track sayısını görmek istiyorum. Sayısı 0 olan seviye seçilemez ama görünür olmalı; böylece hangi riskin veride olmadığını da bilirim.
57. Operatör olarak, panelde filtreye uyan track sayısını ("226 track'ten 50'si") belirgin biçimde görmek istiyorum; böylece haritada kaç iz gördüğümü bilirim.
58. Operatör olarak, oynatma sırasında o an haritada görünen araç sayısını da görmek istiyorum; böylece zamanın yoğunluğunu anlarım.
59. Operatör olarak, bir track'in seviyesinin, bittiği Görüntü'nün son değerlendirmesindeki Temas'ın nihai seviyesi olmasını istiyorum; böylece iz analizi ile Görüntü seviyeleri birbiriyle çelişmez.
60. Operatör olarak, bittiği Görüntü hiç değerlendirilmemiş bir track'i "Değerlendirilmedi" grubunda görmek istiyorum; böylece seviyesi uydurulmaz. Bu grup yalnızca böyle bir track varsa görünür.
61. Operatör olarak, panelde seviyenin kaynağını söyleyen kısa bir not görmek istiyorum ("seviye: track'in bittiği görüntünün son değerlendirmesi"); böylece sayının nereden geldiğini bilirim.
62. Operatör olarak, bir Görüntü yeniden değerlendirilince, panel açıksa track seviyelerinin kendiliğinden yenilenmesini istiyorum; böylece eski seviyeye bakmam.

### İz analizi: haritada gösterim

63. Operatör olarak, oynatma hiç başlamamışken filtreye uyan bütün track'leri tam yollarıyla, hareketsiz görmek istiyorum; böylece günün hareketinin bütün resmini görürüm.
64. Operatör olarak, filtreyi değiştirince haritadaki track'lerin anında azalıp artmasını istiyorum; böylece filtrenin etkisini hemen görürüm.
65. Operatör olarak, track çizgilerinin mevcut renk dilinde, yani araç sınıfının renginde olmasını istiyorum. Tipi bilinmeyen track'ler nötr olmalı; böylece seviye renkleriyle sınıf renkleri karışmaz.
66. Operatör olarak, yüzlerce track açıkken çizgilerin ince ve yarı saydam olmasını istiyorum; böylece harita çizgi yığınına dönmez ve bölge, Üs, seçili temas okunur kalır.
67. Operatör olarak, bir track'in üzerine gelince çizgisinin kalınlaşıp öne çıkmasını, kimliğini, sınıfını, seviyesini ve kayıt aralığını gösteren bir ipucu görmek istiyorum; böylece kalabalıkta tek bir izi okurum.
68. Operatör olarak, bir track'e ya da araca tıklayınca onun vurgulanmasını, diğerlerinin soluklaşmasını ve panelde adının yazmasını istiyorum; böylece bir aracı takip ederim.
69. Operatör olarak, vurgulanan track için panelde "Görüntüye git: img_…" bağlantısı görmek istiyorum. Tıklayınca o Görüntü seçilmeli ve Temas Araçlar listesinde seçili gelmeli; böylece izden değerlendirmeye geçerim.
70. Operatör olarak, vurguyu tekrar tıklayarak ya da Esc ile kaldırmak istiyorum; böylece genel görünüme dönerim.
71. Operatör olarak, İz analizi açıkken seçili Görüntü'nün temaslarının ve rotalarının soluklaşmasını ama kaybolmamasını istiyorum; böylece iki katman birbirine karışmaz.
72. Operatör olarak, panel açılınca haritanın filtreye uyan bütün track'leri kapsayacak şekilde sığmasını istiyorum; böylece kaydırmadan hepsini görürüm.
73. Operatör olarak, paneli kapatınca iz katmanının tamamen kalkmasını ve haritanın önceki haline dönmesini istiyorum; böylece iz analizi seçili Görüntü incelemesini bozmaz.
74. Operatör olarak, iz çizgilerinin ve araç noktalarının açık, koyu ve uydu zeminlerinde görünür olmasını istiyorum; böylece zemin değişince kaybolmazlar.

### İz analizi: zaman simülasyonu

75. Operatör olarak, panelde günün gerçek kayıt aralığını kapsayan bir zaman çizgisi görmek istiyorum (veride 08:10–15:50); böylece hangi saatlerde veri olduğunu bilirim.
76. Operatör olarak, zaman çizgisinde o an seçili saati büyük ve mono yazıyla görmek istiyorum; böylece "şu an saat kaç" sorusunu tek bakışta cevaplarım.
77. Operatör olarak, Oynat'a basınca simülasyonun seçili zamandan ilerlemeye başlamasını istiyorum; böylece günün hareketini izlerim.
78. Operatör olarak, oynatma başlayınca yalnızca o anda kaydı olan araçları görmek istiyorum; böylece o anki gerçek durumu görürüm.
79. Operatör olarak, her aracın o anki konumunda görünmesini ve kaydındaki gerçek hızı ve duraklamalarıyla ilerlemesini istiyorum; böylece hareket veriye dayanır, süs değildir.
80. Operatör olarak, iki kayıt arasındaki konumun iki gerçek kayıt noktasının arasında düz çizgi üzerinde gösterilmesini ve bunun "5 dk'lık kayıtlar arası ara konum" olarak panelde belirtilmesini istiyorum; böylece gösterilen konumun kayıt mı ara değer mi olduğunu bilirim.
81. Operatör olarak, bir aracın yalnızca kendi kayıt aralığında görünmesini istiyorum. İlk kaydından önce görünmemeli, son kaydının anında son konumunda görünmeli, son kaydından sonra kaybolmalı; böylece kaydı bitmiş bir araç haritada kalmaz.
82. Operatör olarak, hareket eden aracın arkasında son 15 dakikalık kısa bir kuyruk görmek istiyorum; böylece yönünü ve hızını okurum ama geçmiş yol ekranı doldurmaz.
83. Operatör olarak, araç noktasında seviyesini gösteren baklava simgesini (dolgu merdiveni) görmek istiyorum; böylece hareket halindeki riskli aracı ayırt ederim.
84. Operatör olarak, Duraklat'a basınca simülasyonun o anda donmasını ve yalnızca o an kaydı olan araçların konumlarında kalmasını istiyorum; böylece bir anı inceleyebilirim.
85. Operatör olarak, Duraklat'tan sonra Oynat'a basınca kaldığı zamandan devam etmesini istiyorum; böylece baştan başlamam.
86. Operatör olarak, zaman çizgisinin tutamacını sürükleyerek ileri geri gitmek istiyorum. Her konumda araçların görünürlüğü, konumu, kuyruğu ve seviyesi o ana göre güncellenmeli; böylece günü elle tararım.
87. Operatör olarak, zaman çizgisinde bir noktaya tıklayınca simülasyonun doğrudan o zamana atlamasını istiyorum. O anda kaydı olmayan araçlar görünmemeli; böylece istediğim saate hemen giderim.
88. Operatör olarak, sürüklemenin ya da atlamanın oynatmayı başlatmamasını istiyorum. Oynatma sürerken sürüklersem sürükleme bitince oynatma kaldığı yerden devam etmeli; böylece kontrol bende kalır.
89. Operatör olarak, zaman çizgisinde kaydın yoğun olduğu saatleri gösteren silik bir yoğunluk göstergesi görmek istiyorum; böylece ilginç saatlere atlarım.
90. Operatör olarak, oynatma hızını 0,5×, 1×, 2× ve 4× arasından küçük bir kontrolle seçmek istiyorum. 1×'in gerçek zamanda saniyede 5 dakika olduğu ipucunda yazmalı; böylece günü istediğim hızda izlerim.
91. Operatör olarak, oynatma kaydın sonuna ulaşınca durmasını istiyorum, başa sarmamalı; böylece son durumu görürüm.
92. Operatör olarak, Sıfırla'ya basınca oynatmanın hiç başlamamış hale dönmesini istiyorum: bütün filtreli track'ler statik ve tam yolla görünmeli; böylece genel görünüme dönerim.
93. Operatör olarak, Oynat/Duraklat düğmesinin durumunu ikonuyla, erişilebilir adıyla ve basılı durumuyla açıkça görmek istiyorum; böylece simülasyonun oynayıp oynamadığını bilirim.
94. Klavye kullanan operatör olarak, zaman çizgisini ok tuşlarıyla 5 dakika, PageUp/PageDown ile 30 dakika kaydırabilmek istiyorum; böylece fare olmadan gezinirim.
95. Operatör olarak, İz analizi açıkken ←/→ kısayolunun zaman çizgisine odaklanmışsam zamanı değiştirmesini, değilsem eskisi gibi kare değiştirmesini istiyorum; böylece kısayollar çakışmaz.
96. Ekran okuyucu kullanan operatör olarak, oynatma durduğunda ya da zaman atlandığında "13:20 · 18 araç görünüyor" gibi tek bir durum mesajı duymak istiyorum. Her karede duyuru olmamalı; böylece sesli geri bildirim boğucu olmaz.
97. Hareket azaltma tercihi olan operatör olarak, oynatmanın yine çalışmasını ama kuyruk ve geçiş efektlerinin sadeleşmesini istiyorum; böylece özellik kullanılabilir kalır.

### Lejant ve harita denetimleri

98. Operatör olarak, sol alt köşede her zaman duran küçük bir lejantta araç sınıfı renklerini görmek istiyorum; böylece çizgi ve kutu renklerini hemen çözerim.
99. Operatör olarak, lejantın katlanmamasını ve haritanın ancak çok küçük bir köşesini kaplamasını istiyorum; böylece hem her zaman görünür hem de engel olmaz.
100. Operatör olarak, Uydu/Sokak anahtarının yakınlaştırma düğmelerinin yanında durmasını istiyorum; böylece sağ üst köşe İz analizi kartına kalır ve denetimler üst üste binmez.

### Performans

101. Operatör olarak, 226 track açıkken ve oynatma sırasında haritanın akıcı kalmasını, panellerin ve listenin takılmamasını istiyorum; böylece demo sırasında ekran donmaz.

## Implementation Decisions

### Terimler
- Arayüz etiketi "Araçlar"dır (Temas'ın arayüzdeki adı). Alan dili, kod, API ve testlerdeki kimlikler "Temas" olarak kalır. Kök glossary'ye (`CONTEXT.md`) bu eşleme bir not olarak eklenir.
- Yeni kavram: **İz analizi**. Günün bütün Track'lerinin seviyeye göre süzülüp zaman içinde oynatılması. Glossary'ye eklenir.

### Veri: track'ler ve seviyeleri (backend)
- Yeni salt okunur uç: **`GET /tracks`**. Her Track için şunları döner:
  - kimlik, ilk ve son kayıt saati (`start`, `end`), kayıt noktaları (saat, enlem, boylam; olduğu gibi);
  - `image_id`: track'in bittiği Görüntü;
  - `level`: o Görüntü'nün son tamamlanmış değerlendirmesindeki Temas'ın nihai seviyesi, yoksa `null`;
  - `label`: o Temas'ın sınıfı (`effective_label` ya da `label`), tespitsizse `null`;
  - `kind`: Temas türü, yoksa `null`.
- **Track → Görüntü eşlemesi:** track'in son kaydının saati bir Görüntü'nün çekim anına eşit ve son konumu o Görüntü'nün karesinin içinde (veya eşleşme eşiği kadar yakınında). Veride 226 track'in 226'sı bu koşulu sağlıyor. Eşleme mevcut aday seçimiyle aynı kuralı kullanır: çekim anında karenin içinde ya da eşiğe yakın track.
- **Seviye kaynağı:** her Görüntü'nün son tamamlanmış değerlendirmesinin Brief'i. Kayıt deposuna, mevcut `latest_levels` gibi "her Görüntü'nün son tamamlanmış Brief'i" okuyan bir sorgu eklenir. Yeni değerlendirme yapılmaz, LLM çağrılmaz, seviye yeniden hesaplanmaz.
- **Geri alınacak ara iş:** bu konuşmada yazılan ve seviyeyi hareket kuralıyla tip bilinmeden hesaplayan ilk `/tracks` sürümü, `summarize_motion` ayrımı ve hareket-kuralı testi. Uç yeni sözleşmeyle yeniden yazılır.
- Arayüz tipleri OpenAPI şemasından yeniden üretilir, test verisi backend'den dışa aktarılır (mevcut `fixtures` akışı).

### Durum (frontend deposu)
- **Tek seçim deposu** korunur. Yeni alanlar:
  - taraf başına çekmece genişliği (tarayıcıda saklanır);
  - iz analizi açık mı;
  - seçili seviyeler (küme);
  - oynatma durumu (`hazır` = hiç başlamadı, `oynuyor`, `duraklatıldı`);
  - simülasyon zamanı (dakika);
  - hız;
  - vurgulanan track;
  - track listesi yükleme durumu (mevcut `idle/loading/ready/error` kalıbı);
  - "Günün görüntüleri" açık mı;
  - Araçlar listesinin kesinlik süzgeci.
- **Oynatma saati depoya her karede yazılmaz.** Animasyon döngüsü (`requestAnimationFrame`) zamanı kendi içinde ilerletir, harita katmanını doğrudan günceller. Depoya ve React'e yalnızca seyrek yazar: saat göstergesi dakikada bir ya da insan gözünün fark edeceği aralıkla, "görünen araç sayısı" değiştiğinde, duraklat/durunca. Böylece her karede bileşen ağacı yeniden çizilmez.
- **Çekmece durumları:** `closed | open | full`. `peek` kalkar; genişlik ayrı bir sayıdır, `full` sabit geniş görünümdür. Sağ çekmecenin paneli Risk & Araçlar'dır; `riskTab` (`temaslar | brief`) korunur. Brief'in ayrı kenar sekmesi kalkar, "B" kısayolu `openRight("brief")` olarak kalır.

### Simülasyon modülü (saf)
- Derin, saf bir modül: girdi track listesi, seçili seviyeler, zaman (ya da `null` = hazır hali), vurgulanan track, kuyruk süresi. Çıktı harita katmanının GeoJSON'u:
  - **hazır hali:** filtreye uyan her track için tam yol (çizgi);
  - **zaman t:** yalnızca `start ≤ t ≤ end` olan track'ler için baş noktası ve `max(start, t − 15 dk)`'dan t'ye kadarki kuyruk;
  - her özellikte kimlik, sınıf tonu, seviye, vurgu ve soluk bayrakları.
- **Ara konum:** t iki kayıt arasındaysa iki kaydın konumu arasında doğrusal ara değer. Tam bir kayıt saatindeyse kaydın kendisi. `t > end` ise hiçbir şey çizilmez: son konum ekranda kalmaz. `t = end` son kayıttır.
- Duraklama gerçek veriden kendiliğinden gelir (ardışık kayıtlar aynı yerde). Ayrı hız hesabı yapılmaz.
- Filtre sayıları (seviye başına, toplam) ve "t anında görünen" sayısı da bu modülden türetilir.

### Harita
- Harita arayüzüne yeni bir alan katmanı eklenir: **`izler`**. Çizgiler ve baş noktaları tek GeoJSON kaynağında, mevcut `setArea` yoluyla verilir; DOM işaretçisi kullanılmaz (226 nokta için).
- Çizim sırası: bölge alanları < ayak izi < Üs halkaları < **izler** < seçili Görüntü'nün rotaları. İz analizi açıkken seçili Görüntü'nün rotaları ve temasları soluklaşır.
- **Görsel dil:**
  - çizgi rengi = sınıf tonu (tip bilinmiyorsa nötr);
  - hazır halinde ince (~1,25 px) ve yarı saydam (~0,35);
  - vurgulu track kalın ve tam opak, diğerleri daha soluk;
  - kuyruk başa doğru opaklaşır;
  - baş noktası seviye baklavası: dolgu merdiveni, sembol katmanı; baklava görselleri tema token'larından üretilir, tema değişince yeniden üretilir;
  - her çizginin altında zeminin tersi ince bir kılıf (mevcut rota kılıfıyla aynı).
- **Etkileşim:** üzerine gelme, çizgi ve baş noktalarında ipucu gösterir; tıklama vurgular. Olaylar mevcut `onMarkerClick` gibi harita arayüzünün olay yoluyla sayfaya iletilir (yeni olay: `onAreaFeatureClick/Hover`).
- **Sığdırma:** panel açılınca filtreye uyan bütün track'lere sığdırılır. Mevcut "yeniden boyutlanınca son sığdırmayı koru, kullanıcı kaydırdıysa dokunma" kuralı geçerli.
- Uydu/Sokak anahtarı sol üste taşınır. Sağ üst köşe İz analizi kartınındır.

### İz analizi kartı
- Harita panelinin içinde, sağ üstte, üstte yüzen opak bir kart; haritayı daraltmaz. Genişlik ~320 px (dar ekranda harita genişliğinin en fazla ~%45'i). Yükseklik içeriğe göre, en fazla harita yüksekliğinin ~%60'ı; taşarsa kart içinde kayar.
- **Başlık:** "İz analizi" + kapat. Bilgi sırası:
  1. Seviye anahtarları (Hepsi · Kritik · Yüksek · Orta · Düşük [· Değerlendirilmedi]); her birinde sayı; seçili hali seviye rozeti dilinde; `aria-pressed`.
  2. Sayı satırı: "226 track'ten 50'si · şu an 18 araç" + seviye kaynağı notu.
  3. Büyük saat göstergesi.
  4. Zaman çizgisi: kaydırıcı rolü, 5 dk adım, saat etiketleri, silik yoğunluk göstergesi.
  5. Oynatma satırı: Oynat/Duraklat · Sıfırla · hız segmenti (0,5× 1× 2× 4×).
  6. Vurgulu track satırı (varsa): kimlik, sınıf, seviye, kayıt aralığı, "Görüntüye git".
- **İkonlar:** mevcut kütüphanenin (lucide) aynı çizgi kalınlığındaki ikonları.
  - rayda İz analizi `Route`, Risk & Araçlar `ShieldAlert`, Görüntü `Image`;
  - oynat `Play`, duraklat `Pause`, sıfırla `RotateCcw`;
  - panel kapat `X`;
  - "Günün görüntüleri" chevron `ChevronUp/Down`.

### Kenar rayı ve çekmece resize
- Ray ikon düğmeleri kare ~36 px, simge 18 px. Radix ipucu adı ve kısayolu gösterir. Etkin düğme ters renk (birincil mürekkep); mavi kullanılmaz, çünkü mavi seçili veri içindir. Erişilebilir ad metinle aynıdır.
- **Resize:**
  - Tutamaç işaretçiyi yakalar (pointer capture) ve hareketleri tutamağın kendisinden izler.
  - Sürüklerken genişlik geçişi kapalıdır; gövdeye `col-resize` imleci ve metin seçimini kapatan bir sınıf eklenir.
  - Harita ve diğer katmanların olayları engellenmez: tutamaç kendi katmanında ve üstte, olay yayılımı durdurulur.
  - Bırakınca genişlik olduğu gibi kalır ve saklanır.
- **Sınırlar:** en az 280 px; en fazla ekranın %50'si ve haritaya en az 400 px kalacak kadar. Pencere küçülünce sınıra çekilir.
- Tutamaç `role="separator"`, `aria-valuenow/min/max`, klavye ←/→ 16 px, Home/End min/max.

### Görüntü ve tespit kutuları
- Açıklama metni kaldırılır.
- **Kutu çizimi:**
  - çerçeve kutunun içine çizilir, dış kılıf yok;
  - çizgi kalınlığı gösterilen kutu boyutuna göre ölçeklenir (en küçük kutularda 1 px, normalde 2 px);
  - seçim halesi kutu boyutunu büyütmez: iç çerçeve kalınlaşır, hale kutu küçükse yalnızca köşe işaretleriyle verilir;
  - etiket çipi kutudan bağımsız konumlanır.
- **Çift sınıf, yalnızca çizimde:** aynı karede kutuları IoU ≥ 0,7 olan tespitler bir "aynı araç" grubudur. Grupta yalnızca en yüksek güvenli olanın kutusu ve rengi çizilir. Diğerleri görüntüde çizilmez; Araçlar listesinde "aynı araç, düşük güvenli ikinci sınıf" olarak soluk gösterilir. Seviye hesabı, sayılar ve backend değişmez.
- Mevcut güven kuralları (0,20 altı yok sayılır, 0,20–0,50 zayıf, 0,50 ve üstü güçlü) değişmez; %60 gibi yeni bir eşik eklenmez.

### Risk & Araçlar ve Brief
- **Kesinlik etiketleri:** `certain` → "Yüksek kesinlik", `likely` → "Orta kesinlik", `weak` → "Düşük kesinlik", `unverified` → "Doğrulanamadı".
- **Özet:** Brief'teki Temas'ların kesinlik dağılımından istemcide sayılır. Her sayı bir süzgeç düğmesi (`aria-pressed`). Sayısı 0 olan grup devre dışıdır.
- **Satır:** kimlik · sınıf karesi (takip durumu çizgisi) + sınıf adı · seviye rozeti · üsse mesafe. Tür, erişilebilir adda ve detay kartında kalır.
- **Brief düzeni:**
  1. özet kartı: seviye rozeti büyük, önerilen eylem, kare kimliği · Bölge · çekim anı · araç sayısı;
  2. metin bölümü: paragraflara bölünür, madde satırları liste olarak;
  3. katlanır "Kaynaklar";
  4. katlanır "Model" (LLM ya da otomatik özet gerekçesi).

  Bilgi silinmez.

### Günün görüntüleri
- Başlangıç: kapalı. Kapalı çubuk yaklaşık 40 px yüksekliğinde, açık panel mevcut yükseklik. Yükseklik geçişi 200 ms, hareket azaltmada yok. Açık/kapalı durumu tarayıcıda saklanır.

### Lejant
- Sol altta her zaman görünen, katlanmayan küçük kutu: yalnızca sınıf renkleri. Diğer açıklamalar (takip çizgileri, seviye dolgusu, bölge, ayak izi) kaldırılır. Bu açıklamalar ilgili yerlerde zaten var: rozet ve ipuçları, İz analizi kartındaki not.

### Tasarım dokümanı
- Tasarım kararları dokümanı (operasyon sayfası) bu kararlarla güncellenir: ikon rayı, resize kuralları, İz analizi görsel dili, lejant.

## Testing Decisions

- **İyi test:** yalnızca dışarıdan görülen davranışı doğrular. Sayfada kullanıcının gördüğü ve yaptığı, haritaya ne çizdirildiği, API'nin ne döndürdüğü. İç durum, bileşen yapısı ve sınıf adları test edilmez. İstisna: görsel kodlamanın kendisi bir davranış olduğunda (örn. takip durumu çizgisi) mevcut testler gibi.
- **Seam'ler** (mevcutlar; yeni seam açılmaz):
  1. **Sayfa seviyesi (Vitest + Testing Library + MSW + sahte harita).** Kenar rayı ve ipuçları, Brief'in kenar düğmesinin olmaması, resize (işaretçi olaylarıyla sürükle/bırak, sınırlar, kalıcılık, klavye), Görüntü çekmecesinde metnin olmaması, çift sınıflı kutuların tek çizilmesi, "Araçlar" terimi, kesinlik özeti ve süzgeci, Brief bölümleri, "Günün görüntüleri"nin katlanması, İz analizi kartı. İz analizi kartında sınanacaklar: filtre çoklu seçim/Hepsi, sayılar, hazır halinde haritaya giden çizgi sayısı; zaman atlamada görünen/görünmeyen track'ler; bitişten sonra kaybolma; vurgulama ve "Görüntüye git"; paneli kapatınca katmanın boşalması. Sahte harita `izler` katmanını diğer alan katmanları gibi kaydeder. Oynatma testleri sahte zamanlayıcıyla (vitest fake timers + rAF) yapılır. Önceki örnek: `temaslar-harita`, `son-iki-saat`, `goruntu-secimi`, `operasyon-ekrani` testleri.
  2. **Saf simülasyon modülü (birim testi, modülün yanında).** Kayıt saatinde kaydın kendisi; iki kayıt arasında doğrusal ara değer; `start` öncesi yok; `end` anında son konum; `end` sonrası yok; 15 dk kuyruk ve başlangıçta kırpılması; filtre ve sayılar; hazır halinde tam yol. Örnek: A 10:00–11:00 track'i 09:30'da yok, 10:00'da ilk konumda, 11:00'da son konumda, 11:01 ve 11:30'da yok. Önceki örnek: `geo.test`, `temas.test`, `sahne.test`.
  3. **Backend HTTP (FastAPI TestClient, bellek içi depo + bellek içi kayıt deposu).** `/tracks` şunları doğrular: her track kayıtlarıyla birlikte ve sırasıyla döner; track'in bittiği Görüntü doğru eşlenir; son tamamlanmış değerlendirmesi olan Görüntü'nün track'i o Brief'teki Temas'ın nihai seviyesini ve sınıfını alır; daha yeni bir değerlendirme eskisini geçer; değerlendirmesi olmayanlar `null` alır; uç LLM ya da tespit çağırmaz. Önceki örnek: `test_data_api.py` (`/images`'ın `last_risk_level` testi).
- Mevcut testlerden ifadesi değişenler ("Temaslar" → "Araçlar", kesinlik sütunu, lejant metinleri, Brief kenar sekmesi, Görüntü çekmecesindeki metin, göz atma hali) yeni kararlara göre güncellenir, silinmez.
- Playwright (`e2e/`) gerçek MapLibre'de şunları duman testi olarak doğrular: İz analizi katmanının çizilmesi, oynatınca en az bir aracın konum değiştirmesi, açık ve koyu temada görünürlük (ekran görüntüsü). Backend gerektirdiği için `BACKEND=1` ile.

## Out of Scope

- Backend'in tespit, eşleşme, seviye veya Brief mantığında herhangi bir değişiklik. Çift sınıflı kutular yalnızca çizimde çözülür; sınıflar arası bastırma backend'e eklenmez.
- Güven eşiklerinin değiştirilmesi (örn. %60).
- Track'lere yeni risk hesabı; tipi olmayan track'lere tip atanması; kaydı olmayan zamanlar için konum üretilmesi (kayıt aralığı dışına tahmin).
- Simülasyonun sunucu tarafında yürütülmesi, canlı veri akışı, kaydın 08:10–15:50 dışına genişletilmesi.
- Sohbet çekmecesi (daha önce kaldırılmış).
- Mobil / dar ekran için ayrı yerleşim. Paneller mevcut masaüstü düzeni içinde sınırlandırılır.
- Değerlendirilmemiş Görüntü'lerin toplu değerlendirilmesi.

## Further Notes

- **Olgular:**
  - Veride 226 Track var (kullanıcının tahmini ~256 idi); her biri 25 kayıt, 5 dk aralıklı, tam 2 saat.
  - Hepsi bir Görüntü'nün çekim anında o Görüntü'nün karesinde bitiyor.
  - 40 Görüntü'nün hepsinin tamamlanmış değerlendirmesi var: 23 yüksek, 13 orta, 3 kritik, 1 düşük. Yani bugün her track'in bir seviyesi ve çoğunun sınıfı var.
- **Çift sınıf:** 264 kutudan 14 çift. Sahte "kayıt dışı temas" yan etkisi backend'de kalıyor; kullanıcı bunu bilerek yalnızca çizimde düzeltmeyi seçti. İleride backend'de sınıflar arası bastırma ayrı bir karar olarak ele alınabilir.
- **Tutamaç sorunu:** mevcut sürüklemede bırakınca dört sabit genişlikten birine atlama ve sürüklerken genişlik geçişi, "bazen çalışmıyor" algısının başlıca nedenleri. Tutamacın harita paneline taşan kısmı da olayları haritayla paylaşıyor.
- **Hız:** 1× = gerçek zamanda saniyede 5 dakika. Bütün gün 1×'te yaklaşık 92 sn, 4×'te yaklaşık 23 sn.
- **Kuyruk:** oynatmada 15 dakika (3 kayıt aralığı).
- ADR-0001 (çekim anından sonrasını görme) İz analizi için geçerli değildir. İz analizi bir Görüntü'nün değerlendirmesi değil, günün kayıtlarının tamamına bakıştır. Seçili Görüntü'nün paneli ve rotaları bu kurala uymaya devam eder. Bu ayrım spec'te ve glossary notunda açıkça yazılı olmalı.
- Ardından bu spec'ten bilet çıkarılacak (`/to-tickets`), dikey dilimler hâlinde: ray + resize; Görüntü + kutular; Araçlar + Brief; Günün görüntüleri + lejant; `/tracks` ucu; İz analizi kartı + filtre; simülasyon + oynatma.
