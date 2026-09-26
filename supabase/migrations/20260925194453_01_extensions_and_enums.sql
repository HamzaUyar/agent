create extension if not exists postgis with schema extensions;
create extension if not exists vector with schema extensions;

create type public.vehicle_class      as enum ('car', 'van', 'truck', 'bus');
create type public.claim_vehicle_type as enum ('car', 'van', 'truck', 'bus', 'heavy', 'light', 'unknown');
create type public.report_source      as enum ('official', 'third_party');
create type public.location_type      as enum ('coordinate', 'zone', 'none');
create type public.claim_behavior     as enum ('stationary', 'moving', 'transit', 'approaching', 'receding', 'normal_traffic', 'unknown');
create type public.claim_type         as enum ('observation', 'friendly_claim', 'threat_warning', 'rumor', 'irrelevant');
create type public.run_status         as enum ('running', 'done', 'failed');
create type public.risk_level         as enum ('low', 'medium', 'high', 'critical');
create type public.match_status       as enum ('matched', 'detection_without_track', 'track_without_detection');
create type public.motion_trend       as enum ('approaching', 'receding', 'stationary', 'passing', 'unknown');
create type public.report_verdict     as enum ('consistent', 'contradicts', 'unverifiable', 'irrelevant');
