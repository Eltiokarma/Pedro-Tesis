import pytest

from gate_dynamic_heat_exchanger import run_checks


@pytest.fixture(scope="module")
def report():
    return run_checks()


@pytest.mark.parametrize("name", ["time_refinement_co_current", "time_refinement_counter_current",
                                  "space_refinement_co_current", "space_refinement_counter_current",
                                  "transient_residence_space_refinement"])
def test_independent_exchanger_acceptance_checks(report, name):
    check = next(item for item in report["checks"] if item["name"] == name)
    assert check["passed"], check


def test_report_does_not_claim_external_or_published_reproduction(report):
    assert report["success"]
    assert not report["comparison_with_external_simulator_executed"]
    assert not report["complete_published_exchanger_case_reproduced"]
