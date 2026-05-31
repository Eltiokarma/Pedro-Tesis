"""
cash_flow.py — Motor de cash flow año-por-año.  PURO (sin UI, sin DataFrames).

Réplica de flujoflujoclass.CashFlowModel.calcular (verificada contra el código),
con UNA divergencia consciente: royalties = rev·pct (escala con el ramp-up),
en vez de la versión simplificada Revenue_base·pct que el motor viejo dejó
activa (la versión real estaba comentada como "para luego").  Para comparar
manzana-con-manzana contra el viejo (Gate 1b) está el flag royalties_on_base.

Enriquece a simulate() con las cuatro: ramp-up de capacidad, royalties,
desfase de impuestos (1 año) y recuperación de working capital.  NO incluye
el interés-sobre-FCI-como-opex del modelo viejo (parte no ortodoxa — excluida
a propósito).

NPV/IRR se delegan a indicators.py (no se reimplementan).

DEFAULTS = caso simple: 1 año de inversión (año 0), capacidad plena desde el
año 1, sin royalties, impuestos en el año devengado, WC invertido en el año 0.
Con esos defaults reproduce EXACTO el cash flow constante de la
profitability_indicators actual (Gate 1a).
"""
from typing import Optional, Sequence


def build_cash_flow(fci_usd: float, wc_usd: float, *,
                    revenue_usd_yr: float,
                    variable_opex_usd_yr: float,
                    fixed_opex_usd_yr: float,
                    dep_schedule: Sequence[float],
                    tax_rate: float, disc_rate: float,
                    construction_schedule: Sequence[float] = (1.0,),
                    rampup_schedule: Sequence[float] = (1.0,),
                    royalties_pct: float = 0.0,
                    royalties_on_base: bool = False,
                    tax_lag: bool = False,
                    wc_invest_at_t_start: bool = False) -> dict:
    """Cash flow anual + NPV/IRR.

    Parámetros
    ----------
    fci_usd, wc_usd : capital fijo y working capital (USD).
    revenue_usd_yr  : ingresos a capacidad plena (USD/año).
    variable_opex_usd_yr : costo operativo VARIABLE a plena capacidad (escala
        con ramp-up).  fixed_opex_usd_yr : costo operativo FIJO (no escala).
    dep_schedule : depreciación por año de OPERACIÓN (de depreciation.py).
        Su largo define los años de operación N.
    construction_schedule : fracción de CapEx por año de construcción
        (default (1.0,) = 1 año, 100% en el año 0).
    rampup_schedule : fracción de capacidad por año de operación durante el
        ramp-up (último valor se sostiene).  Default (1.0,) = plena capacidad.
    royalties_pct : fracción de ingresos.  rev·pct por default (escala con
        ramp); Revenue_base·pct si royalties_on_base=True (= viejo).
    tax_lag : si True, impuestos pagados con 1 año de desfase (= viejo).
    wc_invest_at_t_start : si True, WC se invierte en t_start (= viejo); si
        False (default), en el año 0 (estándar = simulate actual).

    Devuelve dict con listas paralelas (largo = vida = construcción + N):
        años, CapEx, Revenue, CCOP, GP, Dep, TI, Taxes, CF  + NPV, IRR.
    """
    import indicators as _ind

    fc   = list(construction_schedule) if construction_schedule else [1.0]
    ramp = list(rampup_schedule) if rampup_schedule else [1.0]
    dep  = list(dep_schedule)

    n_constr = len(fc)
    N        = len(dep)
    t_start  = n_constr
    vida     = n_constr + N
    años     = list(range(vida))
    wc_year  = t_start if wc_invest_at_t_start else 0

    # Depreciación alineada a años de operación
    D = [0.0] * vida
    for k in range(N):
        D[t_start + k] = float(dep[k])

    CapEx   = [0.0] * vida
    Revenue = [0.0] * vida
    CCOP    = [0.0] * vida
    GP      = [0.0] * vida
    TI      = [0.0] * vida
    accrued = [0.0] * vida

    for i in range(vida):
        capex = fci_usd * (fc[i] if i < n_constr else 0.0)
        if i == wc_year:
            capex += wc_usd
        if i == vida - 1:
            capex -= wc_usd          # recuperación de WC
        CapEx[i] = capex

        if i < t_start:
            rev = vcop = fcop = roy = gp = 0.0
        else:
            op = i - t_start
            factor = ramp[op] if op < len(ramp) else ramp[-1]
            rev  = revenue_usd_yr * factor
            vcop = variable_opex_usd_yr * factor
            fcop = fixed_opex_usd_yr
            base_for_roy = revenue_usd_yr if royalties_on_base else rev
            roy = base_for_roy * royalties_pct
            gp = rev - (fcop + vcop + roy)

        Revenue[i] = rev
        CCOP[i]    = (fcop + vcop + roy)
        GP[i]      = gp
        TI[i]      = gp - D[i]
        accrued[i] = max(TI[i] * tax_rate, 0.0)

    if tax_lag:
        Taxes = [0.0] * vida
        for i in range(1, vida):
            Taxes[i] = accrued[i - 1]
    else:
        Taxes = list(accrued)

    CF = [GP[i] - Taxes[i] - CapEx[i] for i in range(vida)]

    npv = _ind.npv(CF, disc_rate)        # descuenta por índice de año (años)
    irr = _ind.irr(CF)

    return {
        "años": años, "CapEx": CapEx, "Revenue": Revenue, "CCOP": CCOP,
        "GP": GP, "Dep": D, "TI": TI, "Taxes": Taxes, "CF": CF,
        "NPV": npv, "IRR": irr,
    }
