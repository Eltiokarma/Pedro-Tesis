"""T30 — el motor propaga composición por equipos pass-through.

Un pass-through 1-in-1-out (HX, bomba, compresor, fired heater, válvula,
turbina) no transforma composición: su salida = su entrada.  El motor ahora
la propaga en vez de exigir que esté escrita a mano en el JSON.  Si el JSON
declara una composición que DIFIERE del inlet (override manual, química
hardcodeada), se conserva y se emite [W-COMP-OVERRIDE] (advisory). El
balance estricto de especies sigue rechazando la creación de materia."""
import examples_registry as reg
import flowsheet_solver as fsv
from flowsheet_model import Block, Stream, Flowsheet


def _stream(fs, name):
    return next(s for s in fs.streams.values() if s.name == name)


def _block(fs, name):
    return next(b for b in fs.blocks.values() if b.name == name)


# (a) propagación: outlet vacío se llena desde el inlet ───────────────────
def test_passthrough_propaga_comp_desde_inlet():
    """hda_full/S-5 NO tiene composición en el JSON (se le quitó el hardcode
    de T29b); el air-cooler E-102 (1-in-1-out) la propaga desde S-4b."""
    fs = reg.load_example("hda_full")
    fsv.solve(fs)
    s4b = _stream(fs, "S-4b").composition
    s5 = _stream(fs, "S-5").composition
    assert s5, "S-5 debería tener composición propagada, no vacía"
    keys = set(s4b) | set(s5)
    assert max(abs(s4b.get(k, 0) - s5.get(k, 0)) for k in keys) < 1e-4


def test_passthrough_io_clasifica_air_cooler():
    """Tras el split WHB+trim de la integración energética, E-102 (WHB)
    descarga en S-5-hot (el trim cooler E-102T hace S-5-hot → S-5)."""
    fs = reg.load_example("hda_full")
    fsv.solve(fs)
    io = fsv._passthrough_io(_block(fs, "E-102"), fs)        # 1-in-1-out
    assert io is not None and (io[0].name, io[1].name) == ("S-4b", "S-5-hot")


def test_feed_effluent_hx_NO_es_passthrough():
    """E-101 cruza S-1/S-4 (2-in-2-out): NO es pass-through — el motor no
    debe mezclar las composiciones de los dos lados."""
    fs = reg.load_example("hda_full")
    fsv.solve(fs)
    assert fsv._passthrough_io(_block(fs, "E-101"), fs) is None


# (b) override: comp declarada que difiere se conserva + warning ──────────
#
# El caso real original (hno3/E-203 con la oxidación hardcodeada en
# A8-gas-cool) fue RETIRADO en la campaña de warnings 2026-07: la composición
# ahora se propaga y la oxidación vive en V-201 como química declarada
# (inline_reaction R033+R034).  El MECANISMO de override sigue vivo en el
# motor, así que estos tests re-introducen el defecto EN MEMORIA (patrón
# detector-sigue-vivo) y verifican que el catálogo quedó limpio.

# Composición históricamente hardcodeada en A8-gas-cool (oxidación parcial
# NO+½O₂→NO₂ escrita a mano — ver docs/hno3_e203_oxidacion_override.md).
_A8_OVERRIDE = {
    "nitric oxide": 0.07999893334755537,
    "nitrogen": 0.7189904134611538,
    "nitrogen dioxide": 0.04907934560872522,
    "nitrous oxide": 0.000999986666844442,
    "oxygen": 0.04493273423021026,
    "water": 0.10599858668551085,
}


def _hno3_con_override_en_memoria():
    """Carga hno3 y RE-INTRODUCE el override retirado: A8-gas-cool declara
    una composición distinta a su inlet (E-203 es pass-through)."""
    fs = reg.load_example("hno3")
    out = _stream(fs, "A8-gas-cool")
    out.composition = dict(_A8_OVERRIDE)
    out.composition_locked = True
    return fs


