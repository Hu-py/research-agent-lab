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
    if factory is None:
        try:
            from langfuse import Langfuse
        except ImportError:
            raise RuntimeError(
                "LANGFUSE_SDK_MISSING: install research-agent-lab[observability]"
            ) from None
        factory = lambda: Langfuse(
            public_key=public, secret_key=secret,
            base_url=url, tracing_enabled=False, timeout=10
        )
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
