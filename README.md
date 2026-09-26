# Üs Koruma Karar Destek

Roketsan Yapay Zekâ Hackathonu, Aşama 2. Merkez Üs'ün çevresindeki 8 bölgeden gelen drone görüntülerindeki araçların üs için risk oluşturup oluşturmadığına karar veren ve bunu gerekçeli bir **brief** ile açıklayan LLM agent'ı ve operasyon ekranı.

| Klasör | İçerik |
|---|---|
| `backend/` | FastAPI servisi: tespit, eşleme, hareket analizi, rapor değerlendirme, risk ve LLM brief'i. Ayrıntı: [`backend/CLAUDE.md`](backend/CLAUDE.md) |
| `frontend/` | Next.js operasyon ekranı: harita, görüntü, Risk & Temaslar, zaman akışı. Ayrıntı: [`frontend/CLAUDE.md`](frontend/CLAUDE.md) |
| `supabase/` | Veritabanı migration'ları |
| `docs/adr/`, `CONTEXT.md` | Mimari kararlar ve alan dili |

Uygulama iki süreçten oluşur ve ikisi de açık olmalıdır:

```
Tarayıcı ──► frontend (Next.js, :3000) ──/api/*──► backend (FastAPI, :8000)
```

Tarayıcı backend'e doğrudan gitmez. Frontend `/api/*` isteklerini backend'e yönlendirir.

## Gereksinimler

- **Python 3.11+**
- **Node.js 20.9+** (npm ile)
- **Veri paketi (`stage2`):** repoda yok, organizatörlerden alınır. Varsayılan yeri repo klasörünün **yanı** (`../stage2`):
  ```
  Projects/
  ├── RokatsanUI/          ← bu repo
  └── stage2/
      ├── images/          ← 40 drone görüntüsü
      ├── image_meta.json
      ├── zones.json
      ├── tracks.csv
      ├── field_reports.json
      └── detections_all.csv      ← (isteğe bağlı) modelin kayıtlı çıktısı, ağsız demo (USE_INFERENCE=DEMO + DATA_SOURCE=package) için
  ```
  Başka bir yerdeyse `backend/.env` içindeki `DATA_DIR` değerini değiştir. Yol `backend/` klasörüne göre çözülür.
- **Anahtarlar:** Supabase bilgileri ve en az bir LLM anahtarı (GLM, EVREN ya da Anthropic). Bunlar takım içinde paylaşılır ve repoya girmez.

## 1. Backend'i kur ve çalıştır

`backend/` klasöründe çalış.

Sanal ortamı oluştur:

```bash
python -m venv .venv
```

Ortamı etkinleştir. **Windows (PowerShell):**

```bash
.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
source .venv/bin/activate
```

Paketleri kur (`dev` ekleri test araçlarını da getirir):

```bash
pip install -e ".[dev]"
```

Ayar dosyasını şablondan oluştur ve doldur. **Windows:**

```bash
copy .env.example .env
```

**macOS / Linux:**

```bash
cp .env.example .env
```

Sunucuyu başlat:

```bash
uvicorn app.main:app --reload --port 8000
```

Çalıştığını kontrol et: http://localhost:8000/docs adresinde API belgeleri açılmalı.

### `.env` içinde önemli ayarlar

