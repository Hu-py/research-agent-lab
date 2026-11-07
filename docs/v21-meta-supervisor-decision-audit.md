# V2.1 Meta Supervisor — Evidence, policy checks and outcome audit

**Scope: V2 offline nested LangGraph only.** The current paid Frontier workflow,
Supabase tables and Vercel launch screen are unchanged. This release tests
how a controller routes; it does not establish scientific decision accuracy.

## Seven-part control design

1. **State Observer** (v2/evidence.py) derives sanitized process facts:
   paper and hypothesis counts, valid retained IDs, valid feasible IDs,
   competition winner membership, approved protocol flag, model operation
   budget and observed execution status. Unknown data rights stay unknown.
2. **Problem Diagnoser** separates a symptom from unverified root causes.
   Zero retained papers might reflect search mismatch, strict screening or
   insufficient sources. No single root cause is asserted without evidence.
3. **Policy Proposer** (v2/policy.py) compares a frozen heuristic preferred
   route with explicit alternatives, including a safe ABSTAIN outcome.
   Action cost estimates are operation counts, not dollar estimates.
4. **Independent Route Verifier** recomputes hard constraints from
   observations, preventing false paper success, fabricated candidate IDs,
   unknown competition winners, unauthorized data and unsupported protocols.
   The verifier never grants scientific truth.
5. **Decision Ledger** (v2/supervisor.py) stores each decision ID, grounded
   observations, competing actions, constraint verdicts, uncalibrated
   expectations, veto reasons and the route selected.
6. **Outcome Tracker** (v2/feedback.py) checks the state after the selected
   stage actually finishes and records process-metric deltas and operations
   consumed. Process improvement is not scientific improvement.
7. **Descriptive Policy Audit** summarizes recorded outcomes but refuses
   automatic policy training from self-selected, non-randomized executions.

The Supervisor remains deterministic. It does not use a paid LLM as a
scientific judge. Each important decision provides an explanation that can
be inspected and contested.

## Data contract

The state now includes decision_feedback[] and policy_audit.
Each decisions[] item contains observed_facts, problem_diagnosis,
alternatives[], verifier_veto_codes, expected_metric, metric_before,
confidence_calibrated=false, abstained and scientific_quality_verified=false.

Decision feedback rows record observed_process_verdict and
observed_delta, with counterfactual_observed=false and
causal_effect_estimated=false. These results must not be used as
ground-truth rewards for reinforcement learning.

Sensitive paper titles, unpublished team information, model prompts and
raw datasets do not enter public event/decision records.

## Free tests

Run:

    python -m pytest -q tests/test_v2_architecture.py tests/test_v2_supervisor_policy.py
    python -m research_agent_lab.frontier.v2.benchmark
    python -m research_agent_lab.frontier.v2.cli --scenario all_papers_rejected --events

The internal benchmark uses eleven scripted synthetic cases. Adversarial
tests include false stage success, nonexistent candidate IDs, unknown Elo
winner, unsupported experiment, unauthorized mode and ungrounded references.
Passing them verifies bounded transitions; it is NOT a measured rate of
correct scientific decisions.

## Scientific validation roadmap

1. Freeze a realistic, privacy-approved state benchmark, including the
   exact failure mode of all-paper rejection.
2. Obtain independent expert labels for acceptable next actions and
   cite the external evidence behind each label.
3. Compare baseline rules, LLM advice in shadow mode, grounded verifier
   and later adaptive policy using identical frozen inputs.
4. Estimate actual downstream gains from randomized or carefully matched
   controlled interventions, not observational self-evaluations.
5. Introduce checkpoint/idempotency controls and a reviewed real Agent
   driver before enabling any paid V2 operation.

**Scientific value is an externally verified outcome, not a Supervisor claim.**
