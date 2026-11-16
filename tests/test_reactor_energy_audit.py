"""Independent reaction-energy, coupled stoichiometry and failure regressions."""
import math

import pytest
from scipy.integrate import quad

import flowsheet_model as fm
import flowsheet_solver as solver
import reactions_db as rdb
import thermo_db as td
from reactor_calorics import reaction_reference_heat_kW
from stream_enthalpy import stream_enthalpy_kW


def reactor_fs(rid="R035", temperature_K=800.0, adiabatic=False):
    r = rdb.get(rid)
    feed_mass = {sp.thermo_name: -sp.nu * rdb.component_for_mass(sp.thermo_name).mw
                 for sp in r.stoich if sp.nu < 0}
    total = sum(feed_mass.values())
    fs = fm.Flowsheet()
    block = fm.Block(id=1, name="reactor", eq_type="Reactor - jacketed agitated",
                     S=10, reactions=[rid], reactor_mode="stoich",
                     reactor_conversion=0.5, T_op_K=0 if adiabatic else temperature_K,
                     P_op_bar=1.01325)
    feed = fm.Stream(id=2, name="feed", src=0, dst=1, role="feed",
                     mass_flow=fm.SEC_PER_YEAR/fm.TM_TO_KG,
                     temperature=temperature_K-273.15, phase="gas",
                     mass_flow_locked=True, temperature_locked=True,
                     phase_locked=True, composition_locked=True,
                     composition={name: value/total for name, value in feed_mass.items()})
    product = fm.Stream(id=3, name="product", src=1, dst=0, role="product",
                        phase="gas", phase_locked=True)
    fs.blocks[1] = block
    fs.streams = {2: feed, 3: product}
    return fs, block, feed, product


def test_isothermal_heat_counts_kirchhoff_correction_once():
    fs, block, feed, product = reactor_fs()
    messages = solver.solve_equilibrium_reactors(fs)
    assert not any(m.startswith("❌") for m in messages), messages
    rxn = rdb.get("R035")
    extent = 0.5 * feed.composition["toluene"] * 1000 / td.get("toluene").mw
    # Independent integral of the individual species Cp, no stream enthalpy
    # or solver duty used to construct the expected answer.
    delta_cp_integral = sum(
        sp.nu * quad(lambda t: td.get(sp.thermo_name).cp_J_mol_K(t, "gas"),
                     298.15, 800.0)[0] / 1000
        for sp in rxn.stoich)
    expected = extent * (rxn.dh_rxn_298_kJ_mol + delta_cp_integral)
    assert block.duty == pytest.approx(expected, rel=2e-4)
    assert product.composition["benzene"] > 0


def test_adiabatic_reactor_solves_actual_energy_residual():
    fs, block, feed, product = reactor_fs(temperature_K=700, adiabatic=True)
    messages = solver.solve_equilibrium_reactors(fs)
    assert not any(m.startswith("❌") for m in messages), messages
    assert block.duty == 0
    assert product.temperature > feed.temperature
    residual = (stream_enthalpy_kW(product) - stream_enthalpy_kW(feed)
                + block.heat_of_reaction)
    assert abs(residual) < 1e-4


def test_no_silent_custom_reaction_or_cache_leak():
    fs, block, feed, product = reactor_fs()
    block.reactions = []
    block.custom_reactions = [{"id": "TEMP", "name": "HDA",
        "stoich": [{"formula": sp.formula, "phase": sp.phase, "nu": sp.nu}
                   for sp in rdb.get("R035").stoich],
        "dh_rxn_298_kJ_mol": -42.0, "irreversible": True}]
    assert not any(m.startswith("❌") for m in solver.solve_equilibrium_reactors(fs))
    assert rdb.get("_BLOCK1_CUSTOM0") is None
    block.reactions = ["MISSING-REACTION"]
    assert any(m.startswith("❌") for m in solver.solve_equilibrium_reactors(fs))


def test_fixed_product_composition_cannot_override_stoichiometry():
    fs, block, feed, product = reactor_fs()
    product.composition = {"water": 1.0}
    product.composition_locked = True
    solver.solve_equilibrium_reactors(fs)
    assert "water" not in product.composition
    assert product.composition["benzene"] > 0


