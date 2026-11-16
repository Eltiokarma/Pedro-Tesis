"""Data isolation, SI preflight and snapshot provenance for calibration studies."""
import copy
import hashlib
import json

import pytest

import dynamic_study as ds
from dynamic_tank import default_case


def build_study(tmp_path):
    case = default_case()
    case["controller"]["enabled"] = False
    case["simulation"]["duration_s"] = 60.0
    for name in ("fit", "holdout"):
        (tmp_path / f"{name}.json").write_text(json.dumps(case), encoding="utf-8")
    (tmp_path / "fit.csv").write_text(
        "time_s,tank_temperature_K,tank_temperature_K_uncertainty\n"
        "0,300,0.1\n10,305,0.2\n20,310,\n", encoding="utf-8")
    (tmp_path / "holdout.csv").write_text(
        "time_s,tank_temperature_K\n0,301\n10,304\n20,307\n", encoding="utf-8")
    manifest = {
        "schema_version": ds.SCHEMA_VERSION,
        "study_id": "independent-thermal-trials",
        "equipment_id": "synthetic-tank-01",
        "parameters": [{"path": "wall.ua_tank_W_K", "initial": 800,
                        "lower": 100, "upper": 1600}],
        "observables": {"tank_temperature_K": {
            "scale_K": 0.1, "max_validation_rmse_K": 0.5,
            "max_validation_abs_error_K": 1.0}},
        "experiments": [
            {"experiment_id": "fit", "role": "calibration", "case_file": "fit.json",
             "measurements_file": "fit.csv", "data_kind": "synthetic",
             "source": "Synthetic fixture, never plant measurements", "time_offset_s": 0},
            {"experiment_id": "holdout", "role": "validation", "case_file": "holdout.json",
             "measurements_file": "holdout.csv", "data_kind": "synthetic",
             "source": "Independent synthetic fixture", "time_offset_s": 0},
        ],
        "options": {"max_evaluations": 80},
    }
    path = tmp_path / "study.json"
    save_manifest(path, manifest)
    return path, manifest


def save_manifest(path, manifest):
    path.write_text(json.dumps(manifest), encoding="utf-8")


def change_case(tmp_path, name, change):
    path = tmp_path / f"{name}.json"
    case = json.loads(path.read_text(encoding="utf-8"))
    change(case)
    path.write_text(json.dumps(case), encoding="utf-8")


