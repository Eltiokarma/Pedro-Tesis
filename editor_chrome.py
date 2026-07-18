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

import math
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import (
    Qt, Signal, QSize, QRect, QRectF, QPointF, QTimer, QMimeData, QByteArray,
)
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QPainterPath, QPolygonF,
    QFontMetrics, QMouseEvent, QDrag, QPixmap,
)
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QToolButton,
    QFrame, QSizePolicy, QButtonGroup, QGraphicsView, QApplication,
    QGraphicsItem, QGraphicsObject, QStyleOptionGraphicsItem,
)

import pfd_fonts
from tokens import (qfont, FONT_TITLE, FONT_UI, FONT_VALUE, FONT_HINT,
                    FONT_LABEL)
from block_inspector import TOK
import glyph_specs


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
    "ambient":    (52, 40),
    # Siluetas específicas (antes colapsaban en las 8 de arriba y los
    # equipos se dibujaban con un símbolo genérico o incorrecto).
    "valvula":    (56, 44),
    "compresor":  (64, 48),
    "ventilador": (56, 52),
    "horno":      (56, 68),
    "caldera":    (64, 56),
    "ciclon":     (48, 68),
    "torre_enf":  (56, 64),
    "platos":     (48, 64),
    "tambor":     (76, 44),
    "centrifuga": (60, 50),
    "filtro":     (52, 60),
    "secador":    (80, 44),
    # Variantes de HX con geometría propia + cristalizador.  Aspect
    # ratio ≈ content_bbox del símbolo pfd_symbols equivalente
    # (hx-kettle 160×90, hx-air-cooled 140×100, hx-plate 100×90,
    # crystallizer 80×120).
    "hx_kettle":     (84, 52),
    "hx_aircooler":  (70, 52),
    "hx_placa":      (56, 50),
    "cristalizador": (52, 76),
    # Rediseño 1d: seis parejas que compartían glifo e invertían o
    # borraban semántica.  Geometría de referencia: patch PFD-ICN-002
    # de pfd_symbols (splitter-flow-divider, reactor-pfr-coiled,
    # compressor-reciprocating, whb steam drum, packing-random,
    # cooling-tower-natural).
    "splitter":        (56, 44),
    "reactor_pfr":     (76, 46),
    "compresor_recip": (64, 48),
    "hx_whb":          (84, 56),
    "empaque":         (48, 64),
    "torre_nat":       (56, 64),
}

# Ciclo 3 (artboard 3a): el set completo de Design reemplaza las dims
# de las siluetas que refresca y agrega las variantes nuevas.  Las
# dims derivan del bbox del contenido (la escala interna del set ya
# armoniza los tamaños relativos); las entradas legacy no cubiertas
# (reactor/tanque/valvula base, ambient…) quedan como fallback de la
# heurística.
BLOCK_DIMS.update({name: glyph_specs.glyph_dims(name)
                   for name in glyph_specs.GLYPHS})

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

def _palette_glyph_id(palette_id: str) -> str:
    """Glifo que muestra un botón de la paleta: el del eq_type que
    instancia (así el botón enseña el set del ciclo 3), con fallback
    al id del botón para tools/ids sin eq_type."""
    eq = PALETTE_TO_EQ_TYPE.get(palette_id)
    if eq:
        isa = isa_type_for_eq(eq)
        if isa:
            return isa
    return palette_id


PALETTE_LABELS: Dict[str, str] = {
    "reactor":   "Reactor",
    "mezclador": "Mezclador",
    "separador": "Separador / Flash",
    "columna":   "Columna",
    "hx":        "Intercambiador",
    "bomba":     "Bomba",
    "tanque":    "Tanque",
}

