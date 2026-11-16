"""Qt lifecycle and explicit exports for the calibration workbench."""
import copy
import hashlib
import json
import os
import sys
import threading
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from dynamic_calibration_dialog import DynamicCalibrationDialog

_app = QApplication.instance() or QApplication([])


def _wait_until(predicate, timeout_ms=5000):
    if predicate():
        return
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(5)
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start()
    deadline.start(timeout_ms)
    loop.exec()
    poll.stop()
    deadline.stop()
    assert predicate(), "Qt worker did not settle before timeout"


def _result(status="ok", *, usable=True):
    experiments = []
    completed = status not in ("failed", "cancelled")
    for ident, role in (("heat-fit", "calibration"), ("cool-check", "validation")):
        experiments.append({
            "experiment_id": ident, "role": role, "data_kind": "synthetic",
            "baseline_metrics": {"tank_temperature_K": {"n": 3, "rmse": 2.5}},
            "fitted_metrics": {"tank_temperature_K": {
                "n": 3, "rmse": .1, "mae": .08, "bias": -.01, "max_abs_error": .2}}
                if completed else None,
            "fitted_case": {"case_id": ident,
                            "provenance": {"data_kind": "synthetic", "notes": "candidate"}}
                if completed else None,
        })
    return {
        "schema_version": "dynamic-calibration-result/v1",
        "summary": {"status": status, "optimization_converged": completed,
                    "usable_parameter_estimate": usable and completed,
                    "evaluations": 15, "objective_before": 20., "objective_after": .2,
                    "validation_status": "criteria_met" if completed else "not_assessed"},
        "parameters": [{"path": "wall.ua_tank_W_K", "initial": 500, "value": 800,
                        "lower": 100, "upper": 1500, "at_bound": False}],
        "diagnostics": {"rank": 1 if usable else 0, "n_parameters": 1,
                        "scaled_jacobian_condition": 1.0 if usable else None},
        "experiments": experiments,
        "warnings": [] if usable else ["Sensibilidad insuficiente <sensor>"],
        "validation_state": "synthetic_calibration_only",
    }


@pytest.fixture
def workbench(tmp_path, monkeypatch):
    manifest = {
        "schema_version": "dynamic-calibration-study/v1", "study_id": "synthetic-ui-study",
        "equipment_id": "Tank <b>demo</b>",
        "parameters": [{"path": "wall.ua_tank_W_K", "initial": 500., "lower": 100., "upper": 1500.}],
        "observables": {"tank_temperature_K": {
            "scale_K": .2, "max_validation_rmse_K": .5, "max_validation_abs_error_K": 1.}},
        "experiments": [], "options": {"max_evaluations": 100},
    }
    for ident, role in (("heat-fit", "calibration"), ("cool-check", "validation")):
        manifest["experiments"].append({
            "experiment_id": ident, "role": role, "case_file": f"{ident}.json",
            "measurements_file": f"{ident}.csv", "data_kind": "synthetic",
            "source": "Analytical fixture <not a plant>", "time_offset_s": 0.,
        })
        (tmp_path / f"{ident}.json").write_text('{"input": true}', encoding="utf-8")
        (tmp_path / f"{ident}.csv").write_text("time_s,tank_temperature_K\n0,298.15\n", encoding="utf-8")
    path = tmp_path / "study.json"
    raw = json.dumps(manifest).encode("utf-8")
    path.write_bytes(raw)
    prepared = copy.deepcopy(manifest)
    prepared["provenance"] = {"study_sha256": hashlib.sha256(raw).hexdigest()}
    for item in prepared["experiments"]:
        item["case_sha256"] = hashlib.sha256((tmp_path / item["case_file"]).read_bytes()).hexdigest()
        item["measurement_sha256"] = hashlib.sha256(
            (tmp_path / item["measurements_file"]).read_bytes()).hexdigest()
    loader = types.SimpleNamespace(
        load_study=lambda path: copy.deepcopy(prepared),
        PARAMETER_UNITS={"wall.ua_tank_W_K": "W/K"},
    )
    def result_factory(status="ok", *, usable=True):
        report = _result(status, usable=usable)
        report["provenance"] = copy.deepcopy(prepared["provenance"])
        for item, source in zip(report["experiments"], prepared["experiments"]):
            item["provenance"] = {key: source[key] for key in (
                "case_file", "measurements_file", "case_sha256", "measurement_sha256")}
        return report

    engine = types.SimpleNamespace(result=result_factory,
        calibrate_study=lambda path, cancel=None, progress=None: result_factory())
    monkeypatch.setitem(sys.modules, "dynamic_study", loader)
    monkeypatch.setitem(sys.modules, "dynamic_calibration", engine)
    widget = DynamicCalibrationDialog()
    widget.set_study(path)
    yield widget, loader, engine, path
    if widget._worker is not None:
        widget.cancel_calibration()
        _wait_until(lambda: widget._worker is None)
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    _app.processEvents()


