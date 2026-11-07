"""Evidence-grounded *observations* for V2 Meta Supervisor.

All fields are either derivable from current graph state or explicitly
unknown. Crucially: these are process facts, NOT scientific quality labels,
novelty scores, model confidence, or authorizations inferred from LLM prose.
The returned observations contain no titles, abstracts or raw datasets.
"""
from __future__ import annotations
from typing import Any
from .state import V2State, codes

OBSERVATION_KEYS = frozenset((
    "stage", "stage_signal", "issue_codes", "paper_count", "retained_count",
    "retained_ids_valid", "candidate_count", "eligible_count",
    "eligible_ids_valid", "compared_count", "winner_eligible",
    "execution_status", "experiment_outcome", "protocol_allowlisted",
    "data_access_state", "operation_count", "remaining_operations",
    "global_backtracks", "reframe_count", "stage_task_verdict",
    "stage_task_check_valid", "remaining_task_issue_count",
    "verified_task_repairs", "task_focus_candidate_count",
    "literature_retries",
    "formulation_retries", "competition_retries", "verification_retries",
))

def _objects(raw: object) -> list[dict]:
    return [x for x in raw if isinstance(x, dict)] if isinstance(raw, list) else []

def _strings(raw: object) -> list[str]:
    return [x for x in raw if isinstance(x, str) and 0 < len(x) <= 200] \
        if isinstance(raw, list) else []

def observe(state: V2State, *, max_operations: int) -> dict[str, Any]:
    papers = _objects(state.get("literature", {}).get("papers"))
    retained = _strings(state.get("literature", {}).get("retained_ids"))
    candidates = _objects(state.get("hypotheses"))
    eligible = _strings(state.get("feasibility", {}).get("eligible_ids"))
    paper_ids = {p.get("id") for p in papers}
    candidate_ids = {c.get("id") for c in candidates}
    winner = state.get("competition", {}).get("winner_id")
    retries = state.get("local_retries", {})
    access = state.get("context", {}).get("data_access_verified")
    outcome = state.get("experiment_assessment", {}).get("outcome")
    exec_status = state.get("experiment", {}).get("status")
    evaluation = state.get("stage_evaluation") or {}
    current_contract = state.get("active_task_contract") or {}
    evaluated = bool(
        evaluation.get("contract_id") and
        current_contract.get("contract_id") == evaluation.get("contract_id") and
        current_contract.get("target_stage") == evaluation.get("stage")
    )
    return {
        "stage": state.get("stage", "init"),
        "stage_signal": state.get("stage_signal", "unknown"),
        "issue_codes": codes(state.get("issue_codes", [])),
        "paper_count": len(papers),
        "retained_count": len(retained),
        "retained_ids_valid": bool(retained) and len(set(retained)) == len(retained)
                              and set(retained) <= paper_ids,
        "candidate_count": len(candidates),
        "eligible_count": len(eligible),
        "eligible_ids_valid": bool(eligible) and len(set(eligible)) == len(eligible)
                              and set(eligible) <= candidate_ids,
        "compared_count": state.get("competition", {}).get("pair_count", 0)
                           if isinstance(state.get("competition", {}).get("pair_count"), int)
                           else 0,
        "winner_eligible": isinstance(winner, str) and winner in eligible,
        "execution_status": exec_status if exec_status in (
            "executed", "simulated_executed", "failed", "not_executed"
        ) else "unknown",
        "experiment_outcome": outcome if outcome in (
            "supported", "refuted", "failed", "uninformative", "not_executed"
        ) else "unknown",
        "protocol_allowlisted": state.get("protocol", {}).get("template_allowlisted") is True,
        "data_access_state": (
            "verified" if access is True else
            "unverified" if access is False else "unknown"
        ),
        "operation_count": max(0, int(state.get("operation_count", 0))),
        "remaining_operations": max(0, max_operations-int(state.get("operation_count", 0))),
        "stage_task_verdict": evaluation.get("verdict") if evaluated else "unknown",
        "stage_task_check_valid": bool(evaluated and evaluation.get("checks_passed")),
        "remaining_task_issue_count": len(evaluation.get("remaining_target_issue_codes", []))
                                      if evaluated else 0,
        "verified_task_repairs": len(evaluation.get("verified_resolved_issue_codes", []))
                                 if evaluated else 0,
        "task_focus_candidate_count": len(current_contract.get("focus_candidate_ids", []))
                                      if current_contract else 0,
        "global_backtracks": state.get("global_backtracks", 0),
        "reframe_count": state.get("reframe_count", 0),
        "literature_retries": retries.get("evidence", 0),
        "formulation_retries": retries.get("formulation", 0),
        "competition_retries": retries.get("competition", 0),
        "verification_retries": retries.get("verification", 0),
    }

def diagnose(observations: dict[str, Any]) -> dict[str, Any]:
    """Distinguish an observed failure from an *unproven* root cause."""
    stage = observations["stage"]
    issues = observations["issue_codes"]
    roots: list[str] = []
    checks: list[str] = []
    if stage == "evidence" and observations["retained_count"] == 0:
        roots = ["QUERY_MISMATCH_POSSIBLE", "SCREENING_CRITERIA_POSSIBLE",
                 "SOURCE_COVERAGE_POSSIBLE"]
        checks = ["COMPARE_QUERY_AND_TOPIC", "INSPECT_JUROR_REJECTIONS"]
    elif stage == "formulation" and observations["eligible_count"] == 0:
        roots = ["DATA_OR_PROTOCOL_GAP_POSSIBLE"]
        checks = ["VERIFY_DATA_OWNER_PERMISSION", "COMPARE_REQUIRED_AND_REGISTERED_FIELDS"]
    elif stage == "competition" and not observations["winner_eligible"]:
        roots = ["NO_VERIFIABLE_WINNER"]
        checks = ["INSPECT_ORDER_BIAS", "CONFIRM_ELIGIBLE_CANDIDATES"]
    elif stage == "verification" and observations["experiment_outcome"] != "supported":
        roots = ["SCIENTIFIC_OR_EXECUTION_GAP_POSSIBLE"]
        checks = ["INSPECT_PROTOCOL_AND_FAILURE_CRITERIA"]
    if "NO_VERIFIED_DATA" in issues or "DATA_ACCESS_NOT_VERIFIED" in issues:
        checks.append("OBTAIN_INDEPENDENT_PERMISSION_EVIDENCE")
    return {
        "observed_issue_codes": list(issues),
        "hypothesized_causes_not_verified": roots,
        "next_evidence_checks": sorted(set(checks)),
        "root_cause_independently_confirmed": False,
        "scientific_quality_inferred": False,
        "task_evaluation_present": observations.get("stage_task_verdict") != "unknown",
        "stage_task_verdict": observations.get("stage_task_verdict", "unknown"),
        "remaining_task_issue_count": observations.get("remaining_task_issue_count", 0),
    }

def supported_refs(observations: dict[str, Any], refs: object) -> bool:
    """Check a policy's fact references against an independently computed view."""
    if not isinstance(refs, list) or not refs:
        return False
    return all(isinstance(ref, str) and ref in OBSERVATION_KEYS
               and ref in observations for ref in refs)
