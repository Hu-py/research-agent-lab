# V2.2 — Contract → Agents → Independent Evaluation → Repair / Reroute

**Scope: real nested LangGraph control logic, synthetic offline driver only.**
No DeepSeek, OpenAlex, Supabase, raw CUSP datasets, or uncontrolled executors
are invoked by the V2.2 dry-run. The current paid V1 workflow and Vercel
launch button remain unchanged.

## 1. Why this differs from a retry counter

Previously, a stage could succeed because a worker emitted `ready` and a
count increased. Now every **entry to a research subgraph** receives a
controller-owned Task Contract, each local pass is assessed by a
separate deterministic Task Evaluator, and an evidence-linked Repair Plan
or a structured result returns to the Meta Supervisor.

~~~mermaid
flowchart TD
 M["Meta Supervisor · global loop"] --> C["Issue scoped Task Contract"]
 C --> W["Stage-specific Worker Agents / tools"]
 W --> E["Independent Task Evaluator"]
 E -->|repairable defect + budget| R["Specific Repair Plan"]
 R --> W
 E -->|stage precheck passed| M
 E -->|nonrepairable, unverified rights or exhausted| M
 M -->|scientific refutation / missing evidence| C
 M -->|safe stop| S["Actionable, non-fabricated report"]
~~~

**A contract is a measurable work order**, not an LLM instruction with
unlimited authority. Each includes `contract_id`, `issued_by_decision_id`,
source/target stage, exact issue codes, affected hypothesis/paper IDs,
repair intent, locally bounded attempt limit, *stage-specific acceptance
checks*, and the previous baseline state. It contains **no private titles,
abstracts or raw research data**.

## 2. Four independent stage evaluations

| Stage | Program-confirmable contract checks | Cannot currently prove |
| --- | --- | --- |
| Evidence | Retained IDs belong to retrieved papers; nonempty evidence | Paper relevance, novelty, completeness of coverage |
| Formulation | Eligible candidate IDs are registered; feasibility precheck recorded | Actual rights, valid samples, real-world executability |
| Competition | Winner is in eligible set; pair record; order-swap recorded | Objective scientific merit, judge calibration |
| Verification | Allowlisted protocol; executor ran; reviewer outcome interpretable | External replication, causal truth, synthetic realism |

All checks distinguish `stage_passed`, `revision_required` and
`global_reroute`. Stage passing is **not** scientific validation.
Evaluation records also retain:
- Previous issues from the task contract **and every earlier local attempt**.
- Issues *actually resolved through independent checks*; unresolved original
  blockers and newly discovered blockers remain explicit. Unresolved defects
  are passed into **every later cross-stage contract**, even after successful
  rewriting, Elo competition, or a synthetic experiment.
- `defect_progress` reports count of previously known defects, independently
  resolved defects, outstanding defects and a **process-defect resolution
  ratio**. This ratio is not a scientific-quality score. A successful synthetic
  rerun can resolve an executor error, but cannot erase an externally
  refuted scientific hypothesis.
- Process differences (new registered retained papers, newly prechecked
  candidates, child versions with lineage), not claimed scientific benefits.
- A constrained Repair Plan with exact issue codes, allowed repair-action
  codes, affected IDs, retry-vs-reroute and acceptance checks.

A change of title never resolves missing data. A new hypothesis after a
refuting pilot does **not** resolve a scientific contradiction: it remains
outstanding until independently re-tested.

## 3. Local and global feedback

**Local loop:** the independent `stage_evaluation` overrides worker-reported
ready/blocked; the repair plan is visible to the next call through
`state["repair_plan"]`. This provides bounded, issue-specific retries.

**Global loop:** `supervisor.choose_next` issues a new focused contract
*only after policy verification*. For example:
- Paper rejection -> retained issue and `INSPECT_REJECTIONS_AND_REQUERY`.
- Refuted hypothesis `H1` -> formulation receives
  `focus_candidate_ids=["H1"]`,
  `revision_intent="experiment_refutation"`, and
  `REVISE_REFUTED_CLAIM_AND_RETEST`.
- Later evidence request for that hypothesis -> retrieval intent
  `gap_focused`, not a generic rescan.
- No independently authorized data -> cannot enter real empirical research
  regardless of an agent's score.

The independent `policy.verify_option` refuses forward transitions if
a completed stage lacks a matching independent Task Evaluation, even if a
worker says `ready`.

**Outcome ledger:** the existing decision-feedback audit now records the
evaluated task ID, confirmed issue resolutions, remaining defects, newly
emerged issues and observed process changes. These do not constitute
causal policy-learning rewards. The Meta Supervisor also receives current
task verdict and unresolved-issue counts.

## 4. Safety and supported scope

1. Each Task Evaluator is a **deterministic independent process checker**,
   not a second scientific language-model critic. Scientific assertions
   and data-access status remain unverified unless external evidence exists.
2. The current V2 `ScriptedResearchDriver` consumes scoped contracts to
   emulate targeted search, focused changes and descendant lineages.
   **Real OpenAlex/DeepSeek execution is not connected yet.**
3. Revisions are bounded by separate local budgets, global backtrack caps,
   operation ceilings and repeated-state detection; safe-stop always wins
   over fabricated data, arbitrary generated code and permission breaches.
4. Sensitive titles, team attributes, private prompts and data are excluded
   from Task Contracts and telemetry. Only sanitized IDs/check flags and
   codes enter the decision ledger.
5. `feedback.py` deliberately does **not** train a new policy from
   observational process gains. Research-quality improvements require
   independent expert evaluation and matched/randomized policy trials.

## 5. Reproduce without paid model calls

~~~bash
python -m pytest -q tests/test_v2_task_evaluation.py
python -m pytest -q tests/test_v2_architecture.py tests/test_v2_supervisor_policy.py
python -m research_agent_lab.frontier.v2.benchmark
python -m research_agent_lab.frontier.v2.cli --scenario experimental_refutation --events
~~~

The acceptance cases include prior failed paper screening, failed task
retries, new candidate lineage, refutation returning to a *focused*
formulation contract, an unsupported executor and false success records.

## 6. What is not finished

A trustworthy scientific Task Evaluator still needs a citation-grounded
review adapter with independent domain-specific rubric and outcome data.
It must not promote an LLM-generated review into authoritative truth.
Before paid V2 activation: connect authorized real drivers, add durable
checkpoints/idempotency for paid calls, snapshot evidence and data rights,
and build a read-only task contract/evaluation timeline in the workbench.
