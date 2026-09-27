-- Rapor doğrulama (app/reports_v2) sonuçları: bir iddianın bir görüntüdeki doğrulaması.
-- `model_detections` gibi önceden hesaplanmış analiz çıktısıdır: demo öncesi bir kez
-- doldurulur (scripts/fill_report_cache), değerlendirme sırasında önbellek olarak okunur.
-- `cache_key`, LLM'e giden girdinin (politika + kanıt dosyası) özetidir; girdi değişirse
-- yeni satır yazılır. LLM'in ham cevabı `llm_output`'ta, kural kararı ve politikadan sonraki
-- nihai sonuç ayrı sütunlarda tutulur.
create table public.report_verifications (
  id                     bigint generated always as identity primary key,
  cache_key              text not null unique,
  claim_id               bigint references public.report_claims(id) on delete cascade,
  image_id               text references public.images(id) on delete cascade,
  verdict                text check (verdict in
                           ('consistent', 'partial', 'contradicts', 'unverifiable', 'irrelevant')),
  harm                   text check (harm in ('lowers_risk', 'raises_risk', 'none')),
  dangerous_reassurance  boolean,
  context_flags          text[] not null default '{}',
  needs_review           boolean,
  rule_verdict           text,
  reasoning              text,
  checks                 jsonb,
  dossier                jsonb,
  llm_output             jsonb not null,
  model                  text,
  created_at             timestamptz not null default now(),
  updated_at             timestamptz not null default now()
);
create index report_verifications_claim_id_idx on public.report_verifications (claim_id);
create index report_verifications_image_id_idx on public.report_verifications (image_id);

alter table public.report_verifications enable row level security;
