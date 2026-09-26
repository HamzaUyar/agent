-- Ticket 08: iddianın belirttiği yük durumu (görsel doğrulamayla karşılaştırılır).
alter table public.report_claims
  add column cargo text check (cargo in ('loaded', 'empty'));
