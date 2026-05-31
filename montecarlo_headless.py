"""
montecarlo_headless.py — Monte Carlo económico HEADLESS sobre simulate().

PORT-NUEVO (decisión de Fase 0): el motor de cash flow es el de simulate()
(categorize_opex + capex.compute_fci + cost_of_manufacture_components +
profitability_indicators), NO el CostModel/CashFlowModel de flujoflujoclass.
Por eso este MC NO reproduce número-a-número al montecarlo.py viejo: el modelo
económico subyacente es distinto (Turton constant-CF/MACRS, sin ramp-up,
royalties ni interés-en-FCOP).  Se valida internamente (NPV base == simulate()
base; sanity de distribución; tornado coherente).

La ESTADÍSTICA DE SAMPLING (VariableIncierta, inverse_cdf, cópula gaussiana,
percentiles) se porta VERBATIM de montecarlo.py — es correcta y no se
reimplementa.  Con el mismo seed, las muestras son idénticas bit a bit.

Sin dependencia de Tk / PySide6 / flujoflujoclass / ana_qt.
"""
import math
import statistics
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict

import numpy as np

# ======================================================
# CONSTANTES  (verbatim de montecarlo.py)
# ======================================================
KIND_PRODUCT_PRICE      = "product_price"
KIND_RAW_MATERIAL_PRICE = "raw_material_price"
KIND_ISBL               = "isbl"

DIST_TRIANGULAR = "triangular"
DIST_NORMAL     = "normal"
DIST_UNIFORM    = "uniform"

VALID_DISTS = (DIST_TRIANGULAR, DIST_NORMAL, DIST_UNIFORM)


# ======================================================
# VARIABLE INCIERTA  (verbatim de montecarlo.py)
# ======================================================
@dataclass
class VariableIncierta:
    """Spec de una variable a someter a Monte Carlo.

    kind:   KIND_PRODUCT_PRICE | KIND_RAW_MATERIAL_PRICE | KIND_ISBL
    indice: posición dentro de la lista de productos / materias primas
            (ver list_uncertain_targets).  Ignorado para ISBL.
    Para ISBL, los valores van en USD (= econ_inputs['isbl_override_usd']).
    dist:   DIST_TRIANGULAR | DIST_NORMAL | DIST_UNIFORM
        triangular: a=min, c=mode, b=max
        uniform:    a=min, b=max  (mode ignorado)
        normal:     mean=mode, std=(max-min)/4
    """
    kind: str
    indice: int
    nombre: str
    valor_min: float
    valor_mode: float
    valor_max: float
    dist: str = DIST_TRIANGULAR

    def __post_init__(self):
        if self.dist not in VALID_DISTS:
            raise ValueError(f"dist inválida: {self.dist!r}")
        if self.dist in (DIST_TRIANGULAR, DIST_UNIFORM):
            if not (self.valor_min <= self.valor_max):
                raise ValueError(f"'{self.nombre}': min ≤ max requerido")
        if self.dist == DIST_TRIANGULAR:
            if not (self.valor_min <= self.valor_mode <= self.valor_max):
                raise ValueError(f"'{self.nombre}': min ≤ mode ≤ max requerido")

    # ---- inverse CDF, recibe u ∈ (0,1) ----
    def inverse_cdf(self, u):
        u = np.clip(u, 1e-10, 1 - 1e-10)
        if self.dist == DIST_UNIFORM:
            return self.valor_min + (self.valor_max - self.valor_min) * u
        if self.dist == DIST_NORMAL:
            mean = self.valor_mode
            std = max((self.valor_max - self.valor_min) / 4.0, 1e-12)
            return mean + std * _norm_ppf_vec(u)
        # triangular
        a, b, c = self.valor_min, self.valor_max, self.valor_mode
        Fc = (c - a) / (b - a) if b > a else 0.5
        result = np.where(
            u <= Fc,
            a + np.sqrt(u * (b - a) * (c - a)),
            b - np.sqrt((1 - u) * (b - a) * (b - c)),
        )
        return result

    def sample(self, rng):
        u = rng.random()
        return float(self.inverse_cdf(np.array([u]))[0])


_norm_inv_cdf_scalar = statistics.NormalDist().inv_cdf
_norm_ppf_vec = np.vectorize(_norm_inv_cdf_scalar)


