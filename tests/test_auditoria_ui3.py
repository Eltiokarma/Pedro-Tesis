"""tests/test_auditoria_ui3.py — escaneo de cierre de la auditoría UI 2.

Dos clases de test:

  1. CIERRE — congela los hallazgos que los ciclos 2-5 resolvieron, para
     que no reaparezcan (el canvas respira el tema, cero hex sueltos en la
     capa UI, welcome dentro del sistema).
  2. HALLAZGOS DEL ESCANEO — los defectos que este ciclo encontró y
     arregló: dos colisiones que solo se ven cuando algo se dibuja encima
     de otra cosa, invisibles para un test de lógica.

Los dos defectos nuevos comparten causa: un elemento se ancló a una
posición sin saber que otro ya vivía ahí.  Por eso se testean MIDIENDO
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


@pytest.fixture(scope="module")
def ventana(app):
    import flowsheet_qt as fq
    w = fq.FlowsheetMainWindow()
    w.action_load_example("boiler_ft")
    return w


# ─────────────────── 1. Cierre de la auditoría 2 ───────────────────

def test_canvas_respira_el_tema(ventana, tema_restaurado):
    """§A, el hallazgo estructural: el papel del lienzo seguía claro con
    tema oscuro y los glifos se volvían manchas.  Hoy la escena escucha
    themeChanged y el fondo sale del token."""
    vistos = {}
    for tema in ("light", "dark"):
        tokens.apply_preferences(theme=tema)
        tokens._PrefsBus.emit()
        fondo = ventana.scene.backgroundBrush().color().name().lower()
        assert fondo == tokens.TOK["canvas_bg"].lower(), tema
        vistos[tema] = fondo
    assert vistos["light"] != vistos["dark"], \
        "el canvas no cambió de color entre temas"


def test_capa_ui_sin_hex_sueltos():
    """§A.3/§G.5: 90 hex en flowsheet_qt, ~45 en inspector_evidence, la
    paleta duplicada de solver_report.  Hoy la clase entera está muerta;
    tokens.py es el único que declara color."""
    import re
    patron = re.compile(r"#[0-9a-fA-F]{6}\b")
    for nombre in ("flowsheet_qt.py", "editor_chrome.py", "block_inspector.py",
                   "stream_inspector.py", "streams_table.py", "welcome_qt.py",
                   "econ_richview.py", "inspector_evidence.py",
                   "solver_report.py", "datasheet_export.py"):
        with open(os.path.join(_PARENT, nombre), encoding="utf-8") as f:
            codigo = [l for l in f if not l.lstrip().startswith("#")]
        hallados = patron.findall("".join(codigo))
        assert not hallados, f"{nombre} volvió a hardcodear color: {hallados}"


def test_welcome_dentro_del_sistema():
    """§D.1: era la única superficie 100 % ajena (Segoe UI + hex)."""
    with open(os.path.join(_PARENT, "welcome_qt.py"), encoding="utf-8") as f:
        src = f.read()
    assert "Segoe UI" not in src
    assert "TOK[" in src


def test_export_de_fichas_no_sigue_el_tema_de_pantalla(tmp_path,
                                                      tema_restaurado):
    """§A.4.4: «export siempre en papel claro» tenía que ser decisión
    declarada y no accidente.  Con tema OSCURO activo el legajo se sigue
    imprimiendo en tinta clara — si leyera TOK saldría gris sobre negro."""
    import datasheet_export as dx
    src = open(os.path.join(_PARENT, "datasheet_export.py"),
               encoding="utf-8").read()
    assert "THEME_LIGHT" in src, "el export volvió a leer el tema activo"

    from export_examples import _headless_mocks
    _headless_mocks()
    import examples_registry as reg
    import flowsheet_solver as fsv
    fs = reg.load_example("boiler_ft")
    fsv.solve(fs)
    tokens.apply_preferences(theme="dark")
    tokens._PrefsBus.emit()
    destino = tmp_path / "fichas.pdf"
    dx.write_datasheets_pdf(str(destino), fs, fecha="25-07-2026")
    assert destino.stat().st_size > 1000


def test_fichas_usan_la_tipografia_del_proyecto():
    """El plano sale en pfd_fonts; el legajo salía en Helvetica. Dos
    documentos del mismo trabajo no pueden hablar dos tipografías."""
    src = open(os.path.join(_PARENT, "datasheet_export.py"),
               encoding="utf-8").read()
    assert "pfd_fonts" in src
    assert 'QFont("Helvetica"' not in src


# ─────────────── 2. Hallazgos nuevos de este escaneo ───────────────

def _rect_leyenda(w):
    """Rect de la leyenda del Marco PFD en coordenadas de viewport."""
    from PySide6.QtCore import QRect, QRectF
    pf = w.scene.paper_frame
    if pf is None:
        return None
    W, H = pf.PAPER_W, pf.PAPER_H
    bw, bx = 460, W - 500
    bh = 26 if getattr(pf, "_legend_collapsed", False) else 162
    by = H - 160 - bh - 6
    esc = QRectF(pf.x() + bx, pf.y() + by, bw, bh)
    return QRect(w.view.mapFromScene(esc.topLeft()),
                 w.view.mapFromScene(esc.bottomRight())).normalized()


@pytest.mark.parametrize("size", [(1280, 800), (1400, 900), (1920, 1080)])
def test_zoom_no_pisa_la_leyenda(ventana, app, size):
    """HALLAZGO: el control de zoom se anclaba abajo-derecha, que es
    donde el plano pone leyenda + cuadro de título + revisiones.  A
    1280×800 el widget caía ENTERO sobre la leyenda (157×34 px de
    solape).  No se veía en pantallas grandes."""
    ventana.resize(*size)
    ventana.show()
    for _ in range(4):
        app.processEvents()
    leyenda = _rect_leyenda(ventana)
    assert leyenda is not None, "el ejemplo debería traer Marco PFD"
    zoom = ventana._zoom_widget.geometry()
    solape = leyenda.intersected(zoom)
    assert not leyenda.intersects(zoom), (
        f"a {size[0]}×{size[1]} el zoom pisa la leyenda "
        f"({solape.width()}×{solape.height()} px)")


def test_zoom_no_pisa_la_paleta(ventana, app):
    """La corrección movió el zoom a la columna izquierda, donde vive la
    paleta: el arreglo no puede crear la colisión que vino a matar."""
    ventana.resize(1280, 800)
    ventana.show()
    for _ in range(4):
        app.processEvents()
    assert not ventana._palette_widget.geometry().intersects(
        ventana._zoom_widget.geometry())


def test_duty_badge_lleva_pill(ventana):
    """HALLAZGO: el badge «↑Q +6.00 MW» se ancla en (W+6, H/2) — por
    donde SALE la corriente del puerto derecho — y se dibujaba sin fondo,
    así que el trazo cruzaba las letras y el valor quedaba tachado por su
    propia corriente."""
    con_duty = [it for it in ventana.scene.block_items.values()
                if abs(getattr(it.model, "duty", 0.0) or 0.0) >= 0.5]
    assert con_duty, "el ejemplo debería traer un bloque con duty"
    for it in con_duty:
        bg = getattr(it, "duty_badge_bg", None)
        assert bg is not None, f"{it.model.name}: badge sin pill"
        assert bg.isVisible(), f"{it.model.name}: pill oculto con duty≠0"
        # El pill tiene que cubrir el texto, no ser un rect decorativo.
        texto = it.duty_badge.boundingRect().translated(it.duty_badge.pos())
        assert bg.rect().width() >= texto.width(), it.model.name
        assert bg.zValue() < it.duty_badge.zValue(), \
            f"{it.model.name}: el pill tapa su propio texto"


def test_duty_badge_sin_duty_no_deja_pill_huerfano(ventana):
    """Un bloque sin duty no puede dejar un rectángulo flotando."""
    for it in ventana.scene.block_items.values():
        if abs(getattr(it.model, "duty", 0.0) or 0.0) < 0.5:
            bg = getattr(it, "duty_badge_bg", None)
            if bg is not None:
                assert not bg.isVisible(), it.model.name
