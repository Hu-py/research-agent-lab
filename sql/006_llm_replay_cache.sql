-- 006: Optional server-only LLM response replay cache.
-- Run ONLY in the isolated Research Agent Lab Supabase project after 002/003/004.
-- Prompt bodies, titles, raw source documents and model API credentials are
-- NEVER stored here. Response JSON can include internal scientific hypotheses;
-- restrict this table to the authorized backend's privileged key.
create extension if not exists pgcrypto;

create table if not exists public.lab_llm_replay_cache (
  id uuid primary key default gen_random_uuid(),
  scope text not null,
  cache_key text not null check(cache_key ~ '^[0-9a-f]{64}$'),
  model_identity text not null,
  response jsonb not null check(jsonb_typeof(response) = 'object'),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  unique(scope,cache_key),
  check(expires_at > created_at)
);
create index if not exists lab_llm_replay_cache_expiry
  on public.lab_llm_replay_cache(expires_at);
alter table public.lab_llm_replay_cache enable row level security;
revoke all on table public.lab_llm_replay_cache from anon, authenticated;
-- Cleanup policy suggestion: periodically delete expired rows using a
-- trusted Supabase scheduled SQL job (never from public clients).
