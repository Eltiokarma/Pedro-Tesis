"""
FLOWSHEET QT — port de flowsheet_ui.py a PySide6 + QGraphicsView.

OBJETIVO

  Misma funcionalidad que el editor Tk, pero con un canvas vectorial
  profesional:
    · zoom anclado al cursor (transform matrix nativa)
    · pan con middle-button drag o space + drag
    · antialiasing nativo
    · selección Qt nativa (rubber band, multi-select)
    · drag-and-drop, undo/redo a futuro

ESTADO DE LA MIGRACIÓN

  Phase A (este commit) — SCAFFOLD funcional:
    ✓ QGraphicsScene con grid de fondo
    ✓ BlockItem (rect + texto + sub-texto + puertos)
    ✓ StreamItem (polyline ortogonal + label con fondo)
    ✓ Zoom Ctrl+wheel, pan middle-drag, scrollbars automáticas
    ✓ Drag bloques con snap a grid
    ✓ Library tree (QTreeWidget) + 'Add to canvas'
    ✓ Toolbar: New / Open / Save / Examples / Solve / Calcular
    ✓ Property panel con info del item seleccionado
    ✓ Reusa equipment_costs, equipment_ports, flowsheet_solver

  Phase B (próximo commit) — DIALOGS:
    · BlockEditDialog Qt (con duty + heat_source dropdown)
    · StreamEditDialog Qt (con T + Cp + role + ports)
    · OpexExtrasDialog Qt

  Phase C — INTEGRACIONES:
    · Conexión por click-puerto-click sobre el canvas
    · Welcome Qt (port de main.py)
    · Launch analysis económico via subprocess.Popen (sigue Tk)

DEPENDENCIA
    PySide6 (LGPL).  Instalar con:
        pip install PySide6
"""

import sys
import os
import json
import subprocess
from typing import List

from PySide6.QtCore import (
    Qt, QRectF, QPointF, QLineF, QSize,
    Signal,
)
from PySide6.QtGui import (
    QAction, QPen, QBrush, QColor, QPainter, QFont, QPainterPath,
    QPolygonF, QPainterPathStroker, QFontMetrics, QKeySequence,
    QTransform, QIcon,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsScene, QGraphicsView,
    QGraphicsItem, QGraphicsRectItem, QGraphicsPathItem, QGraphicsPolygonItem,
    QGraphicsTextItem, QGraphicsEllipseItem, QGraphicsLineItem,
    QGraphicsItemGroup, QGraphicsSimpleTextItem,
    QToolBar, QStatusBar, QDockWidget, QTreeWidget, QTreeWidgetItem,
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QInputDialog, QMenu, QMenuBar,
    QSplitter, QTextEdit, QSizePolicy, QStyle,
    QDialog, QDialogButtonBox, QLineEdit, QSpinBox, QDoubleSpinBox,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox,
    QGroupBox, QGraphicsSceneContextMenuEvent, QToolButton,
)
from PySide6.QtGui import QUndoStack, QUndoCommand

import equipment_costs as eq
import equipment_ports as ep
import equipment_icons as eicon
import pfd_symbols as pfd
import pfd_fonts

