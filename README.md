# Research Agent Lab

Independent multi-agent research experiment using **LangGraph + DeepSeek + Langfuse + Supabase**. This public repository is separate from [Research Opportunity Workbench](https://github.com/Hu-py/research-opportunity-workbench); the original application's code and data are not changed.

> **V0.1: runnable orchestration prototype.** Synthetic examples validate software wiring, not scientific novelty. Real model runs require your own DeepSeek API key and a human-approved, privacy-filtered evidence snapshot.

## What exists

- Three comparable workflows on **exactly the same** frozen paper/portrait/data evidence: single Agent, fixed multi-Agent rounds, dynamically stopped multi-Agent rounds.
- Independent problem / method / data hypothesis generators; adversarial reviewer; iterative revision; independent numeric evaluation.
- Programmatically reject unknown paper/dataset references, invalid model scores and incomplete critiques.
- Per-run hard caps on model calls / conservatively reserved tokens / paper input count.
- Optional Langfuse generation traces, **redacted by default**.
- Optional isolated Supabase run storage with SQL schema.
- Offline deterministic mock mode, unit tests and GitHub Actions CI.

## 1. Install (Python 3.11+)

    git clone https://github.com/Hu-py/research-agent-lab.git
    cd research-agent-lab
    python -m venv .venv
    source .venv/bin/activate
    pip install -e '.[dev,observability]'

For Windows, activate with .venv\Scripts\activate.

## 2. Run offline smoke test (no keys)

    python -m research_agent_lab.cli --snapshot examples/synthetic_snapshot.json --mode all --mock --max-rounds 2 --out outputs/mock-compare.json
    python -m pytest -q

Modes: single, fixed, adaptive, all. The mock outputs are fabricated and clearly marked.

## 3. Run with real DeepSeek

Create .env from .env.example and fill DEEPSEEK_API_KEY. To use the default Langfuse Cloud tracing, fill both LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY (optional). **Never commit .env.**

Prepare a JSON snapshot with the structure of examples/synthetic_snapshot.json, replacing the synthetic paper citations and metadata with real **human-approved** evidence. Set provenance to approved_export.

    python -m research_agent_lab.cli --snapshot /path/to/approved_snapshot.json --mode adaptive --max-rounds 3 --out outputs/real-run.json

By default, DEEPSEEK_MODEL=deepseek-flash. Set DEEPSEEK_MODEL=deepseek-v4-pro for more advanced evaluation. The implementation uses current DeepSeek model identifiers, not retired deepseek-chat/reasoner aliases.

## 4. Optional Supabase test project

Create a **separate** Supabase test project, execute sql/001_lab_tables.sql in its SQL editor, and set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in local .env. Then run with --persist. This flag explicitly writes the **result** JSON to public.lab_runs. Never expose the service-role key in a client/browser. Supabase is not required for local runs.

## 5. Interpret the results

The JSON output includes agent candidates, objections, score trajectory, final selected hypothesis, evidence IDs, invocation counts, token reservations and (if provided by DeepSeek) real input/output token usage. All ideas retain novelty_verified=false, data_access_verified=false and human_review_required=true.

### Important scope limits

V0.1 **does not yet** connect live OpenAlex, automatically read the original Supabase database, schedule daily 80-paper jobs, implement human feedback-driven learning, or deploy a web UI. Those require safe integration and experimental evaluation, not an implicit side effect of running this prototype. The current MAX_MODEL_CALLS ceiling is **per run**, not an atomic daily budget.

Full integration and security notes: docs/architecture.md.


---

# V0.2 — Profile-grounded frontier research laboratory

**Preserves the V0.1 single / fixed / adaptive comparison workflows.**

The new command is research-frontier. It implements:

1. Knowledge discovery: optional LLM-planned OpenAlex retrieval from research
   portrait and dataset metadata. Independent Agent jurors screen literature,
   with a third adjudicator resolving disagreements.
2. Hypothesis competition: 3 independent perspectives, similarity-guided
   pairings, two-sided Elo debates and versioned refine/fuse candidates.
3. Scientific validation: falsifiability review, registered-dataset checks,
   baselines and ablations; optional fixed-code grouped-holdout CSV pilot.
4. Experience evolution: persistent local memory of research and pilot failures,
   with UCB policy updates from subsequent HUMAN feedback.

A Supervisor decides whether to evolve, expand, rollback or verify within a
bounded LangGraph. It does not bypass scientific review.

## Install and run a no-key mock experiment

    git clone https://github.com/Hu-py/research-agent-lab.git
    cd research-agent-lab
    python -m venv .venv
    source .venv/bin/activate
    pip install -e '.[dev,observability]'
    python -m research_agent_lab.frontier.cli run \
      --snapshot examples/synthetic_snapshot.json \
      --mock --max-generations 1 \
      --memory outputs/frontier-memory.sqlite \
      --out outputs/frontier-demo.json
    python -m pytest -q

This mock example uses fabricated papers and deterministically fabricated
research outputs: it verifies engineering behavior ONLY. The output contains
all versions, pairwise decisions, supervisor steps and the full research
package. Langfuse does not require configuration for offline tests.

## Real DeepSeek scientific exploration

Copy .env.example to a local .env file, and add DEEPSEEK_API_KEY. Optionally
add LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY for redacted Agent traces.

Prepare an approved_export JSON research snapshot with team research line,
dataset FIELD METADATA, and approved bibliographic records (see example
snapshot). Then run:

    python -m research_agent_lab.frontier.cli run \
      --snapshot /path/to/approved_snapshot.json \
      --max-generations 1 --out outputs/frontier-real.json

You may also opt into LLM-planned bibliographic discovery by setting
OPENALEX_API_KEY and adding --discover, optionally followed by
--source-registry examples/source_registry.json. This registry is merely a
small example; a curated export from the existing academic source registry
is preferable. For live OpenAlex discovery, the input snapshot may have an
empty papers array and must NOT be synthetic.

For a numeric local dataset, optionally add
--pilot-manifest /path/to/pilot-manifest.json (format under examples/). The
fixed code checks group-held-out baseline vs a simple one-feature regression.
No LLM-written Python code is executed. If no approved local CSV is provided,
the system produces an experimental PLAN rather than claiming execution.

## Record human feedback only after the automatic pipeline

Retrieve the run_id from the JSON and use:

    python -m research_agent_lab.frontier.cli feedback \
      --run-id YOUR_RUN_ID --reviewer-tag expert-01 \
      --decision revise --novelty 70 --feasibility 60 \
      --comment "The proposed ablation needs work"

This appends experience and updates the next run's strategy selection.
It is preference/bandit optimization, NOT neural reinforcement learning.

## Isolated Supabase and Langfuse

For Supabase, run sql/002_frontier_tables.sql in an independent test project.
Use local SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY and run --persist.
It stores only a restricted result summary, never raw pilot rows.

Langfuse observations are metadata-only by default for privacy; detailed
Agent debate is available in the local JSON output. Never commit live keys,
raw sensitive research data or private traces to this public GitHub repository.

**Limitations:** Supabase is an opt-in result sink, while experience memory is
currently local SQLite; there is no cross-machine memory sync, scheduled paper
ingestion, scientifically validated novelty or final human-review GUI yet.
Source validation checks bibliographic metadata and field IDs, not the truth
of every scientific claim. Per-run limits are not a shared daily quota.
See docs/frontier-methods.md for the methods and evaluation protocol.


---

## V0.3: GitHub Actions live experiment (explicit opt-in)

The optional, **manually triggered** [Live Research Agent Lab workflow](.github/workflows/live-frontier.yml)
runs real DeepSeek + OpenAlex inference, records a single nested Langfuse trace,
and can store the result in a dedicated Supabase project.

- No real API is invoked by the standard push/PR CI.
- A preflight validates configured secrets and existing Supabase tables **before**
  charging DeepSeek.
- The initial input is a **generic, PUBLIC research profile** and is not the
  user's actual database-derived team profile.
- A separate **approved_secret** mode accepts an approved metadata-only
  snapshot via a GitHub Actions Secret named RESEARCH_SNAPSHOT_JSON. No private
  report artifact is uploaded in this mode.
- Old service_role JWT and new sb_secret_* keys are supported. New keys use
  only the apikey header, never Authorization Bearer.
- Existing run/feedback summaries are restored from Supabase for the same
  research line, so the strategy selection can improve across cloud executions.
- No background deployment, automatic paid schedule or unbounded agent loop.

**Start here:** [Cloud setup in Chinese](docs/live-cloud-setup.md).

**Scientific caveat:** This is a technical execution pipeline, not a
validated proof of better research ideas. LLM pairwise preferences and Elo
scores are not independent scientific validation.


---

## V0.4: Evidence-first team research portraits

The new portrait engine lets you reconsider a team's research expertise from
its **verified past output records**, public-safe dataset metadata and separate
external literature—not just the keywords in its old profile.

- Scientific Curator -> adversarial Critic -> corrected research lines -> next
  question Selector -> existing four-layer Research Frontier.
- Every output is cited by its original verified achievement/dataset ID.
- Skill claims from titles are marked inferential; missing dataset access is
  explicit. All unassigned achievements must be acknowledged.
- Profile versions and changes are saved to the isolated Supabase table
  lab_profile_versions, preserving the old version and NEVER updating the
  original workbench's official team profile.
- The next real Actions run can select evidence_source=team_evidence after the
  operator provides approved TEAM_EVIDENCE_JSON metadata (not raw datasets).
- Research generation remains manually triggered; new team evidence must be
  re-exported and the Secret updated before it can alter the profile.

**The original Render database is not externally reachable, so V0.4 has NOT
yet ingested its current live portrait.** Its source code and public bibliographic
seed were inspected; neither should be represented as live team database rows.

1. Apply [SQL migration 003](sql/003_profile_versions.sql) to the isolated
   Supabase project.
2. Follow [the evidence-first portrait guide](docs/evidence-first-portrait.md)
   for an authorized read-only export.
3. Register TEAM_EVIDENCE_JSON under the GitHub Actions repository Secrets.
4. Manually run Live Research Agent Lab (manual) with team_evidence selected.

No private team portrait is ever uploaded to a public CI artifact. During
a team_evidence run, output is stored only in the access-controlled Supabase
research lab tables, and sensitive temporary files are deleted.

---

## V0.5 — Four-perspective research knowledge graph

An evidence-grounded knowledge graph now links historic research problems, proposed methods, dataset assets, source publications and versioned future opportunities.

- Apply [SQL 004](sql/004_research_knowledge_graph.sql) to the isolated Supabase project (requires 003).
- To enable cloud storage, choose team_evidence, save_supabase=true, save_knowledge_graph=true in the manual GitHub Actions workflow. Default is false to avoid breaking existing runs.
- Source references, edge evidence, epistemic status, immutable node versions and candidate ancestry are preserved.
- The portrait-based next-topic selector receives bounded local graph neighborhoods as its input.
- [SQL 005](sql/005_kg_embeddings_optional.sql) is optional. Wait until a 1536-dimensional embedding model is actually configured.

See [knowledge graph instructions](docs/knowledge-graph.md) for setup, queries and privacy safeguards.

No Supabase migration or paid AI call is automatically executed as part of this commit.

### Optional direct metadata sync from the original Workbench

After deploying the dedicated read-only Render export endpoint, choose evidence_source=workbench_sync in the manual GitHub Actions workflow. Set WORKBENCH_API_URL as an Actions Variable and WORKBENCH_EXPORT_TOKEN as a Secret, with the matching RESEARCH_EXPORT_TOKEN and metadata-sharing opt-in on the original Render backend. This avoids pasting the full TEAM_EVIDENCE_JSON on every run. No raw dataset rows or production database credentials are copied to the Lab.

See [integration instructions](docs/knowledge-graph.md) for the deployment and approval details.


### Diagnosing cloud connections before spending on DeepSeek

Use the [Verify Research Lab Connections (no AI calls)](.github/workflows/verify-connections.yml)
workflow from GitHub Actions. It reads the SUPABASE_URL from **Repository
Secrets OR Repository Variables**, checks existing 002/003/004 tables, and
optionally validates the original Render Workbench metadata-export endpoint.
It performs **no paid DeepSeek calls, OpenAlex requests, Langfuse writes or
Supabase writes**.

A missing SUPABASE_URL now reports SUPABASE_URL_NOT_SET separately from a
database connection URI, dashboard URL, or URL with extra path/query fields.
Expected URL format is https://YOUR_PROJECT_REF.supabase.co (the Supabase
Project URL from Settings > Data API). Do not paste the PostgreSQL
connection string, dashboard URL, /rest/v1 endpoint, quotes or placeholders.

