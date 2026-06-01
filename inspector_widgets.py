"""inspector_widgets.py — Átomos visuales del panel de Diagnóstico (Fase 2).

Componentes del rediseño (handoff §3), portados del mockup HTML/CSS a Qt:
  · MetricCard   — tarjeta valor+label con ribbon de 3px por `state`.
  · MetricGrid   — grilla responsiva (cols = max(1,min(3, w//150))).
  · StatusBadge  — pill dot+texto por `kind`.
  · GaugePill    — medidor radial (arco 180°) para fracciones 0..1.
  · DeltaBar     — fila [label][track][valor], fill por `kind`.

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
    """Lee TOK[name] en caliente (TOK muta in-place al cambiar tema)."""
    return _bi.TOK.get(name, _bi.TOK.get(fallback, "#000000"))


# ─────────────────────────────────────────────────────────────────────
#  MetricCard
# ─────────────────────────────────────────────────────────────────────
class MetricCard(QFrame):
    """Tarjeta: label (upper) + valor (mono grande) + unidad + sub, con
    ribbon de 3 px a la izquierda pintado con el color de `state`."""

    def __init__(self, key="", label="", value="", unit="", state="auto",
                 sub=None, flag=None, span=1, parent=None):
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
        _PrefsBus.signal().connect(self._on_prefs)

    def _on_prefs(self):
        self.update()

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(150, 62)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        if w < 6 or h < 6:
            return   # demasiado chico para pintar (evita rects negativos / GDI)
        r = 8.0
        pad_l = 12
        text_w = max(0, w - pad_l - 6)   # nunca negativo (Windows GDI)
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
        # textos (todos los anchos clampados a >=0 — Windows GDI dibsection)
        # label
        p.setPen(QColor(_tok("ink_soft")))
        f_lab = QFont(pfd_fonts.SANS, 7, QFont.Bold)
        f_lab.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
        p.setFont(f_lab)
        p.drawText(QRectF(pad_l, 6, text_w, 14),
                   Qt.AlignLeft | Qt.AlignVCenter, self._label.upper())
        # valor (tinta semántica si aplica) + unidad
        ink = _tok(_STATE_INK.get(self._state, "ink"), "ink") \
            if self._state in _STATE_INK else _tok("ink")
        p.setPen(QColor(ink))
        f_val = QFont(pfd_fonts.MONO, 15, QFont.DemiBold)
        p.setFont(f_val)
        fm = p.fontMetrics()
        val_w = fm.horizontalAdvance(self._value)
        y_val = 22
        p.drawText(QRectF(pad_l, y_val, text_w, 24),
                   Qt.AlignLeft | Qt.AlignVCenter, self._value)
        if self._unit:
            p.setPen(QColor(_tok("ink_soft")))
            p.setFont(QFont(pfd_fonts.MONO, 9))
            unit_w = max(0, w - pad_l - val_w - 8)
            p.drawText(QRectF(pad_l + val_w + 4, y_val, unit_w, 24),
                       Qt.AlignLeft | Qt.AlignVCenter, self._unit)
        # sub
        if self._sub:
            p.setPen(QColor(_tok("ink_mute")))
            p.setFont(QFont(pfd_fonts.SANS, 8))
            p.drawText(QRectF(pad_l, h - 16, text_w, 14),
                       Qt.AlignLeft | Qt.AlignVCenter, str(self._sub))
        # flag (chip arriba-derecha) — sólo si entra
        if self._flag and w > 60:
            p.setFont(QFont(pfd_fonts.SANS, 7, QFont.Bold))
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
        p.setFont(QFont(pfd_fonts.MONO, 14, QFont.DemiBold))
        p.drawText(QRectF(0, cy - 24, w, 22),
                   Qt.AlignHCenter | Qt.AlignVCenter, f"{txt}{self._suffix}")
        # label
        p.setPen(QColor(_tok("ink_soft")))
        f_lab = QFont(pfd_fonts.SANS, 7, QFont.Bold)
        f_lab.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
        p.setFont(f_lab)
        p.drawText(QRectF(0, h - 13, w, 12),
                   Qt.AlignHCenter | Qt.AlignVCenter, self._label.upper())


# ─────────────────────────────────────────────────────────────────────
#  DeltaBar — fila [label][track][valor]
# ─────────────────────────────────────────────────────────────────────
class DeltaBar(QFrame):
    """Fila horizontal: label (mono) · track con fill por `kind` · valor."""

    def __init__(self, label="", frac=0.0, value="", kind="accent",
                 parent=None):
        super().__init__(parent)
        self._label = str(label)
        self._frac = max(0.0, min(1.0, float(frac)))
        self._value = str(value)
        self._kind = kind if kind in _BAR_KIND else "accent"
        self.setFixedHeight(20)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        _PrefsBus.signal().connect(self.update)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        if w < 6 or h < 6:
            return
        lab_w = max(0, min(140, int(w * 0.34)))
        val_w = min(64, max(0, w - lab_w - 12))
        track_x = lab_w + 6
        track_w = max(2, w - lab_w - val_w - 12)
        # label
        p.setPen(QColor(_tok("ink_mute")))
        p.setFont(QFont(pfd_fonts.MONO, 8))
        p.drawText(QRectF(0, 0, lab_w, h),
                   Qt.AlignLeft | Qt.AlignVCenter, self._label)
        # track
        ty = h / 2 - 3
        p.setBrush(QBrush(QColor(_tok("bg_sunk")))); p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(track_x, ty, track_w, 6), 3, 3)
        if self._frac > 0:
            p.setBrush(QBrush(QColor(_tok(_BAR_KIND[self._kind]))))
            p.drawRoundedRect(QRectF(track_x, ty, track_w * self._frac, 6),
                              3, 3)
        # valor
        p.setPen(QColor(_tok("ink")))
        p.setFont(QFont(pfd_fonts.MONO, 8, QFont.DemiBold))
        p.drawText(QRectF(w - val_w, 0, val_w, h),
                   Qt.AlignRight | Qt.AlignVCenter, self._value)


__all__ = ["MetricCard", "MetricGrid", "StatusBadge", "GaugePill", "DeltaBar"]
