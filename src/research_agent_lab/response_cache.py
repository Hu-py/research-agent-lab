"""Opt-in server-only exact LLM response replay, for failed cloud reruns.

A cache hit is ONLY an exact response replay, not a new scientific judgment.
No prompts or original titles are persisted. Cached JSON answers can themselves
contain team research ideas: the isolated Supabase privileged key is mandatory.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone

import httpx

from research_agent_lab.supabase_auth import headers, supabase_url

CACHE_SCHEMA = "v0.7.0"
_NAMESPACE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def _identity(model) -> str:
    """Pin provider, endpoint, output size, and the response contract version."""
    base = getattr(model, "underlying", model)
    model_name = getattr(base, "model", None)
    api_url = getattr(base, "url", None)
    output_limit = getattr(base, "max_output_tokens", None)
    if not isinstance(model_name, str) or not isinstance(api_url, str):
        raise ValueError("REPLAY_MODEL_IDENTITY_UNKNOWN: only explicit DeepSeek models may be cached")
    return f"{model_name}|{api_url}|max_tokens={output_limit}|{CACHE_SCHEMA}"


def request_key(*, namespace: str, model_identity: str, role: str,
                system: str, payload: dict) -> str:
    """Stable key binds the ENTIRE effective prompt and explicit experiment arm."""
    if not _NAMESPACE.fullmatch(namespace):
        raise ValueError("REPLAY_NAMESPACE_INVALID: use 1..64 ASCII letters/digits/_/-")
    canonical = json.dumps({
        "namespace": namespace, "model_identity": model_identity,
        "role": role, "system": system, "payload": payload,
    }, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SupabaseResponseCache:
    def __init__(self, *, scope: str, namespace: str,
                 ttl_days: int = 30, client: httpx.Client | None = None):
        if not isinstance(scope, str) or not 2 <= len(scope) <= 150:
            raise ValueError("REPLAY_SCOPE_INVALID")
        if not _NAMESPACE.fullmatch(namespace):
            raise ValueError("REPLAY_NAMESPACE_INVALID")
        if not 1 <= ttl_days <= 90:
            raise ValueError("REPLAY_TTL_INVALID")
        self.scope = scope
        self.namespace = namespace
        self.ttl_days = ttl_days
        self.client = client or httpx.Client(timeout=25, follow_redirects=False)
        self.owns_client = client is None

    def close(self):
        if self.owns_client:
            self.client.close()

    def preflight(self) -> None:
        self._request(
            "get", params={"select":"cache_key", "limit":"1"}
        )

    def _request(self, method: str, *, params: dict, content: dict | None = None):
        kwargs = {
            "headers": headers(prefer="resolution=merge-duplicates,return=minimal"
                               if method == "post" else None),
            "params": params,
        }
        if content is not None:
            kwargs["json"] = content
        try:
            result = getattr(self.client, method)(
                supabase_url() + "/rest/v1/lab_llm_replay_cache", **kwargs
            )
            result.raise_for_status()
            return result
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                "REPLAY_CACHE_HTTP_" + str(exc.response.status_code)
                + ": execute sql/006_llm_replay_cache.sql or check server key/RLS"
            ) from None
        except httpx.TransportError:
            raise RuntimeError("REPLAY_CACHE_TRANSPORT_FAILURE") from None

    def lookup(self, cache_key: str) -> dict | None:
        result = self._request("get", params={
            "select": "response,expires_at",
            "scope": "eq." + self.scope,
            "cache_key": "eq." + cache_key,
            "limit": "1"
        })
        rows = result.json()
        if not isinstance(rows, list) or len(rows) > 1:
            raise RuntimeError("REPLAY_CACHE_INVALID_SERVER_RESPONSE")
        if not rows:
            return None
        row = rows[0]
        expiry = row.get("expires_at")
        try:
            moment = datetime.fromisoformat(str(expiry).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            raise RuntimeError("REPLAY_CACHE_INVALID_EXPIRY") from None
        if moment.tzinfo is None:
            raise RuntimeError("REPLAY_CACHE_INVALID_EXPIRY")
        if moment <= datetime.now(timezone.utc):
            return None
        response = row.get("response")
        if not isinstance(response, dict):
            raise RuntimeError("REPLAY_CACHE_INVALID_JSON")
        return response

    def save(self, cache_key: str, model_identity: str, response: dict) -> None:
        if not isinstance(response, dict):
            raise ValueError("REPLAY_CACHE_RESPONSE_NOT_OBJECT")
        self._request("post",
            params={"on_conflict": "scope,cache_key"},
            content={
                "scope": self.scope,
                "cache_key": cache_key,
                "model_identity": model_identity[:280],
                "response": response,
                "expires_at": (
                    datetime.now(timezone.utc)
                    + timedelta(days=self.ttl_days)
                ).isoformat(),
            }
        )


class CachedModel:
    """Decorate an enabled tracing model; cache hits are not provider calls."""
    def __init__(self, underlying, store: SupabaseResponseCache):
        self.underlying = underlying
        self.store = store
        self.model_identity = _identity(underlying)
        self.last_cache_hit = False
        self.last_usage: dict = {}

    def complete(self, *, role: str, system: str, payload: dict) -> dict:
        key = request_key(
            namespace=self.store.namespace, model_identity=self.model_identity,
            role=role, system=system, payload=payload
        )
        cached = self.store.lookup(key)
        if cached is not None:
            self.last_cache_hit = True
            self.last_usage = {"input_tokens": 0, "output_tokens": 0}
            return cached
        self.last_cache_hit = False
        result = self.underlying.complete(role=role, system=system, payload=payload)
        # A successful model call is cached even if downstream schema validation
        # fails; later corrective prompts have different keys.
        self.last_usage = getattr(self.underlying, "last_usage", {})
        self.store.save(key, self.model_identity, result)
        return result

    def flush(self):
        if hasattr(self.underlying, "flush"):
            self.underlying.flush()


def configured_cache(*, default_scope: str = "research-team") -> SupabaseResponseCache | None:
    if os.getenv("LLM_REPLAY_CACHE_ENABLED", "false").strip().lower() != "true":
        return None
    store = SupabaseResponseCache(
        scope=os.getenv("LLM_REPLAY_SCOPE") or default_scope,
        namespace=os.getenv("LLM_REPLAY_NAMESPACE") or "controlled_v07",
    )
    store.preflight()
    return store