# Siluetas ISA que cuelgan de cada botón de la paleta.  Los tipos que
# no tienen botón propio (válvula, compresor, ciclón, …) se agrupan
# bajo el botón temáticamente más cercano para que TODO el catálogo
# siga siendo alcanzable desde los menús de variantes (long-press).
PALETTE_GROUPS: Dict[str, Tuple[str, ...]] = {
    "reactor":   ("reactor", "reactor_cstr", "reactor_jacket",
                  "reactor_jacket_na", "reactor_autoclave",
                  "reactor_pfr"),
    "mezclador": ("mezclador", "splitter", "valvula", "valvula_globe",
                  "valvula_3way", "valvula_relief"),
    "separador": ("separador", "tambor", "ciclon", "centrifuga",
                  "centrifuga_decanter", "centrifuga_disc",
                  "filtro", "secador", "cristalizador", "evaporador"),
    "columna":   ("columna", "platos", "platos_sieve", "platos_valve",
                  "empaque", "empaque_rand", "empaque_struct",
                  "torre_enf", "torre_nat"),
    "hx":        ("hx", "hx_kettle", "hx_whb", "hx_aircooler",
                  "hx_cond_air", "hx_placa", "hx_espiral", "horno",
                  "horno_reformer", "caldera", "caldera_fire",
                  "caldera_water"),
    "bomba":     ("bomba", "bomba_pd", "bomba_recip", "compresor",
                  "compresor_axial", "compresor_rotary",
                  "compresor_recip", "ventilador", "ventilador_rad"),
    "tanque":    ("tanque", "tanque_cone", "tanque_float", "ambient"),
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
             stroke_width: float = 1.6, dashed: bool = False):
        pen = QPen(stroke, stroke_width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        if dashed:
            # contorno punteado — estado "unrun" en el propio glifo (1b)
            pen.setStyle(Qt.DashLine)
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
    def _draw_splitter(p, w, h, stroke, fill_brush, sw):
        # divisor de flujo 1→2 — espejo del mixer (rediseño 1d: antes el
        # splitter se dibujaba como mixer y la semántica quedaba invertida)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(6, h/2); path.lineTo(w/2+2, h/2)
        p.drawPath(path)
        path2 = QPainterPath()
        path2.moveTo(w/2+2, h/2); path2.lineTo(w-6, 6)
        p.drawPath(path2)
        path3 = QPainterPath()
        path3.moveTo(w/2+2, h/2); path3.lineTo(w-6, h-6)
        p.drawPath(path3)
        # flechitas de salida (semántica divergente explícita)
        ghost = QColor(stroke); ghost.setAlphaF(0.7)
        p.setPen(QPen(ghost, 1.0))
        p.drawLine(QPointF(w-11, 6), QPointF(w-6, 6))
        p.drawLine(QPointF(w-6, 6), QPointF(w-9, 10))
        p.drawLine(QPointF(w-11, h-6), QPointF(w-6, h-6))
        p.drawLine(QPointF(w-6, h-6), QPointF(w-9, h-10))
        # nodo de división
        p.setPen(QPen(stroke, sw))
        p.setBrush(fill_brush)
        p.drawEllipse(QPointF(w/2+1, h/2), 4.0, 4.0)

    @staticmethod
    def _draw_reactor_pfr(p, w, h, stroke, fill_brush, sw):
        # PFR tubular — carcasa horizontal + serpentín (ref
        # reactor-pfr-coiled): distinto del CSTR agitado
        p.drawRoundedRect(QRectF(6, h/2-14, w-12, 28), 6, 6)
        # serpentín: 4 lazos
        coil = QColor(stroke); coil.setAlphaF(0.75)
        p.setPen(QPen(coil, 1.0)); p.setBrush(Qt.NoBrush)
        n = 4
        x0, x1 = 14.0, w - 14.0
        span = (x1 - x0) / n
        path = QPainterPath()
        path.moveTo(x0, h/2)
        for i in range(n):
            cx = x0 + span * (i + 0.5)
            path.quadTo(cx, h/2 - 22, x0 + span * (i + 1), h/2)
            path.quadTo(cx, h/2 + 22, x0 + span * (i + 0.55), h/2)
        p.drawPath(path)
        # flechita de flujo
        p.setPen(QPen(stroke, 1.2))
        p.drawLine(QPointF(x1 - 2, h/2), QPointF(x1 + 4, h/2))

    @staticmethod
    def _draw_compresor_recip(p, w, h, stroke, fill_brush, sw):
        # compresor recíproco — cilindro + pistón + biela y cigüeñal
        # (antes los 4 tipos de compresor compartían el glifo centrífugo)
        p.drawRect(QRectF(6, h/2-11, w*0.52, 22))
        # pistón dentro del cilindro
        ghost = QColor(stroke); ghost.setAlphaF(0.6)
        p.setPen(QPen(ghost, 1.2)); p.setBrush(Qt.NoBrush)
        px_ = 6 + w*0.52*0.45
        p.drawLine(QPointF(px_, h/2-8), QPointF(px_, h/2+8))
        # biela
        p.setPen(QPen(stroke, 1.2))
        crank_x = w - 13
        p.drawLine(QPointF(px_, h/2), QPointF(crank_x - 4, h/2))
        # cigüeñal (círculo)
        p.setBrush(fill_brush)
        p.drawEllipse(QPointF(crank_x, h/2), 7.0, 7.0)
        p.setBrush(stroke); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(crank_x - 3, h/2 - 3), 1.6, 1.6)
        # base
        p.setPen(QPen(stroke, 1.2))
        p.drawLine(QPointF(10, h-4), QPointF(w-10, h-4))

    @staticmethod
    def _draw_hx_whb(p, w, h, stroke, fill_brush, sw):
        # waste-heat boiler — carcasa kettle + STEAM DRUM superior con
        # salida de vapor (ref whb steam drum): distinto del kettle
        drum_h = 12.0
        # carcasa principal (gases calientes)
        p.drawRoundedRect(QRectF(6, drum_h + 8, w-12, h - drum_h - 16), 6, 6)
        # steam drum arriba
        p.drawRoundedRect(QRectF(w/2-16, 2, 32, drum_h), 6, 6)
        # bajantes drum↔shell
        ghost = QColor(stroke); ghost.setAlphaF(0.6)
        p.setPen(QPen(ghost, 1.0)); p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(w/2-9, drum_h + 2), QPointF(w/2-9, drum_h + 8))
        p.drawLine(QPointF(w/2+9, drum_h + 2), QPointF(w/2+9, drum_h + 8))
        # tubos de gas (2 líneas)
        p.drawLine(QPointF(12, h/2 + 4), QPointF(w-12, h/2 + 4))
        p.drawLine(QPointF(12, h/2 + 9), QPointF(w-12, h/2 + 9))
        # salida de vapor del drum
        p.setPen(QPen(stroke, 1.2))
        p.drawLine(QPointF(w/2, 2), QPointF(w/2, -3))
        # nivel de agua en el drum
        lvl = QColor(stroke); lvl.setAlphaF(0.4)
        p.setPen(QPen(lvl, 1.0))
        p.drawLine(QPointF(w/2-13, drum_h - 3), QPointF(w/2+13, drum_h - 3))

    @staticmethod
    def _draw_empaque(p, w, h, stroke, fill_brush, sw):
        # sección de columna EMPACADA — hatch diagonal (ref
        # packing-random/structured): distinto de la de platos
        p.drawRoundedRect(QRectF(w/2-12, 6, 24, h-12), 2, 2)
        ghost = QColor(stroke); ghost.setAlphaF(0.55)
        p.setPen(QPen(ghost, 0.9)); p.setBrush(Qt.NoBrush)
        # hatch ↘ dentro del cuerpo (entre y=14 y h-14)
        y0, y1 = 14.0, h - 14.0
        step = (y1 - y0) / 4
        for i in range(5):
            y = y0 + i * step
            p.drawLine(QPointF(w/2-9, y), QPointF(w/2+9, y + step*0.7))
        # límites del lecho
        p.setPen(QPen(ghost, 1.1))
        p.drawLine(QPointF(w/2-11, y0), QPointF(w/2+11, y0))
        p.drawLine(QPointF(w/2-11, y1 + step*0.7), QPointF(w/2+11, y1 + step*0.7))

    @staticmethod
    def _draw_torre_nat(p, w, h, stroke, fill_brush, sw):
        # torre de enfriamiento de TIRO NATURAL — hiperboloide (ref
        # cooling-tower-natural): distinta de la inducida con ventilador
        p.setBrush(fill_brush)
        path = QPainterPath()
        path.moveTo(w/2-18, h-6)
        path.cubicTo(w/2-8, h*0.55, w/2-8, h*0.35, w/2-12, 8)
        path.lineTo(w/2+12, 8)
        path.cubicTo(w/2+8, h*0.35, w/2+8, h*0.55, w/2+18, h-6)
        path.closeSubpath()
        p.drawPath(path)
        # pluma de vapor
        ghost = QColor(stroke); ghost.setAlphaF(0.5)
        p.setPen(QPen(ghost, 1.0)); p.setBrush(Qt.NoBrush)
        wisp = QPainterPath()
        wisp.moveTo(w/2-6, 6)
        wisp.quadTo(w/2-2, 1, w/2+3, 4)
        p.drawPath(wisp)
        # agua en la base
        p.drawLine(QPointF(w/2-14, h-9), QPointF(w/2+14, h-9))

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

    @staticmethod
    def _draw_ambient(p, w, h, stroke, fill_brush, sw):
        # Atmósfera: nube (source/sink de aire, chimenea, blowdown, etc.).
        # Silueta de nube = unión de lóbulos circulares sobre una base.
        cx = w / 2.0
        cy = h * 0.58
        r = min(w, h) * 0.20
        cloud = QPainterPath()
        cloud.setFillRule(Qt.WindingFill)
        cloud.addEllipse(QPointF(cx - r * 1.15, cy), r, r)
        cloud.addEllipse(QPointF(cx + r * 1.15, cy), r, r)
        cloud.addEllipse(QPointF(cx - r * 0.35, cy - r * 0.85), r * 1.15, r * 1.15)
        cloud.addEllipse(QPointF(cx + r * 0.6, cy - r * 0.5), r * 0.95, r * 0.95)
        cloud.addRect(QRectF(cx - r * 1.7, cy - r * 0.15, r * 3.4, r * 1.15))
        p.drawPath(cloud.simplified())

    @staticmethod
    def _draw_valvula(p, w, h, stroke, fill_brush, sw):
        # bowtie ISA + actuador de diafragma (vástago + domo)
        cy = h / 2 + 6
        p.drawPolygon(QPolygonF([
            QPointF(6, cy - 11), QPointF(6, cy + 11), QPointF(w/2, cy)]))
        p.drawPolygon(QPolygonF([
            QPointF(w-6, cy - 11), QPointF(w-6, cy + 11), QPointF(w/2, cy)]))
        thin = QPen(stroke, 1.2); thin.setCapStyle(Qt.RoundCap)
        p.setPen(thin); p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(w/2, cy), QPointF(w/2, 12))
        p.drawArc(QRectF(w/2 - 9, 4, 18, 16), 0, 180 * 16)
        p.drawLine(QPointF(w/2 - 9, 12), QPointF(w/2 + 9, 12))

    @staticmethod
    def _draw_compresor(p, w, h, stroke, fill_brush, sw):
        # trapecio ISO (sección que se estrecha hacia la descarga)
        p.drawPolygon(QPolygonF([
            QPointF(8, 8), QPointF(w-8, 16),
            QPointF(w-8, h-16), QPointF(8, h-8)]))
        # flecha de flujo (light)
        ghost = QColor(stroke); ghost.setAlphaF(0.5)
        p.setPen(QPen(ghost, 1.2)); p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(15, h/2), QPointF(w-17, h/2))
        p.drawLine(QPointF(w-22, h/2 - 4), QPointF(w-17, h/2))
        p.drawLine(QPointF(w-22, h/2 + 4), QPointF(w-17, h/2))
        # base
        p.setPen(QPen(stroke, 1.2))
        p.drawLine(QPointF(w/2 - 12, h-3), QPointF(w/2 + 12, h-3))

    @staticmethod
    def _draw_ventilador(p, w, h, stroke, fill_brush, sw):
        # carcasa circular + 3 aspas curvas + hub
        r = min(w, h)/2 - 7
        cx, cy = w/2, h/2
        p.drawEllipse(QPointF(cx, cy), r, r)
        ghost = QColor(stroke); ghost.setAlphaF(0.6)
        p.setPen(QPen(ghost, 1.3)); p.setBrush(Qt.NoBrush)
        for ang in (90, 210, 330):
            a = math.radians(ang)
            tip = QPointF(cx + (r - 3) * math.cos(a),
                          cy - (r - 3) * math.sin(a))
            ctrl = QPointF(cx + r * 0.55 * math.cos(a + 0.65),
                           cy - r * 0.55 * math.sin(a + 0.65))
            blade = QPainterPath(QPointF(cx, cy))
            blade.quadTo(ctrl, tip)
            p.drawPath(blade)
        p.setBrush(stroke); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, cy), 2.2, 2.2)

    @staticmethod
    def _draw_horno(p, w, h, stroke, fill_brush, sw):
        # caja radiante + techo convergente + chimenea (fired heater)
        p.drawRect(QRectF(8, 24, w-16, h-30))
        p.drawPolygon(QPolygonF([
            QPointF(8, 24), QPointF(w/2 - 5, 10),
            QPointF(w/2 + 5, 10), QPointF(w-8, 24)]))
        p.drawRect(QRectF(w/2 - 5, 3, 10, 7))
        # serpentín de proceso (light)
        ghost = QColor(stroke); ghost.setAlphaF(0.5)
        p.setPen(QPen(ghost, 1.0)); p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(12, 34), QPointF(w-12, 34))
        p.drawLine(QPointF(12, 40), QPointF(w-12, 40))
        # llama (light)
        flame = QPainterPath()
        flame.moveTo(w/2 - 8, h-9)
        flame.lineTo(w/2 - 4, h-17)
        flame.lineTo(w/2, h-11)
        flame.lineTo(w/2 + 4, h-19)
        flame.lineTo(w/2 + 8, h-9)
        p.setPen(QPen(ghost, 1.2))
        p.drawPath(flame)

    @staticmethod
    def _draw_caldera(p, w, h, stroke, fill_brush, sw):
        # cuerpo con domo superior + llama en hogar + vapor saliendo
        p.drawRoundedRect(QRectF(10, 12, w-20, h-18), 10, 10)
        ghost = QColor(stroke); ghost.setAlphaF(0.5)
        # nivel de agua dashed
        dpen = QPen(ghost, 1.0); dpen.setStyle(Qt.DashLine)
        p.setPen(dpen); p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(14, h/2 + 2), QPointF(w-14, h/2 + 2))
        # llama del hogar (light)
        p.setPen(QPen(ghost, 1.2))
        flame = QPainterPath()
        flame.moveTo(w/2 - 8, h-10)
        flame.lineTo(w/2 - 4, h-18)
        flame.lineTo(w/2, h-12)
        flame.lineTo(w/2 + 4, h-20)
        flame.lineTo(w/2 + 8, h-10)
        p.drawPath(flame)
        # vapor (squiggle saliendo por arriba)
        steam = QPainterPath()
        steam.moveTo(w/2, 12)
        steam.cubicTo(w/2 - 5, 8, w/2 + 5, 6, w/2, 2)
        p.drawPath(steam)

    @staticmethod
    def _draw_ciclon(p, w, h, stroke, fill_brush, sw):
        # cilindro superior + cono inferior + buscador de vórtice
        body = QPainterPath()
        body.moveTo(10, 12)
        body.lineTo(w-10, 12)
        body.lineTo(w-10, 30)
        body.lineTo(w/2 + 3, h-10)
        body.lineTo(w/2 - 3, h-10)
        body.lineTo(10, 30)
        body.closeSubpath()
        p.drawPath(body)
        thin = QPen(stroke, 1.2)
        p.setPen(thin); p.setBrush(Qt.NoBrush)
        # buscador de vórtice (salida gas, arriba)
        p.drawLine(QPointF(w/2 - 4, 4), QPointF(w/2 - 4, 18))
        p.drawLine(QPointF(w/2 + 4, 4), QPointF(w/2 + 4, 18))
        # entrada tangencial
        p.drawLine(QPointF(2, 16), QPointF(10, 16))
        # vórtice interior (light)
        ghost = QColor(stroke); ghost.setAlphaF(0.45)
        p.setPen(QPen(ghost, 1.0))
        spiral = QPainterPath()
        spiral.moveTo(w/2 + 10, 24)
        spiral.quadTo(w/2 - 12, 32, w/2 + 7, 40)
        spiral.quadTo(w/2 - 8, 48, w/2 + 3, 54)
        p.drawPath(spiral)

    @staticmethod
    def _draw_torre_enf(p, w, h, stroke, fill_brush, sw):
        # perfil hiperbólico (tiro natural / inducido)
        cx = w / 2
        body = QPainterPath()
        body.moveTo(cx - 12, 8)
        body.quadTo(cx - 17, h * 0.55, cx - 20, h - 8)
        body.lineTo(cx + 20, h - 8)
        body.quadTo(cx + 17, h * 0.55, cx + 12, 8)
        body.closeSubpath()
        p.drawPath(body)
        ghost = QColor(stroke); ghost.setAlphaF(0.5)
        p.setPen(QPen(ghost, 1.0)); p.setBrush(Qt.NoBrush)
        # relleno (hash) y agua en la base
        p.drawLine(QPointF(cx - 16, h - 16), QPointF(cx + 16, h - 16))
        p.drawLine(QPointF(cx - 17, h - 13), QPointF(cx + 17, h - 13))
        # pluma de vapor (light)
        plume = QPainterPath()
        plume.moveTo(cx, 8)
        plume.cubicTo(cx - 6, 4, cx + 6, 4, cx, 1)
        p.drawPath(plume)

    @staticmethod
    def _draw_platos(p, w, h, stroke, fill_brush, sw):
        # sección de columna con internos (platos / empaque)
        p.drawRoundedRect(QRectF(w/2 - 14, 6, 28, h - 12), 2, 2)
        # platos con vertederos alternados
        thin = QPen(stroke, 1.1)
        p.setPen(thin); p.setBrush(Qt.NoBrush)
        n = 4
        for i in range(n):
            y = 16 + i * ((h - 30) / (n - 1))
            if i % 2 == 0:
                p.drawLine(QPointF(w/2 - 14, y), QPointF(w/2 + 9, y))
                p.drawLine(QPointF(w/2 + 9, y), QPointF(w/2 + 9, y + 5))
            else:
                p.drawLine(QPointF(w/2 - 9, y), QPointF(w/2 + 14, y))
                p.drawLine(QPointF(w/2 - 9, y), QPointF(w/2 - 9, y + 5))
        # burbujeo (light)
        ghost = QColor(stroke); ghost.setAlphaF(0.4)
        p.setBrush(ghost); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(w/2 - 4, h/2 + 2), 1.2, 1.2)
        p.drawEllipse(QPointF(w/2 + 5, h/2 - 6), 1.2, 1.2)

    @staticmethod
    def _draw_tambor(p, w, h, stroke, fill_brush, sw):
        # recipiente horizontal (cápsula) + nivel + sillas de apoyo
        r = (h - 18) / 2
        p.drawRoundedRect(QRectF(6, 8, w - 12, h - 18), r, r)
        ghost = QColor(stroke); ghost.setAlphaF(0.4)
        dpen = QPen(ghost, 1.0); dpen.setStyle(Qt.DashLine)
        p.setPen(dpen); p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(12, h/2 + 2), QPointF(w - 12, h/2 + 2))
        # sillas
        p.setPen(QPen(stroke, 1.2))
        p.drawLine(QPointF(w * 0.27, h - 10), QPointF(w * 0.27, h - 3))
        p.drawLine(QPointF(w * 0.73, h - 10), QPointF(w * 0.73, h - 3))

    @staticmethod
    def _draw_centrifuga(p, w, h, stroke, fill_brush, sw):
        # bowl troncocónico + canasta interior + eje motriz
        p.drawPolygon(QPolygonF([
            QPointF(12, 16), QPointF(w - 12, 16),
            QPointF(w - 18, h - 8), QPointF(18, h - 8)]))
        # eje + motor
        thin = QPen(stroke, 1.2)
        p.setPen(thin); p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(w/2, 16), QPointF(w/2, 9))
        p.drawRect(QRectF(w/2 - 6, 3, 12, 6))
        # canasta interior (light)
        ghost = QColor(stroke); ghost.setAlphaF(0.5)
        p.setPen(QPen(ghost, 1.0))
        p.drawPolygon(QPolygonF([
            QPointF(19, 21), QPointF(w - 19, 21),
            QPointF(w - 23, h - 13), QPointF(23, h - 13)]))

    @staticmethod
    def _draw_filtro(p, w, h, stroke, fill_brush, sw):
        # carcasa + medio filtrante (hash diagonal) + flujo in/out
        p.drawRoundedRect(QRectF(8, 8, w - 16, h - 16), 4, 4)
        ghost = QColor(stroke); ghost.setAlphaF(0.55)
        p.setPen(QPen(ghost, 1.0)); p.setBrush(Qt.NoBrush)
        band_y1, band_y2 = h/2 - 6, h/2 + 6
        p.drawLine(QPointF(8, band_y1), QPointF(w - 8, band_y1))
        p.drawLine(QPointF(8, band_y2), QPointF(w - 8, band_y2))
        for x in range(14, int(w) - 9, 7):
            p.drawLine(QPointF(x, band_y2), QPointF(x + 5, band_y1))
        # flecha de flujo descendente (light)
        ghost2 = QColor(stroke); ghost2.setAlphaF(0.4)
        p.setPen(QPen(ghost2, 1.2))
        p.drawLine(QPointF(w/2, 13), QPointF(w/2, h/2 - 9))
        p.drawLine(QPointF(w/2 - 3, h/2 - 13), QPointF(w/2, h/2 - 9))
        p.drawLine(QPointF(w/2 + 3, h/2 - 13), QPointF(w/2, h/2 - 9))

    @staticmethod
    def _draw_secador(p, w, h, stroke, fill_brush, sw):
        # tambor rotatorio horizontal + rodillos de apoyo + lifters
        r = (h - 22) / 2
        p.drawRoundedRect(QRectF(6, 8, w - 12, h - 22), r, r)
        # lifters interiores (light)
        ghost = QColor(stroke); ghost.setAlphaF(0.5)
        p.setPen(QPen(ghost, 1.0)); p.setBrush(Qt.NoBrush)
        for x in (w * 0.3, w * 0.5, w * 0.7):
            p.drawLine(QPointF(x - 4, h - 18), QPointF(x + 4, 12))
        # rodillos de apoyo
        p.setPen(QPen(stroke, 1.2)); p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(w * 0.28, h - 8), 3.5, 3.5)
        p.drawEllipse(QPointF(w * 0.72, h - 8), 3.5, 3.5)

    @staticmethod
    def _draw_hx_kettle(p, w, h, stroke, fill_brush, sw):
        # marmita TEMA K: shell horizontal + domo de vapor superior
        p.drawRoundedRect(QRectF(6, 16, w - 12, h - 22), 10, 10)
        dome = QPainterPath()
        dome.moveTo(w/2 - 9, 16)
        dome.arcTo(QRectF(w/2 - 9, 7, 18, 18), 180, -180)
        p.drawPath(dome)
        # haz en U (light)
        ghost = QColor(stroke); ghost.setAlphaF(0.6)
        p.setPen(QPen(ghost, 1.0)); p.setBrush(Qt.NoBrush)
        bundle = QPainterPath()
        bundle.moveTo(12, h/2 + 1)
        bundle.lineTo(w - 20, h/2 + 1)
        bundle.arcTo(QRectF(w - 24, h/2 + 1, 8, 7), 90, -180)
        bundle.lineTo(12, h/2 + 8)
        p.drawPath(bundle)
        # nivel de líquido dashed (light)
        ghost2 = QColor(stroke); ghost2.setAlphaF(0.4)
        dpen = QPen(ghost2, 1.0); dpen.setStyle(Qt.DashLine)
        p.setPen(dpen)
        p.drawLine(QPointF(12, h - 12), QPointF(w - 12, h - 12))

    @staticmethod
    def _draw_hx_aircooler(p, w, h, stroke, fill_brush, sw):
        # aerorrefrigerante API 661: caja de tubos + ventilador arriba
        p.drawRect(QRectF(8, 22, w - 16, h - 28))
        # ventilador circular montado sobre la caja
        p.drawEllipse(QPointF(w/2, 22), 10.0, 10.0)
        # tubos (light)
        ghost = QColor(stroke); ghost.setAlphaF(0.6)
        p.setPen(QPen(ghost, 1.0)); p.setBrush(Qt.NoBrush)
        for i in range(3):
            y = 29 + i * ((h - 38) / 2)
            p.drawLine(QPointF(13, y), QPointF(w - 13, y))
        # aspas (light)
        for ang in (90, 210, 330):
            a = math.radians(ang)
            tip = QPointF(w/2 + 8 * math.cos(a), 22 - 8 * math.sin(a))
            ctrl = QPointF(w/2 + 5 * math.cos(a + 0.7),
                           22 - 5 * math.sin(a + 0.7))
            blade = QPainterPath(QPointF(w/2, 22))
            blade.quadTo(ctrl, tip)
            p.drawPath(blade)
        p.setBrush(stroke); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(w/2, 22), 1.8, 1.8)

    @staticmethod
    def _draw_hx_placa(p, w, h, stroke, fill_brush, sw):
        # intercambiador de placas: marco + pila de placas paralelas
        p.drawRect(QRectF(8, 8, w - 16, h - 16))
        ghost = QColor(stroke); ghost.setAlphaF(0.6)
        p.setPen(QPen(ghost, 1.1)); p.setBrush(Qt.NoBrush)
        n = 5
        for i in range(1, n + 1):
            x = 8 + i * ((w - 16) / (n + 1))
            p.drawLine(QPointF(x, 12), QPointF(x, h - 12))

    @staticmethod
    def _draw_cristalizador(p, w, h, stroke, fill_brush, sw):
        # vessel cónico (fondo a punta) + agitador + cristales
        body = QPainterPath()
        body.moveTo(6, 18)
        body.arcTo(QRectF(6, 8, w - 12, 20), 180, -180)
        body.lineTo(w - 6, h - 24)
        body.lineTo(w/2, h - 4)
        body.lineTo(6, h - 24)
        body.closeSubpath()
        p.drawPath(body)
        # agitador
        thin = QPen(stroke, 1.2); thin.setCapStyle(Qt.RoundCap)
        p.setPen(thin); p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(w/2, 4), QPointF(w/2, h - 22))
        p.drawLine(QPointF(w/2 - 7, h - 24), QPointF(w/2 + 7, h - 24))
        # cristales (rombos light)
        ghost = QColor(stroke); ghost.setAlphaF(0.5)
        p.setPen(QPen(ghost, 0.9))
        for cx, cy in ((w/2 - 9, h/2 + 2), (w/2 + 8, h/2 + 8),
                       (w/2 - 2, h/2 + 14)):
            p.drawPolygon(QPolygonF([
                QPointF(cx, cy - 3.5), QPointF(cx + 3.5, cy),
                QPointF(cx, cy + 3.5), QPointF(cx - 3.5, cy)]))


