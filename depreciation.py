"""
depreciation.py — Tablas y schedule de depreciación.  SINGLE SOURCE del
motor vivo.  PURO (sin UI, sin estado).

Rescatado de flujoflujoclass.CashFlowModel.calcular_depreciacion (cluster
legacy ANA/Monte Carlo que se va a retirar).  Mientras dure ese retiro las
copias en flujoflujoclass.py y montecarlo.py quedan DUPLICADAS; el single
source es ESTE módulo y las copias se eliminan junto con ana_qt.

MACRS — GDS half-year convention (IRS Pub. 946):
  · 5-year   → 6 factores
  · 7-year   → 8 factores
  · 15-year  → 16 factores
Cada tabla suma 1.0 (toda la base depreciable se recupera).
"""

# Factores MACRS por clase (suman 1.0).  Idénticos a
# flujoflujoclass.calcular_depreciacion (tipo_macrs 0/1/2 → clase 5/7/15).
MACRS_TABLES = {
    5:  [0.20, 0.32, 0.192, 0.1152, 0.1152, 0.0576],
    7:  [0.1429, 0.2449, 0.1749, 0.1249, 0.0893, 0.0892, 0.0893, 0.0446],
    15: [0.05, 0.095, 0.0855, 0.077, 0.0693, 0.0623, 0.059, 0.059, 0.0591,
         0.059, 0.0591, 0.059, 0.0591, 0.059, 0.0591, 0.0295],
}


def depreciation_schedule(base_usd, *, method="straight_line", years=None,
                          macrs_class=5):
    """Depreciación por año (USD).  PURO.

    method='straight_line': base/years repetido `years` veces (years = vida
       depreciable).
    method='macrs': base·factor por la tabla MACRS de la clase (5/7/15).

    El largo del vector es el natural al método; el caller
    (profitability_indicators) lo alinea contra los años de operación.
    """
    m = str(method).lower()
    if m in ("straight_line", "sl", "lineal", "linear"):
        n = max(int(years or 1), 1)
        d = float(base_usd) / n
        return [d] * n
    if m == "macrs":
        if macrs_class not in MACRS_TABLES:
            raise ValueError(
                f"macrs_class debe ser 5, 7 o 15 — recibido {macrs_class!r}")
        return [float(base_usd) * f for f in MACRS_TABLES[macrs_class]]
    raise ValueError(f"method de depreciación desconocido: {method!r}")
