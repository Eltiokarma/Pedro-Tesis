import copy
import json

import numpy as np
import pytest

import dynamic_heat_exchanger as hx
from dynamic_heat_exchanger_examples import example_cases, matrix_reference, steady_reference, transport_outlet_reference


@pytest.fixture
def case():
    c = hx.default_case()
    c["cells"] = 4
    c["simulation"].update(duration_s=120., output_interval_s=3., max_step_s=4.)
    return c


def profiles(result):
    return np.array([r["hot_temperature_K"]+r["cold_temperature_K"]+r["wall_temperature_K"] for r in result["series"]])


@pytest.mark.parametrize("arrangement", ["co_current", "counter_current"])
@pytest.mark.parametrize("method", ["BDF", "Radau"])
def test_independent_profiles_with_unequal_properties_and_initial_gradients(case, arrangement, method):
    case["flow_arrangement"] = arrangement
    case["cold_fluid"].update(density_kg_m3=830., cp_J_kg_K=2300.)
    case["geometry"].update(cold_cross_area_m2=.007, cold_heat_area_m2=1.2)
    case["inputs"]["cold_flow_kg_s"] = .13
    case["initial"].update(hot_temperature_K=[345., 335., 325., 315.], cold_temperature_K=[310., 305., 300., 295.],
                           wall_temperature_K=[320., 318., 316., 314.])
    case["simulation"]["method"] = method
    case["events"] = [{"time_s": 31.25, "changes": {"hot_inlet_temperature_K": 350., "cold_flow_kg_s": .19}},
                      {"time_s": 83.4, "changes": {"cold_inlet_temperature_K": 305.}}]
    original = copy.deepcopy(case)
    result = hx.simulate_heat_exchanger(case)
    assert case == original
    assert result["summary"]["success"], result["summary"]
    reference = matrix_reference(case, [r["time_s"] for r in result["series"]])
    assert np.max(np.abs(profiles(result)-reference)) < 2e-4
    assert result["audit"]["max_energy_residual_relative"] < 1e-10
    assert result["audit"]["max_energy_rate_residual_relative"] < 1e-12
    assert np.min(profiles(result)) >= 295.-1e-7
    assert np.max(profiles(result)) <= 360.+1e-7


def test_zero_flow_conserves_each_cell_and_relaxes_to_weighted_equilibrium(case):
    case["inputs"].update(hot_flow_kg_s=0., cold_flow_kg_s=0.)
    case["initial"].update(hot_temperature_K=[360., 350., 340., 330.], cold_temperature_K=290., wall_temperature_K=320.)
    case["simulation"].update(duration_s=1000., output_interval_s=50.)
    result = hx.simulate_heat_exchanger(case)
    assert result["summary"]["success"]
    # Direct inventory calculation, independent of the production coefficient builder.
    capacity = np.array([10.*4180., 10.*4180., 7800.])/4
    initial = profiles(result)[0].reshape(3, 4)
    expected = capacity @ initial / sum(capacity)
    for row in profiles(result):
        energies = capacity @ row.reshape(3, 4)
        assert energies == pytest.approx(capacity @ initial, abs=2e-6)
    for component in profiles(result)[-1].reshape(3, 4):
        assert component == pytest.approx(expected, abs=2e-5)
    assert all(row["cumulative_external_energy_J"] == 0 for row in result["series"])


@pytest.mark.parametrize("arrangement", ["co_current", "counter_current"])
def test_zero_heat_transfer_matches_erlang_and_preserves_cold_and_wall(case, arrangement):
    case["flow_arrangement"] = arrangement
    case["heat_transfer"].update(hot_h_W_m2_K=0., cold_h_W_m2_K=0.)
    result = hx.simulate_heat_exchanger(case)
    assert result["summary"]["success"]
    expected = transport_outlet_reference(case, [r["time_s"] for r in result["series"]])
    assert [r["hot_outlet_temperature_K"] for r in result["series"]] == pytest.approx(expected, abs=2e-4)
    assert np.array([r["cold_temperature_K"] for r in result["series"]]) == pytest.approx(300., abs=1e-8)
    assert np.array([r["wall_temperature_K"] for r in result["series"]]) == pytest.approx(300., abs=1e-8)


