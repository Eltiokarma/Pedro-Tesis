# ======================================================
# PIPELINE GUI -> MOTOR ECONÓMICO
# ======================================================
# Adapta los DataFrames de la GUI (df_capital, df_fixed,
# engine.df_internal) al formato que esperan CostModel /
# CashFlowModel / ReportGenerator y orquesta el cálculo
# end-to-end.
# ======================================================

import pandas as pd

from flujoflujoclass import (
    CostModel,
    CashFlowModel,
    ReportGenerator,
)


# ======================================================
# CONSTRUCCIÓN DEL DICT data ESPERADO POR CostModel
# ======================================================

# CostModel.calcular() usa, para consumables y utilities,
# la fórmula coef * price * production.  La GUI no captura
# coeficientes (la columna física donde estaban en el Excel
# antiguo ahora aloja "time basis"), por lo que aquí
# adoptamos la convención: cost = flowrate_SI * price_SI,
# usando coef = flowrate_SI y forzando production = 1
# mediante un key_products dummy con flow = 1 cuando hay
# consumables/utilities.  Para evitar romper la valoración
# de los productos reales, computamos production_factor a
# partir del primer key product real y lo neutralizamos
# multiplicando el coef de cada consumible/utility por su
# valor; ver _construir_data.
# ======================================================


_STREAM_TO_BUCKET = {
    "Key Products": "key_products",
    "By-products": "byproducts",
    "Waste Streams": "byproducts",
    "Raw Materials": "raw_materials",
    "Consumables": "consumables",
    "Utilities": "utilities",
}


def _valor_capital(df_capital, fila):
    return float(df_capital.iloc[fila, 2])


def _valor_fixed(df_fixed, fila):
    return float(df_fixed.iloc[fila, 2])


def _pct(valor):
    """Convierte 30 (porcentaje) a 0.30.  Si ya viene como
    fracción <= 1.0, lo devuelve tal cual."""
    valor = float(valor)
    return valor / 100.0 if valor > 1.0 else valor


def _construir_data(
        df_capital,
        df_fixed,
        df_internal,
):
    """Arma el dict data que consume CostModel.

    Filas asumidas en df_capital (orden estricto):
        0: ISBL (USD)
        1: OSBL  (%)
        2: ENG   (%)
        3: CONT  (%)
        4: WC    (%)

    Filas asumidas en df_fixed (orden estricto):
        0: Labor (USD/yr)
        1: Supervision         (%)
        2: Salary Overhead     (%)
        3: Maintenance         (%)
        4: Plant Overhead      (%)
        5: Tax & Insurance     (%)
        6: Interest            (%)
        7: General Expenses    (%)
        8: Royalties           (%)
    """

    data = {}

    # CAPITAL
    data["ISBL"]     = _valor_capital(df_capital, 0)
    data["OSBL_pct"] = _pct(_valor_capital(df_capital, 1))
    data["ENG_pct"]  = _pct(_valor_capital(df_capital, 2))
    data["CONT_pct"] = _pct(_valor_capital(df_capital, 3))
    data["WC_pct"]   = _pct(_valor_capital(df_capital, 4))

    # FCOP inputs
    # IMPORTANTE: el modelo trabaja en MMUSD/yr.  labor en
    # el Excel viene en USD/yr, así que dividimos por 1e6
    # para que la suma con maintenance (% de FCI, ya en
    # MMUSD) tenga sentido dimensional.
    data["FCOP_inputs"] = {
        "labor":                _valor_fixed(df_fixed, 0) / 1e6,
        "supervision_pct":      _pct(_valor_fixed(df_fixed, 1)),
        "salary_overhead_pct":  _pct(_valor_fixed(df_fixed, 2)),
        "maintenance_pct":      _pct(_valor_fixed(df_fixed, 3)),
        "plant_overhead_pct":   _pct(_valor_fixed(df_fixed, 4)),
        "tax_insurance_pct":    _pct(_valor_fixed(df_fixed, 5)),
        "interest_pct":         _pct(_valor_fixed(df_fixed, 6)),
        "general_expenses_pct": _pct(_valor_fixed(df_fixed, 7)),
        "royalties_pct":        _pct(_valor_fixed(df_fixed, 8)),
    }

    # STREAMS (todos valuados como flow_SI * price_SI)
    buckets = {
        "key_products":  [],
        "byproducts":    [],
        "raw_materials": [],
        "consumables":   [],
        "utilities":     [],
    }

    for _, fila in df_internal.iterrows():

        stream = str(fila["Stream"]).strip()
        bucket = _STREAM_TO_BUCKET.get(stream)

        if bucket is None:
            continue

        flow_si  = float(fila["Flowrate SI"])
        price_si = float(fila["Price SI"])

        item = {
            "concept": str(fila["Variable"]),
            "unit":    "SI",
            "coef":    flow_si,
            "flow":    flow_si,
            "price":   price_si,
        }

        buckets[bucket].append(item)

    data.update(buckets)

    # Neutralizar production en consumables/utilities.
    # CostModel calcula CONS = sum(coef*price*production).
    # Queremos que CONS = sum(flow_SI*price_SI), por lo que
    # forzamos production = 1.  Eso se logra con un key
    # product dummy con flow=1, PERO necesitamos preservar
    # los key products reales para REV.  Solución: dividir
    # los coef de cons/uts por production_real, así
    # production_real * coef = flow_SI.
    if data["key_products"] and (data["consumables"] or data["utilities"]):
        production_real = data["key_products"][0]["flow"]
        if production_real not in (0, 0.0):
            for item in data["consumables"] + data["utilities"]:
                item["coef"] = item["coef"] / production_real

    return data


