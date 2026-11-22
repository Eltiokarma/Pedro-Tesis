"""Independent network physics, initialization, events and failure semantics."""
import copy
import json
import math

import numpy as np
import pytest

import dynamic_network as network
from dynamic_network_examples import example_cases, reference_trajectories


@pytest.mark.parametrize("filename", list(example_cases()))
@pytest.mark.parametrize("method", ["BDF", "Radau"])
def test_all_topologies_against_closed_forms(filename, method):
    case = example_cases()[filename]
    case["simulation"]["method"] = method
    result = network.simulate_dynamic_network(case)
    assert result["summary"]["success"], result["summary"]
    reference = reference_trajectories(case["case_id"], [row["time_s"] for row in result["series"]])
    for name, variables in reference.items():
        for quantity, expected in variables.items():
            actual = [row["nodes"][name][quantity] for row in result["series"]]
            tolerance = 2e-4 if quantity == "temperature_K" else 5e-6
            assert np.max(np.abs(actual - expected)) < tolerance
    assert max(result["audit"]["max_relative_residual"].values()) < 1e-9
    assert max(result["audit"]["max_relative_rate_residual"].values()) < 1e-9


def single_tank():
    c = example_cases()["cascade.json"]
    c["nodes"] = c["nodes"][:1]
    c["edges"] = [c["edges"][0], {"id": "A_out", "source": "A", "target": None, "mass_flow_kg_s": 1.0}]
    return c


def test_port_uses_donor_enthalpy_and_applies_opposite_signs():
    c = example_cases()["recirculation.json"]
    c["heat_links"] = []
    row = network.simulate_dynamic_network(c)["series"][0]
    cp = c["fluid"]["cp_J_kg_K"]
    assert row["ports"][0]["energy_flow_W"] == pytest.approx(cp * (338.15 - 273.15))
    assert row["ports"][0]["tracer_flow_kg_s"] == 1.0
    assert row["ports"][1]["tracer_flow_kg_s"] == 0.0
    assert row["nodes"]["A"]["net_energy_rate_W"] == pytest.approx(-40 * cp)
    assert row["nodes"]["B"]["net_energy_rate_W"] == pytest.approx(40 * cp)
    assert row["nodes"]["A"]["net_tracer_flow_kg_s"] == -1.0
    assert row["nodes"]["B"]["net_tracer_flow_kg_s"] == 1.0


def test_stop_is_right_continuous_and_heat_continues_without_mass_flow():
    result = network.simulate_dynamic_network(example_cases()["recirculation.json"])
    rows = {r["time_s"]: r for r in result["series"]}
    for time in (100.0, 150.0):
        assert all(port["mass_flow_kg_s"] == 0 for port in rows[time]["ports"])
        assert rows[time]["heat_ports"][0]["heat_first_to_second_W"] > 0
    assert rows[100.0]["nodes"]["A"]["tracer_mass_fraction"] == pytest.approx(rows[200.0]["nodes"]["A"]["tracer_mass_fraction"], abs=1e-10)
    assert rows[100.0]["nodes"]["A"]["temperature_K"] > rows[200.0]["nodes"]["A"]["temperature_K"]
    assert all(port["mass_flow_kg_s"] == 1 for port in rows[200.0]["ports"])
    assert [event["time_s"] for event in result["events"]] == [100, 200]


@pytest.mark.parametrize("filling", [True, False])
def test_variable_inventory_stops_at_exact_mass_bound(filling):
    c = single_tank()
    c["nodes"][0].update(initial_mass_kg=10., min_mass_kg=1., max_mass_kg=20., inventory_mode="variable",
                          initial_temperature_K=308.15, initial_tracer_mass_fraction=.25)
    c["simulation"].update(duration_s=30., output_interval_s=.5, max_step_s=20.)
    c["edges"] = c["edges"][:1] if filling else c["edges"][1:]
    result = network.simulate_dynamic_network(c)
    assert result["summary"]["status"] == "limit"
    assert result["summary"]["final_time_s"] == pytest.approx(10. if filling else 9.)
    for row in result["series"]:
        time, state = row["time_s"], row["nodes"]["A"]
        mass = 10 + time if filling else 10 - time
        temperature = (10*308.15 + time*338.15)/mass if filling else 308.15
        tracer = (2.5 + time)/mass if filling else .25
        assert state["mass_kg"] == pytest.approx(mass, abs=1e-8)
        assert state["temperature_K"] == pytest.approx(temperature, abs=2e-4)
        assert state["tracer_mass_fraction"] == pytest.approx(tracer, abs=2e-6)
    assert max(result["audit"]["max_relative_residual"].values()) < 1e-9


