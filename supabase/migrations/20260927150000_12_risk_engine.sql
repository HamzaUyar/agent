-- Zaman boyutlu risk motorunun (app/risk_engine) çıktıları.
-- Her iz, ilk noktasından itibaren her gözlem adımında yalnız o ana kadarki noktalarla
-- değerlendirilir. `scripts.compute_risk` bir koşuda tüm izleri hesaplayıp yazar; her koşu
-- `risk_engine_runs` satırıyla (parametreler dahil) izlenir, eski koşular silinmez.
-- En son koşuyu okumak için `*_latest` görünümleri kullanılır.

create table public.risk_engine_runs (
  id                  uuid primary key default gen_random_uuid(),
  engine_version      text not null,
  config              jsonb not null,
  detections_source   text,
  track_count         integer not null,
  step_count          integer not null,
  created_at          timestamptz not null default now()
);

-- İz × adım zaman çizelgesi.
create table public.risk_timeline (
  run_id          uuid not null references public.risk_engine_runs(id) on delete cascade,
  track_id        text not null references public.tracks(id) on delete cascade,
  step_no         integer not null,
  image_id        text references public.images(id) on delete set null,
  t               time not null,
  level           public.risk_level not null,
  level_raw       public.risk_level not null,
  code            text not null,
  code_raw        text not null,
  held            boolean not null,
  crit_static     boolean not null,
  priority_score  numeric(5,2) not null check (priority_score between 0 and 100),
  dist_to_base_m  double precision not null,
  dmin_120_m      double precision not null,
  approach_30_m   double precision not null,
  approach_60_m   double precision not null,
  eta_min         double precision,
  stop_now_min    double precision not null,
  bearing_deg     double precision not null,
  tags            text[] not null default '{}',
  score_parts     jsonb not null,
  primary key (run_id, track_id, step_no)
);
create index risk_timeline_run_t_idx on public.risk_timeline (run_id, t);
create index risk_timeline_image_idx on public.risk_timeline (run_id, image_id);

-- Olaylar: bir seviyede (high+ ya da critical) kesintisiz kalınan koşular.
create table public.risk_events (
  id               bigint generated always as identity primary key,
  run_id           uuid not null references public.risk_engine_runs(id) on delete cascade,
  track_id         text not null references public.tracks(id) on delete cascade,
  image_id         text references public.images(id) on delete set null,
  level            public.risk_level not null check (level in ('high', 'critical')),
  t_in             time not null,
  t_out            time,
  dur_min          double precision not null,
  open_at_capture  boolean not null,
  censored_start   boolean not null,
  entry_code       text not null,
  d_in_m           double precision not null,
  dmin_m           double precision not null,
  t_dmin           time not null,
  codes            text[] not null default '{}',
  tags             text[] not null default '{}',
  crit_static_min  double precision not null,
  exit_to          public.risk_level,
  exit_code        text,
  reason           text not null
);
create index risk_events_run_idx on public.risk_events (run_id, level, t_in);

-- Bildirimler: seviye değişmese de üretilir (ENTER, BREACH, DEEPEN, RETRIGGER).
create table public.risk_notices (
  id        bigint generated always as identity primary key,
  run_id    uuid not null references public.risk_engine_runs(id) on delete cascade,
  track_id  text not null references public.tracks(id) on delete cascade,
  image_id  text references public.images(id) on delete set null,
  t         time not null,
  kind      text not null check (kind in ('ENTER', 'BREACH', 'BREACH_AT_BIRTH', 'DEEPEN', 'RETRIGGER')),
  change    text,
  code      text not null,
  d_m       double precision not null
);
create index risk_notices_run_idx on public.risk_notices (run_id, t);

-- Görüntü özeti: resmi seviye çekim anı durumudur; son 2 saatin tepesi bağlamdır.
create table public.image_risk (
  run_id                 uuid not null references public.risk_engine_runs(id) on delete cascade,
  image_id               text not null references public.images(id) on delete cascade,
  capture_time           time not null,
  level                  public.risk_level not null,
  level_raw              public.risk_level not null,
  held                   boolean not null,
  top_track_id           text references public.tracks(id) on delete set null,
  top_code               text,
  top_score              numeric(5,2),
  top_distance_m         double precision,
  n_tracks               integer not null,
  n_critical             integer not null,
  n_critical_active      integer not null,
  n_high_plus            integer not null,
  unregistered_level     public.risk_level not null,
  peak120_level          public.risk_level,
  peak120_track_id       text references public.tracks(id) on delete set null,
  peak120_code           text,
  peak120_start          time,
  peak120_end            time,
  n_critical_events_120  integer not null,
  recent_critical        boolean not null,
  brief_line             text not null,
  primary key (run_id, image_id)
);

alter table public.risk_engine_runs enable row level security;
alter table public.risk_timeline    enable row level security;
alter table public.risk_events      enable row level security;
alter table public.risk_notices     enable row level security;
alter table public.image_risk       enable row level security;

-- En son koşu. security_invoker: görünüm, çağıranın RLS yetkileriyle çalışır.
create view public.risk_latest_run with (security_invoker = true) as
  select * from public.risk_engine_runs order by created_at desc limit 1;

create view public.risk_timeline_latest with (security_invoker = true) as
  select t.* from public.risk_timeline t join public.risk_latest_run r on r.id = t.run_id;

create view public.risk_events_latest with (security_invoker = true) as
  select e.* from public.risk_events e join public.risk_latest_run r on r.id = e.run_id;

create view public.risk_notices_latest with (security_invoker = true) as
  select n.* from public.risk_notices n join public.risk_latest_run r on r.id = n.run_id;

create view public.image_risk_latest with (security_invoker = true) as
  select i.* from public.image_risk i join public.risk_latest_run r on r.id = i.run_id;
