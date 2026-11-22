import copy
import csv
import json
import os
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QTableWidgetItem
import pytest

import dynamic_network_dialog as ui
from dynamic_network import simulate_dynamic_network, validate_network
from dynamic_network_component_examples import example_cases
from dynamic_network_cli import main

_app = QApplication.instance() or QApplication([])


def wait_until(predicate, timeout_ms=10000):
    if predicate(): return
    loop = QEventLoop()
    poll, deadline = QTimer(), QTimer()
    poll.setInterval(5); poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    deadline.setSingleShot(True); deadline.timeout.connect(loop.quit)
    poll.start(); deadline.start(timeout_ms); loop.exec(); poll.stop(); deadline.stop()
    assert predicate(), "Worker did not finish"


@pytest.fixture
def dialog():
    w = ui.DynamicNetworkDialog()
    yield w
    if w._worker is not None:
        w.cancel_simulation(); wait_until(lambda: w._worker is None)
    w.close(); w.deleteLater(); _app.processEvents()


def test_form_roundtrip_preserves_full_case_and_loaded_file_on_bad_input(dialog):
    expected = validate_network(example_cases()["coupled_recirculation.json"])
    assert dialog.case_from_form() == expected
    bad = copy.deepcopy(expected); bad["edges"][0]["target"] = "HX1.hot_out"
    with pytest.raises(ValueError): dialog.set_case(bad)
    assert dialog.case_from_form() == expected
    dialog.connections.item(0, 3).setText("0.1")
    dialog.start_simulation()
    assert dialog._worker is None
    assert "inventario" in dialog.status_label.text()


def test_real_joint_solver_runs_off_gui_thread_and_renders_profiles(dialog, monkeypatch):
    ids = []
    original = ui.simulate_dynamic_network
    def run(config, cancel=None):
        ids.append(threading.get_ident())
        return original(config, cancel=cancel)
    monkeypatch.setattr(ui, "simulate_dynamic_network", run)
    dialog.start_simulation()
    assert not dialog.run_button.isEnabled()
    wait_until(lambda: dialog._worker is None)
    assert ids and ids[0] != threading.get_ident()
    assert dialog._result["summary"]["success"]
    assert dialog.results_table.rowCount() > 0 and dialog.profile_table.rowCount() == 6
    assert dialog.export_json_button.isEnabled()
    dialog.profile_sample.setValue(0)
    assert float(dialog.profile_table.item(0, 1).text()) == 350.
    assert float(dialog.profile_table.item(0, 2).text()) == 290.
    dialog.duration.setText("350")
    assert "ultima corrida" in dialog.status_label.text()
    assert dialog._result["configuration"]["simulation"]["duration_s"] == 300.


def test_close_and_escape_cancel_without_destroying_worker(dialog, monkeypatch):
    started = threading.Event()
    def run(config, cancel=None):
        started.set()
        while not cancel(): threading.Event().wait(.002)
        return simulate_dynamic_network(config, cancel=cancel)
    monkeypatch.setattr(ui, "simulate_dynamic_network", run)
    dialog.show(); dialog.start_simulation(); wait_until(started.is_set)
    dialog.reject()
    assert dialog._close_when_finished
    wait_until(lambda: dialog._worker is None and not dialog.isVisible())
    assert dialog._result["summary"]["status"] == "cancelled"


def test_failure_does_not_export_previous_success(dialog, monkeypatch):
    dialog._completed(simulate_dynamic_network(dialog.case_from_form(), cancel=lambda: True))
    def fail(*a, **k): raise ValueError("fallo controlado")
    monkeypatch.setattr(ui, "simulate_dynamic_network", fail)
    dialog.start_simulation(); wait_until(lambda: dialog._worker is None)
    assert dialog._result is None
    assert dialog.run_button.isEnabled() and not dialog.export_json_button.isEnabled()
    assert "fallo controlado" in dialog.status_label.text()