@pytest.mark.parametrize("power,reason", [(41800., "temperature_high"), (-41800., "temperature_low")])
def test_temperature_limits_located_between_output_samples(power, reason):
    c = single_tank()
    c["edges"] = []
    c["sources"] = []
    c["nodes"][0].update(initial_mass_kg=10., initial_temperature_K=300., heat_power_W=power)
    c["simulation"].update(duration_s=100., min_temperature_K=290., max_temperature_K=310., output_interval_s=7.)
    result = network.simulate_dynamic_network(c)
    assert result["summary"]["status"] == "limit"
    assert result["summary"]["stop_reason"] == "A." + reason
    assert result["summary"]["final_time_s"] == pytest.approx(10., abs=1e-8)
    assert result["series"][-1]["time_s"] == pytest.approx(10., abs=1e-8)


def test_source_step_changes_flux_immediately_without_state_jump():
    c = single_tank()
    c["sources"][0].update(temperature_K=298.15, tracer_mass_fraction=0.)
    c["events"] = [{"time_s": 103., "changes": {"sources": {"feed": {"temperature_K": 338.15, "tracer_mass_fraction": 1.}}}}]
    result = network.simulate_dynamic_network(c)
    row = next(row for row in result["series"] if row["time_s"] == 103.)
    assert row["nodes"]["A"]["temperature_K"] == pytest.approx(298.15)
    assert row["ports"][0]["donor_temperature_K"] == 338.15
    assert row["ports"][0]["tracer_flow_kg_s"] == 1.
    for row in result["series"]:
        response = 1 - math.exp(-max(row["time_s"] - 103., 0.) / 100.)
        assert row["nodes"]["A"]["temperature_K"] == pytest.approx(298.15 + 40*response, abs=2e-4)


def test_output_interval_does_not_change_the_dynamics():
    c = example_cases()["recirculation.json"]
    coarse = network.simulate_dynamic_network(c)
    c["simulation"]["output_interval_s"] = 2.
    fine = network.simulate_dynamic_network(c)
    by_time = {r["time_s"]: r for r in fine["series"]}
    assert coarse["summary"]["rhs_evaluations"] == fine["summary"]["rhs_evaluations"]
    for row in coarse["series"]:
        assert row["nodes"] == by_time[row["time_s"]]["nodes"]


@pytest.mark.parametrize("mutation,match", [
    (lambda c: c.update(schema_version="dynamic-network/v999"), "schema_version"),
    (lambda c: c.update(pressure_Pa=101325.), "desconocidas"),
    (lambda c: c["nodes"][0].update(initial_mass_kg=True), "número"),
    (lambda c: c["nodes"][0].update(initial_mass_kg=float("nan")), "dominio"),
    (lambda c: c["nodes"][0].update(initial_mass_kg=0.), "dominio"),
    (lambda c: c["nodes"][0].update(initial_mass_kg=1.), "inventario"),
    (lambda c: c["nodes"][0].update(initial_temperature_K=278.15), "temperatura"),
    (lambda c: c["nodes"][0].update(initial_tracer_mass_fraction=1.1), "dominio"),
    (lambda c: c["nodes"][1].update(id="A"), "duplicado"),
    (lambda c: c["sources"][0].update(id="A"), "duplicado"),
    (lambda c: c["edges"][0].update(source="missing"), "origen"),
    (lambda c: c["edges"][0].update(target="feed"), "destino"),
    (lambda c: c["edges"][1].update(target="A"), "consigo"),
    (lambda c: c["edges"][0].update(target=None), "sin inventario"),
    (lambda c: c["edges"][1].update(id="feed_A"), "duplicada"),
    (lambda c: c["edges"][1].update(mass_flow_kg_s=-1.), "dominio"),
    (lambda c: c["edges"][1].update(mass_flow_kg_s=.9), "fijo incompatible"),
    (lambda c: c["fluid"].update(cp_J_kg_K=0), "dominio"),
    (lambda c: c["simulation"].update(method="RK45"), "BDF o Radau"),
    (lambda c: c["simulation"].update(output_interval_s=1e-9), "muestras"),
    (lambda c: c["simulation"].update(max_step_s=1e-9), "evaluaciones"),
    (lambda c: c.update(nodes=[]), "no vacía"),
    (lambda c: c.update(heat_links=[{"id": "bad", "first": "A", "second": "feed", "ua_W_K": 10.}]), "térmica"),
])
def test_invalid_network_is_rejected_before_integrating(mutation, match):
    case = example_cases()["cascade.json"]
    mutation(case)
    with pytest.raises(ValueError, match=match):
        network.validate_network(case)