# Ciclo 3 (artboard 3a): los 48 glifos del set de Design se montan
# como métodos _draw_* data-driven (glyph_specs), REEMPLAZANDO los
# QPainter a mano de los nombres que refrescan y agregando las
# variantes nuevas (valvula_globe/relief, reactor_cstr/jacket/…).  El
# router de BlockGlyph.draw y el gate de cobertura los ven idénticos
# a un _draw_ escrito a mano.  El estado unrun llega como pen
# DashLine del caller (contrato de draw) y se propaga a los trazos
# de contorno del spec.
def _bind_design_glyphs():
    from PySide6.QtCore import Qt as _Qt

    def _mk(name):
        def _drawer(p, w, h, stroke, fill_brush, sw):
            dashed = p.pen().style() == _Qt.DashLine
            glyph_specs.draw_glyph(p, name, w, h, stroke, fill_brush,
                                   sw, dashed=dashed)
        return staticmethod(_drawer)

    for _name in glyph_specs.GLYPHS:
        setattr(BlockGlyph, f"_draw_{_name}", _mk(_name))


_bind_design_glyphs()


# ════════════════════════════════════════════════════════

class EditorTopbar(QFrame):
    """Barra superior 52px por ZONAS DE TAREA (artboard 1c):

      izquierda: identidad — logo (◆) + nombre del proyecto + estado de
                 guardado real (set_saved_state)
      centro:    edición del lienzo — undo/redo | Marco PFD · Flujo
      derecha:   workflow de simulación, en orden pedagógico —
                 chip solver → "Validar DOF" → "▶ Resolver" → "Economía"

    Los botones del centro se enlazan a las QActions COMPARTIDAS de la
    ventana via bind_history_actions / bind_canvas_actions
    (QToolButton.setDefaultAction): una sola acción por concepto, con
    shortcut real y check nunca desincronizado — el patrón que ya usaba
    "Tabla de corrientes".

    El topbar es REACTIVE: actualiza el chip cuando la ventana llama
    a `set_solver_state(state, iter, dt)`.
    """

    validateRequested    = Signal()
    solveRequested       = Signal()
    economicsRequested   = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("edTopbar")
        self.setFixedHeight(52)
        self.setStyleSheet(self._qss_topbar())

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 6, 12, 6)
        lay.setSpacing(8)

        # ── IZQUIERDA: logo + project ──
        self._logo = QLabel(self)
        self._logo.setFixedSize(28, 28)
        self._logo.setAlignment(Qt.AlignCenter)
        f = QFont(pfd_fonts.SANS, 14, QFont.Bold)  # glifo-ícono: tamaño geométrico, no tipografía (excepción 2g)
        self._logo.setFont(f)
        self._logo.setText("◆")
        self._logo.setStyleSheet(self._qss_logo())
        lay.addWidget(self._logo)

        proj = QVBoxLayout(); proj.setContentsMargins(0,0,0,0); proj.setSpacing(0)
        self._project = QLabel("(sin nombre)", self)
        self._project.setFont(qfont(FONT_VALUE))
        self._project.setStyleSheet(f"color:{TOK['ink']};")
        self._sub = QLabel("sin guardar", self)
        self._sub.setFont(qfont(FONT_HINT))
        self._sub.setStyleSheet(f"color:{TOK['ink_soft']};")
        proj.addWidget(self._project); proj.addWidget(self._sub)
        lay.addLayout(proj)

        lay.addStretch(1)

        # ── CENTRO: edición del lienzo ──
        # Se puebla en bind_history_actions / bind_canvas_actions con las
        # QActions compartidas de la ventana.  (El botón ✦ Auto-arrange,
        # que no tenía handler, se eliminó; ▦ "Toggle grid" — que en
        # realidad alternaba el Marco PFD — es ahora la propia acción
        # "Marco PFD", bien nombrada y sincronizada.)
        self._mid = QHBoxLayout(); self._mid.setSpacing(2)
        lay.addLayout(self._mid)

        lay.addStretch(1)

        # ── DERECHA: solver chip + Validar + Resolver ──
        self._solver_chip = QFrame(self); self._solver_chip.setObjectName("solverChip")
        sc_lay = QHBoxLayout(self._solver_chip)
        sc_lay.setContentsMargins(8, 4, 12, 4); sc_lay.setSpacing(6)
        self._solver_dot = QLabel(self._solver_chip)
        self._solver_dot.setFixedSize(8, 8)
        sc_lay.addWidget(self._solver_dot)
        self._solver_label = QLabel("en espera", self._solver_chip)
        self._solver_label.setFont(qfont(FONT_LABEL))
        sc_lay.addWidget(self._solver_label)
        self._solver_meta = QLabel("", self._solver_chip)
        self._solver_meta.setFont(qfont(FONT_VALUE))
        self._solver_meta.setStyleSheet(f"color:{TOK['ink_soft']};")
        sc_lay.addWidget(self._solver_meta)
        lay.addWidget(self._solver_chip)
        self.set_solver_state("idle")

        lay.addWidget(self._mk_vdivider())

        self._btn_validate = self._mk_ghost_btn("Validar DOF")
        self._btn_validate.clicked.connect(self.validateRequested.emit)
        lay.addWidget(self._btn_validate)

        self._btn_solve = self._mk_primary_btn("▶  Resolver")
        self._btn_solve.setToolTip("Resolver balances (F5)")
        self._btn_solve.clicked.connect(self.solveRequested.emit)
        lay.addWidget(self._btn_solve)

        # Paso final del workflow, por fin visible en la barra (1c):
        # estado → Validar DOF → Resolver → Economía.
        self._btn_economics = self._mk_ghost_btn("Economía")
        self._btn_economics.setToolTip("Análisis económico del flowsheet")
        self._btn_economics.clicked.connect(self.economicsRequested.emit)
        lay.addWidget(self._btn_economics)

    # ── QSS (extraídos para poder re-aplicarlos en restyle) ────
    @staticmethod
    def _qss_topbar() -> str:
        return (f"#edTopbar {{ background: {TOK['bg_elev']}; "
                f"border-bottom: 1px solid {TOK['line']}; }}")

    @staticmethod
    def _qss_logo() -> str:
        return (f"color:{TOK['accent']}; background:{TOK['accent_tint']}; "
                f"border-radius:8px; border:1px solid {TOK['accent_soft']};")

    @staticmethod
    def _qss_toolbutton() -> str:
        return (
            f"QToolButton {{ background: transparent; color: {TOK['ink_mute']}; "
            f"border: 0; border-radius: 6px; }} "
            f"QToolButton:hover {{ background: {TOK['bg_mute']}; color: {TOK['ink']}; }} "
            f"QToolButton:checked {{ background: {TOK['accent_tint']}; color: {TOK['accent_deep']}; }} "
            f"QToolButton:disabled {{ color: {TOK['ink_ghost']}; }}"
        )

    @staticmethod
    def _qss_divider() -> str:
        return f"color:{TOK['line']}; background:{TOK['line']};"

    @staticmethod
    def _qss_ghost() -> str:
        return (
            f"QPushButton {{ background: transparent; color: {TOK['ink_mute']}; "
            f"border: 1px solid {TOK['line_strong']}; border-radius: 6px; "
            f"padding: 6px 12px; }} "
            f"QPushButton:hover {{ background: {TOK['bg_mute']}; "
            f"color: {TOK['ink']}; border-color: {TOK['accent_soft']}; }}"
        )

    @staticmethod
    def _qss_primary() -> str:
        return (
            f"QPushButton {{ background: {TOK['accent']}; color: {TOK['bg_elev']}; "
            f"border: 0; border-radius: 6px; padding: 7px 14px; }} "
            f"QPushButton:hover {{ background: {TOK['accent_deep']}; }}"
        )

    def restyle(self):
        """Re-aplica todos los QSS con el TOK vivo — lo llama la ventana
        en themeChanged (artboard 2b: un solo nivel de respiración)."""
        self.setStyleSheet(self._qss_topbar())
        self._logo.setStyleSheet(self._qss_logo())
        self._project.setStyleSheet(f"color:{TOK['ink']};")
        self._sub.setStyleSheet(f"color:{TOK['ink_soft']};")
        self._solver_meta.setStyleSheet(f"color:{TOK['ink_soft']};")
        for b in self.findChildren(QToolButton):
            b.setStyleSheet(self._qss_toolbutton())
        for d in self.findChildren(QFrame):
            if isinstance(d, QFrame) and d.frameShape() == QFrame.VLine:
                d.setStyleSheet(self._qss_divider())
        self._btn_validate.setStyleSheet(self._qss_ghost())
        self._btn_economics.setStyleSheet(self._qss_ghost())
        self._btn_solve.setStyleSheet(self._qss_primary())
        # chip: re-aplicar el último estado con los tokens nuevos
        st, it_, dt = getattr(self, "_solver_last", ("idle", 0, 0.0))
        self.set_solver_state(st, it_, dt)

    # ── helpers UI ─────────────────────────────────────
    def _mk_icon_btn(self, glyph: str, tooltip: str) -> QToolButton:
        b = QToolButton(self)
        b.setText(glyph)
        b.setToolTip(tooltip)
        b.setFixedSize(32, 32)
        b.setCursor(Qt.PointingHandCursor)
        b.setFont(QFont(pfd_fonts.SANS, 14))  # glifo-ícono: tamaño geométrico, no tipografía (excepción 2g)
        b.setStyleSheet(self._qss_toolbutton())
        return b

    def _mk_vdivider(self) -> QFrame:
        d = QFrame(self); d.setFrameShape(QFrame.VLine)
        d.setFixedWidth(1); d.setFixedHeight(24)
        d.setStyleSheet(self._qss_divider())
        return d

    def _mk_ghost_btn(self, text: str) -> QPushButton:
        b = QPushButton(text, self)
        b.setCursor(Qt.PointingHandCursor)
        b.setFont(qfont(FONT_UI))
        b.setStyleSheet(self._qss_ghost())
        return b

    def _mk_primary_btn(self, text: str) -> QPushButton:
        b = QPushButton(text, self)
        b.setCursor(Qt.PointingHandCursor)
        b.setFont(qfont(FONT_UI))
        b.setStyleSheet(self._qss_primary())
        return b

    # ── API pública ────────────────────────────────────
    def set_project(self, name: str, sub: str = ""):
        self._project.setText(name or "(sin nombre)")
        if sub:
            self._sub.setText(sub)

    def set_solver_state(self, state: str, iter_: int = 0, dt: float = 0.0):
        """state ∈ {'idle', 'running', 'converged', 'warning', 'failed', 'stale'}."""
        self._solver_last = (state, iter_, dt)   # para restyle()
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

    def set_saved_state(self, text: str):
        """Estado de guardado real bajo el nombre del proyecto
        ('sin guardar' / 'cambios sin guardar' / 'guardado 14:32')."""
        self._sub.setText(text or "")

    def _mk_action_btn(self, action) -> QToolButton:
        """QToolButton 32×32 enlazado a una QAction compartida
        (icono, tooltip, shortcut, check — todo del action)."""
        b = QToolButton(self)
        b.setDefaultAction(action)
        b.setToolButtonStyle(Qt.ToolButtonIconOnly)
        b.setFixedSize(32, 32)
        b.setCursor(Qt.PointingHandCursor)
        b.setStyleSheet(self._qss_toolbutton())
        return b

    def bind_history_actions(self, undo_action, redo_action):
        """Enlaza undo/redo (QActions del QUndoStack, con shortcuts
        reales) a la zona central."""
        self._mid.addWidget(self._mk_action_btn(undo_action))
        self._mid.addWidget(self._mk_action_btn(redo_action))

    def bind_canvas_actions(self, *actions):
        """Enlaza los toggles del lienzo (Marco PFD, Animación de flujo)
        tras un divider — misma QAction que el menú Vista."""
        self._mid.addWidget(self._mk_vdivider())
        for act in actions:
            if act is not None:
                self._mid.addWidget(self._mk_action_btn(act))


