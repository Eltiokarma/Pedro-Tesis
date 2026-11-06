"""tests/test_auditoria_ui3_welcome.py — Auditoría UI 3 §3.1: welcome grande.

La composición de la welcome se diseñó para ~720×560.  Al maximizar, el
stretch entre «Recientes» y «Ejemplos» se comía todo el alto extra: a
1400×900 quedaba una banda vacía de ~600 px entre las dos secciones.  A
la vez, el ancho de texto de las tres tarjetas de ejemplo fijaba el
mínimo de la ventana en ~1035 px: el tamaño de diseño ni siquiera era
alcanzable.

Como los hallazgos de test_auditoria_ui3.py, esto se testea MIDIENDO
geometría (rect vs rect), no leyendo código.
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

_RECIENTES = [f"/home/user/tesis/proyectos/planta_{i}_metanol_final.json"
              for i in range(6)]


@pytest.fixture(scope="module")
def app():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _welcome(app, monkeypatch, w, h, recientes):
    import welcome_qt as wq
    monkeypatch.setattr(wq, "_load_recent", lambda: list(recientes))
    win = wq.WelcomeWindow()
    win.resize(w, h)
    win.show()
    app.processEvents()
    return win


def _kicker(win, texto):
    from PySide6.QtWidgets import QLabel
    hits = [lb for lb in win.findChildren(QLabel) if lb.text() == texto]
    assert len(hits) == 1, texto
    return hits[0]


def _rect_en_ventana(win, wid):
    from PySide6.QtCore import QRect
    return QRect(wid.mapTo(win, wid.rect().topLeft()), wid.size())


def _hueco_recientes_ejemplos(win):
    """Px entre el borde inferior de la sección Recientes (su último
    widget) y el borde superior del kicker «EJEMPLOS»."""
    k_rec = _kicker(win, "RECIENTES")
    k_ej = _kicker(win, "EJEMPLOS")
    lay = k_rec.parentWidget().layout()
    i0, i1 = lay.indexOf(k_rec), lay.indexOf(k_ej)
    seccion = [lay.itemAt(i).widget() for i in range(i0, i1)]
    seccion = [w for w in seccion if w is not None]
    fondo = max(_rect_en_ventana(win, w).bottom() for w in seccion)
    return _rect_en_ventana(win, k_ej).top() - fondo


@pytest.mark.parametrize("recientes", [[], _RECIENTES],
                         ids=["sin_recientes", "seis_recientes"])
def test_ventana_grande_no_abre_banda_entre_secciones(app, monkeypatch,
                                                      recientes):
    """A 1400×900 el hueco Recientes→Ejemplos no crece (más allá del alto
    que liberan las tarjetas) respecto del de diseño (720×560) y queda
    acotado en unidades de SECT_GAP."""
    chica = _welcome(app, monkeypatch, 720, 560, recientes)
    hueco_diseno = _hueco_recientes_ejemplos(chica)
    chica.close()

    grande = _welcome(app, monkeypatch, 1400, 900, recientes)
    assert grande.size().width() == 1400 and grande.size().height() == 900
    hueco = _hueco_recientes_ejemplos(grande)
    grande.close()

    # Tolerancia: a 720 px los títulos de las tarjetas hacen word-wrap
    # (tarjetas más altas); a 1400 px van en una línea y ese alto vuelve
    # al hueco.  Lo que NO puede pasar es que el alto extra de la ventana
    # (+340 px) termine entre las secciones.
    assert hueco <= hueco_diseno + 3 * tokens.SECT_GAP, (
        f"el hueco creció al agrandar: {hueco_diseno} → {hueco} px")
    assert hueco <= 12 * tokens.SECT_GAP, (
        f"banda vacía de {hueco} px entre Recientes y Ejemplos "
        f"(> 12 × SECT_GAP = {12 * tokens.SECT_GAP})")


@pytest.mark.parametrize("recientes", [[], _RECIENTES],
                         ids=["sin_recientes", "seis_recientes"])
def test_tamano_de_diseno_entra_sin_desbordes(app, monkeypatch, recientes):
    """A 720×560 la ventana respeta el tamaño (el mínimo no lo excede),
    todo widget visible cae dentro de la ventana y el título de cada
    tarjeta de ejemplo entra entero (word-wrap, sin recorte)."""
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QWidget
    win = _welcome(app, monkeypatch, 720, 560, recientes)
    assert (win.width(), win.height()) == (720, 560), (
        f"la ventana no baja a 720×560: mínimo {win.minimumSizeHint()}")
    marco = QRect(0, 0, win.width(), win.height())
    fuera = [type(w).__name__ for w in win.findChildren(QWidget)
             if w.isVisible() and w.window() is win
             and not marco.contains(_rect_en_ventana(win, w))]
    assert fuera == [], f"widgets desbordados a 720×560: {fuera}"

    import welcome_qt as wq
    tarjetas = win.findChildren(wq._ExampleCard)
    assert tarjetas, "no se encontraron tarjetas de ejemplo"
    for t in tarjetas:
        lb = t.label
        assert lb.heightForWidth(lb.width()) <= lb.height(), (
            f"título recortado en la tarjeta «{lb.text()}»")
    win.close()
