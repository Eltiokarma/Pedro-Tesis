# ======================================================
# MONTE CARLO — análisis de incertidumbre sobre NPV/IRR
# ======================================================
# Soporta incertidumbre triangular sobre:
#   - precio de cada Key Product (uno por uno)
#   - precio de cada Raw Material  (uno por uno)
#   - ISBL Capital Cost
#
# Output principal:
#   - distribución de NPV/IRR sobre N corridas
#   - estadísticos (mean, std, percentiles, P(NPV<0))
#   - tornado determinístico (vary-one-at-a-time)
#
# Referencias: Towler & Sinnott §9 (Economic Risk),
# Turton §10 (Profitability Analysis & Sensitivity).
# ======================================================

import copy
import random

from dataclasses import dataclass
from typing import List, Optional

from flujoflujoclass import CostModel, CashFlowModel, ReportGenerator


# ======================================================
# TIPOS DE VARIABLE INCIERTA
# ======================================================

KIND_PRODUCT_PRICE      = "product_price"
KIND_RAW_MATERIAL_PRICE = "raw_material_price"
KIND_ISBL               = "isbl"


@dataclass
class VariableIncierta:
    """Spec de una variable a someter a Monte Carlo.

    kind:      KIND_PRODUCT_PRICE | KIND_RAW_MATERIAL_PRICE
               | KIND_ISBL
    indice:    índice dentro de la lista correspondiente
               (data["key_products"] o data["raw_materials"]).
               Ignorado si kind == KIND_ISBL.
    nombre:    para mostrar en outputs (concept o "ISBL").
    valor_min: extremo bajo de la triangular.
    valor_mode:moda (= valor más probable; típicamente el
               valor base del input).
    valor_max: extremo alto.
    """

    kind: str
    indice: int
    nombre: str
    valor_min: float
    valor_mode: float
    valor_max: float

    def sample(self, rng: random.Random) -> float:
        return rng.triangular(
            self.valor_min,
            self.valor_max,
            self.valor_mode,
        )


# ======================================================
# APLICAR MUESTRAS AL data dict
# ======================================================

def _aplicar_muestras(data, variables, muestras):
    """Devuelve una copia profunda de data con los valores
    sampleados sustituidos en su lugar correcto."""
    nuevo = copy.deepcopy(data)

    for var, valor in zip(variables, muestras):

        if var.kind == KIND_PRODUCT_PRICE:
            nuevo["key_products"][var.indice]["price"] = valor

        elif var.kind == KIND_RAW_MATERIAL_PRICE:
            nuevo["raw_materials"][var.indice]["price"] = valor

        elif var.kind == KIND_ISBL:
            nuevo["ISBL"] = valor

        else:
            raise ValueError(f"Kind desconocido: {var.kind}")

    return nuevo


# ======================================================
# NPV / IRR PUROS (sin tocar Excel)
# ======================================================

def _npv(cf, años, tasa):
    return sum(
        cf[i] / ((1 + tasa) ** años[i])
        for i in range(len(cf))
    )


def _irr_biseccion(cf, años, tol=1e-6, max_iter=200):
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


def _correr_un_escenario(data, params):
    """Ejecuta CostModel + CashFlowModel para un set de
    inputs y devuelve (npv, irr)."""
    costos = CostModel(data).calcular()
    cf = CashFlowModel(costos, params).calcular()

    tasa = params["tasa_interes"]
    npv = _npv(cf["CF"], cf["años"], tasa)
    irr = _irr_biseccion(cf["CF"], cf["años"])

    return npv, irr


# ======================================================
# CORRIDA MONTE CARLO
# ======================================================

def correr_montecarlo(
        data_base,
        params,
        variables: List[VariableIncierta],
        n_runs: int = 5000,
        seed: Optional[int] = None,
):
    """Ejecuta N simulaciones samplenado las `variables` de
    sus distribuciones triangulares.

    Devuelve dict con:
        npvs:    lista de NPV (largo = n_runs)
        irrs:    lista de IRR (None si no calcuable)
        samples: lista de listas, samples[i] = valores
                 sampleados para la corrida i, en el mismo
                 orden que `variables`
        stats:   dict con estadísticos
    """

    # Construcción del schedule UNA vez (no depende de las
    # variables que estamos muestreando).  Importante:
    # CashFlowModel necesita params["schedule"] ya
    # expandido (la versión cruda CSV ya quedó atrás).
    rng = random.Random(seed)

    npvs = []
    irrs = []
    samples = []

    for _ in range(n_runs):

        muestras = [v.sample(rng) for v in variables]

        data_run = _aplicar_muestras(data_base, variables, muestras)
        npv, irr = _correr_un_escenario(data_run, params)

        npvs.append(npv)
        irrs.append(irr)
        samples.append(muestras)

    return {
        "npvs":      npvs,
        "irrs":      irrs,
        "samples":   samples,
        "variables": variables,
        "stats":     _estadisticos(npvs, irrs),
    }


