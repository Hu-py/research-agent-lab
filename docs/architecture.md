# Architecture and integration contract

## Scope

This repository is an independent experiment for hypothesis generation.
The source Research Opportunity Workbench stays untouched:

- backend/scientific_tournament.py: independent problem/method/data roles and checks
- backend/research_evolution.py: multi-stage scientific hypothesis revision
- backend/research_budget.py: atomic daily limits
- backend/profile_database.py: database-grounded team profile, approved papers and dataset *metadata*

V0.1 deliberately transfers **no** production code containing implicit database
connections or model vault access. Instead it requires a frozen approved_export
snapshot and validates evidence IDs before accepting proposals.

## Runtime

LangGraph is the orchestration state graph: seed -> reviewer -> optional
critic -> three revisions -> reviewer -> [repeat/finish].

- single: one integrated proposal then one independent review.
- fixed: three independent proposals and exactly N critique/revision rounds.
- adaptive: the same three agents, with early stopping according to quality,
  reviewer revision flag and minimum scoring improvement.

The judge is an LLM. Its numeric assessments are exploratory indicators, **not**
proof of originality or scientific merit. Evidence ID references are mechanically
checked but paper claims remain unverified. Human review is always required.

## Model/observability/storage

- DeepSeek API: HTTPS chat/completions, response_format=json_object,
  default deepseek-flash, thinking disabled for stable structured output.
- Langfuse: per-LLM-call generation observations using the modern SDK;
  trace content is **redacted** to IDs/role/response-key summaries by default.
- Supabase: optional --persist inserts into isolated public.lab_runs only.
  The privileged key must be restricted to a trusted server environment.
- No key or outbound network call when --mock is selected and trace env is empty.

## Limitations and next milestones

- No OpenAlex ingestion, autonomous topic queue, scheduler, or frontend in V0.1.
- No production database access or migration from the main repository.
- No truly independent multi-model reviewers, calibrated human scores, or
  learned adaptive policy yet.
- MAX_MODEL_CALLS and MAX_RESERVED_TOKENS are **per-run** and conservative.
  80 papers/day and shared daily model quotas require a durable atomic budget
  service before enabling scheduled execution.
- Avoid deploying uncontrolled autonomous loops with real keys. All runs are
  bounded by maximum rounds and model-call count.

## Production export contract

Export **only human-approved** paper bibliographic metadata/abstracts and
non-sensitive **dataset metadata** from the source workbench. Mark provenance
approved_export, preserve original trusted IDs, and ensure scientific context
cannot expose private record-level data. Data classified restricted must not
enter the snapshot. Do not reuse service-role credentials from production.
