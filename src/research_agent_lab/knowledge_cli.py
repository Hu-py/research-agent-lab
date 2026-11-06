"""Trusted local CLI to inspect stored graph neighborhoods, or preview a graph.

Never run this command in public GitHub Actions if it prints private team nodes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from research_agent_lab.knowledge_graph import portrait_graph, problem_context
from research_agent_lab.knowledge_store import read_problem_neighborhood
from research_agent_lab.portrait import EvidenceBundle


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Research knowledge graph preview and inspection")
    sub = parser.add_subparsers(dest="command", required=True)
    preview = sub.add_parser("preview", help="Offline graph preview; no API calls")
    preview.add_argument("--evidence", required=True, help="Authorized evidence JSON")
    preview.add_argument("--portrait", required=True, help="Generated portrait report JSON")
    preview.add_argument("--line", default="", help="Optional research line ID")
    inspect = sub.add_parser("inspect", help="Read 1-hop graph neighborhood from Supabase")
    inspect.add_argument("--scope", required=True, help="Authorized bundle_id")
    inspect.add_argument("--line", required=True, help="Research line ID")
    try:
        args = parser.parse_args(argv)
        if args.command == "preview":
            bundle = EvidenceBundle.model_validate_json(
                Path(args.evidence).read_text(encoding="utf-8")
            )
            data = json.loads(Path(args.portrait).read_text(encoding="utf-8"))
            portrait = data.get("profile", data)
            batch = portrait_graph(bundle, portrait)
            summary = {"scope": batch.scope, "counts": batch.counts(),
                       "diagnostics": batch.diagnostics}
            if args.line:
                summary["neighborhood"] = problem_context(batch, args.line)
        else:
            summary = read_problem_neighborhood(args.scope, args.line)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        print("Knowledge graph error: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
