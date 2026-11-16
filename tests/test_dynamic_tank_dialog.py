"""Exercise the Qt lifecycle independently of numerical solver run times."""
import json
import os
import sys
import threading
import types

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog

from dynamic_tank_dialog import DynamicTankDialog

_app = QApplication.instance() or QApplication([])


def _case():
    return {
        "title": "Caso de prueba", "case_id": "qt-test",
        "provenance": {"data_kind": "synthetic"}, "events": [],
        "tank": {"volume_capacity_m3": 1.1234567, "initial_mass_kg": 100,
                 "initial_temperature_K": 298.15},
        "inputs": {"feed_flow_kg_s": 0, "outlet_flow_kg_s": 0,
                   "feed_temperature_K": 298.15,
                   "utility_supply_temperature_K": 343.15,
                   "temperature_setpoint_K": 323.15, "valve_opening": .5},
        "simulation": {"duration_s": 10},
        "controller": {"enabled": True, "direction": "heating"},
    }


def _result(status="ok"):
    return {
        "summary": {"status": status, "success": status == "ok",
                    "stop_reason": "", "final_time_s": 10},
        "series": [{"time_s": t, "tank_temperature_K": 298.15 + t,
                    "jacket_temperature_K": 343.15, "mass_kg": 100,
                    "volume_m3": .1, "valve_opening": .5,
                    "utility_flow_kg_s": .2} for t in (0, 10)],
        "audit": {"mass_residual_kg": 0},
        "metadata": {"validation_state": "synthetic_unvalidated"},
    }


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


@pytest.fixture
def dialog(monkeypatch):
    stub = types.SimpleNamespace(default_case=_case,
                                 simulate_dynamic_tank=lambda config, cancel=None: _result())
    monkeypatch.setitem(sys.modules, "dynamic_tank", stub)
    widget = DynamicTankDialog()
    yield widget, stub
    if widget._worker is not None:
        widget.cancel_simulation()
        _wait_until(lambda: widget._worker is None)
    widget.close()
    widget.deleteLater()
    _app.processEvents()


def test_form_preserves_precision_and_converts_only_edited_temperatures(dialog):
    widget, _ = dialog
    assert widget.case_from_form() == _case()
    widget.fields[("tank", "initial_temperature_K")].setValue(30)
    assert widget.case_from_form()["tank"]["initial_temperature_K"] == 303.15
    assert widget.case_from_form()["tank"]["volume_capacity_m3"] == 1.1234567
    bad = _case()
    bad["inputs"]["valve_opening"] = 2
    with pytest.raises(ValueError, match="fuera"):
        widget.set_case(bad)
    assert widget._config["inputs"]["valve_opening"] == .5


def test_worker_runs_off_gui_thread_and_returns_result(dialog):
    widget, stub = dialog
    main_ident = threading.get_ident()
    worker_ids = []

    def solve(config, cancel=None):
        worker_ids.append(threading.get_ident())
        assert config == _case()
        return _result()

    stub.simulate_dynamic_tank = solve
    widget.start_simulation()
    assert not widget.run_button.isEnabled()
    _wait_until(lambda: widget._worker is None)
    assert worker_ids and worker_ids[0] != main_ident
    assert widget.run_button.isEnabled()
    assert widget.export_json_button.isEnabled()
    assert widget.table.rowCount() == 2
    assert "Completado" in widget.status_label.text()


def test_close_cancels_running_worker_without_destroying_it(dialog):
    widget, stub = dialog
    entered = threading.Event()

    def solve(config, cancel=None):
        entered.set()
        while not cancel():
            # bounded wait happens on the worker, never on the Qt GUI thread
            threading.Event().wait(.002)
        return _result("cancelled")

    stub.simulate_dynamic_tank = solve
    widget.show()
    widget.start_simulation()
    _wait_until(entered.is_set)
    widget.close()
    assert widget._close_when_finished
    _wait_until(lambda: widget._worker is None and not widget.isVisible())
    assert widget._result["summary"]["status"] == "cancelled"


def test_solver_failure_reenables_form_without_inventing_result(dialog):
    widget, stub = dialog

    def invalid(config, cancel=None):
        raise ValueError("Temperatura fuera del dominio")

    stub.simulate_dynamic_tank = invalid
    widget.start_simulation()
    _wait_until(lambda: widget._worker is None)
    assert widget.run_button.isEnabled()
    assert not widget.export_json_button.isEnabled()
    assert widget._result is None
    assert "fuera del dominio" in widget.status_label.text()


def test_edited_form_marks_previous_result_stale(dialog):
    widget, _ = dialog
    widget.start_simulation()
    _wait_until(lambda: widget._worker is None)
    widget.fields[("inputs", "feed_flow_kg_s")].setValue(.1)
    assert "última corrida" in widget.status_label.text()
    assert widget._run_config["inputs"]["feed_flow_kg_s"] == 0


def test_measurement_metrics_render_with_escaped_provenance(dialog):
    widget, _ = dialog
    widget._comparison_finished({
        "summary": {"rows_in_range": 4, "rows_out_of_range": 1},
        "metrics": {"tank_temperature_K": {"unit": "K", "n": 4,
                    "rmse": 1.2, "mae": .9, "bias": -.2, "max_abs_error": 2}},
        "warnings": ["<script>bad</script>"],
        "conclusion": "No demuestra validación física.",
        "provenance": {"sha256": "abc123"},
    })
    rendered = widget.comparison_view.toPlainText()
    assert "1.2" in rendered and "abc123" in rendered
    assert "<script>bad</script>" in rendered
    assert "validación" in rendered


def test_export_retains_comparison_on_exact_run(dialog, monkeypatch, tmp_path):
    widget, _ = dialog
    widget.start_simulation()
    _wait_until(lambda: widget._worker is None)
    widget._comparison = {"provenance": {"sha256": "csv-hash"}, "metrics": {}}
    target = tmp_path / "result.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(target), "JSON"))
    widget._export_json()
    exported = json.loads(target.read_text(encoding="utf-8"))
    assert exported["measurement_comparison"] == widget._comparison
    assert exported["metadata"] == widget._result["metadata"]
    assert "measurement_comparison" not in widget._result


def test_modal_dialog_close_returns_without_blocking(dialog):
    widget, _ = dialog
    fired = []
    QTimer.singleShot(0, lambda: (fired.append(True), widget.close()))
    assert widget.exec() == 0
    assert fired


def test_editor_menu_opens_pilot_lazily(monkeypatch):
    import flowsheet_qt
    import dynamic_tank_dialog
    opened = []

    class FakeDialog:
        def __init__(self, parent):
            opened.append(parent)

        def exec(self):
            return 0

    monkeypatch.setattr(dynamic_tank_dialog, "DynamicTankDialog", FakeDialog)
    window = flowsheet_qt.FlowsheetMainWindow()
    try:
        simulation = next(action.menu() for action in window.menuBar().actions()
                          if action.text() == "&Simulación")
        action = next(action for action in simulation.actions()
                      if action.text() == "Tanque transitorio…")
        action.trigger()
        assert opened == [window]
    finally:
        window.close()
        window.deleteLater()
        _app.processEvents()
