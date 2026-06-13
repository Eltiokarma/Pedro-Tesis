"""PR-A2 — [W-PURGE-ABS]: purga absoluta lockeada dentro de un loop.

Detector advisory (canal awareness_warnings de PR-A) que marca el patrón
de subdeterminación que arregló PR-G1: un bloque NO-splitter en un loop de
reciclo de PROCESO aún no determinado por un splitter, con una salida
lockeada TERMINAL (purga) y una hermana que recircula.  No toca balance ni
overall_status; reusa la detección de SCC del solver.
"""
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import examples_registry as reg
import flowsheet_solver as fsv

_TAG = "[W-PURGE-ABS]"


def _purge_blocks(clave):
    fs = reg.load_example(clave)
    res = fsv.solve(fs)
    blocks = set()
    for w in res.awareness_warnings:
        if w.startswith(_TAG):
            m = re.match(r"\[W-PURGE-ABS\] ([^:]+):", w)
            if m:
                blocks.add(m.group(1))
    return fs, res, blocks


# ── DISPARA donde debe (purgas reales en loops subdeterminados) ─────────
def test_dispara_en_purgas_reales():
    # hda H2-purge, hda_full gas-purge (K-101), industrial blowdown
    casos = [("hda", "V-101"), ("hda_full", "K-101"), ("industrial", "V-301")]
    for clave, blk in casos:
        _, _, blocks = _purge_blocks(clave)
        assert blk in blocks, f"{clave}: esperaba [W-PURGE-ABS] en {blk}, got {blocks}"


# ── NO dispara donde el loop ya está determinado o es splitter ──────────
def test_no_dispara_haber_rec_post_g1():
    # V-102 es splitter (PR-G1) y el loop quedó DETERMINADO → ni V-102 ni
    # V-101 (separador de producto) deben disparar.
    _, _, blocks = _purge_blocks("haber_rec")
    assert "V-102" not in blocks
    assert "V-101" not in blocks
    assert blocks == set(), f"haber_rec no debería disparar nada, got {blocks}"


def test_no_dispara_industrial_splitter_y_loop_determinado():
    _, _, blocks = _purge_blocks("industrial")
    # V-203 usa splitter_active; V-201 está en el mismo loop ya determinado.
    assert "V-203" not in blocks
    assert "V-201" not in blocks


# ── advisory: no altera overall_status; va al canal awareness ───────────
def test_es_advisory_no_altera_estado():
    import json
    golden_path = os.path.join(os.path.dirname(__file__), "..", "data",
                               "examples", "_golden.json")
    with open(golden_path, encoding="utf-8") as f:
        golden = json.load(f)
    any_fired = False
    for clave, g in golden.items():
        fs = reg.load_example(clave)
        res = fsv.solve(fs)
        if any(w.startswith(_TAG) for w in res.awareness_warnings):
            any_fired = True
        assert res.overall_status == g["overall_status"], (
            f"{clave}: overall_status cambió por [W-PURGE-ABS]")
    assert any_fired, "el detector no disparó en ningún ejemplo (¿roto?)"


# ── purgas TERMINALES (fuera de loop) NO disparan ───────────────────────
def test_purga_terminal_no_dispara():
    # urea V-101 (S-purga) y acetic V-101 (S-purga): purgas con flujo
    # absoluto pero el bloque NO está en un loop de reciclo → spec legítima.
    for clave, blk in [("urea", "V-101"), ("acetic", "V-101")]:
        _, _, blocks = _purge_blocks(clave)
        assert blk not in blocks, \
            f"{clave}/{blk}: purga terminal no debería disparar"
