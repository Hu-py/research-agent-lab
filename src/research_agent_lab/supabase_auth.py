"""Shared server-side Supabase REST authentication for modern and legacy keys.

2026 sb_secret_* keys are API gateway keys, NOT JWTs.
Never send them in Authorization: Bearer.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit


def supabase_url() -> str:
    raw = os.getenv("SUPABASE_URL", "")
    url = raw.strip().rstrip("/")
    if not url:
        raise ValueError(
            "SUPABASE_URL_NOT_SET: GitHub Actions did not receive a project URL. "
            "Add SUPABASE_URL under repository Actions Secrets or Variables."
        )
    # Classify errors without ever printing the provided URL, hostname,
    # database password, user name, query string, or token.
    parsed = urlsplit(url)
    if parsed.scheme in ("postgresql", "postgres", "postgresql+psycopg2"):
        raise ValueError(
            "SUPABASE_URL_IS_DATABASE_URI: paste the HTTPS Project URL from "
            "Supabase Settings > Data API, not the PostgreSQL connection string."
        )
    if parsed.hostname in ("supabase.com", "www.supabase.com"):
        raise ValueError(
            "SUPABASE_URL_IS_DASHBOARD: paste the project's HTTPS API URL "
            "(https://<project-ref>.supabase.co), not a dashboard link."
        )
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(
            "SUPABASE_URL_NOT_HTTPS: expected an HTTPS project API URL; "
            "check that the configured value has no quotes or placeholders."
        )
    if (parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/") or parsed.port is not None):
        raise ValueError(
            "SUPABASE_URL_HAS_EXTRA_COMPONENTS: use only the HTTPS project "
            "root URL, without /rest/v1, /dashboard, port or query parameters."
        )
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