# ======================================================
# SCHEDULE
# ======================================================

def _parsear_csv_floats(texto, default):
    if texto is None or str(texto).strip() == "":
        return list(default)
    partes = [
        p.strip()
        for p in str(texto).split(",")
        if p.strip() != ""
    ]
    return [float(p) for p in partes]


def construir_params(
        inputs_economicos,
):
    """Construye el dict params que consume CashFlowModel a
    partir de los inputs económicos de la GUI."""

    schedule_raw = {
        "FC":   _parsear_csv_floats(
            inputs_economicos.get("fc_csv"),
            default=[1.0],
        ),
        "VCOP": _parsear_csv_floats(
            inputs_economicos.get("vcop_csv"),
            default=[1.0],
        ),
    }

    return {
        "vida":          int(inputs_economicos["project_life"]),
        "tasa_impuesto": float(inputs_economicos["tax_rate"]),
        "metodo_dep":    int(inputs_economicos["metodo_dep"]),
        "periodo_dep":   int(inputs_economicos.get("periodo_dep", 10)),
        "tipo_macrs":    int(inputs_economicos.get("tipo_macrs", 0)),
        "tasa_interes":  float(inputs_economicos["discount_rate"]),
        "schedule":      schedule_raw,
    }


# ======================================================
# EJECUCIÓN END-TO-END
# ======================================================

def ejecutar_analisis(
        df_capital,
        df_fixed,
        df_internal,
        inputs_economicos,
        archivo_salida,
):
    """Corre todo el pipeline y exporta el reporte Excel.

    Devuelve un dict con: costos, cf (cashflow dict),
    params, npv_acumulado.
    """

    if df_capital is None or df_capital.empty:
        raise ValueError("Capital Costs vacío")

    if df_fixed is None or df_fixed.empty:
        raise ValueError("Fixed Operating Costs vacío")

    if df_internal is None or df_internal.empty:
        raise ValueError("Variable Operating Costs vacío")

    # 1) data dict + costos
    data = _construir_data(df_capital, df_fixed, df_internal)
    costos = CostModel(data).calcular()

    # 2) params + schedule completo
    params = construir_params(inputs_economicos)

    reporte = ReportGenerator()
    schedule_full = reporte.construir_schedule(
        params["schedule"],
        params["vida"],
    )
    params["schedule"] = schedule_full

    # 3) cash flow
    cf = CashFlowModel(costos, params).calcular()

    # 4) NPV (idéntico al cálculo de exportar_cashflow)
    tasa = params["tasa_interes"]
    npv = sum(
        cf["CF"][i] / ((1 + tasa) ** cf["años"][i])
        for i in range(len(cf["CF"]))
    )

    # 5) IRR aproximada (bisección sobre el CF)
    irr = _calcular_irr(cf["CF"], cf["años"])

    # 6) exportar Excel
    reporte.exportar_cashflow(
        archivo_salida,
        cf,
        params,
        costos,
        data,
    )

    return {
        "data":   data,
        "costos": costos,
        "cf":     cf,
        "params": params,
        "npv":    npv,
        "irr":    irr,
    }


