"""Nested LangGraph: four *actual* local loops and a global Meta Supervisor.

Default driver: synthetic dry-run only. The orchestration cannot execute
arbitrary model-authored code, grant data rights or forge a scientific pass.
Model tools and trusted pilot execution must be separately approved adapters.
"""
from __future__ import annotations

from typing import Any, Callable

from langgraph.graph import START, END, StateGraph

from .driver import ResearchDriver, ScriptedResearchDriver
from .state import V2Limits, V2State, codes, event, initial_state
from .supervisor import choose_next

_REAL_EXECUTION = "executed"
_SYNTHETIC_EXECUTION = "simulated_executed"


def _operation(driver: ResearchDriver, limits: V2Limits, action: str,
               stage: str, target: str, *,
               merge: bool = False,
               append_candidates: bool = False) -> Callable[[V2State], dict]:
    def run(state: V2State) -> dict:
        current = state.get("operation_count", 0)
        if current >= limits.max_operations:
            return {
                "issue_codes": ["OPERATION_BUDGET_EXHAUSTED"],
                "stage_signal": "blocked",
                "events": event(state, phase=stage, action="budget_stop",
                                issue_codes=["OPERATION_BUDGET_EXHAUSTED"]),
            }
        try:
            result = driver.perform(action, state)
            if not isinstance(result, dict):
                raise ValueError("Driver must return an object")
            if len(result) > 30:
                raise ValueError("Driver response exceeds allowed stage schema")
        except Exception:
            # Never leak data, model traces or secrets through dashboard events.
            return {
                "operation_count": current + 1,
                "issue_codes": ["DRIVER_ERROR"],
                "stage_signal": "blocked",
                "events": event(state, phase=stage, action=action,
                                issue_codes=["DRIVER_ERROR"]),
            }

        changes: dict[str, Any] = {
            "operation_count": current + 1,
            "issue_codes": [],
            "stage_signal": "running",
            "stage": stage,
            "events": event(state, phase=stage, action=action),
        }
        if append_candidates:
            proposed = result.get("candidates", [])
            if not isinstance(proposed, list):
                proposed = []
            previous = state.get("hypotheses", [])
            existing = {c.get("id") for c in previous}
            new = []
            for c in proposed:
                if not isinstance(c, dict) or not isinstance(c.get("id"), str):
                    continue
                parents = c.get("parent_ids", [])
                if not isinstance(parents, list):
                    continue
                if c["id"] in existing or c["id"] in {x["id"] for x in new}:
                    continue
                if action != "generate" and (not parents or not set(parents) <= existing):
                    continue
                # A child version must change its scientific content, not only its ID.
                if action != "generate" and any(
                    c.get("question") == p.get("question") and
                    c.get("execution_plan") == p.get("execution_plan")
                    for p in previous if p.get("id") in parents
                ):
                    continue
                new.append(c)
            changes["hypotheses"] = previous + new
            changes["active_candidate_ids"] = [c["id"] for c in new]
            changes["candidate_change_count"] = len(new)
        elif merge:
            old = state.get(target, {})
            changes[target] = {**old, **result}
        else:
            changes[target] = result
        return changes
    return run


def _retry_update(state: V2State, key: str, action: str) -> dict:
    current = state.get("local_retries", {})
    new = {**current, key: current.get(key, 0) + 1}
    return {
        "local_retries": new,
        "events": event(state, phase=key, action=action,
                        attempt=new[key]),
    }


def _budget_blocked(state: V2State) -> bool:
    return bool(set(state.get("issue_codes", [])) & {
        "DRIVER_ERROR", "INVALID_DRIVER_RESULT", "OPERATION_BUDGET_EXHAUSTED"
    })


