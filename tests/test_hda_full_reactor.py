"""HDA: conversion and elemental stoichiometry from live feed/recycle flows."""
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
    assert 0 < r.reactor_conversion < 1
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
    r = next(b for b in fs.blocks.values() if b.name == "R-101")
    expected = min(_km(S3, "toluene"), _km(S3, "hydrogen")) * r.reactor_conversion
    assert expected > 0
    assert math.isclose(d_tol, expected, rel_tol=1e-3)
    for x in (d_h2, d_benz, d_met):
        assert math.isclose(x, d_tol, rel_tol=1e-3)   # 1:1:1:1
    # conversión real = declarada
    assert math.isclose(d_tol / min(_km(S3, "toluene"), _km(S3, "hydrogen")),
                        r.reactor_conversion, abs_tol=0.005)


def test_s4_sale_del_balance_no_hardcodeada():
    """Benzene production equals toluene consumption, independent of recycle seed."""
    fs, _ = _solved()
    S3 = next(s for s in fs.streams.values() if s.name == "S-3")
    S4 = next(s for s in fs.streams.values() if s.name == "S-4")
    produced = _km(S4, "benzene") - _km(S3, "benzene")
    consumed = _km(S3, "toluene") - _km(S4, "toluene")
    assert produced > 0
    assert math.isclose(produced, consumed, rel_tol=1e-3)


def test_reactor_exotermico_y_sin_placeholder():
    fs, res = _solved()
    r = next(b for b in fs.blocks.values() if b.name == "R-101")
    assert r.duty < 0                                  # HDA exotérmica
    assert res.success
    assert len(res.mass_balance_errors) == 0
    assert len(res.energy_balance_errors) == 0
    # R-101 ya no es placeholder ni dispara energía mal cerrada
    assert not any("PLACEHOLDER" in w and "R-101" in w
                   for w in res.awareness_warnings)
    assert not any("ENERGY-BLOCK" in w and "R-101" in w
                   for w in res.awareness_warnings)