def test_stop_restart_changes_boundary_signals_but_heat_exchange_continues(case):
    case["events"] = [{"time_s": 32., "changes": {"hot_flow_kg_s": 0., "cold_flow_kg_s": 0.}},
                      {"time_s": 75., "changes": {"hot_flow_kg_s": .2, "cold_flow_kg_s": .2}},
                      {"time_s": 120., "changes": {"hot_inlet_temperature_K": 330.}}]
    result = hx.simulate_heat_exchanger(case)
    assert result["summary"]["success"]
    times = [r["time_s"] for r in result["series"]]
    assert len(times) == len(set(times))
    stop = next(r for r in result["series"] if r["time_s"] == 32.)
    during = next(r for r in result["series"] if r["time_s"] == 60.)
    restart = next(r for r in result["series"] if r["time_s"] == 75.)
    assert stop["hot_flow_kg_s"] == stop["cold_flow_kg_s"] == 0
    assert restart["hot_flow_kg_s"] == restart["cold_flow_kg_s"] == .2
    assert stop["hot_to_wall_heat_W"] > 1.
    assert stop["total_stored_energy_J"] == pytest.approx(during["total_stored_energy_J"], abs=1e-6)
    assert stop["hot_temperature_K"] != during["hot_temperature_K"]
    assert result["series"][-1]["hot_inlet_temperature_K"] == 330.
    assert np.max(np.abs(profiles(result)-matrix_reference(case, times))) < 2e-4


def test_hot_cold_names_do_not_force_heat_direction(case):
    case["initial"].update(hot_temperature_K=290., cold_temperature_K=350., wall_temperature_K=320.)
    case["inputs"].update(hot_inlet_temperature_K=290., cold_inlet_temperature_K=350.)
    result = hx.simulate_heat_exchanger(case)
    assert result["summary"]["success"]
    assert result["series"][0]["hot_to_wall_heat_W"] < 0
    assert result["series"][0]["cold_to_wall_heat_W"] > 0
    assert result["series"][-1]["hot_outlet_temperature_K"] > 290.
    assert result["series"][-1]["cold_outlet_temperature_K"] < 350.


def test_mesh_preserves_total_inventory_and_wall_conductances(case):
    results = []
    case["simulation"].update(duration_s=1., output_interval_s=1.)
    for n in (1, 8, 128):
        case["cells"] = n
        results.append(hx.simulate_heat_exchanger(case))
    for r in results:
        assert r["summary"]["success"]
        assert r["geometry"]["hot_total_mass_kg"] == 10.
        assert r["geometry"]["cold_total_mass_kg"] == 10.
        assert r["geometry"]["wall_total_heat_capacity_J_K"] == 7800.
        assert r["geometry"]["hot_to_wall_total_conductance_W_K"] == pytest.approx(937.5)
        assert len(r["geometry"]["cell_centres_m"]) == r["configuration"]["cells"]


def test_output_interval_and_json_key_order_do_not_change_dynamics(case):
    case["events"] = [{"time_s": 31.25, "changes": {"hot_inlet_temperature_K": 345.}}]
    fine = hx.simulate_heat_exchanger(case)
    case["simulation"]["output_interval_s"] = 17.
    case["initial"] = dict(reversed(list(case["initial"].items())))
    coarse = hx.simulate_heat_exchanger(case)
    assert profiles(fine)[-1] == pytest.approx(profiles(coarse)[-1], abs=1e-12)
    assert fine["summary"]["rhs_evaluations"] == coarse["summary"]["rhs_evaluations"]


