# Değerlendirme çekim anından sonraki veriyi görmez

Veri paketi günün tamamını kapsıyor: çekim anından sonraki track noktaları ve raporlar da elimizde. Buna rağmen bir Görüntü değerlendirilirken yalnızca çekim anına kadar olan veri kullanılır. Bu kural hem pipeline için hem sohbet agent'ının araçları için geçerli.

Sebep: senaryo "o anda karar vermek". Aracın sonra nereye gittiğini bilerek karar vermek gerçek bir operasyonda mümkün değil ve jüriye hile gibi görünür.

Sonuç: Sorgular her zaman `time <= çekim anı` filtresi taşır. Sonradan olanlar ancak ayrı ve açıkça etiketlenmiş bir "geriye dönük inceleme" görünümünde gösterilebilir.
