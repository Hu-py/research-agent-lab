"""LLM supervisor with hard programmatic resource/verification guardrails."""
from __future__ import annotations

from research_agent_lab.model import BudgetedModel

SYSTEM = (
    "You are the scientific meta-controller. Decide the next action from "
    "evidence quality, tournament uncertainty, expected marginal improvement, "
    "prior failures, and remaining budget. Your decision is advisory: hard "
    "program guards enforce round limits and mandatory scientific verification. "
    "Return JSON only."
)


def choose_next(model: BudgetedModel, *,
                pool: list[dict], matches: list[dict], generation: int,
                max_generations: int, memory_hints: list[dict],
                min_elo_margin: float = 8.0,
                reserved_verification_calls: int = 1) -> dict:
    """Supervisor always asks the model unless bound forces a safe finish."""
    ranked = sorted(pool, key=lambda c: (-c["elo"], c["id"]))
    gap = ranked[0]["elo"] - ranked[1]["elo"] if len(ranked) > 1 else 0
    # Worst-case evolution: 4 calls, next tournament: 1 proximity + up to 6 judges;
    # next supervisor: 1. Keep at least 1 scientific validator call reserved.
    min_budget_for_next_generation = 4 + 1 + 6 + 1 + reserved_verification_calls
    remaining = model.max_calls - model.usage.calls
    if ((generation < max_generations and remaining < min_budget_for_next_generation)
            or (generation >= max_generations and remaining < 2)):
        return {"action": "verify", "reason": "Hard generation/call budget limit",
                "hard_guard": True, "elo_margin": round(gap, 2)}
    raw = model.complete(
        role="supervisor", system=SYSTEM,
        payload={
            "generation": generation,
            "max_generations": max_generations,
            "elo_margin": gap,
            "candidate_summary": [{
                "id": c["id"], "title": c["title"], "elo": c["elo"],
                "parent_ids": c["parent_ids"], "generation": c["generation"]
            } for c in ranked],
            "recent_matches": matches[-5:],
            "memory_hints": memory_hints[:6],
            "remaining_model_calls": remaining,
            "task": "Choose one action: evolve (revise/combine), expand "
                    "(generate a genuinely different idea), rollback "
                    "(archive latest generation and restore earlier candidates), "
                    "or verify (complete scientific review). "
                    "Choose rollback only if generation>0. "
                    "Return {action,reason,expected_gain:string}.",
        },
    )
    if raw.get("action") not in ("evolve", "expand", "rollback", "verify"):
        raise ValueError("Supervisor requested an unsupported action")
    if not isinstance(raw.get("reason"), str) or not raw["reason"].strip():
        raise ValueError("Supervisor failed to explain decision")
    action = raw["action"]
    if action == "rollback" and generation == 0:
        action = "verify"
    # Generation cap blocks all NEW children, not safe rollback.
    if generation >= max_generations and action in ("evolve", "expand"):
        action = "verify"
    # Poor differentiation alone does not imply evolution is useful: model
    # decides whether critique+revision has positive expected value.
    return {
        "action": action,
        "reason": raw["reason"][:600],
        "expected_gain": str(raw.get("expected_gain", ""))[:400],
        "hard_guard": False,
        "elo_margin": round(gap, 2),
    }
