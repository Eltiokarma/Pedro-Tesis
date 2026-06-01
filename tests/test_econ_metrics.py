"""GATE 1 — anti-divergencia econ_metrics (econ_evidence).

econ_metrics() reempaqueta el dict de simulate(run_economics=True) SIN alterar
ningún número: cada campo de la salida == su fuente en el dict crudo. Incluye la
verificación dura del P&L derivado: EBT == revenue − COM_d con los valores REALES
del dict (si no cuadra, es recálculo accidental).
"""
import pytest

import examples_registry as reg
import simulate_engine as se
from econ_evidence import econ_metrics


def _econ(clave, **econ_inputs):
    out = se.simulate(reg.load_example(clave).to_dict(),
                      run_economics=True, econ_inputs=econ_inputs or None)
    return out["economics"]


def test_heroes_match_raw_dict():
    econ = _econ("hda_full")
    m = econ_metrics(econ)
    assert m["heroes"]["npv"]["value"] == econ["NPV_usd"]
    assert m["heroes"]["irr"]["value"] == econ["IRR_pct"]
    assert m["heroes"]["payback"] == econ["payback_yr"]
    assert m["heroes"]["roi"] == econ["ROI_pct"]


def test_capex_opex_match_raw_dict():
    econ = _econ("hda_full")
    m = econ_metrics(econ)
    assert m["capex"]["isbl"] == econ["capex"]["isbl_usd"]
    assert m["capex"]["fci_grass_roots"] == econ["capex"]["fci_grass_roots_usd"]
    assert m["capex"]["working_capital"] == econ["capex"]["working_capital_usd"]
    assert m["opex"]["revenue"] == econ["opex_usd_yr"]["revenue"]
    assert m["opex"]["crm"] == econ["opex_usd_yr"]["crm"]
    assert m["opex"]["com_d"] == econ["com"]["COM_d_usd_yr"]
    # capex_total = FCI + WC (suma trazable, no recálculo de capex)
    assert m["capex"]["capex_total"] == pytest.approx(
        econ["capex"]["fci_grass_roots_usd"]
        + econ["capex"]["working_capital_usd"])


def test_cashflow_length_and_values():
    econ = _econ("hda_full")
    m = econ_metrics(econ)
    raw = econ["cash_flow_schedule_usd_yr"]
    assert len(m["cashflow"]) == len(raw)
    for i, row in enumerate(m["cashflow"]):
        assert row["cf"] == raw[i]            # valor exacto, sin alterar
        assert row["year"] == i + 1           # offset año de operación


def test_pnl_ebt_tied_to_source():
    """CONDICIÓN dura: EBT == revenue − COM_d con valores REALES del dict."""
    econ = _econ("hda_full")
    m = econ_metrics(econ)
    inc = m["income_statement"]
    assert inc is not None
    rev = econ["opex_usd_yr"]["revenue"]
    com_d = econ["com"]["COM_d_usd_yr"]
    assert inc["revenue"] == rev
    assert inc["com_d"] == com_d
    assert inc["ebt"] == pytest.approx(rev - com_d)   # atado a la fuente
    # tax = max(EBT,0)·tax_rate con el tax_rate real
    tr = econ["inputs"]["tax_rate"]
    assert inc["tax"] == pytest.approx(max(rev - com_d, 0.0) * tr)
    # net + dep == operating_cash_flow (cierre interno del P&L)
    if inc["operating_cash_flow"] is not None:
        assert inc["operating_cash_flow"] == pytest.approx(
            inc["net"] + inc["depreciation"])


def test_verdict_consistent_with_signs():
    for clave in ("hda_full", "methanol", "ammonia"):
        econ = _econ(clave)
        m = econ_metrics(econ)
        v = m["verdict"]["kind"]
        assert v in ("ok", "warn", "danger")
        npv = econ["NPV_usd"]
        if npv is not None and npv <= 0:
            assert v == "danger"


def test_montecarlo_tornado_none():
    # econ_metrics NO calcula MC/tornado: deben quedar None (los provee el panel).
    m = econ_metrics(_econ("hda_full"))
    assert m["montecarlo"] is None
    assert m["tornado"] is None


def test_phase_default_monochrome_op():
    # CONDICIÓN 2a: sin schedules → todos los años 'op' (waterfall monocromo).
    m = econ_metrics(_econ("hda_full"))   # default: construction/rampup None
    assert m["cashflow_all_op"] is True
    assert all(r["phase"] == "op" for r in m["cashflow"])


def test_params_from_inputs():
    econ = _econ("hda_full")
    m = econ_metrics(econ)
    assert m["params"]["project_life"] == econ["inputs"]["project_life"]
    assert m["params"]["tax_rate"] == econ["inputs"]["tax_rate"]
    assert m["params"]["discount_rate"] == econ["inputs"]["discount_rate"]


def test_none_econ_returns_none():
    assert econ_metrics(None) is None
    assert econ_metrics({}) is None
