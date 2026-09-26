# 07: Seçili karenin son iki saati şeridi

**What to build:** Zaman akışının alt şeridinde seçili karenin son iki saati görünür: seçili Temas'ın rota noktalarının saatleri, duraklamaları ve bağlı rapor saatleri; çekim anı işaretlidir. Çekim anından sonrası gri ve kapalıdır ("çekim anından sonrası yok"). Temas seçili değilken şerit yalnızca zaman eksenini ve çekim anını gösterir.

**Blocked by:** 06

**Status:** ready-for-agent

- [ ] Alt şerit: çekim anından iki saat öncesinden çekim anına kadar eksen; çekim anı işareti
- [ ] Seçili Temas'ın rota saatleri, duraklamaları (`motion.stops`), bağlı rapor saatleri (`report_findings[].report_time`)
- [ ] Çekim anından sonrası gri ve kapalı; rota saati `null` ise yalnızca duraklama ve rapor saatleri
- [ ] Sayfa testi: T0122 seçilince duraklama ve 12:35 raporu şeritte; çekim anından sonrası kapalı
