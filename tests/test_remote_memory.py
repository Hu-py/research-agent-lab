"""Cloud memory is safely hydrated from isolated Supabase records (no HTTP)."""
from research_agent_lab.frontier import remote_memory
from research_agent_lab.frontier.memory import MemoryStore


def test_restore_runs_and_human_feedback(tmp_path, monkeypatch):
    rows = [{
        "id": "91a8232b-88e0-4357-a8c8-e8fae590550a",
        "line_id": "public-test-line",
        "strategy": "balanced",
        "status": "needs_more_evidence",
        "results": {
            "winner_title": "Falsifiable urban learning",
            "verification": {"evidence_limitations": ["Cross-city test missing"]}
        }
    }]
    feedback = [{
        "run_id": rows[0]["id"],
        "reviewer_tag": "domain-expert",
        "decision": "reject",
        "novelty": 20,
        "feasibility": 30,
        "comment": "Needs external data"
    }]

    def fake_get(client, table, params):
        assert params
        if table == "lab_frontier_runs":
            assert params["line_id"] == "eq.public-test-line"
            return rows
        if table == "lab_frontier_feedback":
            return feedback
        raise AssertionError(table)

    monkeypatch.setattr(remote_memory, "_get", fake_get)
    memory = MemoryStore(str(tmp_path / "sqlite.sqlite"))
    try:
        summary = remote_memory.hydrate_recent_memory(memory, "public-test-line")
        assert summary == {"runs_restored": 1, "feedback_restored": 1}
        assert memory.select_strategy("public-test-line") == "novelty"
        assert any("Falsifiable" in e["summary"] for e in memory.recall("public-test-line"))
        again = remote_memory.hydrate_recent_memory(memory, "public-test-line")
        assert again["runs_restored"] == 0
        assert again["feedback_restored"] == 0
    finally:
        memory.close()
