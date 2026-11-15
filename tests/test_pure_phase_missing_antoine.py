"""Missing Antoine must not create a fictitious boiling point at 800 K."""
import math

import pytest

import flowsheet_solver as solver
import thermo_db


def test_chlorine_without_antoine_uses_eos_for_vapor_and_liquid():
    assert thermo_db.get("chlorine").antoine_A is None
    assert solver._boiling_point_K("chlorine", 7) is None
    assert solver._infer_phase_from_TP({"chlorine": 1}, 99.2 + 273.15, 7) == ("vapor", 1)
    assert solver._infer_phase_from_TP({"chlorine": 1}, 20 + 273.15, 7) == ("liquid", 0)


@pytest.mark.parametrize("component,pressure", [
    ("unknown_property_record", 1.013), ("water", 1000),
    ("water", 0), ("water", math.nan), ("water", math.inf),
])
def test_missing_or_unbracketed_saturation_returns_none(component, pressure):
    assert solver._boiling_point_K(component, pressure) is None


def test_known_normal_and_cryogenic_boiling_points_remain_bracketed():
    assert solver._boiling_point_K("water", .5) == pytest.approx(354.5, abs=.3)
    # The catalogue's rounded Antoine fit differs from NIST by ~0.4 K.
    assert solver._boiling_point_K("nitrogen", 1.01325) == pytest.approx(77.34, abs=.5)
    assert solver._infer_phase_from_TP({"unknown_property_record": 1}, 300, 1) == ("", 0)


def test_nrtl_keeps_chlorine_volatile_in_water_mixture():
    import nrtl
    chlorine_pressure = nrtl._Psat_bar("chlorine", 372.35)
    assert chlorine_pressure == pytest.approx(38.1179, rel=2e-4)
    # At 1 bar and 99.2 C chlorine evaporates while water can remain liquid.
    # A fake Psat=1e-10 would force chlorine entirely into the liquid phase.
    result = nrtl.flash_TP(["chlorine", "water"], [.5, .5], 372.35, 1)
    assert result is not None
    assert result["K"][0] > 1
    assert result["V_frac"] > .5


def test_nrtl_unavailable_saturation_is_explicit(monkeypatch):
    import nrtl
    import eos
    assert nrtl._Psat_bar("unknown_property_record", 300) is None
    assert nrtl._Psat_bar("sucrose", 300) == 1e-10
    assert nrtl._Psat_bar("sodium_hydroxide", 300) == 1e-10
    assert nrtl._Psat_bar("chlorine", thermo_db.get("chlorine").tc_c + 274.15) is None
    monkeypatch.setattr(eos, "psat_bar", lambda *args: None)
    assert nrtl._Psat_bar("chlorine", 300) is None


def test_quimpac_chlorine_compression_has_no_false_phase_override():
    import examples_registry
    fs = examples_registry.load_example("quimpac")
    result = solver.solve(fs)
    assert result.success, result.energy_balance_errors
    hot = next(s for s in fs.streams.values() if s.name == "S-cl2-hp")
    assert hot.phase == "gas" and hot.phase_locked
    assert hot.temperature > 90 and hot.pressure_bar == pytest.approx(7)
    from flowsheet_consistency_audit import check_stream_phase
    assert check_stream_phase(hot) is None
