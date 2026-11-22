import copy
import json

import numpy as np
import pytest
from scipy.special import gammainc

from dynamic_network import simulate_dynamic_network, validate_network
from dynamic_network_components import prepare_network
from dynamic_network_component_examples import example_cases, recirculation_reference
from dynamic_heat_exchanger import default_case, simulate_heat_exchanger


def profiles(result):
    return np.array([[p["nodes"]["HotTank"]["temperature_K"], p["nodes"]["ColdTank"]["temperature_K"]]
        + sum([p["heat_exchangers"]["HX1"][s+"_temperature_K"] for s in ("hot", "cold", "wall")], []) for p in result["series"]])


@pytest.fixture
def ring(): return example_cases()["coupled_recirculation.json"]


@pytest.mark.parametrize("orientation", ["co_current", "counter_current"])
@pytest.mark.parametrize("method", ["BDF", "Radau"])
def test_joint_closed_circuit_against_independent_matrix(ring, orientation, method):
    ring["heat_exchangers"][0]["flow_arrangement"] = orientation
    ring["simulation"]["method"] = method
    before = copy.deepcopy(ring)
    result = simulate_dynamic_network(ring)
    assert ring == before
    assert result["summary"]["success"]
    reference = recirculation_reference(ring, [r["time_s"] for r in result["series"]])
    assert np.max(np.abs(profiles(result)-reference)) < 2e-4
    assert max(result["audit"]["max_relative_residual"].values()) < 1e-9
    assert max(result["audit"]["max_relative_rate_residual"].values()) < 1e-12
    assert result["metadata"]["assembly"] == "simultaneous_conservative_finite_volumes"
    assert "_materials" not in result["configuration"]
    assert all(set(p["nodes"]) == {"HotTank", "ColdTank"} for p in result["series"])
    assert all(len(p["ports"]) == 4 for p in result["series"])
    for point in result["series"]:
        hx = point["heat_exchangers"]["HX1"]
        assert np.asarray(hx["hot_tracer_mass_fraction"]) == pytest.approx(1., abs=1e-12)
        assert np.asarray(hx["cold_tracer_mass_fraction"]) == pytest.approx(0., abs=1e-12)
        assert hx["wall_mass_kg"] == pytest.approx(15.6)
        assert hx["hot_total_mass_kg"] == pytest.approx(10.)
    assert validate_network(result["configuration"]) == result["configuration"]


def test_stop_is_right_continuous_and_exchange_continues_inside_wall(ring):
    result = simulate_dynamic_network(ring)
    points = {r["time_s"]: r for r in result["series"]}
    assert all(p["mass_flow_kg_s"] == 0 for p in points[40.]["ports"])
    assert all(p["mass_flow_kg_s"] == .2 for p in points[70.]["ports"])
    assert points[40.]["nodes"]["HotTank"]["temperature_K"] == pytest.approx(points[65.]["nodes"]["HotTank"]["temperature_K"], abs=1e-10)
    assert points[40.]["heat_exchangers"]["HX1"]["hot_temperature_K"] != points[65.]["heat_exchangers"]["HX1"]["hot_temperature_K"]
    assert points[40.]["heat_exchangers"]["HX1"]["energy_J"] == pytest.approx(points[65.]["heat_exchangers"]["HX1"]["energy_J"], abs=1e-6)
    assert result["events"] == [{"time_s": e["time_s"], "kind": "input_change", "changes": e["changes"]} for e in ring["events"]]


@pytest.mark.parametrize("orientation", ["co_current", "counter_current"])
def test_feed_exchanger_matches_standalone_with_non_grid_boundary_steps(orientation):
    c = example_cases()["coupled_feed.json"]
    c["heat_exchangers"][0]["flow_arrangement"] = orientation
    c["events"] = [{"time_s": 12.25, "changes": {"sources": {"HotFeed": {"temperature_K": 340., "tracer_mass_fraction": .5}}}},
                   {"time_s": 83.3, "changes": {"sources": {"ColdFeed": {"temperature_K": 310.}}}}]
    joint = simulate_dynamic_network(c)
    h = default_case()
    h.update({k: copy.deepcopy(c["heat_exchangers"][0][k]) for k in ("cells", "flow_arrangement", "geometry", "wall", "heat_transfer", "initial")})
    h["simulation"] = copy.deepcopy(c["simulation"])
    h["events"] = [{"time_s": 12.25, "changes": {"hot_inlet_temperature_K": 340.}},
                   {"time_s": 83.3, "changes": {"cold_inlet_temperature_K": 310.}}]
    separate = simulate_heat_exchanger(h)
    assert joint["summary"]["success"] and separate["summary"]["success"]
    for a, b in zip(joint["series"], separate["series"]):
        assert a["time_s"] == b["time_s"]
        for side in ("hot", "cold", "wall"):
            assert a["heat_exchangers"]["HX1"][side+"_temperature_K"] == pytest.approx(b[side+"_temperature_K"], abs=2e-4)
    assert max(joint["audit"]["max_relative_residual"].values()) < 1e-9