def test_study_preview_distinguishes_synthetic_data_and_reserved_experiments(workbench):
    widget, _, _, _ = workbench
    preview = widget.study_view.toPlainText()
    assert "sintéticos" in widget.provenance_label.text()
    assert "Validación reservada" in preview
    assert "Tank <b>demo</b>" in preview
    assert "<not a plant>" in preview
    assert "0.5 K" in preview and "W/K" in preview
    assert widget.run_button.isEnabled()
    assert not widget.export_report_button.isEnabled()


def test_preflight_load_runs_off_gui_thread(workbench):
    widget, loader, _, path = workbench
    main_thread = threading.get_ident()
    ids = []
    previous = loader.load_study

    def load(path):
        ids.append(threading.get_ident())
        return previous(path)

    loader.load_study = load
    widget._load_path(path)
    assert not widget.open_button.isEnabled()
    _wait_until(lambda: widget._worker is None)
    assert ids and ids[0] != main_thread
    assert widget.run_button.isEnabled()


def test_cancelled_preflight_does_not_replace_loaded_study(workbench):
    widget, loader, _, path = workbench
    entered, release = threading.Event(), threading.Event()
    previous = loader.load_study

    def load(path):
        entered.set()
        assert release.wait(3)
        study = previous(path)
        study["study_id"] = "must-not-replace-preview"
        return study

    loader.load_study = load
    widget._load_path(path)
    try:
        _wait_until(entered.is_set)
        widget.cancel_calibration()
    finally:
        release.set()
    _wait_until(lambda: widget._worker is None)
    assert widget._study["study_id"] == "synthetic-ui-study"
    assert "cancelada" in widget.status_label.text()
    assert widget.run_button.isEnabled()


def test_invalid_preflight_preserves_previous_study_and_reports_error(workbench):
    widget, loader, _, path = workbench

    def broken(path):
        raise ValueError("CSV: temperatura no finita")

    loader.load_study = broken
    widget._load_path(path)
    _wait_until(lambda: widget._worker is None)
    assert widget._study["study_id"] == "synthetic-ui-study"
    assert "temperatura no finita" in widget.diagnostics_view.toPlainText()
    assert widget.run_button.isEnabled()


def test_fit_runs_in_worker_and_renders_both_roles(workbench):
    widget, _, engine, _ = workbench
    ids = []
    gui_id = threading.get_ident()

    def calibrate(path, *, cancel, progress):
        ids.append(threading.get_ident())
        progress({"evaluations": 15, "max_evaluations": 100, "simulations_count": 30,
                  "phase": "calibration", "experiment_id": "heat-fit"})
        return engine.result()

    engine.calibrate_study = calibrate
    widget.start_calibration()
    assert not widget.run_button.isEnabled()
    _wait_until(lambda: widget._worker is None)
    assert ids and ids[0] != gui_id
    assert widget.parameter_table.item(0, 3).text() == "800"
    assert widget.metrics_table.rowCount() == 2
    assert widget.metrics_table.item(1, 1).text() == "Validación reservada"
    assert widget.metrics_table.item(1, 5).text() == "0.1"
    assert widget.progress_bar.value() == 15
    assert "no certifica" in widget.status_label.text()
    assert widget.export_report_button.isEnabled()
    assert widget.export_case_button.isEnabled()


