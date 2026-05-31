"""
indicators.py — NPV / IRR sobre vectores de cash flow año-por-año.  PURO.

Rescatado de montecarlo._npv / _irr_biseccion (cluster legacy ya retirado).
Single source = este módulo.

Convención: el cash flow es una lista [cf_0, cf_1, ..., cf_N] donde el índice
es el año (cf_0 = año 0 = -CAPEX).  Opcionalmente `years` da los exponentes
explícitos (compat con la forma montecarlo (cf, años, tasa)).
"""


def npv(cashflows, rate, years=None):
    """Valor presente neto: Σ cf[i] / (1+rate)^year[i].

    `years` default = índice posicional (0, 1, 2, ...)."""
    if years is None:
        return sum(cf / ((1.0 + rate) ** i)
                   for i, cf in enumerate(cashflows))
    return sum(cf / ((1.0 + rate) ** y)
               for cf, y in zip(cashflows, years))


def irr(cashflows, years=None, *, lo=-0.99, hi=10.0, tol=1e-6, max_iter=200):
    """Tasa interna de retorno por bisección (NPV=0).

    Devuelve None si el vector no cambia de signo (todos ≥0 o todos ≤0) o si
    no hay raíz en [lo, hi]."""
    cf = list(cashflows)
    if not cf or all(c >= 0 for c in cf) or all(c <= 0 for c in cf):
        return None
    f_lo = npv(cf, lo, years)
    f_hi = npv(cf, hi, years)
    if f_lo * f_hi > 0:
        return None
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = npv(cf, mid, years)
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)