### Langfuse tracing: safe SDK singleton and no-model-call export smoke test

The live runner's initial auth check must never instantiate Langfuse(tracing_enabled=False). The Langfuse Python ResourceManager is keyed by Public Key, and the disabled singleton can cause later get_client() observations to be no-ops despite successful auth. The check now uses the exact same tracing-enabled get_client() singleton as TracedModel.

Run [Verify Research Lab Connections (no AI calls)](.github/workflows/verify-connections.yml) with check_langfuse=true and emit_langfuse_smoke_trace=true. This records one synthetic span named research-agent-lab-trace-smoke and flushes it. It does not call DeepSeek or upload private research. Find it under Tracing in the Langfuse US project after ingestion.

auth_check() tests only credentials, not span upload. A successful synthetic smoke trace verifies the exporter. Historical runs with missing traces cannot be retroactively made visible; the complete research results remain in isolated Supabase tables.

---

## V0.6 — owner-reviewed CUSP catalog + controlled two-round evolution

A private CUSP register (28 assets / six categories) informed the design; the
file itself, custodians and sensitive source metadata are **not** stored here.

- `catalog_bridge.py` and `catalog_cli.py` accept only explicit data-owner and
  per-record approvals, export minimal sanitized metadata, and merge approved
  dataset refs into existing workbench_sync evidence before the portrait.
