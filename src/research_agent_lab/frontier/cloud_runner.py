"""Explicit GitHub Actions entry point for bounded paid research experiments.

public_demo uses a generic public portrait, NOT the team's database profile.
approved_secret uses a reviewed JSON snapshot stored in a GitHub Secret; no
private artifacts or research details are printed to public workflow logs.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from research_agent_lab.contracts import Snapshot
from research_agent_lab.portrait import EvidenceBundle
from research_agent_lab.portrait_cli import main as portrait_main
from research_agent_lab.portrait_store import check_profile_store
from .storage import check_frontier_supabase
from research_agent_lab.supabase_auth import headers, supabase_url
from .cli import main as frontier_main


PUBLIC_PROFILE = Path(__file__).resolve().parents[3] / "examples" / "public_urban_profile.json"


def choose_snapshot(source: str, private_json: str | None = None, *,
                    directory: str | Path | None = None) -> tuple[Path, bool]:
    """Return (snapshot_path, remove_after_run). Never print source JSON."""
    if source == "public_demo":
        path = PUBLIC_PROFILE
        snapshot = Snapshot.model_validate_json(path.read_text(encoding="utf-8"))
        if snapshot.provenance != "public_demo_profile":
            raise ValueError("Public profile must use public_demo_profile provenance")
        return path, False
    if source != "approved_secret":
        raise ValueError("Unsupported evidence source")
    if not private_json:
        raise ValueError("Missing RESEARCH_SNAPSHOT_JSON secret for approved_secret mode")
    snapshot = Snapshot.model_validate_json(private_json)
    if snapshot.provenance != "approved_export":
        raise ValueError("Secret snapshot provenance must be approved_export")
    if any(dataset.sensitivity != "public" for dataset in snapshot.datasets):
        raise ValueError("Cloud run only accepts public-safe dataset metadata")
    directory_path = Path(directory) if directory else Path(tempfile.gettempdir())
    directory_path.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", prefix="approved-research-",
        suffix=".json", dir=directory_path, delete=False
    ) as temp:
        temp.write(snapshot.model_dump_json())
        path = Path(temp.name)
    path.chmod(0o600)
    return path, True


def _choice(name: str, allowed: set[str]) -> str:
    value = os.getenv(name, "").strip()
    if value not in allowed:
        raise ValueError("Invalid workflow input: " + name)
    return value


def validate_cloud_config(*, persist: bool) -> None:
    required = ("DEEPSEEK_API_KEY", "OPENALEX_API_KEY",
                "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise ValueError("GitHub Secrets missing: " + ", ".join(missing))
    if persist:
        # SQL/network preflight happens in CLI, BEFORE any LLM calls.
        supabase_url()
        headers()


def main() -> int:
    private_path: Path | None = None
    try:
        evidence = _choice("EVIDENCE_SOURCE", {"public_demo", "approved_secret", "team_evidence"})
        generations = _choice("MAX_GENERATIONS_INPUT", {"0", "1"})
        papers = _choice("MAX_PAPERS_INPUT", {"4", "6", "8"})
        pairs = _choice("MAX_PAIRS_INPUT", {"1", "2", "3"})
        persist = _choice("SAVE_SUPABASE", {"true", "false"}) == "true"
        validate_cloud_config(persist=persist)
        if evidence == "team_evidence":
            if not persist:
                raise ValueError("team_evidence requires save_supabase=true for versioned memory")
            raw = os.getenv("TEAM_EVIDENCE_JSON") or ""
            if not raw:
                raise ValueError("Missing TEAM_EVIDENCE_JSON GitHub Secret")
            bundle = EvidenceBundle.model_validate_json(raw)
            # Validate BOTH destination tables prior to charging the model.
            check_profile_store()
            check_frontier_supabase()
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", prefix="team-evidence-",
                suffix=".json",
                dir=os.getenv("RUNNER_TEMP") or tempfile.gettempdir(),
                delete=False
            ) as source_file:
                source_file.write(bundle.model_dump_json())
                private_path = Path(source_file.name)
            private_path.chmod(0o600)
            private_snapshot = Path("outputs/derived-team-snapshot-private.json")
            status = portrait_main([
                "--evidence", str(private_path),
                "--out", "outputs/team-portrait-private.json",
                "--snapshot-out", str(private_snapshot),
                "--persist"
            ])
            if status != 0:
                return status
            path = private_snapshot
        else:
            path, ephemeral = choose_snapshot(
                evidence, os.getenv("RESEARCH_SNAPSHOT_JSON"),
                directory=os.getenv("RUNNER_TEMP") or tempfile.gettempdir()
            )
            if ephemeral:
                private_path = path
        output_path = Path("outputs") / (
            "live-frontier-public.json" if evidence == "public_demo"
            else "live-frontier-private.json"
        )
        args = [
            "run", "--snapshot", str(path), "--discover",
            "--max-generations", generations,
            "--max-papers", papers,
            "--max-pairs", pairs,
            "--out", str(output_path),
        ]
        if persist:
            args.append("--persist")
        status = frontier_main(args)
        if status != 0:
            return status
        result = json.loads(output_path.read_text(encoding="utf-8"))
        print(
            "Completed: run_id=" + str(result["run_id"]) +
            " status=" + str(result["status"]) +
            " generations=" + str(result["generation_count"]) +
            " model_calls=" + str(result["model_calls"])
        )
        print("Langfuse: open the Tracing page to inspect redacted agent calls.")
        if persist:
            print("Supabase: result written to public.lab_frontier_runs.")
        summary_path = os.getenv("GITHUB_STEP_SUMMARY")
        if summary_path:
            lines = [
                "### Live Frontier Experiment",
                "",
                "- Run ID: " + str(result["run_id"]),
                "- Source: " + evidence,
                "- Model calls: " + str(result["model_calls"]),
                "- Generations: " + str(result["generation_count"]),
                "- Status: " + str(result["status"]),
                "",
                "Note: LLM ideation does not certify novelty or scientific accuracy.",
                "",
            ]
            with open(summary_path, "a", encoding="utf-8") as handle:
                handle.write("\n".join(lines))
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        # Avoid printing configured secrets, full prompts or private snapshots.
        message = str(exc)
        print("Cloud workflow error: " + message[:450], file=sys.stderr)
        return 2
    finally:
        if private_path:
            private_path.unlink(missing_ok=True)
            Path("outputs/live-frontier-private.json").unlink(missing_ok=True)
        for private_output in (
            "outputs/derived-team-snapshot-private.json",
            "outputs/team-portrait-private.json",
        ):
            Path(private_output).unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
