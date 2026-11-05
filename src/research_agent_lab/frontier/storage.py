"""Opt-in Supabase persistence of frontier outcomes in isolated tables."""
from __future__ import annotations

import os
import httpx


def persist_frontier_run(result: dict) -> None:
    endpoint = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not endpoint or not key or not endpoint.startswith("https://"):
        raise ValueError("Isolated test Supabase URL and server-side key are required")
    payload = {
        "id": result["run_id"], "line_id": result["line_id"],
        "strategy": result["chosen_strategy"],
        "status": result["status"],
        "model_calls": result["model_calls"],
        "results": {
            "winner_id": result["winner"]["id"],
            "winner_title": result["winner"]["title"],
            "elo": result["winner"]["elo"],
            "generation_count": result["generation_count"],
            "lineage": result["lineage"],
            "verification": result["verification"],
            "pilot": result["pilot"],
            "human_review_required": True,
        }
    }
    with httpx.Client(timeout=30, follow_redirects=False) as http:
        response = http.post(
            endpoint + "/rest/v1/lab_frontier_runs",
            headers={
                "apikey": key,
                "Authorization": "Bearer " + key,
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            json=payload
        )
        response.raise_for_status()
