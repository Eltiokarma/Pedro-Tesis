"""T29b — hda_full/R-101 conectado a la reacción HDA real (R035).

Verifica que el reactor CALCULA S-4 por balance (química real), no con la
composición hardcodeada vieja (0.78 benceno inventado).  El tren de
separación aguas abajo del flash sigue declarado (congelado por locks) —
su re-tuneo es T29c, bloqueado por el over-spec de H2 del loop congelado."""
import math
import examples_registry as reg
import flowsheet_solver as fsv
import thermo_db as tdb

MW = {n: tdb.get(n).mw for n in ("benzene", "hydrogen", "methane", "toluene")}


def _solved():
    fs = reg.load_example("hda_full")
    res = fsv.solve(fs)
    return fs, res


def _km(s, sp):
    return (s.composition or {}).get(sp, 0) * s.mass_flow / MW[sp]


def test_r101_conectado_a_r035_modo_conversion():
    fs, _ = _solved()
    r = next(b for b in fs.blocks.values() if b.name == "R-101")
    assert r.reactions == ["R035"]
    assert r.reactor_mode == "stoich"          # conversión (R035 irreversible)
    assert math.isclose(r.reactor_conversion, 0.85)
    assert 800.0 <= r.T_op_K <= 950.0          # rango válido de R035


def test_balance_hda_cierra_1a1a1a1():
    """R035 consume tolueno+H2 y produce benceno+metano en 1:1:1:1.
    Con conv 0.85 sobre 868.2 kmol tolueno → 738 kmol de cada uno."""
    fs, _ = _solved()
    S3 = next(s for s in fs.streams.values() if s.name == "S-3")
    S4 = next(s for s in fs.streams.values() if s.name == "S-4")
    d_tol = _km(S3, "toluene") - _km(S4, "toluene")
    d_h2 = _km(S3, "hydrogen") - _km(S4, "hydrogen")
    d_benz = _km(S4, "benzene") - _km(S3, "benzene")
    d_met = _km(S4, "methane") - _km(S3, "methane")
    assert math.isclose(d_tol, 738.0, abs_tol=1.0)
    for x in (d_h2, d_benz, d_met):
        assert math.isclose(x, d_tol, rel_tol=1e-3)   # 1:1:1:1
    # conversión real = declarada
    assert math.isclose(d_tol / _km(S3, "toluene"), 0.85, abs_tol=0.005)


def test_s4_sale_del_balance_no_hardcodeada():
    """S-4 ya NO es el 0.78 benceno inventado viejo — sale del balance.
    El benceno producido (738 kmol) coincide con el tolueno convertido por MW
    (antes el viejo declaraba 878.8 kmol, imposible desde 744 convertidos)."""
    fs, _ = _solved()
    S4 = next(s for s in fs.streams.values() if s.name == "S-4")
    assert not math.isclose(S4.composition["benzene"], 0.78, abs_tol=0.01)
    # benceno por balance ≈ 743 kmol (738 producidos + 5 que ya venían)
    assert math.isclose(_km(S4, "benzene"), 743.0, abs_tol=2.0)


def test_reactor_exotermico_y_sin_placeholder():
    fs, res = _solved()
    r = next(b for b in fs.blocks.values() if b.name == "R-101")
    assert r.duty < 0                                  # HDA exotérmica
    assert res.overall_status == "ok"
    assert len(res.mass_balance_errors) == 0
    assert len(res.energy_balance_errors) == 0
    # R-101 ya no es placeholder ni dispara energía mal cerrada
    assert not any("PLACEHOLDER" in w and "R-101" in w
                   for w in res.awareness_warnings)
    assert not any("ENERGY-BLOCK" in w and "R-101" in w
                   for w in res.awareness_warnings)
