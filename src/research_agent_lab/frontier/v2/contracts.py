"""Task contracts for V2 scientific subgraphs.

The Meta Supervisor issues a *bounded, auditable and scoped* instruction
for a destination subgraph. Contracts are controller-authored from known
state, never freeform authority delegated to the LLM driver. IDs, reason
codes and checks are machine-verifiable; scientific quality remains open.
"""
from __future__ import annotations

from typing import Any

from .state import ISSUE_CODES, V2Limits, V2State

PHASES = frozenset(("evidence", "formulation", "competition", "verification"))
CHECKS: dict[str, tuple[str, ...]] = {
    "evidence": ("retained_registered_papers", "nonempty_evidence"),
    "formulation": ("eligible_registered_hypotheses", "metadata_feasibility_checked"),
    "competition": ("eligible_winner", "pairwise_record", "counterorder_checked"),
    "verification": ("allowlisted_protocol", "experiment_ran", "interpretable_result"),
}
REPAIR_ACTIONS = {
    "NO_LITERATURE": "REQUERY_FOR_RELEVANT_EVIDENCE",
    "ALL_PAPERS_REJECTED": "INSPECT_REJECTIONS_AND_REQUERY",
    "LOW_EVIDENCE_COVERAGE": "CLOSE_SPECIFIC_LITERATURE_GAP",
    "LITERATURE_GAP": "CLOSE_SPECIFIC_LITERATURE_GAP",
    "SCIENTIFIC_EVIDENCE_GAP": "FIND_EVIDENCE_FOR_SELECTED_HYPOTHESIS",
    "NO_HYPOTHESES": "REGENERATE_FROM_REGISTERED_EVIDENCE",
    "NO_FEASIBLE_CANDIDATES": "REDUCE_SCOPE_TO_VERIFIED_FIELDS",
    "NO_VERIFIED_DATA": "OBTAIN_INDEPENDENT_DATA_PERMISSION",
    "DATA_ACCESS_NOT_VERIFIED": "OBTAIN_INDEPENDENT_DATA_PERMISSION",
    "OUTCOME_FIELD_NOT_REGISTERED": "REPLACE_TARGET_WITH_REGISTERED_FIELD",
    "FIELD_MAPPING_NOT_REGISTERED": "USE_REGISTERED_FIELDS_ONLY",
    "PROTOCOL_INCOMPLETE": "SPECIFY_BASELINE_SPLIT_AND_FAILURE_CRITERIA",
    "HYPOTHESIS_REFUTED": "REVISE_REFUTED_CLAIM_AND_RETEST",
    "UNINFORMATIVE_RESULT": "IMPROVE_EXPERIMENT_DISCRIMINATION",
    "EXPERIMENT_FAILED": "REPAIR_EXECUTOR_OR_PROTOCOL",
    "EXECUTOR_UNAVAILABLE": "PREPARE_ALLOWLISTED_EXECUTION",
    "UNRESOLVED_CRITIQUE": "ADDRESS_SPECIFIC_CRITIQUE",
    "POSITION_DISAGREEMENT": "RECHECK_ORDER_SENSITIVITY",
    "NO_DISTINCT_CANDIDATES": "GENERATE_SUBSTANTIVELY_DISTINCT_IDEAS",
    "IDEA_UNCHANGED": "CHANGE_RESEARCH_CONTENT_NOT_TITLE",
    "QUERY_UNCHANGED": "CHANGE_QUERY_TARGET_OR_RETRIEVAL_SCOPE",
}

def _ids(raw: object, limit: int = 16) -> list[str]:
    if not isinstance(raw, list):
        return []
    return list(dict.fromkeys(
        x for x in raw if isinstance(x, str) and
        0 < len(x) <= 64 and all(ch.isalnum() or ch in "-_" for ch in x)
    ))[:limit]


def issue_contract(state: V2State, *, target: str, decision_id: str,
                   reason: str, limits: V2Limits) -> dict[str, Any]:
    """Freeze a route-specific instruction and its measurable preconditions."""
    if target not in PHASES:
        raise ValueError("Only research subgraphs receive task contracts")
    causes = [x for x in state.get("issue_codes", []) if x in ISSUE_CODES]
    previous = state.get("stage_evaluation") or {}
    # Keep earlier unresolved scientific defects across ALL phase transitions.
    # A new version or competition score cannot erase external refutation.
    causes.extend(
        x for x in previous.get("remaining_target_issue_codes", [])
        if x in ISSUE_CODES
    )
    if not causes and state.get("stage") == "reframe":
        causes.extend(
            x for x in previous.get("issue_codes", [])
            if x in ISSUE_CODES
        )
    issues = list(dict.fromkeys(causes))
    candidates = _ids(state.get("active_candidate_ids", []))
    winner = state.get("competition", {}).get("winner_id")
    if target == "evidence" and state.get("stage") == "verification":
        candidates = _ids([winner]) if isinstance(winner, str) else candidates
    elif target == "formulation" and state.get("stage") == "verification":
        candidates = _ids([winner]) if isinstance(winner, str) else candidates
    elif target in ("competition", "verification"):
        candidates = _ids(state.get("feasibility", {}).get("eligible_ids", []))
    query_mode = ("gap_focused" if
                  ("SCIENTIFIC_EVIDENCE_GAP" in issues or
                   "LITERATURE_GAP" in issues or
                   state.get("stage") == "verification")
                  else "initial_or_coverage_repair")
    retry_ceiling = {
        "evidence": limits.literature_retries,
        "formulation": limits.hypothesis_revisions,
        "competition": limits.competition_evolutions,
        "verification": limits.experiment_retries,
    }[target]
    baseline_papers = _ids(state.get("literature", {}).get("retained_ids", []))
    baseline_eligible = _ids(state.get("feasibility", {}).get("eligible_ids", []))
    baseline_hypotheses = _ids([
        c.get("id") for c in state.get("hypotheses", [])
        if isinstance(c, dict)
    ])
    return {
        "contract_id": "TC-" + decision_id,
        "issued_by_decision_id": decision_id,
        "source_stage": state.get("stage", "init"),
        "target_stage": target,
        "reason_code": reason,
        "target_issue_codes": issues,
        "focus_candidate_ids": candidates,
        "focus_paper_ids": baseline_papers,
        "retrieval_intent": query_mode,
        "revision_intent": (
            "experiment_refutation" if "HYPOTHESIS_REFUTED" in issues else
            "repair_existing_hypothesis" if target == "formulation" and issues else
            "ordinary_generation"
        ),
        "repair_action_codes": list(dict.fromkeys(
            REPAIR_ACTIONS[x] for x in issues if x in REPAIR_ACTIONS
        )),
        "acceptance_checks": list(CHECKS[target]),
        "max_local_revisions": retry_ceiling,
        "baseline": {
            "retained_paper_ids": baseline_papers,
            "eligible_candidate_ids": baseline_eligible,
            "hypothesis_ids": baseline_hypotheses,
            "observed_issues": issues,
        },
        "bounded_no_external_permission": True,
        "scientific_quality_unverified": True,
    }


def contract_for_stage(state: V2State, stage: str) -> dict[str, Any] | None:
    contract = state.get("active_task_contract")
    if not isinstance(contract, dict):
        return None
    if contract.get("target_stage") != stage:
        return None
    if contract.get("acceptance_checks") != list(CHECKS.get(stage, ())):
        return None
    if not isinstance(contract.get("contract_id"), str):
        return None
    return contract
