"""Qt workbench for explicit calibration and held-out experiment assessment.

Only the worker runs the numerical fit. Results are exported deliberately, never
applied to the open pilot. A converged fit and met thresholds are not evidence
that a synthetic dataset, an instrument or a plant model is experimentally valid.
"""
from __future__ import annotations

import html
import hashlib
import json
import math
import os
from pathlib import Path
import threading

from PySide6.QtCore import QThread, QTimer, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
    QProgressBar, QPushButton, QTabWidget, QTableWidget, QTableWidgetItem,
    QTextBrowser, QVBoxLayout,
)


_PARAMETER_LABELS = {
    "wall.ua_tank_W_K": "UA tanque–pared",
    "wall.ua_jacket_W_K": "UA camisa–pared",
    "wall.ua_ambient_W_K": "UA pared–ambiente",
    "wall.heat_capacity_J_K": "Capacidad térmica de pared",
}
_VARIABLE_LABELS = {
    "tank_temperature_K": "Temperatura física del tanque",
    "jacket_temperature_K": "Temperatura física de camisa",
    "wall_temperature_K": "Temperatura física de pared",
    "tank_indicated_temperature_K": "Temperatura indicada del tanque",
    "wall_indicated_temperature_K": "Temperatura indicada de pared",
    "jacket_indicated_temperature_K": "Temperatura indicada de camisa",
}
_ROLE_LABELS = {"calibration": "Ajuste", "validation": "Validación reservada"}


def _number_text(value):
    if value is None or isinstance(value, bool):
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return "—"
    return f"{number:.6g}" if math.isfinite(number) else "—"


