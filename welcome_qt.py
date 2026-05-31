"""
WELCOME QT — pantalla de bienvenida del editor Qt.

QMainWindow con header, 2 botones grandes + lista de proyectos
recientes.  Todos los proyectos son diagramas `.json` del editor Qt.

Al elegir:
  · Nuevo proyecto      → abre FlowsheetMainWindow (Qt) vacío.
  · Abrir proyecto…     → file dialog .json → FlowsheetMainWindow (Qt)
                          con --open.
  · Recientes           → mismo comportamiento.

Los recientes se guardan en ~/.pedro_tesis_recent.json.
"""

import json
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui  import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QMessageBox, QFrame,
    QSizePolicy,
)


RECENT_FILE = os.path.expanduser("~/.pedro_tesis_recent.json")
MAX_RECENT  = 8


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
    recent = recent[:MAX_RECENT]
    try:
        with open(RECENT_FILE, "w", encoding="utf-8") as f:
            json.dump(recent, f, indent=2)
    except OSError:
        pass


def _here():
    return os.path.dirname(os.path.abspath(__file__))


def launch_flowsheet_qt(json_path=None):
    """Launch flowsheet_main_qt.py en este mismo proceso (no subprocess)
    para que cierre la welcome y abra el editor en la misma app."""
    # Avisamos al caller: cerrar welcome y abrir editor
    return ("qt", json_path)


class WelcomeWindow(QMainWindow):
    """Welcome principal del editor Qt.

    Resuelve un Action al cerrar:
      action: 'qt' | None
      payload: path o None
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tesis — Análisis de proceso y económico")
        import ui_scaling
        ui_scaling.fit_to_screen(self, 720, 560)

        self.action = None
        self.payload = None

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(28, 24, 28, 18)
        layout.setSpacing(12)

        # ---- Header ----
        title = QLabel("Análisis de proceso y económico")
        title_font = QFont("Segoe UI", 18, QFont.Bold)
        title.setFont(title_font)
        layout.addWidget(title)

        subtitle = QLabel(
            "Diseñá el proceso en bloques y después corré el análisis económico."
        )
        subtitle.setStyleSheet("color: #666;")
        layout.addWidget(subtitle)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep)

        # ---- Buttons ----
        lbl_start = QLabel("Empezar")
        f_section = QFont("Segoe UI", 11, QFont.Bold)
        lbl_start.setFont(f_section)
        layout.addWidget(lbl_start)

        btn_new = self._big_button(
            "  Nuevo proyecto",
            "Diseñar el proceso desde cero en el editor Qt.",
            self._on_new,
        )
        layout.addWidget(btn_new)

        btn_open = self._big_button(
            "  Abrir proyecto…",
            "Cargar un diagrama .json del editor Qt.",
            self._on_open,
        )
        layout.addWidget(btn_open)

        # ---- Recent ----
        lbl_recent = QLabel("Recientes")
        lbl_recent.setFont(f_section)
        layout.addWidget(lbl_recent)

        recent = _load_recent()
        if not recent:
            empty = QLabel("(sin archivos recientes)")
            empty.setStyleSheet("color: #888; font-style: italic;")
            layout.addWidget(empty)
        else:
            for path in recent[:MAX_RECENT]:
                layout.addWidget(self._recent_row(path))

        layout.addStretch(1)

        # ---- Footer ----
        sep_b = QFrame()
        sep_b.setFrameShape(QFrame.HLine)
        sep_b.setFrameShadow(QFrame.Sunken)
        layout.addWidget(sep_b)

        footer = QHBoxLayout()
        footer.addStretch(1)
        btn_exit = QPushButton("Salir")
        btn_exit.clicked.connect(self._on_exit)
        footer.addWidget(btn_exit)
        layout.addLayout(footer)

    def _big_button(self, title, hint, slot):
        """Botón grande con título + tooltip."""
        b = QPushButton(title)
        b.setMinimumHeight(48)
        b.setStyleSheet(
            "QPushButton { text-align: left; padding-left: 12px; }"
        )
        f = QFont("Segoe UI", 10)
        b.setFont(f)
        b.setToolTip(hint)
        b.clicked.connect(slot)
        b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return b

    def _recent_row(self, path):
        row = QFrame()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        btn = QPushButton(f"Diagrama  ·  {os.path.basename(path)}")
        btn.setMinimumHeight(34)
        btn.setStyleSheet(
            "QPushButton { text-align: left; padding-left: 12px; }"
        )
        btn.clicked.connect(lambda _, p=path: self._open_path(p))
        layout.addWidget(btn, 1)
        dir_label = QLabel(os.path.dirname(path))
        dir_label.setStyleSheet("color: #999; font-size: 8pt;")
        layout.addWidget(dir_label)
        return row

    # ---- Actions ----

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

    def _on_exit(self):
        self.action = None
        self.close()


def show_and_get_action():
    """Muestra la welcome y devuelve (action, payload) cuando el user cierra."""
    win = WelcomeWindow()
    win.show()
    QApplication.instance().exec()
    return win.action, win.payload
