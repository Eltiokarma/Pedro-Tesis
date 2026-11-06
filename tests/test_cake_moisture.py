"""tests/test_cake_moisture.py — humedad de torta en el modelo unificado.

Auditoría UI 3 §4.2: «Modo especial» convierte los filtros/centrífugas
legacy (separator_active + solids_recovery + solid_components +
cake_moisture) al modelo `mech_sep` (η + fase objetivo + componentes), que
no tenía término de humedad → abrir y guardar FL-101 de sugar.json le
secaba la torta.  Ahora `mech_sep_cake_moisture` vive en el modelo
unificado con la MISMA semántica que el legacy:

    moisture = m_líq_torta / (m_sól_torta + m_líq_torta)

el líquido arrastrado sale del no-target en proporción a su composición,
acotado a lo disponible, y el clamp es [0, 0.95].

Los tests de solver son headless; los de inspector (al final) piden PySide6.
"""
import os
import sys

import pytest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import examples_registry as reg
import flowsheet_model as fm
import flowsheet_solver as fsv


# ───────────────────────────── helpers ─────────────────────────────

def _filtro(eq_type="Filter — belt", **kw):
    """Filtro aislado: feed 1000 kg (sacarosa 60 / agua 40) → torta + madre."""
    fs = fm.Flowsheet()
    b = fm.Block(id=1, name="F-1", eq_type=eq_type, S=20.0,
                 solid_components=["sucrose"], **kw)
    fs.blocks = {1: b}
    is_cf = "centrifuge" in eq_type.lower()
    fs.streams = {
        10: fm.Stream(id=10, name="feed", src=0, dst=1, mass_flow=1000.0,
                      composition={"sucrose": 0.6, "water": 0.4},
                      main_component="sucrose", phase="liquid"),
        11: fm.Stream(id=11, name="torta", src=1, dst=0,
                      src_port="solido" if is_cf else "producto"),
        12: fm.Stream(id=12, name="madre", src=1, dst=0,
                      src_port="liquido" if is_cf else "venteo"),
    }
    return fs, b


def _comp_mass(s):
    return {c: f * s.mass_flow for c, f in (s.composition or {}).items()}


def _fl101_outlets(fs):
    b = next(b for b in fs.blocks.values() if b.name == "FL-101")
    outs = sorted((s for s in fs.streams.values() if s.src == b.id),
                  key=lambda s: s.id)
    return b, [(s.name, s.mass_flow, dict(s.composition), s.phase)
               for s in outs]


def _assert_same_outlets(a, b, rel=1e-12):
    assert [x[0] for x in a] == [y[0] for y in b]
    for (na, ma, ca, pa), (_, mb, cb, pb) in zip(a, b):
        assert mb == pytest.approx(ma, rel=rel), na
        assert pa == pb, na
        assert set(ca) == set(cb), na
        for c in ca:
            assert cb[c] == pytest.approx(ca[c], rel=rel, abs=1e-14), (na, c)


# ─────────────────────────── 1. solver ───────────────────────────

def test_campo_existe_con_default_cero():
    b = fm.Block(id=1, name="F", eq_type="Filter — belt", S=1.0)
    assert b.mech_sep_cake_moisture == 0.0


@pytest.mark.parametrize("eq_type", ["Filter — belt", "Centrifuge — disc stack"])
def test_mech_sep_humedad_reproduce_legacy(eq_type):
    """mech_sep + mech_sep_cake_moisture da EXACTAMENTE lo que daba el
    legacy separator_active + cake_moisture."""
    fs_l, _ = _filtro(eq_type, separator_active=True, solids_recovery=0.9,
                      cake_moisture=0.10)
    fsv.solve_mechanical_separators(fs_l)
    fs_m, _ = _filtro(eq_type, mech_sep_active=True, mech_sep_efficiency=0.9,
                      mech_sep_cake_moisture=0.10)
    fsv.solve_mechanical_separators(fs_m)
    for sid in (11, 12):
        sl, sm = fs_l.streams[sid], fs_m.streams[sid]
        assert sm.mass_flow == pytest.approx(sl.mass_flow, rel=1e-12)
        assert sm.composition == pytest.approx(sl.composition, rel=1e-12)
    torta = fs_m.streams[11]
    assert torta.composition["water"] == pytest.approx(0.10, rel=1e-12)
    assert torta.mass_flow == pytest.approx(600 * 0.9 / 0.9, rel=1e-12)


