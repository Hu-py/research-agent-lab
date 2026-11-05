"""Evidence-first, continuously revisable TEAM research portrait.

Two important separations:
1) team_achievements are OWN work; approved_papers are EXTERNAL literature.
2) a title/tag is a topic clue, NOT proof of an implemented method or dataset access.

Data comes from an explicitly approved database export, never conversation history.
All generated lines retain source refs and their evidence confidence.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from research_agent_lab.model import BudgetedModel
from research_agent_lab.contracts import Snapshot, ResearchLine, Dataset, Paper


class Achievement(BaseModel):
    id: str = Field(min_length=2, max_length=140)
    title: str = Field(min_length=3, max_length=400)
    year: int = Field(ge=1900, le=2100)
    kind: str = "paper"
    tags: list[str] = Field(default_factory=list, max_length=20)
    abstract: str = Field(default="", max_length=3000)
    doi: str = Field(default="", max_length=200)
    venue: str = Field(default="", max_length=200)
    evidence_level: Literal["title_only", "abstract", "fulltext"] = "title_only"
    ownership: Literal["verified_team_output"] = "verified_team_output"


class DataAsset(BaseModel):
    id: str = Field(min_length=2, max_length=140)
    name: str = Field(min_length=2, max_length=200)
    category: str = ""
    description: str = Field(default="", max_length=1300)
    prior_research: str = Field(default="", max_length=1200)
    coverage: str = Field(default="", max_length=300)
    period: str = Field(default="", max_length=200)
    fields: list[str] = Field(default_factory=list, max_length=80)
    sensitivity: Literal["public"] = "public"
    access_verified: bool = False


class ExternalPaper(BaseModel):
    id: str = Field(min_length=2, max_length=140)
    title: str = Field(min_length=3, max_length=400)
    abstract: str = Field(default="", max_length=3000)
    doi: str = Field(default="", max_length=200)
    venue: str = Field(default="", max_length=200)
    ownership: Literal["external_literature"] = "external_literature"


class EvidenceBundle(BaseModel):
    bundle_id: str = Field(min_length=2, max_length=150)
    source: Literal["authorized_database_export"]
    sharing_approved: Literal[True]
    achievements: list[Achievement] = Field(min_length=1, max_length=100)
    datasets: list[DataAsset] = Field(default_factory=list, max_length=100)
    external_papers: list[ExternalPaper] = Field(default_factory=list, max_length=100)
    old_profile: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_unique_ids(self):
        refs = [item.id for item in self.achievements + self.datasets + self.external_papers]
        if len(refs) != len(set(refs)):
            raise ValueError("Every source ID must be globally unique")
        return self


def preview_from_original_inventory(inventory: dict, *, include_public_datasets: bool = False) -> dict:
    """Convert legacy backend.profile_database.evidence_inventory into a PREVIEW.

    Produces NO approved export. The old inventory lacks explicit dataset
    sensitivity and verified field-level provenance; datasets are excluded until
    an authorized curator adds public-safe descriptions and sharing_approved=true.
    """
    if inventory.get("evidence_source") != "postgresql_only":
        raise ValueError("Expected existing PostgreSQL evidence_inventory output")
    ach = []
    for a in inventory.get("team_achievements", []):
        if not isinstance(a, dict) or not a.get("id") or not a.get("title"):
            continue
        ach.append({"id": str(a["id"]), "title": str(a["title"]),
                    "year": int(a.get("year") or 2000), "kind": str(a.get("kind") or "paper"),
                    "tags": a.get("tags") or [], "evidence_level": "title_only",
                    "ownership": "verified_team_output"})
    ext = []
    for p in inventory.get("approved_papers", []):
        if not isinstance(p, dict) or not p.get("id") or not p.get("title"):
            continue
        ext.append({"id": str(p["id"]), "title": str(p["title"]),
                    "doi": str(p.get("doi") or ""), "venue": str(p.get("venue") or ""),
                    "ownership": "external_literature"})
    # Dataset rows in old inventory have no sensitivity declaration.
    # Hence they are NOT safe to send off-box automatically.
    return {
        "bundle_id": "preview-not-approved",
        "source": "authorized_database_export",
        "sharing_approved": False,
        "achievements": ach,
        "datasets": [],
        "external_papers": ext,
        "old_profile": inventory.get("profile") or {},
        "requires_explicit_sharing_review": True,
        "omitted_unverified_dataset_count": len(inventory.get("datasets") or []),
    }


def evidence_hash(bundle: EvidenceBundle) -> str:
    return hashlib.sha256(
        json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False,
                   sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


PROFILE_SYSTEM = (
    "You are an expert scientific research capability analyst. Construct a "
    "research-team portrait grounded ONLY in the evidence bundle. Titles and "
    "keywords are hypotheses about topics, not proof of methods or dataset use. "
    "OWN achievements and EXTERNAL papers must never be conflated. "
    "Do not assume that a registered dataset is accessible or complete. "
    "The previous portrait is an untrusted hypothesis to revise, not a taxonomy "
    "to be preserved. No invented IDs, publications or methods. JSON only."
)


def _validate_profile(raw: object, bundle: EvidenceBundle) -> dict:
    if not isinstance(raw, dict) or not isinstance(raw.get("research_lines"), list):
        raise ValueError("Portrait model must return research_lines")
    lines = raw["research_lines"]
    if not 1 <= len(lines) <= 8:
        raise ValueError("Portrait must have 1..8 evidence-grounded research lines")
    a_ids = {a.id for a in bundle.achievements}
    d_ids = {d.id for d in bundle.datasets}
    e_ids = {p.id for p in bundle.external_papers}
    a_map = {a.id: a for a in bundle.achievements}
    seen = set()
    clean = []
    covered = set()
    for line in lines:
        if not isinstance(line, dict):
            raise ValueError("Malformed research line")
        line_id = line.get("id")
        if not isinstance(line_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]{2,54}", line_id):
            raise ValueError("Research line ID must be lowercase slug")
        if line_id in seen:
            raise ValueError("Duplicate research line ID")
        seen.add(line_id)
        refs = line.get("achievement_ids", [])
        ds = line.get("dataset_ids", [])
        ext = line.get("external_paper_ids", [])
        if not isinstance(refs, list) or not isinstance(ds, list) or not isinstance(ext, list):
            raise ValueError("Evidence references must be lists")
        if not set(refs) <= a_ids or not set(ds) <= d_ids or not set(ext) <= e_ids:
            raise ValueError("Portrait referenced nonexistent or wrong-ownership source IDs")
        if not refs and not ds:
            raise ValueError("A research line needs team output or a registered dataset")
        if len(refs) != len(set(refs)) or len(ds) != len(set(ds)):
            raise ValueError("Repeated source reference")
        name = line.get("name")
        problem = line.get("problem")
        if not isinstance(name, str) or not name.strip() or len(name) > 140:
            raise ValueError("Missing valid research line name")
        if not isinstance(problem, str) or not problem.strip() or len(problem) > 1200:
            raise ValueError("Missing valid research question")
        methods = line.get("methods", [])
        questions = line.get("open_questions", [])
        if not isinstance(methods, list) or not all(isinstance(x, str) for x in methods):
            raise ValueError("Methods must be a list of strings")
        if not isinstance(questions, list) or not all(isinstance(x, str) for x in questions):
            raise ValueError("Open research questions must be strings")
        covered.update(refs)
        confirmed_method_basis = any(a_map[r].evidence_level in ("abstract", "fulltext") for r in refs)
        clean.append({
            "id": line_id,
            "name": name.strip(),
            "problem": problem.strip(),
            "achievement_ids": refs[:25],
            "dataset_ids": ds[:15],
            "external_paper_ids": ext[:15],
            "methods": [x[:170] for x in methods[:12]],
            "open_questions": [x[:500] for x in questions[:8]],
            "evidence_status": (
                "title_based_inference" if not confirmed_method_basis
                else "described_in_verified_team_outputs"
            ) if refs else "data_only_unverified",
            "data_access_verified": bool(ds) and all(
                next(d for d in bundle.datasets if d.id == x).access_verified for x in ds
            ),
            "novelty_verified": False,
        })
    omitted = raw.get("unassigned_achievement_ids", [])
    if not isinstance(omitted, list) or not set(omitted) <= a_ids:
        raise ValueError("Unknown unassigned achievement IDs")
    if covered & set(omitted):
        raise ValueError("A cited achievement cannot also be unassigned")
    if covered | set(omitted) != a_ids:
        raise ValueError("Every team achievement must be covered or explicitly unassigned")
    changes = raw.get("changes_from_previous", [])
    if not isinstance(changes, list) or not all(isinstance(x, str) for x in changes):
        raise ValueError("Missing changes_from_previous list")
    return {
        "research_lines": clean,
        "unassigned_achievement_ids": omitted,
        "changes_from_previous": [x[:400] for x in changes[:15]],
        "source_evidence_hash": evidence_hash(bundle),
        "research_capability_not_fully_verified": True,
    }


def synthesize_portrait(bundle: EvidenceBundle, model: BudgetedModel, *,
                        iterations: int = 1) -> dict:
    """LLM curator -> independent critic -> LLM correction, source-constrained."""
    if not 0 <= iterations <= 2:
        raise ValueError("Portrait revision iterations must be 0..2")
    evidence = bundle.model_dump(mode="json")
    raw = model.complete(
        role="portrait_curator", system=PROFILE_SYSTEM,
        payload={
            "evidence": evidence,
            "task": (
                "Independently regroup team-owned achievements into defensible research lines. "
                "Use actual research questions, not title keyword buckets. "
                "Every source achievement must belong to a line or appear in "
                "unassigned_achievement_ids. Reference registered dataset IDs only. "
                "Return research_lines [{id,name,problem,achievement_ids,dataset_ids,"
                "external_paper_ids,methods,open_questions}], "
                "unassigned_achievement_ids, changes_from_previous."
            ),
        },
    )
    portrait = _validate_profile(raw, bundle)
    critique_history = []
    for round_number in range(iterations):
        critical = model.complete(
            role="portrait_critic", system=PROFILE_SYSTEM + (
                " Independently challenge overgeneralization, unsupported method "
                "claims, hidden work, false dataset readiness and missing past work."
            ),
            payload={"evidence": evidence, "draft_portrait": portrait,
                     "task": "Return issues: list of nonempty strings, "
                             "must_revise: boolean, summary: string."},
        )
        issues = critical.get("issues", [])
        if not isinstance(issues, list) or not all(isinstance(x, str) and x.strip() for x in issues):
            raise ValueError("Invalid portrait critique")
        if not isinstance(critical.get("must_revise"), bool):
            raise ValueError("Portrait critic must decide revision need")
        critique_history.append({
            "round": round_number + 1,
            "issues": [x[:600] for x in issues[:12]],
            "must_revise": critical["must_revise"],
        })
        if not critical["must_revise"]:
            break
        revised = model.complete(
            role="portrait_reviser", system=PROFILE_SYSTEM,
            payload={
                "evidence": evidence,
                "previous_draft": portrait,
                "critique": critical,
                "task": "Produce the COMPLETE corrected research_lines, "
                        "unassigned_achievement_ids and changes_from_previous. "
                        "Keep all evidence links valid and reject unsupported claims."
            },
        )
        portrait = _validate_profile(revised, bundle)
    portrait["critique_history"] = critique_history
    portrait["generated_at"] = datetime.now(timezone.utc).isoformat()
    portrait["version_status"] = "provisional_not_official"
    portrait["input_counts"] = {
        "verified_team_outputs": len(bundle.achievements),
        "public_dataset_metadata": len(bundle.datasets),
        "external_papers": len(bundle.external_papers),
    }
    return portrait


def snapshot_for_line(bundle: EvidenceBundle, portrait: dict,
                      line_id: str) -> Snapshot:
    """Build research pipeline context from selected *revised* line.

    External references used for cited papers remain separate from team papers.
    If the line has no external papers, discovery must be enabled downstream.
    """
    line = next((line for line in portrait["research_lines"]
                 if line["id"] == line_id), None)
    if line is None:
        raise ValueError("Unknown synthesized research line")
    d_map = {d.id: d for d in bundle.datasets}
    p_map = {p.id: p for p in bundle.external_papers}
    papers = [Paper(
        id=p_map[x].id, title=p_map[x].title[:350],
        abstract=p_map[x].abstract, doi=p_map[x].doi,
        venue=p_map[x].venue
    ) for x in line["external_paper_ids"]]
    datasets = [Dataset(
        id=d_map[x].id, name=d_map[x].name,
        description=(d_map[x].description or "Metadata only; data access not verified"),
        fields=d_map[x].fields, sensitivity="public"
    ) for x in line["dataset_ids"]]
    return Snapshot(
        snapshot_id="profile-" + evidence_hash(bundle)[:20] + "-" + line_id,
        provenance="approved_export",
        research_line=ResearchLine(
            id=line_id, name=line["name"], problem=line["problem"],
            goals="Evidence-led research. Novelty is unverified. Existing outputs: " +
                  ", ".join(line["achievement_ids"][:8])
        ),
        papers=papers, datasets=datasets,
    )
