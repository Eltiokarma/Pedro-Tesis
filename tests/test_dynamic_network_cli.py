import csv
import json

import pytest

from dynamic_network_cli import main
from dynamic_network_examples import example_cases


def test_example_check_and_simulation_exports(tmp_path):
    case, checked, result, trajectory = [tmp_path / name for name in ("case.json", "check.json", "run.json", "run.csv")]
    assert main(["--example", "recirculation", "--write-example", str(case)]) == 0
    original = case.read_bytes()
    assert main([str(case), "--check", "--out", str(checked)]) == 0
    assert json.loads(checked.read_text(encoding="utf-8"))["status"] == "initial_conditions_and_all_events_checked"
    assert main([str(case), "--out", str(result), "--csv", str(trajectory)]) == 0
    payload = json.loads(result.read_text(encoding="utf-8"))
    assert payload["summary"]["success"]
    with trajectory.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2 * len(payload["series"])
    assert {row["node_id"] for row in rows} == {"A", "B"}
    assert all(row["data_kind"] == "synthetic" and row["classification"] == "analytical_limit" for row in rows)
    assert case.read_bytes() == original


@pytest.mark.parametrize("overwrite", [False, True])
def test_output_cannot_replace_input_even_with_overwrite(tmp_path, overwrite):
    path = tmp_path / "case.json"
    path.write_text(json.dumps(example_cases()["cascade.json"]), encoding="utf-8")
    original = path.read_bytes()
    args = [str(path), "--out", str(path)] + (["--overwrite"] if overwrite else [])
    assert main(args) == 2
    assert path.read_bytes() == original


def test_existing_output_requires_explicit_overwrite(tmp_path):
    path = tmp_path / "run.json"
    path.write_text("keep", encoding="utf-8")
    assert main(["--check", "--out", str(path)]) == 2
    assert path.read_text(encoding="utf-8") == "keep"
    assert main(["--check", "--out", str(path), "--overwrite"]) == 0


@pytest.mark.parametrize("options", [
    ["--check", "--csv", "x.csv"],
    ["--write-example", "x.json", "--out", "y.json"],
    ["input.json", "--example", "cascade"],
    ["--out", "same.json", "--csv", "same.json"],
])
def test_conflicting_arguments_are_rejected(options):
    assert main(options) == 2


def test_physical_limit_has_failure_exit_code_but_retains_evidence(tmp_path):
    c = example_cases()["cascade.json"]
    c["nodes"][0]["heat_power_W"] = 1e7
    path, output = tmp_path / "case.json", tmp_path / "out.json"
    path.write_text(json.dumps(c), encoding="utf-8")
    assert main([str(path), "--out", str(output)]) == 1
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["summary"]["status"] == "limit"
    assert result["series"][-1]["nodes"]["A"]["temperature_K"] == pytest.approx(c["simulation"]["max_temperature_K"])
