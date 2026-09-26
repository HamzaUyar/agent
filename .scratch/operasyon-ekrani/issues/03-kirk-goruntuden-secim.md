# 03: 40 Görüntü'den seçim

**What to build:** Operatör Görüntü çekmecesinde veri setindeki 40 Görüntü'yü küçük önizlemelerle bir ızgarada görür; her kartta görüntü kimliği, Bölge, çekim anı ve varsa son seviye (renk + şekil + kelime) vardır. Izgara Bölge'ye ve seviyeye ("Değerlendirilmedi" dahil) göre filtrelenir, çekim anına göre sıralanır. Alt zaman akışında da 40 kare çekim anına göre seviye şekliyle dizilidir; oradan tıklamak ya da ←/→ ile gezinmek aynı seçimi yapar. Seçilen karenin önizlemesi büyür, haritada ayak izi çizilir, harita o bölgeye yaklaşır ve üst çubuk kareyi, Bölge'yi ve çekim anını gösterir. Dosya yükleme yoktur. Çekmecede "Risk analizini başlat" düğmesi vardır (daha önce değerlendirilmiş karede "Sonucu aç (önbellek)").

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] `GET /images` ile ızgara; önizlemeler `GET /images/{id}/file`; kartta kimlik, Bölge, çekim anı, son seviye
- [ ] Bölge ve seviye filtresi ("Değerlendirilmedi" seçeneği), çekim anına göre sıralama
- [ ] Zaman akışı üst şeridi: 40 kare saat ekseninde, seviye şekliyle; bütün kareler her zaman seçilebilir; ←/→ önceki/sonraki kare
- [ ] Seçimde büyük önizleme; `GET /images/{id}` köşeleriyle ayak izi haritada; harita kareye yaklaşıyor; üst çubukta kare · Bölge · çekim anı
- [ ] "Risk analizini başlat" düğmesi; `last_risk_level` doluysa "Sonucu aç (önbellek)"; seçim analizi kendiliğinden başlatmıyor
- [ ] Dosya yükleme yok; yalnızca veri setindeki kareler
- [ ] Sayfa testleri: ızgara, filtre, sıralama; zaman akışından ve ızgaradan seçimin aynı sonucu vermesi; ayak izi ve yaklaşma (sahte harita kaydı)
