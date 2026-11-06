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


def test_approach_desconocido_no_se_anuncia_como_cruce(app):
    """Sin T de corrientes (fallback) el approach es None: no se sabe.
    La card decía «cruce térmico imposible ✗» — afirmaba un fallo físico
    que nadie calculó, a un estudiante que todavía no resolvió."""
    import hx_inspector as hx
    vm = _vm_hx(approach=None, dTlm=40.0, data_source="hardcoded_fallback",
                T_h_in=None, T_h_out=None, T_c_in=None, T_c_out=None)
    g = hx.make_diagnostic_grid(vm, on_open=lambda *_: None)
    assert not any("cruce" in t for t in _textos(g)), _textos(g)
    # y un cruce de verdad se sigue diciendo
    g2 = hx.make_diagnostic_grid(_vm_hx(approach=-5.0), lambda *_: None)
    assert any("cruce" in t for t in _textos(g2))


def test_whb_rotulos_no_se_truncan(app):
    """Los rótulos de la tarjeta WHB tenían ancho FIJO de 92 px: «Tasa de
    vapo», «Rango Field e», «Vapor export» (captura del inspector)."""
    from PySide6.QtWidgets import QLabel
    import hx_inspector as hx
    whb = {"steam_kg_per_h": 65959.0, "range_min": 20000.0,
           "range_max": 800000.0, "variant": "Field erected",
           "scale_mismatch": False, "fuera_rango": False,
           "steam_exported_t_y": 527675.0, "revenue_usd_y": None}
    w = hx.WHBSubcomponent(whb)
    w.resize(334, w.sizeHint().height())
    w.show()
    app.processEvents()
    rotulos = [l for l in w.findChildren(QLabel)
               if l.text() in ("Tasa de vapor", "Rango Field erected",
                               "Vapor exportado")]
    assert len(rotulos) == 3
    for l in rotulos:
        if l.wordWrap():
            # envuelve: cada palabra cabe y la altura alcanza para todas
            # las líneas
            fm = l.fontMetrics()
            palabra = max(fm.horizontalAdvance(p) for p in l.text().split())
            assert palabra <= l.contentsRect().width(), l.text()
            assert l.height() >= l.heightForWidth(l.width()), \
                f"«{l.text()}» cortado en alto"
        else:
            assert l.width() >= l.sizeHint().width(), \
                f"«{l.text()}» truncado: {l.width()} < {l.sizeHint().width()}"
    assert not any("tm/yr" in t for t in _textos(w)), "inglés residual"


def _cuenta_color(img, rect, color, margen=4):
    from PySide6.QtGui import QColor
    c = QColor(color).rgb()
    n = 0
    for x in range(rect.left() + margen, rect.right() - margen):
        for y in range(rect.top() + margen, rect.bottom() - margen):
            if img.pixel(x, y) == c:
                n += 1
    return n


def _render_en_inspector(app, w, ancho=334):
    """Monta `w` bajo un host con el mismo QSS que el cuerpo del
    inspector (`background: bg_elev` SIN selector, que cascadea a todo
    descendiente) y lo renderiza."""
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QWidget, QVBoxLayout
    host = QWidget()
    host.setStyleSheet(f"background:{tokens.TOK['bg_elev']};")
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(w)
    host.resize(ancho, w.sizeHint().height())
    host.show()
    app.processEvents()
    img = QImage(host.size(), QImage.Format_RGB32)
    host.render(img)
    return host, img


def test_tarjetas_hx_no_heredan_parches_del_inspector(app, tema_restaurado):
    """El cuerpo del inspector fija `background:bg_elev` sin selector y
    eso cascadea a cada QLabel: dentro de un aviso ámbar o de la tarjeta
    WHB cada rótulo quedaba como un parche rectangular del fondo del
    panel (muy visible en oscuro).  Y el aviso usaba `QFrame {…}` —QLabel
    ES un QFrame— así que cada rótulo llevaba además su propio borde."""
    tokens.apply_preferences(theme="dark")
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QLabel
    import hx_inspector as hx

    def _rotulos(w, host):
        """Rects (en coords del host) de los QLabel de texto que NO
        declaran fondo propio (el pill de estado sí lo declara)."""
        for l in w.findChildren(QLabel):
            if not l.text() or "background" in l.styleSheet():
                continue
            yield l, QRect(l.mapTo(host, l.rect().topLeft()), l.size())

    fila = hx.WarningRow("sinnott_out", "WHB sub-escala: steam_rate=467 "
                         "kg/h < S_min=5000 kg/h. Considerá un kettle.")
    host, img = _render_en_inspector(app, fila)
    for l, r in _rotulos(fila, host):
        assert _cuenta_color(img, r, tokens.TOK["bg_elev"], 0) == 0, \
            f"«{l.text()[:20]}»: parche del fondo del panel en el aviso"
        assert _cuenta_color(img, r, tokens.TOK["line"], 0) == 0, \
            f"«{l.text()[:20]}»: borde propio heredado de `QFrame {{}}`"
    whb = hx.WHBSubcomponent({
        "steam_kg_per_h": 65959.0, "range_min": 20000.0,
        "range_max": 800000.0, "variant": "Packaged",
        "scale_mismatch": False, "fuera_rango": False,
        "steam_exported_t_y": None, "revenue_usd_y": None})
    host2, img2 = _render_en_inspector(app, whb)
    for l, r in _rotulos(whb, host2):
        assert _cuenta_color(img2, r, tokens.TOK["bg_elev"], 0) == 0, \
            f"«{l.text()[:20]}»: parche del fondo del panel en la WHB"


