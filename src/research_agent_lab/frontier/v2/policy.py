"""Untrusted heuristic proposal ranking + separate non-bypassable verifier.

A proposal's benefit and call cost are *planning estimates*, not measured
scientific utility or probabilities. The frozen V2 baseline route remains the
preferred candidate unless an independent guard vetoes it. Safe-stop is the
ABSTAIN action, not a successful research result.
"""
from __future__ import annotations

from typing import Any
from .evidence import supported_refs
from .state import V2Limits, V2State

ESTIMATED_OPERATIONS = {
    "evidence": 3, "formulation": 2, "competition": 2,
    "verification": 3, "reframe": 1, "finalize": 0, "safe_stop": 0,
}
EXPECTED_METRIC = {
    "evidence": "retained_count", "formulation": "eligible_count",
    "competition": "compared_count", "verification": "experiment_executed",
    "reframe": "reframe_count",
    "finalize": "none", "safe_stop": "none",
}
REFS = {
    "evidence": ["stage", "issue_codes", "retained_count", "remaining_operations"],
    "formulation": ["stage", "issue_codes", "eligible_count", "remaining_operations"],
    "competition": ["stage", "eligible_count", "eligible_ids_valid", "winner_eligible"],
    "verification": ["stage", "eligible_count", "winner_eligible", "experiment_outcome"],
    "reframe": ["stage", "issue_codes", "reframe_count", "remaining_operations"],
    "finalize": ["stage", "execution_status", "experiment_outcome"],
    "safe_stop": ["stage", "issue_codes", "remaining_operations"],
}

def propose_options(state: V2State, observations: dict[str, Any],
                    preferred: str, reason: str) -> list[dict[str, Any]]:
    """List transparent, bounded alternatives; do not self-grade correctness."""
    candidate_routes = [preferred]
    if preferred != "safe_stop":
        candidate_routes.append("safe_stop")  # abstain is always available
    if (state.get("stage") == "formulation" and "LITERATURE_GAP" in
            observations["issue_codes"] and preferred != "evidence"):
        candidate_routes.append("evidence")
    if (state.get("stage") == "verification" and
            "SCIENTIFIC_EVIDENCE_GAP" in observations["issue_codes"] and
            preferred != "evidence"):
        candidate_routes.append("evidence")
    return [{
        "action": to, "policy_rank": rank + 1,
        "reason_code": reason if rank == 0 else
                       "ABSTAIN_UNCERTAIN" if to == "safe_stop"
                       else "ALTERNATIVE_EVIDENCE_REVIEW",
        "estimated_operations_not_billing": ESTIMATED_OPERATIONS[to],
        "expected_metric": EXPECTED_METRIC[to],
        "supporting_observation_refs": REFS[to],
        "expected_effect_is_untested": True,
        "scientific_success_probability": None,
    } for rank, to in enumerate(dict.fromkeys(candidate_routes))]


