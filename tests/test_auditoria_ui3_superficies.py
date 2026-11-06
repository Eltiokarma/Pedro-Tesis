"""tests/test_auditoria_ui3_superficies.py — auditoría UI 3, §3.2.

Las cuatro superficies que nacieron después de la auditoría 2 y que el
escaneo de cierre solo verificó por censo (0 hex, tipografía del
sistema), sin pasada de UX: el selector de equipo comercial,
`dialog_kit`, `book_table` y `hx_inspector`.

Igual que `tests/test_auditoria_ui3.py`, los defectos se testean
MIDIENDO (geometría, rects, texto pintado) y no leyendo código: casi
todos son de la clase «algo empuja/pisa/tapa a otra cosa», invisibles
para un test de lógica.
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


@pytest.fixture
def sistema_restaurado():
    import flowsheet_units as funits
    previo = funits.active()
    yield funits
    for k, v in previo.items():
        funits.set_quantity(k, v)


# ─────────────────────────── dialog_kit ───────────────────────────

def test_kit_table_nota_larga_no_desborda_el_dialogo(app):
    """La columna «Notas» del diálogo DOF recibe `"; ".join(b.notes)` —
    frases enteras.  Sin word-wrap la tabla exigía el ancho de la nota
    más larga: el cuerpo scrolleaba en horizontal, la tercera stat card
    quedaba cortada y la nota se leía a medias."""
    from dialog_kit import KitDialog, kit_table
    nota = ("falta T de salida en la corriente S-7; declarar T objetivo "
            "o duty en el bloque aguas arriba; revisar la herencia de P")
    dlg = KitDialog("Grados de libertad · Balance", "x", size=(760, 560))
    tabla = kit_table(["Bloque", "Tipo", "M", "E", "C", "", "Notas"],
                      [["E-101", ("Heat exch. — fixed tube", "mute"),
                        "1", "0", "0", ("⚠", "warn"), (nota, "mute")]],
                      aligns=["l", "l", "r", "r", "r", "c", "l"])
    dlg.body.addWidget(tabla)
    dlg.show()
    app.processEvents()
    # ancho útil del cuerpo: 760 − márgenes 24+24
    assert tabla.minimumSizeHint().width() <= 760 - 48, \
        "la nota larga ensancha la tabla más que el diálogo"
    dlg.close()
