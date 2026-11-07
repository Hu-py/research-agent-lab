"""No live keys, API use or research-team evidence in these tests."""
import pytest

from research_agent_lab.contracts import Snapshot, Paper, Dataset, ResearchLine
from research_agent_lab.frontier.competition import make_candidate, create_seed_candidates
from research_agent_lab.model import BudgetedModel


def snapshot():
    return Snapshot(
        snapshot_id="synthetic-test",
        provenance="synthetic_demo",
        research_line=ResearchLine(
            id="synthetic-method", name="Fictional spatial research",
            problem="Do held-out groups generalize?"
        ),
        papers=[Paper(id="paper-1", title="Synthetic evidence")],
        datasets=[],
    )


def candidate(**overrides):
    c = {
        "title": "Synthetic test hypothesis",
        "question": "Can grouped validation detect false generalization?",
        "mechanism": "Missing context may reduce generalization.",
        "falsifiable_prediction": "Held-out error increases without context.",
        "method": "Grouped spatial regression",
        "minimal_experiment": "Compare grouped and random splits",
        "baselines": ["Train-only mean"],
        "paper_ids": ["paper-1"],
        "dataset_ids": [],
        "limitations": ["Data access not established"],
    }
    return {**c, **overrides}


class Fixer:
    last_usage = {}
    def __init__(self, replacement):
        self.replacement = replacement
        self.calls = []

    def complete(self, *, role, system, payload):
        self.calls.append(role)
        if role == "frontier_candidate_repair":
            assert payload["allowed_paper_ids"] == ["paper-1"]
            assert payload["allowed_dataset_ids"] == []
            return self.replacement
        if role.startswith("frontier_seed:"):
            return candidate(limitations={"sample": "too small"})
        raise AssertionError(role)


def test_plain_singleton_limitation_is_losslessly_converted_without_extra_call():
    model = BudgetedModel(Fixer(candidate()), max_calls=2)
    c = make_candidate(
        candidate(limitations="Limited external validation"),
        snapshot(), identifier="H001", origin="method", parent_ids=[],
        generation=0, model=model
    )
    assert c["limitations"] == ["Limited external validation"]
    assert model.usage.calls == 0


def test_nested_limitation_requires_one_evidence_checked_repair():
    model = BudgetedModel(Fixer(candidate()), max_calls=2)
    c = make_candidate(
        candidate(limitations={"risk": "sample leakage"}),
        snapshot(), identifier="H001", origin="method", parent_ids=[],
        generation=0, model=model
    )
    assert c["limitations"] == ["Data access not established"]
    assert model.usage.calls == 1


def test_repair_preserves_original_registered_citation_when_llm_fabricates_id():
    model = BudgetedModel(Fixer(candidate(paper_ids=["invented-paper"])), max_calls=2)
    fixed = make_candidate(
        candidate(limitations={"risk": "short sample"}),
        snapshot(), identifier="H001", origin="method", parent_ids=[],
        generation=0, model=model
    )
    # Reject invalid replacement reference; preserve only existing registered evidence.
    assert fixed["paper_ids"] == ["paper-1"]
    assert "invented-paper" not in fixed["paper_ids"]


def test_repair_preserves_valid_original_baseline_if_corrected_drops_it():
    model = BudgetedModel(Fixer(candidate(baselines=[])), max_calls=2)
    repaired = make_candidate(
        candidate(limitations={"risk": "short sample"}),
        snapshot(), identifier="H001", origin="method", parent_ids=[],
        generation=0, model=model
    )
    assert repaired["baselines"] == ["Train-only mean"]
    assert model.usage.calls == 1


def test_model_budget_restricts_repair():
    model = BudgetedModel(Fixer(candidate()), max_calls=0)
    with pytest.raises(RuntimeError, match="Model-call ceiling"):
        make_candidate(
            candidate(limitations={"risk": "short sample"}),
            snapshot(), identifier="H001", origin="method", parent_ids=[],
            generation=0, model=model
        )


def test_three_seed_candidates_with_malformed_lists_are_repaired_and_traced():
    stub = Fixer(candidate())
    model = BudgetedModel(stub, max_calls=6)
    all_candidates = create_seed_candidates(snapshot(), model, "balanced", [])
    assert len(all_candidates) == 3
    assert model.usage.calls == 6
    assert stub.calls.count("frontier_candidate_repair") == 3
    assert all(x["paper_ids"] == ["paper-1"] for x in all_candidates)


def test_valid_candidate_retains_existing_no_extra_calls():
    model = BudgetedModel(Fixer(candidate()), max_calls=1)
    c = make_candidate(
        candidate(), snapshot(), identifier="H005", origin="problem",
        parent_ids=[], generation=1, model=model
    )
    assert c["status"] == "candidate"
    assert model.usage.calls == 0



def test_truly_unregistered_paper_cannot_pass_after_two_repair_attempts():
    model = BudgetedModel(Fixer(candidate(paper_ids=["invented-paper"])), max_calls=3)
    with pytest.raises(ValueError, match="UNREGISTERED_PAPER_ID"):
        make_candidate(
            candidate(paper_ids=["invented-paper"], limitations={"risk":"short sample"}),
            snapshot(), identifier="H001", origin="method", parent_ids=[],
            generation=0, model=model
        )
    assert model.usage.calls == 2


def test_second_repair_can_fix_missing_required_scientific_field():
    class IncompleteFixer(Fixer):
        def complete(self, *, role, system, payload):
            if role == "frontier_candidate_repair":
                self.calls.append((role, payload["invalid_field"]))
                if len(self.calls) == 1:
                    return candidate(method="", question="")
                return candidate(method="Grouped spatial regression", question="")
            raise AssertionError(role)

    model = BudgetedModel(IncompleteFixer(candidate()), max_calls=3)
    corrected = make_candidate(
        candidate(method="", question="Original falsifiable question"),
        snapshot(), identifier="H004", origin="refine", parent_ids=["H001"],
        generation=1, model=model
    )
    assert corrected["method"] == "Grouped spatial regression"
    assert corrected["question"] == "Original falsifiable question"
    assert model.usage.calls == 2
