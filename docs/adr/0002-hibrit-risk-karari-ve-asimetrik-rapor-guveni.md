# Risk kararı hibrittir, raporlara asimetrik güvenilir

Risk seviyesini kod kurallarla hesaplar. LLM bu seviyeyi gerekçe yazarak en fazla bir kademe değiştirebilir. Raporlar riski serbestçe yükseltebilir. Düşürebilmeleri için ise kendi bulgularımızla doğrulanmaları gerekir: rapor hangi özellikleri belirtiyorsa (konum, zaman, tip, renk) hepsinin tutması şart. Dostluk iddialarında yalnızca resmi kaynak riski düşürebilir.

Sebep: brief açıkça bazı raporların kasıtlı olarak yanlış olduğunu söylüyor. Riski yükselten sahte bir raporun bedeli en fazla bir yanlış alarm; riski düşüren sahte bir raporun bedeli gözden kaçan bir tehdit. Kuralların tekrarlanabilir ve denetlenebilir olması mentör değerlendirmesi için de önemli.

## Considered Options

- **Kararı tamamen LLM versin:** Esnek, ama aynı girdi farklı sonuç verebilir ve sahte bir "dost unsur" raporuna ikna olabilir.
- **Kararı tamamen kod versin:** Tekrarlanabilir, ama kuralların öngörmediği bağlamı (ör. birbirini doğrulayan iki rapor) kaçırır.
