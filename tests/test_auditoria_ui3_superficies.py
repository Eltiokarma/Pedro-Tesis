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
