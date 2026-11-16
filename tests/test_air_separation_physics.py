"""Cryogenic ASU: conservative performance model with feasible liquid states."""
import pytest

import eos
import examples_registry as reg
import flowsheet_solver as solver
import thermo_db as td


def _solve(scale=1.0):
    fs = reg.load_example("air_sep")
    for s in fs.streams.values():
        if s.role == "feed":
            s.mass_flow *= scale
    result = solver.solve(fs)
    assert result.success
    assert not result.mass_balance_errors
    assert not result.energy_balance_errors
    assert not result.consistency_errors
    return fs


def test_air_separation_conserves_species_and_scales_products():
    fs = _solve()
    scaled = _solve(1.2)
    feeds = [s for s in fs.streams.values() if s.role == "feed"]
    outputs = [s for s in fs.streams.values() if s.role in ("product", "waste")]
    for name in ("nitrogen", "oxygen", "water"):
        incoming = sum(s.mass_flow * s.composition.get(name, 0) for s in feeds)
        outgoing = sum(s.mass_flow * s.composition.get(name, 0) for s in outputs)
        assert outgoing == pytest.approx(incoming, rel=1e-10, abs=1e-9)
    for out in outputs:
        assert not out.mass_flow_locked and not out.composition_locked
        other = next(s for s in scaled.streams.values() if s.name == out.name)
        assert other.mass_flow == pytest.approx(1.2 * out.mass_flow, rel=1e-9)
    dry = next(s for s in fs.streams.values() if s.name == "S-pure")
    assert dry.composition.get("water", 0) == 0


def test_air_separation_liquids_below_critical_and_pr_stable():
    fs = _solve()
    for s in fs.streams.values():
        if s.name not in ("S-cryo", "S-N2-liquido", "S-O2-liquido"):
            continue
        assert s.phase == "liquid"
        names = list(s.composition)
        moles = [s.composition[n] / td.get(n).mw for n in names]
        total = sum(moles)
        for name in names:
            assert s.temperature < td.get(name).tc_c
        flash = eos.flash_TP_eos(names, [n / total for n in moles],
                                 s.temperature + 273.15, s.pressure_bar)
        assert flash is not None
        assert flash["V_frac"] == 0.0


def test_air_separation_external_refrigeration_is_not_fake_nh3_service():
    fs = _solve()
    cryo = next(b for b in fs.blocks.values() if b.name.startswith("E-102"))
    box = next(b for b in fs.blocks.values() if b.name.startswith("CB-101"))
    assert cryo.duty < 0
    # At 1000 t/y, 15 K subcooling is order 1 kW, not the >100 kW
    # produced by extrapolating nonexistent liquid nitrogen to 25 C.
    assert -5.0 < box.duty < 0.0
    assert box.component_recovery_active and not box.column_active
    for b in (cryo, box):
        assert b.heat_source_locked and b.heat_source == ""
    discharge = next(s for s in fs.streams.values() if s.name == "S-HP")
    assert not discharge.temperature_locked and discharge.temperature > 25
