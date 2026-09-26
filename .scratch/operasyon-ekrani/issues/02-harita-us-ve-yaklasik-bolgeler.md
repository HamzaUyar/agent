# 02: Harita, Üs ve yaklaşık bölge alanları

**What to build:** Operatör sayfayı açtığında gerçek bir harita görür: varsayılan uydu zemini, sokak haritasına geçiş düğmesi ve köşede zemin atfı. Haritada Üs belirgin bir ikonla ve 1 km / 3 km halkalarıyla, 8 Bölge merkezleri adlarıyla ve her Bölge'nin merkez çevresinde yaklaşık alanıyla görünür; lejant ve Bölge tooltip'i "yaklaşık alan" der. Harita açılışta Üs'ü ve bütün Bölge'leri kapsayacak şekilde ortalanır. İnternet yoksa düz koyu zemine düşer, katmanlar çalışmaya devam eder.

**Blocked by:** 01

**Status:** ready-for-agent

- [x] Harita sağlayıcıdan bağımsız bir arayüzün arkasında (görünüme sığdır/yaklaş, zemin seç, adlandırılmış GeoJSON katmanları, vurgula, tıklanan özellik); MapLibre uygulaması yalnızca tarayıcıda yükleniyor
- [x] Testler için çizilen katmanları ve görünüm çağrılarını kaydeden sahte harita uygulaması
- [x] Zemin: uydu (Esri World Imagery) ve sokak (OpenFreeMap), anahtarsız; atıf görünür; yüklenemezse düz koyu zemin
- [x] `GET /zones` ile Üs + 1/3 km halkaları, 8 Bölge merkezi ve adı çiziliyor
- [x] Yaklaşık bölge alanı: yarıçap = en yakın komşu Bölge merkezine uzaklığın yarısı; lejantta ve tooltip'te "yaklaşık alan"; kesin sınır gibi görünmüyor
- [x] Backend `[lat, lon]` → harita `[lon, lat]` dönüşümü tek yardımcıda; haversine ve yaklaşık yarıçap küçük testlerle
- [x] Açılışta görünüm Üs ve 8 Bölge merkezini kapsıyor; çekmece açılınca harita daralıyor
- [x] Sayfa testi (MSW + sahte harita): açılışta Üs, 8 Bölge, halkalar ve "yaklaşık alan" lejantı; henüz analiz yok
- [x] Playwright: gerçek MapLibre ile sayfa açılıyor; zemin isteği engellenince düz zemine düşülüyor

## Comments

- 26 Eylül: tamamlandı. MapLibre 6'nın web worker'ı Turbopack paketine girmediği için `public/maplibre/`'dan sunuluyor (`scripts/copy-maplibre-worker.mjs`, `postinstall`/`predev`/`prebuild`). Çizgilerin altında koyu kılıf var; ince açık çizgiler uydu ve sokak zemininde seçilmiyordu. Açılış görünümü Bölge'lerin yaklaşık alanlarını da kapsıyor.