def test_override_conservado_y_warning():
    """Un pass-through cuyo outlet declara comp ≠ inlet conserva la comp
    declarada y emite [W-COMP-OVERRIDE] (mecanismo vivo, fixture en memoria)."""
    fs = _hno3_con_override_en_memoria()
    res = fsv.solve(fs)
    out = _stream(fs, "A8-gas-cool").composition
    assert out.get("nitrogen dioxide", 0) > 0.01        # override conservado
    hits = [w for w in res.awareness_warnings if "W-COMP-OVERRIDE" in w]
    assert len(hits) == 1 and "A8-gas-cool" in hits[0]


def test_v201_oxidacion_y_absorcion_consistentes():
    """La oxidación y absorción se calculan, no se explican retrospectivamente
    mediante IDs inline sobre composiciones y caudales escritos a mano."""
    import audit_examples_components as aec
    fs = reg.load_example("hno3")
    v201 = _block(fs, "V-201")
    assert not v201.inline_reaction
    assert v201.component_recovery_active
    oxidation = _block(fs, "R-301")
    absorption = _block(fs, "R-401")
    assert oxidation.reactions == ["R033"]
    assert oxidation.reactor_mode == absorption.reactor_mode == "stoich"
    assert absorption.custom_reactions
    fsv.solve(fs)
    oxidized = _stream(fs, "A11-NOx-ox")
    acid = _stream(fs, "A13b-HNO3-producto")
    assert oxidized.composition.get("nitrogen_dioxide", 0) > .1
    assert acid.composition.get("nitric_acid", 0) > .5
    rep = aec.audit_example("hno3")
    assert rep["n_critico"] == 0 and rep["n_mayor"] == 0, rep["findings"]


def test_override_advisory_no_oculta_error_de_conservacion():
    """The advisory preserves a manual spec, but cannot waive species balance.

    A controlled nonreactive fixture isolates that gate from the downstream
    chemistry/enthalpy errors caused by corrupting a complete acid plant.
    """
    fs = Flowsheet()
    fs.blocks[1] = Block(1, "E-test", "Heat exch. — fixed tube", 1)
    fs.streams[2] = Stream(2, "feed", 0, 1, mass_flow=1000,
        mass_flow_locked=True, composition={"nitrogen": .8, "oxygen": .2},
        composition_locked=True, temperature=80, temperature_locked=True,
        phase="gas", phase_locked=True)
    fs.streams[3] = Stream(3, "product", 1, 0, role="product",
        composition={"nitrogen": .7, "oxygen": .3}, composition_locked=True,
        temperature=40, temperature_locked=True, phase="gas", phase_locked=True)
    res = fsv.solve(fs)
    assert any("W-COMP-OVERRIDE" in w for w in res.awareness_warnings)
    assert fs.streams[3].composition == {"nitrogen": .7, "oxygen": .3}
    assert not res.energy_balance_errors
    assert any("component_balance" in e for e in res.consistency_errors)
    assert res.overall_status == "error" and not res.success


def test_catalogo_sin_overrides():
    """Ningún ejemplo del catálogo dispara W-COMP-OVERRIDE: el único caso
    (hno3/E-203) fue retirado y la química vive en reactores explícitos."""
    for meta in reg.list_examples():
        res = fsv.solve(reg.load_example(meta["clave"]))
        hits = [w for w in res.awareness_warnings if "W-COMP-OVERRIDE" in w]
        assert not hits, f"{meta['clave']} no debería tener override: {hits}"


# (c) reactores/flashes/columnas NO se ven afectados ─────────────────────
def test_reactor_flash_tower_no_son_passthrough():
    fs = reg.load_example("hda_full")
    fsv.solve(fs)
    for bn in ("R-101", "V-101", "T-101"):     # reactor, flash, columna
        assert fsv._passthrough_io(_block(fs, bn), fs) is None


def test_reactor_outlet_lo_escribe_la_reaccion_no_la_propagacion():
    """S-4 (outlet del reactor R-101) sale de la química (R035), no se
    propaga desde el inlet: su composición DIFIERE del inlet S-3."""
    fs = reg.load_example("hda_full")
    fsv.solve(fs)
    s3 = _stream(fs, "S-3").composition
    s4 = _stream(fs, "S-4").composition
    keys = set(s3) | set(s4)
    assert max(abs(s3.get(k, 0) - s4.get(k, 0)) for k in keys) > 0.1
