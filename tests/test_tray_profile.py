"""Tests del helper tray_profile.build_stage_profile.

Verifica el contrato único de salida desde DOS fuentes (Wang-Henke real con
mock + McCabe-Thiele real) y la degradación elegante para azeótropos.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flowsheet_model as fm
import flowsheet_solver as fsv
import examples_registry as reg
import mccabe_thiele as mt
import tray_profile as tp


def _build(clave):
    """Carga un ejemplo desde su JSON canónico (registry) y lo resuelve."""
    fs = reg.load_example(clave)
    fsv.solve(fs)
    return fs


def _column(fs):
    return next(b for b in fs.blocks.values()
                if getattr(b, "column_active", False))


def test_mccabe_path_top_to_bottom_monotonic():
    """En distillation (B/T) el perfil va top→bot: x_LK decrece y T crece
    de forma monótona (binario casi ideal)."""
    fs = _build('distillation')
    p = tp.build_stage_profile(_column(fs), fs)
    assert p is not None
    assert p["source"] == "mccabe"
    assert "McCabe-Thiele" in p["badge"]
    stages = p["stages"]
    assert len(stages) >= 4
    xs = [s["x_LK"] for s in stages]
    Ts = [s["T_C"] for s in stages]
    # monotonía top→bot
    assert all(xs[i] >= xs[i + 1] - 1e-6 for i in range(len(xs) - 1)), xs
    assert all(Ts[i] <= Ts[i + 1] + 0.2 for i in range(len(Ts) - 1)), Ts
    # extremos físicamente razonables: benceno (bp 80°C) arriba, tolueno (110.6°C) abajo
    assert 75.0 < Ts[0] < 90.0
    assert 100.0 < Ts[-1] < 115.0
    assert xs[0] >= 0.90
    assert xs[-1] <= 0.10


def test_n_feed_in_range_and_LK_HK_propagated():
    fs = _build('distillation')
    b = _column(fs)
    p = tp.build_stage_profile(b, fs)
    assert 1 <= p["n_feed"] <= p["n_stages"]
    assert p["LK"] == b.column_LK
    assert p["HK"] == b.column_HK


def test_n_matches_mccabe_design_golden():
    """Golden: el N del perfil debe coincidir EXACTO con N_stages que
    devuelve mccabe_thiele.design (no se inventa etapas extra)."""
    fs = _build('distillation')
    b = _column(fs)
    d = mt.design_from_block(b, fs)
    p = tp.build_stage_profile(b, fs)
    assert p["n_stages"] == d["N_stages"]
    assert p["n_feed"] == d["feed_stage"]


def test_wanghenke_path_with_mock():
    """Inyectando _wh_result en el bloque, build_stage_profile lo prefiere
    sobre McCabe y reporta source='wanghenke'."""
    fs = _build('distillation')
    b = _column(fs)
    # Mock realista: 4 etapas, comps = [benzene, toluene], LK = benzene
    b._wh_result = {
        "converged": True,
        "T_profile": [354.0, 365.0, 375.0, 383.0],   # K
        "x_profile": [[0.95, 0.05], [0.70, 0.30],
                       [0.30, 0.70], [0.05, 0.95]],
        "y_profile": [[0.98, 0.02], [0.85, 0.15],
                       [0.50, 0.50], [0.10, 0.90]],
        "feed_stage": 2,
        "_comps": ["benzene", "toluene"],
    }
    p = tp.build_stage_profile(b, fs)
    assert p["source"] == "wanghenke"
    assert "Wang-Henke" in p["badge"]
    assert p["n_stages"] == 4
    assert p["n_feed"] == 2
    # extremos del perfil
    assert abs(p["stages"][0]["x_LK"] - 0.95) < 1e-6
    assert abs(p["stages"][-1]["x_LK"] - 0.05) < 1e-6
    assert abs(p["stages"][0]["T_C"] - (354.0 - 273.15)) < 1e-6


def test_wanghenke_multicomp_other_traces():
    """En WH multicomp, los componentes no-LK quedan en other_traces."""
    fs = _build('distillation')
    b = _column(fs)
    b._wh_result = {
        "converged": True,
        "T_profile": [354.0, 380.0, 383.0],
        "x_profile": [[0.95, 0.04, 0.01],
                       [0.50, 0.45, 0.05],
                       [0.05, 0.85, 0.10]],
        "y_profile": [[0.98, 0.02, 0.0]] * 3,
        "feed_stage": 2,
        "_comps": ["benzene", "toluene", "xylene"],
    }
    p = tp.build_stage_profile(b, fs)
    assert p["source"] == "wanghenke"
    assert set(p["other_traces"].keys()) == {"toluene", "xylene"}
    assert len(p["other_traces"]["toluene"]) == 3


def test_azeotrope_truncated_no_crash():
    """Forzar x_D arriba del azeótropo (eth/water): build_stage_profile NO
    lanza, devuelve truncated=True con mensaje explicativo."""
    fs = _build('ethanol')
    b = _column(fs)
    b.column_x_D_LK = 0.97   # > azeótropo etanol/agua (NRTL ~0.915)
    p = tp.build_stage_profile(b, fs)
    assert p is not None
    assert p["truncated"] is True
    assert "azeo" in p["message"].lower() or "azeó" in p["message"].lower()
    # no se pretenden etapas falsas
    assert p["n_stages"] == 0


def test_non_column_block_returns_none():
    """build_stage_profile devuelve None si el bloque no es columna activa
    o no tiene LK/HK declarados — el panel se oculta sin crash."""
    fs = _build('distillation')
    pump = next(b for b in fs.blocks.values()
                if "pump" in (b.eq_type or "").lower())
    assert tp.build_stage_profile(pump, fs) is None
    col = _column(fs)
    col.column_LK = ""
    assert tp.build_stage_profile(col, fs) is None


if __name__ == "__main__":
    test_mccabe_path_top_to_bottom_monotonic()
    test_n_feed_in_range_and_LK_HK_propagated()
    test_n_matches_mccabe_design_golden()
    test_wanghenke_path_with_mock()
    test_wanghenke_multicomp_other_traces()
    test_azeotrope_truncated_no_crash()
    test_non_column_block_returns_none()
    print("tray_profile: OK")
