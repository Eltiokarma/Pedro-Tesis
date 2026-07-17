"""
DIALOG KIT — anatomía única de los diálogos secundarios (artboard 2d).

Los diálogos "utilitarios" (DOF, Setpoints, logs) nunca habían pasado
por diseño: QTextEdit mono crudos y cadenas de QMessageBox.  Este kit
define la anatomía del ciclo 2 y la pinta con tokens:

  · Header 56 px — título FONT_TITLE + subtítulo FONT_HINT + cerrar.
  · Cuerpo — fondo `bg`, padding 20/24, secciones con SECT_GAP.
  · Footer 52 px — acciones a la derecha: primario (accent),
    secundario (contorno line_strong), destructivo (danger).

Uso:
    dlg = KitDialog("Grados de libertad · Balance", "R-101 · reactor",
                    parent=self)
    dlg.body.addWidget(...)
    dlg.add_button("Cerrar")                       # secundario
    dlg.add_button("Aplicar", role="primary", slot=dlg.accept)
    dlg.exec()

Los widgets se construyen leyendo TOK en caliente → un diálogo nuevo
siempre nace en el tema activo (los diálogos son efímeros; no se
suscriben a themeChanged).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QScrollArea, QWidget, QSizePolicy,
)

from tokens import (
    TOK, qfont,
    FONT_DISPLAY, FONT_TITLE, FONT_UI, FONT_VALUE, FONT_HINT, FONT_LABEL,
)


# ─────────────────────────────────────────────────────────────
#  QSS de botones del kit
# ─────────────────────────────────────────────────────────────

def _qss_btn(role: str) -> str:
    if role == "primary":
        return (f"QPushButton {{ background:{TOK['accent']}; "
                f"color:{TOK['bg_elev']}; border:0; border-radius:7px; "
                f"padding:7px 16px; }} "
                f"QPushButton:hover {{ background:{TOK['accent_deep']}; }} "
                f"QPushButton:disabled {{ background:{TOK['bg_mute']}; "
                f"color:{TOK['ink_ghost']}; }}")
    if role == "destructive":
        return (f"QPushButton {{ background:transparent; "
                f"color:{TOK['danger']}; border:1px solid {TOK['danger']}; "
                f"border-radius:7px; padding:6px 16px; }} "
                f"QPushButton:hover {{ background:{TOK['danger_bg']}; }}")
    return (f"QPushButton {{ background:transparent; "
            f"color:{TOK['ink_mute']}; border:1px solid "
            f"{TOK['line_strong']}; border-radius:7px; "
            f"padding:6px 16px; }} "
            f"QPushButton:hover {{ background:{TOK['bg_mute']}; "
            f"color:{TOK['ink']}; border-color:{TOK['accent_soft']}; }}")


def kit_button(text: str, role: str = "secondary") -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    b.setFont(qfont(FONT_UI))
    b.setStyleSheet(_qss_btn(role))
    return b


# ─────────────────────────────────────────────────────────────
#  Piezas de contenido
# ─────────────────────────────────────────────────────────────

def kicker(text: str) -> QLabel:
    k = QLabel(text.upper())
    f = qfont(FONT_LABEL)
    f.setLetterSpacing(QFont.AbsoluteSpacing, 1.0)
    k.setFont(f)
    k.setStyleSheet(f"color:{TOK['ink_soft']};")
    return k


def stat_card(kick: str, value: str, sub: str = "",
              tone: str = "") -> QFrame:
    """Tarjeta de estadística (DOF, Variables, Ecuaciones…).
    tone ∈ {'', 'ok', 'warn', 'bad'} colorea el valor."""
    card = QFrame()
    card.setStyleSheet(
        f"background:{TOK['bg_elev']}; border:1px solid {TOK['line']}; "
        f"border-radius:9px;")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(14, 10, 14, 10)
    lay.setSpacing(2)
    k = kicker(kick)
    k.setStyleSheet(f"color:{TOK['ink_soft']}; border:0;")
    lay.addWidget(k)
    v = QLabel(value)
    v.setFont(qfont(FONT_DISPLAY))
    col = {"ok": TOK["green"], "warn": TOK["amber"],
           "bad": TOK["danger"]}.get(tone, TOK["ink"])
    v.setStyleSheet(f"color:{col}; border:0;")
    lay.addWidget(v)
    if sub:
        s = QLabel(sub)
        s.setFont(qfont(FONT_HINT))
        s.setStyleSheet(f"color:{TOK['ink_mute']}; border:0;")
        lay.addWidget(s)
    return card


def kit_table(headers, rows, aligns=None) -> QFrame:
    """Tabla liviana del kit: headers FONT_LABEL, celdas FONT_VALUE,
    zebra sutil.  rows = [[celda, ...], ...] — cada celda es str o
    (str, tone) con tone ∈ {'ok','warn','bad','mute'}."""
    tones = {"ok": TOK["green"], "warn": TOK["amber"],
             "bad": TOK["danger"], "mute": TOK["ink_mute"]}
    box = QFrame()
    box.setStyleSheet(
        f"background:{TOK['bg_elev']}; border:1px solid {TOK['line']}; "
        f"border-radius:9px;")
    g = QGridLayout(box)
    g.setContentsMargins(14, 10, 14, 10)
    g.setHorizontalSpacing(18)
    g.setVerticalSpacing(6)
    aligns = aligns or ["l"] * len(headers)
    qal = {"l": Qt.AlignLeft, "r": Qt.AlignRight, "c": Qt.AlignCenter}
    for c, h in enumerate(headers):
        hl = kicker(h)
        hl.setStyleSheet(f"color:{TOK['ink_soft']}; border:0;")
        g.addWidget(hl, 0, c, qal.get(aligns[c], Qt.AlignLeft))
    for r, row in enumerate(rows, start=1):
        for c, cell in enumerate(row):
            tone = ""
            if isinstance(cell, tuple):
                cell, tone = cell
            lbl = QLabel(str(cell))
            lbl.setFont(qfont(FONT_VALUE))
            lbl.setStyleSheet(
                f"color:{tones.get(tone, TOK['ink'])}; border:0;")
            g.addWidget(lbl, r, c, qal.get(aligns[c], Qt.AlignLeft))
    g.setColumnStretch(len(headers) - 1, 1)
    return box


# ─────────────────────────────────────────────────────────────
#  El diálogo
# ─────────────────────────────────────────────────────────────

class KitDialog(QDialog):
    """Diálogo con la anatomía del kit (header / cuerpo scrolleable /
    footer).  `self.body` es el QVBoxLayout del cuerpo."""

    def __init__(self, title: str, subtitle: str = "", parent=None,
                 size=(680, 520)):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(*size)
        self.setStyleSheet(f"QDialog {{ background:{TOK['bg']}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── header 56px ──
        head = QFrame()
        head.setFixedHeight(56)
        head.setStyleSheet(
            f"background:{TOK['bg_elev']}; "
            f"border-bottom:1px solid {TOK['line']};")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(20, 8, 12, 8)
        col = QVBoxLayout(); col.setSpacing(0); col.setContentsMargins(0, 0, 0, 0)
        t = QLabel(title)
        t.setFont(qfont(FONT_TITLE))
        t.setStyleSheet(f"color:{TOK['ink']}; border:0;")
        col.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setFont(qfont(FONT_HINT))
            s.setStyleSheet(f"color:{TOK['ink_mute']}; border:0;")
            col.addWidget(s)
        hl.addLayout(col)
        hl.addStretch(1)
        x = QPushButton("✕")   # glifo-ícono (excepción 2g)
        x.setFixedSize(28, 28)
        x.setCursor(Qt.PointingHandCursor)
        x.setStyleSheet(
            f"QPushButton {{ color:{TOK['ink_mute']}; border:0; "
            f"background:transparent; border-radius:6px; }} "
            f"QPushButton:hover {{ background:{TOK['bg_mute']}; "
            f"color:{TOK['ink']}; }}")
        x.clicked.connect(self.reject)
        hl.addWidget(x, alignment=Qt.AlignTop)
        outer.addWidget(head)

        # ── cuerpo scrolleable ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        body_host = QWidget()
        body_host.setStyleSheet("background: transparent;")
        self.body = QVBoxLayout(body_host)
        self.body.setContentsMargins(24, 20, 24, 20)
        self.body.setSpacing(14)
        scroll.setWidget(body_host)
        outer.addWidget(scroll, 1)

        # ── footer 52px ──
        foot = QFrame()
        foot.setFixedHeight(52)
        foot.setStyleSheet(
            f"background:{TOK['bg_elev']}; "
            f"border-top:1px solid {TOK['line']};")
        self._foot_lay = QHBoxLayout(foot)
        self._foot_lay.setContentsMargins(20, 8, 20, 8)
        self._foot_lay.setSpacing(8)
        self._foot_lay.addStretch(1)
        outer.addWidget(foot)

    def add_button(self, text: str, role: str = "secondary",
                   slot=None) -> QPushButton:
        b = kit_button(text, role)
        b.clicked.connect(slot if slot is not None else self.reject)
        self._foot_lay.addWidget(b)
        return b

    def add_footer_note(self, text: str) -> QLabel:
        """Nota a la izquierda del footer (el footer nunca repite datos)."""
        n = QLabel(text)
        n.setFont(qfont(FONT_HINT))
        n.setStyleSheet(f"color:{TOK['ink_soft']}; border:0;")
        self._foot_lay.insertWidget(0, n)
        return n
