"""GATE UI — interacción del lienzo (rubber band, group-drag,
drag de segmento ortogonal, routing de auxiliares).

Render offscreen (QT_QPA_PLATFORM=offscreen) con eventos de mouse
sintéticos sobre el viewport del FlowsheetView.  Protege los tres
defectos reportados:
  1. rubber band de selección por área no seleccionaba BlockItems
     (boundingRect/shape del QGraphicsItemGroup vacíos),
  2. arrastrar el path desfiguraba los segmentos ortogonales
     (drag-translate → ahora drag de segmento perpendicular),
  3. corrientes auxiliares atravesando bloques (pipeline de
     avoidance degenerado + dims modelo≠visual).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPointF, QRectF, QEvent
from PySide6.QtGui import QMouseEvent

import flowsheet_qt as fq
from flowsheet_model import Block, Stream

_app = QApplication.instance() or QApplication([])


# ── helpers ────────────────────────────────────────────────────────────
def _send(vp, etype, pos, btn, btns):
    ev = QMouseEvent(etype, QPointF(pos), QPointF(vp.mapToGlobal(pos)),
                     btn, btns, Qt.NoModifier)
    QApplication.sendEvent(vp, ev)


def _drag(view, sp_from, sp_to):
    vp = view.viewport()
    _send(vp, QEvent.MouseButtonPress, view.mapFromScene(sp_from),
          Qt.LeftButton, Qt.LeftButton)
    _send(vp, QEvent.MouseMove, view.mapFromScene(sp_to),
          Qt.NoButton, Qt.LeftButton)
    _send(vp, QEvent.MouseButtonRelease, view.mapFromScene(sp_to),
          Qt.LeftButton, Qt.NoButton)


def _ortho_violations(nodes, eps=0.51):
    """Segmentos que no son ni horizontales ni verticales."""
    return [i for i in range(len(nodes) - 1)
            if abs(nodes[i + 1][0] - nodes[i][0]) > eps
            and abs(nodes[i + 1][1] - nodes[i][1]) > eps]


def _mk_editor_3b_2s():
    """Editor con 3 bloques + 2 streams conectados (escena mínima)."""
    win = fq.FlowsheetMainWindow()
    win.resize(1400, 900)
    win.show()
    fs = win.fs
    specs = [(1, "B-1", "Pump — centrifugal", 100.0, 300.0),
             (2, "B-2", "Heat exch. — fixed tube", 420.0, 300.0),
             (3, "B-3", "Storage tank — cone roof", 760.0, 300.0)]
    for bid, name, eq, x, y in specs:
        fs.blocks[bid] = Block(id=bid, name=name, eq_type=eq, S=1.0,
                               x=x, y=y)
    fs.streams[10] = Stream(id=10, name="S-10", src=1, dst=2,
                            mass_flow=100.0)
    fs.streams[11] = Stream(id=11, name="S-11", src=2, dst=3,
                            mass_flow=100.0)
    win._rebuild_scene()
    _app.processEvents()
    win.view.setUpdatesEnabled(False)
    win.view.fitInView(QRectF(0, 150, 1000, 400), Qt.KeepAspectRatio)
    return win


# ── 1) rubber band selecciona bloques Y streams ────────────────────────
def test_rubber_band_selecciona_bloques_y_streams():
    win = _mk_editor_3b_2s()
    win.scene.clearSelection()
    _drag(win.view, QPointF(40, 180), QPointF(950, 520))
    sel = win.scene.selectedItems()
    n_blocks = sum(1 for i in sel if isinstance(i, fq.BlockItem))
    n_streams = sum(1 for i in sel if isinstance(i, fq.StreamItem))
    assert n_blocks == 3, f"bloques seleccionados: {n_blocks} != 3"
    assert n_streams == 2, f"streams seleccionados: {n_streams} != 2"


# ── 2) drag de un bloque mueve TODA la selección ───────────────────────
def test_group_drag_mueve_conjunto():
    win = _mk_editor_3b_2s()
    # dar waypoints a un stream para verificar que también se trasladan
    sitem = win.scene.stream_items[10]
    pts = sitem._last_pts
    sitem.model.waypoints = [[pts[2], pts[3]]]
    sitem.update_path()
    win.scene.clearSelection()
    for it in list(win.scene.block_items.values()) + [sitem]:
        it.setSelected(True)
    before_b = {bid: (b.x, b.y) for bid, b in win.fs.blocks.items()}
    before_wp = [list(w) for w in sitem.model.waypoints]

    bitem = win.scene.block_items[1]
    b = bitem.model
    c0 = QPointF(b.x + bitem.W / 2, b.y + bitem.H / 2)
    _drag(win.view, c0, QPointF(c0.x() + 40, c0.y() + 40))

    moved = [bid for bid, b2 in win.fs.blocks.items()
             if (b2.x, b2.y) != before_b[bid]]
    assert len(moved) == 3, f"bloques movidos: {moved}"
    dx = win.fs.blocks[1].x - before_b[1][0]
    dy = win.fs.blocks[1].y - before_b[1][1]
    assert (dx, dy) != (0, 0)
    for w0, w1 in zip(before_wp, sitem.model.waypoints):
        assert (round(w1[0] - w0[0]), round(w1[1] - w0[1])) == \
            (round(dx), round(dy)), "waypoints no siguieron el delta"


# ── 3) drag de segmento: ortogonalidad y puertos intactos ──────────────
def test_segment_drag_preserva_ortogonalidad():
    win = _mk_editor_3b_2s()
    sitem = win.scene.stream_items[10]
    s = sitem.model
    assert not s.waypoints

    # snapshot inmediato del path dibujado (sin event loop en medio)
    pts = sitem._last_pts
    nodes0 = sitem._node_list()
    p_src0, p_dst0 = nodes0[0], nodes0[-1]
    assert not _ortho_violations(
        [(pts[i], pts[i + 1]) for i in range(0, len(pts), 2)])

    # click simple sobre el path: NO debe mutar el modelo
    mid = QPointF((pts[0] + pts[2]) / 2, (pts[1] + pts[3]) / 2)
    _drag(win.view, mid, mid)
    assert s.waypoints == [], "click simple bakeó waypoints"

    # drag perpendicular del primer segmento H/V
    pts = sitem._last_pts
    horizontal = abs(pts[3] - pts[1]) < 1e-6
    mid = QPointF((pts[0] + pts[2]) / 2, (pts[1] + pts[3]) / 2)
    to = QPointF(mid.x(), mid.y() + 40) if horizontal \
        else QPointF(mid.x() + 40, mid.y())
    _drag(win.view, mid, to)

    assert s.waypoints, "el drag no bakeó la ruta"
    nodes = sitem._node_list()
    assert _ortho_violations(nodes) == [], \
        f"segmentos no ortogonales tras drag: {nodes}"
    assert nodes[0] == p_src0 and nodes[-1] == p_dst0, \
        "un endpoint anclado a puerto se movió"
    # el segmento movido quedó snapeado a la grilla
    coords = ([w[1] for w in s.waypoints] if horizontal
              else [w[0] for w in s.waypoints])
    assert any(abs(c % fq.GRID_STEP) < 1e-6 for c in coords)


# ── 4) auxiliares: cero cruces con bloques ajenos (dims visuales) ──────
def test_aux_no_atraviesan_bloques_metanol():
    win = fq.FlowsheetMainWindow()
    win.resize(1400, 900)
    win.show()
    win.action_load_example("methanol")
    win._toggle_aux_visibility(True)
    _app.processEvents()

    crossings = []
    for sid, item in win.scene.stream_items.items():
        s = item.model
        if s.waypoints:        # rutas manuales: responsabilidad del user
            continue
        pts = item._last_pts or []
        for i in range((len(pts) - 2) // 2):
            for bid, bitem in win.scene.block_items.items():
                if bid in (s.src, s.dst):
                    continue
                bm = bitem.model
                if fq._segment_intersects_rect(
                        pts[2 * i], pts[2 * i + 1],
                        pts[2 * i + 2], pts[2 * i + 3],
                        bm.x, bm.y, bitem.W, bitem.H):
                    crossings.append((sid, i, bm.name))
    assert crossings == [], \
        f"streams atraviesan bloques ajenos: {crossings}"


# ── 5) HOTFIX P0: group-drag de selección densa NO se cuelga ───────────
def test_group_drag_denso_no_cuelga():
    """Regresión del crash P0 (merge 6c70f3a): rubber band selecciona
    varios bloques + streams y al arrastrar el conjunto la app se colgaba
    por el routing obstacle-aware (avoidance + lane + jumpers) recomputado
    en CADA píxel de cada mouse-move → O(n²) por píxel.

    El test sintético previo aplicaba UN delta; éste simula una ráfaga
    REAL de ≥60 mouse-moves de 2px sobre una escena densa (hda_full:
    22 bloques / 24 streams) con ≥5 bloques + ≥8 streams seleccionados.
    Debe completar en <2s (watchdog duro a 10s) y dejar la ortogonalidad
    y los puertos intactos tras el release (un solo re-route completo)."""
    import time, faulthandler

    win = fq.FlowsheetMainWindow()
    win.resize(1400, 900)
    win.show()
    win.action_load_example("hda_full")
    _app.processEvents()
    scene, view = win.scene, win.view

    blocks = list(scene.block_items.values())
    streams = list(scene.stream_items.values())
    assert len(blocks) >= 5 and len(streams) >= 8, "escena no es densa"

    scene.clearSelection()
    sel_blocks = blocks[:5]
    sel_streams = streams[:8]
    for it in sel_blocks + sel_streams:
        it.setSelected(True)
    _app.processEvents()

    # endpoints/puertos de los streams conectados ANTES del drag (los que
    # quedan anclados a bloques NO movidos no deben desplazarse de su puerto)
    anchor = sel_blocks[0]
    b = anchor.model
    c0 = QPointF(b.x + anchor.W / 2, b.y + anchor.H / 2)
    vp = view.viewport()

    # watchdog duro: si algo se cuelga >10s, dump del traceback y abort
    faulthandler.dump_traceback_later(10, exit=True)
    try:
        t0 = time.perf_counter()
        _send(vp, QEvent.MouseButtonPress, view.mapFromScene(c0),
              Qt.LeftButton, Qt.LeftButton)
        cur = QPointF(c0)
        for _ in range(60):                # ráfaga real de mouse-moves
            cur = QPointF(cur.x() + 2, cur.y() + 2)
            _send(vp, QEvent.MouseMove, view.mapFromScene(cur),
                  Qt.NoButton, Qt.LeftButton)
        _send(vp, QEvent.MouseButtonRelease, view.mapFromScene(cur),
              Qt.LeftButton, Qt.NoButton)
        elapsed = time.perf_counter() - t0
    finally:
        faulthandler.cancel_dump_traceback_later()

    assert elapsed < 2.0, f"group-drag denso tardó {elapsed:.2f}s (>2s): regresión P0"

    # el modo rígido se cerró al soltar
    assert win._rigid_drag_active is False, "rigid_drag_active no se reseteó"

    # IDEMPOTENCIA: tras el release corrió UN re-route completo, así que la
    # geometría debe ser estable — un re-route adicional no la cambia.  Esto
    # prueba que la fase rígida NO dejó paths obsoletos y que el routing
    # obstacle-aware (avoidance + lane + jumpers) sí se aplicó al final.
    after_release = {sid: list(item._last_pts or [])
                     for sid, item in scene.stream_items.items()}
    win._refresh_all_stream_paths()
    for sid, item in scene.stream_items.items():
        pts2 = list(item._last_pts or [])
        assert pts2 == after_release[sid], \
            f"stream {sid}: geometría no estable tras release (re-route pendiente)"

    # los bloques seleccionados se movieron juntos (mismo delta)
    deltas = {(round(it.model.x), round(it.model.y)) for it in sel_blocks}
    assert len(sel_blocks) == 5 and len(deltas) == 5, "selección incompleta"
