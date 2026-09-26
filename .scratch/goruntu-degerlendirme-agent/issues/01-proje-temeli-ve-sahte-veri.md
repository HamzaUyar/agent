# 01: Proje temeli ve sahte veri

**What to build:** Geliştirici tek komutla, referans örnekten (img_000860, T0122, T0032, 12:35 raporu, üçüncü taraf dost unsur raporu, bölgeler) üretilmiş bir sahte veri paketini Supabase'e yükleyebilir ve yükleme sonunda bir tutarlılık raporu görür. Spec'in gerektirdiği şema eklemeleri uygulanır, mevcut migration'lar repoya da yazılır. Testler için bellekte çalışan bir veri deposu hazırdır.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Bağımlılıklar ve ayarlar (.env okuma) tanımlı; araçlar (pytest, ruff, mypy) çalışıyor
- [ ] Uygulanmış 5 migration ve yeni şema ekleri repoda SQL dosyası olarak var; şema ekleri Supabase'e uygulanmış
- [ ] Sahte veri paketi, 2. aşama veri formatıyla birebir aynı dosyaları üretiyor
- [ ] Yükleyici veri paketini okuyup Supabase'e yazıyor; tekrar çalıştırılınca çoğaltma yapmıyor
- [ ] Yükleme görüntünün kapladığı alanı, merkezini ve bölgesini hesaplıyor
- [ ] Tutarlılık raporu: meta'sı ya da dosyası eksik görüntüler, 5 dakikalık adıma denk gelmeyen çekim saatleri, track/nokta/rapor sayıları, zaman aralıkları
- [ ] Bellek içi veri deposu, çekim anı sınırını (ADR-0001) uygulayan okuma arayüzünü sağlıyor
