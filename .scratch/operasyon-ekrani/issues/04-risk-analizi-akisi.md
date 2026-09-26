# 04: Risk analizi akışı

**What to build:** Operatör "Risk analizini başlat"a bastığında değerlendirme başlar; her adım (numara, ad, özet) geldiği anda üst çubukta ve Risk & Temaslar çekmecesinde görünür ve ekran okuyucuya duyurulur. 15 saniyeyi aşan beklemede "Model yanıtı bekleniyor (en fazla 45 sn)" yazar; ekran hiç boş kalmaz. Önbellekten gelen sonuçta "önbellek" rozeti ve "Yeniden değerlendir" düğmesi, otomatik özette "otomatik özet" rozeti ve sebebi, LLM Brief'inde model adı görünür. Hata ya da 404'te kısa Türkçe mesaj ve "Tekrar dene" çıkar. Akış sürerken başka kare seçilirse eski akış iptal edilir. Brief gelince üst çubukta Görüntü seviyesi (renk + şekil + kelime) ve önerilen eylem görünür, Risk & Temaslar çekmecesi göz atma hâlinde özet sayılarla belirir ve Brief sekmesinde metin, önerilen eylem ve kaynaklar yer alır.

**Blocked by:** 03

**Status:** ready-for-agent

- [x] `POST /evaluations {image_id}` SSE akışı; adım listesi sabit değil, gelen `step` olaylarından
- [x] Adımlar üst çubukta (ilerleme + son adım özeti) ve çekmecede; `aria-live="polite"`
- [x] 15 sn sessizlikte bekleme mesajı
- [x] `run.cached` → "önbellek" rozeti + "Yeniden değerlendir" (`recompute: true` gövdesi)
- [x] `brief.is_fallback` → "otomatik özet" rozeti + `fallback_reason`; değilse model adı
- [x] `error` olayı ve 404 (`detail`) aynı hata durumuna düşüyor: Türkçe mesaj + "Tekrar dene"
- [x] Kare değişince akış iptal ediliyor, değerlendirme ve seçim temizleniyor
- [x] Brief: üst çubukta seviye + önerilen eylem; sağ çekmece göz atma hâlinde ("5 temas"); Brief sekmesi: metin, eylem, kaynaklar, rozet
- [x] Sayfa testleri (MSW akışları parça parça ve gecikmeli): adım sırası, bekleme mesajı, önbellek ve yeniden değerlendirme, otomatik özet, hata/404 ve tekrar dene, iptal, Brief sonrası üst çubuk

## Comments

- 26 Eylül: tamamlandı. Brief gelince listedeki son seviye de güncelleniyor (zaman akışı, kart, filtre). Akış içindeki hata ve 404 aynı hata durumuna düşüyor; iptal edilen akışın geç olayları yok sayılıyor.
