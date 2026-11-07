"""Opt-in V2 agent boundary and deterministic architecture-test driver.

The adapter contract deliberately separates *orchestration* from paid model,
OpenAlex, data access, and experimental execution. No adapter is executed on
module import and no real credentials are loaded by the dry-run CLI.
"""
from __future__ import annotations

from typing import Any, Mapping, Protocol

from .state import Action, V2State

class ResearchDriver(Protocol):
    def perform(self, operation: Action, state: V2State) -> dict[str, Any]:
        """Return a bounded stage update, not LangGraph routing instructions."""


class ScriptedResearchDriver:
    """Synthetic FSM test cases. All science and paper IDs are invented.

    This driver is only for validating control flow. Its simulated evidence,
    executors and successes must never be reported as real research findings.
    """

    SCENARIOS = frozenset((
        "happy_path", "all_papers_rejected", "recover_retrieval",
        "no_data_permission", "recover_feasibility",
        "persistent_infeasibility", "critique_then_evolve",
        "experimental_refutation", "experiment_transient_failure",
        "executor_unavailable", "repeated_noop",
    ))

    def __init__(self, scenario: str = "happy_path"):
        if scenario not in self.SCENARIOS:
            raise ValueError("Unknown synthetic V2 architecture scenario")
        self.scenario = scenario
        self.operations: list[str] = []

    @staticmethod
    def _candidate(cid: str, *, feasible: bool, parent_ids: list[str] | None = None) -> dict:
        return {
            "id": cid,
            "title": f"Fictional test hypothesis {cid}",
            "question": f"Does synthetic {cid} differ from a dummy baseline?",
            "mechanism": "Dry-run reasoning, no scientific evidence",
            "registered_fields": ["fictional_target"] if feasible else [],
            "parent_ids": parent_ids or [],
            "execution_plan": {
                "outcome_field": "fictional_target" if feasible else "missing_field",
                "baseline_method": "fictional mean benchmark",
                "steps": ["Register synthetic protocol", "Simulate a small holdout test"],
            },
        }

    def perform(self, operation: Action, state: V2State) -> dict[str, Any]:
        self.operations.append(operation)
        retries = state.get("local_retries", {})
        backtracks = state.get("global_backtracks", 0)
        authorized = bool(state.get("context", {}).get("synthetic_permission", True))
        if operation == "search":
            return {
                "papers": [{"id": "FAKE_P1"}, {"id": "FAKE_P2"}],
                "source": "synthetic_only",
            }
        if operation == "review_papers":
            should_reject = self.scenario == "all_papers_rejected" or (
                self.scenario == "recover_retrieval" and
                retries.get("evidence", 0) == 0 and
                state.get("reframe_count", 0) == 0
            )
            return {
                "retained_ids": [] if should_reject else ["FAKE_P1"],
                "rejected_ids": ["FAKE_P1", "FAKE_P2"] if should_reject else ["FAKE_P2"],
                "source": "synthetic_only",
            }
        if operation == "revise_query":
            return {"query_seed": "fictional revised query "+str(retries.get("evidence", 0)+1)}
        if operation == "reframe_problem":
            return {"query_seed": "fictional broader scientific mechanism"}
        if operation == "generate":
            if self.scenario in ("no_data_permission", "recover_feasibility",
                                 "persistent_infeasibility", "repeated_noop"):
                feasible = False
            else:
                feasible = authorized
            # After a refuting experimental result, research question is re-scoped.
            prefix = "H1" if backtracks == 0 else "H"+str(1+backtracks*2)
            return {
                "candidates": [
                    self._candidate(prefix, feasible=feasible),
                    self._candidate("H"+str(int(prefix[1:])+1), feasible=feasible),
                ]
            }
        if operation == "check_feasibility":
            focused = set(state.get("active_candidate_ids") or [])
            eligible = [c["id"] for c in state.get("hypotheses", [])
                        if (not focused or c["id"] in focused) and authorized and
                        c.get("execution_plan", {}).get("outcome_field") == "fictional_target"]
            all_ids = [c["id"] for c in state.get("hypotheses", [])
                       if not focused or c["id"] in focused]
            return {
                "eligible_ids": eligible,
                "blocked": [{
                    "id": cid, "issue_codes": [
                        "NO_VERIFIED_DATA" if not authorized else
                        "OUTCOME_FIELD_NOT_REGISTERED"
                    ]
                } for cid in all_ids if cid not in eligible],
                "checked_without_running_data": True,
                "authorization_type": "synthetic_fixture",
            }
        if operation == "revise_hypothesis":
            if self.scenario in ("no_data_permission", "persistent_infeasibility",
                                 "repeated_noop"):
                return {"candidates": []}
            if self.scenario == "recover_feasibility":
                return {"candidates": [
                    self._candidate("H"+str(len(state.get("hypotheses", []))+1),
                                    feasible=True,
                                    parent_ids=[state["hypotheses"][0]["id"]]),
                    self._candidate("H"+str(len(state.get("hypotheses", []))+2),
                                    feasible=True,
                                    parent_ids=[state["hypotheses"][1]["id"]]),
                ]}
            return {"candidates": []}
        if operation == "debate":
            ids = state.get("feasibility", {}).get("eligible_ids", [])
            return {
                "winner_id": ids[0] if ids else "",
                "compared_ids": ids[:3],
                "pair_count": max(0,len(ids)-1),
                "position_bias_checked": True,
                "llm_judgement_not_scientific_truth": True,
            }
        if operation == "criticize":
            if self.scenario == "critique_then_evolve" and retries.get("competition", 0) == 0:
                return {"issue_codes": ["UNRESOLVED_CRITIQUE"], "needs_evolution": True}
            return {"issue_codes": [], "needs_evolution": False}
        if operation == "evolve":
            first = state.get("hypotheses", [])[0]
            child_id = "H"+str(100+len(state.get("hypotheses", [])))
            return {"candidates": [
                self._candidate(child_id, feasible=authorized, parent_ids=[first["id"]])
            ]}
        if operation == "design_experiment":
            return {"protocol_id": "FIXED_SYNTHETIC_TEST", "template_allowlisted": True,
                    "is_real_dataset": False}
        if operation == "execute_experiment":
            if self.scenario == "executor_unavailable":
                return {"status": "not_executed", "reason_code": "EXECUTOR_UNAVAILABLE"}
            if self.scenario == "experiment_transient_failure" and retries.get("verification", 0) == 0:
                return {"status": "failed", "reason_code": "EXPERIMENT_FAILED"}
            return {"status": "simulated_executed",
                    "metric_label": "synthetic demonstration only", "value": 0.0}
        if operation == "inspect_result":
            if state.get("experiment", {}).get("status") == "not_executed":
                return {"outcome": "not_executed", "issue_codes": ["EXECUTOR_UNAVAILABLE"]}
            if state.get("experiment", {}).get("status") == "failed":
                return {"outcome": "failed", "issue_codes": ["EXPERIMENT_FAILED"]}
            if self.scenario == "experimental_refutation" and backtracks == 0:
                return {"outcome": "refuted", "issue_codes": ["HYPOTHESIS_REFUTED"]}
            return {"outcome": "supported", "issue_codes": [],
                    "scientific_truth_verified": False}
        raise ValueError("Unsupported architecture operation")