def test_schema_roundtrip_and_provenance(case):
    normalized = hx.validate_heat_exchanger(case)
    result = hx.simulate_heat_exchanger(normalized)
    restored = json.loads(json.dumps(result, allow_nan=False))
    assert restored["summary"]["success"]
    assert len(restored["metadata"]["config_sha256"]) == 64
    assert restored["metadata"]["validation_state"] == "unvalidated_against_plant"
    assert restored["metadata"]["simulation_data_kind"] == "synthetic"
    assert hx.validate_heat_exchanger(normalized) == normalized


def test_modelica_case_is_explicitly_adapted_and_keeps_geometry():
    case = example_cases()["msl_geometry_adaptation.json"]
    assert case["provenance"]["classification"] == "documented_adaptation"
    assert "v4.1.0" in case["provenance"]["source"]
    assert "No se ha ejecutado Modelica" in case["provenance"]["notes"]
    result = hx.simulate_heat_exchanger(case)
    assert result["summary"]["success"]
    assert result["geometry"]["hot_total_mass_kg"] == 9.
    assert result["geometry"]["wall_total_heat_capacity_J_K"] == pytest.approx(3375.)
    assert np.max(np.abs(profiles(result)-matrix_reference(case, [r["time_s"] for r in result["series"]]))) < 2e-4


@pytest.mark.parametrize("arrangement", ["co_current", "counter_current"])
def test_unequal_capacity_flows_converge_to_ntu_solution(case, arrangement):
    case.update(cells=128, flow_arrangement=arrangement)
    case["cold_fluid"]["cp_J_kg_K"] = 2200.
    case["inputs"]["cold_flow_kg_s"] = .17
    case["simulation"].update(duration_s=1200., output_interval_s=100., max_step_s=10.)
    result = hx.simulate_heat_exchanger(case)
    reference = steady_reference(case)
    assert result["summary"]["success"]
    assert result["series"][-1]["hot_outlet_temperature_K"] == pytest.approx(reference["hot_outlet_temperature_K"], abs=.2)
    assert result["series"][-1]["cold_outlet_temperature_K"] == pytest.approx(reference["cold_outlet_temperature_K"], abs=.2)


@pytest.mark.parametrize("path,value", [
    (("cells",), 0), (("cells",), 129), (("cells",), True), (("cells",), 2.5),
    (("flow_arrangement",), "reverse"), (("schema_version",), "other"),
    (("geometry", "length_m"), 0), (("geometry", "cold_cross_area_m2"), -1),
    (("wall", "thickness_m"), 0), (("wall", "density_kg_m3"), 0),
    (("hot_fluid", "cp_J_kg_K"), -1), (("cold_fluid", "density_kg_m3"), float("nan")),
    (("heat_transfer", "hot_h_W_m2_K"), -1), (("heat_transfer", "cold_h_W_m2_K"), float("inf")),
    (("initial", "hot_temperature_K"), [300.]), (("initial", "cold_temperature_K"), 275.),
    (("initial", "wall_temperature_K"), 370.), (("initial", "wall_temperature_K"), "300"),
    (("inputs", "hot_flow_kg_s"), -.1), (("inputs", "cold_flow_kg_s"), True),
    (("inputs", "hot_inlet_temperature_K"), 400.), (("inputs", "cold_inlet_temperature_K"), 200.),
    (("simulation", "method"), "RK45"), (("simulation", "rtol"), 0.),
    (("simulation", "atol"), 1.), (("simulation", "duration_s"), -1.),
    (("simulation", "output_interval_s"), 1e-12), (("simulation", "max_step_s"), 1e-12),
    (("simulation", "min_temperature_K"), 400.),
    (("provenance", "classification"), "real_plant"), (("provenance", "source"), ""),
    (("events",), None), (("title",), ""),
])
def test_invalid_physical_or_schema_inputs_are_rejected(case, path, value):
    target = case
    for key in path[:-1]: target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError): hx.validate_heat_exchanger(case)


