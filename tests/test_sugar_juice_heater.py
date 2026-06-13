"""T29d — sugar/R-101 es un CALENTADOR de jugo, no un reactor.

Entra S-jugo (30°C) y sale S-1 (70°C) con composición IDÉNTICA: no hay
reacción, es el calentamiento del jugo de caña con vapor antes de la
evaporación.  Estaba mal tipado como "Reactor — jacketed agitated" (y con
S=50 m³ fuera del rango de costeo del reactor).  Re-tipado a intercambiador
de calor líquido (fixed tube).  El duty (+3058 kW) es el mismo salto
entálpico físico de 40°C — solo cambió el TIPO y, con él, el costo."""
import examples_registry as reg
import flowsheet_solver as fsv


def _block(fs, name):
    return next(b for b in fs.blocks.values() if b.name == name)


def _stream(fs, name):
    return next(s for s in fs.streams.values() if s.name == name)


def test_r101_es_intercambiador_no_reactor():
    fs = reg.load_example("sugar")
    fsv.solve(fs)
    b = _block(fs, "R-101")
    assert "heat exch" in b.eq_type.lower()
    assert "reactor" not in b.eq_type.lower()


def test_no_hay_reaccion_solo_calentamiento():
    """S-1 == S-jugo en composición (no transforma) y solo cambia T."""
    fs = reg.load_example("sugar")
    fsv.solve(fs)
    sj, s1 = _stream(fs, "S-jugo"), _stream(fs, "S-1")
    assert sj.composition == s1.composition          # sin transformación
    assert abs(sj.mass_flow - s1.mass_flow) < 1.0     # masa conservada
    assert s1.temperature > sj.temperature            # calienta


def test_s1_se_propaga_desde_sjugo_por_t30():
    """Como ahora es un pass-through 1-in-1-out, T30 lo clasifica y la
    composición de S-1 se propaga desde S-jugo (no depende de hardcode)."""
    fs = reg.load_example("sugar")
    fsv.solve(fs)
    io = fsv._passthrough_io(_block(fs, "R-101"), fs)
    assert io is not None and (io[0].name, io[1].name) == ("S-jugo", "S-1")


def test_duty_calentamiento_se_mantiene_sin_warnings():
    fs = reg.load_example("sugar")
    res = fsv.solve(fs)
    b = _block(fs, "R-101")
    assert 3000 < b.duty < 3120                        # ~3058 kW, exotérmico+
    assert res.overall_status == "ok"
    assert not any("PLACEHOLDER" in w and "R-101" in w
                   for w in res.awareness_warnings)
    assert not any("ENERGY-BLOCK" in w and "R-101" in w
                   for w in res.awareness_warnings)
