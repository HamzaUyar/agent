# Roketsan LEVEL-UP AI Hackathonu — Aşama 2: Saha Raporu Destekli LLM Agent

## Bağlam
- Aşama 1 (Kaggle araç tespiti) bitti, public mAP@0.5 = 0.792.
- Aşama 2: Tespit modelini kullanan bir LLM agent. Drone görüntüsü + hareket kayıtları + saha raporları → üs için risk kararı + gerekçeli kısa brief.
- Değerlendirme: Mentörler kodu inceler (teknik kalite + mimari), jüri sunum/demo ile puanlar (İş Değeri, Çalışan Ürün, Ürün/UX, Sunum/Demo). Agent en az 1–2 görüntüde canlı çalışmalı.
- LLM: GLM API (15 $ kredi, OpenAI-uyumlu function calling). Geliştirmede ücretsiz Flash modelleri, final çıktıda GLM-5.x.

## Tespit sistemi (Aşama 1'den)
- 3 YOLO26 modeli (yolo26m_best, D2=YOLO26l, colab26m), her biri tam görüntü + 800px SAHI tile.
- Sınıf bazlı NMS 0.6 → 3 üyeli WBF (IoU 0.6, avg) → ConvNeXt-Tiny car/van yeniden puanlama (a=0.3).
- Sınıflar: car, van, truck, bus. Val mAP@0.5 = 0.843. Ek: D-FINE-m (val 0.758, van'da iyi).
- Agent için mAP değil, bir çalışma eşiği gerekir (confidence ~0.35–0.45, track eşleşme oranıyla ayarlanacak).

## Veri
- `image_meta.json`: 40 görüntü. width_px, height_px (960×540, 1360×765, 1920×1080), capture_time ("HH:MM"), corner_coordinates (top_left, top_right, bottom_left, bottom_right; [lat, lon]).
  - Köşeler eksene hizalı dikdörtgen. Dönüşüm (organizatörün kullandığı, bunu kullan):
    - `lon = TL_lon + (cx / W) * (TR_lon - TL_lon)`
    - `lat = TL_lat + (cy / H) * (BL_lat - TL_lat)`
    - cx, cy = kutunun MERKEZİ. Doğrulama: img_000860, merkez (756, 301) → 39.92531, 32.87183.
- `zones.json`: base "Merkez Us" (39.92184, 32.85306) + 8 bölge merkezi: Kuzey Yolu, Kuzeydogu Kavsagi, Dogu Yolu, Guneydogu Yerlesimi, Guney Kapisi Yaklasimi, Guneybati Yolu, Bati Yerlesimi, Kuzeybati Yolu (ASCII yazım).
- `tracks.csv`: track_id,time,lat,lon. 226 track × 25 satır (2 saat, 5 dk adım, uçlar dahil).
  - Her track bir araç. Her track'in SON satırı bir görüntünün capture_time'ına denk gelir.
  - 206 track bittiği anda o görüntünün alanı İÇİNDE (görüntü başına 3–8). Hiçbir track birden fazla karede değil.
  - DOĞRULANDI: Çekim anlarında karelerin içine düşen 206 satırın 206'sı da track'in SON satırı; son satır olmayan hiçbir satır bir karede değil.
  - 162 track karenin alanına sadece son satırda giriyor; 22 track 2 saatin tamamını o karenin alanında geçirmiş (park halindeki araç).
  - 20 track bir çekim anında bitiyor ama karenin kenarının 6,6–26 m DIŞINDA. Kenarda kesik/kısmen görünen araç olabilir: kenara yakın tespitlerle eşleşmeye izin ver (eşik ~30 m), değilse "kare kenarında kayıtlı araç, görüntüde yok" olarak not et.
  - Örnek: T0122 → img_000860'taki truck. 14:10'da <1 m. Üsse mesafe: 12:10–12:50 5,95 km (40 dk bekleme) → 12:55–13:10 5,47 km → 13:15–13:55 5,45 km (45 dk bekleme) → 14:00 5,34 → 14:05 4,10 → 14:10 1,65 km. Yaklaşmanın çoğu son 10 dakikada.
  - BULUŞMA: T0206, 13:30–13:55 arasında T0122'nin 33–41 m yakınında duruyor (25 dk, ikisi de hareketsiz, üsse 5,45 km). 14:00'te ikisi de ayrılıp üsse yaklaşıyor; T0206 1,79 km'ye kadar geliyor (14:55), sonra 15:05'te 2,63 km. Organizatörün yerleştirdiği senaryo olması muhtemel.
  - Bir track'in önceki satırları başka bir görüntünün alanından geçebilir (7 durum; örn. T0122 ve T0206, img_003880'in alanında 13:15–13:55). Bu görüntüde görünmek değildir (kare 14:35'te çekilmiş), ama "bu araç daha önce burada bekledi" bağlamı verir.
- `field_reports.json`: {"time", "source": "official"|"third_party", "text"}. Serbest metin, ASCII Türkçe. Koordinat ("39.9374N 32.8483E") veya bölge adı içerebilir.
  - RAPORLARIN TAMAMI DOĞRU DEĞİL: kasıtlı/kazara hatalı veya ilgisiz olabilir. Önce kendi tespit + hareket verisine dayan, raporları bunlarla karşılaştır.
  - 137 rapor: 72 konumlu, 65 konumsuz.
  - KONUMLU 72 raporun hepsi bir görüntünün merkezine <150 m ve hepsinin saati o görüntünün çekim saatinden ÖNCE. Görüntü başına ~1–4 rapor.
  - Rapor koordinatı, görüntüdeki bir aracın SON konumuna (track'in son satırı) genelde 0–10 m. Yani her konumlu rapor görüntüdeki belirli bir araca işaret ediyor. Raporu araca bağlamak için: rapor koordinatına en yakın track SON NOKTASI (aynı görüntüde).
  - Zaman tuzağı: Hareketli araçlar için rapor saatinde araç rapor konumunda DEĞİL (km'lerce uzakta). Örn. 12:35 raporu T0122'nin 14:10 konumunu anlatıyor; 12:35'te T0122 5,95 km kuzeydeydi. Organizatör örneği bunu "konum ✓" saydı → birincil kontrol görüntü anındaki konum; rapor saatindeki konum ikincil "zaman tutarsızlığı" notu.
  - Track türleri: 30 park halinde (yol <0,5 km, %96 durağan), 196 hareketli (yol 3,6–29 km, medyan 10 km, çok duraklamalı).
  - İddia türlerine göre gözlem (işaret edilen aracın gerçek davranışı):
    - DOST iddiaları (19 rapor: "planlı ikmal aracı, kimlik teyidi", "bize bağlı unsur, gelişi bildirildi", "dost devriye"): HEPSİ hareketli araçlara işaret ediyor, çoğu son 30 dk'da üsse 1,5–6 km yaklaşmış. Bazıları "üsse doğru ilerleyen" diyor ama araç uzaklaşıyor (T0075, T0049, T0124). Kanıtla doğrulanamaz → aldatma adayı, riski düşürmez.
    - DURAĞAN iddiaları ("uzun süredir hareketsiz", "bir saatten uzun ayrılmadı", "park halinde", "beklemede"): çoğu gerçekten park araç (doğru). Ama 3'ü hareketli araca işaret ediyor (#67 T0188, #38 T0041, #42 T0138) → yanlış, hareketi gizleyen iddia.
    - "Hareketleri olağan": park araçlar için doğru (T0153, T0157); hareketli/yaklaşan araçlar için yanlış (T0095, T0122, T0222).
    - "Transit geçiyor" (#8 T0147): araç son 30 dk'da üsse 3 km yaklaşmış → yanıltıcı.
    - "Bölgeden uzaklaşıyor" (#21 T0078, #105 T0018): araç aslında yaklaşıyor → yanlış.
    - "N kamyon" sayı/tip iddiaları: tespit sınıfı ve görüntüdeki araç sayısıyla kontrol edilmeli (track'lerde tip yok).
  - TELSİZ KOPUKLUĞU (BAGLAM_DEGISTIRICI): "X bölgesindeki devriyeyle telsiz bağlantısı 40 dakikadır kurulamıyor" → kör nokta aralığı [yazılma-40dk, yazılma]. Aynı bölge için birden fazla rapor varsa aralıkları birleştir.
    - Kuzey Yolu: 12:20 official + 12:40 third_party → 11:40–12:40 (iki bağımsız kaynak, doğrulanmış). Bu aralıkta official R58 (11:50) T0137 için "planlı ikmal aracı, kimlik teyidi yapılmıştır" diyor: devriyeye ulaşılamazken teyit iddiası → güvenilmez. Üstelik T0137 11:50'de 6,43 km'de duruyordu (ilerlemiyordu), 12:30'dan sonra 7,87 → 3,65 km hızla yaklaştı.
    - Kuzeydoğu Kavşağı: 13:40 official → 13:00–13:40. T0122–T0206 buluşması (13:30–13:55) bu kör noktada, en yakın zone Kuzeydoğu Kavşağı (merkeze 2,3 km). R42 (13:40, "yüklü kamyon park halinde") bu aralıkta ve T0138 aslında hareketli → yanlış. R115 (14:00 official, "sabah devriyesi olağandışı bildirmedi") kopukluğun hemen ardından → bayat/güvenilmez.
    - Batı Yerleşimi: 10:30 official → 09:50–10:30. R135 (09:50, "trafik akışı normal") aralık içinde → güvenilmez.
    - Güneydoğu Yerleşimi: 12:40 third_party → 12:00–12:40. R108 (12:35, "trafik akışı normal") aralık içinde → güvenilmez.
    - Kuzeydoğu Kavşağı 08:35 → 07:55–08:35, track verisi 08:10'da başlıyor; etkisi yok.
    - Kural: kör nokta aralığındaki (veya hemen sonrasındaki) aynı bölge "olağan / trafik normal / devriye bildirmedi / kimlik teyidi" raporları → güvenilirlik düşer; bu bölgede bu aralıkta olan araç davranışlarına küçük risk eklemesi.
    - Dikkat: zone ataması "en yakın zone merkezi" ile; bazı noktalar merkeze 2+ km. Brief'te zone adını kesin konum gibi sunma.
  - KONUMSUZ 65 rapor çoğunlukla gürültü: hava (10), sabah devriyesi olağan (8), dün gece doğrulanmamış ihbar (8, pencere dışı), lojistik konvoyu (8), trafik normal (7), ihbar incelendi doğrulanamadı (7), telsiz bağlantısı yok (6), tatbikat/dost unsurlar (4). Bölge bazlı "ağır araç yok, yalnızca binek" (6) iddiaları o bölgedeki görüntülerin tespit sınıflarıyla kontrol edilebilir.

## Eşleştirme
1. Görüntünün capture_time'ında tracks.csv satırlarını al (bunlar izlerin son noktası).
2. Tespit merkezlerini koordinata çevir.
3. Hungarian atama, eşik 10–15 m (haversine).
4. Eşleşmeyen tespit → "kayıt dışı araç" (risk sinyali). Karede olup eşleşmeyen track → "iz var, tespit yok" (kaçırılmış tespit veya şüpheli kayıt).
- Bonus deney: 206 in-frame track = tespit recall'u için bedava ground truth. Confidence eşiğini buna göre seç.

## Mimari ilkesi
Algoritmalar kanıt üretir, LLM muhakeme eder ve açıklar. LLM sayı hesaplamaz/uydurmaz.

| Katman | Sorumlu |
|---|---|
| Tespit + sınıf | YOLO ensemble |
| Piksel→koordinat, track eşleştirme | Kod |
| Hız, bekleme, yaklaşma, CPA, loop | Kod |
| Risk arketipleri + taban skor | Kod (şeffaf kurallar) |
| Serbest metin rapor ayrıştırma | LLM → yapılandırılmış JSON |
| Rapor iddialarını araçlarla doğrulama | LLM + tool calling |
| Nihai karar | LLM, taban seviyeyi en fazla ±1 kademe değiştirebilir, kanıt ID'si göstererek |
| Brief + operatör soru-cevap | LLM |

### Araçlar (tools)
`get_image_meta(image_id)`, `detect(image_id)`, `georef(detections)`, `match_tracks(image_id)`, `motion_features(track_id)`, `risk_rules(track_id)`, `tracks_near(lat, lon, time, radius_m)`, `find_reports(lat, lon, t_start, t_end)`, `verify_claim(report, evidence)`, `vehicle_color(detection_id)`.

## Risk göstergeleri
- Kinematik: üsse radyal yaklaşma hızı, CPA (en yakın geçiş), ETA, son 10 dk hız, ani hızlanma.
- Yörünge: doğrusallık indeksi (net yer değiştirme / yol), loop, üs etrafında çevreleme (mesafe sabit + açı değişiyor), U dönüşü, KADEMELİ YAKLAŞMA (duraklamalar sırayla üsse daha yakın).
- Duraklama: konum, süre, üsse mesafe.
- Popülasyon: zone bazlı hız sapması (medyan + MAD, robust z), baskın akışa ters hareket, yol dışı hareket (tüm izlerin yoğunluk haritasından).
- Çoklu araç: konvoy, buluşma (aynı yer/zaman durma), farklı yönlerden yakınsama.
- Veri bütünlüğü: kayıt boşluğu, fiziksel olarak imkansız sıçrama, izi olmayan tespit, tespiti olmayan iz.
- Kapasite: truck/bus ağırlığı.
- Rapor etkileşimi: tehdit davranışlı araç için "dost unsur / kimlik teyit edildi" → riski YÜKSELTİR (aldatma şüphesi). "Transit" deniyor ama CPA üssü gösteriyor → yanıltıcı rapor.

Arketipler: TRANSİT, YAKLAŞMA, KADEMELİ YAKLAŞMA, KEŞİF/ÇEVRELEME, ÜS YAKINI BEKLEME, KONVOY, BULUŞMA, YOL DIŞI, KAYIT DIŞI.
Seviyeler: DÜŞÜK / ORTA / YÜKSEK / KRİTİK. Eşikleri mümkün olduğunca popülasyona göre ayarla.

## Rapor doğrulama (iddia bazında)
Her rapordan çıkar: konum, zaman referansı ("dün gece" → pencere dışı), tip, sayı, renk, davranış iddiası, kimlik/niyet iddiası, kesinlik ("doğrulanmamış").
Her iddiayı ayrı kontrol et: konum ✓/✗, tip ✓/✗, davranış ✓/✗ (rapor saatinde track'in hızı/yönü). Kaynak (official/third_party) sadece ön olasılık.
Örnek: 12:35 official "39.9253N 32.8718E çevresinde 1 ağır araç, hareketleri olağan" → konum ✓, tip ✓, davranış ✗ (duraklamalı yaklaşma olağan değil).

## Brief formatı
Bulgu (araç, tip, konum, üsse mesafe, hareket özeti) → Rapor tutarlılığı (hangi rapor, hangi iddia ✓/✗) → Karar (seviye) + gerekçe (kanıt ID'leri). Brief'teki her sayı araç çıktılarından gelmeli.

## Mühendislik kuralları
- 40 görüntünün tespitleri önceden çalıştırılıp JSON'a cache'lenir; demoda 1–2 görüntü canlı.
- LLM yanıtları prompt hash'iyle cache'lenir; API çökerse demo cache'ten çalışır.
- temperature 0; aynı girdi → aynı karar.
- Demo: Streamlit (görüntü + kutular, harita + iz, rapor doğrulama tablosu, canlı agent adımları, brief) + toplu işlem için CLI.

## Denenecekler (sunumda sayı olarak)
1. Confidence eşiği vs track eşleşme oranı (recall).
2. Rapor ayrıştırma: Flash vs GLM-5.x (~15 elle etiketli rapor).
3. Ablasyon: doğrulama araçlarıyla / araçsız → yanıltıcı rapora kaç kez kanıldı.
4. Kural skoru vs LLM kararı: farklılıklar gerekçeli mi.
5. Tutarlılık: aynı görüntü 3 kez → aynı seviye mi.