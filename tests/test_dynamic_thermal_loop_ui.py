"""Finite service circuit UI: explicit creation, faithful editing and outputs."""
from __future__ import annotations

import copy
import csv
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog

from dynamic_tank import default_case, default_thermal_loop_case
from dynamic_tank_dialog import DynamicTankDialog, InstrumentationDialog


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


def test_new_loop_is_explicit_and_has_computed_supply(pilot):
    assert pilot.case_from_form()["schema_version"] == "dynamic-tank/v1"
    assert pilot.utility_group.isHidden()
    pilot.thermal_loop_example_button.click()
    case = pilot.case_from_form()
    assert case["schema_version"] == "dynamic-tank/v3"
    assert "utility_supply_temperature_K" not in case["inputs"]
    assert pilot.fields[("inputs", "utility_supply_temperature_K")].isHidden()
    assert not pilot.utility_group.isHidden()
    assert not pilot.calibration_button.isEnabled()
    assert "teóricas" in pilot.calibration_button.toolTip()
    assert "cerrado" in pilot.case_label.text()
    assert "sin contraste experimental" in pilot.provenance_label.text()


def test_loop_precision_and_only_edited_fields_change(pilot):
    case = default_thermal_loop_case()
    case["utility_loop"]["mass_kg"] = 123.456789012345
    case["utility_loop"]["initial_temperature_K"] = 315.1234567890123
    case["utility_loop"]["heater_efficiency"] = .87654321098765
    case["inputs"]["heater_power_request_W"] = 5432.123456789
    pilot.set_case(case)
    assert pilot.case_from_form() == case
    pilot.fields[("utility_loop", "initial_temperature_K")].setValue(55)
    expected = copy.deepcopy(case)
    expected["utility_loop"]["initial_temperature_K"] = 328.15
    assert pilot.case_from_form() == expected
    pilot.fields[("inputs", "heater_power_request_W")].setValue(80000)
    assert pilot.case_from_form()["inputs"]["heater_power_request_W"] == 80000
    assert pilot.case_from_form()["utility_loop"]["heater_max_power_W"] == case["utility_loop"]["heater_max_power_W"]


def test_switching_back_to_v1_restores_prescribed_service(pilot):
    pilot.set_case(default_thermal_loop_case())
    case = default_case()
    pilot.set_case(case)
    assert pilot.case_from_form() == case
    assert pilot.utility_group.isHidden()
    assert not pilot.fields[("inputs", "utility_supply_temperature_K")].isHidden()
    assert pilot.calibration_button.isEnabled()


@pytest.mark.parametrize("invalid", ["bad_mass", "prescribed_service", "static_head"])
def test_invalid_loop_import_is_atomic(pilot, invalid):
    before = pilot.case_from_form()
    bad = default_thermal_loop_case()
    if invalid == "bad_mass":
        bad["utility_loop"]["mass_kg"] = -1
    elif invalid == "prescribed_service":
        bad["inputs"]["utility_supply_temperature_K"] = 330
    else:
        bad["circuit"]["static_head_m"] = 1
    with pytest.raises(ValueError):
        pilot.set_case(bad)
    assert pilot.case_from_form() == before
    assert pilot.utility_group.isHidden()
    assert pilot.calibration_button.isEnabled()


def test_instrument_editor_preserves_loop_schema_and_equipment():
    original = default_thermal_loop_case()
    original["utility_loop"]["mass_kg"] = 97.1234567890123
    editor = InstrumentationDialog(original)
    try:
        assert editor.case_from_form() == original
        editor.fields[("temperature_sensors", "tank", "bias_K")].setText("0.75")
        changed = editor.case_from_form()
        assert changed["schema_version"] == "dynamic-tank/v3"
        assert changed["utility_loop"] == original["utility_loop"]
        assert changed["inputs"] == original["inputs"]
        assert changed["instrumentation"]["temperature_sensors"]["tank"]["bias_K"] == .75
    finally:
        _dispose(editor)


def test_new_case_keeps_previous_run_and_blocks_while_busy(pilot):
    previous = {"summary": {"status": "ok"}, "series": []}
    pilot._result = previous
    pilot._run_config = pilot.case_from_form()
    old_run = copy.deepcopy(pilot._run_config)
    pilot._worker = object()
    try:
        pilot._open_thermal_loop_example()
        assert pilot.case_from_form() == old_run
    finally:
        pilot._worker = None
    pilot._open_thermal_loop_example()
    assert pilot.case_from_form()["schema_version"] == "dynamic-tank/v3"
    assert pilot._result is previous
    assert pilot._run_config == old_run
    assert "última corrida" in pilot.status_label.text()


def test_calibration_has_explicit_v3_guard(pilot):
    pilot.set_case(default_thermal_loop_case())
    pilot._open_calibration()
    assert "referencias teóricas" in pilot.status_label.text()
    assert pilot._worker is None


def test_loop_worker_outputs_balance_plots_and_export(pilot, monkeypatch, tmp_path):
    case = default_thermal_loop_case()
    case["simulation"]["duration_s"] = 2
    case["simulation"]["output_interval_s"] = 1
    case["inputs"]["heater_power_request_W"] = 24000
    case["utility_loop"]["heater_max_power_W"] = 12000
    pilot.set_case(case)
    pilot.start_simulation()
    _wait_until(lambda: pilot._worker is None)
    result = pilot._result
    assert result["summary"]["status"] == "ok"
    assert "depósito de servicio" in pilot.details.toPlainText()
    assert "interna" in pilot.details.toPlainText()
    headings = [pilot.table.horizontalHeaderItem(i).text() for i in range(pilot.table.columnCount())]
    assert "Servicio: suministro (K)" in headings
    assert "Potencia limitada (0/1)" in headings
    if pilot._thermal_plot is not None:
        assert pilot.tabs.isTabVisible(pilot.tabs.indexOf(pilot._thermal_plot))
        temp_ax, power_ax = pilot._thermal_figure.axes
        assert {line.get_label() for line in temp_ax.lines} == {"Suministro del depósito", "Retorno de la camisa"}
        powers = {line.get_label(): list(line.get_ydata()) for line in power_ax.lines}
        assert powers["Electricidad solicitada"] == [24000] * len(result["series"])
        assert powers["Electricidad aplicada"] == [12000] * len(result["series"])
    output = tmp_path / "loop.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(output), "JSON"))
    pilot._export_json()
    assert json.loads(output.read_text(encoding="utf-8")) == result
    trajectory = tmp_path / "loop.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(trajectory), "CSV"))
    pilot._export_csv()
    with trajectory.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len(result["series"])
    assert float(rows[-1]["heater_applied_power_W"]) == 12000
    pilot.set_case(default_case())
    pilot._render_series([])
    if pilot._thermal_plot is not None:
        assert not pilot.tabs.isTabVisible(pilot.tabs.indexOf(pilot._thermal_plot))


def test_loop_file_and_template_keep_instrumented_contract(pilot, monkeypatch, tmp_path):
    case = default_thermal_loop_case()
    source = tmp_path / "case.json"
    source.write_text(json.dumps(case), encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(source), "JSON"))
    pilot._load_case()
    assert pilot.case_from_form() == case
    saved = tmp_path / "saved.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(saved), "JSON"))
    pilot._save_case()
    assert json.loads(saved.read_text(encoding="utf-8")) == case
    template = tmp_path / "measurements.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(template), "CSV"))
    pilot._save_measurement_template()
    header = template.read_text(encoding="utf-8")
    assert "tank_indicated_temperature_K" in header
    assert "utility_reservoir_temperature_K" in header
    assert "heater_applied_power_W" in header
