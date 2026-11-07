"""Free, offline architecture rehearsal for V2 nested LangGraph.

Usage: python -m research_agent_lab.frontier.v2.cli --scenario all_papers_rejected
No API keys, DeepSeek, OpenAlex, Supabase or real dataset reads.
"""
from __future__ import annotations
import argparse
import json
from .driver import ScriptedResearchDriver
from .graph import run_v2_dry_run
from .state import V2Limits

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline multi-loop V2 architecture proof")
    parser.add_argument("--scenario", choices=sorted(ScriptedResearchDriver.SCENARIOS),
                        default="happy_path")
    parser.add_argument("--max-operations", type=int, default=48)
    parser.add_argument("--max-backtracks", type=int, default=3)
    parser.add_argument("--events", action="store_true",
                        help="Show only sanitized node completion and routing events")
    parser.add_argument("--task-audit", action="store_true",
                        help="Show controller-issued contracts, independent task "
                             "evaluations and active defect repair plans")
    args = parser.parse_args(argv)
    limits = V2Limits(max_operations=args.max_operations,
                      global_backtracks=args.max_backtracks)
    state = run_v2_dry_run(args.scenario, limits=limits)
    report = {
        "architecture": "nested_langgraph_v2",
        "execution_mode": "synthetic_offline_no_paid_ai",
        "scenario": args.scenario,
        "status": state["status"],
        "report": state["report"],
        "supervisor_decisions": state["decisions"],
        "decision_feedback": state.get("decision_feedback", []),
        "policy_audit": state.get("policy_audit", {}),
        "node_count": len(state["events"]),
    }
    if args.events:
        report["node_events"] = state["events"]
    if args.task_audit:
        report["task_contracts"] = state.get("task_contracts", [])
        report["task_evaluations"] = state.get("task_evaluations", [])
        report["last_repair_plan"] = state.get("repair_plan", {})
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if state["status"] in ("completed", "safe_stopped") else 1

if __name__ == "__main__":
    raise SystemExit(main())
