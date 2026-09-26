# Üs Koruma Karar Destek

Drone görüntülerini, hareket kayıtlarını ve saha raporlarını birlikte değerlendirip bir görüntüdeki durumun üs için ne kadar riskli olduğuna gerekçeli karar veren agent'ın alan dili.

## Sahne

**Üs**:
Korunan tesis (Merkez Üs); bütün mesafe ve yaklaşma ölçümlerinin referans noktası.
_Avoid_: base, merkez

**Bölge**:
Üs çevresinde drone ile izlenen sekiz adlandırılmış alandan biri; yalnızca merkez noktasıyla tanımlıdır.
_Avoid_: zone, sektör

**Görüntü**:
Bir bölgeden belirli bir çekim anında alınmış tek drone karesi; köşe koordinatları ve çekim saati bilinir.
_Avoid_: resim, frame, fotoğraf

**Çekim anı**:
Görüntünün alındığı saat; değerlendirmenin "şimdi"sidir. Bu andan sonraki hiçbir veri değerlendirmede kullanılmaz.
_Avoid_: capture time, zaman damgası

## Varlıklar

**Tespit**:
Tespit modelinin tek bir görüntüde bulduğu araç: sınıfı (car, van, truck, bus), güveni ve piksel kutusu.
_Avoid_: detection, araç

**Zayıf tespit**:
Güveni düşük olan Tespit; ancak bir Track'le eşleşirse Temas sayılır, eşleşmezse yok sayılır.

**Track**:
Bir aracın konum geçmişi; 5 dakikalık adımlarla, tipi ve kimliği bilinmeyen hareket kaydı.
_Avoid_: iz, rota, hareket kaydı

**Temas**:
Değerlendirilen tek varlık: bir Tespit ile onu çekim anında karşılayan Track'in eşleşmesi, ya da eşi bulunamamış tek bir Tespit veya Track.
_Avoid_: araç, hedef, nesne

**Kayıt dışı temas**:
Track'i bulunmayan bir Tespit'ten oluşan Temas; hareket geçmişi bilinmez. Park halindeki araçların track'i olmayabileceği için kendi başına risk sayılmaz (ADR-0003).

**Kaçırılmış temas**:
Çekim anında görüntünün alanında olduğu halde Tespit'i bulunmayan bir Track'ten oluşan Temas; tipi bilinmez.

**Belirsiz eşleşme**:
Bir Tespit'in eşleşme mesafesi içinde birden fazla Track bulunması; en yakını seçilir, diğerleri aday olarak not edilir.

**Yaklaşma**:
Bir Temas'ın üsse olan mesafesinin yakın geçmişte belirgin biçimde azalması.
_Avoid_: ilerleme, sızma

## Saha bilgisi

**Rapor**:
Sahadan gelen, saatli ve kaynağı (resmi / üçüncü taraf) belli serbest metin gözlem; doğruluğu garanti değildir.
_Avoid_: ihbar, istihbarat, field report

**İddia**:
Bir Rapor'dan çıkarılmış tek, kontrol edilebilir önerme (konum, araç tipi, davranış, dostluk vb.).
_Avoid_: claim, bilgi

**Dostluk iddiası**:
Bir aracın veya bölgedeki unsurların dost olduğunu söyleyen İddia; ancak kendi bulgularımızla doğrulanırsa riski düşürebilir.

**Doğrulanmış dost**:
Resmi bir Dostluk iddiasının belirttiği bütün özelliklerle (konum, zaman, tip, renk) örtüşen Temas.

**Doğrulanamaz iddia**:
Zamanı veya konumu belirsiz olduğu için hiçbir Temas'la karşılaştırılamayan İddia; brief'te görünür, riski etkilemez.

**Rapor kararı**:
Bir İddia'nın bir değerlendirmedeki sonucu: tutarlı, çelişkili, doğrulanamaz veya ilgisiz.
_Avoid_: rapor skoru, güvenilirlik

## Karar

**Risk seviyesi**:
Bir Temas'ın üs için oluşturduğu tehdidin derecesi: düşük, orta, yüksek, kritik. Bir Görüntü'nün risk seviyesi, içindeki en yüksek Temas seviyesidir.
_Avoid_: tehdit puanı, kritiklik

**Brief**:
Bir Görüntü için üretilen, risk seviyesini, Temas bulgularını, rapor değerlendirmesini, önerilen eylemi ve kaynakları içeren gerekçeli Türkçe değerlendirme.
_Avoid_: rapor, özet, çıktı

**Kesinlik**:
Brief'teki her bulgunun ne kadar güvenilir olduğunu gösteren etiket: kesin, olası, zayıf, doğrulanamadı.
_Avoid_: güven skoru, olasılık

**Önerilen eylem**:
Risk seviyesine bağlı sabit adım: izlemeye devam (düşük), takibe al (orta), birim yönlendir (yüksek), alarm ve durdurma (kritik).
