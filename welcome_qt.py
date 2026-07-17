"""
WELCOME QT — pantalla de bienvenida del editor Qt (artboard 2e, ciclo 2).

Rediseñada dentro del sistema de diseño: tokens TOK + tipografía
qfont(FONT_*) + tema claro/oscuro.  Dos columnas (760×580):

  · Izquierda — identidad (◆ Flowsheet) + acciones primarias
    (Nuevo flowsheet / Abrir…) + versión.
  · Derecha  — Recientes (con estado vacío) + Ejemplos (3 destacados
    en fila + enlace al catálogo completo).

Al elegir, `show_and_get_action()` devuelve (action, payload):
  · ('qt', None)        → editor vacío.
  · ('qt', path)        → editor con ese .json abierto.
  · ('example', clave)  → editor con ese ejemplo del registry cargado.
  · (None, None)        → el user cerró sin elegir.

Los recientes se guardan en ~/.pedro_tesis_recent.json.
"""

import json
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QMessageBox, QFrame,
    QSizePolicy, QMenu,
)

import tokens as _tokens
from tokens import (
    TOK, qfont,
    FONT_TITLE, FONT_UI, FONT_VALUE, FONT_HINT, FONT_LABEL,
)
import pfd_fonts


RECENT_FILE = os.path.expanduser("~/.pedro_tesis_recent.json")
MAX_RECENT  = 6          # el panel muestra hasta 6; persisten 8
MAX_RECENT_SAVE = 8
FEATURED_EXAMPLES = ("methanol", "hda", "distillation")