def test_riguroso_sin_rayas_bajo_cada_rotulo(app, tema_restaurado):
    """`border-top` del cuerpo del riguroso iba sin selector: cada QLabel
    de la tabla clave-valor dibujaba su propia raya superior."""
    tokens.apply_preferences(theme="light")
    from PySide6.QtGui import QColor
    import hx_inspector as hx
    rb = hx.RigorousBlock(_vm_hx(), default_open=True)
    host, img = _render_en_inspector(app, rb)
    body = rb._body.geometry().translated(rb.geometry().topLeft())
    linea = QColor(tokens.TOK["line_soft"]).rgb()
    filas_con_raya = 0
    for y in range(body.top() + 3, body.bottom() - 3):
        n = sum(1 for x in range(body.left() + 4, body.right() - 4)
                if img.pixel(x, y) == linea)
        if n >= 20:
            filas_con_raya += 1
    assert filas_con_raya == 0, f"{filas_con_raya} rayas dentro del cuerpo"


# ─────────────────────────── book_table ───────────────────────────

# Ancho que recibe una tarjeta de la sección Diagnóstico con el inspector
# a su ancho POR DEFECTO (tokens.PANEL_W = 520): sidebar 186, scrollbar
# vertical y márgenes de contenido 20+20 dejan 280 px (medido: viewport
# 320 − 40).
_ANCHO_TARJETA = 280


@pytest.fixture(scope="module")
def specs_libro(app):
    import examples_registry as reg
    import flowsheet_solver as fsv
    import inspector_evidence as ev
    fs = reg.load_example("sulfuric")
    fsv.solve(fs)
    r = next(b for b in fs.blocks.values() if b.name == "R-101")
    fs2 = reg.load_example("nested_recycle")
    fsv.solve(fs2)
    v = next(b for b in fs2.blocks.values() if b.name == "V-101")
    return {"stoich": ev.stoich_book_spec(r, fs),
            "flash": ev.flash_book_spec(v),
            "atomos": ev.atom_balance_book_spec(r, fs)}


@pytest.mark.parametrize("clave", ["stoich", "flash"])
def test_tabla_de_libro_cabe_en_el_inspector(app, specs_libro, clave):
    """La tabla de libro empujaba el inspector ENTERO a scroll horizontal:
    a su ancho por defecto solo se veía la primera columna del reparto del
    flash — K_i, el dato de la tabla, quedaba fuera de pantalla.  Los
    culpables: el strip de contexto («R006 — Oxidación de SO2 a SO3
    (proceso de contacto)» en una sola línea: 910 px), las filas de chips
    y de procedencia sin wrap, y la grilla, que fijaba su mínimo en el
    ancho natural de la tabla."""
    from book_table import BookTable
    spec = specs_libro[clave]
    assert spec is not None
    w = BookTable(spec)
    assert w.minimumSizeHint().width() <= _ANCHO_TARJETA, \
        f"{clave}: exige {w.minimumSizeHint().width()} px"
    # y a ese ancho la grilla sigue teniendo TODAS sus columnas —con
    # scroll propio—, no recortadas en silencio
    w.resize(_ANCHO_TARJETA, w.sizeHint().height())
    w.show()
    app.processEvents()
    assert w.grid.width() >= w.grid._natural


def test_balance_de_atomos_strip_y_kicker_envuelven(app, specs_libro):
    """Misma causa en la tarjeta de átomos: kicker y strip de contexto
    exigían 524 y 832 px.  (El resto de la tarjeta —fila de elemento y
    las dos cajas de procedencia lado a lado— queda abierto: ver el
    reporte de la auditoría.)"""
    from PySide6.QtWidgets import QFrame
    from book_table import AtomBalanceCard
    w = AtomBalanceCard(specs_libro["atomos"])
    lay = w.layout()
    kicker = lay.itemAt(0).widget()
    strip = lay.itemAt(1).widget()
    assert isinstance(strip, QFrame)
    for parte, nombre in ((kicker, "kicker"), (strip, "contexto")):
        assert parte.minimumSizeHint().width() <= _ANCHO_TARJETA, \
            f"{nombre}: exige {parte.minimumSizeHint().width()} px"


@pytest.mark.parametrize("rotulo,esperado", [
    ("Especie", "ESPECIE"), ("Comp.", "COMP."), ("Etapa", "ETAPA"),
    ("z_i", "z_i"), ("x_LK", "x_LK"), ("F_i(X)", "F_i(X)"),
    ("L [kmol/h]", "L [kmol/h]"), ("T [°C]", "T [°C]"),
    ("ν/|ν_A|", "ν/|ν_A|"),
])
def test_encabezado_en_caps_no_toca_notacion_ni_unidades(rotulo, esperado):
    """El encabezado ponía en caps todo lo ASCII: «Z_I», «X_LK»,
    «L [KMOL/H]» (captura de la tabla Wang-Henke y del flash).  z_i es la
    fracción molar del componente i; KMOL no es una unidad."""
    from book_table import _BookGrid
    assert _BookGrid._hdr_text(rotulo) == esperado


