"""One bounded, JSON-only model boundary; provider secrets never enter results."""
from __future__ import annotations

import os
import json
from dataclasses import dataclass
from typing import Any, Protocol
import httpx


class Model(Protocol):
    def complete(self, *, role: str, system: str, payload: dict) -> dict: ...


@dataclass
class Usage:
    calls: int = 0
    reserved_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class BudgetExceeded(RuntimeError):
    pass


class BudgetedModel:
    """Conservative reservation, not provider-accurate USD billing."""
    def __init__(self, underlying: Model, max_calls: int = 30,
                 max_reserved_tokens: int = 350000, tokens_per_call: int = 6500):
        self.underlying = underlying
        self.max_calls = max_calls
        self.max_reserved_tokens = max_reserved_tokens
        self.tokens_per_call = tokens_per_call
        self.usage = Usage()

    def complete(self, *, role: str, system: str, payload: dict) -> dict:
        if self.usage.calls + 1 > self.max_calls:
            raise BudgetExceeded("Model-call ceiling exceeded")
        if self.usage.reserved_tokens + self.tokens_per_call > self.max_reserved_tokens:
            raise BudgetExceeded("Reserved-token ceiling exceeded")
        self.usage.calls += 1
        self.usage.reserved_tokens += self.tokens_per_call
        result = self.underlying.complete(role=role, system=system, payload=payload)
        usage = getattr(self.underlying, "last_usage", {})
        self.usage.input_tokens += max(0, int(usage.get("input_tokens", 0)))
        self.usage.output_tokens += max(0, int(usage.get("output_tokens", 0)))
        return result


class DeepSeekJSONModel:
    """Uses current DeepSeek chat-completions API, JSON mode and non-thinking output."""
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 api_url: str | None = None, timeout: float = 90.0,
                 max_output_tokens: int = 2200):
        self.key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        if not self.key:
            raise ValueError("DEEPSEEK_API_KEY missing; use --mock for an offline smoke test")
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
        if self.model not in ("deepseek-flash", "deepseek-v4-pro"):
            raise ValueError("Allowed models: deepseek-flash / deepseek-v4-pro")
        self.url = api_url or os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")
        if not self.url.startswith("https://"):
            raise ValueError("API URL must use HTTPS")
        if not 500 <= max_output_tokens <= 8192:
            raise ValueError("max_output_tokens must be between 500 and 8192")
        self.max_output_tokens = max_output_tokens
        self.http = httpx.Client(timeout=timeout, follow_redirects=False)
        self.last_usage: dict = {}

    def complete(self, *, role: str, system: str, payload: dict) -> dict:
        prompt = json.dumps(payload, ensure_ascii=False)
        try:
            response = self.http.post(
                self.url,
                headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [{"role": "system", "content": system + "\nReturn only a valid JSON object."},
                                 {"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "thinking": {"type": "disabled"},
                    "max_tokens": self.max_output_tokens,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("choices"):
                raise RuntimeError("Model returned no choices")
            choice = data["choices"][0]
            if choice.get("finish_reason") == "length":
                raise RuntimeError("Model response truncated")
            content = (choice.get("message") or {}).get("content")
            output = json.loads(content or "")
            if not isinstance(output, dict):
                raise RuntimeError("Model must return JSON object")
            usage = data.get("usage") or {}
            self.last_usage = {
                "input_tokens": int(usage.get("prompt_tokens") or 0),
                "output_tokens": int(usage.get("completion_tokens") or 0),
            }
            return output
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise RuntimeError("DeepSeek transport error: " + type(exc).__name__) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError("DeepSeek HTTP " + str(exc.response.status_code)) from exc
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            raise RuntimeError("DeepSeek response was not valid JSON") from exc

    def close(self):
        self.http.close()


class MockJSONModel:
    """Deterministic structural demo ONLY. Never present its judgments as research."""
    last_usage: dict = {"input_tokens": 0, "output_tokens": 0}

    def complete(self, *, role: str, system: str, payload: dict) -> dict:
        snapshot = payload["snapshot"]
        paper_ids = [p["id"] for p in snapshot["papers"]]
        dataset_ids = [d["id"] for d in snapshot["datasets"]]
        if role.startswith("seed:") or role.startswith("revise:"):
            lens = role.split(":", 1)[1]
            candidate = (payload.get("candidate") or {})
            return {
                "title": candidate.get("title", "SYNTHETIC DEMO: " + lens + " urban research"),
                "question": candidate.get("question", "Can spatial context predict a falsifiable urban outcome?"),
                "mechanism": candidate.get("mechanism", "Hypothesized measurable spatial interaction."),
                "falsifiable_prediction": "Ablation should alter held-out predictions.",
                "method": "Spatial model with explicit baselines and ablations.",
                "minimal_experiment": "Compare two configurations on held-out spatial groups.",
                "baselines": ["non-spatial regression", "spatial ablation"],
                "paper_ids": paper_ids[:2],
                "dataset_ids": dataset_ids[:1],
                "limitations": ["Synthetic example; not a validated scientific finding."],
            }
        if role == "critic":
            return {"challenges": [
                {"candidate_id": x["id"],
                 "objections": ["Potential data leakage; benchmark with spatial holdout."],
                 "counter_test": "Compare random and spatially blocked cross-validation."}
                for x in payload["candidates"]
            ]}
        if role == "reviewer":
            return {
                "ranked": [
                    {"candidate_id": x["id"],
                     "novelty": 67, "feasibility": 76, "testability": 82, "evidence": 64,
                     "concerns": ["Evidence metadata alone cannot verify novelty."]}
                    for x in payload["candidates"]
                ],
                "needs_revision": payload["rounds_completed"] == 0,
                "reason": "Deterministic mock scoring; no scientific evaluation performed.",
            }
        raise ValueError("Unknown model role: " + role)