def test_close_requests_cancellation_and_keeps_thread_alive_until_finished(workbench):
    widget, _, engine, _ = workbench
    entered = threading.Event()

    def calibrate(path, *, cancel, progress):
        entered.set()
        while not cancel():
            threading.Event().wait(.002)
        return engine.result("cancelled")

    engine.calibrate_study = calibrate
    widget.show()
    widget.start_calibration()
    _wait_until(entered.is_set)
    widget.close()
    assert widget._close_when_finished
    _wait_until(lambda: widget._worker is None and not widget.isVisible())
    assert widget._result["summary"]["status"] == "cancelled"
    assert widget.export_report_button.isEnabled()
    assert not widget.export_case_button.isEnabled()


def test_exception_does_not_reuse_or_export_previous_result(workbench):
    widget, _, engine, _ = workbench
    widget.start_calibration()
    _wait_until(lambda: widget._worker is None)
    assert widget._result is not None

    def broken(*args, **kwargs):
        raise ValueError("Corrida fuera del dominio")

    engine.calibrate_study = broken
    widget.start_calibration()
    _wait_until(lambda: widget._worker is None)
    assert widget._result is None
    assert widget.run_button.isEnabled()
    assert not widget.export_report_button.isEnabled()
    assert "fuera del dominio" in widget.status_label.text()


def test_changed_manifest_requires_review_before_running(workbench):
    widget, _, engine, path = workbench
    calls = []
    engine.calibrate_study = lambda *args, **kwargs: calls.append(True)
    path.write_bytes(path.read_bytes() + b" ")
    widget.start_calibration()
    assert widget._worker is None
    assert not calls
    assert "manifiesto cambió" in widget.status_label.text()


@pytest.mark.parametrize("changed_input", ["study", "case", "measurements"])
def test_changed_worker_snapshot_blocks_results_and_exports(workbench, changed_input):
    widget, _, engine, _ = workbench
    result = engine.result()
    if changed_input == "study":
        result["provenance"]["study_sha256"] = "different-study"
    else:
        key = "case_sha256" if changed_input == "case" else "measurement_sha256"
        result["experiments"][0]["provenance"][key] = "different-input"
    engine.calibrate_study = lambda *args, **kwargs: result
    widget.start_calibration()
    _wait_until(lambda: widget._worker is None)
    assert widget._result is None
    assert not widget.export_report_button.isEnabled()
    assert not widget.export_case_button.isEnabled()
    assert "cambi" in widget.diagnostics_view.toPlainText()


def test_export_rechecks_result_snapshot_before_writing(workbench, monkeypatch, tmp_path):
    widget, _, _, _ = workbench
    widget.start_calibration()
    _wait_until(lambda: widget._worker is None)
    target = tmp_path / "must-not-be-created.json"
    widget._result["experiments"][0]["provenance"]["measurement_sha256"] = "changed"
    errors = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(target), "JSON"))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: errors.append(args[-1]))
    widget._export_report()
    assert not target.exists()
    assert errors and "mediciones" in errors[0]


def test_converged_weak_identification_exports_candidate_with_visible_warning(workbench):
    widget, _, engine, _ = workbench
    engine.calibrate_study = lambda *args, **kwargs: engine.result("warning", usable=False)
    widget.start_calibration()
    _wait_until(lambda: widget._worker is None)
    assert widget.export_case_button.isEnabled()
    assert "candidato con advertencias" in widget.status_label.text()
    assert "Sensibilidad insuficiente <sensor>" in widget.diagnostics_view.toPlainText()


