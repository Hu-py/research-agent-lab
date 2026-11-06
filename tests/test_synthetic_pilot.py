from research_agent_lab.frontier.synthetic_pilot import (
    run_synthetic_network_pilot, can_run_network_pilot
)


def test_fixed_code_synthetic_pilot_is_deterministic_and_bounded():
    first = run_synthetic_network_pilot()
    again = run_synthetic_network_pilot()
    assert first == again
    assert first["n_scenario_cells"] == 18
    assert first["n_generated_experiments"] == 108
    assert first["total_monotonicity_violations"] == 0
    assert not first["raw_research_data_used"]
    assert not first["experimental_claim_verified"]
    assert not first["published_indicator_implementations_used"]
    for row in first["results"]:
        seq=row["performance_ratio_by_intensity"]
        assert len(seq)==6
        assert seq[0] == 1.0
        assert all(seq[i] >= seq[i+1] for i in range(5))


def test_sanity_protocol_skips_unrelated_research_lines():
    assert can_run_network_pilot("resilience_measurement")
    assert not can_run_network_pilot("vertical_building_functions")
