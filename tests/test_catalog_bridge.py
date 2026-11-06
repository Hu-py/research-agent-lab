import pytest

from research_agent_lab.catalog_bridge import (
    approved_catalog_assets, merge_approved_catalog,
    approved_catalog_from_json
)
from research_agent_lab.portrait import EvidenceBundle


def fake_bundle():
    return EvidenceBundle.model_validate({
        "bundle_id":"synthetic-team", "source":"authorized_database_export",
        "sharing_approved":True,
        "achievements":[{"id":"owned-1","title":"A synthetic study","year":2025}],
        "datasets":[], "external_papers":[],
    })


def manifest(approve=True, *, risk="standard_review"):
    return {
        "schema_version":1,
        "approved_by_data_owner":True,
        "assets":[
            {
                "id":"cusp_abcdef1234567890",
                "name":"Synthetic spatial networks",
                "category":"地理与空间单元",
                "coverage":"Fictional city",
                "period":"2025",
                "original_description":"DO_NOT_EXPORT: home location, raw trips",
                "original_prior_research":"DO_NOT_EXPORT: private study",
                "approved_description":"An aggregate network footprint",
                "approved_prior_research":"Published urban network study",
                "risk_class":risk,
                "metadata_sharing_approved":approve,
                "verified_field_list":False,
                "verified_fields":[],
                "access_verified":False,
            }
        ],
    }


def test_approved_catalog_does_not_forward_original_sensitive_columns():
    b, meta = merge_approved_catalog(fake_bundle(), manifest())
    assert meta["newly_added_metadata"] == 1
    assert b.datasets[0].fields == []
    assert b.datasets[0].sensitivity == "internal_metadata_approved"
    assert not b.datasets[0].access_verified
    assert "DO_NOT_EXPORT" not in b.model_dump_json()


def test_owner_approval_and_per_record_approval_required():
    payload=manifest()
    payload["approved_by_data_owner"]=False
    with pytest.raises(ValueError, match="OWNER_APPROVAL_REQUIRED"):
        approved_catalog_assets(payload)
    with pytest.raises(ValueError, match="NO_APPROVED"):
        approved_catalog_assets(manifest(approve=False))


def test_high_risk_metadata_only_and_no_unverified_fields():
    data=manifest(risk="high_review")
    data["assets"][0]["verified_fields"]=["personal_identifier"]
    with pytest.raises(ValueError, match="HIGH_RISK_FIELD_NAMES_EXCLUDED"):
        approved_catalog_assets(data)
    data["assets"][0]["verified_fields"]=[]
    data["assets"][0]["approved_description"]=""
    with pytest.raises(ValueError, match="HIGH_RISK_SUMMARY_REQUIRED"):
        approved_catalog_assets(data)


def test_catalog_cannot_claim_access_by_f_drive_checkmark():
    data=manifest()
    data["assets"][0]["access_verified"]=True
    with pytest.raises(ValueError, match="ACCESS_MUST_REMAIN_UNVERIFIED"):
        approved_catalog_assets(data)


def test_approved_data_can_join_existing_portrait_bundle():
    bundle, _=merge_approved_catalog(fake_bundle(),manifest())
    assert len(bundle.datasets)==1
    assert bundle.datasets[0].id.startswith("cusp_")
    assert bundle.sharing_approved
    assert bundle.achievements[0].id=="owned-1"


def test_name_duplicate_avoids_double_count():
    source=fake_bundle()
    source.datasets.append(source.datasets.__class__()) if False else None
    from research_agent_lab.portrait import DataAsset
    source.datasets.append(DataAsset(
        id="existing-public", name="Synthetic spatial networks", sensitivity="public"
    ))
    updated,counts=merge_approved_catalog(source,manifest())
    assert len(updated.datasets)==1
    assert counts["existing_name_duplicates_skipped"]==1


def test_reject_unapproved_manifest_json():
    with pytest.raises(ValueError,match="CATALOG_NOT_VALID_JSON"):
        approved_catalog_from_json("{bad")
