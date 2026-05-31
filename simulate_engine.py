"""
simulate_engine.py — Fachada HEADLESS del motor de simulación.

flowsheet (dict) → resultados (dict JSON-serializable), sin GUI.

NO reimplementa nada: orquesta y serializa las piezas existentes —
Flowsheet.from_dict/to_dict, flowsheet_solver.solve, capex.compute_fci,
las funciones puras de flowsheet_export (collect_equipment_rows,
compute_utilities_from_duties, categorize_opex) y la cadena económica de
equipment_costs (cost_of_manufacture_components, profitability_indicators) —
exactamente la misma que orquesta ana_qt._run_solver, sin tocar disco.

API:
    simulate(flowsheet_dict, *, run_economics=False, econ_inputs=None,
             write_xlsx=None) -> dict

Garantías:
  · Todo el output es JSON-serializable (sin objetos, DataFrames ni paths,
    salvo que write_xlsx escriba un xlsx deliberadamente).
  · Sin dependencia de PySide6/tkinter: importa y corre sin Qt.

El bloque `summary` reproduce EXACTAMENTE los golden values de
export_examples.golden (overall_status, n_blocks, n_streams, mass/energy
errors, sum_duty, ISBL), para que simulate sea sólo otro camino al mismo
motor (ver gate_simulate.py).
"""
import math

import flowsheet_model as fm
import flowsheet_solver as fsv


# ─────────────────────────────────────────────────────────────
# Helpers de serialización JSON-safe
# ─────────────────────────────────────────────────────────────

