"""Build an evidence-grounded research knowledge graph without LLM inference.

The portrait/frontier agents propose claims; this module creates explicitly
PROVISIONAL nodes and source-constrained edges. No model score promotes a
scientific claim to 'human_verified'.

All IDs are deterministic per scope and evidence key, supporting idempotent
updates without replacing the immutable versions.
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Any

from research_agent_lab.portrait import EvidenceBundle, evidence_hash

NAMESPACE = uuid.UUID("413e70be-1d78-46ef-8143-f8e28b012e36")
WRITER = "research-agent-lab/kg-v1"


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _uuid(scope: str, category: str, key: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{scope}|{category}|{key}"))


def _method_key(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name).casefold().strip()
    if not normalized:
        raise ValueError("Empty method name")
    return "method:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:24]


@dataclass
class GraphBatch:
    scope: str
    sources: list[dict] = field(default_factory=list)
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    node_versions: list[dict] = field(default_factory=list)
    opportunity_versions: list[dict] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)

    def counts(self) -> dict:
        return {key: len(getattr(self, key)) for key in (
            "sources", "nodes", "edges", "evidence",
            "node_versions", "opportunity_versions"
        )}


class GraphBuilder:
    def __init__(self, scope: str, *, profile_version_id: str | None = None,
                 evidence_digest: str = ""):
        if not scope or len(scope) > 150:
            raise ValueError("Invalid research scope")
        if profile_version_id is not None:
            profile_version_id = str(uuid.UUID(str(profile_version_id)))
        self.batch = GraphBatch(scope=scope)
        self.profile_version_id = profile_version_id
        self.evidence_digest = evidence_digest
        self._sources: set[str] = set()
        self._nodes: set[str] = set()
        self._edges: set[str] = set()
        self._evidence: set[str] = set()
        self._versions: set[str] = set()

    @property
    def scope(self) -> str:
        return self.batch.scope

    def source(self, key: str, kind: str, label: str, reference: str = "",
               metadata: dict | None = None) -> str:
        ident = _uuid(self.scope, "source", key)
        if key not in self._sources:
            self._sources.add(key)
            provenance = metadata or {}
            self.batch.sources.append({
                "id": ident, "scope": self.scope, "source_key": key,
                "kind": kind, "reference": reference[:500],
                "label": label[:350], "source_hash": _digest(
                    [kind, label, reference, provenance]
                ),
                "provenance": provenance,
            })
        return ident

    def node(self, key: str, kind: str, label: str, description: str = "",
             *, status: str = "proposed", attributes: dict | None = None,
             change_reason: str = "Evidence re-evaluated") -> str:
        ident = _uuid(self.scope, "node", key)
        if key in self._nodes:
            return ident
        self._nodes.add(key)
        attrs = attributes or {}
        payload = {
            "id": ident, "scope": self.scope, "node_key": key,
            "kind": kind, "label": label[:350],
            "description": description[:1500], "attributes": attrs,
            "epistemic_status": status,
        }
        content_hash = _digest({k: v for k, v in payload.items() if k != "id"})
        self.batch.nodes.append({**payload, "source_hash": content_hash})
        version_key = f"{key}:{self.evidence_digest[:16]}:{content_hash[:20]}"
        if version_key not in self._versions:
            self._versions.add(version_key)
            self.batch.node_versions.append({
                "id": _uuid(self.scope, "node_version", version_key),
                "scope": self.scope, "version_key": version_key,
                "node_id": ident,
                "portrait_version_id": self.profile_version_id,
                "evidence_hash": self.evidence_digest or content_hash,
                "payload": {k: v for k, v in payload.items()
                            if k not in ("scope", "id")},
                "change_reason": change_reason[:600],
            })
        return ident

    def edge(self, from_key: str, to_key: str, relation: str, *,
             source_key: str, evidence_level: str, status: str = "inferred",
             rationale: str = "") -> None:
        if from_key not in self._nodes or to_key not in self._nodes:
            raise ValueError("Edge endpoints must be registered in this graph batch")
        if source_key not in self._sources:
            raise ValueError("Every edge must reference an existing evidence source")
        if from_key == to_key:
            raise ValueError("Self-linked evidence relation")
        edge_key = f"{from_key}|{relation}|{to_key}"
        edge_id = _uuid(self.scope, "edge", edge_key)
        if edge_key not in self._edges:
            self._edges.add(edge_key)
            self.batch.edges.append({
                "id": edge_id, "scope": self.scope,
                "edge_key": edge_key,
                "from_node": _uuid(self.scope, "node", from_key),
                "to_node": _uuid(self.scope, "node", to_key),
                "relation": relation, "epistemic_status": status,
                "rationale": rationale[:900],
                "source_hash": _digest([relation, status, rationale, source_key]),
            })
        evidence_key = f"{edge_key}|{source_key}|{evidence_level}"
        if evidence_key not in self._evidence:
            self._evidence.add(evidence_key)
            self.batch.evidence.append({
                "id": _uuid(self.scope, "evidence", evidence_key),
                "scope": self.scope, "evidence_key": evidence_key,
                "edge_id": edge_id,
                "source_id": _uuid(self.scope, "source", source_key),
                "evidence_level": evidence_level,
                "statement": rationale[:800],
                "locator": source_key[:400],
                "generated_by": WRITER,
            })


def portrait_graph(bundle: EvidenceBundle, portrait: dict,
                   *, profile_version_id: str | None = None) -> GraphBatch:
    """Represent four interconnected perspectives, with strict provenance.

    No database writes. Every team output is kept and associated with at
    least one problem or explicitly unassigned, never silently dropped.
    """
    hashed = evidence_hash(bundle)
    if portrait.get("source_evidence_hash") != hashed:
        raise ValueError("Portrait and authorized evidence bundle hashes differ")
    b = GraphBuilder(bundle.bundle_id, profile_version_id=profile_version_id,
                     evidence_digest=hashed)
    profile_key = "portrait:" + hashed[:24]
    b.source(profile_key, "portrait_version", "Evidence-first portrait",
             metadata={"provisional": True, "bundle_id": bundle.bundle_id})
    achievements = {a.id: a for a in bundle.achievements}
    datasets = {d.id: d for d in bundle.datasets}
    papers = {p.id: p for p in bundle.external_papers}
    used_achievements = set()
    for a in bundle.achievements:
        source_key = "team_output:" + a.id
        b.source(source_key, "team_output", a.title,
                 reference=a.doi, metadata={
                     "year": a.year, "kind": a.kind,
                     "evidence_level": a.evidence_level,
                     "ownership": "verified_team_output",
                 })
        b.node(source_key, "team_output", a.title,
               status="described", attributes={
                   "year": a.year, "verified_record": True,
                   "method_claim_verified": False,
               })
    for d in bundle.datasets:
        key = "data_asset:" + d.id
        b.source(key, "dataset_metadata", d.name, metadata={
            "sensitivity": d.sensitivity, "access_verified": d.access_verified,
            "period": d.period, "coverage": d.coverage,
        })
        b.node(key, "data_asset", d.name, description=d.description,
               status="described", attributes={
                   "category": d.category, "period": d.period,
                   "coverage": d.coverage, "field_names": d.fields,
                   "access_verified": d.access_verified,
                   "sensitivity": d.sensitivity,
               })
    for p in bundle.external_papers:
        key = "external_paper:" + p.id
        b.source(key, "external_paper", p.title, reference=p.doi,
                 metadata={"venue": p.venue, "team_owned": False})
        b.node(key, "external_paper", p.title,
               status="described", attributes={
                   "venue": p.venue, "doi": p.doi,
                   "team_owned": False,
               })
    for line in portrait.get("research_lines", []):
        line_id = line.get("id")
        if not isinstance(line_id, str) or not line_id:
            raise ValueError("Missing research line ID")
        key = "research_problem:" + line_id
        b.node(key, "research_problem", line["name"], line["problem"],
               status=("title_inferred" if line.get("evidence_status") ==
                       "title_based_inference" else "proposed"),
               attributes={
                   "line_id": line_id,
                   "open_questions": line.get("open_questions", [])[:8],
                   "evidence_status": line.get("evidence_status", "inferred"),
                   "novelty_verified": False,
               },
               change_reason="Research problem regrouped from verified outputs")
        for aid in line.get("achievement_ids", []):
            if aid not in achievements:
                raise ValueError("Unknown team achievement in portrait graph")
            used_achievements.add(aid)
            a = achievements[aid]
            b.edge(key, "team_output:" + aid, "BASED_ON_OUTPUT",
                   source_key="team_output:" + aid,
                   evidence_level=a.evidence_level,
                   status=("described" if a.evidence_level in ("abstract", "fulltext")
                           else "inferred"),
                   rationale="Team research line cites an owned output; "
                             "topic linkage is provisional.")
        for did in line.get("dataset_ids", []):
            if did not in datasets:
                raise ValueError("Unknown data asset in portrait graph")
            b.edge(key, "data_asset:" + did, "POTENTIALLY_USES_DATA",
                   source_key="data_asset:" + did, evidence_level="catalogue_metadata",
                   rationale="Dataset catalogue suggests potential applicability; "
                             "raw data access is not inferred.")
        for pid in line.get("external_paper_ids", []):
            if pid not in papers:
                raise ValueError("Unknown external literature in portrait graph")
            p = papers[pid]
            b.edge(key, "external_paper:" + pid, "CONSIDERS_LITERATURE",
                   source_key="external_paper:" + pid,
                   evidence_level="abstract" if p.abstract else "title_only",
                   rationale="External literature may inform this problem; "
                             "it does not prove team capability.")
        for method in line.get("methods", []):
            if not isinstance(method, str):
                raise ValueError("Invalid method in research portrait")
            method = method.strip()
            if not method:
                continue
            mk = _method_key(method)
            b.node(mk, "research_method", method,
                   status="proposed", attributes={
                       "team_capability_verified": False,
                       "inferred_from_research_portrait": True,
                   },
                   change_reason="Proposed methodological capability, not verified")
            b.edge(key, mk, "PROPOSES_METHOD", source_key=profile_key,
                   evidence_level="agent_inferred",
                   rationale="LLM-derived method association; requires independent "
                             "method-section or code verification.")
    claimed = set(portrait.get("unassigned_achievement_ids", []))
    if used_achievements & claimed or used_achievements | claimed != set(achievements):
        raise ValueError("Every team output must be assigned or explicitly unassigned")
    b.batch.diagnostics = {
        "evidence_hash": hashed, "unassigned_achievement_ids": sorted(claimed),
        "source_verified_methods": 0,
        "science_claims_human_verified": 0,
        "current_research_lines": len(portrait.get("research_lines", [])),
    }
    return b.batch


def opportunity_graph(bundle: EvidenceBundle, portrait: dict, run: dict) -> GraphBatch:
    """Bind an entire immutable hypothesis genealogy to the evidence-led graph.

    Only valid IDs are linked, and references not in the approved bundle are
    listed as unresolved, not silently re-labeled as verified literature.
    Must be stored AFTER lab_frontier_runs is persisted (FK constraint).
    """
    if str(run.get("line_id", "")) not in {
        x.get("id") for x in portrait.get("research_lines", [])
    }:
        raise ValueError("Frontier run line does not belong to this portrait")
    run_id = str(uuid.UUID(str(run["run_id"])))
    b = GraphBuilder(bundle.bundle_id, evidence_digest=evidence_hash(bundle))
    prior = portrait_graph(bundle, portrait)
    # Include the source and node rows as part of each self-contained upsert.
    for typ in ("sources", "nodes", "edges", "evidence", "node_versions"):
        getattr(b.batch, typ).extend(getattr(prior, typ))
    b._sources = {x["source_key"] for x in b.batch.sources}
    b._nodes = {x["node_key"] for x in b.batch.nodes}
    b._edges = {x["edge_key"] for x in b.batch.edges}
    b._evidence = {x["evidence_key"] for x in b.batch.evidence}
    b._versions = {x["version_key"] for x in b.batch.node_versions}
    source_key = "frontier_run:" + run_id
    b.source(source_key, "frontier_run", "Research Agent Lab experiment " + run_id,
             metadata={"run_id": run_id, "llm_assessed_only": True})
    candidates = run.get("ranked_candidates", []) + run.get("archived_candidates", [])
    if not candidates or not isinstance(candidates, list):
        raise ValueError("Frontier result has no candidates")
    candidate_ids = [str(c.get("id", "")) for c in candidates]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("Duplicate candidate IDs in frontier result")
    ids = set(candidate_ids)
    selected_id = run.get("winner", {}).get("id")
    missing_refs: set[str] = set()
    for c in candidates:
        candidate_id = str(c["id"])
        node_key = f"opportunity:{run_id}:{candidate_id}"
        b.node(node_key, "research_opportunity", c["title"], c.get("question", ""),
               status="proposed", attributes={
                   "generation": c["generation"],
                   "elo_is_llm_preference_only": True,
                   "human_review_required": True,
               }, change_reason="Candidate generated or evolved by agent tournament")
    for c in candidates:
        candidate_id = str(c["id"])
        node_key = f"opportunity:{run_id}:{candidate_id}"
        current_status = c.get("status", "candidate")
        if current_status not in ("candidate", "archived"):
            raise ValueError("Unknown candidate state")
        parents = c.get("parent_ids", [])
        if not isinstance(parents, list) or not set(parents) <= ids:
            raise ValueError("Candidate refers to unknown ancestors")
        for parent in parents:
            b.edge(node_key, f"opportunity:{run_id}:{parent}", "EVOLVED_FROM",
                   source_key=source_key, evidence_level="agent_inferred",
                   rationale="Recorded agent version lineage")
        b.edge(node_key, "research_problem:" + run["line_id"], "ADDRESSES",
               source_key=source_key, evidence_level="agent_inferred",
               rationale="Proposed hypothesis addresses this team research problem.")
        for did in c.get("dataset_ids", []):
            if did in {d.id for d in bundle.datasets}:
                b.edge(node_key, "data_asset:" + did, "REQUIRES_DATA",
                       source_key=source_key, evidence_level="agent_inferred",
                       rationale="Hypothesis proposes this dataset; access not verified.")
            else:
                missing_refs.add("data:" + str(did))
        for pid in c.get("paper_ids", []):
            if pid in {p.id for p in bundle.external_papers}:
                b.edge(node_key, "external_paper:" + pid, "CITES_LITERATURE",
                       source_key=source_key, evidence_level="agent_inferred",
                       rationale="Agent references registered external literature; "
                                 "claim verification remains outstanding.")
            else:
                missing_refs.add("paper:" + str(pid))
        outcome = ("selected" if candidate_id == selected_id and current_status ==
                   "candidate" else current_status)
        b.batch.opportunity_versions.append({
            "id": _uuid(bundle.bundle_id, "opportunity_version",
                        f"{run_id}|{candidate_id}"),
            "scope": bundle.bundle_id,
            "opportunity_node_id": _uuid(bundle.bundle_id, "node", node_key),
            "run_id": run_id,
            "candidate_key": candidate_id,
            "generation": int(c["generation"]),
            "parent_candidate_keys": parents,
            "outcome": outcome,
            "elo": c.get("elo"),
            "payload": {
                "title": c["title"], "question": c.get("question", ""),
                "mechanism": c.get("mechanism", ""),
                "falsifiable_prediction": c.get("falsifiable_prediction", ""),
                "method": c.get("method", ""),
                "minimal_experiment": c.get("minimal_experiment", ""),
                "baselines": c.get("baselines", []),
                "paper_ids": c.get("paper_ids", []),
                "dataset_ids": c.get("dataset_ids", []),
                "limitations": c.get("limitations", []),
                "novelty_verified": False,
            },
        })
    b.batch.diagnostics = {
        "unresolved_frontier_references": sorted(missing_refs),
        "opportunity_versions": len(b.batch.opportunity_versions),
        "research_line_id": run["line_id"],
        "scientific_quality_verified": False,
    }
    return b.batch


def problem_context(batch: GraphBatch, line_id: str, *, limit: int = 12) -> dict:
    """Local 1-hop retrieval to ground Agent selection in explicit relationships."""
    key = "research_problem:" + line_id
    nodes = {n["id"]: n for n in batch.nodes}
    problems = [n for n in batch.nodes if n["node_key"] == key]
    if not problems:
        raise ValueError("Research line is not in the graph")
    p = problems[0]
    linked = []
    for edge in batch.edges:
        if edge["from_node"] == p["id"] and edge["to_node"] in nodes:
            other = nodes[edge["to_node"]]
            linked.append({
                "relation": edge["relation"], "target": other["label"],
                "target_key": other["node_key"],
                "status": edge["epistemic_status"],
                "evidence_ids": [x["source_id"] for x in batch.evidence
                                 if x["edge_id"] == edge["id"]],
            })
    return {
        "problem": {"id": key, "name": p["label"],
                    "question": p["description"]},
        "relationships": linked[:max(0, min(40, limit))],
        "claims_human_verified": False,
    }
