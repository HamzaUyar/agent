# 01: Operasyon ekranı iskeleti, tasarım sistemi ve çekmeceler

**What to build:** Operatör sayfayı açtığında Konsept A kabuğunu görür. Üstte ince durum çubuğu "Zaman akışından bir kare seçin" der. Ortada kenarlarında boşluk olan çerçeveli harita paneli alanı, altta zaman akışı alanı var. Sağ kenarda "Risk & Temaslar", sol kenarda "Görüntü" ve "Sohbet" sekmeleri durur; sekmeye tıklayarak, tutamaçtan sürükleyerek ya da kısayolla (R, B, G, S) açılır, Esc ile kapanır. Çekmece açılınca harita paneli daralır ama kaybolmaz, arka plan kararmaz. Geliştirici için: Next.js iskeleti, `/api` → backend yönlendirmesi, OpenAPI'den üretilen tipler, SSE okuyucu, sayfa testleri için MSW ve referans veri, Playwright ve tasarım sistemi (token'lar, shadcn, koyu tema) hazırdır.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [x] Next.js (App Router, TypeScript, Tailwind) projesi `frontend/` içinde; `/api/*` isteği backend'e (`:8000`) yönleniyor
- [x] Backend tipleri `/openapi.json`'dan üretiliyor; SSE olay yükleri backend koduna birebir tek bir modülde tanımlı; uydurma alan yok
- [x] SSE okuyucu `fetch` + `ReadableStream` ile olayları ayrıştırıyor ve iptal edilebiliyor (parçalı satır, çok satırlı `data`, iptal için küçük testler)
- [x] Vitest + Testing Library + MSW kurulu; MSW işleyicileri referans örnekten (img_000860, T0122, 12:35 raporu) veri döndürüyor; örnek bir sayfa testi geçiyor
- [x] Playwright kurulu; sayfanın açıldığını doğrulayan bir test geçiyor
- [x] `ui-ux-pro-max` ile tasarım yönü seçildi ve projeye kaydedildi; `design-system` ile üç katmanlı token'lar (`risk-dusuk/orta/yuksek/kritik`, `secim`, `veri-bayat`, `cekmece-*`, `harita-paneli-*`, `ust-cubuk`, `zaman-akisi`); koyu tema varsayılan; glassmorphism/neon yok
- [x] shadcn/ui kurulu, temaya bağlı (Sheet, Tabs, Badge, Tooltip, ScrollArea, Button)
- [x] Kabuk: üst çubuk, harita paneli alanı (~%60, kenarlarda boşluk), zaman akışı alanı; kare seçili değilken "Zaman akışından bir kare seçin"
- [x] Çekmeceler: sağda Risk & Temaslar (Temaslar · Brief sekmeleri), solda Görüntü veya Sohbet; kapalı / göz atma / yarım / tam hâlleri; kenar başına en fazla bir çekmece; modal değil, harita paneli daralıyor
- [x] Klavye: R, B, G, S açar; Esc kapatır; odak çekmeceye taşınır ve kapanınca geri döner; yazı alanında kısayollar çalışmaz
- [x] Seviye, tür, sınıf, kesinlik, eğilim, rapor kararı ve etki için Türkçe etiket eşlemeleri ve `tr-TR` sayı biçimi tek modülde (küçük testlerle)

## Comments

- 26 Eylül: tamamlandı. shadcn `Sheet` yerine düzenin parçası olan paneller (Sheet haritayı daraltmıyor); seçim rengi amber yerine gök mavisi (amber orta/yüksek seviyeyle karışıyor). Kararlar `frontend/design-system/operasyon-ekrani/pages/operasyon.md`.
