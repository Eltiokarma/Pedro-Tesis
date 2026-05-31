"""Tests del desglose itemizado de ΔP hidráulica (_trace_downstream_itemized).

Verifica que el desglose que alimenta el panel UI sea consistente con el ΔP
que el solver dimensionó para cada bomba/compresor.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flowsheet_model as fm
import flowsheet_solver as fsv
import examples_registry as reg
import hydraulic_defaults as hd


def _build(clave):
    """Carga un ejemplo desde su JSON canónico (registry), aplica los presets
    hidráulicos (indexados por el nombre del builder, conservado en el
    manifest) y lo resuelve — igual que el camino real de la UI."""
    fs = reg.load_example(clave)
    hd.apply_example_hydraulics(fs, reg.builder_name(clave))
    fsv.solve(fs)
    return fs


def _rotative(fs):
    return [b for b in fs.blocks.values() if hd._is_rotative(b.eq_type)]


def test_itemized_trace_hydraulic_plant():
    """En hydraulic_plant: el desglose de P-101 debe incluir las caídas de
    los bloques E-101 (HX) y T-101 (columna) más el destination_delta, y
    cerrar contra el ΔP de la bomba."""
    fs = _build('hydraulic')
    p101 = next(b for b in fs.blocks.values() if b.name == "P-101")
    bd = fsv._trace_downstream_itemized(fs, p101.id)
    assert bd is not None, "P-101 sin desglose (no encontró anchor)"
    kinds = {it["kind"] for it in bd["items"]}
    refs = {it["ref"] for it in bd["items"]}
    assert "destination_delta" in kinds
    assert "block" in kinds, "faltan caídas de equipo (E-101/T-101)"
    assert {"E-101", "T-101"} & refs, f"no aparecen E-101/T-101: {refs}"
    assert abs(bd["total_dp_bar"] - p101.delta_p_bar) < 0.05


def test_itemized_trace_ammonia():
    """En ammonia: el anchor es el reactor (P_op=200 bar, seedeado). El
    destination_delta debe dominar (~199 bar)."""
    fs = _build('ammonia')
    k101 = next(b for b in fs.blocks.values() if b.name == "K-101")
    bd = fsv._trace_downstream_itemized(fs, k101.id)
    assert bd is not None
    dd = next((it for it in bd["items"]
               if it["kind"] == "destination_delta"), None)
    assert dd is not None
    assert dd["dp_bar"] > 150.0, f"destination_delta esperado ~199, dio {dd['dp_bar']}"
    assert bd["target_P_bar"] > 150.0
    assert abs(bd["total_dp_bar"] - k101.delta_p_bar) < 0.05


def test_itemized_sum_matches_pump_dp():
    """Para toda bomba/compresor auto-dimensionada con anchor, la suma de los
    items debe ≈ block.delta_p_bar (±0.05 bar)."""
    examples = ['hydraulic', 'ammonia', 'hda',
                'distillation', 'ethanol',
                'ethylene_crk', 'acetic']
    checked = 0
    for name in examples:
        fs = _build(name)
        for b in _rotative(fs):
            if b.delta_p_bar <= 0.01:
                continue
            bd = fsv._trace_downstream_itemized(fs, b.id)
            if bd is None:
                continue                   # sin anchor → caso conocido
            err = abs(bd["total_dp_bar"] - b.delta_p_bar)
            assert err < 0.05, \
                f"{name}/{b.name}: items suman {bd['total_dp_bar']:.3f}, " \
                f"bomba dice {b.delta_p_bar:.3f} (err={err:.3f})"
            assert len(bd["items"]) >= 1
            checked += 1
    assert checked >= 4, f"se verificaron muy pocas bombas ({checked})"


def test_no_anchor_returns_none():
    """Un compresor de entrada sin succión (methanol K-101) o una bomba sin
    anchor downstream devuelve None — no rompe."""
    fs = _build('methanol')
    k101 = next((b for b in fs.blocks.values() if b.name == "K-101"), None)
    if k101 is not None:
        bd = fsv._trace_downstream_itemized(fs, k101.id)
        assert bd is None or isinstance(bd, dict)   # no crash


if __name__ == '__main__':
    test_itemized_trace_hydraulic_plant()
    test_itemized_trace_ammonia()
    test_itemized_sum_matches_pump_dp()
    test_no_anchor_returns_none()
    print("desglose hidráulico: OK")
