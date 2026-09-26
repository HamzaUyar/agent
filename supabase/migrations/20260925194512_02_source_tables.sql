create table public.bases (
  id        bigint generated always as identity primary key,
  name      text not null unique,
  location  extensions.geography(Point, 4326) not null
);

create table public.zones (
  id      bigint generated always as identity primary key,
  name    text not null unique,
  center  extensions.geography(Point, 4326) not null,
  area    extensions.geography(Polygon, 4326)
);

create table public.images (
  id            text primary key,
  file_path     text not null,
  width_px      integer not null check (width_px > 0),
  height_px     integer not null check (height_px > 0),
  capture_time  time not null,
  tl_lat double precision not null, tl_lon double precision not null,
  tr_lat double precision not null, tr_lon double precision not null,
  bl_lat double precision not null, bl_lon double precision not null,
  br_lat double precision not null, br_lon double precision not null,
  footprint     extensions.geography(Polygon, 4326),
  center        extensions.geography(Point, 4326),
  zone_id       bigint references public.zones(id) on delete set null,
  created_at    timestamptz not null default now()
);
create index images_zone_id_idx      on public.images (zone_id);
create index images_capture_time_idx on public.images (capture_time);
create index images_footprint_gix    on public.images using gist (footprint);

create table public.tracks (
  id          text primary key,
  first_seen  time,
  last_seen   time
);

create table public.track_points (
  track_id  text not null references public.tracks(id) on delete cascade,
  time      time not null,
  location  extensions.geography(Point, 4326) not null,
  primary key (track_id, time)
);
create index track_points_time_idx     on public.track_points (time);
create index track_points_location_gix on public.track_points using gist (location);

create table public.field_reports (
  id          bigint generated always as identity primary key,
  time        time not null,
  source      public.report_source not null,
  text        text not null,
  created_at  timestamptz not null default now()
);
create index field_reports_time_idx on public.field_reports (time);
