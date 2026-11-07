"""V0.2 frontier CLI: run autonomous laboratory or register *final* human feedback."""
from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from research_agent_lab.contracts import Snapshot
from research_agent_lab.model import BudgetedModel, DeepSeekJSONModel
from research_agent_lab.integrations import TracedModel
from research_agent_lab.response_cache import CachedModel, configured_cache

from .engine import FrontierConfig, run_frontier
from .memory import MemoryStore
from .mock import FrontierMockModel
from .storage import persist_frontier_run, check_frontier_supabase
from .remote_memory import hydrate_recent_memory
from .live_events import FrontierEventPublisher, check_frontier_event_store, safe_failure_code
from .bilingual_report import create_bilingual_report


def _read_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Profile-grounded, competition-driven, self-evolving research lab"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Run the four-layer supervisor-controlled research graph")
    run.add_argument("--snapshot", required=True, help="Public or approved metadata JSON")
    run.add_argument("--mock", action="store_true", help="Offline deterministic synthetic demonstration")
    run.add_argument("--discover", action="store_true", help="Opt-in: live OpenAlex search")
    run.add_argument("--source-registry", default="", help="Optional JSON list of allowed venues")
    run.add_argument("--max-generations", type=int, default=1)
    run.add_argument("--min-generations", type=int, default=0,
                     help="Required controlled evolution rounds, subject to hard model budget")
    run.add_argument("--synthetic-pilot", action="store_true",
                     help="Run fixed-code toy resilience sanity pilot when applicable")
    run.add_argument("--max-papers", type=int, default=12)
    run.add_argument("--max-pairs", type=int, default=3)
    run.add_argument("--pilot-manifest", default="", help="Optional local CSV pilot manifest")
    run.add_argument("--memory", default="outputs/frontier-memory.sqlite")
    run.add_argument("--out", default="", help="Output JSON; stdout if omitted")
    run.add_argument("--persist", action="store_true", help="Explicitly persist selected metadata to Supabase")
    run.add_argument("--bilingual-report", action="store_true",
                     help="One additional bounded model call for Chinese+English research summary")
    run.add_argument("--stream-progress", action="store_true",
                     help="Opt-in private per-node Supabase live events; requires SQL 007 and --persist")

    feedback = sub.add_parser("feedback", help="Record human review after final recommendation")
    feedback.add_argument("--memory", default="outputs/frontier-memory.sqlite")
    feedback.add_argument("--run-id", required=True)
    feedback.add_argument("--reviewer-tag", required=True)
    feedback.add_argument("--decision", choices=["accept", "revise", "reject"], required=True)
    feedback.add_argument("--novelty", type=int, required=True)
    feedback.add_argument("--feasibility", type=int, required=True)
    feedback.add_argument("--comment", default="")

    args = parser.parse_args(argv)
    try:
        memory = MemoryStore(args.memory)
        try:
            if args.command == "feedback":
                memory.add_feedback(
                    args.run_id, args.reviewer_tag, args.decision,
                    args.novelty, args.feasibility, args.comment
                )
                print("Stored human feedback for run " + args.run_id)
                return 0

            snapshot = Snapshot.model_validate(_read_json(args.snapshot))
            if args.discover and args.mock:
                raise ValueError("Real OpenAlex discovery cannot be combined with mock mode")
            if not args.mock and snapshot.provenance not in ("approved_export", "openalex_discovered"):
                raise ValueError("Live LLM runs require approved_export/openalex_discovered provenance")
            registry = None
            if args.source_registry:
                venues = _read_json(args.source_registry)
                if not isinstance(venues, list) or not venues or not all(
                    isinstance(v, str) and v.strip() for v in venues
                ):
                    raise ValueError("Source registry must be a nonempty JSON list of venue names")
                registry = {v.strip().casefold() for v in venues}
            pilot = _read_json(args.pilot_manifest) if args.pilot_manifest else None
            if args.stream_progress and not args.persist:
                raise ValueError("Private progress events require --persist")
            if args.persist:
                check_frontier_supabase()
                if args.stream_progress:
                    check_frontier_event_store()
                hydrate_recent_memory(memory, snapshot.research_line.id)
            underlying = FrontierMockModel() if args.mock else DeepSeekJSONModel()
            traced = TracedModel(underlying)
            cache = None
            publisher = None
            try:
                cache = (configured_cache(default_scope="research-team")
                         if not args.mock else None)
                active = CachedModel(traced, cache) if cache is not None else traced
                limit = int(os.getenv("MAX_MODEL_CALLS", "30"))
                reserve = int(os.getenv("MAX_RESERVED_TOKENS", "350000"))
                model = BudgetedModel(active, max_calls=limit,
                                      max_reserved_tokens=reserve)
                root_ctx = (
                    traced.client.start_as_current_observation(
                        name="research-frontier-run", as_type="span",
                        input={"snapshot_id": snapshot.snapshot_id,
                               "provenance": snapshot.provenance,
                               "max_generations": args.max_generations}
                    ) if traced.client is not None else nullcontext()
                )
                if args.stream_progress:
                    publisher = FrontierEventPublisher()
                    publisher.started()
                with root_ctx as trace_root:
                    result = run_frontier(
                        snapshot, model, memory,
                        FrontierConfig(
                            max_generations=args.max_generations,
                            minimum_generations=args.min_generations,
                            synthetic_pilot=args.synthetic_pilot,
                            max_papers=args.max_papers,
                            max_pairs_per_tournament=args.max_pairs,
                            discover=args.discover,
                        ),
                        source_allowlist=registry,
                        pilot_manifest=pilot,
                        event_sink=publisher.emit if publisher else None,
                        run_id=publisher.run_id if publisher else None,
                    )
                    if args.bilingual_report:
                        try:
                            result["bilingual_report"] = create_bilingual_report(result, model)
                        except (ValueError, RuntimeError, KeyError, TypeError):
                            # Editorial translation is optional and can never
                            # invalidate a completed, paid scientific experiment.
                            result["bilingual_report"] = {
                                "available": False,
                                "reason_code": "TRANSLATION_UNAVAILABLE",
                                "scientific_evidence_unchanged": True,
                            }
                        result["model_calls"] = model.usage.calls
                        result["provider_calls"] = model.usage.provider_calls
                        result["cache_hits"] = model.usage.cache_hits
                        result["actual_input_tokens"] = model.usage.input_tokens
                        result["actual_output_tokens"] = model.usage.output_tokens
                    if trace_root is not None:
                        trace_root.update(
                            output={"run_id": result["run_id"],
                                    "status": result["status"],
                                    "model_calls": result["model_calls"]}
                        )
                report = {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "mock": args.mock,
                    "warning": (
                        "SYNTHETIC MOCK: no literature/research assertions are real."
                        if args.mock else
                        "LLM judgments are not proof; human verification is required."
                    ),
                    **result,
                }
                if args.persist:
                    persist_frontier_run(result)
                if publisher:
                    publisher.finished()
                output = json.dumps(report, ensure_ascii=False, indent=2)
                if args.out:
                    path = Path(args.out)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(output + "\n", encoding="utf-8")
                    print("Saved " + str(path) + " (run_id=" + result["run_id"] + ")")
                else:
                    print(output)
                return 0
            except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
                if publisher is not None:
                    publisher.failed(safe_failure_code(exc))
                raise
            finally:
                if publisher is not None:
                    publisher.close()
                traced.close()
                if cache is not None:
                    cache.close()
        finally:
            memory.close()
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        print("Frontier Lab failed: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
