from pathlib import Path

from research_agent_lab.contracts import Snapshot
from research_agent_lab.frontier.engine import run_frontier, FrontierConfig
from research_agent_lab.frontier.memory import MemoryStore
from research_agent_lab.frontier.mock import FrontierMockModel
from research_agent_lab.model import BudgetedModel


def snapshot():
    return Snapshot.model_validate_json(
        (Path(__file__).resolve().parents[1] / "examples" /
         "synthetic_snapshot.json").read_text(encoding="utf-8")
    )


class ExpandMock(FrontierMockModel):
    def complete(self, *, role, system, payload):
        if role == "supervisor":
            return {
                "action": "expand" if payload["generation"] == 0 else "verify",
                "reason": "Controlled synthetic expansion test",
                "expected_gain": "none",
            }
        return super().complete(role=role, system=system, payload=payload)


class RollbackMock(FrontierMockModel):
    def complete(self, *, role, system, payload):
        if role == "supervisor":
            return {
                "action": "evolve" if payload["generation"] == 0 else "rollback",
                "reason": "Controlled synthetic rollback test",
                "expected_gain": "none",
            }
        return super().complete(role=role, system=system, payload=payload)


def test_expand_new_distinct_branch(tmp_path):
    memory = MemoryStore(str(tmp_path / "m1.sqlite"))
    try:
        result = run_frontier(snapshot(), BudgetedModel(ExpandMock(), max_calls=30),
                              memory, FrontierConfig(max_generations=1))
        assert any(e["stage"] == "hypothesis_expansion" for e in result["event_log"])
        assert len(result["lineage"]) == 4
        assert any(x["origin"] == "boundary" for x in result["lineage"])
    finally:
        memory.close()


def test_rollback_preserves_old_candidates(tmp_path):
    memory = MemoryStore(str(tmp_path / "m2.sqlite"))
    try:
        result = run_frontier(snapshot(), BudgetedModel(RollbackMock(), max_calls=30),
                              memory, FrontierConfig(max_generations=1))
        assert any(e["stage"] == "rollback" for e in result["event_log"])
        assert len(result["archived_candidates"]) == 2
        assert result["winner"]["generation"] == 0
        assert all(x["status"] == "archived" for x in result["archived_candidates"])
        assert len(result["lineage"]) == 5
    finally:
        memory.close()
