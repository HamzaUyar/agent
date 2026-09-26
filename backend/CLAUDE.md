# CLAUDE.md — Roketsan Hackathon · Aşama 2 Backend

## Proje özeti
Level Up AI | ROKETSAN Yapay Zekâ Hackathonu (25–27 Eylül 2026, Ankara).

- **Aşama 1 (Kaggle, ekip arkadaşları):** Drone görüntülerinde araç tespiti. Sınıflar: `car`, `van`, `truck`, `bus`. Alanı 200 px² ve üzeri olan araçlar etiketli. Metrik: mAP@0.5.
- **Aşama 2 (bu repo):** Senaryo bir üssü (Merkez Üs) korumak. Çevredeki 8 bölge drone ile izleniyor. Agent'a verilen bir görüntüdeki araçların üs için risk oluşturup oluşturmadığına karar veren ve bunu gerekçelendiren kısa bir **brief** üreten bir LLM agent geliştiriyoruz.

Değerlendirme:
- **Mentörler:** kod kalitesi ve mimari.
- **Jüri:** iş değeri, çalışan ürün, ürün ve UX, sunum ve demo.
- **Canlı demo:** Agent en az 1–2 görüntü üzerinde gerçekten çalışmalı.

## Veri (2. aşamada dağıtılacak → `data/`)
| Dosya | İçerik |
|---|---|
| `images/` | 8 bölgeden 40 drone görüntüsü |
| `image_meta.json` | `image_id → width_px, height_px, capture_time ("HH:MM"), corner_coordinates {top_left, top_right, bottom_left, bottom_right: [lat, lon]}` |
| `zones.json` | `base {name, lat, lon}`, `zones [{name, center [lat, lon]}]`. Sadece bölge merkezi var, sınır çokgeni yok. |
| `tracks.csv` | `track_id, time, lat, lon`. Her track bir aracın son 2 saati, 5 dakikalık adımlarla. **Araç tipi yok.** |
| `field_reports.json` | `time, source (official / third_party), text` (serbest metin, Türkçe karakter kullanılmamış) |

- Track'ler ve raporlar tek bir havuz. Hangi görüntüye ait oldukları verilmiyor. Bağlantı **çekim saati ve koordinatlarla** kuruluyor.
- **Raporların hepsi doğru değil.** Bazıları doğru, bazıları hatalı veya ilgisiz (görev tanımı s3). Raporları kendi tespitimiz ve hareket verisiyle karşılaştırıyoruz; çelişkide rapor değil tespit esas alınır (s2), çelişki seviyeyi değiştirmez (ADR-0002).

## Pipeline (üç kol + birleştirme)
```
KOL A (görüntü)            KOL B (tracks)                 KOL C (raporlar, önceden)
detect() → piksel          track_risk(track_id, at_time)  LLM parse → report_claims
  → geo: lat/lon, bölge      hız, yön, rota, duraklama,
                             üsse mesafe trendi
        └──────► matching: capture_time'da birebir atama (eşik 5 m)   ◄──┘
                    → risk: hareket riski × tip katsayısı + rapor değerlendirmesi
                    → agent (LLM): gerekçeli brief
```
- **Piksel → koordinat:** doğrusal oran.
  - `lon = TL_lon + (cx/W)·(TR_lon − TL_lon)`
  - `lat = TL_lat − (cy/H)·(TL_lat − BL_lat)`
  - Kare kuzeye hizalı kabul ediliyor: üst kenar kuzey, sol kenar batı.
- **Eşleme:** adaylar `time == capture_time` olan ve görüntünün alanında kalan track noktaları. Görüntü başına birebir, toplam mesafeyi en aza indiren atama (Hungarian); eşik 5 m, skor eşiği 0,20, maliyet = mesafe + 0,01 × (1 − skor). Gerçek veride 206 noktanın 191'i eşleşir (ortanca 0,13 m). `capture_time` 5 dakikanın katı değilse track konumu ileri kestirilir.
- **Eşleşmeyen durumlar da sinyaldir:**
  - tespit var, track yok → kayıt dışı araç
  - track var, tespit yok → tipi bilinmiyor
- **Rapor kontrolü:** İddia, **çekim anında** noktasına en yakın temasa bağlanır (≤ 60 m). Saat ayrı bir kontroldür: temasın rapor saatindeki track konumu noktaya ≤ 150 m ise tutar. Saat tutmayan dostluk iddiası riski düşüremez (ADR-0002 notu).
- **Referans örnek** (organizatörlerin demosu):
  - `img_000860`, 14:10, Doğu Yolu
  - truck, kutu (727, 284, 58, 34), merkez piksel (756, 301) → 39.92531, 32.87183
  - eşleşen track T0122 (<1 m); ikinci en yakın T0032 (41 m)
  - üsse mesafe 1,6 km, üsse yaklaşıyor
  - Bu değerler testlerde kullanılmalı.

