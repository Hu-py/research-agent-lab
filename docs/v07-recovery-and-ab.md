# V0.7: Exact-response recovery and evidence-aligned A/B evaluation

The upgrade is **opt-in** and designed for the isolated Research Agent Lab
Supabase project. Existing CUSP owner-reviewed data, portrait version records,
knowledge-graph tables and the original Render workbench are unchanged.

## 1. Optional replay cache after cloud failures

Apply [SQL migration 006](../sql/006_llm_replay_cache.sql) **only** to the
isolated Research Agent Lab Supabase project. Do not run it on the original
workbench Postgres database.

The new table \`lab_llm_replay_cache\` contains:
- SHA-256 of the exact model name/endpoint/output limit, complete role/system
  prompt and model request payload, and an explicit namespace.
- The returned JSON **response** (private scientific content; protect it).
- Creation and expiry timestamps, default 30-day TTL.
- **No raw prompts**, source documents or credentials are stored in its rows.

The table has RLS enabled and no anon/authenticated grants. Only the trusted
backend's \`sb_secret_*\` / privileged service key can write it. Cached model
outputs still require private data governance and should not be exported
into public GitHub Artifacts. Expired rows should be periodically purged by
a trusted database admin. No public browser client may read these records.

Start with the FREE
[Verify Research Lab Connections](../.github/workflows/verify-connections.yml)
workflow and choose \`check_llm_replay_cache=true\` to confirm table access
without any paid inference. Then use the
[Live Research Agent Lab](../.github/workflows/live-frontier.yml) manual inputs:

| Input | Setting |
|---|---|
| \`reuse_llm_cache\` | false by default; enable only after SQL 006 and free check |
| \`replay_namespace\` | stable custom ASCII identifier for retries, e.g. \`trial_a_v1\` |
| \`save_supabase\` | must be true |
| \`evidence_source\` | \`workbench_sync\` or \`team_evidence\` for team runs |

A rerun can reuse **exactly matching** DeepSeek JSON responses, including
portrait/research selector responses, juror reviews and candidate proposals.
The wrapper still enforces the same **logical-call limit** as the normal
experiment. It separately records actual provider calls and cache hits.
The model/endpoint/output limit are bound into each key; a different prompt,
research context, evidence summary or version of these response contracts is
**not** a hit. All preflight checks happen before spending on LLM inference.

**Important:** this is not full LangGraph state checkpoint/resume or arbitrary
in-flight call recovery. It cannot replay a response lost before successful
storage, and it does not guarantee zero charges when a network write fails.
It is limited to byte-for-byte identical model requests. Scientific
comparison experiments must use **distinct namespaces** (e.g. \`baseline_A\`
and \`treatment_B\`) to avoid unintentionally reusing judgments across arms.
Caching the same uncertain LLM output does not verify its correctness.

## 2. Read-only A/B descriptive audit

The [Compare Two Frontier Experiments (no AI calls)](
../.github/workflows/compare-frontier.yml) manual workflow accepts two
\`lab_frontier_runs.id\` UUIDs. No additional SQL migration is required.

First run **Baseline** with \`max_generations=0\` and \`max_pairs=3\`, then
run **Treatment** with \`max_generations=2\`, \`max_pairs=3\` and the
same approved evidence. Distinct replay namespaces are recommended.

Future runs store \`comparison_context\` including selected profile snapshot,
model name, registered dataset IDs, retained screened paper IDs, max papers,
tournament budget and configured generations. The audit then reports:

- "Aligned for descriptive comparison" only when these recorded evidence
  and configuration controls match; otherwise it explicitly **blocks**.
- Total candidates, generations, matches, position disagreements, screened
  and retained papers, unresolved screening issues, and evidence limitations.
- Actual provider calls versus logical model requests and replay cache hits.
- Scientific feasibility/novelty and data-permission flags.

The GitHub Summary shows **only aggregate numbers**. It does not upload the
raw report, private candidate text, CUSP metadata, prompts or source papers.
A trusted analyst can run locally:

\`\`\`bash
research-compare --baseline-id UUID_A --treatment-id UUID_B \
  --out /private/descriptive-ab.json
\`\`\`

Historical V0.6 runs without comparison context remain queryable, but
the strict audit marks them **not aligned**. Matching evidence IDs and
model names alone cannot guarantee comparable retrieval ranking or
independent judgments. These audits are **descriptive**, NOT causal effect
estimates. Never compare Elo ratings across runs as if calibrated.
No external paper novelty checking, human blind scoring or reinforcement
learning weight updates are performed by this module.

## 3. Recommended experiment order

1. Keep all unapproved CUSP data out of cloud input.
2. Run free connections with approved catalog and replay-table checks as
   appropriate; do not activate the catalog switch if no assets are approved.
3. Run a modest \`max_generations=0\` baseline, then a
   \`max_generations=2\` treatment with the same authorized metadata.
4. Run the no-AI A/B audit. If paper IDs differ, freeze an evidence snapshot
   before claiming aligned results. Both settings still require human
   judgment of research quality and method novelty.
5. Use the replay cache only when recovery is warranted, not as a substitute
   for a controlled comparative experiment.

The existing SQL 003/004 schema and original team profile are untouched.
