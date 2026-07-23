"""Auditoría con libros — Frente S.2: tabla de reparto del flash TP.

El flash del solver YA era multicomponente (Rachford-Rice C-componente
con γ NRTL sobre todos los volátiles; no-volátiles enteros al líquido)
— lo que faltaba era VERLO: la tabla x/y/K/V-F por componente que
imprime ChemSep, ahora persistida por el solver (_flash_diagnostics)
y renderizada por la evidencia del inspector.

Checkpoints (método CASOS_LIBRO):
· El reparto persistido satisface la identidad de Rachford-Rice
  Σ z_i(K_i−1)/(1+V(K_i−1)) = 0 y las sumas Σx=Σy=1 — las identidades
  del flash isotérmico de Smith-Van Ness-Abbott §12 / Seader §4,
  recomputadas acá a mano sobre los números persistidos.
· K ordenado por volatilidad (hexano > etanol/benceno > agua a la
  misma T) — física, no implementación.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from flowsheet_model import Flowsheet, Block, Stream
import flowsheet_solver as fsolv
import inspector_evidence as ev


def _flash_ternario():
    """Vessel flash con feed ternario etanol/agua/hexano a 360 K."""
    fs = Flowsheet()
    v = Block(id=fs.new_id(), name="V-1", eq_type="Vessel — vertical",
              S=1.0)
    v.flash_active = True
    v.flash_T_K = 360.0
    v.flash_P_bar = 1.013
    fs.blocks[v.id] = v
    feed = Stream(id=fs.new_id(), name="S-f", src=0, dst=v.id,
                  mass_flow=10000, mass_flow_locked=True, temperature=80,
                  composition={"ethanol": 0.35, "water": 0.55,
                               "hexane": 0.10},
                  composition_locked=True, phase="liquid", role="feed")
    vap = Stream(id=fs.new_id(), name="S-v", src=v.id, dst=0,
                 role="product", phase="vapor", src_port="vapor")
    liq = Stream(id=fs.new_id(), name="S-l", src=v.id, dst=0,
                 role="product", phase="liquid", src_port="liquido")
    fs.streams[feed.id] = feed
    fs.streams[vap.id] = vap
    fs.streams[liq.id] = liq
    return fs, v


def test_solver_persiste_reparto_molar():
    fs, v = _flash_ternario()
    fsolv.solve(fs)
    d = ev.flash_split_table(v)
    assert d is not None, "el solver no persistió _flash_diagnostics"
    assert set(d["names"]) == {"ethanol", "water", "hexane"}
    assert 0.0 < d["V_frac"] < 1.0


def test_identidades_rachford_rice():
    """Las identidades del libro sobre los números persistidos:
    Σx = Σy = 1 (1e-6) y residual R-R = 0 (1e-6)."""
    fs, v = _flash_ternario()
    fsolv.solve(fs)
    d = ev.flash_split_table(v)
    assert sum(d["x"]) == pytest.approx(1.0, abs=1e-6)
    assert sum(d["y"]) == pytest.approx(1.0, abs=1e-6)
    V = d["V_frac"]
    rr = sum(d["z"][i] * (d["K"][i] - 1.0)
             / (1.0 + V * (d["K"][i] - 1.0))
             for i in range(len(d["z"])))
    assert rr == pytest.approx(0.0, abs=1e-6), f"residual R-R = {rr}"
    # y_i = K_i·x_i (definición de K)
    for i in range(len(d["z"])):
        assert d["y"][i] == pytest.approx(d["K"][i] * d["x"][i],
                                          rel=1e-6)


def test_identidad_K_gamma_psat():
    """K_i = γ_i(NRTL, x)·P_sat,i(T)/P — la definición del libro
    (Seader §4) recomputada a mano sobre el líquido convergido.
    Nota honesta: hexano no tiene pares NRTL en el catálogo → su γ cae
    a 1 (ideal declarado), por eso NO se asevera K_hexano > K_etanol
    (con γ real de mezcla acuosa lo sería); sí K_etanol > K_agua, cuyo
    par NRTL existe."""
    import nrtl
    import thermo_db as td
    fs, v = _flash_ternario()
    fsolv.solve(fs)
    d = ev.flash_split_table(v)
    T_C = d["T_K"] - 273.15
    gammas = nrtl.gamma(d["names"], d["x"], d["T_K"])
    for i, n in enumerate(d["names"]):
        psat_bar = td.vapor_pressure_kPa(n, T_C) / 100.0
        K_mano = gammas[i] * psat_bar / d["P_bar"]
        assert d["K"][i] == pytest.approx(K_mano, rel=1e-3), \
            f"{n}: K persistido {d['K'][i]:.4f} vs γ·Psat/P {K_mano:.4f}"
    K = dict(zip(d["names"], d["K"]))
    assert K["ethanol"] > K["water"], K


def test_render_estilo_chemsep():
    fs, v = _flash_ternario()
    fsolv.solve(fs)
    txt = ev.flash_split_table_text(v)
    assert txt is not None
    for token in ("V/F", "K_i", "Rachford-Rice", "Seader"):
        assert token in txt, f"falta '{token}' en la tabla"
    # sin flash resuelto → None (la evidencia no inventa)
    v2 = Block(id=99, name="V-2", eq_type="Vessel — vertical", S=1.0)
    assert ev.flash_split_table_text(v2) is None
