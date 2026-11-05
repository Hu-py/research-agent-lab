"""Deterministic synthetic stub; never claim these represent scientific findings."""
from __future__ import annotations

from research_agent_lab.model import MockJSONModel


class FrontierMockModel(MockJSONModel):
    def complete(self, *, role: str, system: str, payload: dict) -> dict:
        if role == "query_planner":
            return {"queries": ["synthetic urban graphs", "synthetic urban evaluation"]}
        if role in ("paper_juror_a", "paper_juror_b", "paper_adjudicator"):
            return {"assessments": [
                {"paper_id": p["id"], "retain": True,
                 "reason": "DEMO ONLY: illustrative bibliographic record"}
                for p in payload["papers"]
            ]}
        if role.startswith("frontier_seed:"):
            lens = role.partition(":")[2]
            pids = [p["id"] for p in payload["snapshot"]["papers"]]
            dids = [d["id"] for d in payload["snapshot"]["datasets"]]
            return {
                "title": "SYNTHETIC DEMO: " + lens + " view of urban learning",
                "question": "Can group-robust spatial predictors beat mean baselines?",
                "mechanism": "Hypothetical interactions in spatial signals.",
                "falsifiable_prediction": "Performance changes under held-out groups.",
                "method": "Fixed grouped validation with ablations.",
                "minimal_experiment": "Fit a simple model and compare a mean baseline.",
                "baselines": ["train-only mean baseline"],
                "paper_ids": pids[:2],
                "dataset_ids": dids[:1],
                "limitations": ["SYNTHETIC DEMO, not a real research assessment"],
            }
        if role == "proximity":
            candidates = payload["candidates"]
            return {"pairs": [
                {"a": a["id"], "b": b["id"],
                 "similarity": 0.65 if a["origin"] == b["origin"] else 0.35}
                for i, a in enumerate(candidates)
                for b in candidates[i + 1:]
            ]}
        if role == "pairwise_judge":
            a = payload["left"]["id"]
            b = payload["right"]["id"]
            return {
                "winner_id": max(a, b),
                "reason": "DEMO ONLY: deterministic lexical choice, not scientific rank.",
                "caveat": "Synthetic mock result has no evidential value."
            }
        if role == "supervisor":
            return {
                "action": "evolve" if payload["generation"] == 0 else "verify",
                "reason": "SYNTHETIC supervisor, deterministic test action.",
                "expected_gain": "No demonstrated gain in mock mode.",
            }
        if role == "evolution_critic":
            return {
                "objections": ["Synthetic review: risk of leakage."],
                "counter_tests": ["Hold out spatial groups."],
            }
        if role.startswith("frontier_evolve:"):
            parent = payload["parents"][0]
            method = role.partition(":")[2]
            return {
                "title": "SYNTHETIC " + method + ": " + parent["title"],
                "question": parent["question"],
                "mechanism": parent["mechanism"],
                "falsifiable_prediction": parent["falsifiable_prediction"],
                "method": parent["method"],
                "minimal_experiment": parent["minimal_experiment"],
                "baselines": parent["baselines"],
                "paper_ids": parent["paper_ids"],
                "dataset_ids": parent["dataset_ids"],
                "limitations": parent["limitations"] + ["Mock revision only"],
            }
        if role == "scientific_validator":
            return {
                "hypothesis_test": "DEMO ONLY: compare group-held-out predictions.",
                "primary_metric": "held-out R2",
                "baselines": ["mean baseline"],
                "ablations": ["remove context"],
                "split_strategy": "spatially grouped holdout",
                "failure_criteria": "effect disappears across holdout groups",
                "evidence_limitations": ["Synthetic, no real accessible raw data."],
                "data_feasible": False,
                "proposed_field_mapping": {},
            }
        return super().complete(role=role, system=system, payload=payload)
