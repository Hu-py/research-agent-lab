"""Independent deterministic stage evaluation for V2 local scientific loops.

Workers can propose artifacts but they cannot set the evaluated verdict.
This code checks only controller-visible identities, metadata and execution
facts. It *never* infers paper relevance, novelty, model quality or the truth
of synthetic results. Every iteration preserves outstanding defects.
"""
from __future__ import annotations

from typing import Any

from .contracts import CHECKS, REPAIR_ACTIONS, contract_for_stage
from .state import V2Limits, V2State, codes

FATAL_ERRORS = frozenset((
    "DRIVER_ERROR", "INVALID_DRIVER_RESULT", "OPERATION_BUDGET_EXHAUSTED"
))
ACCESS_BLOCKERS = frozenset((
    "NO_VERIFIED_DATA", "DATA_ACCESS_NOT_VERIFIED", "REAL_DATA_NOT_VERIFIED"
))
STAGE_ISSUES: dict[str, str] = {
    "evidence": "ALL_PAPERS_REJECTED",
    "formulation": "NO_FEASIBLE_CANDIDATES",
    "competition": "NO_DISTINCT_CANDIDATES",
    "verification": "UNINFORMATIVE_RESULT",
}


def _objects(raw: object) -> list[dict]:
    return [x for x in raw if isinstance(x, dict)] if isinstance(raw, list) else []