# ════════════════════════════════════════════════════════
#  EDITOR PALETTE — vertical floating
# ════════════════════════════════════════════════════════

class _ToolButton(QToolButton):
    """Botón de paleta (tool o block).  Pinta su contenido custom.

    Si `kind == 'block'`, soporta drag-out: al iniciar drag se emite
    un QMimeData con `application/x-pfd-eqtype` apuntando al eq_type
    canónico (via PALETTE_TO_EQ_TYPE). El FlowsheetView ya escucha
    ese mime y crea el bloque en la posición del drop.
    """

    def __init__(self, kind: str, ident: str, tooltip: str,
                 active: bool = False, parent=None):
        super().__init__(parent)
        self._kind = kind   # "tool" | "block"
        self._id = ident
        self._active = active
        self._drag_start = None
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

    # ── Drag-out (solo block-buttons) ──────────────────
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton and self._kind == "block":
            self._drag_start = ev.position().toPoint()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if (self._kind != "block" or
            not (ev.buttons() & Qt.LeftButton) or
            self._drag_start is None):
            return super().mouseMoveEvent(ev)
        # threshold para distinguir click de drag
        if ((ev.position().toPoint() - self._drag_start).manhattanLength()
                < QApplication.startDragDistance()):
            return
        self._start_block_drag()

    def _start_block_drag(self):
        eq_type = PALETTE_TO_EQ_TYPE.get(self._id)
        if not eq_type:
            return
        drag = QDrag(self)
        md = QMimeData()
        # mime que ya escucha FlowsheetView.dropEvent
        md.setData("application/x-pfd-eqtype",
                   QByteArray(eq_type.encode("utf-8")))
        drag.setMimeData(md)
        # Pixmap preview = silueta ISA escalada (glifo real, ciclo 3)
        glyph_id = _palette_glyph_id(self._id)
        w_native, h_native = BLOCK_DIMS.get(glyph_id, (60, 60))
        # render a 1.6x para que se vea generoso bajo el cursor
        target_w = int(w_native * 1.6); target_h = int(h_native * 1.6)
        px = QPixmap(target_w + 2, target_h + 2)
        px.fill(Qt.transparent)
        pp = QPainter(px)
        pp.setRenderHint(QPainter.Antialiasing, True)
        pp.translate(1, 1)
        pp.scale(1.6, 1.6)
        BlockGlyph.draw(pp, glyph_id, w_native, h_native,
                        QColor(TOK["accent"]),
                        fill=QColor(TOK["bg_elev"]),
                        stroke_width=1.5)
        pp.end()
        drag.setPixmap(px)
        drag.setHotSpot(QPointF(target_w/2, target_h/2).toPoint())
        drag.exec(Qt.CopyAction)

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
            # silueta ISA — el botón resuelve al glifo REAL del eq_type
            # que instancia (ciclo 3: el botón muestra el set nuevo,
            # no la silueta base legacy)
            glyph_id = _palette_glyph_id(self._id)
            w, h = BLOCK_DIMS.get(glyph_id, (40, 30))
            # escalar a 30px max
            box_w, box_h = self.width()-12, self.height()-12
            scale = min(box_w / w, box_h / h, 0.5)  # cap a 0.5x para que entre cómodo
            sw, sh = int(w * scale), int(h * scale)
            ox = (self.width() - sw) // 2
            oy = (self.height() - sh) // 2
            p.save()
            p.translate(ox, oy)
            p.scale(scale, scale)
            BlockGlyph.draw(p, glyph_id, w, h, self._stroke,
                            fill=None if not self._active else QColor(0,0,0,0),
                            stroke_width=2.0)
            p.restore()
        else:
            # tool icon — usar glyphs unicode minimalistas
            p.setPen(QPen(self._stroke, 1.6))
            p.setFont(QFont(pfd_fonts.SANS, 14, QFont.Medium))  # glifo-ícono: tamaño geométrico, no tipografía (excepción 2g)
            glyph = {
                "select":  "↖",
                "pan":     "✥",
                "connect": "⟶",
                "mass":    "→",
                "energy":  "↯",
            }.get(self._id, "?")
            p.drawText(self.rect(), Qt.AlignCenter, glyph)


