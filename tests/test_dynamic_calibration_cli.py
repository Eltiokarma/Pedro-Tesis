"""Exercise the study-to-report workflow and preservation of source data."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from calibration_example import reference_temperatures, write_calibration_example
from dynamic_calibration_cli import _write_json, guard_outputs, main
from dynamic_tank import default_case


def test_example_and_preflight_preserve_inputs(tmp_path, capsys):
    folder = tmp_path / "study"
    assert main(["--write-example", str(folder)]) == 0
    inputs = {file: hashlib.sha256(file.read_bytes()).hexdigest() for file in folder.iterdir()}
    output = tmp_path / "preflight.json"
    assert main([str(folder / "study.json"), "--check", "--out", str(output)]) == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["status"] == "inputs_checked_not_fitted"
    assert {exp["role"] for exp in result["experiments"]} == {"calibration", "validation"}
    assert {exp["data_kind"] for exp in result["experiments"]} == {"synthetic"}
    assert all(hashlib.sha256(file.read_bytes()).hexdigest() == digest for file, digest in inputs.items())
    assert main(["--write-example", str(folder)]) == 2
    assert all(hashlib.sha256(file.read_bytes()).hexdigest() == digest for file, digest in inputs.items())
    capsys.readouterr()


def test_calibration_cli_exports_a_traceable_candidate_without_gui(tmp_path):
    study = write_calibration_example(tmp_path / "study")
    report, candidate = tmp_path / "report.json", tmp_path / "candidate.json"
    script = (
        "import sys; from dynamic_calibration_cli import main; "
        f"status=main({[str(study), '--out', str(report), '--fitted-case', str(candidate), '--experiment-id', 'cal_hot']!r}); "
        "assert not any(name.startswith(('PySide6','tkinter')) for name in sys.modules); "
        "raise SystemExit(status)"
    )
    completed = subprocess.run([sys.executable, "-c", script], text=True, capture_output=True,
                               cwd=Path(__file__).resolve().parents[1], timeout=90)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(report.read_text(encoding="utf-8"))
    fitted = json.loads(candidate.read_text(encoding="utf-8"))
    assert result["summary"]["optimization_converged"]
    assert result["summary"]["validation_status"] == "criteria_met"
    assert result["validation_state"] == "synthetic_calibration_only"
    assert fitted["wall"]["ua_tank_W_K"] == pytest.approx(800.0, rel=0.03)
    assert fitted["wall"]["ua_jacket_W_K"] == pytest.approx(1200.0, rel=0.03)
    assert fitted["provenance"]["data_kind"] == "synthetic"
    assert fitted["provenance"]["notes"]


@pytest.mark.parametrize("source", ["study.json", "cal_hot.json", "cal_hot.csv"])
def test_cli_never_overwrites_study_inputs_even_with_overwrite(tmp_path, source, capsys):
    study = write_calibration_example(tmp_path)
    target = tmp_path / source
    before = target.read_bytes()
    assert main([str(study), "--check", "--out", str(target), "--overwrite"]) == 2
    assert target.read_bytes() == before
    capsys.readouterr()


def test_hardlink_and_duplicate_output_protection(tmp_path):
    source, alias = tmp_path / "source.csv", tmp_path / "alias.csv"
    source.write_text("private input", encoding="utf-8")
    try:
        os.link(source, alias)
    except OSError:
        pytest.skip("Hardlinks unavailable in this environment")
    with pytest.raises(ValueError, match="entrada"):
        guard_outputs([alias], [source], overwrite=True)
    with pytest.raises(ValueError, match="distinta"):
        guard_outputs([source, alias], [], overwrite=True)
    assert source.read_text(encoding="utf-8") == "private input"


def test_cli_requires_explicit_experiment_for_case_export(tmp_path, capsys):
    study = write_calibration_example(tmp_path / "study")
    candidate = tmp_path / "candidate.json"
    assert main([str(study), "--fitted-case", str(candidate)]) == 2
    assert not candidate.exists()
    assert main([str(study), "--fitted-case", str(candidate), "--experiment-id", "missing"]) == 2
    assert not candidate.exists()
    capsys.readouterr()


def test_existing_report_requires_explicit_overwrite(tmp_path, capsys):
    study = write_calibration_example(tmp_path / "study")
    report = tmp_path / "report.json"
    report.write_text("original", encoding="utf-8")
    assert main([str(study), "--check", "--out", str(report)]) == 2
    assert report.read_text(encoding="utf-8") == "original"
    assert main([str(study), "--check", "--out", str(report), "--overwrite"]) == 0
    capsys.readouterr()


def test_invalid_unicode_cannot_truncate_existing_output(tmp_path):
    output = tmp_path / "report.json"
    output.write_bytes(b"original")
    with pytest.raises(UnicodeEncodeError):
        _write_json(output, {"source": "\ud800"}, overwrite=True)
    assert output.read_bytes() == b"original"


@pytest.mark.parametrize("change", ["manifest", "case", "measurements"])
def test_cli_rejects_fitted_snapshot_that_changed_after_preflight(tmp_path, monkeypatch, change):
    import dynamic_calibration
    from dynamic_study import load_study
    study_path = write_calibration_example(tmp_path / "study")
    study = load_study(study_path)
    report = {"provenance": dict(study["provenance"]), "experiments": [
        {"experiment_id": exp["experiment_id"], "provenance": {
            "case_sha256": exp["case_sha256"], "measurement_sha256": exp["measurement_sha256"]}}
        for exp in study["experiments"]]}
    if change == "manifest":
        report["provenance"]["study_sha256"] = "changed"
    else:
        key = "case_sha256" if change == "case" else "measurement_sha256"
        report["experiments"][0]["provenance"][key] = "changed"
    monkeypatch.setattr(dynamic_calibration, "calibrate_study", lambda path: report)
    output = tmp_path / "report.json"
    assert main([str(study_path), "--out", str(output)]) == 2
    assert not output.exists()


def test_analytic_reference_rejects_dynamics_it_does_not_represent():
    case = default_case()
    case["controller"]["enabled"] = True
    with pytest.raises(ValueError, match="PI disabled"):
        reference_temperatures(case)
    case["controller"]["enabled"] = False
    case["events"] = [{"time_s": 10.0, "changes": {"feed_flow_kg_s": 1.0}}]
    with pytest.raises(ValueError, match="throughout all events"):
        reference_temperatures(case)