def _ids(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [x for x in raw if isinstance(x, str) and x]


def _independent_checks(stage: str, state: V2State) -> dict[str, bool]:
    if stage == "evidence":
        papers = _objects(state.get("literature", {}).get("papers"))
        paper_ids = {x.get("id") for x in papers}
        retained = _ids(state.get("literature", {}).get("retained_ids"))
        consistent = (bool(retained) and len(retained) ==
                      len(set(retained)) and set(retained) <= paper_ids)
        return {
            "retained_registered_papers": consistent,
            "nonempty_evidence": bool(retained),
        }
    if stage == "formulation":
        ids = _ids(state.get("feasibility", {}).get("eligible_ids"))
        candidates = _objects(state.get("hypotheses"))
        known = {x.get("id") for x in candidates}
        viable = (bool(ids) and len(ids) == len(set(ids)) and
                  set(ids) <= known)
        # Synthetic test-driver field precheck is an independent signal from
        # the dry-run stage itself, not a data-owner authorization.
        checked = state.get("feasibility", {}).get("checked_without_running_data") is True
        return {
            "eligible_registered_hypotheses": viable,
            "metadata_feasibility_checked": checked,
        }
    if stage == "competition":
        verdict = state.get("competition", {})
        ids = _ids(state.get("feasibility", {}).get("eligible_ids"))
        winner = verdict.get("winner_id")
        pair_count = verdict.get("pair_count", 0)
        return {
            "eligible_winner": bool(winner) and winner in ids,
            "pairwise_record": type(pair_count) is int and pair_count >= 1,
            "counterorder_checked": verdict.get("position_bias_checked") is True,
        }
    if stage == "verification":
        protocol = state.get("protocol", {})
        execution = state.get("experiment", {})
        review = state.get("experiment_assessment", {})
        return {
            "allowlisted_protocol": protocol.get("template_allowlisted") is True,
            "experiment_ran": execution.get("status") in (
                "executed", "simulated_executed"
            ),
            "interpretable_result": review.get("outcome") in (
                "supported", "refuted", "uninformative"
            ),
        }
    raise ValueError("Unexpected V2 research stage")


def evaluate_task(state: V2State, *, stage: str,
                  nominal_signal: str, issues: list[str],
                  limits: V2Limits) -> dict[str, Any]:
    """Return an immutable evaluation record; never rely on a worker score."""
    contract = contract_for_stage(state, stage)
    checks = _independent_checks(stage, state)
    passed = bool(contract) and all(checks.values())
    issue_set = set(codes(issues))
    # Independent checks can expose a missing requirement concealed by the
    # worker-provided stage signal, including a fabricated completion.
    if not passed:
        issue_set.add(STAGE_ISSUES[stage])
    if contract is None:
        issue_set.add("INVALID_DRIVER_RESULT")
    if stage == "verification":
        outcome = state.get("experiment_assessment", {}).get("outcome")
        status = state.get("experiment", {}).get("status")
        if outcome == "refuted":
            issue_set.add("HYPOTHESIS_REFUTED")
        if status == "failed":
            issue_set.add("EXPERIMENT_FAILED")
        if status == "not_executed":
            issue_set.add("EXECUTOR_UNAVAILABLE")
    if stage == "competition" and not state.get("competition", {}).get("winner_id"):
        issue_set.add("NO_DISTINCT_CANDIDATES")
    issues_now = sorted(issue_set)
    counts = state.get("local_retries", {})
    ceiling = contract.get("max_local_revisions", 0) if contract else 0
    attempt = counts.get(stage, 0)
    local_possible = (
        attempt < ceiling and
        state.get("operation_count", 0) + 3 < limits.max_operations and
        not bool(set(issues_now) & (FATAL_ERRORS | ACCESS_BLOCKERS))
    )
    if nominal_signal == "evolve" and passed and local_possible:
        verdict, next_signal = "revision_required", "evolve"
    elif stage == "verification" and "HYPOTHESIS_REFUTED" in issues_now:
        verdict, next_signal = "global_reroute", "refuted"
    elif stage == "competition" and "UNRESOLVED_CRITIQUE" in issues_now:
        verdict, next_signal = "global_reroute", "needs_formulation"
    elif passed and not bool(set(issues_now) & FATAL_ERRORS):
        # Completion of this *stage contract*, not proof of scientific truth.
        verdict, next_signal = "stage_passed", "ready"
    elif local_possible:
        verdict, next_signal = "revision_required", "retry"
    else:
        verdict, next_signal = "global_reroute", "blocked"
    # On verification, an uninformative or missing result cannot get a pass
    # merely because an executor ran. It needs a new discriminating protocol.
    if stage == "verification" and "UNINFORMATIVE_RESULT" in issues_now:
        verdict, next_signal = (
            ("revision_required", "retry") if local_possible
            else ("global_reroute", "blocked")
        )
    # If a worker explicitly raised a fatal failure, it stays blocking
    # regardless of the residual metadata left in a previous graph state.
    if set(issues_now) & FATAL_ERRORS:
        verdict, next_signal = "global_reroute", "blocked"
    baseline = contract.get("baseline", {}) if contract else {}
    initial = set(contract.get("target_issue_codes", [])) if contract else set()
    # Count defects from earlier local attempts of the SAME contract too.
    # Otherwise a second-round repair could never show a resolved defect
    # if the target problem was first discovered inside that subgraph.
    previous_attempts = [
        record for record in state.get("task_evaluations", [])
        if record.get("contract_id") == (contract or {}).get("contract_id")
        and record.get("stage") == stage
    ] if contract else []
    historical_failures = {
        issue for item in previous_attempts
        for issue in item.get("issue_codes", [])
        if isinstance(issue, str)
    }
    outstanding_origins = initial | historical_failures
    observed_resolved: list[str] = []
    # Negative evidence cannot be erased by a rewritten title or dropped
    # issue code. Only a second verifiable result can clear the blocker.
    if stage == "evidence" and passed:
        observed_resolved = sorted(outstanding_origins & {
            "NO_LITERATURE", "ALL_PAPERS_REJECTED",
        })
    elif stage == "formulation" and passed:
        observed_resolved = sorted(outstanding_origins & {
            "NO_FEASIBLE_CANDIDATES", "OUTCOME_FIELD_NOT_REGISTERED",
            "FIELD_MAPPING_NOT_REGISTERED", "PROTOCOL_INCOMPLETE",
        })
    elif stage == "verification" and passed and (
        state.get("experiment", {}).get("status") == "executed"
        and state.get("experiment", {}).get("independent_audit") is True
        and state.get("context", {}).get("data_access_verified") is True
    ):
        observed_resolved = sorted(outstanding_origins & {
            "HYPOTHESIS_REFUTED", "UNINFORMATIVE_RESULT",
        })
    # In particular, a simulated pilot never resolves an externally refuted
    # scientific hypothesis or an unverified evidence coverage claim.
    outstanding = sorted(outstanding_origins - set(observed_resolved))
    observed_new = sorted(set(issues_now) - outstanding_origins)
    retained = _ids(state.get("literature", {}).get("retained_ids"))
    eligible = _ids(state.get("feasibility", {}).get("eligible_ids"))
    baseline_retained = baseline.get("retained_paper_ids", [])
    baseline_eligible = baseline.get("eligible_candidate_ids", [])
    new_papers = len(set(retained) - set(baseline_retained))
    new_feasible = len(set(eligible) - set(baseline_eligible))
    revised = [
        c for c in _objects(state.get("hypotheses"))
        if c.get("parent_ids") and isinstance(c.get("id"), str) and
        c["id"] not in baseline.get("hypothesis_ids", [])
    ]
    changes = {
        "new_retained_registered_papers": new_papers
            if checks.get("retained_registered_papers") else 0,
        "new_feasibility_prechecked_candidates": new_feasible
            if checks.get("eligible_registered_hypotheses") else 0,
        "new_version_with_parent_lineage": len(revised),
    }
    repair_actions = list(dict.fromkeys(
        REPAIR_ACTIONS[x] for x in issues_now if x in REPAIR_ACTIONS
    ))
    if not repair_actions and verdict != "stage_passed":
        repair_actions = ["REVIEW_STAGE_EVIDENCE_AND_CONTRACT"]
    return {
        "contract_id": contract.get("contract_id") if contract else None,
        "stage": stage,
        "attempt": attempt + 1,
        "nominal_signal": nominal_signal,
        "stage_signal": next_signal,
        "verdict": verdict,
        "checks": checks,
        "checks_passed": passed,
        "issue_codes": issues_now,
        "original_target_issue_codes": sorted(initial),
        "local_attempt_issue_codes": sorted(historical_failures),
        "verified_resolved_issue_codes": observed_resolved,
        "remaining_target_issue_codes": outstanding,
        "new_issue_codes": observed_new,
        "process_changes": changes,
        "repair_plan": {
            "target_issue_codes": sorted(set(outstanding) | set(issues_now)),
            "repair_action_codes": repair_actions,
            "focus_candidate_ids": contract.get("focus_candidate_ids", []) if contract else [],
            "focus_paper_ids": contract.get("focus_paper_ids", []) if contract else [],
            "acceptance_checks": list(CHECKS[stage]),
            "next_step": (
                "local_revision" if next_signal in ("retry", "evolve")
                else "submit_to_meta_supervisor"
            ),
        },
        "scientific_quality_verified": False,
        "real_data_access_inferred": False,
        "metadata_precheck_only": stage == "formulation",
    }
