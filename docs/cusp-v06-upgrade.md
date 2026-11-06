# V0.6 — CUSP catalog, controlled multi-agent evolution and safe pilots

## What was actually inspected
The supplied **private CUSP data register** contains **28 catalog rows in six categories**:
public events 4, socioeconomic 3, urban functions/facilities 7, mobility/activity 7,
geographic/spatial units 4, and land-use/ecology 3.

The source register contains file-location indicators and custodians, and several
assets mention health, mobility signaling or individual identifiers.
**No raw workbook, custodians, contact fields or F-drive indicators were added
to this public GitHub repository.** The data rows are NOT automatically uploaded
to DeepSeek or Supabase. Local owner-review files were delivered separately.

Of 28 source records, 16 lack useful basic-information descriptions and 8
lack a recorded prior research use. The described columns are merely
**field clues**, not a verified schema, raw file access, or licenses.

## A. Authorized catalog metadata connection

The live `workbench_sync` endpoint previously returned 36 verified team outputs
but zero datasets. The new optional `use_approved_catalog` input can merge
**explicitly approved** CUSP metadata into the same EvidenceBundle *before*
the portrait and graph run. The original Render workbench database is unchanged.

1. Review private `CUSP_metadata_review_PRIVATE.json` and the companion
   owner-review spreadsheet from the conversation, on a controlled machine.
2. Both approval levels are required:
   - root `approved_by_data_owner=true`
   - each selected record `metadata_sharing_approved=true`
3. For each approved record, prepare its own **redacted** `approved_description`
   and optionally `approved_prior_research`. Do not rely on the original
   private description being safe for external model processing.
4. High-risk records (`risk_class=high_review`) MUST contain a specifically
   approved short description. Individual field names are prohibited.
   Any `verified_fields` for standard records require
   `verified_field_list=true`; otherwise use `[]`.
5. Run locally (do not commit these files):

   ```bash
   python -m research_agent_lab.catalog_cli \
     --review /private/CUSP_metadata_review_PRIVATE.json \
     --out /private/CUSP_APPROVED_MINIMAL.json
   ```

   This exports ONLY the explicitly approved records and only approved
   summary fields. It discards original descriptions, owner names, file paths
   and any unapproved rows. No model/API call is made.
6. Add `TEAM_DATA_CATALOG_JSON` in **GitHub → Settings → Secrets and
   variables → Actions → Repository secrets**, populated from this minimal
   file (never upload it to a public repository).
7. In Live Research Agent Lab choose:
   `evidence_source=workbench_sync`,
   `use_approved_catalog=true`, `save_supabase=true`,
   `save_knowledge_graph=true`.

All approved catalog assets remain `internal_metadata_approved`, with
`access_verified=false`. A model may propose their use but cannot assert
that files can be accessed or that any experiment has been run. 
If ALL records remain unapproved, the workflow correctly refuses the
catalog request before a paid model call; leave the switch false until
permissions are available.

## B. Controlled two-round hypothesis evolution

The cloud workflow now supports `max_generations=2`. This is the
**controlled two-round preset**: it requests two evolution generations
when the hard model-call budget permits, rather than letting the Supervisor
finish after the first tournament.

- Seed generation 0: 3 distinct perspectives (problem/method/data).
- With `max_pairs=3`, all three unordered pairs among seed candidates
  receive judges in BOTH candidate orders (six judge calls).
- Generation 1 and 2: independent scientific criticism, local revision and
  cross-perspective fusion. Parent candidates remain immutable, with
  `parent_ids` and version nodes in Supabase.
- Subsequent tournaments evaluate up to three strategically chosen pairs per
  generation, NOT every possible pair of the expanding 5/7-candidate pool.
  Elo is only relative LLM preference under these sampled comparisons.
- The first two iterations have a controlled minimum; if the strict call
  budget is exhausted, the Supervisor must end safely rather than exceed
  the cap.
- The max call ceiling for this preset is 55; it is a **call** ceiling, not
  a precise USD spend cap. Expected model costs exceed the previous
  `max_generations=0` demo. Start with sandbox/mock before a paid run.

The standard (`max_generations=0` or 1) behavior remains available.

## C. Executable toy pilot, no arbitrary LLM-generated code

The optional `synthetic_pilot=true` enables a fixed-code, deterministic
`toy_network_resilience_v1` software sanity experiment when the chosen line
is a network-resilience line:

- 3 generated **toy network** topologies × 2 artificial disturbance patterns
  × 3 artificial restoration settings × 6 nested edge-removal levels
- 108 scenario evaluations, 18 tracked scenario cells
- Network efficiency / connectivity response only; data-independent
- Outputs monotonicity checks, per-cell metrics and caveats
- No raw mobility, health, flood, station or other CUSP data are read
- No LLM-generated Python executes
- No original published UFRI or resilience-triangle implementation is tested
- A zero-monotonicity-violation result is largely true by construction and is
  **not scientific evidence of the H003 hypothesis**

This result is persisted under `lab_frontier_runs.results.pilot` when
enabled. If the selected research line is not appropriate for this fixed
network protocol, the pilot is marked skipped. It must never be used to
declare a hypothesis experimentally verified.

## D. Controlled comparison protocol

For a meaningful evaluation, run TWO settings against an identical
approved evidence snapshot, OpenAlex retrieval window and model/version:

- **Baseline A**: `max_generations=0, max_pairs=3`
- **Treatment B**: `max_generations=2, max_pairs=3`

Do not compare Elo values across independent runs as if they were
calibrated across runs. Instead compare documented novelty verification,
evidence coverage, researcher blind ratings, method feasibility,
unresolved critiques, and human-review outcomes. The current code does NOT
yet perform automated blinded external expert evaluation or train model
weights using reinforcement learning.

## E. Scientific safeguards

- Raw workbook and reviewed metadata not public.
- Explicit owner consent for every externalized metadata record.
- No method expertise inferred purely from titles.
- Data metadata and data access are distinct. `Dataset.access_verified` is
  false by default, and the science gate now programmatically prevents a
  model's `data_feasible=true` claim from overriding unverified access.
- Rank, critique, debate and toy pilot are NOT external validation.
- Existing Supabase 003/004 tables remain sufficient; NO new migration
  is required for V0.6.
