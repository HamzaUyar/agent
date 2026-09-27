# İlerleme

## 25 Eylül 2026 (Cuma)

### Analiz
- Hackathon dokümanları incelendi (`information/`): katılımcı bilgilendirme dokümanı ve case brief sunumu.
- 2. aşamanın gereksinimleri, veri formatları ve değerlendirme kriterleri çıkarıldı.
- Veriler arasındaki bağlantılar belirlendi:
  - görüntü ↔ meta (`image_id`)
  - tespit ↔ track (zaman + en yakın konum)
  - rapor ↔ tespit/track (koordinat, bölge, zaman, tip)

### Kararlar
- Tech stack: **Python (FastAPI) + Next.js + Supabase** (PostGIS + pgvector).
- Pipeline üç koldan oluşuyor:
  - **Kol A:** görüntü → tespit → koordinat
  - **Kol B:** `track_risk(track_id, at_time)`, görüntüden bağımsız
  - **Kol C:** raporlar, önceden parse edilir
- Kol A ve Kol B, **zaman + en yakın konum** eşlemesiyle birleştiriliyor.
- Track riski istek anında, görüntünün çekim saatine göre hesaplanıyor. Zaman kaydırıcılı harita istenirse önceden hesaplama eklenecek.
- Hesaplar deterministik kodla yapılıyor; LLM akıl yürütme ve brief için kullanılıyor. Model seçimi görev bazlı, LiteLLM üzerinden.
- Veritabanına sadece backend yazıyor; RLS açık, policy yok.

### Yapılanlar
- Supabase'te **Roketsan Project** (`akduinmhomalciorwckz`) içinde şema kuruldu. 5 migration uygulandı:
  - `01_extensions_and_enums`: postgis, vector ve 11 enum tipi
  - `02_source_tables`: bases, zones, images, tracks, track_points, field_reports
  - `03_enriched_tables`: report_claims, track_segments
  - `04_analysis_tables`: analysis_runs, detections, track_matches, motion_analyses, report_evaluations, risk_assessments, agent_steps
  - `05_enable_rls`
- Supabase güvenlik ve performans kontrolleri çalıştırıldı. Sadece beklenen bilgi uyarıları var: "RLS açık ama policy yok" ve "kullanılmayan indeks" (tablolar boş).
- `app/backend/` iskeleti oluşturuldu. Dosyalar boş, sadece açıklama satırı içeriyor.
- `CLAUDE.md`, `ILERLEME.md` ve `TODO.md` oluşturuldu.

### Açık sorular
- 12:35 tarihli rapor ile T0122'nin 12:35'teki konumu uyuşuyor mu? Organizatör demosu bu raporu "uyumlu" sayıyor. Gerçek veride kontrol edilecek.
- `capture_time` değerleri 5 dakikalık adımlara denk geliyor mu?
- Track ve rapor sayıları, yani gerçek veri boyutu.
- Embedding modeli ve boyutu. `report_claims.embedding` şu an boyutsuz.

## 26 Eylül 2026 (Cumartesi)

### Tasarım (skill'lerle)
- Proje skill'leri `.claude/skills/` altına kuruldu: python-pro, fastapi-expert, nextjs-developer ve mattpocock/skills'in 24 skill'i.
- `/grill-with-docs` ile agent mimarisi 26 soruda netleştirildi. Çıktılar:
  - `app/CONTEXT.md`: alan dili (Temas, Kayıt dışı / Kaçırılmış temas, Zayıf tespit, Belirsiz eşleşme, Çekim anı, İddia, Dostluk iddiası, Rapor kararı, Kesinlik, Brief, Önerilen eylem)
  - `app/docs/adr/0001`: değerlendirme çekim anından sonrasını görmez
  - `app/docs/adr/0002`: hibrit risk kararı ve asimetrik rapor güveni
- `/setup-matt-pocock-skills`: yerel Markdown iş takibi (`app/.scratch/`), varsayılan triage etiketleri, tek bağlam. `app/CLAUDE.md` oluşturuldu.
- `/to-spec`: `app/.scratch/goruntu-degerlendirme-agent/spec.md` (78 kullanıcı hikâyesi). Test noktaları onaylandı: (1) değerlendirme servisi, (2) sohbet agent'ının araçları.
- `/to-tickets`: 13 iş maddesi, `app/.scratch/goruntu-degerlendirme-agent/issues/`.