# ======================================================
# ESTADÍSTICOS
# ======================================================

def _percentil(valores_ordenados, p):
    """p en [0,100].  Interpolación lineal."""
    n = len(valores_ordenados)
    if n == 0:
        return None
    if n == 1:
        return valores_ordenados[0]

    k = (n - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, n - 1)
    return (
        valores_ordenados[f]
        + (k - f) * (valores_ordenados[c] - valores_ordenados[f])
    )


def _estadisticos(npvs, irrs):
    npvs_ord = sorted(npvs)
    n = len(npvs)

    mean = sum(npvs) / n if n else 0.0
    var = (
        sum((x - mean) ** 2 for x in npvs) / (n - 1)
        if n > 1 else 0.0
    )
    std = var ** 0.5

    irrs_validas = [r for r in irrs if r is not None]

    return {
        "n":           n,
        "npv_mean":    mean,
        "npv_std":     std,
        "npv_min":     npvs_ord[0] if n else None,
        "npv_max":     npvs_ord[-1] if n else None,
        "npv_p10":     _percentil(npvs_ord, 10),
        "npv_p50":     _percentil(npvs_ord, 50),
        "npv_p90":     _percentil(npvs_ord, 90),
        "p_npv_neg":   sum(1 for x in npvs if x < 0) / n if n else 0.0,
        "irr_mean":    (
            sum(irrs_validas) / len(irrs_validas)
            if irrs_validas else None
        ),
        "irr_p10":     (
            _percentil(sorted(irrs_validas), 10)
            if irrs_validas else None
        ),
        "irr_p50":     (
            _percentil(sorted(irrs_validas), 50)
            if irrs_validas else None
        ),
        "irr_p90":     (
            _percentil(sorted(irrs_validas), 90)
            if irrs_validas else None
        ),
        "irr_n_valid": len(irrs_validas),
    }


# ======================================================
# TORNADO CHART (determinístico)
# ======================================================
# Para cada variable: variarla a su min y a su max
# manteniendo el resto en su valor mode.  La diferencia
# de NPV resultante es la longitud de la barra del
# tornado.  Se ordena por |ΔNPV|.
# ======================================================

def correr_tornado(
        data_base,
        params,
        variables: List[VariableIncierta],
):
    """Devuelve lista de dicts ordenada por |ΔNPV| desc:
        nombre, npv_low, npv_high, npv_base, delta_low,
        delta_high, swing.
    swing = |npv_high − npv_low|.
    """

    # NPV en el caso base (todas las variables en su mode)
    data_base_mode = copy.deepcopy(data_base)
    for v in variables:
        if v.kind == KIND_PRODUCT_PRICE:
            data_base_mode["key_products"][v.indice]["price"] = v.valor_mode
        elif v.kind == KIND_RAW_MATERIAL_PRICE:
            data_base_mode["raw_materials"][v.indice]["price"] = v.valor_mode
        elif v.kind == KIND_ISBL:
            data_base_mode["ISBL"] = v.valor_mode

    npv_base, _ = _correr_un_escenario(data_base_mode, params)

    resultados = []

    for v in variables:

        # min
        data_lo = copy.deepcopy(data_base_mode)
        if v.kind == KIND_PRODUCT_PRICE:
            data_lo["key_products"][v.indice]["price"] = v.valor_min
        elif v.kind == KIND_RAW_MATERIAL_PRICE:
            data_lo["raw_materials"][v.indice]["price"] = v.valor_min
        elif v.kind == KIND_ISBL:
            data_lo["ISBL"] = v.valor_min
        npv_lo, _ = _correr_un_escenario(data_lo, params)

        # max
        data_hi = copy.deepcopy(data_base_mode)
        if v.kind == KIND_PRODUCT_PRICE:
            data_hi["key_products"][v.indice]["price"] = v.valor_max
        elif v.kind == KIND_RAW_MATERIAL_PRICE:
            data_hi["raw_materials"][v.indice]["price"] = v.valor_max
        elif v.kind == KIND_ISBL:
            data_hi["ISBL"] = v.valor_max
        npv_hi, _ = _correr_un_escenario(data_hi, params)

        resultados.append({
            "nombre":     v.nombre,
            "kind":       v.kind,
            "npv_base":   npv_base,
            "npv_low":    npv_lo,
            "npv_high":   npv_hi,
            "delta_low":  npv_lo - npv_base,
            "delta_high": npv_hi - npv_base,
            "swing":      abs(npv_hi - npv_lo),
        })

    resultados.sort(key=lambda r: r["swing"], reverse=True)
    return resultados


