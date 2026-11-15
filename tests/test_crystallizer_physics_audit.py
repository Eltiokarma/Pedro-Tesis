"""Crystals must come from supersaturation, with conserved dissolved mother."""
import math

import pytest

import examples_registry as registry
import flowsheet_model as fm
import flowsheet_solver as solver


def simple_crystallizer(salt_fraction=.28, yield_=1.0):
    fs = fm.Flowsheet()
    fs.blocks[1] = fm.Block(
        id=1, name='CR', eq_type='Crystallizer', S=1, T_op_K=295,
        crystallizer_active=True, solute_component='sodium chloride',
        crystal_yield=yield_, crystallizer_solubility_kg_per_kg_solvent=.35893848)
    fs.streams = {
        2: fm.Stream(id=2, name='feed', src=0, dst=1, role='feed', mass_flow=1000,
                     composition={'sodium_chloride':salt_fraction,'water':1-salt_fraction}),
        3: fm.Stream(id=3, name='salt', src=1, dst=0, src_port='producto'),
        4: fm.Stream(id=4, name='mother', src=1, dst=0, src_port='venteo'),
    }
    return fs


def assert_success(messages):
    assert not any(message.startswith('❌') for message in messages), messages


def test_undersaturated_brine_cannot_form_crystals():
    fs = simple_crystallizer(.26)
    assert_success(solver.solve_crystallizers(fs))
    assert fs.streams[3].mass_flow == 0
    assert fs.streams[3].phase == 'solid'
    assert fs.streams[4].mass_flow == 1000
    assert fs.streams[4].composition == pytest.approx(fs.streams[2].composition)


def test_yield_applies_only_to_available_supersaturation_and_accepts_alias():
    fs = simple_crystallizer(yield_=.5)
    assert_success(solver.solve_crystallizers(fs))
    salt, mother = fs.streams[3], fs.streams[4]
    equilibrium_crystals = 280 - .35893848 * 720
    assert salt.mass_flow == pytest.approx(.5 * equilibrium_crystals)
    assert salt.phase == 'solid' and salt.composition == {'sodium_chloride': 1}
    assert mother.mass_flow * mother.composition['water'] == pytest.approx(720)
    assert mother.mass_flow * mother.composition['sodium_chloride'] + salt.mass_flow == pytest.approx(280)


def test_missing_mother_outlet_is_an_explicit_failure():
    fs = simple_crystallizer()
    del fs.streams[4]
    messages = solver.solve_crystallizers(fs)
    assert any(message.startswith('❌') and 'two connected outlets' in message for message in messages)


@pytest.mark.parametrize('field,value', [
    ('crystal_yield', 1.01), ('crystal_yield', math.nan),
    ('crystallizer_solubility_kg_per_kg_solvent', -.1), ('T_op_K', 0),
    ('crystallizer_solvent_component', 'sodium_chloride'),
])
def test_invalid_crystallization_specs_fail_without_clamping(field, value):
    fs = simple_crystallizer()
    setattr(fs.blocks[1], field, value)
    assert any(m.startswith('❌') for m in solver.solve_crystallizers(fs))


def test_legacy_empirical_yield_has_explicit_qualification():
    fs = simple_crystallizer(yield_=.5)
    fs.blocks[1].crystallizer_solubility_kg_per_kg_solvent = None
    messages = solver.solve_crystallizers(fs)
    assert_success(messages)
    assert any('no solubility prediction' in m for m in messages)
    assert fs.streams[3].mass_flow == pytest.approx(140)


def test_salt_example_evaporates_then_cools_to_saturated_mother_and_scales():
    product_masses = []
    for scale in (1, 1.5):
        fs = registry.load_example('salt_crystal')
        feed = next(s for s in fs.streams.values() if s.role == 'feed')
        feed.mass_flow *= scale
        result = solver.solve(fs)
        assert result.success, (result.mass_balance_errors, result.energy_balance_errors,
                                result.consistency_errors)
        assert not result.energy_warnings
        crystal = next(b for b in fs.blocks.values() if b.crystallizer_active)
        evaporator = next(b for b in fs.blocks.values() if b.evaporator_active)
        salt = next(s for s in fs.streams.values() if s.name == 'S-salt')
        mother = next(s for s in fs.streams.values() if s.name == 'S-mother')
        vapor = next(s for s in fs.streams.values() if s.name == 'S-evap-water')
        # IUPAC2022 Table7: 6.142 mol/kg water at295 K; salt MW58.44g/mol.
        assert mother.composition['sodium_chloride']/mother.composition['water'] == pytest.approx(6.142*.05844)
        assert salt.temperature + 273.15 == pytest.approx(295)
        assert salt.phase == 'solid' and salt.mass_flow > 0
        assert salt.mass_flow < .1 * feed.mass_flow * feed.composition['sodium_chloride']
        assert vapor.mass_flow > 0 and vapor.composition == {'water':1}
        assert evaporator.duty > 0 and crystal.duty < 0
        exits = [s for s in fs.streams.values() if s.role in ('product', 'waste')]
        for species in ('water', 'sodium_chloride'):
            assert sum(s.mass_flow * s.composition.get(species, 0) for s in exits) == pytest.approx(
                feed.mass_flow * feed.composition[species], rel=1e-9)
        product_masses.append(salt.mass_flow)
        reloaded = fm.Flowsheet.from_dict(fs.to_dict())
        assert reloaded.blocks[crystal.id].crystallizer_solubility_kg_per_kg_solvent == pytest.approx(.35893848)
    assert product_masses[1] == pytest.approx(1.5 * product_masses[0])
