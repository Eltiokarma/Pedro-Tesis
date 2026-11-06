"""tests/test_auditoria_ui3_dof_chip.py — §3.1 de la auditoría UI 3.

El chip DOF del pie del sidebar del inspector cortaba «Sistema
determinado» a mitad de palabra («Sistema determin»): el sidebar es de
ancho fijo y el texto pedía más de lo que el QLabel recibía.

Se testea MIDIENDO geometría, offscreen: el texto, maquetado con la
fuente real del label y el ancho que el layout le dio, tiene que caber
entero (ninguna línea más ancha que el label, ningún renglón por debajo
de su alto) en todos los estados DOF y en los dos temas.
"""
import os
import sys

import pytest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

import tokens

ESTADOS = [("ok", 0), ("warn", 1), ("warn", 3), ("err", 1), ("err", 12)]


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tema_restaurado():
    previo = tokens._PREFS["theme"]
    yield
    tokens.apply_preferences(theme=previo)
    tokens._PrefsBus.emit()


def _medir(label):
    """(ancho pedido, alto pedido, ancho disponible, alto disponible).

    Maqueta el rich text del label con su fuente real; si el label parte
    líneas, con el ancho que el layout le dio (como hace QLabel)."""
    from PySide6.QtGui import QTextDocument
    disp = label.contentsRect()
    doc = QTextDocument()
    doc.setDocumentMargin(0)
    doc.setDefaultFont(label.font())
    doc.setHtml(label.text())
    if label.wordWrap():
        doc.setTextWidth(disp.width())
    return doc.idealWidth(), doc.size().height(), disp.width(), disp.height()


@pytest.mark.parametrize("tema", ["light", "dark"])
def test_chip_dof_no_trunca(app, tema_restaurado, tema):
    import block_inspector as bi
    from PySide6.QtGui import QFontMetrics
    tokens.apply_preferences(theme=tema)
    tokens._PrefsBus.emit()

    sb = bi._InspectorSidebar()
    sb.resize(sb.width(), 600)
    sb.show()
    try:
        for estado, n in ESTADOS:
            sb.set_dof(estado, n)
            app.processEvents()
            lbl = sb._dof_text
            plano = lbl.text().replace("<b>", "").replace("</b>", "")
            una_linea = QFontMetrics(lbl.font()).horizontalAdvance(plano)
            ancho, alto, w, h = _medir(lbl)
            assert ancho <= w + 0.5, (
                f"{tema}/{estado}: «{plano}» pide {ancho:.0f}px de ancho y "
                f"el label tiene {w}px (en una línea: {una_linea}px)")
            assert alto <= h + 0.5, (
                f"{tema}/{estado}: «{plano}» pide {alto:.0f}px de alto y "
                f"el label tiene {h}px: se recorta un renglón")
    finally:
        sb.close()
        sb.deleteLater()