def _load_recent():
    try:
        with open(RECENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [p for p in data if isinstance(p, str) and os.path.exists(p)]
    except (OSError, ValueError):
        return []


def _save_recent(path):
    recent = _load_recent()
    if path in recent:
        recent.remove(path)
    recent.insert(0, path)
    recent = recent[:MAX_RECENT_SAVE]
    try:
        with open(RECENT_FILE, "w", encoding="utf-8") as f:
            json.dump(recent, f, indent=2)
    except OSError:
        pass


def _here():
    return os.path.dirname(os.path.abspath(__file__))


def launch_flowsheet_qt(json_path=None):
    """Compat: avisa al caller que cierre welcome y abra el editor."""
    return ("qt", json_path)


class WelcomeWindow(QMainWindow):
    """Welcome del editor Qt.  Resuelve (action, payload) al cerrar."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Flowsheet — Simulador de procesos")
        # Tema del usuario ANTES de construir (la welcome aparece antes
        # que el editor, que era quien cargaba las prefs).
        try:
            _tokens.load_prefs_from_disk()
        except Exception:
            pass
        pfd_fonts.load_all()
        import ui_scaling
        ui_scaling.fit_to_screen(self, 760, 580)

        self.action = None
        self.payload = None

        central = QWidget()
        central.setObjectName("welcomeRoot")
        self.setCentralWidget(central)
        central.setStyleSheet(
            f"#welcomeRoot {{ background: {TOK['bg']}; }}")

        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_left_column())
        outer.addWidget(self._build_right_column(), 1)

    # ── columna izquierda: identidad + acciones ────────────────
    def _build_left_column(self) -> QWidget:
        col = QFrame()
        col.setObjectName("welcomeLeft")
        col.setFixedWidth(280)
        col.setStyleSheet(
            f"#welcomeLeft {{ background: {TOK['bg_elev']}; "
            f"border-right: 1px solid {TOK['line']}; }}")
        lay = QVBoxLayout(col)
        lay.setContentsMargins(28, 32, 28, 20)
        lay.setSpacing(10)

        # identidad
        logo = QLabel("◆")
        logo.setFixedSize(44, 44)
        logo.setAlignment(Qt.AlignCenter)
        lf = qfont(FONT_TITLE)
        lf.setPointSizeF(20)   # glifo-ícono: tamaño geométrico (excepción 2g)
        logo.setFont(lf)
        logo.setStyleSheet(
            f"color:{TOK['accent']}; background:{TOK['accent_tint']}; "
            f"border:1px solid {TOK['accent_soft']}; border-radius:10px;")
        lay.addWidget(logo)

        name = QLabel("Flowsheet")
        name.setFont(qfont(FONT_TITLE))
        name.setStyleSheet(f"color:{TOK['ink']};")
        lay.addWidget(name)

        tag = QLabel("Simulador de procesos\ny análisis económico")
        tag.setFont(qfont(FONT_HINT))
        tag.setStyleSheet(f"color:{TOK['ink_mute']};")
        lay.addWidget(tag)

        lay.addSpacing(18)

        btn_new = self._primary_button("＋  Nuevo flowsheet")
        btn_new.clicked.connect(self._on_new)
        lay.addWidget(btn_new)

        btn_open = self._ghost_button("Abrir…")
        btn_open.setToolTip("Cargar un diagrama .json del editor")
        btn_open.clicked.connect(self._on_open)
        lay.addWidget(btn_open)

        lay.addStretch(1)

        ver = QLabel("v0.4 · IBM Plex")
        ver.setFont(qfont(FONT_LABEL))
        ver.setStyleSheet(f"color:{TOK['ink_ghost']}; letter-spacing:1px;")
        lay.addWidget(ver)

        btn_exit = self._ghost_button("Salir")
        btn_exit.clicked.connect(self._on_exit)
        lay.addWidget(btn_exit)
        return col

    # ── columna derecha: recientes + ejemplos ──────────────────
    def _build_right_column(self) -> QWidget:
        col = QFrame()
        lay = QVBoxLayout(col)
        lay.setContentsMargins(28, 32, 28, 20)
        lay.setSpacing(8)

        lay.addWidget(self._kicker("RECIENTES"))

        recent = _load_recent()
        if not recent:
            lay.addWidget(self._empty_state())
        else:
            for path in recent[:MAX_RECENT]:
                lay.addWidget(self._recent_row(path))

        lay.addStretch(1)

        lay.addWidget(self._kicker("EJEMPLOS"))
        # 3 destacados en fila + enlace al catálogo (decisión 2e: los
        # ejemplos son el mejor onramp para una herramienta de tesis,
        # pero en segundo plano — no compiten con "abrir mi proyecto").
        try:
            import examples_registry as reg
            meta = {e["clave"]: e for e in reg.list_examples()}
        except Exception:
            meta = {}
        row = QHBoxLayout(); row.setSpacing(8)
        for clave in FEATURED_EXAMPLES:
            m = meta.get(clave)
            if m is None:
                continue
            row.addWidget(self._example_card(clave, m["nombre"]))
        lay.addLayout(row)

        n = len(meta)
        link = QPushButton(f"Ver los {n} ejemplos  →" if n
                           else "Ver ejemplos  →")
        link.setCursor(Qt.PointingHandCursor)
        link.setFont(qfont(FONT_HINT))
        link.setStyleSheet(
            f"QPushButton {{ background: transparent; border: 0; "
            f"color:{TOK['accent']}; text-align:left; padding:4px 2px; }} "
            f"QPushButton:hover {{ color:{TOK['accent_deep']}; }}")
        link.clicked.connect(lambda: self._show_all_examples(link, meta))
        lay.addWidget(link)
        return col

    # ── piezas ─────────────────────────────────────────────────
    def _kicker(self, text: str) -> QLabel:
        k = QLabel(text)
        f = qfont(FONT_LABEL)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)
        k.setFont(f)
        k.setStyleSheet(f"color:{TOK['ink_soft']};")
        return k

    def _primary_button(self, text: str) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setMinimumHeight(44)
        b.setFont(qfont(FONT_UI))
        b.setStyleSheet(
            f"QPushButton {{ background:{TOK['accent']}; "
            f"color:{TOK['bg_elev']}; border:0; border-radius:8px; "
            f"padding:8px 14px; text-align:left; }} "
            f"QPushButton:hover {{ background:{TOK['accent_deep']}; }}")
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return b

    def _ghost_button(self, text: str) -> QPushButton:
        b = QPushButton(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setMinimumHeight(38)
        b.setFont(qfont(FONT_UI))
        b.setStyleSheet(
            f"QPushButton {{ background: transparent; "
            f"color:{TOK['ink_mute']}; border:1px solid "
            f"{TOK['line_strong']}; border-radius:8px; "
            f"padding:6px 14px; text-align:left; }} "
            f"QPushButton:hover {{ background:{TOK['bg_mute']}; "
            f"color:{TOK['ink']}; border-color:{TOK['accent_soft']}; }}")
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return b

    def _empty_state(self) -> QWidget:
        box = QFrame()
        box.setStyleSheet(
            f"background:{TOK['bg_mute']}; border:1px dashed "
            f"{TOK['line_strong']}; border-radius:10px;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(16, 22, 16, 22)
        lay.setSpacing(4)
        d = QLabel("◇")
        d.setAlignment(Qt.AlignCenter)
        df = qfont(FONT_TITLE)
        df.setPointSizeF(18)   # glifo-ícono: tamaño geométrico (excepción 2g)
        d.setFont(df)
        d.setStyleSheet(f"color:{TOK['ink_ghost']}; border:0;")
        lay.addWidget(d)
        t = QLabel("Todavía no abriste ningún flowsheet")
        t.setAlignment(Qt.AlignCenter)
        t.setFont(qfont(FONT_UI))
        t.setStyleSheet(f"color:{TOK['ink_mute']}; border:0;")
        lay.addWidget(t)
        s = QLabel("Empezá con un ejemplo ↓")
        s.setAlignment(Qt.AlignCenter)
        s.setFont(qfont(FONT_HINT))
        s.setStyleSheet(f"color:{TOK['ink_soft']}; border:0;")
        lay.addWidget(s)
        return box

    def _recent_row(self, path: str) -> QWidget:
        b = QPushButton()
        b.setCursor(Qt.PointingHandCursor)
        b.setMinimumHeight(46)
        lay = QHBoxLayout(b)
        lay.setContentsMargins(12, 4, 12, 4)
        dot = QLabel("◆")
        dot.setFont(qfont(FONT_LABEL))
        dot.setStyleSheet(f"color:{TOK['accent']}; background:transparent;")
        lay.addWidget(dot)
        name = QLabel(os.path.basename(path))
        name.setFont(qfont(FONT_VALUE))
        name.setStyleSheet(f"color:{TOK['ink']}; background:transparent;")
        lay.addWidget(name)
        lay.addStretch(1)
        where = QLabel(os.path.dirname(path))
        where.setFont(qfont(FONT_HINT))
        where.setStyleSheet(
            f"color:{TOK['ink_ghost']}; background:transparent;")
        lay.addWidget(where)
        b.setStyleSheet(
            f"QPushButton {{ background:{TOK['bg_elev']}; border:1px solid "
            f"{TOK['line']}; border-radius:8px; text-align:left; }} "
            f"QPushButton:hover {{ border-color:{TOK['accent_soft']}; "
            f"background:{TOK['accent_tint']}; }}")
        b.clicked.connect(lambda _=False, p=path: self._open_path(p))
        return b

    def _example_card(self, clave: str, nombre: str) -> QWidget:
        b = QPushButton(nombre)
        b.setCursor(Qt.PointingHandCursor)
        b.setMinimumHeight(56)
        b.setFont(qfont(FONT_HINT))
        b.setToolTip(f"Abrir el ejemplo «{nombre}» en el editor")
        b.setStyleSheet(
            f"QPushButton {{ background:{TOK['bg_elev']}; "
            f"color:{TOK['ink']}; border:1px solid {TOK['line']}; "
            f"border-radius:10px; padding:8px; text-align:left; }} "
            f"QPushButton:hover {{ border-color:{TOK['accent_soft']}; "
            f"background:{TOK['accent_tint']}; }}")
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        b.clicked.connect(lambda _=False, k=clave: self._open_example(k))
        return b

    def _show_all_examples(self, anchor: QWidget, meta: dict):
        """Catálogo completo agrupado por categoría, como QMenu."""
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{TOK['bg_elev']}; color:{TOK['ink']}; "
            f"border:1px solid {TOK['line']}; padding:4px 0; }} "
            f"QMenu::item {{ padding:5px 22px 5px 14px; }} "
            f"QMenu::item:selected {{ background:{TOK['accent_tint']}; "
            f"color:{TOK['accent_deep']}; }} "
            f"QMenu::separator {{ height:1px; background:{TOK['line']}; "
            f"margin:4px 8px; }}")
        by_cat: dict = {}
        for e in meta.values():
            by_cat.setdefault(e.get("categoria", "Otros"), []).append(e)
        first = True
        for cat, items in by_cat.items():
            if not first:
                menu.addSeparator()
            first = False
            head = menu.addAction(cat)
            head.setEnabled(False)
            for e in items:
                act = menu.addAction("   " + e["nombre"])
                act.triggered.connect(
                    lambda _=False, k=e["clave"]: self._open_example(k))
        menu.exec(anchor.mapToGlobal(anchor.rect().topLeft()))

    # ── acciones ───────────────────────────────────────────────
    def _on_new(self):
        self.action = "qt"
        self.payload = None
        self.close()

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Abrir proyecto", "",
            "Diagrama de proceso (JSON) (*.json);;"
            "Todos los archivos (*.*)"
        )
        if not path:
            return
        self._open_path(path)

    def _open_path(self, path):
        ext = os.path.splitext(path)[1].lower()
        if ext == ".json":
            _save_recent(path)
            self.action = "qt"
            self.payload = path
            self.close()
            return
        QMessageBox.critical(
            self, "Tipo de archivo no soportado",
            f"No sé cómo abrir la extensión: {ext}\n"
            "Usá .json (diagrama del editor Qt)."
        )

    def _open_example(self, clave: str):
        self.action = "example"
        self.payload = clave
        self.close()

    def _on_exit(self):
        self.action = None
        self.close()


def show_and_get_action():
    """Muestra la welcome y devuelve (action, payload) cuando el user cierra."""
    win = WelcomeWindow()
    win.show()
    QApplication.instance().exec()
    return win.action, win.payload
