"""
ana_qt.py — Análisis Económico (PySide6 rewrite del ANA.py Tkinter)

Look unificado al flowsheet editor: toolbar con íconos SVG (icons.py),
notebook con pestañas para Project Data / Equipment / Streams / Income
Statement / Costing Turton / Results + Cash Flow chart embebido.

Reemplaza el ANA.py legacy preservando funcionalidad core:
  · Import Excel (incluye xlsx del PFD con Equipment + Streams +
    Income Statement + Costing Turton sheets)
  · View / edit del Project Data (Capital + Fixed + Variable)
    — Variable Op. Costs es editable inline (doble-click)
  · Solve económico (FCI, FCOP, VCOP, COM, NPV, IRR, PBP)
  · Display de resultados con plots matplotlib embebidos:
      · Annual Cash Flow (bar chart)
      · Cumulative NPV discounted (line chart)
  · Profile activo (PE/USA/CL/EU) + Heat Integration + Turton γ

Lo que NO incluye (queda en módulos separados, llamable):
  · Monte Carlo (montecarlo.py)
  · Sensitivity tornado plots

CLI:
    python ana_qt.py --import path/to/project.xlsx
    python ana_qt.py                  # arranca vacío, user importa
"""
import os
import sys
from pathlib import Path

import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtGui  import QAction, QIcon, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QToolBar, QStatusBar, QTabWidget, QTableWidget,
    QTableWidgetItem, QLabel, QPushButton, QFileDialog, QMessageBox,
    QHeaderView, QDoubleSpinBox, QSpinBox, QGroupBox, QSplitter,
    QPlainTextEdit, QDialog, QDialogButtonBox, QComboBox, QFrame,
)

import icons


# Matplotlib embebido (opcional — degrada gracefully si no está)
try:
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    _MPL_OK = True
except Exception:
    _MPL_OK = False


# ─────────────────────────────────────────────────────────────
# COLORES / TIPO (consistente con flowsheet editor)
# ─────────────────────────────────────────────────────────────
COLOR_BG       = "#f6f7f9"
COLOR_CARD     = "#ffffff"
COLOR_NEUTRAL  = "#2a2a2a"
COLOR_SUBTLE   = "#6a6a6a"
COLOR_POSITIVE = "#0a8a3e"
COLOR_NEGATIVE = "#c41e3a"
COLOR_ACCENT   = "#1f6feb"
ICON_COLOR     = "#3a3a3a"


def _mk(icon_id, color=None, size=20):
    """Wrapper que usa icons.make_qicon con fallback gracioso."""
    try:
        return icons.make_qicon(icon_id, color=color or ICON_COLOR, size=size)
    except Exception:
        return QIcon()


# ─────────────────────────────────────────────────────────────
# DataFrame → QTableWidget helper
# ─────────────────────────────────────────────────────────────

def df_to_table(table: QTableWidget, df: pd.DataFrame,
                 number_cols=None, freeze_first_col=False):
    """Renderiza un DataFrame en un QTableWidget read-only."""
    if df is None or df.empty:
        table.setRowCount(0); table.setColumnCount(0)
        return
    table.clear()
    table.setRowCount(len(df))
    table.setColumnCount(len(df.columns))
    table.setHorizontalHeaderLabels([str(c) for c in df.columns])
    nfmt = set(number_cols or [])
    for i, (_idx, row) in enumerate(df.iterrows()):
        for j, col in enumerate(df.columns):
            v = row[col]
            if pd.isna(v):
                text = ""
            elif col in nfmt or (isinstance(v, (int, float))
                                  and not isinstance(v, bool)):
                try:
                    text = f"{float(v):,.2f}"
                except (ValueError, TypeError):
                    text = str(v)
            else:
                text = str(v)
            it = QTableWidgetItem(text)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            if col in nfmt or isinstance(v, (int, float)) and not isinstance(v, bool):
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(i, j, it)
    table.resizeColumnsToContents()
    table.horizontalHeader().setStretchLastSection(True)


# ─────────────────────────────────────────────────────────────
# Main Window
# ─────────────────────────────────────────────────────────────