def build_evidence_loop(driver: ResearchDriver, limits: V2Limits):
    sub = StateGraph(V2State)
    sub.add_node("search", _operation(driver, limits, "search", "evidence", "literature"))
    sub.add_node("review", _operation(driver, limits, "review_papers", "evidence",
                                      "literature", merge=True))
    def diagnose(state: V2State) -> dict:
        literature = state.get("literature", {})
        papers = literature.get("papers", [])
        retained = literature.get("retained_ids", [])
        paper_ids = {p.get("id") for p in papers if isinstance(p, dict)}
        ok = (not _budget_blocked(state) and isinstance(retained, list)
              and bool(retained) and set(retained) <= paper_ids)
        retry = (not ok and not _budget_blocked(state)
                 and state["local_retries"]["evidence"] < limits.literature_retries
                 and state["operation_count"] + 2 < limits.max_operations)
        reason = [] if ok else (state.get("issue_codes") if _budget_blocked(state)
                                 else ["ALL_PAPERS_REJECTED" if papers else "NO_LITERATURE"])
        return {
            "stage": "evidence",
            "stage_signal": "ready" if ok else "retry" if retry else "blocked",
            "issue_codes": codes(reason),
            "events": event(state, phase="evidence", action="diagnose",
                            issue_codes=reason, retained=len(retained) if isinstance(retained,list) else 0),
        }
    def revise(state: V2State) -> dict:
        result = _operation(driver, limits, "revise_query", "evidence",
                            "query", merge=True)(state)
        updates = {**result, **_retry_update(state, "evidence", "requery")}
        updates["events"] = result["events"] + [updates["events"][-1]]
        return updates
    sub.add_node("diagnose", diagnose)
    sub.add_node("revise_query", revise)
    sub.add_edge(START, "search")
    sub.add_edge("search", "review")
    sub.add_edge("review", "diagnose")
    sub.add_conditional_edges(
        "diagnose",
        lambda s: "again" if s["stage_signal"] == "retry" else "done",
        {"again": "revise_query", "done": END},
    )
    sub.add_edge("revise_query", "search")
    return sub.compile()


def build_formulation_loop(driver: ResearchDriver, limits: V2Limits):
    sub = StateGraph(V2State)
    sub.add_node("generate", _operation(driver, limits, "generate", "formulation",
                                        "hypotheses", append_candidates=True))
    sub.add_node("check", _operation(driver, limits, "check_feasibility", "formulation",
                                     "feasibility"))
    def diagnose(state: V2State) -> dict:
        report = state.get("feasibility", {})
        existing = {c.get("id") for c in state.get("hypotheses", [])}
        eligible = report.get("eligible_ids", [])
        valid = (isinstance(eligible, list) and bool(eligible)
                 and set(eligible) <= existing)
        if _budget_blocked(state):
            reasons = state.get("issue_codes", [])
        elif valid:
            reasons = []
        else:
            raw = [code for block in report.get("blocked", [])
                   if isinstance(block, dict)
                   for code in block.get("issue_codes", [])]
            reasons = raw or ["NO_FEASIBLE_CANDIDATES"]
        retry = (not valid and not _budget_blocked(state)
                 and "NO_VERIFIED_DATA" not in reasons
                 and state["local_retries"]["formulation"] < limits.hypothesis_revisions
                 and state["operation_count"] + 2 < limits.max_operations)
        return {
            "stage": "formulation",
            "stage_signal": "ready" if valid and not _budget_blocked(state)
                           else "retry" if retry else "blocked",
            "issue_codes": codes(reasons),
            "events": event(state, phase="formulation", action="diagnose",
                            issue_codes=reasons, eligible=len(eligible) if valid else 0),
        }
    def revise(state: V2State) -> dict:
        result = _operation(driver, limits, "revise_hypothesis",
                            "formulation", "hypotheses", append_candidates=True)(state)
        increment = _retry_update(state, "formulation", "revise_from_blockers")
        result["local_retries"] = increment["local_retries"]
        result["events"] += [increment["events"][-1]]
        return result
    sub.add_node("diagnose", diagnose)
    sub.add_node("revise", revise)
    sub.add_conditional_edges(
        START,
        lambda s: "check" if s.get("stage") == "competition" and
        s.get("active_candidate_ids") else "generate",
        {"check": "check", "generate": "generate"},
    )
    sub.add_edge("generate", "check")
    sub.add_edge("check", "diagnose")
    sub.add_conditional_edges(
        "diagnose",
        lambda s: "revise" if s["stage_signal"] == "retry" else "done",
        {"revise": "revise", "done": END},
    )
    sub.add_edge("revise", "check")
    return sub.compile()


