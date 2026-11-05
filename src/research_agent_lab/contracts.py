"""Evidence contracts and programmatic validation (not LLM self-attestation)."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field, model_validator


class ResearchLine(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=160)
    problem: str = Field(min_length=1, max_length=1200)
    goals: str = Field(default="", max_length=1000)


class Paper(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=350)
    abstract: str = Field(default="", max_length=3000)
    doi: str = Field(default="", max_length=160)
    venue: str = Field(default="", max_length=180)


class Dataset(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=1200)
    fields: list[str] = Field(default_factory=list, max_length=80)
    sensitivity: Literal["public", "internal"] = "public"


class Snapshot(BaseModel):
    """Only explicitly approved paper metadata and allowed dataset descriptions."""
    snapshot_id: str = Field(min_length=1, max_length=140)
    provenance: Literal["synthetic_demo", "approved_export", "openalex_discovered", "public_demo_profile"]
    research_line: ResearchLine
    papers: list[Paper] = Field(default_factory=list, max_length=80)
    datasets: list[Dataset] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_references(self) -> "Snapshot":
        paper_ids = [p.id for p in self.papers]
        data_ids = [d.id for d in self.datasets]
        if len(set(paper_ids)) != len(paper_ids):
            raise ValueError("Duplicate paper IDs")
        if len(set(data_ids)) != len(data_ids):
            raise ValueError("Duplicate dataset IDs")
        if set(paper_ids) & set(data_ids):
            raise ValueError("Paper and dataset IDs must not overlap")
        return self


def _text(item: object, name: str, limit: int = 1200) -> str:
    if not isinstance(item, str) or not item.strip() or len(item) > limit:
        raise ValueError("Invalid or missing text: " + name)
    return item.strip()


def _items(item: object, name: str, *, required: bool = False) -> list[str]:
    if not isinstance(item, list) or any(not isinstance(x, str) or len(x) > 350 for x in item):
        raise ValueError("Invalid list: " + name)
    values = list(dict.fromkeys(x.strip() for x in item if x.strip()))
    if required and not values:
        raise ValueError("Missing list values: " + name)
    return values[:15]


def validate_candidate(raw: object, snapshot: Snapshot, lens: str) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("Candidate must be a JSON object")
    required = ["title", "question", "mechanism", "falsifiable_prediction",
                "method", "minimal_experiment"]
    candidate = {name: _text(raw.get(name), name) for name in required}
    for name in ("baselines", "paper_ids", "dataset_ids", "limitations"):
        candidate[name] = _items(raw.get(name, []), name, required=name in ("baselines", "paper_ids"))
    paper_ids = {p.id for p in snapshot.papers}
    data_ids = {d.id for d in snapshot.datasets}
    if not set(candidate["paper_ids"]) <= paper_ids:
        raise ValueError("Candidate cites paper IDs absent from evidence snapshot")
    if not set(candidate["dataset_ids"]) <= data_ids:
        raise ValueError("Candidate cites dataset IDs absent from evidence snapshot")
    candidate.update({
        "id": lens,
        "novelty_verified": False,
        "data_access_verified": False,
        "human_review_required": True,
    })
    return candidate


def validate_challenges(raw: object, candidate_ids: set[str]) -> list[dict]:
    if not isinstance(raw, dict) or not isinstance(raw.get("challenges"), list):
        raise ValueError("Critic must return challenges")
    output = []
    for issue in raw["challenges"]:
        if not isinstance(issue, dict) or issue.get("candidate_id") not in candidate_ids:
            raise ValueError("Unknown critique target")
        output.append({
            "candidate_id": issue["candidate_id"],
            "objections": _items(issue.get("objections"), "objections", required=True),
            "counter_test": _text(issue.get("counter_test"), "counter_test"),
        })
    if {x["candidate_id"] for x in output} != candidate_ids:
        raise ValueError("Every candidate must receive an independent critique")
    if len(output) != len(candidate_ids):
        raise ValueError("Duplicate critique target")
    return output


SCORE_AXES = ("novelty", "feasibility", "testability", "evidence")


def validate_review(raw: object, candidate_ids: set[str]) -> dict:
    if not isinstance(raw, dict) or not isinstance(raw.get("ranked"), list):
        raise ValueError("Reviewer must return ranked candidates")
    ranked = []
    for item in raw["ranked"]:
        if not isinstance(item, dict) or item.get("candidate_id") not in candidate_ids:
            raise ValueError("Unknown review candidate")
        record = {"candidate_id": item["candidate_id"]}
        for axis in SCORE_AXES:
            val = item.get(axis)
            if isinstance(val, bool) or not isinstance(val, (float, int)) or not 0 <= val <= 100:
                raise ValueError("Review score must be 0..100: " + axis)
            record[axis] = round(float(val), 2)
        record["score"] = round(sum(record[k] for k in SCORE_AXES) / 4, 2)
        record["concerns"] = _items(item.get("concerns", []), "concerns")
        ranked.append(record)
    if len(ranked) != len(candidate_ids) or {r["candidate_id"] for r in ranked} != candidate_ids:
        raise ValueError("Review must score each candidate exactly once")
    ranked.sort(key=lambda r: (-r["score"], r["candidate_id"]))
    if not isinstance(raw.get("needs_revision"), bool):
        raise ValueError("needs_revision must be boolean")
    return {
        "ranked": ranked,
        "winner_id": ranked[0]["candidate_id"],
        "needs_revision": raw["needs_revision"],
        "reason": _text(raw.get("reason"), "reason"),
        "score": ranked[0]["score"],
        "llm_assessed_only": True,
    }
