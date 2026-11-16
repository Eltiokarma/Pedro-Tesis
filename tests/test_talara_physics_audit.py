"""Talara: independent conservation/response checks for the declared surrogate."""
import math
from collections import defaultdict

import pytest

from component_recovery import _canonical
from examples_registry import load_example
from flowsheet_model import Block, Stream
from flowsheet_solver import solve
from pseudocomponent_yields import lumped_yield_outputs
from stream_enthalpy import block_delta_h_kW, stream_enthalpy_kW


@pytest.fixture(scope="module")
def solved():
    fs = load_example("talara")
    return fs, solve(fs)


def totals(streams):
    result = defaultdict(float)
    for s in streams:
        for c, w in s.composition.items():
            result[_canonical(c)] += s.mass_flow * w
    return result


def block_streams(fs, block):
    return ([s for s in fs.streams.values() if s.dst == block.id],
            [s for s in fs.streams.values() if s.src == block.id])


def test_talara_closes_all_units_and_boundary_without_frozen_products(solved):
    fs, result = solved
    assert result.success, result.summary()
    assert not result.mass_balance_errors
    assert not result.energy_balance_errors
    assert not result.consistency_errors
    for block in fs.blocks.values():
        ins, outs = block_streams(fs, block)
        if ins and outs:
            assert sum(s.mass_flow for s in outs) == pytest.approx(
                sum(s.mass_flow for s in ins), rel=1e-9, abs=1e-7), block.name
            if not (block.reactions or block.custom_reactions or block.lumped_yield_active):
                tin, tout = totals(ins), totals(outs)
                for c in set(tin) | set(tout):
                    assert tout[c] == pytest.approx(tin[c], rel=1e-9, abs=1e-7), (block.name, c)
    feeds = [s for s in fs.streams.values() if s.role == "feed"]
    products = [s for s in fs.streams.values() if s.role in ("product", "waste")]
    assert sum(s.mass_flow for s in feeds) == pytest.approx(sum(s.mass_flow for s in products), rel=1e-10)
    assert all(not s.mass_flow_locked and not s.composition_locked
               for s in fs.streams.values() if s.role != "feed")
    assert all(s.mass_flow >= 0 and math.isfinite(s.mass_flow) for s in fs.streams.values())


def test_talara_all_feed_scaling_is_causal(solved):
    base, _ = solved
    fs = load_example("talara")
    for s in fs.streams.values():
        if s.role == "feed":
            s.mass_flow *= 1.25
    result = solve(fs)
    assert result.success, result.summary()
    for sid, s in fs.streams.items():
        assert s.mass_flow == pytest.approx(base.streams[sid].mass_flow * 1.25, rel=2e-8, abs=1e-7), s.name
    for bid, b in fs.blocks.items():
        assert b.duty == pytest.approx(base.blocks[bid].duty * 1.25, rel=2e-6, abs=.02), b.name


def test_talara_pressure_changes_have_equipment_and_work(solved):
    fs, _ = solved
    for block in fs.blocks.values():
        if any(kind in block.eq_type.lower() for kind in ("pump", "compressor")):
            ins, outs = block_streams(fs, block)
            assert min(s.pressure_bar for s in outs) > min(s.pressure_bar for s in ins), block.name
            assert block.duty > 0, block.name
        if "valve" in block.eq_type.lower():
            ins, outs = block_streams(fs, block)
            assert min(s.pressure_bar for s in outs) < min(s.pressure_bar for s in ins), block.name
            assert block.duty == pytest.approx(0., abs=1e-6), block.name
            assert block_delta_h_kW(ins, outs) == pytest.approx(0., abs=.1), block.name
    vacuum = next(b for b in fs.blocks.values() if b.name == "T-201")
    assert vacuum.P_op_bar == .08
    assert vacuum.component_recovery_active and not vacuum.splitter_active


