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

from PySide6.QtCore import (
    Qt, QRectF, QPointF, QLineF, QSize,
    Signal,
)
from PySide6.QtGui import (
    QAction, QPen, QBrush, QColor, QPainter, QFont, QPainterPath,
    QPolygonF, QPainterPathStroker, QFontMetrics, QKeySequence,
    QTransform,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsScene, QGraphicsView,
    QGraphicsItem, QGraphicsRectItem, QGraphicsPathItem,
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
    renderer.render(painter)
    painter.end()

    pixmap = QPixmap.fromImage(img)
    pixmap.setDevicePixelRatio(sup)   # decir a Qt que es 2× DPI
    _SVG_PIXMAPS[cache_key] = pixmap
    return pixmap


# ======================================================
# COLORES (paleta Material lite)
# ======================================================

COLOR_CANVAS_BG     = QColor("#fafafc")
COLOR_GRID          = QColor("#e8e8ee")
COLOR_BLOCK_FILL    = QColor("#ffffff")
COLOR_BLOCK_BORDER  = QColor("#5c6bc0")
COLOR_BLOCK_BORDER_SEL = QColor("#283593")
COLOR_BLOCK_TEXT    = QColor("#1a1a1a")
COLOR_BLOCK_SUB     = QColor("#6c6c70")
COLOR_PORT_FREE     = QColor("#bbbbbb")
COLOR_PORT_CONN     = QColor("#1565c0")
COLOR_LABEL_BG      = QColor(255, 255, 255, 220)


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
        gb_layout.addRow("Duty (kW):", self.duty_edit)

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

        layout.addRow(gb_duty)

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
        heat = self.heat_combo.currentText()
        self.block.heat_source = "" if heat == "(auto)" else heat
        # heat_of_reaction (sólo si visible, i.e. reactor)
        if self.hor_edit.isVisible():
            self.block.heat_of_reaction = float(self.hor_edit.value())


class StreamEditDialog(QDialog):
    """Editor del stream: mass_flow, role, price, T, Cp, ports, nombre."""

    def __init__(self, parent, stream: Stream, fs: Flowsheet):
        super().__init__(parent)
        self.stream = stream
        self.fs = fs
        self.setWindowTitle(f"Editar corriente — {stream.name}")
        self.resize(500, 560)

        b_src = fs.blocks[stream.src]
        b_dst = fs.blocks[stream.dst]
        ports_src = list(ep.get_ports(b_src.eq_type).keys())
        ports_dst = list(ep.get_ports(b_dst.eq_type).keys())

        layout = QFormLayout(self)

        # info read-only
        info = QLabel(f"<b>{stream.name}</b>:  {b_src.name}  →  {b_dst.name}")
        info.setStyleSheet("color: #555;")
        layout.addRow(info)

        # nombre
        self.name_edit = QLineEdit(stream.name)
        layout.addRow("Nombre:", self.name_edit)

        # mass flow
        self.mass_edit = QDoubleSpinBox()
        self.mass_edit.setRange(0.0, 1e9)
        self.mass_edit.setDecimals(2)
        self.mass_edit.setSingleStep(100.0)
        self.mass_edit.setValue(stream.mass_flow)
        layout.addRow("Flujo másico (tm/año):", self.mass_edit)

        # rol
        self.role_combo = QComboBox()
        for r in ("internal", "feed", "product"):
            self.role_combo.addItem(r)
        self.role_combo.setCurrentText(stream.role)
        layout.addRow("Rol:", self.role_combo)

        hint = QLabel(
            "feed:    materia prima externa\n"
            "product: producto final\n"
            "internal: corriente entre bloques"
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
        gb_layout.addRow("Temperatura (°C):", self.t_edit)

        # Componente principal (catálogo)
        import components as comp_mod
        self.comp_combo = QComboBox()
        self.comp_combo.addItem("(personalizado)", "")
        for key, label in comp_mod.list_labels():
            self.comp_combo.addItem(label, key)
        cur_idx = self.comp_combo.findData(stream.main_component)
        if cur_idx >= 0:
            self.comp_combo.setCurrentIndex(cur_idx)
        gb_layout.addRow("Componente principal:", self.comp_combo)

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
        gb_layout.addRow(f"Puerto en {b_src.name}:", self.src_port_combo)

        self.dst_port_combo = QComboBox()
        self.dst_port_combo.addItems(ports_dst)
        cur_dp = stream.dst_port or (ports_dst[0] if ports_dst else "")
        if cur_dp:
            idx = self.dst_port_combo.findText(cur_dp)
            if idx >= 0:
                self.dst_port_combo.setCurrentIndex(idx)
        gb_layout.addRow(f"Puerto en {b_dst.name}:", self.dst_port_combo)
        layout.addRow(gb_ports)

        # botones
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _toggle_price(self, role_text):
        visible = role_text in ("feed", "product")
        self.price_label.setVisible(visible)
        self.price_edit.setVisible(visible)

    def apply_to_model(self):
        name = self.name_edit.text().strip()
        if name:
            self.stream.name = name
        self.stream.mass_flow = float(self.mass_edit.value())
        self.stream.role = self.role_combo.currentText()
        if self.stream.role in ("feed", "product"):
            self.stream.price_usd_per_tm = float(self.price_edit.value())
        else:
            self.stream.price_usd_per_tm = 0.0
        self.stream.temperature = float(self.t_edit.value())
        self.stream.cp = float(self.cp_edit.value())
        self.stream.main_component = self.comp_combo.currentData() or ""
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
        self.setHandlesChildEvents(False)

        # Dimensiones del símbolo PFD (varían por equipo).  Fallback al
        # tamaño legacy 130×60 si el eq_type no tiene símbolo nuevo.
        self.W, self.H = pfd.block_dims(block.eq_type)

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
        f_title = QFont(sans, 11, QFont.Bold)
        f_sub   = QFont(mono, 8)

        sub_text = f"S = {block.S:g} {unit}"
        if block.n > 1:
            sub_text += f"  × {block.n}"

        # Tag: AFUERA del bloque, encima, centrado (estilo PFD industrial)
        self.text_name = QGraphicsSimpleTextItem(block.name, parent=self)
        self.text_name.setFont(f_title)
        self.text_name.setBrush(QBrush(COLOR_BLOCK_TEXT))
        br = self.text_name.boundingRect()
        self.text_name.setPos((self.W - br.width()) / 2, -br.height() - 4)
        self.text_name.setZValue(2)

        # Sub: AFUERA del bloque, debajo
        self.text_sub = QGraphicsSimpleTextItem(sub_text, parent=self)
        self.text_sub.setFont(f_sub)
        self.text_sub.setBrush(QBrush(COLOR_BLOCK_SUB))
        br_s = self.text_sub.boundingRect()
        self.text_sub.setPos((self.W - br_s.width()) / 2, self.H + 4)
        self.text_sub.setZValue(2)

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
            # supersample 2× → escalar a 0.5
            pix_item.setScale(0.5)
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
        for pname, (cx, cy) in coords.items():
            ell = QGraphicsEllipseItem(cx - r, cy - r, 2*r, 2*r, parent=self)
            ell.setBrush(QBrush(COLOR_PORT_FREE))
            ell.setPen(QPen(QColor("#333333"), 1))
            ell.setData(0, pname)        # guardamos el nombre del puerto
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
        svg = getattr(self, "_svg_mode", False)
        if selected:
            # borde índigo continuo para selección (estilo Aspen).
            self.rect.setPen(QPen(COLOR_BLOCK_BORDER_SEL,
                                   2.0 if svg else 3.0))
        else:
            # borde sutil gris claro en modo SVG, índigo normal en
            # fallback Qt paths.
            if svg:
                self.rect.setPen(QPen(QColor("#78909c"), 1.2))
            else:
                self.rect.setPen(QPen(COLOR_BLOCK_BORDER, 2))

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
        # push undo si hubo un drag
        if (event.button() == Qt.LeftButton and self.editor is not None
            and self.editor._drag_before_snapshot is not None):
            self.editor.end_action("Mover", self.editor._drag_before_snapshot)
            self.editor._drag_before_snapshot = None

    def contextMenuEvent(self, event):
        """Click derecho → menú contextual."""
        if self.editor is None:
            return
        menu = QMenu()
        title = menu.addAction(self.model.name)
        title.setEnabled(False)
        menu.addSeparator()
        menu.addAction("Conectar desde acá…",
                       lambda: self.editor.start_connection(self.model.id))
        menu.addAction("Editar propiedades… (doble-click)",
                       lambda: self.editor.edit_block(self.model))
        menu.addAction("Borrar",
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

        # label estilo PFD industrial: pill (rounded rect blanco con
        # borde del color del stream) + nombre + flujo en mono.
        self.label_bg = _RoundedRectBody(0, 0, 10, 10)
        self.label_bg.RADIUS = 3
        self.label_bg.setBrush(QBrush(QColor("#ffffff")))
        self.label_bg.setPen(QPen(Qt.NoPen))    # se setea en update_path con el color
        self.label_bg.setZValue(6)

        mono = pfd_fonts.MONO if pfd_fonts.available() else "Consolas"
        self.label_name = QGraphicsSimpleTextItem()
        self.label_name.setFont(QFont(mono, 8, QFont.Medium))
        self.label_name.setZValue(7)

        self.label_flow = QGraphicsSimpleTextItem()
        self.label_flow.setFont(QFont(mono, 8))
        self.label_flow.setBrush(QBrush(QColor("#6b7280")))   # gris suave
        self.label_flow.setZValue(7)

        self.update_path()

    def add_to_scene(self, scene: QGraphicsScene):
        scene.addItem(self)
        scene.addItem(self.label_bg)
        scene.addItem(self.label_name)
        scene.addItem(self.label_flow)

    def remove_from_scene(self, scene: QGraphicsScene):
        for item in (self, self.label_bg, self.label_name, self.label_flow):
            if item.scene() is scene:
                scene.removeItem(item)

    def _color(self):
        if self.isSelected():
            return QColor(STREAM_ROLE_COLORS_SEL.get(self.model.role, "#c62828"))
        return QColor(STREAM_ROLE_COLORS.get(self.model.role, "#37474f"))

    def _update_tooltip(self):
        s = self.model
        b_src = self.fs.blocks.get(s.src)
        b_dst = self.fs.blocks.get(s.dst)
        if b_src is None or b_dst is None:
            return
        lines = [
            f"<b>{s.name}</b>",
            f"<span style='color:#666;'>"
            f"{b_src.name} ({s.src_port or 'auto'}) → "
            f"{b_dst.name} ({s.dst_port or 'auto'})</span>",
            f"Rol: {s.role}",
            f"Flujo: {s.mass_flow:g} tm/año",
        ]
        if s.role in ("feed", "product") and s.price_usd_per_tm:
            total = s.mass_flow * s.price_usd_per_tm
            lbl = "Ingreso" if s.role == "product" else "Costo MP"
            lines.append(f"Precio: {s.price_usd_per_tm:g} USD/tm")
            lines.append(f"{lbl}: $ {total:,.0f}/año")
        if s.cp > 0:
            lines.append(f"T = {s.temperature:g} °C, Cp = {s.cp:g} kJ/kg·K")
        self.setToolTip("<br>".join(lines))

    def update_path(self):
        s = self.model
        b_src = self.fs.blocks.get(s.src)
        b_dst = self.fs.blocks.get(s.dst)
        if b_src is None or b_dst is None:
            return
        # resolver puertos con el catálogo (helper compartido con flowsheet_ui)
        pts = self._compute_polyline(b_src, b_dst, s)
        if not pts:
            return

        path = QPainterPath(QPointF(pts[0], pts[1]))
        for i in range(2, len(pts), 2):
            path.lineTo(pts[i], pts[i+1])
        self.setPath(path)

        color = self._color()
        pen = QPen(color, 2.2)
        pen.setCapStyle(Qt.SquareCap)
        pen.setJoinStyle(Qt.MiterJoin)
        self.setPen(pen)
        self._draw_arrow(path, pts[-2], pts[-1], pts[-4], pts[-3])

        # ---- label (pill blanca con borde del color del stream) ----
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

        self._update_tooltip()

    def _draw_arrow(self, path, x_end, y_end, x_prev, y_prev):
        """Triángulo al final del path (en lugar de marker arrow)."""
        import math
        dx = x_end - x_prev
        dy = y_end - y_prev
        L = math.hypot(dx, dy)
        if L < 0.01:
            return
        ux, uy = dx / L, dy / L      # versor en dirección de la flecha
        nx, ny = -uy, ux             # perpendicular
        # vértices del triángulo
        size = 8
        wing = 4
        tip = QPointF(x_end, y_end)
        b1  = QPointF(x_end - size*ux + wing*nx, y_end - size*uy + wing*ny)
        b2  = QPointF(x_end - size*ux - wing*nx, y_end - size*uy - wing*ny)
        path.moveTo(tip)
        path.lineTo(b1)
        path.lineTo(b2)
        path.lineTo(tip)
        # actualiza el path
        self.setPath(path)

    def mouseDoubleClickEvent(self, event):
        """Doble-click sobre el stream → abrir editor."""
        if self.editor is not None:
            self.editor.edit_stream(self.model)
        super().mouseDoubleClickEvent(event)

    def _label_parts(self, s):
        """Devuelve (nombre_con_tag_de_rol, flujo_con_unidad).
        Pueden ir en distintos tipos/colores dentro de la pill."""
        name = s.name
        if s.role == "feed":      name += " [feed]"
        elif s.role == "product": name += " [product]"
        elif s.role == "utility": name += " [util]"
        # unidad de display: la elegida en el dock de streams, default tm/año
        unit = "tm/año"
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            for w in app.topLevelWidgets() if app else []:
                if hasattr(w, "streams_dock") and w.streams_dock is not None:
                    unit = w.streams_dock.current_unit()
                    break
        except Exception:
            pass
        flow = funits.format_flow(s.mass_flow, unit) if s.mass_flow else ""
        return name, flow

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
            cond_fwd = (side1 == "right" and side2 == "left" and ex2 >= ex1) \
                       or (side1 == "left" and side2 == "right" and ex1 >= ex2)
            if cond_fwd and abs(ey1 - ey2) < 2:
                return [x1, y1, x2, y2]
            if cond_fwd:
                mx = (ex1 + ex2) / 2
                return [x1, y1, ex1, ey1, mx, ey1, mx, ey2, ex2, ey2, x2, y2]
            # mismo lado o opuestos pero atrás: rodea por arriba
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

class FlowsheetScene(QGraphicsScene):
    """QGraphicsScene con grid de fondo + items del flowsheet.
    Mantiene mappings model_id → QGraphicsItem."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackgroundBrush(QBrush(COLOR_CANVAS_BG))
        self.setSceneRect(-200, -200, 5000, 4000)
        self.block_items:  dict = {}      # block_id  → BlockItem
        self.stream_items: dict = {}      # stream_id → StreamItem
        self._draw_grid()

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
        self._zoom = 1.0
        self._panning = False
        self._pan_start = QPointF(0, 0)

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

    COL_NAME, COL_FROM, COL_TO, COL_ROLE, COL_FLOW, COL_T, COL_CP, COL_PRICE = range(8)

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
        cols = ["Nombre", "Desde", "Hacia", "Rol", "Flujo", "T", "Cp", "Precio"]
        self.table = QTableWidget(0, len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.itemDoubleClicked.connect(self._on_double_click)
        for col, width in (
            (self.COL_NAME, 140), (self.COL_FROM, 140), (self.COL_TO, 140),
            (self.COL_ROLE, 70),  (self.COL_FLOW, 120), (self.COL_T, 70),
            (self.COL_CP, 70),    (self.COL_PRICE, 90),
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
            vals = [
                s.name,
                src_label,
                dst_label,
                s.role,
                funits.format_flow(s.mass_flow, unit),
                f"{s.temperature:g} °C" if s.cp > 0 else "—",
                f"{s.cp:g}" if s.cp > 0 else "—",
                (f"${s.price_usd_per_tm:g}/tm"
                 if s.role in ("feed", "product") and s.price_usd_per_tm
                 else "—"),
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if c in (self.COL_FLOW, self.COL_T, self.COL_CP, self.COL_PRICE):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
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
        tb = self.addToolBar("Workflow")
        tb.setMovable(False)

        def add_btn(text, slot, sep=False):
            act = QAction(text, self)
            act.triggered.connect(slot)
            tb.addAction(act)
            if sep:
                tb.addSeparator()

        add_btn("Nuevo",     self.action_new)
        add_btn("Abrir…",    self.action_open)
        add_btn("Guardar…",  self.action_save)

        # menú de ejemplos
        examples_act = QAction("Ejemplos ▾", self)
        examples_menu = QMenu(self)
        from flowsheet_ui import FlowsheetEditor as _LegacyEditor
        # reusar los example builders del editor legacy
        def make_loader(key):
            return lambda: self.action_load_example(key)
        examples_menu.addAction("HDA — Hidrodealquilación de tolueno", make_loader("hda"))
        examples_menu.addAction("Síntesis de metanol",                  make_loader("methanol"))
        examples_menu.addAction("Destilación binaria",                  make_loader("distillation"))
        examples_act.setMenu(examples_menu)
        tb.addAction(examples_act)
        # workaround: QAction con menu necesita un QToolButton para mostrar el dropdown
        btn = tb.widgetForAction(examples_act)
        if btn is not None and hasattr(btn, "setPopupMode"):
            from PySide6.QtWidgets import QToolButton
            btn.setPopupMode(QToolButton.InstantPopup)
        tb.addSeparator()

        add_btn("Borrar selección", self.action_delete)
        # undo/redo
        self.undo_action = self.undo_stack.createUndoAction(self, "↶ Deshacer")
        self.undo_action.setShortcut(QKeySequence.Undo)
        tb.addAction(self.undo_action)
        self.redo_action = self.undo_stack.createRedoAction(self, "↷ Rehacer")
        self.redo_action.setShortcut(QKeySequence.Redo)
        tb.addAction(self.redo_action)
        tb.addSeparator()

        add_btn("Zoom −",     self.view.zoom_out)
        add_btn("100 %",      self.view.zoom_reset)
        add_btn("Zoom +",     self.view.zoom_in)
        add_btn("Ajustar",    self.view.zoom_fit)
        tb.addSeparator()

        add_btn("OPEX extras…",    self.action_opex_extras)
        add_btn("Solve balances",  self.action_solve)
        # toggle del dock de tabla de corrientes (creado en
        # _build_streams_dock); toggleViewAction() ya viene cableado
        # para mostrar/ocultar y refleja el estado actual.
        if hasattr(self, "streams_dock") and self.streams_dock is not None:
            toggle = self.streams_dock.toggleViewAction()
            toggle.setText("Tabla de corrientes")
            toggle.setShortcut("Ctrl+T")
            tb.addAction(toggle)
        add_btn("Calcular",        self.action_compute)
        add_btn("Análisis económico →", self.action_launch_analysis)
        tb.addSeparator()

        # menú Exportar
        export_act = QAction("Exportar ▾", self)
        export_menu = QMenu(self)
        export_menu.addAction("PDF…", self.action_export_pdf)
        export_menu.addAction("SVG (vectorial)…", self.action_export_svg)
        export_menu.addAction("PNG (alta resolución)…", self.action_export_png)
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
            "Doble-click sobre un equipo para agregarlo.\n"
            "Arrastrá los bloques en el canvas.\n"
            "Doble-click sobre un bloque → editar.\n"
            "(dialogs Qt: phase B)"
        )
        info.setStyleSheet("color:#666; font-size:9pt;")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.lib_tree = QTreeWidget()
        self.lib_tree.setHeaderHidden(True)
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
        self.status.showMessage(
            f"{len(self.fs.blocks)} equipos · {len(self.fs.streams)} corrientes"
        )
        # refrescar tabla de corrientes (si ya existe; durante __init__
        # podría no existir todavía)
        if hasattr(self, "streams_dock") and self.streams_dock is not None:
            self.streams_dock.refresh()

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
        # Los example builders son métodos del FlowsheetEditor (Tk).
        from flowsheet_ui import FlowsheetEditor as TkEditor
        # reset del fs y rearmar
        self.fs = Flowsheet()
        shim = _ExampleBuilderShim(self.fs)
        builder_map = {
            "hda":          TkEditor._example_hda,
            "methanol":     TkEditor._example_methanol,
            "distillation": TkEditor._example_distillation,
        }
        builder = builder_map.get(key)
        if builder is None:
            return
        builder(shim)
        self._rebuild_scene()
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
        self._update_status()
        self.end_action(f"Borrar selección ({len(selected)})", before)

    def action_solve(self):
        if not self.fs.blocks:
            QMessageBox.information(self, "Solve", "El diagrama está vacío.")
            return
        result = fsolv.solve(self.fs)
        # refrescar streams (mass_flow / T pueden haber cambiado)
        for sid, item in self.stream_items_iter():
            item.update_path()
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
                              year_target=2026)
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
                                   year_target=2026)
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
        cmd = [sys.executable, "ANA.py", "--import", tmp_path]
        try:
            cwd = os.path.dirname(os.path.abspath(__file__))
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

    def _rebuild_scene(self):
        """Recrea todos los items en la scene desde self.fs."""
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
        """Llamado por BlockItem.itemChange cuando un bloque se mueve."""
        for s in self.fs.streams.values():
            if s.src == block_id or s.dst == block_id:
                item = self.scene.stream_items.get(s.id)
                if item is not None:
                    item.update_path()

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
            self.prop_label.setText(txt)
        elif isinstance(it, StreamItem):
            for other in self.scene.block_items.values():
                other.set_selected_visual(False)
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
                f"Flujo      {s.mass_flow:g} tm/año\n"
                f"T          {s.temperature:g} °C\n"
                f"Cp         {s.cp:g} kJ/kg·K"
            )
            if s.role in ("feed", "product"):
                txt += f"\nPrecio     {s.price_usd_per_tm:g} USD/tm"
            self.prop_label.setText(txt)

    # ---------------------------------------------------
    # LIBRARY → CANVAS
    # ---------------------------------------------------

    def _on_lib_double_click(self, item, _col):
        if item.data(0, Qt.UserRole):
            self._add_block_of_type(item.data(0, Qt.UserRole))

    def _add_selected_from_lib(self):
        sel = self.lib_tree.currentItem()
        if sel is None or not sel.data(0, Qt.UserRole):
            return
        self._add_block_of_type(sel.data(0, Qt.UserRole))

    def _add_block_of_type(self, eq_type):
        spec = eq.EQUIPMENT_DATA.get(eq_type)
        if not spec:
            return
        before = self.begin_action()
        bid = self.fs.new_id()
        nombre = ep.next_block_name(eq_type,
                                     [b.name for b in self.fs.blocks.values()])
        S_default = (spec["S_min"] + spec["S_max"]) / 2
        n_existing = len(self.fs.blocks)
        x = 200 + (n_existing % 6) * 180
        y = 100 + ((n_existing // 6) % 6) * 120
        b = Block(id=bid, name=nombre, eq_type=eq_type, S=S_default,
                  n=1, x=x, y=y)
        self.fs.blocks[bid] = b
        self._render_block(b)
        self._refresh_port_colors()
        self._update_status()
        self.end_action(f"Agregar {nombre}", before)


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
        self.fs.blocks[bid] = b
        return bid

    def _add_example_stream(self, src, dst, name, mass_flow=0.0,
                            role="internal", src_port="", dst_port="",
                            price=0.0, T=25.0, cp=0.0,
                            main_component="", phase="",
                            composition=None):
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