def _num(x):
    """Coerce a float JSON-safe; None si no es finito o no convertible."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _serialize_blocks(fs):
    """Bloques resueltos: identidad + área + duty + presión de operación."""
    rows = []
    for bid, b in fs.blocks.items():
        rows.append({
            "id": int(bid),
            "name": b.name,
            "eq_type": b.eq_type,
            "S": _num(getattr(b, "S", 0.0)),
            "n": int(getattr(b, "n", 1) or 1),
            "duty_kW": _num(getattr(b, "duty", 0.0)),
            "P_op_bar": _num(getattr(b, "P_op_bar", 0.0)),
        })
    return rows


def _serialize_streams(fs):
    """Corrientes resueltas: flujo, T, P, fase, composición, rol."""
    rows = []
    for sid, s in fs.streams.items():
        rows.append({
            "id": int(sid),
            "name": s.name,
            "src": int(s.src),
            "dst": int(s.dst),
            "role": s.role,
            "mass_flow": _num(s.mass_flow),
            "temperature_C": _num(s.temperature),
            "pressure_bar": _num(s.pressure_bar),
            "phase": s.phase,
            "main_component": getattr(s, "main_component", ""),
            "composition": {k: _num(v) for k, v in (s.composition or {}).items()},
            "stream_kind": getattr(s, "stream_kind", "mass"),
            "energy_kW": _num(getattr(s, "energy_kW", 0.0)),
        })
    return rows


def _serialize_audit(report):
    """AuditReport → resumen compacto JSON-safe (conteos + findings)."""
    if report is None:
        return None
    findings = [
        {"category": f.category, "severity": f.severity,
         "message": f.message}
        for f in report.findings
    ]
    by_sev = {}
    for f in report.findings:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
    return {"n_findings": len(findings), "by_severity": by_sev,
            "findings": findings}


def _serialize_solver(fs, res):
    """SolverResult → dict JSON-safe (status, errores, warnings, recycle,
    estados por bloque/stream)."""
    return {
        "overall_status": res.overall_status,
        "success": bool(res.success),
        "iterations": int(res.iterations),
        "mass_balance_errors": list(res.mass_balance_errors),
        "energy_balance_errors": list(res.energy_balance_errors),
        "energy_warnings": list(res.energy_warnings),
        "component_warnings": list(res.component_warnings),
        "consistency_warnings": list(res.consistency_warnings),
        "consistency_errors": list(res.consistency_errors),
        "hx_warnings": list(res.hx_warnings),
        "unresolved_streams": list(res.unresolved_streams),
        "cycles_detected": [list(c) for c in res.cycles_detected],
        "recycle_solutions": [
            {"tear_stream": rs.tear_stream,
             "cycle_blocks": list(rs.cycle_blocks),
             "converged": bool(rs.converged),
             "iterations": int(rs.iterations),
             "final_value": _num(rs.final_value)}
            for rs in res.recycle_solutions
        ],
        "block_status": {str(k): v for k, v in res.block_status.items()},
        "stream_status": {str(k): v for k, v in res.stream_status.items()},
        "audit": _serialize_audit(res.audit_report),
    }


# ─────────────────────────────────────────────────────────────
# Costing (ISBL/ΣCBM) y económico (NPV/IRR) — funciones existentes
# ─────────────────────────────────────────────────────────────

def _summary(fs, res):
    """Golden values — MISMA fórmula que export_examples.golden:
    overall_status, n_blocks, n_streams, mass/energy errors, sum_duty, ISBL."""
    s = {
        "overall_status": res.overall_status,
        "n_blocks": len(fs.blocks),
        "n_streams": len(fs.streams),
        "mass_errors": len(res.mass_balance_errors),
        "energy_errors": len(res.energy_balance_errors),
        "sum_duty": round(sum(float(getattr(b, "duty", 0.0) or 0.0)
                              for b in fs.blocks.values()), 6),
    }
    try:
        import capex
        v = capex.compute_fci(fs).get("sum_cbm")
        if v is not None:
            s["ISBL"] = round(float(v), 2)
    except Exception:
        pass
    return s


def _costing(fs):
    """Costing básico headless: ISBL/ΣCBM/FCI vía capex.compute_fci, más las
    filas puras de equipos y utilities de flowsheet_export.  Serializado."""
    import capex
    import flowsheet_export as fexp
    cd = capex.compute_fci(fs)
    out = {
        "isbl_usd": _num(cd.get("sum_cbm")),
        "sum_cp_usd": _num(cd.get("sum_cp")),
        "fci_grass_roots_usd": _num(cd.get("FCI_grass_roots")),
        "working_capital_usd": _num(cd.get("working_capital")),
        "capex_total_usd": _num(cd.get("CAPEX_total")),
        "depreciable_base_usd": _num(cd.get("depreciable_base")),
        "year_target": cd.get("year_target"),
        "by_category": {
            cat: {"cbm_usd": _num(v[0]) if isinstance(v, (list, tuple)) else _num(v),
                  "n_equipos": (int(v[1]) if isinstance(v, (list, tuple))
                                and len(v) > 1 else None)}
            for cat, v in (cd.get("by_category") or {}).items()
        },
    }
    try:
        out["equipment"] = collect = fexp.collect_equipment_rows(fs)
    except Exception:
        out["equipment"] = []
    try:
        util_rows, util_summary = fexp.compute_utilities_from_duties(fs)
        out["utilities"] = util_rows
        out["utilities_summary"] = util_summary
    except Exception:
        out["utilities"] = []
    return _jsonsafe(out)


def _economics(fs, econ_inputs):
    """Cadena económica IDÉNTICA a ana_qt._run_solver, headless y sin disco:
    categorize_opex → compute_fci → cost_of_manufacture_components →
    profitability_indicators.  Devuelve NPV/IRR/Payback/ROI/COM serializados.

    econ_inputs (todos opcionales; default = econ_defaults):
      tax_rate, discount_rate, project_life (años de operación),
      useful_life (vida depreciable), year_target (CEPCI), isbl_override_usd.
    """
    import capex
    import equipment_costs as ec
    import flowsheet_export as fexp
    econ_inputs = econ_inputs or {}
    try:
        import econ_defaults as ed
        fin = ed.get_financial()
        d_years, d_tax, d_disc = (fin["project_years"], fin["tax_rate"],
                                  fin["discount_rate"])
    except Exception:
        d_years, d_tax, d_disc = 10, 0.30, 0.10

    years   = int(econ_inputs.get("project_life",
                                  econ_inputs.get("years_op", d_years)))
    tax     = float(econ_inputs.get("tax_rate", d_tax))
    disc    = float(econ_inputs.get("discount_rate", d_disc))
    useful  = int(econ_inputs.get("useful_life", years))
    year_t  = int(econ_inputs.get("year_target", 2024))
    isbl_override = econ_inputs.get("isbl_override_usd")  # None → desde bloques
    # Depreciación: 'straight_line' (default, no cambia nada) o 'macrs'.
    dep_method = str(econ_inputs.get("dep_method", "straight_line"))
    macrs_class = int(econ_inputs.get("macrs_class", 5))
    dep_years = econ_inputs.get("dep_years")            # None → useful_life

    opex = fexp.categorize_opex(fs)                      # {revenue,crm,cut,cwt,col}
    cd = capex.compute_fci(fs, year_target=year_t,
                           isbl_override_usd=isbl_override)
    fci = cd["FCI_grass_roots"]
    wc  = cd["working_capital"]
    dep = cd["depreciable_base"]

    com = ec.cost_of_manufacture_components(
        FCI_usd=fci, COL_usd=opex["col"],
        CUT_usd=opex["cut"], CRM_usd=opex["crm"], CWT_usd=opex["cwt"],
        depreciable_base_usd=dep, useful_life_yr=useful,
    )
    prof = ec.profitability_indicators(
        revenue_usd_yr=opex["revenue"], com_d_usd_yr=com["COM_d"],
        fci_usd=fci, depreciable_base_usd=dep, working_capital_usd=wc,
        useful_life_yr=useful, years_op=years, tax_rate=tax, disc_rate=disc,
        dep_method=dep_method, macrs_class=macrs_class, dep_years=dep_years,
    )
    return _jsonsafe({
        "inputs": {"tax_rate": tax, "discount_rate": disc,
                   "project_life": years, "useful_life": useful,
                   "year_target": year_t,
                   "isbl_override_usd": isbl_override,
                   "dep_method": dep_method, "macrs_class": macrs_class,
                   "dep_years": dep_years},
        "opex_usd_yr": opex,
        "capex": {"fci_grass_roots_usd": fci, "working_capital_usd": wc,
                  "depreciable_base_usd": dep,
                  "isbl_usd": cd.get("sum_cbm")},
        "com": {"COM_d_usd_yr": com.get("COM_d"),
                "COM_usd_yr": com.get("COM"),
                "depreciation_SL_usd_yr": com.get("Depreciation_SL"),
                "maintenance_tax_insurance_usd_yr":
                    com.get("Maintenance_Tax_Insurance")},
        "NPV_usd": prof.get("NPV"),
        "IRR_pct": prof.get("IRR %"),
        "IRR_str": prof.get("IRR str"),
        "payback_yr": prof.get("Payback simple"),
        "ROI_pct": prof.get("ROI %"),
        "cash_flow_usd_yr": prof.get("Cash flow"),
        "gross_profit_usd_yr": prof.get("Gross profit"),
        "net_profit_usd_yr": prof.get("Net profit"),
        "veredicto": prof.get("Veredicto"),
        "depreciation": {
            "method": prof.get("dep_method"),
            "macrs_class": prof.get("macrs_class"),
            "schedule_usd_yr": prof.get("Depreciation schedule"),
        },
        "cash_flow_schedule_usd_yr": prof.get("Cash flow schedule"),
    })


def _jsonsafe(obj):
    """Coerce recursivo a estructuras JSON-safe (números finitos, sin objetos)."""
    if isinstance(obj, dict):
        return {str(k): _jsonsafe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonsafe(v) for v in obj]
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int,)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if obj is None or isinstance(obj, str):
        return obj
    # objetos no esperados → repr (último recurso, mantiene JSON-safe)
    return repr(obj)


# ─────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────

def simulate(flowsheet_dict, *, run_economics=False, econ_inputs=None,
             write_xlsx=None):
    """Resuelve un flowsheet (dict) y devuelve resultados (dict JSON-safe).

    Parámetros
    ----------
    flowsheet_dict : dict
        El to_dict() de un Flowsheet (mismo formato que data/examples/*.json).
    run_economics : bool
        Si True, agrega el bloque `economics` (NPV/IRR/Payback/ROI/COM).
    econ_inputs : dict | None
        Overrides económicos (tax_rate, discount_rate, project_life,
        useful_life, year_target, isbl_override_usd).  Default = econ_defaults.
    write_xlsx : str | None
        Si se pasa un path, escribe el xlsx del proyecto vía el
        write_project_xlsx EXISTENTE (única vía de disco, opt-in explícito).

    Devuelve
    --------
    dict con claves: summary, solver, blocks, streams, costing y,
    si run_economics, economics.
    """
    fs = fm.Flowsheet.from_dict(flowsheet_dict)
    res = fsv.solve(fs)

    out = {
        "summary": _summary(fs, res),
        "solver": _serialize_solver(fs, res),
        "blocks": _serialize_blocks(fs),
        "streams": _serialize_streams(fs),
        "costing": _costing(fs),
    }
    if run_economics:
        out["economics"] = _economics(fs, econ_inputs)

    if write_xlsx:
        import flowsheet_export as fexp
        feeds    = [s for s in fs.streams.values() if s.role == "feed"]
        products = [s for s in fs.streams.values() if s.role == "product"]
        isbl_musd = (out["costing"]["isbl_usd"] / 1e6
                     if out["costing"].get("isbl_usd") else None)
        fexp.write_project_xlsx(write_xlsx, fs, isbl_musd, feeds, products)
        out["xlsx_path"] = write_xlsx

    return out
