"""T30 — el motor propaga composición por equipos pass-through.

Un pass-through 1-in-1-out (HX, bomba, compresor, fired heater, válvula,
turbina) no transforma composición: su salida = su entrada.  El motor ahora
la propaga en vez de exigir que esté escrita a mano en el JSON.  Si el JSON
declara una composición que DIFIERE del inlet (override manual, química
hardcodeada), se conserva y se emite [W-COMP-OVERRIDE] (advisory)."""
import examples_registry as reg
import flowsheet_solver as fsv


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
    fs = reg.load_example("hda_full")
    fsv.solve(fs)
    io = fsv._passthrough_io(_block(fs, "E-102"), fs)        # 1-in-1-out
    assert io is not None and (io[0].name, io[1].name) == ("S-4b", "S-5")


def test_feed_effluent_hx_NO_es_passthrough():
    """E-101 cruza S-1/S-4 (2-in-2-out): NO es pass-through — el motor no
    debe mezclar las composiciones de los dos lados."""
    fs = reg.load_example("hda_full")
    fsv.solve(fs)
    assert fsv._passthrough_io(_block(fs, "E-101"), fs) is None


# (b) override: comp declarada que difiere se conserva + warning ──────────
def test_override_conservado_y_warning():
    """hno3/E-203 (air cooler) hardcodea la oxidación NO+½O2→NO2: su outlet
    A8-gas-cool tiene NO2 que el inlet no trae.  El motor CONSERVA esa comp
    y emite [W-COMP-OVERRIDE]."""
    fs = reg.load_example("hno3")
    res = fsv.solve(fs)
    out = _stream(fs, "A8-gas-cool").composition
    assert out.get("nitrogen dioxide", 0) > 0.01        # override conservado
    hits = [w for w in res.awareness_warnings if "W-COMP-OVERRIDE" in w]
    assert len(hits) == 1 and "A8-gas-cool" in hits[0]


def test_warning_es_advisory_no_altera_status():
    fs = reg.load_example("hno3")
    res = fsv.solve(fs)
    assert any("W-COMP-OVERRIDE" in w for w in res.awareness_warnings)
    assert res.overall_status in ("ok", "warning")       # NO 'error'


def test_override_dispara_solo_en_hno3():
    """De los ~120 pass-through con comp == inlet, ninguno dispara override;
    solo hno3/E-203 (química hardcodeada)."""
    total = 0
    for meta in reg.list_examples():
        res = fsv.solve(reg.load_example(meta["clave"]))
        hits = [w for w in res.awareness_warnings if "W-COMP-OVERRIDE" in w]
        if meta["clave"] == "hno3":
            assert len(hits) == 1
        else:
            assert not hits, f"{meta['clave']} no debería tener override"
        total += len(hits)
    assert total == 1


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
