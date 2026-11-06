"""Prepare a minimal owner-approved metadata JSON for private GitHub Secret.

Run locally only; the PRIVATE review inventory is never added to the repo.
This exporter never forwards original_description, custodians, disk paths or
unapproved entries. A human/data-owner must opt in at root AND per record.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_agent_lab.catalog_bridge import (
    approved_catalog_assets, approved_catalog_from_json
)


def export_minimal_approved(manifest: dict) -> dict:
    approved = approved_catalog_assets(manifest)
    by_id = {x["id"]: x for x in manifest["assets"]
             if isinstance(x, dict) and x.get("metadata_sharing_approved") is True}
    return {
        "schema_version": 1,
        "approved_by_data_owner": True,
        "assets": [
            {
                "id": d.id, "name": d.name, "category": d.category,
                "coverage": d.coverage, "period": d.period,
                "risk_class": by_id[d.id]["risk_class"],
                "approved_description": d.description,
                "approved_prior_research": d.prior_research,
                "metadata_sharing_approved": True,
                "verified_field_list": bool(d.fields),
                "verified_fields": d.fields,
                "access_verified": False
            }
            for d in approved
        ]
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create minimal private catalog Secret")
    parser.add_argument("--review", required=True, help="private reviewed JSON path")
    parser.add_argument("--out", required=True, help="private sanitized JSON path")
    args = parser.parse_args(argv)
    raw = Path(args.review).read_text(encoding="utf-8")
    data = approved_catalog_from_json(raw)
    output = export_minimal_approved(data)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False,
                                 separators=(",", ":")), encoding="utf-8")
    target.chmod(0o600)
    print("Metadata Secret generated: approved_assets="
          + str(len(output["assets"])) + "; no original descriptions or raw rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