class EditorPalette(QFrame):
    """Paleta vertical flotante (50px).  Tools arriba, 7 bloques abajo.

    Comportamiento:
      · Click en una tool → toolSelected(id)
      · Click en un bloque → popup con TODAS las variantes de la
        categoría correspondiente.  El usuario elige una y se emite
        blockTypeRequested(eq_type) con el eq_type canónico del
        catálogo.
      · Drag desde un bloque → crea el bloque default (canónico) en
        la posición del drop.
      · Botón "+" → popup con TODOS los eq_types agrupados por
        categoría (Heat exchangers / Compressors / Reactors / etc.).

    La paleta es arrastrable: un handle "⋮⋮" arriba permite moverla
    a cualquier posición dentro del viewport.
    """

    toolSelected         = Signal(str)
    blockRequested       = Signal(str)        # palette-id (legacy)
    blockTypeRequested   = Signal(str)        # eq_type canónico
    moreRequested        = Signal()
    streamRequested      = Signal(str)        # 'mass' | 'energy'

    # ("text", "Anotación") se quitó del set: era un stub que solo
    # cambiaba el cursor.  Se re-agrega cuando exista la colocación de
    # texto real (rediseño 1g).
    TOOLS = [
        ("select",  "Seleccionar (V)"),
        ("pan",     "Pan (espacio)"),
        ("connect", "Conectar stream (C)"),
    ]
    # Corrientes flotantes: click → crea la flecha en el centro de la
    # vista; el usuario arrastra los extremos hasta un puerto para
    # conectarla (el endpoint hace snap al puerto cercano).
    STREAMS = [
        ("mass",   "Corriente de masa — arrastrá los extremos a un puerto"),
        ("energy", "Corriente de energía (kW) — acopla duties entre bloques"),
    ]
    BLOCKS = ["reactor", "mezclador", "separador", "columna",
              "hx", "bomba", "tanque"]

    # Mapeo categoría del catálogo → palette-id (para agrupar variantes
    # bajo el botón correspondiente).
    CATEGORY_TO_PALETTE = {
        "Reactors":           "reactor",
        "Heat exchangers":    "hx",
        "Pumps":              "bomba",
        "Compressors":        "bomba",   # comparten silueta circular
        "Fans":               "bomba",
        "Vessels":            "separador",
        "Storage":            "tanque",
        "Mixers / splitters": "mezclador",
        "Fired heaters":      "hx",
        "Solids / sep.":      "separador",
    }

    @staticmethod
    def _qss_palette() -> str:
        return (f"#edPalette {{ background: {TOK['bg_elev']}; "
                f"border: 1px solid {TOK['line']}; border-radius: 12px; }}")

    @staticmethod
    def _qss_plus() -> str:
        return (
            f"QToolButton {{ background: transparent; color: {TOK['ink_mute']}; "
            f"border: 0; border-radius: 6px; }} "
            f"QToolButton:hover {{ background: {TOK['bg_mute']}; color: {TOK['ink']}; }}"
        )

    def restyle(self):
        """Re-aplica los QSS con el TOK vivo (themeChanged)."""
        self.setStyleSheet(self._qss_palette())
        self._drag_handle.setStyleSheet(
            f"color: {TOK['ink_ghost']}; letter-spacing: -2px;")
        for d in getattr(self, "_dividers", []):
            d.setStyleSheet(f"background:{TOK['line']};")
        if getattr(self, "_plus", None) is not None:
            self._plus.setStyleSheet(self._qss_plus())
        for btns in (self._tool_btns, self._stream_btns, self._block_btns):
            for b in btns.values():
                b._apply_style()
                b.update()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("edPalette")
        self.setFixedWidth(50)
        self._dividers: list = []
        self.setStyleSheet(self._qss_palette())
        # Shadow effect
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            sh = QGraphicsDropShadowEffect(self)
            sh.setBlurRadius(28); sh.setOffset(0, 6)
            c = QColor(40, 30, 20); c.setAlphaF(0.12); sh.setColor(c)
            self.setGraphicsEffect(sh)
        except Exception:
            pass

        # Estado de drag para mover la paleta
        self._drag_offset = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(5, 4, 5, 8); lay.setSpacing(2)

        # ── Drag handle arriba ──
        self._drag_handle = QLabel("⋮⋮", self)
        self._drag_handle.setFixedSize(40, 14)
        self._drag_handle.setAlignment(Qt.AlignCenter)
        self._drag_handle.setCursor(Qt.SizeAllCursor)
        self._drag_handle.setFont(QFont(pfd_fonts.SANS, 9, QFont.Bold))  # glifo-ícono: tamaño geométrico, no tipografía (excepción 2g)
        self._drag_handle.setStyleSheet(
            f"color: {TOK['ink_ghost']}; letter-spacing: -2px;"
        )
        self._drag_handle.setToolTip("Arrastrá para mover la paleta")
        lay.addWidget(self._drag_handle, alignment=Qt.AlignHCenter)

        # ── Tools ──
        self._tool_btns: Dict[str, _ToolButton] = {}
        self._active_tool = "select"
        for tid, tip in self.TOOLS:
            b = _ToolButton("tool", tid, tip, active=(tid == "select"), parent=self)
            b.clicked.connect(lambda _=False, k=tid: self._on_tool_click(k))
            self._tool_btns[tid] = b
            lay.addWidget(b, alignment=Qt.AlignHCenter)

        lay.addWidget(self._mk_divider())

        # ── Corrientes (masa / energía) ──
        self._stream_btns: Dict[str, _ToolButton] = {}
        for sid, tip in self.STREAMS:
            b = _ToolButton("stream", sid, tip, parent=self)
            b.clicked.connect(
                lambda _=False, k=sid: self.streamRequested.emit(k))
            self._stream_btns[sid] = b
            lay.addWidget(b, alignment=Qt.AlignHCenter)

        lay.addWidget(self._mk_divider())

        # ── Bloques (7 tipos, cada uno con popup de variantes) ──
        self._block_btns: Dict[str, _ToolButton] = {}
        for bid in self.BLOCKS:
            b = _ToolButton("block", bid, PALETTE_LABELS.get(bid, bid), parent=self)
            # Click sobre el bloque: abrir popup de variantes
            b.clicked.connect(
                lambda _=False, k=bid, btn=b: self._show_variants_menu(k, btn))
            self._block_btns[bid] = b
            lay.addWidget(b, alignment=Qt.AlignHCenter)

        lay.addWidget(self._mk_divider())

        # ── Botón "+" (popup categorizado de todos los equipos) ──
        plus = QToolButton(self)
        plus.setText("+"); plus.setFixedSize(40, 32)
        plus.setCursor(Qt.PointingHandCursor)
        plus.setFont(QFont(pfd_fonts.SANS, 16, QFont.Bold))  # glifo-ícono: tamaño geométrico, no tipografía (excepción 2g)
        plus.setToolTip("Catálogo completo de equipos")
        plus.setStyleSheet(self._qss_plus())
        self._plus = plus
        plus.clicked.connect(lambda: self._show_full_catalog_menu(plus))
        lay.addWidget(plus, alignment=Qt.AlignHCenter)

        lay.addStretch(1)

    # ── Movimiento de la paleta ──
    def mousePressEvent(self, ev):
        # Solo el handle inicia el drag — los botones consumen sus clicks
        if ev.button() == Qt.LeftButton:
            child = self.childAt(ev.position().toPoint())
            if child is self._drag_handle:
                self._drag_offset = ev.globalPosition().toPoint() - self.pos()
                ev.accept()
                return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._drag_offset is not None and (ev.buttons() & Qt.LeftButton):
            new_pos = ev.globalPosition().toPoint() - self._drag_offset
            # restringir al rectángulo del parent (viewport)
            parent = self.parentWidget()
            if parent is not None:
                pr = parent.rect()
                pw = self.width(); ph = self.height()
                x = max(0, min(new_pos.x(), pr.width()  - pw))
                y = max(0, min(new_pos.y(), pr.height() - ph))
                new_pos = self.mapToParent(self.mapFromGlobal(
                    ev.globalPosition().toPoint())) if parent is None else \
                    type(new_pos)(x, y)
            self.move(new_pos)
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._drag_offset is not None:
            self._drag_offset = None
            ev.accept()
            return
        super().mouseReleaseEvent(ev)

    # ── Helpers ──
    def _mk_divider(self) -> QFrame:
        d = QFrame(self); d.setFixedHeight(1)
        d.setStyleSheet(f"background:{TOK['line']};")
        self._dividers.append(d)
        return d

    def _on_tool_click(self, tool_id: str):
        if self._active_tool == tool_id:
            return
        self._tool_btns[self._active_tool].set_active(False)
        self._active_tool = tool_id
        self._tool_btns[tool_id].set_active(True)
        self.toolSelected.emit(tool_id)

    def set_active_tool(self, tool_id: str):
        if tool_id in self._tool_btns:
            self._on_tool_click(tool_id)

    # ── Popups de variantes / catálogo completo ──
    def _eq_types_for_palette(self, palette_id: str) -> List[str]:
        """Devuelve todos los eq_types del catálogo cuya silueta ISA
        cuelga de este botón de paleta (PALETTE_GROUPS), p.ej. el
        botón 'bomba' agrupa bombas + compresores + ventiladores."""
        try:
            import equipment_costs as _ec
        except Exception:
            return []
        group = PALETTE_GROUPS.get(palette_id, (palette_id,))
        out = []
        for eq_name, spec in _ec.EQUIPMENT_DATA.items():
            mapped = isa_type_for_eq(eq_name)
            if mapped in group:
                out.append(eq_name)
        return sorted(out)

    def _icon_for_eq_type(self, eq_type: str, size: int = 22):
        """Genera un QIcon de 22px renderizando la silueta ISA del
        eq_type via BlockGlyph (mismo dibujo que se ve en el lienzo).
        TF §10: si el eq_type NO tiene silueta ISA nativa, reusa el SVG
        de pfd_symbols (como hace IsaGlyphItem) en vez del rect neutro —
        el menú "+más" muestra el símbolo real."""
        from PySide6.QtGui import QPixmap, QIcon
        try:
            isa = isa_type_for_eq(eq_type)
            if isa not in BLOCK_DIMS:
                icon = self._icon_from_pfd_svg(eq_type, size)
                if icon is not None:
                    return icon
            nw, nh = BLOCK_DIMS.get(isa, (60, 60))
            px = QPixmap(size + 4, size + 4)
            px.fill(Qt.transparent)
            p = QPainter(px)
            p.setRenderHint(QPainter.Antialiasing, True)
            # escalar al recuadro size×size manteniendo proporción
            scale = min(size / nw, size / nh) * 0.9
            sw = nw * scale; sh = nh * scale
            p.translate((size + 4 - sw) / 2, (size + 4 - sh) / 2)
            p.scale(scale, scale)
            BlockGlyph.draw(p, isa, nw, nh, QColor(TOK["ink_mute"]),
                            fill=QColor(TOK["bg_elev"]),
                            stroke_width=2.0 / max(scale, 0.1))
            p.end()
            return QIcon(px)
        except Exception:
            return QIcon()

    def _icon_from_pfd_svg(self, eq_type: str, size: int = 22):
        """TF §10 — QIcon desde el símbolo SVG de pfd_symbols para
        eq_types sin silueta ISA nativa.  None si tampoco hay SVG."""
        from PySide6.QtGui import QPixmap, QIcon
        try:
            import pfd_symbols as pfd
            from PySide6.QtSvg import QSvgRenderer
            from PySide6.QtCore import QRectF
            raw = pfd.EQ_TYPE_TO_SYMBOL.get(eq_type, "")
            if not raw:
                return None
            svg = pfd.wrap_svg(raw, w=size, h=size)
            if not svg:
                return None
            renderer = QSvgRenderer(bytes(svg, "utf-8"))
            if not renderer.isValid():
                return None
            px = QPixmap(size + 4, size + 4)
            px.fill(Qt.transparent)
            p = QPainter(px)
            p.setRenderHint(QPainter.Antialiasing, True)
            renderer.render(p, QRectF(2, 2, size, size))
            p.end()
            return QIcon(px)
        except Exception:
            return None

    def _show_variants_menu(self, palette_id: str, anchor_widget):
        """Muestra un popup con todas las variantes de una categoría.
        Si solo hay una, la emite directo sin abrir el menú."""
        eq_types = self._eq_types_for_palette(palette_id)
        if not eq_types:
            default = PALETTE_TO_EQ_TYPE.get(palette_id)
            if default:
                self.blockTypeRequested.emit(default)
                self.blockRequested.emit(palette_id)
            return
        if len(eq_types) == 1:
            self.blockTypeRequested.emit(eq_types[0])
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        self._style_menu(menu)
        default = PALETTE_TO_EQ_TYPE.get(palette_id)
        for et in eq_types:
            label = et
            if et == default:
                label = f"★  {et}"
            act = menu.addAction(self._icon_for_eq_type(et), label)
            act.triggered.connect(lambda _=False, e=et:
                                  self.blockTypeRequested.emit(e))
        global_pos = anchor_widget.mapToGlobal(
            anchor_widget.rect().topRight()
        )
        menu.exec(global_pos)

    def _show_full_catalog_menu(self, anchor_widget):
        """Popup con TODO el catálogo agrupado por categoría."""
        try:
            import equipment_costs as _ec
            by_cat = _ec.por_categoria()
        except Exception:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        self._style_menu(menu)
        priority = ["Reactors", "Heat exchangers", "Vessels",
                    "Mixers / splitters", "Pumps", "Compressors",
                    "Storage", "Fired heaters", "Fans", "Solids / sep."]
        ordered_cats = [c for c in priority if c in by_cat] + \
                       sorted([c for c in by_cat if c not in priority])
        for cat in ordered_cats:
            sub = menu.addMenu(cat)
            self._style_menu(sub)
            for et in by_cat[cat]:
                act = sub.addAction(self._icon_for_eq_type(et), et)
                act.triggered.connect(lambda _=False, e=et:
                                      self.blockTypeRequested.emit(e))
        global_pos = anchor_widget.mapToGlobal(
            anchor_widget.rect().topRight()
        )
        menu.exec(global_pos)

    def _style_menu(self, menu):
        """Aplica el estilo del editor al QMenu."""
        menu.setStyleSheet(
            f"QMenu {{ background: {TOK['bg_elev']}; color: {TOK['ink']}; "
            f"border: 1px solid {TOK['line']}; padding: 4px 0; "
            f"font-family: '{pfd_fonts.SANS}'; "
            f"font-size: {FONT_HINT[1]}pt; }} "
            f"QMenu::item {{ padding: 6px 22px 6px 14px; }} "
            f"QMenu::item:selected {{ background: {TOK['accent_tint']}; "
            f"color: {TOK['accent_deep']}; }} "
            f"QMenu::separator {{ height: 1px; background: {TOK['line']}; "
            f"margin: 4px 8px; }}"
        )


