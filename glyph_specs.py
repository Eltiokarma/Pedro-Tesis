"""Geometría de glifos del Design ciclo 3 (artboard 3a).

Transcripción LITERAL del subset SVG del bundle de Design
(`docs/design_ciclo3/`): cada spec es una lista de primitivas en caja
100×100 con rol por clase:

  · 'o'    — contorno: stroke tinta, STROKE_OUTLINE, non-scaling.
  · 'd'    — detalle:  stroke tinta al 52 %, STROKE_DETAIL, non-scaling.
  · 'body' — relleno del cuerpo (bg_elev o el tinte de estado del
             semáforo — el COLOR es estado, la FORMA es identidad).
  · 'dot'  — relleno de detalle (tinta 52 %), sin stroke.

Primitivas: ('rect', cls, x, y, w, h, rx) · ('circle', cls, cx, cy, r)
· ('line', cls, x1, y1, x2, y2[, dash]) · ('path', cls, d_string).
El renderer (draw_glyph) escala las COORDENADAS al rect destino pero
mantiene el grosor de trazo constante (vector-effect: non-scaling-stroke
del spec → el zoom no engorda el contorno).

Regla de trazo única del ciclo 3: STROKE_OUTLINE=1.6 · STROKE_DETAIL=1.0
· cap/join redondos.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen

try:
    from tokens import STROKE_OUTLINE, STROKE_DETAIL
except ImportError:
    STROKE_OUTLINE = 1.6
    STROKE_DETAIL = 1.0
DETAIL_ALPHA = 133          # 52 % de la tinta (0.52·255)

# ══════════════════════════════════════════════════════════════════════
# Specs — bundle ciclo 3, caja 100×100
# ══════════════════════════════════════════════════════════════════════
SPECS: Dict[str, List[tuple]] = {
    "bomba": [
        ("circle", "body_o", 50, 46, 26),
        ("path", "d", "M40 34 L66 46 L40 58 Z"),
        ("circle", "dot", 50, 46, 2.4),
        ("line", "o", 34, 82, 66, 82),
    ],
    "compresor": [
        ("path", "body_o", "M22 24 L78 40 L78 60 L22 76 Z"),
        ("path", "d", "M32 50 H64 M56 44 L64 50 L56 56"),
        ("line", "o", 36, 86, 64, 86),
    ],
    "compresor_recip": [
        ("rect", "body_o", 16, 36, 42, 26, 3),
        ("circle", "body_o", 37, 22, 9),
        ("line", "d", 34, 38, 34, 60),
        ("line", "d", 42, 38, 42, 60),
        ("line", "o", 50, 49, 72, 49),
        ("circle", "body_o", 80, 49, 8),
        ("line", "o", 30, 82, 72, 82),
    ],
    "reactor": [                     # g-reactor-cstr
        ("rect", "body_o", 24, 20, 52, 52, 7),
        ("rect", "dot", 45, 6, 10, 7),
        ("line", "d", 50, 13, 50, 56),
        ("line", "o", 39, 56, 61, 56),
        ("line", "d", 43, 50, 57, 62),
        ("line", "d", 36, 72, 36, 80),
        ("line", "d", 64, 72, 64, 80),
    ],
    "reactor_jacket": [              # g-reactor-jacket (familia ◇)
        ("rect", "body_o", 20, 18, 60, 56, 7),
        ("rect", "d", 27, 24, 46, 44, 4),
        ("rect", "dot", 45, 4, 10, 7),
        ("line", "d", 50, 11, 50, 54),
        ("line", "o", 40, 54, 60, 54),
    ],
    "reactor_pfr": [
        ("rect", "body_o", 14, 38, 72, 24, 11),
        ("path", "d", "M22 50 Q30 30 38 50 Q46 70 54 50 Q62 30 70 50"),
        ("path", "d", "M74 50 H84"),
    ],
    "caldera": [                     # g-caldera-fire (fire-tube)
        ("rect", "body_o", 18, 30, 64, 40, 15),
        ("line", "d", 28, 42, 72, 42),
        ("line", "d", 28, 50, 72, 50),
        ("line", "d", 28, 58, 72, 58),
        ("path", "d", "M22 74 L26 66 L30 74"),
    ],
    "caldera_water": [               # g-caldera-water (water-tube)
        ("rect", "body_o", 30, 14, 40, 16, 8),
        ("rect", "body_o", 32, 66, 36, 12, 6),
        ("line", "d", 38, 30, 38, 66),
        ("line", "d", 46, 30, 46, 66),
        ("line", "d", 54, 30, 54, 66),
        ("line", "d", 62, 30, 62, 66),
        ("line", "o", 50, 14, 50, 6),
        ("path", "d", "M42 62 L46 54 L50 62 L54 52 L58 62"),
    ],
    "platos": [                      # g-platos-sieve
        ("rect", "body_o", 36, 12, 28, 76, 3),
        ("circle", "dot", 43, 28, 1.3), ("circle", "dot", 50, 28, 1.3),
        ("circle", "dot", 57, 28, 1.3),
        ("circle", "dot", 43, 44, 1.3), ("circle", "dot", 50, 44, 1.3),
        ("circle", "dot", 57, 44, 1.3),
        ("circle", "dot", 43, 60, 1.3), ("circle", "dot", 50, 60, 1.3),
        ("circle", "dot", 57, 60, 1.3),
        ("line", "d", 40, 28, 60, 28),
        ("line", "d", 40, 44, 60, 44),
        ("line", "d", 40, 60, 60, 60),
        ("line", "d", 40, 76, 60, 76),
    ],
    "platos_valve": [                # sieve + cheurones ⌃ (bundle 3a)
        ("rect", "body_o", 36, 12, 28, 76, 3),
        ("line", "d", 40, 28, 60, 28),
        ("line", "d", 40, 44, 60, 44),
        ("line", "d", 40, 60, 60, 60),
        ("line", "d", 40, 76, 60, 76),
        ("path", "d", "M45 25 L50 21 L55 25"),
        ("path", "d", "M45 41 L50 37 L55 41"),
        ("path", "d", "M45 57 L50 53 L55 57"),
        ("path", "d", "M45 73 L50 69 L55 73"),
    ],
    "empaque": [                     # g-empaque-struct
        ("rect", "body_o", 36, 12, 28, 76, 3),
        ("path", "d", "M40 22 L60 42 M40 42 L60 22 M40 42 L60 62 "
                      "M40 62 L60 42 M40 62 L60 82 M40 82 L60 62"),
    ],
    "hx": [
        ("rect", "body_o", 16, 38, 68, 24, 4),
        ("line", "d", 26, 38, 26, 62),
        ("line", "d", 74, 38, 74, 62),
        ("path", "d", "M26 45 Q50 38 74 45 M26 50 Q50 44 74 50 "
                      "M26 55 Q50 50 74 55"),
        ("line", "o", 40, 38, 40, 32),
        ("line", "o", 60, 62, 60, 68),
    ],
    "hx_kettle": [
        ("rect", "body_o", 16, 42, 68, 34, 14),
        ("path", "body_o", "M38 42 A12 10 0 0 1 62 42 Z"),
        ("path", "d", "M24 56 H70 A6 6 0 0 1 70 64 H24"),
        ("line", "d", 24, 70, 76, 70, (3, 2)),
    ],
    "hx_whb": [
        ("rect", "body_o", 16, 34, 68, 42, 8),
        ("rect", "body_o", 34, 12, 32, 16, 8),
        ("line", "d", 42, 28, 42, 34),
        ("line", "d", 58, 28, 58, 34),
        ("line", "d", 24, 54, 76, 54),
        ("line", "d", 24, 60, 76, 60),
        ("line", "o", 50, 12, 50, 4),
    ],
    "columna": [
        ("rect", "body_o", 38, 10, 24, 80, 4),
        ("line", "d", 42, 22, 58, 22),
        ("line", "d", 42, 32, 58, 32),
        ("line", "d", 42, 42, 58, 42),
        ("line", "d", 42, 52, 58, 52),
        ("line", "d", 42, 62, 58, 62),
        ("line", "d", 42, 72, 58, 72),
        ("line", "o", 38, 50, 30, 50),
    ],
    "mezclador": [
        ("path", "o", "M18 24 L48 48 L18 76 M18 24 L82 48 M18 76 L82 48"),
        ("circle", "body_o", 50, 49, 5),
    ],
    "splitter": [
        ("path", "o", "M18 50 H50 M50 50 L82 22 M50 50 L82 78"),
        ("path", "d", "M74 22 H82 M82 22 L78 30 M74 78 H82 M82 78 L78 70"),
        ("circle", "body_o", 50, 50, 5),
    ],
    "torre_enf": [                   # induced draft: ventilador en la cima
        ("path", "body_o", "M30 82 Q37 46 34 14 L66 14 Q63 46 70 82 Z"),
        ("circle", "body_o", 50, 14, 10),
        ("path", "d", "M50 14 L50 6 M50 14 L57 19 M50 14 L43 19"),
        ("line", "d", 34, 70, 66, 70),
    ],
    "torre_nat": [                   # natural draft: hiperbólico + penacho
        ("path", "body_o", "M28 84 Q40 48 34 12 L66 12 Q60 48 72 84 Z"),
        ("path", "d", "M44 12 Q48 6 54 10"),
        ("line", "d", 34, 72, 66, 72),
    ],
    "valvula": [                     # g-valvula-globe
        ("path", "body_o", "M18 46 L18 70 L50 58 Z"),
        ("path", "body_o", "M82 46 L82 70 L50 58 Z"),
        ("line", "d", 50, 58, 50, 32),
        ("path", "body_o", "M37 32 A13 13 0 0 1 63 32 Z"),
        ("line", "d", 37, 32, 63, 32),
    ],
    "tambor": [
        ("rect", "body_o", 12, 38, 76, 24, 12),
        ("line", "d", 20, 52, 80, 52, (3, 2)),
        ("line", "d", 34, 62, 34, 72),
        ("line", "d", 66, 62, 66, 72),
    ],
    "filtro": [
        ("rect", "body_o", 20, 18, 60, 60, 5),
        ("line", "d", 20, 42, 80, 42),
        ("line", "d", 20, 58, 80, 58),
        ("path", "d", "M28 58 L34 42 M40 58 L46 42 M52 58 L58 42 "
                      "M64 58 L70 42"),
    ],
}


# ══════════════════════════════════════════════════════════════════════
# Parser de paths SVG (subset: M L H V Q A Z, absolutos — lo que usa
# el bundle) → QPainterPath en coordenadas de la caja 100×100.
# ══════════════════════════════════════════════════════════════════════
_TOKEN_RE = re.compile(r"([MLHVQAZ])|(-?\d*\.?\d+)", re.I)


def _arc_to(path: QPainterPath, x1, y1, rx, ry, phi_deg, laf, sf, x2, y2):
    """Arco elíptico SVG (endpoint param.) → arcTo de Qt.
    Conversión endpoint→centro (W3C SVG 1.1 §F.6.5)."""
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        path.lineTo(x2, y2)
        return
    phi = math.radians(phi_deg)
    cphi, sphi = math.cos(phi), math.sin(phi)
    dx2, dy2 = (x1 - x2) / 2.0, (y1 - y2) / 2.0
    x1p = cphi * dx2 + sphi * dy2
    y1p = -sphi * dx2 + cphi * dy2
    rx, ry = abs(rx), abs(ry)
    lam = (x1p / rx) ** 2 + (y1p / ry) ** 2
    if lam > 1:
        s = math.sqrt(lam)
        rx *= s
        ry *= s
    num = rx * rx * ry * ry - rx * rx * y1p * y1p - ry * ry * x1p * x1p
    den = rx * rx * y1p * y1p + ry * ry * x1p * x1p
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if laf == sf:
        co = -co
    cxp = co * rx * y1p / ry
    cyp = -co * ry * x1p / rx
    cx = cphi * cxp - sphi * cyp + (x1 + x2) / 2.0
    cy = sphi * cxp + cphi * cyp + (y1 + y2) / 2.0

    def ang(ux, uy, vx, vy):
        d = math.hypot(ux, uy) * math.hypot(vx, vy)
        if d == 0:
            return 0.0
        c = max(-1.0, min(1.0, (ux * vx + uy * vy) / d))
        a = math.degrees(math.acos(c))
        return -a if (ux * vy - uy * vx) < 0 else a

    th1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dth = ang((x1p - cxp) / rx, (y1p - cyp) / ry,
              (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sf and dth > 0:
        dth -= 360
    elif sf and dth < 0:
        dth += 360
    rect = QRectF(cx - rx, cy - ry, 2 * rx, 2 * ry)
    # Qt: ángulos CCW positivos, 0° a las 3; SVG: y hacia abajo → invertir
    path.arcTo(rect, -th1, -dth)


def parse_path(d: str) -> QPainterPath:
    path = QPainterPath()
    tokens = _TOKEN_RE.findall(d)
    i = 0
    cur = QPointF(0, 0)
    start = QPointF(0, 0)

    def num():
        nonlocal i
        while i < len(tokens) and not tokens[i][1]:
            i += 1
        v = float(tokens[i][1])
        i += 1
        return v

    while i < len(tokens):
        cmd, _ = tokens[i]
        if not cmd:
            i += 1
            continue
        i += 1
        c = cmd.upper()
        if c == "M":
            cur = QPointF(num(), num())
            start = QPointF(cur)
            path.moveTo(cur)
        elif c == "L":
            cur = QPointF(num(), num())
            path.lineTo(cur)
        elif c == "H":
            cur = QPointF(num(), cur.y())
            path.lineTo(cur)
        elif c == "V":
            cur = QPointF(cur.x(), num())
            path.lineTo(cur)
        elif c == "Q":
            cx_, cy_ = num(), num()
            cur = QPointF(num(), num())
            path.quadTo(QPointF(cx_, cy_), cur)
        elif c == "A":
            rx, ry, rot = num(), num(), num()
            laf, sf = int(num()), int(num())
            x2, y2 = num(), num()
            _arc_to(path, cur.x(), cur.y(), rx, ry, rot, laf, sf, x2, y2)
            cur = QPointF(x2, y2)
        elif c == "Z":
            path.closeSubpath()
            cur = QPointF(start)
    return path


# Cache spec_id → lista de (cls, QPainterPath | primitiva escalable)
_PATH_CACHE: Dict[str, List[tuple]] = {}


def _compiled(spec_id: str) -> Optional[List[tuple]]:
    if spec_id in _PATH_CACHE:
        return _PATH_CACHE[spec_id]
    spec = SPECS.get(spec_id)
    if spec is None:
        return None
    out = []
    for prim in spec:
        kind, cls = prim[0], prim[1]
        if kind == "path":
            out.append((cls, "path", parse_path(prim[2]), None))
        elif kind == "rect":
            x, y, w, h = prim[2:6]
            rx = prim[6] if len(prim) > 6 else 0
            p = QPainterPath()
            p.addRoundedRect(QRectF(x, y, w, h), rx, rx)
            out.append((cls, "path", p, None))
        elif kind == "circle":
            cx, cy, r = prim[2:5]
            p = QPainterPath()
            p.addEllipse(QPointF(cx, cy), r, r)
            out.append((cls, "path", p, None))
        elif kind == "line":
            x1, y1, x2, y2 = prim[2:6]
            dash = prim[6] if len(prim) > 6 else None
            p = QPainterPath()
            p.moveTo(x1, y1)
            p.lineTo(x2, y2)
            out.append((cls, "path", p, dash))
    _PATH_CACHE[spec_id] = out
    return out


def has_spec(spec_id: str) -> bool:
    return spec_id in SPECS


def draw_glyph(p: QPainter, spec_id: str, w: float, h: float,
               stroke: QColor, fill_brush: QBrush,
               sw: float = STROKE_OUTLINE, dashed: bool = False) -> bool:
    """Pinta el glifo del spec en (0,0,w,h). El grosor de trazo NO
    escala con w/h (non-scaling-stroke): sw es el contorno; el detalle
    va a sw·(STROKE_DETAIL/STROKE_OUTLINE) con la tinta al 52 %.

    Devuelve False si no hay spec (el caller usa su fallback)."""
    prims = _compiled(spec_id)
    if prims is None:
        return False
    sx, sy = w / 100.0, h / 100.0
    detail = QColor(stroke)
    detail.setAlpha(DETAIL_ALPHA)

    pen_o = QPen(stroke, sw)
    pen_o.setCapStyle(Qt.RoundCap)
    pen_o.setJoinStyle(Qt.RoundJoin)
    pen_o.setCosmetic(True)          # non-scaling-stroke
    if dashed:
        pen_o.setStyle(Qt.DashLine)
    pen_d = QPen(detail, sw * (STROKE_DETAIL / STROKE_OUTLINE))
    pen_d.setCapStyle(Qt.RoundCap)
    pen_d.setJoinStyle(Qt.RoundJoin)
    pen_d.setCosmetic(True)

    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.scale(sx, sy)
    for cls, _, path, dash in prims:
        if cls == "body_o":
            p.setPen(pen_o)
            p.setBrush(fill_brush)
        elif cls == "o":
            p.setPen(pen_o)
            p.setBrush(Qt.NoBrush)
        elif cls == "d":
            pen = QPen(pen_d)
            if dash:
                pen.setDashPattern(list(dash))
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
        elif cls == "dot":
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(detail))
        p.drawPath(path)
    p.restore()
    return True
