"""Evidence-led portrait recalibration with optional version persistence.

CLI returns a selected Snapshot to the existing frontier research workflow.
Actual team metadata must be exported with explicit user authorization.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

from research_agent_lab.model import BudgetedModel, DeepSeekJSONModel
from research_agent_lab.integrations import TracedModel
from research_agent_lab.portrait import (
    EvidenceBundle, evidence_hash, synthesize_portrait, snapshot_for_line,
    PortraitStageError,
)
from research_agent_lab.portrait_store import (
    check_profile_store, latest_portrait, persist_portrait,
)
from research_agent_lab.knowledge_graph import (
    portrait_graph, problem_context,
)
from research_agent_lab.knowledge_store import (
    check_graph_store, persist_graph,
)

SELECTION_SYSTEM = (
    "You are a scientific research portfolio planner. Choose an evidence-grounded "
    "research line for the NEXT bounded hypothesis discovery run. "
    "Prioritize unfinished questions and meaningful opportunities given recorded "
    "past work, not mere keyword frequency. Do not invent capabilities. JSON only."
)


def select_research_line(portrait: dict, model: BudgetedModel,
                         *, knowledge_context: list[dict] | None = None) -> dict:
    lines = portrait.get("research_lines", [])
    if not lines:
        raise ValueError("No eligible research lines")
    raw = model.complete(
        role="research_line_selector", system=SELECTION_SYSTEM,
        payload={
            "lines": lines,
            "knowledge_context": (knowledge_context or [])[:8],
            "task": "Choose one line_id from provided research lines. Return "
                    "line_id, reason (nonempty), and next_test (nonempty)."
        },
    )
    line_id = raw.get("line_id")
    if line_id not in {x["id"] for x in lines}:
        raise ValueError("Selector referenced an unknown research line")
    for key in ("reason", "next_test"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            raise ValueError("Missing selector reasoning: " + key)
    return {"line_id": line_id, "reason": raw["reason"][:600],
            "next_test": raw["next_test"][:700]}


def generate(bundle: EvidenceBundle, model: BudgetedModel,
             *, use_remote_store: bool, refresh: bool = False,
             target_line: str | None = None) -> tuple[dict, object]:
    original_hash = evidence_hash(bundle)
    previous = latest_portrait(bundle.bundle_id) if use_remote_store else None
    unchanged = previous is not None and previous.get("evidence_hash") == original_hash

    if unchanged and not refresh:
        portrait = previous.get("portrait")
        if not isinstance(portrait, dict) or not portrait.get("research_lines"):
            raise ValueError("Cached profile malformed")
        source = "cached_same_evidence"
        profile_record = {"version": previous.get("version"), "id": previous.get("id")}
    else:
        # Old officially registered profile is fallible. When the lab has an
        # earlier evidence-grounded version, use it for a DIFF, not as a rule.
        if previous and isinstance(previous.get("portrait"), dict):
            updated = bundle.model_copy(
                update={"old_profile": previous["portrait"]}
            )
        else:
            updated = bundle
        portrait = synthesize_portrait(updated, model)
        # The hash records ORIGINAL evidence and is stable across version changes.
        portrait["source_evidence_hash"] = original_hash
        source = "regenerated_from_evidence"
        profile_record = (
            persist_portrait(bundle.bundle_id, original_hash, portrait, previous)
            if use_remote_store else {"version": None, "id": None}
        )

    # Explicit graph neighborhoods, not an ungrounded bag of keywords.
    # This pass is local/pure, so it runs without Supabase configured.
    graph = portrait_graph(bundle, portrait)
    candidates_context = [
        problem_context(graph, item["id"], limit=12)
        for item in portrait["research_lines"]
    ]

    if target_line:
        if target_line not in {l["id"] for l in portrait["research_lines"]}:
            raise ValueError("Selected line is absent from new portrait")
        selected = {"line_id": target_line, "reason": "Operator-selected valid line",
                    "next_test": "Evidence-linked scientific discovery"}
    else:
        selected = select_research_line(
            portrait, model, knowledge_context=candidates_context
        )

    snapshot = snapshot_for_line(bundle, portrait, selected["line_id"])
    selected_context = next(x for x in candidates_context
                            if x["problem"]["id"] ==
                            "research_problem:" + selected["line_id"])
    compact = [
        x["relation"] + " " + x["target"] + " (" + x["status"] + ")"
        for x in selected_context["relationships"][:9]
    ]
    if compact:
        goals = (snapshot.research_line.goals +
                 "\nProvisional knowledge graph links: " + "; ".join(compact))[:1000]
        snapshot = snapshot.model_copy(update={
            "research_line": snapshot.research_line.model_copy(update={"goals": goals})
        })
    return {
        "profile": portrait,
        "recalibration": source,
        "profile_record": profile_record,
        "selection": selected,
        "source_evidence_hash": original_hash,
        "input_counts": portrait.get("input_counts") or {
            "verified_team_outputs": len(bundle.achievements),
            "public_dataset_metadata": len(bundle.datasets),
            "external_papers": len(bundle.external_papers),
        },
        "official_team_profile_modified": False,
        "knowledge_graph_preview": {
            "counts": graph.counts(),
            "selected_problem": selected_context,
            "scope": bundle.bundle_id,
            "materialized": False,
        },
    }, snapshot


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Evidence-grounded team research portrait")
    parser.add_argument("--evidence", required=True, help="Authorized JSON export")
    parser.add_argument("--out", required=True, help="Private local profile report")
    parser.add_argument("--snapshot-out", required=True, help="Private frontier snapshot")
    parser.add_argument("--persist", action="store_true", help="Save version in isolated Supabase")
    parser.add_argument("--persist-graph", action="store_true",
                        help="Also materialize evidence links in kg_* (requires SQL 004)")
    parser.add_argument("--refresh", action="store_true", help="Re-review unchanged evidence")
    parser.add_argument("--line-id", default="", help="Optional validated specific line")
    args = parser.parse_args(argv)

    try:
        bundle = EvidenceBundle.model_validate_json(Path(args.evidence).read_text(encoding="utf-8"))
        if args.persist_graph and not args.persist:
            raise ValueError("--persist-graph also requires --persist")
        if args.persist:
            check_profile_store()
        if args.persist_graph:
            check_graph_store()
        # Independent bounded budget so portrait cannot monopolize the later
        # scientific tournament. Total run costs are the sum of both stages.
        # 36+ source records and complete ID coverage often exceed the generic
        # 2,200-token hypothesis limit. This applies ONLY to portrait calls.
        underlying = DeepSeekJSONModel(max_output_tokens=6000)
        traced = TracedModel(underlying)
        try:
            model = BudgetedModel(traced, max_calls=9, max_reserved_tokens=65000)
            report, snapshot = generate(
                bundle, model, use_remote_store=args.persist,
                refresh=args.refresh, target_line=args.line_id or None
            )
        finally:
            traced.close()
        if args.persist_graph:
            batch = portrait_graph(
                bundle, report["profile"],
                profile_version_id=report["profile_record"]["id"]
            )
            counts = persist_graph(batch)
            report["knowledge_graph_preview"]["counts"] = counts
            report["knowledge_graph_preview"]["materialized"] = True
        for path, content in (
            (Path(args.out), report),
            (Path(args.snapshot_out), snapshot.model_dump(mode="json")),
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            path.chmod(0o600)
        print(
            f"Evidence-based portrait ready; "
            f"line_count={len(report['profile']['research_lines'])} "
            f"line_selected={report['selection']['line_id']} "
            f"version={report['profile_record']['version'] or 'local'}"
        )
        return 0
    except (ValueError, OSError, RuntimeError, TypeError, KeyError) as exc:
        # Never expose team titles, IDs, prompts, raw model JSON or credentials
        # in a public GitHub Actions log.
        if isinstance(exc, PortraitStageError):
            stage, code = exc.stage, exc.code
        elif isinstance(exc, ValueError):
            stage, code = "input_or_selection", "INVALID_GENERATED_INPUT"
        elif isinstance(exc, RuntimeError):
            stage, code = "model_or_store", "MODEL_OR_STORAGE_FAILURE"
        else:
            stage, code = "io", "PORTRAIT_RUNTIME_ERROR"
        print(
            "Portrait synthesis error: stage=" + stage + " code=" + code +
            "; no private source content logged", file=sys.stderr
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