# ════════════════════════════════════════════════════════
#  EDITOR ZOOM — bottom-right floating
# ════════════════════════════════════════════════════════

class EditorZoom(QFrame):
    """Control de zoom flotante: − [100%] + ⤢."""

    zoomInRequested  = Signal()
    zoomOutRequested = Signal()
    zoomResetRequested = Signal()
    zoomFitRequested = Signal()

    @staticmethod
    def _qss_zoom() -> str:
        return (f"#edZoom {{ background: {TOK['bg_elev']}; "
                f"border: 1px solid {TOK['line']}; border-radius: 10px; }}")

    @staticmethod
    def _qss_btn() -> str:
        return (
            f"QToolButton {{ background: transparent; color: {TOK['ink_mute']}; "
            f"border: 0; border-radius: 6px; }} "
            f"QToolButton:hover {{ background: {TOK['bg_mute']}; color: {TOK['ink']}; }}"
        )

    @staticmethod
    def _qss_pct() -> str:
        return (
            f"QToolButton {{ background: transparent; color: {TOK['ink']}; "
            f"border: 0; }} "
            f"QToolButton:hover {{ background: {TOK['bg_mute']}; "
            f"border-radius:6px; }}"
        )

    def restyle(self):
        """Re-aplica los QSS con el TOK vivo (themeChanged)."""
        self.setStyleSheet(self._qss_zoom())
        for b in (self._btn_minus, self._btn_plus, self._btn_fit):
            b.setStyleSheet(self._qss_btn())
        self._lbl_pct.setStyleSheet(self._qss_pct())
        if getattr(self, "_divider", None) is not None:
            self._divider.setStyleSheet(f"background:{TOK['line']};")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("edZoom")
        self.setStyleSheet(self._qss_zoom())
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
        self._lbl_pct.setFont(qfont(FONT_VALUE))
        self._lbl_pct.setToolTip("Click → 100% (⌘0)")
        self._lbl_pct.setStyleSheet(self._qss_pct())
        self._lbl_pct.clicked.connect(self.zoomResetRequested.emit)
        lay.addWidget(self._lbl_pct)

        self._btn_plus = self._mk_btn("+", "Zoom in (⌘+)")
        self._btn_plus.clicked.connect(self.zoomInRequested.emit)
        lay.addWidget(self._btn_plus)

        # divider
        d = QFrame(self); d.setFixedWidth(1); d.setFixedHeight(20)
        d.setStyleSheet(f"background:{TOK['line']};")
        self._divider = d
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
        b.setFont(QFont(pfd_fonts.SANS, 13, QFont.Medium))  # glifo-ícono: tamaño geométrico, no tipografía (excepción 2g)
        b.setStyleSheet(self._qss_btn())
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
        self._palette_positioned = False   # primer show vs subsequent resize
        # parent each to host.viewport() so they render on top
        palette.setParent(host.viewport())
        zoom.setParent(host.viewport())
        palette.show(); zoom.show()
        palette.raise_(); zoom.raise_()
        # observar tanto el view como su viewport
        host.installEventFilter(self)
        host.viewport().installEventFilter(self)
        QTimer.singleShot(0, self._reposition)
        self._reposition()

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent
        if ev.type() in (QEvent.Resize, QEvent.Show, QEvent.LayoutRequest):
            self._reposition()
        return False

    def _reposition(self):
        vp = self._host.viewport()
        # Paleta: solo posicionar la primera vez (arriba izquierda).
        # Después el usuario puede arrastrarla y queremos respetar su
        # posición.  En resize, solo clampeamos si quedó fuera del
        # viewport.
        self._palette.adjustSize()
        pw = self._palette.width(); ph = self._palette.height()
        if not self._palette_positioned:
            self._palette.move(14, 14)
            if pw > 0 and ph > 0:
                self._palette_positioned = True
        else:
            # Clamp dentro del viewport por si el resize lo dejó fuera
            cur = self._palette.pos()
            x = max(0, min(cur.x(), vp.width()  - pw))
            y = max(0, min(cur.y(), vp.height() - ph))
            if (x, y) != (cur.x(), cur.y()):
                self._palette.move(x, y)
        self._palette.raise_()
        # Zoom abajo derecha (siempre auto-posicionado contra el border)
        self._zoom.adjustSize()
        z = self._zoom.size()
        self._zoom.move(max(14, vp.width()  - z.width()  - 14),
                        max(14, vp.height() - z.height() - 14))
        self._zoom.raise_()


