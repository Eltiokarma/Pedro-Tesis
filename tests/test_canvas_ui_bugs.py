"""GATE UI — defectos reportados sobre el lienzo (2026-07).

Cubre cuatro fallas de UI, cada una con su test de regresión:

  1. CRASH P0 — arrastrar una selección hecha con rubber band cerraba el
     programa (SIGSEGV).  Qt itera snapshots de punteros crudos mientras
     despacha la selección y el group-drag; destruir handles ahí (el
     _rebuild_handles de cada stream que entra a la selección) dejaba
     punteros colgando.  Ahora el disposal es diferido y los handles no
     son seleccionables.
  2. LEYENDA — las corrientes auxiliares (clusters de servicio, que se
     apilan debajo de su intercambiador) terminaban dibujadas encima de la
     leyenda y del cuadro de título.  La hoja ahora reserva esa esquina.
  3. CENTRADO — los ejercicios cortos no salían centrados en el marco (y
     varios traen TODOS los bloques en (0,0), sin layout).
  4. ENTRADA/SALIDA — las corrientes de límite de batería (src<=0 o
     dst<=0) existen en el modelo y el solver las usa, pero no se
     dibujaba nada: el diagrama parecía no tener alimentaciones ni
     productos.  Ahora se dibujan con muñón + banderola rotulada.

USO:
    QT_QPA_PLATFORM=offscreen python -m pytest tests/test_canvas_ui_bugs.py -q
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF, QRectF, QEvent
from PySide6.QtGui import QMouseEvent
import shiboken6

import flowsheet_qt as fq

_app = QApplication.instance() or QApplication([])


# ── helpers ────────────────────────────────────────────────────────────
def _send(vp, etype, pos, btn, btns):
    ev = QMouseEvent(etype, QPointF(pos), QPointF(vp.mapToGlobal(pos)),
                     btn, btns, Qt.NoModifier)
    QApplication.sendEvent(vp, ev)


def _win(example, aux=True):
    """Ventana nueva con un ejemplo cargado (una por test: cargar dos
    ejemplos en la misma ventana abre un QMessageBox modal)."""
    win = fq.FlowsheetMainWindow()
    win.resize(1400, 900)
    win.show()
    win.action_load_example(example)
    win._toggle_aux_visibility(aux)
    _app.processEvents()
    return win


def _fit(win):
    view, scene = win.view, win.scene
    view.fitInView(scene.itemsBoundingRect().adjusted(-60, -60, 60, 60),
                   Qt.KeepAspectRatio)
    _app.processEvents()


def _content_rect(scene):
    x0, y0, x1, y1 = scene._content_bbox()
    return QRectF(x0, y0, x1 - x0, y1 - y0)


# ── 1) el rubber band oscilante + group-drag no mata el proceso ─────────
def test_rubber_band_oscilante_no_crashea():
    """Regresión del SIGSEGV: la banda de selección crecía y se encogía
    (movimiento real del mouse) sobre una escena densa con auxiliares.
    Cada stream que entraba a la selección reconstruía sus handles y
    destruía los viejos EN MEDIO de la iteración de Qt.

    El test hace 6 ciclos de banda oscilante + un arrastre del conjunto.
    Antes moría con SIGSEGV; ahora completa y deja la selección viva."""
    win = _win("hda_full")
    _fit(win)
    scene, view = win.scene, win.view
    vp = view.viewport()
    W, H = vp.width(), vp.height()

    _send(vp, QEvent.MouseButtonPress, QPointF(4, 4),
          Qt.LeftButton, Qt.LeftButton)
    for c in range(6):
        seq = list(range(1, 21))
        if c < 5:
            seq += list(range(19, 0, -1))       # la banda se encoge
        for i in seq:
            _send(vp, QEvent.MouseMove,
                  QPointF(4 + (W - 8) * i / 20.0, 4 + (H - 8) * i / 20.0),
                  Qt.NoButton, Qt.LeftButton)
    _send(vp, QEvent.MouseButtonRelease, QPointF(W - 4, H - 4),
          Qt.LeftButton, Qt.NoButton)
    _app.processEvents()

    sel = scene.selectedItems()
    assert any(isinstance(i, fq.BlockItem) for i in sel), "banda sin bloques"
    assert any(isinstance(i, fq.StreamItem) for i in sel), "banda sin streams"
    # arrastrar el conjunto tampoco debe morir
    anchor = next(i for i in sel if isinstance(i, fq.BlockItem))
    b = anchor.model
    cur = QPointF(b.x + anchor.W / 2, b.y + anchor.H / 2)
    _send(vp, QEvent.MouseButtonPress, view.mapFromScene(cur),
          Qt.LeftButton, Qt.LeftButton)
    for _ in range(40):
        cur = QPointF(cur.x() + 3, cur.y() + 3)
        _send(vp, QEvent.MouseMove, view.mapFromScene(cur),
              Qt.NoButton, Qt.LeftButton)
    _send(vp, QEvent.MouseButtonRelease, view.mapFromScene(cur),
          Qt.LeftButton, Qt.NoButton)
    _app.processEvents()
    assert win._rigid_drag_active is False


def test_seleccion_no_destruye_items_en_caliente():
    """Invariante que sostiene el fix: ningún item vivo en la escena puede
    destruirse DURANTE el despacho de un cambio de selección."""
    win = _win("methanol")
    scene = win.scene
    antes = list(scene.items())
    for it in list(scene.stream_items.values()):
        it.setSelected(True)
    for it in list(scene.stream_items.values()):
        it.setSelected(False)
    muertos = [it for it in antes if not shiboken6.Shiboken.isValid(it)]
    assert muertos == [], f"{len(muertos)} items destruidos en caliente"


def test_handles_no_entran_a_la_seleccion():
    """Los handles son agarres, no elementos del diagrama: el rubber band
    no debe seleccionarlos (si no, el group-drag los arrastra y termina
    desconectando endpoints)."""
    win = _win("methanol")
    _fit(win)
    view, scene = win.view, win.scene
    vp = view.viewport()
    _send(vp, QEvent.MouseButtonPress, QPointF(2, 2),
          Qt.LeftButton, Qt.LeftButton)
    _send(vp, QEvent.MouseMove, QPointF(vp.width() - 2, vp.height() - 2),
          Qt.NoButton, Qt.LeftButton)
    _send(vp, QEvent.MouseButtonRelease,
          QPointF(vp.width() - 2, vp.height() - 2),
          Qt.LeftButton, Qt.NoButton)
    _app.processEvents()
    handles = [i for i in scene.selectedItems()
               if isinstance(i, (fq._EndpointHandle, fq._StreamHandle,
                                 fq._GhostStreamHandle))]
    assert handles == [], f"{len(handles)} handles en la selección"


def test_group_drag_no_desconecta_corrientes():
    """Arrastrar un grupo de equipos no debe desconectar ninguna corriente
    (era el efecto de que los endpoint handles viajaran con la selección)."""
    win = _win("hda_full")
    _fit(win)
    scene, view = win.scene, win.view
    conectadas = {sid: (s.src, s.dst) for sid, s in win.fs.streams.items()}
    scene.clearSelection()
    for it in list(scene.block_items.values())[:6]:
        it.setSelected(True)
    for it in list(scene.stream_items.values())[:8]:
        it.setSelected(True)
    _app.processEvents()
    anchor = next(i for i in scene.selectedItems()
                  if isinstance(i, fq.BlockItem))
    b = anchor.model
    cur = QPointF(b.x + anchor.W / 2, b.y + anchor.H / 2)
    vp = view.viewport()
    _send(vp, QEvent.MouseButtonPress, view.mapFromScene(cur),
          Qt.LeftButton, Qt.LeftButton)
    for _ in range(50):
        cur = QPointF(cur.x() + 4, cur.y() + 4)
        _send(vp, QEvent.MouseMove, view.mapFromScene(cur),
              Qt.NoButton, Qt.LeftButton)
    _send(vp, QEvent.MouseButtonRelease, view.mapFromScene(cur),
          Qt.LeftButton, Qt.NoButton)
    _app.processEvents()
    ahora = {sid: (s.src, s.dst) for sid, s in win.fs.streams.items()}
    assert ahora == conectadas, "el group-drag cambió conexiones"


# ── 2) la leyenda no se superpone con el diagrama ───────────────────────
def test_auxiliares_no_chocan_con_la_leyenda():
    """Los clusters de servicio se apilan DEBAJO de su intercambiador, que
    es justo donde vive la leyenda: la hoja debe reservar esa esquina."""
    for key in ("distillation", "methanol", "cdu"):
        win = _win(key, aux=True)
        scene = win.scene
        doc = scene._doc_zone_rect()
        assert doc is not None
        for bid, item in scene.block_items.items():
            if not item.isVisible():
                continue
            b = item.model
            r = QRectF(b.x, b.y, item.W, item.H)
            assert not doc.intersects(r), \
                f"{key}: {b.name} cae sobre la leyenda"
        for sid, item in scene.stream_items.items():
            if not item.isVisible():
                continue
            pts = item._last_pts or []
            for i in range(0, len(pts) - 1, 2):
                assert not doc.contains(pts[i], pts[i + 1]), \
                    f"{key}: {item.model.name} pasa por la leyenda"
        assert scene.paper_fits_content()
        win.close()


def test_chevron_de_la_leyenda_sigue_clickeable():
    """El marco ya no vive en (0,0) — el hit-test del chevron mapea el
    click a coords del marco."""
    win = _win("methanol")
    scene = win.scene
    pf = scene.paper_frame
    assert pf.legend_chevron_rect is not None
    p_scene = pf.mapToScene(pf.legend_chevron_rect.center())
    antes = bool(getattr(scene, "_legend_collapsed", False))
    from PySide6.QtWidgets import QGraphicsSceneMouseEvent
    ev = QGraphicsSceneMouseEvent(QEvent.GraphicsSceneMousePress)
    ev.setScenePos(p_scene)
    ev.setButton(Qt.LeftButton)
    scene.mousePressEvent(ev)
    _app.processEvents()
    assert bool(getattr(scene, "_legend_collapsed", False)) is not antes, \
        "el click sobre el chevron no plegó la leyenda"


# ── 3) centrado del diagrama en el marco ───────────────────────────────
def test_ejercicio_corto_queda_centrado():
    """Un ejemplo chico debe quedar centrado en el marco (antes aparecía
    apilado en el vértice superior izquierdo de una hoja 1600×960)."""
    for key in ("pfr", "blower", "letdown"):
        win = _win(key, aux=False)
        scene, pf = win.scene, win.scene.paper_frame
        c = _content_rect(scene).center()
        fcx = pf.x() + pf.PAPER_W / 2.0
        fcy = pf.y() + pf.PAPER_H / 2.0
        # tolerancia de media celda de grilla por el snap
        assert abs(c.x() - fcx) <= 3 * fq.GRID_STEP, \
            f"{key}: descentrado en X ({c.x() - fcx:+.0f} px)"
        assert abs(c.y() - fcy) <= 3 * fq.GRID_STEP, \
            f"{key}: descentrado en Y ({c.y() - fcy:+.0f} px)"
        win.close()


def test_ejemplos_sin_coordenadas_se_ordenan():
    """Varios ejemplos cortos traen TODOS los bloques en (0,0): sin layout
    no hay nada que centrar.  Deben quedar repartidos y sin superponerse."""
    for key in ("pfr", "nested_recycle", "parallel", "hen"):
        win = _win(key, aux=False)
        blocks = [b for b in win.fs.blocks.values()
                  if not getattr(b, "auto_aux", False)]
        pos = {(round(b.x), round(b.y)) for b in blocks}
        assert len(pos) == len(blocks), \
            f"{key}: bloques apilados en la misma posición"
        # y el diagrama no se desparrama (el layering acotado por #equipos)
        span_x = max(b.x for b in blocks) - min(b.x for b in blocks)
        assert span_x <= 400 * len(blocks), f"{key}: layout desparramado"
        win.close()


# ── 4) corrientes de entrada / salida visibles ─────────────────────────
def test_corrientes_de_entrada_y_salida_se_dibujan():
    """Toda corriente de límite de batería (src<=0 o dst<=0) se dibuja con
    su muñón y su banderola rotulada."""
    for key in ("methanol", "distillation", "hda_full", "industrial"):
        win = _win(key, aux=False)
        externas = [(sid, s) for sid, s in win.fs.streams.items()
                    if s.src <= 0 or s.dst <= 0]
        assert externas, f"{key}: el ejemplo no tiene corrientes externas"
        for sid, s in externas:
            item = win.scene.stream_items.get(sid)
            assert item is not None, f"{key}: {s.name} sin item"
            assert item._last_pts, f"{key}: {s.name} no se dibuja"
            assert item.offpage_tag.isVisible(), \
                f"{key}: {s.name} sin banderola de fuera de página"
            assert s.name in item.offpage_label.text(), \
                f"{key}: banderola de {s.name} sin rótulo"
        win.close()


def test_munon_de_frontera_es_ortogonal():
    """El muñón sale derecho del puerto (ortogonal), como toda corriente
    del plano."""
    win = _win("methanol", aux=False)
    for sid, s in win.fs.streams.items():
        if s.src > 0 and s.dst > 0:
            continue
        pts = win.scene.stream_items[sid]._last_pts or []
        for i in range(0, len(pts) - 2, 2):
            dx = abs(pts[i + 2] - pts[i])
            dy = abs(pts[i + 3] - pts[i + 1])
            assert dx < 0.6 or dy < 0.6, \
                f"{s.name}: tramo diagonal {dx:.1f}×{dy:.1f}"


def test_frontera_no_muestra_handle_de_flotante():
    """Una alimentación de fuera de página NO es una corriente flotante: no
    debe mostrar el anillo naranja de agarre sobre el puerto."""
    win = _win("methanol", aux=False)
    for sid, s in win.fs.streams.items():
        if s.src == -1 or s.dst == -1:
            continue
        if s.src > 0 and s.dst > 0:
            continue
        item = win.scene.stream_items[sid]
        assert not item.isSelected()
        assert item._handles == [], \
            f"{s.name}: handle de flotante en una corriente de frontera"


def test_auxiliares_ocultas_no_dejan_puntas_de_flecha():
    """Apagar «Mostrar corrientes auxiliares» debe esconder la corriente
    COMPLETA: trazo, punta de flecha, chevrons y banderola."""
    win = _win("distillation", aux=True)
    win._toggle_aux_visibility(False)
    _app.processEvents()
    for sid, item in win.scene.stream_items.items():
        if not getattr(item.model, "auto_aux", False):
            continue
        assert not item.isVisible()
        assert not item.arrow_head.isVisible(), \
            f"{item.model.name}: punta de flecha huérfana"
        assert all(not a.isVisible() for a in item.direction_arrows)
        assert not item.offpage_tag.isVisible()
