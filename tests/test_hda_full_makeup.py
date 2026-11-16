"""HDA live recycle: makeup feeds, elemental balances and reaction extent."""
import math

import examples_registry as reg
import flowsheet_solver as fsv
import thermo_db as tdb

MW = {n: tdb.get(n).mw for n in ("benzene", "hydrogen", "methane", "toluene")}
H_ATOMS = {"toluene": 8, "benzene": 6, "methane": 4, "hydrogen": 2}
C_ATOMS = {"toluene": 7, "benzene": 6, "methane": 1, "hydrogen": 0}
SP = ("toluene", "hydrogen", "benzene", "methane")


def _solved():
    fs = reg.load_example("hda_full")
    res = fsv.solve(fs)
    return fs, res


def _kmol(s, sp):
    return (s.composition or {}).get(sp, 0) * s.mass_flow / MW[sp]


def _feeds(fs):
    return [s for s in fs.streams.values() if getattr(s, "role", "") == "feed"]


def _products(fs):
    return [s for s in fs.streams.values() if getattr(s, "role", "") == "product"]


def _atoms(streams, table):
    return sum(_kmol(s, sp) * table[sp] for s in streams for sp in SP)


# ── 1. Makeup de H2 presente y bien declarado ───────────────────────────
def test_makeup_h2_presente():
    fs, _ = _solved()
    mk = next((s for s in fs.streams.values() if s.name == "S-H2-makeup"), None)
    assert mk is not None, "S-H2-makeup debe existir (feed externo de H2)"
    assert mk.role == "feed"
    assert mk.composition == {"hydrogen": 1.0}
    # Caudal del orden del consumo + pérdidas (≈1267 kmol H2 = 2555 kg).
    assert math.isclose(mk.mass_flow / MW["hydrogen"], 1267.0, abs_tol=20.0)
    assert mk.mass_flow_locked and mk.composition_locked


def test_hay_dos_feeds_tolueno_y_h2():
    fs, _ = _solved()
    names = {s.name for s in _feeds(fs)}
    assert names == {"S-feed-tol", "S-H2-makeup"}


# ── 2. Balance elemental de H CIERRA (el corazón de T29c) ────────────────
def test_balance_elemental_h_cierra():
    fs, _ = _solved()
    h_in = _atoms(_feeds(fs), H_ATOMS)
    h_out = _atoms(_products(fs), H_ATOMS)
    # Antes: in≈5210, out≈6542, déficit −1332.  Ahora cierra.
    assert math.isclose(h_in, h_out, rel_tol=1e-3), \
        f"H elemental no cierra: in={h_in:.1f} out={h_out:.1f}"
    # Y el H entrante ya NO es sólo el del tolueno (hay makeup).
    h_tol = _atoms([s for s in _feeds(fs) if s.name == "S-feed-tol"], H_ATOMS)
    # el makeup aporta ≈2534 atH (≈30% del H entrante): sustancial, no residual.
    assert h_in > h_tol * 1.3, "el makeup debe aportar H2 sustancial"


def test_balance_elemental_c_cierra():
    fs, _ = _solved()
    c_in = _atoms(_feeds(fs), C_ATOMS)
    c_out = _atoms(_products(fs), C_ATOMS)
    assert math.isclose(c_in, c_out, rel_tol=1e-3), \
        f"C elemental no cierra: in={c_in:.1f} out={c_out:.1f}"


# ── 3. Balance de masa global Σfeeds = Σproductos ────────────────────────
def test_balance_masa_global_cierra():
    fs, _ = _solved()
    m_in = sum(s.mass_flow for s in _feeds(fs))
    m_out = sum(s.mass_flow for s in _products(fs))
    assert math.isclose(m_in, m_out, rel_tol=1e-3), \
        f"masa global no cierra: in={m_in:.1f} out={m_out:.1f}"


# ── 4. NO hay H2 negativo en ningún stream ───────────────────────────────
def test_sin_h2_negativo():
    fs, _ = _solved()
    for s in fs.streams.values():
        assert _kmol(s, "hydrogen") >= -1e-6, \
            f"{s.name}: H2 negativo ({_kmol(s,'hydrogen'):.2f} kmol)"
        assert s.mass_flow >= -1e-6, f"{s.name}: masa negativa"


# ── 5. Reactor R035 preservado (1:1:1:1, conv 0.85) ──────────────────────
def test_reactor_r035_preservado():
    fs, _ = _solved()
    S3 = next(s for s in fs.streams.values() if s.name == "S-3")
    S4 = next(s for s in fs.streams.values() if s.name == "S-4")
    d_tol = _kmol(S3, "toluene") - _kmol(S4, "toluene")
    d_h2 = _kmol(S3, "hydrogen") - _kmol(S4, "hydrogen")
    d_benz = _kmol(S4, "benzene") - _kmol(S3, "benzene")
    d_met = _kmol(S4, "methane") - _kmol(S3, "methane")
    reactor = next(b for b in fs.blocks.values() if b.name == "R-101")
    expected = min(_kmol(S3, "toluene"), _kmol(S3, "hydrogen")) * reactor.reactor_conversion
    assert expected > 0
    assert math.isclose(d_tol, expected, rel_tol=2e-3)
    for x in (d_h2, d_benz, d_met):
        assert math.isclose(x, d_tol, rel_tol=2e-3)          # 1:1:1:1
    assert math.isclose(d_tol / min(_kmol(S3, "toluene"), _kmol(S3, "hydrogen")),
                        reactor.reactor_conversion, abs_tol=0.005)


# ── 6. Lazo de tolueno coherente: reciclo ≤ no-reaccionado ───────────────
def test_toluene_loop_coherente():
    fs, _ = _solved()
    S4 = next(s for s in fs.streams.values() if s.name == "S-4")
    rec = next(s for s in fs.streams.values() if s.name == "S-tol-recic")
    no_reaccionado = _kmol(S4, "toluene")
    reciclo = _kmol(rec, "toluene")
    assert reciclo <= no_reaccionado + 1e-6, \
        f"reciclo tolueno ({reciclo:.1f}) > no-reaccionado ({no_reaccionado:.1f})"
    # Y el feed fresco repone lo consumido (≈738 kmol) + pérdidas.
    feed_tol = _kmol(
        next(s for s in fs.streams.values() if s.name == "S-feed-tol"),
        "toluene")
    S3 = next(s for s in fs.streams.values() if s.name == "S-3")
    consumed = _kmol(S3, "toluene") - _kmol(S4, "toluene")
    assert feed_tol >= consumed * (1 - 1e-3), "fresh toluene must cover net consumption"