# ════════════════════════════════════════════════════════
#  EQ_TYPE → ISA PALETTE TYPE MAPPING
# ════════════════════════════════════════════════════════

# Mapeo explícito eq_type canónico → silueta ISA.  Snapshot 1:1 del
# routing heurístico sobre el catálogo completo (equipment_costs.
# EQUIPMENT_DATA).  La heurística _isa_heuristic() queda solo como
# fallback para eq_types fuera de este dict (p.ej. equipos futuros:
# steam trap, strainer, deaerator).
# Ciclo 3 (3a): mapeo según la tabla eq_type → glifo de Design.  Los
# ◇ compartidos-a-propósito (decisión escrita del artboard): hx ×6
# (casco y tubo, TRABAJOS_FUTUROS §8), hx_whb ×2 (distinción de
# suministro, no de geometría), mezclador ×2 (sinónimos de proceso) y
# tambor ×2 (misma geometría horizontal).
EQ_TYPE_TO_ISA: Dict[str, str] = {
    "Boiler — fire tube": "caldera_fire",
    "Boiler — water tube": "caldera_water",
    "Centrifuge — decanter": "centrifuga_decanter",
    "Centrifuge — disc stack": "centrifuga_disc",
    "Compressor — axial": "compresor_axial",
    "Compressor — centrifugal": "compresor",
    "Compressor — reciprocating": "compresor_recip",
    "Compressor — rotary": "compresor_rotary",
    "Cooling tower — induced draft": "torre_enf",
    "Cooling tower — natural draft": "torre_nat",
    "Crystallizer": "cristalizador",
    "Cyclone — gas/solid": "ciclon",
    "Decanter — gravity": "tambor",
    "Dryer — drum": "secador",
    "Evaporator — vertical": "evaporador",
    "Fan — axial": "ventilador",
    "Fan — centrifugal radial": "ventilador_rad",
    "Filter — belt": "filtro",
    "Fired heater — non-reformer": "horno",
    "Fired heater — reformer": "horno_reformer",
    "Heat exch. — U-tube": "hx",
    "Heat exch. — WHB field erected": "hx_whb",
    "Heat exch. — WHB packaged": "hx_whb",
    "Heat exch. — air cooler": "hx_aircooler",
    "Heat exch. — condenser air-cooled": "hx_cond_air",
    "Heat exch. — condenser shell-tube": "hx",
    "Heat exch. — double pipe": "hx",
    "Heat exch. — fixed tube": "hx",
    "Heat exch. — flat plate": "hx_placa",
    "Heat exch. — floating head": "hx",
    "Heat exch. — kettle reboiler": "hx_kettle",
    "Heat exch. — multiple pipe": "hx",
    "Heat exch. — spiral plate": "hx_espiral",
    "Mixer — inline": "mezclador",
    "Mixer — static": "mezclador",
    "Packing — random": "empaque_rand",
    "Packing — structured": "empaque_struct",
    "Pump — centrifugal": "bomba",
    "Pump — positive displacement": "bomba_pd",
    "Pump — reciprocating": "bomba_recip",
    "Reactor — CSTR (agitado)": "reactor_cstr",
    "Reactor — PFR (tubular)": "reactor_pfr",
    "Reactor — autoclave": "reactor_autoclave",
    "Reactor — jacketed agitated": "reactor_jacket",
    "Reactor — jacketed non-agit.": "reactor_jacket_na",
    "Splitter — flow divider": "splitter",
    "Storage tank — cone roof": "tanque_cone",
    "Storage tank — floating roof": "tanque_float",
    "Tower (column shell)": "columna",
    "Tray — sieve": "platos_sieve",
    "Tray — valve": "platos_valve",
    "Valve — 3-way": "valvula_3way",
    "Valve — control globe": "valvula_globe",
    "Valve — relief": "valvula_relief",
    "Vessel — horizontal": "tambor",
    "Vessel — vertical": "separador",
}


def isa_type_for_eq(eq_type: str) -> Optional[str]:
    """Mapea un eq_type canónico del catálogo (e.g. 'Reactor — CSTR
    (agitado)', 'Heat exch. — flat plate') a una silueta ISA de
    BLOCK_DIMS (reactor/mezclador/separador/columna/hx/bomba/tanque
    más las específicas: valvula/compresor/ventilador/horno/caldera/
    ciclon/torre_enf/platos/tambor/centrifuga/filtro/secador y las
    variantes hx_kettle/hx_aircooler/hx_placa/cristalizador).

    Resuelve primero por el dict explícito EQ_TYPE_TO_ISA (cubre el
    catálogo completo); para eq_types fuera del dict cae a la
    heurística por categoría/substring de _isa_heuristic().

    Devuelve None si no hay match confiable — el caller decide el
    fallback honesto (IsaGlyphItem renderiza el SVG de pfd_symbols,
    o un rect neutro si tampoco hay símbolo).  NUNCA inventa una
    silueta de tanque para un equipo desconocido.
    """
    if not eq_type:
        return None
    mapped = EQ_TYPE_TO_ISA.get(eq_type)
    if mapped:
        return mapped
    return _isa_heuristic(eq_type)


def _isa_heuristic(eq_type: str) -> Optional[str]:
    """Routing heurístico por categoría de equipment_costs y substring
    del nombre — fallback para eq_types no presentes en EQ_TYPE_TO_ISA.
    Devuelve None si ningún patrón matchea con confianza.
    """
    if "ambient" in eq_type.lower() or "atmósfera" in eq_type.lower():
        return "ambient"
    try:
        import equipment_costs as _ec
        cat = _ec.EQUIPMENT_DATA.get(eq_type, {}).get("categoria", "")
    except Exception:
        cat = ""
    cat_l = (cat or "").lower()
    t = eq_type.lower()
    # por categoría primero (más confiable)
    if "reactor" in cat_l:           return "reactor"
    if "heat exchang" in cat_l:      return "hx"
    if "compress" in cat_l:          return "compresor"
    if "pump" in cat_l:              return "bomba"
    if "fan" in cat_l or "blower" in cat_l:     return "ventilador"
    if "valve" in cat_l:             return "valvula"
    if "mixer" in cat_l or "splitter" in cat_l: return "mezclador"
    if "storage" in cat_l:           return "tanque"
    if "fired heater" in cat_l:      return "horno"
    if "tray" in cat_l or "packing" in cat_l:   return "platos"
    if "utilit" in cat_l:
        if "cooling tower" in t:     return "torre_enf"
        if "boiler" in t:            return "caldera"
    if "vessel" in cat_l:
        if "tower" in t or "column" in t:
            return "columna"
        if "horizontal" in t or "decanter" in t:
            return "tambor"
        return "separador"
    if "solids" in cat_l or "dryer" in t or "evapor" in t or "cycl" in t \
       or "crystal" in t:
        if "cycl" in t:                        return "ciclon"
        if "centrif" in t:                     return "centrifuga"
        if "filter" in t or "filtro" in t:     return "filtro"
        if "dryer" in t or "secador" in t:     return "secador"
        return "separador"
    # fallback por substring del eq_type
    if "reactor" in t:               return "reactor"
    if "cooling tower" in t:         return "torre_enf"
    if "tower" in t or "column" in t or "destil" in t: return "columna"
    if "boiler" in t or "caldera" in t:                return "caldera"
    if "furnace" in t or "fired" in t or "horno" in t: return "horno"
    if "exchang" in t or "cooler" in t or "heater" in t \
       or "condenser" in t or "reboiler" in t:        return "hx"
    if "compress" in t or "compresor" in t:            return "compresor"
    if "fan" in t or "blower" in t or "ventilador" in t: return "ventilador"
    if "pump" in t or "bomba" in t:  return "bomba"
    if "valve" in t or "válvula" in t or "valvula" in t: return "valvula"
    if "tray" in t or "packing" in t or "plato" in t:    return "platos"
    if "centrif" in t:               return "centrifuga"
    if "filter" in t or "filtro" in t:                   return "filtro"
    if "mixer" in t or "mezclador" in t or "splitter" in t: return "mezclador"
    if "tank" in t or "tanque" in t or "storage" in t:      return "tanque"
    if "decanter" in t:              return "tambor"
    if "vessel" in t or "flash" in t or "separator" in t:   return "separador"
    return None  # sin match confiable — el caller resuelve el fallback


