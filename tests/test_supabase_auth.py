"""No network or live credentials are used."""
import pytest

from research_agent_lab.supabase_auth import headers, supabase_url


def test_modern_sb_secret_is_never_bearer(monkeypatch):
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_test_key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "eyJlegacy.header.sig")
    result = headers(prefer="return=minimal")
    assert result["apikey"] == "sb_secret_test_key"
    assert "Authorization" not in result
    assert result["Prefer"] == "return=minimal"


def test_legacy_jwt_uses_both(monkeypatch):
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "eyJtest.payload.signature")
    result = headers()
    assert result["Authorization"] == "Bearer eyJtest.payload.signature"
    assert result["apikey"] == "eyJtest.payload.signature"


def test_publishable_refused(monkeypatch):
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_publishable_abc")
    with pytest.raises(ValueError, match="privileged"):
        headers()


def test_absent_key_rejected(monkeypatch):
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    with pytest.raises(ValueError, match="Missing"):
        headers()


def test_project_url_validation(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://demo.supabase.co/")
    assert supabase_url() == "https://demo.supabase.co"
    monkeypatch.setenv("SUPABASE_URL", "http://demo.supabase.co")
    with pytest.raises(ValueError):
        supabase_url()



def test_missing_url_is_distinguished_from_invalid_url(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    with pytest.raises(ValueError, match="SUPABASE_URL_NOT_SET"):
        supabase_url()


def test_database_uri_and_dashboard_link_have_safe_diagnostics(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "postgresql://admin:SUPER_SECRET@db.example.co:5432/mydb")
    with pytest.raises(ValueError, match="SUPABASE_URL_IS_DATABASE_URI") as exc:
        supabase_url()
    assert "SUPER_SECRET" not in str(exc.value)
    monkeypatch.setenv("SUPABASE_URL", "https://supabase.com/dashboard/project/abc")
    with pytest.raises(ValueError, match="SUPABASE_URL_IS_DASHBOARD"):
        supabase_url()


def test_rest_path_or_query_string_rejected_without_echo(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://demo.supabase.co/rest/v1?apikey=PRIVATE")
    with pytest.raises(ValueError, match="SUPABASE_URL_HAS_EXTRA_COMPONENTS") as exc:
        supabase_url()
    assert "PRIVATE" not in str(exc.value)
