"""tests/test_auditoria_ui3_selector.py — auditoría UI 3, §4.1.

El selector de equipo comercial de la sección «Ficha técnica» del
inspector de bloques.  Como en `tests/test_auditoria_ui3_superficies.py`,
los defectos de layout se testean MIDIENDO (anchos, texto que cabe,
píxeles pintados) y los de comportamiento ejerciendo el panel como lo
haría el usuario (elegir un modelo, cancelar, reabrir).

Caso de prueba: steam_turbine / TB-101 — «Turbine — steam» tiene 12
modelos en el catálogo y su veredicto escalar ejercita requerido,
instalado, utilización y los checks de P y T a la vez.
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

# Ancho del viewport del inspector en el que la auditoría midió el
# desborde (dock en su ancho mínimo útil).
_VIEWPORT = 320


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


@pytest.fixture(scope="module")
def turbina():
    """(fs, bloque) de steam_turbine resuelto, sin equipo declarado."""
    from export_examples import _headless_mocks
    _headless_mocks()
    import examples_registry as reg
    import flowsheet_solver as fsv
    fs = reg.load_example("steam_turbine")
    fsv.solve(fs)
    b = next(x for x in fs.blocks.values() if x.name == "TB-101")
    return fs, b


def _clave(eq_type, pred):
    """Clave del primer modelo del catálogo que cumple `pred` — resuelto
    en vivo para no pudrirse cuando la cosecha retire una entrada."""
    import datasheet as ds
    for e in ds.entradas_para(eq_type):
        if pred(e):
            return ds.clave_de(e)
    pytest.skip("el catálogo ya no tiene un modelo para este caso")


def _panel_ficha(app, fs, b, viewport=_VIEWPORT):
    """Inspector con la sección Ficha abierta y el viewport del contenido
    exactamente en `viewport` px."""
    from block_inspector import BlockInspectorPanel
    panel = BlockInspectorPanel()
    panel.load_block(b, fs, lambda: None)
    panel.resize(viewport + panel._sidebar.sizeHint().width() + 40, 1000)
    panel.show()
    panel._switch_section("ficha")
    app.processEvents()
    vp = panel._content_scroll.viewport().width()
    panel.resize(panel.width() + viewport - vp, 1000)
    app.processEvents(); app.processEvents()
    return panel


def _seccion(panel):
    return panel._content_lay.itemAt(0).widget()


# ─────────────────────── texto de las entradas ───────────────────────

def test_texto_de_entrada_vive_en_un_solo_helper(app, turbina):
    """El texto «Marca · Modelo — S unidad» se armaba inline en el
    inspector: cualquier otra superficie que listara el catálogo tenía
    que copiarlo.  Ahora sale de `datasheet.texto_entrada`."""
    import datasheet as ds
    import equipment_costs as ec
    fs, b = turbina
    panel = _panel_ficha(app, fs, b)
    cb = panel._extras["equipo_comercial"]
    s_unit = ec.EQUIPMENT_DATA[b.eq_type].get("S_unit", "")
    esperados = [ds.texto_entrada(e, s_unit)
                 for e in ds.entradas_para(b.eq_type)]
    assert [cb.itemText(i) for i in range(1, cb.count())] == esperados
    # sin S escalar: la granularidad de la envolvente
    assert ds.texto_entrada({"marca": "M", "modelo": "X",
                             "granularidad": "familia"}) == \
        "M · X — envolvente de familia"
    assert ds.texto_entrada({"marca": "M", "modelo": "X"}) == \
        "M · X — envolvente del modelo"
    panel.close()