# ---- matplotlib opcional (perfil de reactor PFR/batch + barras CSTR) ----
# Mismo patrón que results_ui.py pero con backend QtAgg en vez de TkAgg.
# Si el entorno no tiene matplotlib o le falta el binding Qt, el panel
# de perfil degrada con un aviso en vez de crashear.
try:
    import matplotlib
    matplotlib.use("QtAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_qtagg import FigureCanvas as _MplCanvas
    _MPL_OK = True
except Exception:
    _MPL_OK = False
import flowsheet_solver as fsolv
import flowsheet_export as fexp
import flowsheet_validation as fval
import flowsheet_units as funits
from flowsheet_model import (
    Block, Stream, Flowsheet,
    STREAM_ROLE_COLORS, STREAM_ROLE_COLORS_SEL,
    BLOCK_W, BLOCK_H, GRID_STEP, ROUTING_GAP,
)


# ======================================================
# CACHE DE PIXMAPS RENDERIZADOS DESDE SVG
# ======================================================
# QGraphicsSvgItem demostró ser frágil en algunos entornos:
# requiere QtSvgWidgets, a veces no aplica el viewBox y queda
# con boundingRect efectivo cero (resultado: cuadrado vacío).
#
# Solución: renderizar cada SVG a un QPixmap (raster) UNA VEZ
# a 2× resolución (HiDPI-friendly), y usar QGraphicsPixmapItem
# para mostrarlo.  El item queda al tamaño correcto siempre.

_SVG_PIXMAPS   = {}        # (eq_type, w, h) → QPixmap renderizado
_SVG_AVAILABLE = None      # lazy: ¿PySide6.QtSvg disponible?


def _get_svg_pixmap(eq_type, width, height, svg_str=None):
    """Renderiza un SVG a un QPixmap de tamaño width×height (con
    supersampling 2× para nitidez).  Cache compartido.

    Si `svg_str` se pasa, se usa directamente (sirve para el catálogo
    pfd_symbols, donde el SVG ya está armado).  Si no, se busca via
    equipment_icons.get_icon_svg(eq_type) — legacy.

    Devuelve None si:
      · no hay SVG, o
      · PySide6.QtSvg no está disponible, o
      · el SVG no parsea.
    """
    global _SVG_AVAILABLE
    if _SVG_AVAILABLE is False:
        return None

    # cache key incluye un hash chico del svg_str para que distintas
    # versiones (legacy vs pfd_symbols) no choquen.
    key_suffix = hash(svg_str) if svg_str is not None else "legacy"
    cache_key = (eq_type, width, height, key_suffix)
    if cache_key in _SVG_PIXMAPS:
        return _SVG_PIXMAPS[cache_key]

    if svg_str is None:
        svg_str = eicon.get_icon_svg(eq_type)
    if svg_str is None:
        return None

    try:
        from PySide6.QtSvg  import QSvgRenderer
        from PySide6.QtCore import QByteArray
        from PySide6.QtGui  import QImage, QPainter, QPixmap
        _SVG_AVAILABLE = True
    except ImportError:
        _SVG_AVAILABLE = False
        return None

    renderer = QSvgRenderer(QByteArray(svg_str.encode("utf-8")))
    if not renderer.isValid():
        return None

    # supersampling 2× → render más nítido a HiDPI
    sup = 2
    img = QImage(width * sup, height * sup, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    # IMPORTANTE: pasar target_rect explícito que llena toda la imagen.
    # Sin esto, QSvgRenderer usa defaultSize() (de los atrs width/height
    # del <svg>) que mide en unidades de escena, no pixels — y el SVG
    # se renderiza sólo en la esquina superior izquierda del painter,
    # dejando 3/4 de la imagen transparente.
    from PySide6.QtCore import QRectF
    renderer.render(painter, QRectF(0, 0, img.width(), img.height()))
    painter.end()

    pixmap = QPixmap.fromImage(img)
    pixmap.setDevicePixelRatio(sup)   # decir a Qt que es 2× DPI
    _SVG_PIXMAPS[cache_key] = pixmap
    return pixmap


# ======================================================
# COLORES (paleta Material lite)
# ======================================================

COLOR_CANVAS_BG     = QColor("#fbfaf6")   # papel de dibujo (warm off-white)
COLOR_GRID          = QColor(13, 13, 13, 18)   # negro alpha=18/255 (~7%)
COLOR_BLOCK_FILL    = QColor("#ffffff")
COLOR_BLOCK_BORDER  = QColor("#5c6bc0")
COLOR_BLOCK_BORDER_SEL = QColor("#283593")
COLOR_BLOCK_TEXT    = QColor("#1a1a1a")
COLOR_BLOCK_SUB     = QColor("#6c6c70")
COLOR_PORT_FREE     = QColor("#bbbbbb")
COLOR_PORT_CONN     = QColor("#1565c0")
COLOR_LABEL_BG      = QColor(255, 255, 255, 220)

# ---- Status visual (semáforo del solver) ----
# Cuatro estados que pinta cada bloque/stream según el último solve.
# Coordinado con SolverResult.{block_status, stream_status, overall_status}.
COLOR_STATUS_OK      = QColor("#2e7d32")   # verde — balance OK
COLOR_STATUS_WARN    = QColor("#f9a825")   # ámbar — warnings
COLOR_STATUS_ERROR   = QColor("#c62828")   # rojo — error / desbalance
COLOR_STATUS_UNRUN   = QColor("#1976d2")   # azul — no ejecutado / stale
COLOR_STATUS_DIRTY   = QColor("#7b1fa2")   # violeta — flowsheet editado
                                            # post-solve (datos stale)

# Mapeo status string → color
STATUS_COLORS = {
    "ok":      COLOR_STATUS_OK,
    "warning": COLOR_STATUS_WARN,
    "error":   COLOR_STATUS_ERROR,
    "unrun":   COLOR_STATUS_UNRUN,
    "stale":   COLOR_STATUS_DIRTY,
    "empty":   COLOR_STATUS_UNRUN,
}

# Iconos texto para indicar status global en la barra
STATUS_ICONS = {
    "ok":      "✓",
    "warning": "⚠",
    "error":   "✗",
    "unrun":   "●",
    "stale":   "◌",
    "empty":   "○",
}

STATUS_LABELS = {
    "ok":      "Balance OK",
    "warning": "Balance con warnings",
    "error":   "Errores en el balance",
    "unrun":   "Sin ejecutar (apretá F5)",
    "stale":   "Datos stale — re-ejecutar (F5)",
    "empty":   "Diagrama vacío",
}


# ======================================================
# UNDO / REDO — SnapshotCommand
# ======================================================
# Approach pragmático: cada acción que modifica el flowsheet
# (mover bloque, agregar/borrar, editar dialog, etc.) push un
# SnapshotCommand que recuerda el estado del fs ANTES y DESPUÉS.
# Undo/redo restauran el snapshot completo.
#
# Costo: ~1 KB por command (fs.to_dict() es JSON-serializable
# pequeño).  Con 100 acciones = ~100 KB, trivial.
#
# Trade-off: simple y robusto, pero más caro en memoria que
# tener QUndoCommands específicos (MoveBlockCommand,
# AddStreamCommand, etc.).  Para el tamaño de flowsheets típicos
# (decenas de bloques) este enfoque está OK.

class SnapshotCommand(QUndoCommand):
    """Reemplaza el flowsheet entero con un snapshot anterior/posterior."""

    def __init__(self, text, editor, before_dict, after_dict):
        super().__init__(text)
        self.editor = editor
        self.before = before_dict
        self.after  = after_dict
        # bandera para evitar el redo() inicial cuando el command
        # se pushea (el editor ya tiene el estado 'after')
        self._first_push = True

    def redo(self):
        if self._first_push:
            self._first_push = False
            return                  # el state ya está aplicado
        self.editor._apply_snapshot(self.after)

    def undo(self):
        self.editor._apply_snapshot(self.before)


# ======================================================
# DIALOGS DE EDICIÓN
# ======================================================

class BlockEditDialog(QDialog):
    """Editor del bloque: tag ISA, S, n, duty, heat_source."""

    def __init__(self, parent, block: Block):
        super().__init__(parent)
        self.block = block
        self.setWindowTitle(f"Editar equipo — {block.name}")
        self.resize(480, 460)

        spec = eq.EQUIPMENT_DATA.get(block.eq_type, {})

        layout = QFormLayout(self)

        # info read-only
        lbl_type = QLabel(block.eq_type)
        lbl_type.setStyleSheet("color: #555;")
        layout.addRow("Tipo de equipo:", lbl_type)

        # nombre
        self.name_edit = QLineEdit(block.name)
        layout.addRow("Tag (ISA):", self.name_edit)

        # S
        self.s_edit = QDoubleSpinBox()
        self.s_edit.setRange(0.001, 1e9)
        self.s_edit.setDecimals(3)
        self.s_edit.setSingleStep(1.0)
        self.s_edit.setValue(block.S)
        s_label = f"S ({spec.get('S_unit', '?')}):"
        layout.addRow(s_label, self.s_edit)

        # rango válido como hint
        smin = spec.get("S_min")
        smax = spec.get("S_max")
        if smin is not None and smax is not None:
            hint = QLabel(f"Rango válido Turton: [{smin:g} – {smax:g}] {spec.get('S_unit','')}")
            hint.setStyleSheet("color: #888; font-size: 8pt;")
            layout.addRow("", hint)

        # n
        self.n_edit = QSpinBox()
        self.n_edit.setRange(1, 100)
        self.n_edit.setValue(block.n)
        layout.addRow("N° unidades en paralelo:", self.n_edit)

        # ---- duty ----
        gb_duty = QGroupBox("Balance de energía")
        gb_layout = QFormLayout(gb_duty)
        self.duty_edit = QDoubleSpinBox()
        self.duty_edit.setRange(-1e7, 1e7)
        self.duty_edit.setDecimals(1)
        self.duty_edit.setSingleStep(10.0)
        self.duty_edit.setValue(block.duty)
        self.duty_lock = QCheckBox("🔒")
        self.duty_lock.setToolTip(
            "Marcar para FIJAR el duty del bloque (sudoku spec).\n"
            "Sin marcar: el solver lo computa desde balance de energía\n"
            "de las T's del in/out."
        )
        self.duty_lock.setChecked(getattr(block, "duty_locked", False))
        d_row = QWidget(); d_lay = QHBoxLayout(d_row)
        d_lay.setContentsMargins(0,0,0,0)
        d_lay.addWidget(self.duty_lock); d_lay.addWidget(self.duty_edit, 1)
        gb_layout.addRow("Duty (kW):", d_row)

        hint_duty = QLabel(
            ">0 entrega calor (heater, reboiler)\n"
            "<0 extrae calor (cooler, condenser)\n"
            "=0 adiabático o no declarado"
        )
        hint_duty.setStyleSheet("color: #888; font-size: 8pt;")
        gb_layout.addRow("", hint_duty)

        # heat source
        self.heat_combo = QComboBox()
        self.heat_combo.addItem("(auto)")
        for k in ep.UTILITIES.keys():
            self.heat_combo.addItem(k)
        cur = block.heat_source or "(auto)"
        idx = self.heat_combo.findText(cur)
        if idx >= 0:
            self.heat_combo.setCurrentIndex(idx)
        gb_layout.addRow("Utility:", self.heat_combo)

        # heat_of_reaction (solo visible para reactores)
        self.hor_edit = QDoubleSpinBox()
        self.hor_edit.setRange(-1e5, 1e5)
        self.hor_edit.setDecimals(1)
        self.hor_edit.setSingleStep(50.0)
        self.hor_edit.setValue(block.heat_of_reaction)
        self.hor_label = QLabel("Calor de reacción (kJ/kg input):")
        gb_layout.addRow(self.hor_label, self.hor_edit)
        hint_hor = QLabel(
            "Sólo aplica a reactores.\n"
            ">0 endotérmica · <0 exotérmica · =0 sin reacción\n"
            "Ejemplo Methanol: CO+2H₂→CH₃OH, -200 kJ/kg input syngas"
        )
        hint_hor.setStyleSheet("color: #888; font-size: 8pt;")
        gb_layout.addRow("", hint_hor)
        # ocultar si NO es reactor
        is_reactor = "Reactor" in block.eq_type
        self.hor_label.setVisible(is_reactor)
        self.hor_edit.setVisible(is_reactor)
        hint_hor.setVisible(is_reactor)

        # ---- Overrides de U y ΔTlm para sizing de HX ----
        # Solo visible si eq_type es de la categoría Heat exchangers.
        # 0 = "usar valor típico de tabla" (se persiste como None).
        try:
            import equipment_costs as _ec_hx
            _hx_cat = (_ec_hx.EQUIPMENT_DATA.get(block.eq_type, {})
                                .get("categoria") == "Heat exchangers")
        except Exception:
            _hx_cat = False
        self.u_over_edit = QDoubleSpinBox()
        self.u_over_edit.setRange(0.0, 5000.0)
        self.u_over_edit.setDecimals(1)
        self.u_over_edit.setSingleStep(50.0)
        self.u_over_edit.setSuffix(" W/m²·K")
        self.u_over_edit.setValue(float(getattr(block, "U_override", None) or 0.0))
        self.u_over_label = QLabel("U override:")
        gb_layout.addRow(self.u_over_label, self.u_over_edit)
        self.dtlm_over_edit = QDoubleSpinBox()
        self.dtlm_over_edit.setRange(0.0, 500.0)
        self.dtlm_over_edit.setDecimals(2)
        self.dtlm_over_edit.setSingleStep(1.0)
        self.dtlm_over_edit.setSuffix(" K")
        self.dtlm_over_edit.setValue(float(getattr(block, "dtlm_override", None) or 0.0))
        self.dtlm_over_label = QLabel("ΔT_lm override:")
        gb_layout.addRow(self.dtlm_over_label, self.dtlm_over_edit)
        hint_uov = QLabel(
            "Solo aplica a Heat exchangers.  0 = usar valor típico\n"
            "de tabla (U_TYPICAL / DTLM_TYPICAL).  Útil para condensación\n"
            "de vapor puro (U~1500), aceite térmico (U~200), close-approach."
        )
        hint_uov.setStyleSheet("color: #888; font-size: 8pt;")
        gb_layout.addRow("", hint_uov)
        for _w in (self.u_over_label, self.u_over_edit,
                    self.dtlm_over_label, self.dtlm_over_edit, hint_uov):
            _w.setVisible(_hx_cat)

        # ---- Columna de destilación: parámetros de sizing físico ----
        # Solo visible si eq_type == 'Tower (column shell)'.
        # 0 = "usar default canónico de econ_defaults.COLUMN_DEFAULTS".
        is_tower = "Tower" in (block.eq_type or "")
        self.gb_col_phys = QGroupBox("Columna — sizing físico")
        self.gb_col_phys.setVisible(is_tower)
        col_layout = QFormLayout(self.gb_col_phys)

        self.col_pack_type = QComboBox()
        self.col_pack_type.addItem("Platos (default)", "")
        self.col_pack_type.addItem("Empaque random", "random")
        self.col_pack_type.addItem("Empaque estructurado", "structured")
        _ptype = getattr(block, "packing_type", "") or ""
        for _i in range(self.col_pack_type.count()):
            if self.col_pack_type.itemData(_i) == _ptype:
                self.col_pack_type.setCurrentIndex(_i); break
        col_layout.addRow("Tipo interno:", self.col_pack_type)

        self.col_tray_space = QDoubleSpinBox()
        self.col_tray_space.setRange(0.0, 2.0); self.col_tray_space.setDecimals(3)
        self.col_tray_space.setSingleStep(0.05); self.col_tray_space.setSuffix(" m")
        self.col_tray_space.setValue(float(getattr(block, "tray_spacing_m", None) or 0.0))
        col_layout.addRow("Tray spacing:", self.col_tray_space)

        self.col_K_sb = QDoubleSpinBox()
        self.col_K_sb.setRange(0.0, 0.5); self.col_K_sb.setDecimals(4)
        self.col_K_sb.setSingleStep(0.01); self.col_K_sb.setSuffix(" m/s")
        self.col_K_sb.setValue(float(getattr(block, "K_souders_brown", None) or 0.0))
        col_layout.addRow("K Souders-Brown:", self.col_K_sb)

        self.col_head = QDoubleSpinBox()
        self.col_head.setRange(0.0, 20.0); self.col_head.setDecimals(2)
        self.col_head.setSingleStep(0.5); self.col_head.setSuffix(" m")
        self.col_head.setValue(float(getattr(block, "column_head_height_m", None) or 0.0))
        col_layout.addRow("Head height:", self.col_head)

        self.col_tray_eff = QDoubleSpinBox()
        self.col_tray_eff.setRange(0.0, 1.0); self.col_tray_eff.setDecimals(3)
        self.col_tray_eff.setSingleStep(0.05)
        self.col_tray_eff.setValue(float(getattr(block, "tray_efficiency", None) or 0.0))
        col_layout.addRow("Tray efficiency:", self.col_tray_eff)

        self.col_HETP = QDoubleSpinBox()
        self.col_HETP.setRange(0.0, 2.0); self.col_HETP.setDecimals(3)
        self.col_HETP.setSingleStep(0.05); self.col_HETP.setSuffix(" m")
        self.col_HETP.setValue(float(getattr(block, "HETP_m", None) or 0.0))
        col_layout.addRow("HETP (empaque):", self.col_HETP)

        hint_col = QLabel(
            "0 = usar default canónico de econ_defaults.COLUMN_DEFAULTS\n"
            "Defaults: tray_spacing 0.6m (24\"), K=0.06, head 3m,\n"
            "tray_eff 1.0, HETP 0.5m.  Para empaque estructurado HETP~0.3m."
        )
        hint_col.setStyleSheet("color: #888; font-size: 8pt;")
        col_layout.addRow("", hint_col)
        layout.addRow(self.gb_col_phys)

        layout.addRow(gb_duty)

        # ---- Reactor (Capas 4 y 5) ----
        # Solo visible si es Reactor.  Permite seleccionar reacciones
        # del catálogo + modo de solver (equilibrium / pfr / cstr).
        self.gb_eq = QGroupBox("Reactor con reacciones (Capas 4 y 5)")
        self.gb_eq.setVisible(is_reactor)
        eq_layout = QFormLayout(self.gb_eq)

        # Modo del reactor
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("equilibrium  —  Newton Gibbs (Capa 4)", "equilibrium")
        self.mode_combo.addItem("pfr          —  RK4 cinética (Capa 5)", "pfr")
        self.mode_combo.addItem("cstr         —  Newton cinética (Capa 5)", "cstr")
        self.mode_combo.addItem("batch        —  RK4 dN/dt, V cte (Capa 5)", "batch")
        current_mode = getattr(block, "reactor_mode", "equilibrium") or "equilibrium"
        idx = self.mode_combo.findData(current_mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
        eq_layout.addRow("Modo:", self.mode_combo)
        hint_mode = QLabel(
            "• equilibrium: minimización Gibbs multi-reacción\n"
            "  (ignora volumen, recomendado si V grande o cinética rápida)\n"
            "• pfr: flujo pistón con RK4 (requiere V > 0)\n"
            "• cstr: tanque agitado, robusto para cinéticas stiff (requiere V > 0)\n"
            "• batch: RK4 dN/dt, V cte, P emergente (requiere V > 0 + tiempo de tanda)"
        )
        hint_mode.setStyleSheet("color: #888; font-size: 8pt;")
        eq_layout.addRow("", hint_mode)

        # T_op
        self.t_op_edit = QDoubleSpinBox()
        self.t_op_edit.setRange(0.0, 3000.0)
        self.t_op_edit.setDecimals(1)
        self.t_op_edit.setSingleStep(25.0)
        self.t_op_edit.setSuffix(" K")
        self.t_op_edit.setValue(getattr(block, "T_op_K", 0.0))
        eq_layout.addRow("T operación:", self.t_op_edit)
        hint_t = QLabel("0 = usa T promedio del input.")
        hint_t.setStyleSheet("color: #888; font-size: 8pt;")
        eq_layout.addRow("", hint_t)

        # P_op
        self.p_op_edit = QDoubleSpinBox()
        self.p_op_edit.setRange(0.001, 1000.0)
        self.p_op_edit.setDecimals(2)
        self.p_op_edit.setSingleStep(1.0)
        self.p_op_edit.setSuffix(" bar")
        self.p_op_edit.setValue(getattr(block, "P_op_bar", 1.0))
        eq_layout.addRow("P operación:", self.p_op_edit)

        # Volumen del reactor (solo visible si mode != equilibrium)
        self.vol_edit = QDoubleSpinBox()
        self.vol_edit.setRange(0.0, 1e7)
        self.vol_edit.setDecimals(2)
        self.vol_edit.setSingleStep(10.0)
        self.vol_edit.setSuffix(" L")
        self.vol_edit.setValue(getattr(block, "reactor_volume_L", 0.0))
        self.vol_label_widget = QLabel("Volumen reactor:")
        eq_layout.addRow(self.vol_label_widget, self.vol_edit)
        hint_vol = QLabel(
            "Volumen interno del reactor en litros.\n"
            "Solo aplica en modo PFR o CSTR (ignorado en equilibrium)."
        )
        hint_vol.setStyleSheet("color: #888; font-size: 8pt;")
        eq_layout.addRow("", hint_vol)
        self._vol_hint_widget = hint_vol

        # Tiempo de tanda (solo visible en modo batch)
        self.batch_time = QDoubleSpinBox()
        self.batch_time.setRange(1.0, 1e7)
        self.batch_time.setDecimals(0)
        self.batch_time.setSuffix(" s")
        self.batch_time.setValue(getattr(block, "batch_time_s", 3600.0))
        self.batch_time.setToolTip(
            "Tiempo de tanda (solo modo batch).\n"
            "El solver integra dN/dt de 0 a este tiempo, V constante."
        )
        self.batch_time_label = QLabel("Tiempo de tanda:")
        eq_layout.addRow(self.batch_time_label, self.batch_time)

        # Toggle de visibilidad del volumen / batch_time según modo
        def _on_mode_change():
            m = self.mode_combo.currentData()
            show_vol = (m in ("pfr", "cstr", "batch"))
            show_batch = (m == "batch")
            self.vol_label_widget.setVisible(show_vol)
            self.vol_edit.setVisible(show_vol)
            self._vol_hint_widget.setVisible(show_vol)
            self.batch_time_label.setVisible(show_batch)
            self.batch_time.setVisible(show_batch)
        self.mode_combo.currentIndexChanged.connect(lambda _: _on_mode_change())
        _on_mode_change()

        # Lista de reacciones (multi-check)
        from PySide6.QtWidgets import QListWidget, QListWidgetItem
        self.rxn_list = QListWidget()
        self.rxn_list.setSelectionMode(QListWidget.NoSelection)
        self.rxn_list.setMaximumHeight(180)
        try:
            import reactions_db as _rdb
            current = set(getattr(block, "reactions", []) or [])
            for rid in _rdb.list_ids():
                rxn = _rdb.get(rid)
                label = f"{rid} — {rxn.name}"
                item = QListWidgetItem(label)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if rid in current else Qt.Unchecked)
                if not rxn.derivable_capa3:
                    # R022-R025: termo no validable contra Capa 3, sin Keq formal.
                    item.setToolTip(rxn.comments[:200] if rxn.comments else
                                     "Reacción sin Van't Hoff — no usable en este reactor.")
                    item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                else:
                    item.setToolTip(f"Categoría: {rxn.category}\n"
                                     f"Δν={rxn.delta_nu}, fase={rxn.phase_global}\n"
                                     f"Rango T válido: {rxn.T_min_K:.0f}-{rxn.T_max_K:.0f} K\n"
                                     f"ΔH(298) = {rxn.dh_rxn_298_kJ_mol or 0:+.1f} kJ/mol")
                self.rxn_list.addItem(item)
        except Exception as e:
            self.rxn_list.addItem(f"[error cargando reactions_db: {e}]")
        eq_layout.addRow("Reacciones:", self.rxn_list)
        hint_rxn = QLabel(
            "Marcá las reacciones que ocurren en este reactor.\n"
            "Si hay ≥1: el solver computa composición de salida\n"
            "y heat_of_reaction automáticamente (oculta el manual\n"
            "de arriba). Si vacío: modo manual con kJ/kg declarado."
        )
        hint_rxn.setStyleSheet("color: #888; font-size: 8pt;")
        eq_layout.addRow("", hint_rxn)

        # ---- Reacciones CUSTOM in-memory (Hallazgo 1) ----
        # Una QListWidget mostrando las custom existentes + botón para
        # abrir el sub-diálogo CustomReactionDialog.
        self._custom_rxns_data = list(getattr(block, "custom_reactions", []) or [])
        self.custom_rxn_list = QListWidget()
        self.custom_rxn_list.setSelectionMode(QListWidget.SingleSelection)
        self.custom_rxn_list.setMaximumHeight(80)
        self._refresh_custom_rxns_list()
        eq_layout.addRow("Custom (sin DB):", self.custom_rxn_list)
        btn_layout = QHBoxLayout()
        btn_add_custom = QPushButton("+ Reacción custom…")
        btn_add_custom.clicked.connect(self._on_add_custom_rxn)
        btn_del_custom = QPushButton("– Eliminar")
        btn_del_custom.clicked.connect(self._on_del_custom_rxn)
        btn_layout.addWidget(btn_add_custom)
        btn_layout.addWidget(btn_del_custom)
        btn_widget = QWidget(); btn_widget.setLayout(btn_layout)
        eq_layout.addRow("", btn_widget)
        hint_custom = QLabel(
            "⚠ Reacciones custom usan Keq(T) con aprox ΔCp=0 (forma\n"
            "2-parámetros).  Válida cerca de 298 K; el error crece a T\n"
            "lejana.  Para química validada usá el catálogo de arriba."
        )
        hint_custom.setStyleSheet("color: #888; font-size: 8pt;")
        eq_layout.addRow("", hint_custom)

        layout.addRow(self.gb_eq)

        # ---- Diseño de COLUMNA (FUG, Capa 6) ----
        # Solo visible si el bloque es Tower/column.  Si activo, el
        # solver computa automáticamente outputs y duties.
        is_column = ("tower" in block.eq_type.lower()
                      or "column" in block.eq_type.lower()
                      or "destil" in block.eq_type.lower())
        self.gb_col = QGroupBox("Columna de destilación (FUG/NRTL)")
        self.gb_col.setVisible(is_column)
        col_layout = QFormLayout(self.gb_col)

        self.col_active = QCheckBox("Activar diseño automático (FUG)")
        self.col_active.setToolTip(
            "Si está activo, el solver computa composiciones de\n"
            "distillate/bottom + Q_reb automáticamente desde el feed.\n"
            "Si no: declarar outputs manualmente como hasta ahora."
        )
        self.col_active.setChecked(getattr(block, "column_active", False))
        col_layout.addRow(self.col_active)

        self.col_LK = QLineEdit(getattr(block, "column_LK", ""))
        self.col_LK.setPlaceholderText("ethanol, methanol, propane, ...")
        col_layout.addRow("Light key (LK):", self.col_LK)

        self.col_HK = QLineEdit(getattr(block, "column_HK", ""))
        self.col_HK.setPlaceholderText("water, butane, ...")
        col_layout.addRow("Heavy key (HK):", self.col_HK)

        self.col_xD = QDoubleSpinBox()
        self.col_xD.setRange(0.01, 0.999); self.col_xD.setDecimals(4)
        self.col_xD.setSingleStep(0.05)
        self.col_xD.setValue(getattr(block, "column_x_D_LK", 0.95))
        col_layout.addRow("x_D_LK (pureza dist):", self.col_xD)

        self.col_xB = QDoubleSpinBox()
        self.col_xB.setRange(0.0001, 0.5); self.col_xB.setDecimals(4)
        self.col_xB.setSingleStep(0.01)
        self.col_xB.setValue(getattr(block, "column_x_B_LK", 0.05))
        col_layout.addRow("x_B_LK (en fondo):", self.col_xB)

        self.col_Rf = QDoubleSpinBox()
        self.col_Rf.setRange(1.05, 5.0); self.col_Rf.setDecimals(2)
        self.col_Rf.setSingleStep(0.1)
        self.col_Rf.setValue(getattr(block, "column_R_factor", 1.3))
        col_layout.addRow("R / R_min:", self.col_Rf)

        # Método: FUG shortcut vs Wang-Henke riguroso
        self.col_method = QComboBox()
        self.col_method.addItem("FUG (shortcut)",            "fug")
        self.col_method.addItem("Wang-Henke (riguroso)",     "wanghenke")
        cur_method = getattr(block, "column_method", "fug") or "fug"
        idx = self.col_method.findData(cur_method)
        if idx >= 0: self.col_method.setCurrentIndex(idx)
        col_layout.addRow("Método:", self.col_method)

        self.col_N = QSpinBox()
        self.col_N.setRange(0, 200)
        self.col_N.setValue(getattr(block, "column_N_stages", 0))
        self.col_N.setSpecialValueText("auto (FUG)")
        col_layout.addRow("N etapas (WH):", self.col_N)

        hint_col = QLabel(
            "Si activo: el solver usa Fenske-Underwood-Gilliland-Kirkbride\n"
            "para diseñar la columna y escribe outputs automáticamente.\n"
            "Para multicomp (>2 keys), aplica Fenske-Hengstebeck.\n"
            "Detecta azeotropos via NRTL (Capa 6)."
        )
        hint_col.setStyleSheet("color: #888; font-size: 8pt;")
        col_layout.addRow("", hint_col)
        layout.addRow(self.gb_col)

        # ---- Flash drum (Vessel con VLE, Capa 6) ----
        is_vessel = ("vessel" in block.eq_type.lower()
                      or "tanque" in block.eq_type.lower()
                      or "flash" in block.eq_type.lower())
        self.gb_flash = QGroupBox("Flash isotérmico (VLE / NRTL)")
        self.gb_flash.setVisible(is_vessel)
        flash_layout = QFormLayout(self.gb_flash)

        self.flash_active_cb = QCheckBox("Activar flash automático")
        self.flash_active_cb.setToolTip(
            "Si activo: el solver calcula V/F + composiciones x, y\n"
            "usando flash isotérmico NRTL (Capa 6) a T_K, P_bar."
        )
        self.flash_active_cb.setChecked(getattr(block, "flash_active", False))
        flash_layout.addRow(self.flash_active_cb)

        self.flash_T = QDoubleSpinBox()
        self.flash_T.setRange(200, 800); self.flash_T.setDecimals(2)
        self.flash_T.setSingleStep(5.0)
        self.flash_T.setSuffix(" K")
        self.flash_T.setValue(getattr(block, "flash_T_K", 298.15))
        flash_layout.addRow("T_flash:", self.flash_T)

        self.flash_P = QDoubleSpinBox()
        self.flash_P.setRange(0.01, 200.0); self.flash_P.setDecimals(3)
        self.flash_P.setSingleStep(0.1)
        self.flash_P.setSuffix(" bar")
        self.flash_P.setValue(getattr(block, "flash_P_bar", 1.013))
        flash_layout.addRow("P_flash:", self.flash_P)

        hint_flash = QLabel(
            "El solver separa vapor / líquido usando γ·P_sat (NRTL).\n"
            "Asignación por puerto: 'vapor' → vapor output, 'liquido'\n"
            "→ liquid output (sino, primer/segundo output)."
        )
        hint_flash.setStyleSheet("color: #888; font-size: 8pt;")
        flash_layout.addRow("", hint_flash)
        layout.addRow(self.gb_flash)

        # ─────────────────────────────────────────────────────────
        # SEPARADORES MECÁNICOS — modelos internos (filtro,
        # centrífuga, secador, cristalizador, evaporador, ciclón).
        # Cada uno con su QGroupBox visible solo si eq_type coincide.
        # ─────────────────────────────────────────────────────────
        eq_lower = (block.eq_type or "").lower()
        is_separator    = "filter" in eq_lower or "centrifuge" in eq_lower
        is_dryer        = "dryer" in eq_lower
        is_crystallizer = "crystallizer" in eq_lower
        is_evaporator   = "evaporator" in eq_lower
        is_cyclone      = "cyclone" in eq_lower

        # ---- Filter / Centrifuge ----
        self.gb_sep = QGroupBox("Separación sólido-líquido (filtro / centrífuga)")
        self.gb_sep.setVisible(is_separator)
        sep_layout = QFormLayout(self.gb_sep)

        self.sep_active_cb = QCheckBox("Activar separador automático")
        self.sep_active_cb.setToolTip(
            "Si activo: el solver computa torta (cake) y madre\n"
            "desde solids_recovery + cake_moisture.  Modo dual con\n"
            "los outputs lockeados (si están lockeados, los respeta)."
        )
        self.sep_active_cb.setChecked(getattr(block, "separator_active", False))
        sep_layout.addRow(self.sep_active_cb)

        self.sep_recov = QDoubleSpinBox()
        self.sep_recov.setRange(0.0, 1.0); self.sep_recov.setDecimals(3)
        self.sep_recov.setSingleStep(0.01)
        self.sep_recov.setValue(getattr(block, "solids_recovery", 0.95))
        sep_layout.addRow("Solids recovery:", self.sep_recov)

        self.sep_moist = QDoubleSpinBox()
        self.sep_moist.setRange(0.0, 0.95); self.sep_moist.setDecimals(3)
        self.sep_moist.setSingleStep(0.01)
        self.sep_moist.setValue(getattr(block, "cake_moisture", 0.30))
        sep_layout.addRow("Cake moisture:", self.sep_moist)

        self.sep_solids = QLineEdit()
        self.sep_solids.setPlaceholderText("sucrose, biomass, ...  (vacío = usar main_component)")
        self.sep_solids.setText(",".join(getattr(block, "solid_components", []) or []))
        sep_layout.addRow("Solid components:", self.sep_solids)
        layout.addRow(self.gb_sep)

        # ---- Dryer ----
        self.gb_dry = QGroupBox("Secador (Dryer — drum)")
        self.gb_dry.setVisible(is_dryer)
        dry_layout = QFormLayout(self.gb_dry)
        self.dry_active_cb = QCheckBox("Activar secador automático")
        self.dry_active_cb.setToolTip(
            "Si activo: el solver computa producto seco a humedad\n"
            "final declarada + venteo de vapor."
        )
        self.dry_active_cb.setChecked(getattr(block, "dryer_active", False))
        dry_layout.addRow(self.dry_active_cb)
        self.dry_moist = QDoubleSpinBox()
        self.dry_moist.setRange(0.0, 0.5); self.dry_moist.setDecimals(3)
        self.dry_moist.setSingleStep(0.005)
        self.dry_moist.setValue(getattr(block, "final_moisture", 0.02))
        dry_layout.addRow("Final moisture:", self.dry_moist)
        self.dry_comp = QLineEdit()
        self.dry_comp.setText(getattr(block, "moisture_component", "water"))
        dry_layout.addRow("Moisture comp:", self.dry_comp)
        layout.addRow(self.gb_dry)

        # ---- Crystallizer ----
        self.gb_cry = QGroupBox("Cristalizador")
        self.gb_cry.setVisible(is_crystallizer)
        cry_layout = QFormLayout(self.gb_cry)
        self.cry_active_cb = QCheckBox("Activar cristalizador automático")
        self.cry_active_cb.setChecked(getattr(block, "crystallizer_active", False))
        cry_layout.addRow(self.cry_active_cb)
        self.cry_solute = QLineEdit()
        self.cry_solute.setText(getattr(block, "solute_component", ""))
        self.cry_solute.setPlaceholderText("sucrose, urea, ...")
        cry_layout.addRow("Solute comp:", self.cry_solute)
        self.cry_yield = QDoubleSpinBox()
        self.cry_yield.setRange(0.0, 1.0); self.cry_yield.setDecimals(3)
        self.cry_yield.setSingleStep(0.01)
        self.cry_yield.setValue(getattr(block, "crystal_yield", 0.80))
        cry_layout.addRow("Crystal yield:", self.cry_yield)
        layout.addRow(self.gb_cry)

        # ---- Evaporator ----
        self.gb_evp = QGroupBox("Evaporador")
        self.gb_evp.setVisible(is_evaporator)
        evp_layout = QFormLayout(self.gb_evp)
        self.evp_active_cb = QCheckBox("Activar evaporador automático")
        self.evp_active_cb.setChecked(getattr(block, "evaporator_active", False))
        evp_layout.addRow(self.evp_active_cb)
        self.evp_cf = QDoubleSpinBox()
        self.evp_cf.setRange(1.0, 20.0); self.evp_cf.setDecimals(2)
        self.evp_cf.setSingleStep(0.1)
        self.evp_cf.setValue(getattr(block, "concentration_factor", 2.0))
        evp_layout.addRow("Concentration factor:", self.evp_cf)
        self.evp_comp = QLineEdit()
        self.evp_comp.setText(getattr(block, "volatile_component", "water"))
        evp_layout.addRow("Volatile comp:", self.evp_comp)
        layout.addRow(self.gb_evp)

        # ---- Cyclone ----
        self.gb_cyc = QGroupBox("Ciclón gas/sólido")
        self.gb_cyc.setVisible(is_cyclone)
        cyc_layout = QFormLayout(self.gb_cyc)
        self.cyc_active_cb = QCheckBox("Activar ciclón automático")
        self.cyc_active_cb.setChecked(getattr(block, "cyclone_active", False))
        cyc_layout.addRow(self.cyc_active_cb)
        self.cyc_eff = QDoubleSpinBox()
        self.cyc_eff.setRange(0.0, 1.0); self.cyc_eff.setDecimals(3)
        self.cyc_eff.setSingleStep(0.01)
        self.cyc_eff.setValue(getattr(block, "collection_efficiency", 0.90))
        cyc_layout.addRow("Collection efficiency:", self.cyc_eff)
        self.cyc_solids = QLineEdit()
        self.cyc_solids.setPlaceholderText("silica, clinker, ...  (vacío = usar main_component)")
        self.cyc_solids.setText(",".join(getattr(block, "solid_components", []) or []))
        cyc_layout.addRow("Solid components:", self.cyc_solids)
        layout.addRow(self.gb_cyc)

        # ---- Equipo rotativo (bomba / compresor) ----
        is_pump_or_compr = ("pump" in block.eq_type.lower()
                             or "bomba" in block.eq_type.lower()
                             or "compressor" in block.eq_type.lower()
                             or "fan" in block.eq_type.lower())
        self.gb_rot = QGroupBox("Equipo rotativo (bomba / compresor)")
        self.gb_rot.setVisible(is_pump_or_compr)
        rot_layout = QFormLayout(self.gb_rot)

        # ΔP del equipo + checkbox auto-size
        self.rot_dp = QDoubleSpinBox()
        self.rot_dp.setRange(-50.0, 500.0); self.rot_dp.setDecimals(3)
        self.rot_dp.setSingleStep(0.5); self.rot_dp.setSuffix(" bar")
        self.rot_dp.setValue(getattr(block, "delta_p_bar", 0.0))
        self.rot_dp.setToolTip(
            "ΔP que el equipo entrega.\n"
            "Bomba/Compresor: positivo.\n"
            "Si está en 0 y hay P locked downstream, el solver lo\n"
            "auto-dimensiona para llegar a ese target."
        )
        self.rot_auto = QCheckBox("Auto-dimensionar (usa P_locked downstream)")
        self.rot_auto.setChecked(abs(getattr(block, "delta_p_bar", 0.0)) < 1e-6)
        self.rot_auto.setToolTip("Si está marcado, el solver calcula ΔP\n"
                                  "automáticamente para llegar al target.")
        def _on_auto_toggle(checked):
            self.rot_dp.setEnabled(not checked)
            if checked:
                self.rot_dp.setValue(0.0)
        self.rot_auto.toggled.connect(_on_auto_toggle)
        if self.rot_auto.isChecked():
            self.rot_dp.setEnabled(False)
        rot_layout.addRow("ΔP:", self.rot_dp)
        rot_layout.addRow("", self.rot_auto)

        # Eficiencia hidráulica/isentrópica + motor
        self.rot_eta = QDoubleSpinBox()
        self.rot_eta.setRange(0.3, 0.95); self.rot_eta.setDecimals(3)
        self.rot_eta.setSingleStep(0.05)
        # Default por tipo de equipo
        eta_default = 0.70 if "compressor" in block.eq_type.lower() else 0.75
        self.rot_eta.setValue(getattr(block, "efficiency", 0) or eta_default)
        if "compressor" in block.eq_type.lower():
            label_eta = "η isentrópica:"
        else:
            label_eta = "η hidráulica:"
        rot_layout.addRow(label_eta, self.rot_eta)

        hint_rot = QLabel(
            "<b>Default η por tipo:</b><br>"
            "&nbsp;&nbsp;Bomba centrífuga: 0.65-0.85 (default 0.75)<br>"
            "&nbsp;&nbsp;Bomba PD:         0.85-0.95<br>"
            "&nbsp;&nbsp;Compresor centr.: 0.70-0.80 (default 0.70)<br>"
            "&nbsp;&nbsp;Compresor recip:  0.75-0.85<br>"
            "η_motor adicional: 0.95 (eléctrico AC)<br>"
            "W_elec = m·ΔP / (ρ·η_hyd·η_motor)"
        )
        hint_rot.setStyleSheet("color: #888; font-size: 8pt;")
        hint_rot.setTextFormat(Qt.RichText)
        rot_layout.addRow("", hint_rot)
        layout.addRow(self.gb_rot)

        # botones
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def apply_to_model(self):
        """Persistir los valores al Block."""
        name = self.name_edit.text().strip()
        if name:
            self.block.name = name
        self.block.S = float(self.s_edit.value())
        self.block.n = int(self.n_edit.value())
        self.block.duty = float(self.duty_edit.value())
        self.block.duty_locked = bool(self.duty_lock.isChecked())
        heat = self.heat_combo.currentText()
        self.block.heat_source = "" if heat == "(auto)" else heat
        # heat_of_reaction (sólo si visible, i.e. reactor)
        if self.hor_edit.isVisible():
            self.block.heat_of_reaction = float(self.hor_edit.value())
        # Overrides de HX (sólo si visibles, i.e. categoría HX).
        # Valor 0 → guardar None (sin override; usa tablas U/ΔTlm).
        if self.u_over_edit.isVisible():
            v = float(self.u_over_edit.value())
            self.block.U_override = v if v > 0 else None
        if self.dtlm_over_edit.isVisible():
            v = float(self.dtlm_over_edit.value())
            self.block.dtlm_override = v if v > 0 else None
        # Columna — sizing físico (Tower)
        if hasattr(self, "gb_col_phys") and self.gb_col_phys.isVisible():
            self.block.packing_type = self.col_pack_type.currentData() or ""
            for attr, widget in (("tray_spacing_m",        self.col_tray_space),
                                  ("K_souders_brown",       self.col_K_sb),
                                  ("column_head_height_m",  self.col_head),
                                  ("tray_efficiency",       self.col_tray_eff),
                                  ("HETP_m",                self.col_HETP)):
                v = float(widget.value())
                setattr(self.block, attr, v if v > 0 else None)
        # Reactor de equilibrio (Capa 4): persistir reactions, T_op, P_op
        if hasattr(self, "gb_eq") and self.gb_eq.isVisible():
            picked: List[str] = []
            for i in range(self.rxn_list.count()):
                item = self.rxn_list.item(i)
                if item.checkState() == Qt.Checked:
                    rid = item.text().split("—")[0].strip()
                    picked.append(rid)
            self.block.reactions = picked
            # Hallazgo 1: persistir custom_reactions (lista de dicts)
            self.block.custom_reactions = list(self._custom_rxns_data)
            self.block.T_op_K   = float(self.t_op_edit.value())
            self.block.P_op_bar = float(self.p_op_edit.value())
            self.block.reactor_mode = self.mode_combo.currentData() or "equilibrium"
            self.block.reactor_volume_L = float(self.vol_edit.value())
            self.block.batch_time_s = float(self.batch_time.value())
        # Column FUG
        if hasattr(self, "gb_col") and self.gb_col.isVisible():
            self.block.column_active = bool(self.col_active.isChecked())
            self.block.column_LK = self.col_LK.text().strip()
            self.block.column_HK = self.col_HK.text().strip()
            self.block.column_x_D_LK = float(self.col_xD.value())
            self.block.column_x_B_LK = float(self.col_xB.value())
            self.block.column_R_factor = float(self.col_Rf.value())
            self.block.column_method   = self.col_method.currentData() or "fug"
            self.block.column_N_stages = int(self.col_N.value())
        # Flash drum
        if hasattr(self, "gb_flash") and self.gb_flash.isVisible():
            self.block.flash_active = bool(self.flash_active_cb.isChecked())
            self.block.flash_T_K = float(self.flash_T.value())
            self.block.flash_P_bar = float(self.flash_P.value())

        # Separadores mecánicos
        if hasattr(self, "gb_sep") and self.gb_sep.isVisible():
            self.block.separator_active = bool(self.sep_active_cb.isChecked())
            self.block.solids_recovery  = float(self.sep_recov.value())
            self.block.cake_moisture    = float(self.sep_moist.value())
            txt = self.sep_solids.text().strip()
            self.block.solid_components = [t.strip() for t in txt.split(",")
                                             if t.strip()] if txt else []
        if hasattr(self, "gb_dry") and self.gb_dry.isVisible():
            self.block.dryer_active       = bool(self.dry_active_cb.isChecked())
            self.block.final_moisture     = float(self.dry_moist.value())
            self.block.moisture_component = self.dry_comp.text().strip() or "water"
        if hasattr(self, "gb_cry") and self.gb_cry.isVisible():
            self.block.crystallizer_active = bool(self.cry_active_cb.isChecked())
            self.block.solute_component    = self.cry_solute.text().strip()
            self.block.crystal_yield       = float(self.cry_yield.value())
        if hasattr(self, "gb_evp") and self.gb_evp.isVisible():
            self.block.evaporator_active    = bool(self.evp_active_cb.isChecked())
            self.block.concentration_factor = float(self.evp_cf.value())
            self.block.volatile_component   = self.evp_comp.text().strip() or "water"
        if hasattr(self, "gb_cyc") and self.gb_cyc.isVisible():
            self.block.cyclone_active         = bool(self.cyc_active_cb.isChecked())
            self.block.collection_efficiency  = float(self.cyc_eff.value())
            txt = self.cyc_solids.text().strip()
            self.block.solid_components = [t.strip() for t in txt.split(",")
                                             if t.strip()] if txt else []

        # Equipo rotativo (pump / compressor)
        if hasattr(self, "gb_rot") and self.gb_rot.isVisible():
            if self.rot_auto.isChecked():
                self.block.delta_p_bar = 0.0   # solver lo auto-calcula
            else:
                self.block.delta_p_bar = float(self.rot_dp.value())
            self.block.efficiency = float(self.rot_eta.value())

    # ─── Custom reactions helpers (Hallazgo 1) ──────────────────────

    def _refresh_custom_rxns_list(self):
        self.custom_rxn_list.clear()
        for d in self._custom_rxns_data:
            name = d.get("name") or d.get("id", "?")
            self.custom_rxn_list.addItem(f"  ◆ {name}")

    def _on_add_custom_rxn(self):
        dlg = CustomReactionDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.result_dict is not None:
            self._custom_rxns_data.append(dlg.result_dict)
            self._refresh_custom_rxns_list()

    def _on_del_custom_rxn(self):
        idx = self.custom_rxn_list.currentRow()
        if 0 <= idx < len(self._custom_rxns_data):
            self._custom_rxns_data.pop(idx)
            self._refresh_custom_rxns_list()


class CustomReactionDialog(QDialog):
    """Sub-diálogo para definir una reacción custom (Hallazgo 1).

    Campos:
      · Ecuación libre 'A + 2 B -> C + D' (parsea coeficientes).
      · Tabla de especies (formula, fase g/l/aq/s, ν) auto-poblada.
      · ΔH₂₉₈ kJ/mol obligatorio.
      · Radio: reversible / irreversible.
      · Si reversible: ΔS₂₉₈ J/(mol·K) O Keq₂₉₈ (mutuamente excluyentes).
      · Rango T válido [K] default 298–2000.

    Al aceptar: valida vía reactions_db.reaction_from_dict (captura
    ValueError, muestra QMessageBox.warning, NO cierra hasta OK).
    El dict resultante queda en self.result_dict.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reacción custom")
        self.result_dict = None
        layout = QFormLayout(self)

        from PySide6.QtWidgets import (QLineEdit, QTableWidget,
                                          QTableWidgetItem, QRadioButton,
                                          QButtonGroup, QHeaderView)
        # Ecuación libre
        self.eq_edit = QLineEdit()
        self.eq_edit.setPlaceholderText("Ej: CO + H2O -> CO2 + H2")
        self.eq_edit.editingFinished.connect(self._parse_equation)
        layout.addRow("Ecuación:", self.eq_edit)

        # ID + nombre
        self.id_edit = QLineEdit("CUSTOM-1")
        layout.addRow("ID:", self.id_edit)
        self.name_edit = QLineEdit("Reacción custom")
        layout.addRow("Nombre:", self.name_edit)

        # Tabla de especies (formula, fase, nu) — 6 filas máximo
        self.tbl = QTableWidget(6, 3)
        self.tbl.setHorizontalHeaderLabels(["Fórmula", "Fase", "ν"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tbl.setMaximumHeight(180)
        for i in range(6):
            self.tbl.setItem(i, 0, QTableWidgetItem(""))
            self.tbl.setItem(i, 1, QTableWidgetItem("g"))
            self.tbl.setItem(i, 2, QTableWidgetItem(""))
        layout.addRow("Especies:", self.tbl)

        # ΔH₂₉₈
        self.dh_edit = QDoubleSpinBox()
        self.dh_edit.setRange(-1e4, 1e4); self.dh_edit.setDecimals(2)
        self.dh_edit.setSingleStep(1.0); self.dh_edit.setSuffix(" kJ/mol")
        layout.addRow("ΔH₂₉₈:", self.dh_edit)

        # Modo: reversible / irreversible
        self.rb_rev = QRadioButton("Reversible (dar ΔS o Keq)")
        self.rb_irr = QRadioButton("Irreversible (conversión declarada)")
        self.rb_rev.setChecked(True)
        rb_grp = QButtonGroup(self)
        rb_grp.addButton(self.rb_rev); rb_grp.addButton(self.rb_irr)
        layout.addRow(self.rb_rev)
        layout.addRow(self.rb_irr)

        # ΔS₂₉₈ o Keq₂₉₈ (mutuamente excluyentes)
        self.ds_edit = QDoubleSpinBox()
        self.ds_edit.setRange(-1e4, 1e4); self.ds_edit.setDecimals(2)
        self.ds_edit.setSuffix(" J/(mol·K)")
        layout.addRow("ΔS₂₉₈ (o vacío):", self.ds_edit)
        self.keq_edit = QDoubleSpinBox()
        self.keq_edit.setRange(0.0, 1e30); self.keq_edit.setDecimals(6)
        self.keq_edit.setValue(0.0)
        layout.addRow("Keq₂₉₈ (o 0=usar ΔS):", self.keq_edit)

        # Rango T
        self.t_min_edit = QDoubleSpinBox()
        self.t_min_edit.setRange(100, 5000); self.t_min_edit.setValue(298.15)
        self.t_min_edit.setSuffix(" K")
        layout.addRow("T_min:", self.t_min_edit)
        self.t_max_edit = QDoubleSpinBox()
        self.t_max_edit.setRange(100, 5000); self.t_max_edit.setValue(2000)
        self.t_max_edit.setSuffix(" K")
        layout.addRow("T_max:", self.t_max_edit)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _parse_equation(self):
        """'A + 2 B -> C + D' → autopopula la tabla de especies."""
        import re
        eq = self.eq_edit.text().strip()
        if "->" not in eq and "→" not in eq:
            return
        eq = eq.replace("→", "->")
        lhs, rhs = eq.split("->", 1)
        def _parse_side(side, sign):
            terms = [t.strip() for t in side.split("+") if t.strip()]
            out = []
            for t in terms:
                m = re.match(r"^(\d+\.?\d*)?\s*([A-Za-z][\w\d]*)$", t)
                if not m:
                    continue
                coef = float(m.group(1)) if m.group(1) else 1.0
                formula = m.group(2)
                out.append((formula, int(coef * sign)))
            return out
        species = _parse_side(lhs, -1) + _parse_side(rhs, +1)
        for i in range(self.tbl.rowCount()):
            if i < len(species):
                f, nu = species[i]
                self.tbl.item(i, 0).setText(f)
                self.tbl.item(i, 1).setText("g")
                self.tbl.item(i, 2).setText(str(nu))
            else:
                self.tbl.item(i, 0).setText("")
                self.tbl.item(i, 2).setText("")

    def _on_accept(self):
        import reactions_db as _rdb
        # Construir dict desde inputs
        stoich = []
        for i in range(self.tbl.rowCount()):
            f = (self.tbl.item(i, 0).text() if self.tbl.item(i, 0) else "").strip()
            if not f:
                continue
            ph = (self.tbl.item(i, 1).text() if self.tbl.item(i, 1) else "g").strip()
            try:
                nu = int(self.tbl.item(i, 2).text())
            except (ValueError, AttributeError):
                continue
            stoich.append({"formula": f, "phase": ph or "g", "nu": nu})
        d = {
            "id":   self.id_edit.text().strip() or "CUSTOM-?",
            "name": self.name_edit.text().strip() or "Custom",
            "stoich":              stoich,
            "dh_rxn_298_kJ_mol":   float(self.dh_edit.value()),
            "T_min_K":             float(self.t_min_edit.value()),
            "T_max_K":             float(self.t_max_edit.value()),
            "irreversible":        bool(self.rb_irr.isChecked()),
        }
        if not self.rb_irr.isChecked():
            keq = float(self.keq_edit.value())
            ds  = float(self.ds_edit.value())
            if keq > 0:
                d["keq_298"] = keq
            else:
                d["ds_rxn_298_J_mol_K"] = ds
        # Validar
        try:
            _rdb.reaction_from_dict(d)   # solo validación; descartar resultado
        except ValueError as e:
            QMessageBox.warning(self, "Reacción inválida", str(e))
            return  # NO cerrar
        self.result_dict = d
        self.accept()


class StreamEditDialog(QDialog):
    """Editor del stream: mass_flow, role, price, T, Cp, ports, nombre."""

    def __init__(self, parent, stream: Stream, fs: Flowsheet):
        super().__init__(parent)
        self.stream = stream
        self.fs = fs
        self.setWindowTitle(f"Editar corriente — {stream.name}")
        # Tamaño: se ajusta al screen (max 90% del alto disponible),
        # con scroll interno para ver TODAS las secciones aunque la
        # pantalla sea chica.  Los botones OK/Cancel quedan fijos abajo.
        from PySide6.QtWidgets import QScrollArea, QApplication
        try:
            scr = QApplication.primaryScreen().availableGeometry()
            max_h = int(scr.height() * 0.90)
        except Exception:
            max_h = 600
        self.resize(540, min(720, max_h))
        self.setMinimumHeight(360)

        # Auto-lock: cuando es True, cualquier value-changed en los
        # editores marca el lock correspondiente. Arranca False durante
        # el init (para que setear los valores iniciales NO lockee
        # automáticamente todo), se activa al final del __init__.
        self._allow_auto_lock = False

        # Tolerar streams flotantes (src<=0 o dst<=0): el dialog
        # permite configurar mass_flow / composition / kind aunque
        # el stream no esté conectado todavía.  Cuando se conecte
        # (via endpoint handles), los valores configurados se aplican.
        b_src = fs.blocks.get(stream.src)
        b_dst = fs.blocks.get(stream.dst)
        ports_src = (list(ep.get_ports(b_src.eq_type).keys())
                     if b_src is not None else [])
        ports_dst = (list(ep.get_ports(b_dst.eq_type).keys())
                     if b_dst is not None else [])

        # Outer layout: vertical con scroll arriba + botones abajo
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll, 1)

        # Form que vivirá dentro del scroll
        form_widget = QWidget()
        scroll.setWidget(form_widget)
        layout = QFormLayout(form_widget)
        layout.setContentsMargins(12, 12, 12, 12)

        # info read-only — tolera streams flotantes (b_src/b_dst pueden
        # ser None si el stream aún no está conectado a ningún bloque).
        src_name = b_src.name if b_src is not None else "(sin conectar)"
        dst_name = b_dst.name if b_dst is not None else "(sin conectar)"
        info = QLabel(f"<b>{stream.name}</b>:  {src_name}  →  {dst_name}")
        info.setStyleSheet("color: #555;")
        layout.addRow(info)

        # ---- Panel de Spec / Grados de libertad (se rellena al final) ----
        # Una corriente multicomponente es un sistema termodinamico con
        # variables intensivas acopladas: T, P, composicion (n-1 fracs
        # independientes), + extensiva = flujo. Si phase=two_phase, T y P
        # se atan por VLE — lockear ambos puede ser inconsistente.
        # Este label muestra en vivo que va a calcular el solver vs que
        # esta lockeado por el user.
        self.dof_label = QLabel("")
        self.dof_label.setWordWrap(True)
        self.dof_label.setStyleSheet(
            "background: #f4f6f8; border: 1px solid #dde2e7; "
            "border-radius: 4px; padding: 6px 8px; font-size: 8.5pt;"
        )
        layout.addRow(self.dof_label)

        # nombre
        self.name_edit = QLineEdit(stream.name)
        layout.addRow("Nombre:", self.name_edit)

        # mass flow + lock (sudoku)
        self.mass_edit = QDoubleSpinBox()
        self.mass_edit.setRange(0.0, 1e9)
        self.mass_edit.setDecimals(2)
        self.mass_edit.setSingleStep(100.0)
        self.mass_edit.setValue(stream.mass_flow)
        self.mass_lock = QCheckBox("🔒")
        self.mass_lock.setToolTip(
            "Marcar para fijar el flujo másico (sudoku spec).\n"
            "Sin marcar: el solver lo computa desde balance de masa."
        )
        # heurística para el lock inicial: mass_flow_locked OR > 0
        # Estado del lock: SOLO el flag explícito.  Si el stream tiene
        # mass_flow > 0 pero el lock está False, significa que el solver
        # lo computó (no es spec del user) — mostrar unchecked.
        self.mass_lock.setChecked(getattr(stream, "mass_flow_locked", False))
        m_row = QWidget(); m_lay = QHBoxLayout(m_row)
        m_lay.setContentsMargins(0,0,0,0)
        m_lay.addWidget(self.mass_lock); m_lay.addWidget(self.mass_edit, 1)
        layout.addRow("Flujo másico (tm/año):", m_row)

        # rol
        self.role_combo = QComboBox()
        for r in ("internal", "feed", "product", "utility", "waste"):
            self.role_combo.addItem(r)
        self.role_combo.setCurrentText(stream.role)
        layout.addRow("Rol:", self.role_combo)

        # Número de corriente custom (display).  0 = auto (topológico).
        self.num_edit = QSpinBox()
        self.num_edit.setRange(0, 9999)
        self.num_edit.setValue(getattr(stream, "display_number", 0))
        self.num_edit.setSpecialValueText("(auto)")
        layout.addRow("N° corriente (display):", self.num_edit)

        hint = QLabel(
            "feed:    materia prima externa\n"
            "product: producto final\n"
            "internal: corriente entre bloques\n"
            "utility: vapor / agua de enfriamiento\n"
            "waste:   residuo / efluente a tratamiento"
        )
        hint.setStyleSheet("color: #888; font-size: 8pt;")
        layout.addRow("", hint)

        # precio (visible si feed/product)
        self.price_label = QLabel("Precio (USD/tm):")
        self.price_edit = QDoubleSpinBox()
        self.price_edit.setRange(0.0, 1e7)
        self.price_edit.setDecimals(2)
        self.price_edit.setSingleStep(1.0)
        self.price_edit.setValue(stream.price_usd_per_tm)
        layout.addRow(self.price_label, self.price_edit)
        self.role_combo.currentTextChanged.connect(self._toggle_price)
        self._toggle_price(self.role_combo.currentText())

        # termofísicas
        gb_thermo = QGroupBox("Termofísicas (balance de energía)")
        gb_layout = QFormLayout(gb_thermo)
        self.t_edit = QDoubleSpinBox()
        self.t_edit.setRange(-273.0, 2000.0)
        self.t_edit.setDecimals(1)
        self.t_edit.setSingleStep(5.0)
        self.t_edit.setValue(stream.temperature)
        self.t_lock = QCheckBox("🔒")
        self.t_lock.setToolTip(
            "Marcar para fijar T (sudoku spec).\n"
            "Sin marcar: el solver la computa desde balance de energía."
        )
        self.t_lock.setChecked(getattr(stream, "temperature_locked", False))
        t_row = QWidget(); t_lay = QHBoxLayout(t_row)
        t_lay.setContentsMargins(0,0,0,0)
        t_lay.addWidget(self.t_lock); t_lay.addWidget(self.t_edit, 1)
        gb_layout.addRow("Temperatura (°C):", t_row)

        # Setpoint de T (target_temperature, opcional).  Cuando está
        # activado, "Setpoints…" del toolbar puede iterar el duty del
        # bloque upstream para hacer que T real iguale el objetivo.
        sp_row = QWidget()
        sp_lay = QHBoxLayout(sp_row); sp_lay.setContentsMargins(0,0,0,0)
        self.sp_check = QCheckBox("Setpoint T")
        cur_sp = getattr(stream, 'target_temperature', -999.0)
        has_sp = cur_sp > -273.0
        self.sp_check.setChecked(has_sp)
        self.sp_edit = QDoubleSpinBox()
        self.sp_edit.setRange(-273.0, 2000.0)
        self.sp_edit.setDecimals(1)
        self.sp_edit.setSingleStep(5.0)
        self.sp_edit.setValue(cur_sp if has_sp else stream.temperature)
        self.sp_edit.setEnabled(has_sp)
        self.sp_check.toggled.connect(self.sp_edit.setEnabled)
        sp_lay.addWidget(self.sp_check)
        sp_lay.addWidget(self.sp_edit)
        gb_layout.addRow("T objetivo (design):", sp_row)

        # Componente principal (catálogo)
        import components as comp_mod
        # Lock sudoku para composición (componente + composition dict)
        self.comp_lock = QCheckBox("🔒 Composición fija (no recomputar)")
        self.comp_lock.setToolTip(
            "Marcar para fijar la composición del stream.\n"
            "Sin marcar: el solver la computa desde composición de inputs\n"
            "(weighted avg en mixers/HX, sin reaccionar)."
        )
        self.comp_lock.setChecked(getattr(stream, "composition_locked", False))
        gb_layout.addRow(self.comp_lock)

        self.comp_combo = QComboBox()
        self.comp_combo.addItem("(personalizado)", "")
        for key, label in comp_mod.list_labels():
            self.comp_combo.addItem(label, key)
        cur_idx = self.comp_combo.findData(stream.main_component)
        if cur_idx >= 0:
            self.comp_combo.setCurrentIndex(cur_idx)
        gb_layout.addRow("Componente principal:", self.comp_combo)

        # ---- Composición multi-componente (tabla editable) ----
        # El "Componente principal" arriba es legacy single-comp.  Esta
        # tabla es la fuente real de la composición de la mezcla y se
        # guarda en stream.composition (Dict[str, float] = mass frac).
        self._comp_labels = comp_mod.list_labels()   # [(key, label)]
        self.comp_table = QTableWidget(0, 2)
        self.comp_table.setHorizontalHeaderLabels(["Componente", "Fracción másica"])
        self.comp_table.verticalHeader().setVisible(False)
        self.comp_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.comp_table.setColumnWidth(0, 260)
        self.comp_table.setColumnWidth(1, 120)
        self.comp_table.setMinimumHeight(130)
        self.comp_table.setMaximumHeight(220)
        # botones add/quitar/normalizar
        comp_btn_row = QWidget()
        comp_btn_lay = QHBoxLayout(comp_btn_row)
        comp_btn_lay.setContentsMargins(0, 0, 0, 0)
        self.btn_comp_add  = QPushButton("+ Agregar")
        self.btn_comp_del  = QPushButton("− Quitar")
        self.btn_comp_norm = QPushButton("Normalizar a 1.00")
        comp_btn_lay.addWidget(self.btn_comp_add)
        comp_btn_lay.addWidget(self.btn_comp_del)
        comp_btn_lay.addWidget(self.btn_comp_norm)
        comp_btn_lay.addStretch()
        # label sumatoria (validación visual)
        self.comp_sum_lbl = QLabel("Σ = 0.0000")
        self.comp_sum_lbl.setStyleSheet("color: #666; font-weight: 600;")
        comp_btn_lay.addWidget(self.comp_sum_lbl)
        gb_layout.addRow(comp_btn_row)
        gb_layout.addRow(self.comp_table)
        # poblar desde stream.composition (o {main:1.0} si solo había main_component)
        initial = dict(stream.composition or {})
        if not initial and stream.main_component:
            initial = {stream.main_component: 1.0}
        for k, v in initial.items():
            self._add_comp_row(k, float(v))
        # wiring
        self.btn_comp_add.clicked.connect(lambda: self._add_comp_row("", 0.0))
        self.btn_comp_del.clicked.connect(self._del_comp_rows)
        self.btn_comp_norm.clicked.connect(self._normalize_comp_rows)
        self._update_comp_sum()

        # Fase
        self.phase_combo = QComboBox()
        self.phase_combo.addItems(["", "liquid", "vapor", "gas", "two_phase"])
        cur = stream.phase or ""
        self.phase_combo.setCurrentText(cur)
        gb_layout.addRow("Fase:", self.phase_combo)

        # Cp manual (fallback si no se elige componente)
        self.cp_edit = QDoubleSpinBox()
        self.cp_edit.setRange(0.0, 100.0)
        self.cp_edit.setDecimals(3)
        self.cp_edit.setSingleStep(0.1)
        self.cp_edit.setValue(stream.cp)
        gb_layout.addRow("Cp manual (kJ/kg·K):", self.cp_edit)

        cp_hint = QLabel(
            "Si elegís 'Componente principal' + 'Fase', el solver usa\n"
            "Cp(T) del catálogo (más realista que Cp constante).\n"
            "El Cp manual queda como fallback (si componente = personalizado)."
        )
        cp_hint.setStyleSheet("color: #888; font-size: 8pt;")
        gb_layout.addRow("", cp_hint)
        layout.addRow(gb_thermo)

        # puertos ISA
        gb_ports = QGroupBox("Puertos ISA")
        gb_layout = QFormLayout(gb_ports)
        self.src_port_combo = QComboBox()
        self.src_port_combo.addItems(ports_src)
        cur_sp = stream.src_port or (ports_src[0] if ports_src else "")
        if cur_sp:
            idx = self.src_port_combo.findText(cur_sp)
            if idx >= 0:
                self.src_port_combo.setCurrentIndex(idx)
        _src_label = (f"Puerto en {b_src.name}:" if b_src is not None
                      else "Puerto origen (sin conectar):")
        gb_layout.addRow(_src_label, self.src_port_combo)

        self.dst_port_combo = QComboBox()
        self.dst_port_combo.addItems(ports_dst)
        cur_dp = stream.dst_port or (ports_dst[0] if ports_dst else "")
        if cur_dp:
            idx = self.dst_port_combo.findText(cur_dp)
            if idx >= 0:
                self.dst_port_combo.setCurrentIndex(idx)
        _dst_label = (f"Puerto en {b_dst.name}:" if b_dst is not None
                      else "Puerto destino (sin conectar):")
        gb_layout.addRow(_dst_label, self.dst_port_combo)
        layout.addRow(gb_ports)

        # ---- Tipo de corriente (mass / energy) ----
        gb_kind = QGroupBox("Tipo de corriente")
        kind_layout = QFormLayout(gb_kind)
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Masa (material clásico)", "mass")
        self.kind_combo.addItem("Energía pura (Q en kW)", "energy")
        cur_kind = getattr(stream, "stream_kind", "mass") or "mass"
        for _i in range(self.kind_combo.count()):
            if self.kind_combo.itemData(_i) == cur_kind:
                self.kind_combo.setCurrentIndex(_i); break
        kind_layout.addRow("Tipo:", self.kind_combo)
        self.energy_kW_edit = QDoubleSpinBox()
        self.energy_kW_edit.setRange(-1e6, 1e6); self.energy_kW_edit.setDecimals(2)
        self.energy_kW_edit.setSingleStep(50.0); self.energy_kW_edit.setSuffix(" kW")
        self.energy_kW_edit.setValue(float(getattr(stream, "energy_kW", 0.0) or 0.0))
        kind_layout.addRow("Q (energy_kW):", self.energy_kW_edit)
        kind_hint = QLabel(
            "Masa: corriente material clásica (mass_flow, T, comp).\n"
            "Energía: corriente PURA DE CALOR.  energy_kW > 0 → calor\n"
            "sale del bloque origen y entra al destino (Σ duties conserva).\n"
            "Si está flotante (sin src/dst): no afecta balance — útil para\n"
            "preparar la corriente y conectarla después."
        )
        kind_hint.setStyleSheet("color: #888; font-size: 8pt;")
        kind_layout.addRow("", kind_hint)
        # Habilitar energy_kW solo si kind=='energy'
        def _toggle_energy(idx):
            is_energy = (self.kind_combo.itemData(idx) == "energy")
            self.energy_kW_edit.setEnabled(is_energy)
        self.kind_combo.currentIndexChanged.connect(_toggle_energy)
        _toggle_energy(self.kind_combo.currentIndex())
        layout.addRow(gb_kind)

        # ---- Tubería: pérdida de carga (Darcy-Weisbach) ----
        # Hallazgo 4-C: checkbox 'is_pipe'.  Si está desmarcado (default
        # para flowsheets conceptuales), gb_pipe queda greyed y el
        # solver no calcula ΔP.  Marcado → calcula.
        gb_pipe = QGroupBox("Tubería (pérdida de carga)")
        pipe_layout = QFormLayout(gb_pipe)

        self.pipe_is_pipe = QCheckBox(
            "Tratar como tubería física (calcular ΔP Darcy-Weisbach)")
        self.pipe_is_pipe.setToolTip(
            "Desmarcado: corriente conceptual, sin hidráulica.\n"
            "Marcado: el solver calcula ΔP usando los campos de geometría."
        )
        self.pipe_is_pipe.setChecked(bool(getattr(stream, "is_pipe", False)))
        pipe_layout.addRow(self.pipe_is_pipe)

        self.pipe_L = QDoubleSpinBox()
        self.pipe_L.setRange(0.0, 10000.0); self.pipe_L.setDecimals(2)
        self.pipe_L.setSingleStep(1.0); self.pipe_L.setSuffix(" m")
        self.pipe_L.setValue(getattr(stream, "pipe_length_m", 0) or 10.0)
        pipe_layout.addRow("Longitud:", self.pipe_L)

        self.pipe_D = QDoubleSpinBox()
        self.pipe_D.setRange(1.0, 5000.0); self.pipe_D.setDecimals(1)
        self.pipe_D.setSingleStep(5.0); self.pipe_D.setSuffix(" mm")
        # Convertir de m a mm para display, default 50mm
        D_mm = (getattr(stream, "pipe_diameter_m", 0) or 0.050) * 1000.0
        self.pipe_D.setValue(D_mm)
        pipe_layout.addRow("Diámetro interno:", self.pipe_D)

        self.pipe_eps = QDoubleSpinBox()
        self.pipe_eps.setRange(0.001, 5.0); self.pipe_eps.setDecimals(3)
        self.pipe_eps.setSingleStep(0.01); self.pipe_eps.setSuffix(" mm")
        eps_mm = (getattr(stream, "pipe_roughness_m", 4.5e-5) or 4.5e-5) * 1000.0
        self.pipe_eps.setValue(eps_mm)
        pipe_layout.addRow("Rugosidad ε:", self.pipe_eps)

        self.pipe_K = QDoubleSpinBox()
        self.pipe_K.setRange(0.0, 1000.0); self.pipe_K.setDecimals(2)
        self.pipe_K.setSingleStep(0.5)
        self.pipe_K.setValue(getattr(stream, "pipe_K_local", 0.0))
        self.pipe_K.setToolTip(
            "Σ de coeficientes K de accesorios (codos, válvulas, etc).\n"
            "Valores típicos:\n"
            "  Codo 90°: 0.75 | Tee paso: 0.6\n"
            "  Vál. gate: 0.17 | Vál. globo: 10\n"
            "  Reducción: 0.04 | Expansión: 1\n"
            "Ej: 3 codos + 2 gates → K = 3·0.75 + 2·0.17 = 2.6"
        )
        pipe_layout.addRow("K local (accesorios):", self.pipe_K)

        # Presión de la corriente (spec o calculada por solver)
        self.p_edit = QDoubleSpinBox()
        self.p_edit.setRange(0.001, 500.0); self.p_edit.setDecimals(3)
        self.p_edit.setSingleStep(0.1); self.p_edit.setSuffix(" bar")
        self.p_edit.setValue(getattr(stream, "pressure_bar", 1.013))
        self.p_lock = QCheckBox("🔒")
        self.p_lock.setToolTip("Marcar para FIJAR P (spec).  Sin marcar:\n"
                                "el solver la calcula propagando ΔP por el flowsheet.")
        self.p_lock.setChecked(getattr(stream, "pressure_locked", False))
        p_row = QWidget(); p_lay = QHBoxLayout(p_row)
        p_lay.setContentsMargins(0,0,0,0)
        p_lay.addWidget(self.p_lock); p_lay.addWidget(self.p_edit, 1)
        pipe_layout.addRow("Presión:", p_row)

        hint_pipe = QLabel(
            "Defaults: 10 m, 50 mm (2\" Sch40), 0.045 mm (acero comercial).\n"
            "ΔP = ΔP_fric + ΔP_local (K·ρ·v²/2).  ρ y μ de la composición.\n"
            "Si declarás P lock, el solver propaga downstream por las\n"
            "tuberías + ΔP de bombas/HX/columnas."
        )
        hint_pipe.setStyleSheet("color: #888; font-size: 8pt;")
        pipe_layout.addRow("", hint_pipe)
        layout.addRow(gb_pipe)

        # ─── Geometría del path en el canvas ───────────────────────
        # Permite enderezar la flecha sin tener que salir del dialog.
        # Aplica el mismo helper _straighten_to_orthogonal del menu
        # derecho de la flecha, pero con eje explícito.
        gb_geo = QGroupBox("Forma de la flecha en el canvas")
        geo_lay = QHBoxLayout(gb_geo)
        self.btn_geo_auto = QPushButton("Auto-route")
        self.btn_geo_horz = QPushButton("Horizontal")
        self.btn_geo_vert = QPushButton("Vertical")
        for b in (self.btn_geo_auto, self.btn_geo_horz, self.btn_geo_vert):
            geo_lay.addWidget(b)
        geo_hint = QLabel("Alinea el endpoint flotante con el puerto del bloque.")
        geo_hint.setStyleSheet("color: #888; font-size: 8pt;")
        # Wiring: necesitamos el StreamItem para llamar
        # _straighten_to_orthogonal. Lo conseguimos via el parent del
        # dialog (FlowsheetMainWindow) y stream.id.
        def _apply_geo(axis):
            ed = self.parent()
            if ed is None or not hasattr(ed, "scene"):
                return
            si = ed.scene.stream_items.get(self.stream.id)
            if si is None:
                return
            if axis == "auto":
                self.stream.waypoints = []
                si.update_path()
            else:
                si._straighten_to_orthogonal(axis=axis)
            # Refrescar tambien todos los streams para los cruces
            for _sid, _other in ed.scene.stream_items.items():
                _other.update_path(rebuild_handles=False)
            if hasattr(ed, "_mark_dirty"):
                ed._mark_dirty()
        self.btn_geo_auto.clicked.connect(lambda: _apply_geo("auto"))
        self.btn_geo_horz.clicked.connect(lambda: _apply_geo("horizontal"))
        self.btn_geo_vert.clicked.connect(lambda: _apply_geo("vertical"))
        layout.addRow(gb_geo)
        layout.addRow("", geo_hint)

        # Habilitar/deshabilitar inputs de geometría según is_pipe.
        def _toggle_pipe_inputs(checked):
            for w in (self.pipe_L, self.pipe_D, self.pipe_eps, self.pipe_K):
                w.setEnabled(bool(checked))
        self.pipe_is_pipe.toggled.connect(_toggle_pipe_inputs)
        _toggle_pipe_inputs(self.pipe_is_pipe.isChecked())

        # ─── Wiring del panel DOF: cualquier lock/phase/comp/cp/main_comp
        # dispara refresh del resumen en vivo ───
        for chk in (self.mass_lock, self.t_lock, self.p_lock, self.comp_lock):
            chk.toggled.connect(self._update_dof_summary)
        self.phase_combo.currentTextChanged.connect(self._update_dof_summary)
        self.comp_combo.currentIndexChanged.connect(self._update_dof_summary)
        self.cp_edit.valueChanged.connect(self._update_dof_summary)
        # cualquier edit de fila de composición re-evalúa Σ y DOF
        # (lo hace _update_comp_sum via signals al agregar fila)
        self._update_dof_summary()

        # ─── AUTO-LOCK on edit ─────────────────────────────────────
        # Filosofía estilo Aspen/HYSYS: el simple acto de cambiar un
        # valor declara la variable como spec del user. El user puede
        # destildar el 🔒 después si quiere liberar la variable para
        # el solver. valueChanged solo dispara con cambios reales (no
        # con focus-out sin editar); el guard _allow_auto_lock=False
        # durante __init__ evita que los setValue iniciales auto-lockeen.
        self.mass_edit.valueChanged.connect(
            lambda _v: self._auto_lock(self.mass_lock))
        self.t_edit.valueChanged.connect(
            lambda _v: self._auto_lock(self.t_lock))
        self.p_edit.valueChanged.connect(
            lambda _v: self._auto_lock(self.p_lock))
        # composition: agregar/quitar/editar filas marca comp_lock
        self.btn_comp_add.clicked.connect(
            lambda: self._auto_lock(self.comp_lock))
        self.btn_comp_norm.clicked.connect(
            lambda: self._auto_lock(self.comp_lock))
        # dropdown legacy 'Componente principal' también lockea comp
        # (.activated solo dispara con interacción del user, no con
        #  setCurrentIndex programático)
        self.comp_combo.activated.connect(
            lambda _idx: self._auto_lock(self.comp_lock))
        # Habilitar auto-lock AHORA que el init terminó
        self._allow_auto_lock = True

        # ─── Botones OK/Cancel FUERA del scroll, siempre visibles ───
        # antes estaban dentro del QFormLayout y se cortaban en
        # pantallas chicas.  Ahora viven en el outer QVBoxLayout, así
        # que se mantienen visibles aunque el contenido crezca.
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        from PySide6.QtWidgets import QFrame
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #ddd;")
        outer.addWidget(sep)
        outer.addWidget(buttons)
        outer.setContentsMargins(0, 0, 0, 10)

    def _toggle_price(self, role_text):
        visible = role_text in ("feed", "product")
        self.price_label.setVisible(visible)
        self.price_edit.setVisible(visible)

    def _auto_lock(self, checkbox: QCheckBox):
        """Marca el checkbox 🔒 cuando el user editó el valor asociado.
        No hace nada durante el init (cuando _allow_auto_lock=False)."""
        if getattr(self, "_allow_auto_lock", False):
            checkbox.setChecked(True)

    # ---- helpers del editor multi-componente ----
    def _add_comp_row(self, key: str = "", frac: float = 0.0):
        """Agrega una fila a la tabla de composición con un combo de
        componente y un spin de fracción másica. Editar cualquier fila
        auto-lockea comp_lock (filosofía 'tipear es declarar spec')."""
        r = self.comp_table.rowCount()
        self.comp_table.insertRow(r)
        # Style explicito para combo + spin: cuando viven dentro de un
        # QTableWidget y la fila se selecciona, el highlight de la
        # selection-row puede tintar el widget de azul/negro y volverlo
        # ilegible (texto blanco sobre fondo oscuro o todo negro). Estos
        # stylesheets fuerzan fondo blanco/texto negro siempre.
        CELL_STYLE = (
            "QComboBox, QDoubleSpinBox { "
            "  background: white; color: #222; border: 1px solid #ccc; "
            "  padding: 2px; "
            "} "
            "QComboBox QAbstractItemView { "
            "  background: white; color: #222; "
            "  selection-background-color: #5c6bc0; "
            "  selection-color: white; "
            "} "
        )
        combo = QComboBox()
        combo.setStyleSheet(CELL_STYLE)
        combo.addItem("(elegir…)", "")
        for k, lbl in self._comp_labels:
            combo.addItem(lbl, k)
        if key:
            idx = combo.findData(key)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.currentIndexChanged.connect(self._update_comp_sum)
        combo.activated.connect(
            lambda _idx: self._auto_lock(self.comp_lock))
        self.comp_table.setCellWidget(r, 0, combo)
        spin = QDoubleSpinBox()
        spin.setStyleSheet(CELL_STYLE)
        spin.setRange(0.0, 1.0)
        spin.setDecimals(4)
        spin.setSingleStep(0.05)
        spin.setValue(float(frac))
        spin.valueChanged.connect(self._update_comp_sum)
        spin.valueChanged.connect(
            lambda _v: self._auto_lock(self.comp_lock))
        self.comp_table.setCellWidget(r, 1, spin)
        self._update_comp_sum()

    def _del_comp_rows(self):
        """Borra las filas seleccionadas de la tabla."""
        rows = sorted({i.row() for i in self.comp_table.selectedIndexes()},
                      reverse=True)
        for r in rows:
            self.comp_table.removeRow(r)
        self._update_comp_sum()

    def _read_comp_rows(self):
        """Devuelve [(key, frac), ...] desde los widgets de la tabla."""
        out = []
        for r in range(self.comp_table.rowCount()):
            combo = self.comp_table.cellWidget(r, 0)
            spin  = self.comp_table.cellWidget(r, 1)
            if combo is None or spin is None:
                continue
            key = combo.currentData() or ""
            out.append((key, float(spin.value())))
        return out

    def _normalize_comp_rows(self):
        """Escala las fracciones para que sumen 1.0."""
        rows = self._read_comp_rows()
        total = sum(v for _, v in rows)
        if total <= 0:
            return
        for r in range(self.comp_table.rowCount()):
            spin = self.comp_table.cellWidget(r, 1)
            if spin is not None:
                spin.setValue(spin.value() / total)
        self._update_comp_sum()

    def _update_comp_sum(self, *args, **kwargs):
        """Actualiza el label 'Σ = X.XXXX' con ✓ si la suma cuadra a 1.0."""
        rows = self._read_comp_rows()
        total = sum(v for k, v in rows if k)
        valid = total > 0 and abs(total - 1.0) < 0.01
        if total == 0:
            icon, color = "—", "#888"
        elif valid:
            icon, color = "✓", "#1b7e3b"
        else:
            icon, color = "⚠ debe sumar 1.00", "#b54708"
        self.comp_sum_lbl.setText(f"Σ = {total:.4f}  {icon}")
        self.comp_sum_lbl.setStyleSheet(f"color: {color}; font-weight: 600;")
        # Σ cambia → DOF analysis tambien (se cuenta como comp valida o no)
        if hasattr(self, "dof_label"):
            self._update_dof_summary()

    def _update_dof_summary(self):
        """Resumen en vivo de grados de libertad de la corriente.

        Variables intensivas + extensiva considaradas:
          • mass_flow (extensiva)
          • T, P (intensivas)
          • composition (n-1 fracciones independientes)

        Regla de Gibbs para sistema de C componentes y P fases:
          F = C - P + 2  (intensivas)
        Para una corriente material monofasica con C componentes:
          F_intensive = C + 1  (composiciones n-1 + T + P)
        + 1 extensiva (flujo total).

        Lo que importa al user es: que esta lockeando vs que va a
        calcular el solver, y avisar cuando hay over-spec (e.g. T y P
        ambos lockeados con phase=two_phase rompe el VLE).
        """
        if not hasattr(self, "dof_label"):
            return
        # Defensa contra invocaciones durante __init__: el populate inicial
        # de la tabla de composición dispara _update_comp_sum → este método
        # ANTES de que la sección de tubería cree p_lock/phase_combo/comp_combo
        # /cp_edit. Si falta cualquiera, abortamos silenciosamente — el último
        # _update_dof_summary del __init__ corre con todo creado.
        needed = ("mass_lock", "t_lock", "p_lock", "comp_lock",
                  "phase_combo", "comp_combo", "cp_edit")
        if not all(hasattr(self, w) for w in needed):
            return
        locks = []
        free  = []
        for lbl, chk in (("flujo", self.mass_lock), ("T", self.t_lock),
                          ("P", self.p_lock), ("composición", self.comp_lock)):
            (locks if chk.isChecked() else free).append(lbl)
        phase = self.phase_combo.currentText() or "(sin fase)"
        # Contar componentes con fraccion > 0
        n_comp = sum(1 for k, v in self._read_comp_rows() if k and v > 0)

        # ─── Determinar qué fuente de propiedades va a usar el solver ───
        # Cadena de fallback en flowsheet_solver._resolve_cp:
        #   1. thermo_db (DIPPR) con composition dict   (más preciso)
        #   2. thermo_db con main_component             (componente puro)
        #   3. components.py legacy con composition
        #   4. components.py legacy con main_component
        #   5. s.cp > 0 (override manual constante)
        #   6. None  (solver sin propiedades — falla en balance de energía)
        main_comp = self.comp_combo.currentData() or ""
        cp_manual = float(self.cp_edit.value())
        if n_comp >= 2:
            cp_source = "mezcla multi-componente (DIPPR ponderado)"
        elif n_comp == 1 or main_comp:
            cp_source = "componente puro del catálogo"
        elif cp_manual > 0:
            cp_source = f"Cp manual constante = {cp_manual:.3f} kJ/kg·K"
        else:
            cp_source = None

        rows = []
        rows.append(f"<b>Sistema:</b> {n_comp or '?'} componente(s), fase {phase}")
        rows.append("<b>Spec del user:</b> " +
                    (" · ".join(f"🔒 {l}" for l in locks)
                     if locks else "<i>nada lockeado</i>"))
        rows.append("<b>Solver calculará:</b> " +
                    (", ".join(free) if free else
                     "<i>nada — todo over-spec</i>"))
        if cp_source:
            rows.append(f"<b>Propiedades:</b> {cp_source}")
        else:
            rows.append("<b>Propiedades:</b> <i>ninguna fuente disponible</i>")

        # Advertencias DOF
        warns = []
        if phase == "two_phase" and self.t_lock.isChecked() and self.p_lock.isChecked():
            warns.append(
                "⚠ <b>T y P lockeados con fase two_phase:</b> el VLE los "
                "acopla. Lockeá solo T <i>o</i> solo P; la otra sale del "
                "punto de burbuja/rocío con la composición."
            )
        if not locks:
            warns.append(
                "ℹ Sin nada lockeado, el solver propaga el estado desde "
                "upstream. Útil en corrientes internas; un feed externo "
                "típicamente necesita flujo + T + composición fijados."
            )
        if cp_source is None:
            warns.append(
                "⚠ <b>Sin fuente de Cp:</b> agregá componentes a la tabla, "
                "o elegí 'Componente principal', o poné un Cp manual > 0. "
                "El solver no podrá computar el balance de energía sin esto."
            )

        color = "#7a3814" if any("⚠" in w for w in warns) else "#1b4d3e"
        html = (f"<div style='color:{color}'>"
                + "<br>".join(rows + warns)
                + "</div>")
        self.dof_label.setText(html)

    def apply_to_model(self):
        name = self.name_edit.text().strip()
        if name:
            self.stream.name = name
        self.stream.mass_flow = float(self.mass_edit.value())
        self.stream.mass_flow_locked = bool(self.mass_lock.isChecked())
        self.stream.role = self.role_combo.currentText()
        self.stream.display_number = int(self.num_edit.value())
        if self.stream.role in ("feed", "product"):
            self.stream.price_usd_per_tm = float(self.price_edit.value())
        else:
            self.stream.price_usd_per_tm = 0.0
        self.stream.temperature = float(self.t_edit.value())
        self.stream.temperature_locked = bool(self.t_lock.isChecked())
        self.stream.composition_locked = bool(self.comp_lock.isChecked())
        # Pipe geometry para pressure drop (Hallazgo 4-C: gating)
        self.stream.is_pipe = bool(self.pipe_is_pipe.isChecked())
        self.stream.pipe_length_m = float(self.pipe_L.value())
        self.stream.pipe_diameter_m = float(self.pipe_D.value()) / 1000.0
        self.stream.pipe_roughness_m = float(self.pipe_eps.value()) / 1000.0
        self.stream.pipe_K_local = float(self.pipe_K.value())
        self.stream.pressure_bar = float(self.p_edit.value())
        self.stream.pressure_locked = bool(self.p_lock.isChecked())
        # Tipo de corriente (mass/energy) + energy_kW
        self.stream.stream_kind = self.kind_combo.currentData() or "mass"
        self.stream.energy_kW = float(self.energy_kW_edit.value())
        # Setpoint: si la casilla está marcada, guarda T objetivo;
        # si no, -999 (centinela "sin setpoint").
        if self.sp_check.isChecked():
            self.stream.target_temperature = float(self.sp_edit.value())
        else:
            self.stream.target_temperature = -999.0
        self.stream.cp = float(self.cp_edit.value())
        # Composición multi-componente desde la tabla. Si hay filas con
        # componente seleccionado y fracción > 0, se sobreescribe el
        # composition dict del stream y main_component se deriva del
        # dominante (mantiene compatibilidad con código legacy que solo
        # usa main_component).
        rows = self._read_comp_rows()
        comp_dict = {}
        for key, frac in rows:
            if key and frac > 0:
                comp_dict[key] = comp_dict.get(key, 0.0) + frac
        if comp_dict:
            self.stream.composition = comp_dict
            self.stream.main_component = max(
                comp_dict.items(), key=lambda kv: kv[1])[0]
        else:
            # Tabla vacía: respetar dropdown legacy single-componente.
            self.stream.main_component = self.comp_combo.currentData() or ""
            if self.stream.main_component:
                self.stream.composition = {self.stream.main_component: 1.0}
            else:
                self.stream.composition = {}
        self.stream.phase = self.phase_combo.currentText() or ""
        self.stream.src_port = self.src_port_combo.currentText() or ""
        self.stream.dst_port = self.dst_port_combo.currentText() or ""


class OpexExtraRowDialog(QDialog):
    """Editor de UNA fila opex_extras."""

    CATEGORIES = ["Raw Materials", "Utilities", "Consumables",
                  "Waste Treatment", "Other"]

    def __init__(self, parent, row=None):
        super().__init__(parent)
        self.result_row = None
        self.setWindowTitle("OPEX extra" if row else "Nuevo OPEX extra")
        self.resize(420, 340)

        row = row or {
            "name": "", "units": "tm", "time_basis": "year",
            "flowrate": 0.0, "price_usd_per_unit": 0.0,
            "stream": "Utilities",
        }

        layout = QFormLayout(self)

        self.name_edit = QLineEdit(str(row.get("name", "")))
        layout.addRow("Nombre:", self.name_edit)

        self.cat_combo = QComboBox()
        self.cat_combo.addItems(self.CATEGORIES)
        cur = row.get("stream", "Utilities")
        idx = self.cat_combo.findText(cur)
        if idx >= 0:
            self.cat_combo.setCurrentIndex(idx)
        layout.addRow("Categoría:", self.cat_combo)

        self.units_edit = QLineEdit(str(row.get("units", "tm")))
        layout.addRow("Unidades:", self.units_edit)

        self.flow_edit = QDoubleSpinBox()
        self.flow_edit.setRange(0.0, 1e12)
        self.flow_edit.setDecimals(2)
        self.flow_edit.setSingleStep(100.0)
        self.flow_edit.setValue(float(row.get("flowrate", 0.0)))
        layout.addRow("Flujo / consumo:", self.flow_edit)

        self.price_edit = QDoubleSpinBox()
        self.price_edit.setRange(0.0, 1e7)
        self.price_edit.setDecimals(4)
        self.price_edit.setSingleStep(1.0)
        self.price_edit.setValue(float(row.get("price_usd_per_unit", 0.0)))
        layout.addRow("Precio (USD/unidad):", self.price_edit)

        hint = QLabel(
            "Steam MP   30000 tm × $25\n"
            "Cooling   500000 tm × $0.30\n"
            "Electric    4M kWh × $0.08\n"
            "Catalizador Pt   0.5 tm × $25000"
        )
        hint.setStyleSheet("color: #888; font-size: 8pt;")
        layout.addRow("", hint)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_ok(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Inválido", "El nombre no puede estar vacío.")
            return
        self.result_row = {
            "name":               name,
            "units":              self.units_edit.text().strip() or "tm",
            "time_basis":         "year",
            "flowrate":           float(self.flow_edit.value()),
            "price_usd_per_unit": float(self.price_edit.value()),
            "stream":             self.cat_combo.currentText(),
        }
        self.accept()


class OpexExtrasDialog(QDialog):
    """Tabla editable de OPEX extras del flowsheet."""

    def __init__(self, parent, fs: Flowsheet):
        super().__init__(parent)
        self.fs = fs
        self.setWindowTitle("OPEX extras — utilidades, consumibles, materias primas")
        self.resize(820, 460)

        layout = QVBoxLayout(self)

        info = QLabel(
            "Costos operativos variables que NO son streams del PFD.\n"
            "Se agregan automáticamente a Variable Operating Costs al "
            "lanzar el análisis económico.  Las utilities derivadas de "
            "duties (heaters/coolers) se calculan aparte y NO aparecen acá."
        )
        info.setStyleSheet("color: #555;")
        info.setWordWrap(True)
        layout.addWidget(info)

        cols = ["Nombre", "Categoría", "Unidades", "Flujo/año",
                "Precio USD/u", "Total USD/año"]
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.doubleClicked.connect(self._on_edit)
        layout.addWidget(self.table)

        # toolbar
        tb_layout = QHBoxLayout()
        tb_layout.addWidget(QPushButton("+ Agregar", clicked=self._on_add))
        tb_layout.addWidget(QPushButton("Editar fila", clicked=self._on_edit))
        tb_layout.addWidget(QPushButton("− Borrar", clicked=self._on_delete))
        tb_layout.addStretch()
        self.total_label = QLabel("")
        self.total_label.setStyleSheet("font-weight: bold;")
        tb_layout.addWidget(self.total_label)
        tb_layout.addStretch()
        tb_layout.addWidget(QPushButton("Cerrar", clicked=self.accept))
        layout.addLayout(tb_layout)

        self._refresh()

    def _refresh(self):
        self.table.setRowCount(len(self.fs.opex_extras))
        total = 0.0
        for r, ex in enumerate(self.fs.opex_extras):
            annual = ex.get("flowrate", 0) * ex.get("price_usd_per_unit", 0)
            total += annual
            vals = [
                ex.get("name", ""),
                ex.get("stream", ""),
                ex.get("units", ""),
                f"{ex.get('flowrate', 0):g}",
                f"{ex.get('price_usd_per_unit', 0):g}",
                f"$ {annual:>10,.0f}",
            ]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(str(v))
                if c in (3, 4, 5):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, it)
        self.total_label.setText(
            f"Total OPEX extras: $ {total:>10,.0f}/año  ({len(self.fs.opex_extras)} filas)"
        )

    def _on_add(self):
        dlg = OpexExtraRowDialog(self, row=None)
        if dlg.exec() == QDialog.Accepted and dlg.result_row:
            self.fs.opex_extras.append(dlg.result_row)
            self._refresh()

    def _on_edit(self):
        row_idx = self.table.currentRow()
        if row_idx < 0 or row_idx >= len(self.fs.opex_extras):
            QMessageBox.information(self, "Editar", "Seleccioná una fila primero.")
            return
        dlg = OpexExtraRowDialog(self, row=self.fs.opex_extras[row_idx])
        if dlg.exec() == QDialog.Accepted and dlg.result_row:
            self.fs.opex_extras[row_idx] = dlg.result_row
            self._refresh()

    def _on_delete(self):
        row_idx = self.table.currentRow()
        if row_idx < 0 or row_idx >= len(self.fs.opex_extras):
            return
        ex = self.fs.opex_extras[row_idx]
        ans = QMessageBox.question(
            self, "Confirmar borrado",
            f"¿Borrar '{ex.get('name', '?')}'?"
        )
        if ans != QMessageBox.Yes:
            return
        del self.fs.opex_extras[row_idx]
        self._refresh()


# ======================================================
# BLOQUE COMO QGraphicsItem
# ======================================================

class _RoundedRectBody(QGraphicsRectItem):
    """QGraphicsRectItem con esquinas redondeadas dibujadas via paint().

    Hereda de QGraphicsRectItem (no de QGraphicsPathItem) para que
    shape() siga siendo el rect cuadrado completo — garantiza hit
    testing en todo el área del bloque, incluyendo las pequeñas
    zonas de esquinas donde el visual rounded no llega.
    """
    RADIUS = 4

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(self.brush())
        painter.setPen(self.pen())
        painter.drawRoundedRect(self.rect(), self.RADIUS, self.RADIUS)


class _StatusHaloItem(QGraphicsRectItem):
    """Halo decorativo NO-HITTABLE.

    Como BlockItem es un QGraphicsItemGroup con handlesChildEvents=True,
    los clicks en el área de cualquier hijo (incluyendo el halo
    extendido 6px) van al group entero.  Resultado: si un endpoint
    handle del stream queda sobre la zona extendida del halo, el click
    activa el bloque (movable) en vez del handle.

    Solución: shape() vacío y NoButton para que este item NO contribuya
    al hit region del group.  Sigue pintando normal."""

    def shape(self):
        return QPainterPath()        # path vacío = no hit area

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(self.brush())
        painter.setPen(self.pen())
        painter.drawRoundedRect(self.rect(), 4, 4)


class _StreamHandle(QGraphicsEllipseItem):
    """Handle circular azul para arrastrar un waypoint de stream.
    Se renderiza solo cuando el stream está seleccionado.  Al moverlo,
    snap a la grilla y se actualiza model.waypoints[idx]."""

    RADIUS = 5            # tamaño VISUAL del círculo
    HIT_RADIUS = 14       # tamaño de HIT AREA (invisible, más generoso)
                          # — el handle visible es chico para no estorbar,
                          # pero el área clickeable cubre ~28px diámetro

    def shape(self):
        """Hit area más grande que el visual para que el user no
        necesite acertar pixel-perfect."""
        from PySide6.QtCore import QRectF
        path = QPainterPath()
        r = self.HIT_RADIUS
        path.addEllipse(QRectF(-r, -r, 2*r, 2*r))
        return path

    def boundingRect(self):
        from PySide6.QtCore import QRectF
        r = self.HIT_RADIUS
        return QRectF(-r, -r, 2*r, 2*r)

    def __init__(self, stream_item: "StreamItem", waypoint_idx: int):
        r = self.RADIUS
        super().__init__(-r, -r, 2*r, 2*r)
        self._stream_item = stream_item
        self._wp_idx = waypoint_idx
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setBrush(QBrush(QColor("#1f6feb")))
        self.setPen(QPen(QColor("#ffffff"), 1.2))
        self.setZValue(20)        # por encima de BlockItem (z=10) — evita
                                   # que el bloque tape el handle si están
                                   # encimados
        self.setCursor(Qt.SizeAllCursor)
        # init pos desde el modelo (scene-coords)
        wp = stream_item.model.waypoints[waypoint_idx]
        self.setPos(float(wp[0]), float(wp[1]))

    def _neighbor_pts(self):
        """Devuelve (prev, next) — los puntos vecinos en el polyline del
        stream, para el snap ortogonal del magnetismo.

        prev: waypoint[idx-1] o, si idx=0, la posición del puerto source.
        next: waypoint[idx+1] o, si último, la posición del puerto dest.
        Cada uno es (x, y) o None si no se puede resolver.
        """
        si = self._stream_item
        s  = si.model
        i  = self._wp_idx
        n  = len(s.waypoints)
        prev_pt = next_pt = None
        if 0 <= i < n:
            if i > 0:
                wp = s.waypoints[i - 1]
                prev_pt = (float(wp[0]), float(wp[1]))
            else:
                b_src = si.fs.blocks.get(s.src)
                if b_src is not None:
                    try:
                        _, x1, y1 = si._resolve_port(b_src, s.src_port, "right")
                        prev_pt = (x1, y1)
                    except Exception:
                        pass
            if i < n - 1:
                wp = s.waypoints[i + 1]
                next_pt = (float(wp[0]), float(wp[1]))
            else:
                b_dst = si.fs.blocks.get(s.dst)
                if b_dst is not None:
                    try:
                        _, x2, y2 = si._resolve_port(b_dst, s.dst_port, "left")
                        next_pt = (x2, y2)
                    except Exception:
                        pass
        return prev_pt, next_pt

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            # 1. snap a grilla
            nx = round(value.x() / GRID_STEP) * GRID_STEP
            ny = round(value.y() / GRID_STEP) * GRID_STEP
            # 2. MAGNETISMO: snap ortogonal a los vecinos del waypoint
            #    (mantiene segmentos horizontales o verticales si está
            #    suficientemente cerca de alineación).
            SNAP_TOL = 10.0     # tolerancia px
            prev_pt, next_pt = self._neighbor_pts()
            for n_pt in (prev_pt, next_pt):
                if n_pt is None:
                    continue
                if abs(nx - n_pt[0]) < SNAP_TOL:
                    nx = n_pt[0]
                if abs(ny - n_pt[1]) < SNAP_TOL:
                    ny = n_pt[1]
            value = QPointF(nx, ny)
        elif change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            si = self._stream_item
            i = self._wp_idx
            if 0 <= i < len(si.model.waypoints):
                si.model.waypoints[i] = [self.pos().x(), self.pos().y()]
                si.update_path(rebuild_handles=False)
        return super().itemChange(change, value)


# =============================================================
# JUMPERS — cruces de streams con arc (convención PFD industrial)
# =============================================================

def _segments_intersect(x1, y1, x2, y2, x3, y3, x4, y4):
    """Devuelve (xc, yc) si los segmentos (1-2) y (3-4) se cruzan
    estrictamente (no en endpoints).  None si no se cruzan."""
    denom = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(denom) < 1e-9:
        return None    # paralelos
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denom
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / denom
    eps = 1e-3   # tolerancia para descartar cruces en esquinas
    if eps < t < 1 - eps and eps < u < 1 - eps:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def _detect_path_crossings(pts_self, pts_other):
    """Detecta los puntos donde el path 'self' cruza al path 'other'.
    Cada punto retornado es (x_cross, y_cross, seg_idx_self) donde
    seg_idx_self es el índice del segmento en pts_self (par i,
    de pts[2i:2i+4])."""
    crossings = []
    if len(pts_self) < 4 or len(pts_other) < 4:
        return crossings
    n_self = (len(pts_self) - 2) // 2
    n_other = (len(pts_other) - 2) // 2
    for i in range(n_self):
        x1, y1 = pts_self[2*i], pts_self[2*i+1]
        x2, y2 = pts_self[2*i+2], pts_self[2*i+3]
        for j in range(n_other):
            x3, y3 = pts_other[2*j], pts_other[2*j+1]
            x4, y4 = pts_other[2*j+2], pts_other[2*j+3]
            cross = _segments_intersect(x1, y1, x2, y2, x3, y3, x4, y4)
            if cross is not None:
                crossings.append((cross[0], cross[1], i))
    return crossings


HOP_RADIUS = 6.0   # radio de la curvita en el cruce


def _segments_too_close(x1, y1, x2, y2,  ax, ay, bx, by,
                          min_dist: float = 8.0) -> bool:
    """True si los segmentos (1-2) y (a-b) son COLINEALES y se
    SOLAPAN dentro de min_dist (líneas paralelas pegadas).

    No detecta cruces (eso ya lo hace _segments_intersect).  Detecta
    overlap: dos streams ortogonales paralelos pegados verticalmente
    o horizontalmente.
    """
    # Caso horizontal: ambos segmentos son ~horizontales (|dy|<2)
    if abs(y1 - y2) < 2 and abs(ay - by) < 2:
        if abs(y1 - ay) > min_dist:
            return False
        # Overlap en x?
        s1_lo, s1_hi = min(x1, x2), max(x1, x2)
        s2_lo, s2_hi = min(ax, bx), max(ax, bx)
        if s1_hi < s2_lo or s2_hi < s1_lo:
            return False
        return True
    # Caso vertical: ambos ~verticales
    if abs(x1 - x2) < 2 and abs(ax - bx) < 2:
        if abs(x1 - ax) > min_dist:
            return False
        s1_lo, s1_hi = min(y1, y2), max(y1, y2)
        s2_lo, s2_hi = min(ay, by), max(ay, by)
        if s1_hi < s2_lo or s2_hi < s1_lo:
            return False
        return True
    return False


def _apply_lane_offset(pts, other_paths, my_id: int,
                        lane_step: float = 10.0,
                        min_dist: float = 8.0) -> list:
    """Aplica un offset perpendicular a los segmentos del path actual
    que estén SUPERPUESTOS con otros streams paralelos.

    other_paths: list of (other_id, other_pts).
    my_id: id del stream actual (para orden determinístico — el de
           id mayor se desplaza).
    lane_step: cuánto desplazar cada lane (default 10px).
    min_dist: distancia mínima entre paralelos antes de aplicar
              offset (default 8px).

    Devuelve nueva lista de pts.  Si no hay overlap, retorna pts sin
    cambios.
    """
    if len(pts) < 4:
        return pts
    new_pts = list(pts)
    n_segs = (len(pts) - 2) // 2
    for i in range(n_segs):
        x1, y1 = pts[2*i], pts[2*i+1]
        x2, y2 = pts[2*i+2], pts[2*i+3]
        # Contar cuántos other streams están en la misma "lane"
        # (overlap dentro de min_dist), considerando solo los con
        # id menor (los más antiguos dominan, los nuevos se desplazan).
        lanes_occupied = 0
        for other_id, other_pts in other_paths:
            if other_id >= my_id:
                continue
            if not other_pts or len(other_pts) < 4:
                continue
            n_other = (len(other_pts) - 2) // 2
            for j in range(n_other):
                ax, ay = other_pts[2*j], other_pts[2*j+1]
                bx, by = other_pts[2*j+2], other_pts[2*j+3]
                if _segments_too_close(x1, y1, x2, y2, ax, ay, bx, by,
                                         min_dist):
                    lanes_occupied += 1
                    break
        if lanes_occupied == 0:
            continue
        # Aplicar offset perpendicular según lane.  Para horizontal:
        # desplazamiento en y.  Para vertical: en x.  Lane 1, 2, 3...
        # con steps de lane_step.
        offset = lane_step * lanes_occupied
        if abs(y1 - y2) < 2:    # horizontal
            new_pts[2*i+1]   = y1 + offset
            new_pts[2*i+3]   = y2 + offset
        elif abs(x1 - x2) < 2:  # vertical
            new_pts[2*i]     = x1 + offset
            new_pts[2*i+2]   = x2 + offset
    return new_pts


def _segment_intersects_rect(x1, y1, x2, y2, rx, ry, rw, rh):
    """True si el segmento (x1,y1)-(x2,y2) CRUZA el rect (entra/sale,
    no solo toca el borde).  Usado para detectar streams que atraviesan
    bloques ajenos en el routing automático.

    Tolerancia: 1px de margen para evitar falsos positivos cuando el
    segmento solo roza el borde."""
    EPS = 1.0
    # Quick reject: ambos endpoints en el mismo lado externo
    if (x1 < rx - EPS and x2 < rx - EPS): return False
    if (x1 > rx + rw + EPS and x2 > rx + rw + EPS): return False
    if (y1 < ry - EPS and y2 < ry - EPS): return False
    if (y1 > ry + rh + EPS and y2 > ry + rh + EPS): return False
    # Endpoint dentro (strict)?
    if (rx + EPS < x1 < rx + rw - EPS) and (ry + EPS < y1 < ry + rh - EPS):
        return True
    if (rx + EPS < x2 < rx + rw - EPS) and (ry + EPS < y2 < ry + rh - EPS):
        return True
    # Cruce con alguno de los 4 bordes del rect
    edges = [
        (rx, ry,       rx + rw, ry),       # top
        (rx, ry + rh,  rx + rw, ry + rh),  # bottom
        (rx, ry,       rx,      ry + rh),  # left
        (rx + rw, ry,  rx + rw, ry + rh),  # right
    ]
    for (x3, y3, x4, y4) in edges:
        if _segments_intersect(x1, y1, x2, y2, x3, y3, x4, y4) is not None:
            return True
    return False


def _detour_around_rect(x1, y1, x2, y2, rx, ry, rw, rh):
    """Genera puntos intermedios ortogonales para rodear el rect.

    Devuelve la lista de puntos a INSERTAR entre (x1,y1) y (x2,y2)
    (sin incluir esos endpoints).  Elige rodear por arriba/abajo/
    izquierda/derecha según cuál sea más corto en distancia Manhattan.
    """
    # Las 4 posibles vías (sobre/bajo/izq/der) con sus puntos extra:
    options = [
        # Por arriba del rect
        ([x1, ry - 1, x2, ry - 1],
         abs(y1 - (ry - 1)) + abs(x2 - x1) + abs(y2 - (ry - 1))),
        # Por abajo
        ([x1, ry + rh + 1, x2, ry + rh + 1],
         abs(y1 - (ry + rh + 1)) + abs(x2 - x1) + abs(y2 - (ry + rh + 1))),
        # Por izquierda
        ([rx - 1, y1, rx - 1, y2],
         abs(x1 - (rx - 1)) + abs(y2 - y1) + abs(x2 - (rx - 1))),
        # Por derecha
        ([rx + rw + 1, y1, rx + rw + 1, y2],
         abs(x1 - (rx + rw + 1)) + abs(y2 - y1) + abs(x2 - (rx + rw + 1))),
    ]
    # Elegir la de menor costo Manhattan
    options.sort(key=lambda opt: opt[1])
    return options[0][0]


def _avoid_obstacles(pts, obstacles, padding=12, max_iter=8):
    """Modifica pts (polyline) para que no atraviese ningún rect en
    obstacles.  obstacles: list of (x, y, w, h).

    Algoritmo: iterativo.  En cada pasada busca el primer segmento
    que cruza un obstáculo, inserta un detour ortogonal alrededor del
    bloque, y reintenta.  max_iter cap por seguridad.

    El padding se aplica al rect del obstáculo (le agrega margen).
    Default 12 px ≈ 3× grosor de stream típico — suficiente para que
    el handle del bloque (selección border) no toque el stream.
    """
    if not obstacles or len(pts) < 4:
        return pts
    for _ in range(max_iter):
        modified = False
        new_pts: List[float] = []
        i = 0
        while i < len(pts):
            new_pts.append(pts[i])
            new_pts.append(pts[i + 1])
            if i + 2 >= len(pts):
                i += 2
                continue
            x1, y1 = pts[i], pts[i + 1]
            x2, y2 = pts[i + 2], pts[i + 3]
            # Chequear contra cada obstáculo
            detour_added = False
            for (bx, by, bw, bh) in obstacles:
                rx = bx - padding
                ry = by - padding
                rw = bw + 2 * padding
                rh = bh + 2 * padding
                if _segment_intersects_rect(x1, y1, x2, y2, rx, ry, rw, rh):
                    detour = _detour_around_rect(x1, y1, x2, y2,
                                                   rx, ry, rw, rh)
                    new_pts.extend(detour)
                    detour_added = True
                    modified = True
                    break
            i += 2
        pts = new_pts
        if not modified:
            break
    return pts


def _build_path_with_hops(pts, hops):
    """Construye un QPainterPath siguiendo `pts`, insertando un arc
    (semicírculo) en cada punto de cruce listado en `hops`.

    Cada hop: (x_cross, y_cross, seg_idx).
    El path queda: lineTo hasta (cross − r·u), cubicTo (apex + offset
    perpendicular), lineTo (cross + r·u), continuar al siguiente pt.
    """
    import math
    path = QPainterPath(QPointF(pts[0], pts[1]))
    n_segs = (len(pts) - 2) // 2

    # Agrupar hops por segmento.  Ordenarlos a lo largo del segmento.
    hops_by_seg: dict = {}
    for (xc, yc, idx) in hops:
        hops_by_seg.setdefault(idx, []).append((xc, yc))

    for i in range(n_segs):
        x1, y1 = pts[2*i],   pts[2*i+1]
        x2, y2 = pts[2*i+2], pts[2*i+3]
        seg_hops = hops_by_seg.get(i, [])
        if not seg_hops:
            path.lineTo(x2, y2)
            continue
        # Ordenar hops por distancia desde (x1, y1)
        dx, dy = x2 - x1, y2 - y1
        seg_L = math.hypot(dx, dy)
        if seg_L < 1e-3:
            path.lineTo(x2, y2)
            continue
        ux, uy = dx / seg_L, dy / seg_L
        nx, ny = -uy, ux  # perpendicular hacia "arriba"
        def _dist_from_start(p):
            return (p[0] - x1) * ux + (p[1] - y1) * uy
        seg_hops_sorted = sorted(seg_hops, key=_dist_from_start)
        # Dibujar lineTo hasta cada hop, hop con arc, y continuar
        for (xc, yc) in seg_hops_sorted:
            # Punto antes del cruce
            px = xc - HOP_RADIUS * ux
            py = yc - HOP_RADIUS * uy
            path.lineTo(px, py)
            # Punto después
            qx = xc + HOP_RADIUS * ux
            qy = yc + HOP_RADIUS * uy
            # Control points del cubicTo para aproximar un arc de 180°.
            # Factor 0.55 hace que el control sea apex del semicírculo.
            cp1x = px + HOP_RADIUS * nx * 1.3
            cp1y = py + HOP_RADIUS * ny * 1.3
            cp2x = qx + HOP_RADIUS * nx * 1.3
            cp2y = qy + HOP_RADIUS * ny * 1.3
            path.cubicTo(cp1x, cp1y, cp2x, cp2y, qx, qy)
        # Después de todos los hops, lineTo al final del segmento
        path.lineTo(x2, y2)
    return path


class _GhostStreamHandle(QGraphicsEllipseItem):
    """Handle fantasma en un bend point del auto-routing.  Click → bakea
    los bends del auto-route en model.waypoints y aparecen handles reales
    draggables.  Visualmente más chico y traslúcido que los reales."""

    RADIUS = 4
    HIT_RADIUS = 12   # hit area más generosa que el visual

    def shape(self):
        from PySide6.QtCore import QRectF
        path = QPainterPath()
        r = self.HIT_RADIUS
        path.addEllipse(QRectF(-r, -r, 2*r, 2*r))
        return path

    def boundingRect(self):
        from PySide6.QtCore import QRectF
        r = self.HIT_RADIUS
        return QRectF(-r, -r, 2*r, 2*r)

    def __init__(self, stream_item: "StreamItem", x: float, y: float):
        r = self.RADIUS
        super().__init__(-r, -r, 2*r, 2*r)
        self._stream_item = stream_item
        self.setBrush(QBrush(QColor(31, 111, 235, 130)))
        self.setPen(QPen(QColor("#ffffff"), 1.0))
        self.setZValue(19)        # encima de BlockItem (z=10)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click para hacer este bend editable, luego arrastrá")
        self.setPos(x, y)

    def mousePressEvent(self, event):
        si = self._stream_item
        pts = getattr(si, '_last_pts', None)
        if pts and len(pts) >= 6:
            # bakear todos los bend points interiores en model.waypoints
            interior = []
            for i in range(2, len(pts) - 2, 2):
                interior.append([pts[i], pts[i+1]])
            si.model.waypoints = interior
        else:
            # corner case: stream sin bends visibles, agregamos uno en
            # la posición clickeada
            si.model.waypoints = [[self.pos().x(), self.pos().y()]]
        si.update_path()
        event.accept()


class _EndpointHandle(QGraphicsEllipseItem):
    """Handle draggable de un endpoint del stream (START o END).

    A diferencia del waypoint handle (_StreamHandle), este puede
    DESCONECTAR del bloque al ser arrastrado lejos de cualquier puerto,
    o CONECTAR/RECONECTAR a un puerto distinto al soltarlo cerca.

    role: 'start' (controla src/start_xy) | 'end' (controla dst/end_xy)
    """

    RADIUS_OUTER = 7        # tamaño VISUAL (anillo naranja)
    RADIUS_INNER = 4
    HIT_RADIUS   = 18       # HIT AREA invisible — el endpoint cae sobre el
                            # puerto del bloque, así que sin un área grande
                            # los clicks al lado activan el bloque (movable)
    SNAP_RADIUS  = 35.0     # px scene: rango de snap a un puerto.  Generoso
                            # (~1.75 grid steps) para que el user no tenga
                            # que ser perfectamente preciso al arrastrar el
                            # endpoint cerca del puerto del bloque.

    def shape(self):
        """Hit area ~36px diámetro para fácil agarre del handle."""
        from PySide6.QtCore import QRectF
        path = QPainterPath()
        r = self.HIT_RADIUS
        path.addEllipse(QRectF(-r, -r, 2*r, 2*r))
        return path

    def boundingRect(self):
        from PySide6.QtCore import QRectF
        r = self.HIT_RADIUS
        return QRectF(-r, -r, 2*r, 2*r)

    def __init__(self, stream_item: "StreamItem", role: str):
        r = self.RADIUS_OUTER
        super().__init__(-r, -r, 2*r, 2*r)
        self._stream_item = stream_item
        self._role = role           # 'start' | 'end'
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        # estilo: doble anillo (afuera blanco, dentro naranja) para
        # distinguir endpoints de waypoints regulares (azules)
        self.setBrush(QBrush(QColor("#ffffff")))
        self.setPen(QPen(QColor("#ef6c00"), 2.0))   # naranja
        # zValue alto para asegurar que esté POR ENCIMA del BlockItem
        # (z=10) — sino el bloque al que el stream se conecta tapa el
        # handle y los clicks van al bloque, no al handle.
        self.setZValue(21)
        self.setCursor(Qt.SizeAllCursor)
        # snap target visual (círculo verde que aparece sobre el puerto
        # al que vamos a snappear)
        self._snap_marker = None
        # Estado del drag — solo el threshold protege la desconexion
        # accidental. Init explicito para no depender de mousePressEvent
        # haber corrido antes del primer itemChange (caso edge: snap
        # programatico desde BlockItem._snap_nearby_floating_endpoints
        # o algun setPos en init).
        self._press_pos = None
        self._drag_committed = False

        # Setear posición desde el modelo o desde el puerto
        self._sync_pos_from_model()

    def _sync_pos_from_model(self):
        """Lee la pos actual del endpoint (puerto si conectado, xy si
        flotante) y posiciona el handle ahí.

        IMPORTANTE: apagamos ItemSendsGeometryChanges durante el setPos
        para que itemChange NO se dispare. Si se disparara, su rama
        ItemPositionHasChanged haria s.src = -1 (pensando que es un
        drag del usuario) y wipearia la conexion al puerto."""
        si = self._stream_item
        s  = si.model
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
        try:
            if self._role == "start":
                b = si.fs.blocks.get(s.src)
                if b is not None:
                    _, x, y = si._resolve_port(b, s.src_port, "right")
                    self.setPos(x, y)
                elif s.start_xy and len(s.start_xy) >= 2:
                    self.setPos(float(s.start_xy[0]), float(s.start_xy[1]))
            else:
                b = si.fs.blocks.get(s.dst)
                if b is not None:
                    _, x, y = si._resolve_port(b, s.dst_port, "left")
                    self.setPos(x, y)
                elif s.end_xy and len(s.end_xy) >= 2:
                    self.setPos(float(s.end_xy[0]), float(s.end_xy[1]))
        finally:
            self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

    def _find_snap_target(self, scene_pos: QPointF):
        """Busca un puerto de un bloque cercano (dentro de SNAP_RADIUS).
        Devuelve (block_id, port_name, port_xy) o None si no hay match.

        Excluye el bloque que ya está conectado al OTRO endpoint del
        stream (no permite conectar src y dst al mismo bloque) y
        excluye puertos ya ocupados por otro stream — para no formar
        conexiones que validate_connection considera 'puerto duplicado'.
        """
        si = self._stream_item
        editor = getattr(si, "editor", None)
        if editor is None:
            return None
        # bloque del OTRO endpoint (para no conectar a sí mismo)
        s = si.model
        other_bid = s.dst if self._role == "start" else s.src
        best = None
        best_d2 = self.SNAP_RADIUS ** 2
        for bid, bitem in editor.block_items_iter():
            if bid == other_bid:
                continue
            for port_name, port_ell in bitem.port_items.items():
                # coords absolutas del puerto en la escena
                p_scene = port_ell.mapToScene(port_ell.boundingRect().center())
                dx = p_scene.x() - scene_pos.x()
                dy = p_scene.y() - scene_pos.y()
                d2 = dx*dx + dy*dy
                if d2 < best_d2:
                    best_d2 = d2
                    best = (bid, port_name, p_scene)
        return best

    def _show_snap_marker(self, scene_pos: QPointF):
        """Pinta un círculo verde sobre el puerto al que vamos a snappear,
        para feedback visual durante el drag."""
        from PySide6.QtWidgets import QGraphicsEllipseItem as _E
        if self._snap_marker is None:
            self._snap_marker = _E(-10, -10, 20, 20)
            self._snap_marker.setBrush(QBrush(QColor(46, 125, 50, 80)))
            self._snap_marker.setPen(QPen(QColor("#2e7d32"), 2.0))
            self._snap_marker.setZValue(22)        # por encima del handle
            self._snap_marker.setAcceptedMouseButtons(Qt.NoButton)
            if self.scene():
                self.scene().addItem(self._snap_marker)
        self._snap_marker.setPos(scene_pos)
        self._snap_marker.setVisible(True)

    def _hide_snap_marker(self):
        if self._snap_marker is not None:
            self._snap_marker.setVisible(False)

    # Distancia mínima de drag (px) para "commitear" la desconexión del
    # puerto. Debe ser > GRID_STEP (20 px), si no el primer step de
    # grilla (20px en el itemChange snap) ya supera el threshold y
    # desconecta inmediatamente — perdiendo toda la proteccion.
    # 28 px = 1.4 grid steps: necesitas mover 2 celdas de grilla para
    # que la desconexion se compromete. Mover 1 celda y soltar = no-op
    # (snap-back al puerto).
    DRAG_THRESHOLD = 28.0

    def mousePressEvent(self, event):
        """Al iniciar drag: reset del flag de 'commit'."""
        if event.button() == Qt.LeftButton:
            self._press_pos = QPointF(self.pos())   # pos del handle al apretar
            self._drag_committed = False
        super().mousePressEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            # Snap a grilla durante el drag (suave)
            nx = round(value.x() / GRID_STEP) * GRID_STEP
            ny = round(value.y() / GRID_STEP) * GRID_STEP
            value = QPointF(nx, ny)
        elif change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            si = self._stream_item
            s = si.model
            # GATE: solo modificar el modelo si el drag superó el
            # threshold. Antes, el más mínimo movimiento (incluso por
            # click sin querer cerca del puerto) hacía s.src = -1 →
            # 'desconexión accidental' que parecía 'el bloque se va a
            # Jupiter' (el endpoint seguía al cursor, no el bloque).
            if not self._drag_committed:
                pp = self._press_pos
                if pp is None:
                    # Sin mousePressEvent previo (e.g. setPos programatico
                    # con flag accidental, o init weirdo). No commitear:
                    # el handle se mueve visualmente, modelo intacto.
                    return super().itemChange(change, value)
                dx = self.pos().x() - pp.x()
                dy = self.pos().y() - pp.y()
                if dx*dx + dy*dy < self.DRAG_THRESHOLD ** 2:
                    # Movimiento todavía dentro del umbral — visual
                    # se mueve (Qt lo hizo), pero modelo intacto.
                    return super().itemChange(change, value)
                self._drag_committed = True

            # Threshold superado — committear disconnect
            new_xy = [self.pos().x(), self.pos().y()]
            if self._role == "start":
                s.src = -1
                s.src_port = ""
                s.start_xy = new_xy
            else:
                s.dst = -1
                s.dst_port = ""
                s.end_xy = new_xy
            # snap target visual
            tgt = self._find_snap_target(QPointF(*new_xy))
            if tgt is not None:
                self._show_snap_marker(tgt[2])
            else:
                self._hide_snap_marker()
            si.update_path(rebuild_handles=False)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        """Al soltar el handle: si hay un puerto cerca, snap+conectar.
        Si no, dejar flotante con las coords actuales.

        Caso especial: si el drag no superó el threshold (movimiento
        accidental al clickear), restaurar la pos del handle al modelo
        original (el modelo nunca fue modificado, solo la pos visual).
        """
        if not getattr(self, "_drag_committed", False):
            # Drag accidental sin commit — restaurar handle al modelo
            self._sync_pos_from_model()
            self._hide_snap_marker()
            super().mouseReleaseEvent(event)
            self._press_pos = None
            return

        si = self._stream_item
        s  = si.model
        scene_pos = self.pos()    # ya está en scene coords (handle es scene-level)
        tgt = self._find_snap_target(scene_pos)
        if tgt is not None:
            bid, port_name, p_scene = tgt
            if self._role == "start":
                s.src = bid
                s.src_port = port_name
                s.start_xy = []
            else:
                s.dst = bid
                s.dst_port = port_name
                s.end_xy = []
            self.setPos(p_scene)
        else:
            # Mantener flotante: xy ya quedó guardado en itemChange
            pass
        self._hide_snap_marker()
        # Refresh
        si.update_path()
        # Notificar al editor que algo cambió (mark_dirty)
        editor = getattr(si, "editor", None)
        if editor is not None and hasattr(editor, "_mark_dirty"):
            editor._mark_dirty()
        super().mouseReleaseEvent(event)
        # Reset flags al final
        self._press_pos = None
        self._drag_committed = False


class BlockItem(QGraphicsItemGroup):
    """Bloque del flowsheet renderizado en el canvas.

    Compone:
      - QGraphicsRectItem (cuerpo)
      - QGraphicsSimpleTextItem (nombre/tag)
      - QGraphicsSimpleTextItem (categoría + S)
      - QGraphicsEllipseItem por cada puerto del eq_type

    Mantiene una referencia al `Block` del modelo (`self.model`) para
    sincronizar posición al mover.
    """

    PORT_RADIUS = 4

    def __init__(self, block: Block, editor=None):
        super().__init__()
        self.model: Block = block
        self.editor = editor             # FlowsheetMainWindow (para callbacks)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        # IMPORTANTE: setHandlesChildEvents = True (default) — el grupo
        # captura los clicks de TODOS sus hijos y aplica ItemIsMovable.
        # Si lo seteamos a False, los hijos (rect invisible, pixmap del
        # SVG, ports, textos) reciben los clicks individualmente y el
        # bloque queda inerte porque ninguno de ellos es movable.
        self.setHandlesChildEvents(True)

        # Dimensiones del símbolo PFD (varían por equipo).  Fallback al
        # tamaño legacy 130×60 si el eq_type no tiene símbolo nuevo.
        self.W, self.H = pfd.block_dims(block.eq_type)

        # --- halo de status (semáforo solver) ---
        # Rectángulo redondeado AFUERA del símbolo, con borde coloreado
        # según el último solve (verde/azul/amarillo/rojo).  Se pinta
        # ANTES del símbolo (z menor) para que el SVG quede por encima.
        # Default: azul stale (sin solve todavía).
        self._status: str = "stale"
        halo_pad = 6
        # NOTA: usamos _StatusHaloItem (no QGraphicsRectItem) para que
        # el halo NO contribuya al hit region del bloque.  Sino el
        # área extendida 6px tapa los endpoint handles de los streams
        # que se conectan a este bloque y los clicks van al bloque
        # (movable) en vez de los handles.
        self.status_halo = _StatusHaloItem(
            -halo_pad, -halo_pad,
            self.W + 2*halo_pad, self.H + 2*halo_pad,
            parent=self)
        self.status_halo.setBrush(Qt.NoBrush)
        self.status_halo.setPen(QPen(COLOR_STATUS_UNRUN, 1.5, Qt.SolidLine))
        self.status_halo.setZValue(-1.0)   # debajo del símbolo
        self.status_halo.setAcceptedMouseButtons(Qt.NoButton)

        # --- rect base (invisible, solo hit-target) ---
        # El símbolo PFD ES el bloque visible; el rect cumple rol de
        # hit-box para clicks en zonas vacías del símbolo.
        self.rect = _RoundedRectBody(0, 0, self.W, self.H, parent=self)
        self.rect.setBrush(QBrush(QColor(0, 0, 0, 1)))  # invisible, hittable
        self.rect.setPen(Qt.NoPen)
        self.rect.setZValue(-0.5)

        spec = eq.EQUIPMENT_DATA.get(block.eq_type, {})
        unit = spec.get("S_unit", "")
        cat  = spec.get("categoria", "")
        self.decoration_items = []   # items hijos que decoran según categoría
        self._draw_category_decoration(cat, block.eq_type)

        # --- textos (IBM Plex si está disponible, fallback al sistema) ---
        sans = pfd_fonts.SANS if pfd_fonts.available() else "Segoe UI"
        mono = pfd_fonts.MONO if pfd_fonts.available() else "Consolas"
        f_title = QFont(sans, 9, QFont.Bold)

        # Tag: AFUERA del bloque, encima, centrado (estilo PFD industrial).
        # La spec (S = … m²) NO se muestra en el bloque para reducir clutter
        # — se ve en el tooltip al hover y en el panel de propiedades.
        self.text_name = QGraphicsSimpleTextItem(block.name, parent=self)
        self.text_name.setFont(f_title)
        self.text_name.setBrush(QBrush(COLOR_BLOCK_TEXT))
        br = self.text_name.boundingRect()
        self.text_name.setPos((self.W - br.width()) / 2, -br.height() - 4)
        self.text_name.setZValue(2)
        # text_sub queda como atributo None para no romper código que lo
        # referencia (e.g., _update_status, undo); el sub vive en tooltip.
        self.text_sub = None

        # ---- badge de DUTY (kW) — visible siempre que duty != 0 ----
        # Posición: AL LADO del bloque (derecha, alineado al centro).
        # Color: rojo si Q > 0 (calienta = consume utility), azul si Q
        # < 0 (enfría = consume agua/aire).  Permite al user ver de un
        # golpe los requerimientos energéticos sin abrir tooltips.
        # Icono: ↑Q heating, ↓Q cooling.
        self.duty_badge = QGraphicsSimpleTextItem("", parent=self)
        self.duty_badge.setFont(QFont(mono, 8, QFont.Bold))
        self.duty_badge.setPos(self.W + 6, self.H / 2 - 7)
        self.duty_badge.setZValue(3)
        self._update_duty_badge()

        # ---- Badge HYSYS icon (esquina inferior izquierda) ----
        # Pequeño ícono del tipo de equipo (estilo HYSYS line-art) para
        # identificar visualmente el bloque rápido — sin reemplazar el
        # símbolo PFD detallado que dibuja pfd_symbols.
        try:
            from icons import icon_for_eq_type, make_qicon
            from PySide6.QtWidgets import QGraphicsPixmapItem
            icon_id = icon_for_eq_type(block.eq_type)
            ic = make_qicon(icon_id, color="#9aa5b1", size=16)
            if ic is not None:
                self.type_badge = QGraphicsPixmapItem(
                    ic.pixmap(14, 14), parent=self)
                self.type_badge.setPos(2, self.H - 16)
                self.type_badge.setZValue(2.5)
                self.type_badge.setAcceptedMouseButtons(Qt.NoButton)
                self.type_badge.setOpacity(0.7)
            else:
                self.type_badge = None
        except Exception:
            self.type_badge = None

        # --- puertos ---
        self.port_items: dict = {}     # port_name → QGraphicsEllipseItem
        self._render_ports()

        self.setPos(block.x, block.y)
        self.setZValue(10)
        self.setAcceptHoverEvents(True)
        self._update_tooltip()

    # ---------------------------------------------------
    # DECORACIÓN POR CATEGORÍA (símbolos PFD simplificados)
    # ---------------------------------------------------

    def _add_deco_line(self, x1, y1, x2, y2, width=1.5, color=None):
        line = QGraphicsLineItem(x1, y1, x2, y2, parent=self)
        pen = QPen(color or COLOR_BLOCK_BORDER, width)
        line.setPen(pen)
        self.decoration_items.append(line)
        return line

    def _add_deco_path(self, path: QPainterPath, width=1.5, color=None,
                       fill=None):
        item = QGraphicsPathItem(path, parent=self)
        item.setPen(QPen(color or COLOR_BLOCK_BORDER, width))
        if fill is not None:
            item.setBrush(QBrush(fill))
        self.decoration_items.append(item)
        return item

    def _draw_category_decoration(self, category, eq_type):
        """Renderiza el símbolo PFD del eq_type (catálogo pfd_symbols).

        El símbolo se renderiza a su tamaño natural (W × H del viewBox).
        Si no hay símbolo en el catálogo, queda solo el rect (invisible)
        + los textos.
        """
        self._svg_mode = False

        svg_str = pfd.wrap_svg(pfd.EQ_TYPE_TO_SYMBOL.get(eq_type, ""),
                                w=self.W, h=self.H)
        if not svg_str:
            return  # sin símbolo: rect invisible + textos solamente

        try:
            pixmap = _get_svg_pixmap(eq_type, int(self.W), int(self.H),
                                      svg_str=svg_str)
        except Exception:
            pixmap = None
        if pixmap is None or pixmap.isNull():
            return

        try:
            from PySide6.QtWidgets import QGraphicsPixmapItem
            pix_item = QGraphicsPixmapItem(pixmap, parent=self)
            # NO usar setScale(0.5): el pixmap ya tiene
            # setDevicePixelRatio(2) que hace que Qt reporte un
            # boundingRect en unidades lógicas (la mitad del pixel
            # size).  Aplicar setScale(0.5) además habría sido una
            # doble reducción → SVG aparecía a 1/4 del área del bloque.
            pix_item.setPos(0, 0)
            pix_item.setZValue(0)
            pix_item.setTransformationMode(Qt.SmoothTransformation)
            self.decoration_items.append(pix_item)
            self._svg_mode = True
        except Exception:
            pass

    def _render_ports(self):
        r = self.PORT_RADIUS
        coords = pfd.port_coords(self.model.eq_type, self.W, self.H)
        # Stubs: pequeñas líneas desde el puerto hacia el cuerpo del símbolo,
        # para que visualmente el puerto se conecte al SVG (los SVGs tienen
        # margen interno y los puertos quedan al borde del bounding box).
        cx_blk, cy_blk = self.W / 2, self.H / 2
        for pname, (cx, cy) in coords.items():
            # vector hacia el centro del bloque
            dx, dy = cx_blk - cx, cy_blk - cy
            d = (dx * dx + dy * dy) ** 0.5
            stub_len = 8.0
            if d > stub_len:
                ux, uy = dx / d, dy / d
                stub = QGraphicsLineItem(
                    cx, cy, cx + ux * stub_len, cy + uy * stub_len,
                    parent=self,
                )
                stub.setPen(QPen(QColor("#0d0d0d"), 1.6))
                stub.setZValue(0.5)   # encima del rect, debajo del puerto
                self.decoration_items.append(stub)
            ell = QGraphicsEllipseItem(cx - r, cy - r, 2*r, 2*r, parent=self)
            ell.setBrush(QBrush(COLOR_PORT_FREE))
            ell.setPen(QPen(QColor("#333333"), 1))
            ell.setData(0, pname)
            ell.setZValue(3)
            self.port_items[pname] = ell

    def update_port_colors(self, used_ports: set):
        """Marca puertos conectados en azul, libres en gris."""
        for pname, ell in self.port_items.items():
            if pname in used_ports:
                ell.setBrush(QBrush(COLOR_PORT_CONN))
            else:
                ell.setBrush(QBrush(COLOR_PORT_FREE))

    def _update_tooltip(self):
        """Tooltip al hover con info del bloque (HTML)."""
        b = self.model
        spec = eq.EQUIPMENT_DATA.get(b.eq_type, {})
        ports = ep.get_ports(b.eq_type)
        port_list = ", ".join(ports.keys()) if ports else "(sin puertos)"
        lines = [
            f"<b>{b.name}</b>",
            f"<span style='color:#666;'>{b.eq_type}</span>",
            f"S = {b.S:g} {spec.get('S_unit','')}",
        ]
        if b.n > 1:
            lines.append(f"N° unidades: {b.n}")
        if b.duty:
            lines.append(f"Duty: {b.duty:+g} kW")
        if b.heat_source:
            lines.append(f"Utility: {b.heat_source}")
        lines.append(f"<span style='color:#888; font-size:8pt;'>"
                     f"Puertos: {port_list}</span>")
        self.setToolTip("<br>".join(lines))

    def set_selected_visual(self, selected: bool):
        if selected:
            # halo de selección: borde índigo punteado alrededor del
            # bloque, sólo visible al estar seleccionado.
            self.rect.setPen(QPen(COLOR_BLOCK_BORDER_SEL, 1.5, Qt.DashLine))
        else:
            # sin selección el rect queda invisible — el símbolo SVG
            # es la representación visual del bloque, no la caja.
            self.rect.setPen(Qt.NoPen)

    def _update_duty_badge(self):
        """Actualiza el badge '↑Q +X kW' al lado del bloque.

        Rojo (↑) si endo/heating (duty > 0).  Azul (↓) si exo/cooling
        (duty < 0).  Oculto si duty == 0.
        """
        if not hasattr(self, "duty_badge") or self.duty_badge is None:
            return
        q = self.model.duty
        if abs(q) < 0.5:
            self.duty_badge.setText("")
            return
        arrow = "↑Q" if q > 0 else "↓Q"
        color = QColor("#c41e3a") if q > 0 else QColor("#1565c0")
        # Formato compacto: kW si <1000, MW si mayor
        if abs(q) >= 1000:
            val = f"{q/1000:+.2f} MW"
        elif abs(q) >= 10:
            val = f"{q:+.0f} kW"
        else:
            val = f"{q:+.1f} kW"
        self.duty_badge.setText(f"{arrow} {val}")
        self.duty_badge.setBrush(QBrush(color))

    def set_status(self, status: str):
        """Aplica color de status (ok / warning / error / unrun / stale)
        al halo de status del bloque.  Default 'stale' = azul (sin
        solve corrido o flowsheet editado posteriormente)."""
        self._status = status or "stale"
        color = STATUS_COLORS.get(self._status, COLOR_STATUS_UNRUN)
        # Línea más gruesa para error, sólida para ok, punteada para stale
        if self._status == "error":
            pen = QPen(color, 2.5, Qt.SolidLine)
        elif self._status == "warning":
            pen = QPen(color, 2.0, Qt.SolidLine)
        elif self._status == "ok":
            pen = QPen(color, 1.2, Qt.SolidLine)
        else:    # stale / unrun
            pen = QPen(color, 1.2, Qt.DashLine)
        self.status_halo.setPen(pen)

    def itemChange(self, change, value):
        """Sync posición al modelo + refresh streams conectados.

        Group move: si hay varios bloques seleccionados, Qt mueve
        todos juntos.  Cada uno hace su propio itemChange con su
        nueva pos.  Snap aplicado individualmente preserva el
        alineamiento porque el delta es el mismo round.
        """
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            new_pos: QPointF = value
            nx = round(new_pos.x() / GRID_STEP) * GRID_STEP
            ny = round(new_pos.y() / GRID_STEP) * GRID_STEP
            value = QPointF(nx, ny)
        elif change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            self.model.x = self.pos().x()
            self.model.y = self.pos().y()
            if self.editor is not None:
                self.editor.refresh_streams_of(self.model.id)
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        """Doble-click sobre el bloque → abrir editor."""
        if self.editor is not None:
            self.editor.edit_block(self.model)
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        """Si hay una conexión pendiente, este click completa el stream."""
        if (event.button() == Qt.LeftButton
            and self.editor is not None
            and self.editor.is_connecting()):
            self.editor.complete_connection(self.model.id)
            event.accept()
            return
        # snapshot del estado antes del drag (para undo)
        if (event.button() == Qt.LeftButton and self.editor is not None
            and self.editor._drag_before_snapshot is None):
            self.editor._drag_before_snapshot = self.editor.begin_action()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        # IMÁN BIDIRECCIONAL: al soltar el bloque tras un drag, si algún
        # endpoint flotante quedó cerca de un puerto de ESTE bloque, snap.
        # No durante el drag (sería intrusivo), solo al release.
        if event.button() == Qt.LeftButton and self.editor is not None:
            self._snap_nearby_floating_endpoints()
        # push undo si hubo un drag
        if (event.button() == Qt.LeftButton and self.editor is not None
            and self.editor._drag_before_snapshot is not None):
            self.editor.end_action("Mover", self.editor._drag_before_snapshot)
            self.editor._drag_before_snapshot = None

    def _snap_nearby_floating_endpoints(self):
        """Imán block→stream: para cada endpoint flotante de cualquier
        stream, si quedó dentro de SNAP_RADIUS de un puerto de este
        bloque, conecta el endpoint a ese puerto.

        Complementa el imán stream→block existente (_EndpointHandle):
        ahora también moviendo el BLOQUE cerca de una flecha flotante
        se imanta.  Solo se evalúa al SOLTAR (mouseReleaseEvent), no
        durante el drag, para evitar conexiones accidentales al pasar
        por encima."""
        from PySide6.QtCore import QPointF
        if self.editor is None or self.scene() is None:
            return
        SNAP_R = _EndpointHandle.SNAP_RADIUS
        SNAP_R2 = SNAP_R * SNAP_R
        bid = self.model.id
        snapped_any = False
        for s in list(self.editor.fs.streams.values()):
            # Probar endpoint START si está flotante
            for role, src_or_dst, xy_field, port_field, other_field in (
                ("start", "src", "start_xy", "src_port", "dst"),
                ("end",   "dst", "end_xy",   "dst_port", "src"),
            ):
                if getattr(s, src_or_dst) != -1:
                    continue   # ese extremo ya está conectado
                # Evitar que un stream conecte src y dst al mismo bloque
                if getattr(s, other_field) == bid:
                    continue
                xy = getattr(s, xy_field, []) or []
                if len(xy) < 2:
                    continue
                ex, ey = float(xy[0]), float(xy[1])
                best = None
                best_d2 = SNAP_R2
                for port_name, port_ell in self.port_items.items():
                    p = port_ell.mapToScene(port_ell.boundingRect().center())
                    dx, dy = p.x() - ex, p.y() - ey
                    d2 = dx*dx + dy*dy
                    if d2 < best_d2:
                        best_d2 = d2
                        best = (port_name, p)
                if best is None:
                    continue
                port_name, p_scene = best
                setattr(s, src_or_dst, bid)
                setattr(s, port_field, port_name)
                if xy_field == "start_xy":
                    s.start_xy = []
                else:
                    s.end_xy = []
                item = self.scene().stream_items.get(s.id)
                if item is not None:
                    item.update_path()
                snapped_any = True
        if snapped_any and hasattr(self.editor, "_mark_dirty"):
            self.editor._mark_dirty()

    def contextMenuEvent(self, event):
        """Click derecho → menú contextual con íconos HYSYS."""
        if self.editor is None:
            return
        menu = QMenu()
        title = menu.addAction(self.model.name)
        title.setEnabled(False)
        menu.addSeparator()
        # Íconos del set HYSYS (color text-primary)
        mk = getattr(self.editor, "_mk_icon", None)
        icol = getattr(self.editor, "_icon_color", "#3a3a3a")
        ic_connect = mk("act-connect", color=icol, size=16) if mk else QIcon()
        ic_edit    = mk("act-edit",    color=icol, size=16) if mk else QIcon()
        ic_delete  = mk("edit-delete", color="#c41e3a", size=16) if mk else QIcon()
        menu.addAction(ic_connect or QIcon(), "Conectar desde acá…",
                       lambda: self.editor.start_connection(self.model.id))
        menu.addAction(ic_edit or QIcon(), "Editar propiedades… (doble-click)",
                       lambda: self.editor.edit_block(self.model))
        menu.addAction(ic_delete or QIcon(), "Borrar",
                       lambda: self.editor.delete_block(self.model.id))
        menu.exec(event.screenPos())
        event.accept()


# ======================================================
# CORRIENTE COMO QGraphicsPathItem
# ======================================================

class StreamItem(QGraphicsPathItem):
    """Corriente del flowsheet: polyline ortogonal + label con fondo.

    Mantiene referencia al Stream del modelo y se redibuja vía
    `update_path(fs)` cuando los bloques se mueven."""

    def __init__(self, stream: Stream, fs: Flowsheet, editor=None):
        super().__init__()
        self.model: Stream = stream
        self.fs: Flowsheet = fs
        self.editor = editor      # FlowsheetMainWindow (para edit dialog)
        self.setZValue(5)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)

        # punta de flecha al final del stream (triángulo relleno,
        # ítem separado para que no comparta stroke con la línea).
        self.arrow_head = QGraphicsPolygonItem()
        self.arrow_head.setPen(QPen(Qt.NoPen))
        self.arrow_head.setZValue(5.5)

        # handles draggables (uno por waypoint).  Se crean/muestran
        # solo cuando el stream está seleccionado.
        self._handles: list = []

        # status del solver (verde/ámbar/rojo/azul).  Default "stale"
        # hasta que solve() corra y populé el status.
        self._status: str = "stale"

        # Flag de hover para engrosar la línea al pasar mouse.
        self._hovered: bool = False

        # Flechas direccionales intermedias: pequeñas chevrons '>>' a
        # lo largo del path indicando dirección del flujo (no solo
        # al final).  QGraphicsPolygonItems separados, z entre línea
        # y label.  Se actualizan en update_path.
        self.direction_arrows: list = []
        # Offset acumulado para animación — los chevrons se "mueven"
        # a lo largo del path cuando el editor está en modo animado.
        # Lo modula EditorMainWindow._animate_streams (timer).
        self._anim_offset: float = 0.0

        # label estilo PFD industrial: pill (rounded rect blanco con
        # borde del color del stream) + nombre + flujo en mono.
        self.label_bg = _RoundedRectBody(0, 0, 10, 10)
        self.label_bg.RADIUS = 3
        self.label_bg.setBrush(QBrush(QColor("#ffffff")))
        self.label_bg.setPen(QPen(Qt.NoPen))    # se setea en update_path con el color
        self.label_bg.setZValue(6)

        mono = pfd_fonts.MONO if pfd_fonts.available() else "Consolas"
        self.label_name = QGraphicsSimpleTextItem()
        self.label_name.setFont(QFont(mono, 7, QFont.Medium))
        self.label_name.setZValue(7)

        self.label_flow = QGraphicsSimpleTextItem()
        self.label_flow.setFont(QFont(mono, 7))
        self.label_flow.setBrush(QBrush(QColor("#6b7280")))   # gris suave
        self.label_flow.setZValue(7)

        self.update_path()

    def add_to_scene(self, scene: QGraphicsScene):
        scene.addItem(self)
        scene.addItem(self.arrow_head)
        scene.addItem(self.label_bg)
        scene.addItem(self.label_name)
        scene.addItem(self.label_flow)
        # Forzar refresh de handles AHORA que el stream está en escena.
        # Sin esto, los endpoint handles (naranja) de streams flotantes
        # no aparecen hasta que el user clickea el stream — y como los
        # handles son lo que se arrastra a un puerto, la conexión es
        # imposible sin haberlo seleccionado primero. _rebuild_handles
        # con scene=None es no-op (ver guard adentro), así que ahora
        # que scene existe sí crea los _EndpointHandle naranjas.
        self._rebuild_handles()

    def remove_from_scene(self, scene: QGraphicsScene):
        # remover handles de waypoints si estaban activos
        for h in self._handles:
            if h.scene() is scene:
                scene.removeItem(h)
        self._handles.clear()
        # remover chevrons direccionales
        for arr in self.direction_arrows:
            if arr.scene() is scene:
                scene.removeItem(arr)
        self.direction_arrows.clear()
        for item in (self, self.arrow_head, self.label_bg,
                      self.label_name, self.label_flow):
            if item.scene() is scene:
                scene.removeItem(item)

    def _color(self):
        # Selección siempre tiene prioridad para feedback inmediato.
        if self.isSelected():
            return QColor(STREAM_ROLE_COLORS_SEL.get(self.model.role, "#c62828"))
        # Status crítico sobreescribe el color por role (error o warning
        # vienen del último solve y son los más informativos para el user).
        if self._status == "error":
            return COLOR_STATUS_ERROR
        if self._status == "warning":
            return COLOR_STATUS_WARN
        if self._status in ("stale", "unrun"):
            # gris-azul tenue para indicar "no resuelto / sin verificar"
            return QColor("#9aa5b1")
        # status == "ok" o cualquier otro: color normal por role
        return QColor(STREAM_ROLE_COLORS.get(self.model.role, "#37474f"))

    def hoverEnterEvent(self, event):
        """Engrosa la línea al hover para feedback visual."""
        self._hovered = True
        self.update_path(rebuild_handles=False)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update_path(rebuild_handles=False)
        super().hoverLeaveEvent(event)

    def _draw_direction_arrows(self, pts: list):
        """Dibuja pequeños chevrons '>' a lo largo del path indicando
        dirección del flujo.  Espaciado aproximado: cada 130 px.

        Limpia los chevrons previos y crea nuevos según los segmentos.
        """
        import math
        # Limpiar previos
        scene = self.scene()
        for arr in self.direction_arrows:
            if scene is not None and arr.scene() is scene:
                scene.removeItem(arr)
        self.direction_arrows.clear()
        if scene is None or len(pts) < 4:
            return
        color = self._color()
        # Calcular puntos cada ~130 px a lo largo del path
        SPACING = 130.0
        ARROW_SIZE = 5.0
        WING = 3.5
        # Acumular distancia y posicionar
        seg_lengths = []
        for i in range(0, len(pts) - 2, 2):
            dx = pts[i+2] - pts[i]
            dy = pts[i+3] - pts[i+1]
            seg_lengths.append((math.hypot(dx, dy), dx, dy))
        total = sum(L for L, _, _ in seg_lengths)
        if total < SPACING:
            return    # path corto: solo la flecha del final basta
        # Colocar chevrons cada SPACING desde 0.4·SPACING (offset
        # para no chocar con la pill central).  _anim_offset
        # permite que se desplacen para animación de flujo.
        offset_dist = (SPACING * 0.5 + self._anim_offset) % SPACING
        while offset_dist < total - 30:    # 30px margen al final
            # Encontrar el segmento donde cae offset_dist
            d_remaining = offset_dist
            for i, (L, dx, dy) in enumerate(seg_lengths):
                if d_remaining <= L:
                    if L < 1e-3:
                        continue
                    ux, uy = dx / L, dy / L
                    cx = pts[2*i] + ux * d_remaining
                    cy = pts[2*i+1] + uy * d_remaining
                    # chevron triangular apuntando en (ux, uy)
                    nx, ny = -uy, ux  # perpendicular
                    tip = QPointF(cx + ARROW_SIZE * ux, cy + ARROW_SIZE * uy)
                    b1  = QPointF(cx - ARROW_SIZE * ux + WING * nx,
                                    cy - ARROW_SIZE * uy + WING * ny)
                    b2  = QPointF(cx - ARROW_SIZE * ux - WING * nx,
                                    cy - ARROW_SIZE * uy - WING * ny)
                    arr = QGraphicsPolygonItem(QPolygonF([tip, b1, b2]))
                    arr.setBrush(QBrush(color))
                    arr.setPen(QPen(Qt.NoPen))
                    arr.setZValue(5.3)
                    scene.addItem(arr)
                    self.direction_arrows.append(arr)
                    break
                d_remaining -= L
            offset_dist += SPACING

    def set_status(self, status: str):
        """Aplica status del solver y fuerza repintado (color de la línea
        y del label se derivan de _color, que ahora chequea status)."""
        new = status or "stale"
        if new == self._status:
            return
        self._status = new
        self.update_path(rebuild_handles=False)

    def _update_tooltip(self):
        s = self.model
        b_src = self.fs.blocks.get(s.src)
        b_dst = self.fs.blocks.get(s.dst)
        src_label = (f"{b_src.name} ({s.src_port or 'auto'})"
                      if b_src else "(sin conectar)")
        dst_label = (f"{b_dst.name} ({s.dst_port or 'auto'})"
                      if b_dst else "(sin conectar)")
        lines = [
            f"<b>{s.name}</b>",
            f"<span style='color:#666;'>{src_label} → {dst_label}</span>",
            f"Rol: {s.role}  ·  Fase: {s.phase or '—'}",
            f"Flujo: <b>{s.mass_flow:g}</b> tm/año",
            f"T = {s.temperature:g} °C",
        ]
        # Composición — pieza nueva, antes faltaba.  Muestra cada
        # componente con su fracción másica > 0.1%.
        comp = s.composition or {}
        if not comp and s.main_component:
            comp = {s.main_component: 1.0}
        if comp:
            rows = []
            for k, v in sorted(comp.items(), key=lambda kv: -kv[1]):
                if v < 0.001:
                    continue
                # Color de barra: gris si tiny, naranja si principal
                color = "#c41e3a" if v > 0.5 else "#3a3a3a"
                pct = v * 100
                rows.append(f"<span style='color:{color};'>"
                             f"&nbsp;&nbsp;{k}: {pct:.1f}%</span>")
            if rows:
                lines.append("<b>Composición (mass frac):</b>")
                lines.extend(rows)
        if s.role in ("feed", "product") and s.price_usd_per_tm:
            total = s.mass_flow * s.price_usd_per_tm
            lbl = "Ingreso" if s.role == "product" else "Costo MP"
            lines.append(f"Precio: {s.price_usd_per_tm:g} USD/tm  ·  "
                          f"{lbl}: $ {total:,.0f}/año")
        if s.cp > 0:
            lines.append(f"Cp = {s.cp:g} kJ/kg·K (override manual)")
        self.setToolTip("<br>".join(lines))

    def update_path(self, rebuild_handles=True):
        s = self.model
        b_src = self.fs.blocks.get(s.src)
        b_dst = self.fs.blocks.get(s.dst)
        # Endpoint START: si block_src existe, lo tomamos del puerto;
        # si no, lo tomamos de s.start_xy (endpoint flotante).
        if b_src is not None:
            _, x1, y1 = self._resolve_port(b_src, s.src_port, "right")
        elif s.start_xy and len(s.start_xy) >= 2:
            x1, y1 = float(s.start_xy[0]), float(s.start_xy[1])
        else:
            return   # stream sin punto de inicio definido, no se puede dibujar
        # Endpoint END
        if b_dst is not None:
            _, x2, y2 = self._resolve_port(b_dst, s.dst_port, "left")
        elif s.end_xy and len(s.end_xy) >= 2:
            x2, y2 = float(s.end_xy[0]), float(s.end_xy[1])
        else:
            return
        # Si hay waypoints declarados, usar routing manual.
        # Si no, autoroute con _compute_polyline.
        if s.waypoints:
            pts = [x1, y1]
            for wp in s.waypoints:
                pts.append(float(wp[0]))
                pts.append(float(wp[1]))
            pts.append(x2)
            pts.append(y2)
        elif b_src is not None and b_dst is not None:
            pts = self._compute_polyline(b_src, b_dst, s)
            # PADDING-AWARE ROUTING — modificar pts para que NO atraviese
            # los SVGs de los bloques ajenos (no src ni dst).  Las
            # tuberías rodean por arriba/abajo/izq/der según menor
            # costo Manhattan.  Padding 12px ≈ 3× ancho de stream.
            if self.editor is not None:
                obstacles = []
                for bid, item in self.editor.block_items_iter():
                    if bid == s.src or bid == s.dst:
                        continue
                    bm = item.model
                    w, h = pfd.block_dims(bm.eq_type)
                    obstacles.append((bm.x, bm.y, w, h))
                if obstacles:
                    pts = _avoid_obstacles(pts, obstacles, padding=12)
                # LANE ASSIGNMENT — desplazar perpendicularmente los
                # segmentos solapados con otros streams para evitar
                # superposición visual (streams paralelos en lanes
                # distintos como en planos PFD reales).
                other_paths = []
                for other_sid, other_item in self.editor.stream_items_iter():
                    if other_item is self:
                        continue
                    other_pts = getattr(other_item, '_last_pts', None)
                    if other_pts:
                        other_paths.append((other_item.model.id, other_pts))
                if other_paths:
                    pts = _apply_lane_offset(pts, other_paths, s.id,
                                               lane_step=10.0, min_dist=8.0)
        else:
            # Sin waypoints y al menos un endpoint flotante: línea recta
            pts = [x1, y1, x2, y2]
        if not pts:
            return
        # Gap entre la flecha y el bloque destino: acortar el último
        # segmento ~10px para que la punta de flecha NO toque el SVG.
        # También un gap chico (4px) en el origen para no tocar el SVG src.
        import math
        gap_dst = 10.0
        gap_src = 4.0
        if len(pts) >= 4:
            # gap destino: pts[-2:-1] son los últimos x,y
            xL, yL = pts[-4], pts[-3]
            xE, yE = pts[-2], pts[-1]
            dx, dy = xE - xL, yE - yL
            d = math.hypot(dx, dy)
            if d > gap_dst + 1:
                ux, uy = dx / d, dy / d
                pts[-2] = xE - ux * gap_dst
                pts[-1] = yE - uy * gap_dst
            # gap origen
            xS, yS = pts[0], pts[1]
            xN, yN = pts[2], pts[3]
            dx, dy = xN - xS, yN - yS
            d = math.hypot(dx, dy)
            if d > gap_src + 1:
                ux, uy = dx / d, dy / d
                pts[0] = xS + ux * gap_src
                pts[1] = yS + uy * gap_src
        # guardar para que los handles fantasma puedan leer los bend points
        self._last_pts = pts

        # ---- JUMPERS: detectar cruces con OTROS streams y dibujar
        #      pequeños arcs (semicírculos) en los puntos de cruce
        #      para que las flechas no se "toquen".  Solo el stream
        #      con id MAYOR dibuja el hop — así cada cruce tiene
        #      solo una curvita, no dos superpuestas.
        hops = []
        if self.scene() is not None and self.editor is not None:
            try:
                for other_sid, other_item in self.editor.stream_items_iter():
                    if other_item is self:
                        continue
                    if self.model.id < other_item.model.id:
                        continue   # el otro dibujará el hop
                    other_pts = getattr(other_item, '_last_pts', None) or []
                    crosses = _detect_path_crossings(pts, other_pts)
                    hops.extend(crosses)
            except Exception:
                pass

        # Construir el path con hops insertados
        path = _build_path_with_hops(pts, hops)
        self.setPath(path)

        color = self._color()
        # Ancho según rol del stream — líneas más gruesas para procesos
        # principales, finas para utilities/waste secundarios.
        role = self.model.role
        width = {"feed": 2.4, "internal": 2.4, "product": 2.4,
                 "waste": 1.6, "utility": 1.4}.get(role, 2.0)
        # Hover: engrosar línea +50% para feedback visual
        if self._hovered:
            width *= 1.5
        pen = QPen(color, width)
        pen.setCapStyle(Qt.FlatCap)
        pen.setJoinStyle(Qt.MiterJoin)
        # utility / waste con línea punteada para distinguir aún más
        if role == "utility":
            pen.setDashPattern([6.0, 4.0])
        elif role == "waste":
            pen.setDashPattern([3.0, 3.0])
        self.setPen(pen)
        self._draw_arrow(path, pts[-2], pts[-1], pts[-4], pts[-3])
        # Direction arrows intermedios (chevrons cada ~130 px)
        self._draw_direction_arrows(pts)

        # ---- label (pill compacta: SÓLO número de corriente) ----
        # Por default OFF (limpia visual de canvas, sin etiquetas sobre la
        # flecha). El user puede reactivar con editor._show_stream_labels=True
        # (ver View → 'Mostrar etiquetas de corrientes' si está disponible).
        show_label = bool(getattr(self.editor, "_show_stream_labels", False)) \
                     if self.editor is not None else False
        self.label_bg.setVisible(show_label)
        self.label_name.setVisible(show_label)
        self.label_flow.setVisible(show_label)
        if show_label:
            name_text, flow_text = self._label_parts(s)
            self.label_name.setText(name_text)
            self.label_name.setBrush(QBrush(color))
            self.label_flow.setText(flow_text)

            bb_name = self.label_name.boundingRect()
            bb_flow = self.label_flow.boundingRect()

            gap   = 8 if flow_text else 0
            inner = bb_name.width() + gap + bb_flow.width()
            pad_x = 9
            pad_y = 3
            pill_w = inner + 2 * pad_x
            pill_h = max(bb_name.height(), bb_flow.height()) + 2 * pad_y

            lx, ly = self._label_xy(pts)
            x0 = lx - pill_w / 2
            y0 = ly - pill_h / 2

            self.label_bg.setRect(x0, y0, pill_w, pill_h)
            self.label_bg.setPen(QPen(color, 1.0))

            # name a la izquierda, flow a la derecha
            ty = y0 + (pill_h - bb_name.height()) / 2
            self.label_name.setPos(x0 + pad_x, ty)
            self.label_flow.setPos(x0 + pad_x + bb_name.width() + gap, ty)

        if rebuild_handles:
            self._rebuild_handles()
        else:
            # Sin reconstruir handles, RE-SINCRONIZAR los _EndpointHandle
            # existentes con el modelo. Cuando un bloque conectado se
            # mueve (refresh_streams_of), el endpoint del path se redibuja
            # en la nueva pos del puerto pero la bolita naranja del handle
            # quedaba en la pos anterior. _sync_pos_from_model la pone
            # donde el modelo dice — y el flag SendsGeometryChanges está
            # protegido (ver _sync_pos_from_model) para no wipear la
            # conexión.
            for h in self._handles:
                if isinstance(h, _EndpointHandle):
                    h._sync_pos_from_model()

        self._update_tooltip()

    # ---------------------------------------------------
    # WAYPOINTS DRAGGABLES (routing manual)
    # ---------------------------------------------------

    def _rebuild_handles(self):
        """Recrea los handles del stream.  Solo visibles cuando el
        stream está seleccionado.

        Tres tipos:
          1. _EndpointHandle (naranja, doble anillo) en start y end —
             draggable para desconectar del bloque o re-conectar a otro
             puerto cercano (snap radius ~22px).
          2. _StreamHandle (azul sólido) en cada waypoint declarado.
          3. _GhostStreamHandle (azul translúcido) en bend points del
             auto-route — click bakea el bend como waypoint editable.
        """
        scene = self.scene()
        for h in self._handles:
            if scene is not None and h.scene() is scene:
                scene.removeItem(h)
            # también remover snap_marker auxiliar de _EndpointHandle
            sm = getattr(h, "_snap_marker", None)
            if sm is not None and scene is not None and sm.scene() is scene:
                scene.removeItem(sm)
        self._handles.clear()

        if scene is None:
            return
        # Stream flotante (src<=0 o dst<=0): mostrar endpoint handles
        # SIEMPRE, aunque no esté seleccionado, para que el user pueda
        # arrastrarlos a un puerto sin tener que seleccionar primero.
        is_floating = (self.model.src <= 0 or self.model.dst <= 0)
        if not self.isSelected() and not is_floating:
            return

        # Endpoints (start y end) — siempre si seleccionado o flotante
        for role in ("start", "end"):
            h = _EndpointHandle(self, role)
            scene.addItem(h)
            self._handles.append(h)

        # Waypoints + ghosts solo si seleccionado (no en flotante puro)
        if not self.isSelected():
            return

        if self.model.waypoints:
            for i in range(len(self.model.waypoints)):
                h = _StreamHandle(self, i)
                scene.addItem(h)
                self._handles.append(h)
        else:
            # mostrar ghost handles en los interior bend points del
            # auto-route (pts[2:-2] cada 2).
            pts = getattr(self, '_last_pts', None) or []
            for i in range(2, len(pts) - 2, 2):
                h = _GhostStreamHandle(self, pts[i], pts[i+1])
                scene.addItem(h)
                self._handles.append(h)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self._rebuild_handles()
        return super().itemChange(change, value)

    def contextMenuEvent(self, event):
        """Menú right-click: insertar waypoint, editar, borrar, etc."""
        from PySide6.QtWidgets import QMenu
        menu = QMenu()
        click_pos = event.scenePos()
        # Íconos del set HYSYS
        ed = getattr(self, "editor", None)
        mk = getattr(ed, "_mk_icon", None) if ed else None
        icol = getattr(ed, "_icon_color", "#3a3a3a") if ed else "#3a3a3a"
        ic_wp     = mk("act-waypoint", color=icol, size=16) if mk else QIcon()
        ic_reset  = mk("sim-reset",    color=icol, size=16) if mk else QIcon()
        ic_edit   = mk("act-edit",     color=icol, size=16) if mk else QIcon()
        ic_delete = mk("edit-delete",  color="#c41e3a", size=16) if mk else QIcon()
        a_edit = menu.addAction(ic_edit or QIcon(),
                                  "Editar propiedades… (doble-click)")
        menu.addSeparator()
        a_add = menu.addAction(ic_wp or QIcon(), "Insertar waypoint acá")
        a_reset = menu.addAction(ic_reset or QIcon(), "Resetear auto-routing")
        a_reset.setEnabled(bool(self.model.waypoints))
        a_straighten = menu.addAction(
            ic_wp or QIcon(), "Enderezar flecha (horizontal / vertical)")
        menu.addSeparator()
        # Toggle global: mostrar/ocultar pills sobre las flechas.
        # Default OFF (canvas limpio); el user lo activa cuando quiere
        # ver los caudales/composiciones rotulados sobre cada stream.
        labels_on = bool(getattr(ed, "_show_stream_labels", False)) if ed else False
        a_labels = menu.addAction(
            ic_wp or QIcon(),
            "Ocultar etiquetas de corrientes" if labels_on
            else "Mostrar etiquetas de corrientes",
        )
        menu.addSeparator()
        a_del = menu.addAction(ic_delete or QIcon(), "Borrar")
        chosen = menu.exec_(event.screenPos())
        if chosen is a_edit and ed is not None:
            ed.edit_stream(self.model)
            event.accept()
            return
        if chosen is a_del and ed is not None:
            ed._delete_stream(self.model.id)
            event.accept()
            return
        if chosen is a_add:
            # snap a la grilla
            wx = round(click_pos.x() / GRID_STEP) * GRID_STEP
            wy = round(click_pos.y() / GRID_STEP) * GRID_STEP
            self.model.waypoints.append([wx, wy])
            self.update_path()
        elif chosen is a_reset:
            self.model.waypoints.clear()
            self.update_path()
        elif chosen is a_straighten:
            self._straighten_to_orthogonal()
        elif chosen is a_labels and ed is not None:
            ed._show_stream_labels = not labels_on
            # Refrescar TODOS los streams para que el toggle aplique al canvas entero
            for _sid, _si in ed.stream_items_iter():
                _si.update_path(rebuild_handles=False)
        event.accept()

    def _straighten_to_orthogonal(self, axis: str = "auto"):
        """Endereza la flecha a horizontal o vertical pura.

        El clásico problema 'la flecha quedó inclinada y no se puede
        volver a poner derecha' después de un snap de bloque. Esto
        alinea el endpoint flotante para que coincida EXACTAMENTE con
        la coordenada perpendicular del endpoint anclado, y limpia los
        waypoints (la línea va directa, sin bends raros que la
        inclinaron).

        axis:
          'auto'       — decide por |Δx| vs |Δy|, dominante = el eje
                          de la flecha (horizontal si dx>=dy).
          'horizontal' — fuerza alineación en Y (flecha horizontal).
          'vertical'   — fuerza alineación en X (flecha vertical).

        POR QUÉ antes 'cambiaba un poco pero seguía chueca': los
        puertos están en pos del bloque + h*frac (típico 297, 345)
        que NO está en la grilla de 20 px. Snapear el endpoint
        flotante a la grilla perdía 1-5 px de alineación. Fix: el
        eje constreñido se setea EXACTO al anchored, sin grid snap.
        Solo el eje libre se snapea a grilla (no afecta la rectitud).

        Casos:
          • Ambos endpoints anclados: solo limpia waypoints.
          • Un endpoint flotante: alinea el flotante con el anclado.
          • Ambos flotantes: alinea END con START."""
        s = self.model
        fs = getattr(self, "fs", None)
        def _endpoint_pos(role):
            if role == "start":
                if s.src != -1 and fs is not None:
                    b = fs.blocks.get(s.src)
                    if b is not None:
                        _, x, y = self._resolve_port(b, s.src_port, "right")
                        return (x, y, True)
                if s.start_xy and len(s.start_xy) >= 2:
                    return (float(s.start_xy[0]), float(s.start_xy[1]), False)
                return None
            else:
                if s.dst != -1 and fs is not None:
                    b = fs.blocks.get(s.dst)
                    if b is not None:
                        _, x, y = self._resolve_port(b, s.dst_port, "left")
                        return (x, y, True)
                if s.end_xy and len(s.end_xy) >= 2:
                    return (float(s.end_xy[0]), float(s.end_xy[1]), False)
                return None

        p_start = _endpoint_pos("start")
        p_end   = _endpoint_pos("end")
        if p_start is None or p_end is None:
            return

        x1, y1, anchored_start = p_start
        x2, y2, anchored_end   = p_end
        if axis == "auto":
            horizontal = (abs(x2 - x1) >= abs(y2 - y1))
        elif axis == "horizontal":
            horizontal = True
        elif axis == "vertical":
            horizontal = False
        else:
            horizontal = True

        s.waypoints = []

        if anchored_start and anchored_end:
            # Ambos en bloques: nada que mover, auto-route es ortogonal.
            self.update_path()
            return

        # X libre: snap a grilla. Y constreñido: EXACTO al anchored.
        # (y viceversa para vertical)
        def snap(v): return round(v / GRID_STEP) * GRID_STEP

        if anchored_start and not anchored_end:
            if horizontal:
                s.end_xy = [snap(x2), y1]    # Y exacto, X a grilla
            else:
                s.end_xy = [x1, snap(y2)]    # X exacto, Y a grilla
        elif anchored_end and not anchored_start:
            if horizontal:
                s.start_xy = [snap(x1), y2]
            else:
                s.start_xy = [x2, snap(y1)]
        else:
            # Ambos flotantes: alinear END con START en el eje perpendicular.
            if horizontal:
                yy = snap(y1)
                s.start_xy = [snap(x1), yy]
                s.end_xy   = [snap(x2), yy]
            else:
                xx = snap(x1)
                s.start_xy = [xx, snap(y1)]
                s.end_xy   = [xx, snap(y2)]
        self.update_path()

    def _draw_arrow(self, path, x_end, y_end, x_prev, y_prev):
        """Punta de flecha rellena al final del stream — QGraphicsPolygonItem
        separado, no se mezcla con el stroke de la polilínea (que con
        SquareCap dejaba la flecha hueca)."""
        import math
        dx = x_end - x_prev
        dy = y_end - y_prev
        L = math.hypot(dx, dy)
        if L < 0.01:
            self.arrow_head.setPolygon(QPolygonF())
            return
        ux, uy = dx / L, dy / L      # versor en dirección de la flecha
        nx, ny = -uy, ux             # perpendicular
        size = 11
        wing = 4.5
        tip = QPointF(x_end, y_end)
        b1  = QPointF(x_end - size*ux + wing*nx, y_end - size*uy + wing*ny)
        b2  = QPointF(x_end - size*ux - wing*nx, y_end - size*uy - wing*ny)
        self.arrow_head.setPolygon(QPolygonF([tip, b1, b2]))
        self.arrow_head.setBrush(QBrush(self._color()))

    def shape(self):
        """Hit area más ancha que el stroke visible (2.4 px) → click sobre
        o cerca de la flecha la selecciona aunque no caigas justo encima.
        Stroker en 12 px ≈ 5× ancho real."""
        from PySide6.QtGui import QPainterPathStroker
        stroker = QPainterPathStroker()
        stroker.setWidth(12.0)
        stroker.setCapStyle(Qt.RoundCap)
        stroker.setJoinStyle(Qt.RoundJoin)
        return stroker.createStroke(self.path())

    def _translation_snapshot(self):
        """Captura el estado del modelo para drag-translate."""
        s = self.model
        return {
            "start_xy":  list(s.start_xy) if s.start_xy else None,
            "end_xy":    list(s.end_xy)   if s.end_xy   else None,
            "waypoints": [list(wp) for wp in (s.waypoints or [])],
        }

    def _apply_translation(self, dx, dy, snap):
        """Aplica un offset (dx, dy) al modelo:
          • endpoints flotantes (src/dst == -1) → start_xy/end_xy se mueven
          • endpoints anclados a un bloque → quedan en el puerto
          • waypoints → siempre se trasladan
        `snap` es el snapshot inicial (no muta entre updates del drag)."""
        s = self.model
        if s.src == -1 and snap["start_xy"] is not None:
            s.start_xy = [snap["start_xy"][0] + dx, snap["start_xy"][1] + dy]
        if s.dst == -1 and snap["end_xy"] is not None:
            s.end_xy = [snap["end_xy"][0] + dx, snap["end_xy"][1] + dy]
        if snap["waypoints"]:
            s.waypoints = [[wp[0] + dx, wp[1] + dy] for wp in snap["waypoints"]]
        self.update_path()

    def translate_by(self, dx, dy):
        """API pública: trasladar el stream relativo al estado actual.
        Usado por keyPressEvent de la view (flechas del teclado)."""
        snap = self._translation_snapshot()
        self._apply_translation(dx, dy, snap)

    def mousePressEvent(self, event):
        """Inicia drag-translate de toda la flecha al hacer click sobre
        ella (no sobre un handle).

        EXCEPCIÓN: si el stream está fully-connected (src y dst en bloques)
        Y no tiene waypoints, NO hay nada que mover (los endpoints siguen
        a los bloques, no hay bend points editables). En ese caso NO
        interceptamos el click: dejamos que Qt haga la selección normal,
        para que rubber-band + drag de un bloque vecino mueva el conjunto
        sin que esta flecha 'absorba' el click y bloquee el group-drag."""
        if event.button() == Qt.LeftButton:
            s = self.model
            has_floating = (s.src == -1 or s.dst == -1)
            has_waypoints = bool(s.waypoints)
            if not has_floating and not has_waypoints:
                # Fully-connected, sin waypoints — nada que arrastrar.
                # Selección por defecto via super(), no consumimos el evento.
                super().mousePressEvent(event)
                return
            self.setSelected(True)
            self._drag_origin = event.scenePos()
            self._drag_snap = self._translation_snapshot()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, "_drag_origin", None) is not None:
            delta = event.scenePos() - self._drag_origin
            dx = round(delta.x() / GRID_STEP) * GRID_STEP
            dy = round(delta.y() / GRID_STEP) * GRID_STEP
            self._apply_translation(dx, dy, self._drag_snap)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if getattr(self, "_drag_origin", None) is not None:
            self._drag_origin = None
            self._drag_snap = None
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Doble-click sobre el stream → abrir editor."""
        if self.editor is not None:
            self.editor.edit_stream(self.model)
        super().mouseDoubleClickEvent(event)

    def _label_parts(self, s):
        """Devuelve (numero, info_extra) para la pill del stream.

        Pieza 1 (siempre): número topológico/custom/id.
        Pieza 2 (opcional): caudal másico con unidad de display, o
        componente principal si la corriente es multicomponente.

        El usuario puede activar el modo "compacto" via setting
        editor._show_flow_in_pill (default True): muestra "S5 · 100 t/a"
        en vez de solo "S5".  Si la corriente tiene composición
        multi-componente, muestra el principal en vez del flujo:
        "S5 · 95% ETOH"  para destacar visualmente.
        """
        n = getattr(s, "display_number", 0) or None
        if n is None:
            n = getattr(s, "_display_number", None)
        if n is None:
            n = s.id
        # Pieza 2: prioridad
        #   1) multicomp → "X% comp"  (más informativo)
        #   2) mass_flow > 0 → caudal en unidad seleccionada
        comp = s.composition or {}
        extra = ""
        if comp and len([c for c, v in comp.items() if v > 0.01]) >= 2:
            # Multicomponente — mostrar componente principal con %
            top = max(comp.items(), key=lambda kv: kv[1])
            comp_name = top[0]
            # Abreviar nombres largos (ethanol→ETOH, methanol→MEOH, etc.)
            ABBREV = {
                "ethanol": "ETOH", "methanol": "MEOH", "water": "H₂O",
                "ammonia": "NH₃", "nitrogen": "N₂", "hydrogen": "H₂",
                "carbon_dioxide": "CO₂", "co2": "CO₂", "co": "CO",
                "methane": "CH₄", "ethylene": "C₂H₄", "ethane": "C₂H₆",
                "propane": "C₃H₈", "propylene": "C₃H₆",
                "benzene": "C₆H₆", "toluene": "C₇H₈",
                "h2s": "H₂S", "so2": "SO₂", "mdea": "MDEA",
                "acetone": "ACT",  "chloroform": "CHCl₃",
                "isopropanol": "IPA", "cyclohexane": "CHX",
                "ethyl_acetate": "EtAc", "acetic_acid": "AcOH",
                "ethylene_glycol": "EG",
            }
            short = ABBREV.get(comp_name, comp_name[:5].upper())
            extra = f"{top[1]*100:.0f}% {short}"
        elif s.mass_flow > 0:
            # Componente principal solo (single comp) — mostrar caudal
            unit = "tm/año"
            if (hasattr(self, "editor") and self.editor is not None
                    and hasattr(self.editor, "streams_dock")
                    and self.editor.streams_dock is not None):
                unit = self.editor.streams_dock.current_unit()
            extra = funits.format_flow(s.mass_flow, unit)
        return str(n), extra

    # ---- helpers de routing (réplica simplificada de flowsheet_ui) ----

    def _resolve_port(self, b, port_name, default_side):
        ports = ep.get_ports(b.eq_type)
        if port_name and port_name in ports:
            side, frac = ports[port_name]
        else:
            chosen = None
            for pname, (side, frac) in ports.items():
                if side == default_side:
                    chosen = (pname, side, frac)
                    break
            if chosen is None:
                pname = next(iter(ports))
                side, frac = ports[pname]
            else:
                pname, side, frac = chosen
        w, h = pfd.block_dims(b.eq_type)
        if side == "right":
            x, y = b.x + w,         b.y + h * frac
        elif side == "left":
            x, y = b.x,             b.y + h * frac
        elif side == "top":
            x, y = b.x + w * frac,  b.y
        else:  # bottom
            x, y = b.x + w * frac,  b.y + h
        return side, x, y

    @staticmethod
    def _side_dir(side):
        return {"right": (1, 0), "left": (-1, 0),
                "top":   (0, -1), "bottom": (0, 1)}.get(side, (1, 0))

    def _compute_polyline(self, b_src, b_dst, s):
        """Polyline ortogonal Z-shape o L-shape entre puertos del src y dst."""
        # Guard: auto-edge (mismo bloque a sí mismo).  No debería pasar
        # porque complete_connection lo rechaza, pero un JSON malformado
        # podría tenerlo.  Devolvemos un loop pequeño visual.
        if b_src is b_dst:
            w, h = pfd.block_dims(b_src.eq_type)
            x = b_src.x + w
            y = b_src.y + h / 2
            return [x, y, x + 30, y, x + 30, y - 30,
                    b_src.x + w / 2, y - 30,
                    b_src.x + w / 2, b_src.y]
        side1, x1, y1 = self._resolve_port(b_src, s.src_port, "right")
        side2, x2, y2 = self._resolve_port(b_dst, s.dst_port, "left")
        dx1, dy1 = self._side_dir(side1)
        dx2, dy2 = self._side_dir(side2)
        gap = ROUTING_GAP
        ex1, ey1 = x1 + dx1 * gap, y1 + dy1 * gap
        ex2, ey2 = x2 + dx2 * gap, y2 + dy2 * gap

        h_sides = ("left", "right")
        v_sides = ("top", "bottom")

        # ambos horizontales opuestos
        if side1 in h_sides and side2 in h_sides:
            # cond_fwd: el destino está FÍSICAMENTE a la derecha del
            # origen (right→left) o a la izquierda (left→right).  Usa
            # x1/x2 directos, NO ex1/ex2 (que requerían 2×ROUTING_GAP
            # de holgura y forzaban detours feos cuando los bloques
            # estaban cerca).
            cond_fwd = (side1 == "right" and side2 == "left" and x2 > x1) \
                       or (side1 == "left" and side2 == "right" and x1 > x2)
            if cond_fwd and abs(y1 - y2) < 2:
                return [x1, y1, x2, y2]
            if cond_fwd:
                # Z-shape simple: codo en la mitad horizontal.  Sin
                # ROUTING_GAP fijo — bend en el punto medio, lo que
                # produce líneas más naturales aunque haya poco espacio.
                mx = (x1 + x2) / 2
                return [x1, y1, mx, y1, mx, y2, x2, y2]
            # backward (raro: dst físicamente atrás del src): rodea por arriba
            ymin = min(b_src.y, b_dst.y) - 40
            return [x1, y1, ex1, ey1, ex1, ymin, ex2, ymin, ex2, ey2, x2, y2]

        # ambos verticales opuestos
        if side1 in v_sides and side2 in v_sides:
            if side1 == "bottom" and side2 == "top" and ey2 >= ey1:
                if abs(ex1 - ex2) < 2:
                    return [x1, y1, x2, y2]
                my = (ey1 + ey2) / 2
                return [x1, y1, ex1, ey1, ex1, my, ex2, my, ex2, ey2, x2, y2]
            if side1 == "top" and side2 == "bottom" and ey1 >= ey2:
                if abs(ex1 - ex2) < 2:
                    return [x1, y1, x2, y2]
                my = (ey1 + ey2) / 2
                return [x1, y1, ex1, ey1, ex1, my, ex2, my, ex2, ey2, x2, y2]
            w_src, _ = pfd.block_dims(b_src.eq_type)
            w_dst, _ = pfd.block_dims(b_dst.eq_type)
            xmax = max(b_src.x + w_src, b_dst.x + w_dst) + 40
            return [x1, y1, ex1, ey1, xmax, ey1, xmax, ey2, ex2, ey2, x2, y2]

        # perpendiculares → L-shape
        if side1 in h_sides:
            return [x1, y1, ex1, ey1, ex2, ey1, ex2, ey2, x2, y2]
        return [x1, y1, ex1, ey1, ex1, ey2, ex2, ey2, x2, y2]

    def _label_xy(self, pts):
        """Centro del segmento horizontal más largo, para el label."""
        best_len = -1
        best = (pts[0], pts[1])
        for i in range(0, len(pts) - 2, 2):
            x1, y1 = pts[i],   pts[i+1]
            x2, y2 = pts[i+2], pts[i+3]
            if y1 == y2:
                L = abs(x2 - x1)
                if L > best_len:
                    best_len = L
                    best = ((x1 + x2) / 2, y1 - 10)
        return best


# ======================================================
# SCENE — contiene grid, blocks, streams
# ======================================================
# PAPEL DE DIBUJO PFD (marco + leyenda + cuadro de título)
# ======================================================
# Decoración estilo ingeniería: el "papel" donde se dibuja el PFD.
# Es un QGraphicsItemGroup que se ubica en la escena como fondo.
# No es parte del modelo; sólo se ve, no se serializa.

class _PaperFrame(QGraphicsItemGroup):
    """Hoja de dibujo PFD: marco exterior + ticks + cuadro de título + leyenda.

    Tamaño nominal 1600×960 (proporción ~A3 horizontal).  Se inserta
    en (0, 0) de la escena con zValue -100 para que quede de fondo.
    """

    PAPER_W = 1600
    PAPER_H = 960

    def __init__(self, project_title="PFD", area="100",
                 drawing_no="PFD-100-001", rev="A", date=None):
        super().__init__()
        self.setZValue(-100)
        self._project_title = project_title
        self._area          = area
        self._drawing_no    = drawing_no
        self._rev           = rev
        if date is None:
            import datetime
            date = datetime.date.today().isoformat()
        self._date          = date

        self._sans = pfd_fonts.SANS if pfd_fonts.available() else "Segoe UI"
        self._mono = pfd_fonts.MONO if pfd_fonts.available() else "Consolas"
        self._BLACK = QColor("#0d0d0d")
        self._SOFT  = QColor("#6b7280")

        self._build_frame()
        self._build_legend()
        self._build_title_block()

    # ---------- helpers ----------
    def _add_rect(self, x, y, w, h, stroke_w=1.0, fill=None, parent=None):
        item = QGraphicsRectItem(x, y, w, h, parent or self)
        item.setPen(QPen(self._BLACK, stroke_w))
        item.setBrush(QBrush(fill) if fill else QBrush(Qt.NoBrush))
        return item

    def _add_line(self, x1, y1, x2, y2, stroke_w=0.8, color=None, parent=None):
        item = QGraphicsLineItem(x1, y1, x2, y2, parent or self)
        item.setPen(QPen(color or self._BLACK, stroke_w))
        return item

    def _add_text(self, x, y, text, font, color=None, parent=None):
        t = QGraphicsSimpleTextItem(text, parent or self)
        t.setFont(font)
        t.setBrush(QBrush(color or self._BLACK))
        t.setPos(x, y)
        return t

    # ---------- partes ----------
    def _build_frame(self):
        W, H = self.PAPER_W, self.PAPER_H
        # marco exterior
        self._add_rect(20, 20, W - 40, H - 40, stroke_w=1.4)
        # ticks de centrado (cada 25%) — convención ingeniería
        for t in (0.25, 0.5, 0.75):
            self._add_line(W*t, 20,  W*t, 40,  0.6)
            self._add_line(W*t, H-40, W*t, H-20, 0.6)
            self._add_line(20,  H*t, 40,  H*t, 0.6)
            self._add_line(W-40, H*t, W-20, H*t, 0.6)

    def _build_legend(self):
        BLACK = self._BLACK
        SOFT  = self._SOFT
        RED   = QColor("#c41e3a")
        BLUE  = QColor("#1e3a8a")

        # top-right corner
        x0 = self.PAPER_W - 360
        y0 = 60
        gx, gy = x0, y0
        self._add_rect(gx, gy, 320, 88, stroke_w=0.8,
                       fill=QColor("#ffffff"))
        f_title = QFont(self._sans, 9, QFont.Bold)
        f_title.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        f_body  = QFont(self._mono, 8)
        self._add_text(gx + 12, gy + 6,  "LEYENDA", f_title)
        self._add_line(gx + 12, gy + 26, gx + 308, gy + 26, 0.4)
        # process line
        self._add_line(gx + 14, gy + 42, gx + 42, gy + 42, 2.2, BLACK)
        self._add_text(gx + 50, gy + 36, "Línea de proceso", f_body)
        # product
        self._add_line(gx + 14, gy + 58, gx + 42, gy + 58, 2.2, RED)
        self._add_text(gx + 50, gy + 52, "Producto",         f_body)
        # utility
        self._add_line(gx + 14, gy + 74, gx + 42, gy + 74, 2.2, BLUE)
        self._add_text(gx + 50, gy + 68, "Agua / utility",   f_body)

        # port sample
        ell = QGraphicsEllipseItem(gx + 196, gy + 38, 7.2, 7.2, self)
        ell.setBrush(QBrush(QColor("#ffffff")))
        ell.setPen(QPen(BLACK, 1.6))
        self._add_text(gx + 212, gy + 36, "Conexión",  f_body)
        self._add_text(gx + 196, gy + 52, "tm/año",    QFont(self._mono, 8), color=SOFT)
        self._add_text(gx + 196, gy + 68, "S = m², V = m³", QFont(self._mono, 8), color=SOFT)

    def _build_title_block(self):
        BLACK = self._BLACK
        SOFT  = self._SOFT
        W, H  = self.PAPER_W, self.PAPER_H

        # bottom-right
        bx = W - 500
        by = H - 160
        self._add_rect(bx, by, 460, 120, stroke_w=1.4, fill=QColor("#ffffff"))
        # internal grid
        self._add_line(bx,        by + 30,  bx + 460, by + 30,  0.8)
        self._add_line(bx,        by + 70,  bx + 460, by + 70,  0.8)
        self._add_line(bx,        by + 95,  bx + 460, by + 95,  0.8)
        self._add_line(bx + 300,  by + 30,  bx + 300, by + 120, 0.8)
        self._add_line(bx + 380,  by + 70,  bx + 380, by + 120, 0.8)

        f_h1 = QFont(self._sans, 12, QFont.Bold)
        f_label = QFont(self._mono, 7)
        f_label.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
        f_val = QFont(self._sans, 10, QFont.Medium)
        f_val_mono = QFont(self._mono, 9, QFont.Medium)

        # título (fila superior)
        self._add_text(bx + 12, by + 6, self._project_title, f_h1)

        # PROYECTO / ÁREA  (fila 2)
        self._add_text(bx + 12,  by + 36, "PROYECTO", f_label, color=SOFT)
        self._add_text(bx + 12,  by + 50, "PFD",      f_val)
        self._add_text(bx + 312, by + 36, "ÁREA",     f_label, color=SOFT)
        self._add_text(bx + 312, by + 50, self._area, f_val)

        # DIBUJO N° / REV / FECHA (fila 3)
        self._add_text(bx + 12,  by + 73, "DIBUJO N°", f_label, color=SOFT)
        self._add_text(bx + 80,  by + 73, self._drawing_no, f_val_mono)
        self._add_text(bx + 312, by + 73, "REV",      f_label, color=SOFT)
        self._add_text(bx + 342, by + 73, self._rev,  QFont(self._mono, 11, QFont.Bold))
        self._add_text(bx + 388, by + 73, "FECHA",    f_label, color=SOFT)
        self._add_text(bx + 388, by + 100, self._date, f_val_mono)

        # ESCALA / UNIDADES / DIBUJÓ (fila 4)
        self._add_text(bx + 12,  by + 100, "ESCALA",   f_label, color=SOFT)
        self._add_text(bx + 56,  by + 100, "NTS",      f_val_mono)
        self._add_text(bx + 120, by + 100, "UNIDADES", f_label, color=SOFT)
        self._add_text(bx + 180, by + 100, "SI · tm/año", f_val_mono)
        self._add_text(bx + 312, by + 100, "DIBUJÓ",   f_label, color=SOFT)
        self._add_text(bx + 350, by + 100, "—",        f_val_mono)


# ======================================================

class FlowsheetScene(QGraphicsScene):
    """QGraphicsScene con grid de fondo + items del flowsheet.
    Mantiene mappings model_id → QGraphicsItem."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackgroundBrush(QBrush(COLOR_CANVAS_BG))
        self.setSceneRect(-200, -200, 5000, 4000)
        self.block_items:  dict = {}      # block_id  → BlockItem
        self.stream_items: dict = {}      # stream_id → StreamItem
        self.paper_frame: "_PaperFrame|None" = None
        self._draw_grid()

    def set_paper_visible(self, visible: bool,
                           project_title="PFD", area="100",
                           drawing_no="PFD-100-001"):
        """Muestra/oculta el papel de dibujo PFD (marco + leyenda +
        cuadro de título).  Se posiciona en (0, 0)."""
        if visible:
            if self.paper_frame is None:
                self.paper_frame = _PaperFrame(
                    project_title=project_title,
                    area=area, drawing_no=drawing_no,
                )
                self.paper_frame.setPos(0, 0)
                self.addItem(self.paper_frame)
            self.paper_frame.setVisible(True)
        else:
            if self.paper_frame is not None:
                self.paper_frame.setVisible(False)

    def _draw_grid(self):
        pen = QPen(COLOR_GRID, 0)
        rect = self.sceneRect()
        x0 = int(rect.left())
        y0 = int(rect.top())
        x1 = int(rect.right())
        y1 = int(rect.bottom())
        step = GRID_STEP
        # alinear al múltiplo de step
        x0 = (x0 // step) * step
        y0 = (y0 // step) * step
        for x in range(x0, x1 + step, step):
            line = QGraphicsLineItem(x, y0, x, y1)
            line.setPen(pen)
            line.setZValue(-100)
            self.addItem(line)
        for y in range(y0, y1 + step, step):
            line = QGraphicsLineItem(x0, y, x1, y)
            line.setPen(pen)
            line.setZValue(-100)
            self.addItem(line)

    def clear_flowsheet(self):
        # Borra los items conocidos via mapping
        for item in list(self.block_items.values()):
            self.removeItem(item)
        for item in list(self.stream_items.values()):
            item.remove_from_scene(self)
        self.block_items.clear()
        self.stream_items.clear()
        # Defensa: cualquier item no-grid que haya quedado huérfano
        # (renderizado incompleto, fallos previos) se borra ahora.
        for it in list(self.items()):
            if it.zValue() > -100:    # grid items tienen z=-100
                # mantenemos los items con tag de grid, removemos el resto
                self.removeItem(it)


# ======================================================
# VIEW — zoom + pan
# ======================================================

class _LibraryTree(QTreeWidget):
    """QTreeWidget custom que soporta drag&drop hacia el canvas.
    Cuando se arrastra un ítem hijo (eq_type), genera mimeData con
    el eq_type en el formato 'application/x-pfd-eqtype'."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QTreeWidget.DragOnly)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item is None:
            return
        eq_type = item.data(0, Qt.UserRole)
        if not eq_type:
            return  # categoría, no equipo
        from PySide6.QtCore import QMimeData, QByteArray
        from PySide6.QtGui import QDrag
        mime = QMimeData()
        # Distinguir entre equipo y stream según prefijo
        if eq_type.startswith("__STREAM__"):
            # Corriente: el payload es 'mass' o 'energy'
            kind = eq_type.replace("__STREAM__", "")
            mime.setData("application/x-pfd-stream",
                           QByteArray(kind.encode("utf-8")))
        else:
            mime.setData("application/x-pfd-eqtype",
                           QByteArray(str(eq_type).encode("utf-8")))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


class FlowsheetView(QGraphicsView):
    """QGraphicsView con zoom anclado al cursor y pan con middle-drag."""

    ZOOM_STEP = 1.15
    ZOOM_MIN  = 0.30
    ZOOM_MAX  = 3.00

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # aceptar drops desde la biblioteca de equipos
        self.setAcceptDrops(True)
        self._zoom = 1.0
        self._panning = False
        self._pan_start = QPointF(0, 0)

    # ---- drag-and-drop desde la biblioteca de equipos ----
    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md.hasFormat("application/x-pfd-eqtype") \
                or md.hasFormat("application/x-pfd-stream"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        md = event.mimeData()
        if md.hasFormat("application/x-pfd-eqtype") \
                or md.hasFormat("application/x-pfd-stream"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        md = event.mimeData()
        scene_pos = self.mapToScene(event.position().toPoint()
                                      if hasattr(event, "position")
                                      else event.pos())
        x = round(scene_pos.x() / GRID_STEP) * GRID_STEP
        y = round(scene_pos.y() / GRID_STEP) * GRID_STEP
        w = self.window()
        if md.hasFormat("application/x-pfd-eqtype"):
            eq_type = bytes(md.data("application/x-pfd-eqtype")).decode("utf-8")
            if hasattr(w, "_add_block_of_type"):
                w._add_block_of_type(eq_type, x=x, y=y)
            event.acceptProposedAction()
            return
        if md.hasFormat("application/x-pfd-stream"):
            kind = bytes(md.data("application/x-pfd-stream")).decode("utf-8")
            if hasattr(w, "_add_floating_stream"):
                w._add_floating_stream(kind=kind, x=x, y=y)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            # zoom anclado al cursor
            angle = event.angleDelta().y()
            factor = self.ZOOM_STEP if angle > 0 else (1 / self.ZOOM_STEP)
            new_zoom = self._zoom * factor
            if self.ZOOM_MIN <= new_zoom <= self.ZOOM_MAX:
                self._zoom = new_zoom
                self.scale(factor, factor)
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            # mover el viewport (no la scene)
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        """Flechas del teclado → mueven los items seleccionados.
        Paso fino con Shift (1 px), paso de grilla por default."""
        key = event.key()
        if key in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            step = 1 if (event.modifiers() & Qt.ShiftModifier) else GRID_STEP
            dx = dy = 0
            if key == Qt.Key_Left:   dx = -step
            if key == Qt.Key_Right:  dx = +step
            if key == Qt.Key_Up:     dy = -step
            if key == Qt.Key_Down:   dy = +step
            scene = self.scene()
            moved = False
            if scene is not None:
                for item in scene.selectedItems():
                    if isinstance(item, StreamItem):
                        item.translate_by(dx, dy)
                        moved = True
                    elif hasattr(item, "moveBy"):
                        # BlockItem y similares: usar moveBy nativo de Qt
                        item.moveBy(dx, dy)
                        moved = True
            if moved:
                event.accept()
                return
        super().keyPressEvent(event)

    def zoom_in(self):
        self.wheelEvent_like(+1)

    def zoom_out(self):
        self.wheelEvent_like(-1)

    def wheelEvent_like(self, direction):
        factor = self.ZOOM_STEP if direction > 0 else (1 / self.ZOOM_STEP)
        new_zoom = self._zoom * factor
        if self.ZOOM_MIN <= new_zoom <= self.ZOOM_MAX:
            self._zoom = new_zoom
            self.scale(factor, factor)

    def zoom_fit(self):
        if not self.scene().items():
            return
        # bounding box de bloques solamente
        items = [it for it in self.scene().items()
                 if isinstance(it, BlockItem)]
        if not items:
            self.resetTransform()
            self._zoom = 1.0
            return
        bbox = QRectF()
        for it in items:
            bbox = bbox.united(it.sceneBoundingRect())
        bbox.adjust(-50, -50, 50, 50)
        self.fitInView(bbox, Qt.KeepAspectRatio)
        self._zoom = self.transform().m11()

    def zoom_reset(self):
        self.resetTransform()
        self._zoom = 1.0


# ======================================================
# MAIN WINDOW
# ======================================================

# ======================================================
# STREAMS TABLE DOCK — tabla de corrientes con conversión de unidades
# ======================================================

class StreamsTableDock(QDockWidget):
    """Dock con tabla de TODAS las corrientes del flowsheet.

    Cada fila muestra: Nombre · From (block.port) · To (block.port)
    · Role · Flujo (en unidad elegida) · T · Cp · Precio (si feed/product).

    El user puede cambiar la unidad de flujo desde el combo superior:
    tm/año, kg/h, kg/s, t/d, lb/h.  Los labels en el canvas también
    se actualizan a la nueva unidad.

    Double-click en una fila abre el StreamEditDialog del stream.
    """

    (COL_NAME, COL_FROM, COL_TO, COL_ROLE, COL_FLOW, COL_T,
     COL_PHASE, COL_COMP, COL_CP, COL_PRICE) = range(10)

    def __init__(self, parent, editor):
        super().__init__(" Corrientes ", parent)
        self.editor = editor
        self.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.RightDockWidgetArea)
        self.setFeatures(QDockWidget.DockWidgetMovable
                          | QDockWidget.DockWidgetFloatable
                          | QDockWidget.DockWidgetClosable)

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # --- toolbar del dock: unidad de flujo + total in/out ---
        tb_layout = QHBoxLayout()
        tb_layout.addWidget(QLabel("Unidad de flujo:"))
        self.unit_combo = QComboBox()
        for u in funits.FLOW_UNITS_ORDER:
            self.unit_combo.addItem(u)
        self.unit_combo.setCurrentText("tm/año")
        self.unit_combo.currentTextChanged.connect(self._on_unit_changed)
        tb_layout.addWidget(self.unit_combo)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet("color: #555;")
        tb_layout.addWidget(self.lbl_summary)
        tb_layout.addStretch()
        layout.addLayout(tb_layout)

        # --- tabla ---
        cols = ["Nombre", "Desde", "Hacia", "Rol", "Flujo", "T",
                "Fase", "Composición (mass frac)", "Cp", "Precio"]
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemDoubleClicked.connect(self._on_double_click)
        for col, width in (
            (self.COL_NAME, 130), (self.COL_FROM, 130), (self.COL_TO, 130),
            (self.COL_ROLE, 65),  (self.COL_FLOW, 110), (self.COL_T, 65),
            (self.COL_PHASE, 70), (self.COL_COMP, 280),
            (self.COL_CP, 60),    (self.COL_PRICE, 90),
        ):
            self.table.setColumnWidth(col, width)
        layout.addWidget(self.table)

        self.setWidget(widget)

    def current_unit(self):
        return self.unit_combo.currentText()

    def refresh(self):
        """Reconstruye la tabla desde el flowsheet actual."""
        fs = self.editor.fs
        unit = self.current_unit()
        streams = sorted(fs.streams.values(), key=lambda s: s.name)
        self.table.setRowCount(len(streams))

        feed_total_tm = 0.0
        prod_total_tm = 0.0
        for r, s in enumerate(streams):
            src_b = fs.blocks.get(s.src)
            dst_b = fs.blocks.get(s.dst)
            src_label = (
                f"{src_b.name}.{s.src_port or '?'}" if src_b else "(borrado)"
            )
            dst_label = (
                f"{dst_b.name}.{s.dst_port or '?'}" if dst_b else "(borrado)"
            )
            # Composición compacta: "compA 82.4% · compB 17.6%" para
            # streams multicomponente; "(compA)" si solo main_component.
            comp = s.composition or {}
            if not comp and s.main_component:
                comp = {s.main_component: 1.0}
            comp_parts = []
            for k, v in sorted(comp.items(), key=lambda kv: -kv[1]):
                if v < 0.001:
                    continue
                comp_parts.append(f"{k} {v*100:.1f}%")
            comp_str = " · ".join(comp_parts) if comp_parts else "—"
            vals = [
                s.name,
                src_label,
                dst_label,
                s.role,
                funits.format_flow(s.mass_flow, unit),
                f"{s.temperature:g} °C",
                s.phase or "—",
                comp_str,
                f"{s.cp:g}" if s.cp > 0 else "—",
                (f"${s.price_usd_per_tm:g}/tm"
                 if s.role in ("feed", "product") and s.price_usd_per_tm
                 else "—"),
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if c in (self.COL_FLOW, self.COL_T, self.COL_CP, self.COL_PRICE):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                # Tooltip de composición completa (todos los componentes)
                if c == self.COL_COMP and comp:
                    tooltip_lines = [f"<b>{s.name} — composición</b>"]
                    for k, v_ in sorted(comp.items(), key=lambda kv: -kv[1]):
                        m_i = v_ * s.mass_flow
                        tooltip_lines.append(
                            f"&nbsp;&nbsp;{k}: {v_*100:.2f}%  "
                            f"({m_i:.1f} tm/año)")
                    item.setToolTip("<br>".join(tooltip_lines))
                if s.role == "feed":
                    item.setForeground(QBrush(QColor("#2e7d32")))
                elif s.role == "product":
                    item.setForeground(QBrush(QColor("#e65100")))
                # guardar el sid en la primera columna para edit on dblclick
                if c == self.COL_NAME:
                    item.setData(Qt.UserRole, s.id)
                self.table.setItem(r, c, item)

            if s.role == "feed":
                feed_total_tm += s.mass_flow
            elif s.role == "product":
                prod_total_tm += s.mass_flow

        self.lbl_summary.setText(
            f"({len(streams)} corrientes · "
            f"feed: {funits.format_flow(feed_total_tm, unit)} · "
            f"products: {funits.format_flow(prod_total_tm, unit)})"
        )

    def _on_unit_changed(self, _unit):
        """Cambió la unidad de flujo → refresh tabla + labels del canvas."""
        self.refresh()
        # también actualizar labels de streams en el canvas
        for sid, item in self.editor.scene.stream_items.items():
            item.update_path()

    def _on_double_click(self, item):
        row = item.row()
        sid_item = self.table.item(row, self.COL_NAME)
        if sid_item is None:
            return
        sid = sid_item.data(Qt.UserRole)
        stream = self.editor.fs.streams.get(sid)
        if stream is not None:
            self.editor.edit_stream(stream)


class FlowsheetMainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Diagrama de proceso — Qt edition")
        self.resize(1400, 820)

        # Registrar IBM Plex Sans / Mono para tags y especs (Aspen style).
        # Idempotente — si Qt no encuentra las TTFs, cae al sistema.
        pfd_fonts.load_all()

        self.fs = Flowsheet()
        self.scene = FlowsheetScene(self)
        self.view  = FlowsheetView(self.scene)
        self.setCentralWidget(self.view)

        # state de conexión pendiente (right-click + left-click)
        self._connecting_from: int = None

        # undo/redo
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(100)
        # flag para suprimir snapshots durante apply_snapshot (evita recursión)
        self._suppress_snapshot = False
        # snapshot 'antes' del drag de bloques (se pushea al release)
        self._drag_before_snapshot = None

        # Docks se construyen ANTES del toolbar para que éste pueda
        # tomar sus toggleViewAction() y mostrarlos como botones.
        self._build_library_dock()
        self._build_properties_dock()
        self._build_streams_dock()
        self._build_toolbar()
        self._build_statusbar()

        # selección
        self.scene.selectionChanged.connect(self._on_selection_changed)

        # Esc cancela conexión pendiente
        self._setup_shortcuts()

        # Timer de animación de chevrons en streams (efecto de flujo).
        # Cada 80ms avanza el offset de todos los streams.  Visual sutil
        # estilo Aspen "siga el flujo".
        from PySide6.QtCore import QTimer
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(80)   # 12.5 fps, sutil
        self._anim_timer.timeout.connect(self._tick_stream_animation)
        self._anim_enabled = True
        self._anim_timer.start()

    def _tick_stream_animation(self):
        """Avanza el offset de chevrons en cada stream y los re-renderiza.
        Llamado por self._anim_timer cada 80ms."""
        if not self._anim_enabled:
            return
        # Skip si ventana no visible (minimizada / ocultada por otra app):
        # no tiene sentido gastar CPU re-dibujando lo que nadie ve.
        if not self.isVisible():
            return
        STEP = 3.0   # px por frame
        # Snapshot defensivo: si el user elimina un stream MIENTRAS el
        # timer está ticando, el dict cambia bajo nuestros pies → crash.
        for sid, item in list(self.scene.stream_items.items()):
            try:
                item._anim_offset = (item._anim_offset + STEP) % 130.0
                pts = getattr(item, '_last_pts', None)
                if pts:
                    item._draw_direction_arrows(pts)
            except RuntimeError:
                # Qt C++ object deleted underneath (item destroyed)
                continue

    def closeEvent(self, event):
        """Detiene el timer de animación al cerrar la ventana.
        Sin esto el QTimer seguía ticando aún después de close(),
        manteniendo viva la ventana y consumiendo CPU."""
        try:
            self._anim_timer.stop()
        except Exception:
            pass
        super().closeEvent(event)

    def toggle_animation(self, enabled: bool):
        """Activa/desactiva animación de chevrons (toolbar toggle)."""
        self._anim_enabled = enabled
        if not enabled:
            # Reset offsets a 0 para que queden quietos
            for sid, item in self.scene.stream_items.items():
                item._anim_offset = 0.0
                pts = getattr(item, '_last_pts', None)
                if pts:
                    item._draw_direction_arrows(pts)

    def _setup_shortcuts(self):
        from PySide6.QtGui import QShortcut
        # navegación / archivo
        for seq, slot in (
            (QKeySequence.New,    self.action_new),
            (QKeySequence.Open,   self.action_open),
            (QKeySequence.Save,   self.action_save),
            (QKeySequence.Quit,   self.close),
            ("Ctrl+E",            self.action_export_pdf),       # default = PDF
            ("Ctrl+Shift+E",      self.action_export_svg),
            ("F5",                self.action_solve),
            ("F9",                self.action_compute),
            ("Ctrl+Plus",         self.view.zoom_in),
            ("Ctrl+-",            self.view.zoom_out),
            ("Ctrl+0",            self.view.zoom_reset),
            ("Ctrl+1",            self.view.zoom_fit),
        ):
            sc = QShortcut(QKeySequence(seq), self)
            sc.activated.connect(slot)
        # escapar conexión pendiente / borrar
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.cancel_connection)
        QShortcut(QKeySequence(Qt.Key_Delete), self, activated=self.action_delete)

    # ---------------------------------------------------
    # WIDGETS
    # ---------------------------------------------------

    def _build_toolbar(self):
        # Dos toolbars apiladas vertical (siempre visibles, sin overflow).
        # Top:   archivo / ejemplos / edición / zoom / vista
        # Bottom: análisis / solve / exportar
        tb = self.addToolBar("Workflow — Archivo y edición")
        tb.setMovable(False)
        # break para forzar la segunda toolbar abajo en una NUEVA línea
        from PySide6.QtCore import QSize
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        # Helper para crear QIcon desde el set HYSYS — color del texto
        # primario del estilo para que combine con el resto de la UI.
        from icons import make_qicon as _mk
        _ICON_COLOR = "#3a3a3a"
        # Guardamos el helper como atributo de la ventana para usarlo
        # en otros lugares (menús contextuales, dialogs).
        self._mk_icon = _mk
        self._icon_color = _ICON_COLOR

        def add_btn(text, slot, icon_id=None, sep=False, toolbar=None):
            tb_target = toolbar if toolbar is not None else tb
            act = QAction(text, self)
            act.triggered.connect(slot)
            if icon_id is not None:
                ic = _mk(icon_id, color=_ICON_COLOR, size=20)
                if ic is not None:
                    act.setIcon(ic)
            tb_target.addAction(act)
            if sep:
                tb_target.addSeparator()

        add_btn("Nuevo",     self.action_new,  "file-new")
        add_btn("Abrir…",    self.action_open, "file-open")
        add_btn("Guardar…",  self.action_save, "file-save")

        # menú de ejemplos
        examples_act = QAction("Ejemplos ▾", self)
        examples_menu = QMenu(self)
        from flowsheet_ui import FlowsheetEditor as _LegacyEditor
        # reusar los example builders del editor legacy
        def make_loader(key):
            return lambda: self.action_load_example(key)
        # Ícono compartido para todos los ejemplos legacy (equipo genérico)
        _ic_ex = _mk("act-examples", color=_ICON_COLOR, size=18) or QIcon()
        # Reactor para los 3 ejemplos con reacciones (Capas 4-5)
        _ic_rxn = _mk("cfg-rxn", color="#c41e3a", size=18) or QIcon()

        examples_menu.addAction(_ic_ex, "HDA — Hidrodealquilación de tolueno",  make_loader("hda"))
        examples_menu.addAction(_ic_ex, "Síntesis de metanol",                  make_loader("methanol"))
        examples_menu.addAction(_ic_ex, "Destilación binaria benceno/tolueno",  make_loader("distillation"))
        examples_menu.addSeparator()
        examples_menu.addAction(_ic_ex, "Síntesis de amoníaco (Haber-Bosch)",   make_loader("ammonia"))
        examples_menu.addAction(_ic_ex, "Producción de etanol",                 make_loader("ethanol"))
        examples_menu.addAction(_ic_ex, "Producción de biodiesel",              make_loader("biodiesel"))
        examples_menu.addAction(_ic_ex, "Refinería atmosférica simplificada",   make_loader("cdu"))
        examples_menu.addSeparator()
        # ---- Procesos industriales completos ----
        examples_menu.addAction(_ic_ex, "HDA completo (Douglas, escala industrial)", make_loader("hda_full"))
        examples_menu.addAction(_ic_ex, "Endulzamiento de gas natural (MDEA)",       make_loader("gas_sweet"))
        examples_menu.addAction(_ic_ex, "Planta de azúcar (caña)",                   make_loader("sugar"))
        examples_menu.addSeparator()
        examples_menu.addAction(_ic_rxn, "Reformado SMR + WGS (reactor de equilibrio Capa 4)",
                                  make_loader("smr_eq"))
        examples_menu.addAction(_ic_rxn, "Cracking de etano (reactor PFR Capa 5)",
                                  make_loader("ethane_pfr"))
        examples_menu.addAction(_ic_rxn, "Haber-Bosch con recycle (NH3, loop reactivo)",
                                  make_loader("haber_rec"))
        examples_menu.addSeparator()
        # Capa 6 NRTL — destilación azeotrópica
        _ic_az = _mk("an-pinch", color="#1565c0", size=18) or QIcon()
        examples_menu.addAction(_ic_az,
            "Destilación azeotrópica etanol-agua (NRTL Capa 6)",
            make_loader("dist_eth_az"))
        examples_menu.addAction(_ic_az,
            "Reactor + flash + columna AUTOMÁTICOS (FUG + NRTL)",
            make_loader("rxn_flash_col"))
        examples_menu.addAction(_mk("eq-pump", color="#1565c0", size=18) or QIcon(),
            "Planta hidráulica con auto-sizing de bomba",
            make_loader("hydraulic"))
        examples_menu.addSeparator()
        # ⭐ Flagship example
        _ic_flag = _mk("an-case-study", color="#e65100", size=18) or QIcon()
        examples_menu.addAction(_ic_flag,
            "⭐ PLANTA INDUSTRIAL COMPLETA (MeOH + servicios + BOP)",
            make_loader("industrial"))
        # 🇵🇪 QUIMPAC chlor-alkali
        examples_menu.addAction(
            _mk("eq-reactor", color="#1976d2", size=18) or QIcon(),
            "🇵🇪 QUIMPAC — cloro-álcali (membrana, estilo Oquendo)",
            make_loader("quimpac"))
        # ⚗️ HNO3 Ostwald (DuPont)
        examples_menu.addAction(
            _mk("eq-reactor", color="#c62828", size=18) or QIcon(),
            "⚗️ HNO3 Ostwald (dual-presión, estilo DuPont 1920s)",
            make_loader("hno3"))
        # 🏭 Refinería Talara (Petroperú)
        examples_menu.addAction(
            _mk("eq-tower", color="#5d4037", size=18) or QIcon(),
            "🏭 REFINERÍA TALARA — PMRT (95k BPD, conversión profunda)",
            make_loader("talara"))
        # Ícono del menú Ejemplos (templates)
        examples_act.setIcon(_mk("act-examples", color=_ICON_COLOR, size=20))
        examples_act.setMenu(examples_menu)
        tb.addAction(examples_act)
        # workaround: QAction con menu necesita un QToolButton para mostrar el dropdown
        btn = tb.widgetForAction(examples_act)
        if btn is not None and hasattr(btn, "setPopupMode"):
            from PySide6.QtWidgets import QToolButton
            btn.setPopupMode(QToolButton.InstantPopup)
        tb.addSeparator()

        add_btn("Borrar selección", self.action_delete, "edit-delete")
        # undo/redo
        self.undo_action = self.undo_stack.createUndoAction(self, "↶ Deshacer")
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.setIcon(_mk("edit-undo", color=_ICON_COLOR, size=20))
        tb.addAction(self.undo_action)
        self.redo_action = self.undo_stack.createRedoAction(self, "↷ Rehacer")
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.redo_action.setIcon(_mk("edit-redo", color=_ICON_COLOR, size=20))
        tb.addAction(self.redo_action)
        tb.addSeparator()

        add_btn("Zoom −",     self.view.zoom_out,   "zoom-out")
        add_btn("100 %",      self.view.zoom_reset, "zoom-100")
        add_btn("Zoom +",     self.view.zoom_in,    "zoom-in")
        add_btn("Ajustar",    self.view.zoom_fit,   "zoom-fit")

        # ---- SEGUNDA FILA ----
        # addToolBarBreak fuerza que la siguiente toolbar se renderice
        # debajo, no a la derecha.  Ambas filas son siempre visibles.
        self.addToolBarBreak()
        tb2 = self.addToolBar("Workflow — Cálculo y análisis")
        tb2.setMovable(False)
        tb2.setIconSize(QSize(20, 20))
        tb2.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        add_btn("OPEX extras…",    self.action_opex_extras, "act-money",     toolbar=tb2)
        add_btn("Solve balances",  self.action_solve,       "sim-run",       toolbar=tb2)
        add_btn("Setpoints…",      self.action_setpoints,   "act-setpoint",  toolbar=tb2)
        add_btn("DOF / Balance…",  self.action_dof,         "act-dof",       toolbar=tb2)
        add_btn("Auto-size S",     self.action_autosize,    "act-sizing",    toolbar=tb2)
        # Re-bind tb a tb2 para el resto de los add que vienen abajo
        tb = tb2
        # toggle del dock de tabla de corrientes (creado en
        # _build_streams_dock); toggleViewAction() ya viene cableado
        # para mostrar/ocultar y refleja el estado actual.
        if hasattr(self, "streams_dock") and self.streams_dock is not None:
            toggle = self.streams_dock.toggleViewAction()
            toggle.setText("Tabla de corrientes")
            toggle.setShortcut("Ctrl+T")
            toggle.setIcon(_mk("wb-table", color=_ICON_COLOR, size=20))
            tb.addAction(toggle)
        # toggle del papel de dibujo PFD (marco + leyenda + cuadro de título)
        paper_act = QAction("Marco PFD", self)
        paper_act.setCheckable(True)
        paper_act.setShortcut("Ctrl+M")
        paper_act.triggered.connect(self.action_toggle_paper)
        paper_act.setIcon(_mk("act-frame-pfd", color=_ICON_COLOR, size=20))
        tb.addAction(paper_act)
        self._paper_action = paper_act
        # toggle de animación de flujo (chevrons que avanzan)
        anim_act = QAction("Anim. flujo", self)
        anim_act.setCheckable(True)
        anim_act.setChecked(True)
        anim_act.setToolTip("Activar/desactivar animación de flechas\n"
                              "direccionales en los streams.")
        anim_act.setIcon(_mk("sim-active", color=_ICON_COLOR, size=20))
        anim_act.triggered.connect(self.toggle_animation)
        tb.addAction(anim_act)
        add_btn("Calcular",        self.action_compute,           "sim-refresh")
        add_btn("Perfil econ.…",         self.action_econ_profile,    "act-money")
        add_btn("Análisis económico →", self.action_launch_analysis, "an-case-study")
        tb.addSeparator()

        # menú Exportar
        export_act = QAction("Exportar ▾", self)
        export_act.setIcon(_mk("file-export", color=_ICON_COLOR, size=20))
        export_menu = QMenu(self)
        export_menu.addAction(_mk("file-print", color=_ICON_COLOR, size=18) or QIcon(),
                                "PDF…", self.action_export_pdf)
        export_menu.addAction(_mk("file-export", color=_ICON_COLOR, size=18) or QIcon(),
                                "SVG (vectorial)…", self.action_export_svg)
        export_menu.addAction(_mk("file-export", color=_ICON_COLOR, size=18) or QIcon(),
                                "PNG (alta resolución)…", self.action_export_png)
        export_act.setMenu(export_menu)
        tb.addAction(export_act)
        ebtn = tb.widgetForAction(export_act)
        if ebtn is not None and hasattr(ebtn, "setPopupMode"):
            ebtn.setPopupMode(QToolButton.InstantPopup)

    def _build_library_dock(self):
        dock = QDockWidget(" Biblioteca de equipos ", self)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)

        info = QLabel(
            "Arrastrá un equipo al lienzo, o doble-click para agregarlo "
            "al centro de la vista.  Doble-click en un bloque del lienzo → editar."
        )
        info.setStyleSheet("color:#666; font-size:9pt;")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.lib_tree = _LibraryTree(self)
        self.lib_tree.setHeaderHidden(True)
        # Categoría especial "Corrientes" — primero del árbol, con
        # dos ítems para drag&drop de streams flotantes.
        streams_cat = QTreeWidgetItem(["Corrientes"])
        s_mass = QTreeWidgetItem(["→  Corriente de masa"])
        s_mass.setData(0, Qt.UserRole, "__STREAM__mass")
        s_mass.setToolTip(0, "Arrastrá al lienzo: aparece una flecha "
                               "suelta.\nArrastrá los endpoints a un puerto "
                               "para conectar.")
        s_energy = QTreeWidgetItem(["⚡  Corriente de energía (kW)"])
        s_energy.setData(0, Qt.UserRole, "__STREAM__energy")
        s_energy.setToolTip(0, "Arrastrá al lienzo: aparece una flecha "
                                 "de calor suelta.\nAl conectar dos bloques, "
                                 "el solver acopla sus duties por energy_kW.")
        streams_cat.addChild(s_mass)
        streams_cat.addChild(s_energy)
        streams_cat.setExpanded(True)
        self.lib_tree.addTopLevelItem(streams_cat)
        # Categorías de equipos (catálogo)
        cats = eq.por_categoria()
        for cat, names in cats.items():
            parent = QTreeWidgetItem([cat])
            for n in names:
                child = QTreeWidgetItem([n])
                child.setData(0, Qt.UserRole, n)
                parent.addChild(child)
            parent.setExpanded(True)
            self.lib_tree.addTopLevelItem(parent)
        self.lib_tree.itemDoubleClicked.connect(self._on_lib_double_click)
        layout.addWidget(self.lib_tree)

        add_btn = QPushButton("+ Agregar al diagrama")
        add_btn.clicked.connect(self._add_selected_from_lib)
        layout.addWidget(add_btn)

        dock.setWidget(widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

    def _build_properties_dock(self):
        dock = QDockWidget(" Propiedades ", self)
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        self.prop_label = QLabel("(nada seleccionado)")
        self.prop_label.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 9pt;"
        )
        self.prop_label.setWordWrap(True)
        self.prop_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(self.prop_label)

        # ---- Perfil de reactor PFR / batch / barras CSTR (oculto hasta
        #      seleccionar un reactor con solve corrido) ----
        self.pfr_panel = QWidget()
        pfr_lay = QVBoxLayout(self.pfr_panel)
        pfr_lay.setContentsMargins(0, 4, 0, 0)
        # toggles
        from PySide6.QtWidgets import QButtonGroup, QRadioButton
        toggles = QHBoxLayout()
        self.pfr_y_conv = QRadioButton("Conversión %")
        self.pfr_y_flow = QRadioButton("Flujo mol/s")
        self.pfr_y_conv.setChecked(True)
        gy = QButtonGroup(self.pfr_panel)
        gy.addButton(self.pfr_y_conv); gy.addButton(self.pfr_y_flow)
        self.pfr_x_vol = QRadioButton("vs Volumen")
        self.pfr_x_len = QRadioButton("vs Longitud")
        self.pfr_x_len.setChecked(True)
        gx = QButtonGroup(self.pfr_panel)
        gx.addButton(self.pfr_x_vol); gx.addButton(self.pfr_x_len)
        for w in (self.pfr_y_conv, self.pfr_y_flow):
            w.setStyleSheet("font-size: 8pt;")
            toggles.addWidget(w)
        toggles.addSpacing(8)
        for w in (self.pfr_x_len, self.pfr_x_vol):
            w.setStyleSheet("font-size: 8pt;")
            toggles.addWidget(w)
        toggles.addStretch(1)
        pfr_lay.addLayout(toggles)
        if _MPL_OK:
            self._pfr_fig = Figure(figsize=(3.4, 2.6), dpi=90)
            self._pfr_canvas = _MplCanvas(self._pfr_fig)
            self._pfr_canvas.setMinimumHeight(220)
            pfr_lay.addWidget(self._pfr_canvas)
            for w in (self.pfr_y_conv, self.pfr_y_flow,
                      self.pfr_x_vol, self.pfr_x_len):
                w.toggled.connect(self._redraw_pfr_profile)
        else:
            pfr_lay.addWidget(QLabel(
                "matplotlib no disponible — perfil no se puede graficar.\n"
                "pip install matplotlib"
            ))
            self._pfr_canvas = None
        self.pfr_panel.setVisible(False)
        layout.addWidget(self.pfr_panel)
        self._pfr_current_block = None

        layout.addStretch(1)

        self.results_box = QTextEdit()
        self.results_box.setReadOnly(True)
        self.results_box.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 9pt; color: #1565c0;"
        )
        self.results_box.setMaximumHeight(280)
        self.results_box.setPlainText("(apretá Calcular para estimar el ISBL)")
        layout.addWidget(self.results_box)

        dock.setWidget(widget)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def _build_streams_dock(self):
        """Tabla de corrientes con cambio de unidades."""
        self.streams_dock = StreamsTableDock(self, self)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.streams_dock)
        self.streams_dock.refresh()

    def _build_statusbar(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self._update_status()

    def _update_status(self):
        # Status global del último solve.  Si el flowsheet fue editado
        # después del último solve, prepend "◌" indicando datos stale.
        st = getattr(self, "_last_overall_status", None)
        dirty = getattr(self, "_dirty_after_solve", True)
        if st is None or not self.fs.blocks:
            chip = ""
        else:
            if dirty:
                # Datos stale: violeta + label específica
                icon = STATUS_ICONS["stale"]
                label = STATUS_LABELS["stale"]
                color = COLOR_STATUS_DIRTY
            else:
                icon = STATUS_ICONS.get(st, "")
                label = STATUS_LABELS.get(st, "")
                color = STATUS_COLORS.get(st, COLOR_STATUS_UNRUN)
            # Wrappear el chip con color via HTML (statusbar acepta richtext)
            chip = (f'<span style="color:{color.name()}; '
                     f'font-weight:bold;">{icon} {label}</span>  ·  ')
        msg = (chip +
                f"{len(self.fs.blocks)} equipos · "
                f"{len(self.fs.streams)} corrientes")
        # QStatusBar.showMessage no acepta richtext directo — usamos un
        # QLabel permanente al status bar, lazy-init.
        if not hasattr(self, "_status_label_rich"):
            from PySide6.QtWidgets import QLabel as _QL
            self._status_label_rich = _QL()
            self._status_label_rich.setTextFormat(Qt.RichText)
            self.status.addWidget(self._status_label_rich, 1)
        self._status_label_rich.setText(msg)
        # refrescar tabla de corrientes (si ya existe; durante __init__
        # podría no existir todavía)
        if hasattr(self, "streams_dock") and self.streams_dock is not None:
            self.streams_dock.refresh()

    def _apply_solver_status(self, result):
        """Propaga `result.block_status` y `result.stream_status` a los
        items visuales del canvas.  Cada item se colorea según su
        status (verde/azul/amarillo/rojo).  Llamado solo después de
        action_solve(); editar algo después marca todo como 'stale'.

        También refresca los badges de duty (kW) en cada bloque para
        reflejar duties recién inferidos por auto_set_duties_from_thermo.
        """
        for bid, item in self.block_items_iter():
            st = result.block_status.get(bid, "unrun")
            item.set_status(st)
            # Refrescar badge de duty (puede haber cambiado en el solve)
            if hasattr(item, "_update_duty_badge"):
                item._update_duty_badge()
        for sid, item in self.stream_items_iter():
            st = result.stream_status.get(sid, "unrun")
            item.set_status(st)
            # Re-renderizar path para refrescar el label (composición
            # puede ser nueva post-solve)
            item.update_path(rebuild_handles=False)

    def _mark_dirty(self):
        """Marcar que el flowsheet fue editado después del último solve.
        Llamado desde edit dialogs, drag end, delete, etc.

        Efecto visual:
          - status bar muestra '◌ Datos stale — re-ejecutar (F5)' violeta
          - todos los halos de bloques + lineas de streams pasan a azul
            stale, para que el user vea inmediatamente que los colores
            verde/amarillo/rojo previos YA no reflejan el estado actual.
        """
        if not getattr(self, "_dirty_after_solve", True):
            self._dirty_after_solve = True
            # Repinta TODO el flowsheet como stale.  Cualquier edit
            # invalida los colores del último solve.
            for bid, item in self.block_items_iter():
                item.set_status("stale")
            for sid, item in self.stream_items_iter():
                item.set_status("stale")
            if hasattr(self, "_update_status"):
                self._update_status()

    # ---------------------------------------------------
    # ACCIONES — File
    # ---------------------------------------------------

    def action_new(self):
        if self.fs.blocks:
            ans = QMessageBox.question(
                self, "Nuevo diagrama",
                "¿Descartar el diagrama actual y empezar vacío?",
            )
            if ans != QMessageBox.Yes:
                return
        self.fs = Flowsheet()
        self.scene.clear_flowsheet()
        self._update_status()
        self.prop_label.setText("(nada seleccionado)")
        self.results_box.setPlainText("(apretá Calcular para estimar el ISBL)")

    def action_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir diagrama", "", "JSON (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.fs = Flowsheet.from_dict(data)
        except Exception as e:
            QMessageBox.critical(self, "Error al abrir",
                                  f"{type(e).__name__}: {e}")
            return
        self._rebuild_scene()
        self.view.zoom_fit()
        self._update_status()

    def action_save(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Guardar diagrama", "", "JSON (*.json)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.fs.to_dict(), f, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "Error al guardar",
                                  f"{type(e).__name__}: {e}")
            return
        QMessageBox.information(self, "Guardado", f"Diagrama guardado en:\n{path}")

    # ---------------------------------------------------
    # ACCIONES — Examples (reusa builders del editor Tk)
    # ---------------------------------------------------

    def action_load_example(self, key):
        if self.fs.blocks:
            ans = QMessageBox.question(
                self, "Cargar ejemplo",
                "Esto va a reemplazar el diagrama actual. ¿Continuar?",
            )
            if ans != QMessageBox.Yes:
                return
        before = self.begin_action()
        from flowsheet_ui import FlowsheetEditor as TkEditor
        self.fs = Flowsheet()
        shim = _ExampleBuilderShim(self.fs)
        # builder_map: clave → (método del builder, título_PFD, area, drawing_no)
        builder_map = {
            "hda":          (TkEditor._example_hda,
                              "HDA — Hidrodealquilación de tolueno",
                              "100 — Reacción / Sep.", "PFD-HDA-001"),
            "methanol":     (TkEditor._example_methanol,
                              "Síntesis de metanol", "100 — Reacción / Sep.",
                              "PFD-MeOH-001"),
            "distillation": (TkEditor._example_distillation,
                              "Destilación binaria benceno/tolueno",
                              "200 — Separación", "PFD-BTX-001"),
            "ammonia":      (TkEditor._example_ammonia,
                              "Síntesis de amoníaco (Haber-Bosch)",
                              "100 — Reacción", "PFD-NH3-001"),
            "ethanol":      (TkEditor._example_ethanol,
                              "Producción de etanol (fermentación + destilación)",
                              "200 — Fermentación / Sep.", "PFD-EtOH-001"),
            "biodiesel":    (TkEditor._example_biodiesel,
                              "Producción de biodiesel (transesterificación)",
                              "100 — Reacción / Sep.", "PFD-BD-001"),
            "cdu":          (TkEditor._example_crude_distillation,
                              "Refinería atmosférica simplificada (CDU)",
                              "100 — Destilación primaria", "PFD-CDU-001"),
            # ---- Procesos industriales completos (mayor escala, recycles) ----
            "hda_full":     (TkEditor._example_hda_full,
                              "HDA completo (Douglas) — escala industrial",
                              "100 — Reacción / Separación", "PFD-HDA-FULL"),
            "gas_sweet":    (TkEditor._example_gas_sweetening,
                              "Endulzamiento de gas natural (MDEA)",
                              "200 — Tratamiento de gas", "PFD-GAS-001"),
            "sugar":        (TkEditor._example_sugar_mill,
                              "Planta de azúcar (caña → cristalización)",
                              "100 — Cristalización", "PFD-SUGAR-001"),
            "smr_eq":       (TkEditor._example_smr_equilibrium,
                              "Reformado SMR + WGS — reactor de equilibrio (Capa 4)",
                              "100 — Reacción", "PFD-SMR-EQ-001"),
            "ethane_pfr":   (TkEditor._example_ethane_cracker_pfr,
                              "Cracking de etano — reactor PFR cinético (Capa 5)",
                              "100 — Pirólisis", "PFD-ETH-PFR-001"),
            "haber_rec":    (TkEditor._example_haber_recycle,
                              "Haber-Bosch con recycle — NH3 con loop reactivo",
                              "100 — Síntesis NH3", "PFD-NH3-REC-001"),
            "dist_eth_az":  (TkEditor._example_distillation_ethanol_water,
                              "Destilación azeotrópica etanol-agua (NRTL Capa 6)",
                              "200 — Separación", "PFD-ETH-AZ-001"),
            "rxn_flash_col": (TkEditor._example_reactor_flash_column,
                               "Tren reactor + flash + columna AUTOMÁTICOS",
                               "100 — Demo solver", "PFD-AUTO-001"),
            "hydraulic":    (TkEditor._example_hydraulic_plant,
                              "Planta hidráulica — bomba auto-sized",
                              "200 — Hidráulica", "PFD-HYD-001"),
            "industrial":   (TkEditor._example_industrial_complete,
                              "PLANTA INDUSTRIAL COMPLETA — MeOH + servicios + BOP",
                              "100/200/300 — Plant Integration",
                              "PFD-INDUSTRIAL-001"),
            "quimpac":      (TkEditor._example_quimpac_chloralkali,
                              "QUIMPAC — Cloro-álcali (celda de membrana)",
                              "100/200/300 — Chlor-Alkali Plant",
                              "PFD-QUIMPAC-001"),
            "hno3":         (TkEditor._example_hno3_ostwald,
                              "HNO3 Ostwald — DuPont dual-presión",
                              "100/200/300/400/500 — Ostwald Plant",
                              "PFD-OSTWALD-001"),
            "talara":       (TkEditor._example_talara_refinery,
                              "REFINERÍA TALARA — PMRT Petroperú",
                              "100-900 — Conversión Profunda",
                              "PFD-TALARA-001"),
            # ── Catálogo educativo Lote 1 (alimentaria simple) ──
            "pasteurizer":  (TkEditor._example_pasteurizer,
                              "Pasteurizador HTST de jugo",
                              "100 — Alimentaria",
                              "PFD-PAST-001"),
            "pineapple":    (TkEditor._example_pineapple_juice,
                              "Jugo de piña concentrado (evaporación)",
                              "100 — Alimentaria",
                              "PFD-PINE-001"),
            "potato_chips": (TkEditor._example_potato_chips,
                              "Papas fritas (freído industrial)",
                              "100 — Alimentaria",
                              "PFD-CHIP-001"),
            # ── Catálogo educativo Lote 2 (bioproceso + química gratis) ──
            "beer":         (TkEditor._example_beer_brewing,
                              "Cervecería — fermentación batch→continuo",
                              "100 — Bioproceso",
                              "PFD-BEER-001"),
            "sulfuric":     (TkEditor._example_sulfuric_acid,
                              "Ácido sulfúrico (contacto, V₂O₅)",
                              "100 — Inorgánica pesada",
                              "PFD-H2SO4-001"),
            # ── Catálogo educativo Lote 3 (química fina + polímeros) ──
            "acetic":       (TkEditor._example_acetic_acid,
                              "Ácido acético (carbonilación Cativa)",
                              "100 — Química fina",
                              "PFD-AcOH-001"),
            "ldpe":         (TkEditor._example_polyethylene,
                              "Polietileno LDPE (autoclave HP)",
                              "100 — Polímeros",
                              "PFD-LDPE-001"),
            # ── Catálogo educativo Lote 4a (inorgánica + materiales) ──
            "chloralkali_hcl": (TkEditor._example_chloralkali_hcl,
                              "Cloro-álcali compacto + HCl",
                              "100 — Inorgánica pesada",
                              "PFD-CAHCL-001"),
            "cement":       (TkEditor._example_cement,
                              "Cemento Portland (horno rotatorio)",
                              "100 — Materiales",
                              "PFD-CEM-001"),
            "glass":        (TkEditor._example_glass,
                              "Vidrio sodocálcico (horno de fusión)",
                              "100 — Materiales",
                              "PFD-GLASS-001"),
            # ── Catálogo educativo Lote 4b (saponificación + urea) ──
            "soap":         (TkEditor._example_soap,
                              "Jabón por saponificación",
                              "100 — Consumo / química",
                              "PFD-SOAP-001"),
            "urea":         (TkEditor._example_urea,
                              "Urea (Bosch-Meiser, fertilizante)",
                              "100 — Fertilizantes",
                              "PFD-UREA-001"),
            "leche_gloria": (TkEditor._example_leche_gloria,
                              "LECHE GLORIA — Planta láctea integrada",
                              "100 — Alimentaria (caso integrado)",
                              "PFD-GLORIA-001"),
            # ── Catálogo educativo Lote 5 (industrias adicionales) ──
            "ethylene_crk": (TkEditor._example_ethylene_cracking,
                              "Etileno por cracking de etano (R011 Modo A)",
                              "100 — Petroquímica",
                              "PFD-ETH-001"),
            "air_sep":      (TkEditor._example_air_separation,
                              "Separación criogénica de aire O₂/N₂",
                              "100 — Gases industriales",
                              "PFD-AIRSEP-001"),
            "water_treat":  (TkEditor._example_water_treatment,
                              "Tratamiento de agua potable",
                              "200 — Servicios / ambiental",
                              "PFD-WATER-001"),
            "bread":        (TkEditor._example_bread_baking,
                              "Panificación industrial (batch→continuo)",
                              "100 — Alimentaria",
                              "PFD-BREAD-001"),
            "penicillin":   (TkEditor._example_penicillin,
                              "Penicilina por fermentación (batch→continuo)",
                              "100 — Farmacéutica",
                              "PFD-PEN-001"),
            # ── Catálogo educativo Lote 6 (Tier 2 ilustrativos) ──
            "rankine":      (TkEditor._example_rankine_cycle,
                              "Central térmica — ciclo Rankine (Tier 2)",
                              "200 — Energía (ilustrativo)",
                              "PFD-RANK-001"),
            "nuclear":      (TkEditor._example_nuclear_steam,
                              "Isla nuclear — circuito 2° (Tier 2)",
                              "200 — Energía (ilustrativo)",
                              "PFD-NUC-001"),
            "desal":        (TkEditor._example_desalination,
                              "Desalinización MED multi-efecto (Tier 2)",
                              "200 — Agua (ilustrativo)",
                              "PFD-DESAL-001"),
        }
        entry = builder_map.get(key)
        if entry is None:
            return
        builder, title, area, dwg_no = entry
        builder(shim)
        # Estado inicial: stale (azul). El user ve los bloques en azul
        # hasta que apriete F5 para correr el solver y verificar el
        # balance del ejemplo.
        self._last_overall_status = None
        self._dirty_after_solve = True
        self._rebuild_scene()

        # Auto-mostrar el marco PFD con los datos del ejemplo
        self.scene.set_paper_visible(False)        # reset si había uno previo
        self.scene.paper_frame = None
        self.scene.set_paper_visible(True, project_title=title,
                                       area=area, drawing_no=dwg_no)
        if hasattr(self, "_paper_action"):
            self._paper_action.setChecked(True)

        self.view.zoom_fit()
        self._update_status()
        self.end_action(f"Cargar ejemplo: {key}", before)

    # ---------------------------------------------------
    # ACCIONES — Otros
    # ---------------------------------------------------

    def action_delete(self):
        selected = list(self.scene.selectedItems())
        if not selected:
            return
        before = self.begin_action()
        for it in selected:
            if isinstance(it, BlockItem):
                self._delete_block(it.model.id)
            elif isinstance(it, StreamItem):
                self._delete_stream(it.model.id)
        self._mark_dirty()
        self._update_status()
        self.end_action(f"Borrar selección ({len(selected)})", before)

    def action_toggle_paper(self, checked: bool):
        """Muestra/oculta el papel de dibujo PFD (marco + cuadro de
        título + leyenda)."""
        self.scene.set_paper_visible(checked)

    def action_dof(self):
        """Análisis estructural de grados de libertad (DOF audit).

        Usa propagación topológica de masa + composición desde locks
        del user: detecta streams que NO pueden determinarse, bloques
        con ecuaciones de balance incompletas, y reactores isotermales
        sin T_op_K.  Detecta REAL under-spec (a diferencia del análisis
        per-bloque que sobre-estimaba)."""
        if not self.fs.blocks:
            QMessageBox.information(self, "DOF", "El diagrama está vacío.")
            return
        import dof_audit as _da
        report = _da.analyze_flowsheet(self.fs)
        text = _da.format_report(report)

        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Análisis estructural — DOF")
        dlg.resize(820, 540)
        v = QVBoxLayout(dlg)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setStyleSheet("font-family: Consolas, monospace; font-size: 9pt;")
        txt.setPlainText(text)
        v.addWidget(txt)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)
        dlg.exec()

    def action_autosize(self):
        """Auto-dimensiona S de cada bloque desde resultados del solver.

        HX usa A = Q/(U·ΔTlm), reactores V = m·τ/ρ, bombas W = m·ΔP/(ρη),
        compresores W politrópico, torres D del Souders-Brown + H = N·0.6,
        vessels τ_separator, tanques 7 días de buffer.

        Reemplaza el S "manual" inicial por algo derivado del balance.
        Útil después de Solve balances → da una primera estimación
        físicamente coherente para CAPEX."""
        if not self.fs.blocks:
            QMessageBox.information(self, "Auto-size",
                                      "El diagrama está vacío.")
            return
        ans = QMessageBox.question(
            self, "Auto-size equipos",
            "¿Recalcular S de cada bloque desde duty, mass_flow, ΔP y\n"
            "T_op del último solve?  Sobreescribe los S actuales.\n\n"
            "Solo bloques con datos suficientes se modifican.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            return
        import equipment_sizing as es
        # Snapshot para undo
        before = self.begin_action()
        try:
            results = es.auto_size_blocks(self.fs, only_if_unset=False)
        except Exception as e:
            QMessageBox.critical(self, "Error de cálculo",
                                  f"{type(e).__name__}: {e}")
            return
        self.end_action("Auto-size equipment", before)
        # Re-render para que los tooltips/badges reflejen el nuevo S
        self._rebuild_scene()
        # Mostrar log
        text = es.format_sizing_log(results)
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Auto-size — resultados")
        dlg.resize(620, 420)
        v = QVBoxLayout(dlg)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setStyleSheet("font-family: Consolas, monospace; font-size: 9pt;")
        txt.setPlainText(text)
        v.addWidget(txt)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)
        dlg.exec()

    def action_setpoints(self):
        """Verifica los setpoints declarados (target_temperature en
        streams) y ofrece resolverlos por goal-seek de duty."""
        if not self.fs.blocks:
            QMessageBox.information(self, "Setpoints", "El diagrama está vacío.")
            return
        results = fsolv.verify_setpoints(self.fs)
        if not results:
            QMessageBox.information(
                self, "Setpoints",
                "No hay setpoints declarados.\n\n"
                "Para agregar un setpoint:\n"
                "1. Doble-click sobre un stream\n"
                "2. Marcá la casilla 'Setpoint T' y poné la T objetivo\n"
                "3. Volvé a este menú y resolvé"
            )
            return
        lines = ["Setpoints declarados:\n"]
        any_off = False
        for r in results:
            mark = "✓" if r["within_tol"] else "✗"
            if r["kind"] == "T":
                lines.append(
                    f"  {mark} {r['stream_name']}: T objetivo={r['target']:g}°C  "
                    f"actual={r['actual']:.1f}°C  Δ={r['deviation']:+.1f}°C"
                )
            else:
                lines.append(
                    f"  {mark} {r['stream_name']}: pureza {r['component']} "
                    f"objetivo={r['target']:.3f}  actual={r['actual']:.3f}"
                )
            if not r["within_tol"]:
                any_off = True
        msg = "\n".join(lines)
        if not any_off:
            QMessageBox.information(self, "Setpoints — todo OK", msg)
            return
        # Ofrecer resolver los desviados
        msg += ("\n\n¿Resolver setpoints de T por goal-seek? "
                "(ajusta duty del bloque upstream de cada stream)")
        ans = QMessageBox.question(self, "Resolver setpoints", msg)
        if ans != QMessageBox.Yes:
            return
        gs_results = fsolv.solve_setpoints_all(self.fs)
        report = []
        for r in gs_results:
            tag = "✓" if r["success"] else "✗"
            duty_s = f"{r['duty_found']:+.1f} kW" if r["duty_found"] is not None else "—"
            report.append(
                f"  {tag} {r['stream_name']} (block {r['block_name']}): "
                f"duty={duty_s}, T_final={r['t_final']:.1f}°C  [{r['message']}]"
            )
        # refrescar streams en escena
        for sid, sit in self.scene.stream_items.items():
            sit.update_path()
        QMessageBox.information(self, "Goal-seek resultado",
                                  "\n".join(report))

    def action_solve(self):
        if not self.fs.blocks:
            QMessageBox.information(self, "Solve", "El diagrama está vacío.")
            return
        result = fsolv.solve(self.fs)
        # Aplicar status visual (semáforo) a cada bloque y stream
        self._apply_solver_status(result)
        # refrescar streams (mass_flow / T pueden haber cambiado)
        for sid, item in self.stream_items_iter():
            item.update_path()
        self._dirty_after_solve = False
        self._last_overall_status = result.overall_status
        self._update_status()
        # auditar conexiones semánticas
        sem_issues = fval.validate_all_streams(self.fs)
        # mostrar resumen
        summary = result.summary()
        if sem_issues:
            summary += "\n\n─ Validación semántica de conexiones ─\n"
            for name, sev, msg in sem_issues:
                tag = "⚠" if sev == "warn" else "✗"
                summary += f"\n{tag} {name}:\n"
                # solo la primera línea del mensaje (compacto)
                first_line = msg.split("\n")[0] if msg else ""
                summary += f"  {first_line}\n"
        dlg = QMessageBox(self)
        title = "Solver: OK" if (result.success and not sem_issues) \
                else "Solver: revisar"
        dlg.setWindowTitle(title)
        dlg.setText("Resumen del solver:")
        dlg.setDetailedText(summary)
        dlg.exec()

    def action_compute(self):
        # delegamos al editor Tk en una llamada simple para no duplicar lógica.
        # En este scaffold, mostramos los números clave en el panel.
        if not self.fs.blocks:
            QMessageBox.information(self, "Calcular", "Primero agregá al menos un equipo.")
            return
        try:
            equipos = [
                {"nombre": b.eq_type, "S": b.S, "n": b.n}
                for b in self.fs.blocks.values()
            ]
            res = eq.lang_fci(equipos, plant_type="Fluid processing",
                              year_target=2024)
            isbl_mm = eq.isbl_implicito(res["FCI_MMUSD"], 0.30, 0.10, 0.10)
            feeds    = [s for s in self.fs.streams.values() if s.role == "feed"]
            products = [s for s in self.fs.streams.values() if s.role == "product"]
            feed_total    = sum(s.mass_flow for s in feeds)
            product_total = sum(s.mass_flow for s in products)
            revenue = sum(s.mass_flow * s.price_usd_per_tm for s in products)
            raw_mp  = sum(s.mass_flow * s.price_usd_per_tm for s in feeds)
            lines = [
                f"Plant type:   Fluid processing",
                f"Lang factor:  {res['lang_factor']:.2f}",
                f"Σ Cp°:        $ {res['sum_Cp']:>14,.0f}",
                f"FCI:          {res['FCI_MMUSD']:>10.2f} MM USD",
                f"ISBL:         {isbl_mm:>10.2f} MM USD",
                "",
                f"Producción:   {product_total:g} tm/año",
                f"Alimentación: {feed_total:g} tm/año",
                f"Ingresos:     $ {revenue:>14,.0f}",
                f"Materia prima:$ {raw_mp:>14,.0f}",
            ]
            self.results_box.setPlainText("\n".join(lines))
        except Exception as e:
            QMessageBox.critical(self, "Error",
                                  f"{type(e).__name__}: {e}")

    def action_opex_extras(self):
        before = self.begin_action()
        dlg = OpexExtrasDialog(self, self.fs)
        dlg.exec()
        # los cambios se reflejan en self.fs.opex_extras dentro del dialog
        self._update_status()
        self.end_action("Editar OPEX extras", before)

    def action_econ_profile(self):
        """Selector de perfil económico + sliders para HI factor y
        Turton γ (manufacturing overhead).  Estos tres son las
        perillas con mayor impacto en NPV/IRR."""
        import econ_defaults as ed
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout,
                                          QComboBox, QDoubleSpinBox, QLabel,
                                          QDialogButtonBox, QTextEdit)
        dlg = QDialog(self)
        dlg.setWindowTitle("Perfil económico + perillas")
        dlg.resize(620, 640)
        v = QVBoxLayout(dlg)

        v.addWidget(QLabel(
            "Estas tres perillas controlan TODO el costing del próximo\n"
            "'Análisis económico →'.  Editá econ_defaults.py para más fino."))
        form = QFormLayout()

        # 1) Perfil regional
        combo = QComboBox()
        combo.addItems(list(ed.PROFILES.keys()))
        combo.setCurrentText(ed.active_profile())
        form.addRow("Perfil regional:", combo)

        # 2) Heat integration factor
        spin_hi = QDoubleSpinBox()
        spin_hi.setRange(0.0, 1.0); spin_hi.setSingleStep(0.05)
        spin_hi.setDecimals(2)
        spin_hi.setValue(ed.get_heat_integration_factor())
        spin_hi.setToolTip(
            "Fracción del calor que NO se recupera vía cross-exchange.\n"
            "1.0 = sin integración (greenfield)\n"
            "0.5 = típico industrial\n"
            "0.4 = planta moderna con Pinch (default)\n"
            "0.2 = best-in-class MINLP-optimizado")
        form.addRow("Heat integration (0-1):", spin_hi)

        # 3) Turton γ (manufacturing overhead)
        spin_gamma = QDoubleSpinBox()
        spin_gamma.setRange(1.00, 2.00); spin_gamma.setSingleStep(0.01)
        spin_gamma.setDecimals(2)
        spin_gamma.setValue(ed.get_com_coeffs()["gamma_variable"])
        spin_gamma.setToolTip(
            "Multiplicador γ sobre (CUT+CRM+CWT) en Turton Eq 8.2.\n"
            "1.05 = refinería integrada / commodity bulk\n"
            "1.10 = planta con offtake long-term\n"
            "1.23 = standalone chemical plant (Turton default)\n"
            "1.30+ = farma / specialty / agroquímicos")
        form.addRow("Turton γ (1.0-2.0):", spin_gamma)

        v.addLayout(form)

        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setStyleSheet("font-family: Consolas, monospace; "
                                "font-size: 9pt;")

        def _refresh_preview(*_args):
            name = combo.currentText()
            p = ed.load_profile(name)
            lines = [f"PERFIL: {name}\n" + "─" * 50,
                      "\nLABOR"]
            for k, val in p["labor"].items():
                lines.append(f"  {k:32} = {val}")
            lines.append("\nFINANCIAL")
            for k, val in p["financial"].items():
                lines.append(f"  {k:32} = {val}")
            lines.append("\nUTILITY PRICES")
            for k, vd in p["utility_prices"].items():
                lines.append(f"  {k:14} = {vd['price']:>10} {vd.get('unit','')}/u")
            lines.append("\nCAPITAL FRACTIONS")
            for k, val in p["capital_fracs"].items():
                lines.append(f"  {k:32} = {val*100:>5.1f} %")
            lines.append("\nCOM COEFFICIENTS (Turton Eq 8.2)")
            lines.append(f"  α  (FCI con dep)  = 0.180")
            lines.append(f"  β  (Labor coef)   = 2.73")
            lines.append(f"  γ  (overhead)     = {spin_gamma.value():.2f} ← editable")
            lines.append(f"\nHEAT INTEGRATION  = {spin_hi.value():.2f}  ← editable")
            preview.setPlainText("\n".join(lines))

        _refresh_preview()
        combo.currentTextChanged.connect(_refresh_preview)
        spin_hi.valueChanged.connect(_refresh_preview)
        spin_gamma.valueChanged.connect(_refresh_preview)
        v.addWidget(preview)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        v.addWidget(btns)

        if dlg.exec() == QDialog.Accepted:
            ed.set_active_profile(combo.currentText())
            ed.set_heat_integration_factor(spin_hi.value())
            ed.set_com_gamma(spin_gamma.value())
            try:
                import equipment_ports as ep
                ep.refresh_utility_prices()
            except Exception:
                pass
            self.status.showMessage(
                f"Perfil={combo.currentText()}, HI={spin_hi.value():.2f}, "
                f"γ={spin_gamma.value():.2f}.  Aplicar en próximo análisis.",
                6000)

    def action_launch_analysis(self):
        """Genera xlsx temporal y lanza ANA.py como subprocess.
        El diagrama queda intacto en esta ventana."""
        if not self.fs.blocks:
            ans = QMessageBox.question(
                self, "Sin proceso modelado",
                "El diagrama está vacío. ¿Abrir el análisis económico igual?",
            )
            if ans != QMessageBox.Yes:
                return
            feeds, products, isbl = [], [], None
        else:
            # validar mass balance (energía es informativa, no bloquea)
            mb_errors = fsolv._check_mass_balance(self.fs, tol_rel=0.005)
            if mb_errors:
                ans = QMessageBox.question(
                    self, "Balance de masa no cuadra",
                    "Los siguientes equipos no cierran balance:\n\n"
                    + "\n".join(f"   · {m}" for m in mb_errors)
                    + "\n\nUn análisis económico con masas inconsistentes "
                      "puede dar resultados engañosos.  ¿Forzar igual?",
                )
                if ans != QMessageBox.Yes:
                    return

            # calcular ISBL via Lang
            try:
                equipos = [
                    {"nombre": b.eq_type, "S": b.S, "n": b.n}
                    for b in self.fs.blocks.values()
                ]
                res = eq.lang_fci(equipos, plant_type="Fluid processing",
                                   year_target=2024)
                isbl = eq.isbl_implicito(res["FCI_MMUSD"], 0.30, 0.10, 0.10)
            except Exception as e:
                QMessageBox.critical(self, "Error de cálculo",
                                      f"{type(e).__name__}: {e}")
                return
            feeds    = [s for s in self.fs.streams.values() if s.role == "feed"]
            products = [s for s in self.fs.streams.values() if s.role == "product"]

        # opción de xlsx base
        usar_xlsx = QMessageBox.question(
            self, "Análisis económico",
            "El diagrama de bloques queda intacto en esta ventana.\n\n"
            "¿Usar un .xlsx base existente para el análisis?\n\n"
            "  Sí        → seleccionás el archivo\n"
            "  No        → plantilla Turton + feeds/products del diagrama",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        )
        if usar_xlsx == QMessageBox.Cancel:
            return

        base_xlsx = None
        if usar_xlsx == QMessageBox.Yes:
            base_xlsx, _ = QFileDialog.getOpenFileName(
                self, "Proyecto .xlsx base", "", "Excel (*.xlsx *.xls)"
            )
            if not base_xlsx:
                return

        # generar xlsx temporal
        import tempfile
        try:
            tmp_dir = tempfile.gettempdir()
            tmp_path = os.path.join(tmp_dir, f"ANA_from_PFD_{os.getpid()}.xlsx")
            fexp.write_project_xlsx(tmp_path, self.fs, isbl, feeds, products,
                                     base_xlsx)
        except Exception as e:
            QMessageBox.critical(self, "Falló la generación del xlsx",
                                  f"{type(e).__name__}: {e}")
            return

        # lanzar ANA.py como subprocess
        # Preferir el nuevo ana_qt (PySide6, look unificado con SVG icons).
        # Fallback a ANA.py (Tkinter legacy) si ana_qt no está disponible.
        cwd = os.path.dirname(os.path.abspath(__file__))
        if os.path.exists(os.path.join(cwd, "ana_qt.py")):
            cmd = [sys.executable, "ana_qt.py", "--import", tmp_path]
        else:
            cmd = [sys.executable, "ANA.py", "--import", tmp_path]
        try:
            subprocess.Popen(cmd, cwd=cwd)
        except Exception as e:
            QMessageBox.critical(self, "Falló el lanzamiento",
                                  f"{type(e).__name__}: {e}")

    # ---------------------------------------------------
    # EXPORT (PDF / SVG / PNG)
    # ---------------------------------------------------

    def _scene_export_rect(self):
        """Bounding box de los bloques + margen, para que el export
        cubra el contenido visible sin la grilla infinita."""
        items = [it for it in self.scene.items()
                 if isinstance(it, (BlockItem, StreamItem))]
        if not items:
            return self.view.viewport().rect()
        bbox = items[0].sceneBoundingRect()
        for it in items[1:]:
            bbox = bbox.united(it.sceneBoundingRect())
        # incluir pills de streams (label_bg / label_name / label_flow son aparte)
        for sid, sit in self.scene.stream_items.items():
            if sit.label_bg.scene() is self.scene:
                bbox = bbox.united(sit.label_bg.sceneBoundingRect())
        bbox.adjust(-40, -40, 40, 40)
        return bbox

    def action_export_pdf(self):
        if not self.fs.blocks:
            QMessageBox.information(self, "Exportar PDF",
                                     "El diagrama está vacío.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar PDF", "diagrama.pdf",
            "PDF (*.pdf)",
        )
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            from PySide6.QtPrintSupport import QPrinter
            from PySide6.QtCore import QSizeF
            from PySide6.QtGui  import QPageSize, QPageLayout

            bbox = self._scene_export_rect()
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(path)
            # tamaño de la página = bbox (escalado a tamaño físico A4 si
            # bbox es demasiado grande)
            aspect = bbox.width() / max(bbox.height(), 1)
            if aspect > 1:
                printer.setPageOrientation(QPageLayout.Landscape)
            else:
                printer.setPageOrientation(QPageLayout.Portrait)
            printer.setPageSize(QPageSize(QPageSize.A4))

            painter = QPainter(printer)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            # render del scene sobre el painter (sin la grilla)
            self._render_to_painter(painter, bbox,
                                    target_rect=printer.pageRect(QPrinter.DevicePixel))
            painter.end()
            self.status.showMessage(f"Exportado: {path}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "Error al exportar PDF",
                                  f"{type(e).__name__}: {e}")

    def action_export_svg(self):
        if not self.fs.blocks:
            QMessageBox.information(self, "Exportar SVG",
                                     "El diagrama está vacío.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar SVG", "diagrama.svg",
            "SVG (*.svg)",
        )
        if not path:
            return
        if not path.lower().endswith(".svg"):
            path += ".svg"
        try:
            from PySide6.QtSvg import QSvgGenerator
            from PySide6.QtCore import QSize, QRect

            bbox = self._scene_export_rect()
            gen = QSvgGenerator()
            gen.setFileName(path)
            gen.setSize(QSize(int(bbox.width()), int(bbox.height())))
            gen.setViewBox(QRect(0, 0, int(bbox.width()), int(bbox.height())))
            gen.setTitle("Diagrama de proceso")
            gen.setDescription("Generado con flowsheet_qt")

            painter = QPainter(gen)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            self._render_to_painter(painter, bbox,
                                    target_rect=QRect(0, 0,
                                                       int(bbox.width()),
                                                       int(bbox.height())))
            painter.end()
            self.status.showMessage(f"Exportado: {path}", 5000)
        except Exception as e:
            QMessageBox.critical(self, "Error al exportar SVG",
                                  f"{type(e).__name__}: {e}")

    def action_export_png(self):
        if not self.fs.blocks:
            QMessageBox.information(self, "Exportar PNG",
                                     "El diagrama está vacío.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar PNG (alta resolución)", "diagrama.png",
            "PNG (*.png)",
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        try:
            from PySide6.QtGui  import QImage, QColor
            from PySide6.QtCore import QSize, QRect

            bbox = self._scene_export_rect()
            # 2× para alta DPI (≈ 200 DPI cuando se imprime A4)
            scale = 2.0
            target_w = int(bbox.width()  * scale)
            target_h = int(bbox.height() * scale)
            img = QImage(target_w, target_h, QImage.Format_ARGB32)
            img.fill(QColor("#ffffff"))

            painter = QPainter(img)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.TextAntialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            self._render_to_painter(painter, bbox,
                                    target_rect=QRect(0, 0, target_w, target_h))
            painter.end()
            img.save(path)
            self.status.showMessage(f"Exportado: {path} ({target_w}×{target_h})", 5000)
        except Exception as e:
            QMessageBox.critical(self, "Error al exportar PNG",
                                  f"{type(e).__name__}: {e}")

    def _render_to_painter(self, painter, source_rect, target_rect):
        """Render del scene EXCLUYENDO la grilla de fondo (z=-100).

        Para que el export no incluya las líneas de la grilla,
        ocultamos temporalmente los items grid antes de render().
        """
        from PySide6.QtCore import QRectF
        # ocultar grilla
        grid_items = [it for it in self.scene.items()
                      if isinstance(it, QGraphicsLineItem) and it.zValue() <= -100]
        for g in grid_items:
            g.setVisible(False)
        try:
            self.scene.render(
                painter,
                target=QRectF(target_rect),
                source=QRectF(source_rect),
                aspectRatioMode=Qt.KeepAspectRatio,
            )
        finally:
            for g in grid_items:
                g.setVisible(True)

    # ---------------------------------------------------
    # API pública para BlockItem / StreamItem
    # ---------------------------------------------------

    def edit_block(self, block: Block):
        """Abre BlockEditDialog y refresca el render."""
        dlg = BlockEditDialog(self, block)
        if dlg.exec() == QDialog.Accepted:
            before = self.begin_action()
            dlg.apply_to_model()
            self._mark_dirty()
            item = self.scene.block_items.get(block.id)
            if item is not None:
                self.scene.removeItem(item)
                del self.scene.block_items[block.id]
                self._render_block(block)
                # tooltip nuevo
                new_item = self.scene.block_items.get(block.id)
                if new_item is not None:
                    new_item._update_tooltip()
                self.refresh_streams_of(block.id)
            self._refresh_port_colors()
            self._update_status()
            self._on_selection_changed()
            self.end_action(f"Editar {block.name}", before)

    def edit_stream(self, stream: Stream):
        """Abre StreamEditDialog y refresca el render."""
        dlg = StreamEditDialog(self, stream, self.fs)
        if dlg.exec() != QDialog.Accepted:
            return
        # snapshot antes de aplicar
        before = self.begin_action()
        # aplicar al modelo
        dlg.apply_to_model()
        self._mark_dirty()
        # validar la conexión actualizada (puertos pueden haber cambiado)
        sev, msg = fval.validate_connection(
            self.fs, stream.src, stream.dst,
            stream.src_port, stream.dst_port,
        )
        if sev == "error":
            QMessageBox.critical(self, "Conexión inválida",
                                  msg + "\n\nLa edición se revierte.")
            self._apply_snapshot(before)
            return
        if sev == "warn":
            ans = QMessageBox.question(
                self, "Conexión atípica",
                msg + "\n\n¿Mantener los cambios igual?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                self._apply_snapshot(before)
                return
        # OK: refrescar y push undo
        item = self.scene.stream_items.get(stream.id)
        if item is not None:
            item.update_path()
        self._refresh_port_colors()
        self._on_selection_changed()
        self.end_action(f"Editar {stream.name}", before)

    def is_connecting(self) -> bool:
        return self._connecting_from is not None

    def start_connection(self, src_block_id: int):
        # Si ya había una conexión pendiente, avisar al user y
        # sobreescribir (antes se silenciaba el cambio).
        if self._connecting_from is not None \
                and self._connecting_from != src_block_id:
            prev = self.fs.blocks.get(self._connecting_from)
            prev_name = prev.name if prev else "?"
            self.status.showMessage(
                f"Conexión desde {prev_name} cancelada — nueva desde "
                f"{self.fs.blocks[src_block_id].name}…", 4000)
        self._connecting_from = src_block_id
        b = self.fs.blocks[src_block_id]
        self.status.showMessage(
            f"Conectando desde {b.name}…  click en el bloque destino (Esc cancela)"
        )

    def cancel_connection(self):
        if self._connecting_from is not None:
            self._connecting_from = None
            self._update_status()

    def complete_connection(self, dst_block_id: int):
        if self._connecting_from is None:
            return
        src = self._connecting_from
        self._connecting_from = None
        if src == dst_block_id:
            self._update_status()
            return
        # crear stream con autoselect de puertos
        self._add_stream(src, dst_block_id)

    def _add_stream(self, src_id, dst_id, src_port="", dst_port=""):
        b_src = self.fs.blocks.get(src_id)
        b_dst = self.fs.blocks.get(dst_id)
        if b_src is None or b_dst is None:
            return
        if not src_port:
            used_out = [t.src_port for t in self.fs.streams.values()
                        if t.src == src_id and t.src_port]
            src_port = ep.autoselect_outlet(b_src.eq_type, used_out)
        if not dst_port:
            used_in = [t.dst_port for t in self.fs.streams.values()
                       if t.dst == dst_id and t.dst_port]
            dst_port = ep.autoselect_inlet(b_dst.eq_type, used_in)

        # Validación semántica: chequear compatibilidad de fluid types
        sev, msg = fval.validate_connection(self.fs, src_id, dst_id,
                                              src_port, dst_port)
        if sev == "error":
            # Reactor con TODOS sus puertos de alimentación ocupados →
            # ofrecer crear un mixer automáticamente upstream (UX
            # accionable: en lugar de un error muerto, propongo la
            # arquitectura física correcta).
            _is_reactor_full = (
                "Reactor" in (b_dst.eq_type or "")
                and dst_port in ("util_in", "util_out")
                and any("alimentacion" in (t.dst_port or "")
                        for t in self.fs.streams.values() if t.dst == dst_id)
            )
            if _is_reactor_full:
                ans = QMessageBox.question(
                    self, "Reactor con alimentación llena",
                    f"El reactor {b_dst.name} ya tiene sus puertos de "
                    f"alimentación ocupados.  Un reactor admite hasta dos "
                    f"corrientes directas; para combinar más insumos, hay "
                    f"que insertar un Mezclador (Mixer — static) antes.\n\n"
                    f"¿Crear el mezclador automáticamente y reconectar?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                )
                if ans == QMessageBox.Yes:
                    self._insert_mixer_upstream(src_id, dst_id)
                    return
                return
            QMessageBox.critical(self, "Conexión inválida", msg)
            return
        elif sev == "warn":
            ans = QMessageBox.question(
                self, "Conexión atípica",
                msg + "\n\n¿Crear la conexión igual?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if ans != QMessageBox.Yes:
                return

        before = self.begin_action()
        sid = self.fs.new_id()
        name = f"S-{len(self.fs.streams) + 1}"
        s = Stream(
            id=sid, name=name, src=src_id, dst=dst_id,
            mass_flow=0.0,
            src_port=src_port, dst_port=dst_port,
        )
        self.fs.streams[sid] = s
        self._render_stream(s)
        self._refresh_port_colors()
        self._update_status()
        self.end_action(f"Conectar {b_src.name}→{b_dst.name}", before)

    def _insert_mixer_upstream(self, new_src_id, reactor_id):
        """Inserta un Mixer — static delante del reactor, reconecta la
        corriente existente al mixer, agrega la nueva corriente al
        mixer, y conecta el mixer al reactor.  Hallazgo 3 — UX.
        """
        from flowsheet_model import Block
        # Localizar la corriente existente al reactor (la primera con
        # dst_port que empiece con 'alimentacion').
        existing_stream = next(
            (t for t in self.fs.streams.values()
             if t.dst == reactor_id and (t.dst_port or "").startswith("alimentacion")),
            None)
        if existing_stream is None:
            return
        existing_src_id = existing_stream.src
        # Crear el mixer cerca del reactor (entre los dos sources).
        b_reactor = self.fs.blocks[reactor_id]
        b_src_new = self.fs.blocks.get(new_src_id)
        b_src_old = self.fs.blocks.get(existing_src_id)
        mx_id = self.fs.new_id()
        x_mid = (b_reactor.x + (b_src_new.x if b_src_new else b_reactor.x - 200)) / 2
        y_mid = b_reactor.y
        mx_name = f"M-{mx_id:03d}"
        self.fs.blocks[mx_id] = Block(
            id=mx_id, name=mx_name, eq_type="Mixer — static", S=2.0,
            n=1, x=int(x_mid), y=int(y_mid),
        )
        # Eliminar la corriente existente reactor-old y crear:
        # old_src → mixer (alimentacion_1), new_src → mixer (alimentacion_2),
        # mixer → reactor (alimentacion).
        before = self.begin_action()
        self.fs.streams.pop(existing_stream.id, None)
        # Re-render canvas: limpiar las líneas viejas
        for sid in list(self.fs.streams.keys()):
            pass
        # Re-crear como mixer downstream
        for src, port_in, name_suffix in (
            (existing_src_id, "alimentacion_1", "old"),
            (new_src_id,      "alimentacion_2", "new"),
        ):
            new_sid = self.fs.new_id()
            self.fs.streams[new_sid] = Stream(
                id=new_sid, name=f"S-{new_sid}",
                src=src, dst=mx_id, mass_flow=0.0,
                src_port=ep.autoselect_outlet(self.fs.blocks[src].eq_type,
                    [t.src_port for t in self.fs.streams.values()
                     if t.src == src and t.src_port]),
                dst_port=port_in,
            )
        # Mixer → reactor
        final_sid = self.fs.new_id()
        self.fs.streams[final_sid] = Stream(
            id=final_sid, name=f"S-{final_sid}",
            src=mx_id, dst=reactor_id, mass_flow=0.0,
            src_port="producto", dst_port="alimentacion",
        )
        # Re-render todo (canvas pierde tracking de los streams viejos)
        self._render_block(self.fs.blocks[mx_id])
        for s in self.fs.streams.values():
            if s.canvas_line is None:
                self._render_stream(s)
        self._refresh_port_colors()
        self._update_status()
        self.end_action(f"Insertar mixer antes de {b_reactor.name}", before)

    def delete_block(self, bid: int):
        ans = QMessageBox.question(
            self, "Borrar equipo",
            f"¿Borrar '{self.fs.blocks[bid].name}' y sus corrientes asociadas?",
        )
        if ans != QMessageBox.Yes:
            return
        before = self.begin_action()
        bname = self.fs.blocks[bid].name
        self._delete_block(bid)
        self._update_status()
        self.end_action(f"Borrar {bname}", before)

    # ---------------------------------------------------
    # SCENE OPS
    # ---------------------------------------------------

    def stream_items_iter(self):
        return self.scene.stream_items.items()

    def block_items_iter(self):
        return self.scene.block_items.items()

    def _rebuild_scene(self):
        """Recrea todos los items en la scene desde self.fs."""
        # numerar streams topológicamente para display en las pills
        fsolv.assign_stream_numbers(self.fs)
        self.scene.clear_flowsheet()
        for b in self.fs.blocks.values():
            self._render_block(b)
        for s in self.fs.streams.values():
            self._render_stream(s)
        self._refresh_port_colors()

    # ---------------------------------------------------
    # UNDO / REDO infrastructure
    # ---------------------------------------------------

    def _apply_snapshot(self, snapshot_dict):
        """Reemplaza self.fs con un snapshot y reconstruye la scene.
        Lo llaman SnapshotCommand.undo() y .redo()."""
        self._suppress_snapshot = True
        # invalidar drag pendiente: si user undo'a en mitad de un drag,
        # el snapshot guardado al inicio del drag ya no aplica al
        # nuevo state.
        self._drag_before_snapshot = None
        # cancelar conexión pendiente también
        self._connecting_from = None
        try:
            self.fs = Flowsheet.from_dict(snapshot_dict)
            self._rebuild_scene()
            self._update_status()
            self._on_selection_changed()
        finally:
            self._suppress_snapshot = False

    def begin_action(self):
        """Snapshot del fs ANTES de la acción.  Devuelve el dict.
        Llamar al INICIO de una operación que muta el fs."""
        if self._suppress_snapshot:
            return None
        import copy
        return copy.deepcopy(self.fs.to_dict())

    def end_action(self, text, before):
        """Push un SnapshotCommand con el before guardado y el state
        actual como after.  Si el state no cambió, no se pushea."""
        if self._suppress_snapshot or before is None:
            return
        import copy
        after = copy.deepcopy(self.fs.to_dict())
        if before == after:
            return        # no hubo cambios reales
        cmd = SnapshotCommand(text, self, before, after)
        self.undo_stack.push(cmd)

    def _render_block(self, b: Block):
        item = BlockItem(b, editor=self)
        self.scene.addItem(item)
        self.scene.block_items[b.id] = item

    def _render_stream(self, s: Stream):
        item = StreamItem(s, self.fs, editor=self)
        item.add_to_scene(self.scene)
        self.scene.stream_items[s.id] = item

    def _refresh_port_colors(self):
        for bid, bitem in self.scene.block_items.items():
            used = set()
            for s in self.fs.streams.values():
                if s.src == bid and s.src_port:
                    used.add(s.src_port)
                if s.dst == bid and s.dst_port:
                    used.add(s.dst_port)
            bitem.update_port_colors(used)

    def refresh_streams_of(self, block_id):
        """Llamado por BlockItem.itemChange cuando un bloque se mueve.

        Hace dos pasadas para que los jumpers (cruces) queden consistentes:
          1. Actualizar streams CONECTADOS al bloque movido.
          2. Re-render TODOS los streams para que detecten nuevos cruces
             con los actualizados.  O(n²) pero los flowsheets son chicos
             (<50 streams típico).
        """
        # Pass 1: streams del bloque
        for s in self.fs.streams.values():
            if s.src == block_id or s.dst == block_id:
                item = self.scene.stream_items.get(s.id)
                if item is not None:
                    item.update_path(rebuild_handles=False)
        # Pass 2: refresh global de paths para que jumpers se recalculen
        self._refresh_all_stream_paths()

    def _refresh_all_stream_paths(self):
        """Re-renderiza el path de TODOS los streams.  Necesario después
        de mover bloques o de un solve, para que los cruces (jumpers)
        queden coherentes."""
        for sid, item in self.scene.stream_items.items():
            item.update_path(rebuild_handles=False)

    def _delete_block(self, bid):
        item = self.scene.block_items.pop(bid, None)
        if item is not None and item.scene() is self.scene:
            # children del QGraphicsItemGroup (rect, texts, ports,
            # decoration_items) se eliminan automáticamente con el padre,
            # pero Python mantiene refs en la lista decoration_items.
            # Limpiamos para que el GC libere todo.
            if hasattr(item, "decoration_items"):
                item.decoration_items.clear()
            if hasattr(item, "port_items"):
                item.port_items.clear()
            self.scene.removeItem(item)
        self.fs.blocks.pop(bid, None)
        # streams asociados
        to_del = [sid for sid, s in self.fs.streams.items()
                  if s.src == bid or s.dst == bid]
        for sid in to_del:
            self._delete_stream(sid)

    def _delete_stream(self, sid):
        item = self.scene.stream_items.pop(sid, None)
        if item is not None:
            item.remove_from_scene(self.scene)
        self.fs.streams.pop(sid, None)

    # ---------------------------------------------------
    # SELECTION
    # ---------------------------------------------------

    def _on_selection_changed(self):
        sel = self.scene.selectedItems()
        if not sel:
            self.prop_label.setText("(nada seleccionado)")
            self._pfr_current_block = None
            if hasattr(self, "pfr_panel"):
                self.pfr_panel.setVisible(False)
            return

        # mostrar info del primer item seleccionado
        it = sel[0]
        if isinstance(it, BlockItem):
            it.set_selected_visual(True)
            for other in self.scene.block_items.values():
                if other is not it:
                    other.set_selected_visual(False)
            b = it.model
            spec = eq.EQUIPMENT_DATA.get(b.eq_type, {})
            ins  = [s for s in self.fs.streams.values() if s.dst == b.id]
            outs = [s for s in self.fs.streams.values() if s.src == b.id]
            in_t  = sum(s.mass_flow for s in ins)
            out_t = sum(s.mass_flow for s in outs)
            txt = (
                f"EQUIPO    {b.name}\n"
                f"Tipo      {b.eq_type}\n"
                f"Cat.      {spec.get('categoria', '?')}\n"
                f"S         {b.S:g} {spec.get('S_unit', '?')}\n"
                f"n         {b.n}\n"
                f"Duty      {b.duty:+g} kW\n"
                f"Utility   {b.heat_source or '(auto)'}\n\n"
                f"Entradas:  {len(ins)}  ({in_t:g} tm/año)\n"
                f"Salidas:   {len(outs)} ({out_t:g} tm/año)"
            )
            # ---- Diseño FUG automático para columnas ----
            # Si el bloque es tipo Tower (column) y tiene streams in/out
            # multicomponentes, llama a distillation_fug.design_column
            # para mostrar N, R, duties estimados.
            eq_lower = b.eq_type.lower()
            is_column = ("tower" in eq_lower or "column" in eq_lower
                          or "destil" in eq_lower)
            if is_column and ins and outs:
                feed = ins[0]
                # Buscar dos productos con composición distinta para
                # identificar el destilado y el fondo.
                if (feed.composition and len(feed.composition) >= 2
                        and len(outs) >= 2):
                    dist_out = max(outs, key=lambda s: (s.composition or {}).get(
                        max((feed.composition or {}).items(),
                             key=lambda kv: kv[1])[0], 0.0))
                    bot_out = next((s for s in outs if s is not dist_out), None)
                    if bot_out and dist_out.composition and bot_out.composition:
                        # Identificar LK (mayor en distillate) y HK (mayor en
                        # bottom)
                        d_top = max(dist_out.composition.items(),
                                     key=lambda kv: kv[1])
                        b_top = max(bot_out.composition.items(),
                                     key=lambda kv: kv[1])
                        LK = d_top[0]
                        HK = b_top[0]
                        if LK != HK and LK in feed.composition and HK in feed.composition:
                            try:
                                import distillation_fug as fug
                                res = fug.design_column(
                                    feed_composition=feed.composition,
                                    F=feed.mass_flow,
                                    T_K=feed.temperature + 273.15,
                                    P_bar=1.013,
                                    light_key=LK, heavy_key=HK,
                                    x_D_LK=dist_out.composition.get(LK, 0.9),
                                    x_B_LK=bot_out.composition.get(LK, 0.05),
                                    R_factor=1.3,
                                    T_top_K=dist_out.temperature + 273.15,
                                    T_bot_K=bot_out.temperature + 273.15,
                                )
                                if res:
                                    txt += "\n\n─ DISEÑO FUG (NRTL) ─"
                                    txt += f"\nLK / HK    {LK} / {HK}"
                                    txt += f"\nα tope     {res.get('alpha_top',0):.2f}"
                                    txt += f"\nα fondo    {res.get('alpha_bot',0):.2f}"
                                    txt += f"\nα promedio {res.get('alpha_avg',0):.2f}"
                                    if res.get("N_min") is not None:
                                        txt += f"\nN_min      {res['N_min']:.1f}  (Fenske)"
                                    if res.get("R_min") is not None:
                                        txt += f"\nR_min      {res['R_min']:.2f}  (Underwood)"
                                    if res.get("R") is not None:
                                        txt += f"\nR (1.3×min){res['R']:.2f}"
                                    if res.get("N") is not None:
                                        txt += f"\nN real     {res['N']:.1f}  (Gilliland)"
                                    if res.get("N_feed") is not None:
                                        txt += f"\nN_feed     {res['N_feed']:.1f}  (Kirkbride)"
                                    if res.get("Q_cond_kW") is not None:
                                        txt += f"\nQ_cond     {res['Q_cond_kW']:+.1f} kW"
                                    if res.get("Q_reb_kW") is not None:
                                        txt += f"\nQ_reb      {res['Q_reb_kW']:+.1f} kW"
                                    for w in res.get("warnings", [])[:2]:
                                        txt += f"\n{w[:120]}"
                            except Exception:
                                pass

            # ---- Dimensionamiento de BOMBA / COMPRESOR ----
            eq_lower2 = b.eq_type.lower()
            is_pump = ("pump" in eq_lower2 or "bomba" in eq_lower2)
            is_compr = ("compressor" in eq_lower2 or "fan" in eq_lower2)
            if is_pump or is_compr:
                try:
                    import equipment_design as _ed
                    if is_pump:
                        ps = _ed.design_pump_for_block(b, self.fs)
                        if ps is not None:
                            txt += "\n\n─ Dimensionamiento BOMBA ─"
                            txt += f"\nQ          {ps['Q_m3_h']:.2f} m³/h"
                            txt += f"\nHead       {ps['head_m']:.1f} m"
                            txt += f"\nW_hyd      {ps['W_hyd_kW']:.2f} kW"
                            txt += f"\nW_shaft    {ps['W_shaft_kW']:.2f} kW  (η_h={b.efficiency:.2f})"
                            txt += f"\nW_elec     {ps['W_elec_kW']:.2f} kW  (η_motor=0.95)"
                            txt += f"\nNPSHa      {ps['NPSHa_m']:.2f} m"
                            txt += f"\nNPSHr est. {ps['NPSHr_m_est']:.2f} m"
                            margin = ps['cavitation_margin_m']
                            if margin < 1.0:
                                txt += f"\n⚠ Margen cavitación: {margin:.2f} m (<1 m, riesgo!)"
                            else:
                                txt += f"\nMargen cav. {margin:.2f} m  ✓"
                    elif is_compr:
                        cs = _ed.design_compressor_for_block(b, self.fs)
                        if cs is not None:
                            txt += "\n\n─ Dimensionamiento COMPRESOR ─"
                            txt += f"\nRatio P_out/P_in: {cs['ratio']:.2f}"
                            txt += f"\nEtapas rec.:      {cs['n_stages_rec']}"
                            txt += f"\nQ_in (succión):   {cs['Q_in_m3_h']:.1f} m³/h"
                            txt += f"\nHead específico:  {cs['head_kJ_kg']:.1f} kJ/kg"
                            txt += f"\nT descarga:       {cs['T_out_C']:.1f} °C"
                            txt += f"\nW_isen:           {cs['W_isen_kW']:.1f} kW"
                            txt += f"\nW_actual:         {cs['W_act_kW']:.1f} kW  (η={cs['eta_total']:.2f})"
                            if cs['n_stages_rec'] > 1:
                                txt += f"\n⚠ Ratio {cs['ratio']:.1f} > 4: recomendar {cs['n_stages_rec']} etapas + intercoolers"
                            if cs['T_out_C'] > 200:
                                txt += f"\n⚠ T descarga {cs['T_out_C']:.0f}°C > 200°C: necesita enfriamiento intermedio"
                except Exception:
                    pass

            self.prop_label.setText(txt)

            # ---- Perfil PFR / batch / barras CSTR ----
            mode = getattr(b, "reactor_mode", "") or ""
            show = False
            if mode == "pfr":
                show = bool(getattr(b, "_pfr_profile", None)
                            and b._pfr_profile.get("points"))
            elif mode == "batch":
                show = bool(getattr(b, "_batch_profile", None)
                            and b._batch_profile.get("points"))
            elif mode == "cstr":
                # CSTR: mostrar barras si hay streams con composición
                show = any((s.composition for s in self.fs.streams.values()
                            if s.src == b.id or s.dst == b.id))
            if show:
                self._pfr_current_block = b
                self.pfr_panel.setVisible(True)
                # toggles X (vol/len) no aplican a batch/cstr → deshabilitar
                en_x = (mode == "pfr")
                self.pfr_x_vol.setEnabled(en_x)
                self.pfr_x_len.setEnabled(en_x)
                self._redraw_pfr_profile()
            else:
                self._pfr_current_block = None
                self.pfr_panel.setVisible(False)
                if mode in ("pfr", "batch", "cstr"):
                    self.prop_label.setText(
                        self.prop_label.text()
                        + f"\n\n(Reactor {mode}: corré Solve con "
                          "reactor_volume_L > 0 para ver el gráfico)"
                    )
        elif isinstance(it, StreamItem):
            for other in self.scene.block_items.values():
                other.set_selected_visual(False)
            # Ocultar panel de perfil al seleccionar streams
            self._pfr_current_block = None
            if hasattr(self, "pfr_panel"):
                self.pfr_panel.setVisible(False)
            s = it.model
            # defensa: si los bloques referenciados ya no existen
            # (stream huérfano por inconsistencia de modelo), mostrar
            # info parcial sin crash.
            src_b = self.fs.blocks.get(s.src)
            dst_b = self.fs.blocks.get(s.dst)
            b_src = src_b.name if src_b else "(borrado)"
            b_dst = dst_b.name if dst_b else "(borrado)"
            sp = s.src_port or "(auto)"
            dp = s.dst_port or "(auto)"
            txt = (
                f"CORRIENTE  {s.name}\n"
                f"Desde      {b_src}  ({sp})\n"
                f"Hacia      {b_dst}  ({dp})\n"
                f"Rol        {s.role}\n"
                f"Fase       {s.phase or '—'}\n"
                f"Flujo      {s.mass_flow:g} tm/año\n"
                f"T          {s.temperature:g} °C"
            )
            if s.cp > 0:
                txt += f"\nCp         {s.cp:g} kJ/kg·K (manual)"
            # Composición — siempre visible, ANTES no se mostraba.
            comp = s.composition or {}
            if not comp and s.main_component:
                comp = {s.main_component: 1.0}
            if comp:
                txt += "\n\nComposición (% masa):"
                for k, v in sorted(comp.items(), key=lambda kv: -kv[1]):
                    if v < 0.0005:
                        continue
                    # Calcular caudal másico individual del componente
                    m_i = v * s.mass_flow
                    txt += f"\n  {k:14s} {v*100:6.2f}%   ({m_i:>10.1f} tm/año)"
            else:
                txt += "\n\nComposición: no declarada"
            if s.role in ("feed", "product"):
                txt += f"\n\nPrecio     {s.price_usd_per_tm:g} USD/tm"
                if s.mass_flow > 0 and s.price_usd_per_tm > 0:
                    total = s.mass_flow * s.price_usd_per_tm
                    lbl = "Ingreso" if s.role == "product" else "Costo"
                    txt += f"\n{lbl}    $ {total:,.0f}/año"

            # ---- Análisis NRTL (Capa 6) si hay >=2 componentes con
            # parámetros y la fase es líquido o two-phase ----
            comp_clean = {k: v for k, v in (s.composition or {}).items() if v > 0.005}
            if (len(comp_clean) >= 2 and
                s.phase in ("liquid", "two_phase", "vapor", "gas", "")):
                top = sorted(comp_clean.items(), key=lambda kv: -kv[1])
                # Tomar los 2 componentes mayores
                n1, _ = top[0]
                n2, _ = top[1]
                try:
                    import nrtl
                    if nrtl.has_params(n1, n2):
                        T_K = s.temperature + 273.15
                        nrtl_txt = ["\n─ Análisis NRTL (par dominante) ─"]
                        nrtl_txt.append(f"Par:       {n1} / {n2}")
                        # Convertir a binario normalizado
                        x1 = top[0][1] / (top[0][1] + top[1][1])
                        g = nrtl.activity_coeff_binary([n1, n2], x1, T_K)
                        if g:
                            nrtl_txt.append(f"γ {n1}: {g[0]:.3f}")
                            nrtl_txt.append(f"γ {n2}: {g[1]:.3f}")
                        # T_bub binario a 1 atm
                        bp = nrtl.bubble_point([n1, n2], [x1, 1-x1], 1.013)
                        if bp:
                            T_bub_C = bp[0] - 273.15
                            y1 = bp[1][0]
                            nrtl_txt.append(
                                f"T_bub @1atm: {T_bub_C:.1f}°C  "
                                f"(y_{n1}={y1*100:.1f}%)")
                        # Azeotropo si existe
                        az = nrtl.find_azeotrope([n1, n2], 1.013)
                        if az:
                            T_az_C = az["T_az_K"] - 273.15
                            kind_label = ("min-boiling" if az["kind"] == "positive"
                                            else "max-boiling")
                            nrtl_txt.append(
                                f"⚠ AZEOTROPO {kind_label} @1atm:")
                            nrtl_txt.append(
                                f"   x_{n1} = {az['x_az']:.3f}  "
                                f"T = {T_az_C:.1f}°C")
                            # Advertencia si la composición está cerca
                            if abs(x1 - az["x_az"]) < 0.05:
                                nrtl_txt.append(
                                    "   ⚠ stream está CERCA del azeo —")
                                nrtl_txt.append(
                                    "     destilación simple no puede pasar.")
                        txt += "\n" + "\n".join(nrtl_txt)
                except Exception as e:
                    pass    # falta thermo_db / Antoine → skip silencioso

            # ---- Pérdida de carga (Darcy-Weisbach) ----
            if s.mass_flow > 0 and (comp_clean or s.main_component):
                try:
                    import pressure_drop as _pd
                    dp_res = _pd.stream_pressure_drop(s)
                    if dp_res is not None:
                        txt += "\n\n─ Pérdida de carga (Darcy-Weisbach) ─"
                        L = s.pipe_length_m or 10.0
                        D = s.pipe_diameter_m or 0.050
                        K = getattr(s, "pipe_K_local", 0) or 0
                        txt += f"\nL          {L:.1f} m"
                        txt += f"\nD          {D*1000:.0f} mm  ({D*39.37:.1f}\")"
                        if K > 0:
                            txt += f"\nK_local    {K:.2f}  (accesorios)"
                        txt += f"\nv          {dp_res['velocity_m_s']:.2f} m/s"
                        txt += f"\nRe         {dp_res['Re']:.0f}  ({dp_res['regime']})"
                        txt += f"\nf_Darcy    {dp_res['f_Darcy']:.4f}"
                        dp_fric = dp_res.get('delta_P_fric_Pa', dp_res['delta_P_Pa']) / 1000
                        dp_local = dp_res.get('delta_P_local_Pa', 0) / 1000
                        if dp_local > 0:
                            txt += f"\nΔP fric    {dp_fric:.2f} kPa"
                            txt += f"\nΔP local   {dp_local:.2f} kPa"
                        txt += f"\nΔP total   {dp_res['delta_P_bar']:.3f} bar  ({dp_res['delta_P_Pa']/1000:.1f} kPa)"
                        if s.pressure_bar > 0 and s.pressure_bar != 1.013:
                            txt += f"\nP corriente {s.pressure_bar:.3f} bar"
                            if s.pressure_locked:
                                txt += "  🔒"
                except Exception:
                    pass

            self.prop_label.setText(txt)

    def _redraw_pfr_profile(self):
        """Dibuja el visual del reactor actual según su modo:
          · pfr   → perfil espacial (curva vs V/L)
          · batch → curva de especies vs tiempo
          · cstr  → barras entrada→salida (sin curva: mezcla perfecta)
        No-op si falta matplotlib o no hay reactor seleccionado."""
        if not _MPL_OK or self._pfr_canvas is None:
            return
        b = self._pfr_current_block
        if b is None:
            self._pfr_fig.clear()
            self._pfr_canvas.draw()
            return
        mode = getattr(b, "reactor_mode", "") or ""
        if mode == "pfr":
            self._draw_pfr_curve(b)
        elif mode == "batch":
            self._draw_batch_curve(b)
        elif mode == "cstr":
            self._draw_cstr_bars(b)
        else:
            self._pfr_fig.clear()
            self._pfr_canvas.draw()

    def _draw_pfr_curve(self, b):
        """Perfil espacial PFR (curva vs V o L_frac)."""
        prof = getattr(b, "_pfr_profile", None)
        self._pfr_fig.clear()
        if not prof or not prof.get("points"):
            self._pfr_canvas.draw()
            return
        pts = prof["points"]
        use_len = self.pfr_x_len.isChecked()
        use_conv = self.pfr_y_conv.isChecked()
        xs = [p["L_frac"] if use_len else p["V_m3"] for p in pts]
        ax = self._pfr_fig.add_subplot(111)
        all_species = set()
        for p in pts:
            all_species.update((p["X"] if use_conv else p["F"]).keys())
        species = sorted(all_species)
        for sp in species:
            if use_conv:
                ys = [p["X"].get(sp, 0.0) * 100.0 for p in pts]
                if max(ys) < 1e-6:
                    continue
            else:
                ys = [p["F"].get(sp, 0.0) for p in pts]
            ax.plot(xs, ys, linewidth=1.4, label=sp)
        ax.set_xlabel("L / L_total" if use_len else "Volumen acumulado (m³)",
                       fontsize=8)
        ax.set_ylabel("Conversión (%)" if use_conv else "Flujo molar (mol/s)",
                       fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.legend(fontsize=6, loc="best", ncol=2)
        ax.set_title(f"Perfil PFR — {b.name}", fontsize=9, fontweight="bold")
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        self._pfr_fig.tight_layout()
        self._pfr_canvas.draw()

    def _draw_batch_curve(self, b):
        """Curva de especies vs tiempo para reactor batch."""
        prof = getattr(b, "_batch_profile", None)
        self._pfr_fig.clear()
        if not prof or not prof.get("points"):
            self._pfr_canvas.draw()
            return
        pts = prof["points"]
        use_conv = self.pfr_y_conv.isChecked()
        # eje X del batch SIEMPRE es tiempo (no hay "longitud").
        xs = [p["t_s"] for p in pts]
        ax = self._pfr_fig.add_subplot(111)
        species = sorted({s for p in pts
                          for s in (p["X"] if use_conv else p["N"])})
        for sp in species:
            if use_conv:
                ys = [p["X"].get(sp, 0.0)*100.0 for p in pts]
                if max(ys) < 1e-6:
                    continue
            else:
                ys = [p["N"].get(sp, 0.0) for p in pts]
            ax.plot(xs, ys, linewidth=1.4, label=sp)
        ax.set_xlabel("Tiempo de tanda (s)", fontsize=8)
        ax.set_ylabel("Conversión (%)" if use_conv else "Moles (mol)",
                      fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.legend(fontsize=6, loc="best", ncol=2)
        ax.set_title(f"Batch — {b.name}  (t={prof['t_total_s']:.0f}s)",
                     fontsize=9, fontweight="bold")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        self._pfr_fig.tight_layout()
        self._pfr_canvas.draw()

    def _draw_cstr_bars(self, b):
        """Barras entrada→salida por especie. CSTR es mezcla perfecta,
        físicamente NO tiene perfil espacial ni temporal en steady-state."""
        self._pfr_fig.clear()
        ins = [s for s in self.fs.streams.values() if s.dst == b.id]
        outs = [s for s in self.fs.streams.values() if s.src == b.id]

        def _agg(streams):
            tot = {}
            mtot = 0.0
            for s in streams:
                comp = s.composition or {}
                m = s.mass_flow or 0.0
                mtot += m
                for k, v in comp.items():
                    tot[k] = tot.get(k, 0.0) + v*m
            if mtot > 0:
                return {k: v/mtot for k, v in tot.items()}
            return {}

        cin = _agg(ins)
        cout = _agg(outs)
        if not cin and not cout:
            ax = self._pfr_fig.add_subplot(111)
            ax.text(0.5, 0.5, "Sin datos — corré Solve",
                    ha="center", va="center", fontsize=9)
            ax.axis("off")
            self._pfr_canvas.draw()
            return
        species = sorted(set(cin) | set(cout))
        import numpy as _np
        x = _np.arange(len(species))
        w = 0.38
        ax = self._pfr_fig.add_subplot(111)
        ax.bar(x - w/2, [cin.get(s, 0.0)*100 for s in species],  w,
               label="Entrada", color="#5c6bc0")
        ax.bar(x + w/2, [cout.get(s, 0.0)*100 for s in species], w,
               label="Salida",  color="#ef6c00")
        ax.set_xticks(x)
        ax.set_xticklabels(species, fontsize=6, rotation=40, ha="right")
        ax.set_ylabel("% másico", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(True, axis="y", alpha=0.3, linestyle="--")
        ax.legend(fontsize=7, loc="best")
        tau = getattr(b, "tau_s", None) or getattr(b, "_tau_s", None)
        ttl = f"CSTR — {b.name}"
        if tau:
            ttl += f"  (τ={tau:.1f}s)"
        ax.set_title(ttl, fontsize=9, fontweight="bold")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        self._pfr_fig.tight_layout()
        self._pfr_canvas.draw()

    # ---------------------------------------------------
    # LIBRARY → CANVAS
    # ---------------------------------------------------

    def _on_lib_double_click(self, item, _col):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        if data.startswith("__STREAM__"):
            kind = data.replace("__STREAM__", "")
            self._add_floating_stream(kind=kind)
        else:
            self._add_block_of_type(data)

    def _add_selected_from_lib(self):
        sel = self.lib_tree.currentItem()
        if sel is None or not sel.data(0, Qt.UserRole):
            return
        data = sel.data(0, Qt.UserRole)
        if data.startswith("__STREAM__"):
            self._add_floating_stream(kind=data.replace("__STREAM__", ""))
        else:
            self._add_block_of_type(data)

    def _add_block_of_type(self, eq_type, x=None, y=None):
        """Agrega un bloque del tipo dado al flowsheet.  Si x/y no se
        especifican, se ubica en el centro de la vista actual."""
        spec = eq.EQUIPMENT_DATA.get(eq_type)
        if not spec:
            return
        before = self.begin_action()
        bid = self.fs.new_id()
        nombre = ep.next_block_name(eq_type,
                                     [b.name for b in self.fs.blocks.values()])
        S_default = (spec["S_min"] + spec["S_max"]) / 2
        # Posición default: centro de la vista visible, snap a grid.
        # Si el usuario está agregando varios, los desplazamos un poco.
        if x is None or y is None:
            try:
                vp_center = self.view.mapToScene(
                    self.view.viewport().rect().center()
                )
                cx_v, cy_v = vp_center.x(), vp_center.y()
            except Exception:
                cx_v, cy_v = 300, 200
            n_existing = len(self.fs.blocks)
            # offset chico por cada bloque para que no se apilen
            offset = (n_existing % 8) * 30
            x = round((cx_v + offset) / GRID_STEP) * GRID_STEP
            y = round((cy_v + offset) / GRID_STEP) * GRID_STEP
        b = Block(id=bid, name=nombre, eq_type=eq_type, S=S_default,
                  n=1, x=float(x), y=float(y))
        ep.apply_type_defaults(b)
        self.fs.blocks[bid] = b
        self._render_block(b)
        self._refresh_port_colors()
        self._update_status()
        # Asegurar que el nuevo bloque sea visible — centrar la vista
        # en él si no estaba visible.
        try:
            block_item = self.scene.block_items.get(bid)
            if block_item is not None:
                self.view.ensureVisible(block_item, xmargin=60, ymargin=60)
        except Exception:
            pass
        self.end_action(f"Agregar {nombre}", before)

    def _add_floating_stream(self, kind="mass", x=None, y=None,
                               length=120.0):
        """Agrega un Stream FLOTANTE al canvas en la posición (x, y).

        kind: 'mass' o 'energy'.
        length: largo inicial de la flecha en píxeles (default 120).

        Convención: src=-1, dst=-1, start_xy=[x, y], end_xy=[x+length, y].
        El solver IGNORA streams con src<=0 o dst<=0 (no afecta balance).
        El usuario puede arrastrar los endpoints y conectarlos a puertos
        de bloques.
        """
        if x is None or y is None:
            try:
                vp_center = self.view.mapToScene(
                    self.view.viewport().rect().center()
                )
                x = round(vp_center.x() / GRID_STEP) * GRID_STEP
                y = round(vp_center.y() / GRID_STEP) * GRID_STEP
            except Exception:
                x, y = 300.0, 200.0
        kind = kind if kind in ("mass", "energy") else "mass"
        before = self.begin_action()
        sid = self.fs.new_id()
        # Nombre auto: S-Nx para masa, Q-Nx para energía
        prefix = "Q" if kind == "energy" else "S"
        n = 1 + sum(1 for s in self.fs.streams.values()
                     if s.name.startswith(f"{prefix}-flo"))
        name = f"{prefix}-flo-{n}"
        s = Stream(
            id=sid, name=name, src=-1, dst=-1, mass_flow=0.0,
            role="internal",
            start_xy=[float(x), float(y)],
            end_xy=[float(x + length), float(y)],
            stream_kind=kind,
            energy_kW=0.0,
        )
        self.fs.streams[sid] = s
        self._render_stream(s)
        self._refresh_port_colors()
        self._update_status()
        self.end_action(f"Agregar {name} (flotante {kind})", before)
        return sid


# ======================================================
# SHIM PARA REUSAR LOS EXAMPLE BUILDERS DEL EDITOR TK
# ======================================================
# Los `_example_*` methods de FlowsheetEditor (Tk) usan helpers
# `_add_example_block`, `_add_example_stream`, `_add_example_extra`,
# `_set_example_labor`, `_set_block_duty` — son lógica pura sobre
# el modelo, sin Tk.  Acá los re-implementamos contra un shim que
# expone los mismos helpers.

class _ExampleBuilderShim:
    """Objeto plano que provee los métodos que los example builders
    de flowsheet_ui esperan, operando sobre el flowsheet pasado."""

    def __init__(self, fs):
        self.fs = fs

    def _add_example_block(self, name, eq_type, S, x, y, n=1):
        bid = self.fs.new_id()
        b = Block(id=bid, name=name, eq_type=eq_type, S=S, n=n, x=x, y=y)
        # NO llamar a apply_type_defaults aca: los ejemplos son
        # "carga" en espiritu (configuracion pre-curada), no creacion
        # interactiva de usuario. Multiples ejemplos usan
        # 'Reactor — autoclave' con .reactions=[...] esperando modo
        # equilibrium (default historico); apply_type_defaults los
        # pasaria silenciosamente a batch (Patch 3) y romperia el solve
        # por falta de reactor_volume_L. Los ejemplos que quieren
        # PFR/CSTR/batch setean reactor_mode explicitamente despues
        # del _add_example_block (ej. _example_ethane_cracker_pfr).
        self.fs.blocks[bid] = b
        return bid

    def _add_example_stream(self, src, dst, name, mass_flow=0.0,
                            role="internal", src_port="", dst_port="",
                            price=0.0, T=25.0, cp=0.0,
                            main_component="", phase="",
                            composition=None,
                            lock_mass=None, lock_T=None, lock_comp=None):
        """Shim Qt — Hallazgo 2: mismo contrato que FlowsheetEditor de Tk
        con lock_* opcionales (None = heurística vieja)."""
        sid = self.fs.new_id()
        s = Stream(
            id=sid, name=name, src=src, dst=dst,
            mass_flow=mass_flow, role=role,
            src_port=src_port, dst_port=dst_port,
            price_usd_per_tm=price,
            temperature=T, cp=cp,
            main_component=main_component,
            phase=phase,
            composition=dict(composition) if composition else {},
        )
        s.mass_flow_locked   = ((mass_flow > 0) if lock_mass is None
                                  else bool(lock_mass))
        s.temperature_locked = ((abs(T - 25.0) > 0.01) if lock_T is None
                                  else bool(lock_T))
        s.composition_locked = ((bool(composition) or bool(main_component))
                                  if lock_comp is None else bool(lock_comp))
        self.fs.streams[sid] = s
        return sid

    def _add_example_extra(self, name, flowrate, price, units="tm",
                           stream="Utilities"):
        self.fs.opex_extras.append({
            "name": name, "units": units, "time_basis": "year",
            "flowrate": float(flowrate), "price_usd_per_unit": float(price),
            "stream": stream,
        })

    def _set_example_labor(self, labor_usd_per_year):
        self.fs.fixed_overrides["Labor"] = float(labor_usd_per_year)

    def _set_block_duty(self, bid, duty_kw):
        if bid in self.fs.blocks:
            self.fs.blocks[bid].duty = float(duty_kw)
            self.fs.blocks[bid].duty_locked = (abs(duty_kw) > 1e-9)
