"""Industrial chemistry examples use real reactions and feed-derived products."""
import pytest
import examples_registry as registry
import flowsheet_solver as solver
import reactions_db as reactions


def solve_case(key, factor=1.0):
    fs = registry.load_example(key)
    for stream in fs.streams.values():
        if stream.role == "feed":
            stream.mass_flow *= factor
    result = solver.solve(fs)
    assert result.success, (result.mass_balance_errors, result.energy_balance_errors,
                            result.consistency_errors)
    return fs


@pytest.mark.parametrize("key", ["ldpe", "urea", "soap", "cement"])
def test_live_reactive_products_conserve_mass_and_scale(key):
    base = solve_case(key)
    scaled = solve_case(key, 1.4)
    for fs in (base, scaled):
        feeds = sum(s.mass_flow for s in fs.streams.values() if s.role == "feed")
        exits = sum(s.mass_flow for s in fs.streams.values() if s.role in ("product", "waste"))
        assert exits == pytest.approx(feeds, rel=1e-8)
        assert all(not any("PLACEHOLDER" in rid for rid in b.reactions)
                   for b in fs.blocks.values())
    products = {s.name: s for s in base.streams.values() if s.role == "product"}
    for stream in scaled.streams.values():
        if stream.role == "product":
            assert stream.mass_flow == pytest.approx(products[stream.name].mass_flow * 1.4, rel=1e-8)


def test_polymerization_uses_repeat_unit_mass_not_chain_mass():
    fs = solve_case("ldpe")
    polymer = next(s for s in fs.streams.values() if s.name == "S-PE")
    ethylene = next(s for s in fs.streams.values() if s.name == "S-eth")
    reactor = next(b for b in fs.blocks.values() if "R027" in b.reactions)
    assert polymer.mass_flow == pytest.approx(ethylene.mass_flow * reactor.reactor_conversion)
    assert reactions.component_for_mass("polyethylene").mw == reactions.component_for_mass("ethylene").mw
    assert polymer.phase == "solid" and polymer.pressure_bar < 2
    assert len([b for b in fs.blocks.values() if b.eq_type.startswith("Compressor")]) == 3


def test_soap_surrogate_is_atom_balanced_and_named():
    fs = solve_case("soap")
    reactor = next(b for b in fs.blocks.values() if b.custom_reactions)
    reaction = reactions.reaction_from_dict(reactor.custom_reactions[0])
    reactions._check_element_balance([
        reactions.StoichEntry(**entry) for entry in reactor.custom_reactions[0]["stoich"]])
    soap = next(s for s in fs.streams.values() if s.name == "S-soap")
    assert soap.composition.get("sodium_oleate", 0) > 0.99
    assert "soap" not in soap.composition


def test_limestone_only_feed_produces_lime_not_clinker():
    fs = solve_case("cement")
    assert all("clinker" not in s.composition for s in fs.streams.values())
    product = next(s for s in fs.streams.values() if s.role == "product")
    assert product.composition["quicklime"] > 0.95
    co2 = next(s for s in fs.streams.values() if s.name == "S-CO2-emit")
    lime_mol = product.mass_flow * product.composition["quicklime"] / reactions.component_for_mass("quicklime").mw
    gas_mol = co2.mass_flow / reactions.component_for_mass("co2").mw
    assert lime_mol == pytest.approx(gas_mol, rel=1e-4)


def test_urea_compresses_co2_separately_from_liquid_ammonia():
    fs = solve_case("urea")
    compressors = [b for b in fs.blocks.values() if b.eq_type.startswith("Compressor")]
    assert len(compressors) == 4
    for b in compressors:
        inlet = next(s for s in fs.streams.values() if s.dst == b.id)
        outlet = next(s for s in fs.streams.values() if s.src == b.id)
        assert inlet.phase == "gas"
        assert inlet.composition == pytest.approx({"co2": 1.0})
        assert outlet.pressure_bar > inlet.pressure_bar
        assert outlet.temperature > inlet.temperature
        assert b.duty > 0
    ammonia = next(s for s in fs.streams.values() if s.name == "S-NH3")
    assert ammonia.phase == "liquid" and ammonia.pressure_bar >= 10
    assert fs.blocks[ammonia.dst].eq_type.startswith("Pump")
