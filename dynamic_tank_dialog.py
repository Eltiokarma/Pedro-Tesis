"""Qt workbench for the bounded dynamic tank pilot (independent of a PFD).

The worker owns a snapshot of the inputs; Qt widgets are only touched on the
GUI thread. Closing during a solve requests cancellation and waits through the
event loop, so no live QThread is destroyed. SI is retained in files; the form
and temperature chart use degrees Celsius for convenience.
"""
from __future__ import annotations

import copy
from collections import Counter
import csv
import html
import json
import math
from pathlib import Path
import threading

from PySide6.QtCore import QThread, QTimer, Signal, Slot, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QSplitter, QTabWidget, QTableWidget, QTableWidgetItem, QTextBrowser,
    QVBoxLayout, QWidget,
)


class InstrumentationDialog(QDialog):
    """Edit a complete instrument configuration without mutating the open case."""

    def __init__(self, case, parent=None):
        super().__init__(parent)
        import pfd_fonts
        pfd_fonts.load_all()
        if pfd_fonts.available():
            self.setFont(QFont(pfd_fonts.SANS, 10))
        from dynamic_tank import default_instrumented_case, validate_case
        self._original = copy.deepcopy(case)
        self._candidate = copy.deepcopy(case)
        if case.get("schema_version") == "dynamic-tank/v1":
            instrumented = default_instrumented_case()
            self._candidate["schema_version"] = "dynamic-tank/v2"
            self._candidate["instrumentation"] = instrumented["instrumentation"]
            for section in ("tank", "wall", "jacket"):
                self._candidate["instrumentation"]["temperature_sensors"][section]["initial_temperature_K"] = (
                    case[section]["initial_temperature_K"])
            self._candidate["instrumentation"]["valve_actuator"]["initial_opening"] = case["inputs"]["valve_opening"]
        validate_case(self._candidate)
        self.result_case = None
        self.fields = {}
        self.setWindowTitle("Instrumentación del tanque")
        self.resize(720, 440)
        self.setMinimumSize(560, 420)
        outer = QVBoxLayout(self)
        hint = QLabel(
            "La lectura del sensor puede retrasarse y tener sesgo. El control utiliza esa lectura; "
            "los balances utilizan la temperatura física. La hidráulica utiliza la posición real de la válvula. "
            "Los valores iniciales propuestos son sintéticos; requieren caracterización del equipo.")
        hint.setWordWrap(True)
        outer.addWidget(hint)
        tabs = QTabWidget()
        for section, label in (("tank", "Tanque"), ("wall", "Pared"), ("jacket", "Camisa")):
            page = QWidget()
            form = QFormLayout(page)
            sensor = self._candidate["instrumentation"]["temperature_sensors"][section]
            for key, title in (("time_constant_s", "Constante de tiempo (s; 0 = ideal)"),
                               ("bias_K", "Sesgo de la indicación (K)"),
                               ("initial_temperature_K", "Temperatura inicial del sensor (K)")):
                self._field(form, ("temperature_sensors", section, key), title, sensor[key])
            note = QLabel("La constante de tiempo representa inercia térmica, no tiempo muerto. "
                          "El sesgo se suma al estado del sensor y no cambia el balance de energía.")
            note.setWordWrap(True)
            form.addRow(note)
            tabs.addTab(page, label)
        page = QWidget()
        form = QFormLayout(page)
        actuator = self._candidate["instrumentation"]["valve_actuator"]
        self.actuator_enabled = QCheckBox("Actuador con dinámica de movimiento")
        self.actuator_enabled.setChecked(actuator["enabled"])
        form.addRow(self.actuator_enabled)
        for key, title in (("time_constant_s", "Constante de tiempo (s)"),
                           ("opening_rate_per_s", "Velocidad máxima de apertura (fracción/s)"),
                           ("closing_rate_per_s", "Velocidad máxima de cierre (fracción/s)"),
                           ("initial_opening", "Posición inicial real (0–1)")):
            self._field(form, ("valve_actuator", key), title, actuator[key])
        self._field(form, ("tracking_time_s",), "Tiempo de seguimiento anti-windup (s)",
                    self._candidate["instrumentation"]["tracking_time_s"])
        note = QLabel("Al desactivar la dinámica, la posición sigue instantáneamente a la consigna. "
                      "Los límites de velocidad son fracciones de carrera por segundo: 0,05 equivale a 5 %/s. "
                      "El seguimiento del PI usa posición real; no garantiza la estabilidad del lazo.")
        note.setWordWrap(True)
        form.addRow(note)
        tabs.addTab(page, "Válvula y control")
        outer.addWidget(tabs, 1)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color:#b42318;")
        outer.addWidget(self.error_label)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Aplicar al caso")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def _field(self, form, path, title, value):
        field = QLineEdit(repr(value))
        field.setAccessibleName(title)
        field.setMinimumWidth(170)
        self.fields[path] = field
        form.addRow(title, field)

    def case_from_form(self):
        from dynamic_tank import validate_case
        candidate = copy.deepcopy(self._candidate)
        for path, field in self.fields.items():
            try:
                value = float(field.text().strip())
            except ValueError as exc:
                raise ValueError(f"{field.accessibleName()}: introduzca un número; use punto decimal.") from exc
            if not math.isfinite(value):
                raise ValueError(f"{field.accessibleName()}: se requiere un número finito.")
            target = candidate["instrumentation"]
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
        candidate["instrumentation"]["valve_actuator"]["enabled"] = self.actuator_enabled.isChecked()
        validate_case(candidate)
        if candidate != self._original:
            note = "Instrumentación declarada en el formulario; sin caracterización experimental automática."
            if note not in candidate["provenance"]["notes"]:
                candidate["provenance"]["notes"] += " | " + note
            if self._original.get("schema_version") == "dynamic-tank/v1":
                candidate["provenance"]["notes"] += " Valores instrumentales iniciales propuestos sintéticos."
                if candidate["provenance"]["data_kind"] == "measured":
                    candidate["provenance"]["data_kind"] = "mixed"
        return candidate

    def accept(self):
        try:
            result = self.case_from_form()
        except (ValueError, TypeError, KeyError) as exc:
            self.error_label.setText(str(exc))
            return
        self.result_case = result
        super().accept()


