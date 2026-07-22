"""Pendiente de talara — splitters FCC redistribuían flujos al insertar
un bloque pass-through.

Causa raíz: una edición que recrea UNA salida del splitter (insertar un
day-tank, un HX, un mixer aguas abajo) produce un stream nuevo SIN
split_fraction. La regla vieja era binaria — "TODAS keyed o posicional"
— así que el splitter entero caía al reparto posicional y las fracciones
rotaban entre salidas (el corte de nafta recibía la fracción del LCO...).

Fix: effective_split_fractions es la fuente ÚNICA (solve_splitters, la
iteración de masa y el audit W-SPLIT-LOCK la llaman) y soporta keyed
PARCIAL: las salidas keyed conservan su fracción y las nuevas heredan el
remanente 1−Σkeyed. Además _insert_mixer_upstream copia split_fraction
al stream de reemplazo (la inserción queda 100% keyed).
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from examples_registry import load_example
from flowsheet_model import Block, Stream
import flowsheet_solver as fsv


FCC_DESIGN = {          # data/examples/talara.json — R-FCC, 6 cortes
    "C9-nafta-FCC": 0.48,
    "C10-LCO": 0.14,
    "C11-GLP-FCC": 0.18,
    "C11b-gas-seco": 0.03,
    "C11c-slurry": 0.07,
    "C11d-coque-FCC": 0.10,
}


def _fcc(fs):
    return next(b for b in fs.blocks.values() if b.name == "R-FCC")


def _insert_passthrough_on(fs, stream_name):
    """Simula la edición de la UI: reemplaza el stream nombrado por
    (splitter → HX nuevo) + (HX nuevo → dst original). El stream nuevo
    NO trae split_fraction — exactamente lo que produce una inserción
    que no copia el campo."""
    old = next(s for s in fs.streams.values() if s.name == stream_name)
    hx_id = fs.new_id()
    fs.blocks[hx_id] = Block(id=hx_id, name="E-NEW", S=10.0,
                             eq_type="Heat exch. — fixed tube",
                             x=old.src, y=0)
    sid1 = fs.new_id()
    fs.streams[sid1] = Stream(
        id=sid1, name=f"{stream_name}-a", src=old.src, dst=hx_id,
        mass_flow=0.0, phase=old.phase, role=old.role,
        composition=dict(old.composition or {}),
        main_component=old.main_component)
    sid2 = fs.new_id()
    fs.streams[sid2] = Stream(
        id=sid2, name=f"{stream_name}-b", src=hx_id, dst=old.dst,
        mass_flow=0.0, phase=old.phase, role=old.role,
        composition=dict(old.composition or {}),
        main_component=old.main_component)
    del fs.streams[old.id]
    return sid1


def test_talara_baseline_fcc_reparte_por_diseno():
    fs = load_example("talara")
    fsv.solve(fs)
    fcc = _fcc(fs)
    outs = {s.name: s for s in fs.streams.values() if s.src == fcc.id}
    sum_in = sum(s.mass_flow for s in fs.streams.values()
                 if s.dst == fcc.id)
    assert sum_in > 0
    for name, frac in FCC_DESIGN.items():
        got = outs[name].mass_flow / sum_in
        assert abs(got - frac) < 1e-6, f"{name}: {got:.4f} ≠ {frac}"


def test_insertar_passthrough_no_redistribuye_los_otros_cortes():
    """El escenario del pendiente: pass-through en C10-LCO. Los OTROS
    cinco cortes deben conservar su fracción de diseño exacta, y el
    stream nuevo hereda el remanente (la fracción del LCO)."""
    fs = load_example("talara")
    new_sid = _insert_passthrough_on(fs, "C10-LCO")
    fsv.solve(fs)
    fcc = _fcc(fs)
    outs = {s.name: s for s in fs.streams.values() if s.src == fcc.id}
    sum_in = sum(s.mass_flow for s in fs.streams.values()
                 if s.dst == fcc.id)
    assert sum_in > 0
    for name, frac in FCC_DESIGN.items():
        if name == "C10-LCO":
            continue
        got = outs[name].mass_flow / sum_in
        assert abs(got - frac) < 1e-6, (
            f"{name} redistribuido: {got:.4f} ≠ diseño {frac}")
    # El reemplazo hereda el remanente 1−Σkeyed = 0.14 del LCO
    got_new = fs.streams[new_sid].mass_flow / sum_in
    assert abs(got_new - 0.14) < 1e-6, f"pass-through: {got_new:.4f} ≠ 0.14"


def test_fuente_unica_pairs_parcial_keyed():
    """effective_split_fractions con keyed parcial: keyed conservan su
    valor, las nuevas reparten el remanente en partes iguales."""
    fs = load_example("talara")
    fcc = _fcc(fs)
    # Quitar el split_fraction a DOS cortes (0.14 + 0.03 = 0.17)
    for s in fs.streams.values():
        if s.src == fcc.id and s.name in ("C10-LCO", "C11b-gas-seco"):
            s.split_fraction = None
    pairs = fsv.effective_split_fractions(fs, fcc)
    assert pairs is not None
    by_name = {s.name: f for s, f in pairs}
    for name, frac in FCC_DESIGN.items():
        if name in ("C10-LCO", "C11b-gas-seco"):
            assert abs(by_name[name] - 0.17 / 2) < 1e-9
        else:
            assert abs(by_name[name] - frac) < 1e-9


def test_insert_mixer_upstream_copia_split_fraction():
    """La ruta de inserción de la UI copia el campo al reemplazo: el
    splitter queda 100% keyed (ni siquiera se necesita el remanente)."""
    import flowsheet_qt as fq
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    win = fq.FlowsheetMainWindow()
    try:
        fs = win.fs
        # Splitter 60/40 keyed → reactor; fuente nueva para el mixer
        sp = Block(id=fs.new_id(), name="SP-1", eq_type="Splitter — flow divider",
                   S=1.0, splitter_active=True, x=0, y=0)
        fs.blocks[sp.id] = sp
        rx = Block(id=fs.new_id(), name="R-1", eq_type="Reactor — CSTR (agitado)",
                   S=1.0, x=200, y=0)
        fs.blocks[rx.id] = rx
        nuevo = Block(id=fs.new_id(), name="TK-1",
                      eq_type="Storage tank — cone roof", S=1.0, x=0, y=200)
        fs.blocks[nuevo.id] = nuevo
        s_main = Stream(id=fs.new_id(), name="S-main", src=sp.id, dst=rx.id,
                        mass_flow=0.0, dst_port="alimentacion",
                        split_fraction=0.6)
        fs.streams[s_main.id] = s_main
        s_other = Stream(id=fs.new_id(), name="S-other", src=sp.id, dst=0,
                         mass_flow=0.0, split_fraction=0.4)
        fs.streams[s_other.id] = s_other

        win._insert_mixer_upstream(nuevo.id, rx.id)

        sp_outs = [s for s in fs.streams.values() if s.src == sp.id]
        assert len(sp_outs) == 2
        reemplazo = next(s for s in sp_outs if s.name != "S-other")
        assert getattr(reemplazo, "split_fraction", None) == 0.6, (
            "la inserción no copió split_fraction al reemplazo")
    finally:
        win.close()
