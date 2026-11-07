"""Persist LangGraph node completion as private, low-data-volume stage events.

The callback intentionally never stores text about candidate ideas, team datasets,
paper abstracts, prompts, evaluator reasons, model keys, nor failure exception text.
The event table has no FK to completed runs so updates appear during paid runs.
A transient stream outage is diagnostic only; never abort a paid experiment
or silently invent events. Initial table preflight must pass before inference.
"""
from __future__ import annotations

import uuid
from typing import Any

import httpx

from research_agent_lab.supabase_auth import headers, supabase_url


# Allowlist stage fields only. No raw source, unpublished text, or research titles.
_BOOLEAN_FIELDS = {"pilot_executed", "data_feasible_assessment", "no_valid_children"}
_INTEGER_FIELDS = {"generation", "retrieved", "retained", "disagreements",
                   "matches", "archived_generation", "rejected_count"}
_ID_FIELDS = {"leader", "winner"}
_ENUM_FIELDS = {"decision", "strategy"}

def _safe_details(event: dict) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in _BOOLEAN_FIELDS:
        if isinstance(event.get(key), bool):
            safe[key] = event[key]
    for key in _INTEGER_FIELDS:
        value = event.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            safe[key] = max(0, min(value, 100000))
    for key in _ID_FIELDS:
        value = event.get(key)
        if isinstance(value, str) and 0 < len(value) <= 24:
            # Only schema-compatible anonymous candidate IDs, never titles.
            if value.startswith("H") and value[1:].isdigit():
                safe[key] = value
    for key in _ENUM_FIELDS:
        value = event.get(key)
        if isinstance(value, str) and value in (
            "verify", "evolve", "expand", "rollback", "balanced", "novelty", "feasibility"
        ):
            safe[key] = value
    code = event.get("failure_code")
    if isinstance(code, str) and code in {
        "CANDIDATE_SCHEMA_INVALID", "MODEL_BUDGET_EXHAUSTED",
        "MODEL_PROVIDER_ERROR", "EVIDENCE_PIPELINE_ERROR",
        "SCIENTIFIC_GATE_ERROR", "OTHER_RUNTIME_ERROR"
    }:
        safe["failure_code"] = code
    # Length only; don't forward parent IDs or candidate text during live run.
    if isinstance(event.get("created"), list):
        safe["created_count"] = min(30, len(event["created"]))
    if isinstance(event.get("children"), list):
        safe["children_count"] = min(30, len(event["children"]))
    return safe


def check_frontier_event_store() -> None:
    with httpx.Client(timeout=15, follow_redirects=False) as client:
        try:
            response = client.get(
                supabase_url() + "/rest/v1/lab_frontier_events",
                headers=headers(),
                params={"select":"run_id", "limit":"1"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                "FRONTIER_EVENTS_PREFLIGHT_HTTP_" + str(exc.response.status_code)
                + ": run sql/007_frontier_live_events.sql in the isolated lab"
            ) from None
        except httpx.TransportError:
            raise RuntimeError("FRONTIER_EVENTS_PREFLIGHT_TRANSPORT") from None


class FrontierEventPublisher:
    """Best-effort append-only node telemetry, disabled after first delivery error."""
    def __init__(self, run_id: str | None = None, client: httpx.Client | None = None):
        self.run_id = str(uuid.UUID(run_id)) if run_id else str(uuid.uuid4())
        self.next_step = 0
        self.degraded = False
        self.own_client = client is None
        self.client = client or httpx.Client(timeout=12, follow_redirects=False)

    def close(self) -> None:
        if self.own_client:
            self.client.close()

    def emit(self, event: dict) -> None:
        if self.degraded:
            return
        raw_stage = event.get("stage")
        stage = raw_stage if isinstance(raw_stage,str) and raw_stage.islower() and \
            raw_stage.replace("_","").isalpha() else "unclassified_stage"
        payload = {
            "run_id": self.run_id,
            "step_index": self.next_step,
            "stage": stage[:64],
            "details": _safe_details(event),
        }
        try:
            response = self.client.post(
                supabase_url() + "/rest/v1/lab_frontier_events",
                headers=headers(prefer="return=minimal"),
                json=payload,
            )
            response.raise_for_status()
            self.next_step += 1
        except (httpx.HTTPError, ValueError, TypeError):
            # Never print model output or response bodies, which can be private.
            self.degraded = True
            print("NOTICE: private live-stage upload unavailable; final result will still save")

    def started(self) -> None:
        self.emit({"stage":"run_started"})

    def finished(self) -> None:
        self.emit({"stage":"run_completed"})

    def failed(self, failure_code: str = "OTHER_RUNTIME_ERROR") -> None:
        self.emit({"stage":"run_failed", "failure_code": failure_code})


def safe_failure_code(exc: Exception) -> str:
    """Stable non-content diagnostic for UI; never export exception text."""
    message = str(exc)
    if "Candidate contract repair failed" in message or "Initial hypotheses insufficient" in message:
        return "CANDIDATE_SCHEMA_INVALID"
    if "ceiling exceeded" in message or "budget exceeded" in message.lower():
        return "MODEL_BUDGET_EXHAUSTED"
    if message.startswith("DeepSeek ") or message.startswith("Model response"):
        return "MODEL_PROVIDER_ERROR"
    if "paper" in message.lower() or "OpenAlex" in message:
        return "EVIDENCE_PIPELINE_ERROR"
    if "science validation" in message.lower() or "Winner lacks" in message:
        return "SCIENTIFIC_GATE_ERROR"
    return "OTHER_RUNTIME_ERROR"
