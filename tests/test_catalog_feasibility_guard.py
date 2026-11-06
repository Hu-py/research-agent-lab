"""Model must not convert registered metadata into a verified accessible dataset."""
from research_agent_lab.contracts import Snapshot, Dataset, Paper, ResearchLine
from research_agent_lab.frontier.science import validate_scientifically
from research_agent_lab.model import BudgetedModel


class Overconfident:
    last_usage={}
    def complete(self, *, role, system, payload):
        return {
            "hypothesis_test":"Check effect under holdout",
            "primary_metric":"RMSE",
            "baselines":["Mean"],
            "ablations":["Remove context"],
            "split_strategy":"Grouped spatial holdout",
            "failure_criteria":"No model improvement",
            "evidence_limitations":["Data availability unconfirmed"],
            "data_feasible": True,
            "proposed_field_mapping":{},
        }


def candidate():
    return {
        "paper_ids":["paper-1"],"dataset_ids":["cusp_approved_metadata"],
        "baselines":["Mean"],"falsifiable_prediction":"Baseline not beaten"
    }


def snapshot(access=False):
    return Snapshot(
        snapshot_id="fake",provenance="approved_export",
        research_line=ResearchLine(id="research", name="Research",problem="Test?"),
        papers=[Paper(id="paper-1",title="Synthetic publication")],
        datasets=[Dataset(id="cusp_approved_metadata", name="Catalog-only data",
                          sensitivity="internal", access_verified=access)],
    )


def test_model_cannot_grant_data_access_from_catalog_entry():
    result=validate_scientifically(
        snapshot(False),candidate(), BudgetedModel(Overconfident())
    )
    assert result["data_feasible_model_opinion"] is True
    assert result["data_feasible_assessment"] is False
    assert result["dataset_access_evidence_verified"] is False


def test_explicit_access_metadata_does_not_override_human_review():
    result=validate_scientifically(
        snapshot(True),candidate(), BudgetedModel(Overconfident())
    )
    assert result["data_feasible_assessment"] is True
    assert result["novelty_verified"] is False
    assert result["experimental_claim_verified"] is False
