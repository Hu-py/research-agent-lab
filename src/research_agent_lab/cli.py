"""Local run entrypoint. No network or API key is required in --mock mode."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from pydantic import ValidationError

from .contracts import Snapshot
from .model import BudgetedModel, DeepSeekJSONModel, MockJSONModel
from .workflow import run_experiment
from .integrations import TracedModel, persist_run_to_supabase


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Reproducible multi-agent research hypothesis experiments")
    parser.add_argument("--snapshot", required=True, help="Approved JSON evidence snapshot")
    parser.add_argument("--mode", choices=["single", "fixed", "adaptive", "all"], default="adaptive")
    parser.add_argument("--mock", action="store_true", help="Deterministic wiring-only demo, NOT research")
    parser.add_argument("--persist", action="store_true", help="Explicitly write results into isolated lab_runs")
    parser.add_argument("--max-rounds", type=int, default=3)
    parser.add_argument("--target-score", type=float, default=80.0)
    parser.add_argument("--out", default="", help="Output JSON file (defaults to stdout)")
    args = parser.parse_args(argv)
    source = Path(args.snapshot)
    try:
        snapshot = Snapshot.model_validate_json(source.read_text(encoding="utf-8"))
        max_calls = int(os.getenv("MAX_MODEL_CALLS", "30"))
        max_reserved_tokens = int(os.getenv("MAX_RESERVED_TOKENS", "350000"))
        max_papers = int(os.getenv("MAX_PAPERS_PER_RUN", "16"))
        if min(max_calls, max_reserved_tokens, max_papers) <= 0:
            raise ValueError("All budgets must be positive")
        if not args.mock and snapshot.provenance == "synthetic_demo":
            raise ValueError("Real LLM calls require an approved_export evidence snapshot")
        modes = ["single", "fixed", "adaptive"] if args.mode == "all" else [args.mode]
        result = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mock": args.mock,
            "warning": ("MOCK ONLY: algorithm wiring; no scientific claims validated."
                        if args.mock else "LLM-generated hypotheses require human scientific verification."),
            "runs": [],
        }
        for mode in modes:
            underlying = MockJSONModel() if args.mock else DeepSeekJSONModel()
            traced = TracedModel(underlying)
            try:
                model = BudgetedModel(underlying=traced, max_calls=max_calls,
                                    max_reserved_tokens=max_reserved_tokens)
                run = run_experiment(snapshot, mode, model, max_rounds=args.max_rounds,
                                     max_papers=max_papers, target_score=args.target_score)
                result["runs"].append(run)
                if args.persist:
                    persist_run_to_supabase(run)
            finally:
                traced.close()
        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.out:
            target = Path(args.out)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text + "\n", encoding="utf-8")
            print("Saved " + str(target))
        else:
            print(text)
        return 0
    except (ValueError, RuntimeError, ValidationError, OSError) as exc:
        print("Run failed: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