def build_competition_loop(driver: ResearchDriver, limits: V2Limits):
    sub = StateGraph(V2State)
    sub.add_node("debate", _operation(driver, limits, "debate", "competition", "competition"))
    sub.add_node("critic", _operation(driver, limits, "criticize", "competition",
                                      "competition_review"))
    def diagnose(state: V2State) -> dict:
        judgement = state.get("competition_review", {})
        needs_evolution = bool(judgement.get("needs_evolution", False))
        retry = (needs_evolution and not _budget_blocked(state)
                 and state["local_retries"]["competition"] < limits.competition_evolutions
                 and state["operation_count"] + 2 < limits.max_operations)
        issues = codes(judgement.get("issue_codes", []))
        return {
            "stage": "competition",
            "stage_signal": "evolve" if retry else "ready" if not _budget_blocked(state) else "blocked",
            "issue_codes": issues or state.get("issue_codes", []) if _budget_blocked(state) else issues,
            "events": event(state, phase="competition", action="diagnose",
                            issue_codes=issues),
        }
    def evolve(state: V2State) -> dict:
        result = _operation(driver, limits, "evolve", "competition",
                            "hypotheses", append_candidates=True)(state)
        increment = _retry_update(state, "competition", "evolve_after_critique")
        result["local_retries"] = increment["local_retries"]
        result["events"] += [increment["events"][-1]]
        return result
    def inspect_evolved(state: V2State) -> dict:
        valid = state.get("feasibility", {}).get("eligible_ids", [])
        new_ids = state.get("active_candidate_ids", [])
        ok = (not _budget_blocked(state) and bool(new_ids)
              and isinstance(valid, list) and set(new_ids) <= set(valid))
        return {
            "stage_signal": "retry" if ok else "needs_formulation",
            "issue_codes": [] if ok else ["NO_FEASIBLE_CANDIDATES"],
            "events": event(state, phase="competition", action="inspect_evolved",
                            changed=ok),
        }
    sub.add_node("diagnose", diagnose)
    sub.add_node("evolve", evolve)
    sub.add_node("check_evolved", _operation(driver, limits, "check_feasibility",
                                              "competition", "feasibility"))
    sub.add_node("inspect_evolved", inspect_evolved)
    sub.add_edge(START, "debate")
    sub.add_edge("debate", "critic")
    sub.add_edge("critic", "diagnose")
    sub.add_conditional_edges(
        "diagnose", lambda s: "evolve" if s["stage_signal"] == "evolve" else "done",
        {"evolve": "evolve", "done": END},
    )
    sub.add_edge("evolve", "check_evolved")
    sub.add_edge("check_evolved", "inspect_evolved")
    sub.add_conditional_edges(
        "inspect_evolved", lambda s: "debate" if s["stage_signal"] == "retry" else "done",
        {"debate": "debate", "done": END},
    )
    return sub.compile()


