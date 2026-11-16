"""Public v2 fixture/CLI workflow, reference domain and input preservation."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import dynamic_cli
from dynamic_study import load_study
from instrumentation_example import reference_indicated_temperatures, write_instrumentation_examples


def test_instrumentation_example_regenerates_portable_fixture(tmp_path):
    path = write_instrumentation_examples(tmp_path)
    study = load_study(path)
    assert all("_indicated_temperature_K" in name for name in study["observables"])
    assert all(exp["case"]["schema_version"] == "dynamic-tank/v2" for exp in study["experiments"])
    fixture = Path(__file__).resolve().parents[1] / "data/instrumentation_examples"
    for file in tmp_path.rglob("*"):
        if file.is_file():
            assert file.read_bytes() == (fixture / file.relative_to(tmp_path)).read_bytes()
    with pytest.raises(FileExistsError):
        write_instrumentation_examples(tmp_path)


def test_headless_v2_cli_exports_actual_position_and_indication(tmp_path):
    case = Path(__file__).resolve().parents[1] / "data/instrumentation_examples/valve_steps.json"
    output, trajectory = tmp_path / "run.json", tmp_path / "trajectory.csv"
    args = [str(case), "--out", str(output), "--csv", str(trajectory)]
    script = ("import sys; from dynamic_cli import main; "
              f"status=main({args!r}); "
              "assert not any(name.startswith(('PySide6','tkinter')) for name in sys.modules); "
              "raise SystemExit(status)")
    process = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                             cwd=case.parents[2], timeout=60)
    assert process.returncode == 0, process.stdout + process.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    rows = {row["time_s"]: row for row in result["series"]}
    assert rows[100.0]["valve_command"] == 0.9
    assert rows[100.0]["valve_opening"] == pytest.approx(0.1)
    assert rows[105.0]["valve_opening"] == pytest.approx(0.2)
    assert "tank_indicated_temperature_K" in trajectory.read_text(encoding="utf-8").splitlines()[0]
    assert rows[0.0]["tank_indicated_temperature_K"] - rows[0.0]["tank_sensor_temperature_K"] == pytest.approx(0.4)


def test_independent_reference_rejects_moving_actuator_and_ideal_sensor(tmp_path):
    write_instrumentation_examples(tmp_path)
    moving = json.loads((tmp_path / "valve_steps.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="valve movement"):
        reference_indicated_temperatures(moving)
    case = json.loads((tmp_path / "calibration/cal_hot.json").read_text(encoding="utf-8"))
    case["instrumentation"]["temperature_sensors"]["tank"]["time_constant_s"] = 0.0
    with pytest.raises(ValueError, match="positive sensor"):
        reference_indicated_temperatures(case)


def test_csv_encoding_failure_preserves_previous_export(tmp_path):
    path = tmp_path / "old.csv"
    path.write_bytes(b"previous")
    with pytest.raises(UnicodeEncodeError):
        dynamic_cli.export_trajectory({"series": [{"time_s": 0.0, "value": "\ud800"}]}, str(path))
    assert path.read_bytes() == b"previous"
    assert not list(tmp_path.glob(".trajectory-*"))


def test_cli_rechecks_hardlink_alias_created_during_simulation(tmp_path, monkeypatch):
    import dynamic_tank
    source = tmp_path / "case.json"
    source.write_text(json.dumps(dynamic_tank.default_case()), encoding="utf-8")
    before = source.read_bytes()
    target = tmp_path / "alias.csv"

    def simulate(_case):
        try:
            os.link(source, target)
        except OSError:
            pytest.skip("Hardlinks unavailable in this environment")
        return {"summary": {"success": True}, "series": [{"time_s": 0.0}]}

    monkeypatch.setattr(dynamic_tank, "simulate_dynamic_tank", simulate)
    assert dynamic_cli.main([str(source), "--csv", str(target)]) == 2
    assert source.read_bytes() == before
