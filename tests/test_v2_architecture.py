"""V2 architecture contracts: no external services, data or paid model calls."""
import json
import pytest

from research_agent_lab.frontier.v2.cli import main
from research_agent_lab.frontier.v2.driver import ScriptedResearchDriver
from research_agent_lab.frontier.v2.graph import build_v2_graph, run_v2_dry_run
from research_agent_lab.frontier.v2.state import V2Limits, initial_state

def execute(scenario, *, limits=None, context=None):
    return run_v2_dry_run(scenario, limits=limits, context=context)

def test_graph_is_parent_plus_four_real_nested_subgraphs():
    graph = build_v2_graph(ScriptedResearchDriver())
    nodes = set(graph.get_graph().nodes)
    assert {"meta_supervisor", "evidence_loop", "formulation_loop",
            "competition_loop", "verification_loop", "safe_stop", "finalize",
            "reframe"} <= nodes

def test_happy_path_reaches_actionable_synthetic_prototype_without_fake_claim():
    report = execute("happy_path")
    assert report["status"] == "completed"
    assert report["report"]["deliverable_level"] == "B"
    assert report["report"]["scientific_claim_verified"] is False
    assert report["experiment"]["status"] == "simulated_executed"
    assert [d["to"] for d in report["decisions"][:5]] == [
        "evidence", "formulation", "competition", "verification", "finalize"
    ]

def test_all_papers_rejected_requeries_and_reframes_before_safe_stop():
    report = execute("all_papers_rejected")
    assert report["status"] == "safe_stopped"
    assert report["report"]["deliverable_level"] == "C"
    assert "ALL_PAPERS_REJECTED" in report["report"]["final_issue_codes"]
    assert any(d["to"] == "reframe" for d in report["decisions"])
    assert not report["hypotheses"]
    assert report["local_retries"]["evidence"] == 2

def test_literature_loop_can_recover_after_targeted_requery():
    report = execute("recover_retrieval")
    assert report["status"] == "completed"
    assert any(e["action"] == "requery" for e in report["events"])
    assert report["literature"]["retained_ids"] == ["FAKE_P1"]

def test_unverified_data_is_a_hard_stop_not_a_forged_elo_winner():
    report = execute("no_data_permission")
    assert report["status"] == "safe_stopped"
    assert report["report"]["deliverable_level"] == "C"
    assert "NO_VERIFIED_DATA" in report["report"]["final_issue_codes"]
    assert all(x["to"] != "competition" for x in report["decisions"])
    assert not report["competition"]

def test_targeted_repair_creates_new_lineage_and_passes_precheck():
    report = execute("recover_feasibility")
    assert report["status"] == "completed"
    ids = {x["id"] for x in report["hypotheses"]}
    assert len(ids) == 4
    assert any(x.get("parent_ids") for x in report["hypotheses"])
    assert len(report["feasibility"]["eligible_ids"]) == 2
    assert report["local_retries"]["formulation"] == 1
    assert any(e["action"] == "revise_from_blockers" for e in report["events"])

def test_persistent_infeasibility_cannot_cause_unbounded_llm_loops():
    report = execute("persistent_infeasibility")
    assert report["status"] == "safe_stopped"
    assert report["global_backtracks"] <= 3
    assert report["operation_count"] <= 48
    assert report["report"]["deliverable_level"] == "C"

def test_competition_critique_evolves_and_rechecks_before_second_debate():
    report = execute("critique_then_evolve")
    assert report["status"] == "completed"
    assert any(x["action"] == "inspect_evolved" for x in report["events"])
    assert report["local_retries"]["competition"] == 1
    assert any(x.get("parent_ids") for x in report["hypotheses"])

def test_experiment_refutation_returns_globally_to_formulation():
    report = execute("experimental_refutation")
    assert report["status"] == "completed"
    assert any(d["reason_code"] == "REVISE_FROM_EXPERIMENT"
               and d["to"] == "formulation" for d in report["decisions"])
    assert report["global_backtracks"] == 1
    assert len(report["hypotheses"]) >= 4
    assert report["report"]["scientific_claim_verified"] is False

def test_experiment_failure_can_trigger_inner_redesign_retry():
    report = execute("experiment_transient_failure")
    assert report["status"] == "completed"
    assert report["local_retries"]["verification"] == 1
    assert any(e["action"] == "redesign_after_failed_execution" for e in report["events"])

def test_unapproved_executor_stops_with_specific_next_actions():
    report = execute("executor_unavailable")
    assert report["status"] == "safe_stopped"
    assert report["report"]["deliverable_level"] == "C"
    assert report["report"]["next_actions"]
    assert "EXECUTOR_UNAVAILABLE" in report["report"]["final_issue_codes"]

def test_duplicate_non_improving_repairs_cannot_claim_progress():
    report = execute("repeated_noop")
    assert report["status"] == "safe_stopped"
    assert report["report"]["deliverable_level"] == "C"
    assert report["operation_count"] <= 48
    assert not report["feasibility"].get("eligible_ids", [])

def test_operation_budget_is_global_and_protected():
    report = execute("happy_path", limits=V2Limits(max_operations=8))
    assert report["status"] == "safe_stopped"
    assert report["operation_count"] <= 8
    assert report["report"]["scientific_claim_verified"] is False

def test_local_repair_limits_and_global_backtrack_cap_are_distinct():
    report = execute("experimental_refutation", limits=V2Limits(
        literature_retries=0, hypothesis_revisions=0, competition_evolutions=0,
        experiment_retries=0, global_backtracks=0, max_operations=48
    ))
    assert report["status"] == "safe_stopped"
    assert report["global_backtracks"] == 0

def test_event_log_never_contains_raw_private_context():
    token = "NOT_FOR_EVENT_AUDIT_123456"
    report = execute("happy_path", context={
        "synthetic_permission": True, "private_note": token
    })
    assert token not in json.dumps(report["events"])
    assert token not in json.dumps(report["decisions"])
    assert len(report["events"]) >= report["operation_count"]

def test_offline_cli_has_no_network_credentials_or_paid_execution(capsys):
    assert main(["--scenario", "recover_retrieval"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["execution_mode"] == "synthetic_offline_no_paid_ai"
    assert output["report"]["deliverable_level"] == "B"

def test_bad_configuration_cannot_disable_guards():
    with pytest.raises(ValueError):
        V2Limits(max_operations=1)
    with pytest.raises(ValueError):
        V2Limits(max_repeat_signatures=100)
    with pytest.raises(ValueError):
        ScriptedResearchDriver("unknown")
    with pytest.raises(ValueError):
        initial_state("")


def test_unapproved_live_mode_cannot_be_activated_by_injected_state():
    state = initial_state("An unauthorized production attempt",context={"synthetic_permission":True})
    state["run_mode"] = "approved_execution"
    graph = build_v2_graph(ScriptedResearchDriver())
    report = graph.invoke(state, config={"recursion_limit":100})
    assert report["status"] == "safe_stopped"
    assert report["operation_count"] == 0
    assert report["decisions"][0]["reason_code"] == "V2_PRODUCTION_EXECUTION_NOT_ACTIVATED"


def test_safe_stop_reports_no_fake_winner_even_if_old_competition_exists():
    report = execute("executor_unavailable")
    assert report["status"] == "safe_stopped"
    assert report["competition"].get("winner_id")
    assert report["report"]["winner_id"] is None