- `max_generations=2` requests two bounded critique/refine/fuse rounds.
  Choose `max_pairs=3` for all seed-pair comparisons; tournament parents and
  match results are retained. This uses more paid LLM calls.
- `synthetic_pilot=true` can execute 108 toy network simulations (not real
  scientific validation), and the access guard prevents registered metadata
  from being mistaken for an accessible dataset.
- No database schema changes required beyond existing 003/004.

[Full configuration, caveats and paired-run study design](docs/cusp-v06-upgrade.md).


---

## V0.7: optional DeepSeek response replay and no-AI A/B audit

- **Recovery:** [SQL 006](sql/006_llm_replay_cache.sql) adds a server-only
  per-request response cache (opt-in, off by default). It prevents *some*
  duplicate provider calls when a failed run is retried with identical
  prompts, while preserving logical model-call ceilings.
- **Comparison:** [Compare Two Frontier Experiments](
  .github/workflows/compare-frontier.yml) reads two run UUIDs and produces
  a numeric, evidence-aligned audit without extra LLM calls. It explicitly
  blocks unequal registered paper sets or source snapshots and does not
  equate Elo with objective scientific quality.
- **Governance:** No CUSP source files, original prompts, raw metadata or
  model credentials were committed. Cached JSON outputs remain sensitive
  and restricted to privileged Supabase server access.