def test_tracer_residence_through_exchanger_and_downstream_tank():
    c = example_cases()["coupled_feed.json"]
    c["nodes"][0]["initial_mass_kg"] = 2.5  # Same residence as each of the four exchanger cells.
    c["heat_exchangers"][0]["heat_transfer"].update(hot_h_W_m2_K=0., cold_h_W_m2_K=0.)
    result = simulate_dynamic_network(c)
    t = np.array([r["time_s"] for r in result["series"]])
    reference = gammainc(5, t/12.5)
    assert result["summary"]["success"]
    assert [r["nodes"]["HotTank"]["tracer_mass_fraction"] for r in result["series"]] == pytest.approx(reference, abs=3e-6)
    assert [r["nodes"]["HotTank"]["temperature_K"] for r in result["series"]] == pytest.approx(300.+60.*reference, abs=2e-4)


def test_multiple_feed_ports_mix_conservatively_without_inventing_storage():
    c = example_cases()["coupled_feed.json"]
    c["edges"][0]["mass_flow_kg_s"] = .1
    c["sources"].append({"id": "WarmFeed", "temperature_K": 320., "tracer_mass_fraction": 0.})
    c["edges"].append({"id": "warm_supply", "source": "WarmFeed", "target": "HX1.hot_in", "mass_flow_kg_s": .1})
    result = simulate_dynamic_network(c)
    reference_case = copy.deepcopy(c)
    reference_case["sources"] = reference_case["sources"][:-1]
    reference_case["sources"][0].update(temperature_K=340., tracer_mass_fraction=.5)
    reference_case["edges"][0]["mass_flow_kg_s"] = .2
    reference_case["edges"].pop()
    reference = simulate_dynamic_network(reference_case)
    assert result["summary"]["success"]
    for a, b in zip(result["series"], reference["series"]):
        assert a["heat_exchangers"]["HX1"]["hot_temperature_K"] == pytest.approx(b["heat_exchangers"]["HX1"]["hot_temperature_K"], abs=2e-4)
        assert a["heat_exchangers"]["HX1"]["hot_tracer_mass_fraction"] == pytest.approx(b["heat_exchangers"]["HX1"]["hot_tracer_mass_fraction"], abs=3e-6)


def test_two_exchangers_can_connect_directly_and_retain_separate_profiles():
    c = example_cases()["coupled_feed.json"]
    c["heat_exchangers"][0]["heat_transfer"].update(hot_h_W_m2_K=0., cold_h_W_m2_K=0.)
    second = copy.deepcopy(c["heat_exchangers"][0]); second["id"] = "HX2"
    c["heat_exchangers"].append(second)
    c["edges"][1]["target"] = "HX2.hot_in"
    c["edges"].append({"id": "second_hot_return", "source": "HX2.hot_out", "target": "HotTank", "mass_flow_kg_s": .2})
    result = simulate_dynamic_network(c)
    assert result["summary"]["success"]
    t = np.array([r["time_s"] for r in result["series"]])
    assert [r["heat_exchangers"]["HX2"]["hot_tracer_mass_fraction"][-1] for r in result["series"]] == pytest.approx(gammainc(8, t/12.5), abs=3e-6)
    assert max(result["audit"]["max_relative_residual"].values()) < 1e-9


def test_disconnected_closed_exchanger_has_real_wall_mass_and_own_heat_capacity(ring):
    ring.update(nodes=[], edges=[], events=[])
    ring["heat_exchangers"][0]["wall"]["cp_J_kg_K"] = 1234.
    ring["heat_exchangers"][0]["initial"]["wall_temperature_K"] = 310.
    ring["simulation"].update(duration_s=2000., output_interval_s=100.)
    result = simulate_dynamic_network(ring)
    assert result["summary"]["success"]
    expected = (10*4180*350+10*4180*290+15.6*1234*310)/(20*4180+15.6*1234)
    for side in ("hot", "cold", "wall"):
        assert np.asarray(result["series"][-1]["heat_exchangers"]["HX1"][side+"_temperature_K"]) == pytest.approx(expected, abs=1e-4)
    assert result["series"][-1]["heat_exchangers"]["HX1"]["wall_mass_kg"] == pytest.approx(15.6)