# ======================================================
# EXPORTAR A EXCEL (hoja extra)
# ======================================================

def exportar_montecarlo_excel(
        archivo,
        resultado_mc,
        resultado_tornado,
):
    """Agrega hojas 'Monte Carlo' y 'Tornado' a un .xlsx
    existente (o crea uno nuevo)."""

    from openpyxl import load_workbook, Workbook
    from openpyxl.styles import Font

    import os
    if os.path.exists(archivo):
        wb = load_workbook(archivo)
    else:
        wb = Workbook()
        if "Sheet" in wb.sheetnames:
            del wb["Sheet"]

    # -- hoja Monte Carlo --
    if "Monte Carlo" in wb.sheetnames:
        del wb["Monte Carlo"]
    ws = wb.create_sheet("Monte Carlo")

    bold = Font(bold=True)
    stats = resultado_mc["stats"]

    ws.cell(1, 1, "MONTE CARLO SUMMARY").font = bold
    summary = [
        ("Runs",        stats["n"]),
        ("NPV mean",    stats["npv_mean"]),
        ("NPV std",     stats["npv_std"]),
        ("NPV min",     stats["npv_min"]),
        ("NPV P10",     stats["npv_p10"]),
        ("NPV P50",     stats["npv_p50"]),
        ("NPV P90",     stats["npv_p90"]),
        ("NPV max",     stats["npv_max"]),
        ("P(NPV<0)",    stats["p_npv_neg"]),
        ("IRR P10",     stats["irr_p10"]),
        ("IRR P50",     stats["irr_p50"]),
        ("IRR P90",     stats["irr_p90"]),
        ("IRR valid #", stats["irr_n_valid"]),
    ]
    for i, (k, v) in enumerate(summary, start=2):
        ws.cell(i, 1, k)
        ws.cell(i, 2, v)

    # -- raw runs --
    fila_raw = len(summary) + 4
    ws.cell(fila_raw, 1, "RAW RUNS").font = bold

    headers = ["Run", "NPV", "IRR"] + [v.nombre for v in resultado_mc["variables"]]
    for col, h in enumerate(headers, start=1):
        ws.cell(fila_raw + 1, col, h).font = bold

    for i, (npv, irr, muestras) in enumerate(zip(
        resultado_mc["npvs"],
        resultado_mc["irrs"],
        resultado_mc["samples"],
    )):
        ws.cell(fila_raw + 2 + i, 1, i + 1)
        ws.cell(fila_raw + 2 + i, 2, npv)
        ws.cell(fila_raw + 2 + i, 3, irr if irr is not None else "")
        for j, m in enumerate(muestras):
            ws.cell(fila_raw + 2 + i, 4 + j, m)

    # -- hoja Tornado --
    if "Tornado" in wb.sheetnames:
        del wb["Tornado"]
    ws_t = wb.create_sheet("Tornado")

    ws_t.cell(1, 1, "TORNADO CHART (deterministic)").font = bold
    headers_t = ["Variable", "NPV @ min", "NPV @ base", "NPV @ max",
                 "Δ low", "Δ high", "Swing"]
    for col, h in enumerate(headers_t, start=1):
        ws_t.cell(2, col, h).font = bold

    for i, r in enumerate(resultado_tornado, start=3):
        ws_t.cell(i, 1, r["nombre"])
        ws_t.cell(i, 2, r["npv_low"])
        ws_t.cell(i, 3, r["npv_base"])
        ws_t.cell(i, 4, r["npv_high"])
        ws_t.cell(i, 5, r["delta_low"])
        ws_t.cell(i, 6, r["delta_high"])
        ws_t.cell(i, 7, r["swing"])

    wb.save(archivo)
