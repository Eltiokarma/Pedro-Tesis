"""Observation sampling is an output operation, not a change of dynamics."""
import copy

import pytest

import dynamic_tank as tank


def case():
    config = tank.default_case()
    config["controller"]["enabled"] = False
    config["simulation"].update(duration_s=60., output_interval_s=20., max_step_s=3.)
    config["events"] = [{"time_s": 12.3, "changes": {"valve_opening": .8}}]
    return config


def test_dense_observation_samples_preserve_solver_and_boundaries():
    config = case()
    original = copy.deepcopy(config)
    baseline = tank.simulate_dynamic_tank(config)
    sampled = tank.simulate_dynamic_tank(config, sample_times_s=[0., 4.7, 12.3, 12.31, 60.])
    assert config == original
    assert sampled["summary"]["success"]
    assert sampled["summary"]["rhs_evaluations"] == baseline["summary"]["rhs_evaluations"]
    assert sampled["series"][-1] == baseline["series"][-1]
    rows = {row["time_s"]: row for row in sampled["series"]}
    assert set(rows) == {0., 4.7, 12.3, 12.31, 20., 40., 60.}
    assert rows[12.3]["valve_opening"] == .8
    assert sampled["metadata"]["requested_sample_times_s"] == [0., 4.7, 12.3, 12.31, 60.]
    assert "requested_sample_times_s" not in baseline["metadata"]


@pytest.mark.parametrize("samples", [
    "4.7", [True], [float("nan")], [float("inf")], [-1.], [61.],
    [4.7, 4.7], [20., 10.], {4.7},
])
def test_invalid_observation_grid_is_rejected(samples):
    with pytest.raises(ValueError, match="sample_times_s"):
        tank.simulate_dynamic_tank(case(), sample_times_s=samples)


def test_combined_sampling_budget_is_enforced(monkeypatch):
    monkeypatch.setattr(tank, "MAX_SAMPLES", 15)
    # Sixteen distinct timestamps after merging default, event and requested grids.
    with pytest.raises(ValueError, match="exceden"):
        tank.simulate_dynamic_tank(case(), sample_times_s=list(range(1, 13)))


def test_stopped_run_does_not_extrapolate_requested_samples():
    config = case()
    config["tank"].update(initial_mass_kg=10., min_mass_kg=5.)
    config["inputs"]["outlet_flow_kg_s"] = 1.
    result = tank.simulate_dynamic_tank(config, sample_times_s=[2.3, 4.9, 5.1, 60.])
    assert result["summary"]["status"] == "limit"
    assert result["series"][-1]["time_s"] == pytest.approx(5., abs=1e-9)
    assert all(row["time_s"] <= 5. + 1e-9 for row in result["series"])
