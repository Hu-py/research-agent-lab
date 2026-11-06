"""Evidence provenance, graph versioning, opportunity genealogy, and safe writes."""
import json
import uuid

import httpx
import pytest

from research_agent_lab.portrait import EvidenceBundle, evidence_hash
from research_agent_lab.knowledge_graph import (
    portrait_graph, opportunity_graph, problem_context,
)
from research_agent_lab.knowledge_store import persist_graph, check_graph_store


def team_bundle():
    return EvidenceBundle.model_validate({
        "bundle_id": "synthetic-research-team",
        "source": "authorized_database_export",
        "sharing_approved": True,
        "achievements": [
            {"id": "team-paper-a", "title": "Synthetic mobility research",
             "year": 2024, "evidence_level": "title_only"},
            {"id": "team-paper-b", "title": "Synthetic resilience research",
             "year": 2025, "evidence_level": "abstract",
             "abstract": "We studied group robustness with spatial baselines."},
        ],
        "datasets": [
            {"id": "asset-one", "name": "Synthetic spatial dataset",
             "fields": ["grid_id", "year"], "sensitivity": "public",
             "access_verified": False},
        ],
        "external_papers": [
            {"id": "external-article", "title": "Synthetic reference from literature",
             "venue": "Fictional Journal"},
        ],
    })


def team_portrait(bundle=None):
    b = bundle or team_bundle()
    return {
        "source_evidence_hash": evidence_hash(b),
        "research_lines": [
            {"id": "mobility_research", "name": "Urban mobility mechanisms",
             "problem": "What causes spatial activity disparities?",
             "achievement_ids": ["team-paper-a", "team-paper-b"],
             "dataset_ids": ["asset-one"],
             "external_paper_ids": ["external-article"],
             "methods": ["Graph learning", "Spatial validation"],
             "open_questions": ["What is the out-of-city prediction error?"],
             "evidence_status": "title_based_inference"},
        ],
        "unassigned_achievement_ids": [],
        "changes_from_previous": ["Clarity of prior evidence was improved"],
    }


def test_four_perspectives_and_evidence_traceability():
    b = team_bundle()
    batch = portrait_graph(b, team_portrait(b))
    assert {n["kind"] for n in batch.nodes} == {
        "research_problem", "research_method", "data_asset",
        "team_output", "external_paper",
    }
    assert batch.counts()["node_versions"] == batch.counts()["nodes"]
    assert all(ev["source_id"] in {s["id"] for s in batch.sources}
               for ev in batch.evidence)
    assert all(n["epistemic_status"] != "human_verified" for n in batch.nodes)
    assert all(e["epistemic_status"] != "human_verified" for e in batch.edges)
    ctx = problem_context(batch, "mobility_research")
    rels = {r["relation"] for r in ctx["relationships"]}
    assert {"BASED_ON_OUTPUT", "POTENTIALLY_USES_DATA",
            "PROPOSES_METHOD", "CONSIDERS_LITERATURE"} <= rels
    method = [n for n in batch.nodes if n["kind"] == "research_method"][0]
    assert method["attributes"]["team_capability_verified"] is False
    asset = next(n for n in batch.nodes if n["kind"] == "data_asset")
    assert asset["attributes"]["access_verified"] is False


def test_stable_keys_and_append_only_revisions():
    b = team_bundle()
    p = team_portrait(b)
    first = portrait_graph(b, p)
    again = portrait_graph(b, p)
    assert first == again
    p["research_lines"][0]["problem"] = "A clarified scientific question"
    changed = portrait_graph(b, p)
    old = {n["node_key"]: n for n in first.nodes}
    new = {n["node_key"]: n for n in changed.nodes}
    assert old["research_problem:mobility_research"]["id"] == new["research_problem:mobility_research"]["id"]
    old_version = next(x for x in first.node_versions if x["node_id"] ==
                       old["research_problem:mobility_research"]["id"])
    new_version = next(x for x in changed.node_versions if x["node_id"] ==
                       new["research_problem:mobility_research"]["id"])
    assert old_version["id"] != new_version["id"]


