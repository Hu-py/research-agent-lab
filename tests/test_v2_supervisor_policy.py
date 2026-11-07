"""Independent policy-guard checks and observational feedback (NO LLM)."""
import json
import pytest

from research_agent_lab.frontier.v2.evidence import observe, diagnose
from research_agent_lab.frontier.v2.feedback import (
    evaluate_pending_decision, descriptive_policy_audit
)
from research_agent_lab.frontier.v2.graph import run_v2_dry_run
from research_agent_lab.frontier.v2.policy import (
    propose_options, verify_option
)
from research_agent_lab.frontier.v2.state import V2Limits, initial_state
from research_agent_lab.frontier.v2.supervisor import choose_next

LIMITS = V2Limits()

def base(stage,signal="ready"):
    s=initial_state("Fictional research objective")
    s["stage"]=stage
    s["stage_signal"]=signal
    return s

def decide(s):
    return choose_next(s,LIMITS)

def test_observer_counts_only_current_registered_ids():
    s=base("evidence")
    s["literature"]={"papers":[{"id":"A"}],"retained_ids":["FABRICATED"]}
    o=observe(s,max_operations=48)
    assert o["retained_count"]==1
    assert o["retained_ids_valid"] is False
    assert "FABRICATED" not in json.dumps(o)
    assert diagnose(o)["root_cause_independently_confirmed"] is False

def test_false_paper_ready_is_vetoed_even_when_stage_claims_success():
    s=base("evidence")
    s["literature"]={"papers":[{"id":"P01"}],"retained_ids":[]}
    d=decide(s)
    assert d["next_stage"]=="safe_stop"
    record=d["decisions"][-1]
    assert record["abstained"]
    assert record["reason_code"]=="PREFERRED_ROUTE_VETOED"
    assert "FORMULATION_PREREQUISITES_MISSING" in record["verifier_veto_codes"]
    assert len(record["alternatives"])==2

@pytest.mark.parametrize("broken", [
    {"eligible_ids":["H001","UNKNOWN"]},
    {"eligible_ids":["H001","H001"]},
    {"eligible_ids":[]},
])
def test_unfounded_elo_gate_never_approves_hallucinated_ids(broken):
    s=base("formulation")
    s["hypotheses"]=[{"id":"H001"},{"id":"H002"}]
    s["feasibility"]=broken
    d=decide(s)
    assert d["next_stage"]=="safe_stop"
    assert "COMPETITION_REQUIRES_TWO_VERIFIED_CANDIDATES" in d["decisions"][-1]["verifier_veto_codes"]

def test_unverified_data_permission_is_non_bypassable_even_if_eligible():
    s=base("formulation")
    s["hypotheses"]=[{"id":"H001"},{"id":"H002"}]
    s["feasibility"]={"eligible_ids":["H001","H002"]}
    s["issue_codes"]=["NO_VERIFIED_DATA"]
    d=decide(s)
    assert d["next_stage"]=="safe_stop"
    assert "UNVERIFIED_DATA_BLOCKER" in d["decisions"][-1]["verifier_veto_codes"]

def test_competition_cannot_verify_non_existent_winner():
    s=base("competition")
    s["hypotheses"]=[{"id":"H001"},{"id":"H002"}]
    s["feasibility"]={"eligible_ids":["H001","H002"]}
    s["competition"]={"winner_id":"H999","pair_count":2}
    d=decide(s)
    assert d["next_stage"]=="safe_stop"
    assert "VERIFICATION_REQUIRES_ELIGIBLE_CANDIDATE" in d["decisions"][-1]["verifier_veto_codes"]

@pytest.mark.parametrize("status,allowed",[
    ("unknown",False),
    ("not_executed",False),
    ("failed",False),
    ("simulated_executed",True),
])
def test_scientific_gate_requires_actual_allowlisted_protocol(status, allowed):
    s=base("verification")
    s["experiment_assessment"]={"outcome":"supported"}
    s["experiment"]={"status":status}
    s["protocol"]={"template_allowlisted":True}
    d=decide(s)
    assert (d["next_stage"]=="finalize")==allowed
    if not allowed:
        assert d["decisions"][-1]["abstained"]

