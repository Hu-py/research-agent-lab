"""Meta Supervisor: cross-loop scientific routing with hard fail-safe guards.

No LLM may bypass data rights, force a scientific conclusion or spend past
the operation budget. The controller routes by verified stage signals and
structured error taxonomy. This first version is deterministic and testable;
optional LLM *advice* may be added without changing its hard route guard.
"""
from __future__ import annotations

import hashlib
import json

from .state import V2Limits, V2State, codes, event
from .evidence import observe, diagnose
from .policy import propose_options, verify_option
from .feedback import (
    metric_value, evaluate_pending_decision, descriptive_policy_audit
)

STAGES = frozenset(("evidence", "formulation", "competition", "verification"))
HARD_DATA_BLOCKERS = frozenset((
    "NO_VERIFIED_DATA", "DATA_ACCESS_NOT_VERIFIED", "REAL_DATA_NOT_VERIFIED"
))


def choose_next(state: V2State, limits: V2Limits) -> dict:
    prior = state.get("stage", "init")
    signal = state.get("stage_signal", "init")
    issues = codes(state.get("issue_codes", []))
    backtracks = state.get("global_backtracks", 0)
    reframe_count = state.get("reframe_count", 0)
    steps = state.get("operation_count", 0)
    next_stage = "safe_stop"
    reason = "UNKNOWN_STAGE_STATE"
    increment = False
    if state.get("run_mode") != "dry_run_only":
        reason = "V2_PRODUCTION_EXECUTION_NOT_ACTIVATED"
    elif steps >= limits.max_operations or "OPERATION_BUDGET_EXHAUSTED" in issues:
        reason = "OPERATION_BUDGET_EXHAUSTED"
    elif prior == "init":
        next_stage, reason = "evidence", "INITIAL_EVIDENCE"
    elif prior == "evidence":
        if signal == "ready":
            next_stage, reason = "formulation", "EVIDENCE_READY"
        elif backtracks < limits.global_backtracks and reframe_count < 1:
            next_stage, reason, increment = "reframe", "REQUERY_STRATEGY_EXHAUSTED", True
        else:
            reason = "EVIDENCE_EXHAUSTED"
    elif prior == "reframe":
        next_stage, reason = "evidence", "RESEARCH_PROBLEM_REFRAMED"
    elif prior == "formulation":
        if signal == "ready":
            count = len(state.get("feasibility", {}).get("eligible_ids", []))
            if count >= 2:
                next_stage, reason = "competition", "MULTIPLE_ELIGIBLE_HYPOTHESES"
            elif count == 1:
                next_stage, reason = "verification", "SINGLE_ELIGIBLE_SKIP_ELO"
            else:
                reason = "NO_FEASIBLE_CANDIDATES"
        elif set(issues) & HARD_DATA_BLOCKERS:
            reason = "INDEPENDENT_DATA_VERIFICATION_REQUIRED"
        elif ("LITERATURE_GAP" in issues and backtracks < limits.global_backtracks):
            next_stage, reason, increment = "evidence", "RETURN_FOR_EVIDENCE", True
        elif backtracks < limits.global_backtracks and reframe_count < 2:
            next_stage, reason, increment = "reframe", "REFRAME_UNFEASIBLE_PROBLEM", True
        else:
            reason = "FORMULATION_UNRESOLVED"
    elif prior == "competition":
        if signal == "ready":
            next_stage, reason = "verification", "COMPETITION_COMPLETE"
        elif signal == "needs_formulation" and backtracks < limits.global_backtracks:
            next_stage, reason, increment = "formulation", "EVOLVED_IDEA_REQUIRES_FEASIBILITY", True
        else:
            # No winner from position-sensitive or inconclusive ranking.
            next_stage, reason = "verification", "UNCERTAIN_RANKING_WITH_CAVEATS"
    elif prior == "verification":
        if signal == "ready" and state.get("experiment_assessment", {}).get("outcome") == "supported":
            next_stage, reason = "finalize", "VALIDATED_EXPERIMENT_RESULT"
        elif "SCIENTIFIC_EVIDENCE_GAP" in issues and backtracks < limits.global_backtracks:
            next_stage, reason, increment = "evidence", "RETURN_FOR_SCIENTIFIC_EVIDENCE", True
        elif ("HYPOTHESIS_REFUTED" in issues or "UNINFORMATIVE_RESULT" in issues
              ) and backtracks < limits.global_backtracks:
            next_stage, reason, increment = "formulation", "REVISE_FROM_EXPERIMENT", True
        else:
            reason = "EXPERIMENT_NOT_VALIDATED"
    if next_stage in STAGES and prior in STAGES and next_stage != prior:
        # Count only genuine *backtracks*; normal forward progression is free.
        order = {"evidence": 0, "formulation": 1, "competition": 2, "verification": 3}
        if order[next_stage] < order[prior]:
            increment = True if not increment else increment
    if increment and backtracks >= limits.global_backtracks:
        next_stage, reason, increment = "safe_stop", "GLOBAL_BACKTRACK_LIMIT", False

    # A separate deterministic observer recomputes process facts. The proposer
    # cannot authorize data, call a model or declare scientific success.
    observations = observe(state, max_operations=limits.max_operations)
    diagnosis = diagnose(observations)
    proposed = propose_options(state, observations, next_stage, reason)
    considered = [
        {**option, "verification": verify_option(
            state, observations, option, limits
        )} for option in proposed
    ]
    approved = next(
        (option for option in considered if option["verification"]["approved"]),
        None
    )
    verifier_veto = []
    if approved is None:
        next_stage, reason, increment = (
            "safe_stop", "ALL_PROPOSALS_VETOED", False
        )
        verifier_veto = ["NO_SAFE_APPROVED_PROPOSAL"]
        selected_metric = "none"
    elif approved["action"] != next_stage:
        # Abstain rather than promote a self-reported success or bypass a
        # scientific permission, evidence or experiment guard.
        verifier_veto = considered[0]["verification"]["veto_codes"]
        next_stage, reason, increment = (
            approved["action"], "PREFERRED_ROUTE_VETOED", False
        )
        selected_metric = approved["expected_metric"]
    else:
        selected_metric = approved["expected_metric"]
    past_feedback = evaluate_pending_decision(
        state, max_operations=limits.max_operations
    )
    policy_audit = descriptive_policy_audit(past_feedback)
    # Detect identical research-state failures, not just repeated action labels.
    # A short fingerprint is safe to persist; private texts never go into
    # event logs or into the key itself.
    material = {
        "papers": [p.get("id") for p in state.get("literature", {}).get("papers", [])
                   if isinstance(p, dict)],
        "retained": state.get("literature", {}).get("retained_ids", []),
        "hypotheses": [c.get("id") for c in state.get("hypotheses", [])
                       if isinstance(c, dict)],
        "active": state.get("active_candidate_ids", []),
        "feasible": state.get("feasibility", {}).get("eligible_ids", []),
        "protocol_id": state.get("protocol", {}).get("protocol_id"),
        "experiment_outcome": state.get("experiment_assessment", {}).get("outcome"),
    }
    digest = hashlib.sha256(json.dumps(
        material, sort_keys=True, ensure_ascii=True, default=str
    ).encode("utf-8")).hexdigest()[:16]
    signature = f"{prior}:{signal}:{','.join(issues)}:{next_stage}:{digest}"
    hits = state.get("signature_hits", {}).get(signature, 0) + 1
    if hits > limits.max_repeat_signatures:
        next_stage, reason, increment = "safe_stop", "STAGNATION_DETECTED", False
        selected_metric = "none"
        verifier_veto = [*verifier_veto, "STAGNATION_DETECTED"]
    signature_hits = {**state.get("signature_hits", {}), signature: hits}
    # Defensive checks: no LLM/driver can route into an unknown graph node.
    if next_stage not in {*STAGES, "reframe", "finalize", "safe_stop"}:
        next_stage, reason, increment = "safe_stop", "INVALID_ROUTE", False
        selected_metric = "none"
        verifier_veto = [*verifier_veto, "INVALID_ROUTE"]
    decision_number = len(state.get("decisions", [])) + 1
    previous = state.get("decisions", [])
    decision_id = "D" + str(decision_number).zfill(4)
    return {
        "next_stage": next_stage,
        "global_backtracks": backtracks + int(increment),
        "signature_hits": signature_hits,
        "decisions": [*previous, {
            "decision_id": decision_id,
            "from": prior, "to": next_stage, "reason_code": reason,
            "issue_codes": issues, "operation_count": steps,
            "observed_facts": observations,
            "problem_diagnosis": diagnosis,
            "alternatives": considered,
            "selected_expected_metric": selected_metric,
            "expected_metric": selected_metric,
            "metric_before": metric_value(observations, selected_metric),
            "verifier_veto_codes": verifier_veto,
            "decision_method": "frozen_heuristics_plus_independent_guard",
            "confidence_calibrated": False,
            "abstained": next_stage == "safe_stop",
            "scientific_quality_verified": False,
        }],
        "decision_feedback": past_feedback,
        "policy_audit": policy_audit,
        "events": event(state, phase="meta_supervisor", action=reason, issue_codes=issues),
    }
