"""Deterministic research-orchestration stress harness (no paid models).

Runs multiple resource envelopes across the same scripted cases and checks
control invariants, producing a machine-readable CI artifact. These are
architecture experiments, not empirical scientific experiments.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .benchmark import EXPECTED
from .graph import run_v2_dry_run
from .state import V2Limits

PROFILES = {
    "minimal": V2Limits(
        literature_retries=0, hypothesis_revisions=0, competition_evolutions=0,
        experiment_retries=0, global_backtracks=0, max_operations=12,
    ),
    "default": V2Limits(),
    "exploratory": V2Limits(
        literature_retries=3, hypothesis_revisions=3,
        competition_evolutions=3, experiment_retries=3,
        global_backtracks=5, max_operations=80, max_repeat_signatures=3,
    ),
}


def run_stress() -> dict:
    cases: list[dict] = []
    for profile_name, limits in PROFILES.items():
        for scenario in EXPECTED:
            errors: list[str] = []
            try:
                result = run_v2_dry_run(scenario, limits=limits)
                contracts = result.get("task_contracts", [])
                evaluations = result.get("task_evaluations", [])
                valid_ids = {c["contract_id"] for c in contracts}
                decisions = result.get("decisions", [])
                if result.get("status") not in {"completed", "safe_stopped"}:
                    errors.append("UNEXPECTED_TERMINAL_STATUS")
                if result.get("operation_count", 10**9) > limits.max_operations:
                    errors.append("OPERATION_BUDGET_EXCEEDED")
                if result.get("global_backtracks", 10**9) > limits.global_backtracks:
                    errors.append("BACKTRACK_BUDGET_EXCEEDED")
                if result.get("report", {}).get("scientific_claim_verified") is not False:
                    errors.append("UNJUSTIFIED_SCIENTIFIC_CLAIM")
                if not decisions or not evaluations:
                    errors.append("MISSING_DECISION_OR_TASK_AUDIT")
                if any(e.get("contract_id") not in valid_ids for e in evaluations):
                    errors.append("EVALUATION_WITHOUT_ISSUED_CONTRACT")
                if any(e.get("scientific_quality_verified") is not False
                       for e in evaluations):
                    errors.append("SYNTHETIC_VALIDATION_PROMOTED")
                if any(d.get("verifier_veto_codes") and d.get("to") != "safe_stop"
                       for d in decisions):
                    errors.append("INDEPENDENT_VETO_BYPASSED")
                if scenario == "no_data_permission" and any(
                    d.get("to") == "competition" for d in decisions
                ):
                    errors.append("UNAUTHORIZED_COMPETITION")
                if scenario == "all_papers_rejected" and result.get("hypotheses"):
                    errors.append("HALLUCINATED_HYPOTHESES")
                operations = result.get("operation_count", 0)
                status = result.get("status", "unknown")
                audits = len(evaluations)
                if len(result.get("events", [])) < operations:
                    errors.append("MISSING_EXECUTION_EVENTS")
            except Exception as exc:
                # Never include model-facing content or traceback in artifact.
                errors.append("CONTROL_GRAPH_EXCEPTION_" + type(exc).__name__)
                operations, status, audits = 0, "error", 0
            cases.append({
                "profile": profile_name,
                "scenario": scenario,
                "status": status,
                "operations": operations,
                "task_evaluations": audits,
                "passed": not errors,
                "failure_codes": errors,
            })
    return {
        "benchmark": "v2_offline_architecture_stress",
        "source": "synthetic_scripted_no_real_papers",
        "paid_llm_calls": 0,
        "scientific_quality_evaluated": False,
        "profile_count": len(PROFILES),
        "scenario_count": len(EXPECTED),
        "case_count": len(cases),
        "passed_count": sum(c["passed"] for c in cases),
        "failed_count": sum(not c["passed"] for c in cases),
        "cases": cases,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        help="Optional JSON report path; no raw research content")
    args = parser.parse_args(argv)
    report = run_stress()
    serialized = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(json.dumps({
        k: v for k, v in report.items() if k != "cases"
    }, ensure_ascii=False))
    return int(report["failed_count"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
