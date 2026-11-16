"""Moist-air cooling towers conserve air, water and caloric enthalpy."""
import copy
import math

import pytest

from cooling_tower import cooling_tower_outputs, solve_cooling_towers, water_relative_humidity
from flowsheet_model import Block, Flowsheet, Stream
from stream_enthalpy import block_delta_h_kW


def fixture():
    block = Block(1, "CT", "Cooling tower — induced draft", 1,
                  cooling_tower_active=True, cooling_tower_blowdown_fraction=.01,
                  duty=0, duty_locked=True)
    ins = [Stream(2, "water", 0, 1, mass_flow=1e6, temperature=40,
                  composition={"water": 1.0}, phase="liquid"),
           Stream(3, "air", 0, 1, mass_flow=2e6, temperature=25,
                  composition={"nitrogen": .76032, "oxygen": .22968, "water": .01}, phase="gas")]
    outs = [Stream(4, "cold", 1, 0, src_port="agua_fria", temperature=28, phase="liquid"),
            Stream(5, "blowdown", 1, 0, src_port="blowdown", temperature=28, phase="liquid"),
            Stream(6, "exhaust", 1, 0, src_port="vapor_loss", temperature=32, phase="gas")]
    return block, ins, outs


def test_moist_air_balances_and_scale():
    block, ins, outs = fixture()
    amounts = cooling_tower_outputs(block, ins, outs)
    for name in ("water", "nitrogen", "oxygen"):
        assert sum(v.get(name, 0) for v in amounts.values()) == pytest.approx(
            sum(s.mass_flow * s.composition.get(name, 0) for s in ins))
    for s in outs:
        s.mass_flow = sum(amounts[s.id].values())
        s.composition = {name: m / s.mass_flow for name, m in amounts[s.id].items()}
    assert block_delta_h_kW(ins, outs) == pytest.approx(0, abs=1e-9)
    assert 0 < water_relative_humidity(outs[2].composition, 32, 1.013) < 1
    for s in ins:
        s.mass_flow *= 2
    doubled = cooling_tower_outputs(block, ins, outs)
    for sid, components in amounts.items():
        for name, mass in components.items():
            assert doubled[sid][name] == pytest.approx(2 * mass)


@pytest.mark.parametrize("case", ["inlet_humidity", "outlet_humidity", "bad_fraction", "unsupported_solute", "insufficient_makeup"])
def test_invalid_states_rejected_atomically(case):
    block, ins, outs = fixture()
    if case == "inlet_humidity":
        ins[1].composition = {"water": .5, "nitrogen": .5}
    elif case == "outlet_humidity":
        ins[1].mass_flow = 10000
    elif case == "bad_fraction":
        block.cooling_tower_blowdown_fraction = math.nan
    elif case == "unsupported_solute":
        ins[0].composition = {"water": .9, "ethanol": .1}
    else:
        block.cooling_tower_blowdown_fraction = None
        outs[0].mass_flow_locked = True
        outs[0].mass_flow = ins[0].mass_flow
    fs = Flowsheet()
    fs.blocks[1] = block
    fs.streams = {s.id: s for s in ins + outs}
    before = copy.deepcopy(outs)
    messages = solve_cooling_towers(fs)
    assert len(messages) == 1 and messages[0].startswith("✗ Cooling tower")
    assert outs == before


@pytest.mark.parametrize("key", ["cw_loop", "cw_natural"])
def test_catalogue_towers_have_real_humid_air_and_close_energy(key):
    import examples_registry
    import flowsheet_solver
    fs = examples_registry.load_example(key)
    result = flowsheet_solver.solve(fs)
    assert result.success, (result.energy_balance_errors, result.mass_balance_errors)
    assert not result.energy_balance_errors and not result.mass_balance_errors
    tower = next(b for b in fs.blocks.values() if b.cooling_tower_active)
    ins = [s for s in fs.streams.values() if s.dst == tower.id]
    outs = [s for s in fs.streams.values() if s.src == tower.id]
    assert abs(block_delta_h_kW(ins, outs)) < .01
    exhaust = next(s for s in outs if s.src_port == "vapor_loss")
    assert set(exhaust.composition) == {"water", "nitrogen", "oxygen"}
    assert exhaust.pressure_bar == pytest.approx(1.013)
    assert water_relative_humidity(exhaust.composition, exhaust.temperature, exhaust.pressure_bar) <= 1
    for name in ("water", "nitrogen", "oxygen"):
        assert sum(s.mass_flow * s.composition.get(name, 0) for s in outs) == pytest.approx(
            sum(s.mass_flow * s.composition.get(name, 0) for s in ins), rel=1e-7)
