# Risk kararı hibrittir, raporlara asimetrik güvenilir

Risk seviyesini kod kurallarla hesaplar. LLM bu seviyeyi doğrulanmış bir nedenle en fazla bir kademe değiştirebilir; kuralların seviyede zaten saydığı neden (`level_basis`) yükseltme gerekçesi olamaz, aynı olgu iki kez sayılmaz. Tespitle ya da track'le çelişen bir rapor seviyeyi değiştirmez: tespit esas alınır, çelişki gerekçede not edilir. Tutarlı bir tehdit uyarısı riski bir kademe yükseltebilir. Raporların riski düşürebilmesi için ise kendi bulgularımızla doğrulanmaları gerekir: rapor hangi özellikleri belirtiyorsa (konum, zaman, tip, renk) hepsinin tutması şart. Dostluk iddialarında yalnızca resmi kaynak riski düşürebilir.

Sebep: görev tanımı raporların bir kısmının hatalı veya ilgisiz olduğunu (s3) ve çelişkide raporun değil tespitin esas alınacağını (s2) söylüyor. Riski düşüren sahte bir raporun bedeli gözden kaçan bir tehdit olduğu için düşürme sıkı koşullara bağlı; çelişen bir rapor ise aynı temas hakkındaki başka bir raporun riski düşürmesini de engeller. Kuralların tekrarlanabilir ve denetlenebilir olması mentör değerlendirmesi için de önemli.

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

- **Hareket** (duruyor, yaklaşıyor, uzaklaşıyor, transit, hareket halinde) temasın **çekim anındaki** hareketiyle karşılaştırılır: 30 dakikalık eğilim ve süren duraklama. Rapor saatindeki hareketle karşılaştırılmaz, çünkü gerçek verideki bildirimlerde araç rapor saatinde başka yerdeydi. Süre ifadesi ("bir saatten uzun", "N dakikadır", "uzun süredir") `time_reference`'tan okunur; duraklama track'in ilk noktasından beri sürüyorsa gerçek süre bilinmez ve kontrol "doğrulanamadı" olur. Hareket uyuşmazlığı track verisine dayandığı için tip gibi kesin bir çelişkidir. Dostluk iddiasının riski düşürmesi için hareket de tutmalıdır.
- **Sayı** (2 ve üstü) noktanın 30 m içindeki bütün temaslarla tipten bağımsız karşılaştırılır; görülen, iddianın yarısından azsa uyuşmaz. Tespit modeline dayandığı için çelişki "olası" kesinliktedir (model araç kaçırabilir).
- "Olağan trafik N araç, yoğunluk var" türü yoğunluk iddiaları henüz ayrı bir iddia olarak ayrıştırılmıyor (TODO).

## Not: çelişki seviyeyi değiştirmez (27 Eylül)

Önceden tespitle çelişen bir rapor "olası yanıltma" sayılıp temasın seviyesini en az "yüksek"e çekiyordu ve LLM bunu düşüremiyordu. Görev tanımı s2 ("çelişki varsa raporu değil tespitinizi esas alın") ile çeliştiği için kaldırıldı. Gerçek verideki çelişkilerin çoğu, rapordaki "kamyon" ile modelin otomobil/minibüs dediği araç arasındaki tip uyuşmazlığıydı; bu kural büyük olasılıkla hatalı raporlar yüzünden park halindeki araçları "yüksek"e çıkarıyordu. Artık çelişen iddianın etkisi "none"; brief'te "rapor tespitle çelişiyor; tespit esas alındı" diye görünür ve aynı temasa ait bir dostluk iddiasının riski düşürmesini engeller.

## Not: rapor doğrulama yeniden yazıldı; raporlar seviyeyi değiştirmez (27 Eylül)

`pipelines/reports.py` (yalnızca kurallar) kaldırıldı; yerine `app/reports_v2` geldi. Yukarıdaki notların rapor etkisiyle ilgili kısımları (tehdit uyarısı +1, resmi dost raporu riski düşürür, saat kontrolü) artık geçerli değil.

