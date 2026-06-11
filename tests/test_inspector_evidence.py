"""GATE evidencia gráfica — los 7 builders de inspector_evidence.

Contrato: cada *_figure(block, fs) devuelve (Figure, data) con un
bloque preparado, y (None, {"reason": str}) con una razón ESPECÍFICA
y accionable (nunca genérica) cuando faltan datos.  Offscreen.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

import examples_registry as reg
import flowsheet_solver as fsolv
import inspector_evidence as ev
from flowsheet_model import Flowsheet, Block, Stream

_GENERIC = ("figura no disponible", "sin datos", "error")


def _solved(key):
    fs = reg.load_example(key)
    fsolv.solve(fs)
    return fs


def _assert_reason(d, must_contain):
    assert isinstance(d, dict) and d.get("reason"), \
        f"sin razón reportada: {d}"
    r = d["reason"].lower()
    assert must_contain.lower() in r, \
        f"razón no específica: {d['reason']!r} (esperaba {must_contain!r})"
    assert r not in _GENERIC, f"razón genérica: {r!r}"


# ── 1. McCabe-Thiele ───────────────────────────────────────────────────
def test_mccabe_preparada_y_razon():
    fs = _solved("distillation")
    col = next(b for b in fs.blocks.values()
               if getattr(b, "column_active", False))
    fig, d = ev.mccabe_figure(col, fs)
    assert fig is not None, f"sin figura: {d}"
    # sin LK/HK → razón específica
    fs2 = Flowsheet()
    bid = fs2.new_id()
    c2 = Block(id=bid, name="T-1", eq_type="Tower (column shell)",
               S=1.0, x=0, y=0)
    fs2.blocks[bid] = c2
    fig2, d2 = ev.mccabe_figure(c2, fs2)
    assert fig2 is None
    _assert_reason(d2, "LK/HK")


# ── 2. Perfil tray-by-tray ─────────────────────────────────────────────
def test_profile_preparada_y_razon():
    fs = _solved("distillation")
    col = next(b for b in fs.blocks.values()
               if getattr(b, "column_active", False))
    fig, d = ev.profile_figure(col, fs)
    assert fig is not None, f"sin figura: {d}"
    # badge de procedencia presente (Wang-Henke o McCabe)
    assert d.get("badge"), "perfil sin badge de procedencia"
    # columna sin activar → razón con la acción
    col2 = Block(id=999, name="T-2", eq_type="Tower (column shell)",
                 S=1.0, x=0, y=0)
    fig2, d2 = ev.profile_figure(col2, fs)
    assert fig2 is None
    _assert_reason(d2, "diseño automático")


# ── 3. Flash VLE ───────────────────────────────────────────────────────
def _flash_fs():
    fs = Flowsheet()
    vid = fs.new_id()
    v = Block(id=vid, name="V-1", eq_type="Vessel — vertical",
              S=1.0, x=0, y=0)
    v.flash_active = True
    v.flash_T_K = 360.0
    v.flash_P_bar = 1.013
    fs.blocks[vid] = v
    sid = fs.new_id()
    f = Stream(id=sid, name="S-f", src=-1, dst=vid, mass_flow=1000.0,
               temperature=80.0,
               composition={"ethanol": 0.4, "water": 0.6},
               main_component="water", phase="liquid")
    f.start_xy = [0.0, 0.0]
    fs.streams[sid] = f
    return fs, v


def test_flash_preparada_y_razon():
    fs, v = _flash_fs()
    fig, d = ev.flash_figure(v, fs)
    assert fig is not None, f"sin figura: {d}"
    v.flash_active = False
    fig2, d2 = ev.flash_figure(v, fs)
    assert fig2 is None
    _assert_reason(d2, "flash automático")


# ── 4. Reactor (perfil/barras) ─────────────────────────────────────────
def test_reactor_preparada_y_razon():
    fs = _solved("smr_eq")
    r = next(b for b in fs.blocks.values()
             if getattr(b, "reactions", None))
    fig, d = ev.reactor_figure(r, fs)
    assert fig is not None, f"sin figura: {d}"
    # reactor sin corrientes → razón accionable
    fs2 = Flowsheet()
    rid = fs2.new_id()
    r2 = Block(id=rid, name="R-X", eq_type="Reactor — CSTR (agitado)",
               S=1.0, x=0, y=0)
    r2.reactor_mode = "cstr"
    fs2.blocks[rid] = r2
    fig2, d2 = ev.reactor_figure(r2, fs2)
    assert fig2 is None
    _assert_reason(d2, "solver")


# ── 5. Diagrama T-Q ────────────────────────────────────────────────────
def test_hx_tq_preparada_y_razon():
    fs = _solved("methanol")
    # con aux materializadas el HX tiene las 4 T's (lado servicio)
    import equipment_auxiliaries as eaux
    import equipment_costs as ec
    for b in list(fs.blocks.values()):
        if ec.EQUIPMENT_DATA.get(b.eq_type, {}).get("categoria") \
                != "Heat exchangers":
            continue
        if any((s.src == b.id or s.dst == b.id)
               and (s.role or "") == "utility"
               for s in fs.streams.values()):
            continue
        eaux.instantiate_auxiliaries(fs, b)
    fsolv.solve(fs)
    figs = []
    for b in fs.blocks.values():
        if ec.EQUIPMENT_DATA.get(b.eq_type, {}).get("categoria") \
                == "Heat exchangers":
            fig, d = ev.hx_tq_figure(b, fs)
            figs.append(fig)
    assert any(f is not None for f in figs), "ningún HX produjo T-Q"
    # HX sin diagnóstico → razón
    hx2 = Block(id=998, name="E-X", eq_type="Heat exch. — fixed tube",
                S=1.0, x=0, y=0)
    fig2, d2 = ev.hx_tq_figure(hx2, fs)
    assert fig2 is None
    _assert_reason(d2, "diagnóstico térmico")


# ── 6. X_eq vs T (equilibrio) ──────────────────────────────────────────
def test_equilibrium_preparada_y_razon():
    fs = _solved("smr_eq")
    r = next(b for b in fs.blocks.values()
             if getattr(b, "reactions", None)
             and (getattr(b, "reactor_mode", "") or "").lower()
             in ("equilibrium", "gibbs"))
    fig, d = ev.equilibrium_figure(r, fs)
    assert fig is not None, f"sin figura: {d}"
    assert d.get("limitante"), "sin reactante limitante identificado"
    assert d.get("sources"), "sin procedencia (ids de reactions_db)"
    # reactor de equilibrio sin reacciones → razón
    fs2 = Flowsheet()
    rid = fs2.new_id()
    r2 = Block(id=rid, name="R-Y", eq_type="Reactor — CSTR (agitado)",
               S=1.0, x=0, y=0)
    r2.reactor_mode = "equilibrium"
    fs2.blocks[rid] = r2
    fig2, d2 = ev.equilibrium_figure(r2, fs2)
    assert fig2 is None
    _assert_reason(d2, "reacciones")
    # modo no-equilibrio → razón que lo dice
    r2.reactor_mode = "pfr"
    fig3, d3 = ev.equilibrium_figure(r2, fs2)
    assert fig3 is None
    _assert_reason(d3, "equilibrio")


# ── 7. Diagrama de compresión ──────────────────────────────────────────
def test_compressor_preparada_y_razon():
    fs = _solved("ammonia")
    k = next(b for b in fs.blocks.values() if "Compressor" in b.eq_type)
    fig, d = ev.compressor_figure(k, fs)
    assert fig is not None, f"sin figura: {d}"
    assert d["W_act_kW"] >= d["W_isen_kW"] > 0, \
        "trabajo real debe ser >= isentrópico"
    assert d["T_out_C"] >= d["T_isen_C"], \
        "T real de descarga debe ser >= isentrópica"
    # sin razón de compresión (caso K-101 de air_sep) → instrucción exacta
    fs2 = _solved("air_sep")
    k2 = next(b for b in fs2.blocks.values() if "Compressor" in b.eq_type)
    assert (k2.delta_p_bar or 0) <= 0
    fig2, d2 = ev.compressor_figure(k2, fs2)
    assert fig2 is None
    _assert_reason(d2, "delta_p_bar")


# ── contrato: nunca (None, None) ───────────────────────────────────────
def test_contrato_nunca_none_none():
    fs = Flowsheet()
    bid = fs.new_id()
    b = Block(id=bid, name="B", eq_type="Tower (column shell)",
              S=1.0, x=0, y=0)
    fs.blocks[bid] = b
    for fn in (ev.mccabe_figure, ev.profile_figure, ev.flash_figure,
               ev.reactor_figure, ev.hx_tq_figure,
               ev.equilibrium_figure, ev.compressor_figure):
        fig, d = fn(b, fs)
        if fig is None:
            assert isinstance(d, dict) and d.get("reason"), \
                f"{fn.__name__} devolvió None sin razón"
