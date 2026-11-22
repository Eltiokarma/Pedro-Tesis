import pytest

from gate_dynamic_network_components import run_checks


@pytest.fixture(scope="module")
def report(): return run_checks()


@pytest.mark.parametrize("name", ["closed_coupling_co_current", "closed_coupling_counter_current", "residence_through_exchanger_and_tank"])
def test_coupled_acceptance(report, name):
    check = next(c for c in report["checks"] if c["name"] == name)
    assert check["passed"], check
