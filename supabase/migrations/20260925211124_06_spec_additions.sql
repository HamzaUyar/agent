-- Spec: goruntu-degerlendirme-agent. Kesinlik, zayıf tespit, belirsiz eşleşme,
-- temel/nihai seviye ayrımı, otomatik özet, sohbet mesajları.

create type public.certainty as enum ('certain', 'likely', 'weak', 'unverified');

alter table public.analysis_runs
  add column brief_json   jsonb,
  add column is_fallback  boolean not null default false;

alter table public.detections
  add column is_weak boolean not null default false;

alter table public.track_matches
  add column is_ambiguous boolean not null default false;

-- risk_level nihai seviyedir; temel seviye ve LLM ayar gerekçesi ayrı tutulur.
alter table public.risk_assessments rename column risk_level to final_level;
alter table public.risk_assessments
  add column base_level         public.risk_level not null,
  add column adjustment_reason  text,
  add column certainty          public.certainty;

alter table public.report_evaluations
  add column certainty public.certainty;

-- Yükleyicinin tekrar çalıştırılınca çoğaltma yapmaması için doğal anahtar.
alter table public.field_reports
  add constraint field_reports_natural_key unique (time, source, text);

create table public.chat_messages (
  id          bigint generated always as identity primary key,
  run_id      uuid not null references public.analysis_runs(id) on delete cascade,
  role        text not null check (role in ('user', 'assistant', 'tool')),
  content     text not null,
  tool_calls  jsonb,
  created_at  timestamptz not null default now()
);
create index chat_messages_run_id_idx on public.chat_messages (run_id);
alter table public.chat_messages enable row level security;
