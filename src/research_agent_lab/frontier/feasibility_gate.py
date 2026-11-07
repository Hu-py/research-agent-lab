"""Deterministic, feasibility-FIRST empirical research admission gate.

A gate pass is only *metadata precheck*, not evidence of a running study.
The LLM cannot invent access, column names, research novelty or test results.
Blocked research concepts remain in the version lineage for targeted revision.
"""
from __future__ import annotations

from collections import Counter
from research_agent_lab.contracts import Snapshot

PLAN_FIELDS = (
    "unit_of_analysis", "outcome_field", "baseline_method",
    "evaluation_metric", "split_strategy",
)

def check_candidate(candidate: dict, snapshot: Snapshot) -> dict:
    """Only independently registered and accessible fields count."""
    reasons = set()
    assets = {d.id: d for d in snapshot.datasets}
    papers = {p.id for p in snapshot.papers}
    cited = candidate.get("paper_ids") or []
    if not cited or not set(cited) <= papers:
        reasons.add("UNREGISTERED_PAPER")
    dataset_ids = candidate.get("dataset_ids") or []
    if not dataset_ids:
        reasons.add("NO_DATASET_REFERENCE")
    for did in dataset_ids:
        dataset = assets.get(did)
        if dataset is None:
            reasons.add("UNREGISTERED_DATASET")
        else:
            if not dataset.access_verified:
                reasons.add("DATASET_ACCESS_NOT_VERIFIED")
            if not dataset.fields:
                reasons.add("DATASET_FIELDS_NOT_VERIFIED")

    plan = candidate.get("execution_plan")
    if not isinstance(plan, dict):
        reasons.add("MISSING_EXECUTION_PLAN")
        plan = {}
    elif plan.get("study_type") != "empirical":
        reasons.add("UNSUPPORTED_RESEARCH_PROTOCOL")
    for field in PLAN_FIELDS:
        value = plan.get(field)
        if not isinstance(value, str) or not 2 <= len(value.strip()) <= 250:
            reasons.add("INCOMPLETE_EXECUTION_PLAN")
    steps = plan.get("steps")
    if (not isinstance(steps, list) or not 2 <= len(steps) <= 12 or
        any(not isinstance(s, str) or not 5 <= len(s.strip()) <= 350 for s in steps)):
        reasons.add("INSUFFICIENT_EXECUTION_STEPS")

    mappings = plan.get("dataset_field_map")
    matched = set()
    verified_fields = set()
    if not isinstance(mappings, list) or len(mappings) != len(dataset_ids):
        reasons.add("FIELD_MAPPING_MISSING")
    else:
        for mapping in mappings:
            if not isinstance(mapping, dict):
                reasons.add("FIELD_MAPPING_MISSING")
                continue
            did = mapping.get("dataset_id")
            if not isinstance(did, str) or did in matched or did not in dataset_ids:
                reasons.add("FIELD_MAPPING_UNKNOWN_DATASET")
                continue
            matched.add(did)
            fields = mapping.get("fields")
            if not isinstance(fields, list) or not fields or not all(
                isinstance(f, str) and f.strip() for f in fields
            ):
                reasons.add("FIELD_MAPPING_MISSING")
                continue
            dataset = assets.get(did)
            if dataset is None:
                reasons.add("UNREGISTERED_DATASET")
                continue
            registered = set(dataset.fields)
            if not set(fields) <= registered:
                reasons.add("FIELD_MAPPING_NOT_REGISTERED")
            verified_fields.update(registered.intersection(fields))
        if matched != set(dataset_ids):
            reasons.add("FIELD_MAPPING_MISSING")
    target = plan.get("outcome_field")
    if isinstance(target, str) and target.strip() and target not in verified_fields:
        reasons.add("OUTCOME_FIELD_NOT_REGISTERED")

    return {
        "candidate_id": str(candidate.get("id", "")),
        "status": "precheck_passed" if not reasons else "blocked",
        "reason_codes": sorted(reasons),
        "dataset_count": len(dataset_ids),
        "checked_without_running_data": True,
        "scientific_novelty_verified": False,
    }


def screen_pool(candidates: list[dict], snapshot: Snapshot) -> tuple[list[dict], dict]:
    """Hard-block invalid proposals before Elo; never lose their ancestry."""
    updated = []
    checked = 0
    for c in candidates:
        if c.get("status") != "candidate":
            updated.append(c)
            continue
        v = check_candidate(c, snapshot)
        checked += 1
        updated.append({**c, "feasibility": v,
                        "status": "candidate" if v["status"] == "precheck_passed" else "blocked"})
    eligible = sum(c.get("status") == "candidate" for c in updated)
    blocked = [c for c in updated if c.get("status") == "blocked"]
    by_reason = Counter(reason for c in blocked
                        for reason in c.get("feasibility", {}).get("reason_codes", []))
    report = {
        "mode": "feasibility_first_v1",
        "newly_checked": checked,
        "eligible_count": eligible,
        "blocked_count": len(blocked),
        "blocked_candidates": [{
            "id": c["id"], "reason_codes": c.get("feasibility", {}).get("reason_codes", [])
        } for c in blocked],
        "reason_counts": dict(sorted(by_reason.items())),
        "dataset_catalog_count": len(snapshot.datasets),
        "access_verified_dataset_count": sum(
            d.access_verified and bool(d.fields) for d in snapshot.datasets
        ),
        "novelty_verified": False,
        "precheck_is_empirical_metadata_only": True,
    }
    return updated, report


def minimal_viable_plan(snapshot: Snapshot, blocked: list[dict]) -> dict:
    """Never claim a missing raw dataset exists or a synthetic pilot is research proof.

    Always returns a *usable next-action plan*. No unsupported empirical winner
    is manufactured to satisfy an output quota.
    """
    missing = sorted({r for c in blocked
                      for r in c.get("feasibility", {}).get("reason_codes", [])})
    accessible = [d for d in snapshot.datasets if d.access_verified and d.fields]
    target = blocked[0] if blocked else None
    if accessible:
        mode = "field_validation_and_minimal_baseline"
        first_action = (
            "Inspect approved dataset schema and value distributions locally. "
            "Select a valid target, register a reproducible split and run a mean baseline."
        )
        blockers = missing or ["INSUFFICIENT_VERIFIED_STUDY_PROTOCOL"]
    else:
        mode = "rights_and_data_verification"
        first_action = (
            "Obtain independent data-owner permission and check a real schema, "
            "time/space coverage and a reproducible target before any empirical analysis."
        )
        blockers = sorted(set(missing) | {"NO_VERIFIED_EXECUTABLE_DATA"})
    return {
        "deliverable_type": "minimum_actionable_research_plan_not_verified_study",
        "research_line": snapshot.research_line.id,
        "research_question": (
            str(target.get("question") or "")[:450] if target else
            snapshot.research_line.problem[:450]
        ),
        "first_action": first_action,
        "next_steps": [
            first_action,
            "Write one explicit H0/H1 contrast with a registered outcome and baseline.",
            "Run a small controlled test and store actual metrics and failure criteria.",
            "Only then re-enter the competitive research pipeline."
        ],
        "blocked_reason_codes": blockers,
        "ready_for_empirical_experiment": False,
        "requires_human_data_authorization": not bool(accessible),
        "cannot_claim_novelty_or_scientific_validation": True,
        "mode": mode,
    }
