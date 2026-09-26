-- Raporun veri dosyasındaki sırası; doğal anahtar artık bu.
-- Eski anahtar (time, source, text), gerçek veride birebir aynı olan raporları siliyordu
-- (stage2: iki çift "Hava acik, gorus mesafesi iyi."). Yükleyici tekrar çalıştırılınca
-- yine çoğaltma yapmaz: aynı sıradaki rapor güncellenir.
alter table public.field_reports drop constraint field_reports_natural_key;

alter table public.field_reports add column seq integer;

update public.field_reports r
set seq = s.rn
from (select id, row_number() over (order by id) - 1 as rn from public.field_reports) s
where r.id = s.id;

alter table public.field_reports alter column seq set not null;

alter table public.field_reports
  add constraint field_reports_seq_key unique (seq),
  add constraint field_reports_seq_check check (seq >= 0);
