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


# ─────────────────────── ancho del combo (ALTA) ───────────────────────

def test_combo_no_pide_el_ancho_de_su_entrada_mas_larga(app, turbina):
    """El combo se dimensionaba por su entrada más larga (~420 px): la
    sección Ficha medía ~620 px dentro de un viewport de 320 y cortaba
    ayuda, veredicto y filas, con scroll horizontal en el inspector."""
    fs, b = turbina
    b.equipo_comercial = ""
    panel = _panel_ficha(app, fs, b)
    cb = panel._extras["equipo_comercial"]
    util = _VIEWPORT - 40          # márgenes 20+20 del contenido
    assert cb.minimumSizeHint().width() <= util, \
        f"el combo exige {cb.minimumSizeHint().width()} px"
    assert cb.width() <= util
    panel.close()


def test_combo_angosto_no_esconde_el_texto(app, turbina):
    """Con el combo angosto, el texto completo tiene que seguir
    alcanzable: el popup se abre al ancho de la entrada más larga y el
    tooltip dice la entrada elegida entera."""
    import datasheet as ds
    fs, b = turbina
    b.equipo_comercial = ds.clave_de(ds.entradas_para(b.eq_type)[0])
    panel = _panel_ficha(app, fs, b)
    cb = panel._extras["equipo_comercial"]
    fm = cb.view().fontMetrics()
    mas_larga = max(fm.horizontalAdvance(cb.itemText(i))
                    for i in range(cb.count()))
    assert cb.view().minimumWidth() >= mas_larga, \
        "el popup corta las entradas largas"
    assert cb.toolTip() == cb.currentText()
    # el tooltip sigue a la selección
    cb.setCurrentIndex(3)
    assert cb.toolTip() == cb.itemText(3)
    b.equipo_comercial = ""
    panel.close()


# ─────────────────────── rótulo del selector (ALTA) ───────────────────────

def _rotulo_selector(sect):
    from PySide6.QtWidgets import QLabel
    return next(l for l in sect.findChildren(QLabel)
                if l.text().startswith("Equipo comercial"))


@pytest.mark.parametrize("declarado", [False, True])
def test_rotulo_del_selector_se_lee_entero(app, turbina, declarado):
    """«Equipo comercial · 12 modelos» vivía en una columna de 140 px al
    lado del combo y se pintaba «Equipo comercial · 1»: se leía como un
    solo modelo.  El rótulo va arriba del combo, con el ancho de la
    sección, y la sección entera cabe en el viewport — con o sin
    veredicto declarado."""
    import datasheet as ds
    fs, b = turbina
    b.equipo_comercial = (ds.clave_de(ds.entradas_para(b.eq_type)[0])
                          if declarado else "")
    panel = _panel_ficha(app, fs, b)
    sect = _seccion(panel)
    lbl = _rotulo_selector(sect)
    n = len(ds.entradas_para(b.eq_type))
    assert lbl.text() == f"Equipo comercial · {n} modelos"
    assert lbl.fontMetrics().horizontalAdvance(lbl.text()) <= \
        lbl.contentsRect().width(), \
        f"rótulo cortado: {lbl.contentsRect().width()} px para " \
        f"{lbl.fontMetrics().horizontalAdvance(lbl.text())}"
    util = _VIEWPORT - 40
    assert sect.minimumSizeHint().width() <= util, \
        f"la sección exige {sect.minimumSizeHint().width()} px"
    assert panel._content_scroll.horizontalScrollBar().maximum() == 0, \
        "el inspector scrollea de costado"
    b.equipo_comercial = ""
    panel.close()


# ─────────────────── Cancelar deshace la elección (MEDIA) ───────────────────

def test_elegir_modelo_y_cancelar_no_toca_el_bloque(app, turbina):
    """Elegir un modelo escribía `b.equipo_comercial` directo al modelo:
    «Cancelar» cerraba el panel con el cambio ya hecho.  La elección
    queda pendiente en el panel hasta «Guardar cambios»; mientras tanto
    el veredicto ya la muestra."""
    import datasheet as ds
    from PySide6.QtWidgets import QLabel
    fs, b = turbina
    original = ds.clave_de(ds.entradas_para(b.eq_type)[0])
    otro = ds.clave_de(ds.entradas_para(b.eq_type)[1])
    b.equipo_comercial = original
    cerrado = []
    panel = _panel_ficha(app, fs, b)
    panel.closeRequested.connect(lambda: cerrado.append(True))
    cb = panel._extras["equipo_comercial"]
    cb.setCurrentIndex(cb.findData(otro))
    app.processEvents(); app.processEvents()   # rebuild diferido
    assert b.equipo_comercial == original, \
        "elegir en el combo ya escribió en el modelo"
    # la sección reconstruida muestra la elección pendiente
    cb = panel._extras["equipo_comercial"]
    assert cb.currentData() == otro
    modelo = next(e for e in ds.entradas_para(b.eq_type)
                  if ds.clave_de(e) == otro)
    textos = [l.text() for l in _seccion(panel).findChildren(QLabel)]
    import flowsheet_units as funits
    assert any(funits.fmt_canonica(modelo["S"], "kW") in t
               or f"{modelo['S']:g} kW" in t for t in textos), \
        "el veredicto no refleja el modelo elegido"
    # Cancelar
    panel._cancel_btn.click()
    assert cerrado
    assert b.equipo_comercial == original, "Cancelar no deshizo la elección"
    # reabrir el bloque: el combo vuelve al declarado
    panel.load_block(b, fs, lambda: None)
    panel._switch_section("ficha")
    assert panel._extras["equipo_comercial"].currentData() == original
    panel.close()


def test_elegir_otra_seccion_y_guardar_persiste(app, turbina):
    """La elección pendiente sobrevive a cambiar de sección antes de
    guardar: «Guardar cambios» la persiste aunque el combo ya no esté
    renderizado."""
    import datasheet as ds
    fs, b = turbina
    b.equipo_comercial = ""
    otro = ds.clave_de(ds.entradas_para(b.eq_type)[2])
    panel = _panel_ficha(app, fs, b)
    cb = panel._extras["equipo_comercial"]
    cb.setCurrentIndex(cb.findData(otro))
    app.processEvents(); app.processEvents()
    panel._switch_section("identidad")
    assert b.equipo_comercial == ""
    panel._save_btn.click()
    assert b.equipo_comercial == otro
    b.equipo_comercial = ""
    panel.close()
