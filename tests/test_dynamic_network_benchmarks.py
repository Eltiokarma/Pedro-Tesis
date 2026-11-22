from gate_dynamic_network import run_checks


def test_theoretical_network_acceptance_gate():
    report = run_checks()
    assert report["success"], report
    assert len(report["checks"]) == 4
    assert report["comparison_with_external_simulator_executed"] is False
    published = report["checks"][-1]["published_reference"]
    assert abs(published["numerical_integral_C_s"] - published["published_integral_C_s"]) < .1
