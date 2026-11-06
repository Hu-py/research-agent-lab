"""Supabase PostgREST writer for the isolated research knowledge graph.

All writes are opt-in. Source/edge IDs are deterministic; retries are
idempotent. Multi-table HTTP writes are not atomic: run the migration before
use, preflight all tables, and retry the same validated batch after failure.
Immutable history tables ignore duplicates rather than replacing old versions.
"""
from __future__ import annotations

from typing import Any

import httpx

from research_agent_lab.supabase_auth import headers, supabase_url
from research_agent_lab.knowledge_graph import GraphBatch

TABLES = (
    ("kg_sources", "sources", "scope,source_key", False),
    ("kg_nodes", "nodes", "scope,node_key", False),
    ("kg_edges", "edges", "scope,edge_key", False),
    ("kg_evidence", "evidence", "scope,evidence_key", True),
    ("kg_node_versions", "node_versions", "scope,version_key", True),
    ("kg_opportunity_versions", "opportunity_versions",
     "scope,run_id,candidate_key", True),
)


def check_graph_store(client: httpx.Client | None = None) -> None:
    """Read-only check for ALL required 004 migration tables."""
    owned = client is None
    http = client or httpx.Client(timeout=25, follow_redirects=False)
    try:
        for table, _, _, _ in TABLES:
            try:
                response = http.get(
                    supabase_url() + "/rest/v1/" + table,
                    headers=headers(), params={"select": "id", "limit": "0"}
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise RuntimeError(
                    f"{table} not accessible (HTTP {exc.response.status_code}). "
                    "Apply sql/004_research_knowledge_graph.sql to the isolated project."
                ) from None
            except httpx.TransportError:
                raise RuntimeError("Knowledge graph connectivity error") from None
    finally:
        if owned:
            http.close()


def persist_graph(batch: GraphBatch, *, client: httpx.Client | None = None,
                  preflight: bool = True) -> dict[str, int]:
    if not batch.scope:
        raise ValueError("Graph scope is required")
    if any(row.get("scope") != batch.scope for _, field, _, _ in TABLES
           for row in getattr(batch, field)):
        raise ValueError("Cross-scope graph write rejected")
    # Verify relationship endpoints and evidence sources before ANY mutation.
    node_ids = {node["id"] for node in batch.nodes}
    edge_ids = {edge["id"] for edge in batch.edges}
    source_ids = {source["id"] for source in batch.sources}
    for edge in batch.edges:
        if edge["from_node"] not in node_ids or edge["to_node"] not in node_ids:
            raise ValueError("Graph write has an unresolved edge endpoint")
    for ev in batch.evidence:
        if ev["edge_id"] not in edge_ids or ev["source_id"] not in source_ids:
            raise ValueError("Graph write has unresolved evidence provenance")
    for vers in batch.opportunity_versions:
        if vers["opportunity_node_id"] not in node_ids:
            raise ValueError("Opportunity version references an unknown node")
    owned = client is None
    http = client or httpx.Client(timeout=30, follow_redirects=False)
    try:
        if preflight:
            check_graph_store(client=http)
        # SOURCE -> NODE -> EDGE -> EVIDENCE -> VERSION dependency order.
        for table, field, unique, immutable in TABLES:
            rows = getattr(batch, field)
            for start in range(0, len(rows), 80):
                part = rows[start:start + 80]
                prefer = ("resolution=ignore-duplicates"
                          if immutable else "resolution=merge-duplicates")
                try:
                    response = http.post(
                        supabase_url() + "/rest/v1/" + table,
                        headers=headers(prefer=prefer + ",return=minimal"),
                        params={"on_conflict": unique},
                        json=part,
                    )
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise RuntimeError(
                        f"Knowledge graph write {table} HTTP {exc.response.status_code}. "
                        "Partial writes may exist; deterministic IDs allow safe retry."
                    ) from None
                except httpx.TransportError:
                    raise RuntimeError(
                        f"Knowledge graph write {table} transport error; "
                        "retry the same graph batch safely."
                    ) from None
        return batch.counts()
    finally:
        if owned:
            http.close()


def read_problem_neighborhood(scope: str, line_id: str,
                              *, max_edges: int = 30,
                              client: httpx.Client | None = None) -> dict:
    """Bounded server-side one-hop retrieval, not all-graph full-text export."""
    if not scope or not line_id or len(scope) > 150 or len(line_id) > 80:
        raise ValueError("Invalid graph read scope or line ID")
    owned = client is None
    http = client or httpx.Client(timeout=20, follow_redirects=False)
    try:
        root = http.get(
            supabase_url() + "/rest/v1/kg_nodes",
            headers=headers(),
            params={"select": "id,node_key,label,description",
                    "scope": "eq." + scope,
                    "node_key": "eq.research_problem:" + line_id,
                    "limit": "1"},
        )
        root.raise_for_status()
        matches = root.json()
        if not isinstance(matches, list) or not matches:
            return {"problem": None, "relationships": []}
        problem = matches[0]
        edges = http.get(
            supabase_url() + "/rest/v1/kg_edges",
            headers=headers(), params={
                "select": "relation,epistemic_status,to_node",
                "scope": "eq." + scope,
                "from_node": "eq." + problem["id"],
                "limit": str(max(0, min(100, max_edges))),
            },
        )
        edges.raise_for_status()
        rels = edges.json()
        if not isinstance(rels, list):
            raise RuntimeError("Unexpected graph edge response")
        node_ids = [str(x["to_node"]) for x in rels]
        linked = {}
        if node_ids:
            targets = http.get(
                supabase_url() + "/rest/v1/kg_nodes",
                headers=headers(), params={
                    "select": "id,node_key,label,epistemic_status",
                    "scope": "eq." + scope,
                    "id": "in.(" + ",".join(node_ids) + ")",
                    "limit": "100",
                },
            )
            targets.raise_for_status()
            target_rows = targets.json()
            if not isinstance(target_rows, list):
                raise RuntimeError("Unexpected graph node response")
            linked = {row["id"]: row for row in target_rows}
        return {
            "problem": problem,
            "relationships": [
                {"relation": rel["relation"],
                 "status": rel["epistemic_status"],
                 "node": linked.get(rel["to_node"])}
                for rel in rels if rel["to_node"] in linked
            ],
        }
    finally:
        if owned:
            http.close()
