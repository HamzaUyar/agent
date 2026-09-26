create table public.analysis_runs (
  id                  uuid primary key default gen_random_uuid(),
  image_id            text not null references public.images(id) on delete cascade,
  status              public.run_status not null default 'running',
  detector_version    text,
  models              jsonb not null default '{}'::jsonb,
  overall_risk_level  public.risk_level,
  overall_risk_score  numeric(5,2),
  brief               text,
  error               text,
  created_at          timestamptz not null default now(),
  finished_at         timestamptz
);
create index analysis_runs_image_id_idx on public.analysis_runs (image_id);

create table public.detections (
  id           bigint generated always as identity primary key,
  run_id       uuid not null references public.analysis_runs(id) on delete cascade,
  label        public.vehicle_class not null,
  confidence   real not null check (confidence between 0 and 1),
  bbox_x       real not null,
  bbox_y       real not null,
  bbox_w       real not null check (bbox_w > 0),
  bbox_h       real not null check (bbox_h > 0),
  center_px_x  real not null,
  center_px_y  real not null,
  location     extensions.geography(Point, 4326),
  attributes   jsonb not null default '{}'::jsonb,
  vlm_agrees   boolean
);
create index detections_run_id_idx   on public.detections (run_id);
create index detections_location_gix on public.detections using gist (location);

create table public.track_matches (
  id            bigint generated always as identity primary key,
  run_id        uuid not null references public.analysis_runs(id) on delete cascade,
  detection_id  bigint references public.detections(id) on delete cascade,
  track_id      text references public.tracks(id) on delete cascade,
  distance_m    double precision,
  rank          integer check (rank >= 1),
  status        public.match_status not null,
  check (detection_id is not null or track_id is not null)
);
create index track_matches_run_id_idx       on public.track_matches (run_id);
create index track_matches_detection_id_idx on public.track_matches (detection_id);
create index track_matches_track_id_idx     on public.track_matches (track_id);

create table public.motion_analyses (
  match_id              bigint primary key references public.track_matches(id) on delete cascade,
  as_of_time            time not null,
  dist_to_base_now_m    double precision,
  dist_to_base_start_m  double precision,
  approach_rate_mps     double precision,
  total_distance_m      double precision,
  avg_speed_mps         double precision,
  recent_speed_mps      double precision,
  heading_deg           double precision,
  trend                 public.motion_trend not null default 'unknown',
  stop_count            integer,
  stop_minutes          integer,
  route_zone_ids        bigint[],
  path                  extensions.geography(LineString, 4326)
);

create table public.report_evaluations (
  id                  bigint generated always as identity primary key,
  run_id              uuid not null references public.analysis_runs(id) on delete cascade,
  claim_id            bigint not null references public.report_claims(id) on delete cascade,
  detection_id        bigint references public.detections(id) on delete set null,
  track_id            text references public.tracks(id) on delete set null,
  match_basis         text[] not null default '{}',
  spatial_distance_m  double precision,
  time_delta_min      double precision,
  verdict             public.report_verdict not null,
  reasoning           text,
  created_at          timestamptz not null default now()
);
create index report_evaluations_run_id_idx       on public.report_evaluations (run_id);
create index report_evaluations_claim_id_idx     on public.report_evaluations (claim_id);
create index report_evaluations_detection_id_idx on public.report_evaluations (detection_id);
create index report_evaluations_track_id_idx     on public.report_evaluations (track_id);

create table public.risk_assessments (
  id            bigint generated always as identity primary key,
  run_id        uuid not null references public.analysis_runs(id) on delete cascade,
  detection_id  bigint references public.detections(id) on delete cascade,
  track_id      text references public.tracks(id) on delete cascade,
  risk_level    public.risk_level not null,
  risk_score    numeric(5,2),
  factors       jsonb not null default '{}'::jsonb,
  reasoning     text,
  check (detection_id is not null or track_id is not null)
);
create index risk_assessments_run_id_idx       on public.risk_assessments (run_id);
create index risk_assessments_detection_id_idx on public.risk_assessments (detection_id);
create index risk_assessments_track_id_idx     on public.risk_assessments (track_id);

create table public.agent_steps (
  id          bigint generated always as identity primary key,
  run_id      uuid not null references public.analysis_runs(id) on delete cascade,
  step_no     integer not null,
  step_name   text not null,
  input       jsonb,
  output      jsonb,
  model       text,
  tokens_in   integer,
  tokens_out  integer,
  latency_ms  integer,
  created_at  timestamptz not null default now(),
  unique (run_id, step_no)
);
