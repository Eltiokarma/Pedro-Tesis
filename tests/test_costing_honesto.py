"""PR-B — Costing honesto: la tabla de equipos muestra lo que el costing
REALMENTE usó (T_op/P_op efectivos), no el crudo 1.0/0.0 del bloque, y
expone el origen del material.  Solo VISIBILIDAD — el CBM no cambia."""
import math
import pytest

import examples_registry as reg
import flowsheet_export as fx
from flowsheet_solver import effective_pressure, effective_temperature


def _rows(clave="talara"):
    fs = reg.load_example(clave)
    # Templates now leave propagated temperatures/compositions unset.
    # Cost the operating case, not their unsolved placeholder values.
    from flowsheet_solver import solve
    solve(fs)
    return fs, fx.collect_equipment_rows(fs, 2024)


def test_p_op_columna_es_la_presion_efectiva_del_costing():
    """La columna P_op debe ser la presión EFECTIVA (la que entra a FP),
    no el b.P_op_bar crudo.  Antes 37/42 mostraban 1.0 aunque el costing
    usaba 40-80 bar internamente."""
    fs, rows = _rows()
    byname = {b.name: b for b in fs.blocks.values()}
    for r in rows:
        b = byname[r["Tag"]]
        assert math.isclose(r["P_op [bar]"], effective_pressure(fs, b),
                            rel_tol=1e-6), \
            f"{r['Tag']}: P_op tabla {r['P_op [bar]']} ≠ efectiva " \
            f"{effective_pressure(fs, b)}"
    # Hay bloques cuyo P efectivo (heredado de corrientes) supera su P_op_bar
    # crudo: antes mostraban 1.0; ahora muestran la P real que usó el costing.
    mejorados = [r for r in rows
                 if r["P_op [bar]"] > float(getattr(byname[r["Tag"]],
                                                     "P_op_bar", 0.0) or 0.0) + 1e-6]
    assert mejorados, "ningún bloque hereda P efectiva de sus corrientes (T4)"
    # los hornos HT son el caso testigo (P_op_bar crudo=1.0 → efectiva 40-80)
    tags = {r["Tag"] for r in mejorados}
    assert {"F-HTD", "F-HTF", "F-HTN"} <= tags


def test_t_op_columna_poblada_desde_corrientes_adyacentes():
    """T_op debe poblarse del promedio de Ts de corrientes adyacentes cuando
    el bloque no declara T_op_K, en vez de mostrar 0.0°C."""
    fs, rows = _rows()
    byname = {b.name: b for b in fs.blocks.values()}
    for r in rows:
        b = byname[r["Tag"]]
        t_eff_k = effective_temperature(fs, b)
        esperado = (t_eff_k - 273.15) if t_eff_k else 0.0
        assert math.isclose(r["T_op [°C]"], esperado, abs_tol=1e-6), \
            f"{r['Tag']}: T_op tabla {r['T_op [°C]']} ≠ esperado {esperado}"
    en_cero = sum(1 for r in rows if math.isclose(r["T_op [°C]"], 0.0, abs_tol=1e-9))
    assert en_cero < len(rows) // 2, "demasiadas filas siguen en T_op=0.0"


def test_t_op_unidades_kelvin_vs_celsius():
    """Regresión del bug de unidades: stream.temperature está en °C pero
    block.T_op_K en K.  Un fired heater HT debe dar cientos de °C, no
    decenas (que sería tratar °C como K)."""
    # Isolate unit conversion from pump heating and plant feed changes.
    from flowsheet_model import Block, Stream, Flowsheet
    fs = Flowsheet()
    b = Block(id=1, name="F-test", eq_type="Fired heater — non-reformer", S=5000)
    fs.blocks = {1: b}
    fs.streams = {1: Stream(id=1, name="in", src=0, dst=1, temperature=250.),
                  2: Stream(id=2, name="out", src=1, dst=0, temperature=370.)}
    assert fx.collect_equipment_rows(fs, 2024)[0]["T_op [°C]"] == pytest.approx(310.)
    b.T_op_K = 573.15
    assert fx.collect_equipment_rows(fs, 2024)[0]["T_op [°C]"] == pytest.approx(300.)


