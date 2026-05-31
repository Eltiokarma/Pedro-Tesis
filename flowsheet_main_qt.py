"""
FLOWSHEET MAIN — entry point del editor Qt (PySide6).

Uso:
    python flowsheet_main_qt.py                # nuevo diagrama vacío
    python flowsheet_main_qt.py --open d.json  # abre un diagrama

Editor principal Qt. Comparte modelo (`flowsheet_model.py`) y motores
(`equipment_*`, `flowsheet_solver`) con el resto del proyecto.

Requiere:
    pip install PySide6
"""

import sys


def main():
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        print(
            "Falta PySide6.  Instalalo con:\n"
            "    pip install PySide6\n",
            file=sys.stderr,
        )
        return 2

    import flowsheet_qt as fq
    from flowsheet_model import Flowsheet

    import ui_scaling
    ui_scaling.enable_high_dpi()
    app = QApplication(sys.argv)
    app.setApplicationName("Diagrama de proceso (Qt)")

    # --open path → saltea welcome, abre el editor directo
    initial_path = None
    skip_welcome = False
    if "--open" in sys.argv:
        idx = sys.argv.index("--open")
        if idx + 1 < len(sys.argv):
            initial_path = sys.argv[idx + 1]
            skip_welcome = True
    if "--no-welcome" in sys.argv:
        skip_welcome = True

    if not skip_welcome:
        import welcome_qt as wq
        action, payload = wq.show_and_get_action()
        if action is None:
            return 0           # user cerró sin elegir
        # action == "qt"
        initial_path = payload

    # ---- abrir editor Qt ----
    win = fq.FlowsheetMainWindow()
    if initial_path:
        import json
        try:
            with open(initial_path, "r", encoding="utf-8") as f:
                win.fs = Flowsheet.from_dict(json.load(f))
            win._rebuild_scene()
            win.view.zoom_fit()
            win._update_status()
        except Exception as e:
            QMessageBox.critical(
                win, "No se pudo abrir",
                f"{type(e).__name__}: {e}",
            )

    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