# ======================================================
# SAMPLING CORRELACIONADO — Gaussian copula  (verbatim)
# ======================================================
def _matriz_correlacion_a_array(K, correlacion):
    if correlacion is None:
        return np.eye(K)
    if isinstance(correlacion, dict):
        M = np.eye(K)
        for (i, j), rho in correlacion.items():
            if i == j:
                continue
            M[i, j] = rho
            M[j, i] = rho
        return M
    M = np.asarray(correlacion, dtype=float)
    if M.shape != (K, K):
        raise ValueError(
            f"Matriz correlación con shape {M.shape}, se esperaba ({K},{K})")
    M = (M + M.T) / 2
    np.fill_diagonal(M, 1.0)
    return M


def _muestrear_correlacionado(variables, n_runs, correlacion, seed):
    """Array (n_runs, K) de muestras según las dist marginales y la
    matriz `correlacion`.  Mismo seed → muestras idénticas a montecarlo.py."""
    K = len(variables)
    rng = np.random.default_rng(seed)
    M = _matriz_correlacion_a_array(K, correlacion)
    if K == 0:
        return np.empty((n_runs, 0))
    if np.allclose(M, np.eye(K)):
        U = rng.random((n_runs, K))
    else:
        try:
            L = np.linalg.cholesky(M)
        except np.linalg.LinAlgError as e:
            raise ValueError(
                "Matriz de correlación no es positive semi-definite.") from e
        Z = rng.standard_normal((n_runs, K))
        Z_corr = Z @ L.T
        U = 0.5 * (1.0 + np.vectorize(math.erf)(Z_corr / math.sqrt(2)))
    X = np.empty_like(U)
    for k, v in enumerate(variables):
        X[:, k] = v.inverse_cdf(U[:, k])
    return X


# ======================================================
# ESTADÍSTICOS  (verbatim de montecarlo.py)
# ======================================================
def _percentil(valores_ordenados, p):
    n = len(valores_ordenados)
    if n == 0:
        return None
    if n == 1:
        return valores_ordenados[0]
    k = (n - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, n - 1)
    return (valores_ordenados[f]
            + (k - f) * (valores_ordenados[c] - valores_ordenados[f]))


def _estadisticos(npvs, irrs):
    npvs_ord = sorted(npvs)
    n = len(npvs)
    mean = sum(npvs) / n if n else 0.0
    var = (sum((x - mean) ** 2 for x in npvs) / (n - 1)) if n > 1 else 0.0
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
        "irr_mean":    (sum(irrs_validas) / len(irrs_validas)
                        if irrs_validas else None),
        "irr_p10":     (_percentil(sorted(irrs_validas), 10)
                        if irrs_validas else None),
        "irr_p50":     (_percentil(sorted(irrs_validas), 50)
                        if irrs_validas else None),
        "irr_p90":     (_percentil(sorted(irrs_validas), 90)
                        if irrs_validas else None),
        "irr_n_valid": len(irrs_validas),
    }


# ======================================================
# NÚCLEO NUEVO — evaluación sobre simulate()
# ======================================================
def _solve(flowsheet_dict):
    """from_dict + solve UNA vez (flows invariantes a precios/ISBL)."""
    import flowsheet_model as fm
    import flowsheet_solver as fsv
    fs = fm.Flowsheet.from_dict(flowsheet_dict)
    fsv.solve(fs)
    return fs


def _targets(fs):
    """Listas ordenadas de streams producto (role='product') y materia
    prima (role='feed'), índice = posición — igual que categorize_opex."""
    products = [s for s in fs.streams.values() if s.role == "product"]
    raws     = [s for s in fs.streams.values() if s.role == "feed"]
    return products, raws


def list_uncertain_targets(flowsheet_dict):
    """Targets sampleables del flowsheet, para que el panel construya las
    VariableIncierta con el índice correcto.  Devuelve dict JSON-safe."""
    import capex
    fs = _solve(flowsheet_dict)
    products, raws = _targets(fs)
    isbl = capex.compute_fci(fs).get("sum_cbm")
    return {
        "products": [{"index": i, "name": s.name,
                      "base_price_usd_per_tm": float(getattr(s, "price_usd_per_tm", 0.0))}
                     for i, s in enumerate(products)],
        "raw_materials": [{"index": i, "name": s.name,
                           "base_price_usd_per_tm": float(getattr(s, "price_usd_per_tm", 0.0))}
                          for i, s in enumerate(raws)],
        "isbl": {"base_usd": float(isbl) if isbl else None},
    }