## İlkeler
- **Hesaplar kodla, akıl yürütme LLM ile.** Koordinat, mesafe, hız ve eşleme deterministik Python koduyla yapılır; LLM sayı hesaplamaz; bunun sebebi doğruluk ve tekrarlanabilirlik.
- **Model seçimi görev bazlı.** Görev → model zinciri `app/llm/models.toml` dosyasında. Metin görevlerinin zinciri organizatörlerin gateway'indeki `glm-5.3-flash` ile başlar (görev tanımı s4); EVREN ve Claude yedektir. VLM zinciri EVREN `qwen3-vl-30b` ile başlar (GLM görüntülü istekte şemaya uymuyor). Zincir sırayla denenir (kimlik bilgisi yoksa ya da bütçe dolduysa atla, hata veya şemaya uymayan cevapta sıradakine geç). Gateway'e takım limitleri uygulanır (`app/llm/limits.py`): 4 eşzamanlı istek, 60 istek/dk, 15 USD; 429'da aynı modelde üstel bekleme.
  - rapor parse etme: hızlı LLM
  - renk ve yük çıkarımı: VLM
  - karar ve brief: en güçlü akıl yürütme modeli
- **Tespit modeli arayüz arkasında.** `detect(image) → [Detection]` şeklinde tanımlı. `USE_INFERENCE=DEMO` modelin kayıtlı çıktısı (Supabase `model_detections`; paket modunda `DETECTIONS_CSV_PATH`), `REAL` EVREN'deki model (`EVREN_MODEL_API_KEY`). Başka tespit kaynağı yok.
- **Veritabanına sadece backend yazar** (`service_role` anahtarıyla). Pipeline'lar SQL bilmez; sorgular `app/db/repositories.py` içindedir.
- **İzlenebilirlik.** Her agent adımı `agent_steps` tablosuna yazılır; brief kaynaklarını belirtir.

## Tech stack
Python 3.11+ (ortam: `.venv`, Python 3.14, pip), FastAPI (SSE), Pydantic v2, psycopg 3 (PostGIS sorguları SQL ile), anthropic SDK, openai SDK (yalnızca GLM için), pytest, ruff, mypy strict. Planlanan ama henüz kullanılmayan: LangGraph. Frontend: Next.js + Tailwind + shadcn/ui + MapLibre/deck.gl.

## Veritabanı (Supabase)
- Organizasyon **Roketsan**, proje **Roketsan Project** (`akduinmhomalciorwckz`, ap-south-1, Postgres 17).
- Eklentiler `extensions` şemasında: `postgis`, `vector`. Konumlar `geography(..., 4326)` tipinde. 16 tablonun hepsinde RLS açık, policy yok (backend `service_role` kullanıyor).
- Tablolar:
  - **Kaynak:** `bases`, `zones`, `images`, `tracks`, `track_points`, `field_reports`
  - **Zenginleştirilmiş:** `report_claims`, `track_segments`
  - **Model çıktısı:** `model_detections` (USE_INFERENCE=DEMO; yükleme `python -m scripts.load_detections`)
  - **Analiz:** `analysis_runs`, `detections`, `track_matches`, `motion_analyses`, `report_evaluations`, `risk_assessments`, `agent_steps`
- Migration'lar: `01_extensions_and_enums` … `10_model_detections` (`supabase/migrations/`).
- **Storage:** görüntü dosyaları özel `drone-images` bucket'ında; `images.file_path` = `drone-images/<id>.jpg`. Yerelde (`DATA_DIR/images`) olmayan görüntü, tespit ve VLM ilk ihtiyaç duyduğunda `service_role` ile indirilip oraya yazılır (`app/storage.py`). Arayüzün görüntü ucu (`GET /images/{id}/file`) Supabase modunda dosyayı yerel klasöre bakmadan doğrudan bucket'tan sunar; yalnızca ağsız demoda (`DATA_SOURCE=package`) yerelden okur. Yükleme: `upload-images [klasör]`.

## Dizin yapısı
```
app/
  main.py            FastAPI uygulaması
  data_package.py    veri paketi okuma ve zaman yardımcıları (paket modu)
  core/              config.py (ayarlar), rules.py + risk_rules.toml (eşikler)
  api/               analyze.py (SSE, sohbet), data.py, stores.py
  db/                session, models, repositories
  pipelines/         detection, vision, geo, motion, matching, report_parser, reports, risk
  agent/
    service.py       EvaluationService: ince orkestratör, aşama başına bir SSE adımı
    stages.py        tipli aşamalar (ImageContext → Detections ∥ TrackBranch → Matches
                     → Contacts → ClaimEvaluations → RiskResult → FinalDecision → Brief)
    events.py        adımların özet ve data yükleri (frontend sözleşmesi)
    brief_text.py    brief ve özet metinleri
    decision.py      LLM kararı (±1 kademe, ADR-0002)
    runner.py        kayıt, önbellekten tekrar oynatma
    chat.py, tools.py  sohbet agent'ı ve araçları
    prompts/         brief, chat, report_parse, vision
  llm/               client.py, limits.py, models.toml
  schemas/           domain, api, claims, chat, runs
scripts/             load_data, parse_reports, run_eval_set, trace_evaluation, ...
tests/               test_evaluation (ana test noktası), test_stages, ..., fixtures/
../supabase/migrations/  şema migration'ları (01 … 10)
```

## Çalışma notları
- İlerleme `ILERLEME.md` dosyasına, yapılacaklar `TODO.md` dosyasına, demoyu ve teslimi etkileyebilecek riskler `RISKLER.md` dosyasına yazılır. İş tamamlandıkça üçü de güncellenir.
- Gizli anahtarlar `.env` dosyasında durur, repoya girmez. Şablon: `.env.example`.
