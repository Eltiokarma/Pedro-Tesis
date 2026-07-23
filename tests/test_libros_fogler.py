"""Auditoría con ejercicios de libro — Frente R (Fogler).

Caso 1: la tabla estequiométrica del ejemplo canónico de Fogler
(Elements of CRE 4ª ed., §3.4): oxidación de SO₂ con aire,
2 SO₂ + O₂ → 2 SO₃, feed 28 % mol SO₂ / 72 % aire.

Método CASOS_LIBRO: el checkpoint se recomputa A MANO acá adentro
(fracciones molares del libro → θ/δ/ε por definición), no contra los
catálogos del repo.  Valores del libro: θ_O2 = 0.54, θ_N2 = 2.03,
δ = −0.5 por mol de SO₂, ε = y_A0·δ = −0.14.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

from flowsheet_model import Flowsheet, Block, Stream
import inspector_evidence as ev
import thermo_db as td


def _fogler_so2_fs(X_declarada=0.5):
    """Reactor stoich con el feed del libro (28 % SO₂ / 72 % aire)."""
    # fracciones MOLARES del enunciado
    y = {"so2": 0.28, "oxygen": 0.72 * 0.21, "nitrogen": 0.72 * 0.79}
    # → fracciones másicas (recomputo independiente con MW de thermo_db)
    mw = {n: td.get(n).mw for n in y}
    m = {n: y[n] * mw[n] for n in y}
    tot = sum(m.values())
    w = {n: m[n] / tot for n in y}

    fs = Flowsheet()
    r = Block(id=fs.new_id(), name="R-101",
              eq_type="Reactor — jacketed agitated", S=10.0,
              reactor_mode="stoich", reactor_conversion=X_declarada,
              custom_reactions=[{
                  "id": "FOGLER-SO2", "name": "2 SO2 + O2 -> 2 SO3",
                  "stoich": [
                      {"formula": "SO2", "phase": "g", "nu": -2},
                      {"formula": "O2",  "phase": "g", "nu": -1},
                      {"formula": "SO3", "phase": "g", "nu": 2}],
                  "dh_rxn_298_kJ_mol": -197.8, "irreversible": True,
              }])
    fs.blocks[r.id] = r
    feed = Stream(id=fs.new_id(), name="S-feed", src=0, dst=r.id,
                  mass_flow=100000, mass_flow_locked=True,
                  temperature=227, role="feed", phase="gas",
                  composition=w, composition_locked=True)
    out = Stream(id=fs.new_id(), name="S-out", src=r.id, dst=0,
                 role="product", phase="gas")
    fs.streams[feed.id] = feed
    fs.streams[out.id] = out
    return fs, r


def test_fogler_so2_theta_delta_epsilon():
    fs, r = _fogler_so2_fs()
    d = ev.stoich_table(r, fs)
    assert d is not None
    assert d["limitante"] == "so2"
    # checkpoints del libro (dimensionales de la definición, no del repo)
    filas = {row["name"]: row for row in d["rows"]}
    assert filas["oxygen"]["theta"] == pytest.approx(0.1512 / 0.28,
                                                     rel=1e-3)    # 0.54
    assert filas["nitrogen"]["theta"] == pytest.approx(0.5688 / 0.28,
                                                       rel=1e-3)  # 2.031
    assert d["delta"] == pytest.approx(-0.5)      # (2−1−2)/2 por mol SO₂
    assert d["y_A0"] == pytest.approx(0.28, rel=1e-3)
    assert d["epsilon"] == pytest.approx(-0.14, rel=1e-2)


def test_fogler_so2_remanentes_a_X():
    """F_i(X) = F_A0·(θ_i + ν_i·X) — tabla 3-5 evaluada en X=0.5."""
    fs, r = _fogler_so2_fs(X_declarada=0.5)
    d = ev.stoich_table(r, fs)
    F_A0 = d["F_A0_kmol_h"]
    filas = {row["name"]: row for row in d["rows"]}
    assert d["X"] == pytest.approx(0.5) and d["X_origin"] == "declarada"
    assert filas["so2"]["F_X_kmol_h"] == pytest.approx(F_A0 * 0.5, rel=1e-6)
    assert filas["oxygen"]["F_X_kmol_h"] == pytest.approx(
        F_A0 * (0.54 - 0.25), rel=1e-2)
    assert filas["sulfur_trioxide"]["F_X_kmol_h"] == pytest.approx(
        F_A0 * 0.5, rel=1e-6)
    # inerte: no cambia
    assert filas["nitrogen"]["cambio_kmol_h"] == pytest.approx(0.0)
    assert filas["nitrogen"]["es_inerte"]


def test_render_texto_estilo_libro():
    fs, r = _fogler_so2_fs()
    txt = ev.stoich_table_text(r, fs)
    assert txt is not None
    assert "Fogler" in txt and "θ_i" in txt and "ε = y_A0·δ" in txt
    assert "(A)" in txt and "(I)" in txt      # limitante e inerte marcados


def test_tabla_en_ejemplo_real_smr():
    """El reactor de smr_eq (reacciones del catálogo) produce tabla."""
    import examples_registry as reg
    import flowsheet_solver as fsolv
    fs = reg.load_example("smr_eq")
    fsolv.solve(fs)
    rb = next(b for b in fs.blocks.values()
              if getattr(b, "reactions", None))
    d = ev.stoich_table(rb, fs)
    assert d is not None and d["rows"], "smr_eq sin tabla estequiométrica"
    assert ev.stoich_table_text(rb, fs)


def test_no_reactor_no_tabla():
    fs, r = _fogler_so2_fs()
    bomba = Block(id=99, name="P-1", eq_type="Pump — centrifugal", S=1.0)
    fs.blocks[99] = bomba
    assert ev.stoich_table(bomba, fs) is None
