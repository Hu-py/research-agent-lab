-- 004: Evidence-grounded research knowledge graph.
-- Run ONLY in the isolated research-agent-lab Supabase project.
-- This migration creates new tables, and does not modify existing profile/run data.
create extension if not exists pgcrypto;

create table if not exists public.kg_sources (
  id uuid primary key,
  scope text not null,
  source_key text not null,
  kind text not null check (kind in
    ('team_output','dataset_metadata','external_paper','portrait_version','frontier_run')),
  reference text not null default '',
  label text not null,
  source_hash text not null,
  provenance jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (scope, source_key),
  unique (scope, id),
  check (jsonb_typeof(provenance) = 'object')
);

create table if not exists public.kg_nodes (
  id uuid primary key,
  scope text not null,
  node_key text not null,
  kind text not null check (kind in
    ('research_problem','research_method','data_asset','team_output','external_paper','research_opportunity')),
  label text not null,
  description text not null default '',
  attributes jsonb not null default '{}'::jsonb,
  epistemic_status text not null default 'proposed' check (epistemic_status in
    ('proposed','title_inferred','described','human_verified','rejected')),
  source_hash text not null,
  first_seen_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (scope, node_key),
  unique (scope, id),
  check (jsonb_typeof(attributes) = 'object')
);
create index if not exists kg_nodes_scope_kind on public.kg_nodes(scope,kind);
create index if not exists kg_nodes_search on public.kg_nodes using gin
  (to_tsvector('simple', label || ' ' || description));

create table if not exists public.kg_edges (
  id uuid primary key,
  scope text not null,
  edge_key text not null,
  from_node uuid not null,
  to_node uuid not null,
  relation text not null check (relation in
    ('ADDRESSES','BASED_ON_OUTPUT','CONSIDERS_LITERATURE','PROPOSES_METHOD',
     'POTENTIALLY_USES_DATA','EVOLVED_FROM','CITES_LITERATURE',
     'REQUIRES_DATA','EXTENDS_PROBLEM')),
  epistemic_status text not null default 'proposed' check (epistemic_status in
    ('proposed','inferred','described','human_verified','rejected')),
  rationale text not null default '',
  source_hash text not null,
  created_at timestamptz not null default now(),
  unique (scope,edge_key),
  unique (scope,id),
  foreign key (scope,from_node) references public.kg_nodes(scope,id),
  foreign key (scope,to_node) references public.kg_nodes(scope,id),
  check (from_node <> to_node)
);
create index if not exists kg_edges_outgoing on public.kg_edges(scope,from_node,relation);
create index if not exists kg_edges_incoming on public.kg_edges(scope,to_node,relation);

create table if not exists public.kg_evidence (
  id uuid primary key,
  scope text not null,
  evidence_key text not null,
  edge_id uuid not null,
  source_id uuid not null,
  evidence_level text not null check (evidence_level in
    ('title_only','abstract','fulltext','catalogue_metadata','agent_inferred','human_reviewed')),
  statement text not null default '',
  locator text not null default '',
  generated_by text not null default 'portrait_materializer',
  recorded_at timestamptz not null default now(),
  unique (scope,evidence_key),
  foreign key (scope,edge_id) references public.kg_edges(scope,id),
  foreign key (scope,source_id) references public.kg_sources(scope,id)
);
create index if not exists kg_evidence_edge on public.kg_evidence(scope,edge_id);

-- History is APPEND ONLY: a new evidence digest creates a new version.
create table if not exists public.kg_node_versions (
  id uuid primary key,
  scope text not null,
  version_key text not null,
  node_id uuid not null,
  portrait_version_id uuid references public.lab_profile_versions(id),
  evidence_hash text not null,
  payload jsonb not null,
  change_reason text not null,
  created_at timestamptz not null default now(),
  unique(scope,version_key),
  foreign key (scope,node_id) references public.kg_nodes(scope,id),
  check(jsonb_typeof(payload)='object')
);
create index if not exists kg_node_versions_node on public.kg_node_versions(scope,node_id,created_at desc);

-- Each tournament candidate has an immutable version row; parent refs are
-- preserved as local run candidate IDs, and EVOLVED_FROM edges link resolved nodes.
create table if not exists public.kg_opportunity_versions (
  id uuid primary key,
  scope text not null,
  opportunity_node_id uuid not null,
  run_id uuid not null references public.lab_frontier_runs(id),
  candidate_key text not null,
  generation integer not null check(generation >= 0),
  parent_candidate_keys text[] not null default '{}',
  outcome text not null check (outcome in ('candidate','archived','selected')),
  elo numeric(8,2),
  payload jsonb not null,
  created_at timestamptz not null default now(),
  unique(scope,run_id,candidate_key),
  foreign key (scope,opportunity_node_id) references public.kg_nodes(scope,id),
  check(jsonb_typeof(payload)='object')
);
create index if not exists kg_opp_versions_run on public.kg_opportunity_versions(scope,run_id);

-- No anonymous access; privileged server requests only. Never expose
-- service role / sb_secret_* in a browser or public repository.
alter table public.kg_sources enable row level security;
alter table public.kg_nodes enable row level security;
alter table public.kg_edges enable row level security;
alter table public.kg_evidence enable row level security;
alter table public.kg_node_versions enable row level security;
alter table public.kg_opportunity_versions enable row level security;

revoke all on table
  public.kg_sources,public.kg_nodes,public.kg_edges,
  public.kg_evidence,public.kg_node_versions,public.kg_opportunity_versions
from anon, authenticated;
