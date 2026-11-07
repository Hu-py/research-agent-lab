"""Non-causal Decision->Outcome audit, not self-reward or RL training.

Reports *observed* process changes. Merely increasing retrieved papers,
Elo comparisons or executed synthetic experiments does not prove improved
scientific quality, and historical decisions are not randomized.
"""
from __future__ import annotations
from collections import Counter
from typing import Any

from .evidence import observe
from .state import V2State

def metric_value(observations: dict[str, Any], metric: str) -> int | None:
    if metric in ("retained_count", "eligible_count", "compared_count",
                  "reframe_count"):
        value = observations.get(metric)
        return value if type(value) is int else None
    if metric == "experiment_executed":
        return int(observations.get("execution_status") in (
            "simulated_executed", "executed"
        ))
    return None

def evaluate_pending_decision(state: V2State, *,
                              max_operations: int) -> list[dict]:
    prior = state.get("decisions", [])
    previous_feedback = state.get("decision_feedback", [])
    if not prior:
        return previous_feedback
    record = prior[-1]
    if any(x.get("decision_id") == record.get("decision_id")
           for x in previous_feedback):
        return previous_feedback
    target_stage = record.get("to")
    if target_stage in ("safe_stop", "finalize"):
        return previous_feedback
    # Backtracks might execute a reframe_marker, but never award a
    # process improvement merely for a scheduled (unexecuted) action.
    stage = state.get("stage")
    if stage != target_stage:
        return previous_feedback
    current = observe(state, max_operations=max_operations)
    metric = record.get("expected_metric", "none")
    before = record.get("metric_before")
    after = metric_value(current, metric)
    if type(before) is not int or type(after) is not int:
        verdict = "not_measurable"
        delta = None
    else:
        delta = after - before
        verdict = "observed_process_progress" if delta > 0 else (
            "unchanged" if delta == 0 else "declined"
        )
    used = max(0, int(state.get("operation_count", 0)) -
               int(record.get("operation_count", 0)))
    row = {
        "decision_id": record.get("decision_id"),
        "selected_action": target_stage,
        "expected_metric": metric,
        "metric_before": before,
        "metric_after": after,
        "observed_delta": delta,
        "observed_process_verdict": verdict,
        "operations_consumed": used,
        "counterfactual_observed": False,
        "causal_effect_estimated": False,
        "scientific_quality_verified": False,
    }
    return [*previous_feedback, row]

def descriptive_policy_audit(feedback: list[dict]) -> dict[str, Any]:
    counts = Counter(x.get("observed_process_verdict", "unknown") for x in feedback)
    return {
        "observed_decision_outcomes": len(feedback),
        "process_progress": counts["observed_process_progress"],
        "unchanged": counts["unchanged"],
        "declined": counts["declined"],
        "not_measurable": counts["not_measurable"],
        "policy_ready_for_automatic_retraining": False,
        "why_no_automatic_retraining": "observational_nonrandomized_proxy_outcomes",
        "scientific_quality_verified": False,
    }
