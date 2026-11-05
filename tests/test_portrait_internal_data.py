import pytest
from research_agent_lab.portrait import EvidenceBundle, synthesize_portrait, snapshot_for_line
from research_agent_lab.model import BudgetedModel


def input_bundle(approved: bool):
    return {
        "bundle_id": "fake-internal-export",
        "source": "authorized_database_export",
        "sharing_approved": True,
        "achievements": [{
            "id": "paper-one", "title": "Synthetic example output",
            "year": 2025
        }],
        "datasets": [{
            "id": "internal-asset",
            "name": "Approved aggregate metadata only",
            "sensitivity": "internal_metadata_approved",
            "metadata_sharing_approved": approved,
            "fields": [], "access_verified": False
        }],
    }


def test_internal_data_without_approval_rejected():
    with pytest.raises(Exception, match="requires explicit sharing approval"):
        EvidenceBundle.model_validate(input_bundle(False))


class SmallModel:
    last_usage = {}
    def complete(self, *, role, system, payload):
        if role == "portrait_curator":
            return {
                "research_lines": [{
                    "id": "urban_networks",
                    "name": "Urban network science",
                    "problem": "Can a network signal generalize?",
                    "achievement_ids": ["paper-one"],
                    "dataset_ids": ["internal-asset"],
                    "external_paper_ids": [], "methods": [],
                    "open_questions": ["Is out of sample accuracy stable?"]
                }],
                "unassigned_achievement_ids": [], "changes_from_previous": [],
            }
        if role == "portrait_critic":
            return {"issues": [], "must_revise": False}
        raise AssertionError(role)


def test_approved_internal_metadata_stays_internal_in_frontier():
    bundle = EvidenceBundle.model_validate(input_bundle(True))
    profile = synthesize_portrait(bundle, BudgetedModel(SmallModel()))
    snap = snapshot_for_line(bundle, profile, "urban_networks")
    assert snap.datasets[0].sensitivity == "internal"
    assert not profile["research_lines"][0]["data_access_verified"]