- **Raporlar risk seviyesini değiştirmez.** Doğrulanamayan bilgi riski ne düşürür ne de tek başına yükseltir; rapor yalnızca gerekçe ve bayrak üretir. Tutarlı bir tehdit uyarısını karar LLM'i kanıt göstererek +1 kademe önerebilir (kod doğrular).
- **Kimlik iddiası hiçbir zaman "tutarlı" değildir.** "Dost", "ikmal", "bize bağlı", "devriye", "tatbikat" veriyle doğrulanamaz; en fazla "doğrulanamaz". Gerçek veride 18 dost iddiasının neredeyse hepsi üsse yaklaşan araçlara işaret ediyordu; konvoy ve tatbikat duyuruları günün tek koordineli ağır araç yaklaşmasıyla (Kuzey Yolu, 12:10–12:15) aynı saate denk geliyor.
- **Zaman kayması çelişki değildir** (yönetim kararı). Rapor koordinatı aracın çekim anındaki konumunu gösterir; aracın rapor saatinde başka yerde olması güveni düşürmez. Hareket iddiası ("olağan", "duruyor", "uzaklaşıyor", "transit") çekim anındaki hareketle karşılaştırılır; yazıldığında doğru olup çekim anında yanlış olan rapor "bayat güvence"dir.
- **Karar LLM'in, kurallar ikinci görüş.** Kod her rapor için kanıt dosyası ve bağlam sinyallerini hesaplar (noktadaki araç, tip, sayı, çekim anındaki hareket, bölge hareketliliği, birlikte hareket eden ağır araç grupları); LLM kararı verir; kurallar aynı kanıtla ayrıca karar verir. İkisi çelişki konusunda ayrışırsa rapor operatöre "incelenmeli" diye gösterilir.
- **Tehlikeli güvence** (riski düşüren ama kanıtla çelişen rapor: yaklaşan araca "olağan", hareket eden kamyon varken "ağır araç yok") ayrıca işaretlenir.

Neden: `eval/report_gold.json`'daki 137 gerçek raporla ölçüldü. Eski kurallar 35 yalanın 23'ünü, 15 tehlikeli güvencenin 3'ünü yakalıyordu. Yeni akış 34/35 ve 15/15 yakalıyor. Kurallar tek başına orijinal metinlerde benzer skor alıyor ama ifadesi değiştirilmiş raporlarda (genelleme testi) 23/35'e düşüyor, çünkü ayrıştırıcının etiketine bağımlı; LLM aynı testte 34/35'te kaldı. Ölçüm: `python -m scripts.eval_reports B C --package … --claims … --detections … --out …`.


## Not: LLM, risk motorunun saydığı nedenle seviyeyi yükseltemez (27 Eylül)

Risk motoru (ADR-0004) track'in bütün hareketini değerlendirir. Temasın `level_basis`'i artık yalnızca seviyeyi belirleyen satırın nedeni değil; verideki bütün hareket nedenleri: yaklaşma, üsse yakın uzun duraklama, üs çevresinde dolaşma. Kaçırılmış temasta tipin bilinmemesi (`kacirilmis_temas`) de eklenir, çünkü motor tipi bilinmeyen aracı bilerek ağır saymaz. LLM'in ±1 yükseltmesi yalnızca kuralların kullanmadığı bir kanıtla, örneğin temasla tutarlı bir tehdit uyarısıyla kabul edilir.

Neden: yeni motorla yapılan ilk koşuda LLM 237 temasın 33'ünü bir kademe yükseltti. Bunların çoğu, motorun bilerek yüksek bıraktığı "üssün 1 km yakınında park edip ayrılan" araçlardı; LLM "uzun duraklama" gerekçesiyle onları kritik yaptı. Kalan yükseltmeler de uzakta duran ya da kaçırılmış temaslardı. Sonuç olarak kritik görüntü sayısı 14'ten 25'e çıktı ve motorun kalibrasyonu bozuldu (`pipelines/risk.py: engine_basis`).
