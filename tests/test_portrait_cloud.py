"""Cloud input router test: no real key, DB query, or model call."""
import json
from pathlib import Path

from research_agent_lab.frontier import cloud_runner


def test_team_evidence_mode_is_private_and_nonpublishing(tmp_path, monkeypatch):
    evidence = {
        "bundle_id": "fictional-team",
        "source": "authorized_database_export",
        "sharing_approved": True,
        "achievements": [{"id": "output001", "title": "Fictional study of city form",
                          "year": 2025}],
        "datasets": [], "external_papers": []
    }
    for key in ("DEEPSEEK_API_KEY", "OPENALEX_API_KEY",
                "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.setenv(key, "test")
    monkeypatch.setenv("EVIDENCE_SOURCE", "team_evidence")
    monkeypatch.setenv("MAX_GENERATIONS_INPUT", "0")
    monkeypatch.setenv("MAX_PAPERS_INPUT", "4")
    monkeypatch.setenv("MAX_PAIRS_INPUT", "1")
    monkeypatch.setenv("SAVE_SUPABASE", "true")
    monkeypatch.setenv("TEAM_EVIDENCE_JSON", json.dumps(evidence))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cloud_runner, "validate_cloud_config", lambda persist: None)
    monkeypatch.setattr(cloud_runner, "check_profile_store", lambda: None)
    monkeypatch.setattr(cloud_runner, "check_frontier_supabase", lambda: None)
    def fake_portrait_cli(argv):
        assert "--persist" in argv
        assert "--evidence" in argv
        snapshot = {
            "snapshot_id": "fake-profile-version",
            "provenance": "approved_export",
            "research_line": {
                "id": "urban_form", "name": "Urban form",
                "problem": "How can space be measured?", "goals": "Falsifiable"
            },
            "papers": [], "datasets": [],
        }
        out = Path(argv[argv.index("--snapshot-out") + 1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(snapshot))
        return 0
    def fake_frontier_cli(argv):
        assert "--persist" in argv
        assert "--discover" in argv
        assert "--snapshot" in argv
        output = Path(argv[argv.index("--out") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({
            "run_id": "synthetic-id", "status": "needs_more_evidence",
            "generation_count": 0, "model_calls": 0,
        }))
        return 0
    monkeypatch.setattr(cloud_runner, "portrait_main", fake_portrait_cli)
    monkeypatch.setattr(cloud_runner, "frontier_main", fake_frontier_cli)
    assert cloud_runner.main() == 0
    assert not (tmp_path / "outputs/derived-team-snapshot-private.json").exists()
    assert not (tmp_path / "outputs/live-frontier-private.json").exists()
    assert not any(tmp_path.glob("team-evidence-*"))


def test_team_source_fails_before_model_if_no_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv("EVIDENCE_SOURCE", "team_evidence")
    monkeypatch.setenv("MAX_GENERATIONS_INPUT", "0")
    monkeypatch.setenv("MAX_PAPERS_INPUT", "4")
    monkeypatch.setenv("MAX_PAIRS_INPUT", "1")
    monkeypatch.setenv("SAVE_SUPABASE", "true")
    monkeypatch.delenv("TEAM_EVIDENCE_JSON", raising=False)
    monkeypatch.setattr(cloud_runner, "validate_cloud_config", lambda persist: None)
    assert cloud_runner.main() == 2