def test_multiple_reaction_extents_use_all_species():
    initial = {"CH4": 10.0, "H2O": 20.0, "CO": 1.0, "H2": 0.0, "CO2": 0.0}
    final = dict(initial)
    expected = {"R003": 2.0, "R002": 0.7}
    for rid, extent in expected.items():
        for sp in rdb.get(rid).stoich:
            final[sp.formula] = final.get(sp.formula, 0) + sp.nu * extent
    assert rdb.reaction_extents_from_species(list(expected), initial, final) == pytest.approx(expected)
    final["H2"] += 1.0
    assert rdb.reaction_extents_from_species(list(expected), initial, final) is None


def test_salt_molecular_masses_and_species_aliases_are_available():
    assert rdb.component_for_mass("sodium_chloride").mw == pytest.approx(58.44)
    assert rdb.component_for_mass("sodium_hydroxide").mw == pytest.approx(40.0, rel=1e-3)
    assert rdb.formula_for("nitric oxide") == "NO"
    assert rdb.formula_for("nitrogen dioxide") == "NO2"


def test_batch_unmapped_inert_is_not_lost(monkeypatch):
    monkeypatch.setattr(rdb, "_check_kinetics_compatibility", lambda ids: None)
    monkeypatch.setattr(rdb.Reaction, "is_kinetic_T_valid", lambda self, temperature: True)
    # Isolate the mass bridge from kinetic integration: no conversion.
    def unchanged_batch(ids, n_in, temperature, pressure, volume, duration, **kwargs):
        return {"N_out": dict(n_in)}
    monkeypatch.setattr(rdb, "solve_batch", unchanged_batch)
    result = rdb.solve_batch_from_composition(
        ["R011"], {"ethane": 0.6, "uncharacterized_inert": 0.4},
        inlet_mass_kg_s=2.0, T_K=1100, P_bar=1,
        V_reactor_L=100, t_batch_s=10)
    assert result is not None
    assert result["outlet_mass_kg_s"] == pytest.approx(2.0)
    assert result["outlet_composition"]["uncharacterized_inert"] == pytest.approx(0.4)
    assert result["xi"]["R011"] == pytest.approx(0.0)


def test_adiabatic_over_specification_is_reported():
    fs, block, feed, product = reactor_fs(adiabatic=True)
    product.temperature_locked = True
    product.temperature = 500
    messages = solver.solve_equilibrium_reactors(fs)
    assert any("adiabático" in m and m.startswith("❌") for m in messages)


def test_electrolysis_work_is_explicit_and_not_counted_as_heat():
    fs, block, feed, product = reactor_fs(temperature_K=353.15)
    block.reactions = []
    block.custom_reactions = [{"id": "CELL", "name": "Membrane cell",
        "stoich": [
            {"formula": "NaCl", "phase": "aq", "nu": -2},
            {"formula": "H2O", "phase": "l", "nu": -2},
            {"formula": "NaOH", "phase": "aq", "nu": 2},
            {"formula": "H2", "phase": "g", "nu": 1},
            {"formula": "Cl2", "phase": "g", "nu": 1}],
        "dh_rxn_298_kJ_mol": 456.8, "irreversible": True}]
    block.electrolysis_voltage_V = 3.2
    block.electrolysis_current_efficiency = 0.96
    block.electrolysis_electrons_per_extent = 2
    feed.composition = {"sodium_chloride": 0.26, "water": 0.74}
    feed.phase = product.phase = "liquid"
    power = fm.Stream(id=4, name="electricity", src=0, dst=1,
                      stream_kind="energy", role="utility")
    fs.streams[4] = power
    messages = solver.solve_equilibrium_reactors(fs)
    assert not any(m.startswith("❌") for m in messages), messages
    extent = (0.26 * 1000 / 58.44 / 2) * block.reactor_conversion
    expected_work = extent * 2 * 96485.33212 * 3.2 / 0.96 / 1000
    assert power.energy_kW == pytest.approx(expected_work, rel=1e-10)
    assert block._electrical_work_kW == power.energy_kW
    assert block.duty < 0
    assert block.duty + power.energy_kW == pytest.approx(
        stream_enthalpy_kW(product) - stream_enthalpy_kW(feed)
        + block.heat_of_reaction, abs=1e-5)
