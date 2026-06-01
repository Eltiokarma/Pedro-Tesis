"""econ_evidence.py — fuente de datos del Panel Económico.  Qt-free.

econ_metrics(econ) reempaqueta el dict de simulate(run_economics=True)["economics"]
en la forma estructurada que consumen los widgets/figuras del panel.

PRINCIPIO (duro): NO recalcula NADA. Solo lee, renombra y reordena valores que
el motor (capex/cost_of_manufacture/cash_flow + MACRS + CEPCI) ya computó. Cada
número de la salida es trazable 1:1 a una clave del dict crudo. Si una clave que
el handoff asume no existe en el dict real, se devuelve None/empty — no se fabrica.

Gaps conocidos vs handoff §2 (dict real de simulate, auditados en Fase 0):
  · NPV/IRR/payback/ROI → NPV_usd/IRR_pct/payback_yr/ROI_pct
  · discount_rate/project_years/construction_years → dentro de inputs{}
  · capex{} usa claves *_usd; opex se arma de opex_usd_yr{} + com{}
  · cash_flow → cash_flow_schedule_usd_yr (lista de floats de AÑOS DE OPERACIÓN;
    índice i = año de operación i+1; NO incluye años de construcción cuando
    construction_schedule es None — caso default → waterfall monocromo 'op')
  · montecarlo / tornado → NO existen en el dict → None (el tab MC usa el
    MonteCarloPanel vivo, que llama run_monte_carlo/run_tornado aparte)
  · income_statement → NO existe → se DERIVA un P&L por aritmética de presentación
    sobre valores reales (Revenue − COM_d = EBT − tax = neto + dep = flujo op),
    cada celda trazable a su origen.
"""
from __future__ import annotations

from typing import Optional


def _verdict(npv, irr_pct, hurdle_pct, payback_yr, life_yr) -> dict:
    """Viable / Marginal / No viable (handoff §2). irr y hurdle en %."""
    ok_irr = (irr_pct is not None and hurdle_pct is not None
              and irr_pct > hurdle_pct)
    ok_pb = (payback_yr is not None and life_yr is not None
             and payback_yr < life_yr)
    if npv is not None and npv > 0 and ok_irr and ok_pb:
        return {"text": "Viable", "kind": "ok"}
    if npv is not None and npv > 0:
        return {"text": "Marginal", "kind": "warn"}
    return {"text": "No viable", "kind": "danger"}


def _phase_for_year(op_index, n_constr, n_ramp):
    """Fase del año dado su índice. El vector de cash flow del motor (default)
    contiene SOLO años de operación → op_index 0-based desde inicio de operación.
    Cuando hay schedules, los primeros n_ramp años de operación son 'ramp'.
    (Los años de construcción NO están en este vector — van con CapEx negativo
    en la rama enriquecida; acá etiquetamos lo que el vector contiene.)"""
    if n_ramp and op_index < n_ramp:
        return "ramp"
    return "op"


