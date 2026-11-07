"""V2.2 task-contract → independent evaluation → scoped repair integration.

All scenarios are fictional; process-level passing must never be misreported
as research novelty, real-data access or externally audited conclusions.
"""
import json
import pytest

from research_agent_lab.frontier.v2.contracts import issue_contract, contract_for_stage
from research_agent_lab.frontier.v2.evaluator import evaluate_task
from research_agent_lab.frontier.v2.graph import run_v2_dry_run, build_v2_graph
from research_agent_lab.frontier.v2.driver import ScriptedResearchDriver
from research_agent_lab.frontier.v2.state import V2Limits, initial_state
from research_agent_lab.frontier.v2.supervisor import choose_next


def test_every_stage_has_a_controller_issued_contract_and_an_independent_evaluation():
    result = run_v2_dry_run("happy_path")
    assert result["status"] == "completed"
    contracts = result["task_contracts"]
    assert [c["target_stage"] for c in contracts] == [
        "evidence", "formulation", "competition", "verification"
    ]
    assert [x["stage"] for x in result["task_evaluations"]] == [
        "evidence", "formulation", "competition", "verification"
    ]
    assert all(r["verdict"] == "stage_passed"
               for r in result["task_evaluations"])
    for c in contracts:
        assert c["contract_id"].startswith("TC-D")
        assert c["acceptance_checks"]
        assert c["scientific_quality_unverified"] is True
        assert c["bounded_no_external_permission"] is True
    for assessment in result["task_evaluations"]:
        assert assessment["checks_passed"] is True
        assert assessment["scientific_quality_verified"] is False


def test_literature_repair_actually_resolves_an_observed_local_defect():
    run = run_v2_dry_run("recover_retrieval")
    findings = [e for e in run["task_evaluations"] if e["stage"] == "evidence"]
    assert len(findings) == 2
    assert findings[0]["verdict"] == "revision_required"
    assert "ALL_PAPERS_REJECTED" in findings[0]["issue_codes"]
    assert "INSPECT_REJECTIONS_AND_REQUERY" in findings[0]["repair_plan"]["repair_action_codes"]
    assert findings[1]["verdict"] == "stage_passed"
    assert "ALL_PAPERS_REJECTED" in findings[1]["verified_resolved_issue_codes"]
    assert findings[0]["contract_id"] == findings[1]["contract_id"]
    assert any(row["task_evaluation_grounded"]
               and "ALL_PAPERS_REJECTED" in row["verified_resolved_issue_codes"]
               for row in run["decision_feedback"])


def test_formulation_local_revisions_must_have_checkable_outcome():
    run = run_v2_dry_run("recover_feasibility")
    reviews = [e for e in run["task_evaluations"] if e["stage"] == "formulation"]
    assert len(reviews) == 2
    assert reviews[0]["verdict"] == "revision_required"
    assert "NO_FEASIBLE_CANDIDATES" in reviews[0]["issue_codes"]
    assert reviews[1]["verdict"] == "stage_passed"
    assert "NO_FEASIBLE_CANDIDATES" in reviews[1]["verified_resolved_issue_codes"]
    assert reviews[1]["process_changes"]["new_version_with_parent_lineage"] >= 2
    assert run["policy_audit"]["observed_task_repairs"] >= 1


def test_refuted_hypothesis_produces_focused_cross_stage_contract_and_descendant():
    run = run_v2_dry_run("experimental_refutation")
    focused = [
        c for c in run["task_contracts"]
        if c["target_stage"] == "formulation" and
        c["revision_intent"] == "experiment_refutation"
    ]
    assert len(focused) == 1
    c = focused[0]
    assert "HYPOTHESIS_REFUTED" in c["target_issue_codes"]
    assert c["focus_candidate_ids"]
    assert c["repair_action_codes"] == ["REVISE_REFUTED_CLAIM_AND_RETEST"]
    assert c["source_stage"] == "verification"
    parent = c["focus_candidate_ids"][0]
    assert any(parent in cand.get("parent_ids", [])
               for cand in run["hypotheses"] if cand["id"] != parent)
    # A rewritten hypothesis is NOT a refutation that has been scientifically
    # resolved. Its evidence burden persists until a real independent test.
    formulation_evals = [r for r in run["task_evaluations"]
                         if r["contract_id"] == c["contract_id"]]
    assert formulation_evals and "HYPOTHESIS_REFUTED" in (
        formulation_evals[-1]["remaining_target_issue_codes"])
    assert run["report"]["scientific_claim_verified"] is False


def test_after_reframe_query_contract_retains_original_failure_code():
    run = run_v2_dry_run("all_papers_rejected")
    contracts = [c for c in run["task_contracts"] if c["target_stage"] == "evidence"]
    assert len(contracts) == 2
    assert "ALL_PAPERS_REJECTED" in contracts[1]["target_issue_codes"]
    assert "INSPECT_REJECTIONS_AND_REQUERY" in contracts[1]["repair_action_codes"]
    assert run["status"] == "safe_stopped"
    assert run["report"]["deliverable_level"] == "C"


