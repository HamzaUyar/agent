# Risk kararı hibrittir, raporlara asimetrik güvenilir

Risk seviyesini kod kurallarla hesaplar. LLM bu seviyeyi gerekçe yazarak en fazla bir kademe değiştirebilir. Raporlar riski serbestçe yükseltebilir. Düşürebilmeleri için ise kendi bulgularımızla doğrulanmaları gerekir: rapor hangi özellikleri belirtiyorsa (konum, zaman, tip, renk) hepsinin tutması şart. Dostluk iddialarında yalnızca resmi kaynak riski düşürebilir.

Sebep: brief açıkça bazı raporların kasıtlı olarak yanlış olduğunu söylüyor. Riski yükselten sahte bir raporun bedeli en fazla bir yanlış alarm; riski düşüren sahte bir raporun bedeli gözden kaçan bir tehdit. Kuralların tekrarlanabilir ve denetlenebilir olması mentör değerlendirmesi için de önemli.

## Considered Options

- **Kararı tamamen LLM versin:** Esnek, ama aynı girdi farklı sonuç verebilir ve sahte bir "dost unsur" raporuna ikna olabilir.
- **Kararı tamamen kod versin:** Tekrarlanabilir, ama kuralların öngörmediği bağlamı (ör. birbirini doğrulayan iki rapor) kaçırır.

## Not: iddia çekim anındaki temasa bağlanır, saat ayrı bir doğrulama özelliğidir (27 Eylül)

Koordinatlı bir iddia, **çekim anında** konumu iddia noktasına en yakın (≤ `bind_now_m`, 60 m) temasa bağlanır; kaçırılmış temaslar da aday olabilir. Organizatörün gerçek verisinde rapor koordinatları aracın çekim anındaki konumundan üretilmiş: 72 koordinatlı raporun 72'si çekim anında bir temasa ≤ 54 m, rapor saati ise 5–120 dk önce. Eskiden iddia rapor saatinde o noktada olan araca bağlanıyordu; bu, park halindeki ilgisiz araçlara bağlanma ve "o saatte orada değildi" diye yanlış çelişkiler üretiyordu.

Saat, tip ve renk gibi bir özelliktir (`time_check`: ok, mismatch, unknown): bağlanan temasın rapor saatindeki track konumu iddia noktasına ≤ `match_m` ise tutar. Asimetrik güven buna da uygulanır:
- **Dostluk iddiası** riski ancak konum, saat ve belirttiği her özellik tutarsa düşürür; saat tutmuyor ya da bilinmiyorsa "doğrulanamaz".
- **Gözlem** saati tutmasa da "tutarlı" kalır, risk yükselmez; gerekçede not düşülür. Saat uyuşmazlığı tek başına yanıltma kanıtı sayılmaz.
- **Tehdit uyarısı** riski yine yükseltir.
- LLM, saati tutmayan bir raporu seviye düşürmek için kanıt gösteremez.
- Kayıt dışı temasa bağlanan iddia listelenir ama etkisi seviyeye uygulanmaz (track'i yok, ADR-0003).

## Not: hareket ve sayı iddiaları (27 Eylül)

- **Hareket** (duruyor, yaklaşıyor, uzaklaşıyor, transit, hareket halinde) temasın **çekim anındaki** hareketiyle karşılaştırılır: 30 dakikalık eğilim ve süren duraklama. Rapor saatindeki hareketle karşılaştırılmaz, çünkü gerçek verideki bildirimlerde araç rapor saatinde başka yerdeydi. Süre ifadesi ("bir saatten uzun", "N dakikadır", "uzun süredir") `time_reference`'tan okunur; duraklama track'in ilk noktasından beri sürüyorsa gerçek süre bilinmez ve kontrol "doğrulanamadı" olur. Hareket uyuşmazlığı track verisine dayandığı için tip gibi kesin bir çelişkidir ve riski yükseltir. Dostluk iddiasının riski düşürmesi için hareket de tutmalıdır.
- **Sayı** (2 ve üstü) noktanın 30 m içindeki bütün temaslarla tipten bağımsız karşılaştırılır; görülen, iddianın yarısından azsa uyuşmaz. Tespit modeline dayandığı için çelişki "olası" kesinliktedir ve **tek başına riski yükseltmez** (model araç kaçırabilir); başka bir özellik de uyuşmuyorsa o özellik yükseltir.
- "Olağan trafik N araç, yoğunluk var" türü yoğunluk iddiaları henüz ayrı bir iddia olarak ayrıştırılmıyor (TODO).
