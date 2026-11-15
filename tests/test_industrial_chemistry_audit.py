"""Plant-level regressions against stoichiometry and feed-response laws."""
import pytest

import examples_registry
import flowsheet_solver


def plant(key, scale=1):
    fs = examples_registry.load_example(key)
    for s in fs.streams.values():
        if s.src == 0 and s.stream_kind == "mass":
            s.mass_flow *= scale
    result = flowsheet_solver.solve(fs)
    assert not result.mass_balance_errors, result.mass_balance_errors
    assert not result.energy_balance_errors, result.energy_balance_errors
    assert not result.consistency_errors, result.consistency_errors
    assert all(r.converged for r in result.recycle_solutions)
    from stream_enthalpy import stream_enthalpy_kW
    for b in fs.blocks.values():
        if not (b.reactions or b.custom_reactions):
            continue
        ins = [s for s in fs.streams.values() if s.dst == b.id and s.stream_kind == "mass"]
        outs = [s for s in fs.streams.values() if s.src == b.id and s.stream_kind == "mass"]
        mass_kg_s = sum(s.mass_flow for s in ins) * 1000 / (8760 * 3600)
        expected_duty = (sum(stream_enthalpy_kW(s) for s in outs)
                         - sum(stream_enthalpy_kW(s) for s in ins)
                         + b.heat_of_reaction * mass_kg_s
                         - getattr(b, "_electrical_work_kW", 0))
        assert b.duty == pytest.approx(expected_duty, rel=1e-4, abs=1e-5), b.name
    return fs


def stream(fs, name):
    return next(s for s in fs.streams.values() if s.name == name)


def test_hno3_follows_ammonia_stoichiometry_and_design_selectivities():
    fs = plant("hno3")
    acid = stream(fs, "A13b-HNO3-producto")
    # 4 NH3 -> 4 NO -> 4 NO2 -> 4 HNO3. MW rounding is ~1e-5.
    expected = 1000 / 17.031 * .96 * .995 * .999 * 63.012
    actual = acid.mass_flow * acid.composition["nitric_acid"]
    assert actual == pytest.approx(expected, rel=1e-3)
    assert .55 <= acid.composition["nitric_acid"] <= .65
    assert acid.composition.get("ammonia", 0) == 0
    # No internally pinned product flow/composition survives the rewrite.
    assert all(not s.mass_flow_locked and not s.composition_locked
               for s in fs.streams.values() if s.src != 0)
    # Reheat before work recovery keeps the dry tail gas in the validated
    # caloric range across expansion, rather than extrapolating NOx below 298 K.
    turbine = next(b for b in fs.blocks.values() if b.name == "TB-501")
    hot, stack = stream(fs, "A14b-tail-hot"), stream(fs, "A15-stack")
    assert turbine.eq_type == "Turbine — gas (axial)"
    assert hot.temperature == pytest.approx(350)
    assert 25 < stack.temperature < hot.temperature
    assert stack.pressure_bar == pytest.approx(1.013)
    assert hot.pressure_bar == pytest.approx(11)
    assert turbine.duty < 0
    from stream_enthalpy import resolved_vapor_fraction, stream_enthalpy_kW
    for name in ("A8-gas-cool", "A12c-absorcion-reaccion", "A13-HNO3-crudo"):
        mixed = stream(fs, name)
        phases = mixed.component_vapor_fractions
        assert phases and all(c in phases for c, w in mixed.composition.items() if w > 0)
        expected_quality = sum(w * phases[c] for c, w in mixed.composition.items())
        assert resolved_vapor_fraction(mixed) == pytest.approx(expected_quality)
        assert 0 < expected_quality < 1
        assert stream_enthalpy_kW(mixed) is not None


@pytest.mark.parametrize("key,product", [
    ("hno3", "A13b-HNO3-producto"), ("quimpac", "S-naoh-50-producto"),
    ("chloralkali_hcl", "S-HCl-33")])
def test_products_scale_with_fresh_feeds_and_second_solve_is_stable(key, product):
    fs = plant(key)
    original = stream(fs, product)
    mass, composition = original.mass_flow, dict(original.composition)
    scaled = stream(plant(key, 1.5), product)
    assert scaled.mass_flow == pytest.approx(1.5 * mass, rel=2e-3)
    assert scaled.composition == pytest.approx(composition, rel=2e-3, abs=1e-8)
    flowsheet_solver.solve(fs)
    assert original.mass_flow == pytest.approx(mass, rel=2e-3)
    assert original.composition == pytest.approx(composition, rel=2e-3, abs=1e-8)


def test_chloralkali_products_obey_faradaic_and_stoichiometric_ratios():
    fs = plant("quimpac")
    chlorine = stream(fs, "S-cl2-liq")
    caustic = stream(fs, "S-naoh-50-producto")
    hydrogen = stream(fs, "S-h2")
    cl = chlorine.mass_flow * chlorine.composition["chlorine"]
    naoh = caustic.mass_flow * caustic.composition["sodium_hydroxide"]
    h2 = hydrogen.mass_flow * hydrogen.composition["hydrogen"]
    assert naoh / cl == pytest.approx(80 / 70.906, rel=1e-3)
    assert h2 / cl == pytest.approx(2.016 / 70.906, rel=1e-3)
    assert .49 <= caustic.composition["sodium_hydroxide"] <= .51
    cell = next(b for b in fs.blocks.values() if b.name == "R-201")
    watts = cell._electrical_work_kW
    expected_kWh_per_t = 2 * 96485.33212 * 3.2 / (.96 * 70.906 * 3.6)
    assert watts * 8760 / cl == pytest.approx(expected_kWh_per_t, rel=1e-3)
    assert cell.duty < 0, "cell needs cooling after the DC work is included"
    assert sum(s.energy_kW for s in fs.streams.values()
               if s.dst == cell.id and s.stream_kind == "energy") == pytest.approx(watts)


def test_chlorine_compression_and_caustic_boiling_point_have_equipment():
    fs = plant("quimpac")
    inlet, discharge = stream(fs, "S-cl2-dry"), stream(fs, "S-cl2-hp")
    assert discharge.pressure_bar > inlet.pressure_bar
    assert discharge.temperature > inlet.temperature
    assert stream(fs, "S-cl2-liq").temperature < discharge.temperature
    evaporate = stream(fs, "S-naoh-concentrada")
    assert evaporate.temperature == pytest.approx(143)
    assert evaporate.pressure_bar == pytest.approx(1.013)
    assert stream(fs, "S-naoh-50-producto").temperature == pytest.approx(50)


def test_compact_chloralkali_hcl_has_dynamic_chemistry_and_absorption_heat():
    fs = plant("chloralkali_hcl")
    cl_feed = stream(fs, "S-Cl2-rxn-lp")
    acid = stream(fs, "S-HCl-33")
    expected_hcl = cl_feed.mass_flow * cl_feed.composition["chlorine"] * (2*36.46/70.906)
    assert acid.mass_flow * acid.composition["hydrogen_chloride"] == pytest.approx(
        expected_hcl * .9995, rel=1e-3)
    assert .32 <= acid.composition["hydrogen_chloride"] <= .34
    assert acid.temperature < 40
    assert stream(fs, "S-absorbedor-vent").composition["hydrogen"] > .5
    cell = next(b for b in fs.blocks.values() if b.name == "R-101")
    absorber = next(b for b in fs.blocks.values() if b.name == "R-202-ABS")
    assert cell._electrical_work_kW > 0
    assert absorber.duty < -10, "the substantial HCl solution heat must be removed"
