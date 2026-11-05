-- Run this only in a dedicated Supabase test project, using the SQL Editor.
-- No anon/authenticated access: the Python runner uses a server-side service-role key.
create extension if not exists pgcrypto;

create table if not exists public.lab_runs (
  id uuid primary key default gen_random_uuid(),
  snapshot_id text not null,
  mode text not null check (mode in ('single','fixed','adaptive')),
  model_calls integer not null check (model_calls >= 0),
  reserved_tokens bigint not null check (reserved_tokens >= 0),
  result jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists lab_runs_snapshot_time
  on public.lab_runs (snapshot_id, created_at desc);
alter table public.lab_runs enable row level security;

create table if not exists public.lab_feedback (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.lab_runs(id) on delete cascade,
  reviewer_tag text not null,
  decision text not null check (decision in ('accept','revise','reject')),
  novelty integer check (novelty between 0 and 100),
  feasibility integer check (feasibility between 0 and 100),
  rationale text not null default '',
  created_at timestamptz not null default now(),
  unique (run_id, reviewer_tag)
);
alter table public.lab_feedback enable row level security;

-- No broad RLS policies: only privileged server-side access by default.
-- Keep the service-role key out of repositories, frontends and CI logs.
