"""Data-owner-reviewed CUSP catalog metadata bridge.

Never read or upload raw CSV/SHP/traces or custodians. The spreadsheet review
record itself is PRIVATE and may contain unsanitized descriptions, so it is
never accepted as the cloud upload format. This module emits ONLY explicitly
approved, independently edited summary fields, not original descriptions.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError
from research_agent_lab.portrait import DataAsset, EvidenceBundle


def approved_catalog_assets(manifest: dict) -> list[DataAsset]:
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("CATALOG_SCHEMA: expected review schema v1")
    if manifest.get("approved_by_data_owner") is not True:
        raise ValueError("CATALOG_OWNER_APPROVAL_REQUIRED")
    source = manifest.get("assets")
    if not isinstance(source, list) or not source or len(source) > 100:
        raise ValueError("CATALOG_ASSETS_INVALID")
    out: list[DataAsset] = []
    seen: set[str] = set()
    for item in source:
        if not isinstance(item, dict):
            raise ValueError("CATALOG_INVALID_ROW")
        if item.get("metadata_sharing_approved") is not True:
            continue
        asset_id = item.get("id")
        if not isinstance(asset_id, str) or not asset_id.startswith("cusp_"):
            raise ValueError("CATALOG_INVALID_ASSET_ID")
        if asset_id in seen:
            raise ValueError("CATALOG_DUPLICATE_APPROVED_ID")
        seen.add(asset_id)
        # High-risk entries require a separately prepared short, approved
        # summary and must not use the original description/field details.
        risk = item.get("risk_class")
        if risk not in ("high_review", "standard_review"):
            raise ValueError("CATALOG_RISK_REVIEW_MISSING")
        approved_description = item.get("approved_description", "")
        approved_research = item.get("approved_prior_research", "")
        if not isinstance(approved_description, str) or not isinstance(approved_research, str):
            raise ValueError("CATALOG_APPROVED_TEXT_INVALID")
        if risk == "high_review" and not approved_description.strip():
            raise ValueError("CATALOG_HIGH_RISK_SUMMARY_REQUIRED")
        # No generated or inferred field names: only separately verified list
        # can enter the evidence model; default metadata-only fields=[].
        fields = item.get("verified_fields", [])
        if not isinstance(fields, list) or not all(
            isinstance(f, str) and f.strip() and len(f) <= 100 for f in fields
        ):
            raise ValueError("CATALOG_VERIFIED_FIELDS_INVALID")
        if risk == "high_review" and fields:
            raise ValueError("CATALOG_HIGH_RISK_FIELD_NAMES_EXCLUDED")
        if fields and item.get("verified_field_list") is not True:
            raise ValueError("CATALOG_FIELD_VERIFICATION_REQUIRED")
        if item.get("access_verified") is True:
            # A spreadsheet F-drive checkmark is not legal permission to use
            # data; this contract intentionally cannot confer access.
            raise ValueError("CATALOG_ACCESS_MUST_REMAIN_UNVERIFIED")
        payload = {
            "id": asset_id,
            "name": item.get("name", ""),
            "category": item.get("category", ""),
            "coverage": str(item.get("coverage") or "")[:300],
            "period": str(item.get("period") or "")[:200],
            "description": approved_description[:1000],
            "prior_research": approved_research[:1000],
            "fields": list(dict.fromkeys(fields)),
            "sensitivity": "internal_metadata_approved",
            "metadata_sharing_approved": True,
            "access_verified": False,
        }
        try:
            out.append(DataAsset.model_validate(payload))
        except ValidationError:
            raise ValueError("CATALOG_APPROVED_ASSET_INVALID") from None
    if not out:
        raise ValueError("CATALOG_NO_APPROVED_ASSETS")
    return out


def merge_approved_catalog(bundle: EvidenceBundle, manifest: dict) -> tuple[EvidenceBundle, dict]:
    """Merge only approved metadata into owned evidence, preserving prior refs."""
    approved = approved_catalog_assets(manifest)
    existing_ids = {a.id for a in bundle.achievements}
    existing_ids |= {x.id for x in bundle.external_papers}
    current_assets = list(bundle.datasets)
    seen_names = {d.name.strip().casefold() for d in current_assets}
    added = []
    name_duplicates = 0
    for item in approved:
        if item.id in existing_ids:
            raise ValueError("CATALOG_ID_COLLIDES_WITH_PAPER_OR_OUTPUT")
        if item.id in {x.id for x in current_assets}:
            raise ValueError("CATALOG_ID_COLLIDES_WITH_EXISTING_DATASET")
        key = item.name.strip().casefold()
        if key in seen_names:
            name_duplicates += 1
            continue
        seen_names.add(key)
        current_assets.append(item)
        added.append(item.id)
    updated = bundle.model_copy(update={"datasets": current_assets})
    # Important: model_copy does not re-validate mutable inner collections.
    validated = EvidenceBundle.model_validate(updated.model_dump(mode="json"))
    return validated, {
        "approved_catalog_metadata": len(approved),
        "newly_added_metadata": len(added),
        "existing_name_duplicates_skipped": name_duplicates,
        "data_access_verified": False,
        "raw_data_files_uploaded": False,
    }


def approved_catalog_from_json(raw_json: str) -> dict:
    try:
        content = json.loads(raw_json)
    except json.JSONDecodeError:
        raise ValueError("CATALOG_NOT_VALID_JSON") from None
    if not isinstance(content, dict):
        raise ValueError("CATALOG_JSON_MUST_BE_OBJECT")
    return content
