"""Synthetic regressions: invalid LLM proposals must not ruin the whole graph."""
from pathlib import Path

import pytest

from research_agent_lab.contracts import Snapshot
from research_agent_lab.frontier.engine import FrontierConfig, run_frontier
from research_agent_lab.frontier.mock import FrontierMockModel
from research_agent_lab.frontier.memory import MemoryStore
from research_agent_lab.model import BudgetedModel


FIXTURE = Path(__file__).resolve().parents[1] / "examples" / "synthetic_snapshot.json"


def example():
    return Snapshot.model_validate_json(FIXTURE.read_text(encoding="utf-8"))


class InvalidOneSeed(FrontierMockModel):
    def complete(self, *, role, system, payload):
        if role == "frontier_seed:method":
            return {"title": "Only title, missing required scientific fields"}
        if role == "frontier_candidate_repair":
            return {"title": "Still missing required fields"}
        return super().complete(role=role, system=system, payload=payload)


class InvalidChildren(FrontierMockModel):
    def complete(self, *, role, system, payload):
        if role.startswith("frontier_evolve:") or role == "frontier_candidate_repair":
            return {"title": "Only title"}
        return super().complete(role=role, system=system, payload=payload)


def test_one_bad_seed_is_excluded_without_inventing_it(tmp_path):
    memory=MemoryStore(str(tmp_path/"memory.sqlite"))
    try:
        result=run_frontier(
            example(), BudgetedModel(InvalidOneSeed(),max_calls=35),memory,
            FrontierConfig(max_generations=0,max_pairs_per_tournament=1)
        )
    finally:
        memory.close()
    ids=[x["id"] for x in result["lineage"]]
    assert ids==["H001","H003"]
    generated=next(e for e in result["event_log"] if e["stage"]=="generate")
    assert generated["rejected_count"]==1
    assert generated["rejected_candidates"][0]["id"]=="H002"
    assert len(result["matches"])==1
    assert result["status"]=="needs_more_evidence"


def test_no_valid_evolution_children_preserves_prior_ranked_studies(tmp_path):
    memory=MemoryStore(str(tmp_path/"memory.sqlite"))
    try:
        result=run_frontier(
            example(),BudgetedModel(InvalidChildren(),max_calls=40),memory,
            FrontierConfig(max_generations=1,minimum_generations=1,
                           max_pairs_per_tournament=1)
        )
    finally:
        memory.close()
    event=next(e for e in result["event_log"] if e["stage"]=="hypothesis_evolution")
    assert event["no_valid_children"] is True
    assert event["rejected_count"]==2
    assert event["children"]==[]
    assert result["generation_count"]==0
    assert len(result["lineage"])==3
    assert result["verification"]["primary_metric"]
    assert len([e for e in result["event_log"] if e["stage"]=="elo_tournament"])==1


def test_budget_and_evidence_constraints_do_not_get_bypassed(tmp_path):
    memory=MemoryStore(str(tmp_path/"memory.sqlite"))
    try:
        model=BudgetedModel(FrontierMockModel(),max_calls=3)
        with pytest.raises(ValueError,match="At least"):
            run_frontier(example(),model,memory,
                         FrontierConfig(max_generations=2,minimum_generations=2))
        assert model.usage.calls==0
    finally:
        memory.close()
