"""Declared entrainment has its own strict phase/quality consistency audit."""
import copy

import pytest

from flowsheet_consistency_audit import check_stream_phase
from flowsheet_model import Stream


def entrained_trace():
    return Stream(1, "acid with entrained gas", 0, 1, mass_flow=100.,
                  temperature=35., pressure_bar=1.1, phase="two_phase",
                  phase_locked=True, vapor_fraction=4.2e-6,
                  composition={"water": 1-4.2e-6, "nitrogen_dioxide": 4.2e-6},
                  component_vapor_fractions={"water": 0., "nitrogen_dioxide": 1.})


@pytest.mark.parametrize("locked", [False, True])
def test_valid_declared_allocation_reports_scope_without_equilibrium_flash(monkeypatch, locked):
    import flowsheet_solver
    def must_not_flash(*args, **kwargs):
        raise AssertionError("declared entrainment is not an equilibrium calculation")
    monkeypatch.setattr(flowsheet_solver, "_infer_phase_from_TP", must_not_flash)
    stream = entrained_trace()
    stream.phase_locked = locked
    before = copy.deepcopy(stream)
    finding = check_stream_phase(stream)
    assert (finding.category, finding.severity) == ("model_scope", "info")
    assert finding.data["derived_vapor_fraction"] == pytest.approx(4.2e-6)
    assert "no es una prediccion de equilibrio" in finding.message
    assert stream == before


@pytest.mark.parametrize("allocation", [
    {"water": 0.},
    {"water": 0., "nitrogen_dioxide": -1.},
    {"water": 0., "nitrogen_dioxide": 1.1},
    {"water": 0., "nitrogen_dioxide": float("nan")},
    {"water": 0., "nitrogen_dioxide": float("inf")},
    None,
])
def test_invalid_or_incomplete_allocation_remains_a_phase_error(allocation):
    stream = entrained_trace()
    stream.phase_locked = False  # an unlocked phase must not hide an invalid map
    stream.component_vapor_fractions = allocation
    finding = check_stream_phase(stream)
    assert (finding.category, finding.severity) == ("phase", "error")


@pytest.mark.parametrize("field,value", [
    ("phase", "liquid"), ("phase", "vapor"),
    ("vapor_fraction", 0.), ("vapor_fraction", float("nan")),
])
def test_bulk_phase_or_stale_quality_mismatch_remains_an_error(field, value):
    stream = entrained_trace()
    setattr(stream, field, value)
    finding = check_stream_phase(stream)
    assert (finding.category, finding.severity) == ("phase", "error")