@pytest.mark.parametrize("mutation", [
    "inlet_as_source", "outlet_as_target", "wall_port", "mismatched_flow", "event_flow", "different_cp",
    "different_density", "duplicate_id", "reserved_id", "extra_inputs", "unknown_event_node",
    "unknown_event_edge", "extra_field", "tracer_profile", "tracer_bound", "too_many_cells", "too_many_samples",
])
def test_incompatible_topologies_and_future_inputs_fail_before_integration(ring, mutation):
    h = ring["heat_exchangers"][0]
    if mutation == "inlet_as_source": ring["edges"][1]["source"] = "HX1.hot_in"
    if mutation == "outlet_as_target": ring["edges"][0]["target"] = "HX1.hot_out"
    if mutation == "wall_port": ring["edges"][0]["target"] = "HX1.wall_in"
    if mutation == "mismatched_flow": ring["edges"][0]["mass_flow_kg_s"] = .1
    if mutation == "event_flow": ring["events"][0]["changes"]["edges"]["hot_supply"]["mass_flow_kg_s"] = .1
    if mutation == "different_cp": h["hot_fluid"]["cp_J_kg_K"] = 2200.
    if mutation == "different_density": h["cold_fluid"]["density_kg_m3"] = 900.
    if mutation == "duplicate_id": h["id"] = "HotTank"
    if mutation == "reserved_id": h["id"] = "dx_other"
    if mutation == "extra_inputs": h["inputs"] = {"hot_flow_kg_s": 8.}
    if mutation == "unknown_event_node": ring["events"][0]["changes"]["nodes"] = {"dx_0_wall_0": {"heat_power_W": 1.}}
    if mutation == "unknown_event_edge": ring["events"][0]["changes"]["edges"]["dx_0_hot_flow_0"] = {"mass_flow_kg_s": 1.}
    if mutation == "extra_field": ring["pressure_Pa"] = 1e5
    if mutation == "tracer_profile": h["initial_tracer_mass_fraction"]["hot"] = [.5]
    if mutation == "tracer_bound": h["initial_tracer_mass_fraction"]["hot"] = 1.1
    if mutation == "too_many_cells":
        h["cells"] = 129
    if mutation == "too_many_samples": ring["simulation"]["output_interval_s"] = .0001
    with pytest.raises(ValueError): simulate_dynamic_network(ring)


def test_mass_limit_retains_connected_profiles_and_cancellation_is_not_success():
    c = example_cases()["coupled_feed.json"]
    c["nodes"][0]["inventory_mode"] = "variable"
    next(e for e in c["edges"] if e["id"] == "hot_discharge")["mass_flow_kg_s"] = 1.
    result = simulate_dynamic_network(c)
    assert result["summary"]["status"] == "limit"
    assert result["summary"]["stop_reason"] == "HotTank.minimum_inventory"
    assert result["summary"]["final_time_s"] == pytest.approx(5.)
    assert result["series"][-1]["heat_exchangers"]["HX1"]["hot_temperature_K"]
    cancelled = simulate_dynamic_network(c, cancel=lambda: True)
    assert cancelled["summary"]["status"] == "cancelled"
    assert not cancelled["summary"]["success"]
    assert cancelled["summary"]["final_time_s"] == 0.
    json.dumps(cancelled, allow_nan=False)


def test_schema_roundtrip_and_output_sampling_independence(ring):
    c = validate_network(ring)
    assert validate_network(json.loads(json.dumps(c))) == c
    first = simulate_dynamic_network(c)
    c["simulation"]["output_interval_s"] = 17.
    second = simulate_dynamic_network(c)
    assert profiles(first)[-1] == pytest.approx(profiles(second)[-1], abs=1e-11)
    assert first["summary"]["rhs_evaluations"] == second["summary"]["rhs_evaluations"]


def test_preflight_keeps_wall_materials_internal(ring):
    normalized, graph, mapping = prepare_network(ring)
    assert "_materials" not in normalized
    assert all(name.startswith("dx_") for name in graph["_materials"])
    assert set(mapping) == {"HX1"}


def test_one_cell_return_uses_distinct_ports_without_artificial_delay(ring):
    ring.update(nodes=[], events=[])
    unit = ring["heat_exchangers"][0]
    unit["cells"] = 1
    unit["initial"] = {key: values[0] for key, values in unit["initial"].items()}
    ring["edges"] = [{"id": side+"_return", "source": "HX1."+side+"_out", "target": "HX1."+side+"_in", "mass_flow_kg_s": .2}
                     for side in ("hot", "cold")]
    result = simulate_dynamic_network(ring)
    ring["edges"] = []
    closed = simulate_dynamic_network(ring)
    assert result["summary"]["success"] and closed["summary"]["success"]
    for a, b in zip(result["series"], closed["series"]):
        for side in ("hot", "cold", "wall"):
            assert a["heat_exchangers"]["HX1"][side+"_temperature_K"] == pytest.approx(b["heat_exchangers"]["HX1"][side+"_temperature_K"], abs=2e-4)


def test_extracting_published_equipment_keeps_source_but_marks_new_network_adaptation():
    from dynamic_network_components import component_from_case
    c = default_case()
    c["provenance"]["classification"] = "published_reproduction"
    unit = component_from_case("HX", c)
    assert unit["provenance"]["classification"] == "documented_adaptation"
    assert c["provenance"]["classification"] == "published_reproduction"
    assert unit["provenance"]["source"] == c["provenance"]["source"]
