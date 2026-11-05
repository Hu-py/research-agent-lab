"""Versioned, non-authoritative portrait records in isolated Supabase.

No source paper abstracts or raw datasets are stored. The official workbench
profile is NOT updated; all records are provisional research-lab evaluations.
"""
from __future__ import annotations

import json
import httpx

from research_agent_lab.supabase_auth import headers, supabase_url


def _get(client: httpx.Client, *, bundle_id: str, max_versions: int = 1) -> list[dict]:
    resp = client.get(
        supabase_url() + "/rest/v1/lab_profile_versions",
        headers=headers(),
        params={"select": "id,bundle_id,evidence_hash,version,portrait,created_at",
                "bundle_id": "eq." + bundle_id, "order": "version.desc",
                "limit": str(max(1, min(5, max_versions)))}
    )
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"Profile version table cannot be read (HTTP {exc.response.status_code})") from None
    result = resp.json()
    if not isinstance(result, list):
        raise RuntimeError("Profile versions query returned unexpected data")
    return result


def latest_portrait(bundle_id: str) -> dict | None:
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        result = _get(client, bundle_id=bundle_id)
        return result[0] if result else None


def persist_portrait(bundle_id: str, source_hash: str, portrait: dict,
                     last: dict | None) -> dict:
    """Save compact capability claims and provenance, never the raw evidence bundle."""
    version = int((last or {}).get("version") or 0) + 1
    payload = {
        "bundle_id": bundle_id,
        "evidence_hash": source_hash,
        "version": version,
        "status": "provisional_not_official",
        "portrait": portrait,
        "delta": {"changes_from_previous": portrait.get("changes_from_previous", [])},
    }
    with httpx.Client(timeout=25, follow_redirects=False) as client:
        response = client.post(
            supabase_url() + "/rest/v1/lab_profile_versions",
            headers=headers(prefer="return=representation"),
            json=payload,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"Profile version save HTTP {exc.response.status_code}; "
                "check sql/003_profile_versions.sql"
            ) from None
        data = response.json()
        if not isinstance(data, list) or len(data) != 1:
            raise RuntimeError("Profile version insert response invalid")
        return {"id": data[0]["id"], "version": version}


def check_profile_store() -> None:
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        _get(client, bundle_id="__preflight__")
