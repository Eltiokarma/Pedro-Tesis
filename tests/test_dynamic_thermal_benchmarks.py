"""Externally sourced numbers and independent coupled-system references."""
import copy
import json

import numpy as np
import pytest

from gate_dynamic_thermal_loop import FOLDER, published_component_benchmark, run_gate
from thermal_loop_examples import example_cases, reference_temperatures


def test_published_energyplus_temperature_and_integral():
    check = published_component_benchmark()
    assert check["passed"]
    assert check["final_temperature_C"] == pytest.approx(52.21956227895557, abs=1e-6)
    assert check["integral_C_s"] == pytest.approx(14716.592986047968, abs=1e-4)
    assert check["scope"] == "production_reservoir_balance_with_prescribed_return_not_full_closed_loop"


def test_committed_inputs_match_reproducible_case_factory():
    for filename, generated in example_cases().items():
        assert json.loads((FOLDER / filename).read_text(encoding="utf-8")) == generated


def test_four_inventory_reference_rejects_non_linear_or_variable_inventory_use():
    case = example_cases()["coupled_disturbances.json"]
    original = copy.deepcopy(case)
    temperatures = reference_temperatures(case, [0, 10, 600, 1000, 1300, 1800])
    assert temperatures.shape == (6, 4)
    assert np.isfinite(temperatures).all()
    assert case == original
    case["controller"]["enabled"] = True
    with pytest.raises(ValueError, match="manual control"):
        reference_temperatures(case, [0, 10])
    case = copy.deepcopy(original)
    case["instrumentation"]["valve_actuator"]["enabled"] = True
    with pytest.raises(ValueError, match="ideal actuator"):
        reference_temperatures(case, [0, 10])
    case = copy.deepcopy(original)
    case["inputs"]["outlet_flow_kg_s"] = 0
    with pytest.raises(ValueError, match="constant process inventory"):
        reference_temperatures(case, [0, 10])


@pytest.mark.parametrize("times", [[0, 0], [10, 0], [-1], [1801], [float("nan")]])
def test_reference_rejects_invalid_sampling(times):
    with pytest.raises(ValueError, match="sample times"):
        reference_temperatures(example_cases()["coupled_disturbances.json"], times)


def test_thermal_loop_acceptance_gate():
    result = run_gate()
    assert result["success"], [(check["check"], check) for check in result["checks"] if not check["passed"]]
    assert len(result["checks"]) == 7
    assert "no_experimental_validation" in result["scope"]
    assert result["checks"][1]["scope"] == "full_engine_v3_decoupled_reservoir"
