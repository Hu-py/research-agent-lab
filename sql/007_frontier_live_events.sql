-- 007: Private, append-only frontier stage events for authenticated live replay.
-- Run only in the dedicated Research Agent Lab Supabase project after 002.
-- No FOREIGN KEY to lab_frontier_runs: stages exist before final run is saved.
create table if not exists public.lab_frontier_events (
  run_id uuid not null,
  step_index integer not null check(step_index >= 0 and step_index <= 100),
  stage text not null check(stage ~ '^[a-z_]{3,64}$'),
  details jsonb not null default '{}'::jsonb check(jsonb_typeof(details) = 'object'),
  recorded_at timestamptz not null default now(),
  primary key(run_id,step_index)
);
create index if not exists idx_lab_frontier_events_recent
  on public.lab_frontier_events(recorded_at desc);
create index if not exists idx_lab_frontier_events_run
  on public.lab_frontier_events(run_id,step_index asc);
alter table public.lab_frontier_events enable row level security;
revoke all on table public.lab_frontier_events from anon, authenticated;
-- Privileged server-only key. Do not publish rows via GitHub Actions artifacts.
-- Retention: a trusted administrator may prune stage events after 90 days.