def test_humedad_cero_es_mech_sep_previo():
    fs, _ = _filtro(mech_sep_active=True, mech_sep_efficiency=0.9,
                    mech_sep_cake_moisture=0.0)
    fsv.solve_mechanical_separators(fs)
    torta, madre = fs.streams[11], fs.streams[12]
    assert torta.mass_flow == pytest.approx(540.0, rel=1e-12)
    assert torta.composition == {"sucrose": 1.0}
    assert madre.mass_flow == pytest.approx(460.0, rel=1e-12)


def test_humedad_sube_mueve_liquido_y_cierra_balance():
    res = {}
    for m in (0.03, 0.10):
        fs, _ = _filtro(mech_sep_active=True, mech_sep_efficiency=0.9,
                        mech_sep_cake_moisture=m)
        fsv.solve_mechanical_separators(fs)
        torta, madre = fs.streams[11], fs.streams[12]
        assert torta.composition["water"] == pytest.approx(m, rel=1e-12)
        assert torta.mass_flow + madre.mass_flow == pytest.approx(1000.0,
                                                                  rel=1e-12)
        for c in ("sucrose", "water"):
            tot = _comp_mass(torta).get(c, 0) + _comp_mass(madre).get(c, 0)
            assert tot == pytest.approx(1000.0 * {"sucrose": 0.6,
                                                  "water": 0.4}[c], rel=1e-12)
        res[m] = (_comp_mass(torta)["water"], madre.mass_flow)
    assert res[0.10][0] > res[0.03][0]          # más agua en la torta
    assert res[0.10][1] < res[0.03][1]          # menos madre


def test_humedad_no_inventa_liquido():
    """Si la humedad pide más líquido del que hay, la torta se lleva todo
    el líquido y nada más (mismo tope que el legacy)."""
    fs, _ = _filtro(mech_sep_active=True, mech_sep_efficiency=1.0,
                    mech_sep_cake_moisture=0.95)
    fsv.solve_mechanical_separators(fs)
    torta, madre = fs.streams[11], fs.streams[12]
    assert torta.mass_flow == pytest.approx(1000.0, rel=1e-12)
    assert madre.mass_flow == pytest.approx(0.0, abs=1e-9)


def test_humedad_no_aplica_a_ciclon_ni_decanter():
    """Ciclón y decanter no tienen torta: el término no los toca."""
    for et in ("Cyclone — gas/solid", "Decanter — gravity",
               "Centrifuge — decanter"):
        outs = []
        for m in (0.0, 0.3):
            fs, _ = _filtro(et, mech_sep_active=True, mech_sep_efficiency=0.9,
                            mech_sep_cake_moisture=m)
            fsv.solve_mechanical_separators(fs)
            outs.append([(s.mass_flow, dict(s.composition))
                         for s in (fs.streams[11], fs.streams[12])])
        assert outs[0] == outs[1], et


# ───────────────────────── 2. carga / guardado ─────────────────────────

def test_carga_legacy_siembra_desde_cake_moisture():
    fs = reg.load_example("sugar")
    b = next(b for b in fs.blocks.values() if b.name == "FL-101")
    assert b.separator_active and not b.mech_sep_active
    assert b.mech_sep_cake_moisture == pytest.approx(0.03)


def test_mech_sep_guardado_sin_la_clave_no_se_siembra():
    """Un mech_sep ya guardado (sin la clave) conserva su comportamiento:
    torta seca, aunque arrastre un cake_moisture legacy inerte
    (salt_crystal FL-101 trae 0.08)."""
    fs = reg.load_example("salt_crystal")
    b = next(b for b in fs.blocks.values() if b.name == "FL-101")
    assert b.mech_sep_active and b.cake_moisture == pytest.approx(0.08)
    assert b.mech_sep_cake_moisture == 0.0


def test_ida_y_vuelta_serializa_la_humedad():
    fs, b = _filtro(mech_sep_active=True, mech_sep_cake_moisture=0.07)
    d = fs.to_dict()
    assert d["blocks"][1]["mech_sep_cake_moisture"] == 0.07
    fs2 = fm.Flowsheet.from_dict(d)
    assert fs2.blocks[1].mech_sep_cake_moisture == 0.07
    # y una clave explícita gana a la siembra legacy
    d["blocks"][1].update(separator_active=True, mech_sep_active=False,
                          cake_moisture=0.30, mech_sep_cake_moisture=0.05)
    assert fm.Flowsheet.from_dict(d).blocks[1].mech_sep_cake_moisture == 0.05


