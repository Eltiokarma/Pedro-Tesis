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
            10.0,   # ISBL típico para planta MYPE
            30.0,   # Towler: 0.3 × ISBL para projects estándar
            10.0,   # Towler: 0.10 × (ISBL+OSBL)
            10.0,   # Towler: 0.10 × (ISBL+OSBL) (clase 4)
            15.0,   # Towler: 0.15 × FCI (planta continua)
        ],
    })


# ======================================================
# FIXED OPERATING COSTS
# ======================================================
# Convención: fila 0 = Labor (USD/yr), filas 1-8 son
# porcentajes según el modelo de Turton §8 (FCOP).
# ======================================================

def template_fixed():
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
            500_000.0,   # labor (Turton: ~50 operadores × $20-30k típico)
            25.0,        # Turton: 0.25 × Labor
            50.0,        # Turton: 0.5 × (Labor + Supervision)
            4.0,         # Turton: 0.04 × FCI (planta continua)
            50.0,        # Turton: 0.5 × (Labor + Maintenance)
            2.0,         # Turton: 0.02 × (ISBL + OSBL)
            8.0,         # Towler: 8% costo de capital
            1.0,         # Turton: 1% de WC
            0.0,         # Royalties: 0% default (variable según licencia)
        ],
    })


# ======================================================
# VARIABLE OPERATING COSTS
# ======================================================
# Una fila de ejemplo (Key Product) para que el user vea
# el formato.  Se agregan / eliminan filas desde la UI.
# ======================================================

def template_variable():
    return pd.DataFrame([
        {
            "variable operating costs": "Main Product",
            "units":                    "tm",
            "time basis":               "year",
            "flowrate":                 10_000.0,
            "price usd/units":          1_000.0,
            "stream":                   "Key Products",
        },
        {
            "variable operating costs": "Feedstock",
            "units":                    "tm",
            "time basis":               "year",
            "flowrate":                 12_000.0,
            "price usd/units":          200.0,
            "stream":                   "Raw Materials",
        },
    ])


# ======================================================
# FILA EN BLANCO PARA AGREGAR (variable costs)
# ======================================================

def fila_variable_vacia():
    return {
        "variable operating costs": "New variable",
        "units":                    "tm",
        "time basis":               "year",
        "flowrate":                 0.0,
        "price usd/units":          0.0,
        "stream":                   "Raw Materials",
    }
