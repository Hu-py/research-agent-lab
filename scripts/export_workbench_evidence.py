#!/usr/bin/env python3
"""Authorized read-only metadata exporter for the *original* workbench DB.

Run only in an environment that ALREADY has read permission to its PostgreSQL
DATABASE_URL and source repository installed/importable. The public GitHub
runner cannot and must not access a protected database automatically.

Default output is NOT sharing-approved; operator explicitly reviews the file
and passes --approve-public-safe-export for DeepSeek/cloud use.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only team evidence export")
    parser.add_argument("--source-repo", required=True, help="Existing workbench checkout")
    parser.add_argument("--out", required=True, help="Private local JSON output")
    parser.add_argument("--bundle-id", default="research-team", help="Stable identity for profile versions")
    parser.add_argument("--approve-public-safe-export", action="store_true",
                        help="Explicitly approve exported metadata for cloud/LLM sharing")
    parser.add_argument("--limit-achievements", type=int, default=40)
    parser.add_argument("--limit-datasets", type=int, default=25)
    parser.add_argument("--limit-external", type=int, default=20)
    parser.add_argument("--include-approved-internal-metadata", action="store_true",
                        help="Explicit opt-in: share allowed internal DATASET METADATA, never raw data")
    parser.add_argument("--internal-allowlist", default="",
                        help="Private JSON list of individually approved internal dataset IDs")
    args = parser.parse_args(argv)
    if not os.getenv("DATABASE_URL"):
        parser.error("Set DATABASE_URL in authorized original-workbench environment")
    root = Path(args.source_repo).resolve()
    if not (root / "backend" / "profile_database.py").is_file():
        parser.error("source-repo must be the original Research Opportunity Workbench checkout")
    if args.include_approved_internal_metadata and not args.approve_public_safe_export:
        parser.error("Internal metadata requires --approve-public-safe-export")
    approved_internal_ids = set()
    if args.include_approved_internal_metadata:
        if not args.internal_allowlist:
            parser.error("Internal metadata requires --internal-allowlist")
        allowed = json.loads(Path(args.internal_allowlist).read_text(encoding="utf-8"))
        if not isinstance(allowed, list) or not allowed or not all(
            isinstance(x, str) and x for x in allowed
        ):
            parser.error("Internal allowlist must be a nonempty JSON list of IDs")
        approved_internal_ids = set(allowed)
    if not 1 <= args.limit_achievements <= 100 or not 0 <= args.limit_datasets <= 100:
        parser.error("Source limits out of bounds")
    sys.path.insert(0, str(root))
    from sqlalchemy import create_engine, select, or_, and_
    from sqlalchemy.orm import Session
    from backend.profile_database import evidence_inventory
    from backend.repository import TeamAchievement
    from backend.cusp import CuspDataset, sensitive_level
    from research_workbench.core import Paper
    from research_agent_lab.portrait import EvidenceBundle

    # Do NOT use session_factory(): the original factory may call create_all()
    # and seed entries. This tool should never create or modify tables.
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    try:
        with Session(engine, autoflush=False) as session:
            inventory = evidence_inventory(session)
            verified_ids = {row["id"] for row in inventory["team_achievements"]}
            achievement_rows = session.scalars(
                select(TeamAchievement).where(TeamAchievement.status == "verified")
                .order_by(TeamAchievement.year.desc(), TeamAchievement.title)
                .limit(args.limit_achievements)
            ).all()
            achievements = [
                {
                    "id": obj.id, "title": obj.title[:400],
                    "year": obj.year, "kind": obj.kind,
                    "tags": json.loads(obj.tags_json or "[]")[:20],
                    "abstract": "", "doi": obj.doi[:200],
                    "venue": obj.venue[:200],
                    "evidence_level": "title_only",
                    "ownership": "verified_team_output"
                }
                for obj in achievement_rows if obj.id in verified_ids
            ]
            allowed_filter = (
                or_(
                    CuspDataset.sensitivity == "public",
                    and_(CuspDataset.sensitivity == "internal",
                         CuspDataset.id.in_(approved_internal_ids))
                ) if approved_internal_ids else (CuspDataset.sensitivity == "public")
            )
            public_assets = session.scalars(
                select(CuspDataset).where(allowed_filter)
                .order_by(CuspDataset.category, CuspDataset.name)
                .limit(args.limit_datasets)
            ).all()
            assets = [
                {
                    "id": item.id, "name": item.name[:200],
                    "category": item.category[:100],
                    "description": item.description[:1300],
                    "prior_research": item.prior_research[:1200],
                    "coverage": item.coverage[:300],
                    "period": item.period[:200],
                    "fields": [],  # Original CUSP catalogue does not verify fields.
                    "sensitivity": (
                        "internal_metadata_approved"
                        if item.sensitivity == "internal" else "public"
                    ),
                    "metadata_sharing_approved": (
                        args.approve_public_safe_export and item.sensitivity == "internal"
                    ),
                    "access_verified": False,
                }
                for item in public_assets
                if sensitive_level(item.name) != "restricted"
            ]
            external = []
            for row in inventory["approved_papers"][:args.limit_external]:
                paper = session.get(Paper, row["id"])
                if paper:
                    external.append({
                        "id": paper.id[:140], "title": paper.title[:400],
                        "abstract": (paper.abstract or "")[:3000],
                        "doi": (paper.doi or "")[:200],
                        "venue": (paper.venue or "")[:200],
                        "ownership": "external_literature"
                    })
            payload = {
                "bundle_id": args.bundle_id,
                "source": "authorized_database_export",
                "sharing_approved": args.approve_public_safe_export,
                "achievements": achievements,
                "datasets": assets,
                "external_papers": external,
                "old_profile": inventory.get("profile") or {},
            }
            if args.approve_public_safe_export:
                EvidenceBundle.model_validate(payload)
            path = Path(args.out).expanduser().resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            path.chmod(0o600)
            print(json.dumps({
                "export_status": (
                    "explicitly_approved_public_metadata" if args.approve_public_safe_export
                    else "not_approved_for_llm"
                ),
                "achievements": len(achievements),
                "public_datasets": len(assets),
                "external_approved_papers": len(external),
                "source_datasets_omitted_if_internal_or_restricted": (
                    not args.include_approved_internal_metadata
                ),
                "raw_data_or_paths_exported": False,
                "original_db_modified": False,
                "path": str(path),
            }, ensure_ascii=False))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
