"""Scientific validity gate and optional executable, leakage-aware CSV pilot.

Pilot is intentionally narrow, fixed code. NEVER execute model-generated Python.
"""
from __future__ import annotations

import csv
import hashlib
import math
from pathlib import Path

from research_agent_lab.contracts import Snapshot
from research_agent_lab.model import BudgetedModel

SYSTEM = (
    "You are a skeptical methodology reviewer. An Elo winner and LLM scores "
    "are not proof. Detect unsupported novelty claims, data access assumptions, "
    "leakage, missing baselines and untestable predictions. Return JSON."
)


def validate_scientifically(snapshot: Snapshot, winner: dict,
                            model: BudgetedModel) -> dict:
    paper_ids = {p.id for p in snapshot.papers}
    data = {x.id: x for x in snapshot.datasets}
    if not winner["paper_ids"] or not set(winner["paper_ids"]) <= paper_ids:
        raise ValueError("Winner has unknown paper evidence")
    if not set(winner["dataset_ids"]) <= set(data):
        raise ValueError("Winner has unknown dataset evidence")
    if not winner["baselines"] or not winner["falsifiable_prediction"]:
        raise ValueError("Winner lacks baseline or falsifiable claim")

    raw = model.complete(
        role="scientific_validator", system=SYSTEM,
        payload={
            "snapshot": snapshot.model_dump(mode="json"),
            "winner": winner,
            "task": "Return structured plan: "
                    "hypothesis_test (nonempty JSON string), primary_metric (nonempty JSON string), "
                    "baselines (nonempty array of nonempty strings), ablations (nonempty array of nonempty strings), "
                    "split_strategy (nonempty JSON string), failure_criteria (nonempty JSON string), "
                    "evidence_limitations (nonempty array of nonempty strings), "
                    "data_feasible (boolean), proposed_field_mapping (object). "
                    "Use the exact top-level keys above. Express H0 and H1 together in the "
                    "hypothesis_test string. Do not nest objects in text fields. "
                    "If NO registered datasets exist, data_feasible=false and "
                    "proposed_field_mapping={} because access cannot be assumed.",
        },
    )
    required = ("hypothesis_test", "primary_metric", "split_strategy", "failure_criteria")
    for field in required:
        if not isinstance(raw.get(field), str) or not raw[field].strip():
            raise ValueError("Invalid science validation field " + field)
    for field in ("baselines", "ablations", "evidence_limitations"):
        if not isinstance(raw.get(field), list) or not raw[field] or not all(
            isinstance(x, str) and x.strip() for x in raw[field]
        ):
            raise ValueError("Science validation requires " + field)
    if not isinstance(raw.get("data_feasible"), bool) or not isinstance(
        raw.get("proposed_field_mapping"), dict
    ):
        raise ValueError("Invalid field mapping or feasibility")
    # A model cannot grant data permissions or override registered fields.
    mapping = raw["proposed_field_mapping"]
    if mapping:
        dataset_id = mapping.get("dataset_id")
        listed = data.get(dataset_id)
        if listed is None:
            raise ValueError("Science validation proposed unregistered dataset")
        for key in ("target", "group"):
            val = mapping.get(key)
            if val and val not in listed.fields:
                raise ValueError("Science validation proposed nonexistent " + key)
        features = mapping.get("features", [])
        if not isinstance(features, list) or not set(features) <= set(listed.fields):
            raise ValueError("Science validation proposed unregistered features")
    # Model self-assessment cannot grant access to data. A catalogue entry,
    # field description or F-drive checkmark is NOT a permission grant.
    legal_data_access = bool(winner["dataset_ids"]) and all(
        data[asset_id].access_verified for asset_id in winner["dataset_ids"]
    )
    model_assessment = bool(raw["data_feasible"])
    return {
        "hypothesis_test": raw["hypothesis_test"][:1400],
        "primary_metric": raw["primary_metric"][:250],
        "baselines": raw["baselines"][:12],
        "ablations": raw["ablations"][:12],
        "split_strategy": raw["split_strategy"][:650],
        "failure_criteria": raw["failure_criteria"][:700],
        "evidence_limitations": raw["evidence_limitations"][:12],
        "data_feasible_assessment": model_assessment and legal_data_access,
        "data_feasible_model_opinion": model_assessment,
        "dataset_access_evidence_verified": legal_data_access,
        "proposed_field_mapping": mapping,
        "registered_dataset_metadata_only": True,
        "novelty_verified": False,
        "experimental_claim_verified": False,
    }


