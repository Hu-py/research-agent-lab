"""Optional observability and isolated result persistence, disabled by default."""
from __future__ import annotations

import os
from contextlib import nullcontext
import httpx

from .supabase_auth import headers as supabase_headers, supabase_url


class TracedModel:
    """Log per-Agent execution while keeping source documents out of traces by default."""
    def __init__(self, underlying):
        self.underlying = underlying
        self.client = None
        if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
            try:
                from langfuse import get_client
            except ImportError as exc:
                raise RuntimeError("pip install 'research-agent-lab[observability]'") from exc
            self.client = get_client()

    @property
    def last_usage(self) -> dict:
        return getattr(self.underlying, "last_usage", {})

    def complete(self, *, role: str, system: str, payload: dict) -> dict:
        # Do not upload sensitive paper abstracts or dataset descriptions by default.
        inp = {
            "snapshot_id": payload.get("snapshot", {}).get("snapshot_id"),
            "role": role,
            "round": payload.get("rounds_completed"),
        }
        ctx = (self.client.start_as_current_observation(
            name=role, as_type="generation", input=inp
        ) if self.client is not None else nullcontext())
        with ctx as span:
            result = self.underlying.complete(role=role, system=system, payload=payload)
            if span is not None:
                span.update(output={"response_keys": sorted(result.keys())})
        return result

    def flush(self):
        if self.client is not None:
            self.client.flush()

    def close(self):
        self.flush()
        if hasattr(self.underlying, "close"):
            self.underlying.close()


def persist_run_to_supabase(run: dict) -> None:
    """Save legacy baselines to the lab_runs table (not frontier table)."""
    payload = {
        "snapshot_id": run["snapshot_id"],
        "mode": run["experiment_mode"],
        "model_calls": run["model_calls"],
        "reserved_tokens": run["reserved_tokens"],
        "result": run,
    }
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        try:
            response = client.post(
                supabase_url() + "/rest/v1/lab_runs",
                headers=supabase_headers(prefer="return=minimal"),
                json=payload,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Supabase lab_runs HTTP {exc.response.status_code}"
            ) from None
        except httpx.TransportError:
            raise RuntimeError("Supabase baseline write transport error") from None