# ======================================================
# MONTE CARLO
# ======================================================

def construir_data_y_params(
        df_capital,
        df_fixed,
        df_internal,
        inputs_economicos,
):
    """Helper: construye data + params (con schedule
    expandido) sin correr el análisis.  Útil para correr
    Monte Carlo sin recomputar el schedule cada
    iteración."""

    if df_capital is None or df_capital.empty:
        raise ValueError("Capital Costs vacío")
    if df_fixed is None or df_fixed.empty:
        raise ValueError("Fixed Operating Costs vacío")
    if df_internal is None or df_internal.empty:
        raise ValueError("Variable Operating Costs vacío")

    data = _construir_data(df_capital, df_fixed, df_internal)
    params = construir_params(inputs_economicos)

    reporte = ReportGenerator()
    params["schedule"] = reporte.construir_schedule(
        params["schedule"],
        params["vida"],
    )

    return data, params


def ejecutar_montecarlo(
        df_capital,
        df_fixed,
        df_internal,
        inputs_economicos,
        variables_inciertas,
        n_runs=5000,
        seed=None,
        archivo_salida=None,
        adjuntar_a_excel_existente=True,
):
    """Corre N simulaciones Monte Carlo + tornado chart.

    variables_inciertas: lista de
        montecarlo.VariableIncierta.

    Si archivo_salida es dado y
    adjuntar_a_excel_existente=True, agrega hojas
    'Monte Carlo' y 'Tornado' al .xlsx existente (típicamente
    el reporte económico ya generado por ejecutar_analisis).

    Devuelve dict con 'mc' (resultado del MC), 'tornado'
    (lista ordenada) y 'archivo' (path, si aplica).
    """

    from montecarlo import correr_montecarlo, correr_tornado, exportar_montecarlo_excel

    data, params = construir_data_y_params(
        df_capital, df_fixed, df_internal, inputs_economicos,
    )

    mc = correr_montecarlo(
        data, params, variables_inciertas, n_runs=n_runs, seed=seed,
    )

    tornado = correr_tornado(
        data, params, variables_inciertas,
    )

    if archivo_salida is not None:
        exportar_montecarlo_excel(archivo_salida, mc, tornado)

    return {
        "mc":       mc,
        "tornado":  tornado,
        "archivo":  archivo_salida,
        "data":     data,
        "params":   params,
    }


# ======================================================
# IRR (Newton-Raphson simple sobre NPV)
# ======================================================

def _npv(cf, años, tasa):
    return sum(
        cf[i] / ((1 + tasa) ** años[i])
        for i in range(len(cf))
    )


def _calcular_irr(cf, años, tol=1e-6, max_iter=200):
    """IRR por bisección entre -0.99 y +10.  Devuelve None
    si no converge o si no hay cambio de signo en el CF."""

    if not cf or all(c >= 0 for c in cf) or all(c <= 0 for c in cf):
        return None

    lo, hi = -0.99, 10.0
    f_lo = _npv(cf, años, lo)
    f_hi = _npv(cf, años, hi)

    if f_lo * f_hi > 0:
        return None

    for _ in range(max_iter):
        mid = (lo + hi) / 2
        f_mid = _npv(cf, años, mid)

        if abs(f_mid) < tol:
            return mid

        if f_lo * f_mid < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid

    return (lo + hi) / 2
