"""Evaluation must never claim scientific improvement from raw Elo or mismatched papers."""
import pytest
import httpx

from research_agent_lab.frontier.audit import compare_runs, read_run


def make_run(run_id, generation=0, papers=None, model="deepseek-flash"):
    p = papers if papers is not None else ["P1", "P2"]
    return {
        "id":run_id, "line_id":"line-a", "strategy":"balanced",
        "model_calls":15+generation*10, "status":"needs_more_evidence",
        "results":{
            "snapshot_id":"same-profile",
            "generation_count":generation,
            "provider_calls":15+generation*7,
            "cache_hits":generation*3,
            "comparison_context":{
                "initial_snapshot_id":"same-profile","model_name":model,
                "retained_paper_ids":p,"dataset_ids":["D1"],
                "max_papers":6,"max_pairs":3,
                "requested_generations":generation,
            },
            "lineage":[{"id":"H1"}]*(3+generation*2),
            "matches":[{"position_disagreement":False}]*(3+generation*3),
            "screening":{"screened_count":6,"retained_count":len(p),
                         "unresolved_disagreements":[]},
            "verification":{"evidence_limitations":["dataset inaccessible"],
                            "data_feasible_assessment":False},
            "pilot":{},
            "ranked_candidates":[],
            "paper_ids":["P1"]
        }
    }


def test_aligned_run_comparison_is_descriptive_not_causal():
    a=make_run("baseline",0)
    b=make_run("treatment",2)
    report=compare_runs(a,b)
    assert report["comparability"]=="aligned_for_descriptive_comparison"
    assert report["treatment_minus_baseline"]["candidate_versions"]==4
    assert report["treatment_minus_baseline"]["provider_calls"]==14
    assert report["no_cross_run_elo_comparison"] is True
    assert report["external_novelty_verification_performed"] is False
    assert report["blind_human_review_performed"] is False


def test_paper_or_model_mismatch_blocks_interpretation():
    a=make_run("a")
    b=make_run("b",2,papers=["P1", "P3"],model="another")
    result=compare_runs(a,b)
    assert result["comparability"]=="blocked"
    assert "DIFFERENT_SCREENED_EVIDENCE" in result["blocking_reasons"]
    assert "DIFFERENT_MODEL_IDS" in result["blocking_reasons"]


def test_legacy_run_without_comparison_context_blocked():
    a=make_run("a")
    b=make_run("b",2)
    del b["results"]["comparison_context"]
    assert "MISSING_COMPARISON_CONTEXT" in compare_runs(a,b)["blocking_reasons"]


def test_run_id_validation_rejects_arbitrary_query():
    with pytest.raises(ValueError, match="INVALID_EXPERIMENT_RUN_ID"):
        read_run("a);drop table lab_frontier_runs;")


def test_store_reader_uses_new_secret_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY","sb_secret_fake")
    uid="00000000-0000-4000-8000-000000000001"
    seen=[]
    def handler(request):
        seen.append(request)
        return httpx.Response(200,json=[make_run(uid)])
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        got=read_run(uid,client=client)
    assert got["id"]==uid
    assert seen[0].headers["apikey"]=="sb_secret_fake"
    assert seen[0].url.params["id"]=="eq."+uid


def test_missing_context_fields_fail_closed():
    a=make_run("a")
    b=make_run("b",2)
    del b["results"]["comparison_context"]["retained_paper_ids"]
    assert "INCOMPLETE_COMPARISON_CONTEXT" in compare_runs(a,b)["blocking_reasons"]
