"""Read-only, evidence-aligned comparison of two research-lab experiments.

No LLM-as-judge conclusions. Never compare raw Elo across runs. No private
paper titles or candidate text in the automated report.
"""
from __future__ import annotations

import uuid

import httpx

from research_agent_lab.supabase_auth import headers, supabase_url


def read_run(run_id: str, *, client: httpx.Client | None = None) -> dict:
    try:
        verified_id = str(uuid.UUID(run_id))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("INVALID_EXPERIMENT_RUN_ID") from None
    owned = client is None
    http = client or httpx.Client(timeout=25, follow_redirects=False)
    try:
        try:
            resp = http.get(
                supabase_url() + "/rest/v1/lab_frontier_runs",
                headers=headers(),
                params={
                    "select": "id,line_id,strategy,status,model_calls,results,created_at",
                    "id": "eq." + verified_id, "limit": "1",
                },
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                "COMPARISON_STORE_HTTP_" + str(exc.response.status_code)
            ) from None
        except httpx.TransportError:
            raise RuntimeError("COMPARISON_STORE_TRANSPORT") from None
        rows = resp.json()
        if not isinstance(rows, list) or len(rows) > 1:
            raise RuntimeError("COMPARISON_UNEXPECTED_STORE_RESPONSE")
        if not rows:
            raise ValueError("COMPARISON_RUN_NOT_FOUND")
        return rows[0]
    finally:
        if owned:
            http.close()


def metrics(run: dict) -> dict:
    result = run.get("results")
    if not isinstance(result, dict):
        raise ValueError("COMPARISON_MISSING_RESULT")
    screening = result.get("screening") or {}
    verification = result.get("verification") or {}
    pilot = result.get("pilot") or {}
    ranked = result.get("ranked_candidates") or []
    lineage = result.get("lineage") or []
    matches = result.get("matches") or []
    if not all(isinstance(v, dict) for v in
               (screening, verification, pilot)):
        raise ValueError("COMPARISON_MALFORMED_RESULTS")
    for collection in (ranked, lineage, matches):
        if not isinstance(collection, list):
            raise ValueError("COMPARISON_MALFORMED_RESULTS")
    limit = verification.get("evidence_limitations") or []
    if not isinstance(limit, list):
        limit = []
    id_count = lambda values: len({v for v in values if isinstance(v, str)})
    disagreements = sum(1 for match in matches if
                        isinstance(match, dict) and
                        match.get("position_disagreement") is True)
    feasibility = result.get("feasibility") or {}
    return {
        "feasibility_precheck_eligible": int(feasibility.get("eligible_count") or 0),
        "feasibility_precheck_blocked": int(feasibility.get("blocked_count") or 0),
        "no_executable_candidates": run.get("status") == "no_executable_candidates",
        "generation_count": int(result.get("generation_count") or 0),
        "candidate_versions": len(lineage),
        "tournament_matches": len(matches),
        "position_disagreements": disagreements,
        "screened_papers": int(screening.get("screened_count") or 0),
        "retained_papers": int(screening.get("retained_count") or 0),
        "unresolved_screening_disagreements": len(
            screening.get("unresolved_disagreements") or []
        ),
        "winner_cited_papers": id_count(result.get("paper_ids") or []),
        "evidence_limitations_count": len(limit),
        "dataset_access_verified": verification.get(
            "dataset_access_evidence_verified"
        ) is True,
        "data_feasible_assessment": verification.get(
            "data_feasible_assessment"
        ) is True,
        "pilot_executed": str(pilot.get("status") or "").startswith("executed_"),
        "pilot_is_confirmatory": False,
        "novelty_verified": False,
        "human_review_required": True,
        "logical_model_calls": int(run.get("model_calls") or 0),
        "provider_calls": int(
            result.get("provider_calls", run.get("model_calls") or 0)
        ),
        "replay_cache_hits": int(result.get("cache_hits") or 0),
        "needs_more_evidence": run.get("status") == "needs_more_evidence",
    }


def compare_runs(baseline: dict, treatment: dict) -> dict:
    a = baseline.get("results") or {}
    b = treatment.get("results") or {}
    if not isinstance(a, dict) or not isinstance(b, dict):
        raise ValueError("COMPARISON_MISSING_RESULT")
    context_a, context_b = a.get("comparison_context"), b.get("comparison_context")
    reasons: list[str] = []
    notes: list[str] = []

    if baseline.get("line_id") != treatment.get("line_id"):
        reasons.append("DIFFERENT_RESEARCH_LINES")
    if not isinstance(context_a, dict) or not isinstance(context_b, dict):
        reasons.append("MISSING_COMPARISON_CONTEXT")
    else:
        required = {
            "initial_snapshot_id", "model_name", "dataset_ids",
            "retained_paper_ids", "max_papers", "max_pairs",
            "requested_generations",
        }
        if not required <= set(context_a) or not required <= set(context_b):
            reasons.append("INCOMPLETE_COMPARISON_CONTEXT")
        if context_a.get("initial_snapshot_id") != context_b.get("initial_snapshot_id"):
            reasons.append("DIFFERENT_PROFILE_SNAPSHOTS")
        if context_a.get("model_name") != context_b.get("model_name"):
            reasons.append("DIFFERENT_MODEL_IDS")
        if context_a.get("dataset_ids") != context_b.get("dataset_ids"):
            reasons.append("DIFFERENT_DATASET_CATALOGS")
        if context_a.get("retained_paper_ids") != context_b.get("retained_paper_ids"):
            reasons.append("DIFFERENT_SCREENED_EVIDENCE")
        if context_a.get("max_papers") != context_b.get("max_papers"):
            reasons.append("DIFFERENT_SEARCH_DEPTH")
        if context_a.get("max_pairs") != context_b.get("max_pairs"):
            reasons.append("DIFFERENT_TOURNAMENT_BUDGETS")
        if (context_a.get("requested_generations") or 0) != 0:
            notes.append("BASELINE_IS_NOT_ZERO_GENERATION")
        if (context_b.get("requested_generations") or 0) <= 0:
            notes.append("TREATMENT_HAS_NO_EVOLUTION")

    base_metrics, treat_metrics = metrics(baseline), metrics(treatment)
    differences = {
        key: treat_metrics[key] - base_metrics[key]
        for key in ("generation_count", "candidate_versions",
                    "tournament_matches", "position_disagreements",
                    "screened_papers", "retained_papers",
                    "unresolved_screening_disagreements",
                    "winner_cited_papers", "evidence_limitations_count",
                    "logical_model_calls", "provider_calls", "replay_cache_hits")
    }
    return {
        "analysis_kind": "descriptive_pairwise_audit_not_causal_effect",
        "baseline_run_id": baseline.get("id"),
        "treatment_run_id": treatment.get("id"),
        "comparability": "aligned_for_descriptive_comparison" if not reasons else "blocked",
        "blocking_reasons": reasons,
        "design_notes": notes,
        "baseline": base_metrics,
        "treatment": treat_metrics,
        "treatment_minus_baseline": differences,
        "no_cross_run_elo_comparison": True,
        "external_novelty_verification_performed": False,
        "blind_human_review_performed": False,
        "experiment_reproducibility_warning": (
            "Matching listed evidence and metadata cannot freeze model randomness, "
            "unrecorded OpenAlex query ranking or external LLM knowledge. "
            "Do not interpret deltas as causal effects or validated scientific improvements."
        ),
    }
