"""
FLOWSHEET MAIN — entry point del editor Qt (PySide6).

Uso:
    python flowsheet_main_qt.py                # nuevo diagrama vacío
    python flowsheet_main_qt.py --open d.json  # abre un diagrama

Mientras dura la migración Tk → Qt, este script corre EN PARALELO
con `flowsheet_main.py` (Tk legacy).  Ambos comparten el modelo
(`flowsheet_model.py`) y los motores (`equipment_*`, `flowsheet_solver`,
`pipeline`).  Los JSONs guardados son intercambiables.

Requiere:
    pip install PySide6
"""

import sys


def main():
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "Falta PySide6.  Instalalo con:\n"
            "    pip install PySide6\n",
            file=sys.stderr,
        )
        return 2

    import flowsheet_qt as fq
    from flowsheet_model import Flowsheet

    app = QApplication(sys.argv)
    app.setApplicationName("Diagrama de proceso (Qt)")

    win = fq.FlowsheetMainWindow()

    # --open path → cargar diagrama al inicio
    if "--open" in sys.argv:
        idx = sys.argv.index("--open")
        if idx + 1 < len(sys.argv):
            import json
            path = sys.argv[idx + 1]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    win.fs = Flowsheet.from_dict(json.load(f))
                win._rebuild_scene()
                win.view.zoom_fit()
                win._update_status()
            except Exception as e:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    win, "No se pudo abrir",
                    f"{type(e).__name__}: {e}",
                )

    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
