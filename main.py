# ======================================================
# MAIN — entry point de la app.
#
# Muestra una pantalla de bienvenida con tres opciones:
#
#   [ New project ]   → nuevo flowsheet vacío
#   [ Open project ]  → .json (flowsheet) o .xlsx (legacy
#                       análisis económico sin proceso)
#   [ Recent ]        → últimos archivos abiertos
#
# El "proyecto" en la nueva arquitectura es el flowsheet.
# El análisis económico se accede después, desde un botón
# adentro del flowsheet.
# ======================================================

import json
import os
import subprocess
import sys

from tkinter import Tk, StringVar
from tkinter import ttk
from tkinter import filedialog, messagebox


RECENT_FILE = os.path.expanduser("~/.pedro_tesis_recent.json")
MAX_RECENT  = 8


# ======================================================
# RECENT FILES (~/.pedro_tesis_recent.json)
# ======================================================

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


# ======================================================
# LAUNCHERS
# ======================================================

def _here():
    return os.path.dirname(os.path.abspath(__file__))


def _launch_flowsheet_new():
    subprocess.Popen([sys.executable, "flowsheet_main.py"], cwd=_here())


def _launch_flowsheet_open(json_path):
    _save_recent(json_path)
    subprocess.Popen(
        [sys.executable, "flowsheet_main.py", "--open", json_path],
        cwd=_here(),
    )


def _launch_legacy_xlsx(xlsx_path):
    _save_recent(xlsx_path)
    subprocess.Popen(
        [sys.executable, "ANA.py", "--import", xlsx_path],
        cwd=_here(),
    )


# ======================================================
# WELCOME WINDOW
# ======================================================

class WelcomeWindow:

    def __init__(self):
        root = Tk()
        root.title("Tesis — Análisis de proceso y económico")
        root.geometry("680x520+200+120")
        self.root = root

        # encabezado
        header = ttk.Frame(root, padding=(24, 18))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="Análisis de proceso y económico",
            font=("Segoe UI", 18, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            header,
            text="Diseñá el proceso en bloques y después corré el análisis económico.",
            foreground="#666",
        ).pack(anchor="w", pady=(4, 0))

        ttk.Separator(root, orient="horizontal").pack(fill="x")

        body = ttk.Frame(root, padding=(24, 16))
        body.pack(fill="both", expand=True)

        ttk.Label(
            body, text="Empezar", font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        btn_new = ttk.Button(
            body, text="  Nuevo proyecto — diseñar el proceso desde cero",
            command=self._on_new,
        )
        btn_new.pack(fill="x", pady=3, ipady=6)

        btn_open = ttk.Button(
            body, text="  Abrir proyecto…  (.json del diagrama o .xlsx legacy)",
            command=self._on_open,
        )
        btn_open.pack(fill="x", pady=3, ipady=6)

        # recientes
        ttk.Label(
            body, text="Recientes", font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(18, 4))

        recent = _load_recent()
        if not recent:
            ttk.Label(
                body, text="(sin archivos recientes)",
                foreground="#888", font=("Segoe UI", 9, "italic"),
            ).pack(anchor="w")
        else:
            for path in recent:
                self._add_recent_row(body, path)

        # pie
        footer = ttk.Frame(root, padding=(24, 10))
        footer.pack(fill="x", side="bottom")
        ttk.Separator(root, orient="horizontal").pack(fill="x", side="bottom")
        ttk.Button(footer, text="Salir", command=root.destroy).pack(side="right")

    def _add_recent_row(self, body, path):
        row = ttk.Frame(body)
        row.pack(fill="x", pady=1)
        ext = os.path.splitext(path)[1].lower()
        tag = "Diagrama" if ext == ".json" else ("Excel legacy" if ext in (".xlsx", ".xls") else "?")
        ttk.Button(
            row, text=f"{tag}  ·  {os.path.basename(path)}",
            command=lambda p=path: self._open_path(p),
        ).pack(side="left", fill="x", expand=True)
        ttk.Label(row, text=os.path.dirname(path),
                  foreground="#999", font=("Segoe UI", 8)).pack(side="left", padx=8)

    def _on_new(self):
        self.root.destroy()
        _launch_flowsheet_new()

    def _on_open(self):
        path = filedialog.askopenfilename(
            title="Abrir proyecto",
            filetypes=[
                ("Diagrama de proceso (JSON)", "*.json"),
                ("Proyecto legacy (Excel)",    "*.xlsx *.xls"),
                ("Todos los archivos",         "*.*"),
            ],
        )
        if not path:
            return
        self._open_path(path)

    def _open_path(self, path):
        ext = os.path.splitext(path)[1].lower()

        if ext == ".json":
            self.root.destroy()
            _launch_flowsheet_open(path)
            return

        if ext in (".xlsx", ".xls"):
            cont = messagebox.askokcancel(
                "Proyecto sin proceso modelado",
                "Este archivo es un proyecto legacy del análisis económico, "
                "sin diagrama de proceso asociado.\n\n"
                "Lo voy a abrir directamente en el análisis económico. "
                "Si querés modelar el proceso en bloques primero, cancelá "
                "y elegí 'Nuevo proyecto'.",
            )
            if not cont:
                return
            self.root.destroy()
            _launch_legacy_xlsx(path)
            return

        messagebox.showerror(
            "Tipo de archivo no soportado",
            f"No sé cómo abrir la extensión: {ext}\n"
            "Usá .json (diagrama) o .xlsx (proyecto legacy).",
        )

    def run(self):
        self.root.mainloop()


def main():
    WelcomeWindow().run()


if __name__ == "__main__":
    main()
