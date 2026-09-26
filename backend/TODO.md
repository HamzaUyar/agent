# TODO

Asıl plan, `app/.scratch/goruntu-degerlendirme-agent/issues/` altındaki iş maddeleri; spec'i `spec.md`. Bu liste onların özeti ve plana girmeyen işler.

## İş maddeleri
- [x] 01 · Proje temeli ve sahte veri
- [x] 02 · İzci mermi: img_000860 uçtan uca
- [x] 03 · Temas kenar durumları (zayıf tespit, belirsiz eşleşme, kayıt dışı / kaçırılmış temas, ileri kestirim, tip çelişkisi)
- [x] 04 · Tam hareket analizi ve kural tablosu (hız, yön, duraklama, bölgeler; eşikler `risk_rules.toml`'da)
- [x] 05 · Model yönlendirme (`models.toml`, anthropic SDK + GLM yedeği) ve rapor ayrıştırma
- [x] 06 · Rapor değerlendirme (asimetrik güven, ADR-0002; "rapor kendi track'iyle çelişiyor → yüksek" satırı)
- [x] 07 · LLM karar ayarı (±1 kademe, kanıtlı düşürme) ve brief yazarı; zaman sınırı ve otomatik özet
- [x] 08 · VLM görsel doğrulama (renk ve yük iddiaları, zayıf tespit; yalnızca gerektiğinde)
- [x] 09 · Önbellek (LLM brief'i tercihli), yeniden hesaplama, `GET /evaluations/{id}`
- [x] 10 · Sohbet agent'ı (5 salt okuma aracı, `POST /evaluations/{id}/chat`)
- [x] 11 · Gerçek tespit modeli entegrasyonu (Ultralytics YOLO, `DETECTOR_MODE=model`)
- [ ] 12 · Değerlendirme seti koşucusu · engel: 06 ✅, 07 ✅
- [ ] 13 · Gerçek veri yükleme ve açık soruların kapatılması · engel: 01 ✅, 12 ve 2. aşama verisi

Hemen başlanabilecekler: **12**.

## Plan dışı işler
- [x] `app/` için git repo'su başlat, ilk commit'i yap, GitHub'a push et (private)
- [x] EVREN anahtarı, şart kabulü ve rapor ayrıştırma (6 iddia `report_claims`'te)
- [ ] Organizatörlerin GLM anahtarı gelince: `.env`'e `GLM_API_KEY`/`GLM_API_BASE`, `models.toml`'da `glm_org` model adını doğrula
- [x] GLM-5.3 gecikmesi ölçüldü; düşünme kapatıldı (13–20 sn), zaman sınırı ve otomatik özet (ticket 07)
- [ ] `backend/CLAUDE.md`'deki dizin yapısını güncelle (`data_package.py`, `agent/service.py`, `supabase/migrations/`)
- [ ] Boş test dosyalarını (`test_geo.py`, `test_motion.py`, `test_matching.py`) kaldır ya da doldur. Onaylanan test noktalarına göre bunlar ayrı test edilmiyor; istisna interpolasyon gibi karmaşık hesaplar.
- [ ] Ayrıntılı analiz tablolarını (`detections`, `track_matches`, `risk_assessments`) doldur; şu an sonuç yalnızca `brief_json` içinde
- [ ] `docker-compose.yml`: backend, frontend ve isteğe bağlı yerel Supabase
- [x] Tip geçmişi için önceki karelerin tespitini önbelleğe al (`UltralyticsDetector` her görüntüyü bir kez çalıştırıyor)
- [ ] Frontend (Next.js): ayrı spec; API sözleşmesi spec'te tanımlı
- [ ] Demo öncesi: demo görüntülerini `recompute: true` ile değerlendirip önbelleği ısıt (R1, R2, R9)
- [ ] Sunum ve demo provası

- [ ] Gerçek görüntüler gelince VLM'i birkaç kırpmada gözle kontrol et (renk paleti, "araç değil" oranı; R11)
- [ ] Mevcut raporlarda yük geçiyorsa `parse_reports --force` ile `cargo` alanını doldur

- [ ] Model ağırlıkları gelince: `pip install -e '.[model]'`, `.env`'de `DETECTOR_MODE=model` + `DETECTOR_WEIGHTS_PATH` (+ eğitim boyutu `DETECTOR_IMGSZ`), img_000860'ta kutunun (727, 284, 58, 34) civarında truck çıktığını doğrula; sınıf adları `CLASS_ALIASES`'ta yoksa ekle

## Açık kararlar
- [ ] Zaman kaydırıcılı risk haritası yapılacak mı (spec'te kapsam dışı, sonraya bırakıldı)?
- [ ] Embedding modeli ve `report_claims.embedding` boyutu
- [x] Görev bazında modeller: rapor ayrıştırma Haiku 4.5; VLM ve sohbet Sonnet 5; karar ve brief Opus 5.5; her görev için yedek GLM
