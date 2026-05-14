# ======================================================
# FLOWSHEET_MAIN — entry point cuando el flowsheet es la
# ventana principal de la app (no Toplevel hijo).
#
# Uso:
#   python flowsheet_main.py                # nuevo flowsheet vacío
#   python flowsheet_main.py --open f.json  # abre flowsheet desde JSON
#
# Desde acá el user arma el proceso en bloques y aprieta
# 'Análisis económico →' para lanzar ANA.py.
# ======================================================

import sys

from tkinter import Tk
from tkinter import messagebox

from flowsheet_ui import FlowsheetEditor, Flowsheet


def main():
    initial_json = None
    if "--open" in sys.argv:
        idx = sys.argv.index("--open")
        if idx + 1 < len(sys.argv):
            initial_json = sys.argv[idx + 1]

    root = Tk()
    editor = FlowsheetEditor(root, df_capital=None, on_apply=None, mode="main")

    if initial_json:
        try:
            import json
            with open(initial_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            editor.fs = Flowsheet.from_dict(data)
            for b in editor.fs.blocks.values():
                editor._render_block(b)
            for s in editor.fs.streams.values():
                editor._render_stream(s)
            editor._update_status()
        except Exception as e:
            messagebox.showerror("Open failed", f"{type(e).__name__}: {e}")

    root.mainloop()


if __name__ == "__main__":
    main()
