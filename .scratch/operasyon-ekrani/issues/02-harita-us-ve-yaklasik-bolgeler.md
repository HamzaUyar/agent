# 02: Harita, Üs ve yaklaşık bölge alanları

**What to build:** Operatör sayfayı açtığında gerçek bir harita görür: varsayılan uydu zemini, sokak haritasına geçiş düğmesi ve köşede zemin atfı. Haritada Üs belirgin bir ikonla ve 1 km / 3 km halkalarıyla, 8 Bölge merkezleri adlarıyla ve her Bölge'nin merkez çevresinde yaklaşık alanıyla görünür; lejant ve Bölge tooltip'i "yaklaşık alan" der. Harita açılışta Üs'ü ve bütün Bölge'leri kapsayacak şekilde ortalanır. İnternet yoksa düz koyu zemine düşer, katmanlar çalışmaya devam eder.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Harita sağlayıcıdan bağımsız bir arayüzün arkasında (görünüme sığdır/yaklaş, zemin seç, adlandırılmış GeoJSON katmanları, vurgula, tıklanan özellik); MapLibre uygulaması yalnızca tarayıcıda yükleniyor
- [ ] Testler için çizilen katmanları ve görünüm çağrılarını kaydeden sahte harita uygulaması
- [ ] Zemin: uydu (Esri World Imagery) ve sokak (OpenFreeMap), anahtarsız; atıf görünür; yüklenemezse düz koyu zemin
- [ ] `GET /zones` ile Üs + 1/3 km halkaları, 8 Bölge merkezi ve adı çiziliyor
- [ ] Yaklaşık bölge alanı: yarıçap = en yakın komşu Bölge merkezine uzaklığın yarısı; lejantta ve tooltip'te "yaklaşık alan"; kesin sınır gibi görünmüyor
- [ ] Backend `[lat, lon]` → harita `[lon, lat]` dönüşümü tek yardımcıda; haversine ve yaklaşık yarıçap küçük testlerle
- [ ] Açılışta görünüm Üs ve 8 Bölge merkezini kapsıyor; çekmece açılınca harita daralıyor
- [ ] Sayfa testi (MSW + sahte harita): açılışta Üs, 8 Bölge, halkalar ve "yaklaşık alan" lejantı; henüz analiz yok
- [ ] Playwright: gerçek MapLibre ile sayfa açılıyor; zemin isteği engellenince düz zemine düşülüyor
