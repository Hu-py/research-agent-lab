-- Run in a DEDICATED Supabase laboratory project. Never alter production tables.
create extension if not exists pgcrypto;

create table if not exists public.lab_frontier_runs (
  id uuid primary key,
  line_id text not null,
  strategy text not null check(strategy in ('balanced','novelty','feasibility')),
  status text not null check(status in ('candidate_for_human_review','needs_more_evidence')),
  model_calls integer not null check(model_calls >= 0),
  results jsonb not null,
  created_at timestamptz not null default now()
);
create index if not exists idx_frontier_line_created
  on public.lab_frontier_runs (line_id, created_at desc);
alter table public.lab_frontier_runs enable row level security;

create table if not exists public.lab_frontier_feedback (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.lab_frontier_runs(id) on delete cascade,
  reviewer_tag text not null,
  decision text not null check (decision in ('accept','revise','reject')),
  novelty integer not null check (novelty between 0 and 100),
  feasibility integer not null check (feasibility between 0 and 100),
  comment text not null default '',
  created_at timestamptz not null default now(),
  unique(run_id,reviewer_tag)
);
alter table public.lab_frontier_feedback enable row level security;

-- No anon/authenticated RLS policies. Only trusted server-side service-role
-- clients should have read/write access. Local feedback memory remains separate.
