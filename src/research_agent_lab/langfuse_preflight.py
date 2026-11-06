"""Read-only Langfuse key + region check before any paid research inference.

This checks authentication only; no traces, documents or model prompts are
uploaded and no DeepSeek calls are made.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit


def check_langfuse_connection(*, factory=None) -> None:
    public = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    secret = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    url = os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com").strip().rstrip("/")
    if not public.startswith("pk-lf-") or not secret.startswith("sk-lf-"):
        raise RuntimeError(
            "LANGFUSE_KEY_FORMAT: verify PUBLIC_KEY=pk-lf-... and "
            "SECRET_KEY=sk-lf-... in GitHub Actions Secrets"
        )
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in {
            "cloud.langfuse.com", "us.cloud.langfuse.com",
            "jp.cloud.langfuse.com", "hipaa.cloud.langfuse.com",
        } or parsed.path or parsed.query or parsed.fragment or parsed.port):
        raise RuntimeError(
            "LANGFUSE_REGION: LANGFUSE_BASE_URL must match the project region "
            "(EU, US, Japan, or HIPAA). Check repository Actions Variables."
        )
    if os.getenv("LANGFUSE_TRACING_ENABLED", "true").lower() == "false":
        raise RuntimeError("LANGFUSE_TRACING_DISABLED: enable tracing for research runs")
    if os.getenv("OTEL_SDK_DISABLED", "false").lower() == "true":
        raise RuntimeError("LANGFUSE_OTEL_DISABLED: OpenTelemetry SDK is disabled")
    try:
        if float(os.getenv("LANGFUSE_SAMPLE_RATE", "1")) <= 0:
            raise RuntimeError("LANGFUSE_ZERO_SAMPLE_RATE: no traces would be exported")
    except ValueError:
        raise RuntimeError("LANGFUSE_INVALID_SAMPLE_RATE") from None
    if factory is None:
        try:
            from langfuse import get_client
        except ImportError:
            raise RuntimeError(
                "LANGFUSE_SDK_MISSING: install research-agent-lab[observability]"
            ) from None
        # IMPORTANT: Use the SAME enabled singleton as TracedModel.
        # Constructing Langfuse(tracing_enabled=False) here poisoned the
        # LangfuseResourceManager singleton (keyed by public key), making all
        # subsequent observations silently no-op despite valid auth_check.
        factory = get_client
    try:
        client = factory()
        # SDK authentication endpoint returns True only for a valid pair
        # against the correct regional host.
        ok = client.auth_check()
    except Exception:
        raise RuntimeError(
            "LANGFUSE_AUTH_FAILED: keys or region incorrect, or server unreachable. "
            "Check LANGFUSE_BASE_URL and generate a matching project key pair."
        ) from None
    if not ok:
        raise RuntimeError(
            "LANGFUSE_AUTH_FAILED: verify keys and matching Langfuse region."
        )
    return client


def emit_synthetic_langfuse_trace(client=None) -> None:
    """Explicit test span only: no research data, no model/API inference.

    The UI may show the span after Langfuse finishes asynchronous ingestion.
    This verifies the actual exporter path, unlike auth_check alone.
    """
    if client is None:
        from langfuse import get_client
        client = get_client()
    with client.start_as_current_observation(
        name="research-agent-lab-trace-smoke",
        as_type="span",
        input={"synthetic": True, "purpose": "observability connectivity"},
    ) as span:
        span.update(output={"result": "synthetic-smoke", "llm_calls": 0})
    client.flush()