def test_columna_material_origen_presente_y_al_final():
    fs, rows = _rows()
    assert "Material (origen)" in rows[0]
    assert list(rows[0])[-1] == "Material (origen)"
    by = {r["Tag"]: r for r in rows}
    # PR-B2: los hornos se costean como CS aunque su servicio sea corrosivo.
    assert by["F-HTD"]["Material (origen)"] == "default (CS)"
    assert "default" in by["F-101"]["Material (origen)"].lower()
    # The revised feed has trace H2S below the screening threshold; the
    # reactor still reports its high-pressure hydrogen rule.  Corrosive
    # species above threshold are tested independently below.
    assert by["R-HTD"]["Material"] == "SS304"
    assert "H2 a alta P" in by["R-HTD"]["Material (origen)"]


def test_fired_heaters_siempre_cs():
    """PR-B2: ningún fired heater recibe aleación por composición/presión —
    la corrosión la sufren solo los tubos, no la estructura.  Los hornos HT
    de talara (servicio H2S a alta P) pasaron de SS316 (FBM 13-15) a CS."""
    fs, rows = _rows()
    by = {r["Tag"]: r for r in rows}
    for tag in ("F-HTD", "F-HTF", "F-HTN", "F-101", "F-RCA"):
        assert by[tag]["Material"] == "CS", f"{tag} debería ser CS"
    # FBM de los HT cae a CS+FP (≈4-6 por la presión), no 13-15 de aleación
    for tag in ("F-HTD", "F-HTF", "F-HTN"):
        assert by[tag]["FBM"] < 7.0, f"{tag} FBM={by[tag]['FBM']} (aún aleado?)"
    assert all(by[tag]["CBM USD (2024)"] > 0
               for tag in ("F-HTD", "F-HTF", "F-HTN", "F-101", "F-RCA"))
    # Compare equal-size heaters: a different plant's revised duties are
    # not a valid control for pressure-factor behavior.
    from flowsheet_model import Block, Flowsheet
    pair = Flowsheet()
    pair.blocks = {
        1: Block(id=1, name="F-low", eq_type="Fired heater — non-reformer", S=5000, P_op_bar=2.),
        2: Block(id=2, name="F-high", eq_type="Fired heater — non-reformer", S=5000, P_op_bar=80.)}
    compared = {r["Tag"]: r for r in fx.collect_equipment_rows(pair, 2024)}
    assert compared["F-high"]["CBM USD (2024)"] > compared["F-low"]["CBM USD (2024)"]


@pytest.mark.parametrize("species", ["hydrogen sulfide", "hydrogen_sulfide", "hydrogen-sulfide"])
def test_corrosion_rule_accepts_canonical_species_and_reports_origin(species):
    from flowsheet_model import Block, Stream, Flowsheet
    fs = Flowsheet()
    fs.blocks = {1: Block(id=1, name="R-test", eq_type="Reactor — autoclave", S=5)}
    fs.streams = {1: Stream(id=1, name="sour", src=0, dst=1,
                           composition={species: .1, "water": .9})}
    row = fx.collect_equipment_rows(fs, 2024)[0]
    assert row["Material"] == "SS316"
    assert "hydrogen sulfide" in row["Material (origen)"]


