"""Opt-in isolated Supabase frontier persistence and non-sensitive preflight."""
from __future__ import annotations

import httpx

from research_agent_lab.supabase_auth import headers, supabase_url


def check_frontier_supabase() -> None:
    """Read-only connectivity/permissions check; does not write any records."""
    with httpx.Client(timeout=25, follow_redirects=False) as client:
        try:
            response = client.get(
                supabase_url() + "/rest/v1/lab_frontier_runs",
                headers=headers(),
                params={"select": "id", "limit": "1"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Supabase lab_frontier_runs preflight HTTP {exc.response.status_code}; "
                "check SQL schema / key / RLS"
            ) from None
        except httpx.TransportError as exc:
            raise RuntimeError("Supabase preflight transport error") from None


def persist_frontier_run(result: dict) -> None:
    """Store minimal research results, not raw profile/abstract/pilot CSV rows."""
    payload = {
        "id": result["run_id"], "line_id": result["line_id"],
        "strategy": result["chosen_strategy"],
        "status": result["status"],
        "model_calls": result["model_calls"],
        "results": {
            "winner_id": (result["winner"]["id"] if result["winner"] else None),
            "winner_title": (result["winner"]["title"] if result["winner"] else None),
            "elo": (result["winner"]["elo"] if result["winner"] else None),
            "generation_count": result["generation_count"],
            "lineage": result["lineage"],
            "verification": result["verification"],
            "pilot": result["pilot"],
            "human_review_required": True,
            "paper_ids": result["winner"].get("paper_ids", []),
            "snapshot_id": result.get("source_snapshot_id", ""),
            "ranked_candidates": result.get("ranked_candidates", []),
            "archived_candidates": result.get("archived_candidates", []),
            "matches": result.get("matches", []),
            "supervisor_decisions": result.get("supervisor_decisions", []),
            "screening": result.get("screening", {}),
            "feasibility": result.get("feasibility", {}),
            "minimum_viable_plan": result.get("minimum_viable_plan"),
            "knowledge": result.get("knowledge", {}),
            "comparison_context": result.get("comparison_context", {}),
            "bilingual_report": result.get("bilingual_report"),
            "provider_calls": result.get("provider_calls", result["model_calls"]),
            "cache_hits": result.get("cache_hits", 0),
            "event_log": result.get("event_log", []),
        }
    }
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        try:
            response = client.post(
                supabase_url() + "/rest/v1/lab_frontier_runs",
                headers=headers(prefer="return=minimal"),
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Supabase lab_frontier_runs write HTTP {exc.response.status_code}; "
                "check isolated lab schema / keys"
            ) from None
        except httpx.TransportError:
            raise RuntimeError("Supabase write transport error") from None
