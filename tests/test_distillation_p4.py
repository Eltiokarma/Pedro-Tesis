"""
tests/test_distillation_p4.py — PARCHE 4: UI del panel de columnas (smoke).

Caso J: cargar un ejemplo con columna, resolver, seleccionar el bloque
Tower y verificar que prop_label (texto plano monoespaciado) contiene los
campos nuevos sin romper el formato existente.

USO:  QT_QPA_PLATFORM=offscreen python -m pytest tests/test_distillation_p4.py -v
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Cargar PySide6 REAL en import (durante la colección de pytest), ANTES de
# que otros tests (test_example_locks) llamen validate_ui.headless_mocks(),
# que reemplaza PySide6 por MagicMock en sys.modules si aún no está cargado.
# Sin esto, este test (el único que necesita Qt real) recibe el mock.
import PySide6.QtWidgets  # noqa: F401

import flowsheet_model as fm
import flowsheet_solver as fsv
from examples_library import ExampleBuilder


class TestJ_PanelColumna(unittest.TestCase):
    def _panel_text(self, method):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        import flowsheet_qt as fq
        win = fq.FlowsheetMainWindow()
        fs = fm.Flowsheet()
        # industrial_complete: columna T-201 multicomponente (separación
        # factible con las keys auto-detectadas → FUG produce N).
        ExampleBuilder(fs)._example_industrial_complete()
        col = next(b for b in fs.blocks.values()
                   if getattr(b, "column_active", False))
        col.column_method = method
        win.fs = fs
        win._rebuild_scene()
        fsv.solve(fs)
        app.processEvents()
        item = win.scene.block_items[col.id]
        item.setSelected(True)
        win._on_selection_changed()
        app.processEvents()
        return win.prop_label.text(), col

    def test_fug_block_presente(self):
        txt, col = self._panel_text("fug")
        self.assertIn("─ DISEÑO FUG (NRTL) ─", txt)
        self.assertIn("q feed", txt)
        self.assertIn("α promedio", txt)
        self.assertIn("N real", txt)

    def test_wanghenke_block_presente(self):
        txt, col = self._panel_text("wanghenke")
        self.assertIn("─ DISEÑO FUG (NRTL) ─", txt)
        self.assertIn("q feed", txt)
        self.assertIn("N real", txt)
        self.assertEqual(col.column_method, "wanghenke")
        self.assertIn("─ WANG-HENKE (MESH) ─", txt)
        self.assertIn("Convergió", txt)
        self.assertIn("Balance E", txt)

    def test_formato_sin_html_ni_emoji(self):
        txt, _ = self._panel_text("fug")
        # formato planilla técnica: sin tags HTML, sin emojis nuevos
        self.assertNotIn("<", txt)
        self.assertNotIn("<br", txt)
        for emoji in ("🔥", "💧", "⚗", "📊", "✅"):
            self.assertNotIn(emoji, txt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
