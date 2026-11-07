"""V2 shared scientific state, budgets and trace contracts.

Only sanitized identifiers/diagnostic codes belong in events. Raw literature,
unreleased team data and prompts belong in explicitly authorized context only.
V2 is opt-in and has no side effects or paid calls on import.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict

Stage = Literal["evidence", "formulation", "competition", "verification"]
NextStage = Literal["evidence", "formulation", "competition", "verification",
                    "reframe", "finalize", "safe_stop"]
Status = Literal["ready", "blocked", "needs_revision", "refuted", "complete"]
Action = Literal[
    "search", "review_papers", "revise_query", "reframe_problem",
    "generate", "check_feasibility", "revise_hypothesis",
    "debate", "criticize", "evolve",
    "design_experiment", "execute_experiment", "inspect_result",
]

@dataclass(frozen=True)
class V2Limits:
    literature_retries: int = 2
    hypothesis_revisions: int = 2
    competition_evolutions: int = 1
    experiment_retries: int = 1
    global_backtracks: int = 3
    max_operations: int = 48
    max_repeat_signatures: int = 2

    def __post_init__(self) -> None:
        for value in vars(self).values():
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError("V2 bounds must be non-negative integers")
        if not 8 <= self.max_operations <= 200:
            raise ValueError("V2 max_operations must be in 8..200")
        if self.global_backtracks > 10 or self.max_repeat_signatures > 5:
            raise ValueError("V2 global safety bounds are too high")


class V2State(TypedDict, total=False):
    # Inputs: fixed from authorized evidence; never inferred from LLM prose.
    objective: str
    context: dict[str, Any]
    run_mode: str
    # Working scientific artifacts
    query: dict[str, Any]
    literature: dict[str, Any]
    hypotheses: list[dict[str, Any]]
    active_candidate_ids: list[str]
    candidate_change_count: int
    feasibility: dict[str, Any]
    competition_review: dict[str, Any]
    competition: dict[str, Any]
    protocol: dict[str, Any]
    experiment: dict[str, Any]
    experiment_assessment: dict[str, Any]
    # Routing and recovery
    stage: str
    stage_signal: str
    issue_codes: list[str]
    next_stage: str
    strategy: str
    local_retries: dict[str, int]
    global_backtracks: int
    reframe_count: int
    operation_count: int
    signature_hits: dict[str, int]
    # Append-only audit
    events: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    decision_feedback: list[dict[str, Any]]
    policy_audit: dict[str, Any]
    # Final deliverable
    status: str
    report: dict[str, Any]


VALID_OPERATIONS: frozenset[str] = frozenset((
    "search", "review_papers", "revise_query", "reframe_problem",
    "generate", "check_feasibility", "revise_hypothesis",
    "debate", "criticize", "evolve",
    "design_experiment", "execute_experiment", "inspect_result",
))
ISSUE_CODES: frozenset[str] = frozenset((
    "NO_LITERATURE", "ALL_PAPERS_REJECTED", "LOW_EVIDENCE_COVERAGE",
    "EVIDENCE_EXHAUSTED", "LITERATURE_GAP", "QUERY_UNCHANGED",
    "NO_HYPOTHESES", "NO_FEASIBLE_CANDIDATES", "NO_VERIFIED_DATA",
    "DATA_ACCESS_NOT_VERIFIED", "FIELD_MAPPING_NOT_REGISTERED",
    "OUTCOME_FIELD_NOT_REGISTERED", "PROTOCOL_INCOMPLETE",
    "IDEA_UNCHANGED", "DUPLICATE_IDEA", "POSITION_DISAGREEMENT",
    "UNRESOLVED_CRITIQUE", "NO_DISTINCT_CANDIDATES",
    "EXECUTOR_UNAVAILABLE", "EXPERIMENT_FAILED",
    "UNINFORMATIVE_RESULT", "HYPOTHESIS_REFUTED",
    "PROTOCOL_UNSUPPORTED", "SCIENTIFIC_EVIDENCE_GAP",
    "OPERATION_BUDGET_EXHAUSTED", "LOOP_LIMIT_REACHED",
    "STAGNATION_DETECTED", "DRIVER_ERROR", "INVALID_DRIVER_RESULT",
    "REAL_DATA_NOT_VERIFIED",
))


def initial_state(objective: str, *, context: dict[str, Any] | None = None) -> V2State:
    if not isinstance(objective, str) or not objective.strip():
        raise ValueError("Research objective is required")
    return {
        "objective": objective.strip(),
        "context": context or {},
        "run_mode": "dry_run_only",
        "query": {}, "literature": {}, "hypotheses": [],
        "active_candidate_ids": [], "candidate_change_count": 0,
        "feasibility": {}, "competition": {}, "competition_review": {}, "protocol": {},
        "experiment": {}, "experiment_assessment": {},
        "stage": "init", "stage_signal": "init", "issue_codes": [],
        "next_stage": "evidence", "strategy": "initial",
        "local_retries": {"evidence": 0, "formulation": 0,
                          "competition": 0, "verification": 0},
        "global_backtracks": 0, "reframe_count": 0,
        "operation_count": 0, "signature_hits": {},
        "events": [], "decisions": [], "decision_feedback": [],
        "policy_audit": {}, "status": "running", "report": {},
    }


def codes(raw: object) -> list[str]:
    """Drop untrusted/freeform error strings from durable UI-facing telemetry."""
    if not isinstance(raw, (tuple, list, set)):
        return ["INVALID_DRIVER_RESULT"]
    result = sorted({x for x in raw if isinstance(x, str) and x in ISSUE_CODES})
    return result


def event(state: V2State, *, phase: str, action: str,
          issue_codes: list[str] | None = None, **metadata: Any) -> list[dict[str, Any]]:
    """Event record deliberately stores only stage and stable code-level metadata."""
    safe: dict[str, Any] = {
        "index": len(state.get("events", [])),
        "phase": phase,
        "action": action,
        "issue_codes": codes(issue_codes or []),
    }
    for key, value in metadata.items():
        if key in ("count", "retained", "eligible", "blocked", "attempt", "changed") and (
            (isinstance(value, int) and not isinstance(value, bool)) or
            (key == "changed" and isinstance(value, bool))
        ):
            safe[key] = value
    return [*state.get("events", []), safe]