def test_unverified_data_never_enters_elo_and_repair_plan_remains_actionable():
    run = run_v2_dry_run("no_data_permission")
    assert run["status"] == "safe_stopped"
    assert all(c["target_stage"] != "competition" for c in run["task_contracts"])
    finding = next(e for e in run["task_evaluations"] if e["stage"] == "formulation")
    assert finding["verdict"] == "global_reroute"
    assert "NO_VERIFIED_DATA" in finding["repair_plan"]["target_issue_codes"]
    assert "OBTAIN_INDEPENDENT_DATA_PERMISSION" in finding["repair_plan"]["repair_action_codes"]


def test_competition_evolution_must_recheck_eligibility_and_record_task_verdict():
    run = run_v2_dry_run("critique_then_evolve")
    assert run["status"] == "completed"
    evaluations = [x for x in run["task_evaluations"] if x["stage"] == "competition"]
    assert evaluations[0]["stage_signal"] == "evolve"
    assert evaluations[-1]["verdict"] == "stage_passed"
    assert any(c.get("parent_ids") for c in run["hypotheses"])
    assert any(e["action"] == "inspect_evolved" for e in run["events"])


def test_experiment_failure_retries_with_new_evaluation_and_keeps_evidence_limit():
    run = run_v2_dry_run("experiment_transient_failure")
    reviews = [r for r in run["task_evaluations"] if r["stage"] == "verification"]
    assert len(reviews) == 2
    assert reviews[0]["verdict"] == "revision_required"
    assert "EXPERIMENT_FAILED" in reviews[0]["issue_codes"]
    assert reviews[1]["verdict"] == "stage_passed"
    assert run["report"]["scientific_claim_verified"] is False


def test_unavailable_executor_does_not_get_promoted_to_scientific_success():
    run = run_v2_dry_run("executor_unavailable")
    assert run["status"] == "safe_stopped"
    assert not run["report"]["scientific_claim_verified"]
    assert run["task_evaluations"][-1]["checks"]["experiment_ran"] is False
    assert run["report"]["deliverable_level"] == "C"


def test_scientific_quality_remains_unverified_even_after_synthetic_pass():
    run = run_v2_dry_run("happy_path")
    assert all(r["scientific_quality_verified"] is False for r in run["task_evaluations"])
    assert all(c["scientific_quality_unverified"] is True for c in run["task_contracts"])
    assert run["report"]["route_success_is_not_scientific_truth"] is True


def test_forged_stage_success_cannot_cross_independent_task_gate():
    state = initial_state("Fictional objective")
    state["stage"] = "evidence"
    state["stage_signal"] = "ready"
    state["literature"] = {"papers": [{"id": "P1"}], "retained_ids": ["P1"]}
    c = issue_contract(state, target="evidence", decision_id="D0009",
                       reason="TEST", limits=V2Limits())
    state["active_task_contract"] = c
    # Agent wrote a plausible status, but no independent record was produced.
    d = choose_next(state, V2Limits())
    assert d["next_stage"] == "safe_stop"
    assert "INDEPENDENT_TASK_EVALUATION_MISSING" in (
        d["decisions"][-1]["verifier_veto_codes"])


def test_independent_evaluator_rejects_invented_references_despite_ready_claim():
    state = initial_state("Synthetic")
    state["stage"] = "evidence"
    state["stage_signal"] = "ready"
    state["literature"] = {
        "papers": [{"id": "P1"}], "retained_ids": ["P_FAKE"]
    }
    c = issue_contract(state, target="evidence", decision_id="D0001",
                       reason="TEST", limits=V2Limits())
    state["active_task_contract"] = c
    evaluation = evaluate_task(state, stage="evidence", nominal_signal="ready",
                               issues=[], limits=V2Limits())
    assert evaluation["checks_passed"] is False
    assert evaluation["verdict"] != "stage_passed"
    assert "ALL_PAPERS_REJECTED" in evaluation["issue_codes"]


def test_sensitive_research_objective_and_private_notes_absent_from_public_ledger():
    secret = "PRIVATE_CUSP_RESEARCH_NOT_FOR_LOGS"
    run = run_v2_dry_run("happy_path", objective=secret,
                         context={"synthetic_permission": True,
                                  "private_note": secret})
    ledger = json.dumps({
        "task_contracts": run["task_contracts"],
        "task_evaluations": run["task_evaluations"],
        "decisions": run["decisions"],
        "decision_feedback": run["decision_feedback"],
    })
    assert secret not in ledger


def test_bounded_global_and_local_loops_still_terminate():
    for scenario in ("all_papers_rejected", "persistent_infeasibility",
                     "repeated_noop", "no_data_permission"):
        run = run_v2_dry_run(scenario)
        assert run["status"] == "safe_stopped"
        assert run["operation_count"] <= 48
        assert run["global_backtracks"] <= 3
        assert len(run["task_evaluations"]) <= 30
