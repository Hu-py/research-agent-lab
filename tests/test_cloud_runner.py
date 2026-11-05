import json

import pytest

from research_agent_lab.frontier.cloud_runner import (
    PUBLIC_PROFILE, choose_snapshot, validate_cloud_config,
)
from research_agent_lab.contracts import Snapshot


def test_public_source_is_generic():
    path, remove_after = choose_snapshot("public_demo")
    assert path == PUBLIC_PROFILE
    assert not remove_after
    snapshot = Snapshot.model_validate_json(path.read_text())
    assert snapshot.provenance == "public_demo_profile"
    assert not snapshot.papers
    assert not snapshot.datasets
    assert "GENERIC" in snapshot.research_line.goals


def test_private_snapshot_requires_approved_export(tmp_path):
    public, _ = choose_snapshot("public_demo")
    record = json.loads(public.read_text())
    with pytest.raises(ValueError, match="approved_export"):
        choose_snapshot("approved_secret", json.dumps(record), directory=tmp_path)
    record["provenance"] = "approved_export"
    path, ephemeral = choose_snapshot(
        "approved_secret", json.dumps(record), directory=tmp_path
    )
    assert ephemeral
    assert path.is_file()
    assert path.parent == tmp_path
    assert Snapshot.model_validate_json(path.read_text()).provenance == "approved_export"
    path.unlink()


def test_unknown_evidence_source_and_absent_secret(tmp_path):
    with pytest.raises(ValueError, match="Missing"):
        choose_snapshot("approved_secret", "", directory=tmp_path)
    with pytest.raises(ValueError, match="Unsupported"):
        choose_snapshot("arbitrary")


def test_required_secrets_preflight(monkeypatch):
    keys = ("DEEPSEEK_API_KEY", "OPENALEX_API_KEY",
            "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="GitHub Secrets missing"):
        validate_cloud_config(persist=False)
    for key in keys:
        monkeypatch.setenv(key, "test")
    validate_cloud_config(persist=False)


def test_modern_supabase_key_preflight(monkeypatch):
    for key in ("DEEPSEEK_API_KEY", "OPENALEX_API_KEY",
                "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.setenv(key, "test")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_dummy")
    validate_cloud_config(persist=True)
