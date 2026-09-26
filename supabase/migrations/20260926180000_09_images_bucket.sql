-- Drone görüntüleri Supabase Storage'da, özel `drone-images` bucket'ında.
-- `images.file_path` artık "<bucket>/<nesne>" biçiminde (ör. drone-images/img_000860.jpg).
-- Bucket herkese açık değil: backend `service_role` anahtarıyla okur ve yazar.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('drone-images', 'drone-images', false, 20971520, array['image/jpeg', 'image/png'])
on conflict (id) do nothing;
