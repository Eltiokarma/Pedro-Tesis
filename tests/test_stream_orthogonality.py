"""GATE UI — regla ortogonal de los streams del canvas.

Todo stream FULL-CONECTADO (src y dst en bloques) se dibuja solo con
segmentos horizontales o verticales.  Regresión: los pases de routing
(_avoid_obstacles / _apply_lane_offset) movían un solo extremo de un
segmento y dejaban tramos diagonales, y _compute_polyline tenía atajos
"casi alineado → línea directa" con tolerancia <2px levemente
inclinados.  La red de seguridad _orthogonalize garantiza la regla; este
gate la protege sobre los ejemplos que históricamente la rompían
(industrial ×4, hda ×3, hda_full ×2) más un set de control.

Los streams flotantes (un endpoint libre) quedan exentos: dibujan la
recta directa a propósito.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

import examples_registry as reg
import flowsheet_qt as fq

_app = QApplication.instance() or QApplication([])

CLAVES = ["industrial", "hda", "hda_full", "methanol", "ammonia", "cdu"]


def _diagonales(clave):
    w = fq.FlowsheetMainWindow()
    w.resize(1600, 1000)
    w.show()
    _app.processEvents()
    try:
        w.fs = reg.load_example(clave)
        w._rebuild_scene()
        _app.processEvents()
        bad = []
        for sid, item in w.stream_items_iter():
            s = item.model
            if s.src == -1 or s.dst == -1:
                continue                      # flotante: recta directa ok
            flat = getattr(item, "_last_pts", None) or []
            pts = [(flat[i], flat[i + 1]) for i in range(0, len(flat), 2)]
            for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                if abs(ax - bx) > 0.5 and abs(ay - by) > 0.5:
                    bad.append((sid, s.name, (ax, ay), (bx, by)))
        return bad
    finally:
        w.close()


@pytest.mark.parametrize("clave", CLAVES)
def test_streams_ortogonales(clave):
    bad = _diagonales(clave)
    assert not bad, (
        f"{clave}: {len(bad)} segmento(s) diagonales en streams "
        f"full-conectados: {bad[:5]}")


def test_orthogonalize_inserta_codos():
    """Unidad: la red de seguridad convierte un tramo diagonal en un codo
    que continúa la dirección del segmento previo."""
    # previo horizontal → codo H→V
    pts = fq._orthogonalize([0, 0, 10, 0, 20, 8])
    pares = [(pts[i], pts[i + 1]) for i in range(0, len(pts), 2)]
    for a, b in zip(pares, pares[1:]):
        assert abs(a[0] - b[0]) <= 0.5 or abs(a[1] - b[1]) <= 0.5
    assert pares[-1] == (20, 8)
    # previo vertical → codo V→H
    pts = fq._orthogonalize([0, 0, 0, 10, 8, 20])
    pares = [(pts[i], pts[i + 1]) for i in range(0, len(pts), 2)]
    for a, b in zip(pares, pares[1:]):
        assert abs(a[0] - b[0]) <= 0.5 or abs(a[1] - b[1]) <= 0.5
    assert pares[-1] == (8, 20)