def test_fl101_convertido_a_mech_sep_da_lo_mismo():
    """La conversión que hace «Modo especial» (sin UI): mech_sep con la η
    de solids_recovery y la humedad sembrada → mismas salidas."""
    fs = reg.load_example("sugar")
    fsv.solve(fs)
    _, antes = _fl101_outlets(fs)
    fs2 = reg.load_example("sugar")
    b = next(b for b in fs2.blocks.values() if b.name == "FL-101")
    b.mech_sep_active, b.separator_active = True, False
    b.mech_sep_efficiency = b.solids_recovery
    fsv.solve(fs2)
    _, despues = _fl101_outlets(fs2)
    _assert_same_outlets(antes, despues)
    assert any(abs(x[2].get("water", 0) - 0.03) < 1e-12 for x in despues)


# ─────────────────────── 3. inspector «Modo especial» ───────────────────────

@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _panel_especial(b, fs):
    from block_inspector import BlockInspectorPanel
    p = BlockInspectorPanel()
    p.load_block(b, fs, lambda: None)
    p._build_section_content("especial")
    return p


def test_fl101_abrir_y_guardar_no_cambia_el_balance(app):
    """Test crítico (§4.2): sugar.json FL-101 resuelto; se abre en el
    inspector, «Modo especial» se aplica sin tocar nada (convierte a
    mech_sep) y se re-resuelve → salidas idénticas."""
    fs = reg.load_example("sugar")
    fsv.solve(fs)
    _, antes = _fl101_outlets(fs)

    fs2 = reg.load_example("sugar")
    b = next(b for b in fs2.blocks.values() if b.name == "FL-101")
    p = _panel_especial(b, fs2)
    assert p._fields["mech_sep_cake_moisture"].value() == "3.00"
    assert float(p._fields["mech_sep_efficiency"].value()) == \
        pytest.approx(0.75)
    p._apply_to_block()
    assert b.mech_sep_active and not b.separator_active
    assert b.mech_sep_cake_moisture == 0.03
    assert b.mech_sep_efficiency == pytest.approx(0.75)
    fsv.solve(fs2)
    _, despues = _fl101_outlets(fs2)
    _assert_same_outlets(antes, despues)


def test_inspector_humedad_editable_mueve_liquido(app):
    fs = reg.load_example("sugar")
    fsv.solve(fs)
    b, base = _fl101_outlets(fs)
    feed_m = sum(s.mass_flow for s in fs.streams.values() if s.dst == b.id)
    p = _panel_especial(b, fs)
    p._fields["mech_sep_cake_moisture"].setValue("10")
    p._apply_to_block()
    assert b.mech_sep_cake_moisture == pytest.approx(0.10)
    fsv.solve(fs)
    _, nuevo = _fl101_outlets(fs)
    torta0 = next(x for x in base if abs(x[2]["water"] - 0.03) < 1e-9)
    torta1 = next(x for x in nuevo if x[0] == torta0[0])
    assert torta1[2]["water"] == pytest.approx(0.10, rel=1e-12)
    assert torta1[1] > torta0[1]                       # la torta gana líquido
    assert sum(x[1] for x in nuevo) == pytest.approx(feed_m, rel=1e-9)


def test_inspector_humedad_solo_en_filtro_y_centrifuga(app):
    casos = {"Filter — belt": True, "Centrifuge — disc stack": True,
             "Cyclone — gas/solid": False, "Decanter — gravity": False,
             "Centrifuge — decanter": False}
    for et, esperado in casos.items():
        fs, b = _filtro(et, mech_sep_active=True)
        p = _panel_especial(b, fs)
        assert ("mech_sep_cake_moisture" in p._fields) is esperado, et


def test_inspector_humedad_mech_sep_ida_y_vuelta(app):
    fs, b = _filtro(mech_sep_active=True, mech_sep_cake_moisture=0.123456)
    p = _panel_especial(b, fs)
    assert p._fields["mech_sep_cake_moisture"].value() == "12.35"
    p._apply_to_block()
    assert b.mech_sep_cake_moisture == 0.123456       # sin editar: exacto
    p = _panel_especial(b, fs)
    p._fields["mech_sep_cake_moisture"].setValue("0")
    p._apply_to_block()
    assert b.mech_sep_cake_moisture == 0.0
