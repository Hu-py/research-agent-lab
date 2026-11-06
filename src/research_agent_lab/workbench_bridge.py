"""Fetch owner-approved research metadata from the original Render workbench.

Only enabled by explicit workflow_dispatch + a dedicated, read-only export
token. GitHub Secrets are never printed or persisted in research reports.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit
import httpx

from research_agent_lab.portrait import EvidenceBundle


def fetch_workbench_evidence(*, base_url: str | None = None,
                             export_token: str | None = None,
                             client: httpx.Client | None = None) -> EvidenceBundle:
    url = (base_url or os.getenv("WORKBENCH_API_URL") or "").rstrip("/")
    token = export_token or os.getenv("WORKBENCH_EXPORT_TOKEN") or ""
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or
        not parsed.hostname.endswith(".onrender.com") or
        parsed.username or parsed.password or parsed.query or
        parsed.fragment or parsed.port or parsed.path):
        raise ValueError("WORKBENCH_API_URL must be a bare HTTPS Render service URL")
    if len(token) < 32:
        raise ValueError("WORKBENCH_EXPORT_TOKEN must be configured as a dedicated token")
    owned = client is None
    http = client or httpx.Client(timeout=40, follow_redirects=False)
    try:
        try:
            response = http.get(
                url + "/api/integrations/research-agent-lab/evidence",
                headers={
                    "X-Research-Export-Token": token,
                    "Accept": "application/json",
                    "Cache-Control": "no-store",
                }
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                "Workbench export failed with HTTP "
                + str(exc.response.status_code)
                + "; check Render deployment, dedicated token and metadata approval"
            ) from None
        except httpx.TransportError:
            raise RuntimeError("Workbench export transport connection failed") from None
        bundle = EvidenceBundle.model_validate(response.json())
        if not bundle.sharing_approved:
            raise ValueError("Workbench metadata not approved for LLM sharing")
        return bundle
    finally:
        if owned:
            http.close()