| Ayar | Ne işe yarar |
|---|---|
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL` | Veritabanı ve görüntü deposu. `DATA_SOURCE=supabase` iken gerekli. |
| `GLM_API_KEY` / `EVREN_API_KEY` / `ANTHROPIC_API_KEY` | LLM sağlayıcıları. Sırayla denenir (`app/llm/models.toml`), anahtarı olmayan atlanır. Hiçbiri yoksa brief kurallarla yazılır ("otomatik özet"). |
| `DATA_DIR` | Veri paketinin yeri (varsayılan `../../stage2`). |
| `DATA_SOURCE` | `supabase` (varsayılan) ya da `package`: **ağsız demo**. Veri `DATA_DIR`'den okunur, kayıtlar bellekte tutulur. |
| `USE_INFERENCE` | Araç tespiti nereden gelsin (aşağıdaki tabloya bak). |

**Tespit modları (`USE_INFERENCE`):**

| Mod | Açıklama | Gerekenler |
|---|---|---|
| `DEMO` (varsayılan) | Modelin önceden alınmış çıktısı. En hızlısıdır, EVREN'e gitmez. | `DATA_SOURCE=supabase`: `model_detections` tablosu (yükleme: `python -m scripts.load_detections`). `DATA_SOURCE=package`: `DETECTIONS_CSV_PATH` (ör. `../../stage2/detections_all.csv`) |
| `REAL` | Ekibin EVREN'deki modeli **canlı** çalışır. Görüntü her analizde EVREN'e gönderilir. | `EVREN_MODEL_API_KEY`, internet |

### Ağsız demo (internet ya da veritabanı yoksa)

`.env` içinde `DATA_SOURCE=package`, `USE_INFERENCE=DEMO`, `DETECTIONS_CSV_PATH=../../stage2/detections_all.csv` ve `CLAIMS_PATH=../../stage2/claims.json` yap. Tespitler CSV'den okunur. Rapor iddiaları bu dosyadan okunur. Dosyayı bir kez, ağ ve Supabase erişimi varken üret (`backend/` klasöründe):

```bash
python -m scripts.export_claims --out ../../stage2/claims.json
```

LLM anahtarlarına ulaşılamazsa brief yine kurallarla yazılır.

## 2. Frontend'i kur ve çalıştır

İkinci bir terminalde, `frontend/` klasöründe çalış.

Paketleri kur:

```bash
npm install
```

Geliştirme sunucusunu başlat:

```bash
npm run dev
```

Tarayıcıda **http://localhost:3000** adresini aç.

Backend 8000'den farklı bir porttaysa frontend'i başlatmadan önce `BACKEND_URL` ayarla. **Windows (PowerShell):**

```bash
$env:BACKEND_URL="http://localhost:8001"
```

**macOS / Linux:**

```bash
export BACKEND_URL=http://localhost:8001
```

## 3. Kullanım

1. Alttaki **zaman akışından** ya da soldaki **Görüntü** çekmecesinden (`G`) bir kare seç. Harita karenin konumuna yaklaşır.
2. **Risk analizini başlat**'a bas. Backend analizi o anda çalıştırır ve adımlar canlı gelir. Sağdaki **Risk & Temaslar** çekmecesi kendiliğinden açılır.
3. Brief gelince seviye ve önerilen eylem üst çubukta görünür. Temaslar harita, görüntü ve listede birlikte seçilir.
4. Sağ üstteki düğmeyle açık ve koyu tema arasında geçiş yapılır.

Kısayollar: `R` Risk & Temaslar · `B` Brief · `G` Görüntü · `←` / `→` önceki ve sonraki kare · `Esc` çekmeceyi kapat.

## Testler ve kontroller

**Backend** (`backend/` klasöründe, sanal ortam etkinken):

```bash
pytest
```

```bash
ruff check app
```

```bash
mypy --strict app scripts
```

**Frontend** (`frontend/` klasöründe):

```bash
npm test
```

```bash
npm run typecheck
```

```bash
npm run lint
```

Uçtan uca testler (Playwright) için tarayıcıyı bir kez kur, sonra çalıştır:

```bash
npx playwright install chromium
```

```bash
npm run e2e
```

## Yardımcı komutlar (backend)

Sanal ortam etkinken `backend/` klasöründe çalıştırılır.

| Komut | Ne yapar |
|---|---|
| `load-data` | Veri paketini Supabase'e yükler. |
| `upload-images` | Görüntüleri Supabase Storage'daki `drone-images` bucket'ına yükler. |
| `export-claims --out <dosya>` | Ağsız demo için rapor iddialarını Supabase'ten dosyaya yazar. |
| `run-eval-set` | Değerlendirme setini çalıştırır (seviye, eşleşme ve rapor kararı doğruluğu). |

## Sık karşılaşılan sorunlar

- **"Değerlendirme başlatılamadı. Backend'e ulaşılamıyor olabilir."** Backend çalışmıyor ya da farklı bir portta. Backend terminalini ve `BACKEND_URL` ayarını kontrol et.
- **Analiz uzun sürüyor.** Canlı tespit (`USE_INFERENCE=REAL`) ve LLM çağrısı birlikte 15–40 saniye sürebilir. Adımlar geldikçe ekranda görünür. Hız gerekiyorsa `USE_INFERENCE=DEMO` kullan.
- **Harita zemini yüklenmiyor.** Sokak ve uydu zemini internetten gelir. İnternet yoksa harita düz zemine geçer, katmanlar çalışmaya devam eder.
- **`.env` değişikliği etkisiz.** Backend'i yeniden başlat. Ayarlar yalnızca açılışta okunur.
- **Windows'ta `npm run fixtures` hata veriyor.** Script macOS/Linux yolunu (`.venv/bin/python`) kullanıyor. Günlük çalıştırma için gerekmez.
