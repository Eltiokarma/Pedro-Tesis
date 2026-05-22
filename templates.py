# ======================================================
# TEMPLATES — DataFrames default para New Project
# ======================================================
# Valores típicos de Turton/Towler para arrancar un
# proyecto sin tener Excel.  El usuario solo necesita
# editar los específicos de su planta (ej. ISBL, productos,
# raw materials, precios).
# ======================================================

import pandas as pd


# ======================================================
# CAPITAL COSTS
# ======================================================
# Convención del modelo:
#   fila 0: ISBL en MM USD
#   fila 1..4: porcentajes (%) sobre ISBL/FCI
# ======================================================

def template_capital():
    # Defaults desde econ_defaults.py (perfil activo) — antes hardcoded.
    try:
        import econ_defaults as _ed
        cf = _ed.get_capital_fracs()
        osbl_pct = cf["OSBL_pct_of_ISBL"]   * 100
        eng_pct  = cf["engineering_pct"]    * 100
        cont_pct = cf["contingency_pct"]    * 100
        wc_pct   = cf["working_capital_pct"] * 100
    except Exception:
        osbl_pct, eng_pct, cont_pct, wc_pct = 30.0, 10.0, 10.0, 15.0
    return pd.DataFrame({
        "Concept": [
            "ISBL Capital Cost",
            "OSBL %",
            "Engineering %",
            "Contingency %",
            "Working Capital %",
        ],
        "Units": [
            "MM USD",
            "% of ISBL",
            "% of ISBL+OSBL",
            "% of ISBL+OSBL",
            "% of FCI",
        ],
        "Value": [
            10.0,        # ISBL placeholder — el PFD lo sobrescribe con
                          # el valor de lang_fci / CGR cuando importa.
            osbl_pct, eng_pct, cont_pct, wc_pct,
        ],
    })


# ======================================================
# FIXED OPERATING COSTS
# ======================================================
# Convención: fila 0 = Labor (USD/yr), filas 1-8 son
# porcentajes según el modelo de Turton §8 (FCOP).
# ======================================================

def template_fixed():
    # Labor placeholder: el PFD inyecta el valor Turton-real
    # (operadores × salario del perfil activo) via write_project_xlsx.
    # Si no se importa de PFD, el user puede editar.  Los %
    # vienen de econ_defaults perfil activo.
    try:
        import econ_defaults as _ed
        f = _ed.get_fcop_fracs()
        sup  = f["supervision_pct"]      * 100
        ovh  = f["salary_overhead_pct"]  * 100
        maint= f["maintenance_pct"]      * 100
        po   = f["plant_overhead_pct"]   * 100
        ti   = f["tax_insurance_pct"]    * 100
        int_ = f["interest_pct"]         * 100
        ge   = f["general_expenses_pct"] * 100
        roy  = f["royalties_pct"]        * 100
        # Labor placeholder = 10 operadores × salario perfil activo
        labor_placeholder = 10 * _ed.get_labor()["salary_per_operator_usd_yr"]
    except Exception:
        sup, ovh, maint, po, ti, int_, ge, roy = (
            25.0, 50.0, 4.0, 50.0, 2.0, 8.0, 1.0, 0.0)
        labor_placeholder = 250_000.0
    return pd.DataFrame({
        "Concept": [
            "Labor",
            "Supervision %",
            "Salary Overhead %",
            "Maintenance %",
            "Plant Overhead %",
            "Tax & Insurance %",
            "Interest %",
            "General Expenses %",
            "Royalties %",
        ],
        "Basis": [
            "USD/yr (total)",
            "% of Labor",
            "% of Labor + Supervision",
            "% of FCI",
            "% of Labor + Maintenance",
            "% of ISBL + OSBL",
            "% of FCI",
            "% of Working Capital",
            "% of Revenue",
        ],
        "Value": [
            labor_placeholder,
            sup, ovh, maint, po, ti, int_, ge, roy,
        ],
    })


