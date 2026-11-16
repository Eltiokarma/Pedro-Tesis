"""Sulfuric-acid product follows reactive absorption and conserves atoms."""
import pytest
import examples_registry as registry
import flowsheet_solver as solver
import reactions_db as reactions


def solved(scale=1):
    fs = registry.load_example("sulfuric")
    for s in fs.streams.values():
        if s.role == "feed":
            s.mass_flow *= scale
    result = solver.solve(fs)
    assert result.success, (result.mass_balance_errors, result.energy_balance_errors,
                            result.consistency_errors)
    return fs


def component_flow(streams, name):
    return sum(s.mass_flow * s.composition.get(name, 0) for s in streams)


def test_absorption_reacts_instead_of_inventing_acid():
    fs = solved()
    rx = next(b for b in fs.blocks.values() if "R032" in b.reactions)
    inputs = [s for s in fs.streams.values() if s.dst == rx.id]
    outputs = [s for s in fs.streams.values() if s.src == rx.id]
    consumed = ((component_flow(inputs, "sulfur_trioxide") -
                 component_flow(outputs, "sulfur_trioxide")) /
                reactions.component_for_mass("sulfur_trioxide").mw)
    produced = component_flow(outputs, "sulfuric_acid") / reactions.component_for_mass("sulfuric_acid").mw
    assert consumed > 0
    assert produced == pytest.approx(consumed, rel=1e-4)
    feeds = [s for s in fs.streams.values() if s.role == "feed"]
    exits = [s for s in fs.streams.values() if s.role in ("product", "waste")]
    assert sum(s.mass_flow for s in exits) == pytest.approx(sum(s.mass_flow for s in feeds), rel=1e-8)
    assert component_flow(exits, "nitrogen") == pytest.approx(component_flow(feeds, "nitrogen"), rel=1e-4)


def test_acid_product_scales_with_feed_without_frozen_output():
    base, larger = solved(), solved(1.3)
    p0 = next(s for s in base.streams.values() if s.name == "S-H2SO4")
    p1 = next(s for s in larger.streams.values() if s.name == "S-H2SO4")
    assert p1.mass_flow == pytest.approx(p0.mass_flow * 1.3, rel=1e-8)
    assert p1.composition == pytest.approx(p0.composition, rel=1e-8)