def econ_metrics(econ: dict, costing: dict = None) -> Optional[dict]:
    """Reempaqueta economics de simulate(run_economics=True). None si econ
    es None/empty.  No recalcula: cada valor sale del dict crudo."""
    if not econ:
        return None
    inp = econ.get("inputs", {}) or {}
    capex = econ.get("capex", {}) or {}
    opex = econ.get("opex_usd_yr", {}) or {}
    com = econ.get("com", {}) or {}

    npv = econ.get("NPV_usd")
    irr = econ.get("IRR_pct")
    hurdle = inp.get("discount_rate")
    hurdle_pct = (hurdle * 100.0) if isinstance(hurdle, (int, float)) else None
    payback = econ.get("payback_yr")
    roi = econ.get("ROI_pct")
    life = inp.get("project_life")

    # cash flow: lista de floats (años de operación). Derivar año+fase.
    cf_raw = econ.get("cash_flow_schedule_usd_yr") or []
    cons = inp.get("construction_schedule")
    ramp = inp.get("rampup_schedule")
    n_constr = len(cons) if cons else 0
    n_ramp = len(ramp) if ramp else 0
    cashflow = [
        {"year": i + 1, "cf": float(c),
         "phase": _phase_for_year(i, n_constr, n_ramp)}
        for i, c in enumerate(cf_raw)
    ]
    all_op = all(x["phase"] == "op" for x in cashflow)  # default → monocromo

    # P&L derivado (aritmética de presentación, trazable a la fuente).
    revenue = opex.get("revenue")
    com_d = com.get("COM_d_usd_yr")
    dep = com.get("depreciation_SL_usd_yr")
    tax_rate = inp.get("tax_rate")
    income = None
    if revenue is not None and com_d is not None:
        ebt = revenue - com_d                       # = Revenue − COM_d
        tax = (max(ebt, 0.0) * tax_rate
               if isinstance(tax_rate, (int, float)) else None)
        net = (ebt - tax) if tax is not None else None
        op_cf = (net + dep) if (net is not None and dep is not None) else None
        income = {
            "revenue": revenue, "com_d": com_d, "ebt": ebt,
            "tax_rate": tax_rate, "tax": tax, "net": net,
            "depreciation": dep, "operating_cash_flow": op_cf,
        }

    # ── tablas de CAPEX (datos REALES de costing; None si no se pasó) ──
    cost = costing or {}
    capex_breakdown = None
    isbl_by_category = None
    if cost:
        isbl = cost.get("isbl_usd")
        capex_breakdown = {
            "isbl": isbl,
            "contingency": cost.get("contingency_usd"),
            "aux_facilities": cost.get("aux_facilities_usd"),
            "fci_grass_roots": cost.get("fci_grass_roots_usd"),
            "working_capital": cost.get("working_capital_usd"),
            "capex_total": cost.get("capex_total_usd"),
        }
        bycat = cost.get("by_category") or {}
        if bycat:
            isbl_by_category = {
                "isbl_total": isbl,
                "rows": [
                    {"category": cat,
                     "n": v.get("n_equipos"),
                     "material": v.get("material"),
                     "cbm": v.get("cbm_usd"),
                     "pct": ((v.get("cbm_usd") or 0) / isbl * 100.0)
                            if isbl else None}
                    for cat, v in bycat.items()
                ],
            }

    # ── tabla de OPEX (solo el desglose REAL del motor; las sub-líneas
    #    finas de Turton —supervisión/admin/ventas— NO se exponen → no se
    #    inventan).  COM_d = directos cash + M+T+I + depreciación.
    opex_breakdown = None
    if opex.get("revenue") is not None and com.get("COM_d_usd_yr") is not None:
        opex_breakdown = {
            "com_d": com.get("COM_d_usd_yr"),
            "directos": [
                ("Materias primas (CRM)", opex.get("crm")),
                ("Utilities (CUT)", opex.get("cut")),
                ("Tratamiento de residuos (CWT)", opex.get("cwt")),
                ("Mano de obra (COL)", opex.get("col")),
            ],
            "fijos": [
                ("Mant. + impuestos + seguros",
                 com.get("maintenance_tax_insurance_usd_yr")),
                ("Depreciación (SL)", com.get("depreciation_SL_usd_yr")),
            ],
            "note": ("Desglose con los términos que el motor expone "
                     "(Turton 8.2). Las sub-líneas finas —supervisión, "
                     "overhead de planta, admin/ventas/I+D— se aplican como "
                     "coeficientes y no se reportan línea por línea."),
        }

    return {
        "verdict": _verdict(npv, irr, hurdle_pct, payback, life),
        "heroes": {
            "npv": {"value": npv, "unit": "USD", "neg": (npv or 0) < 0},
            "irr": {"value": irr, "marker": hurdle_pct, "hurdle": hurdle_pct},
            "payback": payback, "roi": roi,
        },
        "capex": {
            "isbl": capex.get("isbl_usd"),
            "fci_grass_roots": capex.get("fci_grass_roots_usd"),
            "working_capital": capex.get("working_capital_usd"),
            "depreciable_base": capex.get("depreciable_base_usd"),
            "capex_total": ((capex.get("fci_grass_roots_usd") or 0.0)
                            + (capex.get("working_capital_usd") or 0.0))
                            if capex.get("fci_grass_roots_usd") is not None
                            else None,
        },
        "opex": {
            "revenue": opex.get("revenue"),
            "crm": opex.get("crm"), "cut": opex.get("cut"),
            "cwt": opex.get("cwt"), "col": opex.get("col"),
            "com_d": com.get("COM_d_usd_yr"),
            "com": com.get("COM_usd_yr"),
            "depreciation": com.get("depreciation_SL_usd_yr"),
            "maintenance_tax_insurance": com.get("maintenance_tax_insurance_usd_yr"),
        },
        "cashflow": cashflow,
        "cashflow_all_op": all_op,
        "payback_year": payback,        # años de operación (mismo origen que cf)
        "income_statement": income,
        "montecarlo": econ.get("montecarlo"),   # None — lo provee MonteCarloPanel
        "tornado": econ.get("tornado"),         # None — idem
        "params": {
            "project_life": inp.get("project_life"),
            "useful_life": inp.get("useful_life"),
            "tax_rate": inp.get("tax_rate"),
            "discount_rate": inp.get("discount_rate"),
            "dep_method": inp.get("dep_method"),
            "macrs_class": inp.get("macrs_class"),
            "year_target": inp.get("year_target"),
            "construction_schedule": inp.get("construction_schedule"),
            "rampup_schedule": inp.get("rampup_schedule"),
            "royalties_pct": inp.get("royalties_pct"),
            "isbl_override_usd": inp.get("isbl_override_usd"),
        },
        # tablas de CAPEX/OPEX (None si no se pasó `costing`)
        "capex_breakdown": capex_breakdown,
        "isbl_by_category": isbl_by_category,
        "opex_breakdown": opex_breakdown,
    }
