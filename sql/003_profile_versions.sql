-- Execute in the SAME isolated Research Agent Lab Supabase test project.
-- This does not change the original Research Opportunity Workbench database.
create extension if not exists pgcrypto;

create table if not exists public.lab_profile_versions (
  id uuid primary key default gen_random_uuid(),
  bundle_id text not null,
  version integer not null check (version >= 1),
  evidence_hash text not null,
  status text not null check (status = 'provisional_not_official'),
  portrait jsonb not null,
  delta jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(bundle_id, version)
);
create index if not exists idx_lab_profile_versions_lookup
  on public.lab_profile_versions (bundle_id, version desc);
alter table public.lab_profile_versions enable row level security;

-- No public RLS policies. Only server-side privileged keys can read/write.
-- Store only explicitly approved public-safe research metadata and capability
-- summaries. Never raw team data or secret credentials.
