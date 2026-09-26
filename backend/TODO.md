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
- [x] 12 · Değerlendirme seti koşucusu (`run-eval-set`, etiketler `eval/*.toml`)
- [ ] 13 · Gerçek veri yükleme ve açık soruların kapatılması · engel: 01 ✅, 12 ve 2. aşama verisi

Hemen başlanabilecek iş maddesi yok; 13 gerçek 2. aşama verisini bekliyor.

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

- [x] LLM'in boş ya da "..." değerlendirme paragrafı geçersiz sayılıyor, sıradaki modele geçiliyor
- [x] Sentetik 2. aşama paketi (Kaggle eğitim görüntülerinden 40 kare, track'ler, bilerek yanlış raporlar, otomatik etiketler) ve bütün pipeline'ın onunla koşturulması
- [ ] Brief'te temasların gruplanması: görüntü başına ortanca 16 temas, brief ortanca 20 satır (R12). Riskli temaslar ayrıntılı, geri kalanı özet satırında
- [ ] Düşürme kanıtı kuralı (R13): tutarlı gözlem raporu mu, yalnızca dostluk iddiası mı?
- [ ] LLM kararının tekrarlanabilirliği (R14): sıcaklık 0, prompt sıkılaştırma
- [x] Supabase'te artık stage2 (gerçek veri) yüklü; sentetik paket diskte (`backend/synthetic/`)
- [ ] Brief prompt'u: kaçırılmış ve kayıt dışı temas ayrımı, K1/K2 sızıntısı, "muhtemel" gibi çeviri ifadeleri; mesafelerde ondalık virgül

- [ ] LLM yükseltmelerinde kanıtın o temasa ait olduğunu doğrula (canlı örnekte başka temasın raporuyla yükseltti)

- [x] Kayıt dışı temas kuralı (ADR-0003): düşük, üsse < 1 km'de orta; LLM prompt'unda temas türleri Türkçe karşılıklarıyla
- [ ] Raporların kayıt dışı temaslara bağlanabilmesi (şu an bağlama track konumuna dayanıyor; temasın track dışında bir kimliği gerekiyor)
- [x] `field_reports` doğal anahtarı: `seq` sütunu (migration 08; 137/137 rapor yüklü)
- [x] Stage2 verisini Supabase'e yükle (`load_data ../../stage2 --replace`), `parse_reports`, `.env` `DATA_DIR=../../stage2` ve `DETECTOR_MOCK_PATH=../../stage2/detections_evren.json`
- [ ] `models.toml` `glm_org`: model adı `glm-5.3-flash`, base URL görev tanımında; düşünme kapatılamıyor (`reasoning_effort`)
- [ ] Sentetik üretecin varsayılan Kaggle yolu: `train/` artık `Desktop/train`'de

- [x] Ekibin tespit modeli (EVREN, `DETECTOR_MODE=evren`) ve tespitlerin dosyaya aktarılması (`stage2/detections_evren.json`)
- [ ] Model ekibine: img_000860'taki kamyonu (727, 284, 58, 34) görmüyor; 40 görüntüde track'li 16 araç kaçırılıyor
- [ ] 14,1 m'lik eşleşmeyi kontrol et (15 m eşiğine yakın; yanlış eşleşme olabilir)
- [ ] Doğrudan EVREN modunda API açılışında tespit önbelleğini ısıt ya da demoda dosyayı kullan

- [x] **Rapor bağlama (R15):** iddia çekim anındaki temasa bağlanıyor, saat ayrı kontrol (`time_check`)
- [ ] Hareket iddiasını track eğilimiyle, "uzun süredir yerinde" iddiasını duraklama süresiyle, sayı iddiasını tespit sayısıyla karşılaştır (R15)
- [ ] Kalan 18 tip çelişkisinin hepsi "kamyon" ↔ modelin otomobil/minibüs dediği araç: model hatası mı tuzak mı, birkaç kırpmayı gözle kontrol et (VLM ile tip doğrulaması?)
- [ ] Kayıt dışı temasa bağlanan çelişkili raporun etkisini temasa uygula (ADR-0003 TODO)
- [ ] Brief'te gün boyu geçerli doğrulanamaz iddiaları (tatbikat, söylenti) tek satırda özetle

## Açık kararlar
- [ ] Zaman kaydırıcılı risk haritası yapılacak mı (spec'te kapsam dışı, sonraya bırakıldı)?
- [ ] Embedding modeli ve `report_claims.embedding` boyutu
- [x] Görev bazında modeller: rapor ayrıştırma Haiku 4.5; VLM ve sohbet Sonnet 5; karar ve brief Opus 5.5; her görev için yedek GLM
