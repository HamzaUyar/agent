# Risk, izin ilk noktasından itibaren her adımda değerlendirilir

Temel seviyeyi zaman boyutlu risk motoru (`app/risk_engine`, parametreler `app/core/risk_engine.toml`) verir. Her track, ilk noktasından çekim anına kadar her 5 dakikalık gözlemde yalnızca o ana kadarki noktalarla değerlendirilir (ADR-0001 korunur). Temasın temel seviyesi çekim anındaki yayınlanan seviyedir. Eski tablo yalnızca çekim anındaki trende bakıyordu (`base_level`, kaldırıldı).

Motorun katmanları:

- **Özellikler:** son 15/30/60 dk yaklaşma, son 2 saatteki en yakın geçiş, tahmini varış süresi, son sürüş adımının üsse yönelimi, çember ve yay devriyesi istatistikleri, park süresi. Noktalar arasında interpolasyon yapılmaz, çünkü 5 dakikada çember üzerinde 70–120° yol alınabiliyor ve ara nokta üsse yapay bir yakınlık üretir.
- **Seviye tablosu:** ilk uyan satır geçerli.
  - Kritik:
    - C1: ≤ 1 km'de hareket eden araç
    - C2: yaklaşıyor ve ≤ 1,5 km
    - C3: yaklaşan kamyon/otobüs ≤ 2 km
    - C4: varış ≤ 10 dk
    - C5: hedefli atılım ≤ 2,5 km
  - Yüksek:
    - H1: yaklaşıyor ≤ 3 km
    - H2: ≤ 1,4 km, park eden dahil
    - H3: sokulup geri çekilme
    - H4: çember
    - H4r: yay devriyesi
    - H5: yaklaşıp durma
    - H6: sürünme
  - Orta: her yaklaşma, uzak çember, iç halkada bulunma.
- **Durum makinesi:** yükselme anında olur. İniş beklemeli: kritik ve yüksek 15 dk, orta 20 dk. Çıkış eşikleri +200 m daha gevşek (histerezis). Düşükten ortaya çıkmak için 2 ardışık gözlem gerekir.
- **Öncelik skoru (0–100):** seviye bandı + yaklaşma hızı, davranış, ağır araç ve yeni giriş bileşenleri. Aynı seviyedeki temasları sıralar, seviyeyi değiştirmez. Referansları sabittir, göreli ölçek değildir.

Sebep: görev tanımında riskin yalnızca çekim anında ölçüleceğine dair bir şey yok. Çekim anına bakan tablo üssün 1 km içine girip çıkan 37 aracın hiçbirini görmüyordu, çünkü çekim anında hepsi uzaklaşmıştı. Parametreler 10 bakış açılı iki turlu bir Delphi süreciyle ve ekip ayarıyla ("Orta-A") belirlendi. Doğrulama gerçek veri (226 iz × 25 adım), eğitimde kullanılmayan 13.000 sentetik iz ve 260 Monte Carlo koşusuyla yapıldı.

## Considered Options

- **Çekim anı tablosu (eski):** Açıklaması kolay. Sentetik tehditlerin %17,7'si hiç yüksek almıyor, geçmişteki sokulmalar görünmüyor.
- **İlk konsensüs seti (C1 koşulsuz, C2 2,2 km, 120 dk kalıcı taban):** Uyarıyı en erken veriyor. Zamanın %15'i kritik, aynı anda 21'e kadar kritik var, masum sentetik izlerin %12'si kritik oluyor.
- **Göreli ölçek (verinin %90'lık dilimine bölmek):** Kritik sayısı hep küçük kalır. Seviye başka araçlara bağlı olur: sakin günde de alarm verir, yoğun günde alarm azalır, tek görüntüde hesaplanamaz.
- **Seçilen, Orta-A:** Tehdit kaçırma %0,6'da kalıyor, ihlal öncesi yüksek uyarı 10/11. Zamanın %3,9'u kritik, aynı anda kritik medyanı 2, masum sentetik izlerde kritik %2,2. Bedeli: ihlalden ≥ 5 dk önce kritik uyarı 10/11'den 7/11'e iniyor (o araçlar ihlalden önce yine yüksek alıyor).

## Consequences

- Temasa `level_code`, `priority_score`, `level_tags` ve izin başından itibaren `level_history` eklenir. Görüntü seviyesi yine temasların en yükseğidir.
- Park eden araç üssün 1 km içinde olsa da kritik değil yüksektir. Gerekçede "üs yakınında X dk bekledi" yazar.
- İniş beklemesi, hızla uzaklaşan aracı 15 dk kritik tutabilir (ör. T0002, 6,7 km). Hızlı çıkış kuralı seviye salınımını 12'den 30'a çıkardığı için eklenmedi. Bunun yerine öncelik skoru tutulan seviyeyi bandın altına iter.
- `risk_rules.toml [levels]` yalnızca karar LLM'inin dikkat nedenlerini doğrulamak için kalır. LLM'in ±1 ayarı (ADR-0002) değişmedi.
- Hiçbir görüntünün adayı olmayan track'ler (kaydı var, çekim anında kadraj dışında) görüntüsüz olarak değerlendirilir: seviyeyi motor verir, görüntü özetlerine katılmaz; LLM operatör için kısa bir metin yazar (`track_assessments`, migration 13).
- Günün tamamı `scripts.compute_risk` ile Supabase'e yazılır (migration 12: `risk_timeline`, `risk_events`, `risk_notices`, `image_risk`, en son koşu `*_latest` görünümleri).
- Referans uygulamayla birebir eşleşme `tests/test_risk_engine.py` içindeki 5.650 adımlık altın dosyayla korunur.