@pytest.mark.parametrize("sistema,u_t,u_p", [
    ("Modelo (tm/año)", "°C", "bar"),
    ("SI estricto", "K", "kPa"),
    ("Imperial (US)", "°F", "psi"),
])
def test_contexto_del_flash_respeta_el_sistema(app, specs_libro,
                                               sistema_restaurado,
                                               sistema, u_t, u_p):
    """El strip del reparto del flash imprimía «76.9 °C · 1.013 bar»
    fijos, encima de los campos T_flash/P_flash del mismo inspector que
    sí respetan el sistema: el mismo dato en dos unidades en un panel
    (exactamente el §2.1 de la auditoría 3, reapareciendo)."""
    import examples_registry as reg
    import flowsheet_solver as fsv
    import inspector_evidence as ev
    sistema_restaurado.set_system(sistema)
    fs = reg.load_example("nested_recycle")
    fsv.solve(fs)
    v = next(b for b in fs.blocks.values() if b.name == "V-101")
    ctx = dict(ev.flash_book_spec(v)["context"])
    assert ctx["Flash TP · T"].endswith(u_t), ctx
    assert ctx["P"].endswith(u_p), ctx


def test_duties_de_columna_respetan_el_sistema(app, sistema_restaurado):
    """Q_cond/Q_reb del strip de etapas Wang-Henke salían en kW/MW fijos."""
    import types
    import distillation_wanghenke as wh
    import inspector_evidence as ev
    r = wh.wang_henke(["benzene", "toluene"], [0.5, 0.5], F=10.0 / 3600.0,
                      T_feed_K=380.0, P_bar=1.013, N=8, feed_stage=4,
                      D_over_F=0.5, R=1.8, max_iter=80)
    r.update(feed_stage=4, _comps=["benzene", "toluene"],
             Q_cond_kW=-120.0, Q_reb_kW=135.0)
    b = types.SimpleNamespace(_wh_result=r, column_LK="benzene",
                              column_HK="toluene", column_active=True)
    sistema_restaurado.set_system("Imperial (US)")
    ctx = dict(ev.wh_stage_book_spec(b, None)["context"])
    assert ctx["Q_cond"].endswith("MMBtu/h") and ctx["Q_cond"].startswith("-")
    assert ctx["Q_reb"].endswith("MMBtu/h") and ctx["Q_reb"].startswith("+")
    sistema_restaurado.set_system("Modelo (tm/año)")
    ctx = dict(ev.wh_stage_book_spec(b, None)["context"])
    assert ctx["Q_reb"] == "+135 kW", ctx


# ─────────────── diálogos del kit en uso (flowsheet_qt) ───────────────

@pytest.fixture
def dialogos_capturados(monkeypatch):
    """Intercepta KitDialog.exec: el diálogo se construye entero pero no
    bloquea; el test lee lo que se iba a mostrar."""
    import dialog_kit
    vistos = []
    monkeypatch.setattr(dialog_kit.KitDialog, "exec",
                        lambda self: vistos.append(self) or 0)
    return vistos


@pytest.fixture(scope="module")
def ventana(app):
    import flowsheet_qt as fq
    w = fq.FlowsheetMainWindow()
    w.action_load_example("boiler_ft")
    return w


def test_setpoints_en_el_sistema_de_unidades(app, ventana, sistema_restaurado,
                                             dialogos_capturados):
    """El diálogo Setpoints imprimía «°C» fijo para objetivo, actual y Δ,
    aunque el usuario declara la T objetivo en el inspector de corrientes
    en SU unidad.  La Δ es una diferencia: se resta en la unidad activa
    (10 °C de salto son 18 °F, no 50 °F)."""
    from PySide6.QtWidgets import QLabel
    s = next(x for x in ventana.fs.streams.values()
             if x.temperature is not None)
    previo = s.target_temperature
    try:
        s.target_temperature = float(s.temperature) + 10.0
        sistema_restaurado.set_system("Imperial (US)")
        ventana.action_setpoints()
        dlg = dialogos_capturados[-1]
        textos = [l.text() for l in dlg.findChildren(QLabel)]
        assert not any(t.endswith("°C") for t in textos), textos
        assert "-18.0 °F" in textos, textos
    finally:
        s.target_temperature = previo


def test_lang_flujos_en_el_sistema_de_unidades(app, ventana,
                                               sistema_restaurado,
                                               dialogos_capturados):
    from PySide6.QtWidgets import QLabel
    sistema_restaurado.set_system("Métrico (ingeniería)")
    ventana.action_compute()
    dlg = dialogos_capturados[-1]
    textos = [l.text() for l in dlg.findChildren(QLabel)]
    assert not any("tm/año" in t for t in textos), textos
    assert any(t.endswith("kg/h") for t in textos), textos