def test_forged_portrait_references_rejected():
    b = team_bundle()
    p = team_portrait(b)
    p["research_lines"][0]["dataset_ids"] = ["nonexistent"]
    with pytest.raises(ValueError, match="Unknown data asset"):
        portrait_graph(b, p)
    p = team_portrait(b)
    p["source_evidence_hash"] = "wrong"
    with pytest.raises(ValueError, match="hashes differ"):
        portrait_graph(b, p)


def dummy_run():
    rid = str(uuid.UUID("ebf7391e-0ea0-486b-99dc-5e5b442eb720"))
    def candidate(cid, parent, generation, paper_ids):
        return {
            "id": cid, "title": "Hypothesis " + cid, "question": "Can this be falsified?",
            "method": "Grouped model", "mechanism": "Spatial effect",
            "falsifiable_prediction": "Lift under blocked split",
            "minimal_experiment": "Compare with OLS", "baselines": ["OLS"],
            "dataset_ids": ["asset-one"],
            "paper_ids": paper_ids, "parent_ids": parent,
            "generation": generation, "elo": 1200.0,
            "status": "candidate",
        }
    return {
        "run_id": rid, "line_id": "mobility_research",
        "winner": {"id": "H002"},
        "ranked_candidates": [
            candidate("H001", [], 0, ["external-article"]),
            candidate("H002", ["H001"], 1, ["https://openalex.org/W1234"]),
        ],
        "archived_candidates": [],
    }


def test_frontier_version_dag_and_unresolved_openalex_metadata():
    b = team_bundle()
    batch = opportunity_graph(b, team_portrait(b), dummy_run())
    assert len(batch.opportunity_versions) == 2
    assert len(set(x["id"] for x in batch.opportunity_versions)) == 2
    assert any(e["relation"] == "EVOLVED_FROM" for e in batch.edges)
    selected = next(x for x in batch.opportunity_versions if x["candidate_key"] == "H002")
    assert selected["outcome"] == "selected"
    assert selected["parent_candidate_keys"] == ["H001"]
    assert "paper:https://openalex.org/W1234" in batch.diagnostics["unresolved_frontier_references"]


def test_reject_unknown_parent_before_write():
    b = team_bundle()
    run = dummy_run()
    run["ranked_candidates"][1]["parent_ids"] = ["not-a-candidate"]
    with pytest.raises(ValueError, match="unknown ancestors"):
        opportunity_graph(b, team_portrait(b), run)


def test_supabase_writer_uses_idempotent_conflict_keys(monkeypatch):
    b = team_bundle()
    batch = portrait_graph(b, team_portrait(b))
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_dummy_test_key")
    requests = []
    def transport(req: httpx.Request):
        requests.append(req)
        assert req.headers.get("apikey") == "sb_secret_dummy_test_key"
        assert "authorization" not in req.headers
        if req.method == "GET":
            return httpx.Response(200, json=[])
        if req.method == "POST":
            parsed = json.loads(req.content)
            assert all(row["scope"] == b.bundle_id for row in parsed)
            return httpx.Response(201)
        return httpx.Response(400)
    with httpx.Client(transport=httpx.MockTransport(transport)) as http:
        counts = persist_graph(batch, client=http)
    assert counts["nodes"] == len(batch.nodes)
    assert len([req for req in requests if req.method == "GET"]) == 6
    urls = [str(req.url) for req in requests if req.method == "POST"]
    assert any("/kg_node_versions" in url and "on_conflict=" in url for url in urls)
    assert all(not any(x in str(req.url) for x in ("lab_profile_versions", "profiles"))
               for req in requests)


def test_writer_rejects_broken_edge_without_network(monkeypatch):
    b = team_bundle()
    batch = portrait_graph(b, team_portrait(b))
    batch.edges[0]["to_node"] = str(uuid.uuid4())
    with pytest.raises(ValueError, match="unresolved edge endpoint"):
        persist_graph(batch)


def test_read_problem_context_missing_raises():
    b = team_bundle()
    with pytest.raises(ValueError, match="not in"):
        problem_context(portrait_graph(b, team_portrait(b)), "unlisted")
