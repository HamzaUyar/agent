# Kayıt dışı temas kendi başına risk değildir

Track'i bulunmayan bir tespit (kayıt dışı temas) temel seviye tablosunda düşük sayılır. Yalnızca üsse `unregistered_alert_m`'den (varsayılan 1 km) yakınsa orta olur. Brief'te "hareket kaydı yok, park halinde olabilir" notuyla görünür. Önceki kural bu temasları en az orta, üsse 2 km'den yakınsa yüksek sayıyordu.

Sebep: 2. aşama görev tanımı açıkça "park halindeki araçların hareket kaydı olmayabilir" diyor. Gerçek veride her görüntünün karesinde yalnızca 3–7 track var. Oysa Kaggle görüntülerinde görüntü başına ortanca 21 araç bulunuyor. Eski kuralla park halindeki her araç alarm üretiyordu. Sentetik paketle ölçüldü: %60 track kapsamasında hiçbir görüntü düşük kalmıyordu. Track'in yokluğu bir tehdit sinyali değil, veri setinin bir özelliği.

## Considered Options

- **Eski kural (kayıt dışı ≥ orta, < 2 km yüksek):** Kayıt dışı aracı gözden kaçırmaz, ama gerçek veride alarm yorgunluğu yaratır ve brief'i gürültüye boğar.
- **Kayıt dışı temasları hiç göstermemek:** Brief sadeleşir, ama üssün dibindeki bilinmeyen bir aracı da gizler.
- **Seçilen: düşük, üssün hemen yakınında orta:** Temas brief'te görünmeye devam eder. Risk ancak ek bir sinyal (yakınlık) varsa yükselir.

## Consequences

- LLM karar prompt'u, bir aracı yalnızca track'i yok diye yükseltmemesini söylüyor. LLM yine de gerekçesiyle ±1 kademe değiştirebilir (ADR-0002).
- Raporlar şu an kayıt dışı temaslara bağlanamıyor: bağlama, aracın rapor saatindeki track konumuna dayanıyor. Hakkında bir rapor olan kayıt dışı aracın riskini yükseltebilmek için bağlamanın genişletilmesi gerekiyor (TODO).
