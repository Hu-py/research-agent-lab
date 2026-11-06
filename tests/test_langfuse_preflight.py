"""No actual Langfuse or DeepSeek calls."""
import pytest
from research_agent_lab.langfuse_preflight import check_langfuse_connection


class Stub:
    def __init__(self, ok): self.ok = ok
    def auth_check(self): return self.ok


def test_valid_credentials_and_us_region(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
    check_langfuse_connection(factory=lambda: Stub(True))


def test_bad_key_detected_before_any_connection(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "sk-lf-swapped")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "pk-lf-swapped")
    with pytest.raises(RuntimeError, match="LANGFUSE_KEY_FORMAT"):
        check_langfuse_connection(factory=lambda: 1/0)


def test_bad_region_detected_before_any_connection(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://example.com/trace")
    with pytest.raises(RuntimeError, match="LANGFUSE_REGION"):
        check_langfuse_connection(factory=lambda: 1/0)


def test_invalid_project_pair_reports_safe_error(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-privatevalue")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
    with pytest.raises(RuntimeError, match="LANGFUSE_AUTH_FAILED") as e:
        check_langfuse_connection(factory=lambda: Stub(False))
    assert "sk-lf-privatevalue" not in str(e.value)
