"""T29a — Reacción HDA (hidrodealquilación de tolueno) en reactions_db.

Verifica que R035 existe, es termodinámicamente consistente (ΔH derivado de
los ΔHf de thermo_db por Hess coincide con el valor declarado) y que el motor
puede aplicarla a un reactor sintético produciendo benzene+methane por balance
con duty exotérmico.  NO toca hda/hda_full (eso es T29b/c)."""
import math
import pytest

import reactions_db as rdb
import thermo_db as tdb


def test_r035_existe_y_es_hda():
    r = rdb.get("R035")
    assert r is not None
    assert "HDA" in r.name or "idrodealquila" in r.name
    stoich = {s.formula: s.nu for s in r.stoich}
    # C7H8 + H2 → C6H6 + CH4  (Δν = 0, todo gas)
    assert stoich == {"C7H8": -1, "H2": -1, "C6H6": 1, "CH4": 1}
    assert r.delta_nu == 0
    assert r.phase_global == "gas"
    assert r.origin == "curated"
    assert r.irreversible is True
    assert r.kinetics_available is False        # sin fuente cinética citada


def test_find_by_species_toluene_encuentra_hda():
    ids = [x.id for x in rdb.find_by_species("toluene")]
    assert "R035" in ids
    # benzene también la incluye (es producto)
    assert "R035" in [x.id for x in rdb.find_by_species("benzene")]


def test_mapeo_formula_thermo_de_los_4():
    """FASE 0.4: las 4 especies de la HDA mapean formula↔thermo_db."""
    assert rdb.thermo_name("C7H8") == "toluene"      # antes daba 'c7h8' (roto)
    assert rdb.thermo_name("C6H6") == "benzene"
    assert rdb.thermo_name("H2") == "hydrogen"
    assert rdb.thermo_name("CH4") == "methane"
    # inverso (lo usa el flowsheet: composition usa nombres canónicos)
    assert rdb.formula_for("toluene") == "C7H8"


def test_dh_rxn_298_consistente_con_hess():
    """La ΔH declarada (−42.11) debe coincidir con el recálculo independiente
    Σνᵢ·ΔHf_i desde thermo_db.  Esto valida la consistencia termodinámica."""
    hess = ((tdb.get("benzene").dh_f_gas_kJ_mol
             + tdb.get("methane").dh_f_gas_kJ_mol)
            - (tdb.get("toluene").dh_f_gas_kJ_mol
               + tdb.get("hydrogen").dh_f_gas_kJ_mol))
    assert math.isclose(hess, -42.11, abs_tol=0.05)
    # el motor a 298 K devuelve el ΔH declarado…
    motor = rdb.dh_rxn_kJ_mol("R035", 298.15)
    assert math.isclose(motor, -42.11, abs_tol=0.05)
    # …y coincide con el Hess independiente (consistencia)
    assert math.isclose(motor, hess, abs_tol=0.05)


def test_dh_rxn_corrige_con_temperatura():
    """Con el mapeo C7H8→toluene activo, la integral ΔCp_rxn opera: ΔH(T) se
    aparta de ΔH(298).  (Antes, con C7H8 sin mapear, devolvía siempre −42.11.)"""
    dh900 = rdb.dh_rxn_kJ_mol("R035", 900.0)
    assert dh900 is not None
    assert not math.isclose(dh900, -42.11, abs_tol=0.5)   # ΔCp activo
    assert dh900 < 0                                       # sigue exotérmica


def test_reactor_sintetico_hda_balance_y_duty():
    """FASE 2.3: reactor sintético tolueno+H2 (5:1) con conversión declarada
    produce benzene+methane por balance, conserva masa y da duty exotérmico.
    NO toca hda/hda_full."""
    mw_t = tdb.get("toluene").mw
    mw_h = tdb.get("hydrogen").mw
    m_t, m_h = 1 * mw_t, 5 * mw_h                 # molar 1:5 → másico
    tot = m_t + m_h
    comp = {"toluene": m_t / tot, "hydrogen": m_h / tot}
    res = rdb.solve_stoichiometric_reactor(
        ["R035"], comp, inlet_mass_kg_s=10.0,
        T_K=900.0, P_bar=35.0, conversion=0.5)
    assert res is not None
    out = res["outlet_composition"]
    # productos aparecen, tolueno baja
    assert out.get("benzene", 0) > 0
    assert out.get("methane", 0) > 0
    assert out["toluene"] < comp["toluene"]
    # masa conservada (la holgura ~1e-5 es redondeo de MW en la estequiometría)
    assert math.isclose(res["outlet_mass_kg_s"], 10.0, rel_tol=1e-3)
    # exotérmica
    assert res["duty_kW"] < 0
    assert res["heat_of_reaction_kJ_per_kg"] < 0
    assert res["unmapped"] == []                  # las 4 especies mapean
