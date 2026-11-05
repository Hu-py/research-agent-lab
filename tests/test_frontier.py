import json
from pathlib import Path

import pytest

from research_agent_lab.contracts import Snapshot
from research_agent_lab.frontier.engine import FrontierConfig, run_frontier
from research_agent_lab.frontier.memory import MemoryStore
from research_agent_lab.frontier.mock import FrontierMockModel
from research_agent_lab.model import BudgetedModel


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "synthetic_snapshot.json"


def demo():
    return Snapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


def execute(tmp_path, generations=1, calls=30):
    with_context = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        model = BudgetedModel(FrontierMockModel(), max_calls=calls)
        result = run_frontier(
            demo(), model, with_context,
            FrontierConfig(max_generations=generations, max_papers=12)
        )
        return result
    finally:
        with_context.close()


def test_full_four_layers_and_lineage(tmp_path):
    report = execute(tmp_path)
    assert report["experiment_mode"] == "frontier"
    assert report["status"] == "needs_more_evidence"
    assert not report["novelty_verified"]
    assert not report["automatic_human_push"]
    assert report["human_review_required"]
    assert report["generation_count"] == 1
    assert len(report["lineage"]) == 5
    assert len(report["matches"]) == 6
    assert len(report["supervisor_decisions"]) == 2
    assert len(report["screening"]["jurors"]) == 2
    assert report["model_calls"] == 25
    assert any(x["parent_ids"] for x in report["lineage"])
    assert report["verification"]["primary_metric"]


def test_supervisor_hard_call_guard(tmp_path):
    report = execute(tmp_path, generations=3, calls=20)
    assert report["generation_count"] == 0
    assert report["supervisor_decisions"][-1]["hard_guard"]
    assert report["model_calls"] <= 20


def test_zero_generation(tmp_path):
    report = execute(tmp_path, generations=0)
    assert report["generation_count"] == 0
    assert len(report["lineage"]) == 3
    assert report["model_calls"] == 13


def test_feedback_updates_policy_not_machine_scores(tmp_path):
    store = MemoryStore(str(tmp_path / "feedback.sqlite"))
    try:
        assert store.select_strategy("line") == "balanced"
        store.record_run("run-1", "line", "balanced", best_title="A",
                         lessons=["review"], status="eligible")
        assert store.select_strategy("line") == "balanced"
        store.add_feedback("run-1", "reviewer-1", "reject", 15, 25, "weak")
        assert store.select_strategy("line") == "novelty"
        assert store.recall("line")
        with pytest.raises(Exception):
            store.add_feedback("run-1", "reviewer-1", "accept", 90, 90)
    finally:
        store.close()


def test_hypothesis_ids_are_unique(tmp_path):
    report = execute(tmp_path)
    ids = [x["id"] for x in report["lineage"]]
    assert len(ids) == len(set(ids))
    assert all(set(x["parent_ids"]) <= set(ids) for x in report["lineage"])
