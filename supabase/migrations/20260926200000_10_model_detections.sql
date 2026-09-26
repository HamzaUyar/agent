-- Tespit modelinin önceden alınmış çıktısı (USE_INFERENCE=DEMO). Kaynak: detections_all.csv
-- (image_id, cls, score, x, y, w, h). Kutu piksel cinsinden sol üst köşe + genişlik/yükseklik.
-- Değerlendirme kayıtlarındaki `detections` tablosundan ayrıdır: o tablo bir koşunun
-- kullandığı tespitleri tutar, bu tablo modelin ham çıktısıdır (düşük skorlular dahil).
create table public.model_detections (
  id        bigint generated always as identity primary key,
  image_id  text not null references public.images(id) on delete cascade,
  source    text not null,
  label     public.vehicle_class not null,
  score     real not null check (score between 0 and 1),
  bbox_x    real not null,
  bbox_y    real not null,
  bbox_w    real not null check (bbox_w > 0),
  bbox_h    real not null check (bbox_h > 0)
);
create index model_detections_image_id_idx on public.model_detections (image_id);
create index model_detections_source_idx   on public.model_detections (source);

alter table public.model_detections enable row level security;