def verify_option(state: V2State, observations: dict[str, Any], option: dict,
                  limits: V2Limits) -> dict[str, Any]:
    """Independent deterministic recomputation of route guards.

    It does not trust Agent state labels as proof of data rights, winner
    identity or experiment success. Synthetic data is allowed only for
    explicitly synthetic dry-runs, never for actual scientific validation.
    """
    action = option.get("action")
    stage = observations["stage"]
    signal = observations["stage_signal"]
    issues = set(observations["issue_codes"])
    violations: list[str] = []
    # Safe-stop is always permitted, even if an untrusted caller has tried
    # to activate live mode. Otherwise we would veto the only safe exit.
    if state.get("run_mode") != "dry_run_only" and action != "safe_stop":
        violations.append("V2_LIVE_MODE_NOT_AUTHORIZED")
    if action not in ESTIMATED_OPERATIONS:
        violations.append("ACTION_NOT_ALLOWLISTED")
    elif not supported_refs(observations, option.get("supporting_observation_refs")):
        violations.append("UNGROUNDED_ACTION_EVIDENCE")
    if action not in ("safe_stop",) and observations["remaining_operations"] <= 0:
        violations.append("OPERATION_BUDGET_EXCEEDED")
    if action not in ("safe_stop",) and (
            "OPERATION_BUDGET_EXHAUSTED" in issues or "DRIVER_ERROR" in issues):
        violations.append("UNRECOVERED_SYSTEM_FAILURE")
    if action in ("competition", "verification", "finalize") and (
            "NO_VERIFIED_DATA" in issues or
            "DATA_ACCESS_NOT_VERIFIED" in issues or
            "REAL_DATA_NOT_VERIFIED" in issues):
        violations.append("UNVERIFIED_DATA_BLOCKER")
    # If this is a completed V2 subgraph, independently evaluated task
    # readiness is required in addition to the old state/identity guards.
    # Direct isolated policy-unit tests without an active task preserve
    # their earlier contract (the full graph always has a contract).
    current = state.get("active_task_contract") or {}
    eval_record = state.get("stage_evaluation") or {}
    if (current.get("target_stage") == stage and
            stage in ("evidence", "formulation", "competition", "verification")):
        valid_evaluation = (
            eval_record.get("contract_id") == current.get("contract_id")
            and eval_record.get("stage") == stage
            and isinstance(eval_record.get("checks"), dict)
        )
        if not valid_evaluation and action not in ("safe_stop", "reframe"):
            violations.append("INDEPENDENT_TASK_EVALUATION_MISSING")
        elif valid_evaluation and action in ("formulation", "competition",
                                               "verification", "finalize"):
            # Forward progression is denied if the independent evaluator
            # has not passed the stage, even if a worker says "ready".
            forward = (stage == "evidence" and action == "formulation") or (
                stage == "formulation" and action in ("competition", "verification")
            ) or (stage == "competition" and action == "verification") or (
                stage == "verification" and action == "finalize"
            )
            if forward and eval_record.get("verdict") != "stage_passed":
                violations.append("STAGE_TASK_NOT_ACCEPTED")
    if action == "evidence":
        if stage not in ("init", "reframe", "formulation", "verification"):
            violations.append("EVIDENCE_ROUTE_FROM_UNSUPPORTED_STAGE")
        if stage == "formulation" and "LITERATURE_GAP" not in issues:
            violations.append("EVIDENCE_ROUTE_REQUIRES_LITERATURE_GAP")
        if stage == "verification" and "SCIENTIFIC_EVIDENCE_GAP" not in issues:
            violations.append("EVIDENCE_ROUTE_REQUIRES_SCIENTIFIC_GAP")
    elif action == "formulation":
        valid = (
            stage == "evidence" and signal == "ready" and
            observations["retained_ids_valid"]
        ) or (
            stage == "competition" and signal == "needs_formulation"
        ) or (
            stage == "verification" and (
                "HYPOTHESIS_REFUTED" in issues or "UNINFORMATIVE_RESULT" in issues
            )
        )
        if not valid:
            violations.append("FORMULATION_PREREQUISITES_MISSING")
    elif action == "competition":
        if (stage != "formulation" or signal != "ready" or
                observations["eligible_count"] < 2 or
                not observations["eligible_ids_valid"]):
            violations.append("COMPETITION_REQUIRES_TWO_VERIFIED_CANDIDATES")
    elif action == "verification":
        from_formulation = (stage == "formulation" and signal == "ready" and
                            observations["eligible_count"] == 1 and
                            observations["eligible_ids_valid"])
        from_competition = (stage == "competition" and signal == "ready" and
                            observations["winner_eligible"])
        if not (from_formulation or from_competition):
            violations.append("VERIFICATION_REQUIRES_ELIGIBLE_CANDIDATE")
    elif action == "reframe":
        if stage not in ("evidence", "formulation"):
            violations.append("REFRAME_FROM_UNSUPPORTED_STAGE")
        if observations["reframe_count"] >= (
            1 if stage == "evidence" else 2
        ):
            violations.append("REFRAME_ATTEMPT_LIMIT")
    elif action == "finalize":
        if not (
            stage == "verification" and signal == "ready"
            and observations["experiment_outcome"] == "supported"
            and observations["execution_status"] in
                ("simulated_executed", "executed")
            and observations["protocol_allowlisted"]
        ):
            violations.append("FINALIZE_WITHOUT_VERIFIABLE_PROTOCOL_RESULT")
    elif action != "safe_stop" and action not in ESTIMATED_OPERATIONS:
        violations.append("UNKNOWN_ROUTE")

    # Guard against unauthorized global backtracking even for policy advice.
    order = {"evidence": 0, "formulation": 1, "competition": 2, "verification": 3}
    is_backtrack = ((stage in order and action in order and
                     order[action] < order[stage])
                    or action == "reframe")
    if is_backtrack and observations["global_backtracks"] >= limits.global_backtracks:
        violations.append("GLOBAL_BACKTRACK_LIMIT")
    return {
        "approved": not violations,
        "veto_codes": sorted(set(violations)),
        "verifier_kind": "deterministic_independent_constraints",
        "scientific_quality_verified": False,
    }
