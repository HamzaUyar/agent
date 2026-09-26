# Test verisi

Bu dosyalar elle yazılmadı; backend'in gerçek kodundan üretildi ve sözleşmeyle birebir aynı.

| Dosya | Kaynak |
|---|---|
| `zones.json` | `GET /zones`, `stage2/` veri paketi |
| `images.json` | `GET /images`, `stage2/` (40 görüntü; `last_risk_level` veritabanından gelir, testler için örnek: img_000860 `high`, img_008333 `low`, img_004423 `medium`, diğerleri değerlendirilmemiş) |
| `image_details.json` | `GET /images/{id}`, `stage2/` (40 görüntü) |
| `img_000860.events.json` | `POST /evaluations` olayları: backend'in `tests/fixtures/mock_package` referans örneği, sahte tespitler (kamyon 727,284 → T0122 eşleşmiş, kritik; güveni 0,83 bir otomobil → kayıt dışı temas; T0032 → kaçırılmış temas), LLM yok → otomatik özet |

Hepsi, `lib/api/openapi.json` ve ondan türeyen `lib/api/schema.d.ts` ile birlikte `npm run fixtures` komutuyla yeniden üretilir (`scripts/export_fixtures.py`, backend'in `.venv`'i). Backend sözleşmesi değişince bu komut çalıştırılır.
