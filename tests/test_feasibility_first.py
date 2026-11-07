"""Feasibility gate: typed schema, genuine access and bounded correction, no paid calls."""
from pathlib import Path
from research_agent_lab.contracts import Dataset,Paper,ResearchLine,Snapshot
from research_agent_lab.frontier.feasibility_gate import (
    check_candidate,screen_pool,minimal_viable_plan
)
from research_agent_lab.frontier.engine import FrontierConfig,run_frontier
from research_agent_lab.frontier.mock import FrontierMockModel
from research_agent_lab.frontier.memory import MemoryStore
from research_agent_lab.model import BudgetedModel


def dataset_snapshot(access=True):
    return Snapshot(
        snapshot_id="synthetic-test",provenance="synthetic_demo",
        research_line=ResearchLine(id="synthetic_line",name="Fictional line",
                                   problem="Assess data feasibility"),
        papers=[Paper(id="P1",title="Fictional research")],
        datasets=[Dataset(id="D1",name="Synthetic schema",access_verified=access,
                          fields=["street","target","feature"])],
    )


def candidate():
    return {"id":"H001","status":"candidate","title":"Synthetic idea",
            "question":"Does the feature predict the target?",
            "paper_ids":["P1"],"dataset_ids":["D1"],
            "execution_plan":{
                "study_type":"empirical","unit_of_analysis":"street segment",
                "outcome_field":"target","baseline_method":"mean baseline",
                "evaluation_metric":"held-out RMSE",
                "split_strategy":"spatial group split",
                "steps":["Inspect approved dataset field distributions",
                         "Compare held-out test results to a trivial baseline"],
                "dataset_field_map":[{"dataset_id":"D1",
                                      "fields":["street","target","feature"]}],
            }}


def test_access_and_schema_precheck_only():
    verdict=check_candidate(candidate(),dataset_snapshot())
    assert verdict["status"]=="precheck_passed"
    assert verdict["scientific_novelty_verified"] is False
    assert "DATASET_ACCESS_NOT_VERIFIED" in check_candidate(
        candidate(),dataset_snapshot(access=False))["reason_codes"]


def test_missing_data_and_fabricated_outcome_are_blocked():
    no_data={**candidate(),"dataset_ids":[]}
    assert "NO_DATASET_REFERENCE" in check_candidate(
        no_data,dataset_snapshot())["reason_codes"]
    forged=candidate()
    forged["execution_plan"]["outcome_field"]="fictional_column"
    verdict=check_candidate(forged,dataset_snapshot())
    assert "OUTCOME_FIELD_NOT_REGISTERED" in verdict["reason_codes"]


def test_blocked_candidates_not_sent_to_elo_and_remain_in_audit():
    good=candidate()
    bad={**candidate(),"id":"H002","dataset_ids":[]}
    all_candidates,report=screen_pool([good,bad],dataset_snapshot())
    assert [c["status"] for c in all_candidates]==["candidate","blocked"]
    assert report["eligible_count"]==1
    assert report["blocked_candidates"][0]["id"]=="H002"


def test_no_access_returns_actionable_plan_not_fabricated_research():
    plan=minimal_viable_plan(dataset_snapshot(access=False),[{
        "feasibility":{"reason_codes":["NO_DATASET_REFERENCE"]},
        "question":"Can it work?"
    }])
    assert plan["first_action"]
    assert plan["next_steps"]
    assert plan["ready_for_empirical_experiment"] is False
    assert plan["requires_human_data_authorization"] is True


def test_mock_frontier_never_ranks_inaccessible_data(tmp_path):
    snapshot=Snapshot.model_validate_json(
        (Path(__file__).resolve().parents[1]/"examples"/"synthetic_snapshot.json").read_text()
    )
    memory=MemoryStore(str(tmp_path/"memory.sqlite"))
    try:
        model=BudgetedModel(FrontierMockModel(),max_calls=55)
        result=run_frontier(snapshot,model,memory,
             FrontierConfig(max_generations=2,minimum_generations=2,
                            feasibility_first=True))
    finally:
        memory.close()
    assert result["status"]=="needs_more_evidence"
    assert result["recommendation_state"]=="no_executable_candidates"
    assert result["winner"] is None
    assert result["matches"]==[]
    assert result["minimum_viable_plan"]["next_steps"]
    assert result["minimum_viable_plan"]["ready_for_empirical_experiment"] is False
    assert result["generation_count"]==0


class FeasibleSeedModel(FrontierMockModel):
    """Mock valid registered data, no live research data or external calls."""
    def complete(self, *, role, system, payload):
        if role.startswith("frontier_seed:"):
            lens=role.partition(":")[2]
            record=candidate()
            record["title"]="Synthetic verifiable "+lens
            record["question"]="Does a registered synthetic feature predict a target?"
            record["mechanism"]="This is a toy regression, not scientific evidence."
            record["falsifiable_prediction"]="Held-out RMSE may differ from mean baseline."
            record["method"]="Train-only fit and grouped holdout"
            record["minimal_experiment"]="Fit mean baseline and compare held-out errors"
            record["baselines"]=["mean baseline"]
            record["limitations"]=["Synthetic toy; no real-world novelty verified"]
            return record
        return super().complete(role=role,system=system,payload=payload)


class RepairableModel(FeasibleSeedModel):
    def complete(self, *,role,system,payload):
        if role.startswith("frontier_seed:"):
            record=super().complete(role=role,system=system,payload=payload)
            record.pop("execution_plan")
            return record
        if role=="frontier_feasibility_reviser":
            result=candidate()
            result.update({
                "title":"Repaired synthetic plan",
                "question":"Does the synthetic predictor reduce mean error?",
                "mechanism":"Fictional relation for testing gate only.",
                "falsifiable_prediction":"RMSE decreases on held-out groups.",
                "method":"Simple grouped baseline",
                "minimal_experiment":"Compare mean to single-variable regression",
                "baselines":["train-only mean"],
                "limitations":["Toy example only"]
            })
            return result
        return super().complete(role=role,system=system,payload=payload)


def test_verified_synthetic_metadata_reaches_real_tournament(tmp_path):
    memory=MemoryStore(str(tmp_path/"feasible.sqlite"))
    try:
        run=run_frontier(
            dataset_snapshot(),BudgetedModel(FeasibleSeedModel(),max_calls=30),
            memory,FrontierConfig(max_generations=0,max_pairs_per_tournament=1,
                                  feasibility_first=True)
        )
    finally:
        memory.close()
    assert run["feasibility"]["eligible_count"]==3
    assert len(run["matches"])==1
    assert run["winner"] is not None
    assert run["status"]=="needs_more_evidence"  # LLM mock cannot validate science


def test_two_bounded_feedback_revisions_stop_when_single_candidate_passes(tmp_path):
    memory=MemoryStore(str(tmp_path/"repair.sqlite"))
    try:
        run=run_frontier(
            dataset_snapshot(),BudgetedModel(RepairableModel(),max_calls=25),
            memory,FrontierConfig(max_generations=0,max_pairs_per_tournament=1,
                                  feasibility_first=True,max_feasibility_revisions=2)
        )
    finally:
        memory.close()
    assert run["feasibility"]["eligible_count"]==1
    assert run["winner"]["origin"]=="feasibility_repair"
    assert run["winner"]["parent_ids"]
    assert len(run["matches"])==0
    assert sum(x["stage"]=="feasibility_revision" for x in run["event_log"])==1
    assert any(x["status"]=="blocked" for x in run["archived_candidates"])
