"""LangGraph supervisor-controlled end-to-end scientific opportunity laboratory.

Unlike an uncontrolled autonomous agent, all paths and I/O are constrained.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Callable, TypedDict

from langgraph.graph import START, END, StateGraph

from research_agent_lab.contracts import Snapshot
from research_agent_lab.model import BudgetedModel
from .competition import create_seed_candidates, run_tournament, evolve_hypotheses, expand_hypothesis
from .knowledge import independent_screen, discover_for_line
from .memory import MemoryStore
from .science import validate_scientifically, run_csv_pilot
from .synthetic_pilot import run_synthetic_network_pilot, can_run_network_pilot
from .supervisor import choose_next


@dataclass(frozen=True)
class FrontierConfig:
    max_generations: int = 1
    max_papers: int = 12
    max_pairs_per_tournament: int = 3
    discover: bool = False
    minimum_generations: int = 0
    synthetic_pilot: bool = False

    def __post_init__(self):
        if not 0 <= self.max_generations <= 3:
            raise ValueError("max_generations must be between 0 and 3")
        if not 0 <= self.minimum_generations <= self.max_generations:
            raise ValueError("minimum_generations must be between 0 and maximum_generations")
        if not 1 <= self.max_papers <= 40:
            raise ValueError("max_papers must be between 1 and 40")
        if not 1 <= self.max_pairs_per_tournament <= 6:
            raise ValueError("max_pairs_per_tournament must be between 1 and 6")


class FrontierState(TypedDict):
    snapshot: dict
    query_diagnostics: dict
    screening: dict
    candidates: list[dict]
    matches: list[dict]
    generation: int
    strategy: str
    memory_hints: list[dict]
    decisions: list[dict]
    events: list[dict]
    verification: dict
    pilot: dict
    final: dict


def build_frontier_graph(model: BudgetedModel, config: FrontierConfig, *,
                         source_allowlist: set[str] | None = None,
                         search_fn: Callable | None = None,
                         pilot_manifest: dict | None = None):
    def discover_node(state: FrontierState) -> dict:
        snapshot = Snapshot.model_validate(state["snapshot"])
        kwargs = {"max_results": config.max_papers,
                  "source_allowlist": source_allowlist}
        if search_fn is not None:
            kwargs["search_fn"] = search_fn
        found, summary = discover_for_line(snapshot, model, **kwargs)
        return {
            "snapshot": found.model_dump(mode="json"),
            "query_diagnostics": summary,
            "events": state["events"] + [{"stage": "knowledge_discovery",
                                           "retrieved": summary["retrieved"]}],
        }

    def screen_node(state: FrontierState) -> dict:
        snapshot = Snapshot.model_validate(state["snapshot"])
        screened, summary = independent_screen(
            snapshot, model, max_papers=config.max_papers
        )
        return {
            "snapshot": screened.model_dump(mode="json"),
            "screening": summary,
            "events": state["events"] + [{
                "stage": "independent_paper_screen",
                "retained": summary["retained_count"],
                "disagreements": summary["disagreements"]
            }],
        }

    def generate_node(state: FrontierState) -> dict:
        snapshot = Snapshot.model_validate(state["snapshot"])
        pool = create_seed_candidates(
            snapshot, model, state["strategy"], state["memory_hints"]
        )
        return {
            "candidates": pool,
            "events": state["events"] + [{
                "stage": "generate", "created": [c["id"] for c in pool],
                "strategy": state["strategy"]
            }],
        }

    def tournament_node(state: FrontierState) -> dict:
        ranked, matches = run_tournament(
            [c for c in state["candidates"] if c["status"] == "candidate"],
            model, max_pairs=config.max_pairs_per_tournament
        )
        return {
            "candidates": ranked + [c for c in state["candidates"] if c["status"] != "candidate"],
            "matches": state["matches"] + matches,
            "events": state["events"] + [{
                "stage": "elo_tournament", "generation": state["generation"],
                "matches": len(matches),
                "leader": ranked[0]["id"],
                "leader_rating": ranked[0]["elo"]
            }],
        }

    def supervisor_node(state: FrontierState) -> dict:
        decision = choose_next(
            model, pool=[c for c in state["candidates"] if c["status"] == "candidate"],
            matches=state["matches"],
            generation=state["generation"], max_generations=config.max_generations,
            memory_hints=state["memory_hints"],
            reserved_verification_calls=1,
            minimum_generations=config.minimum_generations,
        )
        return {
            "decisions": state["decisions"] + [decision],
            "events": state["events"] + [{
                "stage": "supervisor", "generation": state["generation"],
                "decision": decision["action"],
                "reason": decision["reason"]
            }],
        }

    def evolve_node(state: FrontierState) -> dict:
        snapshot = Snapshot.model_validate(state["snapshot"])
        children = evolve_hypotheses(
            [c for c in state["candidates"] if c["status"] == "candidate"],
            snapshot, model,
            strategy=state["strategy"], memory_hints=state["memory_hints"],
            generation=state["generation"] + 1
        )
        # Keep ALL earlier candidates, so a failed revision cannot erase the champion.
        return {
            "candidates": state["candidates"] + children,
            "generation": state["generation"] + 1,
            "events": state["events"] + [{
                "stage": "hypothesis_evolution",
                "children": [{"id": c["id"], "parent_ids": c["parent_ids"]}
                             for c in children],
            }],
        }

    def expand_node(state: FrontierState) -> dict:
        snapshot = Snapshot.model_validate(state["snapshot"])
        child = expand_hypothesis(
            state["candidates"], snapshot, model,
            strategy=state["strategy"], memory_hints=state["memory_hints"],
            generation=state["generation"] + 1
        )
        return {
            "candidates": state["candidates"] + [child],
            "generation": state["generation"] + 1,
            "events": state["events"] + [{
                "stage": "hypothesis_expansion", "created": child["id"],
            }],
        }

    def rollback_node(state: FrontierState) -> dict:
        # Preserve history, but archive the most recent generation to prevent
        # a weak revised idea from displacing an earlier strong hypothesis.
        pool = [dict(c, status=("archived" if c["generation"] == state["generation"]
                                  and c["generation"] > 0 else c["status"]))
                for c in state["candidates"]]
        if not any(c["status"] == "candidate" for c in pool):
            raise ValueError("Cannot rollback every candidate")
        return {
            "candidates": pool,
            "events": state["events"] + [{
                "stage": "rollback", "archived_generation": state["generation"],
            }],
        }

    def verify_node(state: FrontierState) -> dict:
        winner = sorted([c for c in state["candidates"] if c["status"] == "candidate"],
                        key=lambda x: (-x["elo"], x["id"]))[0]
        snapshot = Snapshot.model_validate(state["snapshot"])
        validation = validate_scientifically(snapshot, winner, model)
        pilot = {}
        if pilot_manifest is not None:
            if pilot_manifest.get("dataset_id") not in winner["dataset_ids"]:
                raise ValueError("Pilot CSV dataset is not referenced by winning hypothesis")
            pilot = run_csv_pilot(snapshot, pilot_manifest)
        elif config.synthetic_pilot:
            if can_run_network_pilot(snapshot.research_line.id):
                pilot = run_synthetic_network_pilot()
            else:
                pilot = {
                    "status": "skipped_not_applicable",
                    "recipe": "toy_network_resilience_v1",
                    "reason": "Fixed-code synthetic pilot only supports network-resilience lines",
                    "experimental_claim_verified": False,
                }
        pilot_executed = pilot.get("status", "").startswith("executed_")
        return {
            "verification": validation,
            "pilot": pilot,
            "events": state["events"] + [{
                "stage": "scientific_gate",
                "winner": winner["id"],
                "data_feasible_assessment": validation["data_feasible_assessment"],
                "pilot_executed": pilot_executed,
            }],
        }

    def finish_node(state: FrontierState) -> dict:
        ranked = sorted([c for c in state["candidates"] if c["status"] == "candidate"],
                        key=lambda x: (-x["elo"], x["id"]))
        archived = [c for c in state["candidates"] if c["status"] != "candidate"]
        eligible = bool(state["verification"]["data_feasible_assessment"]
                        and state["screening"]["retained_count"])
        return {
            "final": {
                "status": "candidate_for_human_review" if eligible else "needs_more_evidence",
                "winner": ranked[0],
                "ranked_candidates": ranked,
                "archived_candidates": archived,
                "lineage": [{
                    "id": c["id"], "parent_ids": c["parent_ids"],
                    "generation": c["generation"], "origin": c["origin"],
                    "status": c["status"]
                } for c in sorted(state["candidates"], key=lambda r: r["id"])],
                "matches": state["matches"],
                "supervisor_decisions": state["decisions"],
                "verification": state["verification"],
                "pilot": state["pilot"],
                "knowledge": state["query_diagnostics"],
                "screening": state["screening"],
                "event_log": state["events"],
                "generation_count": state["generation"],
                "human_review_required": True,
                "novelty_verified": False,
                "selection_is_llm_assessed_only": True,
                "automatic_human_push": False,
            },
        }

    graph = StateGraph(FrontierState)
    graph.add_node("discover", discover_node)
    graph.add_node("screen", screen_node)
    graph.add_node("generate", generate_node)
    graph.add_node("tournament", tournament_node)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("evolve", evolve_node)
    graph.add_node("expand", expand_node)
    graph.add_node("rollback", rollback_node)
    graph.add_node("verify", verify_node)
    graph.add_node("finish", finish_node)
    graph.add_conditional_edges(
        START, lambda _: "discover" if config.discover else "screen",
        {"discover": "discover", "screen": "screen"}
    )
    graph.add_edge("discover", "screen")
    graph.add_edge("screen", "generate")
    graph.add_edge("generate", "tournament")
    graph.add_edge("tournament", "supervisor")
    graph.add_conditional_edges("supervisor",
                                lambda state: state["decisions"][-1]["action"],
                                {"evolve": "evolve", "expand": "expand",
                                 "rollback": "rollback", "verify": "verify"})
    graph.add_edge("evolve", "tournament")
    graph.add_edge("expand", "tournament")
    graph.add_edge("rollback", "verify")
    graph.add_edge("verify", "finish")
    graph.add_edge("finish", END)
    return graph.compile()


def run_frontier(snapshot: Snapshot, model: BudgetedModel, memory: MemoryStore,
                 config: FrontierConfig | None = None, *,
                 source_allowlist: set[str] | None = None,
                 search_fn: Callable | None = None,
                 pilot_manifest: dict | None = None) -> dict:
    config = config or FrontierConfig()
    if not config.discover and len(snapshot.papers) < 1:
        raise ValueError("At least one paper is required without live discovery")
    if len(snapshot.papers) > config.max_papers and not config.discover:
        raise ValueError("Snapshot exceeds max_papers; freeze a smaller controlled comparison")
    # Reserve calls for each requested mandatory generation (2 evolution
    # critiques, 2 child proposals, proximity + reversed duels, gate).
    minimum_calls = (2 + 3 + 1 + 2 * min(3, config.max_pairs_per_tournament) + 1
                     + config.minimum_generations * (
                         4 + 1 + 2 * config.max_pairs_per_tournament
                     ))
    if model.max_calls < minimum_calls:
        raise ValueError(f"At least {minimum_calls} model calls required for the initial experiment")
    line_id = snapshot.research_line.id
    strategy = memory.select_strategy(line_id)
    hints = memory.recall(line_id)
    initial: FrontierState = {
        "snapshot": snapshot.model_dump(mode="json"),
        "query_diagnostics": {}, "screening": {}, "candidates": [],
        "matches": [], "generation": 0, "strategy": strategy,
        "memory_hints": hints, "decisions": [], "events": [],
        "verification": {}, "pilot": {}, "final": {}
    }
    result = build_frontier_graph(
        model, config, source_allowlist=source_allowlist,
        search_fn=search_fn, pilot_manifest=pilot_manifest
    ).invoke(initial, config={"recursion_limit": 60})
    run_id = str(uuid.uuid4())
    final = result["final"]
    memory.record_run(
        run_id, line_id, strategy, best_title=final["winner"]["title"],
        lessons=final["verification"]["evidence_limitations"],
        status="eligible" if final["status"] == "candidate_for_human_review" else "failure",
        experiment_summary=(json.dumps(final["pilot"], ensure_ascii=False)
                            if final["pilot"] else ""),
    )
    return {
        "run_id": run_id,
        "experiment_mode": "frontier",
        "source_snapshot_id": snapshot.snapshot_id,
        "final_evidence_provenance": result["snapshot"]["provenance"],
        "line_id": line_id,
        "chosen_strategy": strategy,
        "memory_hints_used": len(hints),
        "model_calls": model.usage.calls,
        "reserved_tokens": model.usage.reserved_tokens,
        "actual_input_tokens": model.usage.input_tokens,
        "actual_output_tokens": model.usage.output_tokens,
        **final,
    }