class AnaMainWindow(QMainWindow):
    """Ventana principal del Análisis Económico."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Análisis Económico — Pedro-Tesis")
        self.resize(1280, 800)

        # Estado: dataframes cargados
        self.df_capital   = pd.DataFrame()
        self.df_fixed     = pd.DataFrame()
        self.df_variable  = pd.DataFrame()
        self.df_equipment = pd.DataFrame()
        self.df_streams   = pd.DataFrame()
        self.df_income    = pd.DataFrame()
        self.df_costing   = pd.DataFrame()
        self.current_file = None

        self._build_toolbar()
        self._build_central()
        self._build_statusbar()

    # ─── Toolbar con íconos SVG ──────────────────────────────
    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(self.geometry().size().scaled(28, 28,
                          Qt.KeepAspectRatio))
        from PySide6.QtCore import QSize
        tb.setIconSize(QSize(22, 22))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(tb)

        # Grupo: archivo
        act_new = QAction(_mk("file-new"), "New", self)
        act_new.setToolTip("Empezar nuevo proyecto (limpia datos)")
        act_new.triggered.connect(self.action_new)
        tb.addAction(act_new)

        act_open = QAction(_mk("file-open"), "Open…", self)
        act_open.setShortcut("Ctrl+O")
        act_open.setToolTip("Importar proyecto desde Excel (.xlsx)")
        act_open.triggered.connect(self.action_open)
        tb.addAction(act_open)

        act_save = QAction(_mk("file-save"), "Save", self)
        act_save.setShortcut("Ctrl+S")
        act_save.setToolTip("Guardar como Excel")
        act_save.triggered.connect(self.action_save)
        tb.addAction(act_save)

        tb.addSeparator()

        # Grupo: análisis
        act_solve = QAction(_mk("sim-run", color=COLOR_POSITIVE), "Solve", self)
        act_solve.setShortcut("F5")
        act_solve.setToolTip("Calcular FCI, COM, NPV, IRR, PBP (F5)")
        act_solve.triggered.connect(self.action_solve)
        tb.addAction(act_solve)

        act_montecarlo = QAction(_mk("an-monte-carlo"),
                                    "Monte Carlo…", self)
        act_montecarlo.setToolTip("Análisis Monte Carlo de NPV "
                                    "con incertidumbre")
        act_montecarlo.triggered.connect(self.action_montecarlo)
        tb.addAction(act_montecarlo)

        tb.addSeparator()

        # Grupo: navegación
        act_flowsheet = QAction(_mk("eq-cstr"),
                                   "Open Flowsheet…", self)
        act_flowsheet.setToolTip("Abrir editor PFD (genera el xlsx "
                                   "de entrada para este análisis)")
        act_flowsheet.triggered.connect(self.action_open_flowsheet)
        tb.addAction(act_flowsheet)

        # Spacer + status
        from PySide6.QtWidgets import QWidget as _W
        spacer = _W()
        spacer.setSizePolicy(spacer.sizePolicy().Expanding,
                              spacer.sizePolicy().Preferred)
        tb.addWidget(spacer)

        self.profile_label = QLabel("")
        self.profile_label.setStyleSheet(
            f"color: {COLOR_SUBTLE}; padding-right: 12px; font-size: 9pt;"
        )
        tb.addWidget(self.profile_label)
        self._refresh_profile_label()

        act_profile = QAction(_mk("act-money", color=COLOR_ACCENT),
                                "Perfil econ…", self)
        act_profile.setToolTip("Editar perfil económico activo (PE/USA/CL/EU)"
                                 ", Heat Integration, Turton γ")
        act_profile.triggered.connect(self.action_profile)
        tb.addAction(act_profile)

    def _refresh_profile_label(self):
        try:
            import econ_defaults as ed
            p = ed.active_profile()
            hi = ed.get_heat_integration_factor()
            g  = ed.get_com_coeffs()["gamma_variable"]
            self.profile_label.setText(
                f"Perfil: {p}   HI={hi:.2f}   γ={g:.2f}")
        except Exception:
            self.profile_label.setText("")

    # ─── Central: splitter horizontal con tabs ──────────────
    def _build_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # Banner del proyecto cargado
        self.banner = QLabel("Ningún proyecto cargado. "
                               "Usá Open… para importar un .xlsx, o "
                               "Open Flowsheet… para diseñar uno.")
        self.banner.setStyleSheet(
            f"background: {COLOR_CARD}; color: {COLOR_SUBTLE}; "
            "padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px;"
        )
        lay.addWidget(self.banner)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)
        self.tabs.setDocumentMode(True)
        lay.addWidget(self.tabs, 1)

        # Cada tab tiene su QTableWidget
        self._make_tab("Capital Costs",       _mk("act-money"))
        self._make_tab("Fixed Op. Costs",     _mk("act-money", color="#666"))
        self._make_tab("Variable Op. Costs",  _mk("act-money"))
        self._make_tab("Equipment",           _mk("eq-cstr"))
        self._make_tab("Streams",             _mk("eq-pipe"))
        self._make_tab("Costing Turton",      _mk("an-case-study"))
        self._make_tab("Income Statement",    _mk("an-case-study"))
        self._make_tab("Results",             _mk("an-optimizer"))
        self._make_chart_tab()

    def _make_tab(self, name, icon=None):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        table = QTableWidget()
        table.setAlternatingRowColors(True)
        table.setStyleSheet(
            "QTableWidget {background: white; gridline-color: #e0e0e0;}"
            "QHeaderView::section {background: #f0f2f5; "
            " color: #2a2a2a; font-weight: 600; padding: 4px;}"
        )
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Interactive)
        lay.addWidget(table)
        if icon:
            idx = self.tabs.addTab(w, icon, name)
        else:
            idx = self.tabs.addTab(w, name)
        # Guardar referencia
        setattr(self, f"_tab_{name.replace(' ', '_').replace('.', '').lower()}",
                  (w, table))
        return idx, table

    def _table_for_tab(self, name):
        attr = f"_tab_{name.replace(' ', '_').replace('.', '').lower()}"
        pair = getattr(self, attr, None)
        return pair[1] if pair else None

    def _make_chart_tab(self):
        """Tab con plots matplotlib embebidos para cash flow + NPV."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        if _MPL_OK:
            self.chart_figure = Figure(figsize=(11, 5), dpi=100,
                                          facecolor=COLOR_BG)
            self.chart_canvas = FigureCanvasQTAgg(self.chart_figure)
            lay.addWidget(self.chart_canvas)
            self.chart_msg = QLabel(
                "Corré Solve (F5) para ver el cash flow año por año.",
            )
            self.chart_msg.setStyleSheet(
                f"color: {COLOR_SUBTLE}; padding: 4px 8px;")
            self.chart_msg.setAlignment(Qt.AlignCenter)
            lay.addWidget(self.chart_msg)
        else:
            self.chart_canvas = None
            lay.addWidget(QLabel(
                "matplotlib no instalado — instalar con:\n"
                "    pip install matplotlib\n\n"
                "El cash flow se sigue calculando y aparece en\n"
                "el tab 'Income Statement' como tabla."
            ))
        self.tabs.addTab(w, _mk("an-monte-carlo"), "Cash Flow Chart")
        self._tab_chart = w

    def _update_chart(self, cf_years, cf_values, npv_cumulative,
                       payback_yr=None, npv_final=None):
        """Actualiza el plot embebido con datos de cash flow + cum NPV."""
        if not _MPL_OK or self.chart_canvas is None:
            return
        self.chart_figure.clear()
        # Plot 1: bars de annual cash flow
        ax1 = self.chart_figure.add_subplot(1, 2, 1, facecolor="white")
        colors = [COLOR_POSITIVE if v >= 0 else COLOR_NEGATIVE
                   for v in cf_values]
        ax1.bar(cf_years, [v/1e6 for v in cf_values], color=colors,
                 edgecolor="white")
        ax1.axhline(0, color="black", linewidth=0.8)
        ax1.set_title("Annual Cash Flow", fontsize=11, fontweight="bold",
                       color=COLOR_NEUTRAL)
        ax1.set_xlabel("Project year")
        ax1.set_ylabel("CF (MM USD)")
        ax1.grid(True, axis="y", alpha=0.3, linestyle="--")
        for spine in ("top", "right"):
            ax1.spines[spine].set_visible(False)

        # Plot 2: cumulative NPV (discounted)
        ax2 = self.chart_figure.add_subplot(1, 2, 2, facecolor="white")
        cum_mm = [v/1e6 for v in npv_cumulative]
        ax2.plot(cf_years, cum_mm, marker="o", color=COLOR_ACCENT,
                  linewidth=2)
        # Sombreado: verde si positivo, rojo si negativo
        ax2.fill_between(cf_years, cum_mm, 0,
                         where=[v >= 0 for v in cum_mm],
                         interpolate=True, alpha=0.20,
                         color=COLOR_POSITIVE)
        ax2.fill_between(cf_years, cum_mm, 0,
                         where=[v < 0 for v in cum_mm],
                         interpolate=True, alpha=0.20,
                         color=COLOR_NEGATIVE)
        ax2.axhline(0, color="black", linewidth=0.8)
        ax2.set_title("Cumulative NPV (discounted)", fontsize=11,
                       fontweight="bold", color=COLOR_NEUTRAL)
        ax2.set_xlabel("Project year")
        ax2.set_ylabel("Σ PV(CF)  (MM USD)")
        ax2.grid(True, alpha=0.3, linestyle="--")
        for spine in ("top", "right"):
            ax2.spines[spine].set_visible(False)
        # PBP descontado: punto donde cum NPV cruza 0
        if payback_yr is not None and 0 < payback_yr < cf_years[-1]:
            ax2.axvline(payback_yr, color=COLOR_NEGATIVE,
                         linestyle="--", linewidth=1.5,
                         label=f"PBP discntd ≈ {payback_yr:.1f} yr")
            ax2.legend(loc="best", fontsize=9)
        # Anotar NPV final en el último punto
        if npv_final is not None:
            ax2.annotate(
                f"NPV = {npv_final/1e6:+.1f} MM",
                xy=(cf_years[-1], cum_mm[-1]),
                xytext=(-90, 12 if cum_mm[-1] >= 0 else -24),
                textcoords="offset points",
                fontsize=10, fontweight="bold",
                color=COLOR_POSITIVE if cum_mm[-1] >= 0 else COLOR_NEGATIVE,
            )
        self.chart_figure.tight_layout()
        self.chart_canvas.draw()
        if hasattr(self, "chart_msg"):
            self.chart_msg.setText(
                f"NPV(final) = {npv_final/1e6:+.2f} MM USD" if npv_final
                else "")

    def _build_statusbar(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Listo.")

    # ─── ACCIONES ─────────────────────────────────────────────

    def action_new(self):
        ans = QMessageBox.question(
            self, "Nuevo proyecto",
            "Descarta los datos actuales y empieza nuevo.\n"
            "¿Continuar?",
            QMessageBox.Yes | QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        self.df_capital = self.df_fixed = self.df_variable = pd.DataFrame()
        self.df_equipment = self.df_streams = self.df_income = pd.DataFrame()
        self.df_costing = pd.DataFrame()
        self.current_file = None
        self._refresh_tabs()
        self.banner.setText("Ningún proyecto cargado.")
        self.status.showMessage("Proyecto reseteado.", 4000)

    def action_open(self, path=None):
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self, "Importar proyecto", "", "Excel (*.xlsx *.xls)")
            if not path:
                return
        try:
            self._import_xlsx(path)
        except Exception as e:
            QMessageBox.critical(self, "Error al importar",
                                   f"{type(e).__name__}: {e}")
            return
        self.status.showMessage(f"Importado: {os.path.basename(path)}", 6000)

    def action_save(self):
        if self.df_capital.empty:
            QMessageBox.information(self, "Save",
                                      "No hay nada que guardar.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar como", "", "Excel (*.xlsx)")
        if not path:
            return
        try:
            self._export_xlsx(path)
        except Exception as e:
            QMessageBox.critical(self, "Error al guardar",
                                   f"{type(e).__name__}: {e}")
            return
        self.status.showMessage(f"Guardado: {os.path.basename(path)}", 6000)

    def action_solve(self):
        if self.df_capital.empty:
            QMessageBox.warning(self, "Solve",
                                  "Importá un proyecto primero (Ctrl+O).")
            return
        self._run_solver()

    def action_montecarlo(self):
        if self.df_capital.empty:
            QMessageBox.warning(self, "Monte Carlo",
                                  "Importá un proyecto primero (Ctrl+O).")
            return
        QMessageBox.information(
            self, "Monte Carlo",
            "Para Monte Carlo, ejecutar:\n\n"
            "   python -m montecarlo --input <proyecto.xlsx>\n\n"
            "Integración inline en próxima versión.")

    def action_open_flowsheet(self):
        """Abre el flowsheet editor en un subprocess (no bloqueante)."""
        import subprocess
        try:
            cwd = os.path.dirname(os.path.abspath(__file__))
            entry = os.path.join(cwd, "flowsheet_main_qt.py")
            if not os.path.exists(entry):
                entry = os.path.join(cwd, "flowsheet_qt.py")
            subprocess.Popen([sys.executable, entry], cwd=cwd)
            self.status.showMessage("Flowsheet editor lanzado.", 4000)
        except Exception as e:
            QMessageBox.critical(self, "Error",
                                   f"No se pudo lanzar flowsheet: {e}")

    def action_profile(self):
        """Dialog editar perfil económico activo + HI + γ."""
        try:
            import econ_defaults as ed
        except ImportError:
            QMessageBox.warning(self, "Perfil",
                                  "Módulo econ_defaults.py no disponible.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Perfil económico")
        dlg.resize(420, 220)
        v = QVBoxLayout(dlg)
        form = QFormLayout()
        combo = QComboBox()
        combo.addItems(list(ed.PROFILES.keys()))
        combo.setCurrentText(ed.active_profile())
        form.addRow("Perfil:", combo)
        spin_hi = QDoubleSpinBox()
        spin_hi.setRange(0.0, 1.0); spin_hi.setDecimals(2)
        spin_hi.setSingleStep(0.05)
        spin_hi.setValue(ed.get_heat_integration_factor())
        form.addRow("Heat integration (0-1):", spin_hi)
        spin_g = QDoubleSpinBox()
        spin_g.setRange(1.00, 2.00); spin_g.setDecimals(2)
        spin_g.setSingleStep(0.01)
        spin_g.setValue(ed.get_com_coeffs()["gamma_variable"])
        form.addRow("Turton γ (overhead):", spin_g)
        v.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)
        if dlg.exec() == QDialog.Accepted:
            ed.set_active_profile(combo.currentText())
            ed.set_heat_integration_factor(spin_hi.value())
            ed.set_com_gamma(spin_g.value())
            try:
                import equipment_ports as ep
                ep.refresh_utility_prices()
            except Exception:
                pass
            self._refresh_profile_label()
            self.status.showMessage("Perfil económico actualizado.", 4000)
            if not self.df_capital.empty:
                # Re-correr solver con nuevos parámetros
                self._run_solver()

    # ─── Import / Export ──────────────────────────────────────

    def _import_xlsx(self, path):
        """Lee Project sheet (3 secciones) + opcionales Equipment,
        Streams, Income Statement, Costing Turton."""
        df_raw = pd.read_excel(path, sheet_name="Project", header=None)
        # 3 secciones lado a lado: cols 0-2, 4-6, 8-13
        def _slice(cols):
            df = pd.DataFrame(df_raw.iloc[1:, cols].values,
                               columns=df_raw.iloc[0, cols].values)
            return df.dropna(how='all').reset_index(drop=True)
        self.df_capital  = _slice([0, 1, 2])
        self.df_fixed    = _slice([4, 5, 6])
        self.df_variable = _slice([8, 9, 10, 11, 12, 13])

        xls = pd.ExcelFile(path)
        if "Equipment" in xls.sheet_names:
            self.df_equipment = pd.read_excel(
                path, sheet_name="Equipment").dropna(how='all')
        else:
            self.df_equipment = pd.DataFrame()
        if "Streams" in xls.sheet_names:
            self.df_streams = pd.read_excel(
                path, sheet_name="Streams").dropna(how='all')
        else:
            self.df_streams = pd.DataFrame()
        if "Income Statement" in xls.sheet_names:
            self.df_income = pd.read_excel(
                path, sheet_name="Income Statement").dropna(how='all')
        else:
            self.df_income = pd.DataFrame()
        if "Costing Turton" in xls.sheet_names:
            self.df_costing = pd.read_excel(
                path, sheet_name="Costing Turton",
                header=None,
                names=["Concepto", "Detalle", "Valor"]).dropna(how='all')
        else:
            self.df_costing = pd.DataFrame()

        self.current_file = path
        self.banner.setText(
            f"<b>{os.path.basename(path)}</b>  ·  "
            f"{len(self.df_capital)} capital  ·  "
            f"{len(self.df_fixed)} fixed  ·  "
            f"{len(self.df_variable)} variable  ·  "
            f"{len(self.df_equipment)} equipos  ·  "
            f"{len(self.df_streams)} streams  ·  "
            f"{len(self.df_income)} años P&L"
        )
        self._refresh_tabs()

    def _export_xlsx(self, path):
        with pd.ExcelWriter(path, engine='openpyxl') as w:
            # 3 secciones lado a lado en sheet Project
            from openpyxl import Workbook
            # simpler: usar sheets separadas
            self.df_capital.to_excel(w, sheet_name="Capital",  index=False)
            self.df_fixed.to_excel(w,   sheet_name="Fixed",    index=False)
            self.df_variable.to_excel(w, sheet_name="Variable", index=False)
            if not self.df_equipment.empty:
                self.df_equipment.to_excel(w, sheet_name="Equipment",
                                              index=False)
            if not self.df_streams.empty:
                self.df_streams.to_excel(w, sheet_name="Streams",
                                            index=False)
            if not self.df_income.empty:
                self.df_income.to_excel(w, sheet_name="Income Statement",
                                           index=False)
            if not self.df_costing.empty:
                self.df_costing.to_excel(w, sheet_name="Costing Turton",
                                            index=False)

    # ─── Refresh tabs ─────────────────────────────────────────

    def _refresh_tabs(self):
        # Capital + Fixed: editables las columnas Value (un solo número)
        df_to_table(self._table_for_tab("Capital Costs"),
                     self.df_capital, number_cols={"Value"})
        self._make_editable(self._table_for_tab("Capital Costs"),
                              self.df_capital, ["Value"],
                              self._on_capital_edit)
        df_to_table(self._table_for_tab("Fixed Op. Costs"),
                     self.df_fixed, number_cols={"Value"})
        self._make_editable(self._table_for_tab("Fixed Op. Costs"),
                              self.df_fixed, ["Value"],
                              self._on_fixed_edit)
        # Variable: editables flowrate + price usd/units
        df_to_table(self._table_for_tab("Variable Op. Costs"),
                     self.df_variable,
                     number_cols={"flowrate", "price usd/units"})
        self._make_editable(self._table_for_tab("Variable Op. Costs"),
                              self.df_variable,
                              ["flowrate", "price usd/units"],
                              self._on_variable_edit)
        # Read-only: equipos, streams, costing, income
        df_to_table(self._table_for_tab("Equipment"),
                     self.df_equipment)
        df_to_table(self._table_for_tab("Streams"),
                     self.df_streams)
        df_to_table(self._table_for_tab("Costing Turton"),
                     self.df_costing)
        df_to_table(self._table_for_tab("Income Statement"),
                     self.df_income)

    def _make_editable(self, table, df, editable_cols, on_change):
        """Marca las columnas en `editable_cols` como editables.
        Conecta `cellChanged` a `on_change(row, col, new_value)`."""
        if table is None or df is None or df.empty:
            return
        cols = list(df.columns)
        for j, col in enumerate(cols):
            if col not in editable_cols:
                continue
            for i in range(table.rowCount()):
                item = table.item(i, j)
                if item is not None:
                    item.setFlags(item.flags() | Qt.ItemIsEditable)
        # Conectar señal — desconectar primero para no acumular
        try:
            table.cellChanged.disconnect()
        except Exception:
            pass
        table.cellChanged.connect(
            lambda r, c, t=table, d=df, cl=cols, cb=on_change:
                self._handle_cell_changed(t, d, cl, r, c, cb))

    def _handle_cell_changed(self, table, df, cols, row, col, cb):
        item = table.item(row, col)
        if item is None:
            return
        col_name = cols[col]
        raw = item.text().strip().replace(",", "")
        try:
            new_val = float(raw)
        except ValueError:
            # revertir al valor original
            old = df.iat[row, col]
            table.blockSignals(True)
            item.setText(f"{old:,.2f}" if isinstance(old, (int, float))
                          else str(old))
            table.blockSignals(False)
            QMessageBox.warning(self, "Valor inválido",
                                  f"'{raw}' no es número.")
            return
        cb(row, col_name, new_val)

    def _on_capital_edit(self, row, col, new_val):
        self.df_capital.iat[row, list(self.df_capital.columns).index(col)] = new_val
        self.status.showMessage(
            f"Capital fila {row+1} {col} actualizado → {new_val:,.2f}", 4000)

    def _on_fixed_edit(self, row, col, new_val):
        self.df_fixed.iat[row, list(self.df_fixed.columns).index(col)] = new_val
        self.status.showMessage(
            f"Fixed fila {row+1} {col} actualizado → {new_val:,.2f}", 4000)

    def _on_variable_edit(self, row, col, new_val):
        self.df_variable.iat[row,
            list(self.df_variable.columns).index(col)] = new_val
        var_name = str(self.df_variable.iat[row, 0])
        self.status.showMessage(
            f"{var_name}: {col} = {new_val:,.2f}.  Solve para recalcular.",
            6000)

    # ─── Solver económico ────────────────────────────────────

    def _run_solver(self):
        """Re-corre el costing Turton + profitability con los valores
        actuales y actualiza Results tab + Costing Turton tab."""
        try:
            import equipment_costs as ec
        except Exception as e:
            QMessageBox.critical(self, "Solver",
                                   f"Falta equipment_costs: {e}")
            return
        # CRM, CUT, CWT, REV
        crm = cut = cwt = revenue = 0.0
        for _, row in self.df_variable.iterrows():
            stream = str(row.get("stream", "")).strip()
            flow   = float(row.get("flowrate", 0) or 0)
            price  = float(row.get("price usd/units", 0) or 0)
            cost   = flow * price
            if stream == "Raw Materials":  crm += cost
            elif stream == "Utilities":    cut += cost
            elif stream in ("Waste / Byproduct", "Waste Streams"):
                if price < 0:    cwt += abs(cost)
                elif price > 0:  revenue += cost
            elif stream == "Key Products": revenue += cost
        # COL desde fixed
        col = 0.0
        if not self.df_fixed.empty and "Concept" in self.df_fixed.columns:
            mask = self.df_fixed["Concept"].astype(str).str.strip() == "Labor"
            if mask.any():
                col = float(self.df_fixed.loc[mask, "Value"].iloc[0] or 0)
        # FCI desde capital row 0
        fci = 0.0
        if not self.df_capital.empty:
            isbl_val = float(self.df_capital.iat[0, 2] or 0)
            fci = isbl_val * 1e6 * 1.45    # rough multiplier OSBL+ENG+CONT

        com  = ec.cost_of_manufacture(FCI_usd=fci, COL_usd=col,
                                         CUT_usd=cut, CRM_usd=crm,
                                         CWT_usd=cwt)
        prof = ec.profitability_indicators(
            revenue_usd_yr=revenue, com_d_usd_yr=com["COM_d"],
            fci_usd=fci)

        # ── Income Statement año por año (tabla detallada) ──
        # Usa Revenue - CRM - CUT - CWT - COL - Depreciation directo
        # (sin los multipliers Turton 0.180/2.73/1.23).  Es el desglose
        # "líneas" para visualizar dónde está el dinero.
        try:
            import flowsheet_export as fexp
            income_rows = fexp.compute_income_statement(
                revenue_usd_yr=revenue, crm=crm, cut=cut,
                cwt=cwt, col=col, fci_usd=fci,
            )
            self.df_income = pd.DataFrame(income_rows)
            df_to_table(self._table_for_tab("Income Statement"),
                         self.df_income)
        except Exception as e:
            self.status.showMessage(f"⚠ income stmt no actualizado: {e}", 6000)

        # ── Chart de cash flow CONSISTENTE CON NPV TURTON ──
        # Para que el NPV del plot coincida con el del tab Results
        # (que usa profitability_indicators con COM_d Turton),
        # construimos un cash flow constante = prof["Cash flow"]
        # para todos los años de operación, año 0 = -FCI.
        try:
            import econ_defaults as _ed
            fin  = _ed.get_financial()
            disc = fin["discount_rate"]
            yrs  = fin["project_years"]
        except Exception:
            disc, yrs = 0.10, 10
        cf_const = prof["Cash flow"]
        cf_years  = list(range(0, yrs + 1))
        cf_values = [-fci] + [cf_const] * yrs
        cum = []
        running = 0.0
        for yr, cf in zip(cf_years, cf_values):
            pv = cf / ((1 + disc) ** yr)
            running += pv
            cum.append(running)
        # Payback descontado (cuando cum cruza 0)
        pbp_disc = None
        for i in range(1, len(cum)):
            if cum[i-1] < 0 <= cum[i]:
                pbp_disc = (cf_years[i-1] +
                              (0 - cum[i-1]) / (cum[i] - cum[i-1]) *
                              (cf_years[i] - cf_years[i-1]))
                break
        self._update_chart(cf_years, cf_values, cum,
                             payback_yr=pbp_disc,
                             npv_final=cum[-1])

        # Build Results table
        npv  = prof["NPV"]
        pbp  = prof["Payback simple"]
        irr  = prof["IRR %"]
        rows = [
            ("FCI",              f"{fci:,.0f} USD",            ""),
            ("Revenue",          f"{revenue:,.0f} USD/yr",     ""),
            ("CRM (Raw Mat)",    f"{crm:,.0f} USD/yr",         ""),
            ("CUT (Utilities)",  f"{cut:,.0f} USD/yr",         ""),
            ("CWT (Waste)",      f"{cwt:,.0f} USD/yr",         ""),
            ("COL (Labor)",      f"{col:,.0f} USD/yr",         ""),
            ("",                 "",                            ""),
            ("COM_d Turton 8.2", f"{com['COM_d']:,.0f} USD/yr", ""),
            ("Gross profit",     f"{prof['Gross profit']:,.0f} USD/yr",
             "✓" if prof['Gross profit'] > 0 else "✗"),
            ("Net profit",       f"{prof['Net profit']:,.0f} USD/yr",
             "✓" if prof['Net profit'] > 0 else "✗"),
            ("Cash flow / yr",   f"{prof['Cash flow']:,.0f} USD/yr",   ""),
            ("",                 "",                            ""),
            ("NPV (10yr, 10%)",  f"{npv:,.0f} USD",
             "✓" if npv > 0 else "✗"),
            ("Payback simple",   f"{pbp:.2f} años" if pbp != float('inf') else "n/a",
             "✓" if pbp != float('inf') and pbp < 7 else "⚠"),
            ("IRR",              f"{irr:.1f} %" if irr else "n/a",
             "✓" if irr and irr > 15 else "⚠"),
        ]
        df_results = pd.DataFrame(rows, columns=["Concepto", "Valor", ""])
        table_r = self._table_for_tab("Results")
        df_to_table(table_r, df_results)
        # Color rows según verde/rojo
        for i, (c, v, flag) in enumerate(rows):
            if flag == "✓":
                table_r.item(i, 2).setForeground(Qt.darkGreen)
            elif flag == "✗":
                table_r.item(i, 2).setForeground(Qt.red)
            elif flag == "⚠":
                table_r.item(i, 2).setForeground(Qt.darkYellow)
        self.tabs.setCurrentIndex(self.tabs.indexOf(
            self._table_for_tab("Results").parent()))
        self.status.showMessage(
            f"Solve OK.  NPV={npv/1e6:+.1f} MM USD   "
            f"Payback={pbp:.1f} yr   IRR={irr:.1f}%" if irr
            else f"NPV={npv/1e6:+.1f} MM USD",
            10000)


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = AnaMainWindow()
    win.show()
    # CLI: --import path.xlsx
    if "--import" in sys.argv:
        idx = sys.argv.index("--import")
        if idx + 1 < len(sys.argv):
            path = sys.argv[idx + 1]
            if os.path.exists(path):
                win.action_open(path)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
