# 08: Temas hakkında sohbet ve demo uçtan uca testi

**What to build:** Detay kartının altındaki "Bu temas hakkında sor" düğmesi Sohbet çekmecesini hazır dolu soruyla açar: track'li Temas'ta "T0122 nereden geldi?", kayıt dışı Temas'ta "Üsse 0,8 km'deki kayıt dışı otomobil hakkında ne biliyoruz?". Operatör soruyu düzenleyip gönderir; çağrılan araçlar sırayla satır olarak, cevap ve modeli akış sonunda görünür. Sohbet yalnızca tamamlanmış değerlendirmede açılır; hata olursa Türkçe mesaj ve "Tekrar dene" çıkar. Demo akışı backend açıkken uçtan uca doğrulanır.

**Blocked by:** 06

**Status:** ready-for-agent

- [ ] "Bu temas hakkında sor" → Sohbet çekmecesi (sol), hazır soru Temas türüne göre; düzenlenebilir; 1–2000 karakter sınırı
- [ ] `POST /evaluations/{run_id}/chat` SSE: `tool` satırları, `answer` cevap + model, `error` → mesaj + tekrar dene
- [ ] Değerlendirme tamamlanmadan sohbet kapalı; sohbet geçmişi yalnızca istemcide, kare değişince sıfırlanıyor
- [ ] Sayfa testleri: hazır soru (track'li ve kayıt dışı), araç satırları ve cevap, hata ve tekrar dene
- [ ] Playwright (backend açık): img_000860 seç → adımlar akar → seviye görünür → T0122 detayı → "T0122 nereden geldi?" cevabı; demo öncesi kontrol olarak belgelenmiş
