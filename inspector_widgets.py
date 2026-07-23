"""inspector_widgets.py — Átomos visuales del panel de Diagnóstico (Fase 2).

Componentes del rediseño (handoff §3), portados del mockup HTML/CSS a Qt:
  · MetricCard   — tarjeta valor+label con ribbon de 3px por `state`.
                   Ciclo 4 (4b): columna que fluye (el sub crece, no se
                   recorta) + escala de clasificación opcional.
  · ClassificationScale — barra 9px de bandas frío/acento/cálido con
                   marcador (N_s radial·mixto·axial, etc.) — artboard 4b.
  · MetricGrid   — grilla responsiva (cols = max(1,min(3, w//150))).
  · StatusBadge  — pill dot+texto por `kind`.
  · GaugePill    — medidor radial (arco 180°) para fracciones 0..1.
  · DeltaBar     — fila de 3 celdas [label][track flex][valor auto] —
                   el valor nunca se recorta (bug 2 del bundle ciclo 4).

Patrón del repo (igual que streams_table._MassBar/_StackedBar):
  · QWidget/QFrame + paintEvent(QPainter, Antialiasing).
  · TODO color desde block_inspector.TOK, LEÍDO EN CALIENTE en cada paint
    (apply_preferences muta TOK in-place) → respeta temas/acentos.
  · Suscripción a _PrefsBus.signal() para re-pintar/re-construir al cambiar
    tema/densidad/acento (igual que _on_prefs_changed del panel).
  · Headless-safe: sólo Qt, sin matplotlib. Si Qt falta, no se importa.

Mapeo state→token de ribbon (handoff §2 + extensión aprobada, sin tocar TOK):
  spec→spec_ribbon, auto→auto_ribbon, ok→green, warn→amber, alert→orange,
  danger→danger, accent→accent, info→spec, neutral→ink_soft, sinnott→sinnott.
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QBrush, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QSizePolicy,
)

import pfd_fonts
import block_inspector as _bi   # para leer TOK/ROW_PAD en caliente
from block_inspector import _PrefsBus
from tokens import qfont, FONT_VALUE, FONT_HINT, FONT_LABEL


# ─────────────────────────────────────────────────────────────────────
#  Mapeo state/kind → token (color principal) y token de fondo (_bg).
#  Se resuelve por NOMBRE; el valor se lee de TOK en cada uso (hot).
# ─────────────────────────────────────────────────────────────────────
_STATE_RIBBON = {
    "spec": "spec_ribbon", "auto": "auto_ribbon", "ok": "green",
    "warn": "amber", "alert": "orange", "danger": "danger",
    "accent": "accent", "info": "spec", "neutral": "ink_soft",
    "sinnott": "sinnott",
}
# color de tinta para el valor cuando el state es semántico
_STATE_INK = {
    "ok": "green", "warn": "amber", "alert": "orange", "danger": "danger",
    "spec": "spec", "accent": "accent", "info": "spec", "sinnott": "sinnott",
}
# kind del StatusBadge → (token_ink, token_bg)
_KIND_TOKENS = {
    "ok": ("green", "green_bg"), "warn": ("amber", "amber_bg"),
    "alert": ("orange", "orange_bg"), "danger": ("danger", "danger_bg"),
    "info": ("spec", "spec_bg"), "accent": ("accent", "accent_tint"),
    "neutral": ("ink_soft", "bg_mute"), "sinnott": ("sinnott", "sinnott_bg"),
}
# kind de barra → token de fill
_BAR_KIND = {
    "in": "spec", "out": "orange", "ok": "green", "warn": "amber",
    "danger": "danger", "accent": "accent",
}


def _tok(name: str, fallback: str = "ink") -> str:
    """Lee TOK[name] en caliente (TOK muta in-place al cambiar tema).
    Sin fallback hex: "ink" siempre existe en la paleta — un hex fijo
    derivaría en silencio al cambiar tema (§G.3 auditoría 2)."""
    return _bi.TOK.get(name, _bi.TOK[fallback])


# ─────────────────────────────────────────────────────────────────────
#  ClassificationScale — barra de clasificación de la MetricCard (4b)
# ─────────────────────────────────────────────────────────────────────
class ClassificationScale(QWidget):
    """Escala de clasificación del bundle ciclo 4 (artboard 4b): barra
    de 9 px con bandas (pale del eje frío/cálido + tint del acento),
    marcador de 2 px `ink` con halo `bg_elev`, y ticks con el nombre de
    cada banda.  P. ej. N_s: radial · mixto · axial (Perry fig. 10-32).

    spec = {"marker": float, "max": float, "min": float (default 0),
            "bands": [{"label": str, "to": float, "kind":
                       "cool"|"accent"|"warm"}, ...]}
    """

    BAR_H = 9
    _BAND_BG = {"cool": "service_cold_pale", "accent": "accent_tint",
                "warm": "service_hot_pale"}

    def __init__(self, spec: dict, parent=None):
        super().__init__(parent)
        self._spec = dict(spec or {})
        self.setFixedHeight(24)          # barra 9 + gap 3 + ticks 12
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        _PrefsBus.signal().connect(self.update)

    def paintEvent(self, ev):
        if self.width() <= 0 or self.height() <= 0:
            return   # widget 0×0 (thrash de layout) → QPainter(self) no activaría
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width()
        if w < 12:
            return
        s = self._spec
        bands = s.get("bands") or []
        lo = float(s.get("min", 0.0))
        hi = float(s.get("max", 1.0) or 1.0)
        if hi - lo <= 0 or not bands:
            return
        # bandas (clip redondeado radius 5)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, self.BAR_H), 5, 5)
        p.save()
        p.setClipPath(path)
        prev = lo
        for b in bands:
            to = float(b.get("to", hi))
            x0 = (prev - lo) / (hi - lo) * w
            x1 = (to - lo) / (hi - lo) * w
            p.fillRect(QRectF(x0, 0, x1 - x0, self.BAR_H),
                       QColor(_tok(self._BAND_BG.get(b.get("kind"),
                                                     "bg_sunk"))))
            prev = to
        p.restore()
        # marcador: línea 2px ink con halo bg_elev (spec 4b)
        mk = s.get("marker")
        if mk is not None:
            f = (float(mk) - lo) / (hi - lo)
            f = 0.0 if f < 0.0 else (1.0 if f > 1.0 else f)
            mx = f * w
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(_tok("bg_elev"))))
            p.drawRect(QRectF(mx - 2.5, -2, 5, self.BAR_H + 4))
            p.setBrush(QBrush(QColor(_tok("ink"))))
            p.drawRect(QRectF(mx - 1, -2, 2, self.BAR_H + 4))
        # ticks (nombres de banda) — micro-tipografía de la escala de
        # clasificación (spec dibujable 4b: 9px/600), no un tamaño libre
        f_t = QFont(pfd_fonts.SANS, 7, QFont.DemiBold)
        p.setFont(f_t)
        p.setPen(QColor(_tok("ink_soft")))
        n = len(bands)
        for i, b in enumerate(bands):
            align = (Qt.AlignLeft if i == 0 else
                     Qt.AlignRight if i == n - 1 else Qt.AlignHCenter)
            p.drawText(QRectF(0, self.BAR_H + 3, w, 11),
                       align | Qt.AlignVCenter, str(b.get("label", "")))


# ─────────────────────────────────────────────────────────────────────
#  MetricCard
# ─────────────────────────────────────────────────────────────────────
class MetricCard(QFrame):
    """Tarjeta: label (upper) + valor (mono grande) + unidad + sub +
    escala de clasificación opcional, con ribbon de 3 px a la izquierda
    pintado con el color de `state`.

    Ciclo 4 (bug 3 del bundle): columna que FLUYE — el sub es una fila
    propia con word-wrap y la tarjeta crece (nada de posición absoluta
    a h−16 que recortaba «Perry fig. 10-32»).  Pad 9/12/10/15,
    min-height 58, radius 8."""

    def __init__(self, key="", label="", value="", unit="", state="auto",
                 sub=None, flag=None, span=1, scale=None, parent=None):
        super().__init__(parent)
        self.key = key
        self._label = str(label)
        self._value = str(value)
        self._unit = str(unit or "")
        self._state = state if state in _STATE_RIBBON else "auto"
        self._sub = sub
        self._flag = flag
        self.span = max(1, int(span))
        self.setMinimumHeight(58)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        lay = QVBoxLayout(self)
        # l=15 (12 + ribbon 3) · t=9 · r=12 · b=10 — spec 4b
        lay.setContentsMargins(15, 9, 12, 10)
        lay.setSpacing(3)

        # label (fila 1) — deja sitio al flag pintado arriba-derecha
        self._lab_w = QLabel(self._label.upper())
        f_lab = qfont(FONT_LABEL)
        f_lab.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
        self._lab_w.setFont(f_lab)
        lay.addWidget(self._lab_w)

        # valor + unidad (fila 2, baseline)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        self._val_w = QLabel(self._value)
        f_val = qfont(FONT_VALUE)
        f_val.setWeight(QFont.DemiBold)
        self._val_w.setFont(f_val)
        row.addWidget(self._val_w, 0, Qt.AlignBottom)
        self._unit_w = None
        if self._unit:
            self._unit_w = QLabel(self._unit)
            self._unit_w.setFont(qfont(FONT_HINT))
            row.addWidget(self._unit_w, 0, Qt.AlignBottom)
        row.addStretch(1)
        lay.addLayout(row)

        # sub (fila 3): FLUYE — word-wrap, la tarjeta crece (bug 3)
        self._sub_w = None
        if self._sub:
            self._sub_w = QLabel(str(self._sub))
            self._sub_w.setFont(qfont(FONT_HINT))
            self._sub_w.setWordWrap(True)
            lay.addWidget(self._sub_w)

        # escala de clasificación (fila 4, opcional — artboard 4b)
        self._scale_w = None
        if scale:
            self._scale_w = ClassificationScale(scale)
            lay.addSpacing(3)
            lay.addWidget(self._scale_w)

        self._retint()
        _PrefsBus.signal().connect(self._on_prefs)

    def _retint(self):
        """Aplica tintas desde TOK (en caliente al cambiar tema)."""
        base = "background:transparent; border:0;"
        self._lab_w.setStyleSheet(f"color:{_tok('ink_soft')}; {base}")
        ink = _tok(_STATE_INK.get(self._state, "ink"), "ink") \
            if self._state in _STATE_INK else _tok("ink")
        self._val_w.setStyleSheet(f"color:{ink}; {base}")
        if self._unit_w is not None:
            self._unit_w.setStyleSheet(f"color:{_tok('ink_soft')}; {base}")
        if self._sub_w is not None:
            self._sub_w.setStyleSheet(f"color:{_tok('ink_mute')}; {base}")

    def _on_prefs(self):
        self._retint()
        self.update()

    def paintEvent(self, ev):
        if self.width() <= 0 or self.height() <= 0:
            return   # widget 0×0 (thrash de layout) → QPainter(self) no activaría
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        if w < 6 or h < 6:
            return   # demasiado chico para pintar (evita rects negativos / GDI)
        r = 8.0
        # fondo + borde redondeado
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r, r)
        p.fillPath(path, QBrush(QColor(_tok("bg_elev"))))
        p.setPen(QPen(QColor(_tok("line")), 1))
        p.drawPath(path)
        # ribbon 3px (clip al rect redondeado)
        p.save()
        p.setClipPath(path)
        p.fillRect(QRectF(0, 0, 3, h),
                   QBrush(QColor(_tok(_STATE_RIBBON[self._state]))))
        p.restore()
        # flag (chip arriba-derecha) — sólo si entra
        if self._flag and w > 60:
            p.setFont(qfont(FONT_LABEL))
            ftxt = str(self._flag)
            fw = p.fontMetrics().horizontalAdvance(ftxt) + 10
            chip = QRectF(w - fw - 6, 6, fw, 14)
            ink_t, bg_t = _KIND_TOKENS.get(
                self._state if self._state in _KIND_TOKENS else "neutral",
                ("ink_soft", "bg_mute"))
            p.setBrush(QBrush(QColor(_tok(bg_t)))); p.setPen(Qt.NoPen)
            p.drawRoundedRect(chip, 6, 6)
            p.setPen(QColor(_tok(ink_t)))
            p.drawText(chip, Qt.AlignCenter, ftxt)


# ─────────────────────────────────────────────────────────────────────
#  MetricGrid — grilla responsiva
# ─────────────────────────────────────────────────────────────────────
class MetricGrid(QWidget):
    """QGridLayout que reflowea: cols = max(1, min(3, ancho//150))."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: List[QWidget] = []
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(8)
        self._grid.setVerticalSpacing(8)
        self._cols = 0

    def add(self, widget: QWidget):
        self._cards.append(widget)
        self._relayout(force=True)

    def _calc_cols(self) -> int:
        w = max(self.width(), 1)
        return max(1, min(3, w // 150))

    def _relayout(self, force=False):
        cols = self._calc_cols()
        if cols == self._cols and not force:
            return
        self._cols = cols
        # limpiar layout (sin destruir widgets)
        while self._grid.count():
            self._grid.takeAt(0)
        r = c = 0
        for card in self._cards:
            span = min(getattr(card, "span", 1), cols)
            if c + span > cols:
                r += 1
                c = 0
            self._grid.addWidget(card, r, c, 1, span)
            c += span
            if c >= cols:
                r += 1
                c = 0
        for i in range(cols):
            self._grid.setColumnStretch(i, 1)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._relayout()


# ─────────────────────────────────────────────────────────────────────
#  StatusBadge
# ─────────────────────────────────────────────────────────────────────
class StatusBadge(QFrame):
    """Pill: dot Ø7 + texto. Fondo {kind}_bg, ink {kind}."""

    def __init__(self, text="", kind="neutral", parent=None, lg=False):
        super().__init__(parent)
        self._text = str(text)
        self._kind = kind if kind in _KIND_TOKENS else "neutral"
        self._lg = bool(lg)              # variante grande (veredicto de héroe)
        self.setFixedHeight(28 if self._lg else 20)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        _PrefsBus.signal().connect(self.update)

    # geometría dependiente de tamaño (lg vs normal)
    @property
    def _fs(self):
        # glifo-ícono: tamaño geométrico, no tipografía (excepción 2g)
        # (sizing dinámico del widget custom, acoplado a _dot/_padl/_padr)
        return 11 if self._lg else 9        # font size
    @property
    def _dot(self):
        return 9.0 if self._lg else 7.0     # diámetro del dot
    @property
    def _padl(self):
        return 26 if self._lg else 20       # x del texto
    @property
    def _padr(self):
        return 30 if self._lg else 24       # margen total dot+paddings

    def _metrics_w(self) -> int:
        f = QFont(pfd_fonts.SANS, self._fs, QFont.DemiBold)
        from PySide6.QtGui import QFontMetrics
        return QFontMetrics(f).horizontalAdvance(self._text)

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(self._metrics_w() + self._padr + 8,
                     28 if self._lg else 20)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, ev):
        if self.width() <= 0 or self.height() <= 0:
            return   # widget 0×0 (thrash de layout) → QPainter(self) no activaría
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        if w < 6 or h < 6:
            return
        ink_t, bg_t = _KIND_TOKENS[self._kind]
        p.setBrush(QBrush(QColor(_tok(bg_t)))); p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(0, 0, w, h), 6, 6)
        txt_w = max(0, w - self._padr)
        # dot
        d = self._dot
        p.setBrush(QBrush(QColor(_tok(ink_t))))
        p.drawEllipse(QRectF(8, h / 2 - d / 2, d, d))
        # texto
        p.setPen(QColor(_tok(ink_t)))
        p.setFont(QFont(pfd_fonts.SANS, self._fs, QFont.DemiBold))
        p.drawText(QRectF(self._padl, 0, txt_w, h),
                   Qt.AlignLeft | Qt.AlignVCenter, self._text)


# ─────────────────────────────────────────────────────────────────────
#  GaugePill — medidor radial 180°
# ─────────────────────────────────────────────────────────────────────
class GaugePill(QWidget):
    """Arco de 180° (π→0). Track bg_sunk, arco de valor `color` (default
    accent), aguja, valor central mono. `marker` (frac) = tick de umbral."""

    def __init__(self, key="", label="", value=0.0, text=None, suffix="",
                 marker=None, color=None, span=2, parent=None):
        super().__init__(parent)
        self.key = key
        self._label = str(label)
        self._value = max(0.0, min(1.0, float(value)))
        self._text = text
        self._suffix = str(suffix or "")
        self._marker = marker
        self._color_tok = color or "accent"
        self.span = max(1, int(span))
        self.setMinimumSize(116, 70)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        _PrefsBus.signal().connect(self.update)

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(140, 70)

    def paintEvent(self, ev):
        if self.width() <= 0 or self.height() <= 0:
            return   # widget 0×0 (thrash de layout) → QPainter(self) no activaría
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        if w < 8 or h < 8:
            return
        m = 10
        diam = min(w - 2 * m, (h - 18) * 2)
        diam = max(diam, 20)
        cx = w / 2.0
        cy = h - 14
        arc = QRectF(cx - diam / 2, cy - diam / 2, diam, diam)
        # track (180°: de 180° a 0°)
        pen = QPen(QColor(_tok("bg_sunk")), 7)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(arc, 0 * 16, 180 * 16)
        # arco de valor
        pen.setColor(QColor(_tok(self._color_tok)))
        p.setPen(pen)
        span_deg = int(180 * self._value)
        p.drawArc(arc, (180 - span_deg) * 16, span_deg * 16)
        # marker (umbral)
        if self._marker is not None:
            mk = max(0.0, min(1.0, float(self._marker)))
            import math
            ang = math.pi * (1.0 - mk)
            r_out = diam / 2 + 2
            r_in = diam / 2 - 9
            mpen = QPen(QColor(_tok("danger")), 2)
            p.setPen(mpen)
            p.drawLine(int(cx + r_in * math.cos(ang)),
                       int(cy - r_in * math.sin(ang)),
                       int(cx + r_out * math.cos(ang)),
                       int(cy - r_out * math.sin(ang)))
        # valor central
        txt = self._text if self._text is not None \
            else f"{self._value * 100:.0f}"
        p.setPen(QColor(_tok("ink")))
        p.setFont(qfont(FONT_VALUE))
        p.drawText(QRectF(0, cy - 24, w, 22),
                   Qt.AlignHCenter | Qt.AlignVCenter, f"{txt}{self._suffix}")
        # label
        p.setPen(QColor(_tok("ink_soft")))
        f_lab = qfont(FONT_LABEL)
        f_lab.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
        p.setFont(f_lab)
        p.drawText(QRectF(0, h - 13, w, 12),
                   Qt.AlignHCenter | Qt.AlignVCenter, self._label.upper())


# ─────────────────────────────────────────────────────────────────────
#  DeltaBar — fila [label][track][valor]
# ─────────────────────────────────────────────────────────────────────
class DeltaBar(QFrame):
    """Fila horizontal de 3 celdas: [label] · [track flex] · [valor en
    celda propia].  Bug 2 del bundle ciclo 4: el valor vive FUERA de la
    barra, con su ancho medido del texto → nunca se recorta («00000.0»
    al ancho real del panel).  El track absorbe el resto (min-width 0)."""

    LABEL_MIN = 38     # spec 4b: [label 38px] · [track flex] · [valor auto]

    def __init__(self, label="", frac=0.0, value="", kind="accent",
                 parent=None):
        super().__init__(parent)
        self._label = str(label)
        self._frac = max(0.0, min(1.0, float(frac)))
        self._value = str(value)
        self._kind = kind if kind in _BAR_KIND else "accent"
        self.setFixedHeight(24)   # +4px: label/valor pasan de mono 8pt a FONT_VALUE (11.5pt)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        _PrefsBus.signal().connect(self.update)

    def paintEvent(self, ev):
        if self.width() <= 0 or self.height() <= 0:
            return   # widget 0×0 (thrash de layout) → QPainter(self) no activaría
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        if w < 6 or h < 6:
            return
        from PySide6.QtGui import QFontMetrics
        f_lab = qfont(FONT_VALUE)
        f_val = qfont(FONT_VALUE); f_val.setWeight(QFont.DemiBold)
        # celda de valor: ancho = el del texto (nunca se recorta)
        val_w = QFontMetrics(f_val).horizontalAdvance(self._value)
        # celda de label: su texto, entre LABEL_MIN y 140
        lab_w = min(140, max(self.LABEL_MIN,
                             QFontMetrics(f_lab).horizontalAdvance(
                                 self._label)))
        lab_w = min(lab_w, max(0, w - val_w - 24))   # panel muy angosto
        track_x = lab_w + 12
        track_w = max(0, w - track_x - val_w - 12)   # min-width 0
        # label
        p.setPen(QColor(_tok("ink_mute")))
        p.setFont(f_lab)
        p.drawText(QRectF(0, 0, lab_w, h),
                   Qt.AlignLeft | Qt.AlignVCenter, self._label)
        # track (flex — puede colapsar a 0; el valor no)
        if track_w > 2:
            ty = h / 2 - 4
            p.setBrush(QBrush(QColor(_tok("bg_sunk")))); p.setPen(Qt.NoPen)
            p.drawRoundedRect(QRectF(track_x, ty, track_w, 8), 4, 4)
            if self._frac > 0:
                p.setBrush(QBrush(QColor(_tok(_BAR_KIND[self._kind]))))
                p.drawRoundedRect(
                    QRectF(track_x, ty, track_w * self._frac, 8), 4, 4)
        # valor — celda propia, alineado a la derecha
        p.setPen(QColor(_tok("ink")))
        p.setFont(f_val)
        p.drawText(QRectF(w - val_w, 0, val_w, h),
                   Qt.AlignRight | Qt.AlignVCenter, self._value)


__all__ = ["MetricCard", "MetricGrid", "StatusBadge", "GaugePill",
           "DeltaBar", "ClassificationScale"]
