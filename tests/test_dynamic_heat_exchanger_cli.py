import csv
import json

import pytest

import dynamic_heat_exchanger as hx
from dynamic_heat_exchanger_cli import main


def test_example_preflight_profiles_and_export_provenance(tmp_path):
    case, check, output, csvfile = [tmp_path/name for name in ("case.json", "check.json", "run.json", "profiles.csv")]
    assert main(["--example", "msl_geometry_adaptation", "--write-example", str(case)]) == 0
    before = case.read_bytes()
    assert main([str(case), "--check", "--out", str(check)]) == 0
    assert json.loads(check.read_text(encoding="utf-8"))["status"] == "initial_conditions_and_all_events_checked"
    assert main([str(case), "--out", str(output), "--csv", str(csvfile)]) == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["summary"]["success"]
    with csvfile.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(result["series"])*result["configuration"]["cells"]
    assert {int(r["cell_index"]) for r in rows} == set(range(20))
    assert all(r["classification"] == "documented_adaptation" and r["data_kind"] == "synthetic" for r in rows)
    assert all("No se ha ejecutado Modelica" in r["provenance_notes"] for r in rows)
    assert rows[-20]["position_m"] == "0.5"
    assert float(rows[-20]["cold_temperature_K"]) == result["series"][-1]["cold_outlet_temperature_K"]
    assert case.read_bytes() == before


@pytest.mark.parametrize("flag", ["--out", "--csv"])
@pytest.mark.parametrize("overwrite", [False, True])
def test_output_cannot_replace_input(tmp_path, flag, overwrite):
    path = tmp_path/"case.json"
    path.write_text(json.dumps(hx.default_case()), encoding="utf-8")
    before = path.read_bytes()
    assert main([str(path), flag, str(path)]+(["--overwrite"] if overwrite else [])) == 2
    assert path.read_bytes() == before


def test_existing_output_requires_overwrite(tmp_path):
    path = tmp_path/"result.json"
    path.write_text("keep", encoding="utf-8")
    assert main(["--check", "--out", str(path)]) == 2
    assert path.read_text() == "keep"
    assert main(["--check", "--out", str(path), "--overwrite"]) == 0


@pytest.mark.parametrize("args", [
    ["--check", "--csv", "profiles.csv"],
    ["--write-example", "example.json", "--out", "result.json"],
    ["case.json", "--example", "counter_current"],
    ["--out", "same.json", "--csv", "same.json"],
])
def test_incompatible_arguments_are_rejected(args):
    assert main(args) == 2


def test_numerical_stop_has_nonzero_exit_and_exports_partial_evidence(tmp_path, monkeypatch):
    case, output = tmp_path/"case.json", tmp_path/"output.json"
    config = hx.default_case()
    config["simulation"]["max_step_s"] = config["simulation"]["duration_s"]
    case.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(hx, "MAX_RHS_EVALUATIONS", 20)
    assert main([str(case), "--out", str(output)]) == 1
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["summary"]["stop_reason"] == "evaluation_budget_exceeded"
    assert result["series"][0]["time_s"] == 0.


def test_invalid_json_is_reported_without_creating_output(tmp_path):
    case, output = tmp_path/"bad.json", tmp_path/"out.json"
    case.write_text("{bad", encoding="utf-8")
    assert main([str(case), "--out", str(output)]) == 2
    assert not output.exists()