def build_verification_loop(driver: ResearchDriver, limits: V2Limits):
    sub = StateGraph(V2State)
    sub.add_node("design", _operation(driver, limits, "design_experiment",
                                      "verification", "protocol"))
    def execute(state: V2State) -> dict:
        if not state.get("protocol", {}).get("template_allowlisted"):
            return {
                "experiment": {"status": "not_executed",
                               "reason_code": "PROTOCOL_UNSUPPORTED"},
                "stage_signal": "blocked",
                "issue_codes": ["PROTOCOL_UNSUPPORTED"],
                "events": event(state, phase="verification",
                                action="unsafe_executor_blocked",
                                issue_codes=["PROTOCOL_UNSUPPORTED"]),
            }
        return _operation(driver, limits, "execute_experiment",
                          "verification", "experiment")(state)
    sub.add_node("execute", execute)
    sub.add_node("interpret", _operation(driver, limits, "inspect_result",
                                         "verification", "experiment_assessment"))
    def diagnose(state: V2State) -> dict:
        exec_status = state.get("experiment", {}).get("status")
        review = state.get("experiment_assessment", {})
        outcome = review.get("outcome")
        if _budget_blocked(state):
            issues = state.get("issue_codes", [])
        elif exec_status == "not_executed":
            issues = ["EXECUTOR_UNAVAILABLE"]
        elif exec_status == "failed":
            issues = ["EXPERIMENT_FAILED"]
        elif outcome == "refuted":
            issues = ["HYPOTHESIS_REFUTED"]
        elif outcome == "uninformative":
            issues = ["UNINFORMATIVE_RESULT"]
        elif outcome == "supported" and exec_status in (_REAL_EXECUTION, _SYNTHETIC_EXECUTION):
            issues = []
        else:
            issues = ["UNINFORMATIVE_RESULT"]
        retry = (not _budget_blocked(state) and
                 "EXPERIMENT_FAILED" in issues and
                 state["local_retries"]["verification"] < limits.experiment_retries and
                 state["operation_count"] + 3 < limits.max_operations)
        signal = ("ready" if not issues else "retry" if retry
                  else "refuted" if "HYPOTHESIS_REFUTED" in issues else "blocked")
        return {
            "stage": "verification", "stage_signal": signal,
            "issue_codes": codes(issues),
            "events": event(state, phase="verification", action="diagnose",
                            issue_codes=issues),
        }
    def retry(state: V2State) -> dict:
        return _retry_update(state, "verification", "redesign_after_failed_execution")
    sub.add_node("diagnose", diagnose)
    sub.add_node("retry", retry)
    sub.add_edge(START, "design")
    sub.add_edge("design", "execute")
    sub.add_edge("execute", "interpret")
    sub.add_edge("interpret", "diagnose")
    sub.add_conditional_edges(
        "diagnose", lambda s: "again" if s["stage_signal"] == "retry" else "done",
        {"again": "retry", "done": END},
    )
    sub.add_edge("retry", "design")
    return sub.compile()


def _report(state: V2State, *, completed: bool) -> dict:
    experiment = state.get("experiment", {})
    assessment = state.get("experiment_assessment", {})
    outcome = assessment.get("outcome")
    simulated = experiment.get("status") == _SYNTHETIC_EXECUTION
    # No synthetic fixture can ever produce a research validation claim.
    authentic = (
        state.get("run_mode") == "approved_execution" and
        experiment.get("status") == _REAL_EXECUTION and
        experiment.get("independent_audit") is True and
        assessment.get("scientific_truth_verified") is True and
        state.get("context", {}).get("data_access_verified") is True
    )
    level = "A" if completed and authentic else "B" if completed and simulated else "C"
    return {
        "research_goal": state.get("objective", ""),
        "deliverable_level": level,
        "recommendation": ("audited_pilot_ready" if level == "A" else
                           "synthetic_method_prototype" if level == "B" else
                           "actionable_plan_requires_verification"),
        "scientific_claim_verified": bool(completed and authentic),
        "no_fabricated_evidence": True,
        "last_stage": state.get("stage"),
        "final_issue_codes": state.get("issue_codes", []),
        "next_actions": (
            ["Independently replicate results and check novelty against primary literature"]
            if level == "A" else
            ["Check dataset rights and field schema; select an allowlisted pilot",
             "Prepare an explicit baseline, holdout split and failure criteria",
             "Repeat validation only after inputs are independently verified"]
        ),
        "candidate_ids": [x.get("id") for x in state.get("hypotheses", [])],
        "winner_id": (state.get("competition", {}).get("winner_id")
                      if completed and level in ("A", "B") else None),
        "experiment_outcome": outcome,
        "operation_count": state.get("operation_count", 0),
        "global_backtracks": state.get("global_backtracks", 0),
        "local_retries": dict(state.get("local_retries", {})),
    }


