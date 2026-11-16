"""Explicit instrument editing and distinct physical/indicated Qt channels."""
from __future__ import annotations

import copy
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog

from dynamic_tank_dialog import DynamicTankDialog, InstrumentationDialog
from dynamic_calibration_dialog import DynamicCalibrationDialog, _VARIABLE_LABELS
from dynamic_tank import default_case


_app = QApplication.instance() or QApplication([])


def _dispose(widget):
    widget.close()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    _app.processEvents()


@pytest.fixture
def pilot():
    widget = DynamicTankDialog()
    yield widget
    assert widget._worker is None
    _dispose(widget)


def _v2():
    from dynamic_tank import default_instrumented_case
    return default_instrumented_case()


def test_cancelling_instrument_editor_does_not_activate_v2(pilot, monkeypatch):
    original = pilot.case_from_form()
    monkeypatch.setattr(InstrumentationDialog, "exec", lambda self: QDialog.Rejected)
    pilot._open_instrumentation()
    assert pilot.case_from_form() == original
    assert pilot.case_from_form()["schema_version"] == "dynamic-tank/v1"
    assert "ideales" in pilot.case_label.text()


def test_explicit_activation_preserves_equipment_and_initial_states():
    original = default_case()
    original["tank"]["initial_temperature_K"] = 311.123456789
    original["inputs"]["valve_opening"] = .35
    original["provenance"]["data_kind"] = "measured"
    editor = InstrumentationDialog(original)
    try:
        assert original["schema_version"] == "dynamic-tank/v1"
        candidate = editor.case_from_form()
        assert candidate["schema_version"] == "dynamic-tank/v2"
        for key in original.keys() - {"schema_version", "provenance"}:
            assert candidate[key] == original[key]
        assert candidate["instrumentation"]["temperature_sensors"]["tank"]["initial_temperature_K"] == 311.123456789
        assert candidate["instrumentation"]["valve_actuator"]["initial_opening"] == .35
        assert candidate["provenance"]["data_kind"] == "mixed"
        assert "sintéticos" in candidate["provenance"]["notes"]
    finally:
        _dispose(editor)


def test_v2_fields_round_trip_without_precision_loss(pilot):
    case = _v2()
    case["instrumentation"]["temperature_sensors"]["tank"]["time_constant_s"] = 12.123456789012345
    case["instrumentation"]["temperature_sensors"]["wall"]["bias_K"] = -.234567891234
    pilot.set_case(case)
    assert pilot.case_from_form() == case
    editor = InstrumentationDialog(case)
    try:
        assert editor.case_from_form() == case
        editor.fields[("temperature_sensors", "tank", "bias_K")].setText("1.25")
        changed = editor.case_from_form()
        assert changed["instrumentation"]["temperature_sensors"]["tank"]["bias_K"] == 1.25
        assert changed["instrumentation"]["temperature_sensors"]["tank"]["time_constant_s"] == 12.123456789012345
        assert case["instrumentation"]["temperature_sensors"]["tank"]["bias_K"] == 0
    finally:
        _dispose(editor)


@pytest.mark.parametrize("invalid", ["nan", "inf", "-1", ""])
def test_invalid_instrument_edit_is_atomic_and_keeps_dialog_open(invalid):
    case = _v2()
    before = copy.deepcopy(case)
    editor = InstrumentationDialog(case)
    try:
        editor.fields[("temperature_sensors", "tank", "time_constant_s")].setText(invalid)
        editor.accept()
        assert editor.result_case is None
        assert editor.result() != QDialog.Accepted
        assert editor.error_label.text()
        assert case == before
    finally:
        _dispose(editor)


def test_invalid_import_does_not_partially_replace_form(pilot):
    original = pilot.case_from_form()
    bad = _v2()
    bad["tank"]["initial_mass_kg"] = 600
    bad["instrumentation"]["valve_actuator"]["initial_opening"] = 2
    with pytest.raises(ValueError):
        pilot.set_case(bad)
    assert pilot.case_from_form() == original