def test_failed_result_has_report_but_no_case_export(workbench):
    widget, _, engine, _ = workbench
    result = engine.result("failed")
    result["failure"] = {"reason": "experiment_failed", "experiment_id": "<sensor>"}
    engine.calibrate_study = lambda *args, **kwargs: result
    widget.start_calibration()
    _wait_until(lambda: widget._worker is None)
    assert widget.export_report_button.isEnabled()
    assert not widget.export_case_button.isEnabled()
    assert "experiment_failed" in widget.diagnostics_view.toPlainText()
    assert "<sensor>" in widget.diagnostics_view.toPlainText()


def test_explicit_exports_preserve_report_and_selected_case(workbench, monkeypatch, tmp_path):
    widget, _, _, _ = workbench
    widget.start_calibration()
    _wait_until(lambda: widget._worker is None)
    report_path = tmp_path / "report.json"
    case_path = tmp_path / "candidate.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(report_path), "JSON"))
    widget._export_report()
    assert json.loads(report_path.read_text(encoding="utf-8")) == widget._result
    widget.case_combo.setCurrentIndex(1)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(case_path), "JSON"))
    widget._export_case()
    assert json.loads(case_path.read_text(encoding="utf-8"))["case_id"] == "cool-check"


@pytest.mark.parametrize("source_name", ["study.json", "heat-fit.json", "cool-check.csv"])
def test_export_cannot_overwrite_inputs(workbench, monkeypatch, source_name):
    widget, _, _, path = workbench
    widget.start_calibration()
    _wait_until(lambda: widget._worker is None)
    source = path.parent / source_name
    before = source.read_bytes()
    errors = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(source), "JSON"))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: errors.append(args[-1]))
    widget._export_report()
    assert source.read_bytes() == before
    assert errors and "sobrescribir" in errors[0]


def test_export_cannot_overwrite_input_through_hardlink(workbench, tmp_path):
    widget, _, _, path = workbench
    linked = tmp_path / "alias.json"
    try:
        os.link(path, linked)
    except OSError as exc:
        pytest.skip(f"Hardlinks unavailable: {exc}")
    with pytest.raises(ValueError, match="sobrescribir"):
        widget._ensure_output(linked)


def test_external_new_reference_is_protected_without_rereading_csv(workbench, tmp_path):
    widget, _, _, path = workbench
    new_csv = tmp_path / "new-observations.csv"
    new_csv.write_text("new observation input", encoding="utf-8")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["experiments"][0]["measurements_file"] = new_csv.name
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="sobrescribir"):
        widget._ensure_output(new_csv)


def test_export_rechecks_input_references_after_save_chooser(workbench, monkeypatch, tmp_path):
    widget, _, _, path = workbench
    widget.start_calibration()
    _wait_until(lambda: widget._worker is None)
    new_csv = tmp_path / "new-csv-reference.csv"
    new_csv.write_text("preserve input", encoding="utf-8")
    errors = []

    def choose(*args):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["experiments"][0]["measurements_file"] = new_csv.name
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return str(new_csv), "JSON"

    monkeypatch.setattr(QFileDialog, "getSaveFileName", choose)
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: errors.append(args[-1]))
    widget._export_report()
    assert new_csv.read_text(encoding="utf-8") == "preserve input"
    assert errors and "sobrescribir" in errors[0]


def test_pilot_opens_calibration_lazily_without_changing_case(monkeypatch):
    import dynamic_calibration_dialog
    from dynamic_tank_dialog import DynamicTankDialog
    opened = []

    class FakeDialog:
        def __init__(self, parent):
            opened.append(parent)

        def exec(self):
            return 0

    monkeypatch.setattr(dynamic_calibration_dialog, "DynamicCalibrationDialog", FakeDialog)
    pilot = DynamicTankDialog()
    try:
        before = pilot.case_from_form()
        pilot.calibration_button.click()
        assert opened == [pilot]
        assert pilot.case_from_form() == before
    finally:
        pilot.close()
        pilot.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        _app.processEvents()
