"""
economics_panel.py — Panel económico IN-PROCESS de la GUI viva.

UNA sola UI (rediseño 1e/1f): el diálogo monta EconRichView desde el
arranque — header + hero de KPIs (una sola vez) + sidebar de 7 panes
reales + footer de acciones.  Los parámetros viven en el pane
«⚙ Parámetros» (este módulo construye el formulario) y Monte Carlo corre
EMBEBIDO en su pane con las figuras de econ_figures (densidad de NPV +
tornado).  El dump ASCII de resultados, la tab bar exterior duplicada,
el renderer legacy y la ventana Monte Carlo aparte murieron con el
rediseño.

NO reimplementa el motor económico: orquesta simulate() y presenta el
dict.  NO importa ana_qt / montecarlo / flujoflujoclass — solo
simulate_engine, econ_defaults y montecarlo_headless (lazy).  Respeta el
perfil económico activo (econ_defaults: perfil regional + HI factor +
Turton γ), que simulate() ya aplica por dentro.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QLabel,
    QDoubleSpinBox, QSpinBox, QCheckBox, QComboBox, QPushButton,
    QLineEdit, QWidget,
)
from PySide6.QtCore import Qt

import econ_defaults as ed
import simulate_engine as se
from tokens import TOK, fmt_pct


def _parse_csv(text):
    """'0.5, 0.75, 1.0' -> [0.5, 0.75, 1.0].  [] si vacío/ inválido."""
    text = (text or "").strip()
    if not text:
        return []
    out = []
    for tok in text.replace(";", ",").split(","):
        tok = tok.strip()
        if not tok:
            continue
        try:
            out.append(float(tok))
        except ValueError:
            return []
    return out


def _wrap(layout):
    """Envuelve un layout en un QWidget (para QFormLayout.addRow)."""
    w = QWidget(); w.setLayout(layout)
    return w


class EconomicsPanel(QDialog):
    """Diálogo económico in-process.  Toma un Flowsheet, monta la
    EconRichView (única UI), recolecta inputs económicos en el pane
    Parámetros (prellenados con econ_defaults), corre simulate() al
    apretar «Calcular» y puebla los panes con el resultado."""

    def __init__(self, fs, parent=None):
        super().__init__(parent)
        self.fs = fs
        self.last_result = None        # último dict de simulate() (para tests)
        self._main_window = parent
        self.setWindowTitle("Análisis económico")
        # Tamaño apto para laptops chicas: los panes scrollean por dentro.
        self.resize(760, 700)
        self.setMinimumSize(560, 400)
        self._build_ui()

    # ── construcción de UI ───────────────────────────────────────────
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        # Widgets huésped de la rich view — se construyen UNA vez y se
        # re-enganchan en cada _mount_rich (detach_hosted).
        self._params_widget = self._build_params_widget()
        self._mc_pane = MonteCarloPane(
            get_flowsheet_dict=lambda: self.fs.to_dict(),
            get_econ_inputs=self.collect_econ_inputs)
        self._rich = None
        self._rich_lay = outer
        self._last_metrics = None
        self._mount_rich(None)          # estado vacío → pane Parámetros
        # Cambio de tema → re-montar la vista para que las figuras
        # matplotlib re-lean los tokens (antes quedaban con los colores
        # del tema anterior; la anotación de payback era ilegible en dark).
        from tokens import _PrefsBus
        _PrefsBus.signal().connect(self._on_theme_changed)

    def _on_theme_changed(self):
        try:
            self._mount_rich(self._last_metrics)
        except RuntimeError:            # diálogo ya destruido (shutdown)
            pass

    def _build_params_widget(self):
        """Formulario de parámetros (pane ⚙ de la rich view)."""
        w = QWidget()
        root = QVBoxLayout(w)
        root.setContentsMargins(0, 0, 0, 0)

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
        form.addRow("Año CEPCI:", self.spin_year)

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

        # Cash flow enriquecido (opt-in; vacío/0 = caso simple)
        cf_box = QGroupBox("Cash flow (opcional — vacío = caso simple)")
        cf_form = QFormLayout(cf_box)
        self.edit_constr = QLineEdit()
        self.edit_constr.setPlaceholderText("ej: 0.6,0.4  (vacío = 1 año, año 0)")
        self.edit_constr.setToolTip("Fracción de CapEx por año de construcción (CSV).")
        cf_form.addRow("Construcción (FC):", self.edit_constr)
        self.edit_ramp = QLineEdit()
        self.edit_ramp.setPlaceholderText("ej: 0.5,0.75,1.0  (vacío = plena)")
        self.edit_ramp.setToolTip("Fracción de capacidad por año de operación (ramp-up, CSV).")
        cf_form.addRow("Ramp-up (VCOP):", self.edit_ramp)
        self.spin_roy = QDoubleSpinBox()
        self.spin_roy.setRange(0.0, 0.5); self.spin_roy.setSingleStep(0.01)
        self.spin_roy.setDecimals(3); self.spin_roy.setValue(0.0)
        self.spin_roy.setToolTip("Royalties como fracción de ingresos (rev·pct).")
        cf_form.addRow("Royalties (frac):", self.spin_roy)
        self.chk_taxlag = QCheckBox("Desfase de impuestos (1 año)")
        cf_form.addRow(self.chk_taxlag)
        root.addWidget(cf_box)

        # Estado + botón Calcular
        self.lbl_status = QLabel("Configurá y presioná «Calcular».")
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)
        self.btn_calc = QPushButton("Calcular")
        self.btn_calc.clicked.connect(self._run)
        root.addWidget(self.btn_calc)
        root.addStretch(1)
        return w

    def _mount_rich(self, m):
        """(Re)monta la EconRichView con las métricas m (None = estado
        vacío pre-cálculo).  Los widgets huésped (parámetros y Monte
        Carlo) sobreviven al re-montaje."""
        from econ_richview import EconRichView
        if self._rich is not None:
            self._rich.detach_hosted()
            self._rich.setParent(None)
            self._rich.deleteLater()
        proj = getattr(self.fs, "name", "") or "flowsheet"
        desc = f"{proj} · CEPCI {self.spin_year.value()}"
        export_cb = getattr(self._main_window, "action_export_xlsx", None)
        rv = EconRichView(m, project=desc,
                          params_widget=self._params_widget,
                          mc_widget=self._mc_pane,
                          show_export=callable(export_cb))
        rv.rerun.connect(self._run)
        rv.closeClicked.connect(self.reject)
        if callable(export_cb):
            rv.exportExcel.connect(export_cb)
        self._rich_lay.addWidget(rv, stretch=1)
        self._rich = rv
        self._last_metrics = m

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
        # Cash flow enriquecido (opt-in). Schedules solo si hay CSV; royalties
        # y tax_lag se pasan siempre (0/False = caso simple, no enriquece).
        constr = _parse_csv(self.edit_constr.text())
        ramp = _parse_csv(self.edit_ramp.text())
        if constr:
            inputs["construction_schedule"] = constr
        if ramp:
            inputs["rampup_schedule"] = ramp
        inputs["royalties_pct"] = float(self.spin_roy.value())
        inputs["tax_lag"] = bool(self.chk_taxlag.isChecked())
        return inputs

    # ── ejecución ────────────────────────────────────────────────────
    def _run(self):
        """Corre simulate(run_economics=True) IN-PROCESS y puebla la UI."""
        try:
            out = se.simulate(
                self.fs.to_dict(),
                run_economics=True,
                econ_inputs=self.collect_econ_inputs(),
            )
        except Exception as e:                       # pragma: no cover
            self.last_result = None
            self.lbl_status.setText(
                f"<b style='color:{TOK['danger']}'>Error al calcular:</b> "
                f"{type(e).__name__}: {e}")
            if self._rich is not None:
                self._rich.set_pane(6)
            return
        self.last_result = out
        self._render(out)

    def _render(self, out):
        """Puebla la rich view con el dict de simulate().  Si el
        flowsheet no resolvió (status error/empty), muestra el detalle
        en el pane Parámetros en vez de números engañosos."""
        status = out.get("summary", {}).get("overall_status", "error")
        if status in ("error", "empty"):
            solver = out.get("solver", {})
            errs = (solver.get("mass_balance_errors", [])
                    + solver.get("energy_balance_errors", [])
                    + solver.get("consistency_errors", []))
            detail = "<br>".join(f"· {m}" for m in errs[:12]) or "(sin detalle)"
            self.lbl_status.setText(
                f"<b style='color:{TOK['danger']}'>El flowsheet no resolvió "
                f"(status: {status}).</b><br>No se muestran indicadores "
                f"económicos para evitar números engañosos.<br>{detail}")
            if self._rich is not None:
                self._rich.set_pane(6)
            return

        econ = out.get("economics", {})
        warn = ""
        if status == "warning":
            warn = (f"  <span style='color:{TOK['amber']}'>(solver con "
                    "warnings — revisar balances)</span>")
        irr = econ.get("IRR_pct")
        self.lbl_status.setText(
            f"<b>Veredicto:</b> {econ.get('veredicto', '—')}"
            f"   ·   TIR {fmt_pct(irr) if irr is not None else '—'}"
            f"   ·   status: {status}{warn}")

        from econ_evidence import econ_metrics
        m = econ_metrics(econ, out.get("costing"))
        if not m:
            self.lbl_status.setText(
                f"<b style='color:{TOK['danger']}'>El cálculo no devolvió "
                f"métricas económicas.</b>")
            if self._rich is not None:
                self._rich.set_pane(6)
            return
        self._mount_rich(m)


class MonteCarloPane(QWidget):
    """Pane Monte Carlo EMBEBIDO en la rich view (rediseño 1f).

    Reemplaza a la ventana ASCII aparte: mismas variables inciertas
    (precios de productos / materias primas / ISBL), distribución y
    rango ±% por variable, n_runs, seed y correlación opcional — pero el
    resultado se presenta con las figuras reales de econ_figures
    (densidad de NPV con P10/P50/P90 y cola P(NPV<0) + tornado), que
    estaban implementadas y nunca cableadas.

    Motor: montecarlo_headless (lazy) → simulate() repetido.
    """

    def __init__(self, get_flowsheet_dict, get_econ_inputs, parent=None):
        super().__init__(parent)
        self._get_fs = get_flowsheet_dict
        self._get_inputs = get_econ_inputs
        self.last_result = None
        self.last_tornado = None
        self._rows = []          # [{kind, indice, nombre, base, chk, combo, spin}]
        self._build_ui()

    def _build_ui(self):
        import montecarlo_headless as mh
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        intro = QLabel(
            "Variables inciertas: marcá las que querés samplear y su rango "
            "±%.  El motor es simulate() repetido.")
        intro.setWordWrap(True)
        root.addWidget(intro)

        try:
            targets = mh.list_uncertain_targets(self._get_fs())
        except Exception as e:                       # pragma: no cover
            root.addWidget(QLabel(f"No se pudieron leer targets: {e}"))
            targets = {"products": [], "raw_materials": [], "isbl": {}}

        box = QGroupBox("Variables")
        form = QFormLayout(box)

        def _add_row(kind, idx, name, base, unit):
            chk = QCheckBox(f"{name}  (base {base:.4g} {unit})")
            combo = QComboBox()
            combo.addItem("Triangular", mh.DIST_TRIANGULAR)
            combo.addItem("Normal", mh.DIST_NORMAL)
            combo.addItem("Uniforme", mh.DIST_UNIFORM)
            spin = QDoubleSpinBox()
            spin.setRange(1.0, 90.0); spin.setValue(20.0); spin.setSuffix(" %")
            row_w = QHBoxLayout()
            row_w.addWidget(combo); row_w.addWidget(spin)
            form.addRow(chk, _wrap(row_w))
            self._rows.append({"kind": kind, "indice": idx, "nombre": name,
                               "base": base, "chk": chk, "combo": combo,
                               "spin": spin})

        for p in targets.get("products", []):
            _add_row(mh.KIND_PRODUCT_PRICE, p["index"], p["name"],
                     p["base_price_usd_per_tm"], "usd/tm")
        for r in targets.get("raw_materials", []):
            _add_row(mh.KIND_RAW_MATERIAL_PRICE, r["index"], r["name"],
                     r["base_price_usd_per_tm"], "usd/tm")
        isbl_base = (targets.get("isbl") or {}).get("base_usd")
        if isbl_base:
            _add_row(mh.KIND_ISBL, 0, "ISBL", isbl_base, "usd")

        root.addWidget(box)

        # Parámetros de corrida
        pbox = QGroupBox("Corrida")
        pform = QFormLayout(pbox)
        self.spin_runs = QSpinBox(); self.spin_runs.setRange(10, 100000)
        self.spin_runs.setValue(2000)
        pform.addRow("Corridas (n):", self.spin_runs)
        self.spin_seed = QSpinBox(); self.spin_seed.setRange(0, 2_000_000_000)
        self.spin_seed.setValue(42)
        pform.addRow("Seed:", self.spin_seed)
        self.chk_corr = QCheckBox("Correlacionar variables (ρ común)")
        self.spin_rho = QDoubleSpinBox()
        self.spin_rho.setRange(-0.95, 0.95); self.spin_rho.setSingleStep(0.05)
        self.spin_rho.setValue(0.0); self.spin_rho.setEnabled(False)
        self.chk_corr.toggled.connect(self.spin_rho.setEnabled)
        rho_w = QHBoxLayout(); rho_w.addWidget(self.chk_corr)
        rho_w.addWidget(self.spin_rho)
        pform.addRow(_wrap(rho_w))
        root.addWidget(pbox)

        self.btn_run = QPushButton("Correr Monte Carlo")
        self.btn_run.clicked.connect(self._run_mc)
        root.addWidget(self.btn_run)

        self.lbl = QLabel("Configurá y corré.")
        self.lbl.setWordWrap(True)
        root.addWidget(self.lbl)

        # Figuras (densidad de NPV + tornado) — pobladas tras la corrida
        self._figs_host = QWidget()
        self._figs_lay = QVBoxLayout(self._figs_host)
        self._figs_lay.setContentsMargins(0, 0, 0, 0)
        self._figs_lay.setSpacing(10)
        root.addWidget(self._figs_host)
        root.addStretch(1)

    def _build_variables(self):
        import montecarlo_headless as mh
        variables = []
        for r in self._rows:
            if not r["chk"].isChecked():
                continue
            base = r["base"]; pct = r["spin"].value() / 100.0
            variables.append(mh.VariableIncierta(
                kind=r["kind"], indice=r["indice"], nombre=r["nombre"],
                valor_min=base * (1 - pct), valor_mode=base,
                valor_max=base * (1 + pct),
                dist=r["combo"].currentData()))
        return variables

    def _run_mc(self):
        import montecarlo_headless as mh
        variables = self._build_variables()
        if not variables:
            self.lbl.setText("Marcá al menos una variable.")
            return
        # correlación común opcional (off-diagonal ρ entre todas las vars)
        correlacion = None
        if self.chk_corr.isChecked() and len(variables) > 1:
            rho = self.spin_rho.value()
            correlacion = {(i, j): rho
                           for i in range(len(variables))
                           for j in range(i + 1, len(variables))}
        fs_dict = self._get_fs()
        econ_inputs = self._get_inputs()
        try:
            res = mh.run_monte_carlo(
                fs_dict, variables, econ_inputs,
                n_runs=int(self.spin_runs.value()),
                seed=int(self.spin_seed.value()), correlacion=correlacion)
            tor = mh.run_tornado(fs_dict, variables, econ_inputs)
        except Exception as e:
            self.lbl.setText(
                f"<b style='color:{TOK['danger']}'>Monte Carlo falló:</b> "
                f"{type(e).__name__}: {e}")
            return
        self.last_result = res
        self.last_tornado = tor
        self._render(res, tor)

    def _render(self, res, tor):
        """Resumen + figuras (nada de ASCII)."""
        s = res["stats"]

        def f(x):
            return "—" if x is None else f"{x:,.2f}"

        neg_pct = s["p_npv_neg"] * 100.0
        neg_col = TOK["danger"] if neg_pct > 10 else TOK["ink_mute"]
        self.lbl.setText(
            f"<b>n = {s['n']:,}</b> · seed {int(self.spin_seed.value())}"
            f"  ·  NPV P10/P50/P90 = {f(s['npv_p10'])} / {f(s['npv_p50'])} / "
            f"{f(s['npv_p90'])} M USD"
            f"  ·  <span style='color:{neg_col}'>P(NPV&lt;0) = "
            f"{neg_pct:.1f} %</span>")

        # limpiar figuras previas
        while self._figs_lay.count():
            it = self._figs_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        try:
            from matplotlib.backends.backend_qtagg import FigureCanvas
            from econ_figures import npv_density_figure, tornado_figure
        except Exception:                            # pragma: no cover
            return

        # densidad de NPV — npvs del motor vienen en M USD; las figuras
        # esperan USD
        import math
        samples_usd = [x * 1e6 for x in res.get("npvs", [])
                       if isinstance(x, (int, float)) and math.isfinite(x)]
        mc_dict = {
            "samples": samples_usd,
            "p10": (s["npv_p10"] or 0) * 1e6,
            "p50": (s["npv_p50"] or 0) * 1e6,
            "p90": (s["npv_p90"] or 0) * 1e6,
            "p_neg": s["p_npv_neg"],
            "n_runs": s["n"],
        }
        fig, _meta = npv_density_figure(mc_dict)
        if fig is not None:
            c = FigureCanvas(fig); c.setMinimumHeight(220)
            self._figs_lay.addWidget(c)

        # tornado — npv_low/high en M USD → USD; base = P50
        rows = [{"name": t.get("nombre", f"var{i}"),
                 "lo": (t.get("npv_low") or 0) * 1e6,
                 "hi": (t.get("npv_high") or 0) * 1e6}
                for i, t in enumerate(tor or [])]
        if rows:
            fig2, _m2 = tornado_figure(rows,
                                       base=(s["npv_p50"] or 0) * 1e6)
            if fig2 is not None:
                c2 = FigureCanvas(fig2); c2.setMinimumHeight(200)
                self._figs_lay.addWidget(c2)
