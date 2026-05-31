"""
economics_panel.py — Panel económico IN-PROCESS de la GUI viva.

Reemplaza el bridge legacy (xlsx temporal + subproceso ana_qt.py) por un
QDialog que corre simulate_engine.simulate(run_economics=True) sobre el
flowsheet actual y muestra NPV/IRR/Payback/ROI/COM ahí mismo, sin disco ni
subproceso.

NO reimplementa el motor económico: orquesta simulate() y presenta el dict.
NO importa ana_qt / montecarlo / flujoflujoclass — solo simulate_engine y
econ_defaults.  Respeta el perfil económico activo (econ_defaults: perfil
regional + HI factor + Turton γ), que simulate() ya aplica por dentro.

El diseño visual es responsabilidad de una fase Design posterior; acá se
prioriza correcto y funcional, con widgets nombrados y estructura limpia.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QLabel,
    QDoubleSpinBox, QSpinBox, QCheckBox, QComboBox, QPushButton, QTextEdit,
    QDialogButtonBox,
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

import econ_defaults as ed
import simulate_engine as se


def _fmt_usd(x):
    """USD con separador de miles; '—' si None."""
    if x is None:
        return "—"
    try:
        return f"$ {float(x):,.0f}"
    except (TypeError, ValueError):
        return str(x)


def _fmt_musd(x):
    if x is None:
        return "—"
    try:
        return f"$ {float(x) / 1e6:,.2f} MM"
    except (TypeError, ValueError):
        return str(x)


def _fmt_pct(x):
    if x is None or isinstance(x, str):
        return x if isinstance(x, str) else "—"
    try:
        return f"{float(x):.1f} %"
    except (TypeError, ValueError):
        return str(x)


def _fmt_yr(x):
    if x is None or isinstance(x, str):
        return x if isinstance(x, str) else "—"
    try:
        return f"{float(x):.2f} años"
    except (TypeError, ValueError):
        return str(x)


class EconomicsPanel(QDialog):
    """Diálogo económico in-process.  Toma un Flowsheet, recolecta inputs
    económicos (prellenados con econ_defaults), corre simulate() al apretar
    "Calcular" y muestra el resultado."""

    def __init__(self, fs, parent=None):
        super().__init__(parent)
        self.fs = fs
        self.last_result = None        # último dict de simulate() (para tests)
        self.setWindowTitle("Análisis económico (in-process)")
        self.resize(560, 720)
        self._build_ui()

    # ── construcción de UI ───────────────────────────────────────────
    def _build_ui(self):
        root = QVBoxLayout(self)

        # Perfil activo (read-only — se edita en "Perfil económico…")
        prof = QGroupBox("Perfil económico activo (read-only)")
        pf = QFormLayout(prof)
        try:
            gamma = ed.get_com_coeffs().get("gamma_variable", float("nan"))
            hi = ed.get_heat_integration_factor()
            pf.addRow("Perfil regional:", QLabel(str(ed.active_profile())))
            pf.addRow("Heat integration:", QLabel(f"{hi:.2f}"))
            pf.addRow("Turton γ:", QLabel(f"{gamma:.2f}"))
        except Exception as e:                       # pragma: no cover
            pf.addRow(QLabel(f"(perfil no disponible: {e})"))
        pf.addRow(QLabel("Editá en «Perfil económico…»."))
        root.addWidget(prof)

        # Inputs financieros (prellenados con get_financial)
        fin = {}
        try:
            fin = ed.get_financial()
        except Exception:
            fin = {}
        d_years = int(fin.get("project_years", 10))
        d_tax   = float(fin.get("tax_rate", 0.30))
        d_disc  = float(fin.get("discount_rate", 0.10))

        box = QGroupBox("Parámetros financieros")
        form = QFormLayout(box)

        self.spin_life = QSpinBox()
        self.spin_life.setRange(1, 60)
        self.spin_life.setValue(d_years)
        form.addRow("Vida del proyecto (años):", self.spin_life)

        self.spin_useful = QSpinBox()
        self.spin_useful.setRange(1, 60)
        self.spin_useful.setValue(d_years)
        self.spin_useful.setToolTip("Vida depreciable (default = vida del proyecto).")
        form.addRow("Vida depreciable (años):", self.spin_useful)

        self.spin_tax = QDoubleSpinBox()
        self.spin_tax.setRange(0.0, 1.0)
        self.spin_tax.setSingleStep(0.01)
        self.spin_tax.setDecimals(3)
        self.spin_tax.setValue(d_tax)
        form.addRow("Tasa de impuestos (0-1):", self.spin_tax)

        self.spin_disc = QDoubleSpinBox()
        self.spin_disc.setRange(0.0, 1.0)
        self.spin_disc.setSingleStep(0.01)
        self.spin_disc.setDecimals(3)
        self.spin_disc.setValue(d_disc)
        form.addRow("Tasa de descuento (0-1):", self.spin_disc)

        self.spin_year = QSpinBox()
        self.spin_year.setRange(1990, 2100)
        self.spin_year.setValue(2024)
        self.spin_year.setToolTip("Año base CEPCI para el costing de capital.")
        form.addRow("Año CEPCI (year_target):", self.spin_year)

        # ISBL override opcional (en MMUSD).  Vacío → derivado de los bloques.
        row_isbl = QHBoxLayout()
        self.chk_isbl = QCheckBox("ISBL override (MMUSD):")
        self.chk_isbl.setToolTip(
            "Si está desmarcado, el ISBL se deriva de los bloques (Turton "
            "por equipo) — idéntico a la ruta Guardar.")
        self.spin_isbl = QDoubleSpinBox()
        self.spin_isbl.setRange(0.0, 1e6)
        self.spin_isbl.setDecimals(3)
        self.spin_isbl.setEnabled(False)
        self.chk_isbl.toggled.connect(self.spin_isbl.setEnabled)
        row_isbl.addWidget(self.chk_isbl)
        row_isbl.addWidget(self.spin_isbl)
        form.addRow(row_isbl)

        root.addWidget(box)

        # Depreciación: lineal (default) o MACRS 5/7/15
        dep_box = QGroupBox("Depreciación")
        dep_form = QFormLayout(dep_box)
        self.combo_dep = QComboBox()
        # itemData = (dep_method, macrs_class)
        self.combo_dep.addItem("Lineal", ("straight_line", None))
        self.combo_dep.addItem("MACRS 5 años", ("macrs", 5))
        self.combo_dep.addItem("MACRS 7 años", ("macrs", 7))
        self.combo_dep.addItem("MACRS 15 años", ("macrs", 15))
        self.combo_dep.setToolTip(
            "Lineal = base/período (default, comportamiento histórico).\n"
            "MACRS = depreciación acelerada IRS (tax-shield temprano).")
        dep_form.addRow("Método:", self.combo_dep)

        self.spin_dep_years = QSpinBox()
        self.spin_dep_years.setRange(1, 60)
        self.spin_dep_years.setValue(d_years)
        self.spin_dep_years.setToolTip("Período de depreciación lineal (años).")
        dep_form.addRow("Período lineal (años):", self.spin_dep_years)

        def _on_dep_changed(*_a):
            data = self.combo_dep.currentData()
            if not data:
                return
            method, _ = data
            self.spin_dep_years.setEnabled(method == "straight_line")
        self.combo_dep.currentIndexChanged.connect(_on_dep_changed)
        _on_dep_changed()
        root.addWidget(dep_box)

        # Botón Calcular
        self.btn_calc = QPushButton("Calcular")
        self.btn_calc.clicked.connect(self._run)
        root.addWidget(self.btn_calc)

        # Resultados
        res_box = QGroupBox("Resultados")
        res_layout = QVBoxLayout(res_box)
        self.lbl_status = QLabel("Presioná «Calcular».")
        self.lbl_status.setWordWrap(True)
        res_layout.addWidget(self.lbl_status)

        self.txt_results = QTextEdit()
        self.txt_results.setReadOnly(True)
        self.txt_results.setFont(QFont("Consolas", 10))
        res_layout.addWidget(self.txt_results)
        root.addWidget(res_box, stretch=1)

        # Cerrar
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        root.addWidget(btns)

    # ── recolección de inputs ────────────────────────────────────────
    def collect_econ_inputs(self):
        """Devuelve el dict econ_inputs para simulate(), tomado de los
        campos del panel.  Mismas claves que consume simulate_engine."""
        inputs = {
            "project_life": int(self.spin_life.value()),
            "useful_life": int(self.spin_useful.value()),
            "tax_rate": float(self.spin_tax.value()),
            "discount_rate": float(self.spin_disc.value()),
            "year_target": int(self.spin_year.value()),
        }
        if self.chk_isbl.isChecked():
            inputs["isbl_override_usd"] = float(self.spin_isbl.value()) * 1e6
        method, macrs_class = self.combo_dep.currentData()
        inputs["dep_method"] = method
        if method == "macrs":
            inputs["macrs_class"] = int(macrs_class)
        else:
            inputs["dep_years"] = int(self.spin_dep_years.value())
        return inputs

    # ── ejecución ────────────────────────────────────────────────────
    def _run(self):
        """Corre simulate(run_economics=True) IN-PROCESS y renderiza."""
        try:
            out = se.simulate(
                self.fs.to_dict(),
                run_economics=True,
                econ_inputs=self.collect_econ_inputs(),
            )
        except Exception as e:                       # pragma: no cover
            self.last_result = None
            self.lbl_status.setText(
                f"<b style='color:#c0392b'>Error al calcular:</b> "
                f"{type(e).__name__}: {e}")
            self.txt_results.clear()
            return
        self.last_result = out
        self._render(out)

    def _render(self, out):
        """Pinta el dict de simulate().  Si el flowsheet no resolvió
        (status error/empty), muestra mensaje claro en vez de números."""
        status = out.get("summary", {}).get("overall_status", "error")
        if status in ("error", "empty"):
            solver = out.get("solver", {})
            errs = (solver.get("mass_balance_errors", [])
                    + solver.get("energy_balance_errors", [])
                    + solver.get("consistency_errors", []))
            detail = "\n".join(f"   · {m}" for m in errs[:12]) or "   (sin detalle)"
            self.lbl_status.setText(
                f"<b style='color:#c0392b'>El flowsheet no resolvió "
                f"(status: {status}).</b><br>No se muestran indicadores "
                f"económicos para evitar números engañosos.")
            self.txt_results.setPlainText(
                f"Estado del solver: {status}\n\nProblemas:\n{detail}")
            return

        econ = out.get("economics", {})
        cap = econ.get("capex", {})
        com = econ.get("com", {})
        opex = econ.get("opex_usd_yr", {})

        warn = ""
        if status == "warning":
            warn = ("  <span style='color:#b9770e'>(solver con warnings — "
                    "revisar balances)</span>")
        self.lbl_status.setText(
            f"<b>Veredicto:</b> {econ.get('veredicto', '—')}"
            f"   ·   status: {status}{warn}")

        depinfo = econ.get("depreciation", {})
        _dm = depinfo.get("method", "straight_line")
        dep_label = ("Lineal" if _dm == "straight_line"
                     else f"MACRS {depinfo.get('macrs_class')} años")
        lines = []
        lines.append(f"Depreciación: {dep_label}")
        lines.append("")
        lines.append("INDICADORES DE RENTABILIDAD")
        lines.append("─" * 46)
        lines.append(f"  NPV                 {_fmt_usd(econ.get('NPV_usd'))}")
        lines.append(f"  IRR                 {_fmt_pct(econ.get('IRR_pct'))}")
        lines.append(f"  Payback (simple)    {_fmt_yr(econ.get('payback_yr'))}")
        lines.append(f"  ROI                 {_fmt_pct(econ.get('ROI_pct'))}")
        lines.append("")
        lines.append("CAPITAL")
        lines.append("─" * 46)
        lines.append(f"  ISBL                {_fmt_musd(cap.get('isbl_usd'))}")
        lines.append(f"  FCI (grass roots)   {_fmt_musd(cap.get('fci_grass_roots_usd'))}")
        lines.append(f"  Working capital     {_fmt_musd(cap.get('working_capital_usd'))}")
        lines.append("")
        lines.append("COSTO DE MANUFACTURA (Turton Eq 8.2)")
        lines.append("─" * 46)
        lines.append(f"  COM_d (con dep.)    {_fmt_usd(com.get('COM_d_usd_yr'))} /año")
        lines.append(f"  COM (sin dep.)      {_fmt_usd(com.get('COM_usd_yr'))} /año")
        lines.append("")
        lines.append("FLUJOS ANUALES")
        lines.append("─" * 46)
        lines.append(f"  Revenue             {_fmt_usd(opex.get('revenue'))} /año")
        lines.append(f"  CRM (materias prim) {_fmt_usd(opex.get('crm'))} /año")
        lines.append(f"  CUT (utilities)     {_fmt_usd(opex.get('cut'))} /año")
        lines.append(f"  CWT (tratamiento)   {_fmt_usd(opex.get('cwt'))} /año")
        lines.append(f"  COL (labor)         {_fmt_usd(opex.get('col'))} /año")
        lines.append(f"  Cash flow           {_fmt_usd(econ.get('cash_flow_usd_yr'))} /año")
        self.txt_results.setPlainText("\n".join(lines))
