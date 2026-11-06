"""Regression: preflight must not initialize a disabled SDK singleton."""
import sys
from types import SimpleNamespace

import pytest

from research_agent_lab.langfuse_preflight import (
    check_langfuse_connection, emit_synthetic_langfuse_trace,
)


class SyntheticObservation:
    def __init__(self, calls): self.calls = calls
    def __enter__(self): return self
    def __exit__(self, *args): self.calls.append(("end",))
    def update(self, **kwargs): self.calls.append(("update", kwargs))


class StubClient:
    def __init__(self):
        self.calls = []
    def auth_check(self):
        self.calls.append(("auth",))
        return True
    def start_as_current_observation(self, **kwargs):
        self.calls.append(("start", kwargs))
        return SyntheticObservation(self.calls)
    def get_trace_url(self):
        self.calls.append(("url",))
        return "https://us.cloud.langfuse.com/project/demo/traces/0123456789abcdef0123456789abcdef"
    def flush(self):
        self.calls.append(("flush",))


def _env(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-fake")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-fake")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
    for var in ("LANGFUSE_TRACING_ENABLED", "OTEL_SDK_DISABLED", "LANGFUSE_SAMPLE_RATE"):
        monkeypatch.delenv(var, raising=False)


def test_preflight_and_traces_use_same_enabled_get_client(monkeypatch):
    _env(monkeypatch)
    shared = StubClient()
    calls = []
    def singleton_get_client():
        calls.append("get_client")
        return shared
    # Fail loudly if someone reintroduces the old unsafe constructor path.
    monkeypatch.setitem(sys.modules, "langfuse", SimpleNamespace(
        get_client=singleton_get_client,
        Langfuse=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("Never instantiate Langfuse(tracing_enabled=False) in preflight")
        ),
    ))
    checked = check_langfuse_connection()
    assert checked is shared
    trace_url = emit_synthetic_langfuse_trace(checked)
    assert trace_url == "https://us.cloud.langfuse.com/project/demo/traces/0123456789abcdef0123456789abcdef"
    assert calls == ["get_client"]
    assert shared.calls[0] == ("auth",)
    assert shared.calls[1][0] == "start"
    assert shared.calls[1][1]["name"] == "research-agent-lab-trace-smoke"
    assert shared.calls[-1] == ("flush",)
    assert "synthetic" in str(shared.calls)
    assert "research" not in str(shared.calls[1][1].get("input", {})).lower()


@pytest.mark.parametrize("key,value,pattern", [
    ("LANGFUSE_TRACING_ENABLED", "false", "LANGFUSE_TRACING_DISABLED"),
    ("OTEL_SDK_DISABLED", "true", "LANGFUSE_OTEL_DISABLED"),
    ("LANGFUSE_SAMPLE_RATE", "0", "LANGFUSE_ZERO_SAMPLE_RATE"),
])
def test_noop_tracing_configuration_fails_before_model(monkeypatch,key,value,pattern):
    _env(monkeypatch)
    monkeypatch.setenv(key,value)
    with pytest.raises(RuntimeError, match=pattern):
        check_langfuse_connection(factory=lambda: StubClient())


def test_synthetic_trace_does_not_print_untrusted_url(monkeypatch):
    _env(monkeypatch)
    class BadStub(StubClient):
        def get_trace_url(self):
            return "https://attacker.example/collect?token=should-never-log"
    assert emit_synthetic_langfuse_trace(BadStub()) is None