### Ticket 01: Proje temeli ve sahte veri ✅
- `pyproject.toml` (pydantic, pydantic-settings, psycopg; geliştirme için pytest, ruff, mypy strict). Ortam: `.venv`, Python 3.14. uv kurulu olmadığı için pip kullanıldı.
- `core/config.py`: ayarlar `.env`'den okunuyor; gizli değerler `SecretStr`.
- `data_package.py`: organizatör formatındaki paketi okuma/yazma ve tutarlılık raporu (dosyası ya da meta'sı eksik görüntü, 5 dakikalık adıma denk gelmeyen çekim saati, adım boşlukları, tekrarlı noktalar, zaman aralıkları).
- `db/repositories.py`: `DataRepository` arayüzü ve `InMemoryRepository`. Zamana bağlı her okuma üst sınır alıyor (ADR-0001).
- `scripts/make_mock_data.py`: organizatör örneğinden sahte paket, `tests/fixtures/mock_package/`. İçeriği: img_000860, img_000100, T0122, T0032 (karenin içinde, 41 m), T0200, 5 rapor (14:20 raporu çekim anından sonra).
- `scripts/load_data.py`: paketi Supabase'e yükler. Tekrar çalıştırılabilir (upsert); `--replace` ve `--check-only` seçenekleri var. Görüntünün kapladığı alan, merkezi ve bölgesi hesaplanıyor.
- Migration'lar repoda: `app/supabase/migrations/` (01–05 ve yeni 06).
- `06_spec_additions` Supabase'e uygulandı:
  - `certainty` enum'u
  - `analysis_runs.brief_json` ve `is_fallback`
  - `detections.is_weak`
  - `track_matches.is_ambiguous`
  - `risk_assessments`: `risk_level` → `final_level` olarak yeniden adlandırıldı; `base_level`, `adjustment_reason` ve `certainty` eklendi
  - `report_evaluations.certainty`
  - `field_reports`'a doğal anahtar
  - `chat_messages` tablosu
- Doğrulama: Sahte veri Supabase'e iki kez yüklendi, sayılar değişmedi. PostGIS sorgusuyla kontrol edildi: img_000860'ın bölgesi Doğu Yolu, kapladığı alan 8.064 m²; 14:10'da T0122 0 m, T0032 41 m.
- Test noktası olmadığı için bu maddede test yazılmadı (tdd skill'i onaylanmamış noktalara test yazılmasını istemiyor).

### Ticket 02: İzci mermi img_000860 uçtan uca ✅
- `agent/service.py`: `EvaluationService`. Adımlar: görüntü → tespit → konum → eşleşme → hareket → risk → brief. Her adım bir `StepEvent`; son olay yapılandırılmış Brief. Brief LLM'siz, şablondan (otomatik özet).
- `pipelines/detection.py`: `Detector` arayüzü ve `MockDetector` (img_000860 truck 727, 284, 58, 34).
- `pipelines/geo.py`: `pixel_to_geo`, `distance_m`, `nearest_zone`.
- `pipelines/matching.py`: 15 m eşik; her track en fazla bir tespite atanıyor; ikinci aday tutuluyor.
- `pipelines/motion.py`: son 30 dakikada üsse mesafe 300 m'den fazla azaldıysa "yaklaşıyor".
- `pipelines/risk.py`: temel seviye tablosu (kritik, yüksek, orta, düşük), görüntü seviyesi = temasların en yükseği, seviyeye bağlı önerilen eylem.
- API:
  - `GET /images`: bölge, çekim saati, son seviye
  - `POST /evaluations`: SSE akışı (`run`, `step`, `brief`, `error` olayları); bilinmeyen görüntüde 404
  - Açılışta kaynak veri Supabase'ten okunup bellek içi depoya alınıyor.
- `db/models.py`: `fetch_package` ve `RunRecorder` (`analysis_runs` ve `agent_steps` tablolarına yazar; istemci bağlantıyı koparsa kayıt `failed` olarak işaretlenir).
- Testler (`tests/test_evaluation.py`, 6 test): img_000860 koordinatı, T0122 eşleşmesi (ikinci aday T0032, 41 m), üsse ~1,6 km, yaklaşıyor, KRİTİK; çekim anı sonrası veri brief'i değiştirmiyor (ADR-0001); olay sırası; önerilen eylem; bilinmeyen görüntü; tespitsiz görüntü.
- Uçtan uca deneme: API gerçek Supabase'e bağlı çalıştırıldı. SSE akışı ve 404 çalışıyor; kayıt `done` ve 7 adım yazıldı.
- Kod incelemesi: 4 bulgu çıktı (ticket 01'den 1, ticket 02'den 3), hepsi düzeltildi. Bulgular: gizli dosyaların görüntü sayılması, bağlantı kopunca kaydın `running`'de kalması, aynı track'in iki tespite atanması, tekrarlanan dakika dönüşümü.
- Tek başıma verdiğim kararlar:
  - API, veri tabanı işlemlerini senkron psycopg ile yapıyor; akış Starlette'in thread havuzunda yürüyor. fastapi-expert skill'i async veri tabanı işlemi öneriyor; buna gerek olursa sonra geçilir.
  - Ayrıntılı analiz tabloları (`detections`, `track_matches`, `risk_assessments`) henüz doldurulmuyor; bütün sonuç `brief_json` içinde.

### Ticket 03: Temas kenar durumları ✅
- **Zayıf tespit:** Güveni < 0,25 olan kutular yok sayılıyor. 0,25–0,50 arası zayıf tespit; ancak bir track'le eşleşirse temas sayılıyor. Güçlü tespitler track'lere önce atanıyor, böylece zayıf bir kopya kutu güçlü tespitin track'ini alamıyor.
- **Belirsiz eşleşme:** Eşik (15 m) içinde birden fazla track varsa `is_ambiguous` işaretleniyor; ikinci aday brief'te görünüyor.
- **Kayıt dışı ve kaçırılmış temas:** Karenin alanında olup tespit edilmeyen track'ler `missed` türünde temas olarak çıkıyor; tipleri bilinmediği için risk yalnızca hareketten hesaplanıyor.
- **Adım dışı çekim saati:** Spec interpolasyon istiyordu, ama bu ADR-0001 ile çelişiyor (sonraki noktayı kullanmak gerekir). Onun yerine son iki noktadan **ileri kestirim** yapılıyor; kestirilen konumlar "olası" kesinliğiyle işaretleniyor. Aynı saatte tekrarlı noktalar olsa da çalışıyor.
- **Tip çelişkisi:** Çekim anına kadarki karelerdeki gözlemler toplanıyor; çelişki varsa daha riskli tip kullanılıyor (truck > bus > van > car). Brief'te `observed_labels`, `type_conflict` ve `effective_label` alanları var.
- **Kesinlik:** kesin (güçlü tespit, tek eşleşme), olası (belirsiz eşleşme, kestirilen konum, kayıt dışı ya da kaçırılmış temas), zayıf (zayıf tespit).
- Veri deposuna `track_points_between` eklendi, artık kullanılmayan `track_points_at` kaldırıldı.
- Testler: 17'si de geçiyor. `tests/test_contact_edge_cases.py` 11 senaryo içeriyor. Sahte veride T0032 karenin içinde olduğu için img_000860'ta artık bir kaçırılmış temas çıkıyor; img_000100'da T0200 kaçırılmış temas (uzaklaşıyor, düşük).
- Uçtan uca deneme gerçek Supabase'le yapıldı: img_000860 KRİTİK; T0122 eşleşmiş, T0032 kaçırılmış.
- Kod incelemesi: 2 bulgu çıktı, ikisi de düzeltildi (tekrarlı noktada sıfıra bölme; zayıf kutunun track çalması).
- Not: Tip geçmişi için her değerlendirmede önceki karelerin tespiti yeniden çalıştırılıyor. 40 görüntüde sorun değil, ama gerçek modelle yavaşlarsa önbelleğe alınmalı.

### Ticket 04: Tam hareket analizi ve kural tablosu ✅
- **Eşik dosyası:** `app/core/risk_rules.toml` ([trend], [motion], [levels] bölümleri) ve onu okuyan `app/core/rules.py`. `EvaluationService` farklı eşiklerle de çalıştırılabiliyor.
- **Hareket özeti (brief'te):** rota, toplam yol, ortalama hız, son 10 dakikadaki hız, yön (kuzey = 0°; yerinde duruyorsa yok), duraklamalar (başlangıç, bitiş, süre, yer, bölge, üsse mesafe), geçilen bölgeler.
- **Kural tablosuna eklenen satır:** Üsse 3 km'den yakın bir yerde ≥ 30 dk duraklama: orta. Burada "3 km"yi duraklamanın yapıldığı yerin üsse mesafesi olarak yorumladım. Sonucu: sahte verideki T0032 (1,6 km'de 2 saattir park halinde) artık orta.
- Kaçırılmış temaslar da tipleri bilinmeden aynı tabloyla değerlendiriliyor (ör. üsse 800 m'de yaklaşıyorsa kritik).
- Otomatik özet metni hız, yön ve duraklamaları gösteriyor.
- Testler: 34'ü de geçiyor. `tests/test_motion_and_rules.py` şunları kapsıyor: kural tablosunun her satırı, kayıt dışı temas satırları, eşik dosyası (varsayılan, değiştirilmiş, özel yol), görüntü seviyesi = temasların en yükseği, T0122'nin hareket özeti.
- T0122'nin hareket özeti demo ile uyumlu: son 10 dk 6,4 m/s, 12:10'da 40 dk ve 13:15'te 45 dk duraklama, yön 252°. Sahte rotanın toplam yolu 7,9 km; demo 10,5 km diyor.
- Uçtan uca deneme gerçek Supabase'le yapıldı. Kod incelemesinde bulgu çıkmadı.
- Kapsam dışı kalan: Spec'teki "rapor kendi track'iyle çelişiyor → yüksek" satırı rapor değerlendirmesine (ticket 06) bağlı.

### Ticket 05: Model yönlendirme ve rapor ayrıştırma ✅
- **Mimari değişiklik:** Planlanan LiteLLM yerine Claude modelleri resmi `anthropic` SDK'sıyla (1.8) çağrılıyor. claude-api skill'i başka sağlayıcıların arayüzünü taklit eden ara katmanlara izin vermiyor. GLM yedeği `openai` SDK'sıyla, OpenAI uyumlu uç noktası üzerinden ayrı bir sağlayıcı.
- `app/llm/models.toml`: model kataloğu ve görev zincirleri. YAML yerine TOML seçildi (ek bağımlılık yok, `risk_rules.toml` ile tutarlı).
  - report_parse: Haiku 4.5 → GLM
  - vision: Sonnet 5 → GLM
  - reasoning: Opus 5.5 → GLM
  - chat: Sonnet 5 → GLM
- `app/llm/client.py`: `AnthropicProvider` (`messages.parse` + Pydantic şeması, reddetme kontrolü), `GlmProvider` (JSON modu + şema doğrulama) ve `LLMRouter`. Router kimlik bilgisi olmayan modeli atlıyor, hata veren ya da şemaya uymayan cevapta sıradaki modele geçiyor; hepsi başarısızsa denemelerin listesiyle `LLMUnavailableError` fırlatıyor.
- `app/schemas/claims.py`: `ReportClaim`. Bu model hem LLM'den istenen şema hem de normalize edilmiş iddianın kendisi.
- `app/pipelines/report_parser.py`: Prompt `agent/prompts/report_parse.md` dosyasında.
  - Koordinatlar rapor metninden regex ile okunuyor ve LLM'in verdiğinin yerine geçiyor. Metinde olmayan koordinat atılıyor.
  - Bölge adları, Türkçe karakter farkı gözetilmeden bilinen bölgelerle eşleniyor; tanınmayan bölge atılıyor.
  - Sıfır ya da negatif araç sayısı atılıyor.
- `scripts/parse_reports.py` ve `db/models.py` (`reports_to_parse`, `replace_claims`): Varsayılan olarak yalnızca iddiası olmayan raporlar işleniyor; `--force` hepsini yeniden ayrıştırıyor.
- Testler (`tests/test_report_parser.py`, 14 test, sahte sağlayıcılarla): koordinat ve bölge normalizasyonu, çok iddialı rapor, yedek modele geçiş (hata, geçersiz çıktı, kimlik bilgisi yok), hepsinin başarısız olması, görev yönlendirmesi. Toplam 48 test.
- Test noktası notu: Bu, onaylanan iki test noktasının dışında üçüncü bir nokta. Ticket'ın kabul kriteri sahte LLM ile test istediği için eklendi.
- Doğrulama:
  - `.env`'de anahtar olmadığı için gerçek LLM çağrısı yapılamadı; komut her raporda anlaşılır bir hatayla 1 koduyla çıktı.
  - `ant` CLI da yok.
  - Veritabanına yazma elle hazırlanmış bir iddiayla Supabase'te doğrulandı (koordinat → geography, bölge → `zone_id`), sonra silindi. `report_claims` şu an boş.
- Kod incelemesi: 1 bulgu çıktı, düzeltildi. LLM tanınmayan bir bölge adı verdiğinde metindeki koordinat kayboluyordu.

### LLM sağlayıcısı: EVREN (SSB) ✅
- EVREN'in LLM servisi ana sağlayıcı oldu: OpenAI uyumlu, `https://evren-llmapi.ssyz.org.tr/v1`. 1 Kasım 2026'ya kadar ücretsiz; günde 10M token, dakikada 500K token, en fazla 32 paralel istek. Veri Türkiye'de işleniyor.
- Kullanım şartları v1, kullanıcının açık onayıyla API üzerinden kabul edildi (26 Eylül). Önce metin okunup özetlendi.
- `GlmProvider`, genel `OpenAICompatibleProvider`'a dönüştü; EVREN ve organizatör GLM'i bununla bağlanıyor. Şema modele `response_format=json_schema` ile veriliyor. `max_tokens` en az 4096, çünkü düşünen modellerde bütçe düşünmeyle paylaşılıyor.
- `models.toml` zincirleri:
  - Metin görevleri: EVREN `glm-5.3` → organizatör GLM (`GLM_API_KEY`) → EVREN `deepseek-v4.1-flash` → Claude
  - VLM: `qwen3-vl-30b` → `gemma-4-31b` → `deepseek-v4.1-flash` → Sonnet 5
- Router, cevabı veren modeli `sağlayıcı/model` biçiminde döndürüyor (ör. `evren/glm-5.3`), çünkü aynı model iki sağlayıcıda da var.
- **Gerçek çağrı:** 5 raporun hepsi GLM-5.3 ile ayrıştırıldı ve sonuçlar doğru (dostluk iddiaları, "ağır araç", "mavi araç", belirsiz zaman).
  - Süre: rapor başına ~30–50 sn.
  - Bir raporda GLM-5.3 ve DeepSeek anlık olarak 503 ("modele bağlanılamadı") döndü; ikinci çalıştırmada başarılı oldu.
  - **Canlı demo riski:** Brief yazımı (ticket 07) da GLM-5.3 kullanacak; gecikme ve 503'ler için otomatik özete geçiş kritik.

### Ticket 06: Rapor değerlendirme ✅
- `app/pipelines/reports.py`: iddialar kodla değerlendiriliyor (ADR-0002).
  - **Bağlama:** Koordinatlı iddia, **rapor saatinde** konumuna ≤ 150 m olan temasa bağlanıyor.
  - **Karşılaştırma:** Tip belirtilmişse temasın tipiyle karşılaştırılıyor ("ağır" = truck/bus, "hafif" = car/van). Renk, VLM (ticket 08) gelene kadar doğrulanamıyor.
  - **Çelişki:** Rapor saatinde orada kimse yoksa ama bir temasın o saatte **başka bir yerde olduğu biliniyorsa** ve şu an oradaysa, iddia çelişkili; temas en az yüksek. O saatte kaydı olmayan track için çelişki sayılmıyor.
  - **Dostluk iddiası:** Ancak kaynak resmiyse ve belirtilen her özellik doğrulandıysa riski düşürüyor (doğrulanmış dost → düşük). Üçüncü taraf ya da doğrulanamayan özellik varsa etkisi yok.
  - **Tehdit uyarısı:** seviyeyi +1 kademe artırıyor.
  - **Çakışma:** Riski artıran etki, düşüreni eziyor.
  - **Liste dışı kalanlar:** Pencere dışındaki (120 dk), görüntüden uzak (> 500 m) ve çekim anından sonraki raporlar değerlendirilmiyor.
  - **Belirsiz olanlar:** Konumu olmayan dostluk iddiası, tehdit uyarısı ve söylentiler "doğrulanamaz" olarak listeleniyor. Görüntünün bölgesini anan bölge iddiaları da doğrulanamaz.
- Eşikler `risk_rules.toml`'da, yeni `[reports]` bölümünde.
- Veri deposuna `claims_until` eklendi (`ClaimRecord`). API açılışta iddiaları da Supabase'ten okuyor (`fetch_claims`).
- Brief'e eklenenler: `report_findings` (rapor kararı, kesinlik, etki, gerekçe, bağlanan track) ve temasta `verified_friend`. Rapor etkileri temasın nihai seviyesine uygulanıyor; temel seviye kuralların sonucu olarak kalıyor. Otomatik özet metninde "Raporlar:" bölümü var.
- Olay akışına "raporlar" adımı eklendi (risk adımından önce).
- Testler: `tests/test_report_evaluation.py` 16 senaryo; toplam 64 test. Senaryolar: aday seçimi, rapor saatindeki konumla karşılaştırma, asimetrik güven (resmi/üçüncü taraf, doğrulanamayan renk, yanlış tip), çelişki, tehdit uyarısı, çelişkinin doğrulanmış dostluğu ezmesi, kaydı olmayan track.
- **Gerçek veriyle uçtan uca:** GLM-5.3'ün çıkardığı iddialarla img_000860'ta 4 iddia listelendi (2 tutarlı, 2 doğrulanamaz); seviyeler değişmedi (KRİTİK).
  - **Önemli bulgu:** 12:35 raporundaki nokta o saatte T0122'ye değil, park halindeki **T0032'ye** (38 m) denk geliyor; rapor T0032 ile tutarlı. Organizatör demosu bu raporu T0122'ye bağlıyor (RISKLER R7).
- Kod incelemesi: 1 bulgu çıktı, düzeltildi (kaydı olmayan track'in çelişki sayılması).
- Türkçe ek hatası ("13:40'teki") metin "saat 13:40 konumunda" biçiminde yazılarak giderildi.

### Ticket 07: LLM karar ayarı ve brief yazarı ✅
- `app/agent/decision.py`: LLM (görev `reasoning`, GLM-5.3) temasları `K1`, `K2` etiketleriyle ve bulgularla birlikte alıyor. Çıktısı temas başına seviye önerisi, gerekçe, kanıt iddia kimlikleri ve değerlendirme paragrafı.
- **Kod öneriyi doğruluyor ve şunları reddediyor:**
  - bir kademeden fazla değişiklik
  - kanıtsız düşürme
  - başka bir temasa ait ya da "tutarlı" olmayan kanıtla düşürme
  - bir raporun riskini yükselttiği temasın düşürülmesi (ADR-0002: riski artıran etki kazanır)
- Kabul edilen ayarın gerekçesi `adjustment_reason`, reddedilen önerinin sebebi `adjustment_rejected` alanında.
- **Zaman sınırı** (`risk_rules.toml` [brief] `timeout_s = 45`): Süre aşılırsa ya da hiçbir model cevap vermezse otomatik özete geçiliyor; `fallback_reason` alanında sebep yazıyor.
- Brief'in başlığı, bulgular, raporlar ve önerilen eylem kodla üretiliyor; LLM yalnızca "Değerlendirme" paragrafını yazıyor. Brief'te `model` alanı var (ör. `evren/glm-5.3`).
- Olay akışına "karar" adımı eklendi: risk → karar → brief.
- `models.toml`'da model başına `extra_body` alanı var. GLM-5.3 için düşünme kapalı: `chat_template_kwargs.enable_thinking=false`.
- **Gecikme ölçümleri (img_000860, EVREN):**
  - Düşünme açıkken: GLM-5.3 4096 token'ın tamamını düşünmeye harcadı ve 86 sn'de boş cevap döndü. Bir çalıştırmada yedek DeepSeek devreye girdi, toplam 29–77 sn sürdü.
  - Düşünme kapalıyken: doğrudan çağrı 4,1 sn, 153 token, geçerli JSON.
  - API üzerinden 3 çalıştırma: 19 / 13 / 20 sn, üçünde de `evren/glm-5.3`.
  - 503 oranı yüksek: tek denemede isteklerin yaklaşık yarısı ilk seferde 503 aldı. SDK'nın 2 yeniden denemesi bunları karşılıyor.
- **Gerçek çıktı örneği:** GLM-5.3, T0122'yi kanıt göstermeden KRİTİK'ten YÜKSEK'e düşürmek istedi, kod reddetti. Başka bir çalıştırmada DeepSeek T0032'yi gerekçesiyle ORTA'dan YÜKSEK'e çıkardı ve sahte dostluk iddiasını kullanmadı.
- Prompt düzeltmeleri: temaslar K1/K2 değil track kimliğiyle anılıyor, İngilizce terim kullanılmıyor.
- **Hata düzeltmesi:** GLM boş değerlendirme döndürdüğünde başlıkta yanlışlıkla "(otomatik özet)" yazıyordu. Artık etiket, brief'i bir LLM'in yazıp yazmadığına bağlı.
- Testler: `tests/test_llm_decision.py` 14 senaryo; toplam 79 test. Kapsananlar: ±1 kademe, kanıtlı ve kanıtsız düşürme, başka temasın kanıtı, raporun yükselttiği temas, yedek model, hepsinin başarısız olması, zaman aşımı, LLM'siz akış, boş değerlendirme, olay sırası, model ayarının sağlayıcıya iletilmesi.
- Kod incelemesi: 1 bulgu çıktı, düzeltildi. LLM, raporun yükselttiği bir temasın seviyesini düşürebiliyordu.

### Ticket 09: Önbellek, yeniden hesaplama ve değerlendirme okuma ✅
- `app/agent/runner.py`: `EvaluationRunner`, `RunStore` arayüzü ve testler için `InMemoryRunStore`. Kayıt, önbellekten tekrar oynatma ve bağlantı kopması mantığı API katmanından buraya taşındı; API ince kaldı.
- **Önbellek kuralı:** Görüntünün son başarılı değerlendirmesi, adımlarıyla birlikte tekrar oynatılıyor; tespit ve LLM yeniden çalışmıyor. LLM'in yazdığı brief, daha yeni bir otomatik özete tercih ediliyor; demoda 503 yüzünden oluşan bir özet iyi sonucun önüne geçmiyor. Başarısız kayıtlar önbellek sayılmıyor. Güncel şemaya uymayan eski kayıtlar atlanıyor.
- `db/models.py` `RunRecorder` bu arayüzü karşılıyor: `get` (bütün adımlarla) ve `latest_cached` eklendi; kayıt kimlikleri artık string.
- `schemas/runs.py`: `StoredRun`. Veritabanı katmanı agent katmanını import etmesin diye ayrı modülde.
- API:
  - `POST /evaluations {image_id, recompute}`: `run` olayında `cached` bayrağı var.
  - `GET /evaluations/{run_id}`: kayıt, bütün adımları ve brief ile; bulunamazsa 404.
  - İç üreteç, bağlantı kapanmadan kapatılıyor (`contextlib.closing`), böylece kopmada kayıt `failed` işaretlenebiliyor.
- Testler: `tests/test_runner_cache.py` 8 senaryo; toplam 87 test. Senaryolar: kayıt, önbellekten tekrar oynatma (tespit tekrar çalışmıyor), yeniden hesaplama, LLM brief'inin otomatik özete tercihi, başka seçenek yokken otomatik özetin önbelleklenmesi, başarısız kaydın atlanması, bağlantı kopması, kayıt okuma.
- **Uçtan uca (Supabase + EVREN):** önbellekten dönüş ~2 sn, yeni değerlendirme ~8 sn (GLM-5.3). Yeniden hesaplamadan sonraki istek yeni kaydı döndürdü. `GET` 9 adımı döndürdü. Bilinmeyen ve geçersiz kimlikte 404.
- Kod incelemesi: 1 bulgu çıktı, düzeltildi. Eski şemadaki bir kayıt önbellek aramasını çökertiyordu; img_000100'de gerçekten oluyordu.

### Ticket 10: Sohbet agent'ı ✅
- `app/agent/tools.py`: 5 salt okuma aracı, hepsi aktif değerlendirmenin çekim anıyla sınırlı (ADR-0001):
  - `temas_gecmisi`: rota, eğilim, hız, yön, duraklamalar
  - `raporlari_ara`: konum, bölge ya da saat aralığıyla
  - `rapor_degerlendirmesi`: brief'teki rapor kararı ve gerekçesi
  - `goruntu_degerlendir`: yalnızca çekim saati daha önce olan görüntüler; önbellek kullanıyor
  - `track_diger_goruntulerde`
- Çekim anından sonraki bir iddia, hiç var olmayan bir iddiayla aynı cevabı alıyor ("bulunamadı"); varlığı sızmıyor. Araçlar hata fırlatmıyor, `{"hata": ...}` döndürüyor.
- `app/agent/chat.py`: `ChatAgent`.
  - Araç çağırma döngüsü soru başına en fazla 6 tur; sınıra ulaşırsa bunu açıkça söylüyor.
  - Konuşma geçmişi ve aktif brief modele bağlam olarak veriliyor.
  - Hiçbir model cevap veremezse `error` olayı yayılıyor.
- `app/llm/client.py`:
  - `ToolCall`, `ChatTurn` ve sağlayıcılara `chat` eklendi. OpenAI uyumlu sağlayıcı araç çağırmayı destekliyor; Claude sağlayıcısı "desteklenmiyor" diyor ve zincir sıradaki modele geçiyor.
  - `complete_json` ve `chat` aynı zincir mantığını (`_run_chain`) paylaşıyor.
- **Sızan düşünce sorunu:** Düşünmesi kapalı GLM-5.3, İngilizce iç akıl yürütmesini cevabın başına yazıyordu. `<cevap>` etiketi talimatını da dinlemedi. Çözüm:
  - Etiket varsa etiketin içi kullanılıyor.
  - Yoksa taslak, kısa bir yapılandırılmış çıktı çağrısıyla temizleniyor (`{"cevap": ...}`).
  - Bu çağrı da başarısız olursa: "Sonuç:" işaretinden önceki kısım yalnızca İngilizce bir düşünceye benziyorsa atılıyor; Türkçe bir cevap kesilmiyor.
- Mesajlar `chat_messages` tablosuna yazılıyor (`ChatRecorder`). `schemas/chat.py`'deki `ChatMessage`, katmanlar ters bağlanmasın diye ayrı modülde.
- API: `POST /evaluations/{run_id}/chat {message}`. SSE ile `tool` (araç adı, argümanlar, sonuç) ve `answer` (içerik, model) ya da `error` olayları akıyor. Tamamlanmamış değerlendirme için 404.
- Testler: 110 test.
  - `tests/test_chat_tools.py` (12): ikinci onaylı test noktası, çekim anı sınırı
  - `tests/test_chat_agent.py` (11): araç döngüsü, geçmiş, bağlam, yedek model, hata, adım sınırı, sızan düşüncenin temizlenmesi
- **Canlı deneme (EVREN, GLM-5.3), soru başına 11–16 sn:**
  - "T0122 nereden geldi?" → `temas_gecmisi`
  - "13:40 dost devriye raporu neden riski düşürmedi?" → iki kez `rapor_degerlendirmesi`
  - "T0122 başka görüntülerde görünmüş mü?" → `track_diger_goruntulerde`
  - Model doğru aracı kendi seçti; cevaplar Türkçe ve önce sonucu veriyor.
  - "14:30'da nerede olacak?" sorusunda "şu anda bilinemez" dedi, kestirimini açıkça tahmin olarak işaretledi.
- Kod incelemesi: 1 bulgu çıktı, düzeltildi. Yedek temizleme mantığı Türkçe bir cevabı ilk "Sonuç:" ifadesinden kesiyordu.

### Ticket 08: VLM görsel doğrulama ✅
- `app/pipelines/vision.py`: `VisualVerifier` arayüzü ve `VlmVerifier` (görev `vision`: qwen3-vl-30b → gemma → deepseek → Sonnet 5). Tespit kutusu çevresiyle kırpılıp en az 384 px'e büyütülüyor (Pillow, yeni bağımlılık) ve JPEG olarak gönderiliyor. Cevap: `is_vehicle`, `color` (11 renklik Türkçe palet), `cargo` (loaded / empty). Dosya yoksa, okunamıyorsa, model cevap vermezse ya da 30 sn aşılırsa sonuç yok, özellik "doğrulanamadı" kalıyor.
- `app/llm/client.py`: `complete_json`'a isteğe bağlı `image` eklendi (OpenAI uyumlu: `image_url` data URL; Claude: base64 image bloğu). Görüntüsüz çağrılar değişmedi.
- **Yalnızca gerektiğinde ve kutu başına en fazla bir kez:**
  - Track'le eşleşen zayıf tespit. VLM araç değil derse kutu düşüyor, track kaçırılmış temas olarak kalıyor. Araç derse kesinlik "zayıf"tan "olası"ya çıkıyor.
  - Temasa bağlanan iddia renk ya da yük belirtiyorsa (`evaluate_claims`'e tembel `observe` geçiliyor). Kaçırılmış temasın kutusu olmadığı için rengi doğrulanamıyor.
- **Rapor kararına etkisi:** Renk rapordan paletteki renge indirgeniyor ("koyu yeşil" → yesil, "lacivert" → mavi). Renk ya da yük uyuşmazsa iddia çelişkili, temas en az yüksek; yalnızca görsel özelliğe dayalı çelişki "olası" kesinlikte. Renk tutarsa resmi dostluk iddiası artık riski düşürebiliyor.
- İddiaya `cargo` alanı eklendi; `07_claim_cargo` migration'ı Supabase'e uygulandı, `fetch_claims`/`replace_claims` güncellendi. Rapor ayrıştırma prompt'u yükü soruyor.
- Brief: temasta `visual` alanı, notlarda "görsel: beyaz, yüklü", kaynaklarda VLM modeli. Olay verisi: `eslesme.visually_rejected`, `raporlar.visual_checks`. Karar LLM'i de görsel bulguyu görüyor.
- Testler: `tests/test_visual_verification.py` 21 senaryo (sahte VLM); toplam 131 test.
- Canlı deneme: sentetik bir karede EVREN `qwen3-vl-30b` rengi doğru bildi (mavi), düz dikdörtgeni araç saymadı, 0,4 sn. Gerçek görüntü olmadığı için uçtan uca VLM denemesi yapılamadı (R11).
- Kod incelemesi: 1 bulgu çıktı, düzeltildi (okunamayan görüntü dosyası bütün değerlendirmeyi düşürüyordu).

### Ticket 11: Gerçek tespit modeli ✅ (ağırlıklar bekleniyor)
- Model ekibinin teslim biçimi soruldu: **Ultralytics YOLO `.pt`**.
- `app/pipelines/detection.py`:
  - `UltralyticsDetector` aynı `Detector` arayüzünü gerçekleştiriyor. Kutular xyxy → (x, y, w, h), güven ve sınıf; sınıf adları `CLASS_ALIASES` ile eşleniyor (car/van/truck/bus ve Türkçe karşılıkları), tanınmayan sınıf uyarıyla atlanıyor.
  - Model ilk tespitte yükleniyor; ultralytics yalnızca model modunda import ediliyor (isteğe bağlı bağımlılık: `pip install -e '.[model]'`, torch'u da kurar).
  - Modelden `conf = 0,25` (yok sayma eşiği) ile tahmin isteniyor; isteğe bağlı `DETECTOR_IMGSZ`.
  - Her görüntü bir kez çalıştırılıyor (önbellek); yükleme ve çıkarım kilitle sıraya alınıyor. Böylece tip geçmişi için önceki karelerin tekrar tespiti ucuz.
  - Görüntü dosyası yoksa `ImageFileMissingError` (boş kare sayılmıyor). Önceki bir karenin dosyası yoksa yalnızca o karenin tip geçmişi atlanıyor.
  - `build_detector(settings)`: `DETECTOR_MODE=mock` → `MockDetector`; `model` → `UltralyticsDetector`. Ağırlık yolu tanımsız ya da dosya yoksa açılışta anlaşılır hata. Sürüm `yolo:<dosya adı>` olarak kayda yazılıyor.
- `Detector` protokolüne `version` eklendi; API artık `MockDetector` yerine protokole bağlı. `find_image_file` `data_package.py`'ye taşındı (VLM ve tespit ortak kullanıyor).
- Testler: `tests/test_detector_model.py` 13 senaryo (Ultralytics sonuç biçimini taklit eden sahte model; referans örnek T0122 / KRİTİK), toplam 145 test.
- Kod incelemesi: 2 bulgu çıktı, düzeltildi:
  - Önbellek tespit bileşeni sürümüne bakmıyordu; model moduna geçince sahte tespitli eski kayıt tekrar oynatılabilirdi. Artık `latest_cached` aynı `detector_version`'la sınırlı (Supabase'te sorgu doğrulandı).
  - Önceki bir karenin dosyası eksikse bütün değerlendirme düşüyordu.
- Gerçek ağırlık olmadığı için gerçek modelle deneme yapılmadı; ultralytics/torch kurulmadı.

### Ticket 12: Değerlendirme seti koşucusu ✅
- **Etiket biçimi (TOML):** Görüntü başına beklenen seviye, isteğe bağlı olarak bir tespitle eşleşmesi gereken track'ler ve rapor başına beklenen karar. Rapor, saat ve kaynakla tanımlanıyor; isteğe bağlı `claim_type` raporun yalnızca o türdeki iddialarını değerlendiriyor. `ignored` kararı, rapor o görüntüde hiç değerlendirilmemeli demek (ör. çekim anından sonra). Hatalı seviye, yazım hatalı alan, geçersiz saat ve aynı görüntünün iki kez etiketlenmesi dosya adıyla birlikte reddediliyor. Biçim ve açıklaması `backend/eval/mock_labels.toml`'da.
- `app/eval_set.py`: `load_labels`, `run_eval_set`, `render`. Her görüntü baştan değerlendiriliyor (önbellek yok); bir görüntünün hatası diğerlerini durdurmuyor.
- **Ölçümler:**
  - seviye doğruluğu ve düşük tahmin sayısı (asıl tehlike)
  - eşleşme: doğru eşleşen / beklenen, fazladan eşleşme
  - rapor kararı doğruluğu
  - çelişkili rapor yakalama oranı ve yanlış alarm
  - LLM'in yazdığı brief sayısı
- Bir raporun iddiaları farklı karar alırsa raporun kararı: çelişkili > tutarlı > doğrulanamaz > ilgisiz.
- Komut: `python -m scripts.run_eval_set [etiketler.toml] [--no-llm] [--json çıktı.json]` (`run-eval-set`). Veri ve iddialar Supabase'ten, tespit bileşeni `DETECTOR_MODE`'dan.
- Testler: `tests/test_eval_set.py` 16 senaryo (sahte etiketler); toplam 161 test.
- **Gerçek çalıştırma (Supabase, GLM-5.3'ün çıkardığı iddialar):** Kurallarla 2/2 seviye, 1/1 eşleşme, 5/5 rapor kararı. LLM ile de aynı sonuç, 13 sn, iki brief'i de GLM-5.3 yazdı. Sahte veride çelişkili rapor olmadığı için yakalama oranı ölçülemedi (0/0); o senaryo testlerde var.
- Kod incelemesinde bulgu çıkmadı.

### Proje incelemesi ve boş değerlendirme düzeltmesi
- **İnceleme:** API gerçek Supabase ve EVREN ile uçtan uca çalıştırıldı: yeni değerlendirme 8 sn, önbellekten 1,7 sn, sohbet 23 sn (doğru araç seçimi), 404'ler doğru, 500 yok. Mantık katmanının test kapsamı %95–100; API, veritabanı ve script'ler (spec gereği) birim testi dışında, elle doğrulandı.
- **Bulgu (düzeltildi):** GLM-5.3 değerlendirme paragrafını zaman zaman boş ya da "..." döndürüyordu (6 denemede 3); brief yine de "LLM yazdı" diye işaretleniyordu. Artık `DecisionDraft.assessment` en az 3 kelimelik gerçek bir paragraf istiyor (şemada `min_length=20`). Uymayan cevap zincirde sıradaki modele geçiyor, hiçbiri uymazsa otomatik özete düşülüyor. Canlı denemede 6/6 brief paragraflı.
- **Bulgu (açık, R12):** Kaggle eğitim görüntülerinde görüntü başına ortanca 21 araç var. Track'i olmayan her araç en az orta, üsse < 2 km'de yüksek sayıldığı için kalabalık karelerde "kayıt dışı temas seli" oluşuyor. img_000860'a 25 sahte kutuyla denendi: 19 kayıt dışı temas yüksek, brief 29 satır.
- **Bulgu (açık):** Paragraf metninde hâlâ olgu ve üslup hataları var: kaçırılmış temas T0200'e "kayıt dışı" deniyor, temas etiketleri (K1, K2) metne sızıyor, "muhtemel düzeyinde" gibi çeviri ifadeleri kullanılıyor. Brief'te mesafeler "1.6 km" diye yazılıyor ("1,6 km" olmalı).
- **Karar:** Sıradaki iş, Kaggle eğitim görüntülerinden sentetik bir 2. aşama paketi üretmek (40 görüntü, track'ler, bilerek yanlış raporlar, otomatik etiketler) ve bütün pipeline'ı onunla koşturmak.

### Sentetik 2. aşama paketi ve bütün pipeline'ın koşturulması
- `scripts/make_synthetic_data.py`: Kaggle eğitim görüntülerinden (`train/`, 6.471 gerçek drone görüntüsü, 165 bin etiketli kutu) organizatör biçiminde paket üretiyor.
  - Görüntü ve kutular gerçek; konum, track ve raporlar uydurma. Ölçek, otomobil kutusunun boyundan kestiriliyor (~4,5 m).
  - 10 görüntülük desen: yaklaşan ağır ve hafif araç, üsse yakın park, kayıt dışı, kaçırılmış temas, sakin trafik. Arka plan araçları yerinde gidip gelen yerel trafik ya da park halinde.
  - Raporlar organizatör üslubunda ve bir kısmı bilerek yanlış: konum/saat çelişkisi, yanlış tip, üçüncü taraf sahte dostluk. Ayrıca resmi dostluk, tehdit uyarısı, çekim sonrası, ilgisiz ve bölge raporları var.
  - Beklenen etiketler senaryonun gerçek değerlerinden kural tablosuyla hesaplanıyor; pipeline bunları pikselden, track'ten ve rapor metninden çıkarmak zorunda.
  - Üreteç tutarlılığı doğruluyor: başka bir görüntünün track'i bir kareye düşmemeli, raporlar doğru araca bağlanmalı, track'siz güçlü bir kutu zayıf ya da kaçırılmış bir aracın track'ini kapmamalı.
  - `--coverage`: arka plan araçlarından track'i olanların oranı (R12 stres testi).
- Sahte detektör tespitleri dosyadan okunabiliyor (`DETECTOR_MOCK_PATH`). `run_eval_set` Supabase'siz de çalışıyor (`--package`, `--claims`, `--detections`).
- Değerlendirme seti, LLM'in seviyeyi değiştirdiği görüntüleri ayrıca sayıyor ("LLM ayarı"); etiketler kural tablosuna göre olduğu için LLM açıkken seviye farkı kural hatası anlamına gelmeyebilir.
- `tests/test_synthetic.py`: pipeline sentetik senaryoyu birebir geri çıkarmalı. Bilerek bozma denemesi yapıldı (rapor bağlama mesafesi 150 → 3 m): rapor kararları %36'ya, çelişki yakalama 0/4'e düştü; test gerçekten ölçüyor. Toplam 174 test.
- **Sonuçlar (40 görüntü, 619 araç, 609 track, 17.613 nokta, 28 rapor):**

| Çalıştırma | Seviye | Eşleşme | Rapor kararı | Çelişki | Süre |
|---|---|---|---|---|---|
| Kurallar, ideal iddialar (yerel) | 40/40 | 605/605 | 28/28 | 8/8 | 3 sn |
| Kurallar, GLM'in ayrıştırdığı iddialar (Supabase) | 40/40 | 605/605 | 27/28 | 8/8 | — |
| LLM karar + brief + VLM (Supabase) | 31/40 | 603/605 | 27/28 | 8/8 | 7 dk |

  - Supabase'e yükleme 15 sn, GLM ile 28 raporun ayrıştırılması 74 sn. GLM'in ayrıştırması neredeyse kusursuz: koordinat, tip ve iddia türü doğru. Tek hata, aynı kalıptaki üç "yol çalışması" raporundan birinin ilgisiz yerine gözlem sayılması.
  - LLM açıkken 9 seviye farkı var ve hepsi LLM'in ±1 kademe ayarı; 8'i yukarı. Örnekler: resmi olarak doğrulanmış iki dost aracı "düşük"ten "orta"ya çıkardı; 2,7–2,9 km'de yaklaşan araçları kritiğe çıkardı; 1,1 km'de 2 saattir park halindeki kamyonları yükseltti. Aynı görüntülerin yeniden çalıştırılmasında 5 görüntünün 4'ünde hiç ayar yapmadı; LLM kararı tekrarlanabilir değil.
  - **Dikkat:** Bir çalıştırmada LLM, 1,7 km'de yaklaşan bir otobüsü kritikten yükseğe düşürdü. Kanıt olarak, aracın 45 dk önce uzakta park halindeyken "hareketleri olağan" diyen tutarlı bir rapor gösterdi. Kod buna izin veriyor, çünkü tutarlı her iddia düşürme kanıtı sayılıyor.
  - VLM 70 zayıf kutunun 2'sini "araç değil" diye reddetti; ikisi de gerçek araçtı, track kaçırılmış temasa döndü.
  - GLM bir kez 21 bin satır boş satırdan oluşan bozuk bir cevap verdi; o görüntü otomatik özete düştü.
- **Brief uzunluğu:** Görüntü başına ortanca 16 temas; brief ortanca 20, en fazla 34 satır. `--coverage 0.6` ile kayıt dışı temas ortancası 5 (en fazla 16) ve hiçbir görüntü düşük kalmıyor (5 → 0).
- Supabase'te şu an sentetik paket yüklü (sahte paketin yerine). Geri dönmek için: `load_data tests/fixtures/mock_package --replace` + `parse_reports`.

### Canlı iz sürme komutu
- `scripts/trace_evaluation.py`: tek bir görüntüyü canlı değerlendirip her kolun çıktısını geldiği anda basıyor: meta, Kol A (tespit, konum), Kol B1 (çekim anı konumları), Birleşim 1 (eşleşme), Kol B2 (hareket), Birleşim 2 (temel seviye), Kol C (raporlar), risk, LLM kararı, brief. LLM ve VLM çağrıları zaman damgası ve süreyle log olarak araya düşüyor; `--image-out` kutuları, track'leri ve seviyeleri görüntünün üzerine çiziyor.
- Servis olaylarına eklenenler (geriye dönük uyumlu): "hareket" adımında temel seviyenin girdileri, "eslesme" adımında her eşleşmenin kutusu. LLM yönlendiricisi başarılı çağrıları süresiyle, VLM sonuçlarını logluyor.
- `scripts/common.py`: değerlendirme seti ve iz sürme komutunun ortak kurulumu.
- **Canlı örnek (img_002724, Supabase + EVREN, 6–8 sn):** 11 araç. VLM zayıf kutulardan birini onayladı (beyaz otomobil), diğerini reddetti; o gerçek bir minibüstü, çatı gölgesinde kısmen görünüyordu, T0314 kaçırılmış temasa döndü. 13:15 resmi tehdit uyarısı, 7,5 km ötedeki bir noktayı gösterdiği halde aracın rapor saatindeki konumu üzerinden doğru araca (T0316) bağlandı; seviye yüksek → kritik.
- **Bulgu:** İlk çalıştırmada LLM, T0316 hakkındaki tehdit uyarısını gerekçe gösterip T0314'ü orta seviyeye çıkardı; değerlendirme paragrafında da T0316'ya "kayıt dışı temas" dedi. Yükseltmeler kanıt istemediği için kod bunu kabul etti. İkinci çalıştırmada LLM hiç ayar yapmadı, ama kaçırılmış temas T0314'e yine "kayıt dışı" dedi (R14 ve brief prompt'u maddesi).

### Stage2 verisi geldi: analiz ve kayıt dışı temas kuralı (ADR-0003)
- **Veri analizi** (`stage2/`): 40 görüntü, 226 track (her biri tam 25 nokta / 120 dk, boşluk ve tekrar yok), 137 rapor (98 resmi, 39 üçüncü taraf, 72'si koordinatlı, 4 ve 5 basamaklı koordinatlar). Bütün çekim saatleri 5 dk adımında; bütün kareler kuzeye hizalı. **Her track tam olarak bir görüntünün çekim anında bitiyor**; görev tanımı da bunu söylüyor. Her karede yalnızca 3–7 track var. Stage2 görüntüleri Kaggle eğitim etiketlerinde yok (0/40); tespit için ekibin modeli gerekiyor.
- **Şema bulguları:** `field_reports` doğal anahtarı `(time, source, text)`, gerçek verideki iki çift birebir aynı raporu sessizce siliyor (137 → 135); `seq` sütunu önerildi. Analiz tabloları hâlâ boş; `match_status` enum'u koddaki temas türleriyle aynı değil. Enum'lar, koordinat biçimleri ve kısıtlar veriyle uyumlu.
- **Görev tanımı** (`stage2/gorev_tanimi.pdf`): park halindeki araçların hareket kaydı olmayabilir; eşleşmede "makul bir mesafe sınırı"; organizatör GLM'i `glm-5.3-flash`, düşünme kapatılamıyor.
- **Kural değişikliği (ADR-0003):** Kayıt dışı temas artık düşük ("hareket kaydı yok, park halinde olabilir"); yalnızca üsse `unregistered_alert_m`'den (1 km) yakınsa orta. Önceki kural: en az orta, < 2 km yüksek. Karar prompt'una temas türlerinin Türkçe karşılıkları ve "track'i yok diye yükseltme" kuralı eklendi.
- **Etki (sentetik paketler, aynı veri):** %60 kapsamada 217 kayıt dışı temasın 216'sı düşük; düşük görüntü 0 → 6, yüksek 15 → 10, kritik değişmedi (8). Tam kapsamada düşük 5 → 8.
- Testler: kural tablosu satırları (< 1 km orta, 1,5 ve 2,5 km düşük), gerekçe metni, eşiğin dosyadan okunması; toplam 178.

### Ekibin tespit modeli pipeline'a bağlandı (EVREN model platformu)
- Model: `u84f118304558/d2-y26l-v2-60ep-mixup01` (YOLO26-L, sınıflar car/van/truck/bus, imgsz 1280), EVREN'de barındırılıyor. Resmi `evren-sdk` (0.9.2, PyPI, SSB) kuruldu; kurulmadan önce paket incelendi (tek bağımlılık httpx; istek adresi `api.ssyz.org.tr`).
- `EvrenDetector` (`DETECTOR_MODE=evren`): görüntüyü EVREN'e gönderiyor; normalize `[x1, y1, x2, y2]` kutuları piksele çeviriyor; sınıf adlarını eşliyor; her görüntüyü süreç içinde bir kez çalıştırıyor. `UltralyticsDetector` ile ortak temel sınıfı (`_FileModelDetector`) paylaşıyor. Ayarlar: `EVREN_MODEL_API_KEY` (LLM anahtarından ayrı, `.env`'de), `EVREN_DETECTOR_MODEL`, `DETECTOR_IMGSZ` (varsayılan 1280).
- `scripts/export_detections.py`: 40 görüntünün tespitlerini bir kez alıp JSON'a yazıyor (14 sn). Demoda `DETECTOR_MODE=mock` + `DETECTOR_MOCK_PATH` ile kullanılınca değerlendirme anında başlıyor ve EVREN kesintilerinden etkilenmiyor. Sürüm adı dosyayı taşıyor (`file:detections_evren.json`), önbellek karışmıyor. Çıktı: `stage2/detections_evren.json`.
- **Canlı sonuç (img_000860):** 4 otomobil bulundu; dördü de kendi track'ine 0,1–0,2 m ile eşlendi. Organizatör örneğindeki kamyonu (727, 284) model 0,05 güvende bile görmüyor. Kamyonun track'i T0122 kaçırılmış temas olarak yakalandı ve hareketinden yüksek hesaplandı; kamyon tespit edilseydi seviye kritik olurdu.
- **40 gerçek görüntü (kurallar, raporsuz):** 260 tespit; 190'ı track'le eşleşti (ortanca 0,17 m, en fazla 14,1 m); 39 kayıt dışı (hepsi düşük); 16 kaçırılmış; modelin track'li araçlarda yakalama oranı ~%92. Görüntü başına ortanca 6 araç. Görüntü seviyeleri: 23 orta, 15 yüksek, 1 kritik, 1 düşük.
- **Performans bulgusu:** Doğrudan EVREN modunda ilk değerlendirme, tip geçmişi için önceki bütün karelerin tespitini EVREN'den istediğinden ~13 sn sürüyor; dosyadan okunan tespitlerle bu sorun kalkıyor.
- Testler: `EvrenDetector` (sahte istemci; normalize ve piksel kutular, istek parametreleri, önbellek, eksik dosya, ayarla kurulum) ve dışa aktarma; toplam 188.

### Gerçek veriyle uçtan uca doğrulama (26 Eylül akşam)
- **Kurulum:** Supabase'te stage2 (40 görüntü, 226 track, 137 rapor), GLM'in ayrıştırdığı 138 iddia, ekibin EVREN modelinin tespitleri (dosyadan), GLM karar ve brief, VLM.
- **Çalışanlar:**
  - 40/40 görüntü hatasız; ortanca 8,9 sn, en fazla 45 sn; 39 brief'i GLM yazdı, 1'i otomatik özet (zaman aşımı).
  - API: yeni değerlendirme 15 sn, önbellek 2 sn, `GET` 9 adım, sohbet 37 sn (doğru araçlar), 500 yok.
  - Rapor ayrıştırma 137/137: koordinat, tip, tür ve hareket doğru. "Söylenti" (25) savunulabilir: "ihbar incelendi, doğrulanamadı", "dün gece… doğrulanmamış ihbar", "…yönünde ihbar alındı".
  - Eşleşme: tespitlerin %73'ü track'le eşleşti (ortanca 0,17 m); track'li araçlarda modelin yakalama oranı ~%92. En uzak eşleşme 14,1 m (img_006388, T0057; ikinci aday T0026 6,5 m, yoğun kare).
  - **R7 kapandı:** 12:35 "ağır araç, hareketleri olağan" raporunun saatinde noktanın 300 m içinde track yok (T0122 5,6 km uzakta); rapor yanıltıcı, sistem "çelişkili" diyor.
- **Bulgu (kritik) — rapor bağlama yanlış anda yapılıyor:**
  - Koordinatlı raporların neredeyse tamamı bir görüntüdeki aracın **çekim anındaki** konumuna işaret ediyor: 5 basamaklılar 0–1 m, 4 basamaklılar 2–30 m. Rapor saati çekimden 5–120 dk önce. Görev tanımındaki örnek de 12:40 raporunu 13:25'teki tespitle karşılaştırıyor.
  - Kod iddiayı rapor saatinde o noktada olan araca bağlıyor. Sonuçlar: 5 "doğrulanmış dost"un 5'i yanlış araca bağlanmış (ilgisiz park halindeki araçların riski düştü). Dost bildirimleri o saatte noktada park eden başka araca bağlanıp "tip uyuşmuyor" çelişkisi üretiyor. Doğru dost bildirimleri ("…konumundan üsse doğru ilerleyen otomobil planlı ikmal aracıdır", "…gelişi önceden bildirilmiştir") "o saatte orada değildi" diye çelişkili sayılıyor.
  - Rapor etkileri 37 kez riski yükseltiyor; LLM de 24 kez +1 ekliyor. Görüntü seviyeleri: 10 kritik, 24 yüksek, 6 orta, 0 düşük.
- **Bulgu — hareket iddiası kontrol edilmiyor:** Dost bildirimlerindeki tuzaklar hareketle ayrışıyor: "üsse doğru ilerleyen" ama uzaklaşan (14:50, T0075), "üsse gelen" ama geçen (12:15, T0124). Kod yalnızca tip, renk ve yükü karşılaştırıyor. Tip tuzağı da var: "panelvan" denen T0156 otomobil.
- **Bulgu — brief'teki rapor gürültüsü:** 273 rapor bulgusunun 209'u doğrulanamaz; gün boyu geçerli "tatbikat" dostluk iddiası 81 kez, söylentiler 60 kez her görüntüde listeleniyor.
- Model sınıf dağılımı (260 kutu): 206 otomobil, 26 minibüs, 24 kamyon, 4 otobüs.

### B1: Arayüz için backend ek uçları (26 Eylül)
- `GET /zones`: üs ve 8 bölge merkezi, `zones.json` biçiminde (`base {name, lat, lon}`, `zones [{name, center [lat, lon]}]`). Bölge sınırı yok, uydurulmadı.
- `GET /images/{image_id}`: `image_meta.json` kaydı (`width_px`, `height_px`, `capture_time`, `corner_coordinates` `[lat, lon]`) + `center` (dört köşenin ortası) + `zone` (`/images` ile aynı en yakın merkez kuralı). Veri setinde yoksa 404.
- `GET /images/{image_id}/file`: `DATA_DIR/images`'tan dosya; `content-type` uzantıdan, `Cache-Control: public, max-age=86400`, `ETag`/`Last-Modified`. Görüntü veri setinde yoksa ya da dosyası eksikse ayrı mesajla 404. Dosya adı veri setindeki kimlikten kurulur.
- `contacts[].motion.route` noktalarına `time` ("HH:MM") eklendi; `lat`/`lon` aynı, alan isteğe bağlı (önbellekteki eski brief'lerde `null`). Rota çekim anına kadarki kayıtlı noktalardır; ileri kestirilen konum rotaya girmez (ADR-0001). Demo öncesi `recompute: true` ile ısıtılan kayıtlarda saatler dolu gelir.
- Yeni uçlar bellek içi depodan okur; veritabanı sorgusu eklenmedi.
- Testler: rota saatleri servis üzerinden (T0122 rotası 12:10–14:10, sonrası yok); üç uç `TestClient` ile, depo ve görüntü klasörü bağımlılık olarak değiştirilerek (spec'e istisna olarak eklendi). Toplam 194.
- Ortam: `backend/.venv` Anaconda'nın Python 3.12'siyle kuruldu (`/opt/anaconda3/bin/python3.12 -m venv .venv`); zsh'te conda PATH'te değil.

### Rapor bağlama çekim anına taşındı, saat ayrı kontrol (27 Eylül, R15/R7)
- **Değişiklik** (`pipelines/reports.py`, ADR-0002 notu): Koordinatlı iddia, **çekim anında** noktasına en yakın temasa bağlanıyor (`risk_rules.toml` `[reports] bind_now_m = 60`). Kaçırılmış ve kayıt dışı temaslar da aday. Saat ayrı bir özellik: `time_check` (ok, mismatch, unknown) bağlanan temasın rapor saatindeki track konumunu `match_m` (150 m) ile karşılaştırıyor. Rapor çekim anındaysa temasın şimdiki (gerekirse kestirilmiş) konumu kullanılıyor.
  - Dostluk iddiası: saat tutmuyor ya da bilinmiyorsa "doğrulanamaz", risk düşmüyor. Düşürme için konum + saat + belirtilen her özellik.
  - Gözlem: saat tutmasa da "tutarlı", risk yükselmiyor, gerekçeye not ("rapor saatindeki konumu uyuşmuyor").
  - Tehdit uyarısı: yükseltmeye devam, saat notuyla.
  - "Rapor saatinde orada kimse yok ama temas şu an orada → çelişkili" dalı kaldırıldı.
  - Kayıt dışı temasa bağlanan iddianın etkisi seviyeye uygulanamadığı için `none` yazılıyor ve gerekçede belirtiliyor; dostluk iddiası orada doğrulanamaz (kod incelemesi bulgusu).
- `ReportFinding.time_check` brief'te ve "Raporlar:" satırında ("tutarlı, saat tutmuyor"). Karar LLM'i girdide `time_check`'i görüyor; saati tutmayan rapor düşürme kanıtı olarak reddediliyor (prompt da güncellendi).
- `RunRecorder.get`: güncel şemaya uymayan eski kayıt artık 500 yerine "yok" (404) dönüyor; `latest_cached` aynı yolu kullanıyor (kod incelemesi bulgusu). Önceki bütün kayıtlarda `time_check` olmadığı için önbellek kendiliğinden yenileniyor.
- Sentetik üreteç gerçek verinin kurgusuna uyarlandı: rapor koordinatı odak aracın çekim anındaki konumu (5 ondalık). `location_contradiction` türü artık yalan sayılmadığı için yerine `friendly_time_mismatch` (saati tutmayan resmi dostluk → doğrulanamaz) geldi; dostluk raporları çekim anında.
- Testler: `test_report_evaluation.py` 22 senaryo (12:35 organizatör örneği, 10:20 park halindeki kamyon yerine gelen otomobile bağlama, kaçırılmış temasa bağlama, yakında temas yok, adım dışı çekim saati, kayıt dışı temasın etkisi). Eski "kendi track'iyle çelişiyor" testleri yeni anlamla yeniden yazıldı, sebebi docstring'de. Karar kuralı için 1 test. Toplam 195; ruff ve `mypy --strict app scripts` temiz. `tests/` altındaki 30 mypy hatası bu değişiklikten önce de vardı (test sahtelerinde protokol üyeleri eksik).
- **Ölçüm (gerçek veri, 40 görüntü, kurallar, LLM'siz, EVREN tespitleri dosyadan; gerçek etiket seti yok):**

  | | Önce | Sonra |
  |---|---|---|
  | Koordinatlı iddialardan çelişkili (72'de) | 35 | 18 |
  | Bütün bulgular: tutarlı / çelişkili / doğrulanamaz | 28 / 35 / 210 | 26 / 18 / 225 |
  | Rapor etkisi: yükseltir / düşürür | 35 / 5 | 16 / 0 |
  | Görüntü seviyesi: kritik / yüksek / orta / düşük | 1 / 32 / 7 / 0 | 1 / 25 / 13 / 1 |

  - Seviyesi değişen 11 görüntü: 9'u düştü (img_000267, img_000531, img_003189, img_008001, img_003880, img_007171, img_001147, img_007664 yüksek → orta; img_006444 yüksek → düşük), 2'si yükseldi (img_005788, img_004423 orta → yüksek: "5 kamyon" / "3 kamyon" raporu artık o noktadaki otomobile bağlanıyor, tip çelişkisi).
  - Kalan 18 çelişkinin hepsi tip uyuşmazlığı: rapor "kamyon" diyor, model aynı araca otomobil ya da minibüs diyor. Bir kısmı gerçek tuzak (img_003201, "panelvan" denen T0156 otomobil), bir kısmı modelin kamyon kaçırması olabilir (260 kutuda 24 kamyon).
  - Eski 5 "doğrulanmış dost"un hepsi yanlış araca bağlıydı; şimdi 0. Gerçek verideki resmi dostluk bildirimlerinin hepsinde araç rapor saatinde o noktada değil, bu yüzden hiçbiri riski düşürmüyor.
  - img_000860: 12:35 raporu T0122'ye bağlı, "tutarlı, saat tutmuyor"; seviye yüksek (model kamyonu görmüyor, T0122 kaçırılmış temas).

### Hareket ve sayı iddiaları kontrol ediliyor (27 Eylül, R15)
- **Hareket** (`pipelines/reports.py` `_behavior_check`, ADR-0002 notu): İddia, bağlanan temasın çekim anındaki hareketiyle karşılaştırılıyor. Duruyor → süren duraklama ya da "yerinde duruyor" eğilimi; yaklaşıyor / uzaklaşıyor → 30 dk eğilimi; transit → yaklaşmıyor; hareket halinde → duraklamada değil. Süre `time_reference`'tan okunuyor ("bir saatten uzun" 60 dk, "N dakikadır", "uzun süredir" `long_stop_minutes` = 30). Duraklama track'in başından beri sürüyorsa süre "doğrulanamadı". Uyuşmazlık kesin çelişki, riski yükseltiyor; dostluk iddiası için hareket de tutmalı. Kayıt dışı temasın hareketi doğrulanamıyor.
- **Sayı** (`_count_check`): 2 ve üstü sayı, noktanın 30 m içindeki bütün temaslarla (tipten bağımsız) karşılaştırılıyor; görülen < iddia × 0,5 ise uyuşmaz. Çelişki "olası" ve tek başına riski yükseltmiyor (kullanıcı kararı); `_apply_report_effects` artık yalnızca etkisi "raises" olan çelişkiyle yükseltiyor.
- `MotionFinding`'e `current_stop_minutes` ve `stop_open_ended` eklendi (brief ve sohbet aracı da görüyor). Yeni zorunlu alanlar yüzünden önceki kayıtlar önbellekten düşüyor.
- Eşikler `risk_rules.toml` `[reports]`: `long_stop_minutes`, `count_radius_m`, `count_ratio`.
- Sentetik üreteç: `behavior_contradiction` (üsse yakın park halindeki araç "üsse doğru ilerliyor") ve `count_contradiction` türleri; pipeline birebir yakalıyor.
- Testler: `test_report_evaluation.py` 34 senaryo (5 kamyon durdu ama yaklaşıyor, dost "üsse ilerliyor" ama uzaklaşıyor / hareket de tutunca doğrulanmış dost, transit ama yaklaşıyor, süre yeterli / kısa / kaydın başından beri, duraklama kaydı yok, kayıt dışı temas, sayı çok fazla / yakın / hareketle birlikte). Toplam 207; ruff ve `mypy --strict app scripts` temiz. Kod incelemesinde bulgu çıkmadı. "Yoğunluk" iddiaları bu turda yapılmadı (kullanıcı kararı).
- **Ölçüm (gerçek veri, 40 görüntü, kurallar, LLM'siz):**

  | | Önce | Sonra |
  |---|---|---|
  | Bulgular: tutarlı / çelişkili (yükseltir) / çelişkili (etkisiz) / doğrulanamaz | 26 / 16 / 2 / 225 | 22 / 22 / 2 / 223 |
  | Görüntüler: kritik / yüksek / orta / düşük | 1 / 25 / 13 / 1 | 1 / 28 / 11 / 0 |

  - Yeni yakalanan 6 tuzak, hepsinde araç çekim anında iddianın tersini yapıyor: 10:00 "transit geçiyor" T0147 (üsse yaklaşıyor, 6,6 m/s); 11:40 "7 kamyonun durduğu" T0135 (yaklaşıyor, çevrede 1 araç); 12:15 resmi dost "üsse gelen otomobil" T0124 (yaklaşmadan geçiyor); 13:50 "bölgeden uzaklaşıyor" ve 14:25 "1 kamyonun durduğu" T0078 (8,3 m/s ile yaklaşıyor); 14:50 resmi dost "üsse doğru ilerleyen" T0075 (uzaklaşıyor).
  - T0112 ("5 kamyon durdu") ve T0093 ("ağır araç bekliyor") zaten tip çelişkisiyle çelişkiliydi; gerekçelerine hareket uyuşmazlığı eklendi. Beklenmeyen yeni çelişki yok.
  - Seviyesi yükselen 3 görüntü: img_000733 ve img_001147 orta → yüksek, img_006444 düşük → yüksek (sahte dost bildirimi).

### Gateway uyumu: glm-5.3-flash ve takım limitleri (27 Eylül, görev tanımı s4-s11)
- `/validate stage2/gorev_tanimi.pdf against app/backend` bulguları #1, #4, #5 ve #8.
- `models.toml`: `glm_org` model adı `glm-5.3-flash` (gateway başka adı 400 ile reddeder), `reasoning_effort = "low"` (`thinking` gönderilmez, düşünme kapatılamaz). Bütün zincirlerde ilk sırada, VLM zinciri dahil (model görüntü okur, s7). Anahtar yoksa EVREN'e geçilir; davranış anahtar gelene kadar öncekiyle aynı.
- `config.py`: `glm_api_base` varsayılanı gateway URL'i; `data_dir` varsayılanı `../../stage2`. `.env.example` buna göre (detektör dosyası dahil).
- `llm/limits.py` `GatewayLimits`: süreç geneli `BoundedSemaphore(4)`, 60 sn'lik kayan pencerede 60 istek, token sayacı ve fiyat verilirse bütçe kesicisi (`BudgetExceededError` → zincirde sıradaki model). Zaman aşımında arka planda süren çağrılar da semaforu tuttuğu için eşzamanlılık 4'ü aşmıyor.
- `client.py` `LimitedProvider`: 429'da aynı modelde 2, 4, 8, 16 sn bekleyerek yeniden dener (beklerken yeri bırakır); SDK'nın kendi yeniden denemesi kapalı ki her deneme sayaca girsin. `finish_reason == "length"` olan cevap reddediliyor (sohbette de).
- Testler: `test_llm_limits.py` 13 senaryo (61. istek bekler, 5. eşzamanlı istek bekler, bütçe, 429 backoff ve yedeğe geçiş, istek gövdesi: model adı / `max_tokens` ≥ 1000 / `reasoning_effort` / `thinking` yok / base64 `image_url`, kesik cevap). Zincir sırasını sabitleyen 3 test güncellendi. Toplam 220; ruff ve mypy temiz.
- Açık: gateway fiyatı bilinmiyor, bu yüzden bütçe kesicisi fiyatlar `.env`'e girilene kadar devrede değil; gerçek harcama `/key/info`'da.

### Çelişen rapor seviyeyi değiştirmiyor (27 Eylül, görev tanımı s2, ADR-0002 notu)
- Görev tanımı: "çelişki varsa raporu değil tespitinizi esas alın". Önceden çelişki "olası yanıltma" sayılıp temas en az "yüksek"e çekiliyordu ve LLM düşüremiyordu (kullanıcı kararıyla kaldırıldı).
- `pipelines/reports.py`: çelişen iddianın etkisi her zaman `none`, gerekçenin sonunda "tespit esas alındı". `service.py` `_apply_report_effects`: çelişki gerekçeye not düşülür, seviye değişmez; aynı temasa ait dostluk iddiasının riski düşürmesini engeller. Tutarlı tehdit uyarısı yine +1.
- Prompt'lar (`brief.md`, `chat.md`) ve belgeler: "kasıtlı yanıltma" yerine "hatalı veya ilgisiz"; LLM'e çelişkinin tek başına seviye değiştirme gerekçesi olmadığı söyleniyor.
- Sentetik üreteçte `raises_high` etkisi kaldırıldı; 8 test yeni kurala göre güncellendi. Toplam 220; ruff ve mypy temiz.
- **Ölçüm (gerçek veri, 40 görüntü, kurallar, LLM'siz):**

  | | Önce | Sonra |
  |---|---|---|
  | Görüntüler: kritik / yüksek / orta / düşük | 1 / 28 / 11 / 0 | 1 / 15 / 23 / 1 |
  | Temaslar: kritik / yüksek / orta / düşük | 1 / 59 / 93 / 92 | 1 / 43 / 105 / 96 |
  | Çelişkili bulgu | 24 | 24 |

  - 16 temas "yüksek"ten düştü (12'si orta, 4'ü düşük), 13 görüntünün seviyesi düştü. Çelişkiler aynı sayıda yakalanıyor, yalnızca seviyeye etkisi yok.
  - Dikkat: hareket tuzaklarındaki yaklaşan araçlar (T0078 8,3 m/s, T0112) de ortaya indi, çünkü üsse 3 km'den uzaklar ve temel tablo onları orta veriyor. Bunları yükseltmek artık LLM'in (+1, gerekçeli) ya da temel tablonun işi.

### Hız ve yön kaydın tamamından (27 Eylül, görev tanımı s3, validate bulgusu #13)
- `risk_rules.toml` `recent_window_minutes` 10 → 30: hız ve yön eğilimle aynı pencereden. Seviye hesabı değişmedi (eğilim zaten 30 dk'lıktı); gerçek veride 40 görüntünün seviyesi ve 24 çelişki aynı.
- LLM girdisine `avg_speed_mps` (2 saat), `distance_to_base_30min_ago_km` ve `heading_deg` eklendi; prompt'a alanların anlamı ve "tek andan yorumlama" yazıldı. Brief metni: "üsse uzaklık 30 dk önce X km, şimdi Y km, son 30 dk A m/s, 2 saatlik ortalama B m/s". Sohbet aracı da ortalama hızı döndürüyor.
- T0122: 30 dk'lık pencerenin 20 dk'sı 13:15 duraklamasının sonu olduğu için hız 6,4 → 2,1 m/s; hemen yeniden hareket etmiş bir aracın anlık hızı artık daha düşük görünüyor, duraklamalar listesi bunu açıklıyor.
- Testler: T0122 testi güncellendi, LLM girdisi ve brief metni için 1 yeni test. Toplam 221; ruff ve mypy temiz.

### Görüntüler Supabase Storage'a taşınıyor
- Migration `09_images_bucket`: özel `drone-images` bucket'ı (jpeg/png, 20 MB sınır) oluşturuldu.
- `images.file_path` biçimi `drone-images/<id>.jpg` oldu (`load-data` da bunu yazıyor); `fetch_package` yolu `ImageMeta.file_path`'e taşıyor.
- `app/storage.py`: Storage REST istemcisi (`service_role`). Tespit (EVREN/YOLO) ve VLM, görüntü `DATA_DIR/images`'ta yoksa Storage'dan indirip oraya yazıyor; yerel dosya varsa Storage'a gidilmiyor.
- `upload-images [klasör]`: dosyaları bucket'a yükleyip `file_path`'i günceller. 40 görüntü Dashboard'dan bucket'a yüklendi (boyutlar paketle aynı); `images.file_path` 40 kayıtta `drone-images/<id>.jpg` yapıldı.

### USE_INFERENCE ve birebir eşleşme (27 Eylül)
- `.env`'de `USE_INFERENCE`: `DEMO` tespitleri modelin kayıtlı çıktısından (`detections_all.csv`), `REAL` görüntüyü EVREN'deki modele göndererek alır. Tanımlıysa `DETECTOR_MODE`'un yerine geçer; tanımsızsa eski davranış.
- CSV Supabase'te tablo olarak duruyor (migration `10_model_detections`, 2.889 satır, 40 görüntü): görüntü bazında sorgulanıyor ve `images`'a bağlı, bucket'a göre daha uygun. Yükleme: `python -m scripts.load_detections [csv]` (kaynak adına göre baştan yazar). `DATA_SOURCE=package` iken DEMO CSV'yi `DETECTIONS_CSV_PATH`'ten okur.
- Eşleşme: açgözlü en-yakın yerine görüntü başına birebir, toplam mesafeyi en aza indiren atama (Hungarian, `scipy`). Adaylar çekim anında görüntünün alanındaki track noktaları; maliyet = mesafe + 0,01 × (1 − skor); mesafe düzlem yaklaşımı (111.320 m/derece). Güçlü ve zayıf tespitler artık tek atamada; eşleşmeyen zayıf tespit yine düşer.
- Eşikler: `min_confidence` 0,25 → 0,20 (modelden istenen alt sınır da 0,20), `matching.threshold_m` 15 → 5 m.
- Gerçek veride: 206 track noktasının 191'i eşleşiyor, ortanca 0,13 m, en uzak 1,85 m (`tests/test_matching.py`, paket yerelde varsa). Tam pipeline da (VLM'siz) 191/206 veriyor.
- img_000860'taki kamyonun CSV'deki skoru 0,037: eşiğin altında kaldığı için T0122 kaçırılmış temas, görüntü kritik yerine yüksek (R5'le aynı).
- Testler: 12 yeni (eşleşme, USE_INFERENCE, CSV okuma); eşik değişen 5 test güncellendi. Toplam 274; ruff ve mypy temiz.

### Tespit kaynağı yalnızca USE_INFERENCE (27 Eylül)
- `DETECTOR_MODE` ve onunla gelen `mock` (sahte tespit, `DETECTOR_MOCK_PATH`, yerleşik img_000860 örneği) ile `model` (yerel Ultralytics YOLO, `DETECTOR_WEIGHTS_PATH`, `[model]` ek paketi) kaldırıldı. Tespit kaynağı tek ayar: `USE_INFERENCE=DEMO` (varsayılan, kayıtlı çıktı) ya da `REAL` (EVREN).
- `MockDetector` → `RecordedDetector` (sürüm zorunlu, yerleşik örnek yok); `load_mock_detections` / `dump_mock_detections` → `load_detections_json` / `dump_detections_json`. JSON biçimi yalnızca `run_eval_set --detections`, `export_detections` ve sentetik üreteçte kullanılıyor.
- Testler: YOLO testleri çıkarıldı; sınıf eşlemesi (Türkçe adlar dahil) ve önceki karesi eksik görüntü EVREN detektörüyle sınanıyor.

### VLM zincirinden GLM çıkarıldı (27 Eylül)
- `models.toml` `vision`: `qwen3-vl-30b → gemma-4-31b → deepseek-v4.1-flash → Sonnet 5`. glm-5.3-flash görüntülü istekte istenen JSON yerine şemanın kendisini döndürüyordu; her VLM çağrısı önce onu deneyip hata alıyor, 10-15 sn kaybediyordu. Claude anahtarı şu an yok; Sonnet anahtar gelene kadar atlanır.
- VLM artık track'le eşleşmiş zayıf kutuyu düşüremiyor. Önceden "araç değil" cevabı kutuyu düşürüp track'i kaçırılmış temasa çeviriyordu; görülen 3 vakanın 3'ü de gerçek araçtı (ağaç/gölge altında, track < 1 m). Şimdi: araç derse kesinlik "olası", demezse kutu kalır, kesinlik "zayıf", brief'te "araç görsel olarak seçilemedi (hareket kaydı var)". Olay alanı `visually_rejected` → `visually_unconfirmed`.
- Karşılaştırma seti hazır (ağ kısıtı yüzünden çalıştırılmadı): `stage2/vlm_bench/` (32 kırpma, `bench.py`).

### Açık konular
- `app/` git repo'su oldu ve GitHub'a (private) push edildi.
- Gerçek veride kontrol edilecek sorular aynı: 12:35 raporu, `capture_time` hizası, veri boyutu.
- Embedding modeli ve boyutu hâlâ belirsiz.
- EVREN anahtarı çalışıyor; `report_claims` 6 iddiayla dolu. Organizatörlerin GLM anahtarı yarın gelecek, o zaman `GLM_API_KEY`/`GLM_API_BASE` ve model adı doğrulanacak.

### Kol B eşleşmeden ayrıldı (27 Eylül, pipeline iyileştirmesi madde 1)
- `EvaluationService.track_branch(image)` → `TrackBranch(positions, motions)`: aday track'ler (çekim anında karenin içinde ya da kareye eşleşme eşiği + 1 m kadar yakın) ve her birinin hareket özeti. Görev tanımı s3: her track kendi görüntüsünün çekim anında biter, tespiti beklemeye gerek yok.
- Değerlendirmede track kolu tespitle aynı anda çalışıyor (thread); eşleşme ve temas oluşturma hazır sonucu kullanıyor, `_motion` temas başına ayrıca çağrılmıyor. Tip geçmişi de aynı aday tanımını kullanıyor.
- Ölçüm: 40 gerçek görüntünün kurallarla, LLM'siz bütün SSE olayları (360 olay, veriler dahil) önce ve sonra byte düzeyinde aynı.
- Testler: `tests/test_track_branch.py` (aday tanımı, hareketin yeniden okunmaması, tespitle paralellik); toplam 277.

### Görsel doğrulama tek paralel dalgada (27 Eylül, pipeline iyileştirmesi madde 3)
- Önceden zayıf kutular paralel soruluyordu, ama renk/yük iddialarının kutuları rapor değerlendirmesi sırasında tek tek ve sırayla VLM'e gidiyordu (her biri ~10 sn).
- `reports.visual_track_ids(...)`: renk ya da yük belirten iddiaların bağlanacağı track'li temaslar; `evaluate_claims` ile aynı bağlama kuralını (`_bind`) kullanıyor. Servis (`_inspect_all`) eşleşmeden hemen sonra bu kutuları zayıf kutularla birlikte tek bir paralel dalgada (en fazla 4) soruyor; rapor değerlendirmesi yalnızca sonucu okuyor.
- Ölçüm: 40 gerçek görüntü, kurallar + belirlenimci sahte VLM: 360 olayın hepsi ve 17 VLM çağrısının kutuları önce ve sonra aynı.
- Testler: renk iddiası ile zayıf kutunun aynı dalgada aynı anda sorulması, bağlanmayan ya da ilgisiz iddianın VLM'e gitmemesi; toplam 279.

### Değerlendirme tipli aşamalara bölündü (27 Eylül, refactor)
- `EvaluationService.evaluate` (~260 satırlık tek üreteç) ince bir orkestratör oldu: aşamaları sırayla çağırıp her birinden sonra SSE adımını yayıyor. Kol A (`detect`) ve Kol B (`track_branch`) yine `concurrent.futures` ile paralel.
- `app/agent/stages.py`: her aşama saf ya da yan etkisi imzasında açık (`repo`, `detector`, `verifier`, `router`) bir fonksiyon; girdi/çıktılar dondurulmuş dataclass: `ImageContext`, `Detections`, `TrackBranch`, `Matches`, `Contacts`, `ClaimEvaluations`, `RiskResult`, `FinalDecision` → `Brief`.
- `app/agent/events.py`: adımların özet ve `data` yükleri (frontend sözleşmesi) tek yerde. `app/agent/brief_text.py`: brief ve özet metinleri.
- Ölçüm: 40 gerçek görüntünün bütün olayları ve brief'leri önce ve sonra byte düzeyinde aynı; üç koşuda: kurallar, kurallar + belirlenimci sahte VLM, sahte VLM + kabul/red üreten sahte LLM.
- Testler: `tests/test_stages.py` (eşleşme; rapor etkilerinin bağlanması, ADR-0002); toplam 285.

### Storage indirmesinde yarış düzeltildi (27 Eylül, uçtan uca test)
- Uçtan uca test: Supabase'ten `img_003201` (14:55, Güney Kapısı Yaklaşımı), boş bir `DATA_DIR` ile `POST /evaluations` üzerinden çalıştırıldı. Görüntü yerelde yokken değerlendirme 3. adımdan sonra `FileNotFoundError` ile düşüyordu. Sebep: görsel doğrulamanın paralel işçileri dosyayı aynı anda indirip aynı `.part` dosyasına yazıyordu; ilk işçi dosyayı taşıyınca diğerlerinin `replace` çağrısı patlıyordu.
- `storage.resolve_image_file`: hedef dosya başına bir kilit. Bekleyen çağrı kilidi alınca dosyayı yeniden kontrol ediyor, bu yüzden indirme tek sefer yapılıyor.
- Ölçüm: aynı temiz başlangıçla 8 adımın hepsi ve brief geliyor (~23 sn, GLM + EVREN VLM).
- Testler: `test_concurrent_callers_share_one_download` (4 eşzamanlı çağrı, tek istek, artık `.part` kalmıyor); 279 test geçiyor.

### Görüntü ucu dosyayı bucket'tan sunuyor (27 Eylül)
- `GET /images/{id}/file` yalnızca `DATA_DIR/images` klasörüne bakıyordu. Yerelde dosya yoksa 404 dönüyor, ön yüzde görüntü analiz yapılana kadar görünmüyordu.
- Supabase modunda uç artık `images.file_path` ile `drone-images` bucket'ından okuyup sunuyor, yerel klasöre hiç bakmıyor. Ağsız demoda (`DATA_SOURCE=package`) yerel klasör kullanılmaya devam ediyor (`app.state.image_storage = None`).
- `SupabaseStorage.fetch`: içerik ve içerik tipi. Supabase olmayan nesne için 400 döndürüyor, asıl kod gövdede (`"statusCode": "404"`); `StorageError.not_found` bunu ayırıyor. Nesne yoksa 404, Storage'a ulaşılamazsa 502.
- Ölçüm: boş görüntü klasörüyle üç görüntü 200 `image/jpeg` döndü (0,5–1,4 sn). `img_000860` `stage2` kopyasıyla byte düzeyinde aynı. Yerel klasöre bir şey yazılmadı.
- Testler: `test_data_api.py` içinde bucket'tan sunma (yerel dosya varken bile), olmayan nesne → 404, ulaşılamayan Storage → 502.

### Karar: aynı olgu iki kez sayılmıyor, kayıt dışı temas nedeni (27 Eylül)
- Sorun: canlı testte `img_003201` aynı girdiyle bir koşuda ORTA, bir koşuda YÜKSEK çıkıyordu. T0213 ve T0156'nın ORTA'sı zaten yaklaşmadan geliyordu; LLM "yaklaşma" ile yükseltiyor, kod nedeni doğru bulup kabul ediyordu.
- `risk.base_level` seviyeyi belirleyen satırın nedenini de döndürüyor (`LevelDecision.basis`); temas bunu `level_basis` olarak taşıyor. Rapor etkisiyle yükselen temasa `tehdit_uyarisi` ekleniyor. `level_basis`'teki bir nedenle yükseltme reddediliyor ("zaten sayıldı"). Kuralların görmediği bir birleşim (ör. yaklaşan araç + kaçırılmış temas) hâlâ yükseltebilir.
- Yeni neden `kayit_disi`: temasın `kind`'ı "unregistered" olmalı. Seviye yükseltme gerekçesi olamaz (ADR-0003); üssün `unregistered_alert_m` yakınındaki kayıt dışı temas için "dikkat gerekmiyor" reddediliyor, uzaktaki park halindeki araç için geçerli.
- Prompt (`prompts/brief.md`): `level_basis` ve `kayit_disi` kuralları; özet bölümü yeniden yazıldı (araç tip ve davranışla tarif edilir, ikinci cümle bağlam verir, niyet yorumu ve olmayanı sıralamak yasak, kod filtresinden geçen iyi/kötü örnekler).
- Ölçüm: `img_003201` üç kez canlı: üçü de ORTA, hiç yükseltme önerisi yok; üç özet de filtreden geçti.
- Testler: `level_basis` ile yükseltmenin reddi, tehdit uyarısının ikinci kez yükseltememesi, `kayit_disi` doğrulaması, yakın/uzak kayıt dışı temas; mevcut yükseltme testleri kuralın saymadığı nedene çevrildi. 313 test geçiyor.

### Karar LLM'inin girdisi Türkçe olgu satırları (27 Eylül, madde 7)
- Sorun: `build_input` ham JSON veriyordu (İngilizce alan adları, "approaching"/"high", noktalı ondalık, `level_reasons` tekrarı). Uçtan uca testte LLM "son 30 dakikada yaklaştı" dedi (yaklaşma 60–30 dk önceydi), İngilizce terim sızdırdı.
- `decision.contact_facts`: temas başına sabit anahtarlı Türkçe satırlar (`tur`, `tip`, `kesinlik`, `uzaklik`, `hareket`, `duraklamalar`, `yakin_duraklama`, `cevrede_dolasma`, `seviye`, varsa `dost`, `gorsel`, `notlar`, `raporlar`). Sayılar `formatting` ile virgüllü; yön sekiz yön adıyla; eşik karşılaştırmasını ("aşıyor"/"altında") ve dolaşmayı kod yapıyor. Rapor iddiaları karar, saat kontrolü ve gerekçeyle; bağlanmayanlar ayrı bölümde. Bölge adı ve geçilen bölgeler girdiden çıktı (hiçbir neden kullanmıyor, özette yasak). Rapor gerekçesindeki tip adları (ör. "truck") yalnızca LLM girdisinde Türkçeleşiyor; brief ve SSE aynen.
- `FactKey` (eski `FactField`): `dayanak`'ın gösterebileceği anahtarlar, girdideki anahtarlarla aynı liste. Neden doğrulaması `ContactFinding`'e bakmaya devam ediyor. Prompt yeni anahtarlara göre güncellendi ("sayıları yeniden hesaplama, zaman penceresini değiştirme").
- Ölçüm: 40 gerçek görüntü LLM'siz (stage2, `detections_evren.json`): 360 SSE olayı önce ve sonra byte düzeyinde aynı. LLM girdisi 319.209 → 148.792 karakter (%53 az; kelime 30.073 → 21.850), 40 girdide İngilizce kod değeri ve noktalı ondalık yok. Sistem prompt'u 7,5K → 9,5K karakter büyüdü (anahtar açıklamaları).
- Canlı (glm-5.3-flash, VLM kapalı, img_000860/006388/006444): seviyeler ve kabul edilen seviye değişiklikleri önce ve sonra aynı; `dayanak`'ta yeni anahtarlar doğru kullanıldı; img_006444 önce 45 sn zaman aşımına düşmüştü, sonra cevap verdi. Özetin sayı/kimlik yüzünden atılması rastgele: sonra 3'te 2 atıldı, aynı iki görüntünün tekrarında ikisi de geçti. Atılan özetin metni saklanmıyor.
- Testler: girdide İngilizce kod ve noktalı ondalık yok; T0122 referans örneği, süren duraklama ve kayıt dışı temasın beklenen satırları; girdideki her anahtar `FactKey`'de; yeni anahtarlı `dayanak` kabul, eski anahtar şemada red; rapor gerekçesinde tip adı; track'siz raporların başlığı. 322 test geçiyor.
- Kod incelemesi: track'i olmayan iddialar "hiçbir temasa bağlanmayan" diye veriliyordu; oysa kayıt dışı temasa bağlanmış olabilirler (ADR-0003). Başlık "Track'e bağlanmayan raporlar (bölge düzeyinde ya da kayıt dışı bir temasla ilgili)" oldu.

### Rapor doğrulamada tespit modelinin görmediği araca görsel bakış (27 Eylül)
- Sorun: rapora bağlanan araç kaçırılmış temassa (track var, tespit yok) kanıt dosyasında tip "tespit edilemedi" oluyor, tip/renk/yük iddiası doğrulanamıyordu.
- `ReportVerifier._look`: bağlanan araç tespit edilmemişse ve iddia tip, renk ya da yük söylüyorsa `evidence.track_crop` temasın çekim anındaki konumunu halkayla (10 m), son 30 dk'lık yolunu çizgiyle işaretleyip kırpar. Organizatör gateway'indeki glm-5.3-flash (`look` görevi, yalnızca `glm_org`) raporu görmeden bakar (`prompts/vision_track.md`). Araç görüldüyse, tip seçildiyse ve eminlik düşük değilse sonuç kanıt dosyasına `gorsel_inceleme` olarak girer; aksi hâlde rapor eskisi gibi doğrulanır.
- GLM görüntülü istekte cevabı şemanın biçimine sarıyordu (`{"description", "properties": {...}}`); VLM zincirinden bu yüzden çıkarılmıştı. `client.parse_schema_json` alanlar `properties` içindeyse oradan okuyor.
- Politika: görsel incelemenin kuralı yalnızca o çağrının kullanıcı mesajına eklenir (`prompts/look_policy.md`; `policy.md` değişseydi bütün rapor önbelleği geçersiz olurdu). Tek dayanağı görsel bakış olan tip çelişkisi en fazla "kısmen"; kesinlik en fazla "olası"; görsel bakışla görülen tip riski düşüren bir raporu "tutarlı" yapamaz (`combine(looked=True)` → doğrulanamaz).
- Ölçüm (stage2, `stage2_out/detections.csv`): bu yola giren 2 koordinatlı rapor var (125 → T0122, halkada araç yok; 132 → T0073, altın cevap kamyon). EVREN VLM'leri uydurdu (qwen yük yığınına "panelvan, yüksek"; kamyona "otomobil"). GLM 14 koşuda hiç yanlış tip vermedi: 125'te "araç yok / belirsiz", 132'de 1 kez "kamyon, düşük", kalanlarda "belirsiz, düşük". Eminlik düşük olduğu için ikisi de kullanılmıyor; gerçek veride sonuç değişmiyor. Çağrı 2–6 sn.
- Kırpma denemesi (GLM, her varyant 2 rapor × 3 koşu): halkalı 40 m, işaretsiz ±64 px (~7 m), işaretsiz ±128 px (~15 m), artı işaretli ±128 px. Kırpmanın kendisi sonucu değiştirmedi. Asıl hata istemdeydi: "üç tekerlekli araç sayılmaz" cümlesi, veri setinin truck dediği yük kasalı üç tekerlekliyi (T0122, organizatör örneği) dışarıda bırakıyordu. Düzeltmeden sonra ±128 px işaretsiz kırpmada 125 → 3/3 "kamyon", 132 → 3/3 "panelvan" (altın cevap kamyon). GLM her cevapta eminliği "düşük" veriyor; eminlik süzgeci bu yüzden bütün bakışları eliyor.
- T0073 (132) aslında görsel değil eşleşme sorunu: track noktasına 45 px (~5 m) uzakta 0,43 güvenli truck tespiti var, 5 m eşiğini kıl payı geçiyor. Eğik görüntüde doğrusal dönüşüm noktayı aracın birkaç metre yanına düşürüyor.
- Uygulandı: kırpıntı işaretsiz ±128 px, nokta ortada (`evidence.CROP_HALF_PX`); istem "karenin ortası"na göre.
- Uygulandı: tespiti olmayan track'in 8 m içindeki eşleşmemiş tespit kanıt dosyasında `yakindaki_eslesmemis_tespit` ("olası aynı araç"); LLM'e kuralı `prompts/nearby_policy.md`; kesinlik en fazla "olası"; varken GLM'e sorulmaz (tespit esas alınır). Sınıflar arası yinelenen kutular (IoU > 0,5) tek sayılır, başka bir track'e eşleşmiş tespitin yinelenen kutusu aday değildir. Eşleşme eşiği (5 m) risk motorunu da etkilediği için gevşetilmedi.
- 132 düzeltildi: 5 m ötedeki truck 0,43 aslında T0081'e eşleşmiş; T0073'ün yanındaki car/van 0,12 kutuları o kamyonun yinelenmesi. Rapor noktası (4 ondalık) T0073'e bağlanıyor, altın cevaptaki kamyon T0081. Gerçek veride (`detections.csv`) 9 tespitsiz track'in hiçbirinin yakınında aday tespit yok; `detections_all.csv`'de tespitsiz track kalmıyor. Yani yakındaki tespit kuralı bu veride tetiklenmiyor.
- Uçtan uca (GLM, 3 koşu): 125 → GLM 3/3 "kamyon, düşük" (kullanılmıyor), karar 3/3 çelişkili (altın cevapla aynı, hareket). 132 → GLM 2/3 "panelvan, orta" (T0073'ün kendi aracı; ağaç gölgesinde), karar o koşularda "kısmen" (arayüzde tutarlı/olası), bakış kullanılmayan koşuda "tutarlı". Altın cevap tutarlı.
- **Karar: görsel bakış ve yakındaki tespit yalnızca bilgi notu.** Kanıt olarak kullanıldığında gerçek veride hiçbir rapor iyileşmedi, 132 kötüleşti (3 koşunun 2'sinde "tutarlı" yerine "kısmen"). Artık ikisi de doğrulama LLM'inin girdisine ve karara girmiyor; rapor bulgusunun gerekçesine not düşüyor ("tespit modeli görmedi; görsel incelemede kamyon (eminlik düşük, karara girmedi)"). `look_policy.md`, `nearby_policy.md` ve `combine`'ın zayıf tip kuralı kaldırıldı. Aç/kapa: `REPORT_LOOK` (varsayılan açık).
- Ölçüm: 155 raporun LLM girdisi HEAD ile birebir aynı (rapor önbelleği geçerli). Gerçek veride not düşen raporlar: 125 "kamyon, eminlik düşük", 132 "panelvan, eminlik orta".
- Testler: bakış yalnızca not (karar ve kesinlik değişmez, LLM girdisinde yok), tip görülmezse not yok, `REPORT_LOOK=false`, yakındaki tespit notu ve o varken bakış yapılmaması, yinelenen kutular, sarılmış JSON. 324 test geçiyor.
