# 05: Temas'ların ve rotaların haritaya eklenmesi

**What to build:** Brief geldiğinde haritada her Temas çekim anındaki konumunda görünür; tür (eşleşmiş / kayıt dışı / kaçırılmış) işaretin çizgisi ve dolgusuyla, seviye renk + şekil (● ■ ▲ ◆) + etiketle ayrılır. Track'i olan Temas'ların rotası saatleriyle, duraklamaları saat, süre ve yerle çizilir; son yön harita üzerinde okla, eğilim ("yaklaşıyor / uzaklaşıyor / duruyor / geçiyor") metinle verilir; yönü bilinmeyen Temas'ta "yön belirsiz" yazar. Çekim anından sonraki hiçbir konum ya da tahmini rota çizilmez. Görüntü çekmecesinde kare üzerinde tespit kutuları sınıf, güven ve track kimliğiyle görünür; zayıf tespitler kesikli kutu, kaçırılmış Temas'lar kutusuz konum işaretidir.

**Blocked by:** 04

**Status:** ready-for-agent

- [x] Temas katmanı: `contacts[].location`; tür çizgi/dolguyla, seviye renk + şekil + etiketle
- [x] Rota katmanı: `motion.route` saatleriyle (saat `null` ise saatsiz); duraklamalar `motion.stops`
- [x] Son yön oku (`heading_deg`) ve eğilim metni (`trend`); `heading_deg` yoksa "yön belirsiz"
- [x] Çekim anından sonrası çizilmiyor; tahmini rota yok
- [x] Görüntü çekmecesi: `bbox` kutuları (sınıf, güven, track); `is_weak` kesikli; `missed` kutusuz işaret (konum → piksel köşe koordinatlarıyla)
- [x] Hareket azaltma tercihinde rota animasyonu kapalı
- [x] Sayfa testleri: Brief sonrası temas, rota, duraklama, yön katmanları (sahte harita kaydı); eski önbellek kaydında saatsiz rota; kutular ve kaçırılmış temas işareti

## Comments

- 26 Eylül: tamamlandı. Aynı karedeki Temas'lar birkaç metre arayla durduğu için etiketler üst üste biniyordu: nokta gerçek konumda kalıyor, etiketler seviyeye göre sırayla yerleştirilip çakışırsa aşağı kaydırılıyor ve kırık çizgiyle noktaya bağlanıyor. Rota saatleri 30 dakikada bir ve son noktada etiketli. Lejant açılır/kapanır.
