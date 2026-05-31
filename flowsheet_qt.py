"""
FLOWSHEET QT — editor Qt principal del proyecto (PySide6 + QGraphicsView).

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
    · StreamInspector — rediseño slide-out con secciones contextuales
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
    QAction, QActionGroup, QPen, QBrush, QColor, QPainter, QFont, QPainterPath,
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
    QScrollArea, QCompleter, QFrame, QRadioButton, QButtonGroup,
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
# CATÁLOGO DE EJEMPLOS AGRUPADO POR CATEGORÍA
# ======================================================
# Única fuente de verdad para los menús de ejemplos (menubar + toolbar).
# Cada categoría → lista de (key, label).  Las keys deben existir en el
# builder_map de action_load_example().
def _load_example_categories():
    """Fase 2: el catálogo del menú se puebla DESDE el registry data-driven
    (data/examples/manifest.json), no hardcodeado.  Devuelve el mismo formato
    que consumen los dos menús: [(categoria, [(clave, label), ...]), ...] en
    el orden del manifest (= orden histórico del menú).

    Fallback defensivo: si el registry/manifest no está disponible (entorno
    roto), devuelve [] — los menús quedan vacíos pero la app no crashea al
    construir la UI."""
    try:
        import examples_registry as _reg
        return [(cat, [(e["clave"], e["label"]) for e in items])
                for cat, items in _reg.list_categories()]
    except Exception:
        return []


EXAMPLE_CATEGORIES = _load_example_categories()


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

    # Guard: dimensiones inválidas → QImage 0×0 haría que QPainter(img)
    # falle ("Painter not active").  Devolvemos None en vez de pintar.
    if width <= 0 or height <= 0:
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
# Paleta por tipo de puerto — se usa cuando el puerto está libre para
# guiar visualmente al user (qué clase de stream se espera).  Cuando el
# puerto se conecta, el color del puerto se satura (relleno sólido).
# Conjunto compatible con daltonismo (verde ≠ rojo + diferencias de tono):
COLOR_PORT_IN       = QColor("#2e7d32")   # verde — proceso entra
COLOR_PORT_OUT      = QColor("#1565c0")   # azul — proceso sale
COLOR_PORT_UTIL_IN  = QColor("#ef6c00")   # naranja — utility entra (CW/steam)
COLOR_PORT_UTIL_OUT = QColor("#bf360c")   # naranja oscuro — utility sale
COLOR_PORT_FUEL     = QColor("#5d4037")   # marrón — combustible
COLOR_PORT_VENT     = QColor("#9e9e9e")   # gris — venteo / atmósfera
COLOR_PORT_DRAIN    = QColor("#455a64")   # gris azulado — drenaje
COLOR_PORT_AUX      = QColor("#7e57c2")   # violeta — auxiliar genérico
# Tinte claro = puerto libre (con su color tenue como hint)
# Color saturado = puerto conectado (mismo hue, alpha pleno)
def _port_tint(color: QColor) -> QColor:
    """Devuelve una versión clara del color (alpha 60%, mismo hue)
    para puertos libres — el user ve el HINT del tipo pero no
    confunde con un puerto activo."""
    c = QColor(color)
    c.setAlpha(110)
    return c
PORT_KIND_COLORS = {
    "process_in":  COLOR_PORT_IN,
    "process_out": COLOR_PORT_OUT,
    "utility_in":  COLOR_PORT_UTIL_IN,
    "utility_out": COLOR_PORT_UTIL_OUT,
    "fuel":        COLOR_PORT_FUEL,
    "vent":        COLOR_PORT_VENT,
    "drain":       COLOR_PORT_DRAIN,
    "aux":         COLOR_PORT_AUX,
}
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
        # Acotamos el tamano inicial al de la pantalla para que el
        # dialog siempre entre. El contenido es scrolleable.
        try:
            screen = self.screen() if hasattr(self, "screen") else None
            avail = screen.availableGeometry() if screen else None
            max_h = int(avail.height() * 0.85) if avail else 720
            max_w = int(avail.width()  * 0.60) if avail else 540
        except Exception:
            max_h, max_w = 720, 540
        self.resize(min(540, max_w), min(700, max_h))
        self.setMaximumHeight(max_h)

        spec = eq.EQUIPMENT_DATA.get(block.eq_type, {})

        # ─── Scroll container ───
        # Todos los widgets del editor viven dentro de un QWidget que
        # va dentro de un QScrollArea; asi siempre entra en pantalla.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        layout = QFormLayout(content)

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

        # ─── Reactividad (Fase 8 — predictor de reacciones) ─────────
        # Aparece SIEMPRE (es opt-in via toggle). Lee de
        # block.feed_analysis_cache si el predictor corrio.
        self.gb_reactivity = QGroupBox("Reactividad (predictor Capa 4b)")
        rxlay = QVBoxLayout(self.gb_reactivity)

        # Toggle allow_reactions
        from chemfx.defaults import default_allow_reactions
        default_allow = default_allow_reactions(
            getattr(block, "eq_type", "") or "")
        self.allow_rxn_cb = QCheckBox(
            "Permitir reacciones en este bloque  "
            f"(default por tipo: {'ON' if default_allow else 'OFF'})"
        )
        self.allow_rxn_cb.setChecked(bool(
            getattr(block, "allow_reactions", default_allow)))
        self.allow_rxn_cb.setToolTip(
            "Si está marcado, las reacciones activas (debajo) se incluyen "
            "en el balance al correr Solve. Si está desmarcado, todas se "
            "ignoran. El asistente puede sugerir activar esto."
        )
        rxlay.addWidget(self.allow_rxn_cb)

        # Status: corrió el predictor o no
        fa_cache = getattr(block, "feed_analysis_cache", None) or {}
        n_predicted = fa_cache.get("n_predicted", 0)
        n_curated = fa_cache.get("n_curated", 0)
        n_warns = fa_cache.get("n_warnings", 0)
        if not fa_cache:
            status_text = (
                "<i>El predictor todavía no corrió sobre este bloque.</i><br>"
                "Apretá <b>Solve balances</b> para activar el análisis.")
        else:
            status_text = (
                f"Análisis: <b>{n_curated}</b> curadas · "
                f"<b>{n_predicted}</b> predichas · "
                f"<b>{n_warns}</b> warnings"
            )
        status_lbl = QLabel(status_text)
        status_lbl.setStyleSheet(
            "color: #444; font-size: 8.5pt; padding: 4px 0;")
        rxlay.addWidget(status_lbl)

        # Tabla de reacciones detectadas + checkboxes en active_reactions
        self.rxn_table = QTableWidget(0, 4)
        self.rxn_table.setHorizontalHeaderLabels(
            ["✓", "ID", "Reacción", "Conf"])
        self.rxn_table.verticalHeader().setVisible(False)
        self.rxn_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.rxn_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.rxn_table.setColumnWidth(0, 30)
        self.rxn_table.setColumnWidth(1, 140)
        self.rxn_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch)
        self.rxn_table.setColumnWidth(3, 50)
        self.rxn_table.setMinimumHeight(120)
        self.rxn_table.setMaximumHeight(200)
        rxlay.addWidget(self.rxn_table)
        self._populate_reactivity_table(block, fa_cache)

        rxhint = QLabel(
            "Marcá las reacciones que querés incluir en el balance.\n"
            "🟢 ALTA · 🟡 MEDIA · 🟠 BAJA · ⚫ no aplicable (fuera de rango T)"
        )
        rxhint.setStyleSheet("color: #888; font-size: 8pt;")
        rxlay.addWidget(rxhint)

        layout.addRow(self.gb_reactivity)

        # ─── Especies del equipo (read-only) ───
        # Espejo de los streams conectados a los puertos del bloque. NO se
        # editan especies acá: viven en las corrientes. Para modificar,
        # doble-click sobre el nombre del stream → abre el StreamInspector.
        try:
            parent_fs = getattr(parent, "fs", None)
        except Exception:
            parent_fs = None
        self._species_tbl_in = None
        self._species_tbl_out = None
        self._species_incoming: list = []
        self._species_outgoing: list = []
        if parent_fs is not None:
            self._build_species_section(parent_fs, block, layout)

        # botones (fuera del scroll: siempre visibles al fondo)
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ─── helpers Reactividad (Fase 8) ───
    def _populate_reactivity_table(self, block, fa_cache: dict) -> None:
        """Rellena la tabla de reacciones detectadas con checkboxes
        para activar/desactivar cada una en block.active_reactions."""
        active = set(getattr(block, "active_reactions", []) or [])
        rows: list = []
        # 1. Curadas: id + name (de fa_cache.curated_ids + curated_names)
        curated_ids = fa_cache.get("curated_ids", []) or []
        curated_names = fa_cache.get("curated_names", []) or []
        for rid, name in zip(curated_ids, curated_names):
            rows.append({
                "id": rid, "label": name or rid,
                "kind": "CURATED", "conf": "ALTA",
            })
        # 2. Predichas: del summary
        for r in fa_cache.get("predicted_summary", []) or []:
            label = r.get("display_label", "") or r.get("id", "")
            conf = (r.get("confidence_mechanism", "alta") or "alta").upper()
            rows.append({
                "id": r.get("id", ""), "label": label,
                "kind": "PRED", "conf": conf,
                "fav": r.get("favorable_at_T", False),
            })
        # 3. Auto-reactions (catálogo) en caché de fa_cache no se almacenan
        #    individualmente — solo n_auto. Lo dejamos para v2.

        self.rxn_table.setRowCount(len(rows))
        for ri, row in enumerate(rows):
            # Col 0: checkbox
            cb = QCheckBox()
            cb.setChecked(row["id"] in active)
            cb_w = QWidget()
            cb_l = QHBoxLayout(cb_w)
            cb_l.setContentsMargins(4, 0, 0, 0)
            cb_l.addWidget(cb)
            cb_l.addStretch()
            self.rxn_table.setCellWidget(ri, 0, cb_w)
            # Guardar reference para leer al apply
            cb.setProperty("rxn_id", row["id"])
            # Col 1: ID
            id_it = QTableWidgetItem(row["id"][:30])
            id_it.setToolTip(f"[{row['kind']}] {row['id']}")
            self.rxn_table.setItem(ri, 1, id_it)
            # Col 2: descripcion
            lbl_it = QTableWidgetItem(row["label"][:80])
            lbl_it.setToolTip(row["label"])
            self.rxn_table.setItem(ri, 2, lbl_it)
            # Col 3: confidence icono
            conf = row["conf"]
            icon_map = {"ALTA": "🟢", "MEDIA": "🟡", "BAJA": "🟠"}
            cf_it = QTableWidgetItem(icon_map.get(conf, "⚫"))
            cf_it.setToolTip(f"Confidence: {conf}")
            self.rxn_table.setItem(ri, 3, cf_it)

    # ─── helpers Especies del equipo (read-only) ───
    def _build_species_section(self, fs, block, layout) -> None:
        """Sección read-only con los streams entrantes y salientes del
        bloque y sus especies. Cero edición acá; doble-click sobre un
        stream abre el StreamInspector del editor."""
        gb = QGroupBox("Especies del equipo (read-only)")
        gbl = QVBoxLayout(gb)

        self._species_incoming = [
            s for s in fs.streams.values() if s.dst == block.id]
        self._species_outgoing = [
            s for s in fs.streams.values() if s.src == block.id]

        gbl.addWidget(QLabel("<b>◀ Entradas</b>"))
        if self._species_incoming:
            self._species_tbl_in = self._make_stream_species_table(
                self._species_incoming)
            gbl.addWidget(self._species_tbl_in)
        else:
            lbl = QLabel("(sin streams conectados a la entrada)")
            lbl.setStyleSheet("color: #888; font-style: italic;")
            gbl.addWidget(lbl)

        gbl.addWidget(QLabel("<b>▶ Salidas</b>"))
        if self._species_outgoing:
            self._species_tbl_out = self._make_stream_species_table(
                self._species_outgoing)
            gbl.addWidget(self._species_tbl_out)
        else:
            lbl = QLabel("(sin streams conectados a la salida)")
            lbl.setStyleSheet("color: #888; font-style: italic;")
            gbl.addWidget(lbl)

        hint = QLabel(
            "ℹ Doble-click sobre un stream para editar sus valores. "
            "Las especies viven en las corrientes, no en el equipo."
        )
        hint.setStyleSheet("color: #888; font-size: 8pt;")
        hint.setWordWrap(True)
        gbl.addWidget(hint)

        layout.addRow(gb)

    def _make_stream_species_table(self, streams: list) -> QTableWidget:
        tbl = QTableWidget(0, 4)
        tbl.setHorizontalHeaderLabels([
            "Stream", "Flujo (tm/año)", "T (°C)", "Especies",
        ])
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.verticalHeader().setVisible(False)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.setMinimumHeight(60)
        tbl.setMaximumHeight(180)
        tbl.setProperty("streams_by_row", streams)
        self._populate_species_table(tbl, streams)
        tbl.cellDoubleClicked.connect(
            lambda row, _col, t=tbl: self._on_species_table_dblclick(t, row)
        )
        return tbl

    def _populate_species_table(
            self, tbl: QTableWidget, streams: list) -> None:
        tbl.setRowCount(len(streams))
        for ri, s in enumerate(streams):
            nm = QTableWidgetItem(s.name)
            nm.setForeground(QColor("#1565c0"))
            f = nm.font(); f.setUnderline(True); nm.setFont(f)
            nm.setToolTip("Doble-click para editar este stream")
            tbl.setItem(ri, 0, nm)
            tbl.setItem(ri, 1, QTableWidgetItem(f"{s.mass_flow:,.1f}"))
            T = getattr(s, "temperature", 0.0)
            tbl.setItem(ri, 2, QTableWidgetItem(f"{T:.1f}"))
            if s.composition:
                parts = [
                    f"{k} {v*100:.1f}%"
                    for k, v in sorted(
                        s.composition.items(), key=lambda kv: -kv[1])[:4]
                ]
                comp_str = ", ".join(parts)
                if len(s.composition) > 4:
                    comp_str += f", +{len(s.composition)-4} más"
                comp_color = None
            elif s.main_component:
                comp_str = f"{s.main_component} (100%)"
                comp_color = None
            else:
                comp_str = "⚠ Aún no resuelto. Ejecutá Solve."
                comp_color = QColor("#b8860b")
            it = QTableWidgetItem(comp_str)
            it.setToolTip(comp_str)
            if comp_color is not None:
                it.setForeground(comp_color)
            tbl.setItem(ri, 3, it)
        tbl.resizeColumnsToContents()

    def _on_species_table_dblclick(
            self, tbl: QTableWidget, row: int) -> None:
        streams = tbl.property("streams_by_row")
        if not streams or row < 0 or row >= len(streams):
            return
        stream = streams[row]
        editor = self.parent()
        edit_fn = getattr(editor, "edit_stream", None)
        if edit_fn is None:
            return
        edit_fn(stream)
        # Repoblar tablas: los Stream se mutan in-place en apply_to_model
        if self._species_tbl_in is not None:
            self._populate_species_table(
                self._species_tbl_in, self._species_incoming)
        if self._species_tbl_out is not None:
            self._populate_species_table(
                self._species_tbl_out, self._species_outgoing)

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

        # Reactividad — toggle allow_reactions + active_reactions (Fase 8)
        if hasattr(self, "allow_rxn_cb"):
            self.block.allow_reactions = bool(self.allow_rxn_cb.isChecked())
        if hasattr(self, "rxn_table"):
            active_ids: list = []
            for ri in range(self.rxn_table.rowCount()):
                cb_w = self.rxn_table.cellWidget(ri, 0)
                if cb_w is None:
                    continue
                cb = cb_w.findChild(QCheckBox)
                if cb is None:
                    continue
                if cb.isChecked():
                    rid = cb.property("rxn_id")
                    if rid:
                        active_ids.append(rid)
            self.block.active_reactions = active_ids

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
    """Editor de reaccion 'estilo iPhone': pickers de chips, balance/ΔH auto.

    Diseño single-page sin tabla y sin coeficientes visibles. El usuario:
      1. Tap + verde para agregar reactivos (popup picker del thermo_db).
      2. Tap + verde para agregar productos.
      3. El balance atómico y el ΔH se calculan solos en cada cambio.
      4. Opcionalmente abre "Avanzado" para ID, nombre, modo, ΔS, plantillas.

    Internamente sigue persistiendo el mismo dict {stoich, dh, T_min, ...}
    compatible con reactions_db.reaction_from_dict.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Nueva reacción")
        self.setMinimumWidth(580)
        self.resize(640, 700)
        self.result_dict = None

        # Estado interno (chips). Cada chip:
        #   {formula, phase, nu, widget, name}
        # nu < 0 para reactivos, > 0 para productos.
        self.reactant_chips: list = []
        self.product_chips:  list = []
        self._setting_dh = False
        self._user_overrode_dh = False

        # Cargar thermo_db
        try:
            import thermo_db as _tdb
            self._thermo_db = _tdb
            _names = sorted(_tdb.list_names())
        except Exception:
            self._thermo_db = None
            _names = []
        self._compound_items = []
        for n in _names:
            try:
                ct = self._thermo_db.get(n) if self._thermo_db else None
            except Exception:
                ct = None
            f = getattr(ct, "formula", "") if ct else ""
            disp = f"{n}  ({f})" if f else n
            self._compound_items.append((disp, f, n))
        self._disp_list = [d for d, _, _ in self._compound_items]

        # ─── Layout principal ───
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(10)

        # Título
        title = QLabel("✨ Nueva reacción")
        title.setStyleSheet(
            "font-size: 17pt; font-weight: 600; color: #111;")
        outer.addWidget(title)
        hint = QLabel(
            "Elegí reactivos y productos. Los coeficientes, el balance "
            "atómico y el ΔH se calculan automáticamente.")
        hint.setStyleSheet("color: #666; font-size: 9pt;")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        # Reactivos
        outer.addWidget(self._section_label("Reactivos"))
        rb, self.reactant_layout = self._make_chip_container()
        outer.addWidget(rb)

        # Productos
        outer.addWidget(self._section_label("Productos"))
        pb, self.product_layout = self._make_chip_container()
        outer.addWidget(pb)

        # Botón Sugerir productos
        sg_row = QHBoxLayout()
        btn_suggest = QPushButton("🔮 Sugerir productos")
        btn_suggest.setMinimumHeight(34)
        btn_suggest.setToolTip(
            "Llama al predictor chemfx con los reactivos elegidos "
            "para sugerir productos y completar la reacción.")
        btn_suggest.clicked.connect(self._predict_from_reactants)
        sg_row.addWidget(btn_suggest)
        sg_row.addStretch()
        outer.addLayout(sg_row)

        # Badges
        bd_row = QHBoxLayout()
        bd_row.setSpacing(6)
        self.badge_balance = QLabel("Balance: —")
        self.badge_balance.setStyleSheet(self._badge_style("neutral"))
        self.badge_dh = QLabel("ΔH: —")
        self.badge_dh.setStyleSheet(self._badge_style("neutral"))
        bd_row.addWidget(self.badge_balance)
        bd_row.addWidget(self.badge_dh)
        bd_row.addStretch()
        outer.addLayout(bd_row)

        # Condiciones
        outer.addWidget(self._section_label("Condiciones típicas"))
        cond_row = QHBoxLayout()
        cond_row.addWidget(QLabel("T desde"))
        self.t_min_edit = QDoubleSpinBox()
        self.t_min_edit.setRange(100, 5000)
        self.t_min_edit.setValue(298)
        self.t_min_edit.setSuffix(" K")
        cond_row.addWidget(self.t_min_edit)
        cond_row.addWidget(QLabel("a"))
        self.t_max_edit = QDoubleSpinBox()
        self.t_max_edit.setRange(100, 5000)
        self.t_max_edit.setValue(2000)
        self.t_max_edit.setSuffix(" K")
        cond_row.addWidget(self.t_max_edit)
        cond_row.addStretch()
        outer.addLayout(cond_row)

        # ─── Avanzado (colapsable) ───
        self.gb_advanced = QGroupBox(
            "Avanzado  (ID, nombre, ΔS/Keq, plantillas)")
        self.gb_advanced.setCheckable(True)
        self.gb_advanced.setChecked(False)
        adv = QFormLayout(self.gb_advanced)
        self.id_edit = QLineEdit("CUSTOM-1")
        adv.addRow("ID:", self.id_edit)
        self.name_edit = QLineEdit("Reacción custom")
        adv.addRow("Nombre:", self.name_edit)
        self.dh_edit = QDoubleSpinBox()
        self.dh_edit.setRange(-1e4, 1e4)
        self.dh_edit.setDecimals(2)
        self.dh_edit.setSuffix(" kJ/mol")
        self.dh_edit.valueChanged.connect(self._on_dh_changed)
        adv.addRow("ΔH₂₉₈ override:", self.dh_edit)
        self.rb_rev = QRadioButton("Reversible (ΔS o Keq)")
        self.rb_irr = QRadioButton("Irreversible (conversión declarada)")
        self.rb_rev.setChecked(True)
        rb_grp = QButtonGroup(self)
        rb_grp.addButton(self.rb_rev)
        rb_grp.addButton(self.rb_irr)
        adv.addRow("Tipo:", self.rb_rev)
        adv.addRow("", self.rb_irr)
        self.ds_edit = QDoubleSpinBox()
        self.ds_edit.setRange(-1e4, 1e4)
        self.ds_edit.setDecimals(2)
        self.ds_edit.setSuffix(" J/(mol·K)")
        adv.addRow("ΔS₂₉₈:", self.ds_edit)
        self.keq_edit = QDoubleSpinBox()
        self.keq_edit.setRange(0.0, 1e30)
        self.keq_edit.setDecimals(6)
        adv.addRow("Keq₂₉₈:", self.keq_edit)
        # Plantillas
        self.tpl_combo = QComboBox()
        self.tpl_combo.addItem("— Elegir plantilla —", None)
        self._templates = [
            ("Combustión CH4", {
                "r": [("CH4", "g"), ("O2", "g")],
                "p": [("CO2", "g"), ("H2O", "g")],
                "T": (298, 2500), "name": "Combustión metano"}),
            ("Water-gas shift", {
                "r": [("CO", "g"), ("H2O", "g")],
                "p": [("CO2", "g"), ("H2", "g")],
                "T": (473, 773), "name": "Water-gas shift"}),
            ("Esterificación HAc+EtOH", {
                "r": [("C2H4O2", "l"), ("C2H6O", "l")],
                "p": [("C4H8O2", "l"), ("H2O", "l")],
                "T": (333, 423), "name": "Esterificación HAc+EtOH"}),
            ("Steam reforming CH4", {
                "r": [("CH4", "g"), ("H2O", "g")],
                "p": [("CO", "g"), ("H2", "g")],
                "T": (973, 1273), "name": "Steam reforming CH4"}),
            ("Methanation", {
                "r": [("CO", "g"), ("H2", "g")],
                "p": [("CH4", "g"), ("H2O", "g")],
                "T": (523, 723), "name": "Methanation"}),
            ("Haber-Bosch (NH3)", {
                "r": [("N2", "g"), ("H2", "g")],
                "p": [("NH3", "g")],
                "T": (673, 823), "name": "Haber-Bosch"}),
        ]
        for disp, data in self._templates:
            self.tpl_combo.addItem(disp, data)
        self.tpl_combo.currentIndexChanged.connect(self._apply_template_v2)
        adv.addRow("Plantilla:", self.tpl_combo)
        btn_rebal = QPushButton("⚖ Re-balancear manualmente")
        btn_rebal.clicked.connect(lambda: self._auto_balance_chips(silent=False))
        adv.addRow("", btn_rebal)
        outer.addWidget(self.gb_advanced)
        self.gb_advanced.toggled.connect(self._toggle_advanced)
        # Botones OK/Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Guardar")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        # Init: render chips + colapsar avanzado
        self._refresh_chips()
        self._toggle_advanced(False)
        self._recompute_all()

    # ─── helpers de UI ───
    def _section_label(self, text):
        l = QLabel(text)
        l.setStyleSheet(
            "font-size: 10pt; font-weight: 600; color: #555; "
            "padding-top: 6px;")
        return l

    def _make_chip_container(self):
        fr = QFrame()
        fr.setStyleSheet(
            "QFrame { background: #f5f5f7; border-radius: 10px; "
            "padding: 6px; }")
        fr.setMinimumHeight(54)
        lay = QHBoxLayout(fr)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(6)
        return fr, lay

    def _badge_style(self, kind):
        if kind == "ok":
            return ("padding: 5px 14px; border-radius: 12px; font-size: 9pt; "
                    "font-weight: 500; color: #16632c; background: #d4ecd4;")
        if kind == "bad":
            return ("padding: 5px 14px; border-radius: 12px; font-size: 9pt; "
                    "font-weight: 500; color: #8b0000; background: #fbd0d0;")
        return ("padding: 5px 14px; border-radius: 12px; font-size: 9pt; "
                "color: #666; background: #e8e8e8;")

    def _refresh_chips(self):
        """Limpia y reconstruye los layouts de chips desde reactant_chips
        + product_chips."""
        if not hasattr(self, "reactant_layout"):
            return
        for lay, chips, side in (
            (self.reactant_layout, self.reactant_chips, "reactant"),
            (self.product_layout,  self.product_chips,  "product"),
        ):
            while lay.count() > 0:
                it = lay.takeAt(0)
                w = it.widget()
                if w is not None:
                    w.setParent(None)
            for ch in chips:
                w = self._make_chip_widget(side, ch)
                ch["widget"] = w
                lay.addWidget(w)
            # Botón +
            btn_add = QPushButton("+")
            btn_add.setFixedSize(34, 34)
            btn_add.setStyleSheet(
                "QPushButton { border-radius: 17px; background: #34c759; "
                "color: white; font-weight: bold; font-size: 14pt; border: none; }"
                "QPushButton:hover { background: #2ab04b; }"
            )
            btn_add.setToolTip(
                "Agregar reactivo" if side == "reactant" else "Agregar producto")
            btn_add.clicked.connect(
                lambda _c=False, s=side: self._open_picker(s))
            lay.addWidget(btn_add)
            lay.addStretch()

    def _make_chip_widget(self, side, ch):
        fr = QFrame()
        fr.setStyleSheet(
            "QFrame { background: white; border: 1px solid #d0d0d0; "
            "border-radius: 14px; }"
        )
        fr.setMinimumHeight(32)
        h = QHBoxLayout(fr)
        h.setContentsMargins(10, 4, 4, 4)
        h.setSpacing(2)
        nu_abs = abs(ch.get("nu", 0))
        prefix = (f"{nu_abs} " if nu_abs > 1 else "")
        nm = ch.get("name") or ch.get("formula") or "?"
        phase = ch.get("phase", "g")
        lbl = QLabel(
            f"<b>{prefix}{nm}</b>"
            f"&nbsp;&nbsp;<span style='color:#888; font-size:8pt;'>({phase})</span>"
        )
        h.addWidget(lbl)
        btn_x = QPushButton("×")
        btn_x.setFixedSize(22, 22)
        btn_x.setStyleSheet(
            "QPushButton { border: none; color: #999; font-size: 13pt; "
            "background: transparent; }"
            "QPushButton:hover { color: #c41e3a; }"
        )
        btn_x.clicked.connect(
            lambda _c=False, s=side, c=ch: self._remove_chip(s, c))
        h.addWidget(btn_x)
        return fr

    def _toggle_advanced(self, checked):
        for w in self.gb_advanced.findChildren(QWidget):
            if w is self.gb_advanced:
                continue
            w.setVisible(bool(checked))

    # ─── operaciones sobre chips ───
    def _open_picker(self, side):
        from PySide6.QtWidgets import QInputDialog
        if not self._disp_list:
            QMessageBox.warning(self, "Agregar",
                "El thermo_db no cargó. No puedo listar compuestos.")
            return
        disp, ok = QInputDialog.getItem(
            self, "Agregar " + ("reactivo" if side == "reactant" else "producto"),
            "Buscá el compuesto (podés tipear para filtrar):",
            self._disp_list, 0, True)
        if not ok or not disp:
            return
        formula = ""
        name = disp.strip()
        for d, f, n in self._compound_items:
            if d == disp:
                formula = f
                name = n
                break
        if not formula:
            formula = disp.split()[0]
            name = formula
        phase, ok = QInputDialog.getItem(
            self, f"Fase de {name}",
            "Estado de la materia:",
            ["g (gas)", "l (líquido)", "s (sólido)", "aq (acuoso)"],
            0, False)
        if not ok:
            return
        phase = phase.split()[0]
        chips = (self.reactant_chips
                 if side == "reactant" else self.product_chips)
        sign = -1 if side == "reactant" else +1
        chips.append({
            "formula": formula, "phase": phase, "nu": sign,
            "name": name, "widget": None,
        })
        self._refresh_chips()
        self._auto_balance_chips(silent=True)
        self._recompute_all()

    def _remove_chip(self, side, ch):
        chips = (self.reactant_chips
                 if side == "reactant" else self.product_chips)
        if ch in chips:
            chips.remove(ch)
        self._refresh_chips()
        self._auto_balance_chips(silent=True)
        self._recompute_all()

    def _all_chips(self):
        return self.reactant_chips + self.product_chips

    # ─── balance + ΔH + predictor ───
    def _atom_counts(self, formula):
        import re
        d = {}
        if not formula:
            return d
        for m in re.finditer(r"([A-Z][a-z]?)(\d*)", formula):
            el, num = m.group(1), m.group(2)
            if not el:
                continue
            d[el] = d.get(el, 0) + (int(num) if num else 1)
        return d

    def _name_for_formula(self, formula):
        for _d, f, n in self._compound_items:
            if f == formula:
                return n
        return None

    def _recompute_all(self):
        """Actualiza badges balance + ΔH; auto-calcula ΔH por Hess si
        el user no lo overridó manualmente."""
        if not hasattr(self, "badge_balance"):
            return
        chips = self._all_chips()
        if not chips:
            self.badge_balance.setText("Balance: vacío")
            self.badge_balance.setStyleSheet(self._badge_style("neutral"))
            self.badge_dh.setText("ΔH: —")
            self.badge_dh.setStyleSheet(self._badge_style("neutral"))
            return
        # Balance
        total = {}
        for ch in chips:
            nu = ch.get("nu", 0)
            if nu == 0:
                continue
            for el, n in self._atom_counts(ch.get("formula", "")).items():
                total[el] = total.get(el, 0) + nu * n
        ok = bool(total) and all(abs(v) < 1e-6 for v in total.values())
        if ok:
            self.badge_balance.setText("✓ Balanceado")
            self.badge_balance.setStyleSheet(self._badge_style("ok"))
        else:
            non_zero = {k: int(round(v)) for k, v in total.items()
                        if abs(v) > 1e-6}
            msg = ("  ".join(f"{k}: {v:+d}" for k, v in non_zero.items())
                   or "incompleto")
            self.badge_balance.setText(f"✗ {msg}")
            self.badge_balance.setStyleSheet(self._badge_style("bad"))
        # ΔH
        if not self._user_overrode_dh:
            dh = self._hess_dh()
            if dh is not None:
                self._setting_dh = True
                try:
                    self.dh_edit.setValue(dh)
                finally:
                    self._setting_dh = False
                kind = "ok" if dh < 0 else "neutral"
                self.badge_dh.setText(f"ΔH: {dh:+.1f} kJ/mol")
                self.badge_dh.setStyleSheet(self._badge_style(kind))
            else:
                self.badge_dh.setText("ΔH: — (faltan datos)")
                self.badge_dh.setStyleSheet(self._badge_style("neutral"))
        else:
            v = float(self.dh_edit.value())
            self.badge_dh.setText(f"ΔH: {v:+.1f} kJ/mol (manual)")
            self.badge_dh.setStyleSheet(self._badge_style("neutral"))

    def _hess_dh(self):
        if self._thermo_db is None:
            return None
        total = 0.0
        for ch in self._all_chips():
            nu = ch.get("nu", 0)
            if nu == 0:
                continue
            ct = None
            name = ch.get("name") or ""
            try:
                ct = self._thermo_db.get(name)
            except Exception:
                ct = None
            if ct is None:
                f = ch.get("formula", "")
                for _d, ff, nn in self._compound_items:
                    if ff == f:
                        try:
                            ct = self._thermo_db.get(nn)
                        except Exception:
                            ct = None
                        break
            if ct is None:
                return None
            phase = ch.get("phase", "g")
            if phase in ("l", "aq"):
                dh = (getattr(ct, "dh_f_liq_kJ_mol", None)
                      or getattr(ct, "dh_f_gas_kJ_mol", None))
            else:
                dh = (getattr(ct, "dh_f_gas_kJ_mol", None)
                      or getattr(ct, "dh_f_liq_kJ_mol", None))
            if dh is None:
                return None
            total += nu * dh
        return total

    def _on_dh_changed(self, _v):
        if self._setting_dh:
            return
        self._user_overrode_dh = True
        self._recompute_all()

    def _auto_balance_chips(self, silent=False):
        """Calcula coeficientes por null space y los settea en los chips."""
        try:
            import numpy as np
        except ImportError:
            if not silent:
                QMessageBox.warning(self, "Auto-balance",
                    "Requiere numpy. pip install numpy")
            return
        from math import gcd
        from functools import reduce
        chips = self._all_chips()
        if len(chips) < 2:
            return
        signs = [-1 if ch in self.reactant_chips else +1 for ch in chips]
        formulas = [ch.get("formula", "") for ch in chips]
        apsp = [self._atom_counts(f) for f in formulas]
        all_el = sorted({e for d in apsp for e in d})
        if not all_el:
            return
        A = np.zeros((len(all_el), len(chips)))
        for j, ad in enumerate(apsp):
            for i, el in enumerate(all_el):
                A[i, j] = ad.get(el, 0) * signs[j]
        try:
            _, s, vh = np.linalg.svd(A)
        except Exception:
            return
        tol = max(A.shape) * np.spacing(np.linalg.norm(A) or 1.0)
        rank = int(np.sum(s > tol))
        null_dim = len(chips) - rank
        if null_dim != 1:
            if not silent:
                if null_dim == 0:
                    QMessageBox.warning(self, "Auto-balance",
                        "El sistema está sobredeterminado.\n"
                        "Revisá las fórmulas o agregá especies que falten.")
                else:
                    QMessageBox.warning(self, "Auto-balance",
                        f"El sistema es ambiguo (null space = {null_dim}).\n"
                        "Definí mejor las especies.")
            return
        nu = vh[-1, :]
        nz = next((v for v in nu if abs(v) > 1e-9), 1.0)
        nu = nu / nz
        sc = np.round(nu * 10000).astype(int)
        nzv = [abs(v) for v in sc if v != 0]
        if not nzv:
            return
        g = reduce(gcd, nzv) or 1
        coeffs = [int(v // g) for v in sc]
        if all(c <= 0 for c in coeffs) and any(c < 0 for c in coeffs):
            coeffs = [-c for c in coeffs]
        for k, ch in enumerate(chips):
            ch["nu"] = coeffs[k] * signs[k]
        self._refresh_chips()

    def _apply_template_v2(self, idx):
        if idx <= 0:
            return
        data = self.tpl_combo.itemData(idx)
        if not isinstance(data, dict):
            return
        self.reactant_chips.clear()
        self.product_chips.clear()
        for f, ph in data.get("r", []):
            nm = self._name_for_formula(f) or f
            self.reactant_chips.append({
                "formula": f, "phase": ph, "nu": -1,
                "name": nm, "widget": None})
        for f, ph in data.get("p", []):
            nm = self._name_for_formula(f) or f
            self.product_chips.append({
                "formula": f, "phase": ph, "nu": +1,
                "name": nm, "widget": None})
        self.tpl_combo.blockSignals(True)
        self.tpl_combo.setCurrentIndex(0)
        self.tpl_combo.blockSignals(False)
        if data.get("T"):
            self.t_min_edit.setValue(float(data["T"][0]))
            self.t_max_edit.setValue(float(data["T"][1]))
        if data.get("name"):
            self.name_edit.setText(data["name"])
        self._user_overrode_dh = False
        self._refresh_chips()
        self._auto_balance_chips(silent=True)
        self._recompute_all()

    def _predict_from_reactants(self):
        """Predice productos via chemfx a partir de los reactivos elegidos."""
        reactants = [ch.get("formula", "") for ch in self.reactant_chips]
        reactants = [r for r in reactants if r]
        if not reactants:
            QMessageBox.warning(self, "Sugerir productos",
                "Primero agregá al menos un reactivo (botón verde +).")
            return
        try:
            from chemfx.predictor.reaction_predictor import predict_reactions
        except ImportError:
            QMessageBox.warning(self, "Sugerir productos",
                "chemfx no disponible. pip install rdkit thermo")
            return
        cnames = []
        for r in reactants:
            n = self._name_for_formula(r) or r.lower()
            cnames.append(n)
        T_mid = 0.5 * (self.t_min_edit.value() + self.t_max_edit.value())
        try:
            fa = predict_reactions(cnames, T_K=T_mid)
        except Exception as e:
            QMessageBox.warning(self, "Sugerir productos",
                f"El predictor falló: {e}")
            return
        cands = (list(getattr(fa, "curated", []) or [])
                 + list(getattr(fa, "predicted", []) or []))
        if not cands:
            QMessageBox.information(self, "Sugerir productos",
                f"No encontré reacciones plausibles a {T_mid:.0f} K\n"
                f"para: {', '.join(reactants)}.\n\n"
                "Probá con más reactivos o agregá los productos a mano.")
            return
        if len(cands) > 1:
            items = []
            for r in cands[:15]:
                lbl = getattr(r, "display_label", "") or getattr(r, "id", "?")
                conf = getattr(r, "confidence_mechanism", None)
                items.append(f"[{conf.name if conf else '?'}] {lbl}")
            from PySide6.QtWidgets import QInputDialog
            sel, ok = QInputDialog.getItem(self, "Sugerir productos",
                f"Encontré {len(cands)} opción(es). ¿Cuál usar?",
                items, 0, False)
            if not ok:
                return
            rxn = cands[items.index(sel)]
        else:
            rxn = cands[0]
        stoich = list(getattr(rxn, "stoichiometry", []) or [])
        if not stoich:
            QMessageBox.warning(self, "Sugerir productos",
                "La reacción seleccionada no trae estequiometría.")
            return
        self.reactant_chips.clear()
        self.product_chips.clear()
        for sp in stoich:
            f = str(getattr(sp, "formula", "") or "")
            ph = str(getattr(sp, "phase", "g") or "g")
            nu = int(getattr(sp, "nu", 0) or 0)
            if nu == 0:
                continue
            nm = self._name_for_formula(f) or f
            ch = {"formula": f, "phase": ph, "nu": nu,
                  "name": nm, "widget": None}
            (self.reactant_chips if nu < 0 else self.product_chips).append(ch)
        label = getattr(rxn, "display_label", "") or getattr(rxn, "id", "")
        if label:
            self.name_edit.setText(label[:60])
        tr = getattr(rxn, "T_range_K", None)
        if tr and len(tr) == 2:
            try:
                self.t_min_edit.setValue(float(tr[0]))
                self.t_max_edit.setValue(float(tr[1]))
            except Exception:
                pass
        self._user_overrode_dh = False
        self._refresh_chips()
        self._recompute_all()

    def _on_accept(self):
        import reactions_db as _rdb
        stoich = []
        for ch in self._all_chips():
            f = ch.get("formula", "")
            nu = int(ch.get("nu", 0))
            if not f or nu == 0:
                continue
            ph = ch.get("phase", "g")
            stoich.append({"formula": f, "phase": ph, "nu": nu})
        if len(stoich) < 2:
            QMessageBox.warning(self, "Guardar",
                "Necesito al menos un reactivo y un producto.\n"
                "Tip: tocá los botones verdes + para agregar.")
            return
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
        try:
            _rdb.reaction_from_dict(d)
        except ValueError as e:
            QMessageBox.warning(self, "Reacción inválida", str(e))
            return
        self.result_dict = d
        self.accept()


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

    def _stream_alive(self) -> bool:
        """Verifica que el stream subyacente sigue en fs.streams.  Si fue
        borrado por _delete_stream pero el handle quedó en escena (caso
        edge: selección Qt, scene listing race condition), evita acceder
        al modelo huérfano y crashear."""
        try:
            si = self._stream_item
            return si is not None and si.model is not None \
                and si.fs is not None \
                and si.model.id in si.fs.streams
        except Exception:
            return False

    def _self_destruct(self):
        """Quita el handle de la escena si su stream fue borrado."""
        try:
            sc = self.scene()
            if sc is not None:
                sc.removeItem(self)
        except Exception:
            pass

    def itemChange(self, change, value):
        # GUARD: si el stream subyacente fue borrado pero el handle
        # quedó vivo (caso reportado: borrar nodo + drag posterior →
        # crash), abortamos sin tocar modelo.
        if change == QGraphicsItem.ItemPositionHasChanged \
                and not self._stream_alive():
            self._self_destruct()
            return super().itemChange(change, value)
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


def _simplify_orthogonal(pts, eps=0.5):
    """Limpia una polyline ortogonal eliminando puntos interiores que son
    colineales con sus vecinos.  Esto colapsa los tramos "de ida y vuelta
    sobre la misma línea" (backtracks): tres puntos seguidos sobre el mismo
    eje (misma x o misma y) donde el del medio es redundante o un pico que
    sale y vuelve.  Preserva SIEMPRE los extremos (puertos).

    Ejemplos:
      (0,0)→(10,0)→(5,0)   ⇒  (0,0)→(5,0)     (pico horizontal colapsado)
      (0,0)→(10,0)→(10,0)  ⇒  (0,0)→(10,0)    (duplicado eliminado)
    Un detour real (con offset perpendicular intermedio) NO es colineal y
    se conserva.
    """
    if len(pts) < 6:
        return pts
    P = [(pts[i], pts[i + 1]) for i in range(0, len(pts) - 1, 2)]
    changed = True
    while changed and len(P) > 2:
        changed = False
        i = 1
        while i < len(P) - 1:
            ax, ay = P[i - 1]
            bx, by = P[i]
            cx, cy = P[i + 1]
            dup = abs(ax - bx) < eps and abs(ay - by) < eps
            collinear_h = abs(ay - by) < eps and abs(by - cy) < eps
            collinear_v = abs(ax - bx) < eps and abs(bx - cx) < eps
            if dup or collinear_h or collinear_v:
                del P[i]            # punto interior redundante / backtrack
                changed = True
            else:
                i += 1
    out = []
    for (x, y) in P:
        out.append(x)
        out.append(y)
    return out


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

    def mouseDoubleClickEvent(self, event):
        """Doble-click sobre la bolita naranja → abrir editor del stream.
        Sin este override, Qt por default llama mousePressEvent en el
        segundo click, lo que prepara otro drag potencial pero NO abre
        nada. Usuario espera que doble-click haga 'algo útil' (editar
        propiedades) — delegamos al stream item subyacente."""
        si = self._stream_item
        editor = getattr(si, "editor", None) if si is not None else None
        if editor is not None and hasattr(editor, "edit_stream"):
            # Reset flags primero para que cualquier itemChange residual
            # no commitee disconnect mientras el dialog está abierto.
            self._drag_committed = False
            self._press_pos = None
            editor.edit_stream(si.model)
        event.accept()

    def itemChange(self, change, value):
        # GUARD: si el stream subyacente fue borrado pero el handle quedó
        # vivo (caso reportado: borrar nodo + drag posterior → crash), nos
        # auto-destruimos sin tocar modelo.
        if change == QGraphicsItem.ItemPositionHasChanged:
            try:
                si = self._stream_item
                alive = (si is not None and si.model is not None
                         and si.fs is not None
                         and si.model.id in si.fs.streams)
            except Exception:
                alive = False
            if not alive:
                try:
                    sc = self.scene()
                    if sc is not None: sc.removeItem(self)
                except Exception:
                    pass
                return super().itemChange(change, value)
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
            # SANITY: si new_xy ~= (0, 0) Y press_pos NO estaba en (0, 0)
            # → anomalía. Algo dejó el handle en (0,0) entre press y este
            # update (e.g., un sync programatico mid-drag, un Qt internal
            # weirdness). NO commitear — sería escribir start_xy=[0,0]
            # → flecha 'a Jupiter'. Restaurar pos desde el modelo y
            # abortar el drag.
            pp_check = self._press_pos
            if (abs(new_xy[0]) < 1.0 and abs(new_xy[1]) < 1.0
                    and pp_check is not None
                    and (abs(pp_check.x()) > 1.0 or abs(pp_check.y()) > 1.0)):
                self._drag_committed = False
                self._sync_pos_from_model()
                return super().itemChange(change, value)
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
        # GUARD: stream borrado mientras el handle estaba siendo arrastrado.
        try:
            si = self._stream_item
            alive = (si is not None and si.model is not None
                     and si.fs is not None
                     and si.model.id in si.fs.streams)
        except Exception:
            alive = False
        if not alive:
            try:
                sc = self.scene()
                if sc is not None: sc.removeItem(self)
            except Exception:
                pass
            return
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
            # CRITICAL: clear _drag_committed BEFORE setPos. El setPos
            # dispara itemChange→ItemPositionHasChanged. Si
            # _drag_committed sigue True, mi codigo de itemChange
            # entra al bloque de disconnect y sobreescribe s.src=-1,
            # start_xy=new_xy — DESHACIENDO el snap que acabamos de
            # commitear. Tambien clearamos _press_pos para que el
            # check 'pp is None' haga return early si itemChange
            # llega a fire de todos modos.
            self._drag_committed = False
            self._press_pos = None
            # Y para mayor seguridad, deshabilitar geometry signals
            # durante el setPos (igual que en _sync_pos_from_model).
            self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
            try:
                self.setPos(p_scene)
            finally:
                self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        else:
            # Mantener flotante: xy ya quedó guardado en itemChange
            pass
        self._hide_snap_marker()
        # IMPORTANTE: super().mouseReleaseEvent + reset de flags ANTES de
        # update_path. update_path con rebuild_handles=True default
        # destruye este handle (self) — llamar super() o setear self.*
        # despues sería operar sobre un item ya quitado de la escena,
        # lo cual puede dejar internal Qt state inconsistente.
        super().mouseReleaseEvent(event)
        self._press_pos = None
        self._drag_committed = False
        # Refresh (puede destruir 'self' via _rebuild_handles)
        si.update_path()
        # Notificar al editor que algo cambió (mark_dirty)
        editor = getattr(si, "editor", None)
        if editor is not None and hasattr(editor, "_mark_dirty"):
            editor._mark_dirty()


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

        # Dimensiones del bloque.  PRIORIDAD a las dims nativas del
        # glyph ISA escaladas (1.5x) — así el recuadro del bloque tiene
        # el mismo aspect ratio que la silueta y no quedan espacios
        # vacíos a los lados.  Fallback a pfd_symbols.block_dims solo
        # para eq_types que no mapeen a un tipo ISA conocido.
        try:
            from editor_chrome import isa_type_for_eq, BLOCK_DIMS
            isa = isa_type_for_eq(block.eq_type)
            if isa in BLOCK_DIMS:
                nw, nh = BLOCK_DIMS[isa]
                # Factor 1.6 = visual size cómodo (reactor → 96x102,
                # tower → 70x141, hx → 134x80) sin sacrificar densidad.
                self.W, self.H = nw * 1.6, nh * 1.6
            else:
                self.W, self.H = pfd.block_dims(block.eq_type)
        except Exception:
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
            # Color teal del nuevo tema + más grande (18px) + opacity 0.95
            # para que sean realmente visibles sobre la silueta ISA.
            ic = make_qicon(icon_id, color="#0d6e78", size=20)
            if ic is not None:
                self.type_badge = QGraphicsPixmapItem(
                    ic.pixmap(18, 18), parent=self)
                self.type_badge.setPos(2, self.H - 20)
                self.type_badge.setZValue(2.5)
                self.type_badge.setAcceptedMouseButtons(Qt.NoButton)
                self.type_badge.setOpacity(0.95)
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
        """Renderiza la silueta ISA del eq_type (Parte B — NUEVA_UI).

        Reemplaza el SVG raster del antiguo pfd_symbols por un
        IsaGlyphItem vectorial nativo (QPainter paths). El glyph se
        escala a las dimensiones W×H del bloque preservando las
        proporciones del diseño hi-fi. Mantiene puertos, badges,
        tag y halo de status idénticos.

        Si el módulo editor_chrome no está disponible (entorno sin
        PySide6 dev install), cae al SVG legacy para no perder UI.
        """
        self._svg_mode = False
        self._isa_item = None
        try:
            from editor_chrome import IsaGlyphItem
            isa = IsaGlyphItem(eq_type, self.W, self.H, parent=self)
            isa.setPos(0, 0)
            isa.setZValue(0)
            # estado inicial sync con _status del solver
            isa.set_state(self._isa_state_for_status(self._status))
            self.decoration_items.append(isa)
            self._isa_item = isa
            self._svg_mode = True
            return
        except Exception:
            pass

        # ─── Fallback: SVG raster legacy ─────────────────────
        svg_str = pfd.wrap_svg(pfd.EQ_TYPE_TO_SYMBOL.get(eq_type, ""),
                                w=self.W, h=self.H)
        if not svg_str:
            return

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
            pix_item.setPos(0, 0)
            pix_item.setZValue(0)
            pix_item.setTransformationMode(Qt.SmoothTransformation)
            self.decoration_items.append(pix_item)
            self._svg_mode = True
        except Exception:
            pass

    @staticmethod
    def _isa_state_for_status(status: str) -> str:
        """Mapea el `_status` del solver al estado visual del ISA glyph."""
        return {
            "ok":      "idle",      # el halo verde ya está en status_halo
            "warning": "warning",
            "error":   "error",
            "unrun":   "idle",
            "stale":   "idle",
            "empty":   "idle",
        }.get(status, "idle")

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
            kind = ep.get_port_kind(self.model.eq_type, pname)
            base_color = PORT_KIND_COLORS.get(kind, COLOR_PORT_AUX)
            ell = QGraphicsEllipseItem(cx - r, cy - r, 2*r, 2*r, parent=self)
            ell.setBrush(QBrush(_port_tint(base_color)))
            ell.setPen(QPen(base_color, 1.2))
            ell.setData(0, pname)
            ell.setData(1, kind)
            ell.setZValue(3)
            self.port_items[pname] = ell
            # tooltip — el user ve qué clase es ese puerto al hover
            ell.setToolTip(f"{pname}  ·  {kind.replace('_', ' ')}")

    def update_port_colors(self, used_ports: set):
        """Pinta cada puerto según (a) tipo, (b) estado conectado.

        · Conectado → relleno sólido del color por tipo (alpha 100%).
        · Libre     → relleno tinte claro (alpha 110/255) — el user ve
                       el HINT del tipo pero no confunde con uno activo.
        """
        for pname, ell in self.port_items.items():
            kind = ell.data(1) or "aux"
            base_color = PORT_KIND_COLORS.get(kind, COLOR_PORT_AUX)
            if pname in used_ports:
                ell.setBrush(QBrush(base_color))           # saturado
            else:
                ell.setBrush(QBrush(_port_tint(base_color)))  # tinte

    def update_warning_badge(self) -> None:
        """Muestra/oculta el badge de alerta en la esquina superior
        derecha del bloque segun model.reaction_warnings.

        Llamar despues de chemfx.analyze_flowsheet(fs) para refrescar
        todos los bloques. Es no-op si el bloque no tiene warnings.

        Color por severity (max del bloque):
          critical → rojo (#c41e3a)
          high     → naranja (#e57c00)
          medium   → amarillo (#f4b400)
          (sin warnings → badge oculto)
        """
        warns = getattr(self.model, "reaction_warnings", None) or []
        # Maximo de severidad en este bloque
        severity_order = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        max_sev = "low"
        max_score = -1
        for w in warns:
            if not isinstance(w, dict):
                continue
            sev = w.get("severity", "medium")
            score = severity_order.get(sev, 0)
            if score > max_score:
                max_score = score
                max_sev = sev
        # Crear el badge la primera vez
        if not hasattr(self, "_warning_badge") or self._warning_badge is None:
            from PySide6.QtWidgets import QGraphicsEllipseItem
            self._warning_badge = QGraphicsEllipseItem(-7, -7, 14, 14)
            self._warning_badge.setPen(QPen(QColor("#ffffff"), 1.5))
            self._warning_badge.setZValue(20)   # encima del bloque
            self._warning_badge.setAcceptedMouseButtons(Qt.NoButton)
            self.addToGroup(self._warning_badge)
        # Color + visibilidad segun warnings
        if not warns:
            self._warning_badge.setVisible(False)
            return
        color_map = {
            "critical": "#c41e3a",
            "high":     "#e57c00",
            "medium":   "#f4b400",
        }
        color = color_map.get(max_sev, "#9ca3af")
        self._warning_badge.setBrush(QBrush(QColor(color)))
        self._warning_badge.setVisible(True)
        # Posicion: esquina superior derecha del bloque
        try:
            w, h = pfd.block_dims(self.model.eq_type)
        except Exception:
            w, h = 80, 60
        # Local coords (BlockItem es un group con setPos absoluto al bloque)
        self._warning_badge.setPos(w - 4, 4)
        # Tooltip con el primer warning
        first_msg = ""
        for w_ in warns:
            if isinstance(w_, dict):
                first_msg = w_.get("message", "")
                if first_msg:
                    break
        if len(warns) > 1:
            first_msg += f"\n\n+ {len(warns) - 1} warning(s) más"
        self._warning_badge.setToolTip(first_msg)

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
        # Sync IsaGlyphItem (silueta ISA) — el halo da el verde/amarillo/rojo
        # pero la propia silueta también colorea el stroke en warning/error.
        if getattr(self, "_isa_item", None) is not None:
            # Si el bloque está seleccionado, conservar 'selected' visual.
            if self.isSelected():
                self._isa_item.set_state("selected")
            else:
                self._isa_item.set_state(self._isa_state_for_status(self._status))

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
        elif change == QGraphicsItem.ItemSelectedHasChanged:
            # sync visual del IsaGlyphItem con selección Qt
            if getattr(self, "_isa_item", None) is not None:
                if bool(value):
                    self._isa_item.set_state("selected")
                else:
                    self._isa_item.set_state(
                        self._isa_state_for_status(self._status))
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
        # Herramienta "connect" activa: el primer click sobre un bloque
        # inicia la conexión (sin necesidad del menú contextual).
        if (event.button() == Qt.LeftButton
            and self.editor is not None
            and getattr(self.editor, "_active_canvas_tool", "select") == "connect"):
            self.editor.start_connection(self.model.id)
            event.accept()
            return
        # snapshot del estado antes del drag (para undo)
        if (event.button() == Qt.LeftButton and self.editor is not None
            and self.editor._drag_before_snapshot is None):
            self.editor._drag_before_snapshot = self.editor.begin_action()
        super().mousePressEvent(event)

    def hoverEnterEvent(self, event):
        """Estado visual hover sobre el ISA glyph (no pisa selected)."""
        isa = getattr(self, "_isa_item", None)
        if isa is not None and not self.isSelected():
            isa.set_state("hover")
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        isa = getattr(self, "_isa_item", None)
        if isa is not None and not self.isSelected():
            isa.set_state(self._isa_state_for_status(self._status))
        super().hoverLeaveEvent(event)

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
        # Toggle de burbuja de diagnóstico para intercambiadores de calor
        is_hx = False
        try:
            import equipment_costs as _ec
            is_hx = _ec.EQUIPMENT_DATA.get(self.model.eq_type, {}).get(
                "categoria") == "Heat exchangers"
        except Exception:
            is_hx = False
        if is_hx:
            menu.addSeparator()
            on = bool(getattr(self.model, "bubble_visible", False))
            menu.addAction(
                QIcon(),
                "Ocultar diagnóstico HX" if on else "Mostrar diagnóstico HX",
                self._toggle_hx_bubble)
        menu.addSeparator()
        menu.addAction(ic_delete or QIcon(), "Borrar",
                       lambda: self.editor.delete_block(self.model.id))
        menu.exec(event.screenPos())
        event.accept()

    def _toggle_hx_bubble(self):
        self.model.bubble_visible = not bool(getattr(self.model, "bubble_visible", False))
        mgr = getattr(self.editor, "_hx_bubble_manager", None)
        if mgr is not None:
            mgr.refresh_all()


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
        # Sanear la polyline: quitar backtracks (tramos que van y vuelven
        # sobre la misma línea, p. ej. detours/lanes que dejan picos
        # colineales).  Preserva los extremos (puertos).
        pts = _simplify_orthogonal(pts)
        # Gap entre la punta de flecha y el NODO (puerto) del bloque.
        # _resolve_port ancla en el centro del dot del puerto; dejamos un
        # gap = radio del nodo (~4px) para que la punta toque el nodo sin
        # taparlo.  (Antes era 10px contra el bounding-box → la flecha
        # quedaba separada del nodo, que está inset respecto a la caja.)
        import math
        gap_dst = 4.0
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
            # existentes con el modelo (usado cuando un bloque conectado
            # se mueve y los handles deben seguir al puerto).
            # SKIP el handle que está siendo arrastrado por el user:
            # _press_pos != None significa drag activo. Si llamo setPos
            # ahí, Qt pierde el reference point del drag offset y el
            # próximo mouseMove computa delta desde el lugar incorrecto
            # → handle salta a la esquina superior izquierda (0,0) o
            # peor. Qt maneja su pos durante el drag; mejor no tocar.
            for h in self._handles:
                if isinstance(h, _EndpointHandle):
                    if getattr(h, "_press_pos", None) is not None:
                        continue   # drag activo — Qt lo maneja
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

        # Endpoints (start y end) — siempre si seleccionado o flotante.
        # PERO: solo si el modelo tiene info valida para esa punta.
        # Sin esto, un endpoint sin info (src=-1 AND start_xy=[]) crea
        # un handle que se queda en (0,0) — el clasico 'va a Jupiter'.
        s = self.model
        for role in ("start", "end"):
            if role == "start":
                has_info = (
                    (s.src != -1 and self.fs.blocks.get(s.src) is not None)
                    or (s.start_xy and len(s.start_xy) >= 2)
                )
            else:
                has_info = (
                    (s.dst != -1 and self.fs.blocks.get(s.dst) is not None)
                    or (s.end_xy and len(s.end_xy) >= 2)
                )
            if not has_info:
                continue   # no creas handle sin pos valida
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

    # ---- helpers de routing (cálculo de paths entre puertos de bloques) ----

    def _resolve_port(self, b, port_name, default_side):
        ports = ep.get_ports(b.eq_type)
        if port_name and port_name in ports:
            pname = port_name
            side, frac = ports[port_name]
        else:
            chosen = None
            for pn, (sd, fr) in ports.items():
                if sd == default_side:
                    chosen = (pn, sd, fr)
                    break
            if chosen is None:
                pname = next(iter(ports))
                side, frac = ports[pname]
            else:
                pname, side, frac = chosen
        # Anclar la flecha al CENTRO REAL del nodo dibujado.  Los dots se
        # renderizan con item.W/H (= BLOCK_DIMS del glyph ISA × 1.6), que
        # difieren de pfd.block_dims tras la migración a glyphs ISA — usar
        # block_dims acá dejaba la punta de la flecha separada del nodo.
        sc = self.scene()
        item = sc.block_items.get(b.id) if sc is not None else None
        if item is not None:
            ell = getattr(item, "port_items", {}).get(pname)
            if ell is not None:
                c = ell.sceneBoundingRect().center()
                return side, c.x(), c.y()
            w, h = getattr(item, "W", None), getattr(item, "H", None)
            if w is None or h is None:
                w, h = pfd.block_dims(b.eq_type)
        else:
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
        # NoAnchor en resize: mantiene fija la esquina sup-izq de la escena
        # cuando el viewport cambia de tamaño.  Así, al abrir el panel de
        # propiedades (dock a la derecha que come ~520px), el contenido del
        # canvas NO se desplaza a la izquierda (con AnchorViewCenter el
        # centro en píxeles se corría y "desordenaba" los bloques).
        self.setResizeAnchor(QGraphicsView.NoAnchor)
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

class FlowsheetMainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Diagrama de proceso — Qt edition")
        import ui_scaling
        ui_scaling.fit_to_screen(self, 1400, 820)

        # Registrar IBM Plex Sans / Mono para tags y especs (Aspen style).
        # Idempotente — si Qt no encuentra las TTFs, cae al sistema.
        pfd_fonts.load_all()

        # Cargar preferencias del usuario (tema, densidad, acento) desde
        # ~/.flowsheet_prefs.json — silencioso si no existe.
        try:
            import block_inspector as _bi
            _bi.load_prefs_from_disk()
        except Exception:
            pass

        self.fs = Flowsheet()
        self.scene = FlowsheetScene(self)
        self.view  = FlowsheetView(self.scene)

        # ── EditorTopbar (Parte B del rediseño NUEVA_UI) ────────────
        # Barra superior fina (52px) con identidad del proyecto, undo/
        # redo, status del solver y los dos botones primarios (Validar
        # DOF + Resolver).  Convive con las QToolBars legacy debajo,
        # que mantienen las acciones de file / examples / export /
        # análisis económico.
        from editor_chrome import (
            EditorTopbar, EditorPalette, EditorZoom, _Overlay,
            PALETTE_TO_EQ_TYPE,
        )
        central_wrap = QWidget(self)
        wrap_lay = QVBoxLayout(central_wrap)
        wrap_lay.setContentsMargins(0, 0, 0, 0)
        wrap_lay.setSpacing(0)
        self.editor_topbar = EditorTopbar(self)
        wrap_lay.addWidget(self.editor_topbar)
        wrap_lay.addWidget(self.view, 1)
        self.setCentralWidget(central_wrap)
        # guardar refs (overlays se construyen después de las acciones)
        self._palette_widget = EditorPalette(self.view.viewport())
        self._zoom_widget    = EditorZoom(self.view.viewport())
        self._chrome_overlay = _Overlay(self.view, self._palette_widget, self._zoom_widget)
        self._palette_to_eq_type = PALETTE_TO_EQ_TYPE
        # Bubble manager se inicializa al final del __init__ (necesita
        # stream_items_iter pero ese método ya está disponible).
        self._bubble_manager = None
        self._hx_bubble_manager = None

        # state de conexión pendiente (right-click + left-click)
        self._connecting_from: int = None
        # herramienta activa de la paleta (select/pan/connect/text)
        self._active_canvas_tool: str = "select"
        # visibilidad de corrientes auxiliares (toggle Ctrl+U, default ON)
        self._show_aux: bool = True

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
        self._build_menubar()
        self._wire_editor_chrome()
        # Por default ocultar los toolbars legacy: el EditorTopbar + el
        # menubar nuevo cubren todas las acciones.  Vista > Toolbars
        # legacy permite re-mostrarlos.
        self._set_legacy_toolbars_visible(False)
        # Ocultar también los docks legacy (biblioteca, propiedades,
        # tabla de corrientes, predictor de reactividad) — la nueva UI
        # los cubre con la paleta + Inspector + burbujas.  El usuario
        # puede re-mostrarlos desde el menú Vista si los necesita.
        for _dock_attr in ("lib_dock", "props_dock", "streams_dock",
                            "reactivity_dock"):
            _d = getattr(self, _dock_attr, None)
            if _d is not None:
                _d.hide()

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

        # ── Bubble manager (parche NUEVA_UI_P_SAD_3) ──
        # Crea las burbujas flotantes sobre streams cuyo
        # stream.bubble_visible es True.  Refresh inicial = sin
        # burbujas (los nuevos flowsheets arrancan con bubble_visible
        # False en todos los streams).
        try:
            from stream_bubbles import BubbleManager
            # Pasamos lambdas para que el manager siempre lea la fs y los
            # stream items actuales (resistente a swaps de fs por
            # action_new/open/undo).
            self._bubble_manager = BubbleManager(
                self.view,
                lambda: self.fs,
                self.stream_items_iter,
            )
            self._bubble_manager.refresh_all()
        except Exception as _e:
            print(f"[bubbles] no se pudo inicializar: {_e}")
            self._bubble_manager = None

        # ── HX diagnostic bubbles (parche HX riguroso) ──
        # Burbujas ancladas a bloques HX con block.bubble_visible=True.
        try:
            from hx_bubbles import HXBubbleManager
            import hx_edu as _hx_edu
            self._hx_bubble_manager = HXBubbleManager(
                self.view,
                lambda: self.fs,
                self.block_items_iter,
                lambda topic: _hx_edu.open_topic(topic, parent=self),
            )
            self._hx_bubble_manager.refresh_all()
        except Exception as _e:
            print(f"[hx-bubbles] no se pudo inicializar: {_e}")
            self._hx_bubble_manager = None

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
        # escapar conexión pendiente — Delete se cablea via QAction en el
        # menubar (Editar > Borrar selección) para evitar el "Ambiguous
        # shortcut overload" que ocurre al registrar Del dos veces.
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.cancel_connection)

    # ---------------------------------------------------
    # MENU BAR (Parte B — NUEVA_UI, reemplazo de toolbars)
    # ---------------------------------------------------

    def _build_menubar(self):
        """Menu bar que reusa todas las acciones del toolbar legacy.
        Una vez construido, las QToolBars se ocultan por default."""
        mb = self.menuBar()
        # estilo plano consistente con el resto del editor
        try:
            from block_inspector import TOK as _T
            mb.setStyleSheet(
                f"QMenuBar {{ background:{_T['bg_elev']}; color:{_T['ink']}; "
                f"border-bottom:1px solid {_T['line']}; }} "
                f"QMenuBar::item {{ padding:5px 10px; background:transparent; }} "
                f"QMenuBar::item:selected {{ background:{_T['bg_mute']}; "
                f"color:{_T['accent_deep']}; border-radius:4px; }} "
                f"QMenu {{ background:{_T['bg_elev']}; color:{_T['ink']}; "
                f"border:1px solid {_T['line']}; padding:4px 0; }} "
                f"QMenu::item {{ padding:5px 22px 5px 14px; }} "
                f"QMenu::item:selected {{ background:{_T['accent_tint']}; "
                f"color:{_T['accent_deep']}; }}"
            )
        except Exception:
            pass

        _mk = getattr(self, "_mk_icon", None) or (lambda *a, **k: None)
        ic_color = getattr(self, "_icon_color", "#3a3a3a")

        def _ac(label, slot, shortcut=None, icon_id=None):
            act = QAction(label, self)
            act.triggered.connect(slot)
            if shortcut: act.setShortcut(shortcut)
            if icon_id and _mk:
                ic = _mk(icon_id, color=ic_color, size=16)
                if ic is not None:
                    act.setIcon(ic)
            return act

        # ── Archivo ──
        m_file = mb.addMenu("&Archivo")
        m_file.addAction(_ac("&Nuevo",      self.action_new,
                               QKeySequence.New,  "file-new"))
        m_file.addAction(_ac("&Abrir…",     self.action_open,
                               QKeySequence.Open, "file-open"))
        m_file.addAction(_ac("&Guardar…",   self.action_save,
                               QKeySequence.Save, "file-save"))
        m_file.addSeparator()
        # Ejemplos — submenu agrupado por categoría
        m_examples = m_file.addMenu("&Ejemplos")
        for _cat, _items in EXAMPLE_CATEGORIES:
            _sub = m_examples.addMenu(_cat)
            for _key, _label in _items:
                _sub.addAction(_label, lambda k=_key: self.action_load_example(k))

        m_file.addSeparator()
        # Exportar — submenu
        m_export = m_file.addMenu("E&xportar")
        m_export.addAction(_ac("PDF…",          self.action_export_pdf,
                                  "Ctrl+E", "file-print"))
        m_export.addAction(_ac("SVG (vectorial)…", self.action_export_svg,
                                  "Ctrl+Shift+E", "file-export"))
        m_export.addAction(_ac("PNG (alta resolución)…", self.action_export_png,
                                  None, "file-export"))
        m_file.addSeparator()
        m_file.addAction(_ac("Salir", self.close, QKeySequence.Quit))

        # ── Editar ──
        m_edit = mb.addMenu("&Editar")
        if hasattr(self, "undo_action"):
            m_edit.addAction(self.undo_action)
        if hasattr(self, "redo_action"):
            m_edit.addAction(self.redo_action)
        m_edit.addSeparator()
        m_edit.addAction(_ac("&Borrar selección", self.action_delete,
                              QKeySequence.Delete, "edit-delete"))

        # ── Vista ──
        m_view = mb.addMenu("&Vista")
        m_view.addAction(_ac("Zoom −", self.view.zoom_out,    "Ctrl+-",  "zoom-out"))
        m_view.addAction(_ac("100 %",  self.view.zoom_reset,  "Ctrl+0",  "zoom-100"))
        m_view.addAction(_ac("Zoom +", self.view.zoom_in,     "Ctrl++",  "zoom-in"))
        m_view.addAction(_ac("Ajustar a vista", self.view.zoom_fit,
                              "F",  "zoom-fit"))
        m_view.addSeparator()
        # Marco PFD toggle — reusa el _paper_action si existe
        if hasattr(self, "_paper_action"):
            m_view.addAction(self._paper_action)
        else:
            m_view.addAction(_ac("Marco PFD", self.action_toggle_paper, "Ctrl+M"))
        # Animación
        anim_act = QAction("Animación de flujo", self)
        anim_act.setCheckable(True); anim_act.setChecked(True)
        anim_act.triggered.connect(self.toggle_animation)
        m_view.addAction(anim_act)
        m_view.addSeparator()
        # Paleta vertical de equipos (toggle visibilidad)
        self._palette_visibility_action = QAction("Paleta de equipos", self)
        self._palette_visibility_action.setCheckable(True)
        self._palette_visibility_action.setChecked(True)
        self._palette_visibility_action.setShortcut("Ctrl+P")
        self._palette_visibility_action.triggered.connect(
            self._toggle_palette_visibility
        )
        m_view.addAction(self._palette_visibility_action)
        # Corrientes auxiliares (cooling water / steam / aire / combustible /
        # chimenea, etc.) — toggle visibilidad.  Default ON.
        self._aux_visibility_action = QAction("Mostrar corrientes auxiliares", self)
        self._aux_visibility_action.setCheckable(True)
        self._aux_visibility_action.setChecked(getattr(self, "_show_aux", True))
        self._aux_visibility_action.setShortcut("Ctrl+U")
        self._aux_visibility_action.triggered.connect(self._toggle_aux_visibility)
        m_view.addAction(self._aux_visibility_action)
        # Inspector dock (slide-out de la nueva UI)
        if hasattr(self, "_inspector_dock") and self._inspector_dock is not None:
            m_view.addAction(self._inspector_dock.toggleViewAction())
        # Docks legacy (biblioteca, propiedades, tabla, predictor de
        # reactividad) — agrupados en un sub-menú "Docks legacy" para
        # mantenerlos accesibles sin ensuciar el menú principal.
        m_legacy = m_view.addMenu("Docks legacy")
        for attr, label in (
            ("lib_dock",        "Biblioteca de equipos (vieja)"),
            ("props_dock",      "Propiedades (viejo)"),
            ("streams_dock",    "Tabla de corrientes"),
            ("reactivity_dock", "Predictor de reactividad"),
        ):
            d = getattr(self, attr, None)
            if d is None:
                continue
            # la tabla de corrientes usa la acción robusta del toolbar
            if attr == "streams_dock" and getattr(self, "_streams_table_action", None):
                m_legacy.addAction(self._streams_table_action)
                continue
            act = d.toggleViewAction()
            act.setText(label)
            m_legacy.addAction(act)
        m_view.addSeparator()
        # ── Sistema de unidades global (afecta UI + exportación) ──
        m_units = m_view.addMenu("&Unidades")
        self._unit_system_group = QActionGroup(self)
        self._unit_system_group.setExclusive(True)
        self._unit_system_actions = {}
        _cur_sys = funits.current_system()
        for _sysname in funits.UNIT_SYSTEMS_ORDER:
            _u = funits.UNIT_SYSTEMS[_sysname]
            _act = QAction(
                f"{_sysname}   ({_u['flow']} · {_u['temp']} · {_u['pressure']} · {_u['energy']})",
                self)
            _act.setCheckable(True)
            _act.setChecked(_sysname == _cur_sys)
            _act.triggered.connect(lambda _checked=False, n=_sysname: self._set_unit_system(n))
            self._unit_system_group.addAction(_act)
            self._unit_system_actions[_sysname] = _act
            m_units.addAction(_act)
        m_view.addSeparator()
        # Preferencias (tema, densidad, acento)
        m_view.addAction(_ac("&Preferencias…", self._open_preferences, "Ctrl+,"))
        m_view.addSeparator()
        # Toggle de toolbars legacy
        self._legacy_tb_action = QAction("Toolbars legacy", self)
        self._legacy_tb_action.setCheckable(True)
        self._legacy_tb_action.setChecked(False)
        self._legacy_tb_action.triggered.connect(
            lambda v: self._set_legacy_toolbars_visible(v))
        m_view.addAction(self._legacy_tb_action)

        # ── Simulación ──
        m_sim = mb.addMenu("&Simulación")
        m_sim.addAction(_ac("Validar &DOF", self.action_dof,
                              None, "act-dof"))
        m_sim.addAction(_ac("&Resolver balances", self.action_solve,
                              "F5", "sim-run"))
        m_sim.addAction(_ac("&Calcular costos",  self.action_compute,
                              "F9", "sim-refresh"))
        m_sim.addSeparator()
        m_sim.addAction(_ac("Setpoints…",  self.action_setpoints,
                              None, "act-setpoint"))
        m_sim.addAction(_ac("Auto-size S", self.action_autosize,
                              None, "act-sizing"))
        m_sim.addAction(_ac("OPEX extras…", self.action_opex_extras,
                              None, "act-money"))
        m_sim.addSeparator()
        m_sim.addAction(_ac("Perfil económico…", self.action_econ_profile,
                              None, "act-money"))
        m_sim.addAction(_ac("Análisis económico →", self.action_launch_analysis,
                              None, "an-case-study"))
        m_sim.addAction(_ac("Exportar a Excel…", self.action_export_xlsx,
                              None, "act-money"))

    def _set_legacy_toolbars_visible(self, visible: bool):
        """Muestra/oculta las QToolBars legacy.  Usado en __init__ para
        esconderlas por default (el EditorTopbar + menubar cubren todo)
        y desde el menú Vista > Toolbars legacy para re-mostrarlas."""
        for tb in self.findChildren(QToolBar):
            tb.setVisible(bool(visible))

    def _set_unit_system(self, name):
        """Aplica el sistema de unidades global (Vista > Unidades) y refresca
        todo lo que muestra magnitudes: tabla de corrientes, labels del canvas,
        burbujas, panel de propiedades y footer.  Afecta también la exportación
        (que lee funits.active() al exportar)."""
        funits.set_system(name)
        # sincronizar el segmented control de flujo del dock
        if getattr(self, "streams_dock", None) is not None:
            try:
                self.streams_dock.select_flow_unit(funits.active_unit("flow"))
            except Exception:
                pass
        # re-render labels de corrientes (caudal) en el canvas
        if hasattr(self, "scene") and hasattr(self.scene, "stream_items"):
            for _sid, _item in self.scene.stream_items.items():
                if hasattr(_item, "update_path"):
                    try:
                        _item.update_path()
                    except Exception:
                        pass
        # burbujas de corriente / HX
        for _mgr in ("_bubble_manager", "_hx_bubble_manager"):
            m = getattr(self, _mgr, None)
            if m is not None:
                try:
                    m.refresh_all()
                except Exception:
                    pass
        # panel de propiedades (re-disparar la selección actual)
        try:
            self._on_selection_changed()
        except Exception:
            pass
        # marcar el preset activo en el menú
        cur = funits.current_system()
        for sysname, act in getattr(self, "_unit_system_actions", {}).items():
            act.setChecked(sysname == cur)
        self._update_status()

    def _open_preferences(self):
        """Vista > Preferencias…  Abre el diálogo de tema/densidad/acento.
        Los cambios se aplican en vivo al Inspector (vía PrefsBus signal)
        y se persisten en ~/.flowsheet_prefs.json."""
        try:
            from block_inspector import PreferencesDialog
        except Exception as e:
            QMessageBox.warning(self, "No disponible",
                                f"Preferencias no disponibles: {e}")
            return
        dlg = PreferencesDialog(self)
        dlg.exec()

    def _toggle_palette_visibility(self, visible: bool):
        """Vista > Paleta de equipos (Ctrl+P): muestra/oculta la
        paleta vertical flotante sin tocar zoom o demás overlays."""
        if hasattr(self, "_palette_widget") and self._palette_widget is not None:
            self._palette_widget.setVisible(bool(visible))

    def _toggle_aux_visibility(self, show: bool):
        """Vista > Mostrar corrientes auxiliares (Ctrl+U): muestra/oculta
        los bloques y streams auto_aux (utility/ambiente).  Si todavía no
        hay ninguna corriente auto_aux (p.ej. en un ejemplo o archivo
        cargado), el click las materializa para los intercambiadores de
        calor que no tengan utility y las muestra."""
        has_aux = any(getattr(s, "auto_aux", False)
                      for s in self.fs.streams.values())
        if not has_aux:
            n = self._ensure_hx_auxiliaries()
            if n:
                self._show_aux = True
                if getattr(self, "_aux_visibility_action", None) is not None:
                    self._aux_visibility_action.setChecked(True)
                self._apply_aux_visibility()
                self._update_status()
                return
        self._show_aux = bool(show)
        self._apply_aux_visibility()

    def _toggle_streams_table(self, *args):
        """Muestra/oculta el dock de la tabla de corrientes de forma robusta
        (lo trae al frente y le asigna una altura visible al mostrarlo)."""
        d = getattr(self, "streams_dock", None)
        if d is None:
            return
        if d.isVisible():
            d.hide()
        else:
            if d.isFloating():
                d.setFloating(False)
            d.show()
            d.raise_()
            try:
                from PySide6.QtCore import Qt as _Qt
                self.resizeDocks([d], [260], _Qt.Vertical)
            except Exception:
                pass
            try:
                d.refresh()
            except Exception:
                pass

    def _ensure_hx_auxiliaries(self):
        """Materializa las corrientes de servicio (cooling water / steam) de
        los intercambiadores de calor que aún no tengan ninguna corriente
        utility conectada, las dimensiona desde el duty (solve) y redibuja.
        Devuelve cuántos HX recibieron auxiliares."""
        import equipment_auxiliaries as _aux
        import equipment_costs as _ec
        import flowsheet_solver as _fsolv
        # Resolver PRIMERO (duties + flujos de proceso): añadir corrientes
        # nuevas antes del solve inicial puede interferir con la resolución.
        try:
            _fsolv.solve(self.fs)
        except Exception:
            pass
        created = 0
        for b in list(self.fs.blocks.values()):
            if _ec.EQUIPMENT_DATA.get(b.eq_type, {}).get("categoria") != "Heat exchangers":
                continue
            # no duplicar: saltar HX que ya tienen una corriente utility
            # (manual o auto) conectada
            if any((s.src == b.id or s.dst == b.id) and (s.role or "") == "utility"
                   for s in self.fs.streams.values()):
                continue
            if _aux.instantiate_auxiliaries(self.fs, b):
                created += 1
        if created:
            # dimensionar las corrientes nuevas desde el duty + redibujar
            try:
                _fsolv.solve(self.fs)
            except Exception:
                pass
            self._rebuild_scene()
        return created

    def _apply_aux_visibility(self):
        """Aplica el estado actual de _show_aux a los items auto_aux del
        canvas.  Llamar tras crear aux y tras reconstruir la escena."""
        show = getattr(self, "_show_aux", True)
        for bid, item in self.block_items_iter():
            if getattr(item.model, "auto_aux", False):
                item.setVisible(show)
        for sid, item in self.stream_items_iter():
            if getattr(item.model, "auto_aux", False):
                item.setVisible(show)

    # ---------------------------------------------------
    # EDITOR CHROME WIRING (Parte B — NUEVA_UI)
    # ---------------------------------------------------

    def _wire_editor_chrome(self):
        """Conecta las señales del EditorTopbar / EditorPalette /
        EditorZoom a las acciones existentes de la ventana."""
        tb = self.editor_topbar
        # Undo/redo — reutilizar el undo_stack
        tb.undoRequested.connect(self.undo_stack.undo)
        tb.redoRequested.connect(self.undo_stack.redo)
        # Estado inicial de undo/redo y observador del stack.
        # Guard contra RuntimeError al cerrar la app: cuando QUndoStack
        # se destruye el signal puede dispararse una vez más con el
        # objeto C++ ya muerto.
        def _refresh_undo_buttons():
            try:
                tb.set_undo_enabled(self.undo_stack.canUndo(),
                                    self.undo_stack.canRedo())
            except RuntimeError:
                pass   # objeto C++ ya destruido (shutdown)
        self.undo_stack.canUndoChanged.connect(lambda _: _refresh_undo_buttons())
        self.undo_stack.canRedoChanged.connect(lambda _: _refresh_undo_buttons())
        _refresh_undo_buttons()
        # Grid toggle — refresh paper grid
        tb.gridToggled.connect(self._on_topbar_grid_toggle)
        # Auto-arrange (action existente si la hay; si no, no-op visual)
        if hasattr(self, "action_auto_arrange"):
            tb.autoArrangeRequested.connect(self.action_auto_arrange)
        elif hasattr(self, "action_autoarrange"):
            tb.autoArrangeRequested.connect(self.action_autoarrange)
        # Validar DOF + Resolver
        tb.validateRequested.connect(self.action_dof)
        tb.solveRequested.connect(self.action_solve)
        # Nombre del proyecto inicial
        tb.set_project(self._current_project_name(), "sin guardar")

        # ── Palette: tool/block ─────────────────────────────────
        pal = self._palette_widget
        pal.blockRequested.connect(self._on_palette_block_requested)
        # blockTypeRequested viene del popup de variantes — eq_type directo
        pal.blockTypeRequested.connect(self._on_palette_eq_type_requested)
        # Tools: el primer slice solo activa el modo de selección/pan/connect.
        pal.toolSelected.connect(self._on_palette_tool_selected)
        pal.moreRequested.connect(self._on_palette_more_requested)
        # Corrientes flotantes (masa / energía) desde la paleta nueva.
        pal.streamRequested.connect(self._add_floating_stream)

        # ── Zoom overlay ────────────────────────────────────────
        zm = self._zoom_widget
        zm.zoomInRequested.connect(self.view.zoom_in)
        zm.zoomOutRequested.connect(self.view.zoom_out)
        zm.zoomResetRequested.connect(self.view.zoom_reset)
        zm.zoomFitRequested.connect(self.view.zoom_fit)
        # observador de zoom para actualizar el %
        if hasattr(self.view, "zoomChanged"):
            self.view.zoomChanged.connect(zm.set_zoom)
        else:
            # Fallback: refrescar via timer cada 200ms (sutil)
            from PySide6.QtCore import QTimer
            self._zoom_refresh_timer = QTimer(self)
            self._zoom_refresh_timer.setInterval(250)
            self._zoom_refresh_timer.timeout.connect(self._refresh_zoom_chip)
            self._zoom_refresh_timer.start()

    def _refresh_zoom_chip(self):
        try:
            f = self.view.transform().m11()
            self._zoom_widget.set_zoom(f)
        except Exception:
            pass

    def _current_project_name(self) -> str:
        # Sin path persistido aún: usar el window title como fallback
        try:
            t = self.windowTitle()
        except Exception:
            t = ""
        return t.split("—")[0].strip() or "(sin nombre)"

    def _on_topbar_grid_toggle(self):
        """Toggle de visibilidad del marco PFD (cuando existe)."""
        if hasattr(self, "_paper_action"):
            self._paper_action.trigger()

    def _on_palette_block_requested(self, palette_id: str):
        """Crear un bloque del tipo seleccionado en la paleta (default
        canónico). Usado por drag-from-palette."""
        eq_type = self._palette_to_eq_type.get(palette_id)
        if eq_type is None:
            return
        self._add_block_of_type(eq_type)

    def _on_palette_eq_type_requested(self, eq_type: str):
        """Crear un bloque del eq_type EXACTO elegido en el popup de
        variantes o en el catálogo completo (+ botón)."""
        if not eq_type:
            return
        self._add_block_of_type(eq_type)

    def _on_palette_tool_selected(self, tool_id: str):
        """Activar herramienta de manipulación del canvas."""
        self._active_canvas_tool = tool_id
        # cambiar de herramienta cancela cualquier conexión a medio hacer
        if tool_id != "connect":
            self.cancel_connection()
        v = self.view
        if tool_id == "pan":
            v.setDragMode(QGraphicsView.ScrollHandDrag)
        elif tool_id == "select":
            v.setDragMode(QGraphicsView.RubberBandDrag)
        elif tool_id == "connect":
            # Si existe modo de conexión nativo, activarlo.  Si no, dar
            # un hint visual (cambio de cursor) y dejar la UX manual:
            # right-click + left-click.
            v.setDragMode(QGraphicsView.NoDrag)
            v.viewport().setCursor(Qt.CrossCursor)
            return
        elif tool_id == "text":
            v.setDragMode(QGraphicsView.NoDrag)
            v.viewport().setCursor(Qt.IBeamCursor)
            return
        v.viewport().setCursor(Qt.ArrowCursor)

    def _on_palette_more_requested(self):
        """Mostrar el dock de biblioteca para acceder a tipos secundarios."""
        if hasattr(self, "lib_dock"):
            self.lib_dock.show()
            self.lib_dock.raise_()

    def update_solver_chip(self, state: str, iter_: int = 0, dt: float = 0.0):
        """API pública — el solver llama acá tras finalizar para
        actualizar el chip del topbar."""
        if hasattr(self, "editor_topbar"):
            self.editor_topbar.set_solver_state(state, iter_, dt)

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
        def make_loader(key):
            return lambda: self.action_load_example(key)
        # Ícono compartido para todos los ejemplos (equipo genérico)
        _ic_ex = _mk("act-examples", color=_ICON_COLOR, size=18) or QIcon()

        # Mismo catálogo agrupado por categoría que el menubar (single
        # source of truth: EXAMPLE_CATEGORIES).
        for _cat, _items in EXAMPLE_CATEGORIES:
            _sub = examples_menu.addMenu(_cat)
            for _key, _label in _items:
                _sub.addAction(_ic_ex, _label, make_loader(_key))
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
        # toggle del dock de tabla de corrientes — acción propia (robusta):
        # toggleViewAction() a veces re-muestra el dock con altura 0 o detrás
        # del layout; _toggle_streams_table() lo muestra, lo trae al frente y
        # le da una altura visible.
        if hasattr(self, "streams_dock") and self.streams_dock is not None:
            act = QAction("Tabla de corrientes", self)
            act.setCheckable(True)
            act.setChecked(self.streams_dock.isVisible())
            act.setShortcut("Ctrl+T")
            act.setIcon(_mk("wb-table", color=_ICON_COLOR, size=20))
            act.triggered.connect(self._toggle_streams_table)
            tb.addAction(act)
            self._streams_table_action = act
            # mantener el check sincronizado si el dock cambia por otra vía
            try:
                self.streams_dock.visibilityChanged.connect(
                    lambda vis: self._streams_table_action.setChecked(bool(vis)))
            except Exception:
                pass
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
        add_btn("Exportar a Excel…", self.action_export_xlsx, "act-money")
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
        self.lib_dock = dock   # ref para toggle desde Vista

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

        # ---- Diagrama McCabe-Thiele (oculto hasta seleccionar una columna) ----
        # Recomienda la columna (etapas, etapa de feed, R_min) desde el modelo.
        self.mccabe_panel = QWidget()
        mcc_lay = QVBoxLayout(self.mccabe_panel)
        mcc_lay.setContentsMargins(0, 4, 0, 0)
        self._mccabe_caption = QLabel("")
        self._mccabe_caption.setWordWrap(True)
        self._mccabe_caption.setStyleSheet("font-size: 8pt;")
        mcc_lay.addWidget(self._mccabe_caption)
        if _MPL_OK:
            self._mccabe_fig = Figure(figsize=(3.4, 3.2), dpi=90)
            self._mccabe_canvas = _MplCanvas(self._mccabe_fig)
            self._mccabe_canvas.setMinimumHeight(260)
            mcc_lay.addWidget(self._mccabe_canvas)
        else:
            mcc_lay.addWidget(QLabel(
                "matplotlib no disponible — McCabe-Thiele no se grafica."))
            self._mccabe_canvas = None
        self.mccabe_panel.setVisible(False)
        layout.addWidget(self.mccabe_panel)

        # ---- Perfil tray-by-tray (oculto hasta seleccionar una columna) ----
        # 9º método del widget: T y composición por etapa.  Fuente:
        # Wang-Henke MESH si existe, fallback al McCabe-Thiele (CMO binario).
        # NUNCA etiqueta uno como el otro: el badge es explícito.
        self.profile_panel = QWidget()
        prof_lay = QVBoxLayout(self.profile_panel)
        prof_lay.setContentsMargins(0, 4, 0, 0)
        self._profile_caption = QLabel("")
        self._profile_caption.setWordWrap(True)
        self._profile_caption.setStyleSheet("font-size: 8pt;")
        prof_lay.addWidget(self._profile_caption)
        if _MPL_OK:
            self._profile_fig = Figure(figsize=(3.4, 2.8), dpi=90)
            self._profile_canvas = _MplCanvas(self._profile_fig)
            self._profile_canvas.setMinimumHeight(240)
            prof_lay.addWidget(self._profile_canvas)
        else:
            prof_lay.addWidget(QLabel(
                "matplotlib no disponible — perfil no se grafica."))
            self._profile_canvas = None
        self.profile_panel.setVisible(False)
        layout.addWidget(self.profile_panel)

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
        self.props_dock = dock   # ref para toggle desde Vista

        # ─── Dock de Reactividad (Fase 8 — predictor de reacciones) ───
        # Aparece al lado del dock de propiedades. Si chemfx no esta
        # instalado o falta alguna dep, simplemente no se crea (no rompe
        # la UI principal).
        try:
            from chemfx.ui.reactivity_dock_qt import ReactivityDock
            self.reactivity_dock = ReactivityDock(self, editor=self)
            self.addDockWidget(Qt.RightDockWidgetArea, self.reactivity_dock)
            # Tab-ifica si ya hay otro dock derecho
            self.tabifyDockWidget(dock, self.reactivity_dock)
            # Por default mostramos el dock de propiedades primero
            dock.raise_()
        except Exception:
            # chemfx no disponible o PySide6 incompatible — silenciar.
            self.reactivity_dock = None

    def _build_streams_dock(self):
        """Tabla de corrientes hi-fi (rediseño parche P2).  Custom
        layout con NumberPill + composition strip + mass bar + T/P
        stacked.  Vive en streams_table.py."""
        from streams_table import StreamsTableDock as _NewStreamsTableDock
        self.streams_dock = _NewStreamsTableDock(self, self)
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
            # chip del EditorTopbar
            if hasattr(self, "editor_topbar"):
                self.editor_topbar.set_solver_state("stale")

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
        # Burbujas: limpiar todas (no hay streams)
        if getattr(self, "_bubble_manager", None) is not None:
            self._bubble_manager.refresh_all()
        if getattr(self, "_hx_bubble_manager", None) is not None:
            self._hx_bubble_manager.refresh_all()

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
        # Zoom 100% nativo + centrar la vista en el bbox de los bloques
        # (el user prefiere ver el tamaño real, centrado, sin scroll).
        self.view.zoom_reset()
        self._center_view_on_blocks()
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
        import examples_registry as _reg
        # Fase 2: el ejemplo se carga desde data/examples/<clave>.json vía el
        # registry (data-driven), en vez de correr un builder imperativo.
        # La metadata del marco PFD (nombre/área/código) viene del manifest.
        meta = _reg.get_metadata(key)
        if meta is None:
            return
        self.fs = _reg.load_example(key)
        title  = meta["nombre"]
        area   = meta["capa"]
        dwg_no = meta["codigo_pfd"]
        # apply_example_hydraulics se indexa por el nombre del builder
        # (_example_*), que el manifest conserva como string-key de
        # hydraulic_defaults.EXAMPLE_PRESETS.
        builder_key = meta["builder"]
        try:
            from hydraulic_defaults import apply_example_hydraulics
            apply_example_hydraulics(self.fs, builder_key)
        except Exception:
            pass
        # Los JSON traen las posiciones legacy (silueta 130x60); las siluetas
        # ISA nuevas son más grandes y quedan apachurradas → expandir.
        self._expand_block_spacing(factor=1.7)
        self._last_overall_status = None
        self._dirty_after_solve = True
        self._rebuild_scene()

        # Auto-mostrar el marco PFD con los datos del ejemplo
        self.scene.set_paper_visible(False)
        self.scene.paper_frame = None
        self.scene.set_paper_visible(True, project_title=title,
                                       area=area, drawing_no=dwg_no)
        if hasattr(self, "_paper_action"):
            self._paper_action.setChecked(True)

        self.view.zoom_reset()
        self._center_view_on_blocks()
        self._update_status()
        self.end_action(f"Cargar ejemplo: {key}", before)

    # ---------------------------------------------------
    # ACCIONES — Otros
    # ---------------------------------------------------

    def _expand_block_spacing(self, factor: float = 1.7):
        """Multiplica las coordenadas (x, y) de TODOS los bloques por
        un factor + snap a la grilla.  Usado al cargar ejemplos legacy
        para que las nuevas siluetas ISA (más grandes que el rect
        130x60 viejo) no queden apachurradas y los streams tengan
        longitud cómoda."""
        if not self.fs.blocks:
            return
        # Anclar el escalado al bloque más arriba-izquierda para no
        # desparramar el diagrama lejos del origen.
        min_x = min(b.x for b in self.fs.blocks.values())
        min_y = min(b.y for b in self.fs.blocks.values())
        for b in self.fs.blocks.values():
            b.x = min_x + (b.x - min_x) * factor
            b.y = min_y + (b.y - min_y) * factor
            # snap a la grilla del modelo
            b.x = round(b.x / GRID_STEP) * GRID_STEP
            b.y = round(b.y / GRID_STEP) * GRID_STEP

    def _center_view_on_blocks(self):
        """Centra la vista en el centroide del bbox de los bloques.
        No cambia el zoom — solo el centro."""
        if not self.fs.blocks:
            return
        try:
            xs = [b.x for b in self.fs.blocks.values()]
            ys = [b.y for b in self.fs.blocks.values()]
            # Centro del bbox (no del centroide — más estable cuando
            # hay un bloque outlier muy lejos)
            cx = (min(xs) + max(xs)) / 2.0
            cy = (min(ys) + max(ys)) / 2.0
            # Sumar la mitad de W/H típico para centrar el ÁREA visible,
            # no la esquina top-left de los bloques
            cx += BLOCK_W / 2.0
            cy += BLOCK_H / 2.0
            from PySide6.QtCore import QPointF
            self.view.centerOn(QPointF(cx, cy))
        except Exception:
            pass

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
        # Actualizar el chip del EditorTopbar (Parte B)
        chip_state = {
            "ok":      "converged",
            "warning": "warning",
            "error":   "failed",
        }.get(result.overall_status, "idle")
        n_iter = getattr(result, "iter_count", 0) or 0
        dt = getattr(result, "elapsed_s", 0.0) or 0.0
        self.update_solver_chip(chip_state, n_iter, dt)
        # Refrescar burbujas con los valores resueltos
        if self._bubble_manager is not None:
            self._bubble_manager.refresh_all()
        if self._hx_bubble_manager is not None:
            self._hx_bubble_manager.refresh_all()
        # auditar conexiones semánticas
        sem_issues = fval.validate_all_streams(self.fs)
        # mostrar resumen en el diálogo visual de resultado
        from solver_report import show_solver_report
        show_solver_report(result, sem_issues, parent=self)

        # ─── Hook automático: predictor de reacciones (Fase 8) ───
        # Despues de Solve, correr el analizador pasivo. NO afecta el
        # balance (es solo anotacion). Si chemfx no esta disponible o
        # falla, silencioso.
        try:
            import chemfx
            chemfx.analyze_flowsheet(self.fs)
            # Refrescar badge visual de warning en cada bloque del canvas
            for _bid, _bitem in self.block_items_iter():
                try:
                    _bitem.update_warning_badge()
                except Exception:
                    pass
            if getattr(self, "reactivity_dock", None) is not None:
                self.reactivity_dock.refresh_from_flowsheet(self.fs)
                # Si hay warnings criticos, traer el dock al frente
                n_crit = sum(
                    1
                    for b in self.fs.blocks.values()
                    for w in (getattr(b, "reaction_warnings", []) or [])
                    if isinstance(w, dict) and w.get("severity") == "critical"
                )
                if n_crit > 0:
                    self.reactivity_dock.raise_()
        except Exception as e:
            # No bloquear el solve por un error en el predictor.
            import logging
            logging.getLogger(__name__).debug(
                f"predictor post-solve fallo: {e}")

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
        """Abre el panel económico IN-PROCESS: corre simulate() sobre el
        flowsheet actual y muestra NPV/IRR/Payback/ROI/COM ahí mismo, sin
        xlsx temporal ni subproceso.  El diagrama queda intacto.

        Reemplaza el bridge legacy (xlsx + ana_qt subprocess), preservado
        en _action_launch_analysis_xlsx_legacy pero ya NO invocado (su
        retiro es un commit posterior)."""
        if not self.fs.blocks:
            ans = QMessageBox.question(
                self, "Sin proceso modelado",
                "El diagrama está vacío. ¿Abrir el análisis económico igual?",
            )
            if ans != QMessageBox.Yes:
                return
        try:
            from economics_panel import EconomicsPanel
            EconomicsPanel(self.fs, self).exec()
        except Exception as e:
            QMessageBox.critical(self, "Falló el panel económico",
                                  f"{type(e).__name__}: {e}")

    def action_export_xlsx(self):
        """Exporta el proyecto a .xlsx vía el write_project_xlsx existente
        (Save explícito, desacoplado del panel económico)."""
        if not self.fs.blocks:
            QMessageBox.information(self, "Exportar a Excel",
                                    "El diagrama está vacío.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar proyecto a Excel", "", "Excel (*.xlsx)")
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"
        try:
            feeds    = [s for s in self.fs.streams.values() if s.role == "feed"]
            products = [s for s in self.fs.streams.values() if s.role == "product"]
            import capex as _capex
            isbl = _capex.compute_fci(self.fs).get("sum_cbm")
            isbl_musd = (isbl / 1e6) if isbl else None
            fexp.write_project_xlsx(path, self.fs, isbl_musd, feeds, products)
        except Exception as e:
            QMessageBox.critical(self, "Falló la exportación",
                                  f"{type(e).__name__}: {e}")
            return
        self.status.showMessage(f"Exportado: {path}", 6000)

    def _action_launch_analysis_xlsx_legacy(self):
        """[LEGACY — ya NO invocado desde el botón] Genera xlsx temporal y
        lanza ana_qt.py como subprocess.  Preservado para retiro en commit
        posterior; el panel in-process lo reemplaza."""
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
        """Abre BlockInspectorDock (nuevo) y refresca el render al guardar.

        El dock es slide-out, no modal, y se reusa para distintos bloques.
        Las opciones avanzadas/nicho (custom reactions, FUG columna,
        separadores mecánicos, batch, flash, dryer, etc.) viven aún en
        BlockEditDialog y se acceden via el link "Opciones avanzadas…"
        del propio panel.
        """
        # construcción perezosa
        if not hasattr(self, "_inspector_dock") or self._inspector_dock is None:
            from block_inspector import BlockInspectorDock
            self._inspector_dock = BlockInspectorDock(self)
            self.addDockWidget(Qt.RightDockWidgetArea, self._inspector_dock)

        def _on_save():
            """Callback tras 'Guardar cambios' — refresca canvas + solver hooks."""
            before = self.begin_action()
            self._mark_dirty()
            item = self.scene.block_items.get(block.id)
            if item is not None:
                self.scene.removeItem(item)
                del self.scene.block_items[block.id]
                self._render_block(block)
                new_item = self.scene.block_items.get(block.id)
                if new_item is not None:
                    new_item._update_tooltip()
                self.refresh_streams_of(block.id)
            self._refresh_port_colors()
            self._update_status()
            self._on_selection_changed()
            self.end_action(f"Editar {block.name}", before)

        def _open_advanced(b):
            """Fallback: opciones avanzadas via el dialog legacy."""
            dlg = BlockEditDialog(self, b)
            if dlg.exec() == QDialog.Accepted:
                before = self.begin_action()
                dlg.apply_to_model()
                self._mark_dirty()
                item = self.scene.block_items.get(b.id)
                if item is not None:
                    self.scene.removeItem(item)
                    del self.scene.block_items[b.id]
                    self._render_block(b)
                    new_item = self.scene.block_items.get(b.id)
                    if new_item is not None:
                        new_item._update_tooltip()
                    self.refresh_streams_of(b.id)
                self._refresh_port_colors()
                self._update_status()
                self._on_selection_changed()
                self.end_action(f"Editar {b.name} (avanzado)", before)
                # repopular el inspector con los valores nuevos
                self._inspector_dock.show_for(b, self.fs,
                                              on_save=_on_save,
                                              open_advanced=_open_advanced)

        self._inspector_dock.show_for(
            block, self.fs,
            on_save=_on_save,
            open_advanced=_open_advanced,
        )

    def edit_stream(self, stream: Stream):
        """Abre StreamInspectorDock (slide-out, no-modal).  Reemplaza
        el dialog modal viejo con el rediseño hi-fi.

        Importante: el panel muta el stream EN VIVO mientras el user
        edita / cambia de sección.  Para que Cancelar funcione, tomamos
        un snapshot ANTES de show_for y proveemos dos callbacks:

          · on_save  = validar; si OK pushea undo cmd; si error revierte
                        desde el snapshot
          · on_cancel = revierte siempre desde el snapshot
        """
        if not hasattr(self, "_stream_inspector_dock") or \
                self._stream_inspector_dock is None:
            from stream_inspector import StreamInspectorDock
            self._stream_inspector_dock = StreamInspectorDock(self)
            self.addDockWidget(Qt.RightDockWidgetArea, self._stream_inspector_dock)

        # Snapshot PRE-edit: capturado antes de que el panel toque nada.
        # Esto es lo que permite que Cancelar / validación-fallida
        # revierta limpiamente a estado original.
        before_snapshot = self.begin_action()

        def _on_save():
            self._mark_dirty()
            is_floating = (stream.src == -1 or stream.dst == -1)
            if not is_floating:
                sev, msg = fval.validate_connection(
                    self.fs, stream.src, stream.dst,
                    stream.src_port, stream.dst_port,
                )
            else:
                sev, msg = "ok", None
            if sev == "error":
                QMessageBox.critical(self, "Conexión inválida",
                    msg + "\n\nLa edición se revierte.")
                self._apply_snapshot(before_snapshot)
                return
            if sev == "warn":
                ans = QMessageBox.question(
                    self, "Conexión atípica",
                    msg + "\n\n¿Mantener los cambios igual?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                )
                if ans != QMessageBox.Yes:
                    self._apply_snapshot(before_snapshot)
                    return
            # OK: refrescar canvas + pushear undo cmd
            item = self.scene.stream_items.get(stream.id)
            if item is not None:
                item.update_path()
            self._refresh_port_colors()
            self._on_selection_changed()
            if self._bubble_manager is not None:
                self._bubble_manager.refresh_all()
            if self._hx_bubble_manager is not None:
                self._hx_bubble_manager.refresh_all()
            self.end_action(f"Editar {stream.name}", before_snapshot)

        def _on_cancel():
            """Revierte cualquier edición in-memory hecha por el panel
            (vía _stash_current_section en cada cambio de sección) sin
            pushear un comando undo."""
            self._apply_snapshot(before_snapshot)
            # refrescar la tabla / canvas / burbujas con estado original
            item = self.scene.stream_items.get(stream.id)
            if item is not None:
                item.update_path()
            if hasattr(self, "streams_dock") and self.streams_dock:
                try: self.streams_dock.refresh()
                except Exception: pass
            if self._bubble_manager is not None:
                self._bubble_manager.refresh_all()
            if self._hx_bubble_manager is not None:
                self._hx_bubble_manager.refresh_all()

        self._stream_inspector_dock.show_for(
            stream, self.fs,
            on_save=_on_save, on_cancel=_on_cancel,
        )

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
        # Respetar el toggle de corrientes auxiliares (Ctrl+U) tras
        # cargar / undo / redo.
        self._apply_aux_visibility()
        # Burbujas: reconcilar tras cargar / undo / redo
        if getattr(self, "_bubble_manager", None) is not None:
            self._bubble_manager.refresh_all()
        if getattr(self, "_hx_bubble_manager", None) is not None:
            self._hx_bubble_manager.refresh_all()

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
        # Burbujas: actualizar leaders (anclas de streams cambiaron)
        if getattr(self, "_bubble_manager", None) is not None:
            self._bubble_manager._refresh_leaders()
        if getattr(self, "_hx_bubble_manager", None) is not None:
            self._hx_bubble_manager._refresh_leaders()

    def _remove_block_item(self, bid):
        item = self.scene.block_items.pop(bid, None)
        if item is not None and item.scene() is self.scene:
            if hasattr(item, "decoration_items"):
                item.decoration_items.clear()
            if hasattr(item, "port_items"):
                item.port_items.clear()
            self.scene.removeItem(item)
        self.fs.blocks.pop(bid, None)

    def _delete_block(self, bid):
        self._remove_block_item(bid)
        # streams asociados (cada _delete_stream limpia los source/sink aux
        # que queden huérfanos y marca aux_user_edited en el bloque real).
        to_del = [sid for sid, s in self.fs.streams.items()
                  if s.src == bid or s.dst == bid]
        for sid in to_del:
            self._delete_stream(sid)

    def _delete_stream(self, sid):
        s = self.fs.streams.get(sid)
        aux_endpoints = []
        if s is not None and getattr(s, "auto_aux", False):
            for bid in (s.src, s.dst):
                blk = self.fs.blocks.get(bid)
                if blk is None:
                    continue
                if getattr(blk, "auto_aux", False):
                    aux_endpoints.append(bid)        # candidato a limpiar
                else:
                    # Memoria de edición: si el user borra una corriente
                    # auxiliar, no la regeneramos al guardar/abrir.
                    blk.aux_user_edited = True
        item = self.scene.stream_items.pop(sid, None)
        if item is not None:
            item.remove_from_scene(self.scene)
        self.fs.streams.pop(sid, None)
        # Limpiar source/sink auxiliares que quedaron sin ninguna corriente.
        for bid in aux_endpoints:
            if bid in self.fs.blocks and not any(
                    st.src == bid or st.dst == bid
                    for st in self.fs.streams.values()):
                self._remove_block_item(bid)

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
                f"Duty      {('+' if b.duty > 0 else '')}{funits.fmt_energy(b.duty)}\n"
                f"Utility   {b.heat_source or '(auto)'}\n\n"
                f"Entradas:  {len(ins)}  ({in_t:g} tm/año)\n"
                f"Salidas:   {len(outs)} ({out_t:g} tm/año)"
            )
            # ---- ΔH térmico a través del bloque (in→out) ----
            # Σ(ṁ·h)_salida − Σ(ṁ·h)_entrada [kW]; para un HX ≈ duty.
            if ins and outs:
                try:
                    import stream_enthalpy as _se
                    dH = _se.block_delta_h_kW(ins, outs)
                    txt += (f"\nΔH (in→out) {('+' if dH > 0 else '')}"
                            f"{funits.fmt_energy(dH)}  (térmico)")
                except Exception:
                    pass
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
                                import flowsheet_solver as _fsv
                                T_feed_K = feed.temperature + 273.15
                                q_feed = _fsv._column_feed_q(feed, T_feed_K, 1.013)
                                res = fug.design_column(
                                    feed_composition=feed.composition,
                                    F=feed.mass_flow,
                                    T_K=T_feed_K,
                                    P_bar=1.013,
                                    light_key=LK, heavy_key=HK,
                                    x_D_LK=dist_out.composition.get(LK, 0.9),
                                    x_B_LK=bot_out.composition.get(LK, 0.05),
                                    R_factor=1.3,
                                    q=q_feed,
                                    T_top_K=dist_out.temperature + 273.15,
                                    T_bot_K=bot_out.temperature + 273.15,
                                )
                                if res:
                                    txt += "\n\n─ DISEÑO FUG (NRTL) ─"
                                    txt += f"\nLK / HK    {LK} / {HK}"
                                    txt += f"\nα tope     {res.get('alpha_top',0):.2f}"
                                    txt += f"\nα fondo    {res.get('alpha_bot',0):.2f}"
                                    txt += f"\nα promedio {res.get('alpha_avg',0):.2f}"
                                    _q = res.get("q", 1.0)
                                    if abs(_q - 1.0) < 0.02:   _fase = "líq sat"
                                    elif abs(_q) < 0.02:       _fase = "vap sat"
                                    elif 0.0 < _q < 1.0:       _fase = "bifásico"
                                    elif _q > 1.0:             _fase = "líq subenfr"
                                    else:                      _fase = "vap sobrecalentado"
                                    txt += f"\nq feed     {_q:.2f}  ({_fase})"
                                    _ncomp = res.get("n_signif_comps", 0)
                                    if _ncomp >= 3:
                                        txt += f"\nMulticomp  {_ncomp} comp · Underwood real"
                                        if res.get("underwood_fallback"):
                                            txt += "\n⚠ Underwood mc no convergió, usado binario"
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

                                    # ── Bloque WANG-HENKE (MESH) ──
                                    wh_res = getattr(b, "_wh_result", None)
                                    if (getattr(b, "column_method", "fug") == "wanghenke"
                                            and wh_res is not None):
                                        Twh = wh_res.get("T_profile") or []
                                        Vwh = wh_res.get("V_profile") or []
                                        conv = wh_res.get("converged", False)
                                        txt += "\n\n─ WANG-HENKE (MESH) ─"
                                        txt += f"\nN etapas   {len(Twh)}"
                                        txt += f"\nEtapa feed {wh_res.get('feed_stage', '-')}"
                                        txt += (f"\nConvergió  {'sí' if conv else 'NO'}"
                                                f" en {wh_res.get('iterations', 0)} iter")
                                        if Twh:
                                            txt += f"\nT tope     {Twh[0]-273.15:.1f} °C"
                                            txt += f"\nT fondo    {Twh[-1]-273.15:.1f} °C"
                                        if len(Vwh) >= 2:
                                            txt += f"\nV tope     {Vwh[1]:.2f} mol/s"
                                            txt += f"\nV fondo    {Vwh[-1]:.2f} mol/s"
                                        txt += (f"\nΔV/V_avg   {wh_res.get('V_var',0.0)*100:.1f}%"
                                                f"  (0% = MES; >5% = MESH activo)")
                                        if wh_res.get("Q_cond_kW") is not None:
                                            txt += f"\nQ_cond     {wh_res['Q_cond_kW']:+.1f} kW"
                                        if wh_res.get("Q_reb_kW") is not None:
                                            txt += f"\nQ_reb      {wh_res['Q_reb_kW']:+.1f} kW"
                                        be = wh_res.get("balance_err")
                                        if be is not None:
                                            txt += f"\nBalance E  {be*100:.1f}%  (cierre global)"
                                        if not conv:
                                            txt += "\n✗ NO CONVERGIÓ — revisar N, R_factor, o pureza objetivo"
                                        for w in wh_res.get("warnings", []):
                                            wu = w.upper()
                                            if "AZEOTROPO" in wu or "INALCANZABLE" in wu:
                                                txt += f"\n✗ {w[:80]}"
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

                # ---- Desglose ΔP itemizado: de dónde viene la ΔP ----
                try:
                    bd = fsolv._trace_downstream_itemized(self.fs, b.id)
                    if bd is not None and bd["items"]:
                        txt += "\n\n─ Desglose hidráulico ─"
                        txt += (f"\nOrigen:  {bd['origin_stream_name']} @ "
                                f"{bd['origin_P_bar']:.3f} bar 🔒")
                        txt += (f"\nDestino: {bd['target_stream_name']} @ "
                                f"{bd['target_P_bar']:.3f} bar 🔒")
                        txt += f"\nΔP total: {bd['total_dp_bar']:.3f} bar"
                        txt += "\n\nAporte por elemento:"
                        total = bd["total_dp_bar"]
                        for it in sorted(bd["items"],
                                         key=lambda x: -x["dp_bar"]):
                            pct = (100 * it["dp_bar"] / total
                                   if total > 0 else 0.0)
                            bar_len = (max(1, int(32 * it["dp_bar"] / total))
                                       if (total > 0 and it["dp_bar"] > 0)
                                       else 0)
                            bar = "█" * bar_len + "·" * (32 - bar_len)
                            txt += (f"\n  {bar} {it['dp_bar']:6.3f} bar "
                                    f"({pct:5.1f}%) {it['detail'][:40]}")
                        txt += f"\n  Suma: {total:.3f} bar  ✓ cierra"
                    elif is_pump and bd is None:
                        txt += ("\n\n─ Desglose hidráulico ─"
                                "\nSin anchor downstream — ΔP no resoluble "
                                "automáticamente. Declará pressure_locked en "
                                "algún stream downstream para activar el "
                                "auto-sizing.")
                except Exception:
                    pass

            # ---- Resumen del REACTOR (modo, reacciones, conversión, calor)
            # Hace visible LO QUE EL SOLVER COMPUTÓ: hasta acá sólo se veía
            # 'Tipo', 'Duty' y 'ΔH', sin evidencia de la química o las specs.
            try:
                rxs = list(getattr(b, "reactions", None) or [])
                cust = list(getattr(b, "custom_reactions", None) or [])
                mode = getattr(b, "reactor_mode", "") or ""
                if rxs or cust or mode in ("pfr", "cstr", "batch", "stoich"):
                    txt += "\n\n── Reactor ──"
                    if mode:
                        txt += f"\nModo        {mode}"
                    if rxs:
                        txt += f"\nReacciones  {', '.join(rxs)}"
                    if cust:
                        txt += f"\nCustom      {len(cust)} reacción(es) ad-hoc"
                    if (mode == "stoich"
                            and getattr(b, "reactor_conversion", None) is not None):
                        txt += (f"\nConversión  "
                                f"{b.reactor_conversion * 100:.1f} % del "
                                f"reactivo limitante (declarado)")
                    if getattr(b, "T_op_K", 0) and b.T_op_K > 0:
                        txt += f"\nT_op        {b.T_op_K - 273.15:.1f} °C"
                    if getattr(b, "P_op_bar", 0) and b.P_op_bar > 0:
                        txt += f"\nP_op        {b.P_op_bar:.2f} bar"
                    if mode in ("pfr", "cstr", "batch") and \
                            getattr(b, "reactor_volume_L", 0) > 0:
                        txt += f"\nVolumen     {b.reactor_volume_L:.1f} L"
                    if mode == "batch" and getattr(b, "batch_time_s", 0) > 0:
                        txt += f"\nt_batch     {b.batch_time_s:.0f} s"
                    hor = getattr(b, "heat_of_reaction", None)
                    if hor is not None and abs(hor) > 1e-9:
                        sign = ("exotérmica" if hor < 0
                                else "endotérmica")
                        txt += (f"\nCalor rx    {hor:+.2f} kJ/kg input "
                                f"({sign})")
            except Exception:
                pass

            # ---- Evidencia textual por tipo de equipo (HX, flash, mech_sep,
            # splitter, tanque, horno) — mismo patrón que la sección Reactor:
            # mostrar LO QUE EL SOLVER ya computó, no info genérica.
            try:
                eq_lower = (b.eq_type or "").lower()
                # ── Intercambiador / Fired heater: _hx_diagnostics ──
                hxd = getattr(b, "_hx_diagnostics", None)
                if hxd and isinstance(hxd, dict):
                    txt += "\n\n── Intercambiador ──"
                    Th_i = hxd.get("T_h_in"); Th_o = hxd.get("T_h_out")
                    Tc_i = hxd.get("T_c_in"); Tc_o = hxd.get("T_c_out")
                    if Th_i is not None and Th_o is not None:
                        txt += f"\nCaliente    {Th_i:.1f} → {Th_o:.1f} °C"
                    if Tc_i is not None and Tc_o is not None:
                        txt += f"\nFrío        {Tc_i:.1f} → {Tc_o:.1f} °C"
                    if hxd.get("dTlm") is not None:
                        txt += f"\nΔT_LMTD     {hxd['dTlm']:.1f} °C"
                    if hxd.get("approach") is not None:
                        txt += (f"\nApproach    {hxd['approach']:.1f} °C"
                                f"  (ΔT_min={hxd.get('dT_min', 0):.0f} °C)")
                    if hxd.get("U_used"):
                        txt += f"\nU usado     {hxd['U_used']:.0f} W/m²·K"
                    if hxd.get("F") is not None:
                        txt += f"\nF correc.   {hxd['F']:.2f}"
                    if hxd.get("service"):
                        txt += f"\nServicio    {hxd['service']}"
                    elif hxd.get("cross_check"):
                        txt += f"\nServicio    {hxd['cross_check']}"
                    for w in (hxd.get("warnings") or [])[:3]:
                        txt += f"\n⚠ {w}"
                elif "fired" in eq_lower and abs(b.duty) > 1e-9:
                    # Fired heater sin _hx_diagnostics: al menos duty + combustible inferido
                    txt += "\n\n── Horno ──"
                    txt += f"\nDuty        {b.duty:+.1f} kW (calor al proceso)"
                    txt += f"\nT_proceso   ver streams in/out arriba"

                # ── Flash drum (Vessel con flash_active) ──
                if getattr(b, "flash_active", False):
                    txt += "\n\n── Flash drum ──"
                    if b.flash_T_K > 0:
                        txt += f"\nT_op        {b.flash_T_K - 273.15:.1f} °C"
                    if b.flash_P_bar > 0:
                        txt += f"\nP_op        {b.flash_P_bar:.2f} bar"
                    txt += ("\nDivide la corriente de entrada en vapor "
                            "(volátiles) y líquido por VLE isotérmico NRTL.")

                # ── Separador mecánico (mech_sep_active) ──
                if getattr(b, "mech_sep_active", False):
                    txt += "\n\n── Separador mecánico ──"
                    tgt = getattr(b, "mech_sep_target_phase", "solid") or "solid"
                    eff = getattr(b, "mech_sep_efficiency", None)
                    is_decanter = "decanter" in eq_lower
                    if is_decanter:
                        txt += "\nTipo        Decanter L-L por densidad"
                    elif "cyclone" in eq_lower:
                        txt += "\nTipo        Ciclón"
                    elif "centrifuge" in eq_lower:
                        txt += "\nTipo        Centrífuga"
                    else:
                        txt += "\nTipo        Filtro / knockout genérico"
                    # 'Fase obj.' sólo tiene sentido cuando el solver separa
                    # POR FASE; en decanters opera por DENSIDAD, no por fase.
                    if not is_decanter:
                        txt += f"\nFase obj.   {tgt}"
                    if eff is not None:
                        txt += f"\nη recup.    {eff * 100:.1f} %"
                    if b.T_op_K > 0:
                        txt += f"\nT_op        {b.T_op_K - 273.15:.1f} °C"
                    if b.P_op_bar > 0:
                        txt += f"\nP_op        {b.P_op_bar:.2f} bar"

                # ── Splitter (mass splitter por fracciones declaradas) ──
                if getattr(b, "splitter_active", False):
                    fracs = list(getattr(b, "splitter_fractions", []) or [])
                    if fracs:
                        txt += "\n\n── Splitter ──"
                        for i, f in enumerate(fracs):
                            txt += f"\nSalida {i+1}    {f * 100:.1f} %"
                        s = sum(fracs)
                        if abs(s - 1.0) > 1e-3:
                            txt += f"\n⚠ fracciones suman {s:.3f} (≠ 1)"

                # ── Storage tank ──
                if "tank" in eq_lower or "storage" in eq_lower:
                    if b.S > 0:
                        # Para tanques, S es volumen en m³ (catálogo Turton).
                        txt += "\n\n── Tanque ──"
                        txt += f"\nCapacidad   {b.S:.1f} m³"
                        # Estimar residencia si hay un stream principal
                        in_ms = [s for s in self.fs.streams.values()
                                  if s.dst == b.id and s.mass_flow > 0]
                        out_ms = [s for s in self.fs.streams.values()
                                  if s.src == b.id and s.mass_flow > 0]
                        flow = max([s.mass_flow for s in (in_ms or out_ms)],
                                    default=0)
                        if flow > 0 and b.S > 0:
                            # tm/año → m³/h con ρ≈1000 (estimación rápida);
                            # solo para dar un orden de magnitud de residencia.
                            m3_h = (flow * 1000.0 / 1000.0) / 8760.0  # ~m³/h
                            if m3_h > 0:
                                tau_h = b.S / m3_h
                                if tau_h >= 48:
                                    txt += (f"\nResidencia  ≈ {tau_h/24:.1f} días "
                                            f"(tanque sobredim. p/ flujo actual)")
                                else:
                                    txt += (f"\nResidencia  ≈ {tau_h:.1f} h "
                                            f"(estim. con ρ=1000)")
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
            # Columna: recomendar y dibujar el McCabe-Thiele desde el modelo.
            self._draw_mccabe_for_block(b)
            # Perfil tray-by-tray (9º método): T y x_LK por etapa.
            self._draw_profile_for_block(b)
        elif isinstance(it, StreamItem):
            for other in self.scene.block_items.values():
                other.set_selected_visual(False)
            # Ocultar paneles de perfil al seleccionar streams
            self._pfr_current_block = None
            if hasattr(self, "pfr_panel"):
                self.pfr_panel.setVisible(False)
            if hasattr(self, "mccabe_panel"):
                self.mccabe_panel.setVisible(False)
            if hasattr(self, "profile_panel"):
                self.profile_panel.setVisible(False)
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

    def _draw_profile_for_block(self, b):
        """Perfil tray-by-tray (T y x_LK por etapa) de una columna activa.
        Fuente: Wang-Henke si está convergido en _wh_result, fallback al
        McCabe-Thiele que ya construyó el panel del medio.  Multicomp WH
        agrega trazas adicionales; McCabe muestra solo el LK + nota CMO.
        El badge de procedencia es EXPLÍCITO — nunca se confunden fuentes."""
        panel = getattr(self, "profile_panel", None)
        if panel is None:
            return
        if not getattr(b, "column_active", False):
            panel.setVisible(False)
            return
        try:
            import tray_profile as _tp
            p = _tp.build_stage_profile(b, self.fs)
        except Exception:
            p = None
        if p is None:
            panel.setVisible(False)
            return
        # CAPTION (siempre — evidencia textual del perfil).  Para columnas
        # binarias casi-ideales, ya cubre los extremos: x y T del tope, fondo
        # y etapa de feed, más el badge de procedencia explícito.
        stages = p["stages"]
        if not stages:
            cap = ("⚠ " + (p.get("message") or "perfil truncado")
                   + f"  ·  {p['badge']}")
        else:
            top = stages[0]
            bot = stages[-1]
            n_feed = int(p.get("n_feed") or 0)
            feed_stage = stages[n_feed - 1] if 1 <= n_feed <= len(stages) else None
            cap = (f"Perfil de la columna — {p['badge']}:  "
                   f"N = {p['n_stages']} etapas, feed = {p['n_feed']}, "
                   f"{p['LK']}/{p['HK']}\n"
                   f"  tope (etapa 1): x_{p['LK']}={top['x_LK']:.3f},  "
                   f"T={top['T_C']:.1f}°C   ·   "
                   f"fondo (etapa {p['n_stages']}): x_{p['LK']}={bot['x_LK']:.3f},  "
                   f"T={bot['T_C']:.1f}°C")
            if feed_stage:
                cap += (f"\n  feed (etapa {p['n_feed']}): "
                        f"x_{p['LK']}={feed_stage['x_LK']:.3f},  "
                        f"T={feed_stage['T_C']:.1f}°C")
            if p["source"] == "mccabe":
                cap += ("\n  T por etapa = bubble point del binario "
                        "(líquido saturado, CMO).  Multicomp riguroso "
                        "requiere column_method='wanghenke'.")
            if p.get("truncated"):
                cap = "⚠ " + cap
        self._profile_caption.setText(cap)
        # CANVAS (opcional — solo si matplotlib-Qt está disponible).
        if self._profile_canvas is not None:
            try:
                self._draw_profile_canvas(p)
            except Exception:
                pass
        panel.setVisible(True)

    def _draw_profile_canvas(self, p):
        """Dibuja la figura del perfil tray-by-tray (T y x_LK por etapa) en
        el canvas.  Separado del caption para que la evidencia textual
        siempre llegue al panel aunque el canvas falle."""
        fig = self._profile_fig
        fig.clear()
        ax = fig.add_subplot(111)
        stages = p["stages"]
        if not stages:
            ax.text(0.5, 0.5, "⚠ " + (p.get("message") or "perfil truncado"),
                    ha="center", va="center", fontsize=8,
                    transform=ax.transAxes, wrap=True)
            ax.set_xticks([]); ax.set_yticks([])
            fig.tight_layout()
            self._profile_canvas.draw_idle()
            return
        xs = [s["stage"] for s in stages]
        Ts = [s["T_C"] for s in stages]
        xL = [s["x_LK"] for s in stages]
        ax.plot(xs, Ts, color="#d23", marker="o", ms=3, lw=1.0,
                label="T (°C)")
        ax.set_xlabel("etapa  (1 = tope)", fontsize=8)
        ax.set_ylabel("T (°C)", color="#d23", fontsize=8)
        ax.tick_params(axis="y", labelcolor="#d23", labelsize=7)
        ax.tick_params(axis="x", labelsize=7)
        ax2 = ax.twinx()
        ax2.plot(xs, xL, color="#1f6feb", marker="s", ms=3, lw=1.0,
                 label=f"x_{p['LK']}")
        ax2.set_ylabel(f"x ({p['LK']})", color="#1f6feb", fontsize=8)
        ax2.tick_params(axis="y", labelcolor="#1f6feb", labelsize=7)
        ax2.set_ylim(0, 1)
        for _name, vals in (p.get("other_traces") or {}).items():
            if len(vals) == len(xs):
                ax2.plot(xs, vals, color="#888", ls=":", lw=0.8)
        n_feed = int(p.get("n_feed") or 0)
        if 1 <= n_feed <= len(stages):
            ax.axvline(n_feed, color="#888", ls="--", lw=0.7)
            ax.annotate("feed", xy=(n_feed, Ts[n_feed - 1]),
                        xytext=(3, 3), textcoords="offset points",
                        fontsize=7, color="#555")
        ax.annotate("cond.", xy=(xs[0], Ts[0]),
                    xytext=(3, -10), textcoords="offset points",
                    fontsize=7, color="#555")
        ax.annotate("reb.", xy=(xs[-1], Ts[-1]),
                    xytext=(-22, -10), textcoords="offset points",
                    fontsize=7, color="#555")
        fig.tight_layout()
        self._profile_canvas.draw_idle()

    def _draw_flash_for_block(self, b):
        """Para un Vessel con flash_active ~binario: dibuja el flash en el
        diagrama x-y (curva de equilibrio + punto de operación z_F + las
        composiciones de las fases x/y) calculado desde el modelo."""
        panel = getattr(self, "mccabe_panel", None)
        if panel is None:
            return
        try:
            import distillation_simple as _ds
            f = _ds.flash_from_block(b, self.fs)
        except Exception:
            f = None
        if f is None:
            panel.setVisible(False)
            return
        # CAPTION (siempre — evidencia textual del cálculo).
        self._mccabe_caption.setText(
            f"Flash binario {f['LK']}/{f['HK']} @ {f['T_K']-273.15:.0f}°C, "
            f"{f['P_bar']:.2f} bar — del modelo:  V/F = {f['V_frac']:.2f},  "
            f"x({f['LK']})={f['x_LK']:.3f} (líq) / y={f['y_LK']:.3f} (vap),  "
            f"z_F={f['z_F']:.2f}")
        # CANVAS (solo si matplotlib-Qt está disponible).
        if self._mccabe_canvas is not None:
            try:
                fig = self._mccabe_fig
                fig.clear()
                ax = fig.add_subplot(111)
                xs, ys = f["equilibrium"]
                ax.plot([0, 1], [0, 1], color="#b8b0a0", lw=0.8)
                ax.plot(xs, ys, color="#1f6feb", lw=1.4)
                ax.plot([f["x_LK"], f["y_LK"]], [f["x_LK"], f["y_LK"]],
                        color="#d4691e", lw=0.8, ls="--")
                ax.plot([f["x_LK"]], [f["y_LK"]], "o", color="#d4691e", ms=6)
                ax.axvline(f["z_F"], color="#888", lw=0.6, ls=":")
                ax.set_xlim(0, 1)
                ax.set_ylim(0, 1)
                ax.set_xlabel(f"x ({f['LK']})", fontsize=8)
                ax.set_ylabel(f"y ({f['LK']})", fontsize=8)
                ax.tick_params(labelsize=7)
                ax.set_aspect("equal", adjustable="box")
                fig.tight_layout()
                self._mccabe_canvas.draw_idle()
            except Exception:
                pass
        panel.setVisible(True)

    def _draw_mccabe_for_block(self, b):
        """Si b es una columna binaria resoluble, recomienda y dibuja su
        diagrama McCabe-Thiele (curva de equilibrio + rectas de operación +
        q-line + escalera de etapas) calculado desde el modelo.  Si no,
        oculta el panel."""
        panel = getattr(self, "mccabe_panel", None)
        if panel is None:
            return
        if not getattr(b, "column_active", False):
            if getattr(b, "flash_active", False):
                self._draw_flash_for_block(b)
            else:
                panel.setVisible(False)
            return
        try:
            import mccabe_thiele as _mt
            d = _mt.design_from_block(b, self.fs)
        except Exception:
            d = None
        if d is None:
            panel.setVisible(False)
            return
        # CAPTION (siempre — texto es la evidencia del cálculo aunque
        # matplotlib-Qt no esté disponible y el canvas no se pueda dibujar).
        if not d.get("feasible", True):
            cap = "⚠ " + (d.get("message", "") or "Specs no escalonables.")
        else:
            rmin = d["R_min"]
            cap = (
                f"McCabe-Thiele {d['LK']}/{d['HK']} — recomendado del modelo:  "
                f"N = {d['N_stages']} etapas teóricas (feed en {d['feed_stage']}),  "
                f"R = {d['R']:.2f}"
                + (f"  (R_min {rmin:.2f})" if rmin else "")
                + f",  z_F={d['z_F']:.2f} → x_D={d['x_D']:.2f}/x_B={d['x_B']:.2f}")
            sz = d.get("sizing") or {}
            if sz.get("N_real"):
                cap += (f"\nEtapas reales ≈ {sz['N_real']} "
                        f"(E_o={sz['E_o']:.2f} O'Connell, α={sz['alpha_avg']:.2f})")
            if sz.get("diameter_m"):
                cap += (f"   ·   Ø columna ≈ {sz['diameter_m']:.2f} m "
                        f"(Souders-Brown, plato perforado, 70% inundación)")
            pk = d.get("packing") or {}
            if pk.get("Z_packed_m"):
                cap += (f"\nAlternativa relleno (Pall rings): NTU ≈ "
                        f"{pk['NTU']:.1f}, altura ≈ {pk['Z_packed_m']:.1f} m "
                        f"(N·HETP, HETP={pk['HETP_m']:.2f} m)")
        self._mccabe_caption.setText(cap)
        # CANVAS (opcional — solo si matplotlib-Qt está disponible).
        if self._mccabe_canvas is not None:
            try:
                self._draw_mccabe_canvas(d)
            except Exception:
                pass
        panel.setVisible(True)

    def _draw_mccabe_canvas(self, d):
        """Dibuja la figura McCabe-Thiele (rama factible + rama infactible
        con sólo equilibrio y marcas).  Separado del caption para que la
        evidencia textual siempre llegue al panel aunque el canvas falle."""
        fig = self._mccabe_fig
        fig.clear()
        ax = fig.add_subplot(111)
        xs, ys = d["equilibrium"]
        ax.plot([0, 1], [0, 1], color="#b8b0a0", lw=0.8)
        ax.plot(xs, ys, color="#1f6feb", lw=1.4)
        if not d.get("feasible", True):
            for a in d.get("azeotropes", []):
                ax.plot([a], [a], "o", color="#d11", ms=6)
                ax.axvline(a, color="#d11", lw=0.7, ls="--")
            for xv, c in ((d["x_D"], "#2a9d4a"), (d["x_B"], "#9d2a8a")):
                ax.axvline(xv, color=c, lw=0.5, ls=":")
        else:
            sx = [p[0] for p in d["stages"]]
            sy = [p[1] for p in d["stages"]]
            ax.plot(sx, sy, color="#d4691e", lw=1.0)
            rs, ri = d["rect"]; ss, si = d["strip"]
            xfp = d["feed_point"][0]
            ax.plot([xfp, d["x_D"]], [rs * xfp + ri, rs * d["x_D"] + ri],
                    color="#2a9d4a", lw=1.1)
            ax.plot([d["x_B"], xfp], [ss * d["x_B"] + si, ss * xfp + si],
                    color="#9d2a8a", lw=1.1)
            for xv, c in ((d["x_D"], "#2a9d4a"), (d["z_F"], "#888"),
                          (d["x_B"], "#9d2a8a")):
                ax.axvline(xv, color=c, lw=0.5, ls=":")
            for a in d.get("azeotropes", []):
                ax.axvline(a, color="#d11", lw=0.6, ls="--")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.set_xlabel(f"x ({d['LK']})", fontsize=8)
        ax.set_ylabel(f"y ({d['LK']})", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.set_aspect("equal", adjustable="box")
        fig.tight_layout()
        self._mccabe_canvas.draw_idle()

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
        # Corrientes auxiliares por defecto (cooling water / steam / aire /
        # combustible / chimenea, etc.) con su source/sink colocado cerca.
        # Solo al crear de cero (no retroactivo).  Render de lo creado.
        try:
            import equipment_auxiliaries as _aux
            for _new_id in _aux.instantiate_auxiliaries(self.fs, b):
                if _new_id in self.fs.blocks:
                    self._render_block(self.fs.blocks[_new_id])
                elif _new_id in self.fs.streams:
                    self._render_stream(self.fs.streams[_new_id])
            self._apply_aux_visibility()
        except Exception as _e:
            import logging
            logging.getLogger(__name__).debug(f"aux instancing fallo: {_e}")
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

