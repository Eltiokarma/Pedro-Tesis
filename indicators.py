# ======================================================
# PROFITABILITY INDICATORS
# ======================================================
# Indicadores estándar de Turton §10:
#   - PBP simple (payback period non-discounted)
#   - PBP discounted (discounted payback period)
#   - DCFROR (= IRR, equivalente al "rate of return that
#     makes NPV=0")
#   - ROI (Return on Investment)
#   - NPV @ varias tasas (sensibilidad determinística)
#
# Convención de Turton para PBP:
#   "Tiempo desde el startup hasta que la suma acumulada
#    de CF (operativo, sin capital) recupera la inversión
#    fija FCI."
#
# Pero nuestro modelo tiene capital y operación entrelazados
# por año (CF[i] = GP - Taxes - CapEx).  Para mantener
# consistencia con el resto del modelo, usamos la definición
# alternativa también común:
#
#   PBP = año en que la suma acumulada de CF cruza CERO
#         (a.k.a. "discounted payback" cuando se usa PV).
#
# Esto es directo y reproducible.  Si querés la convención
# estricta de Turton (ignorar capital en el numerador),
# pasá la lista CF de operación (GP - Taxes) por separado.
# ======================================================

from typing import List, Optional


# ======================================================
# NPV
# ======================================================

def npv(cf: List[float], años: List[float], tasa: float) -> float:
    return sum(
        cf[i] / ((1 + tasa) ** años[i])
        for i in range(len(cf))
    )


def npv_at_rates(cf, años, tasas):
    """Devuelve dict tasa→NPV.  Útil para tabla
    de sensibilidad determinística."""
    return {t: npv(cf, años, t) for t in tasas}


# ======================================================
# IRR / DCFROR (bisección)
# ======================================================

def irr(cf, años, tol=1e-7, max_iter=300) -> Optional[float]:
    """Tasa que hace NPV=0.  Devuelve None si el CF no
    cambia de signo (sin IRR real)."""

    if not cf or all(c >= 0 for c in cf) or all(c <= 0 for c in cf):
        return None

    lo, hi = -0.99, 10.0
    f_lo = npv(cf, años, lo)
    f_hi = npv(cf, años, hi)

    if f_lo * f_hi > 0:
        return None

    for _ in range(max_iter):
        mid = (lo + hi) / 2
        f_mid = npv(cf, años, mid)
        if abs(f_mid) < tol:
            return mid
        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid

    return (lo + hi) / 2


# DCFROR es el nombre que usa Turton; matemáticamente IRR.
def dcfror(cf, años) -> Optional[float]:
    return irr(cf, años)


# ======================================================
# PAYBACK PERIOD
# ======================================================

def _payback(cf_evaluado: List[float], años: List[float]) -> Optional[float]:
    """Devuelve el año (con fracción interpolada) en que
    la suma acumulada de cf_evaluado pasa de negativa a
    positiva por primera vez.

    cf_evaluado se asume ya ajustado (nominal o
    descontado).  años es la lista de años display
    paralela a cf_evaluado.

    None si nunca se recupera la inversión.
    """

    acumulado = 0.0
    acumulado_prev = 0.0

    for i, cf_i in enumerate(cf_evaluado):
        acumulado_prev = acumulado
        acumulado += cf_i

        if acumulado_prev < 0 <= acumulado:
            # interpolación lineal: fracción del año actual
            # que hace falta para que cumulative llegue a 0
            if cf_i == 0:
                return float(años[i])
            fraccion = -acumulado_prev / cf_i
            # año del cruce = año previo + fracción
            año_prev = años[i-1] if i > 0 else años[i] - 1
            return float(año_prev) + fraccion

    return None


def payback_simple(cf, años) -> Optional[float]:
    """PBP no descontado: año en que Σ CF cruza cero."""
    return _payback(cf, años)


def payback_descontado(cf, años, tasa) -> Optional[float]:
    """PBP descontado: año en que Σ PV(CF) cruza cero."""
    pv = [
        cf[i] / ((1 + tasa) ** años[i])
        for i in range(len(cf))
    ]
    return _payback(pv, años)


# ======================================================
# ROI (Return on Investment) — promedio simple anual
# ======================================================

def roi_promedio(cf, años, FCI, t_start=None) -> Optional[float]:
    """ROI promedio:  (mean annual operating CF) / FCI.

    Si t_start es dado, promedia solo desde el año de
    inicio de operación en adelante; si no, sobre todo
    el horizonte.

    Devuelve fracción (multiplicá por 100 para %)."""

    if FCI == 0:
        return None

    if t_start is None:
        cf_op = cf
        n = len(cf)
    else:
        cf_op = cf[t_start:]
        n = len(cf_op)

    if n == 0:
        return None

    return (sum(cf_op) / n) / FCI


# ======================================================
# RESUMEN INTEGRADO
# ======================================================

def resumen(cf, años, FCI, tasa_descuento, t_start=None,
            tasas_extra=(0.0, 0.05, 0.10, 0.15, 0.20, 0.25)):
    """Calcula todos los indicadores y los devuelve en un
    dict listo para mostrar en Excel/UI."""

    return {
        "NPV":                 npv(cf, años, tasa_descuento),
        "NPV_at_rates":        npv_at_rates(cf, años, tasas_extra),
        "IRR":                 irr(cf, años),
        "DCFROR":              dcfror(cf, años),
        "PBP_simple":          payback_simple(cf, años),
        "PBP_descontado":      payback_descontado(cf, años, tasa_descuento),
        "ROI_promedio":        roi_promedio(cf, años, FCI, t_start),
        "tasa_descuento":      tasa_descuento,
    }
