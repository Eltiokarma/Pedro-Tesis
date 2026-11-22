"""Qt editor for connected transient tanks/exchangers; cancellable joint solver."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import threading

from PySide6.QtCore import QThread, Signal, QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QLineEdit, QTabWidget, QTableWidget, QTableWidgetItem, QWidget, QFileDialog, QAbstractItemView, QSpinBox)

from dynamic_network import validate_network, simulate_dynamic_network
from dynamic_network_component_examples import example_cases
from dynamic_network_components import component_from_case, PORTS
from dynamic_heat_exchanger import default_case


class _NetworkTask(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = copy.deepcopy(config)
        self.cancel_event = threading.Event()

    def run(self):
        try: self.completed.emit(simulate_dynamic_network(self.config, cancel=self.cancel_event.is_set))
        except Exception as exc: self.failed.emit(f"{type(exc).__name__}: {exc}")


class DynamicNetworkDialog(QDialog):
    """Explicit transient circuit; never infers inventories from the stationary PFD."""
    TANK_KEYS = ("id", "initial_mass_kg", "initial_temperature_K", "initial_tracer_mass_fraction", "heat_power_W")
    SOURCE_KEYS = ("id", "temperature_K", "tracer_mass_fraction")
    GROUP_LABELS = {"edges": "Conexion", "sources": "Alimentacion", "nodes": "Tanque"}
    VALUE_LABELS = {"mass_flow_kg_s": "Caudal (kg/s)", "temperature_K": "Temperatura (K)",
                    "tracer_mass_fraction": "Trazador (0–1)", "heat_power_W": "Potencia (W)"}
    FLOW_LABELS = {"co_current": "Cocorriente", "counter_current": "Contracorriente"}

    def __init__(self, parent=None):
        super().__init__(parent)
        import pfd_fonts
        pfd_fonts.load_all()
        if pfd_fonts.available(): self.setFont(QFont(pfd_fonts.SANS, 10))
        self.setWindowTitle("Red transitoria: tanques e intercambiadores")
        self.resize(1160, 760)
        self._config = self._result = self._run_config = self._worker = self._input_path = None
        self._close_when_finished = self._loading = False
        outer = QVBoxLayout(self)
        info = QLabel("Conecte los cuatro puertos del intercambiador con tanques o alimentaciones. "
                      "Cada circuito conserva su inventario con los caudales impuestos.")
        info.setWordWrap(True); outer.addWidget(info)
        tools = QHBoxLayout()
        self.examples = QComboBox()
        self.examples.addItem("Dos circuitos con recirculacion", "coupled_recirculation.json")
        self.examples.addItem("Alimentaciones y depositos de descarga", "coupled_feed.json")
        tools.addWidget(self.examples)
        self.edit_controls = [self.examples]
        for label, slot in (("Cargar ejemplo", self._load_example), ("Abrir caso", self._load_case), ("Guardar copia del caso", self._save_case)):
            self.edit_controls.append(self._button(tools, label, slot))
        outer.addLayout(tools)
        form = QHBoxLayout()
        self.duration, self.interval, self.method = QLineEdit(), QLineEdit(), QComboBox()
        self.method.addItems(["BDF", "Radau"])
        for label, control in (("Duracion (s)", self.duration), ("Muestra cada (s)", self.interval), ("Metodo", self.method)):
            form.addWidget(QLabel(label)); form.addWidget(control); self.edit_controls.append(control)
        outer.addLayout(form)
        self.fluid_label = QLabel(); outer.addWidget(self.fluid_label)
        self.tabs = QTabWidget(); outer.addWidget(self.tabs)
        self.tanks = self._table(["Tanque", "Masa inicial (kg)", "Temperatura inicial (K)", "Trazador (0–1)", "Potencia (W)"])
        self.sources = self._table(["Alimentacion", "Temperatura (K)", "Trazador (0–1)"])
        self.exchangers = self._table(["Equipo", "Tramos", "Orientacion"])
        self.connections = self._table(["Conexion", "Origen", "Destino (vacio: descarga)", "Caudal (kg/s)"])
        self.events_table = self._table(["Tiempo (s)", "Grupo", "Elemento", "Propiedad", "Valor"])
        for title, table, slot in (("Tanques", self.tanks, self._add_tank), ("Alimentaciones", self.sources, self._add_source),
                                  ("Intercambiadores", self.exchangers, self._add_exchanger),
                                  ("Conexiones", self.connections, self._add_connection), ("Cambios programados", self.events_table, self._add_event)):
            page = QWidget(); column = QVBoxLayout(page); column.addWidget(table)
            buttons = QHBoxLayout(); self.edit_controls.append(self._button(buttons, "Agregar", slot))
            if table in (self.connections, self.events_table):
                self.edit_controls.append(self._button(buttons, "Eliminar fila", lambda checked=False, t=table: self._remove_row(t)))
            column.addLayout(buttons); self.tabs.addTab(page, title); self.edit_controls.append(table)
            table.itemChanged.connect(self._mark_stale)
        self.ports_label = QLabel(); self.ports_label.setWordWrap(True); outer.addWidget(self.ports_label)
        self.results_table = self._table(["Tiempo (s)", "Equipo", "Tanque (K)", "Salida h (K)", "Salida c (K)"])
        self.results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabs.addTab(self.results_table, "Resultados")
        page = QWidget(); column = QVBoxLayout(page); selection = QHBoxLayout()
        self.profile_unit, self.profile_sample, self.profile_time = QComboBox(), QSpinBox(), QLabel()
        for label, control in (("Equipo", self.profile_unit), ("Muestra", self.profile_sample)):
            selection.addWidget(QLabel(label)); selection.addWidget(control)
        selection.addWidget(self.profile_time); column.addLayout(selection)
        self.profile_table = self._table(["Posicion (m)", "Fluido h (K)", "Fluido c (K)", "Pared (K)", "Trazador h", "Trazador c"])
        self.profile_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        column.addWidget(self.profile_table); self.tabs.addTab(page, "Perfiles")
        self.profile_unit.currentIndexChanged.connect(self._render_profile)
        self.profile_sample.valueChanged.connect(self._render_profile)
        actions = QHBoxLayout()
        self.run_button = self._button(actions, "Simular red", self.start_simulation)
        self.cancel_button = self._button(actions, "Cancelar", self.cancel_simulation)
        self.export_json_button = self._button(actions, "Exportar resultado", self._export_json)
        self.export_csv_button = self._button(actions, "Exportar perfiles CSV", self._export_csv)
        outer.addLayout(actions)
        self.status_label = QLabel(); self.status_label.setTextFormat(Qt.PlainText); self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)
        self.duration.textChanged.connect(self._mark_stale); self.interval.textChanged.connect(self._mark_stale)
        self.method.currentIndexChanged.connect(self._mark_stale)
        self.set_case(example_cases()["coupled_recirculation.json"]); self._set_busy(False)

    @staticmethod
    def _button(layout, text, slot):
        button = QPushButton(text); button.clicked.connect(slot); layout.addWidget(button)
        return button

    @staticmethod
    def _table(headers):
        table = QTableWidget(0, len(headers)); table.setHorizontalHeaderLabels(headers)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    @staticmethod
    def _put(table, rows, *, fixed_first=False):
        table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                item = QTableWidgetItem("" if value is None else str(value))
                if fixed_first and j == 0: item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(i, j, item)
        table.resizeColumnsToContents()

    @staticmethod
    def _rows(table):
        return [[table.item(i, j).text().strip() if table.item(i, j) else "" for j in range(table.columnCount())]
                for i in range(table.rowCount())]

    def set_case(self, config, *, input_path=None):
        if self._worker is not None: raise ValueError("Espere a que termine la simulacion.")
        normalized = validate_network(config)
        self._loading = True
        try:
            self._config, self._input_path = normalized, input_path
            self.duration.setText(str(normalized["simulation"]["duration_s"]))
            self.interval.setText(str(normalized["simulation"]["output_interval_s"]))
            self.method.setCurrentText(normalized["simulation"]["method"])
            self._put(self.tanks, [[n[k] for k in self.TANK_KEYS] for n in normalized["nodes"]], fixed_first=True)
            self._put(self.sources, [[n[k] for k in self.SOURCE_KEYS] for n in normalized["sources"]], fixed_first=True)
            self._put(self.exchangers, [[h["id"], h["cells"], self.FLOW_LABELS[h["flow_arrangement"]]] for h in normalized.get("heat_exchangers", [])], fixed_first=True)
            self._put(self.connections, [[e[k] for k in ("id", "source", "target", "mass_flow_kg_s")] for e in normalized["edges"]])
            self._put(self.events_table, [[e["time_s"], self.GROUP_LABELS[section], identifier, self.VALUE_LABELS[key], value] for e in normalized["events"]
                for section, updates in e["changes"].items() for identifier, values in updates.items() for key, value in values.items()])
            self.fluid_label.setText(f"Fluido comun: Cp = {normalized['fluid']['cp_J_kg_K']:g} J/(kg K); densidad = {normalized['fluid']['density_kg_m3']:g} kg/m³.")
            self.ports_label.setText("Puertos: "+", ".join(h["id"]+"."+p for h in normalized.get("heat_exchangers", []) for p in PORTS))
        finally: self._loading = False
        self._mark_stale()

    def case_from_form(self):
        c = copy.deepcopy(self._config)
        c["simulation"].update(duration_s=float(self.duration.text()), output_interval_s=float(self.interval.text()), method=self.method.currentText())
        for table, section, keys in ((self.tanks, "nodes", self.TANK_KEYS), (self.sources, "sources", self.SOURCE_KEYS)):
            lookup = {n["id"]: n for n in c[section]}
            for row in self._rows(table):
                for key, value in zip(keys[1:], row[1:]): lookup[row[0]][key] = float(value)
        for identifier, cells, arrangement in self._rows(self.exchangers):
            h = next(h for h in c["heat_exchangers"] if h["id"] == identifier)
            n = int(cells)
            if n != h["cells"]:
                for profiles in (h["initial"], h["initial_tracer_mass_fraction"]):
                    for key, values in profiles.items():
                        if isinstance(values, list):
                            if len(set(values)) != 1: raise ValueError("El perfil inicial no es uniforme; cargue un caso con la nueva malla explicita.")
                            profiles[key] = values[0]
            h.update(cells=n, flow_arrangement={v: k for k, v in self.FLOW_LABELS.items()}.get(arrangement, arrangement))
        c["edges"] = [{"id": row[0], "source": row[1], "target": row[2] or None, "mass_flow_kg_s": float(row[3])} for row in self._rows(self.connections)]
        grouped = {}
        for time, section, identifier, key, value in self._rows(self.events_table):
            section = {v: k for k, v in self.GROUP_LABELS.items()}.get(section, section)
            key = {v: k for k, v in self.VALUE_LABELS.items()}.get(key, key)
            values = grouped.setdefault(float(time), {}).setdefault(section, {}).setdefault(identifier, {})
            if key in values: raise ValueError("Dos cambios de la misma propiedad en el mismo instante.")
            values[key] = float(value)
        c["events"] = [{"time_s": t, "changes": values} for t, values in sorted(grouped.items())]
        normalized = validate_network(c)
        if normalized != self._config and normalized["provenance"]["classification"] == "published_reproduction":
            normalized["provenance"]["classification"] = "documented_adaptation"
            normalized["provenance"]["notes"] += " Parametros modificados en el editor de redes respecto al caso publicado."
        return normalized

    def _mark_stale(self, *args):
        if not self._loading and self._worker is None:
            self.status_label.setText("Cambios pendientes de simular. Las exportaciones corresponden a la ultima corrida." if self._result else "Listo para comprobar conexiones y simular. Datos sinteticos.")

    def _add_unit(self, section):
        try:
            from dynamic_network_examples import _node
            c = self.case_from_form()
            prefix = {"nodes": "Tank", "sources": "Feed", "heat_exchangers": "HX"}[section]
            ids = {n["id"] for s in ("nodes", "sources", "heat_exchangers") for n in c.get(s, [])}
            i = 1
            while prefix+str(i) in ids: i += 1
            name, temperature = prefix+str(i), c["ambient_temperature_K"]
            if section == "nodes": unit = _node(name, 20., temperature)
            elif section == "sources": unit = {"id": name, "temperature_K": temperature, "tracer_mass_fraction": 0.}
            else:
                h = default_case()
                h["hot_fluid"] = copy.deepcopy(c["fluid"]); h["cold_fluid"] = copy.deepcopy(c["fluid"])
                h["simulation"] = copy.deepcopy(c["simulation"])
                h["initial"] = {k: temperature for k in h["initial"]}
                h["inputs"].update(hot_inlet_temperature_K=temperature, cold_inlet_temperature_K=temperature)
                unit = component_from_case(name, h); c["schema_version"] = "dynamic-network/v2"
            c.setdefault(section, []).append(unit)
            self.set_case(c, input_path=self._input_path)
        except (ValueError, TypeError, KeyError) as exc: self.status_label.setText(str(exc))

    def _add_tank(self): self._add_unit("nodes")
    def _add_source(self): self._add_unit("sources")
    def _add_exchanger(self): self._add_unit("heat_exchangers")

    def _append_row(self, table, values):
        i = table.rowCount(); table.insertRow(i)
        for j, value in enumerate(values): table.setItem(i, j, QTableWidgetItem(str(value)))

    def _add_connection(self): self._append_row(self.connections, (f"link{self.connections.rowCount()+1}", "", "", "0"))
    def _add_event(self):
        first = self.connections.item(0, 0)
        self._append_row(self.events_table, ("10", "Conexion", first.text() if first else "", "Caudal (kg/s)", "0"))

    def _remove_row(self, table):
        if table.currentRow() >= 0: table.removeRow(table.currentRow()); self._mark_stale()

    def _set_busy(self, busy):
        for control in self.edit_controls: control.setEnabled(not busy)
        self.run_button.setEnabled(not busy); self.cancel_button.setEnabled(busy)
        self.export_json_button.setEnabled(not busy and self._result is not None)
        self.export_csv_button.setEnabled(not busy and self._result is not None)

    def start_simulation(self):
        if self._worker is not None: return
        try: config = self.case_from_form()
        except (ValueError, TypeError, KeyError) as exc: self.status_label.setText(str(exc)); return
        self._run_config, self._result = copy.deepcopy(config), None
        self.results_table.setRowCount(0); self.profile_table.setRowCount(0)
        self._worker = _NetworkTask(config, self)
        self._worker.completed.connect(self._completed); self._worker.failed.connect(self._failed); self._worker.finished.connect(self._finished)
        self._set_busy(True); self.status_label.setText("Calculando tanques e intercambiadores en una misma simulacion…")
        self._worker.start()

    def cancel_simulation(self):
        if self._worker is not None:
            self._worker.cancel_event.set(); self.cancel_button.setEnabled(False)
            self.status_label.setText("Cancelacion solicitada; esperando el cierre del calculo.")

    def _completed(self, result):
        self._result = result
        summary = result["summary"]
        status = {"ok": "Completado", "cancelled": "Cancelado", "limit": "Limite alcanzado", "error": "Error"}.get(summary["status"], summary["status"])
        residual = max(result["audit"]["max_relative_residual"].values())
        self.status_label.setText(f"{status}: t = {summary['final_time_s']:g} s. Residuo relativo maximo = {residual:.3g}. "+("" if summary["success"] else summary["stop_reason"]))
        points = result["series"][::max(1, (len(result["series"])+299)//300)]
        if points[-1] is not result["series"][-1]: points.append(result["series"][-1])
        rows = []
        for p in points:
            rows.extend([[p["time_s"], name, f"{s['temperature_K']:.7g}", "", ""] for name, s in p["nodes"].items()])
            rows.extend([[p["time_s"], name, "", f"{s['hot_outlet_temperature_K']:.7g}", f"{s['cold_outlet_temperature_K']:.7g}"] for name, s in p.get("heat_exchangers", {}).items()])
        self._put(self.results_table, rows)
        self.profile_unit.clear(); self.profile_unit.addItems(list(result["metadata"].get("heat_exchangers", {})))
        self.profile_sample.setRange(0, len(result["series"])-1); self.profile_sample.setValue(len(result["series"])-1)
        self._render_profile(); self.tabs.setCurrentWidget(self.results_table)

    def _render_profile(self, *args):
        if not self._result or not self.profile_unit.currentText(): return
        name = self.profile_unit.currentText()
        point = self._result["series"][min(self.profile_sample.value(), len(self._result["series"])-1)]
        unit = point["heat_exchangers"][name]
        positions = self._result["metadata"]["heat_exchangers"][name]["cell_centres_m"]
        self.profile_time.setText(f"t = {point['time_s']:g} s")
        keys = [s+"_temperature_K" for s in ("hot", "cold", "wall")]+[s+"_tracer_mass_fraction" for s in ("hot", "cold")]
        self._put(self.profile_table, [[f"{x:.7g}", *[f"{unit[k][i]:.7g}" for k in keys]] for i, x in enumerate(positions)])

    def _failed(self, message): self.status_label.setText("No se completo la simulacion: "+message)
    def _finished(self):
        worker, self._worker = self._worker, None
        worker.deleteLater(); self._set_busy(False)
        if self._close_when_finished: QTimer.singleShot(0, self.close)

    def closeEvent(self, event):
        if self._worker is not None: self._close_when_finished = True; self.cancel_simulation(); event.ignore()
        else: super().closeEvent(event)

    def reject(self):
        if self._worker is not None: self._close_when_finished = True; self.cancel_simulation()
        else: super().reject()

    def _load_example(self):
        try: self.set_case(example_cases()[self.examples.currentData()])
        except ValueError as exc: self.status_label.setText(str(exc))

    def _load_case(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir red transitoria", "", "JSON (*.json)")
        if path:
            try: self.set_case(json.loads(Path(path).read_text(encoding="utf-8-sig")), input_path=path)
            except (OSError, ValueError, TypeError, KeyError) as exc: self.status_label.setText(str(exc))

    def _save(self, kind):
        if kind != "case" and self._result is None: return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar "+kind, "red_transitoria."+("csv" if kind == "csv" else "json"), "CSV (*.csv)" if kind == "csv" else "JSON (*.json)")
        if not path: return
        try:
            from dynamic_calibration_cli import _write_json, guard_outputs
            guard_outputs([path], [self._input_path] if self._input_path else [], overwrite=True)
            if kind == "csv":
                from dynamic_cli import export_trajectory
                from dynamic_network_cli import trajectory_rows
                export_trajectory({"series": trajectory_rows(self._result)}, path)
            else: _write_json(path, self.case_from_form() if kind == "case" else self._result, overwrite=True)
            self.status_label.setText("Archivo guardado: "+path)
        except (OSError, ValueError, TypeError, KeyError) as exc: self.status_label.setText(str(exc))

    def _save_case(self): self._save("case")
    def _export_json(self): self._save("result")
    def _export_csv(self): self._save("csv")
