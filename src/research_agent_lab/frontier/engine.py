"""LangGraph supervisor-controlled end-to-end scientific opportunity laboratory.

Unlike an uncontrolled autonomous agent, all paths and I/O are constrained.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Callable, TypedDict
import os

from langgraph.graph import START, END, StateGraph

from research_agent_lab.contracts import Snapshot
from research_agent_lab.model import BudgetedModel
from .competition import create_seed_candidates, run_tournament, evolve_hypotheses, expand_hypothesis
from .knowledge import independent_screen, discover_for_line
from .memory import MemoryStore
from .science import validate_scientifically, run_csv_pilot
from .synthetic_pilot import run_synthetic_network_pilot, can_run_network_pilot
from .supervisor import choose_next
from .feasibility_gate import screen_pool, minimal_viable_plan


@dataclass(frozen=True)
class FrontierConfig:
    max_generations: int = 1
    max_papers: int = 12
    max_pairs_per_tournament: int = 3
    discover: bool = False
    minimum_generations: int = 0
    synthetic_pilot: bool = False
    feasibility_first: bool = False
    max_feasibility_revisions: int = 2

    def __post_init__(self):
        if not 0 <= self.max_generations <= 3:
            raise ValueError("max_generations must be between 0 and 3")
        if not 0 <= self.minimum_generations <= self.max_generations:
            raise ValueError("minimum_generations must be between 0 and maximum_generations")
        if not 1 <= self.max_papers <= 40:
            raise ValueError("max_papers must be between 1 and 40")
        if not 1 <= self.max_pairs_per_tournament <= 6:
            raise ValueError("max_pairs_per_tournament must be between 1 and 6")
        if not 0 <= self.max_feasibility_revisions <= 3:
            raise ValueError("max_feasibility_revisions must be between 0 and 3")


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
    feasibility: dict
    feasibility_revisions: int


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
        rejected: list[dict] = []
        pool = create_seed_candidates(
            snapshot, model, state["strategy"], state["memory_hints"],
            rejections=rejected,
            min_candidates=0 if config.feasibility_first else 2
        )
        return {
            "candidates": pool,
            "events": state["events"] + [{
                "stage": "generate", "created": [c["id"] for c in pool],
                "rejected_count": len(rejected),
                "rejected_candidates": rejected,
                "strategy": state["strategy"]
            }],
        }


    def feasibility_node(state: FrontierState) -> dict:
        """Provisional, deterministic field-level check, never an LLM score."""
        snapshot = Snapshot.model_validate(state["snapshot"])
        pool, report = screen_pool(state["candidates"], snapshot)
        return {
            "candidates": pool,
            "feasibility": report,
            "events": state["events"] + [{
                "stage": "feasibility_gate",
                "eligible_count": report["eligible_count"],
                "blocked_count": report["blocked_count"],
                "revision_attempt": state["feasibility_revisions"],
                "reason_counts": report["reason_counts"],
            }],
        }

    def feasibility_route(state: FrontierState) -> str:
        eligible = state["feasibility"]["eligible_count"]
        if eligible >= 2:
            return "tournament"
        if eligible == 1:
            return "verify"
        snapshot = Snapshot.model_validate(state["snapshot"])
        can_revise_with_real_data = any(
            d.access_verified and d.fields for d in snapshot.datasets
        )
        remaining = model.max_calls - model.usage.calls
        if (can_revise_with_real_data
                and state["feasibility_revisions"] < config.max_feasibility_revisions
                and remaining >= 5):
            return "feasibility_revise"
        return "no_viable_study"

    def feasibility_revise_node(state: FrontierState) -> dict:
        """Use *specific blocked reasons* to revise the minimal empirical scope.

        Does not re-evaluate blocked proposals through Elo. A bounded repair
        creates a new immutable descendant, preserving the failed parent.
        """
        snapshot = Snapshot.model_validate(state["snapshot"])
        blocked = sorted(
            (c for c in state["candidates"] if c["status"] == "blocked"),
            key=lambda c: (len(c.get("feasibility", {}).get("reason_codes", [])), c["id"])
        )
        source = blocked[0] if blocked else None
        children = []
        rejection_code = None
        if source is not None:
            from .competition import make_candidate
            verified_assets = [
                {"id": d.id, "fields": d.fields, "description": d.description[:200]}
                for d in snapshot.datasets if d.access_verified and d.fields
            ]
            try:
                raw = model.complete(
                    role="frontier_feasibility_reviser",
                    system=(
                        "You are an evidence-first research methods engineer. "
                        "Revise this failed proposal into a smaller, genuinely "
                        "executable empirical study using ONLY supplied independently "
                        "verified dataset IDs and exact registered column names. "
                        "Never assert data ownership, an experiment result, novelty, "
                        "or schema fields that have not been registered. "
                        "Do not merely rewrite the title. JSON only."
                    ),
                    payload={
                        "previous_candidate": source,
                        "blocking_reason_codes": source["feasibility"]["reason_codes"],
                        "verified_assets": verified_assets,
                        "registered_paper_ids": [p.id for p in snapshot.papers],
                        "task": (
                            "Return a COMPLETE candidate with title, question, mechanism, "
                            "falsifiable_prediction, method, minimal_experiment, "
                            "baselines, paper_ids, dataset_ids, limitations, and "
                            "execution_plan: {study_type:'empirical',unit_of_analysis,"
                            "outcome_field,baseline_method,evaluation_metric,"
                            "split_strategy,steps:[...],"
                            "dataset_field_map:[{dataset_id,fields:[...]}]}. "
                            "Produce the smallest testable comparison with a trivial baseline "
                            "and explicit group split. If impossible, state missing inputs "
                            "and do not invent any registered facts."
                        ),
                    },
                )
                idx = max([int(c["id"][1:]) for c in state["candidates"]] or [0]) + 1
                new_child = make_candidate(
                    raw, snapshot, identifier=f"H{idx:03d}",
                    origin="feasibility_repair",
                    parent_ids=[source["id"]],
                    generation=source["generation"] + 1,
                    model=None
                )
                children.append(new_child)
            except (ValueError, TypeError, KeyError):
                rejection_code = "FEASIBILITY_REPAIR_SCHEMA_INVALID"
        return {
            "candidates": state["candidates"] + children,
            "feasibility_revisions": state["feasibility_revisions"] + 1,
            "events": state["events"] + [{
                "stage": "feasibility_revision",
                "revision_attempt": state["feasibility_revisions"] + 1,
                "children": [{"id": c["id"], "parent_ids": c["parent_ids"]}
                             for c in children],
                "blocked_reason_codes": (
                    source.get("feasibility", {}).get("reason_codes", []) if source else []
                ),
                "rejection_code": rejection_code,
            }],
        }

    def no_viable_node(state: FrontierState) -> dict:
        snapshot = Snapshot.model_validate(state["snapshot"])
        blocked = [c for c in state["candidates"] if c.get("status") == "blocked"]
        plan = minimal_viable_plan(snapshot, blocked)
        pilot = {}
        if config.synthetic_pilot and can_run_network_pilot(snapshot.research_line.id):
            pilot = run_synthetic_network_pilot()
            plan["method_only_synthetic_pilot_executed"] = True
            plan["method_pilot_warning"] = (
                "Toy software sanity checks are not empirical validation or evidence "
                "of novelty, network realism, or access to observed datasets."
            )
        final = {
            "status": "no_executable_candidates",
            "winner": None,
            "ranked_candidates": [],
            "archived_candidates": state["candidates"],
            "lineage": [{
                "id": c["id"], "parent_ids": c["parent_ids"],
                "generation": c["generation"], "origin": c["origin"],
                "status": c["status"]
            } for c in state["candidates"]],
            "matches": state["matches"],
            "supervisor_decisions": state["decisions"],
            "verification": {
                "data_feasible_assessment": False,
                "dataset_access_evidence_verified": False,
                "evidence_limitations": plan["blocked_reason_codes"],
                "novelty_verified": False,
                "experimental_claim_verified": False,
            },
            "pilot": pilot,
            "knowledge": state["query_diagnostics"],
            "screening": state["screening"],
            "feasibility": state["feasibility"],
            "minimum_viable_plan": plan,
            "event_log": state["events"] + [{
                "stage": "no_recommendation",
                "eligible_count": 0,
                "blocked_count": len(blocked),
                "reason_counts": state["feasibility"].get("reason_counts", {}),
                "plan_mode": plan["mode"],
            }],
            "generation_count": state["generation"],
            "human_review_required": True,
            "novelty_verified": False,
            "selection_is_llm_assessed_only": True,
            "automatic_human_push": False,
        }
        return {"final": final, "pilot": pilot, "events": final["event_log"]}

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
        rejected: list[dict] = []
        children = evolve_hypotheses(
            [c for c in state["candidates"] if c["status"] == "candidate"],
            snapshot, model,
            strategy=state["strategy"], memory_hints=state["memory_hints"],
            generation=state["generation"] + 1,
            rejections=rejected
        )
        # Keep ALL earlier candidates, so a failed revision cannot erase the champion.
        # If every proposal is malformed, verify the prior champion rather than
        # entering a fake extra evolution round.
        return {
            "candidates": state["candidates"] + children,
            "generation": state["generation"] + (1 if children else 0),
            "events": state["events"] + [{
                "stage": "hypothesis_evolution",
                "children": [{"id": c["id"], "parent_ids": c["parent_ids"]}
                             for c in children],
                "rejected_count": len(rejected),
                "rejected_candidates": rejected,
                "no_valid_children": not bool(children),
            }],
        }

    def expand_node(state: FrontierState) -> dict:
        snapshot = Snapshot.model_validate(state["snapshot"])
        try:
            child = expand_hypothesis(
                state["candidates"], snapshot, model,
                strategy=state["strategy"], memory_hints=state["memory_hints"],
                generation=state["generation"] + 1
            )
        except ValueError:
            # A single unusable boundary idea should not destroy a run.
            return {
                "events": state["events"] + [{
                    "stage": "hypothesis_expansion",
                    "no_valid_children": True,
                    "rejected_count": 1
                }]
            }
        return {
            "candidates": state["candidates"] + [child],
            "generation": state["generation"] + 1,
            "events": state["events"] + [{
                "stage": "hypothesis_expansion", "created": child["id"],
                "rejected_count": 0
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
                "feasibility": state["feasibility"] if config.feasibility_first else {},
                "minimum_viable_plan": None,
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
    graph.add_node("feasibility", feasibility_node)
    graph.add_node("feasibility_revise", feasibility_revise_node)
    graph.add_node("no_viable_study", no_viable_node)
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
    if config.feasibility_first:
        graph.add_edge("generate", "feasibility")
        graph.add_conditional_edges(
            "feasibility", feasibility_route,
            {"tournament": "tournament", "verify": "verify",
             "feasibility_revise": "feasibility_revise",
             "no_viable_study": "no_viable_study"},
        )
        graph.add_edge("feasibility_revise", "feasibility")
        graph.add_edge("no_viable_study", END)
    else:
        graph.add_edge("generate", "tournament")
    graph.add_edge("tournament", "supervisor")
    graph.add_conditional_edges("supervisor",
                                lambda state: state["decisions"][-1]["action"],
                                {"evolve": "evolve", "expand": "expand",
                                 "rollback": "rollback", "verify": "verify"})
    # Only legitimate, validated children may trigger another tournament.
    post_revision_routes = {"verify": "verify", "tournament": "tournament"}
    if config.feasibility_first:
        post_revision_routes["feasibility"] = "feasibility"
    graph.add_conditional_edges(
        "evolve",
        lambda state: ("verify" if state["events"][-1].get("no_valid_children")
                       else "feasibility" if config.feasibility_first else "tournament"),
        post_revision_routes
    )
    graph.add_conditional_edges(
        "expand",
        lambda state: ("verify" if state["events"][-1].get("no_valid_children")
                       else "feasibility" if config.feasibility_first else "tournament"),
        post_revision_routes
    )
    graph.add_edge("rollback", "verify")
    graph.add_edge("verify", "finish")
    graph.add_edge("finish", END)
    return graph.compile()


def run_frontier(snapshot: Snapshot, model: BudgetedModel, memory: MemoryStore,
                 config: FrontierConfig | None = None, *,
                 source_allowlist: set[str] | None = None,
                 search_fn: Callable | None = None,
                 pilot_manifest: dict | None = None,
                 event_sink: Callable[[dict], None] | None = None,
                 run_id: str | None = None) -> dict:
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
        "verification": {}, "pilot": {}, "final": {},
        "feasibility": {}, "feasibility_revisions": 0
    }
    execution = build_frontier_graph(
        model, config, source_allowlist=source_allowlist,
        search_fn=search_fn, pilot_manifest=pilot_manifest
    )
    # No behavior change for legacy (non-streamed) calls. For opt-in live
    # telemetry, use LangGraph values streaming and emit real node completions.
    if event_sink is None:
        result = execution.invoke(initial, config={"recursion_limit": 60})
    else:
        result = initial
        reported = 0
        for state in execution.stream(
            initial, config={"recursion_limit": 60}, stream_mode="values"
        ):
            result = state
            event_rows = state.get("events") or []
            for event in event_rows[reported:]:
                event_sink(event)
            reported = len(event_rows)
    run_id = str(uuid.UUID(run_id)) if run_id is not None else str(uuid.uuid4())
    final = result["final"]
    memory.record_run(
        run_id, line_id, strategy,
        best_title=(final["winner"]["title"] if final["winner"] is not None
                    else "[NO_EXECUTABLE_EMPIRICAL_CANDIDATE]"),
        lessons=final["verification"].get("evidence_limitations", []),
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
        "comparison_context": {
            "model_name": ("mock" if model.underlying.__class__.__name__ == "FrontierMockModel"
                           else os.getenv("DEEPSEEK_MODEL", "deepseek-flash")),
            "initial_snapshot_id": snapshot.snapshot_id,
            "retained_paper_ids": sorted(
                p["id"] for p in result["snapshot"]["papers"]
            ),
            "dataset_ids": sorted(
                d["id"] for d in result["snapshot"]["datasets"]
            ),
            "requested_generations": config.max_generations,
            "minimum_generations": config.minimum_generations,
            "max_pairs": config.max_pairs_per_tournament,
            "max_papers": config.max_papers,
            "synthetic_pilot": config.synthetic_pilot,
            "live_discovery": config.discover,
            "evaluation_claim_verified": False,
            "feasibility_first": config.feasibility_first,
        },
        "model_calls": model.usage.calls,
        "reserved_tokens": model.usage.reserved_tokens,
        "actual_input_tokens": model.usage.input_tokens,
        "actual_output_tokens": model.usage.output_tokens,
        **final,
    }
