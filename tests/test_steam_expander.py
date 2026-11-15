"""Wet turbine phase, efficiency and first-law invariants."""
import copy

import pytest

from flowsheet_model import SEC_PER_YEAR, TM_TO_KG, Stream
from steam_expander import saturation_temperature_C, wet_steam_expander
from stream_enthalpy import stream_enthalpy_kW


def steam(temperature=450., pressure=60.):
    return Stream(1, "steam", 0, 1, mass_flow=SEC_PER_YEAR/TM_TO_KG,
                  composition={"water": 1.}, phase="vapor",
                  temperature=temperature, pressure_bar=pressure)


@pytest.mark.parametrize("temperature", [450., 280.])
def test_cycle_expansion_condenses_at_outlet_saturation_and_closes_energy(temperature):
    feed = steam(temperature)
    before = copy.deepcopy(feed)
    result = wet_steam_expander(feed, .1, .85, .95)
    assert result is not None
    assert result["phase"] == "two_phase"
    assert 0 < result["vapor_fraction"] < 1
    # Independent steam-table anchor: Tsat(10 kPa) = 45.81 C.
    assert result["T_out_C"] == pytest.approx(45.81, abs=.1)
    out = copy.copy(feed)
    out.temperature = result["T_out_C"]
    out.phase, out.vapor_fraction = result["phase"], result["vapor_fraction"]
    out.pressure_bar = .1
    dh = stream_enthalpy_kW(out) - stream_enthalpy_kW(feed)
    assert dh == pytest.approx(result["W_act_kW"] - result["Q_mechanical_loss_kW"], abs=1e-8)
    assert result["W_gas_kW"] == pytest.approx(.85 * result["W_isen_kW"])
    assert result["W_act_kW"] == pytest.approx(.95 * result["W_gas_kW"])
    assert result["Q_mechanical_loss_kW"] > 0
    assert result["s_out_kJ_kgK"] > result["s_in_kJ_kgK"]
    assert feed == before


def test_reversible_expansion_preserves_entropy_and_wet_inlet_supported():
    feed = steam(saturation_temperature_C(10.), 10.)
    feed.phase, feed.vapor_fraction = "two_phase", .95
    result = wet_steam_expander(feed, .1, 1., 1.)
    assert result is not None
    assert result["s_out_kJ_kgK"] == pytest.approx(result["s_in_kJ_kgK"], abs=1e-10)
    assert result["Q_mechanical_loss_kW"] == 0
    assert 0 < result["vapor_fraction"] < .95


def test_subcooled_vapor_and_nonwater_feed_are_rejected():
    assert wet_steam_expander(steam(200., 60.), .1) is None
    feed = steam()
    feed.composition = {"water": .99, "nitrogen": .01}
    assert wet_steam_expander(feed, .1) is None


def test_small_expansion_can_remain_superheated():
    result = wet_steam_expander(steam(450., 10.), 8., .85)
    assert result is not None
    assert result["phase"] == "vapor"
    assert result["vapor_fraction"] == 1
    assert saturation_temperature_C(8.) < result["T_out_C"] < 450.
