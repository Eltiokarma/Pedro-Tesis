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

import equipment_costs as eq
import equipment_ports as ep
import flowsheet_solver as fsolv
import flowsheet_export as fexp
from flowsheet_model import (
    Block, Stream, Flowsheet,
    STREAM_ROLE_COLORS, STREAM_ROLE_COLORS_SEL,
    BLOCK_W, BLOCK_H, GRID_STEP, ROUTING_GAP,
)


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

        self.cp_edit = QDoubleSpinBox()
        self.cp_edit.setRange(0.0, 100.0)
        self.cp_edit.setDecimals(3)
        self.cp_edit.setSingleStep(0.1)
        self.cp_edit.setValue(stream.cp)
        gb_layout.addRow("Cp (kJ/kg·K):", self.cp_edit)

        cp_hint = QLabel(
            "Típicos:  agua líq 4.18 · vapor 2.0 · aire 1.0\n"
            "hidrocarburos líq 1.7-2.2 · Cp=0 omite del balance"
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

        # --- cuerpo (rect base + decoración por categoría) ---
        self.rect = QGraphicsRectItem(0, 0, BLOCK_W, BLOCK_H, parent=self)
        self.rect.setBrush(QBrush(COLOR_BLOCK_FILL))
        self.rect.setPen(QPen(COLOR_BLOCK_BORDER, 2))

        spec = eq.EQUIPMENT_DATA.get(block.eq_type, {})
        unit = spec.get("S_unit", "")
        cat  = spec.get("categoria", "")
        self.decoration_items = []   # items hijos que decoran según categoría
        self._draw_category_decoration(cat, block.eq_type)

        # --- textos ---
        f_title = QFont("Segoe UI", 10, QFont.Bold)
        f_sub   = QFont("Segoe UI", 7)

        sub_text = f"S = {block.S:g} {unit}"
        if block.n > 1:
            sub_text += f"  × {block.n}"

        self.text_name = QGraphicsSimpleTextItem(block.name, parent=self)
        self.text_name.setFont(f_title)
        self.text_name.setBrush(QBrush(COLOR_BLOCK_TEXT))
        br = self.text_name.boundingRect()
        self.text_name.setPos((BLOCK_W - br.width()) / 2, 6)

        self.text_sub = QGraphicsSimpleTextItem(sub_text, parent=self)
        self.text_sub.setFont(f_sub)
        self.text_sub.setBrush(QBrush(COLOR_BLOCK_SUB))
        br_s = self.text_sub.boundingRect()
        self.text_sub.setPos((BLOCK_W - br_s.width()) / 2, BLOCK_H - br_s.height() - 4)

        # --- puertos ---
        self.port_items: dict = {}     # port_name → QGraphicsEllipseItem
        self._render_ports()

        self.setPos(block.x, block.y)
        self.setZValue(10)

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
        """Dibuja símbolos PFD simplificados según la categoría del
        equipo.  Mantiene el rect base para hit-testing/select."""
        w, h = BLOCK_W, BLOCK_H
        cx, cy = w / 2, h / 2

        if category == "Heat exchangers":
            # 2 líneas paralelas horizontales atravesando el bloque
            # (representa el banco de tubos)
            self._add_deco_line(8, h * 0.42, w - 8, h * 0.42, 1.3,
                                QColor("#90a4ae"))
            self._add_deco_line(8, h * 0.58, w - 8, h * 0.58, 1.3,
                                QColor("#90a4ae"))
            # punteros de retorno en los extremos
            self._add_deco_line(8, h * 0.42, 8, h * 0.58, 1.3,
                                QColor("#90a4ae"))
            self._add_deco_line(w - 8, h * 0.42, w - 8, h * 0.58, 1.3,
                                QColor("#90a4ae"))

        elif category == "Pumps":
            # círculo central (cuerpo de la bomba)
            r = 14
            circle = QPainterPath()
            circle.addEllipse(cx - r, cy - r, 2*r, 2*r)
            self._add_deco_path(circle, 1.5, QColor("#5c6bc0"),
                                QColor("#e8eaf6"))
            # triángulo apuntando a la derecha (impulsor)
            tri = QPainterPath()
            tri.moveTo(cx - 5, cy - 6)
            tri.lineTo(cx + 6, cy)
            tri.lineTo(cx - 5, cy + 6)
            tri.closeSubpath()
            self._add_deco_path(tri, 0, COLOR_BLOCK_BORDER,
                                COLOR_BLOCK_BORDER)

        elif category == "Compressors":
            # forma trapezoidal (entrada estrecha, salida ancha)
            tr = QPainterPath()
            tr.moveTo(15, h * 0.30)
            tr.lineTo(w - 15, h * 0.18)
            tr.lineTo(w - 15, h * 0.82)
            tr.lineTo(15, h * 0.70)
            tr.closeSubpath()
            self._add_deco_path(tr, 1.5, QColor("#5c6bc0"),
                                QColor("#fff3e0"))

        elif category == "Reactors":
            # rect interno + agitador (línea vertical + cruz arriba)
            inner = QPainterPath()
            inner.addRoundedRect(10, h * 0.20, w - 20, h * 0.6, 4, 4)
            self._add_deco_path(inner, 1.3, QColor("#5c6bc0"),
                                QColor("#fbe9e7"))
            # eje del agitador
            self._add_deco_line(cx, 6, cx, h * 0.50, 1.2)
            # paletas del agitador (cruz)
            self._add_deco_line(cx - 7, h * 0.50, cx + 7, h * 0.50, 1.2)

        elif category == "Vessels":
            # caso especial: torre vs vessel horizontal vs vertical
            if "Tower" in eq_type:
                # rect alto centrado + bandejas (líneas horizontales)
                col_w = 22
                rect = QPainterPath()
                rect.addRoundedRect(cx - col_w / 2, 8, col_w, h - 16, 3, 3)
                self._add_deco_path(rect, 1.5, QColor("#5c6bc0"),
                                    QColor("#e3f2fd"))
                # bandejas
                for i in range(1, 5):
                    y_tray = 8 + (h - 16) * i / 5
                    self._add_deco_line(cx - col_w / 2 + 2, y_tray,
                                        cx + col_w / 2 - 2, y_tray, 0.8,
                                        QColor("#90a4ae"))
            elif "horizontal" in eq_type.lower():
                # cilindro horizontal (rect redondeado en los extremos)
                rect = QPainterPath()
                rect.addRoundedRect(8, h * 0.30, w - 16, h * 0.4, 12, 12)
                self._add_deco_path(rect, 1.5, QColor("#5c6bc0"),
                                    QColor("#e3f2fd"))
            else:
                # vessel vertical (rect alto)
                vw = w * 0.45
                rect = QPainterPath()
                rect.addRoundedRect(cx - vw / 2, 8, vw, h - 16, 8, 8)
                self._add_deco_path(rect, 1.5, QColor("#5c6bc0"),
                                    QColor("#e3f2fd"))

        elif category == "Storage":
            # tanque: cilindro vertical con techo
            tw = w * 0.55
            rect = QPainterPath()
            rect.addRect(cx - tw / 2, h * 0.30, tw, h * 0.55)
            self._add_deco_path(rect, 1.5, QColor("#5c6bc0"),
                                QColor("#e8f5e9"))
            # techo (línea curva arriba)
            if "cone" in eq_type.lower():
                roof = QPainterPath()
                roof.moveTo(cx - tw / 2, h * 0.30)
                roof.lineTo(cx, h * 0.18)
                roof.lineTo(cx + tw / 2, h * 0.30)
                self._add_deco_path(roof, 1.5, QColor("#5c6bc0"))
            else:  # floating roof
                self._add_deco_line(cx - tw / 2 + 2, h * 0.35,
                                    cx + tw / 2 - 2, h * 0.35, 1.0,
                                    QColor("#5c6bc0"))

        elif category == "Fired heaters":
            # horno: rect con llama (triángulos abajo)
            rect = QPainterPath()
            rect.addRoundedRect(8, h * 0.25, w - 16, h * 0.55, 4, 4)
            self._add_deco_path(rect, 1.5, QColor("#5c6bc0"),
                                QColor("#fff8e1"))
            # llama: 3 triángulos en la base
            flame = QPainterPath()
            base_y = h * 0.80
            tip_y  = h * 0.65
            for fx in (cx - 14, cx, cx + 14):
                flame.moveTo(fx - 4, base_y)
                flame.lineTo(fx, tip_y)
                flame.lineTo(fx + 4, base_y)
            self._add_deco_path(flame, 1.3, QColor("#ef6c00"),
                                QColor("#ffcc80"))

        elif category == "Fans / blowers":
            # círculo con 3 aspas
            r = 13
            circle = QPainterPath()
            circle.addEllipse(cx - r, cy - r, 2*r, 2*r)
            self._add_deco_path(circle, 1.3, QColor("#5c6bc0"),
                                QColor("#e1f5fe"))
            # aspas (líneas radiales)
            import math
            for k in range(3):
                ang = (math.pi / 2) + k * (2 * math.pi / 3)
                self._add_deco_line(
                    cx, cy,
                    cx + r * 0.85 * math.cos(ang),
                    cy + r * 0.85 * math.sin(ang),
                    1.4, QColor("#5c6bc0"),
                )

        elif category == "Solids / sep.":
            # rect con triángulo de sólidos (cono abajo)
            inner = QPainterPath()
            inner.moveTo(12, h * 0.30)
            inner.lineTo(w - 12, h * 0.30)
            inner.lineTo(cx + 8, h - 6)
            inner.lineTo(cx - 8, h - 6)
            inner.closeSubpath()
            self._add_deco_path(inner, 1.3, QColor("#5c6bc0"),
                                QColor("#efebe9"))

        # otras categorías: solo el rect base + el texto

    def _render_ports(self):
        ports = ep.get_ports(self.model.eq_type)
        r = self.PORT_RADIUS
        for pname, (side, frac) in ports.items():
            if side == "right":
                cx, cy = BLOCK_W, BLOCK_H * frac
            elif side == "left":
                cx, cy = 0, BLOCK_H * frac
            elif side == "top":
                cx, cy = BLOCK_W * frac, 0
            else:  # bottom
                cx, cy = BLOCK_W * frac, BLOCK_H
            ell = QGraphicsEllipseItem(cx - r, cy - r, 2*r, 2*r, parent=self)
            ell.setBrush(QBrush(COLOR_PORT_FREE))
            ell.setPen(QPen(QColor("#333333"), 1))
            ell.setData(0, pname)        # guardamos el nombre del puerto
            self.port_items[pname] = ell

    def update_port_colors(self, used_ports: set):
        """Marca puertos conectados en azul, libres en gris."""
        for pname, ell in self.port_items.items():
            if pname in used_ports:
                ell.setBrush(QBrush(COLOR_PORT_CONN))
            else:
                ell.setBrush(QBrush(COLOR_PORT_FREE))

    def set_selected_visual(self, selected: bool):
        if selected:
            self.rect.setPen(QPen(COLOR_BLOCK_BORDER_SEL, 3))
        else:
            self.rect.setPen(QPen(COLOR_BLOCK_BORDER, 2))

    def itemChange(self, change, value):
        """Sync posición al modelo + refresh streams conectados."""
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            # snap a grid
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
        super().mousePressEvent(event)

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

        # label asociado (texto + fondo)
        self.label_bg   = QGraphicsRectItem()
        self.label_bg.setBrush(QBrush(COLOR_LABEL_BG))
        self.label_bg.setPen(QPen(Qt.NoPen))
        self.label_bg.setZValue(6)

        self.label_text = QGraphicsSimpleTextItem()
        self.label_text.setFont(QFont("Segoe UI", 8))
        self.label_text.setBrush(QBrush(QColor("#222222")))
        self.label_text.setZValue(7)

        self.update_path()

    def add_to_scene(self, scene: QGraphicsScene):
        scene.addItem(self)
        scene.addItem(self.label_bg)
        scene.addItem(self.label_text)

    def remove_from_scene(self, scene: QGraphicsScene):
        for item in (self, self.label_bg, self.label_text):
            if item.scene() is scene:
                scene.removeItem(item)

    def _color(self):
        if self.isSelected():
            return QColor(STREAM_ROLE_COLORS_SEL.get(self.model.role, "#c62828"))
        return QColor(STREAM_ROLE_COLORS.get(self.model.role, "#37474f"))

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
        pen = QPen(color, 2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)

        # flecha simple al final
        # (Qt no tiene flecha built-in en PathItem; la dibujamos como
        # parte del path al final).  Simplificación: triángulo aparte
        # con add_arrow_to_path en una v2; aquí dejamos pen con flecha
        # cosmética en el extremo.
        self._draw_arrow(path, pts[-2], pts[-1], pts[-4], pts[-3])

        # label
        lx, ly = self._label_xy(pts)
        text = self._label_text(s)
        self.label_text.setText(text)
        bb = self.label_text.boundingRect()
        self.label_text.setPos(lx - bb.width() / 2, ly - bb.height() / 2)
        pad = 2
        self.label_bg.setRect(
            lx - bb.width() / 2 - pad,
            ly - bb.height() / 2 - 1,
            bb.width() + 2 * pad,
            bb.height() + 2,
        )

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

    def _label_text(self, s):
        role_tag = ""
        if s.role == "feed":    role_tag = " [feed]"
        elif s.role == "product": role_tag = " [product]"
        flow = f"  {s.mass_flow:g} tm/año" if s.mass_flow else ""
        return s.name + role_tag + flow

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
        if side == "right":
            x, y = b.x + BLOCK_W,         b.y + BLOCK_H * frac
        elif side == "left":
            x, y = b.x,                   b.y + BLOCK_H * frac
        elif side == "top":
            x, y = b.x + BLOCK_W * frac,  b.y
        else:  # bottom
            x, y = b.x + BLOCK_W * frac,  b.y + BLOCK_H
        return side, x, y

    @staticmethod
    def _side_dir(side):
        return {"right": (1, 0), "left": (-1, 0),
                "top":   (0, -1), "bottom": (0, 1)}.get(side, (1, 0))

    def _compute_polyline(self, b_src, b_dst, s):
        """Polyline ortogonal Z-shape o L-shape entre puertos del src y dst."""
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
            xmax = max(b_src.x + BLOCK_W, b_dst.x + BLOCK_W) + 40
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
        for item in list(self.block_items.values()):
            self.removeItem(item)
        for item in list(self.stream_items.values()):
            item.remove_from_scene(self)
        self.block_items.clear()
        self.stream_items.clear()


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

class FlowsheetMainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Diagrama de proceso — Qt edition")
        self.resize(1400, 820)

        self.fs = Flowsheet()
        self.scene = FlowsheetScene(self)
        self.view  = FlowsheetView(self.scene)
        self.setCentralWidget(self.view)

        # state de conexión pendiente (right-click + left-click)
        self._connecting_from: int = None

        self._build_toolbar()
        self._build_library_dock()
        self._build_properties_dock()
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
        tb.addSeparator()

        add_btn("Zoom −",     self.view.zoom_out)
        add_btn("100 %",      self.view.zoom_reset)
        add_btn("Zoom +",     self.view.zoom_in)
        add_btn("Ajustar",    self.view.zoom_fit)
        tb.addSeparator()

        add_btn("OPEX extras…",    self.action_opex_extras)
        add_btn("Solve balances",  self.action_solve)
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

    def _build_statusbar(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self._update_status()

    def _update_status(self):
        self.status.showMessage(
            f"{len(self.fs.blocks)} equipos · {len(self.fs.streams)} corrientes"
        )

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

        # Los example builders son métodos del FlowsheetEditor (Tk).
        # Los podemos llamar con un shim que provee los helpers que esperan.
        from flowsheet_ui import FlowsheetEditor as TkEditor
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

    # ---------------------------------------------------
    # ACCIONES — Otros
    # ---------------------------------------------------

    def action_delete(self):
        for it in list(self.scene.selectedItems()):
            if isinstance(it, BlockItem):
                self._delete_block(it.model.id)
            elif isinstance(it, StreamItem):
                self._delete_stream(it.model.id)
        self._update_status()

    def action_solve(self):
        if not self.fs.blocks:
            QMessageBox.information(self, "Solve", "El diagrama está vacío.")
            return
        result = fsolv.solve(self.fs)
        # refrescar streams (mass_flow / T pueden haber cambiado)
        for sid, item in self.stream_items_iter():
            item.update_path()
        self._update_status()
        # mostrar resumen
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Solver: " + ("OK" if result.success else "revisar"))
        dlg.setText("Resumen del solver:")
        dlg.setDetailedText(result.summary())
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
        dlg = OpexExtrasDialog(self, self.fs)
        dlg.exec()
        # los cambios se reflejan en self.fs.opex_extras dentro del dialog
        self._update_status()

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
        # incluir labels de streams (label_bg / label_text son items aparte)
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
            dlg.apply_to_model()
            # refrescar item
            item = self.scene.block_items.get(block.id)
            if item is not None:
                self.scene.removeItem(item)
                del self.scene.block_items[block.id]
                self._render_block(block)
                # los streams conectados también se refrescan visualmente
                self.refresh_streams_of(block.id)
            self._refresh_port_colors()
            self._update_status()
            self._on_selection_changed()

    def edit_stream(self, stream: Stream):
        """Abre StreamEditDialog y refresca el render."""
        dlg = StreamEditDialog(self, stream, self.fs)
        if dlg.exec() == QDialog.Accepted:
            dlg.apply_to_model()
            item = self.scene.stream_items.get(stream.id)
            if item is not None:
                item.update_path()
            self._refresh_port_colors()
            self._on_selection_changed()

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
        # autoselect de puertos
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

    def delete_block(self, bid: int):
        ans = QMessageBox.question(
            self, "Borrar equipo",
            f"¿Borrar '{self.fs.blocks[bid].name}' y sus corrientes asociadas?",
        )
        if ans != QMessageBox.Yes:
            return
        self._delete_block(bid)
        self._update_status()

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
            b_src = self.fs.blocks[s.src].name
            b_dst = self.fs.blocks[s.dst].name
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
        bid = self.fs.new_id()
        nombre = ep.next_block_name(eq_type,
                                     [b.name for b in self.fs.blocks.values()])
        S_default = (spec["S_min"] + spec["S_max"]) / 2
        # posicionar en una grilla simple
        n_existing = len(self.fs.blocks)
        x = 200 + (n_existing % 6) * 180
        y = 100 + ((n_existing // 6) % 6) * 120
        b = Block(id=bid, name=nombre, eq_type=eq_type, S=S_default,
                  n=1, x=x, y=y)
        self.fs.blocks[bid] = b
        self._render_block(b)
        self._refresh_port_colors()
        self._update_status()


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
                            price=0.0, T=25.0, cp=0.0):
        sid = self.fs.new_id()
        s = Stream(
            id=sid, name=name, src=src, dst=dst,
            mass_flow=mass_flow, role=role,
            src_port=src_port, dst_port=dst_port,
            price_usd_per_tm=price,
            temperature=T, cp=cp,
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