def test_no_protocol_allowed_no_finalization_even_if_model_says_supported():
    s=base("verification")
    s["experiment_assessment"]={"outcome":"supported"}
    s["experiment"]={"status":"simulated_executed"}
    s["protocol"]={"template_allowlisted":False}
    d=decide(s)
    assert d["next_stage"]=="safe_stop"
    assert "FINALIZE_WITHOUT_VERIFIABLE_PROTOCOL_RESULT" in d["decisions"][-1]["verifier_veto_codes"]

def test_decision_record_contains_reasons_alternatives_and_uncalibrated_utility():
    run=run_v2_dry_run("recover_retrieval")
    decisions=run["decisions"]
    assert len(decisions)>=5
    for row in decisions:
        assert row["decision_id"].startswith("D")
        assert isinstance(row["observed_facts"],dict)
        assert isinstance(row["alternatives"],list)
        assert row["problem_diagnosis"]["scientific_quality_inferred"] is False
        assert row["confidence_calibrated"] is False
        assert row["scientific_quality_verified"] is False
        for alt in row["alternatives"]:
            assert alt["expected_effect_is_untested"] is True
            assert alt["scientific_success_probability"] is None
            assert alt["verification"]["verifier_kind"]=="deterministic_independent_constraints"

def test_feedback_uses_actual_next_state_not_same_agents_self_score():
    run=run_v2_dry_run("happy_path")
    history=run["decision_feedback"]
    assert len(history)>=3
    assert history[0]["selected_action"]=="evidence"
    assert history[0]["expected_metric"]=="retained_count"
    assert history[0]["observed_delta"]==1
    assert history[0]["observed_process_verdict"]=="observed_process_progress"
    assert all(x["causal_effect_estimated"] is False for x in history)
    assert all(x["counterfactual_observed"] is False for x in history)
    assert all(x["scientific_quality_verified"] is False for x in history)
    assert run["policy_audit"]["policy_ready_for_automatic_retraining"] is False

def test_no_retrieval_progress_is_recorded_as_no_progress():
    run=run_v2_dry_run("all_papers_rejected")
    reviews=[r for r in run["decision_feedback"] if r["expected_metric"]=="retained_count"]
    assert reviews and all(r["observed_process_verdict"]=="unchanged" for r in reviews)

def test_process_progress_cannot_be_mislabeled_as_real_science():
    run=run_v2_dry_run("happy_path")
    assert run["report"]["scientific_claim_verified"] is False
    assert run["report"]["deliverable_level"]=="B"
    assert run["policy_audit"]["scientific_quality_verified"] is False

def test_private_context_not_exposed_in_decision_audit():
    secret="KEEP_THIS_PRIVATE_ACROSS_ALL_DECISION_RECORDS"
    run=run_v2_dry_run("happy_path",context={
        "synthetic_permission":True,
        "private_note":secret, "data_access_verified":False,
    })
    whole=json.dumps({"decisions":run["decisions"],
                      "feedback":run["decision_feedback"],
                      "audit":run["policy_audit"]})
    assert secret not in whole
    assert "fictional test hypothesis" not in whole.lower()

def test_no_policy_retraining_from_tiny_nonrandom_observations():
    rows=[{"observed_process_verdict":"observed_process_progress"} for _ in range(3)]
    summary=descriptive_policy_audit(rows)
    assert summary["process_progress"]==3
    assert summary["policy_ready_for_automatic_retraining"] is False

def test_unsafe_unknown_advice_is_rejected():
    s=base("init")
    o=observe(s,max_operations=48)
    invented={"action":"call_any_tool",
              "supporting_observation_refs":["stage"],
              "expected_metric":"none"}
    verdict=verify_option(s,o,invented,LIMITS)
    assert not verdict["approved"]
    assert "ACTION_NOT_ALLOWLISTED" in verdict["veto_codes"]

def test_unknown_evidence_reference_is_rejected_even_for_valid_action():
    s=base("init")
    o=observe(s,max_operations=48)
    invented={"action":"evidence",
              "supporting_observation_refs":["private_freeform_text"],
              "expected_metric":"retained_count"}
    verdict=verify_option(s,o,invented,LIMITS)
    assert not verdict["approved"]
    assert "UNGROUNDED_ACTION_EVIDENCE" in verdict["veto_codes"]
