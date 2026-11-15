"""Process-level conservation and response, independent of frozen economics.

Recovery factors are declared performance specifications. These tests establish
conservation and response to feed changes, not validation against plant data.
"""
import math

import pytest

import examples_registry as reg
import flowsheet_solver as solver


KEYS = ('hda_full', 'gas_sweet', 'sugar', 'leche_gloria',
        'glass', 'water_treat', 'penicillin')


def solved(key, scale=1.0):
    fs = reg.load_example(key)
    if scale != 1:
        for stream in fs.streams.values():
            # Scaling the plant includes its independent solvent circulation
            # specification. All product flows remain calculated.
            if stream.mass_flow_locked:
                stream.mass_flow *= scale
    result = solver.solve(fs)
    assert result.success, (key, result.summary())
    assert not result.mass_balance_errors, (key, result.mass_balance_errors)
    assert not result.energy_balance_errors, (key, result.energy_balance_errors)
    assert not result.consistency_errors, (key, result.consistency_errors)
    assert not result.unresolved_streams, (key, result.unresolved_streams)
    assert all(rec.converged for rec in result.recycle_solutions)
    return fs, result


def external_mass(fs):
    outgoing_blocks = {s.src for s in fs.streams.values() if s.stream_kind == 'mass'}
    m_in = m_out = 0.0
    for s in fs.streams.values():
        if s.stream_kind != 'mass':
            continue
        if s.role == 'feed':
            m_in += s.mass_flow
        elif (s.dst not in fs.blocks or s.dst not in outgoing_blocks):
            m_out += s.mass_flow
    return m_in, m_out


@pytest.mark.parametrize('key', KEYS)
def test_industrial_examples_conserve_mass_and_have_finite_states(key):
    fs, _ = solved(key)
    m_in, m_out = external_mass(fs)
    assert m_out == pytest.approx(m_in, rel=1e-4), (key, m_in, m_out)
    for s in fs.streams.values():
        if s.stream_kind != 'mass' or s.mass_flow <= 1e-8:
            continue
        assert math.isfinite(s.mass_flow) and s.mass_flow >= 0
        assert math.isfinite(s.temperature) and s.temperature > -273.15
        assert math.isfinite(s.pressure_bar) and s.pressure_bar > 0
        assert s.composition, (key, s.name)
        assert sum(s.composition.values()) == pytest.approx(1, abs=1e-7)
        assert all(math.isfinite(w) and w >= 0 for w in s.composition.values())


@pytest.mark.parametrize('key', KEYS)
def test_products_respond_to_plant_feed_scaling(key):
    base, _ = solved(key)
    larger, _ = solved(key, scale=1.2)
    products = [s for s in base.streams.values() if s.role == 'product']
    assert products
    for before in products:
        after = larger.streams[before.id]
        assert before.mass_flow > 0
        assert not after.mass_flow_locked
        assert after.mass_flow == pytest.approx(1.2 * before.mass_flow, rel=2e-3)


def test_milk_fat_is_separated_and_evaporated_solids_are_conserved():
    fs, _ = solved('leche_gloria')
    by_name = {s.name: s for s in fs.streams.values()}
    assert by_name['S-crema-total'].composition['milk_fat'] == pytest.approx(.4)
    assert by_name['S-manteq'].composition['milk_fat'] == pytest.approx(.82)
    assert by_name['S-fluida'].composition['milk_fat'] == pytest.approx(.03, abs=.001)
    assert 1 - by_name['S-evap'].composition['water'] == pytest.approx(.26)
    for name in ('S-vap-1-a-condensacion', 'S-vap-2-a-condensacion'):
        assert by_name[name].composition == {'water': 1.0}
    assert by_name['S-conc-esterilizada'].temperature == 140
    assert by_name['S-conc-esterilizada'].pressure_bar == 4


def test_sugar_clarifier_cannot_create_petroleum_residue():
    fs, _ = solved('sugar')
    by_name = {s.name: s for s in fs.streams.values()}
    assert 'limestone' in by_name['S-jugo'].composition
    assert all('atmospheric_residue' not in s.composition for s in fs.streams.values())
    assert by_name['S-cachaza'].mass_flow == pytest.approx(20000)
    for b in fs.blocks.values():
        if b.evaporator_active:
            outs = [s for s in fs.streams.values() if s.src == b.id]
            assert len({s.temperature for s in outs}) == 1
            assert len({s.pressure_bar for s in outs}) == 1


def test_amine_makeup_has_a_matching_purge_and_physical_letdowns():
    fs, _ = solved('gas_sweet')
    by_name = {s.name: s for s in fs.streams.values()}
    assert by_name['S-purga-amina'].mass_flow == pytest.approx(by_name['S-makeup'].mass_flow, rel=1e-4)
    assert by_name['S-gas-dulce'].composition['h2s'] < 1e-5
    assert by_name['S-rich-amine'].pressure_bar > by_name['S-rich-amine-out'].pressure_bar
    assert by_name['S-rich-hot'].pressure_bar > by_name['S-rich-hot-out'].pressure_bar
    assert by_name['S-lean-warm'].composition == pytest.approx(by_name['S-lean-hot'].composition)


def test_glass_carbonate_offgas_is_derived_from_each_carbonate_feed():
    fs, _ = solved('glass')
    streams = {s.name: s for s in fs.streams.values()}
    expected = (streams['S-lime'].mass_flow * 44.0095 / 100.09
                + streams['S-soda'].mass_flow * 44.0095 / 105.99)
    assert streams['S-CO2'].mass_flow == pytest.approx(expected)
    assert streams['S-glass'].mass_flow == pytest.approx(1000 - expected)


def test_penicillin_recovery_cannot_synthesize_antibiotic_from_glucose_water():
    fs, _ = solved('penicillin')
    incoming = sum(s.mass_flow * s.composition.get('penicillin', 0)
                   for s in fs.streams.values() if s.role == 'feed')
    outgoing = sum(s.mass_flow * s.composition.get('penicillin', 0)
                   for s in fs.streams.values() if s.role in ('product', 'waste'))
    assert outgoing == pytest.approx(incoming)
    assert not any(b.reactions for b in fs.blocks.values())
    assert 'downstream' in reg.get_metadata('penicillin')['nombre']


def test_water_suspended_solids_have_sludge_and_backwash_destinations():
    fs, _ = solved('water_treat')
    outgoing = sum(s.mass_flow * s.composition.get('raw_water_solids', 0)
                   for s in fs.streams.values() if s.role in ('product', 'waste'))
    assert outgoing == pytest.approx(2.0)
    assert 'sin desinfección' in reg.get_metadata('water_treat')['label']
