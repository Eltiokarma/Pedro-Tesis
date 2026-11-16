"""Physical regressions for the integrated methanol/steam/CW example."""
import math

import pytest
import examples_registry
import flowsheet_solver
from stream_enthalpy import stream_enthalpy_kW


def solved(scale=1.0):
    fs = examples_registry.load_example('industrial')
    for stream in fs.streams.values():
        if stream.role == 'feed':
            stream.mass_flow *= scale
    result = flowsheet_solver.solve(fs)
    assert result.success, (result.mass_balance_errors,
                            result.energy_balance_errors,
                            result.consistency_errors)
    assert all(r.converged for r in result.recycle_solutions)
    return fs


def test_integrated_boundary_mass_and_product_scaling():
    fs = solved()
    incoming = {s.dst for s in fs.streams.values()}
    outgoing = {s.src for s in fs.streams.values()}
    feed = sum(s.mass_flow for s in fs.streams.values()
               if s.src == 0 or s.src not in incoming)
    product = sum(s.mass_flow for s in fs.streams.values()
                  if s.dst == 0 or s.dst not in outgoing)
    assert product == pytest.approx(feed, rel=1e-4)
    twice = solved(2.0)
    a = next(s for s in fs.streams.values() if s.name == 'S-MeOH')
    b = next(s for s in twice.streams.values() if s.name == 'S-MeOH')
    assert a.mass_flow > 0
    assert b.mass_flow == pytest.approx(2 * a.mass_flow, rel=1e-3)


def test_steam_and_cooling_water_are_demand_driven_and_close_energy():
    fs = solved()
    for name in ('E-102', 'E-103'):
        block = next(b for b in fs.blocks.values() if b.name == name)
        ins = [s for s in fs.streams.values() if s.dst == block.id]
        outs = [s for s in fs.streams.values() if s.src == block.id]
        assert len(ins) == len(outs) == 2
        hin = sum(stream_enthalpy_kW(s) for s in ins)
        hout = sum(stream_enthalpy_kW(s) for s in outs)
        assert abs(hout - hin) <= 1e-4 * max(abs(hin), abs(hout), 1)
        assert abs(block.duty) < 1e-5  # heat exchange internal to these four ports
        utility = next(s for s in ins if s.role == 'utility')
        assert utility.mass_flow > 0 and not utility.mass_flow_locked


def test_pressure_reduction_is_explicit_and_boiler_has_two_real_products():
    fs = solved()
    streams = {s.name:s for s in fs.streams.values()}
    assert streams['S-crude'].pressure_bar > 70
    assert streams['S-degassed'].pressure_bar == pytest.approx(1.5, abs=0.05)
    assert streams['S-BFW-feed'].temperature < 100
    assert streams['S-MP-supply'].phase == 'vapor'
    assert streams['S-MP-supply'].pressure_bar == pytest.approx(30)
    boiler = next(b for b in fs.blocks.values() if b.name == 'F-301')
    outputs = [s for s in fs.streams.values() if s.src == boiler.id]
    assert {s.phase for s in outputs} == {'liquid', 'vapor'}
    assert boiler.duty > 0 and math.isfinite(boiler.duty)
