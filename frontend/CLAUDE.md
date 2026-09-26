@AGENTS.md

# Operasyon ekranı (frontend)

Üs Koruma Karar Destek'in arayüzü. Alan dili kökteki `CONTEXT.md`, kararlar `docs/adr/`; spec ve biletler `../.scratch/operasyon-ekrani/`. Tasarım kararları `design-system/operasyon-ekrani/pages/operasyon.md` (MASTER'ı geçersiz kılar), token'lar `app/globals.css`.

- Backend sözleşmesi tek kaynak: tipler `lib/api/openapi.json`'dan üretilir; SSE olay tipleri `lib/api/types.ts`. Uydurma alan yazılmaz. Backend değişince `npm run fixtures` (şema + tipler + test verisi).
- Bileşenler `fetch` bilmez; bütün çağrılar `lib/api/client.ts`. Tarayıcı `/api/*`'ye gider, `next.config.ts` backend'e (`BACKEND_URL`, varsayılan `:8000`) yönlendirir.
- Tek seçim deposu `store/operasyon.ts` (Zustand).
- Metinler Türkçe ve alan dilinde (`lib/labels.ts`); sayılar `lib/format.ts`. Seviye hiçbir yerde yalnızca renkle verilmez. Çekim anından sonrası gösterilmez (ADR-0001).
- Testler: sayfa davranışı Vitest + Testing Library + MSW ile (`tests/`, veri `tests/fixtures/` backend'den üretilmiş); küçük birim testleri yanlarında (`*.test.ts`); Playwright `e2e/`.

Komutlar: `npm run dev` · `npm test` · `npm run typecheck` · `npm run lint` · `npm run e2e` · `npm run build`
