"""Regression stress suite is fully offline and reproducible."""
from research_agent_lab.frontier.v2.stress import PROFILES, run_stress


def test_all_resource_profiles_preserve_trust_guards():
    report = run_stress()
    assert report["case_count"] == 33
    assert report["failed_count"] == 0, [
        x for x in report["cases"] if not x["passed"]
    ]
    assert report["paid_llm_calls"] == 0
    assert report["scientific_quality_evaluated"] is False


def test_limits_are_independent_and_synthetic():
    assert PROFILES["minimal"].global_backtracks == 0
    assert PROFILES["default"].hypothesis_revisions == 2
    assert PROFILES["exploratory"].max_operations == 80
