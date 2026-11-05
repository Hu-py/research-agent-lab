import json
from pathlib import Path

from research_agent_lab.contracts import Snapshot
from research_agent_lab.model import BudgetedModel, MockJSONModel
from research_agent_lab.workflow import run_experiment


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "synthetic_snapshot.json"


def example():
    return Snapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def run(mode):
    budget = BudgetedModel(MockJSONModel(), max_calls=30)
    return run_experiment(example(), mode, budget, max_rounds=2)


def test_single_baseline():
    result = run("single")
    assert result["model_calls"] == 2
    assert result["rounds_completed"] == 0
    assert len(result["all_candidates"]) == 1
    assert result["human_review_required"]
    assert not result["novelty_verified"]


def test_fixed_multi_agent_two_rounds():
    result = run("fixed")
    assert result["model_calls"] == 14
    assert result["rounds_completed"] == 2
    assert len(result["all_candidates"]) == 3
    assert len(result["score_history"]) == 3
    assert result["review"]["llm_assessed_only"]


def test_adaptive_early_stop():
    result = run("adaptive")
    assert result["rounds_completed"] == 1
    assert result["model_calls"] == 9
    assert len(result["score_history"]) == 2
    assert result["winner"]["paper_ids"]


def test_no_rounds_for_fixed():
    budget = BudgetedModel(MockJSONModel())
    result = run_experiment(example(), "fixed", budget, max_rounds=0)
    assert result["rounds_completed"] == 0
    assert result["model_calls"] == 4


def test_determinism():
    first = run("adaptive")
    second = run("adaptive")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
