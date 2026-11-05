"""Shared server-side Supabase REST authentication for modern and legacy keys.

2026 sb_secret_* keys are API gateway keys, NOT JWTs.
Never send them in Authorization: Bearer.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit


def supabase_url() -> str:
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("SUPABASE_URL must be a bare HTTPS project URL")
    return url


def supabase_key() -> str:
    key = (os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not key:
        raise ValueError("Missing SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY")
    if key.startswith("sb_publishable_") or key.startswith("eyJ") and key.count(".") != 2:
        raise ValueError("Invalid privileged Supabase key format")
    if not (key.startswith("sb_secret_") or (key.startswith("eyJ") and key.count(".") == 2)):
        raise ValueError("Use sb_secret_* or the legacy service_role JWT, not a public key")
    return key


def headers(*, prefer: str | None = None) -> dict[str, str]:
    key = supabase_key()
    values = {"apikey": key, "Content-Type": "application/json"}
    if not key.startswith("sb_secret_"):
        values["Authorization"] = "Bearer " + key
    if prefer:
        values["Prefer"] = prefer
    return values
