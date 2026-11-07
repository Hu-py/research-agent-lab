"""Free, fictional Supervisor QA; never estimates scientific quality."""
from __future__ import annotations
import json
from .graph import run_v2_dry_run
from .state import V2Limits

EXPECTED = {
 "happy_path":"completed", "all_papers_rejected":"safe_stopped",
 "recover_retrieval":"completed", "no_data_permission":"safe_stopped",
 "recover_feasibility":"completed", "persistent_infeasibility":"safe_stopped",
 "critique_then_evolve":"completed", "experimental_refutation":"completed",
 "experiment_transient_failure":"completed", "executor_unavailable":"safe_stopped",
 "repeated_noop":"safe_stopped",
}

def run_benchmark() -> dict:
    results=[]
    for scenario, expected in EXPECTED.items():
        state=run_v2_dry_run(scenario,limits=V2Limits())
        decisions=state["decisions"]
        audited=bool(decisions) and all(
            "observed_facts" in d and "alternatives" in d
            and "problem_diagnosis" in d and
            d.get("scientific_quality_verified") is False
            for d in decisions)
        safe=all(not d.get("verifier_veto_codes") or d.get("to")=="safe_stop"
                 for d in decisions)
        passed_=(state["status"]==expected and audited and safe and
                 state["report"]["scientific_claim_verified"] is False and
                 state["operation_count"] <= 48)
        results.append({
            "scenario":scenario,"status":state["status"],
            "expected":expected,"passed":passed_,
            "decisions":len(decisions),
            "feedback_rows":len(state.get("decision_feedback",[])),
            "abstentions":sum(bool(d.get("abstained")) for d in decisions),
        })
    return {
        "benchmark":"synthetic_control_flow_only",
        "data":"fictional_scripted",
        "cases":len(results),"passed":sum(x["passed"] for x in results),
        "failed":sum(not x["passed"] for x in results),
        "scientific_decision_accuracy":"not_estimated",
        "causal_policy_improvement":"not_estimated",
        "ready_for_automatic_policy_training":False,
        "results":results,
    }

def main() -> int:
    report=run_benchmark()
    print(json.dumps(report,indent=2,ensure_ascii=False))
    return int(report["failed"]>0)

if __name__=="__main__":
    raise SystemExit(main())
