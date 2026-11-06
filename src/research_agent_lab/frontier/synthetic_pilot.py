"""Deterministic, bounded scientific smoke pilot; no datasets, no LLM code execution.

One narrow protocol for network-resilience *software sanity checking*. It does
NOT implement published flood-resilience indices or establish H003 validity.
The intervention graph and damage fields are intentionally toy examples.
"""
from __future__ import annotations

from collections import deque
import hashlib
import math


def _graphs() -> dict[str, tuple[int, list[tuple[int, int]]]]:
    grid = []
    for y in range(4):
        for x in range(4):
            n = y * 4 + x
            if x < 3: grid.append((n, n + 1))
            if y < 3: grid.append((n, n + 4))
    # The second network models dense hub-and-spoke; it is NOT observed
    # commuter OD behavior and must never be presented as a real OD matrix.
    commute = sorted({tuple(sorted((a, b))) for a, b in
                      ([(0, j) for j in range(1, 12)] +
                       [(j, j + 1) for j in range(1, 11)] +
                       [(2, 8), (4, 10), (3, 7)])})
    rail = [(i, i + 1) for i in range(9)] + [(1, 5), (3, 8)]
    return {"street_grid_toy": (16, grid),
            "commute_hub_toy": (12, commute),
            "rail_chain_toy": (10, rail)}


def _efficiency(n: int, edges: list[tuple[int, int]]) -> float:
    adj = [[] for _ in range(n)]
    for a, b in edges:
        adj[a].append(b)
        adj[b].append(a)
    total = 0.0
    for start in range(n):
        dist = [-1] * n
        dist[start] = 0
        q = deque([start])
        while q:
            a = q.popleft()
            for b in adj[a]:
                if dist[b] == -1:
                    dist[b] = dist[a] + 1
                    q.append(b)
        total += sum(1 / d for d in dist if d > 0)
    return total / (n * (n - 1))


def _rank_edges(edges: list[tuple[int, int]], pattern: str, graph: str) -> list[tuple[int,int]]:
    if pattern == "concentrated":
        # A fixed virtual center, no actual geolocation.
        return sorted(edges, key=lambda ab: (
            abs((ab[0] + ab[1]) / 2 - 5.0), ab
        ))
    return sorted(edges, key=lambda ab: hashlib.sha256(
        f"toy-v1|{graph}|{ab[0]}|{ab[1]}".encode()
    ).hexdigest())


def run_synthetic_network_pilot() -> dict:
    """3 toy topologies x 2 patterns x 3 restoration settings x 6 levels.

    Uses fixed-code connectivity/efficiency only. No real data read, no 
    random LLM-generated code, and no numerical claim about published indices.
    """
    comparisons = []
    violations = 0
    for layer, (n, original) in _graphs().items():
        reference = _efficiency(n, original)
        assert reference > 0
        for pattern in ("concentrated", "distributed"):
            ranked = _rank_edges(original, pattern, layer)
            for restoration in (0, 1, 3):
                series = []
                for intensity in range(6):
                    damaged_count = math.floor(
                        len(original) * (intensity / 5.0) * 0.7 /
                        (1.0 + 0.25 * restoration)
                    )
                    removed = set(ranked[:damaged_count])
                    kept = [e for e in original if e not in removed]
                    efficiency = _efficiency(n, kept)
                    series.append(round(efficiency / reference, 8))
                bad = sum(series[i] > series[i-1] + 1e-8
                          for i in range(1,len(series)))
                violations += bad
                comparisons.append({
                    "layer": layer, "disturbance_pattern": pattern,
                    "restoration_parameter": restoration,
                    "performance_ratio_by_intensity": series,
                    "monotonicity_violations": bad,
                })
    return {
        "status": "executed_synthetic_software_sanity_only",
        "recipe": "toy_network_resilience_v1",
        "n_generated_experiments": len(comparisons) * 6,
        "n_scenario_cells": len(comparisons),
        "damage_levels": [0,1,2,3,4,5],
        "patterns": ["concentrated","distributed"],
        "restoration_parameters": [0,1,3],
        "toy_layers": list(_graphs()),
        "total_monotonicity_violations": violations,
        "results": comparisons,
        "raw_research_data_used": False,
        "external_network_data_used": False,
        "published_indicator_implementations_used": False,
        "experimental_claim_verified": False,
        "data_access_verified": False,
        "warning": (
            "This is a fixed-code toy graph stress test only. Monotonicity of "
            "basic shortest-path efficiency under nested edge removal is "
            "largely a construction property, NOT evidence that any published "
            "urban flood resilience metric is valid, invalid or novel."
        ),
    }


def can_run_network_pilot(research_line_id: str) -> bool:
    """Explicitly narrow topical applicability; skip unsupported fields."""
    return "resilience" in research_line_id.casefold() or "韧性" in research_line_id
