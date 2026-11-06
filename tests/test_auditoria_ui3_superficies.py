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


def test_enter_dispara_el_primario_y_no_el_cerrar(app):
    """El ✕ del header es un QPushButton con autoDefault y es el primer
    widget enfocable: Enter cerraba el diálogo en vez de aplicar.  El
    botón primario tiene que ser el default; el ✕ no toma foco."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from dialog_kit import KitDialog
    dlg = KitDialog("Setpoints", "objetivos")
    disparos = []
    dlg.add_button("Cancelar")
    dlg.add_button("Aplicar", role="primary",
                   slot=lambda: disparos.append("aplicar"))
    dlg.show()
    app.processEvents()
    QTest.keyClick(dlg, Qt.Key_Return)
    app.processEvents()
    assert disparos == ["aplicar"], "Enter no ejecutó la acción primaria"
    assert dlg.isVisible(), "Enter cerró el diálogo por el ✕"
    dlg.close()


def test_cerrar_del_header_tiene_tooltip(app):
    from PySide6.QtWidgets import QPushButton
    from dialog_kit import KitDialog
    dlg = KitDialog("x")
    cerrar = [b for b in dlg.findChildren(QPushButton) if b.text() == "✕"]
    assert cerrar and cerrar[0].toolTip(), "el ✕ es un glifo mudo"


# ─────────────────────────── hx_inspector ───────────────────────────

def _vm_hx(**kw):
    vm = {"dTlm": 38.5, "F": 1.0, "U_eff": 900.0, "approach": 16.0,
          "dT_min": 10.0, "data_source": "partial_from_utility_range",
          "n_shell": 1, "n_tube": 2, "service": "condensación de vapor",
          "T_h_in": 260.0, "T_h_out": 200.0, "T_c_in": 184.0,
          "T_c_out": 184.0, "duty": -305.5, "warnings": [], "whb": None,
          "is_cross": False}
    vm.update(kw)
    return vm


def _textos(w):
    from PySide6.QtWidgets import QLabel
    return [l.text() for l in w.findChildren(QLabel)]


@pytest.mark.parametrize("sistema,esperado", [
    ("Modelo (tm/año)", "260.0 / 200.0 °C"),
    ("SI estricto", "533.1 / 473.1 K"),
    ("Imperial (US)", "500.0 / 392.0 °F"),
])
def test_diseno_riguroso_T_de_corrientes_en_el_sistema(
        app, sistema_restaurado, sistema, esperado):
    """«T caliente in/out 260 / 200 K»: los T_h/T_c del diagnóstico son
    temperaturas de CORRIENTE en °C (equipment_sizing las toma de
    Stream.temperature) y el riguroso las rotulaba en kelvin — 533 K de
    error de lectura, al lado del diagrama T-Q que dice 260 °C.  Son dato
    de operación (el mismo de las burbujas): van por el sistema."""
    import hx_inspector as hx
    sistema_restaurado.set_system(sistema)
    rb = hx.RigorousBlock(_vm_hx(), default_open=True)
    txt = _textos(rb)
    assert esperado in txt, f"{sistema}: {txt}"
    assert "260 / 200 K" not in txt
