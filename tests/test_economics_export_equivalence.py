"""Embedded OPEX assumptions must survive API, sensitivity and workbook paths."""
import pandas as pd
import pytest

import flowsheet_export as export
from flowsheet_model import Block, Flowsheet, Stream
from simulate_engine import _economics


def fixture(gamma):
    fs = Flowsheet()
    fs.blocks[1] = Block(1, "P-1", "Pump — centrifugal", 50.)
    fs.streams = {
        2: Stream(2, "feed", 0, 1, mass_flow=100000, role="feed",
                  price_usd_per_tm=10., main_component="water"),
        3: Stream(3, "product", 1, 0, mass_flow=100000, role="product",
                  price_usd_per_tm=30., main_component="water"),
    }
    fs.fixed_overrides = {"Labor": 50000.}
    fs.econ_overrides = {"com_gamma": gamma}
    return fs


@pytest.mark.parametrize("gamma", [1.05, 1.10, 1.23])
def test_embedded_variable_cost_factor_matches_api_and_sensitivity(gamma):
    fs = fixture(gamma)
    rows = export._collect_pfd_opex_rows(fs, [fs.streams[2]], [fs.streams[3]])
    costing = export.compute_turton_costing(
        fs, pd.DataFrame(rows), pd.DataFrame([{"Concept": "Labor", "Value": 50000.}]),
        fci_musd=None)
    api = _economics(fs, {})
    assert costing["com"]["gamma"] == gamma
    assert costing["com"]["COM_d"] == pytest.approx(api["com"]["COM_d_usd_yr"], abs=1e-8)
    assert costing["profit"]["NPV"] == pytest.approx(api["NPV_usd"], abs=1e-8)
    assert costing["profit"]["IRR %"] == pytest.approx(api["IRR_pct"], abs=1e-8)
    assert costing["sensitivity"]["Base  (mid case)"]["NPV"] == pytest.approx(api["NPV_usd"], abs=1e-8)
    assert any(label.strip() == f"{gamma:.2f}·(CUT+CRM+CWT)"
               for label, _, _ in costing["rows"])


def test_workbook_income_statement_uses_the_same_embedded_coefficients(monkeypatch):
    fs = fixture(1.05)
    captured = {}
    monkeypatch.setattr(export, "write_3sections_xlsx",
                        lambda *args, **kwargs: captured.update(kwargs))
    export.write_project_xlsx("unused.xlsx", fs, None,
                              [fs.streams[2]], [fs.streams[3]])
    assert captured["costing"]["com"]["gamma"] == 1.05
    assert export.assert_costing_income_coherence(
        captured["costing"], captured["income_stmt"], rel_tol=1e-10)
    assert captured["costing"]["profit"]["NPV"] == pytest.approx(
        _economics(fs, {})["NPV_usd"], abs=1e-8)
