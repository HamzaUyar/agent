# 02: İzci mermi: img_000860 uçtan uca

**What to build:** Operatör img_000860 için değerlendirme başlattığında adımlar SSE ile akar: sahte tespit, konumlandırma, en yakın track eşleşmesi, üsse mesafe ve yaklaşma, temel seviye, şablondan otomatik özet. Brief kaydedilir; görüntü listesi uç noktası çalışır.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Değerlendirme servisi test noktası kurulu (sahte tespit, sahte LLM, bellek içi depo)
- [ ] img_000860: koordinat 39.92531, 32.87183; eşleşme T0122 (<1 m, ikinci aday T0032 41 m); üsse ~1,6 km; yaklaşıyor; seviye kritik
- [ ] Çekim anından sonraki track noktaları sonucu etkilemiyor (ADR-0001)
- [ ] Değerlendirme başlatma uç noktası adımları SSE ile akıtıyor, son olay yapılandırılmış brief
- [ ] Görüntü listesi uç noktası
- [ ] Değerlendirme ve adımları Supabase'e kaydediliyor
