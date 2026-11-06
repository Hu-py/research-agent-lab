from dataclasses import replace
from pathlib import Path

from research_agent_lab.contracts import Snapshot
from research_agent_lab.frontier.engine import run_frontier, FrontierConfig
from research_agent_lab.frontier.memory import MemoryStore
from research_agent_lab.frontier.mock import FrontierMockModel
from research_agent_lab.model import BudgetedModel
import pytest


def snapshot():
    base=Path(__file__).resolve().parents[1]/"examples"/"synthetic_snapshot.json"
    return Snapshot.model_validate_json(base.read_text(encoding="utf-8"))


def test_controlled_two_evolution_rounds_preserve_all_ancestors(tmp_path):
    snap=snapshot()
    memory=MemoryStore(str(tmp_path/"two_rounds.sqlite"))
    try:
        result=run_frontier(
            snap, BudgetedModel(FrontierMockModel(), max_calls=55),memory,
            FrontierConfig(
                max_generations=2, minimum_generations=2,
                max_papers=8, max_pairs_per_tournament=3
            )
        )
    finally:
        memory.close()
    assert result["generation_count"] == 2
    assert len(result["lineage"]) == 7  # 3 originals + 2 revisions + 2 revisions
    assert len([e for e in result["event_log"]
                if e["stage"] == "hypothesis_evolution"]) == 2
    rounds=[e for e in result["event_log"]
            if e["stage"] == "elo_tournament"]
    assert len(rounds)==3
    assert rounds[0]["matches"]==3  # all three unordered initial pairs
    assert len(result["matches"])==9
    assert sum(1 for d in result["supervisor_decisions"]
               if d["action"]=="evolve") == 2
    assert all(v["id"] for v in result["lineage"])
    assert result["novelty_verified"] is False


def test_minimum_rounds_cannot_exceed_maximum():
    with pytest.raises(ValueError, match="minimum_generations"):
        FrontierConfig(max_generations=1,minimum_generations=2)


def test_synthetic_toy_pilot_in_resilience_line(tmp_path):
    original=snapshot()
    derived=original.model_copy(update={
        "research_line": original.research_line.model_copy(update={
            "id":"resilience_measurement",
        })
    })
    memory=MemoryStore(str(tmp_path/"toy_sanity.sqlite"))
    try:
        result=run_frontier(
            derived,BudgetedModel(FrontierMockModel(),max_calls=25),memory,
            FrontierConfig(
                max_generations=0,minimum_generations=0,
                max_pairs_per_tournament=3,synthetic_pilot=True,
            )
        )
    finally:
        memory.close()
    assert result["pilot"]["status"] == "executed_synthetic_software_sanity_only"
    assert result["pilot"]["n_generated_experiments"] == 108
    assert result["pilot"]["experimental_claim_verified"] is False
    assert result["status"] == "needs_more_evidence"
    assert next(e for e in result["event_log"]
                if e["stage"] == "scientific_gate")["pilot_executed"] is True
