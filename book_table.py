"""book_table.py — «Tabla de libro» del kit (Design ciclo 4, artboard 4a).

UN componente para las tres instancias didácticas del inspector:
  · Tabla estequiométrica (Fogler §3.4) — todo reactor con reacción.
  · Reparto del flash x/y/K (estilo ChemSep) — todo vessel con flash.
  · Etapas de columna Wang-Henke (estreno) — toggle tabla ↔ figura.

Resuelve en la raíz el defecto «columnas que bailan»: la tabla deja de
ser un render monoespaciado dentro de una tarjeta de fuente
proporcional y pasa a SER una grilla pintada con columnas medidas
(el mono de FONT_VALUE es tabular por construcción).

Anatomía (spec del bundle, valores exactos):
  · Contenedor  — bg_elev, borde 1px line, radius 10, overflow hidden.
  · Kicker      — FONT_LABEL upper, tracking 1.2, ink_soft; banda
                  bg_mute con dot accent Ø6 y borde inferior line.
  · Strip de contexto — banda bg_sunk, pares FONT_LABEL upper +
                  FONT_VALUE mono; gap 6/18.
  · Tabla       — celdas FONT_VALUE (mono tabular); numéricas a la
                  derecha, especie a la izquierda (600); encabezado
                  FONT_LABEL upper ink_soft con borde line_strong;
                  filas pad 5/6 con borde line_soft.
  · Fila destacable (A/FEED/COND/REB) — ribbon 3px izq. en el color
                  del rol + pill en la 1ª celda (tint/ink, bold).
  · Inerte (I)  — pill tag_bg/tag_ink; especie en ink_mute.
  · Fila Σ      — footer visual: borde sup. 1.5px line_strong, fondo
                  bg_sunk, peso 700.
  · Chips derivados (δ, ε, V/F) — pill tint/ink radius 7.
  · Procedencia de X — pill ▪ declarada (spec) / ◦ alcanzada (auto),
                  vocabulario sudoku del ciclo 3.
  · Fuente      — pie estándar: banda bg_mute, glifo ▤ + FONT_HINT.

Decisiones del bundle que este widget encarna:
  · «Cambio» negativo = tinta neutra + signo + ↓ (ink_mute), NO el
    rojo semántico — negativo acá es consumo, no error.
  · K_i codificado en el eje frío/cálido existente: K>1 (↑ vapor) =
    service_hot_deep · K<1 (↓ líquido) = service_cold_deep.  Solo
    tinta + glifo, sin fondo (competiría con el ribbon de fila).

El spec de entrada es un dict Qt-free (lo construye
inspector_evidence.*_book_spec) → testeable sin pantalla.
Los colores se leen de TOK al construir; el inspector se reconstruye
al cambiar tema (patrón _on_prefs_changed), igual que _diag_text_card.
"""
from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QBrush, QPainter, QPen, QFontMetrics
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QSizePolicy,
)

import block_inspector as _bi     # TOK en caliente (muta con el tema)
from tokens import qfont, FONT_VALUE, FONT_HINT, FONT_LABEL


def _tok(name: str, fallback: str = "ink") -> str:
    return _bi.TOK.get(name, _bi.TOK[fallback])


# kind → (token de tinta, token de fondo) — pills/chips/ribbons.
# Mismo mapeo que el bundle (BookTable._kind).
_KIND_TOKENS = {
    "accent":  ("accent", "accent_tint"),
    "spec":    ("spec_ink", "spec_bg"),
    "neutral": ("tag_ink", "tag_bg"),
    "warm":    ("service_hot_deep", "service_hot_pale"),
    "cool":    ("service_cold_deep", "service_cold_pale"),
    "green":   ("green", "green_bg"),
    "amber":   ("amber", "amber_bg"),
    "danger":  ("danger", "danger_bg"),
    "sinnott": ("sinnott_ink", "sinnott_bg"),
}


def _kind(k: str):
    return _KIND_TOKENS.get(k or "neutral", _KIND_TOKENS["neutral"])


