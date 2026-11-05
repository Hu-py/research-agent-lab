import json
from pathlib import Path

from research_agent_lab.cli import main


def test_mock_all_modes_and_json_output(tmp_path, monkeypatch):
    for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "SUPABASE_URL",
                "SUPABASE_SERVICE_ROLE_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    source = Path(__file__).resolve().parents[1] / "examples" / "synthetic_snapshot.json"
    target = tmp_path / "results.json"
    status = main(["--snapshot", str(source), "--mode", "all",
                   "--mock", "--max-rounds", "2", "--out", str(target)])
    assert status == 0
    result = json.loads(target.read_text(encoding="utf-8"))
    assert result["mock"] is True
    assert [r["experiment_mode"] for r in result["runs"]] == ["single", "fixed", "adaptive"]
    assert all(r["human_review_required"] for r in result["runs"])
