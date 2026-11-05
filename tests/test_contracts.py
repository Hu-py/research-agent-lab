from pathlib import Path

import pytest
from research_agent_lab.contracts import (
    Snapshot, validate_candidate, validate_challenges, validate_review,
)
from research_agent_lab.model import BudgetedModel, BudgetExceeded, MockJSONModel

FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "synthetic_snapshot.json"


def example():
    return Snapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def valid_candidate():
    raw = MockJSONModel().complete(
        role="seed:problem", system="", payload={"snapshot": example().model_dump()}
    )
    return raw


def test_unknown_papers_rejected():
    candidate = valid_candidate()
    candidate["paper_ids"] = ["fabricated-paper-DOI"]
    with pytest.raises(ValueError, match="absent"):
        validate_candidate(candidate, example(), "problem")


def test_unregistered_data_rejected():
    candidate = valid_candidate()
    candidate["dataset_ids"] = ["secret"]
    with pytest.raises(ValueError, match="absent"):
        validate_candidate(candidate, example(), "problem")


def test_malformed_review_rejected():
    bad = {"ranked": [{
        "candidate_id": "problem", "novelty": 150,
        "feasibility": 10, "testability": 10, "evidence": 10
    }], "needs_revision": False, "reason": "no"}
    with pytest.raises(ValueError, match="0..100"):
        validate_review(bad, {"problem"})


def test_challenges_require_every_candidate():
    with pytest.raises(ValueError, match="Every candidate"):
        validate_challenges({"challenges": [{
            "candidate_id": "problem", "objections": ["a"], "counter_test": "b"
        }]}, {"problem", "method"})


def test_call_budget_is_hard_stop():
    model = BudgetedModel(MockJSONModel(), max_calls=1)
    kwargs = {"role": "seed:problem", "system": "", "payload": {"snapshot": example().model_dump()}}
    model.complete(**kwargs)
    with pytest.raises(BudgetExceeded):
        model.complete(**kwargs)
    assert model.usage.calls == 1


def test_token_reservation_is_hard_stop():
    model = BudgetedModel(MockJSONModel(), max_calls=5, max_reserved_tokens=6499)
    kwargs = {"role": "seed:problem", "system": "", "payload": {"snapshot": example().model_dump()}}
    with pytest.raises(BudgetExceeded, match="token"):
        model.complete(**kwargs)
    assert model.usage.calls == 0
