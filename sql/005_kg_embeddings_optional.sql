-- Optional semantic search layer; run only when an embedding model with
-- 1536 output dimensions has been selected. This migration has NO model calls.
create schema if not exists extensions;
create extension if not exists vector with schema extensions;

create table if not exists public.kg_embeddings (
  id uuid primary key default gen_random_uuid(),
  scope text not null,
  node_id uuid not null,
  embedding_model text not null,
  embedding extensions.vector(1536) not null,
  created_at timestamptz not null default now(),
  unique(scope,node_id,embedding_model),
  foreign key(scope,node_id) references public.kg_nodes(scope,id)
);
alter table public.kg_embeddings enable row level security;
revoke all on public.kg_embeddings from anon, authenticated;

-- When embeddings become available, add an index appropriate to the selected
-- number of vectors. Do not guess an embedding model from DeepSeek chat API.