def test_add_units_and_connect_new_exchanger_through_editor(dialog):
    dialog._add_exchanger(); dialog._add_tank(); dialog._add_source()
    c = dialog.case_from_form()
    assert len(c["heat_exchangers"]) == 2 and len(c["nodes"]) == 3 and len(c["sources"]) == 1
    # Insert a second exchanger in the hot return using its explicit ports.
    dialog.connections.item(1, 2).setText("HX2.hot_in")
    dialog._add_connection()
    row = dialog.connections.rowCount()-1
    for col, value in enumerate(("second_return", "HX2.hot_out", "HotTank", ".2")):
        dialog.connections.setItem(row, col, QTableWidgetItem(value))
    # A global stop/restart also changes this new segment.
    for time, flow in ((40., 0.), (70., .2)):
        dialog._append_row(dialog.events_table, (str(time), "Conexion", "second_return", "Caudal (kg/s)", str(flow)))
    result = simulate_dynamic_network(dialog.case_from_form())
    assert result["summary"]["success"]
    assert set(result["series"][-1]["heat_exchangers"]) == {"HX1", "HX2"}


def test_uniform_mesh_refines_but_nonuniform_initial_profile_is_not_silently_resampled(dialog):
    dialog.exchangers.item(0, 1).setText("12")
    c = dialog.case_from_form()
    assert len(c["heat_exchangers"][0]["initial"]["hot_temperature_K"]) == 12
    c["heat_exchangers"][0]["initial"]["hot_temperature_K"][0] = 340.
    dialog.set_case(c)
    dialog.exchangers.item(0, 1).setText("6")
    with pytest.raises(ValueError, match="no es uniforme"): dialog.case_from_form()


def test_editor_exports_exact_run_and_protects_loaded_case(dialog, monkeypatch, tmp_path):
    original = tmp_path/"case.json"
    config = dialog.case_from_form()
    original.write_text(json.dumps(config), encoding="utf-8")
    dialog.set_case(config, input_path=str(original))
    dialog.start_simulation(); wait_until(lambda: dialog._worker is None)
    before = original.read_bytes()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(original), ""))
    dialog._export_json()
    assert original.read_bytes() == before
    result, trajectory = tmp_path/"result.json", tmp_path/"profiles.csv"
    dialog.duration.setText("450")
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(result), ""))
    dialog._export_json()
    assert json.loads(result.read_text(encoding="utf-8"))["configuration"]["simulation"]["duration_s"] == 300.
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(trajectory), ""))
    dialog._export_csv()
    with trajectory.open(encoding="utf-8", newline="") as f: rows = list(csv.DictReader(f))
    assert {r["unit_kind"] for r in rows} == {"tank", "heat_exchanger_cell"}
    assert all(r["data_kind"] == "synthetic" for r in rows)
    assert len(rows) == 8*len(dialog._result["series"])


def test_network_menu_opens_connected_editor(monkeypatch):
    import flowsheet_qt
    opened = []
    class Fake:
        def __init__(self, parent): opened.append(parent)
        def exec(self): return 0
    monkeypatch.setattr(ui, "DynamicNetworkDialog", Fake)
    window = flowsheet_qt.FlowsheetMainWindow()
    try:
        menu = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Simulación")
        action = next(a for a in menu.actions() if a.text() == "Red transitoria e intercambiadores…")
        action.trigger()
        assert opened == [window]
    finally:
        window.close(); window.deleteLater(); _app.processEvents()


def test_cli_connected_case_roundtrip_and_heterogeneous_csv(tmp_path):
    case, result, csvfile = [tmp_path/name for name in ("case.json", "result.json", "profiles.csv")]
    assert main(["--example", "coupled_feed", "--write-example", str(case)]) == 0
    assert main([str(case), "--out", str(result), "--csv", str(csvfile)]) == 0
    run = json.loads(result.read_text(encoding="utf-8"))
    assert run["schema_version"] == "dynamic-network/v2"
    with csvfile.open(encoding="utf-8", newline="") as f: rows = list(csv.DictReader(f))
    assert len(rows) == 6*len(run["series"])
    assert all(row["component_classification"] == "analytical_limit" for row in rows if row["unit_kind"] == "heat_exchanger_cell")


def test_editing_a_published_case_marks_documented_adaptation(dialog):
    from dynamic_network_examples import example_cases as legacy_cases
    case = legacy_cases()["energyplus_mixed_tank.json"]
    dialog.set_case(case)
    assert dialog.case_from_form()["provenance"]["classification"] == "published_reproduction"
    dialog.sources.item(0, 1).setText("300")
    assert dialog.case_from_form()["provenance"]["classification"] == "documented_adaptation"