class _TaskThread(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, config=None, *, result=None, csv_path=None, parent=None):
        super().__init__(parent)
        self.config = copy.deepcopy(config)
        self.result = copy.deepcopy(result)
        self.csv_path = csv_path
        self.cancel_event = threading.Event()

    def run(self):
        try:
            if self.csv_path is not None:
                from dynamic_measurements import compare_measurements
                result = compare_measurements(self.result, self.csv_path)
            else:
                from dynamic_tank import simulate_dynamic_tank
                result = simulate_dynamic_tank(
                    self.config, cancel=self.cancel_event.is_set)
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class DynamicTankDialog(QDialog):
    """Accessible pilot with cancellable simulation and measurement comparison."""

    # (key path, user-facing label, minimum, maximum, decimals, Celsius display)
    _FIELDS = (
        (("tank", "volume_capacity_m3"), "Capacidad del tanque (m³)", .000001, 1e8, 4, False),
        (("tank", "initial_mass_kg"), "Masa inicial (kg)", .000001, 1e12, 3, False),
        (("tank", "initial_temperature_K"), "Temperatura inicial (°C)", -273.14, 5000, 2, True),
        (("simulation", "duration_s"), "Duración (s)", .001, 1e9, 1, False),
        (("inputs", "feed_flow_kg_s"), "Alimentación (kg/s)", 0, 1e8, 4, False),
        (("inputs", "outlet_flow_kg_s"), "Descarga (kg/s)", 0, 1e8, 4, False),
        (("inputs", "feed_temperature_K"), "Temperatura de alimentación (°C)", -273.14, 5000, 2, True),
        (("inputs", "utility_supply_temperature_K"), "Temperatura del servicio (°C)", -273.14, 5000, 2, True),
        (("inputs", "temperature_setpoint_K"), "Consigna de temperatura (°C)", -273.14, 5000, 2, True),
        (("inputs", "valve_opening"), "Apertura manual de válvula (0–1)", 0, 1, 3, False),
    )
    _TABLE_COLUMNS = (
        ("time_s", "Tiempo (s)"),
        ("tank_temperature_K", "Tanque físico (K)"),
        ("jacket_temperature_K", "Camisa física (K)"),
        ("mass_kg", "Masa (kg)"),
        ("volume_m3", "Volumen (m³)"),
        ("valve_opening", "Posición real (0-1)"),
        ("utility_flow_kg_s", "Servicio (kg/s)"),
    )
    _INSTRUMENT_COLUMNS = (
        ("wall_temperature_K", "Pared física (K)"),
        ("tank_indicated_temperature_K", "Tanque indicado (K)"),
        ("wall_indicated_temperature_K", "Pared indicada (K)"),
        ("jacket_indicated_temperature_K", "Camisa indicada (K)"),
        ("valve_command", "Consigna de válvula (0-1)"),
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        from dynamic_tank import default_case
        self._config = default_case()
        self._result = None
        self._comparison = None
        self._run_config = None
        self._worker = None
        self._close_when_finished = False
        self._form_loading = False
        self._plot = None
        self._valve_plot = None
        import pfd_fonts
        pfd_fonts.load_all()
        if pfd_fonts.available():
            self.setFont(QFont(pfd_fonts.SANS, 10))
        self.setWindowTitle("Tanque transitorio — piloto")
        self.resize(1180, 760)
        self.setMinimumSize(840, 560)

        outer = QVBoxLayout(self)
        self.provenance_label = QLabel(
            "Ejemplo sintético; requiere validación con mediciones.")
        self.provenance_label.setWordWrap(True)
        self.provenance_label.setStyleSheet("font-weight:600; padding:6px;")
        outer.addWidget(self.provenance_label)
        hint = QLabel(
            "Tanque bien mezclado con camisa, pared y circuito de servicio. "
            "Líquido monofásico con propiedades constantes. "
            "Este caso se configura de forma independiente del diagrama abierto.")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        splitter = QSplitter(Qt.Horizontal)
        outer.addWidget(splitter, 1)
        settings = QWidget()
        settings_layout = QVBoxLayout(settings)
        form_group = QGroupBox("Condiciones del caso")
        self.form = QFormLayout(form_group)
        self.form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.fields = {}
        for path, label, lower, upper, decimals, _celsius in self._FIELDS:
            field = QDoubleSpinBox()
            field.setRange(lower, upper)
            field.setDecimals(decimals)
            field.setKeyboardTracking(False)
            field.setFixedWidth(145)
            field.setAccessibleName(label)
            field.valueChanged.connect(self._mark_edited)
            self.fields[path] = field
            self.form.addRow(label, field)
        self.controller_enabled = QCheckBox("Control automático de temperatura (PI)")
        self.controller_enabled.toggled.connect(self._mark_edited)
        self.form.addRow(self.controller_enabled)
        self.controller_direction = QComboBox()
        self.controller_direction.addItem("Calentamiento", "heating")
        self.controller_direction.addItem("Enfriamiento", "cooling")
        self.controller_direction.currentIndexChanged.connect(self._mark_edited)
        self.form.addRow("Acción del control", self.controller_direction)
        settings_layout.addWidget(form_group)
        self.case_label = QLabel()
        self.case_label.setWordWrap(True)
        settings_layout.addWidget(self.case_label)
        row = QHBoxLayout()
        self.load_button = QPushButton("Abrir caso…")
        self.save_case_button = QPushButton("Guardar caso…")
        self.load_button.clicked.connect(self._load_case)
        self.save_case_button.clicked.connect(self._save_case)
        row.addWidget(self.load_button)
        row.addWidget(self.save_case_button)
        settings_layout.addLayout(row)
        self.template_button = QPushButton("Plantilla CSV de mediciones…")
        self.template_button.clicked.connect(self._save_measurement_template)
        settings_layout.addWidget(self.template_button)
        self.calibration_button = QPushButton("Calibrar con ensayos…")
        self.calibration_button.clicked.connect(self._open_calibration)
        settings_layout.addWidget(self.calibration_button)
        self.instrumentation_button = QPushButton("Instrumentación…")
        self.instrumentation_button.clicked.connect(self._open_instrumentation)
        settings_layout.addWidget(self.instrumentation_button)
        self.instrumentation_example_button = QPushButton("Ejemplo con instrumentación sintética")
        self.instrumentation_example_button.clicked.connect(self._open_instrumented_example)
        settings_layout.addWidget(self.instrumentation_example_button)
        note = QLabel(
            "El archivo del caso conserva las propiedades, curvas, "
            "parámetros PI y cambios programados. Las temperaturas del "
            "archivo y de la tabla se expresan en K.")
        note.setWordWrap(True)
        settings_layout.addWidget(note)
        settings_layout.addStretch()
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setWidget(settings)
        splitter.addWidget(self.settings_scroll)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self.status_label = QLabel("Listo para simular.")
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        self.table = QTableWidget(0, len(self._TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels([label for _, label in self._TABLE_COLUMNS])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setAccessibleName("Trayectoria de la última simulación")
        try:
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
            from matplotlib.figure import Figure
            self._figure = Figure(figsize=(6, 4), tight_layout=True)
            self._plot = FigureCanvasQTAgg(self._figure)
            self.tabs.addTab(self._plot, "Temperaturas")
            self._valve_figure = Figure(figsize=(6, 4), tight_layout=True)
            self._valve_plot = FigureCanvasQTAgg(self._valve_figure)
            self.tabs.addTab(self._valve_plot, "Válvula")
        except ImportError:
            pass
        self.tabs.addTab(self.table, "Trayectoria")
        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(False)
        self.tabs.addTab(self.details, "Balances y diagnóstico")
        self.comparison_view = QTextBrowser()
        self.tabs.addTab(self.comparison_view, "Mediciones")
        right_layout.addWidget(self.tabs, 1)
        export_row = QHBoxLayout()
        self.compare_button = QPushButton("Comparar CSV medido…")
        self.compare_button.clicked.connect(self._compare_csv)
        self.export_json_button = QPushButton("Resultado JSON…")
        self.export_json_button.clicked.connect(self._export_json)
        self.export_csv_button = QPushButton("Trayectoria CSV…")
        self.export_csv_button.clicked.connect(self._export_csv)
        for button in (self.compare_button, self.export_json_button, self.export_csv_button):
            button.setEnabled(False)
            export_row.addWidget(button)
        right_layout.addLayout(export_row)
        splitter.addWidget(right)
        splitter.setSizes([390, 760])

        footer = QHBoxLayout()
        self.run_button = QPushButton("Simular")
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(self.start_simulation)
        self.cancel_button = QPushButton("Cancelar cálculo")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_simulation)
        self.close_button = QPushButton("Cerrar")
        self.close_button.clicked.connect(self.close)
        footer.addWidget(self.run_button)
        footer.addWidget(self.cancel_button)
        footer.addStretch()
        footer.addWidget(self.close_button)
        outer.addLayout(footer)
        self.set_case(self._config)

    def set_case(self, config):
        """Load fields atomically; never silently clamp imported values."""
        if config.get("schema_version") == "dynamic-tank/v2":
            from dynamic_tank import validate_case
            validate_case(config)
        values = []
        for path, _label, lower, upper, _decimals, celsius in self._FIELDS:
            value = config[path[0]][path[1]]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"El campo {'.'.join(path)} debe ser numérico.")
            display_value = value - 273.15 if celsius else value
            if not math.isfinite(value) or not lower <= display_value <= upper:
                raise ValueError(f"El campo {'.'.join(path)} está fuera del rango del formulario.")
            values.append((path, display_value))
        enabled = config["controller"]["enabled"]
        direction = config["controller"]["direction"]
        if not isinstance(enabled, bool) or direction not in ("heating", "cooling"):
            raise ValueError("Configuración de control inválida.")
        if not isinstance(config.get("events", []), list):
            raise ValueError("Los cambios programados deben ser una lista.")
        if not isinstance(config.get("provenance", {}), dict):
            raise ValueError("La procedencia del caso debe ser un objeto.")
        self._form_loading = True
        try:
            self._config = copy.deepcopy(config)
            for path, value in values:
                self.fields[path].setValue(value)
            self._loaded_display_values = {
                path: field.value() for path, field in self.fields.items()}
            self.controller_enabled.setChecked(enabled)
            self.controller_direction.setCurrentIndex(
                self.controller_direction.findData(direction))
            self._update_case_label()
        finally:
            self._form_loading = False
        self._mark_edited()

    def case_from_form(self):
        config = copy.deepcopy(self._config)
        for path, _label, _lower, _upper, _decimals, celsius in self._FIELDS:
            value = self.fields[path].value()
            # Keep imported full precision unless the user changed the field.
            if value != self._loaded_display_values[path]:
                config[path[0]][path[1]] = value + 273.15 if celsius else value
        config["controller"]["enabled"] = self.controller_enabled.isChecked()
        config["controller"]["direction"] = self.controller_direction.currentData()
        return config

    def _update_case_label(self):
        title = self._config.get("title", self._config.get("case_id", "Caso"))
        count = len(self._config.get("events", []))
        instrumented = self._config.get("schema_version") == "dynamic-tank/v2"
        instrumentation = ("Instrumentación explícita: el PI usa la temperatura indicada."
                           if instrumented else "Sensores y accionamiento ideales (caso v1).")
        self.case_label.setText(f"{title}\nCambios programados en el caso: {count}.\n{instrumentation}")
        kind = self._config.get("provenance", {}).get("data_kind", "sin declarar")
        self.provenance_label.setText(
            "Ejemplo sintético; requiere validación con mediciones."
            if kind == "synthetic" else
            f"Procedencia declarada: {kind}. La carga de un caso no demuestra validación física.")

    def _mark_edited(self, *_args):
        if self._form_loading:
            return
        self.fields[("inputs", "valve_opening")].setEnabled(
            not self.controller_enabled.isChecked())
        if self._result is not None:
            self.status_label.setText(
                "Parámetros modificados. Las curvas y exportaciones corresponden a la última corrida; vuelva a simular.")

    def _set_busy(self, busy, *, comparison=False):
        self.settings_scroll.setEnabled(not busy)
        self.run_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy and not comparison)
        for button in (self.compare_button, self.export_json_button, self.export_csv_button):
            button.setEnabled(not busy and self._result is not None)

    @Slot()
    def start_simulation(self):
        if self._worker is not None:
            return
        self._run_config = self.case_from_form()
        worker = _TaskThread(self._run_config, parent=self)
        worker.completed.connect(self._simulation_finished)
        self._launch_worker(worker)
        self.status_label.setText("Calculando la trayectoria… Puede cancelar el cálculo.")

    def _launch_worker(self, worker, *, comparison=False):
        self._worker = worker
        worker.failed.connect(self._task_failed)
        worker.finished.connect(self._worker_finished)
        self._set_busy(True, comparison=comparison)
        worker.start()

    @Slot()
    def cancel_simulation(self):
        if self._worker is not None:
            self._worker.cancel_event.set()
            self.cancel_button.setEnabled(False)
            self.status_label.setText(
                "Terminando la lectura de mediciones antes de cerrar…"
                if self._worker.csv_path is not None else
                "Cancelación solicitada; cerrando el cálculo en curso…")

    @Slot(object)
    def _simulation_finished(self, result):
        self._result = result
        self._comparison = None
        self.comparison_view.clear()
        summary = result.get("summary", {})
        final_time = summary.get("final_time_s", 0)
        status = {"ok": "Completado", "limit": "Límite alcanzado",
                  "cancelled": "Cancelado", "error": "Error"}.get(
                      summary.get("status"), "Estado desconocido")
        reason = self._reason_label(summary.get("stop_reason", ""))
        self.status_label.setText(f"Estado: {status} · t = {final_time:g} s\n{reason}")
        self._render_diagnostics(result)
        self._render_series(result.get("series", []))

    @staticmethod
    def _reason_label(reason):
        labels = {
            "duration_reached": "Se completó el tiempo solicitado.",
            "minimum_inventory": "Se alcanzó la cantidad mínima de líquido del modelo.",
            "tank_capacity": "Se alcanzó la capacidad del tanque.",
            "pump_curve_domain": "El punto de operación salió del dominio declarado de la bomba.",
            "user_cancelled": "El usuario canceló el cálculo.",
            "evaluation_budget_exceeded": "Se alcanzó el límite de trabajo del integrador.",
            "integration_failed": "El integrador no pudo completar el cálculo.",
            "nonfinite_state": "Se detectó un estado numérico inválido.",
            "balance_audit_failed": "El cierre numérico de balances superó la tolerancia.",
        }
        if reason in labels:
            return labels[reason]
        for name, label in (("tank", "tanque"), ("wall", "pared"), ("jacket", "camisa")):
            if reason == name + "_temperature_low":
                return f"La temperatura de {label} alcanzó el límite inferior del modelo."
            if reason == name + "_temperature_high":
                return f"La temperatura de {label} alcanzó el límite superior del modelo."
        return "Consulte los diagnósticos de la corrida." if reason else ""

    def _render_diagnostics(self, result):
        esc = lambda value: html.escape(str(value))
        audit = result.get("audit", {})
        rows = []
        for key, label, unit in (("mass", "Masa total", "kg"),
                                 ("tracer", "Trazador", "kg"),
                                 ("energy", "Energía", "J")):
            value = audit.get(f"max_{key}_residual_{unit}")
            relative = audit.get(f"max_{key}_residual_relative")
            absolute_text = "—" if value is None else f"{value:.6g} {unit}"
            relative_text = "—" if relative is None else f"{relative:.6g}"
            rows.append(f"<tr><td>{label}</td><td>{absolute_text}</td><td>{relative_text}</td></tr>")
        metadata = result.get("metadata", {})
        provenance = metadata.get("provenance", {})
        counts = Counter(event.get("kind", "otro") for event in result.get("events", []))
        event_labels = {"controller_sample": "Muestras del control PI",
                        "input_change": "Cambios programados", "input_event": "Cambios programados",
                        "terminal_limit": "Límites alcanzados"}
        events_text = ", ".join(f"{esc(event_labels.get(key, 'Otros'))}: {count}"
                                for key, count in counts.items()) or "Sin eventos."
        diagnostics = []
        for diagnostic in result.get("diagnostics", []):
            if isinstance(diagnostic, dict):
                diagnostic = diagnostic.get("message", str(diagnostic))
            diagnostics.append(f"<li>{esc(diagnostic)}</li>")
        self.details.setHtml(
            "<h3>Conservación numérica</h3>"
            "<p>Frontera: tanque, pared y camisa. Se comparan los cambios de inventario "
            "con los flujos externos integrados en el tiempo.</p>"
            "<table cellpadding='6' border='1'><tr><th>Balance</th><th>Residuo máximo</th>"
            "<th>Residuo relativo</th></tr>" + "".join(rows) + "</table>"
            "<p>Un residuo pequeño verifica conservación numérica; no mide el error frente a una planta.</p>"
            "<h3>Diagnósticos</h3><ul>" + ("".join(diagnostics) or "<li>Sin incidencias adicionales.</li>")
            + "</ul><h3>Supuestos y límites</h3><ul>"
            + "".join(f"<li>{esc(item)}</li>" for item in result.get("assumptions", []))
            + "</ul><h3>Procedencia de la corrida</h3>"
            + f"<p>Modelo: {esc(metadata.get('model_version', ''))}. "
            + "Trayectoria calculada; sin validación experimental automática.</p>"
            + f"<p>{esc(provenance.get('source', ''))}</p>"
            + f"<p>Huella del caso: {esc(metadata.get('config_sha256', ''))}</p>"
            + f"<p>Eventos registrados: {events_text}. El JSON conserva los detalles completos.</p>")

    def _render_series(self, series):
        # The result retains every sample. The table is a bounded preview to
        # avoid allocating hundreds of thousands of Qt item objects.
        stride = max(1, math.ceil(len(series) / 2000))
        preview = series[::stride]
        if series and preview[-1] is not series[-1]:
            preview = preview + [series[-1]]
        instrumented = any("valve_command" in sample for sample in series)
        columns = self._TABLE_COLUMNS + (self._INSTRUMENT_COLUMNS if instrumented else ())
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels([label for _, label in columns])
        self.table.setRowCount(len(preview))
        for row, sample in enumerate(preview):
            for col, (key, _label) in enumerate(columns):
                value = sample.get(key)
                item = QTableWidgetItem("" if value is None else f"{value:.7g}")
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        self.table.setToolTip(
            f"Vista de {len(preview)} de {len(series)} muestras. La exportación conserva todas.")
        if self._plot is not None:
            self._figure.clear()
            ax = self._figure.add_subplot(111)
            for section, label, color in (("tank", "Tanque", "tab:blue"),
                                          ("jacket", "Camisa", "tab:orange"),
                                          ("wall", "Pared", "tab:green")):
                key = section + "_temperature_K"
                samples = [s for s in preview if key in s]
                ax.plot([s["time_s"] for s in samples],
                        [s[key] - 273.15 for s in samples], color=color, label=label + " físico")
                indicated = section + "_indicated_temperature_K"
                samples = [s for s in preview if indicated in s]
                if samples:
                    ax.plot([s["time_s"] for s in samples],
                            [s[indicated] - 273.15 for s in samples],
                            linestyle="--", color=color, label=label + " indicado")
            if series and self._run_config is not None:
                initial = self._run_config["inputs"]["temperature_setpoint_K"]
                setpoints = [sample.get("temperature_setpoint_K", initial) - 273.15
                             for sample in preview]
                ax.step([s["time_s"] for s in preview], setpoints,
                        where="post", linestyle="--", color="0.4", label="Consigna")
            ax.set_xlabel("Tiempo (s)")
            ax.set_ylabel("Temperatura (°C)")
            ax.grid(True, alpha=.25)
            ax.legend(loc="best", fontsize=8, ncols=2 if instrumented else 1)
            self._plot.draw_idle()
        if self._valve_plot is not None:
            self._valve_figure.clear()
            ax = self._valve_figure.add_subplot(111)
            values = [sample for sample in preview if "valve_opening" in sample]
            if values:
                draw = ax.plot if instrumented else ax.step
                options = {} if instrumented else {"where": "post"}
                draw([s["time_s"] for s in values], [s["valve_opening"] for s in values],
                     label="Posición real", color="tab:blue", **options)
            values = [sample for sample in preview if "valve_command" in sample]
            if values:
                ax.step([s["time_s"] for s in values], [s["valve_command"] for s in values],
                        where="post", linestyle="--", label="Consigna de válvula", color="tab:orange")
            ax.set_xlabel("Tiempo (s)")
            ax.set_ylabel("Fracción de carrera (0–1)")
            ax.set_ylim(-.05, 1.05)
            ax.grid(True, alpha=.25)
            if preview:
                ax.legend(loc="best")
            self._valve_plot.draw_idle()

    @Slot(str)
    def _task_failed(self, message):
        self.status_label.setText(f"No se completó la tarea: {message}")
        self.details.setPlainText(message)
        self.tabs.setCurrentWidget(self.details)

    @Slot()
    def _worker_finished(self):
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self._set_busy(False)
        if self._close_when_finished:
            QTimer.singleShot(0, self.close)

    def _load_case(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir caso transitorio", "", "Caso JSON (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as stream:
                self.set_case(json.load(stream))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            QMessageBox.warning(self, "No se pudo abrir el caso", str(exc))

    def _write_json(self, path, value):
        Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                        allow_nan=False) + "\n", encoding="utf-8")

    def _save_case(self):
        path, _ = QFileDialog.getSaveFileName(self, "Guardar caso transitorio", "tanque_transitorio.json", "JSON (*.json)")
        if path:
            try:
                self._write_json(path, self.case_from_form())
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "No se pudo guardar", str(exc))

    def _save_measurement_template(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Crear plantilla de mediciones", "mediciones_tanque.csv", "CSV (*.csv)")
        if path:
            try:
                from dynamic_measurements import write_measurement_template
                write_measurement_template(
                    path, instrumented=self._config.get("schema_version") == "dynamic-tank/v2")
                self.status_label.setText(
                    "Plantilla creada con encabezados SI. Añada mediciones reales; "
                    "time_s se cuenta desde el mismo inicio que la simulación.")
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "No se pudo guardar la plantilla", str(exc))

    def _open_calibration(self):
        """Open the study workbench without changing this pilot's parameters."""
        if self._worker is not None:
            return
        try:
            from dynamic_calibration_dialog import DynamicCalibrationDialog
            DynamicCalibrationDialog(self).exec()
        except Exception as exc:
            QMessageBox.warning(self, "No se pudo abrir la calibración", str(exc))

    def _open_instrumentation(self):
        if self._worker is not None:
            return
        editor = None
        try:
            editor = InstrumentationDialog(self.case_from_form(), self)
            if editor.exec() == QDialog.Accepted:
                self.set_case(editor.result_case)
                if self._result is None:
                    self.status_label.setText("Instrumentación aplicada al caso. Listo para simular.")
        except (ValueError, TypeError, KeyError) as exc:
            QMessageBox.warning(self, "No se pudo configurar la instrumentación", str(exc))
        finally:
            if editor is not None:
                editor.deleteLater()

    def _open_instrumented_example(self):
        if self._worker is not None:
            return
        try:
            path = (Path(__file__).resolve().parent / "data" / "instrumentation_examples"
                    / "instrumented_heating.json")
            self.set_case(json.loads(path.read_text(encoding="utf-8")))
            if self._result is None:
                self.status_label.setText("Ejemplo con instrumentación sintética cargado. Listo para simular.")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            QMessageBox.warning(self, "No se pudo abrir el ejemplo", str(exc))

    def _export_json(self):
        if self._result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar última corrida", "resultado_transitorio.json", "JSON (*.json)")
        if path:
            try:
                export = copy.deepcopy(self._result)
                if self._comparison is not None:
                    export["measurement_comparison"] = copy.deepcopy(self._comparison)
                self._write_json(path, export)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "No se pudo exportar", str(exc))

    def _export_csv(self):
        if self._result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Exportar trayectoria calculada", "trayectoria_simulada.csv", "CSV (*.csv)")
        if path:
            try:
                series = self._result.get("series", [])
                columns = list(dict.fromkeys(key for sample in series for key in sample))
                with open(path, "w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=columns)
                    writer.writeheader()
                    writer.writerows(series)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "No se pudo exportar", str(exc))

    def _compare_csv(self):
        if self._result is None or self._worker is not None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Comparar mediciones con la última corrida", "", "CSV (*.csv)")
        if not path:
            return
        worker = _TaskThread(result=self._result, csv_path=path, parent=self)
        worker.completed.connect(self._comparison_finished)
        self._launch_worker(worker, comparison=True)
        self.status_label.setText("Comparando el CSV con la última trayectoria…")

    @Slot(object)
    def _comparison_finished(self, comparison):
        self._comparison = comparison
        esc = lambda value: html.escape(str(value))
        summary = comparison.get("summary", {})
        rows = []
        labels = dict(self._TABLE_COLUMNS + self._INSTRUMENT_COLUMNS)
        for variable, metrics in comparison.get("metrics", {}).items():
            cells = [esc(labels.get(variable, variable)), esc(metrics.get("unit", "")),
                     esc(metrics.get("n", 0))]
            for key in ("rmse", "mae", "bias", "max_abs_error"):
                value = metrics.get(key)
                cells.append("—" if value is None else f"{value:.6g}")
            rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
        self.comparison_view.setHtml(
            "<p><b>Comparación descriptiva; no demuestra por sí sola validación de planta.</b></p>"
            f"<p>Filas dentro del intervalo: {esc(summary.get('rows_in_range', 0))}; "
            f"fuera del intervalo: {esc(summary.get('rows_out_of_range', 0))}.</p>"
            "<table cellpadding='6' border='1'><tr><th>Variable</th><th>Unidad</th>"
            "<th>N</th><th>RMSE</th><th>Error medio absoluto</th><th>Sesgo</th>"
            "<th>Error máximo</th></tr>" + "".join(rows) + "</table>"
            "<p>RMSE: raíz del error cuadrático medio. Sesgo: simulación menos medición.</p>"
            f"<p>{esc(comparison.get('conclusion', ''))}</p>"
            + "".join(f"<p>{esc(warning)}</p>" for warning in comparison.get("warnings", []))
            + f"<p>Huella del archivo: {esc(comparison.get('provenance', {}).get('sha256', ''))}</p>")
        self.tabs.setCurrentWidget(self.comparison_view)
        self.status_label.setText("Comparación terminada. Revise cobertura, errores y procedencia de las mediciones.")

    def reject(self):
        if self._worker is not None:
            self._close_when_finished = True
            self.cancel_simulation()
            return
        super().reject()

    def closeEvent(self, event):
        if self._worker is not None:
            self._close_when_finished = True
            self.cancel_simulation()
            event.ignore()
        else:
            super().closeEvent(event)


def main():
    """Optional standalone entry point, also available from the editor menu."""
    import sys
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    dialog = DynamicTankDialog()
    dialog.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
