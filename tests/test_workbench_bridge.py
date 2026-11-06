import httpx
import pytest

from research_agent_lab.workbench_bridge import fetch_workbench_evidence


def valid_bundle():
    return {
        "bundle_id": "research-team",
        "source": "authorized_database_export",
        "sharing_approved": True,
        "achievements": [{
            "id": "demo-output", "title": "Synthetic research evidence",
            "year": 2025,
        }],
        "datasets": [],
        "external_papers": [],
    }


def test_authorized_fetch_does_not_log_or_echo_token():
    captured = []
    def mock(request):
        captured.append(request)
        return httpx.Response(200, json=valid_bundle())
    with httpx.Client(transport=httpx.MockTransport(mock)) as client:
        bundle = fetch_workbench_evidence(
            base_url="https://research-atlas-api-test.onrender.com",
            export_token="s" * 40, client=client
        )
    assert bundle.bundle_id == "research-team"
    assert captured[0].headers["X-Research-Export-Token"] == "s" * 40
    assert captured[0].url.path == "/api/integrations/research-agent-lab/evidence"


def test_export_not_approved_rejected():
    def mock(request):
        payload = valid_bundle()
        payload["sharing_approved"] = False
        return httpx.Response(200, json=payload)
    with httpx.Client(transport=httpx.MockTransport(mock)) as client:
        with pytest.raises(ValueError, match="validation error"):
            fetch_workbench_evidence(
                base_url="https://research-atlas-api-test.onrender.com",
                export_token="z" * 40, client=client
            )


def test_export_403_is_safe():
    def mock(request):
        return httpx.Response(403, text="FORBIDDEN SECRET TEXT")
    with httpx.Client(transport=httpx.MockTransport(mock)) as client:
        with pytest.raises(RuntimeError, match="HTTP 403") as exc:
            fetch_workbench_evidence(
                base_url="https://research-atlas-api-test.onrender.com",
                export_token="k" * 40, client=client
            )
        assert "FORBIDDEN SECRET" not in str(exc.value)


def test_reject_untrusted_target_hosts():
    with pytest.raises(ValueError, match="Render service URL"):
        fetch_workbench_evidence(
            base_url="http://localhost:8000", export_token="s" * 40
        )
    with pytest.raises(ValueError, match="Render service URL"):
        fetch_workbench_evidence(
            base_url="https://example.com", export_token="s" * 40
        )