# ─────────────────────────────────────────────────────────────────────
#  _BookGrid — la grilla pintada (columnas medidas, mono tabular)
# ─────────────────────────────────────────────────────────────────────
class _BookGrid(QWidget):
    """Tabla pintada: encabezado + filas.  Anchos de columna medidos
    con QFontMetrics sobre el contenido (adiós alineado por espacios).
    El ancho sobrante se entrega a la primera columna (especie)."""

    HDR_H = 24
    ROW_H = 24
    SIGMA_H = 28
    PAD_X = 6          # padding horizontal de celda
    RIBBON_W = 3

    def __init__(self, columns: List[dict], rows: List[dict], parent=None):
        super().__init__(parent)
        self._cols = columns
        self._rows = rows
        self._f_val = qfont(FONT_VALUE)
        self._f_val_b = qfont(FONT_VALUE)
        self._f_val_b.setWeight(QFont.DemiBold)
        self._f_sig = qfont(FONT_VALUE)
        self._f_sig.setWeight(QFont.Bold)
        self._f_hdr = qfont(FONT_LABEL)
        self._f_hdr.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
        # pill de badge: FONT_LABEL una talla abajo (chip de dato)
        self._f_badge = qfont(FONT_LABEL)
        self._f_badge.setPointSizeF(8.0)
        self._f_badge.setWeight(QFont.Bold)
        self._natural = self._measure()
        h = self.HDR_H + sum(self.SIGMA_H if r.get("sigma") else self.ROW_H
                             for r in rows)
        self.setMinimumSize(self._natural, h)
        self.setFixedHeight(h)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # ── medición de columnas ──
    def _cell_w(self, cell: dict, fm_val: QFontMetrics,
                fm_badge: QFontMetrics) -> int:
        w = fm_val.horizontalAdvance(str(cell.get("t", "")))
        badge = cell.get("badge")
        if badge:
            w += fm_badge.horizontalAdvance(str(badge.get("text", ""))) + 18
        if cell.get("dir") in ("up", "down") or cell.get("K") in ("up", "down"):
            w += 12                      # glifo ↑/↓ + gap
        return w

    @staticmethod
    def _hdr_text(label) -> str:
        """Encabezado en caps — pero SOLO si es ASCII puro: ν/θ/° son
        notación del libro, no tipografía (upper convertiría ν→Ν y el
        encabezado leería 'N/|N_A|')."""
        t = str(label)
        return t.upper() if t.isascii() else t

    def _measure(self) -> int:
        fm_val = QFontMetrics(self._f_val_b)
        fm_badge = QFontMetrics(self._f_badge)
        fm_hdr = QFontMetrics(self._f_hdr)
        self._col_w = []
        for ci, col in enumerate(self._cols):
            w = fm_hdr.horizontalAdvance(self._hdr_text(col.get("label", "")))
            for r in self._rows:
                cells = r.get("cells") or []
                if ci < len(cells):
                    w = max(w, self._cell_w(cells[ci], fm_val, fm_badge))
            self._col_w.append(w + 2 * self.PAD_X)
        return sum(self._col_w) + self.RIBBON_W + 2

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width()
        if w < 8:
            return
        # ancho sobrante → columna 0 (especie)
        col_w = list(self._col_w)
        extra = w - self._natural
        if extra > 0 and col_w:
            col_w[0] += extra
        x0 = self.RIBBON_W + 1

        # ── encabezado ──
        p.setFont(self._f_hdr)
        p.setPen(QColor(_tok("ink_soft")))
        x = x0
        for ci, col in enumerate(self._cols):
            align = (Qt.AlignRight if col.get("align") == "right"
                     else Qt.AlignLeft)
            p.drawText(QRectF(x + self.PAD_X, 0,
                              col_w[ci] - 2 * self.PAD_X, self.HDR_H),
                       align | Qt.AlignVCenter,
                       self._hdr_text(col.get("label", "")))
            x += col_w[ci]
        p.setPen(QPen(QColor(_tok("line_strong")), 1))
        p.drawLine(0, self.HDR_H, w, self.HDR_H)

        # ── filas ──
        y = self.HDR_H
        fm_badge = QFontMetrics(self._f_badge)
        for r in self._rows:
            sigma = bool(r.get("sigma"))
            rh = self.SIGMA_H if sigma else self.ROW_H
            if sigma:
                p.fillRect(QRectF(0, y, w, rh), QColor(_tok("bg_sunk")))
                p.setPen(QPen(QColor(_tok("line_strong")), 1.5))
                p.drawLine(0, y, w, y)
            ribbon = r.get("ribbon")
            if ribbon:
                ink_t, _bg_t = _kind(ribbon)
                p.fillRect(QRectF(0, y, self.RIBBON_W, rh),
                           QColor(_tok(ink_t)))
            x = x0
            cells = r.get("cells") or []
            for ci, col in enumerate(self._cols):
                if ci >= len(cells):
                    x += col_w[ci]
                    continue
                cell = cells[ci]
                align = (Qt.AlignRight if col.get("align") == "right"
                         else Qt.AlignLeft)
                # tinta de la celda (decisiones del bundle)
                if sigma:
                    font, ink = self._f_sig, _tok("ink")
                elif ci == 0:
                    font = self._f_val_b
                    ink = _tok("ink_mute") if r.get("muted") else _tok("ink")
                else:
                    font, ink = self._f_val, _tok("ink")
                if cell.get("neutral"):
                    ink = _tok("ink_soft")
                if cell.get("K") == "up":
                    font, ink = self._f_val_b, _tok("service_hot_deep")
                elif cell.get("K") == "down":
                    font, ink = self._f_val_b, _tok("service_cold_deep")
                if cell.get("dir") == "down":
                    ink = _tok("ink_mute")     # consumo ≠ error

                cx = x + self.PAD_X
                cw = col_w[ci] - 2 * self.PAD_X
                # badge pill (celda 0: A / I / FEED / COND / REB)
                badge = cell.get("badge")
                txt = str(cell.get("t", ""))
                if badge and align == Qt.AlignLeft:
                    b_ink, b_bg = _kind(badge.get("kind"))
                    b_txt = str(badge.get("text", ""))
                    bw = fm_badge.horizontalAdvance(b_txt) + 12
                    bh = 15
                    br = QRectF(cx, y + (rh - bh) / 2, bw, bh)
                    p.setPen(Qt.NoPen)
                    p.setBrush(QBrush(QColor(_tok(b_bg))))
                    p.drawRoundedRect(br, 5, 5)
                    p.setPen(QColor(_tok(b_ink)))
                    p.setFont(self._f_badge)
                    p.drawText(br, Qt.AlignCenter, b_txt)
                    cx += bw + 6
                    cw -= bw + 6
                # glifo ↑/↓ (dir = consumo/producción · K = sube/baja)
                arrow = None
                if cell.get("dir") == "down" or cell.get("K") == "down":
                    arrow = "↓"
                elif cell.get("dir") == "up" or cell.get("K") == "up":
                    arrow = "↑"
                p.setFont(font)
                if arrow and align == Qt.AlignRight:
                    # flecha antes del número, tinta fantasma para dir /
                    # tinta de eje para K (el glifo acompaña, no grita)
                    fmv = QFontMetrics(font)
                    tw = fmv.horizontalAdvance(txt)
                    a_ink = (ink if cell.get("K")
                             else _tok("ink_ghost"))
                    p.setPen(QColor(a_ink))
                    p.drawText(QRectF(cx, y, cw - tw - 4, rh),
                               Qt.AlignRight | Qt.AlignVCenter, arrow)
                p.setPen(QColor(ink))
                p.drawText(QRectF(cx, y, cw, rh),
                           align | Qt.AlignVCenter, txt)
                x += col_w[ci]
            if not sigma:
                p.setPen(QPen(QColor(_tok("line_soft")), 1))
                p.drawLine(0, y + rh, w, y + rh)
            y += rh


