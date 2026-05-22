"""
EDITOR CHROME — topbar, paleta vertical flotante y zoom control.

Pieza visual nueva de la Parte B del rediseño (NUEVA_UI_P_SAD_1):

  · EditorTopbar  — barra de 52px con identidad del proyecto a la
                    izquierda, undo/redo/auto-arrange en el centro,
                    status del solver (dot + label + iter/tiempo) +
                    botones "Validar DOF" + "▶ Resolver" a la derecha.

  · EditorPalette — paleta vertical flotante de 50px de ancho, estilo
                    Figma.  Tools arriba (select / pan / connect / text)
                    y 7 tipos de bloque abajo, dibujados como siluetas
                    ISA via QPainter (no íconos rasterizados — los
                    mismos paths que se usan on-canvas).

  · EditorZoom    — control flotante bottom-right con − / 100% / + / fit.

  · BlockGlyph.draw — función que pinta la silueta ISA de un tipo de
                      bloque sobre un QPainter (reusable en la paleta
                      y eventualmente on-canvas para BlockItem nuevo).

Los tokens (colores, dimensiones) viven en `block_inspector.TOK` para
mantener una sola fuente de verdad entre Inspector y Editor.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import (
    Qt, Signal, QSize, QRect, QRectF, QPointF, QTimer,
)
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QPainterPath, QPolygonF,
    QFontMetrics, QMouseEvent,
)
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QToolButton,
    QFrame, QSizePolicy, QButtonGroup, QGraphicsView,
)

import pfd_fonts
from block_inspector import TOK


# ════════════════════════════════════════════════════════
#  BLOCK GLYPH — paths ISA por tipo (los mismos del mockup)
# ════════════════════════════════════════════════════════

# Dimensiones canónicas por tipo de bloque (del jsx)
BLOCK_DIMS: Dict[str, Tuple[int, int]] = {
    "reactor":    (60, 64),
    "mezclador":  (56, 44),
    "separador":  (56, 70),
    "columna":    (44, 88),
    "hx":         (84, 50),
    "bomba":      (56, 50),
    "tanque":     (52, 60),
}

# Mapeo del tipo del mockup → eq_type canónico del catálogo
# equipment_costs.EQUIPMENT_DATA.
PALETTE_TO_EQ_TYPE: Dict[str, str] = {
    "reactor":   "Reactor — CSTR (agitado)",
    "mezclador": "Mixer — static",
    "separador": "Vessel — vertical",
    "columna":   "Tower (column shell)",
    "hx":        "Heat exch. — fixed tube",
    "bomba":     "Pump — centrifugal",
    "tanque":    "Storage tank — cone roof",
}

PALETTE_LABELS: Dict[str, str] = {
    "reactor":   "Reactor",
    "mezclador": "Mezclador",
    "separador": "Separador / Flash",
    "columna":   "Columna",
    "hx":        "Intercambiador",
    "bomba":     "Bomba",
    "tanque":    "Tanque",
}


class BlockGlyph:
    """Painter de siluetas ISA. Estática — sin estado.

    `draw(painter, type_, w, h, stroke, fill)` pinta la silueta del
    tipo dado dentro del rectángulo (0,0,w,h) usando el painter ya
    configurado por el caller.  No salva/restaura el painter — eso es
    responsabilidad del caller (si va a transformar antes).
    """

    @staticmethod
    def draw(p: QPainter, type_: str, w: int, h: int,
             stroke: QColor, fill: QColor = None,
             stroke_width: float = 1.6):
        pen = QPen(stroke, stroke_width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        if fill is None:
            fill_brush = QBrush(QColor(TOK["bg_elev"]))
        else:
            fill_brush = QBrush(fill)
        p.setBrush(fill_brush)
        p.setRenderHint(QPainter.Antialiasing, True)

        # router por tipo
        method = getattr(BlockGlyph, f"_draw_{type_}", None)
        if method is None:
            # fallback: rect
            p.drawRoundedRect(QRectF(2, 2, w-4, h-4), 4, 4)
            return
        method(p, w, h, stroke, fill_brush, stroke_width)

    # ── tipos ──────────────────────────────────────────
    @staticmethod
    def _draw_reactor(p, w, h, stroke, fill_brush, sw):
        # body (rect rounded) + agitator shaft + impeller blades + legs
        p.drawRoundedRect(QRectF(6, 10, w-12, h-16), 6, 6)
        # agitator shaft
        thin = QPen(stroke, 1.2); thin.setCapStyle(Qt.RoundCap)
        p.setPen(thin); p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(w/2, 4), QPointF(w/2, h-12))
        # impeller blades
        pen2 = QPen(stroke, sw); pen2.setCapStyle(Qt.RoundCap)
        p.setPen(pen2)
        p.drawLine(QPointF(w/2-7, h-14), QPointF(w/2+7, h-14))
        # diagonal blade (light)
        ghost = QColor(stroke); ghost.setAlphaF(0.5)
        p.setPen(QPen(ghost, 1.0))
        p.drawLine(QPointF(w/2-5, h-18), QPointF(w/2+5, h-10))
        # fluid line (light)
        ghost2 = QColor(stroke); ghost2.setAlphaF(0.35)
        p.setPen(QPen(ghost2, 1.0))
        p.drawLine(QPointF(9, h/2+4), QPointF(w-9, h/2+4))
        # legs
        p.setPen(QPen(stroke, 1.2))
        p.drawLine(QPointF(w/2-12, h-6), QPointF(w/2-12, h-1))
        p.drawLine(QPointF(w/2+12, h-6), QPointF(w/2+12, h-1))

    @staticmethod
    def _draw_mezclador(p, w, h, stroke, fill_brush, sw):
        # Y-junction
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(6, 6); path.lineTo(w/2-2, h/2-2); path.lineTo(6, h-6)
        p.drawPath(path)
        path2 = QPainterPath()
        path2.moveTo(6, 6); path2.lineTo(w/2-2, h/2-2); path2.lineTo(w-6, h/2)
        p.drawPath(path2)
        path3 = QPainterPath()
        path3.moveTo(6, h-6); path3.lineTo(w/2-2, h/2+2); path3.lineTo(w-6, h/2)
        p.drawPath(path3)
        # junction circle
        p.setBrush(fill_brush)
        p.drawEllipse(QPointF(w/2-1, h/2), 4.0, 4.0)

    @staticmethod
    def _draw_separador(p, w, h, stroke, fill_brush, sw):
        # vertical flash drum: body rect + domes
        p.drawRect(QRectF(w/2-15, 10, 30, h-20))
        p.drawEllipse(QPointF(w/2, 10), 15.0, 5.0)
        p.drawEllipse(QPointF(w/2, h-10), 15.0, 5.0)
        # demister hash
        ghost = QColor(stroke); ghost.setAlphaF(0.4)
        p.setPen(QPen(ghost, 1.0)); p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(w/2-8, 16), QPointF(w/2+8, 16))
        p.drawLine(QPointF(w/2-8, 18), QPointF(w/2+8, 18))
        # liquid level dashed
        ghost2 = QColor(stroke); ghost2.setAlphaF(0.4)
        p.setPen(QPen(ghost2, 1.0))
        p.drawLine(QPointF(w/2-13, h-22), QPointF(w/2+13, h-22))
        # droplet circles
        p.setBrush(ghost2); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(w/2-6, h-18), 1.0, 1.0)
        p.drawEllipse(QPointF(w/2+4, h-14), 1.0, 1.0)

    @staticmethod
    def _draw_columna(p, w, h, stroke, fill_brush, sw):
        # rectángulo alto + 7 trays horizontales
        p.drawRoundedRect(QRectF(w/2-12, 6, 24, h-12), 2, 2)
        ghost = QColor(stroke); ghost.setAlphaF(0.55)
        p.setPen(QPen(ghost, 0.9)); p.setBrush(Qt.NoBrush)
        for i in range(7):
            y = 12 + i * ((h - 22) / 6)
            p.drawLine(QPointF(w/2-9, y), QPointF(w/2+9, y))
        # feed indicator
        p.setPen(QPen(stroke, 1.2))
        p.drawLine(QPointF(w/2-12, h/2), QPointF(w/2-16, h/2))

    @staticmethod
    def _draw_hx(p, w, h, stroke, fill_brush, sw):
        # shell horizontal (rounded rect)
        p.drawRoundedRect(QRectF(6, h/2-12, w-12, 24), 4, 4)
        # end caps (light)
        ghost = QColor(stroke); ghost.setAlphaF(0.5)
        p.setPen(QPen(ghost, 1.0)); p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(14, h/2-12), QPointF(14, h/2+12))
        p.drawLine(QPointF(w-14, h/2-12), QPointF(w-14, h/2+12))
        # tube bundle (3 squiggles)
        ghost2 = QColor(stroke); ghost2.setAlphaF(0.6)
        p.setPen(QPen(ghost2, 1.0))
        # path 1
        path = QPainterPath()
        path.moveTo(14, h/2-5)
        path.quadTo(w/2, h/2 - 5 - 7, w-14, h/2-5)
        p.drawPath(path)
        # path 2
        path2 = QPainterPath()
        path2.moveTo(14, h/2)
        path2.quadTo(w/2, h/2 - 5, w-14, h/2)
        p.drawPath(path2)
        # path 3
        path3 = QPainterPath()
        path3.moveTo(14, h/2+5)
        path3.quadTo(w/2, h/2 + 5 - 3, w-14, h/2+5)
        p.drawPath(path3)
        # utility ports
        p.setPen(QPen(stroke, 1.2))
        p.drawLine(QPointF(w/2-12, h/2-12), QPointF(w/2-12, h/2-16))
        p.drawLine(QPointF(w/2+12, h/2+12), QPointF(w/2+12, h/2+16))

    @staticmethod
    def _draw_bomba(p, w, h, stroke, fill_brush, sw):
        # círculo + triángulo direccional
        r = min(w, h)/2 - 6
        p.drawEllipse(QPointF(w/2, h/2), r, r)
        # triangle (filled translucent)
        tri = QPolygonF([
            QPointF(w/2-6, h/2-7),
            QPointF(w/2+8, h/2),
            QPointF(w/2-6, h/2+7),
        ])
        tri_fill = QColor(stroke); tri_fill.setAlphaF(0.18)
        p.setBrush(tri_fill); p.setPen(Qt.NoPen)
        p.drawPolygon(tri)
        # shaft center
        p.setBrush(stroke); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(w/2-1, h/2), 2.0, 2.0)
        # base
        p.setPen(QPen(stroke, 1.2))
        p.drawLine(QPointF(w/2-10, h-4), QPointF(w/2+10, h-4))

    @staticmethod
    def _draw_tanque(p, w, h, stroke, fill_brush, sw):
        # storage tank — dome top + body + dish bottom
        p.drawEllipse(QPointF(w/2, 10), (w-12)/2, 5.0)
        # body
        path = QPainterPath()
        path.moveTo(6, 10)
        path.lineTo(6, h-8)
        path.quadTo(w/2, h-2, w-6, h-8)
        path.lineTo(w-6, 10)
        p.drawPath(path)
        # level line dashed
        ghost = QColor(stroke); ghost.setAlphaF(0.35)
        dpen = QPen(ghost, 1.0); dpen.setStyle(Qt.DashLine)
        p.setPen(dpen); p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(9, h/2+4), QPointF(w-9, h/2+4))
        # manhole rect
        ghost2 = QColor(stroke); ghost2.setAlphaF(0.5)
        p.setPen(QPen(ghost2, 1.0))
        p.drawRect(QRectF(w/2-3, 6, 6, 4))


# ════════════════════════════════════════════════════════
#  EDITOR TOPBAR
# ════════════════════════════════════════════════════════

class EditorTopbar(QFrame):
    """Barra superior 52px, fondo blanco con borde inferior, tipografía
    IBM Plex Sans.  Tres regiones:

      izquierda: logo (◆) + nombre del proyecto + sub
      centro:    undo / redo (divider) auto-arrange / grid
      derecha:   chip de solver + "Validar DOF" + "▶ Resolver"

    El topbar es REACTIVE: actualiza el chip cuando la ventana llama
    a `set_solver_state(state, iter, dt)`.
    """

    undoRequested        = Signal()
    redoRequested        = Signal()
    autoArrangeRequested = Signal()
    gridToggled          = Signal()
    validateRequested    = Signal()
    solveRequested       = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("edTopbar")
        self.setFixedHeight(52)
        self.setStyleSheet(
            f"#edTopbar {{ background: {TOK['bg_elev']}; "
            f"border-bottom: 1px solid {TOK['line']}; }}"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 6, 12, 6)
        lay.setSpacing(8)

        # ── IZQUIERDA: logo + project ──
        self._logo = QLabel(self)
        self._logo.setFixedSize(28, 28)
        self._logo.setAlignment(Qt.AlignCenter)
        f = QFont(pfd_fonts.SANS, 14, QFont.Bold)
        self._logo.setFont(f)
        self._logo.setText("◆")
        self._logo.setStyleSheet(
            f"color:{TOK['accent']}; background:{TOK['accent_tint']}; "
            f"border-radius:8px; border:1px solid {TOK['accent_soft']};"
        )
        lay.addWidget(self._logo)

        proj = QVBoxLayout(); proj.setContentsMargins(0,0,0,0); proj.setSpacing(0)
        self._project = QLabel("(sin nombre)", self)
        self._project.setFont(QFont(pfd_fonts.MONO, 10, QFont.Medium))
        self._project.setStyleSheet(f"color:{TOK['ink']};")
        self._sub = QLabel("v0.4 · sin guardar", self)
        sf = QFont(pfd_fonts.SANS, 8); self._sub.setFont(sf)
        self._sub.setStyleSheet(f"color:{TOK['ink_soft']};")
        proj.addWidget(self._project); proj.addWidget(self._sub)
        lay.addLayout(proj)

        lay.addStretch(1)

        # ── CENTRO: undo / redo / auto-arrange / grid ──
        mid = QHBoxLayout(); mid.setSpacing(2)
        self._btn_undo = self._mk_icon_btn("↶", "Deshacer (⌘Z)")
        self._btn_undo.clicked.connect(self.undoRequested.emit)
        mid.addWidget(self._btn_undo)
        self._btn_redo = self._mk_icon_btn("↷", "Rehacer (⌘⇧Z)")
        self._btn_redo.clicked.connect(self.redoRequested.emit)
        mid.addWidget(self._btn_redo)
        mid.addWidget(self._mk_vdivider())
        self._btn_arrange = self._mk_icon_btn("✦", "Auto-arrange")
        self._btn_arrange.clicked.connect(self.autoArrangeRequested.emit)
        mid.addWidget(self._btn_arrange)
        self._btn_grid = self._mk_icon_btn("▦", "Toggle grid")
        self._btn_grid.setCheckable(True); self._btn_grid.setChecked(True)
        self._btn_grid.clicked.connect(self.gridToggled.emit)
        mid.addWidget(self._btn_grid)
        lay.addLayout(mid)

        lay.addStretch(1)

        # ── DERECHA: solver chip + Validar + Resolver ──
        self._solver_chip = QFrame(self); self._solver_chip.setObjectName("solverChip")
        sc_lay = QHBoxLayout(self._solver_chip)
        sc_lay.setContentsMargins(8, 4, 12, 4); sc_lay.setSpacing(6)
        self._solver_dot = QLabel(self._solver_chip)
        self._solver_dot.setFixedSize(8, 8)
        sc_lay.addWidget(self._solver_dot)
        self._solver_label = QLabel("en espera", self._solver_chip)
        self._solver_label.setFont(QFont(pfd_fonts.SANS, 9, QFont.Medium))
        sc_lay.addWidget(self._solver_label)
        self._solver_meta = QLabel("", self._solver_chip)
        self._solver_meta.setFont(QFont(pfd_fonts.MONO, 8))
        self._solver_meta.setStyleSheet(f"color:{TOK['ink_soft']};")
        sc_lay.addWidget(self._solver_meta)
        lay.addWidget(self._solver_chip)
        self.set_solver_state("idle")

        lay.addWidget(self._mk_vdivider())

        self._btn_validate = self._mk_ghost_btn("Validar DOF")
        self._btn_validate.clicked.connect(self.validateRequested.emit)
        lay.addWidget(self._btn_validate)

        self._btn_solve = self._mk_primary_btn("▶  Resolver")
        self._btn_solve.clicked.connect(self.solveRequested.emit)
        lay.addWidget(self._btn_solve)

    # ── helpers UI ─────────────────────────────────────
    def _mk_icon_btn(self, glyph: str, tooltip: str) -> QToolButton:
        b = QToolButton(self)
        b.setText(glyph)
        b.setToolTip(tooltip)
        b.setFixedSize(32, 32)
        b.setCursor(Qt.PointingHandCursor)
        b.setFont(QFont(pfd_fonts.SANS, 14))
        b.setStyleSheet(
            f"QToolButton {{ background: transparent; color: {TOK['ink_mute']}; "
            f"border: 0; border-radius: 6px; }} "
            f"QToolButton:hover {{ background: {TOK['bg_mute']}; color: {TOK['ink']}; }} "
            f"QToolButton:checked {{ background: {TOK['accent_tint']}; color: {TOK['accent_deep']}; }} "
            f"QToolButton:disabled {{ color: {TOK['ink_ghost']}; }}"
        )
        return b

    def _mk_vdivider(self) -> QFrame:
        d = QFrame(self); d.setFrameShape(QFrame.VLine)
        d.setFixedWidth(1); d.setFixedHeight(24)
        d.setStyleSheet(f"color:{TOK['line']}; background:{TOK['line']};")
        return d

    def _mk_ghost_btn(self, text: str) -> QPushButton:
        b = QPushButton(text, self)
        b.setCursor(Qt.PointingHandCursor)
        b.setFont(QFont(pfd_fonts.SANS, 9, QFont.Medium))
        b.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {TOK['ink_mute']}; "
            f"border: 1px solid {TOK['line_strong']}; border-radius: 6px; "
            f"padding: 6px 12px; }} "
            f"QPushButton:hover {{ background: {TOK['bg_mute']}; "
            f"color: {TOK['ink']}; border-color: {TOK['accent_soft']}; }}"
        )
        return b

    def _mk_primary_btn(self, text: str) -> QPushButton:
        b = QPushButton(text, self)
        b.setCursor(Qt.PointingHandCursor)
        b.setFont(QFont(pfd_fonts.SANS, 9, QFont.Bold))
        b.setStyleSheet(
            f"QPushButton {{ background: {TOK['accent']}; color: white; "
            f"border: 0; border-radius: 6px; padding: 7px 14px; }} "
            f"QPushButton:hover {{ background: {TOK['accent_deep']}; }}"
        )
        return b

    # ── API pública ────────────────────────────────────
    def set_project(self, name: str, sub: str = ""):
        self._project.setText(name or "(sin nombre)")
        if sub:
            self._sub.setText(sub)

    def set_solver_state(self, state: str, iter_: int = 0, dt: float = 0.0):
        """state ∈ {'idle', 'running', 'converged', 'warning', 'failed', 'stale'}."""
        color_map = {
            "idle":      TOK["ink_soft"],
            "running":   TOK["amber"],
            "converged": TOK["green"],
            "warning":   TOK["amber"],
            "failed":    TOK["danger"],
            "stale":     TOK["spec"],
        }
        bg_map = {
            "idle":      TOK["bg_mute"],
            "running":   TOK["amber_bg"],
            "converged": TOK["green_bg"],
            "warning":   TOK["amber_bg"],
            "failed":    TOK["danger_bg"],
            "stale":     TOK["spec_bg"],
        }
        label_map = {
            "idle":      "en espera",
            "running":   "resolviendo…",
            "converged": "convergido",
            "warning":   "convergido con warnings",
            "failed":    "falla — revisar DOF",
            "stale":     "datos stale — re-ejecutar",
        }
        color = color_map.get(state, TOK["ink_soft"])
        bg = bg_map.get(state, TOK["bg_mute"])
        label = label_map.get(state, state)
        self._solver_dot.setStyleSheet(
            f"background:{color}; border-radius:4px;"
        )
        self._solver_label.setText(label)
        self._solver_label.setStyleSheet(f"color:{color}; font-weight:500;")
        if state == "converged" and iter_:
            self._solver_meta.setText(f"· {iter_} iter · {dt:.1f}s")
            self._solver_meta.setVisible(True)
        elif state == "running" and iter_:
            self._solver_meta.setText(f"· iter {iter_}")
            self._solver_meta.setVisible(True)
        else:
            self._solver_meta.setVisible(False)
        self._solver_chip.setStyleSheet(
            f"#solverChip {{ background:{bg}; border-radius:14px; }}"
        )

    def set_undo_enabled(self, can_undo: bool, can_redo: bool):
        self._btn_undo.setEnabled(can_undo)
        self._btn_redo.setEnabled(can_redo)


# ════════════════════════════════════════════════════════
#  EDITOR PALETTE — vertical floating
# ════════════════════════════════════════════════════════

class _ToolButton(QToolButton):
    """Botón de paleta (tool o block).  Pinta su contenido custom."""

    def __init__(self, kind: str, ident: str, tooltip: str,
                 active: bool = False, parent=None):
        super().__init__(parent)
        self._kind = kind   # "tool" | "block"
        self._id = ident
        self._active = active
        self.setToolTip(tooltip)
        self.setFixedSize(40, 40)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style()

    def ident(self) -> str:
        return self._id

    def set_active(self, on: bool):
        self._active = on
        self._apply_style()
        self.update()

    def _apply_style(self):
        if self._active:
            bg = TOK["accent"]
            self._stroke = QColor("white")
            self._cinta = TOK["accent_deep"]
        else:
            bg = "transparent"
            self._stroke = QColor(TOK["ink_mute"])
            self._cinta = None
        self.setStyleSheet(
            f"QToolButton {{ background: {bg}; border: 0; border-radius: 8px; }} "
            f"QToolButton:hover {{ background: "
            f"{TOK['bg_mute'] if not self._active else TOK['accent_deep']}; }}"
        )

    def paintEvent(self, ev):
        # Pintar el fondo (vía stylesheet) primero
        from PySide6.QtWidgets import QStyleOption, QStyle
        opt = QStyleOption(); opt.initFrom(self)
        p = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, p, self)

        # cinta lateral si activo
        if self._active and self._cinta:
            p.fillRect(QRect(0, 6, 3, self.height()-12), QColor(self._cinta))

        if self._kind == "block":
            # silueta ISA
            w, h = BLOCK_DIMS.get(self._id, (40, 30))
            # escalar a 30px max
            box_w, box_h = self.width()-12, self.height()-12
            scale = min(box_w / w, box_h / h, 0.5)  # cap a 0.5x para que entre cómodo
            sw, sh = int(w * scale), int(h * scale)
            ox = (self.width() - sw) // 2
            oy = (self.height() - sh) // 2
            p.save()
            p.translate(ox, oy)
            p.scale(scale, scale)
            BlockGlyph.draw(p, self._id, w, h, self._stroke,
                            fill=None if not self._active else QColor(0,0,0,0),
                            stroke_width=2.0)
            p.restore()
        else:
            # tool icon — usar glyphs unicode minimalistas
            p.setPen(QPen(self._stroke, 1.6))
            p.setFont(QFont(pfd_fonts.SANS, 14, QFont.Medium))
            glyph = {
                "select":  "↖",
                "pan":     "✋",
                "connect": "⟶",
                "text":    "T",
            }.get(self._id, "?")
            p.drawText(self.rect(), Qt.AlignCenter, glyph)


class EditorPalette(QFrame):
    """Paleta vertical flotante (50px).  Tools arriba, 7 bloques abajo.

    Las señales `toolSelected(id)` y `blockRequested(id)` notifican al
    parent.  Para el block library, el flowsheet decide si crear el
    bloque al click (V1) o al drag (futuro).
    """

    toolSelected    = Signal(str)
    blockRequested  = Signal(str)
    moreRequested   = Signal()

    TOOLS = [
        ("select",  "Seleccionar (V)"),
        ("pan",     "Pan (espacio)"),
        ("connect", "Conectar stream (C)"),
        ("text",    "Anotación (T)"),
    ]
    BLOCKS = ["reactor", "mezclador", "separador", "columna",
              "hx", "bomba", "tanque"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("edPalette")
        self.setFixedWidth(50)
        self.setStyleSheet(
            f"#edPalette {{ background: {TOK['bg_elev']}; "
            f"border: 1px solid {TOK['line']}; border-radius: 12px; }}"
        )
        # Shadow effect — usar QGraphicsDropShadow
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtCore import Qt as _Qt
            sh = QGraphicsDropShadowEffect(self)
            sh.setBlurRadius(28)
            sh.setOffset(0, 6)
            c = QColor(40, 30, 20); c.setAlphaF(0.12)
            sh.setColor(c)
            self.setGraphicsEffect(sh)
        except Exception:
            pass

        lay = QVBoxLayout(self)
        lay.setContentsMargins(5, 8, 5, 8); lay.setSpacing(2)

        self._tool_btns: Dict[str, _ToolButton] = {}
        self._active_tool = "select"
        for tid, tip in self.TOOLS:
            b = _ToolButton("tool", tid, tip, active=(tid == "select"), parent=self)
            b.clicked.connect(lambda _=False, k=tid: self._on_tool_click(k))
            self._tool_btns[tid] = b
            lay.addWidget(b, alignment=Qt.AlignHCenter)

        lay.addWidget(self._mk_divider())

        self._block_btns: Dict[str, _ToolButton] = {}
        for bid in self.BLOCKS:
            b = _ToolButton("block", bid, PALETTE_LABELS.get(bid, bid), parent=self)
            b.clicked.connect(lambda _=False, k=bid: self.blockRequested.emit(k))
            self._block_btns[bid] = b
            lay.addWidget(b, alignment=Qt.AlignHCenter)

        lay.addWidget(self._mk_divider())

        plus = QToolButton(self)
        plus.setText("+"); plus.setFixedSize(40, 32)
        plus.setCursor(Qt.PointingHandCursor)
        plus.setFont(QFont(pfd_fonts.SANS, 16, QFont.Bold))
        plus.setToolTip("Más equipos (válvula, splitter, …)")
        plus.setStyleSheet(
            f"QToolButton {{ background: transparent; color: {TOK['ink_mute']}; "
            f"border: 0; border-radius: 6px; }} "
            f"QToolButton:hover {{ background: {TOK['bg_mute']}; color: {TOK['ink']}; }}"
        )
        plus.clicked.connect(self.moreRequested.emit)
        lay.addWidget(plus, alignment=Qt.AlignHCenter)

        lay.addStretch(1)

    def _mk_divider(self) -> QFrame:
        d = QFrame(self); d.setFixedHeight(1)
        d.setStyleSheet(f"background:{TOK['line']};")
        return d

    def _on_tool_click(self, tool_id: str):
        # Actualizar visualmente cuál está activo
        if self._active_tool == tool_id:
            return
        self._tool_btns[self._active_tool].set_active(False)
        self._active_tool = tool_id
        self._tool_btns[tool_id].set_active(True)
        self.toolSelected.emit(tool_id)

    def set_active_tool(self, tool_id: str):
        if tool_id in self._tool_btns:
            self._on_tool_click(tool_id)


# ════════════════════════════════════════════════════════
#  EDITOR ZOOM — bottom-right floating
# ════════════════════════════════════════════════════════

class EditorZoom(QFrame):
    """Control de zoom flotante: − [100%] + ⤢."""

    zoomInRequested  = Signal()
    zoomOutRequested = Signal()
    zoomResetRequested = Signal()
    zoomFitRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("edZoom")
        self.setStyleSheet(
            f"#edZoom {{ background: {TOK['bg_elev']}; "
            f"border: 1px solid {TOK['line']}; border-radius: 10px; }}"
        )
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            sh = QGraphicsDropShadowEffect(self)
            sh.setBlurRadius(20); sh.setOffset(0, 4)
            c = QColor(40, 30, 20); c.setAlphaF(0.12); sh.setColor(c)
            self.setGraphicsEffect(sh)
        except Exception:
            pass

        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 3, 4, 3); lay.setSpacing(0)

        self._btn_minus = self._mk_btn("−", "Zoom out (⌘−)")
        self._btn_minus.clicked.connect(self.zoomOutRequested.emit)
        lay.addWidget(self._btn_minus)

        self._lbl_pct = QToolButton(self)
        self._lbl_pct.setText("100%")
        self._lbl_pct.setFixedSize(54, 28)
        self._lbl_pct.setCursor(Qt.PointingHandCursor)
        self._lbl_pct.setFont(QFont(pfd_fonts.MONO, 9, QFont.Medium))
        self._lbl_pct.setToolTip("Click → 100% (⌘0)")
        self._lbl_pct.setStyleSheet(
            f"QToolButton {{ background: transparent; color: {TOK['ink']}; "
            f"border: 0; }} "
            f"QToolButton:hover {{ background: {TOK['bg_mute']}; "
            f"border-radius:6px; }}"
        )
        self._lbl_pct.clicked.connect(self.zoomResetRequested.emit)
        lay.addWidget(self._lbl_pct)

        self._btn_plus = self._mk_btn("+", "Zoom in (⌘+)")
        self._btn_plus.clicked.connect(self.zoomInRequested.emit)
        lay.addWidget(self._btn_plus)

        # divider
        d = QFrame(self); d.setFixedWidth(1); d.setFixedHeight(20)
        d.setStyleSheet(f"background:{TOK['line']};")
        lay.addSpacing(4); lay.addWidget(d); lay.addSpacing(4)

        self._btn_fit = self._mk_btn("⤢", "Ajustar a vista (F)")
        self._btn_fit.clicked.connect(self.zoomFitRequested.emit)
        lay.addWidget(self._btn_fit)

        self.setFixedHeight(34)
        self.adjustSize()

    def _mk_btn(self, glyph: str, tip: str) -> QToolButton:
        b = QToolButton(self)
        b.setText(glyph); b.setToolTip(tip)
        b.setFixedSize(28, 28)
        b.setCursor(Qt.PointingHandCursor)
        b.setFont(QFont(pfd_fonts.SANS, 13, QFont.Medium))
        b.setStyleSheet(
            f"QToolButton {{ background: transparent; color: {TOK['ink_mute']}; "
            f"border: 0; border-radius: 6px; }} "
            f"QToolButton:hover {{ background: {TOK['bg_mute']}; color: {TOK['ink']}; }}"
        )
        return b

    def set_zoom(self, factor: float):
        self._lbl_pct.setText(f"{int(round(factor * 100))}%")


# ════════════════════════════════════════════════════════
#  OVERLAY HELPER
# ════════════════════════════════════════════════════════

class _Overlay(QWidget):
    """Widget transparente que actúa como contenedor de overlays
    (paleta + zoom) sobre el viewport del QGraphicsView.

    Re-posiciona sus hijos en resizeEvent del padre via instalación
    de event filter.  Mantiene a la paleta arriba-izquierda y al
    zoom abajo-derecha.
    """

    def __init__(self, host: QGraphicsView, palette: EditorPalette,
                 zoom: EditorZoom):
        super().__init__(host.viewport())
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._host = host
        self._palette = palette
        self._zoom = zoom
        # parent each to host.viewport() so they render on top
        palette.setParent(host.viewport())
        zoom.setParent(host.viewport())
        palette.show(); zoom.show()
        palette.raise_(); zoom.raise_()
        # observar tanto el view como su viewport: en QGraphicsView el
        # Resize externo le llega al view, no siempre al viewport.
        host.installEventFilter(self)
        host.viewport().installEventFilter(self)
        # Diferir el primer reposition (algunos platforms ofreceen el
        # tamaño real solo después del primer paint)
        QTimer.singleShot(0, self._reposition)
        self._reposition()

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        if ev.type() in (QEvent.Resize, QEvent.Show, QEvent.LayoutRequest):
            self._reposition()
        return False

    def _reposition(self):
        vp = self._host.viewport()
        # paleta arriba izquierda, con margen
        self._palette.adjustSize()
        self._palette.move(14, 14)
        self._palette.raise_()
        # zoom abajo derecha
        self._zoom.adjustSize()
        z = self._zoom.size()
        self._zoom.move(max(14, vp.width()  - z.width()  - 14),
                        max(14, vp.height() - z.height() - 14))
        self._zoom.raise_()
