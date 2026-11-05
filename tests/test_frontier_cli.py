import json
from pathlib import Path

from research_agent_lab.frontier.cli import main

SNAPSHOT = Path(__file__).resolve().parents[1] / "examples" / "synthetic_snapshot.json"


def test_mock_cli_and_human_feedback(tmp_path, monkeypatch):
    for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    out = tmp_path / "result.json"
    memory = tmp_path / "memory.sqlite"
    status = main(["run", "--snapshot", str(SNAPSHOT), "--mock",
                   "--max-generations", "1",
                   "--memory", str(memory), "--out", str(out)])
    assert status == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["mock"]
    assert report["run_id"]
    assert report["generation_count"] == 1
    assert main(["feedback", "--memory", str(memory), "--run-id", report["run_id"],
                 "--reviewer-tag", "test-reviewer", "--decision", "revise",
                 "--novelty", "60", "--feasibility", "75"]) == 0


def test_forbid_mock_with_live_discovery(tmp_path):
    assert main(["run", "--snapshot", str(SNAPSHOT), "--mock",
                 "--discover", "--memory", str(tmp_path / "m.sqlite")]) == 2
