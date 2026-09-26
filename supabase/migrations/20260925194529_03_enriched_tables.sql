create table public.report_claims (
  id               bigint generated always as identity primary key,
  report_id        bigint not null references public.field_reports(id) on delete cascade,
  location_type    public.location_type not null,
  location         extensions.geography(Point, 4326),
  zone_id          bigint references public.zones(id) on delete set null,
  vehicle_type     public.claim_vehicle_type,
  vehicle_count    integer check (vehicle_count > 0),
  color            text,
  behavior         public.claim_behavior,
  claim_type       public.claim_type not null,
  time_reference   text,
  is_verifiable    boolean not null default true,
  extractor_model  text,
  embedding        extensions.vector,
  created_at       timestamptz not null default now()
);
create index report_claims_report_id_idx on public.report_claims (report_id);
create index report_claims_zone_id_idx   on public.report_claims (zone_id);
create index report_claims_location_gix  on public.report_claims using gist (location);

create table public.track_segments (
  track_id        text not null references public.tracks(id) on delete cascade,
  t_start         time not null,
  t_end           time not null,
  distance_m      double precision not null,
  speed_mps       double precision not null,
  heading_deg     double precision,
  dist_to_base_m  double precision not null,
  zone_id         bigint references public.zones(id) on delete set null,
  is_stopped      boolean not null,
  primary key (track_id, t_start),
  check (t_end > t_start)
);
create index track_segments_zone_id_idx on public.track_segments (zone_id);