def build_v2_graph(driver: ResearchDriver, limits: V2Limits | None = None):
    """Compile four nested loops with a parent routing graph."""
    limits = limits or V2Limits()
    graph = StateGraph(V2State)
    def meta(state: V2State) -> dict:
        update = choose_next(state, limits)
        destination = update["next_stage"]
        if destination in ("evidence", "formulation", "competition", "verification"):
            # New cross-loop entry gets a fresh bounded local repair budget;
            # global backtracks and signatures still prevent infinite cycling.
            if state.get("stage") != destination:
                update["local_retries"] = {
                    **state.get("local_retries", {}), destination: 0
                }
        return update
    graph.add_node("meta_supervisor", meta)
    graph.add_node("evidence_loop", build_evidence_loop(driver, limits))
    graph.add_node("formulation_loop", build_formulation_loop(driver, limits))
    graph.add_node("competition_loop", build_competition_loop(driver, limits))
    graph.add_node("verification_loop", build_verification_loop(driver, limits))
    graph.add_node("reframe", _operation(driver, limits, "reframe_problem",
                                          "reframe", "query", merge=True))
    def after_reframe(state: V2State) -> dict:
        return {
            "stage": "reframe", "stage_signal": "reframed",
            "reframe_count": state.get("reframe_count", 0) + 1,
            "local_retries": {**state.get("local_retries", {}), "evidence": 0},
        }
    graph.add_node("reframe_marker", after_reframe)
    def finish(state: V2State) -> dict:
        return {
            "status": "completed",
            "report": _report(state, completed=True),
            "events": event(state, phase="meta_supervisor", action="finalize"),
        }
    def stop(state: V2State) -> dict:
        return {
            "status": "safe_stopped",
            "report": _report(state, completed=False),
            "events": event(state, phase="meta_supervisor", action="safe_stop",
                            issue_codes=state.get("issue_codes", [])),
        }
    graph.add_node("finalize", finish)
    graph.add_node("safe_stop", stop)
    graph.add_edge(START, "meta_supervisor")
    graph.add_conditional_edges(
        "meta_supervisor",
        lambda s: s["next_stage"],
        {
            "evidence": "evidence_loop",
            "formulation": "formulation_loop",
            "competition": "competition_loop",
            "verification": "verification_loop",
            "reframe": "reframe",
            "finalize": "finalize",
            "safe_stop": "safe_stop",
        },
    )
    for name in ("evidence_loop", "formulation_loop", "competition_loop",
                 "verification_loop"):
        graph.add_edge(name, "meta_supervisor")
    graph.add_edge("reframe", "reframe_marker")
    graph.add_edge("reframe_marker", "meta_supervisor")
    graph.add_edge("finalize", END)
    graph.add_edge("safe_stop", END)
    return graph.compile()


def run_v2_dry_run(scenario: str, objective: str = "Synthetic research objective",
                   *, limits: V2Limits | None = None,
                   context: dict | None = None) -> V2State:
    """Never creates a model client, network connection, or external API call."""
    driver = ScriptedResearchDriver(scenario)
    limits = limits or V2Limits()
    initial = initial_state(objective, context=context or {
        "synthetic_permission": scenario != "no_data_permission"
    })
    graph = build_v2_graph(driver, limits)
    # LangGraph recursions count subgraph steps, not scientific loops.
    return graph.invoke(initial, config={"recursion_limit": max(100, limits.max_operations * 8)})
