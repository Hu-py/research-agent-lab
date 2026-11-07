# Feasibility-first research generation / 可执行性优先选题

## Why

Old Elo tournaments chose a relative winner even when **all** proposals
depended on unverified datasets. Merely increasing competition generations
cannot cure a missing dependent variable or unknown raw-data permission.

New paid GitHub experiments enable `FEASIBILITY_FIRST=true` by default.
The mock and existing generic CLI paths retain backward-compatible legacy
behavior unless `--feasibility-first` is supplied.

## Hard pre-tournament checks

`frontier/feasibility_gate.py` requires:
- At least one registered bibliographic paper reference.
- All referenced datasets actually listed in the approved snapshot, with
  **independently verified data access** (`access_verified=true`).
- Nonempty independently registered **field names** (not model-inferred names).
- A structured `execution_plan` describing study type (`empirical`),
  spatial/analytical unit, outcome, baseline, evaluation metric, split strategy,
  at least two procedural steps and exact per-dataset field mappings.
- Every declared outcome field must occur in the candidate's verified mapping.

This is a **metadata precheck**. It does NOT execute real data, inspect actual
sample distributions or certify published scientific novelty. Those require
later separately controlled tests. Literature quality remains provisional.

## Constructive feedback / 失败后的迭代修正

1. Generate Problem/Method/Data hypotheses with a structured plan.
2. Run the deterministic feasibility gate **before** Elo.
3. If two or more survive, enter the normal reversed-order tournament.
4. If only one survives, skip meaningless Elo and send it to Scientific Gate.
5. If none survives but registered access-verified datasets and columns exist,
   the Feasibility Reviser receives precise blocking codes and can generate
   an immutable child version, up to two attempts (configurable 0–3).
   Its field mappings are checked again; it cannot invent data.
6. If no access-verified dataset exists, **do not waste money endlessly
   requesting repairs**. Store all blocked hypotheses and deliver
   `minimum_viable_plan` with a specific next-action checklist and status
   `no_executable_candidates`. This is not misrepresented as an empirical
   study or a research recommendation.
7. Optional fixed-code synthetic pilot can run in supported network-resilience
   scenarios; it is a software sanity test, not external scientific proof.

A "guaranteed usable research paper" is impossible without requisite data,
test protocols and novel results. The system instead guarantees an **actionable
minimal next step**, and marks whether empirical execution is independently
supported. Hard provider call ceilings, secrets privacy and human-review
requirements remain unchanged.

## Data governance

CUSP metadata is never auto-approved. To enable owner-approved, redacted
metadata ingestion, an authorized administrator must configure:

- GitHub Actions Secret `TEAM_DATA_CATALOG_JSON` with separately reviewed
  schema-v1 fields, explicitly root and per-row approved.
- GitHub Actions Variable `USE_APPROVED_CATALOG=true`.

No original spreadsheet, custodians, raw traces or unapproved metadata are
included. This catalog bridge **never** sets `access_verified=true`; a
separate legal/data QA process must verify actual usable datasets.

## UI and storage

The new `feasibility` / `minimum_viable_plan` JSON objects are saved in
the existing isolated `lab_frontier_runs.results` JSONB, without a new SQL
migration. There is no Elo winner when no candidate passes the gate.
A fixed bilingual diagnostic is provided at no additional LLM cost in this
case; the original unsupported hypotheses remain in the audit lineage.
