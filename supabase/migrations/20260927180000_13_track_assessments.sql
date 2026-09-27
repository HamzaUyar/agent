-- Görüntüsüz track'lerin değerlendirmesi (app/agent/track_brief).
-- Bazı araçların hareket kaydı var ama hiçbir görüntünün adayı değiller (çekim anında
-- kadraj dışında kaldılar). Seviyeyi risk motoru verir (`risk_timeline`, image_id boş);
-- LLM operatör için kısa bir değerlendirme yazar. `scripts.assess_tracks` yazar.

create table public.track_assessments (
  id              bigint generated always as identity primary key,
  risk_run_id     uuid not null references public.risk_engine_runs(id) on delete cascade,
  track_id        text not null references public.tracks(id) on delete cascade,
  rules_version   text not null,
  end_time        time not null,
  level           public.risk_level not null,
  code            text not null,
  priority_score  numeric(5,2) not null check (priority_score between 0 and 100),
  facts           text not null,
  assessment      text not null,
  is_fallback     boolean not null,
  rejected        text,
  model           text,
  created_at      timestamptz not null default now()
);
create index track_assessments_run_idx on public.track_assessments (risk_run_id, track_id);

alter table public.track_assessments enable row level security;

-- En son risk koşusundaki görüntüsüz track'ler: kaydın son adımı ve son değerlendirmesi.
create view public.unframed_tracks_latest with (security_invoker = true) as
  select t.track_id, t.t as end_time, t.level, t.code, t.priority_score,
         t.dist_to_base_m, t.dmin_120_m, t.tags,
         a.assessment, a.is_fallback, a.model, a.created_at as assessed_at
  from public.risk_timeline_latest t
  join (select track_id, max(step_no) as step_no from public.risk_timeline_latest
        where image_id is null group by track_id) last
    on last.track_id = t.track_id and last.step_no = t.step_no
  left join lateral (
    select * from public.track_assessments x
    where x.risk_run_id = t.run_id and x.track_id = t.track_id
    order by x.created_at desc limit 1
  ) a on true
  where t.image_id is null;