def _apply_row(fs, products, raws, variables, fila, econ_inputs):
    """Aplica una fila de muestras a fs (precios) + econ_inputs (ISBL).
    Devuelve econ_inputs_run (copia con isbl_override si corresponde)."""
    run_inputs = dict(econ_inputs)
    for var, valor in zip(variables, fila):
        v = float(valor)
        if var.kind == KIND_PRODUCT_PRICE:
            products[var.indice].price_usd_per_tm = v
        elif var.kind == KIND_RAW_MATERIAL_PRICE:
            raws[var.indice].price_usd_per_tm = v
        elif var.kind == KIND_ISBL:
            run_inputs["isbl_override_usd"] = v
        else:
            raise ValueError(f"Kind desconocido: {var.kind}")
    return run_inputs


def _eval_npv_irr(fs, econ_inputs_run):
    """Llama la cadena económica de simulate() sobre el fs resuelto.
    Devuelve (npv_musd, irr_frac).  Unidades = contrato del MC viejo:
    NPV en MUSD, IRR en fracción."""
    import simulate_engine as se
    econ = se._economics(fs, econ_inputs_run)
    npv = econ.get("NPV_usd")
    irr = econ.get("IRR_pct")
    npv_musd = (float(npv) / 1e6) if npv is not None else float("nan")
    irr_frac = (float(irr) / 100.0) if isinstance(irr, (int, float)) else None
    return npv_musd, irr_frac


def run_monte_carlo(flowsheet_dict, variables: List[VariableIncierta],
                    econ_inputs: Optional[dict] = None,
                    n_runs: int = 5000, seed: Optional[int] = None,
                    correlacion=None) -> Dict:
    """Monte Carlo headless sobre simulate().

    flowsheet_dict: to_dict() de un Flowsheet.
    variables:      lista de VariableIncierta (precios producto/RM, ISBL).
    econ_inputs:    overrides económicos de simulate() (tax/disc/life/dep…).
    Devuelve {npvs, irrs, samples, variables, stats} JSON-serializable.
    El sampler es el de montecarlo.py (mismo seed → mismas muestras)."""
    econ_inputs = dict(econ_inputs or {})
    samples = _muestrear_correlacionado(variables, n_runs, correlacion, seed)
    fs = _solve(flowsheet_dict)
    products, raws = _targets(fs)

    npvs, irrs = [], []
    for n in range(n_runs):
        fila = samples[n] if samples.shape[1] else []
        run_inputs = _apply_row(fs, products, raws, variables, fila, econ_inputs)
        npv, irr = _eval_npv_irr(fs, run_inputs)
        npvs.append(npv)
        irrs.append(irr)

    return {
        "npvs":      npvs,
        "irrs":      irrs,
        "samples":   samples.tolist(),
        "variables": [_serialize_var(v) for v in variables],
        "stats":     _estadisticos(npvs, irrs),
        "engine":    "simulate",   # PORT-NUEVO: no comparable 1:1 al MC viejo
    }


def run_tornado(flowsheet_dict, variables: List[VariableIncierta],
                econ_inputs: Optional[dict] = None) -> List[Dict]:
    """Tornado determinístico (vary-one-at-a-time entre min y max, resto en
    mode).  Mismo shape que montecarlo.correr_tornado.  NPV en MUSD."""
    econ_inputs = dict(econ_inputs or {})
    fs = _solve(flowsheet_dict)
    products, raws = _targets(fs)

    # base: todas en mode
    base_inputs = _apply_row(
        fs, products, raws, variables,
        [v.valor_mode for v in variables], econ_inputs)
    npv_base, _ = _eval_npv_irr(fs, base_inputs)

    resultados = []
    for v in variables:
        modes = [vv.valor_mode for vv in variables]
        idx = variables.index(v)
        # low
        lo = list(modes); lo[idx] = v.valor_min
        npv_lo, _ = _eval_npv_irr(
            fs, _apply_row(fs, products, raws, variables, lo, econ_inputs))
        # high
        hi = list(modes); hi[idx] = v.valor_max
        npv_hi, _ = _eval_npv_irr(
            fs, _apply_row(fs, products, raws, variables, hi, econ_inputs))
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


def _serialize_var(v: VariableIncierta) -> dict:
    return asdict(v)