def test_load_snapshot_has_exact_provenance_and_no_file_mutations(tmp_path):
    path, manifest = build_study(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = ds.load_study(path)
    after = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert before == after
    assert result["provenance"]["study_sha256"] == hashlib.sha256(before["study.json"]).hexdigest()
    assert result["provenance"]["authenticity"] == "user_declared_unverified"
    assert result["provenance"]["independence"] == "duplicate_detection_only_not_proof"
    assert result["provenance"]["calibration_observations"] == 3
    fit = result["experiments"][0]
    assert fit["measurement_sha256"] == hashlib.sha256(before["fit.csv"]).hexdigest()
    assert fit["case_sha256"] == hashlib.sha256(before["fit.json"]).hexdigest()
    assert fit["observations"][1]["uncertainties"] == {"tank_temperature_K": 0.2}
    assert fit["measurements_file"] == "fit.csv"
    assert fit["case_file"] == "fit.json"
    assert str(tmp_path) not in json.dumps(result)
    json.dumps(result, allow_nan=False)


def test_snapshot_read_once_with_repeated_calibration_reference(tmp_path, monkeypatch):
    path, manifest = build_study(tmp_path)
    extra = dict(manifest["experiments"][0], experiment_id="replicated-fit-reference")
    manifest["experiments"].append(extra)
    save_manifest(path, manifest)
    calls = []
    original = ds._read_csv

    def counted(csv_path):
        calls.append(csv_path.name)
        return original(csv_path)

    monkeypatch.setattr(ds, "_read_csv", counted)
    result = ds.load_study(path)
    assert calls == ["fit.csv", "holdout.csv"]
    result["experiments"][0]["observations"][0]["values"]["tank_temperature_K"] = 999
    assert result["experiments"][2]["observations"][0]["values"]["tank_temperature_K"] == 300


@pytest.mark.parametrize("alias", ["same_file", "renamed", "reformatted", "reweighted", "extra_columns"])
def test_reused_holdout_rejected_even_when_relabelled(tmp_path, alias):
    path, manifest = build_study(tmp_path)
    if alias == "same_file":
        manifest["experiments"][1]["measurements_file"] = "fit.csv"
    elif alias == "renamed":
        (tmp_path / "holdout.csv").write_bytes((tmp_path / "fit.csv").read_bytes())
    elif alias == "reformatted":
        (tmp_path / "holdout.csv").write_text(
            "tank_temperature_K,time_s\r\n300.0,-0.0\r\n305.000,1e1\r\n310,20.00\r\n",
            encoding="utf-8")
    elif alias == "reweighted":
        (tmp_path / "holdout.csv").write_text(
            "time_s,tank_temperature_K,tank_temperature_K_uncertainty\n"
            "0,300,2\n10,305,3\n20,310,4\n", encoding="utf-8")
    else:
        (tmp_path / "holdout.csv").write_text(
            "time_s,tank_temperature_K,volume_m3\n0,300,1\n5,,9\n10,305,2\n20,310,3\n",
            encoding="utf-8")
    save_manifest(path, manifest)
    with pytest.raises(ValueError, match="leakage"):
        ds.load_study(path)


def test_clock_shifted_duplicate_holdout_rejected(tmp_path):
    path, manifest = build_study(tmp_path)
    manifest["experiments"][1]["time_offset_s"] = -5
    (tmp_path / "holdout.csv").write_text(
        "time_s,tank_temperature_K\n5,300\n15,305\n25,310\n", encoding="utf-8")
    save_manifest(path, manifest)
    with pytest.raises(ValueError, match="aligned fingerprint"):
        ds.load_study(path)


def test_reformatted_duplicate_with_different_offset_is_still_rejected(tmp_path):
    path, manifest = build_study(tmp_path)
    manifest["experiments"][1]["time_offset_s"] = 1
    (tmp_path / "holdout.csv").write_text(
        "time_s,tank_temperature_K\n0.0,300\n1e1,305\n20.0,310\n", encoding="utf-8")
    save_manifest(path, manifest)
    with pytest.raises(ValueError, match="canonical fingerprint"):
        ds.load_study(path)


def test_offsets_and_sparse_selected_observations_remain_explicit(tmp_path):
    path, manifest = build_study(tmp_path)
    manifest["experiments"][0]["time_offset_s"] = -5
    (tmp_path / "fit.csv").write_text(
        "time_s,tank_temperature_K\n0,\n5,300\n15,\n25,310\n", encoding="utf-8")
    save_manifest(path, manifest)
    result = ds.load_study(path)
    assert result["experiments"][0]["observations"][1]["time_s"] == 5
    assert result["experiments"][0]["time_offset_s"] == -5
    assert result["provenance"]["calibration_observations"] == 2


@pytest.mark.parametrize("value", [True, "800", float("nan"), float("inf"), 10**400])
def test_parameter_initial_must_be_finite_json_number(tmp_path, value):
    path, manifest = build_study(tmp_path)
    manifest["parameters"][0]["initial"] = value
    save_manifest(path, manifest)
    with pytest.raises(ValueError):
        ds.load_study(path)


@pytest.mark.parametrize("updates", [
    {"lower": 800}, {"upper": 800}, {"lower": -1},
    {"path": "tank.cp_J_kg_K"}, {"extra": 1},
    {"path": "wall.heat_capacity_J_K", "lower": 0},
    {"upper": 1e308},
])
def test_invalid_or_physically_overflowing_parameter_bounds_rejected(tmp_path, updates):
    path, manifest = build_study(tmp_path)
    manifest["parameters"][0].update(updates)
    save_manifest(path, manifest)
    with pytest.raises(ValueError):
        ds.load_study(path)


@pytest.mark.parametrize("budget", [True, 0, 501, 1.5, "80"])
def test_optimisation_budget_is_bounded_integer(tmp_path, budget):
    path, manifest = build_study(tmp_path)
    manifest["options"]["max_evaluations"] = budget
    save_manifest(path, manifest)
    with pytest.raises(ValueError, match="max_evaluations"):
        ds.load_study(path)


def test_unknown_schema_fields_and_duplicate_json_keys_are_rejected(tmp_path):
    path, manifest = build_study(tmp_path)
    manifest["calibration_magic"] = True
    save_manifest(path, manifest)
    with pytest.raises(ValueError, match="unknown"):
        ds.load_study(path)
    path.write_text('{"study_id":"a","study_id":"b"}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate key"):
        ds.load_study(path)


def test_empty_labels_and_source_are_not_valid_provenance(tmp_path):
    path, manifest = build_study(tmp_path)
    manifest["experiments"][0]["source"] = "  "
    save_manifest(path, manifest)
    with pytest.raises(ValueError, match="source"):
        ds.load_study(path)


@pytest.mark.parametrize("edit", ["same_id", "no_holdout", "closed_loop", "different_equipment"])
def test_experiment_roles_and_physics_are_checked(tmp_path, edit):
    path, manifest = build_study(tmp_path)
    if edit == "same_id":
        manifest["experiments"][1]["experiment_id"] = "fit"
    elif edit == "no_holdout":
        manifest["experiments"][1]["role"] = "calibration"
    elif edit == "closed_loop":
        change_case(tmp_path, "fit", lambda c: c["controller"].update(enabled=True))
    else:
        change_case(tmp_path, "holdout", lambda c: c["tank"].update(cp_J_kg_K=3000))
    save_manifest(path, manifest)
    with pytest.raises(ValueError):
        ds.load_study(path)


def test_initial_conditions_operating_speed_and_fitted_guesses_may_differ(tmp_path):
    path, manifest = build_study(tmp_path)

    def perturb(case):
        case["tank"]["initial_mass_kg"] = 600
        case["tank"]["initial_temperature_K"] = 310
        case["wall"]["initial_temperature_K"] = 310
        case["wall"]["ua_tank_W_K"] = 900
        case["jacket"]["initial_temperature_K"] = 310
        case["pump"]["speed_fraction"] = 0.5
        case["inputs"]["ambient_temperature_K"] = 301

    change_case(tmp_path, "holdout", perturb)
    result = ds.load_study(path)
    assert result["experiments"][1]["case"]["tank"]["initial_mass_kg"] == 600
    assert result["experiments"][1]["case"]["wall"]["ua_tank_W_K"] == 900


@pytest.mark.parametrize("data", [
    "time_s,tank_temperature_K\n0,300\n10,305\n61,310\n",
    "time_s,tank_temperature_K\n0,0\n10,305\n20,310\n",
    "time_s,tank_temperature_K\n0,-5\n10,305\n20,310\n",
    "time_s,wall_temperature_K\n0,300\n10,305\n20,310\n",
    "time_s,tank_temperature_K\n0,300\n10,\n20,\n",
])
def test_selected_data_must_cover_time_domain_and_degrees_of_freedom(tmp_path, data):
    path, manifest = build_study(tmp_path)
    (tmp_path / "fit.csv").write_text(data, encoding="utf-8")
    with pytest.raises(ValueError):
        ds.load_study(path)


@pytest.mark.parametrize("reference", ["/tmp/case.json", "C:/private/case.json", "C:case.json", "\\case.json", "folder\\case.json", " fit.json"])
def test_only_portable_relative_references_are_accepted(tmp_path, reference):
    path, manifest = build_study(tmp_path)
    manifest["experiments"][0]["case_file"] = reference
    save_manifest(path, manifest)
    with pytest.raises(ValueError, match="relative|forward slashes"):
        ds.load_study(path)


def test_loader_rejects_excessive_selected_measurements(tmp_path, monkeypatch):
    path, manifest = build_study(tmp_path)
    monkeypatch.setattr(ds, "MAX_SELECTED_OBSERVATIONS", 5)
    with pytest.raises(ValueError, match="selected numeric observations"):
        ds.load_study(path)


@pytest.mark.parametrize("temperature", [277, 364])
def test_loose_error_criteria_cannot_admit_data_outside_property_domain(tmp_path, temperature):
    path, manifest = build_study(tmp_path)
    manifest["observables"]["tank_temperature_K"].update(
        max_validation_rmse_K=1000, max_validation_abs_error_K=1000)
    (tmp_path / "holdout.csv").write_text(
        f"time_s,tank_temperature_K\n0,301\n10,{temperature}\n20,307\n", encoding="utf-8")
    save_manifest(path, manifest)
    with pytest.raises(ValueError, match="declared property temperature domain"):
        ds.load_study(path)


def test_loader_rejects_excessive_json_bytes(tmp_path, monkeypatch):
    path, manifest = build_study(tmp_path)
    monkeypatch.setattr(ds, "MAX_JSON_BYTES", 10)
    with pytest.raises(ValueError, match="byte limit"):
        ds.load_study(path)


def test_unknown_observables_and_nonpositive_scales_rejected(tmp_path):
    path, manifest = build_study(tmp_path)
    manifest["observables"]["tank_temperature_K"]["scale_K"] = 0
    save_manifest(path, manifest)
    with pytest.raises(ValueError):
        ds.load_study(path)
    manifest["observables"] = {"tank_temperature_C": {
        "scale_K": 1, "max_validation_rmse_K": 1, "max_validation_abs_error_K": 1}}
    save_manifest(path, manifest)
    with pytest.raises(ValueError, match="explicit"):
        ds.load_study(path)