# ── ciclón gas/sólido: fases correctas + costeado (no zero-cost) ────────
def test_cyclone_fases_gas_solido_y_costeado():
    """El ejemplo 'cyclone' (equipo poco usado) ejercita el ciclón gas/sólido:
    la salida limpia debe quedar en fase GAS, el polvo en fase SOLID (antes
    ambos salían mal-etiquetados 'liquid'), y el ciclón debe DIMENSIONARSE y
    costearse (antes S=0 → costo nulo, no tenía sizer)."""
    import capex
    fs = reg.load_example("cyclone")
    from flowsheet_solver import solve
    solve(fs)
    byname = {s.name: s for s in fs.streams.values()}
    assert (byname["S-cleangas"].phase or "").lower() == "gas", \
        "el gas limpio del ciclón debe quedar en fase gas"
    assert (byname["S-dust"].phase or "").lower() == "solid", \
        "el polvo del ciclón debe quedar en fase solid"
    cd = capex.compute_fci(fs)
    zc = {b["name"] for b in cd.get("zero_cost_blocks", [])}
    assert "CY-101" not in zc, "el ciclón debe dimensionarse y costearse"
    cy = next(b for b in fs.blocks.values() if b.name == "CY-101")
    assert cy.S > 0, f"CY-101 sin dimensionar (S={cy.S})"


# ── mixers/splitters standalone: dimensionados y costeados (no zero-cost) ─
def test_mixer_splitter_standalone_costeados():
    """Los ejemplos 'bypass'/'parallel' (topologías raras) usan bloques
    'Splitter — flow divider' y 'Mixer — static' standalone.  La categoría
    'Mixers / splitters' tiene correlación de costo pero antes no tenía sizer
    → S=0 (costo nulo).  Con size_mixer_splitter deben quedar dimensionados."""
    import capex
    from flowsheet_solver import solve
    for clave in ("bypass", "parallel"):
        fs = reg.load_example(clave)
        solve(fs)
        cd = capex.compute_fci(fs)
        zc = {b["name"] for b in cd.get("zero_cost_blocks", [])}
        for b in fs.blocks.values():
            if b.eq_type.startswith(("Splitter", "Mixer")):
                assert b.name not in zc, \
                    f"{clave}/{b.name} ({b.eq_type}) quedó sin costo"
                assert b.S > 0, f"{clave}/{b.name} sin dimensionar (S={b.S})"


# ── centrífuga y cooling tower: dimensionadas y costeadas (no zero-cost) ──
def test_centrifuge_y_cooling_tower_costeados():
    """Los ejemplos 'centrifuge' (Solids / sep.) y 'cooling' (Utilities)
    ejercitan equipos que tenían correlación de costo pero NINGÚN sizer
    → S=0 (costo nulo).  Con size_centrifuge / size_cooling_tower deben
    quedar dimensionados y costeados."""
    import capex
    from flowsheet_solver import solve
    for clave, tag in (("centrifuge", "CF-101"), ("cooling", "CT-101")):
        fs = reg.load_example(clave)
        solve(fs)
        cd = capex.compute_fci(fs)
        zc = {b["name"] for b in cd.get("zero_cost_blocks", [])}
        assert tag not in zc, f"{clave}/{tag} quedó sin costo"
        b = next(b for b in fs.blocks.values() if b.name == tag)
        assert b.S > 0, f"{clave}/{tag} sin dimensionar (S={b.S})"


# ── boiler / fan / valve standalone: dimensionados y costeados ───────────
def test_boiler_fan_valve_costeados():
    """Ejemplos 'boiler_ft'/'blower'/'letdown' ejercitan eq_types que tenían
    correlación de costo pero NINGÚN sizer (Utilities boiler, Fans / blowers,
    Valves) → S=0.  Con size_boiler_steam / size_fan / size_valve deben quedar
    dimensionados y costeados."""
    import capex
    from flowsheet_solver import solve
    for clave, tag in (("boiler_ft", "B-101"), ("blower", "FN-101"),
                       ("letdown", "V-101")):
        fs = reg.load_example(clave)
        solve(fs)
        cd = capex.compute_fci(fs)
        zc = {b["name"] for b in cd.get("zero_cost_blocks", [])}
        assert tag not in zc, f"{clave}/{tag} quedó sin costo"
        b = next(b for b in fs.blocks.values() if b.name == tag)
        assert b.S > 0, f"{clave}/{tag} sin dimensionar (S={b.S})"
