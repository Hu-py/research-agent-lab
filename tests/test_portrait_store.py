"""A profile version must not overwrite the existing team profile."""
from research_agent_lab.portrait import EvidenceBundle
from research_agent_lab.portrait_cli import generate
from research_agent_lab.model import BudgetedModel


class Stub:
    last_usage = {}
    def complete(self, *, role, system, payload):
        if role == "portrait_curator":
            return {"research_lines": [
                {"id": "spatial_learning", "name": "Spatial learning",
                 "problem": "Which generalizations survive out-of-city testing?",
                 "achievement_ids": ["a1"], "dataset_ids": [],
                 "external_paper_ids": [], "methods": [],
                 "open_questions": ["How does performance vary?"]}
            ], "unassigned_achievement_ids": [],
                "changes_from_previous": ["Corrected an overly broad prior profile"]}
        if role == "portrait_critic":
            return {"issues": [], "must_revise": False, "summary": "Sufficient"}
        if role == "research_line_selector":
            return {"line_id": "spatial_learning", "reason": "Falsifiable",
                    "next_test": "Hold out a new city"}
        raise AssertionError(role)


def fake_bundle():
    return EvidenceBundle.model_validate({
        "bundle_id": "team", "source": "authorized_database_export",
        "sharing_approved": True,
        "achievements": [{"id":"a1", "title":"Synthetic urban study", "year":2023}]
    })


def test_portrait_cache_avoids_repeated_llm_calls(monkeypatch):
    b = fake_bundle()
    fresh_model = BudgetedModel(Stub(), max_calls=5)
    result, _ = generate(b, fresh_model, use_remote_store=False)
    assert fresh_model.usage.calls == 3

    monkeypatch.setattr("research_agent_lab.portrait_cli.latest_portrait",
                        lambda bundle_id: {
                            "id": "a-version", "version": 1,
                            "evidence_hash": result["source_evidence_hash"],
                            "portrait": result["profile"],
                        })
    cached_model = BudgetedModel(Stub(), max_calls=5)
    cached, _ = generate(b, cached_model, use_remote_store=True)
    assert cached_model.usage.calls == 1
    assert cached["recalibration"] == "cached_same_evidence"


def test_force_refresh_generates_new_version(monkeypatch):
    b = fake_bundle()
    first, _ = generate(b, BudgetedModel(Stub()), use_remote_store=False)
    monkeypatch.setattr("research_agent_lab.portrait_cli.latest_portrait",
                        lambda bundle_id: {
                            "id": "first", "version": 1,
                            "evidence_hash": first["source_evidence_hash"],
                            "portrait": first["profile"],
                        })
    writes = []
    def save(bundle_id, source_hash, profile, previous):
        writes.append((bundle_id,source_hash))
        return {"id": "second", "version": 2}
    monkeypatch.setattr("research_agent_lab.portrait_cli.persist_portrait", save)
    report, _ = generate(b, BudgetedModel(Stub()), use_remote_store=True, refresh=True)
    assert report["profile_record"]["version"] == 2
    assert report["recalibration"] == "regenerated_from_evidence"
    assert len(writes) == 1
