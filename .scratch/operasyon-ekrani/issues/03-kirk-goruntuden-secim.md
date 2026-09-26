# 03: 40 Görüntü'den seçim

**What to build:** Operatör Görüntü çekmecesinde veri setindeki 40 Görüntü'yü küçük önizlemelerle bir ızgarada görür; her kartta görüntü kimliği, Bölge, çekim anı ve varsa son seviye (renk + şekil + kelime) vardır. Izgara Bölge'ye ve seviyeye ("Değerlendirilmedi" dahil) göre filtrelenir, çekim anına göre sıralanır. Alt zaman akışında da 40 kare çekim anına göre seviye şekliyle dizilidir; oradan tıklamak ya da ←/→ ile gezinmek aynı seçimi yapar. Seçilen karenin önizlemesi büyür, haritada ayak izi çizilir, harita o bölgeye yaklaşır ve üst çubuk kareyi, Bölge'yi ve çekim anını gösterir. Dosya yükleme yoktur. Çekmecede "Risk analizini başlat" düğmesi vardır (daha önce değerlendirilmiş karede "Sonucu aç (önbellek)").

**Blocked by:** 02

**Status:** ready-for-agent

- [x] `GET /images` ile ızgara; önizlemeler `GET /images/{id}/file`; kartta kimlik, Bölge, çekim anı, son seviye
- [x] Bölge ve seviye filtresi ("Değerlendirilmedi" seçeneği), çekim anına göre sıralama
- [x] Zaman akışı üst şeridi: 40 kare saat ekseninde, seviye şekliyle; bütün kareler her zaman seçilebilir; ←/→ önceki/sonraki kare
- [x] Seçimde büyük önizleme; `GET /images/{id}` köşeleriyle ayak izi haritada; harita kareye yaklaşıyor; üst çubukta kare · Bölge · çekim anı
- [x] "Risk analizini başlat" düğmesi; `last_risk_level` doluysa "Sonucu aç (önbellek)"; seçim analizi kendiliğinden başlatmıyor
- [x] Dosya yükleme yok; yalnızca veri setindeki kareler
- [x] Sayfa testleri: ızgara, filtre, sıralama; zaman akışından ve ızgaradan seçimin aynı sonucu vermesi; ayak izi ve yaklaşma (sahte harita kaydı)

## Comments

- 26 Eylül: tamamlandı (04 ile aynı commit'te; analiz düğmesi akışa bağlı). Zaman akışından seçim, sol kenar boşsa Görüntü çekmecesini açıyor. Dosyası yüklenemeyen karede "önizleme yok". Harita, seçili karenin ~1,2 km çevresine yaklaşıyor.
- Not: backend `.env`'deki `DATA_DIR=../../stage2` artık olmayan `Desktop/stage2`'yi gösteriyor; veri `roketsan/stage2`'de. Önizlemeler için `DATA_DIR=../stage2` olmalı.
