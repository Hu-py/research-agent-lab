from research_agent_lab.model import BudgetedModel
from research_agent_lab.portrait_cli import generate, select_research_line
from research_agent_lab.portrait import EvidenceBundle


class Dummy:
    last_usage = {"input_tokens":0,"output_tokens":0}

    def complete(self, *, role, system, payload):
        if role == "portrait_curator":
            return {
                "research_lines": [{
                    "id": "urban_resilience",
                    "name": "Urban resilience research",
                    "problem": "Which features govern spatial transfer?",
                    "achievement_ids": ["ach1"], "dataset_ids": [],
                    "external_paper_ids": [], "methods": [],
                    "open_questions": ["Transfer beyond training zones?"],
                }],
                "unassigned_achievement_ids": [],
                "changes_from_previous": ["Sharper research question"],
            }
        if role == "portrait_critic":
            return {"issues": [], "must_revise": False, "summary": "Evidence grounded"}
        if role == "research_line_selector":
            return {"line_id": "urban_resilience", "reason": "Testable question",
                    "next_test": "Cross-region holdout"}
        raise AssertionError(role)


def test_research_profile_flows_into_frontier_snapshot():
    bundle = EvidenceBundle.model_validate({
        "bundle_id": "team-example", "source": "authorized_database_export",
        "sharing_approved": True,
        "achievements": [
            {"id": "ach1", "title": "Fictitious resilient cities study",
             "year": 2025, "ownership": "verified_team_output"}
        ],
    })
    model = BudgetedModel(Dummy(), max_calls=5)
    report, snapshot = generate(bundle, model, use_remote_store=False)
    assert report["official_team_profile_modified"] is False
    assert report["recalibration"] == "regenerated_from_evidence"
    assert report["selection"]["line_id"] == "urban_resilience"
    assert snapshot.research_line.id == "urban_resilience"
    assert snapshot.papers == []
    assert model.usage.calls == 3
