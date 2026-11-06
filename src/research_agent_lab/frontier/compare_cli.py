"""CLI for two saved lab runs; no AI calls, no public research-artifact upload."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from research_agent_lab.frontier.audit import compare_runs, read_run


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="Research Agent Lab read-only A/B audit")
    p.add_argument("--baseline-id", required=True)
    p.add_argument("--treatment-id", required=True)
    p.add_argument("--out", default="")
    args = p.parse_args(argv)
    try:
        base = read_run(args.baseline_id)
        treat = read_run(args.treatment_id)
        result = compare_runs(base, treat)
        if args.out:
            path = Path(args.out)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            path.chmod(0o600)
        # Only emit IDs and aggregate diagnostics to public GitHub logs.
        print("Comparison status=" + result["comparability"] +
              " blocking_codes=" + ",".join(result["blocking_reasons"]) +
              " baseline_candidates=" + str(result["baseline"]["candidate_versions"]) +
              " treatment_candidates=" + str(result["treatment"]["candidate_versions"]))
        return 0
    except (ValueError, RuntimeError, OSError, TypeError, KeyError) as exc:
        print("Research A/B audit failed: " + str(exc)[:200], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