def test_talara_hds_removes_existing_h2s_and_does_not_invent_hydrogen(solved):
    fs, _ = solved
    for name in ("R-HTN", "R-HTD", "R-HTF"):
        block = next(b for b in fs.blocks.values() if b.name == name)
        ins, outs = block_streams(fs, block)
        assert not block.reactions
        ti, to = totals(ins), totals(outs)
        for c in ("hydrogen", "hydrogen_sulfide"):
            c = _canonical(c)
            assert to[c] == pytest.approx(ti[c], rel=1e-10)
        acid = next(s for s in outs if "Gas-agrio" in s.name)
        sulfide = _canonical("hydrogen_sulfide")
        assert totals([acid])[sulfide] == pytest.approx(ti[sulfide] * .999)
        assert "org" in block.task_ref.lower()


def test_talara_smr_wgs_and_gasifier_elemental_balance(solved):
    import thermo_db
    fs, _ = solved
    atoms = {"carbon": {"C": 1}, "methane": {"C": 1, "H": 4},
             "water": {"H": 2, "O": 1}, "oxygen": {"O": 2},
             "nitrogen": {"N": 2}, "co": {"C": 1, "O": 1},
             "co2": {"C": 1, "O": 2}, "hydrogen": {"H": 2}}
    for name in ("R-SMR", "R-WGS", "R-GAS-FCK"):
        b = next(b for b in fs.blocks.values() if b.name == name)
        ins, outs = block_streams(fs, b)
        def elements(streams):
            values = defaultdict(float)
            for c, mass in totals(streams).items():
                for element, number in atoms[c].items():
                    values[element] += mass / thermo_db.get(c).mw * number
            return values
        ei, eo = elements(ins), elements(outs)
        for e in set(ei) | set(eo):
            # Published rounded molecular weights introduce ppm mass error.
            assert eo[e] == pytest.approx(ei[e], rel=2e-4, abs=1e-7), (name, e)
        assert all(stream_enthalpy_kW(s) is not None for s in ins + outs)


def test_talara_every_nonzero_stream_has_enthalpy(solved):
    fs, _ = solved
    for s in fs.streams.values():
        if s.mass_flow > 0:
            assert stream_enthalpy_kW(s) is not None, s.name
    for b in fs.blocks.values():
        ins, outs = block_streams(fs, b)
        if ins and outs and not (b.reactions or b.custom_reactions):
            if any(t in b.eq_type.lower() for t in ("pump", "compressor")):
                continue
            assert block_delta_h_kW(ins, outs) == pytest.approx(b.duty, rel=1e-6, abs=.1), b.name


def yield_fixture():
    b = Block(1, "Yield surrogate", "Reactor - jacketed agitated", 1,
              lumped_yield_active=True,
              lumped_yields={"crude_oil": {"naphtha": .8, "carbon": .2}},
              lumped_yield_basis="Illustrative mass yields, no molecular assay.",
              component_recoveries={"liquid": {"naphtha": 1}},
              component_recovery_default_port="other")
    ins = [Stream(2, "feed", 0, 1, mass_flow=100,
                  composition={"crude_oil": .9, "hydrogen": .1})]
    outs = [Stream(3, "liquid", 1, 0, src_port="liquid"),
            Stream(4, "other", 1, 0, src_port="other")]
    return b, ins, outs


def test_declared_yields_conserve_mass_and_real_cofeeds():
    b, ins, outs = yield_fixture()
    values = lumped_yield_outputs(b, ins, outs)
    assert values[3]["naphtha"] == pytest.approx(72)
    assert values[4]["carbon"] == pytest.approx(18)
    assert values[4]["hydrogen"] == pytest.approx(10)
    assert sum(sum(v.values()) for v in values.values()) == pytest.approx(100)


@pytest.mark.parametrize("bad", [-.2, .7, 1.2, math.nan, math.inf])
def test_declared_yields_reject_invalid_fractions(bad):
    b, ins, outs = yield_fixture()
    b.lumped_yields["crude_oil"]["naphtha"] = bad
    with pytest.raises(ValueError):
        lumped_yield_outputs(b, ins, outs)


def test_yields_cannot_transform_real_hydrogen_or_omit_basis():
    b, ins, outs = yield_fixture()
    b.lumped_yields = {"hydrogen": {"carbon": 1}}
    with pytest.raises(ValueError, match="petroleum"):
        lumped_yield_outputs(b, ins, outs)
    b, ins, outs = yield_fixture()
    b.lumped_yield_basis = ""
    with pytest.raises(ValueError, match="basis"):
        lumped_yield_outputs(b, ins, outs)