def run_csv_pilot(snapshot: Snapshot, manifest: dict, *,
                  max_rows: int = 5000) -> dict:
    """Fixed-code grouped holdout baseline vs univariate OLS.

    Explicit local manifest with dataset_id, path, target, feature, group.
    No generated code, no raw rows in the result. Not a scientific discovery.
    """
    dataset = next((d for d in snapshot.datasets
                    if d.id == manifest.get("dataset_id")), None)
    if dataset is None:
        raise ValueError("Pilot dataset is not registered")
    fields = [manifest.get(k) for k in ("target", "feature", "group")]
    if not all(isinstance(x, str) and x in dataset.fields for x in fields):
        raise ValueError("Pilot fields must be pre-registered dataset metadata")
    target, feature, group = fields
    if len(set(fields)) != 3:
        raise ValueError("Pilot target/feature/group must be distinct")
    path = Path(str(manifest.get("path", ""))).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != ".csv" or path.stat().st_size > 15_000_000:
        raise ValueError("Pilot CSV missing, too large or not a CSV")
    parsed = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if not {target, feature, group} <= set(reader.fieldnames or []):
            raise ValueError("Pilot CSV missing registered fields")
        for idx, row in enumerate(reader):
            if idx >= max_rows:
                break
            try:
                y, x = float(row[target]), float(row[feature])
                g = row[group]
            except (TypeError, ValueError, KeyError):
                continue
            if not math.isfinite(x) or not math.isfinite(y) or not g:
                continue
            parsed.append((g, x, y))
    if len(parsed) < 40:
        raise ValueError("Pilot requires >=40 valid rows")
    group_ids = sorted({g for g, _, _ in parsed})
    if len(group_ids) < 10:
        raise ValueError("Pilot needs >=10 distinct spatial/temporal holdout groups")
    held_out = {g for g in group_ids if int(hashlib.sha256(g.encode()).hexdigest(), 16) % 5 == 0}
    if len(held_out) < 2 or len(held_out) > len(group_ids) - 2:
        held_out = set(group_ids[::5])
    train = [(x, y) for g, x, y in parsed if g not in held_out]
    test = [(x, y) for g, x, y in parsed if g in held_out]
    if len(train) < 20 or len(test) < 10:
        raise ValueError("Too few group-held-out training/testing records")
    mean_y = sum(y for _, y in train) / len(train)
    mean_x = sum(x for x, _ in train) / len(train)
    denominator = sum((x - mean_x) ** 2 for x, _ in train)
    slope = (sum((x - mean_x) * (y - mean_y) for x, y in train) /
             denominator) if denominator > 1e-12 else 0.0
    intercept = mean_y - slope * mean_x

    def scores(pred):
        mse = sum((y - pred(x)) ** 2 for x, y in test) / len(test)
        denom = sum((y - mean_y) ** 2 for _, y in test)
        r2 = 1 - mse * len(test) / denom if denom > 1e-12 else None
        return {"rmse": round(math.sqrt(mse), 6),
                "r2": round(r2, 6) if r2 is not None else None}

    return {
        "status": "executed_pilot_not_confirmatory",
        "dataset_id": dataset.id,
        "split": "SHA256-stable grouped holdout, approximately 20% groups",
        "training_rows": len(train),
        "testing_rows": len(test),
        "training_groups": len(group_ids) - len(held_out),
        "testing_groups": len(held_out),
        "baseline_mean": scores(lambda x: mean_y),
        "single_feature_ols": scores(lambda x: intercept + slope * x),
        "warning": "Single-feature grouped pilot; not proof of causality, generalization or novelty. "
                   "No arbitrary LLM-generated code was executed.",
    }