@pytest.mark.parametrize("events", [
    [{"time_s": 0, "changes": {"hot_flow_kg_s": 0}}],
    [{"time_s": 121, "changes": {"hot_flow_kg_s": 0}}],
    [{"time_s": 10, "changes": {}}],
    [{"time_s": 10, "changes": {"pressure_Pa": 2e5}}],
    [{"time_s": 10, "changes": {"hot_flow_kg_s": -.1}}],
    [{"time_s": 10, "changes": {"cold_inlet_temperature_K": 400}}],
    [{"time_s": 20, "changes": {"hot_flow_kg_s": 0}}, {"time_s": 10, "changes": {"hot_flow_kg_s": 1}}],
    [{"time_s": 20, "changes": {"hot_flow_kg_s": 0}}, {"time_s": 20, "changes": {"hot_flow_kg_s": 1}}],
])
def test_all_event_intervals_are_checked_before_simulation(case, events):
    case["events"] = events
    with pytest.raises(ValueError): hx.simulate_heat_exchanger(case)


@pytest.mark.parametrize("section", [None, "geometry", "initial", "inputs"])
def test_unknown_and_missing_keys_do_not_silently_change_model(case, section):
    target = case if section is None else case[section]
    target["pressure_Pa"] = 2e5
    with pytest.raises(ValueError): hx.validate_heat_exchanger(case)
    del target["pressure_Pa"]
    target.pop(next(iter(target)))
    with pytest.raises(ValueError): hx.validate_heat_exchanger(case)


@pytest.mark.parametrize("extreme", ["capacity", "conductance", "future_flow", "integral"])
def test_derived_overflow_is_a_preflight_error(case, extreme):
    if extreme == "capacity": case["hot_fluid"].update(density_kg_m3=1e250, cp_J_kg_K=1e250)
    if extreme == "conductance":
        case["heat_transfer"]["hot_h_W_m2_K"] = 1e300
        case["geometry"]["hot_heat_area_m2"] = 1e200
    if extreme == "future_flow": case["events"] = [{"time_s": 60., "changes": {"hot_flow_kg_s": 1e307}}]
    if extreme == "integral":
        case["simulation"].update(duration_s=1e250, output_interval_s=1e249, max_step_s=1e249)
        case["inputs"]["hot_flow_kg_s"] = 1e80
    with pytest.raises(ValueError): hx.validate_heat_exchanger(case)


def test_cancellation_returns_only_completed_segments(case):
    case["events"] = [{"time_s": 10., "changes": {"hot_flow_kg_s": 0.}}]
    original_solve = hx.solve_ivp
    completed = []
    def solve(*args, **kwargs):
        result = original_solve(*args, **kwargs)
        completed.append(True)
        return result
    # Cancellation is requested after a completed event segment, not mid-write.
    from unittest.mock import patch
    with patch.object(hx, "solve_ivp", solve):
        result = hx.simulate_heat_exchanger(case, cancel=lambda: bool(completed))
    assert not result["summary"]["success"]
    assert result["summary"]["status"] == "cancelled"
    assert result["summary"]["final_time_s"] == 10.
    assert result["series"][-1]["hot_flow_kg_s"] == 0.
    json.dumps(result, allow_nan=False)


def test_evaluation_budget_does_not_return_a_successful_trajectory(case, monkeypatch):
    # Preflight admits the requested number of steps; RHS budget then stops work.
    case["simulation"]["max_step_s"] = 120.
    monkeypatch.setattr(hx, "MAX_RHS_EVALUATIONS", 20)
    result = hx.simulate_heat_exchanger(case)
    assert not result["summary"]["success"]
    assert result["summary"]["stop_reason"] == "evaluation_budget_exceeded"
    assert result["summary"]["final_time_s"] == 0.
    assert result["summary"]["samples"] == 1