class _CalibrationThread(QThread):
    completed = Signal(object)
    failed = Signal(str)
    progressed = Signal(object)

    def __init__(self, study_path, parent=None):
        super().__init__(parent)
        self.study_path = str(study_path)
        self.cancel_event = threading.Event()

    def run(self):
        try:
            from dynamic_calibration import calibrate_study
            result = calibrate_study(
                self.study_path,
                cancel=self.cancel_event.is_set,
                progress=self.progressed.emit,
            )
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class _StudyThread(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, study_path, parent=None):
        super().__init__(parent)
        self.study_path = Path(study_path).resolve()
        self.cancel_event = threading.Event()

    def run(self):
        try:
            from dynamic_study import load_study
            study = load_study(self.study_path)
            self.completed.emit(None if self.cancel_event.is_set() else
                                {"path": self.study_path, "study": study})
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class DynamicCalibrationDialog(QDialog):
    """Load a study, fit in a worker, inspect and explicitly export its result."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._study_path = None
        self._study = None
        self._result = None
        self._worker = None
        self._close_when_finished = False
        self._protected_inputs = set()
        self._export_cases = []

        import pfd_fonts
        pfd_fonts.load_all()
        if pfd_fonts.available():
            self.setFont(QFont(pfd_fonts.SANS, 10))
        self.setWindowTitle("Calibración del tanque con ensayos")
        self.resize(1200, 780)
        self.setMinimumSize(900, 580)

        layout = QVBoxLayout(self)
        self.provenance_label = QLabel(
            "Cargue un estudio. Ajustar parámetros no demuestra validez de planta.")
        self.provenance_label.setWordWrap(True)
        self.provenance_label.setStyleSheet("font-weight:600; padding:6px;")
        layout.addWidget(self.provenance_label)
        hint = QLabel(
            "Se ajustan parámetros térmicos con los ensayos de ajuste y se evalúan "
            "con ensayos reservados. Cada ensayo contiene sus condiciones y "
            "perturbaciones prescritas. Los CSV usan segundos y kelvin.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        open_row = QHBoxLayout()
        self.open_button = QPushButton("Abrir estudio JSON…")
        self.open_button.clicked.connect(self._open_study)
        self.example_button = QPushButton("Abrir demostración sintética")
        self.example_button.clicked.connect(self._open_example)
        open_row.addWidget(self.open_button)
        open_row.addWidget(self.example_button)
        open_row.addStretch()
        layout.addLayout(open_row)
        self.path_label = QLabel("Sin estudio cargado.")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        self.status_label = QLabel("Listo para cargar un estudio.")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Sin cálculo")
        self.progress_bar.setAccessibleName("Evaluaciones del objetivo utilizadas")
        layout.addWidget(self.progress_bar)

        self.tabs = QTabWidget()
        self.study_view = QTextBrowser()
        self.study_view.setOpenExternalLinks(False)
        self.tabs.addTab(self.study_view, "Estudio y procedencia")
        self.parameter_table = self._table(
            ["Parámetro", "Unidad", "Inicial", "Estimado", "Mínimo", "Máximo", "En límite"],
            "Parámetros iniciales y estimados",
        )
        self.tabs.addTab(self.parameter_table, "Parámetros")
        self.metrics_table = self._table(
            ["Ensayo", "Uso", "Variable", "N", "RMSE inicial (K)", "RMSE ajustado (K)",
             "MAE ajustado (K)", "Sesgo ajustado (K)", "Máximo absoluto (K)"],
            "Errores por ensayo de ajuste y validación reservada",
        )
        self.tabs.addTab(self.metrics_table, "Errores por ensayo")
        self.diagnostics_view = QTextBrowser()
        self.diagnostics_view.setOpenExternalLinks(False)
        self.tabs.addTab(self.diagnostics_view, "Diagnóstico")
        layout.addWidget(self.tabs, 1)

        export_row = QHBoxLayout()
        self.export_report_button = QPushButton("Guardar informe JSON…")
        self.export_report_button.clicked.connect(self._export_report)
        self.case_combo = QComboBox()
        self.case_combo.setAccessibleName("Ensayo cuyo caso ajustado se exportará")
        self.export_case_button = QPushButton("Guardar caso ajustado…")
        self.export_case_button.clicked.connect(self._export_case)
        self.export_case_button.setToolTip(
            "Requiere un ajuste convergido. Los candidatos con identificación débil "
            "conservan sus advertencias. Exportar no certifica precisión de planta.")
        export_row.addWidget(self.export_report_button)
        export_row.addStretch()
        export_row.addWidget(QLabel("Caso del ensayo:"))
        export_row.addWidget(self.case_combo, 1)
        export_row.addWidget(self.export_case_button)
        layout.addLayout(export_row)
        export_note = QLabel(
            "Las exportaciones no modifican los archivos de entrada ni el tanque abierto. "
            "Revise los diagnósticos antes de utilizar un caso ajustado.")
        export_note.setWordWrap(True)
        layout.addWidget(export_note)

        footer = QHBoxLayout()
        self.run_button = QPushButton("Calibrar")
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(self.start_calibration)
        self.cancel_button = QPushButton("Cancelar cálculo")
        self.cancel_button.clicked.connect(self.cancel_calibration)
        self.close_button = QPushButton("Cerrar")
        self.close_button.clicked.connect(self.close)
        footer.addWidget(self.run_button)
        footer.addWidget(self.cancel_button)
        footer.addStretch()
        footer.addWidget(self.close_button)
        layout.addLayout(footer)
        self._set_busy(False)

    @staticmethod
    def _table(headers, accessible_name):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setAccessibleName(accessible_name)
        return table

    @staticmethod
    def _input_paths(study_path, study):
        paths = {Path(study_path).resolve()}
        base = Path(study_path).resolve().parent
        for experiment in study["experiments"]:
            for key in ("case_file", "measurements_file"):
                paths.add((base / experiment[key]).resolve())
        return paths

    def set_study(self, path):
        """Validate before replacing the visible study or discarding results."""
        if self._worker is not None:
            raise RuntimeError("Espere a que termine el cálculo antes de cambiar de estudio.")
        from dynamic_study import load_study
        resolved = Path(path).resolve()
        study = load_study(resolved)
        self._apply_study(resolved, study)

    def _apply_study(self, resolved, study):
        protected = self._input_paths(resolved, study)
        self._study_path = resolved
        self._study = study
        self._protected_inputs = protected
        self.path_label.setText(str(resolved))
        self._clear_result()
        self._render_study()
        self.status_label.setText("Estudio cargado. Revise parámetros, ensayos y criterios.")
        self.tabs.setCurrentWidget(self.study_view)
        self._set_busy(False)

    @Slot(object)
    def _study_loaded(self, payload):
        if payload is None or (self._worker is not None and self._worker.cancel_event.is_set()):
            self.status_label.setText("Lectura del estudio cancelada.")
            return
        self._apply_study(payload["path"], payload["study"])
        self._set_busy(self._worker is not None)

    def _clear_result(self):
        self._result = None
        self._export_cases = []
        self.case_combo.clear()
        self.parameter_table.setRowCount(0)
        self.metrics_table.setRowCount(0)
        self.diagnostics_view.clear()
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Sin cálculo")

    def _render_study(self):
        from dynamic_study import PARAMETER_UNITS
        esc = lambda value: html.escape(str(value))
        study = self._study
        experiments = study["experiments"]
        synthetic = all(item["data_kind"] == "synthetic" for item in experiments)
        self.provenance_label.setText(
            "Demostración con datos sintéticos: no valida un equipo real."
            if synthetic else
            "Procedencia declarada por el usuario, sin verificación de autenticidad. "
            "El ajuste no certifica precisión de planta.")
        rows = []
        for item in experiments:
            kind = "Sintético" if item["data_kind"] == "synthetic" else "Aportado por usuario"
            cells = [item["experiment_id"], _ROLE_LABELS[item["role"]], kind, item["source"],
                     item["case_file"], item["measurements_file"]]
            rows.append("<tr>" + "".join(f"<td>{esc(cell)}</td>" for cell in cells) + "</tr>")
        criteria = []
        for variable, values in study["observables"].items():
            criteria.append(
                f"<li>{esc(_VARIABLE_LABELS.get(variable, variable))}: "
                f"escala declarada {_number_text(values['scale_K'])} K; "
                f"RMSE reservado ≤ {_number_text(values['max_validation_rmse_K'])} K; "
                f"error absoluto máximo ≤ {_number_text(values['max_validation_abs_error_K'])} K.</li>")
        params = []
        for item in study["parameters"]:
            unit = PARAMETER_UNITS[item["path"]]
            params.append(
                f"<li>{esc(_PARAMETER_LABELS.get(item['path'], item['path']))}: "
                f"inicial {_number_text(item['initial'])} {esc(unit)}; "
                f"límites {_number_text(item['lower'])}–{_number_text(item['upper'])} {esc(unit)}.</li>")
        self.study_view.setHtml(
            f"<h3>{esc(study['study_id'])}</h3><p>Equipo declarado: {esc(study['equipment_id'])}</p>"
            "<p>Los ensayos reservados no participan en el ajuste. Su independencia "
            "experimental y las condiciones de los instrumentos deben comprobarse aparte.</p>"
            "<table cellpadding='5' border='1'><tr><th>Ensayo</th><th>Uso</th><th>Origen</th>"
            "<th>Fuente</th><th>Caso</th><th>Observaciones</th></tr>" + "".join(rows) + "</table>"
            "<h3>Parámetros y límites</h3><ul>" + "".join(params) + "</ul>"
            "<h3>Pesos y criterios declarados</h3><ul>" + "".join(criteria) + "</ul>"
            "<p>Si una observación incluye incertidumbre estándar positiva, se usa para "
            "normalizar su residuo; en caso contrario se usa la escala declarada. "
            "Estos valores y criterios deben justificarse para el uso previsto.</p>"
            f"<p>Presupuesto de evaluaciones del objetivo: {esc(study['options']['max_evaluations'])}.</p>"
            f"<p>Huella del estudio: {esc(study['provenance'].get('study_sha256', ''))}</p>")

    def _set_busy(self, busy):
        self.open_button.setEnabled(not busy)
        self.example_button.setEnabled(not busy)
        self.run_button.setEnabled(not busy and self._study_path is not None)
        self.cancel_button.setEnabled(busy)
        self.export_report_button.setEnabled(not busy and self._result is not None)
        exportable = self._can_export_case()
        self.case_combo.setEnabled(not busy and exportable)
        self.export_case_button.setEnabled(not busy and exportable)

    def _can_export_case(self):
        summary = self._result.get("summary", {}) if self._result else {}
        return bool(summary.get("optimization_converged") is True
                    and summary.get("status") in ("ok", "warning") and self._export_cases)

    @Slot()
    def start_calibration(self):
        if self._worker is not None or self._study_path is None:
            return
        try:
            # CSV/case validation runs on the numerical worker. The small
            # manifest must still match the choices shown in the preview.
            with self._study_path.open("rb") as handle:
                raw = handle.read(2 * 1024 * 1024 + 1)
            if (len(raw) > 2 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() !=
                    self._study["provenance"]["study_sha256"]):
                raise ValueError("El manifiesto cambió. Vuelva a abrirlo para revisar sus cambios.")
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.status_label.setText(f"No se pudo iniciar: {exc}")
            return
        self._clear_result()
        self._close_when_finished = False
        worker = _CalibrationThread(self._study_path, parent=self)
        self._worker = worker
        worker.completed.connect(self._calibration_finished)
        worker.failed.connect(self._task_failed)
        worker.progressed.connect(self._progress_changed)
        worker.finished.connect(self._worker_finished)
        self.progress_bar.setRange(0, self._study["options"]["max_evaluations"])
        self.progress_bar.setFormat("Evaluaciones del objetivo: %v / %m")
        self._set_busy(True)
        self.status_label.setText("Calculando el ajuste. Puede cancelar el cálculo.")
        worker.start()

    @Slot(object)
    def _progress_changed(self, payload):
        phases = {"baseline": "Calculando referencia inicial", "calibration": "Ajustando",
                  "jacobian": "Evaluando sensibilidad local", "validation": "Evaluando ensayos reservados",
                  "fitted_report": "Preparando resultados ajustados", "completed": "Cálculo terminado"}
        maximum = payload.get("max_evaluations", self.progress_bar.maximum())
        current = payload.get("evaluations", self.progress_bar.value())
        if isinstance(maximum, int) and maximum > 0:
            self.progress_bar.setMaximum(maximum)
        if isinstance(current, int) and current >= 0:
            self.progress_bar.setValue(min(current, self.progress_bar.maximum()))
        if self._worker is not None and self._worker.cancel_event.is_set():
            return
        phase = phases.get(payload.get("phase"), "Evaluando modelo")
        self.status_label.setText(
            f"{phase}. Evaluaciones del objetivo: {current}/{maximum}; "
            f"simulaciones: {payload.get('simulations_count', '—')}. "
            f"Ensayo: {payload.get('experiment_id', '—')}.")

    @Slot()
    def cancel_calibration(self):
        if self._worker is not None:
            self._worker.cancel_event.set()
            self.cancel_button.setEnabled(False)
            self.status_label.setText(
                "Cancelación solicitada; terminando la lectura de archivos."
                if isinstance(self._worker, _StudyThread) else
                "Cancelación solicitada; cerrando el cálculo en curso.")

    @Slot(object)
    def _calibration_finished(self, result):
        try:
            self._assert_report_matches_study(result)
        except ValueError as exc:
            self._clear_result()
            self._task_failed(str(exc))
            return
        self._result = result
        summary = result.get("summary", {})
        state = {"ok": "Ajuste completado", "warning": "Ajuste con advertencias",
                 "failed": "Ajuste no completado", "cancelled": "Ajuste cancelado"}.get(
                     summary.get("status"), "Revise el estado del ajuste")
        validation = {"criteria_met": "Se cumplen los criterios reservados declarados.",
                      "criteria_exceeded": "Se exceden los criterios reservados declarados.",
                      "not_assessed": "Los criterios reservados no se han podido evaluar."}.get(
                          summary.get("validation_status"), "Sin evaluación reservada disponible.")
        caution = (" Estimación sin respaldo de todos los diagnósticos o criterios: "
                   "el caso exportado es un candidato con advertencias."
                   if summary.get("optimization_converged") and
                   not summary.get("usable_parameter_estimate") else "")
        self.status_label.setText(f"{state}. {validation}{caution} Esto no certifica validez de planta.")
        self._render_parameters(result.get("parameters", []))
        self._render_metrics(result.get("experiments", []))
        self._render_diagnostics(result)
        self._export_cases = [item for item in result.get("experiments", [])
                              if isinstance(item.get("fitted_case"), dict)]
        self.case_combo.clear()
        for item in self._export_cases:
            self.case_combo.addItem(
                f"{item['experiment_id']} · {_ROLE_LABELS.get(item.get('role'), item.get('role', ''))}",
                item["experiment_id"],
            )
        self.tabs.setCurrentWidget(self.metrics_table if self._export_cases else self.diagnostics_view)

    def _render_parameters(self, parameters):
        from dynamic_study import PARAMETER_UNITS
        self.parameter_table.setRowCount(len(parameters))
        for row, item in enumerate(parameters):
            path = item.get("path", "")
            cells = [_PARAMETER_LABELS.get(path, path), PARAMETER_UNITS.get(path, ""),
                     *[_number_text(item.get(key)) for key in ("initial", "value", "lower", "upper")],
                     "Sí" if item.get("at_bound") else "No"]
            self._fill_row(self.parameter_table, row, cells)
        self.parameter_table.resizeColumnsToContents()

    def _render_metrics(self, experiments):
        rows = []
        for item in experiments:
            before = item.get("baseline_metrics") or {}
            after = item.get("fitted_metrics") or {}
            for variable in dict.fromkeys([*before, *after]):
                initial, fitted = before.get(variable, {}), after.get(variable, {})
                rows.append([item.get("experiment_id", ""), _ROLE_LABELS.get(item.get("role"), ""),
                             _VARIABLE_LABELS.get(variable, variable), str(fitted.get("n", initial.get("n", 0))),
                             _number_text(initial.get("rmse")),
                             *[_number_text(fitted.get(key)) for key in
                               ("rmse", "mae", "bias", "max_abs_error")]])
        self.metrics_table.setRowCount(len(rows))
        for row, cells in enumerate(rows):
            self._fill_row(self.metrics_table, row, cells)
        self.metrics_table.resizeColumnsToContents()

    @staticmethod
    def _fill_row(table, row, cells):
        for column, cell in enumerate(cells):
            table.setItem(row, column, QTableWidgetItem(str(cell)))

    def _render_diagnostics(self, result):
        esc = lambda value: html.escape(str(value))
        summary, diag = result.get("summary", {}), result.get("diagnostics", {})
        warnings = result.get("warnings", [])
        condition = _number_text(diag.get("scaled_jacobian_condition"))
        failure = result.get("failure")
        failure_html = ("<h3>Motivo de la interrupción</h3><pre>"
                        + esc(json.dumps(failure, ensure_ascii=False, indent=2)) + "</pre>"
                        if failure else "")
        self.diagnostics_view.setHtml(
            "<h3>Interpretación del ajuste</h3>"
            "<p>La convergencia indica terminación numérica del optimizador. Los criterios "
            "reservados comparan errores con umbrales declarados; no verifican por sí solos "
            "la autenticidad de datos ni la validez de una instalación.</p>"
            f"<p>Optimizador convergido: {'Sí' if summary.get('optimization_converged') else 'No'}. "
            f"Estimación utilizable según diagnósticos y criterios: "
            f"{'Sí' if summary.get('usable_parameter_estimate') else 'No'}.</p>"
            f"<p>Objetivo normalizado inicial: {_number_text(summary.get('objective_before'))}; "
            f"final: {_number_text(summary.get('objective_after'))}. "
            f"Evaluaciones: {esc(summary.get('evaluations', '-'))}; "
            f"simulaciones: {esc(summary.get('simulations_count', '-'))}.</p>"
            "<h3>Sensibilidad local</h3>"
            f"<p>Rango: {esc(diag.get('rank', '—'))}/{esc(diag.get('n_parameters', '—'))}. "
            f"Número de condición del jacobiano escalado: {condition}.</p>"
            "<p>Un rango deficiente o un condicionamiento elevado indica dificultad para "
            "distinguir parámetros con estos ensayos. Este diagnóstico local no demuestra "
            "identificabilidad estructural ni proporciona un intervalo de confianza.</p>"
            "<h3>Advertencias</h3><ul>"
            + ("".join(f"<li>{esc(item)}</li>" for item in warnings) or "<li>Sin advertencias adicionales.</li>")
            + "</ul>" + failure_html
            + ("<h3>Alcance de la instrumentación</h3><ul>"
               + "".join(f"<li>{esc(note)}</li>" for note in result.get("scope_notes", [])) + "</ul>"
               if result.get("scope_notes") else "")
            + "<h3>Procedencia</h3>"
            + f"<p>Estado declarado: {esc(result.get('validation_state', 'sin declarar'))}.</p>"
            + "<p>El informe JSON conserva los valores, condiciones y huellas utilizados. "
            "Un estudio sintético verifica el procedimiento, no un equipo real.</p>")

    @Slot(str)
    def _task_failed(self, message):
        self.status_label.setText(f"No se completó la tarea: {message}")
        self.diagnostics_view.setPlainText(message)
        self.tabs.setCurrentWidget(self.diagnostics_view)

    @Slot()
    def _worker_finished(self):
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self._set_busy(False)
        if self._close_when_finished:
            QTimer.singleShot(0, self.reject)

    def _open_study(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir estudio de calibración", "", "JSON (*.json)")
        if path:
            self._load_path(path)

    def _open_example(self):
        self._load_path(Path(__file__).resolve().parent / "data" / "calibration_examples" / "study.json")

    def _load_path(self, path):
        if self._worker is not None:
            return
        self._close_when_finished = False
        worker = _StudyThread(path, parent=self)
        self._worker = worker
        worker.completed.connect(self._study_loaded)
        worker.failed.connect(self._task_failed)
        worker.finished.connect(self._worker_finished)
        self._set_busy(True)
        self.status_label.setText("Leyendo y validando el estudio y sus archivos de ensayo.")
        worker.start()

    def _ensure_output(self, path):
        target = Path(path).resolve()
        protected = set(self._protected_inputs)
        if self._study_path is not None:
            # Include new references if a manifest was edited externally after
            # the run, without allowing that edit to alter the stored result.
            if self._study_path.exists():
                with self._study_path.open("rb") as handle:
                    raw = handle.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise ValueError("El manifiesto fue modificado y supera el límite de lectura.")
                current = json.loads(raw.decode("utf-8-sig"))
                protected.update(self._input_paths(self._study_path, current))
        key = os.path.normcase(str(target))
        for source in protected:
            if key == os.path.normcase(str(source)) or (
                target.exists() and source.exists() and target.samefile(source)
            ):
                raise ValueError("La salida no puede sobrescribir el estudio, sus casos ni sus mediciones.")
        return target

    def _assert_report_matches_study(self, result):
        """Reject a fit of files that differ from the reviewed preflight snapshot."""
        from dynamic_calibration_cli import guard_snapshot
        if not isinstance(result, dict) or not self._study:
            raise ValueError("No hay un resultado comprobado del estudio revisado.")
        try:
            guard_snapshot(self._study, result)
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("El resultado no conserva las huellas de todas sus entradas.") from exc

    def _write_output(self, path, value):
        from dynamic_calibration_cli import _write_json
        self._assert_report_matches_study(self._result)
        # Recheck resolved destinations/aliases, including references edited
        # since the run. Atomic replacement avoids truncating hardlinked data.
        target = self._ensure_output(path)
        _write_json(target, value, overwrite=True)

    def _export_report(self):
        if self._worker is not None or self._result is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar informe de calibración", "informe_calibracion.json", "JSON (*.json)")
        if path:
            try:
                self._write_output(path, self._result)
            except (OSError, ValueError, TypeError, KeyError) as exc:
                QMessageBox.warning(self, "No se pudo guardar el informe", str(exc))

    def _export_case(self):
        if self._worker is not None or not self._can_export_case():
            return
        index = self.case_combo.currentIndex()
        if not 0 <= index < len(self._export_cases):
            return
        item = self._export_cases[index]
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar copia del caso ajustado", "tanque_ajustado.json", "JSON (*.json)")
        if path:
            try:
                self._write_output(path, item["fitted_case"])
            except (OSError, ValueError, TypeError, KeyError) as exc:
                QMessageBox.warning(self, "No se pudo guardar el caso", str(exc))

    def reject(self):
        if self._worker is not None:
            self._close_when_finished = True
            self.cancel_calibration()
            return
        super().reject()

    def closeEvent(self, event):
        if self._worker is not None:
            self._close_when_finished = True
            self.cancel_calibration()
            event.ignore()
        else:
            super().closeEvent(event)
