"""Never accept invented literature IDs or silently turn a missing vote into yes."""
from research_agent_lab.contracts import Snapshot, Paper, ResearchLine
from research_agent_lab.frontier.knowledge import independent_screen
from research_agent_lab.model import BudgetedModel


def snapshot():
    return Snapshot(
        snapshot_id="synthetic-2", provenance="approved_export",
        research_line=ResearchLine(id="p", name="Synthetic",
                                   problem="Assess evidence relevance"),
        papers=[
            Paper(id="paper-1", title="Synthetic paper one"),
            Paper(id="paper-2", title="Synthetic paper two"),
            Paper(id="paper-3", title="Synthetic paper three"),
        ],
    )


class MockDisagreement:
    last_usage = {}
    def __init__(self, repair=True):
        self.repair = repair
        self.calls = []

    def complete(self, *, role, system, payload):
        self.calls.append(role)
        if role.startswith("paper_juror_"):
            return {
                "assessments": [
                    {"paper_id": p["id"],
                     "retain": role == "paper_juror_a" or p["id"] == "paper-3",
                     "reason": "Mock review."}
                    for p in payload["papers"]
                ]
            }
        if role == "paper_adjudicator":
            # Deliberately omit one disagreement, despite valid JSON.
            return {"assessments": [
                {"paper_id": "paper-1", "retain": True, "reason": "Mock evidence"},
                {"paper_id": "unknown", "retain": True, "reason": "MALFORMED"}
            ]}
        if role == "paper_adjudicator_repair":
            assert payload["required_paper_ids"] == ["paper-2"]
            return {"assessments": (
                [{"paper_id": "paper-2", "retain": True,
                  "reason": "Mock corrected evidence"}] if self.repair
                else [{"paper_id": "UNKNOWN", "retain": True, "reason": "not trusted"}]
            )}
        raise AssertionError(role)


def test_targeted_repair_resolves_missing_disagreement():
    stub = MockDisagreement()
    model = BudgetedModel(stub, max_calls=6)
    screened, info = independent_screen(snapshot(), model)
    assert {p.id for p in screened.papers} == {"paper-1", "paper-2", "paper-3"}
    assert info["adjudication_attempts"] == 2
    assert info["unresolved_disagreements"] == []
    assert info["adjudication_complete"]
    assert model.usage.calls == 4
    assert stub.calls[-1] == "paper_adjudicator_repair"


def test_unresolved_disagreement_is_excluded_and_reported():
    stub = MockDisagreement(repair=False)
    screened, info = independent_screen(snapshot(), BudgetedModel(stub, max_calls=6))
    assert {p.id for p in screened.papers} == {"paper-1", "paper-3"}
    assert info["unresolved_disagreements"] == ["paper-2"]
    assert not info["adjudication_complete"]


def test_all_unresolved_is_not_approved_as_scientific_evidence():
    class NeverDecides(MockDisagreement):
        def complete(self, *, role, system, payload):
            if role.startswith("paper_juror_"):
                return {"assessments": [
                    {"paper_id": p["id"], "retain": role == "paper_juror_a",
                     "reason": "mock"}
                    for p in payload["papers"]
                ]}
            return {"assessments": []}
    import pytest
    with pytest.raises(ValueError, match="No literature survived"):
        independent_screen(snapshot(), BudgetedModel(NeverDecides(), max_calls=6))


def test_duplicate_judgment_is_unresolved_without_second_valid_vote():
    class Duplicate(MockDisagreement):
        def complete(self, *, role, system, payload):
            if role == "paper_adjudicator":
                return {"assessments": [
                    {"paper_id": "paper-1", "retain": True, "reason": "first"},
                    {"paper_id": "paper-1", "retain": False, "reason": "second"},
                    {"paper_id": "paper-2", "retain": True, "reason": "valid"},
                ]}
            if role == "paper_adjudicator_repair":
                assert payload["required_paper_ids"] == ["paper-1"]
                return {"assessments": []}
            return super().complete(role=role, system=system, payload=payload)
    screened, report = independent_screen(snapshot(), BudgetedModel(Duplicate(), max_calls=6))
    assert {p.id for p in screened.papers} == {"paper-2", "paper-3"}
    assert report["unresolved_disagreements"] == ["paper-1"]
