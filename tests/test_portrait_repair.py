"""Large team evidence and strict LLM contract correction — no external API."""
import pytest

from research_agent_lab.portrait import (
    EvidenceBundle, PortraitStageError, _validate_with_repairs,
    synthesize_portrait, _validate_profile
)
from research_agent_lab.model import BudgetedModel, DeepSeekJSONModel


def big_bundle(n=36):
    return EvidenceBundle.model_validate({
        "bundle_id": "synthetic-36-team-outputs",
        "source": "authorized_database_export",
        "sharing_approved": True,
        "achievements": [
            {"id": "team-study-" + str(i).zfill(3),
             "title": "Synthetic spatial research paper " + str(i),
             "year": 2020 + i % 5} for i in range(n)
        ],
        "datasets": [], "external_papers": [],
    })


def profile(bundle, ids=None, unassigned=None):
    refs = ids if ids is not None else [a.id for a in bundle.achievements]
    return {
        "research_lines": [{
            "id": "spatial_science",
            "name": "Synthetic research cluster",
            "problem": "Can spatial generalization be measured?",
            "achievement_ids": refs,
            "dataset_ids": [], "external_paper_ids": [],
            "methods": ["Grouped evaluation"],
            "open_questions": ["What is an unseen region performance?"],
        }],
        "unassigned_achievement_ids": unassigned if unassigned is not None else [],
        "changes_from_previous": ["A synthetic grouping"],
    }


class RecoverModel:
    last_usage = {"input_tokens": 0, "output_tokens": 0}
    def __init__(self, bundle):
        self.bundle = bundle
        self.roles = []
    def complete(self, *, role, system, payload):
        self.roles.append(role)
        if role == "portrait_curator":
            return profile(self.bundle, ids=[x.id for x in self.bundle.achievements[:9]])
        if role == "portrait_contract_repair":
            assert "missing_achievement_ids" in payload["repair_feedback"]
            assert len(payload["repair_feedback"]["missing_achievement_ids"]) == 27
            return profile(self.bundle)
        if role == "portrait_critic":
            return {"issues": [], "must_revise": False, "summary": "Enough"}
        raise AssertionError(role)


def test_36_outputs_are_all_kept_and_model_repair_used():
    bundle = big_bundle()
    underlying = RecoverModel(bundle)
    model = BudgetedModel(underlying, max_calls=9)
    result = synthesize_portrait(bundle, model)
    assert len(result["research_lines"][0]["achievement_ids"]) == 36
    assert "portrait_contract_repair" in underlying.roles
    assert result["input_counts"]["public_dataset_metadata"] == 0
    assert result["input_counts"]["external_papers"] == 0
    assert model.usage.calls == 3


def test_fail_closed_after_bounded_repair_without_exposing_paper_title():
    b = big_bundle()
    class NeverFix:
        last_usage = {}
        def complete(self, *, role, system, payload):
            return profile(b, ids=[b.achievements[0].id])
    with pytest.raises(PortraitStageError, match="INCOMPLETE_ACHIEVEMENT_COVERAGE"):
        _validate_with_repairs(profile(b, ids=[]), b,
                               BudgetedModel(NeverFix()), stage="curator")


def test_no_silent_drop_when_one_group_has_more_than_25_papers():
    b = big_bundle()
    clean = _validate_profile(profile(b), b)
    assert len(clean["research_lines"][0]["achievement_ids"]) == 36


def test_increase_output_limit_only_when_requested(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    m = DeepSeekJSONModel(max_output_tokens=6000)
    assert m.max_output_tokens == 6000
    m.close()
    with pytest.raises(ValueError, match="max_output_tokens"):
        DeepSeekJSONModel(max_output_tokens=10000)
