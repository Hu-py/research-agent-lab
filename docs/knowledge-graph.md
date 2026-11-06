# V0.5 — Research Knowledge Graph | 科研知识谱系

This relational graph is shared by the research problem, method capability, dataset asset and future opportunity perspectives.
The graph is provisional, evidence-linked and continuously versioned. An LLM claim is NOT automatically verified.

## Setup in isolated Supabase

Run [migration 004](../sql/004_research_knowledge_graph.sql) once in the SAME isolated Research Agent Lab Supabase project. Migration 003 must be installed first.

| Table | Content |
|---|---|
| kg_sources | Source-of-record paper, dataset, profile and agent-run IDs |
| kg_nodes | Questions, proposed methods, data assets, team/external publications and opportunities |
| kg_edges | Directed relations with epistemic status |
| kg_evidence | Which source supports an edge and with what evidence level |
| kg_node_versions | Immutable content revisions and linked profile versions |
| kg_opportunity_versions | Agent candidates, parent lineage and selected/archived outcomes |

The SQL enables RLS and revokes anon/authenticated grants. Only trusted server-side secrets may write.

The optional [migration 005](../sql/005_kg_embeddings_optional.sql) adds a 1536-dimensional pgvector table. DO NOT run it until a compatible embedding model has been selected; DeepSeek chat does not imply embeddings exist.

## GitHub Actions (explicit opt-in)

Open the manual Live Research Agent Lab workflow and use:

- evidence_source = team_evidence
- save_supabase = true
- save_knowledge_graph = true (new switch; defaults to false)
- max_generations = 0, max_papers = 4, max_pairs = 1 for the first paid experiment

The existing TEAM_EVIDENCE_JSON Secret must contain only explicitly approved metadata.
All six graph tables are preflighted before DeepSeek is called.

The portrait passes a bounded one-hop, source-linked graph context to its Research Line Selector. The latest approved profile and all candidate versions are written with stable deterministic IDs, so a retry does not create duplicate nodes. Every graph assertion is tagged provisional unless independently verified by a human.

Multi-table REST upserts are not one atomic SQL transaction. If interrupted, safely retry an identical batch; a future controlled database RPC can add transactional publishing.

## Inspect the graph

Local offline preview, with approved evidence and a portrait report:

    python -m research_agent_lab.knowledge_cli preview --evidence /private/team-evidence.json --portrait /private/portrait-report.json --line YOUR_LINE_ID

Read a bounded stored neighborhood on a trusted local workstation after configuring Supabase secrets:

    python -m research_agent_lab.knowledge_cli inspect --scope YOUR_BUNDLE_ID --line YOUR_LINE_ID

Supabase SQL Editor queries:

    select kind,count(*) from public.kg_nodes group by kind order by kind;
    select relation,epistemic_status,count(*) from public.kg_edges group by relation,epistemic_status;
    select candidate_key,generation,parent_candidate_keys,outcome from public.kg_opportunity_versions order by created_at desc limit 20;

## Evidence discipline and limits

Titles and paper abstracts do not prove team method mastery; model-generated method associations remain PROPOSES_METHOD rather than human_verified.
Dataset metadata does not grant raw data access. Public and individually approved internal metadata remain separate; sensitive contents/files are not stored.
Owned team outputs and external literature are distinct kinds. Unresolved newly retrieved OpenAlex references are reported, not silently misclassified as verified literature.
Original Research Opportunity Workbench production tables are untouched. No live team database import, schema execution, paid model run or automatic schedule has been performed in this update.
An embeddings generator, cross-field semantic retrieval, graph-learning evaluation and a curator UI are not yet built.

## Authorized, read-only Workbench synchronization (optional)

The existing team_evidence mode accepts an approved GitHub Secret snapshot. The new workbench_sync mode fetches approved research metadata directly from the original Render service on each MANUALLY TRIGGERED experiment. It does not access the production database from GitHub.

The original Workbench service must deploy the new GET /api/integrations/research-agent-lab/evidence endpoint and set:
- RESEARCH_EXPORT_ENABLED=true
- RESEARCH_EXPORT_LLM_SHARING_APPROVED=true, only after dataset owners approve sending filtered public metadata to external LLMs
- RESEARCH_EXPORT_TOKEN=unique randomly generated token at least 32 characters long

These are original Render SERVER environment variables, not client-side settings. This read-only endpoint emits verified team outputs, public dataset metadata and approved bibliography. It omits internal/restricted data, data holders, file paths, raw records, pending team works and credentials. It does not update production tables.

In the Lab repository configure:
- GitHub Actions Variable WORKBENCH_API_URL = HTTPS original Render API origin
- GitHub Actions Secret WORKBENCH_EXPORT_TOKEN = matching dedicated token

Keep the existing DeepSeek, Langfuse, OpenAlex and Supabase secrets. Do not reuse a general API_BEARER_TOKEN or team login session for this integration.

Then manually select evidence_source=workbench_sync, save_supabase=true, and save_knowledge_graph=true. The workflow verifies the export, rebuilds or reuses the evidence-led portrait, saves source-linked graph relations and runs bounded hypothesis competition. Only a private temporary runner file holds the export; team content is not uploaded as a public Actions artifact.

Deployment note: original Render services currently use feature branches with autoDeploy disabled; a code commit to main does not deploy this endpoint automatically. The actual service branch and a manual deployment must be reviewed separately.

This is manual sync-on-run, not a scheduled background collector.
