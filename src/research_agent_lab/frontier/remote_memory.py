"""Hydrate cloud-run experience and human scores from isolated Supabase tables.

SQL remains untouched. Only concise summaries and explicit human feedback are
rehydrated. API keys remain in server environment variables.
"""
from __future__ import annotations

import sqlite3
import httpx

from research_agent_lab.supabase_auth import headers, supabase_url
from .memory import MemoryStore, STRATEGIES


def _get(client: httpx.Client, table: str, params: dict) -> list[dict]:
    try:
        response = client.get(
            supabase_url() + "/rest/v1/" + table,
            headers=headers(), params=params,
        )
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list):
            raise RuntimeError("Unexpected Supabase list response from " + table)
        return rows
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Supabase {table} memory read HTTP {exc.response.status_code}"
        ) from None
    except httpx.TransportError:
        raise RuntimeError("Supabase memory read transport error") from None


def hydrate_recent_memory(memory: MemoryStore, line_id: str, limit: int = 30) -> dict:
    """Restore latest runs + user feedback in an ephemeral runner process.

    Read only this line's rows. Gracefully handle no prior runs and no ratings.
    Fail closed on auth/schema issues before DeepSeek is billed.
    """
    limit = max(1, min(50, int(limit)))
    with httpx.Client(timeout=25, follow_redirects=False) as client:
        runs = _get(client, "lab_frontier_runs", {
            "select": "id,line_id,strategy,status,results,created_at",
            "line_id": "eq." + line_id,
            "order": "created_at.desc",
            "limit": str(limit),
        })
        restored = 0
        for run in reversed(runs):
            if run.get("line_id") != line_id or run.get("strategy") not in STRATEGIES:
                continue
            run_id = str(run.get("id", ""))
            if not run_id:
                continue
            results = run.get("results") or {}
            if not isinstance(results, dict):
                continue
            if memory.db.execute("SELECT 1 FROM run_index WHERE run_id=?", (run_id,)).fetchone():
                continue
            verification = results.get("verification") or {}
            if not isinstance(verification, dict):
                verification = {}
            lessons = verification.get("evidence_limitations") or []
            if not isinstance(lessons, list):
                lessons = []
            memory.record_run(
                run_id, line_id, run["strategy"],
                best_title=str(results.get("winner_title", ""))[:200],
                lessons=[str(v) for v in lessons[:6]],
                status=("eligible" if run.get("status") == "candidate_for_human_review"
                        else "failure"),
                experiment_summary="",
            )
            restored += 1

        known_ids = [str(x.get("id")) for x in runs if x.get("id")]
        feedback_count = 0
        if known_ids:
            feedback = _get(client, "lab_frontier_feedback", {
                "select": "run_id,reviewer_tag,decision,novelty,feasibility,comment",
                "run_id": "in.(" + ",".join(known_ids) + ")",
                "limit": "500",
            })
            for entry in feedback:
                if not isinstance(entry, dict):
                    continue
                try:
                    memory.add_feedback(
                        str(entry["run_id"]), str(entry["reviewer_tag"]),
                        str(entry["decision"]), int(entry["novelty"]),
                        int(entry["feasibility"]), str(entry.get("comment") or "")
                    )
                    feedback_count += 1
                except (KeyError, ValueError, TypeError, sqlite3.IntegrityError):
                    # Skip malformed/duplicate review entries.
                    continue
        return {"runs_restored": restored, "feedback_restored": feedback_count}