- **Limitations:** Exact request replay ≠ full LangGraph checkpointing. The
  cross-run audit is descriptive, not causal or external scientific validation.

[Read V0.7 setup and scientific limitations](docs/v07-recovery-and-ab.md).


## V0.9: authenticated live research-stage timeline

After executing [SQL 007](sql/007_frontier_live_events.sql), enable `stream_live_events=true` in the live workflow to record **real LangGraph node completions** in a private, append-only table. The Research Atlas workbench can display them during execution after secure Vercel configuration. [Setup instructions](docs/v09-live-events.md).


## V1.0 — workbench-triggered research and paired Chinese/English report

The Research Atlas Next.js workbench can dispatch this pre-existing GitHub
Actions workflow through an **administrator-only** server-side endpoint,
using a repository-scoped GitHub PAT. Only validated input values are
submitted; no research content, CUSP data, model keys or Langfuse secrets
are sent from the browser.

[Live Research Agent Lab](.github/workflows/live-frontier.yml) has 10 inputs
(maximum supported by GitHub workflow_dispatch). It now always writes results
to the **isolated Supabase lab** (`SAVE_SUPABASE=true`) and exposes
`bilingual_report` (enabled by default) instead of the older
`save_supabase` input. The bilingual editor is optional and makes at most
one additional bounded DeepSeek call **after** the scientific gate, preserving
six zh/en scientific summary fields and uncertainty. If editorial generation
fails, the scientific run still saves and the report explicitly says that
the translation was unavailable.

**Bilingual summary is not additional scientific evidence.** The raw
candidate, pairwise juror and method review are unchanged and remain in
Supabase; the translation does not upgrade feasibility, novelty or
experimental verification. Results can be read in the new
Research Atlas `多智能体博弈回放` page.

The server-only setup and permissions are documented in the Workbench repo:
[Game replay / Run launch documentation](
https://github.com/Hu-py/research-opportunity-workbench/blob/main/docs/research-agent-game-replay.md).
