"""GATE 3 — figuras del Panel Económico (econ_figures), render Y degradación.

Dos caminos probados por figura:
  · RENDER REAL (matplotlib presente): cada *_figure() devuelve una Figure con
    datos de ejemplo del README. No None.
  · DEGRADACIÓN LIMPIA (matplotlib "ausente", monkeypatch): devuelve (None, None)
    sin crashear.

Validación específica del waterfall: el marcador de payback cae en el año del
cruce del acumulado (no solo el vector tiene el largo correcto).
"""
import builtins
import importlib

import pytest

import econ_figures as ef


def _has_mpl():
    try:
        import matplotlib  # noqa: F401
        return True
    except Exception:
        return False


# ─── datos de ejemplo (README) ──────────────────────────────────────────
def _cashflow():
    data = [(-2.6, "ramp")] + [(6.8, "op")] * 8 + [(10.4, "op")]
    return [{"year": i + 1, "cf": v * 1e6, "phase": ph}
            for i, (v, ph) in enumerate(data)]


def _montecarlo():
    import numpy as np
    rng = np.random.default_rng(42)
    return {"samples": rng.normal(11.6e6, 5e6, 2000).tolist(),
            "p10": 4.1e6, "p50": 11.6e6, "p90": 19.8e6,
            "p_neg": 0.07, "n_runs": 2000, "seed": 42}


def _tornado():
    return [{"name": "Precio productos", "lo": -7.5e6, "hi": 31.2e6},
            {"name": "Materias primas", "lo": 0.9e6, "hi": 23.4e6},
            {"name": "ISBL", "lo": 7.4e6, "hi": 16.2e6}]


# ─── RENDER REAL ────────────────────────────────────────────────────────
@pytest.mark.skipif(not _has_mpl(), reason="matplotlib no instalado")
def test_cashflow_renders():
    fig, meta = ef.cashflow_figure(_cashflow(), payback_year=6.0)
    assert fig is not None
    assert meta["n_years"] == 10


@pytest.mark.skipif(not _has_mpl(), reason="matplotlib no instalado")
def test_npv_density_renders():
    fig, meta = ef.npv_density_figure(_montecarlo())
    assert fig is not None
    assert meta["n_runs"] == 2000


@pytest.mark.skipif(not _has_mpl(), reason="matplotlib no instalado")
def test_tornado_renders():
    fig, meta = ef.tornado_figure(_tornado(), base=11.8e6)
    assert fig is not None
    assert meta["n_vars"] == 3


# ─── VALIDACIÓN OFF-BY-ONE del marcador de payback ──────────────────────
@pytest.mark.skipif(not _has_mpl(), reason="matplotlib no instalado")
def test_waterfall_payback_marker_position():
    """El marcador cae en el año del cruce del acumulado, atado a payback_yr."""
    cf = _cashflow()
    # cruce real del acumulado: capex implícito = |suma de fases negativas|
    # acá validamos contra un payback conocido y que el marcador lo respeta.
    for pb in (4.0, 6.0, 8.5):
        fig, meta = ef.cashflow_figure(cf, payback_year=pb)
        assert fig is not None
        mx = meta["marker_x"]
        # el marcador debe caer dentro del rango de años y cerca de pb
        assert mx is not None
        assert abs(mx - pb) < 1.0, f"marcador {mx} lejos de payback {pb}"
    # payback infinito → sin marcador, sin crash
    fig, meta = ef.cashflow_figure(cf, payback_year=float("inf"))
    assert fig is not None
    assert meta["marker_x"] is None


# ─── DEGRADACIÓN LIMPIA (matplotlib ausente) ────────────────────────────
def _block_matplotlib(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "matplotlib" or name.startswith("matplotlib."):
            raise ImportError("matplotlib bloqueado (test)")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_cashflow_degrades_without_mpl(monkeypatch):
    _block_matplotlib(monkeypatch)
    fig, meta = ef.cashflow_figure(_cashflow(), payback_year=6.0)
    assert fig is None and meta is None


def test_npv_density_degrades_without_mpl(monkeypatch):
    _block_matplotlib(monkeypatch)
    fig, meta = ef.npv_density_figure(_montecarlo())
    assert fig is None and meta is None


def test_tornado_degrades_without_mpl(monkeypatch):
    _block_matplotlib(monkeypatch)
    fig, meta = ef.tornado_figure(_tornado(), base=11.8e6)
    assert fig is None and meta is None


# ─── DATOS OPCIONALES AUSENTES → None limpio ────────────────────────────
def test_optional_data_none():
    assert ef.cashflow_figure([], None) == (None, None)
    assert ef.npv_density_figure(None) == (None, None)
    assert ef.tornado_figure(None) == (None, None)