# ─────────────────────────────────────────────────────────────────────
#  BookTable — el componente completo (kicker + contexto + grilla +
#  chips + procedencia + nota + fuente)
# ─────────────────────────────────────────────────────────────────────
class BookTable(QFrame):
    """Tarjeta «tabla de libro».  `spec` es el dict Qt-free de
    inspector_evidence.*_book_spec (ver docstring del módulo)."""

    def __init__(self, spec: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("bookTable")
        self.setStyleSheet(
            f"#bookTable {{ background:{_tok('bg_elev')}; "
            f"border:1px solid {_tok('line')}; border-radius:10px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── kicker ──
        kick = QFrame()
        kick.setStyleSheet(
            f"background:{_tok('bg_mute')}; "
            f"border:0; border-bottom:1px solid {_tok('line')}; "
            f"border-top-left-radius:10px; border-top-right-radius:10px;")
        kl = QHBoxLayout(kick)
        kl.setContentsMargins(14, 7, 14, 7)
        kl.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(6, 6)
        dot.setStyleSheet(
            f"background:{_tok('accent')}; border-radius:3px; border:0;")
        kl.addWidget(dot)
        kt = QLabel(str(spec.get("kicker", "")).upper())
        f_k = qfont(FONT_LABEL)
        f_k.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        kt.setFont(f_k)
        kt.setStyleSheet(f"color:{_tok('ink_soft')}; border:0;")
        kl.addWidget(kt)
        kl.addStretch(1)
        lay.addWidget(kick)

        # ── strip de contexto ──
        ctx = spec.get("context") or []
        if ctx:
            strip = QFrame()
            strip.setStyleSheet(
                f"background:{_tok('bg_sunk')}; border:0;")
            sl = QHBoxLayout(strip)
            sl.setContentsMargins(14, 8, 14, 8)
            sl.setSpacing(18)
            for lab, val in ctx:
                cell = QHBoxLayout()
                cell.setSpacing(5)
                ll = QLabel(str(lab).upper())
                ll.setFont(qfont(FONT_LABEL))
                ll.setStyleSheet(f"color:{_tok('ink_soft')}; border:0;")
                cell.addWidget(ll)
                vl = QLabel(str(val))
                vl.setFont(qfont(FONT_VALUE))
                vl.setStyleSheet(f"color:{_tok('ink')}; border:0;")
                cell.addWidget(vl)
                wrap = QFrame()
                wrap.setStyleSheet("border:0; background:transparent;")
                wrap.setLayout(cell)
                sl.addWidget(wrap)
            sl.addStretch(1)
            lay.addWidget(strip)

        # ── grilla ──
        grid_wrap = QFrame()
        grid_wrap.setStyleSheet("border:0; background:transparent;")
        gl = QVBoxLayout(grid_wrap)
        gl.setContentsMargins(14, 4, 14, 2)
        self.grid = _BookGrid(spec.get("columns") or [],
                              spec.get("rows") or [])
        gl.addWidget(self.grid)
        lay.addWidget(grid_wrap)

        # ── chips derivados ──
        chips = spec.get("chips") or []
        if chips:
            ch_wrap = QFrame()
            ch_wrap.setStyleSheet("border:0; background:transparent;")
            cl = QHBoxLayout(ch_wrap)
            cl.setContentsMargins(14, 8, 14, 2)
            cl.setSpacing(8)
            for ch in chips:
                ink_t, bg_t = _kind(ch.get("kind"))
                pill = QLabel(
                    f"{ch.get('label', '')}  {ch.get('value', '')}")
                f_c = qfont(FONT_VALUE)
                f_c.setWeight(QFont.DemiBold)
                pill.setFont(f_c)
                pill.setStyleSheet(
                    f"background:{_tok(bg_t)}; color:{_tok(ink_t)}; "
                    f"border:0; border-radius:7px; padding:3px 11px;")
                cl.addWidget(pill)
            cl.addStretch(1)
            lay.addWidget(ch_wrap)

        # ── procedencia de X (vocabulario sudoku) ──
        prov = spec.get("provenance")
        if prov:
            pv_wrap = QFrame()
            pv_wrap.setStyleSheet("border:0; background:transparent;")
            pl = QHBoxLayout(pv_wrap)
            pl.setContentsMargins(14, 5, 14, 2)
            pl.setSpacing(8)
            pre = QLabel(str(prov.get("pre", "")))
            pre.setFont(qfont(FONT_HINT))
            pre.setStyleSheet(f"color:{_tok('ink_mute')}; border:0;")
            pl.addWidget(pre)
            ink_t, bg_t = _kind(prov.get("kind"))
            pill = QLabel(f"{prov.get('glyph', '')} {prov.get('label', '')}")
            f_p = qfont(FONT_HINT)
            f_p.setWeight(QFont.DemiBold)
            pill.setFont(f_p)
            pill.setStyleSheet(
                f"background:{_tok(bg_t)}; color:{_tok(ink_t)}; "
                f"border:0; border-radius:6px; padding:1px 9px;")
            pl.addWidget(pill)
            pl.addStretch(1)
            lay.addWidget(pv_wrap)

        # ── nota (identidad / fórmula) ──
        note = spec.get("note")
        if note:
            nl = QLabel(str(note))
            nl.setFont(qfont(FONT_VALUE))
            nl.setWordWrap(True)
            nl.setStyleSheet(
                f"color:{_tok('ink_mute')}; border:0; "
                f"padding:2px 14px 2px 14px; background:transparent;")
            lay.addWidget(nl)

        # ── warning honesto (p.ej. especies sin MW) ──
        warn = spec.get("warn")
        if warn:
            wl = QLabel(f"⚠ {warn}")
            wl.setFont(qfont(FONT_HINT))
            wl.setWordWrap(True)
            wl.setStyleSheet(
                f"color:{_tok('amber')}; border:0; "
                f"padding:2px 14px; background:transparent;")
            lay.addWidget(wl)

        # ── pie de fuente ──
        src = QFrame()
        src.setStyleSheet(
            f"background:{_tok('bg_mute')}; "
            f"border:0; border-top:1px solid {_tok('line_soft')}; "
            f"border-bottom-left-radius:10px; "
            f"border-bottom-right-radius:10px;")
        srl = QHBoxLayout(src)
        srl.setContentsMargins(14, 7, 14, 7)
        srl.setSpacing(7)
        glyph = QLabel("▤")     # glifo-ícono (excepción 2g)
        glyph.setStyleSheet(
            f"color:{_tok('ink_soft')}; border:0; font-size:11px;")
        srl.addWidget(glyph)
        st = QLabel(f"Fuente: {spec.get('source', '')}")
        st.setFont(qfont(FONT_HINT))
        st.setWordWrap(True)
        st.setStyleSheet(f"color:{_tok('ink_soft')}; border:0;")
        srl.addWidget(st, 1)
        lay.addWidget(src)


__all__ = ["BookTable"]
