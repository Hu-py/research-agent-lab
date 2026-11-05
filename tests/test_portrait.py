"""Only fabricated team evidence is used in these tests."""
import json
import pytest

from research_agent_lab.portrait import (
    EvidenceBundle, evidence_hash, preview_from_original_inventory,
    synthesize_portrait, snapshot_for_line,
)
from research_agent_lab.model import BudgetedModel


def bundle():
    return EvidenceBundle.model_validate({
        "bundle_id": "fake-export-1", "source": "authorized_database_export",
        "sharing_approved": True,
        "achievements": [
            {"id": "achievement-1", "title": "Synthetic study of urban spatial mismatch",
             "year": 2024, "evidence_level": "title_only"},
            {"id": "achievement-2", "title": "Synthetic study of network transfer",
             "year": 2025, "evidence_level": "abstract",
             "abstract": "We benchmark spatial transfer under held-out regions."},
        ],
        "datasets": [{
            "id": "asset-1", "name": "Synthetic urban indicators",
            "coverage": "Generic city", "fields": ["grid_id", "x", "target"],
            "sensitivity": "public", "access_verified": False,
        }],
        "external_papers": [{
            "id": "paper-1", "title": "External scientific reference",
            "ownership": "external_literature"
        }],
        "old_profile": {"research_lines": [{"id": "old-theme", "name": "Generic AI"}]}
    })


class FakePortraitModel:
    last_usage = {"input_tokens": 0, "output_tokens": 0}

    def complete(self, *, role, system, payload):
        if role in ("portrait_curator", "portrait_reviser"):
            return {
                "research_lines": [{
                    "id": "urban_transfer",
                    "name": "Urban learning generalization",
                    "problem": "Why do spatial models fail when extrapolating?",
                    "achievement_ids": ["achievement-1", "achievement-2"],
                    "dataset_ids": ["asset-1"],
                    "external_paper_ids": ["paper-1"],
                    "methods": ["Grouped generalization benchmark"],
                    "open_questions": ["Can a new region disprove the model?"],
                }],
                "unassigned_achievement_ids": [],
                "changes_from_previous": ["Replace broad AI line by a falsifiable problem"],
            }
        if role == "portrait_critic":
            return {"issues": ["Title-only first work needs explicit uncertainty"],
                    "must_revise": False, "summary": "Use evidence levels"}
        raise ValueError(role)


def test_portrait_grounds_every_output_and_uncertainty():
    b = bundle()
    model = BudgetedModel(FakePortraitModel(), max_calls=3)
    result = synthesize_portrait(b, model)
    assert result["research_lines"][0]["id"] == "urban_transfer"
    assert result["research_lines"][0]["evidence_status"] == "described_in_verified_team_outputs"
    assert result["research_lines"][0]["data_access_verified"] is False
    assert result["version_status"] == "provisional_not_official"
    assert result["source_evidence_hash"] == evidence_hash(b)
    assert model.usage.calls == 2


def test_snapshot_from_profile():
    b = bundle()
    result = synthesize_portrait(b, BudgetedModel(FakePortraitModel()))
    snap = snapshot_for_line(b, result, "urban_transfer")
    assert snap.papers[0].id == "paper-1"
    assert snap.datasets[0].id == "asset-1"
    assert snap.research_line.problem.startswith("Why")
    assert snap.provenance == "approved_export"


def test_external_literature_not_team_achievement():
    b = bundle()
    data = b.model_dump()
    data["achievements"][0]["id"] = "paper-1"
    with pytest.raises(ValueError, match="unique"):
        EvidenceBundle.model_validate(data)


def test_missing_team_output_rejected():
    b = bundle()
    class Omit(FakePortraitModel):
        def complete(self, *, role, system, payload):
            answer = super().complete(role=role, system=system, payload=payload)
            if role == "portrait_curator":
                answer["research_lines"][0]["achievement_ids"] = ["achievement-1"]
            return answer
    with pytest.raises(ValueError, match="covered or explicitly"):
        synthesize_portrait(b, BudgetedModel(Omit()), iterations=0)


def test_legacy_inventory_is_not_implicitly_approved():
    preview = preview_from_original_inventory({
        "evidence_source": "postgresql_only",
        "team_achievements": [{"id": "a1", "title": "Example", "year": 2025, "kind": "paper"}],
        "datasets": [{"id": "private-asset", "name": "Restricted dataset"}],
        "approved_papers": [],
        "profile": {"research_lines": []},
    })
    assert preview["sharing_approved"] is False
    assert preview["datasets"] == []
    assert preview["omitted_unverified_dataset_count"] == 1
    with pytest.raises(Exception):
        EvidenceBundle.model_validate(preview)