def test_applied_instrumentation_keeps_previous_run_snapshot(pilot, monkeypatch):
    previous = {"series": [], "summary": {"status": "ok"}}
    pilot._result = previous
    pilot._run_config = pilot.case_from_form()
    old_run = copy.deepcopy(pilot._run_config)

    def save(editor):
        editor.fields[("temperature_sensors", "tank", "bias_K")].setText("0.75")
        editor.accept()
        return editor.result()

    monkeypatch.setattr(InstrumentationDialog, "exec", save)
    pilot._open_instrumentation()
    assert pilot._result is previous
    assert pilot._run_config == old_run
    assert pilot.case_from_form()["schema_version"] == "dynamic-tank/v2"
    assert "última corrida" in pilot.status_label.text()


def test_charts_and_table_distinguish_indication_command_and_physics(pilot):
    case = _v2()
    pilot.set_case(case)
    pilot._run_config = copy.deepcopy(case)
    series = [{"time_s": t, "tank_temperature_K": 300 + t,
               "wall_temperature_K": 310 + t, "jacket_temperature_K": 320 + t,
               "tank_indicated_temperature_K": 298 + t,
               "wall_indicated_temperature_K": 308 + t,
               "jacket_indicated_temperature_K": 318 + t,
               "valve_command": .9, "valve_opening": .2 + t * .02,
               "mass_kg": 500, "volume_m3": .5, "utility_flow_kg_s": .1}
              for t in (0, 10)]
    pilot._render_series(series)
    headings = [pilot.table.horizontalHeaderItem(i).text() for i in range(pilot.table.columnCount())]
    assert "Tanque físico (K)" in headings
    assert "Tanque indicado (K)" in headings
    assert "Consigna de válvula (0-1)" in headings
    if pilot._plot is not None:
        labels = {line.get_label() for line in pilot._figure.axes[0].lines}
        assert {"Tanque físico", "Tanque indicado"} <= labels
        valve = {line.get_label(): list(line.get_ydata()) for line in pilot._valve_figure.axes[0].lines}
        assert valve["Posición real"] != valve["Consigna de válvula"]
    pilot.set_case(default_case())
    pilot._render_series([{key: value for key, value in row.items()
                           if "indicated" not in key and key != "valve_command"} for row in series])
    assert pilot.table.columnCount() == len(pilot._TABLE_COLUMNS)


def test_instrumented_template_and_comparison_use_indicated_labels(pilot, monkeypatch, tmp_path):
    pilot.set_case(_v2())
    output = tmp_path / "measurements.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(output), "CSV"))
    pilot._save_measurement_template()
    header = output.read_text(encoding="utf-8")
    assert "tank_indicated_temperature_K" in header
    pilot._comparison_finished({"metrics": {"tank_indicated_temperature_K": {"unit": "K", "n": 2}}})
    assert "Tanque indicado" in pilot.comparison_view.toPlainText()


def test_calibration_scope_notes_are_visible_and_escaped():
    widget = DynamicCalibrationDialog()
    try:
        widget._render_diagnostics({"scope_notes": ["Sesgos <declarados>, no estimados"], "summary": {}})
        assert "Sesgos <declarados>, no estimados" in widget.diagnostics_view.toPlainText()
        assert "indicada" in _VARIABLE_LABELS["tank_indicated_temperature_K"]
        assert "física" in _VARIABLE_LABELS["tank_temperature_K"]
    finally:
        _dispose(widget)


def test_instrument_controls_do_not_open_while_a_worker_is_active(pilot, monkeypatch):
    opened = []
    monkeypatch.setattr(InstrumentationDialog, "exec", lambda self: opened.append(True))
    pilot._worker = object()
    try:
        pilot._open_instrumentation()
        pilot._open_instrumented_example()
        assert not opened
    finally:
        pilot._worker = None


def test_example_button_loads_versioned_instrumented_case(pilot):
    pilot.instrumentation_example_button.click()
    case = pilot.case_from_form()
    assert case["schema_version"] == "dynamic-tank/v2"
    assert case["provenance"]["data_kind"] == "synthetic"
    assert set(case["instrumentation"]["temperature_sensors"]) == {"tank", "wall", "jacket"}
    assert "sintética" in pilot.status_label.text()
