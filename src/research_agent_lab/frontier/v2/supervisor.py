"""Meta Supervisor: cross-loop scientific routing with hard fail-safe guards.

No LLM may bypass data rights, force a scientific conclusion or spend past
the operation budget. The controller routes by verified stage signals and
structured error taxonomy. This first version is deterministic and testable;
optional LLM *advice* may be added without changing its hard route guard.
"""
from __future__ import annotations

from .state import V2Limits, V2State, codes, event

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
    if steps >= limits.max_operations or "OPERATION_BUDGET_EXHAUSTED" in issues:
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

    signature = f"{prior}:{signal}:{','.join(issues)}:{next_stage}"
    hits = state.get("signature_hits", {}).get(signature, 0) + 1
    if hits > limits.max_repeat_signatures:
        next_stage, reason = "safe_stop", "STAGNATION_DETECTED"
    signature_hits = {**state.get("signature_hits", {}), signature: hits}
    # Defensive checks: no LLM/driver can route into an unknown graph node.
    if next_stage not in {*STAGES, "reframe", "finalize", "safe_stop"}:
        next_stage, reason = "safe_stop", "INVALID_ROUTE"
    return {
        "next_stage": next_stage,
        "global_backtracks": backtracks + int(increment),
        "signature_hits": signature_hits,
        "decisions": [*state.get("decisions", []), {
            "from": prior, "to": next_stage, "reason_code": reason,
            "issue_codes": issues, "operation_count": steps,
        }],
        "events": event(state, phase="meta_supervisor", action=reason, issue_codes=issues),
    }
