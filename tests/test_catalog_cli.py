from research_agent_lab.catalog_cli import export_minimal_approved


def test_export_never_copies_unapproved_original_description():
    raw={
        "schema_version": 1, "approved_by_data_owner": True,
        "assets":[
            {
                "id":"cusp_1234567890123456", "name":"Synthetic grid",
                "category":"geography","risk_class":"standard_review",
                "metadata_sharing_approved": True,
                "original_description":"DO_NOT_COPY_PRIVATE_TRIPS",
                "original_prior_research":"DO_NOT_COPY_STUDY",
                "approved_description":"Public-safe aggregate grid metadata",
                "approved_prior_research":"Public study",
                "coverage":"Fictional place","period":"2025",
                "verified_fields":[],
                "access_verified":False,
            },
            {
                "id":"cusp_9876543210987654", "name":"Private diagnosis",
                "risk_class":"high_review",
                "metadata_sharing_approved":False,
                "original_description":"DO_NOT_COPY_HEALTH_RECORDS"
            }
        ]
    }
    output=export_minimal_approved(raw)
    assert len(output["assets"])==1
    assert output["assets"][0]["approved_description"].startswith("Public-safe")
    assert "DO_NOT_COPY" not in str(output)
    assert output["approved_by_data_owner"] is True