@pytest.mark.parametrize("changes,match", [
    ({"edges": {"A_B": {"mass_flow_kg_s": .5}}}, "t=100.*fijo incompatible"),
    ({"nodes": {"A": {"initial_mass_kg": 20.}}}, "desconocidas"),
    ({"sources": {"feed": {"temperature_K": float("inf")}}}, "dominio"),
    ({"edges": {"unknown": {"mass_flow_kg_s": 1.}}}, "desconocidas"),
    ({"sources": {"feed": {}}}, "vacío"),
    ({}, "vacío"),
])
def test_every_event_is_preflight_checked(changes, match):
    case = example_cases()["cascade.json"]
    case["events"] = [{"time_s": 100., "changes": changes}]
    with pytest.raises(ValueError, match=match):
        network.validate_network(case)


def test_simultaneous_balanced_flow_changes_are_applied_together():
    c = single_tank()
    c["events"] = [{"time_s": 100., "changes": {"edges": {"feed_A": {"mass_flow_kg_s": .5}, "A_out": {"mass_flow_kg_s": .5}}}}]
    result = network.simulate_dynamic_network(c)
    assert result["summary"]["success"]
    assert all(abs(row["nodes"]["A"]["mass_kg"] - 100) < 1e-9 for row in result["series"])


def test_disconnected_finite_inventory_retains_its_initial_state():
    c = single_tank()
    c["edges"] = []
    result = network.simulate_dynamic_network(c)
    assert result["summary"]["success"]
    assert result["series"][0]["nodes"] == result["series"][-1]["nodes"]


def test_cancellation_is_not_reported_as_success():
    result = network.simulate_dynamic_network(single_tank(), cancel=lambda: True)
    assert result["summary"]["status"] == "cancelled"
    assert result["summary"]["final_time_s"] == 0
    assert len(result["series"]) == 1


def test_cancellation_inside_solver_keeps_a_finite_partial_result():
    count = 0
    def cancel():
        nonlocal count
        count += 1
        return count > 50
    result = network.simulate_dynamic_network(single_tank(), cancel=cancel)
    assert result["summary"]["status"] == "cancelled"
    assert not result["summary"]["success"]
    json.dumps(result, allow_nan=False)


def test_evaluation_budget_is_explicit(monkeypatch):
    monkeypatch.setattr(network, "MAX_RHS_EVALUATIONS", 100)
    c = single_tank()
    c["simulation"]["max_step_s"] = 60.
    result = network.simulate_dynamic_network(c)
    assert result["summary"]["stop_reason"] == "evaluation_budget_exceeded"
    assert not result["summary"]["success"]


def test_inputs_are_not_mutated_and_provenance_is_preserved():
    c = example_cases()["recirculation.json"]
    before = copy.deepcopy(c)
    result = network.simulate_dynamic_network(c)
    assert c == before
    assert result["configuration"]["events"] == before["events"]
    assert result["metadata"]["simulation_data_kind"] == "synthetic"
    assert result["metadata"]["validation_state"] == "unvalidated_against_plant"
    assert len(result["metadata"]["config_sha256"]) == 64
    json.dumps(result, allow_nan=False)


def test_numerically_unrepresentable_initial_capacity_is_rejected():
    c = single_tank()
    c["fluid"]["cp_J_kg_K"] = 1e308
    with pytest.raises(ValueError, match="numérico"):
        network.validate_network(c)


def test_numerically_unrepresentable_future_flow_is_rejected():
    c = single_tank()
    c["events"] = [{"time_s": 100., "changes": {"edges": {
        "feed_A": {"mass_flow_kg_s": 1e300}, "A_out": {"mass_flow_kg_s": 1e300}}}}]
    c["fluid"]["cp_J_kg_K"] = 1e100
    with pytest.raises(ValueError, match="numéricamente"):
        network.validate_network(c)


def test_initial_volume_must_be_numerically_representable():
    c = single_tank()
    c["fluid"]["density_kg_m3"] = 1e-320
    with pytest.raises(ValueError, match="numérico"):
        network.validate_network(c)
