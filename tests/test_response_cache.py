"""Exact-request replay without external calls, credential exposure or remote data."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from research_agent_lab.response_cache import (
    CachedModel, SupabaseResponseCache, request_key, configured_cache
)
from research_agent_lab.model import BudgetedModel


class DummyDeepSeek:
    model = "deepseek-flash"
    url = "https://api.deepseek.com/chat/completions"
    max_output_tokens = 2200
    last_usage = {}
    def __init__(self): self.calls = 0
    def complete(self, *, role, system, payload):
        self.calls += 1
        self.last_usage = {"input_tokens": 12, "output_tokens": 21}
        return {"role": role, "answer": "synthetic", "call_index": self.calls}


class InMemoryStore:
    namespace = "baseline_A"
    def __init__(self): self.cache = {}
    def lookup(self, key): return self.cache.get(key)
    def save(self, key, model, response): self.cache[key] = response


def test_identical_prompt_replays_without_new_provider_charges():
    provider = DummyDeepSeek()
    store = InMemoryStore()
    first = CachedModel(provider, store)
    budget = BudgetedModel(first, max_calls=3)
    args = {"role":"hypothesis", "system":"synthetic", "payload":{"paper_ids":["p1"]}}
    response1 = budget.complete(**args)
    response2 = budget.complete(**args)
    assert response1 == response2
    assert provider.calls == 1
    assert budget.usage.calls == 2
    assert budget.usage.cache_hits == 1
    assert budget.usage.provider_calls == 1
    assert budget.usage.input_tokens == 12


def test_namespace_model_and_payload_are_part_of_cache_key():
    arguments={"model_identity":"deepseek-flash|test","role":"judge",
               "system":"synthetic","payload":{"x":1}}
    key=request_key(namespace="baseline_A",**arguments)
    assert key == request_key(namespace="baseline_A",**arguments)
    assert key != request_key(namespace="treatment_B",**arguments)
    assert key != request_key(namespace="baseline_A",**{**arguments,"payload":{"x":2}})
    assert key != request_key(namespace="baseline_A",**{**arguments,"model_identity":"other"})
    with pytest.raises(ValueError,match="NAMESPACE"):
        request_key(namespace="../oops",**arguments)


def test_supabase_cache_reads_and_writes_with_new_secret_key(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://demo.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY","sb_secret_dont_print")
    logged = []
    cache_key = "a"*64
    expires = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    def responder(request):
        logged.append(request)
        if request.method == "GET":
            return httpx.Response(200,json=[{"response":{"synthetic":1},"expires_at":expires}])
        return httpx.Response(201, text="")
    with httpx.Client(transport=httpx.MockTransport(responder)) as http:
        cache = SupabaseResponseCache(scope="research-team",namespace="A",client=http)
        assert cache.lookup(cache_key)=={"synthetic":1}
        cache.save(cache_key,"testmodel",{"synthetic":1})
    assert len(logged)==2
    assert logged[0].headers["apikey"]=="sb_secret_dont_print"
    assert "Authorization" not in logged[0].headers
    assert logged[1].url.params["on_conflict"]=="scope,cache_key"


def test_expired_record_cannot_be_reused(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL","https://demo.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY","sb_secret_dont_print")
    def expired(request):
        return httpx.Response(200,json=[{
            "response":{"old":1},
            "expires_at":(datetime.now(timezone.utc)-timedelta(days=2)).isoformat()
        }])
    with httpx.Client(transport=httpx.MockTransport(expired)) as client:
        store=SupabaseResponseCache(scope="research-team",namespace="A",client=client)
        assert store.lookup("a"*64) is None


def test_cache_opt_in_off_does_not_touch_supabase(monkeypatch):
    monkeypatch.delenv("LLM_REPLAY_CACHE_ENABLED",raising=False)
    assert configured_cache() is None
