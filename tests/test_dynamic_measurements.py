"""Independent arithmetic and ingestion checks for dynamic measurement comparison."""
import hashlib
import json
import math

import pytest

from dynamic_measurements import compare_measurements, write_measurement_template


def trajectory(success=True):
    return {
        "summary": {"success": success},
        "metadata": {"config_sha256": "example-config-hash"},
        "series": [
            {"time_s": 0, "tank_temperature_K": 300, "volume_m3": 1},
            {"time_s": 10, "tank_temperature_K": 320, "volume_m3": 2},
            {"time_s": 20, "tank_temperature_K": 310, "volume_m3": 3},
        ],
    }


def save(tmp_path, contents):
    path = tmp_path / "observations.csv"
    path.write_text(contents, encoding="utf-8")
    return path


def test_known_interpolation_metrics_and_hash(tmp_path):
    path = save(tmp_path, "time_s,tank_temperature_K,volume_m3\n"
                "0,301,1\n5,308,1.6\n15,311,2.5\n20,308,3\n")
    result = compare_measurements(trajectory(), path, source_label="test-run")
    metric = result["metrics"]["tank_temperature_K"]
    # Prediction errors are -1, 2, 4, 2; these expected values do not reuse code.
    assert metric["n"] == 4
    assert metric["rmse"] == pytest.approx(2.5)
    assert metric["mae"] == pytest.approx(2.25)
    assert metric["bias"] == pytest.approx(1.75)
    assert metric["max_abs_error"] == 4
    assert result["metrics"]["volume_m3"]["mae"] == pytest.approx(.025)
    assert result["summary"]["status"] == "ok"
    assert result["provenance"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["provenance"]["simulation_config_sha256"] == "example-config-hash"
    assert result["validation_state"] == "comparison_only_unverified"
    assert result["provenance"]["source_kind"] == "user_supplied_unverified"
    json.dumps(result, allow_nan=False)


def test_missing_cells_uncertainty_and_no_extrapolation(tmp_path):
    path = save(tmp_path, "time_s,tank_temperature_K,tank_temperature_K_uncertainty,volume_m3\n"
                "0,301,0.5,\n5,,,1.5\n25,300,1,9\n")
    result = compare_measurements(trajectory(), path)
    assert result["summary"]["status"] == "warning"
    assert result["summary"]["rows_in_range"] == 2
    assert result["summary"]["rows_out_of_range"] == 1
    assert result["summary"]["comparison_count"] == 2
    assert result["metrics"]["tank_temperature_K"]["n"] == 1
    assert result["metrics"]["tank_temperature_K"]["missing_count"] == 1
    assert result["metrics"]["tank_temperature_K"]["excluded_out_of_range_count"] == 1
    assert result["metrics"]["tank_temperature_K"]["normalized_rmse"] == 2
    assert result["metrics"]["volume_m3"]["rmse"] == 0
    assert result["excluded_rows"][0]["reason"] == "after_simulation"


def test_offset_is_explicit_and_does_not_clamp(tmp_path):
    path = save(tmp_path, "time_s,tank_temperature_K\n0,300\n5,300\n10,310\n30,400\n")
    result = compare_measurements(trajectory(), path, time_offset_s=-5)
    assert result["summary"]["rows_out_of_range"] == 2
    assert result["comparisons"][0]["time_s"] == 5
    assert result["comparisons"][0]["simulation_time_s"] == 0
    assert result["metrics"]["tank_temperature_K"]["rmse"] == 0
    assert result["excluded_rows"][0]["reason"] == "before_simulation"


def test_all_out_of_range_has_null_metrics(tmp_path):
    path = save(tmp_path, "time_s,tank_temperature_K\n21,300\n22,300\n")
    result = compare_measurements(trajectory(), path)
    assert result["summary"]["status"] == "no_overlap"
    assert not result["summary"]["comparison_available"]
    assert result["metrics"]["tank_temperature_K"]["rmse"] is None
    assert result["metrics"]["tank_temperature_K"]["n"] == 0
    assert result["comparisons"] == []
    json.dumps(result, allow_nan=False)


def test_partial_run_is_not_declared_validated(tmp_path):
    path = save(tmp_path, "time_s,tank_temperature_K\n0,300\n10,320\n")
    result = compare_measurements(trajectory(False), path)
    assert result["metrics"]["tank_temperature_K"]["rmse"] == 0
    assert result["summary"]["simulation_partial"]
    assert result["summary"]["status"] == "warning"
    assert "cannot establish validity" in result["warnings"][0]


def test_single_point_partial_trajectory_only_matches_exact_time(tmp_path):
    run = trajectory(False)
    run["series"] = run["series"][:1]
    path = save(tmp_path, "time_s,tank_temperature_K\n0,300\n1,300\n")
    result = compare_measurements(run, path)
    assert result["metrics"]["tank_temperature_K"]["n"] == 1
    assert result["summary"]["rows_out_of_range"] == 1


def test_control_actions_are_right_continuous_without_artificial_ramps(tmp_path):
    run = {
        "summary": {"success": True},
        "series": [
            {"time_s": 0, "valve_opening": .1, "utility_flow_kg_s": 1},
            {"time_s": 10, "valve_opening": .9, "utility_flow_kg_s": 4},
            {"time_s": 20, "valve_opening": .3, "utility_flow_kg_s": 2},
        ],
    }
    path = save(tmp_path, "time_s,valve_opening,utility_flow_kg_s\n"
                "0,0.1,1\n5,0.1,1\n10,0.9,4\n15,0.9,4\n20,0.3,2\n")
    result = compare_measurements(run, path)
    assert result["metrics"]["valve_opening"]["rmse"] == 0
    assert result["metrics"]["utility_flow_kg_s"]["rmse"] == 0
    assert result["provenance"]["interpolation"]["valve_opening"] == "previous_value_right_continuous"


@pytest.mark.parametrize("contents, match", [
    ("time_s,tank_temperature_C\n0,20\n", "Unknown CSV"),
    ("time_s,tank_temperature_K,tank_temperature_K\n0,300,300\n", "duplicate"),
    ("time_s,tank_temperature_K\n1,300\n1,300\n", "strictly increasing"),
    ("time_s,tank_temperature_K\n1,300\n0,300\n", "strictly increasing"),
    ("time_s,tank_temperature_K\nnan,300\n", "finite"),
    ("time_s,tank_temperature_K\n0,inf\n", "finite"),
    ("time_s,tank_temperature_K\n-1,300\n", "nonnegative"),
    ("time_s,tank_temperature_K\n0\n", "column count"),
    ("time_s,tank_temperature_K\n0,300,400\n", "column count"),
    ("time_s,tank_temperature_K\n0,\n", "no numeric observations"),
    ("time_s,tank_temperature_K\n", "no observation rows"),
    ("time_s\n0\n", "at least one"),
    ("tank_temperature_K\n300\n", "requires time_s"),
    ("time_s,tank_temperature_K,volume_m3_uncertainty\n0,300,1\n", "requires its observation"),
    ("time_s,tank_temperature_K,tank_temperature_K_uncertainty\n0,300,0\n", "positive"),
    ("time_s,tank_temperature_K,tank_temperature_K_uncertainty\n0,,1\n", "blank observation"),
])
def test_bad_csv_rejected(tmp_path, contents, match):
    with pytest.raises(ValueError, match=match):
        compare_measurements(trajectory(), save(tmp_path, contents))


@pytest.mark.parametrize("mutation", ["no_series", "duplicate_time", "nan_value", "missing_variable"])
def test_malformed_trajectory_rejected(tmp_path, mutation):
    run = trajectory()
    if mutation == "no_series":
        run["series"] = []
    elif mutation == "duplicate_time":
        run["series"][1]["time_s"] = 0
    elif mutation == "nan_value":
        run["series"][1]["tank_temperature_K"] = math.nan
    else:
        del run["series"][1]["tank_temperature_K"]
    with pytest.raises(ValueError):
        compare_measurements(run, save(tmp_path, "time_s,tank_temperature_K\n0,300\n"))


def test_template_has_no_fabricated_rows(tmp_path):
    path = tmp_path / "empty_template.csv"
    write_measurement_template(path)
    text = path.read_text(encoding="utf-8")
    assert text.startswith("time_s,tank_temperature_K,")
    assert len(text.splitlines()) == 1


def test_utf8_bom_and_invalid_offset(tmp_path):
    path = save(tmp_path, "\ufefftime_s,tank_temperature_K\n0,300\n")
    assert compare_measurements(trajectory(), path)["summary"]["comparison_available"]
    with pytest.raises(ValueError, match="time_offset_s"):
        compare_measurements(trajectory(), path, time_offset_s=float("nan"))


def test_unknown_completion_state_stays_partial(tmp_path):
    run = trajectory()
    del run["summary"]
    result = compare_measurements(run, save(tmp_path, "time_s,tank_temperature_K\n0,300\n"))
    assert result["summary"]["simulation_partial"]
