# 06: Temas listesi ve detay kartı

**What to build:** Risk & Temaslar çekmecesinde Temas'lar seviyeye göre sıralıdır; düşük seviyeliler katlanır bir grupta durur ("19 kayıt dışı temas, en yakını 0,8 km"). Her satırda tür rozeti, sınıf, track kimliği, Üs'e mesafe, seviye ve kesinlik vardır. Bir Temas'a listeden, haritadaki işaretten ya da görüntüdeki kutudan tıklanınca üç görünüm aynı Temas'a odaklanır: harita rotayı vurgulayıp yaklaşır, görüntü kutuyu vurgular, çekmece yarım açılıp detay kartını gösterir. Detay kartında tespit, eşleşme, hareket (üsse mesafenin çekim anına kadarki mini grafiği dahil), seviye (temel → nihai, gerekçeler, LLM ayarı ve reddedilen öneri), dostluk/tip çelişkisi ve bu Temas'a bağlı Rapor kararları görünür.

**Blocked by:** 05

**Status:** ready-for-agent

- [ ] Liste seviyeye göre sıralı; düşükler katlanır grupta; satırda tür, sınıf (`effective_label`), track, mesafe, seviye, kesinlik
- [ ] Tek seçim deposu: Temas anahtarı `track_id` ya da (kayıt dışı için) `contacts[]` sırası; yeni değerlendirmede sıfırlanıyor
- [ ] Üç yoldan seçim ve senkron: harita vurgu + yaklaşma, görüntü kutu vurgusu, çekmece yarım + detay kartı
- [ ] Tespit: sınıf, güven, zayıf mı; Eşleşme: track, mesafe, ikinci aday, belirsiz eşleşme uyarısı
- [ ] Hareket: 30 dk önce / şimdi mesafe, son ve ortalama hız, yön, duraklamalar, geçilen Bölge'ler, mini mesafe grafiği (rota + Üs'ten istemcide; saat yoksa sıra ekseni)
- [ ] Seviye: `base_level → final_level`, `level_reasons`, `adjustment_reason`, `adjustment_rejected`; doğrulanmış dost / tip çelişkisi rozetleri
- [ ] Bağlı Rapor kararları (`report_findings` içinde `track_id` eşleşenler): karar, etki (↑ ↓ –), gerekçe; kayıt dışı Temas'ta "bu temasa rapor bağlanamıyor" notu
- [ ] Sayfa testleri: sıralama ve katlama; üç yoldan seçim senkronu; detay kartının bölümleri; saatsiz rota grafiği; kayıt dışı temas notu
