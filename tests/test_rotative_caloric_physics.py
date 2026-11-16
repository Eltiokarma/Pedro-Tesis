"""First-law and composition-basis regressions for gas machinery."""
import pytest

from compressor_thermo import gas_machine_for_stream, mixture_molecular_weight
from equipment_design import design_compressor_for_block
from flowsheet_model import Block, Flowsheet, Stream, SEC_PER_YEAR, TM_TO_KG
from stream_enthalpy import stream_enthalpy_kW
import flowsheet_solver as solver


@pytest.mark.parametrize("component,tin", [
    ("water", 180.0), ("ethylene", 25.0),
    ("hydrogen", 25.0), ("nitrogen", 25.0)])
@pytest.mark.parametrize("ratio", [3.0, 12.7])
def test_compressor_power_equals_enthalpy_rise_plus_rejected_heat(component, tin, ratio):
    fs = Flowsheet()
    b = Block(id=2, name="K-1", eq_type="Compressor — centrifugal", S=1,
              delta_p_bar=ratio-1, efficiency=0.78)
    fs.blocks = {2: b}
    flow = SEC_PER_YEAR / TM_TO_KG
    feed = Stream(id=1, name="Feed", src=1, dst=2, mass_flow=flow,
                  temperature=tin, pressure_bar=1, phase="gas",
                  composition={component: 1.0}, main_component=component)
    out = Stream(id=2, name="Product", src=2, dst=3, mass_flow=flow,
                 temperature=tin, pressure_bar=ratio, phase="gas",
                 composition={component: 1.0}, main_component=component)
    fs.streams = {1: feed, 2: out}
    messages = []
    assert solver._propagate_T_compressor_isentropic(b, fs, skipped=messages, tol_T=1e-8)
    assert not messages
    dh = stream_enthalpy_kW(out)-stream_enthalpy_kW(feed)
    assert b.duty == pytest.approx(dh+b._q_intercool_kW+b._q_mechanical_loss_kW,
                                  rel=1e-8, abs=1e-6)
    assert b.duty > dh > 0
    assert b._q_mechanical_loss_kW > 0
    assert b._n_stages == (1 if ratio == 3 else 2)
    assert b._q_intercool_kW == pytest.approx((b._n_stages-1)*dh, rel=1e-8)
    design = design_compressor_for_block(b, fs)
    assert design["W_act_kW"] == pytest.approx(b.duty, rel=1e-10)
    assert design["T_out_C"] == pytest.approx(out.temperature, abs=1e-8)


def test_mass_fraction_molecular_weight_is_harmonic():
    import thermo_db
    composition = {"hydrogen": 0.5, "nitrogen": 0.5}
    expected = 1/(0.5/thermo_db.get("hydrogen").mw+0.5/thermo_db.get("nitrogen").mw)
    assert mixture_molecular_weight(composition) == pytest.approx(expected)


def test_expander_generated_power_and_heat_loss_conserve_energy():
    feed = Stream(id=1, name="Feed", src=1, dst=2,
                  mass_flow=SEC_PER_YEAR/TM_TO_KG,
                  temperature=500, pressure_bar=10, phase="gas",
                  composition={"nitrogen": 1.0}, main_component="nitrogen")
    result = gas_machine_for_stream(feed, 1, efficiency=0.85)
    assert result is not None
    hin = stream_enthalpy_kW(feed)
    feed.temperature = result["T_out_C"]
    hout = stream_enthalpy_kW(feed)
    assert result["W_act_kW"] < 0
    assert result["Q_mechanical_loss_kW"] > 0
    assert hout-hin == pytest.approx(result["W_act_kW"]-result["Q_mechanical_loss_kW"], rel=1e-8)


def test_incompatible_locked_compressor_temperature_is_an_error():
    fs = Flowsheet()
    fs.blocks = {i: Block(id=i, name=f"B-{i}", eq_type="Vessel - vertical", S=1)
                 for i in (1, 2, 3)}
    fs.blocks[2].eq_type = "Compressor — centrifugal"
    fs.blocks[2].delta_p_bar = 2
    fs.streams = {
        1: Stream(id=1, name="Feed", src=1, dst=2, mass_flow=1000,
                  temperature=25, pressure_bar=1, phase="gas",
                  mass_flow_locked=True, temperature_locked=True, pressure_locked=True,
                  composition={"nitrogen": 1.0}, composition_locked=True),
        2: Stream(id=2, name="Product", src=2, dst=3, mass_flow=0,
                  temperature=25, pressure_bar=3, phase="gas",
                  temperature_locked=True, pressure_locked=True),
    }
    result = solver.solve(fs)
    assert not result.success
    assert any("energia de maquina no cierra" in msg for msg in result.energy_balance_errors)


@pytest.mark.parametrize("example", ["rankine", "nuclear"])
def test_power_cycles_expand_to_saturated_wet_steam_with_closed_first_law(example):
    import json
    from pathlib import Path
    from steam_expander import saturation_temperature_C

    data = Path(__file__).resolve().parents[1]/"data"/"examples"/f"{example}.json"
    fs = Flowsheet.from_dict(json.loads(data.read_text(encoding="utf-8")))
    result = solver.solve(fs)
    assert result.success, result.energy_balance_errors
    turbine = next(b for b in fs.blocks.values() if b.eq_type == "Turbine — steam")
    feed = next(s for s in fs.streams.values() if s.dst == turbine.id)
    outlet = next(s for s in fs.streams.values() if s.src == turbine.id)
    assert outlet.phase == "two_phase"
    assert 0 < outlet.vapor_fraction < 1
    assert outlet.temperature == pytest.approx(saturation_temperature_C(outlet.pressure_bar), abs=1e-7)
    delta_h = stream_enthalpy_kW(outlet)-stream_enthalpy_kW(feed)
    assert turbine.duty < 0
    assert delta_h == pytest.approx(turbine.duty-turbine._q_mechanical_loss_kW,
                                    rel=1e-8, abs=1e-6)