# ════════════════════════════════════════════════════════
#  IsaGlyphItem — QGraphicsItem on-canvas
# ════════════════════════════════════════════════════════

# Modelo visual del glifo (artboard 1b del rediseño) — DOS ejes
# independientes que conviven sin pisarse:
#
#   · STATUS del solver (ok/warning/error/stale/unrun/empty) → colorea el
#     CUERPO del símbolo: trazo + tinte de relleno, leídos en caliente de
#     tokens.STATUS_TOKEN / STATUS_FILL_TOKEN.  Reemplaza al halo-caja
#     _StatusHaloItem que dibujaba un rectángulo alrededor del equipo.
#       ok      → trazo verde + fill green_bg + dot verde
#       warning → trazo amber + fill amber_bg + chip "!"
#       error   → trazo danger + fill danger_bg + chip "!" (color + símbolo)
#       stale   → trazo ink_soft, glifo atenuado ("esto ya no vale")
#       unrun   → trazo ink_mute PUNTEADO en el propio glifo
#
#   · ESTADO de interacción (idle/hover/selected/solving) → anillos y
#     halos ALREDEDOR del símbolo, nunca el color del cuerpo:
#       hover    → halo accent_tint
#       selected → anillo dashed accent offset 6px (NO pisa el status)
#       solving  → ring circular dashed pulsante
ISA_INTERACTION_STATES = ("idle", "hover", "selected", "solving")


class IsaGlyphItem(QGraphicsItem):
    """QGraphicsItem que pinta la silueta ISA de un bloque dentro
    del rectángulo (0,0,W,H).

    El glyph se dibuja en sus dimensiones NATIVAS (BLOCK_DIMS del
    diseño) y luego se escala via QPainter.scale() para llenar el
    rect del bloque. Eso preserva las proporciones del símbolo y
    permite que BlockItem use cualquier W×H (las del catálogo
    pfd_symbols, las que ya tiene cableadas con port_coords).

    El status del solver se fija via `set_status(status)` (colorea el
    cuerpo del símbolo); el estado de interacción via `set_state(name)`
    con idle/hover/selected/solving (anillos alrededor).  Son ejes
    independientes: la selección nunca pisa el color de estado (1b).
    """

    def __init__(self, eq_type: str, w: float, h: float, parent=None):
        super().__init__(parent)
        self._eq_type = eq_type
        self._isa = isa_type_for_eq(eq_type)
        self._w = float(w)
        self._h = float(h)
        self._state = "idle"      # interacción: idle/hover/selected/solving
        self._status = "stale"    # solver: ok/warning/error/stale/unrun/empty
        self._warning = False
        self.setAcceptedMouseButtons(Qt.NoButton)  # no captura clicks
        self.setZValue(0.0)

    # ── API ───────────────────────────────────────────
    def set_state(self, state: str):
        """Estado de interacción ∈ {idle, hover, selected, solving}.
        (Compat: 'warning'/'error' llegados por la API vieja se derivan
        a set_status.)"""
        if state in ("warning", "error"):
            self.set_status(state)
            return
        if state not in ISA_INTERACTION_STATES:
            state = "idle"
        if state == self._state:
            return
        self._state = state
        self.update()

    def set_status(self, status: str):
        """Status del solver ∈ {ok, warning, error, stale, unrun, empty}."""
        status = status or "stale"
        if status == self._status:
            return
        self._status = status
        self.update()

    def set_warning(self, on: bool):
        if bool(on) != self._warning:
            self._warning = bool(on)
            self.update()

    def set_size(self, w: float, h: float):
        if abs(w - self._w) < 1e-3 and abs(h - self._h) < 1e-3:
            return
        self.prepareGeometryChange()
        self._w = float(w)
        self._h = float(h)
        self.update()

    def isa_type(self) -> Optional[str]:
        return self._isa

    def _pfd_pixmap(self):
        """Pixmap del símbolo pfd_symbols para eq_types sin silueta
        nativa.  Reusa el cache `_get_svg_pixmap` de flowsheet_qt
        (import lazy — flowsheet_qt ya está cargado en runtime y a su
        vez importa este módulo, no se puede importar top-level)."""
        try:
            import pfd_symbols as pfd
            svg = pfd.wrap_svg(
                pfd.EQ_TYPE_TO_SYMBOL.get(self._eq_type, ""),
                w=self._w, h=self._h)
            if not svg:
                return None
            from flowsheet_qt import _get_svg_pixmap
            return _get_svg_pixmap(self._eq_type, int(self._w),
                                   int(self._h), svg_str=svg)
        except Exception:
            return None

    # ── QGraphicsItem ─────────────────────────────────
    def boundingRect(self) -> QRectF:
        # Incluir margen para el anillo de selección dashed (+6px)
        # y el chip de warning (-8, 0 esquina sup-derecha).
        return QRectF(-8, -10, self._w + 16, self._h + 18)

    def paint(self, p: QPainter, option, widget=None):
        import tokens as _tokens
        status = self._status
        if self._warning and status not in ("error", "warning"):
            status = "warning"

        # Cuerpo del símbolo según STATUS (1b): trazo + tinte de relleno,
        # también en ok — el equipo cambia de color al resolver (verde
        # suave), no solo un dot que se pierde entre los puertos.
        # solving atenúa el trazo mientras el solver corre.
        stroke = QColor(_tokens.status_hex(status))
        if self._state == "solving":
            stroke = QColor(TOK["ink_soft"])
        stroke_w = _tokens.STROKE_OUTLINE
        dashed_body = (status in ("unrun", "empty"))
        fill_hex = _tokens.status_fill_hex(status)
        fill = QColor(fill_hex) if fill_hex else QColor(TOK["bg_elev"])

        p.setRenderHint(QPainter.Antialiasing, True)

        # Halo hover: bg accent_tint detrás del glyph
        if self._state == "hover":
            halo = QColor(TOK["accent_tint"]); halo.setAlphaF(0.7)
            p.setPen(Qt.NoPen); p.setBrush(QBrush(halo))
            p.drawRoundedRect(QRectF(-3, -3, self._w + 6, self._h + 6), 8, 8)

        # Halo solving: ring circular dashed pulsante
        if self._state == "solving":
            ring = QColor(TOK["accent"]); ring.setAlphaF(0.35)
            pen = QPen(ring, 1.5)
            pen.setStyle(Qt.DashLine); pen.setCapStyle(Qt.RoundCap)
            pen.setDashPattern([4, 6])
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            r = max(self._w, self._h) / 2 + 8
            p.drawEllipse(QPointF(self._w/2, self._h/2), r, r)

        if self._isa is not None:
            # Glyph ISA — escalar UNIFORMEMENTE (preservando
            # proporciones) desde sus dims nativas (BLOCK_DIMS) a las
            # dims reales del bloque.  Si las proporciones no calzan
            # exactas, el glyph queda centrado dentro del recuadro y
            # los puertos quedan en el border del recuadro como antes.
            # Esto evita el efecto "achatado" que ocurría con
            # scale(sx, sy) no-uniforme.
            native_w, native_h = BLOCK_DIMS.get(self._isa, (60, 60))
            scale = min(self._w / native_w, self._h / native_h)
            # offset para centrar el glyph dentro de la caja real
            ox = (self._w - native_w * scale) / 2.0
            oy = (self._h - native_h * scale) / 2.0
            p.save()
            if status == "stale":
                # desaturado — "esto ya no vale"
                p.setOpacity(0.72)
            p.translate(ox, oy)
            p.scale(scale, scale)
            BlockGlyph.draw(p, self._isa, native_w, native_h, stroke,
                            fill=fill,
                            stroke_width=stroke_w / max(scale, 0.1),
                            dashed=dashed_body)
            p.restore()
        else:
            # Fallback honesto para eq_types sin silueta nativa:
            # 1º el símbolo SVG de pfd_symbols; si tampoco existe,
            # rect redondeado NEUTRO (nunca una silueta de tanque
            # que el usuario pueda confundir con un equipo real).
            pm = self._pfd_pixmap()
            if pm is not None and not pm.isNull():
                p.drawPixmap(
                    QRectF(0, 0, self._w, self._h).toRect(), pm)
            else:
                pen = QPen(stroke, stroke_w)
                if dashed_body:
                    pen.setStyle(Qt.DashLine)
                p.setPen(pen)
                p.setBrush(QBrush(fill))
                p.drawRoundedRect(
                    QRectF(2, 2, self._w - 4, self._h - 4), 6, 6)

        # Anillo de selección dashed (offset 6px) — accent, separado del
        # color de estado: convive con ok/warning/error sin pisarlos.
        if self._state == "selected":
            pen = QPen(QColor(TOK["accent"]), 1.0)
            pen.setStyle(Qt.DashLine); pen.setDashPattern([3, 3])
            p.setPen(pen); p.setBrush(Qt.NoBrush)
            p.setOpacity(0.7)
            p.drawRoundedRect(QRectF(-6, -6, self._w + 12, self._h + 12), 10, 10)
            p.setOpacity(1.0)

        # Chip "!" esquina sup-derecha (warning/error) — color + símbolo,
        # legible también para daltonismo.
        if status in ("warning", "error"):
            chip_color = TOK["danger"] if status == "error" else TOK["amber"]
            cx = self._w - 2; cy = -2
            p.setBrush(QBrush(QColor(chip_color))); p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(cx, cy), 7.5, 7.5)
            p.setPen(QPen(QColor("white"), 1.2))
            p.setFont(QFont(pfd_fonts.SANS, 8, QFont.Bold))  # glifo-ícono: tamaño geométrico, no tipografía (excepción 2g)
            p.drawText(QRectF(cx-7, cy-7, 14, 14), Qt.AlignCenter, "!")
        elif status == "ok":
            # dot verde discreto — balance OK sin gritar
            p.setBrush(QBrush(QColor(TOK["green"]))); p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(self._w - 2, -2), 4.0, 4.0)
