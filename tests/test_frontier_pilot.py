import csv
from pathlib import Path

import pytest

from research_agent_lab.frontier.science import run_csv_pilot
from research_agent_lab.contracts import Snapshot


def demo():
    return Snapshot.model_validate_json(
        (Path(__file__).resolve().parents[1] / "examples" /
         "synthetic_snapshot.json").read_text(encoding="utf-8")
    )


def test_executable_grouped_pilot(tmp_path):
    path = tmp_path / "pilot.csv"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["segment_id", "x", "y", "synthetic_target"])
        writer.writeheader()
        for g in range(20):
            for i in range(12):
                x = g + i * 0.25
                writer.writerow({"segment_id": f"group-{g}", "x": x,
                                 "y": "0", "synthetic_target": 4 * x + 3})
    res = run_csv_pilot(demo(), {
        "dataset_id": "demo-data-1", "path": str(path),
        "target": "synthetic_target", "feature": "x", "group": "segment_id"
    })
    assert res["status"] == "executed_pilot_not_confirmatory"
    assert res["single_feature_ols"]["rmse"] <= res["baseline_mean"]["rmse"]
    assert res["training_groups"] + res["testing_groups"] == 20
    assert "rows" not in res


def test_no_nonregistered_fields(tmp_path):
    with pytest.raises(ValueError, match="registered"):
        run_csv_pilot(demo(), {"dataset_id": "demo-data-1", "path": "x.csv",
                               "target": "secret", "feature": "x",
                               "group": "segment_id"})
