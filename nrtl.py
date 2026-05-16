"""
NRTL — Coeficientes de actividad para mezclas líquidas no ideales (Capa 6).

Carga lazy desde data/nrtl_db.md (10 pares binarios) y provee:

    gamma(names, x_vec, T_K)               → coef de actividad por componente
    activity_coeff_binary(names, x, T_K)   → atajo binario
    bubble_point(names, x_vec, P_bar)      → (T_bub_K, y_vec)
    dew_point(names, y_vec, P_bar)         → (T_dew_K, x_vec)
    flash_TP(names, z_vec, T_K, P_bar)     → {'V_frac', 'x', 'y'}
    find_azeotrope(names, P_bar)           → {'x_az', 'T_az_K', 'kind'} | None
    has_params(name1, name2)               → bool

NRTL binario:
    ln γ₁ = x₂² [ τ₂₁ (G₂₁/(x₁+x₂G₂₁))² + τ₁₂ G₁₂/(x₂+x₁G₁₂)² ]
    G_ij  = exp(-α_ij · τ_ij)
    τ_ij  = A_ij/T + B_ij

Pᵢ_sat(T) se obtiene del antoine de Capa 1 (compounds_db / thermo_db).
"""

import math
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_NRTL_PATH = Path(__file__).parent / "data" / "nrtl_db.md"


# ============================================================
# Parser de parámetros NRTL
# ============================================================

# Cache de parámetros: {(name1, name2): {A12, B12, A21, B21, alpha, T_min, T_max}}
_PARAMS: Optional[Dict[Tuple[str, str], dict]] = None


def _parse_nrtl_db() -> Dict[Tuple[str, str], dict]:
    """Lee data/nrtl_db.md y extrae los parámetros NRTL para cada par."""
    if not _NRTL_PATH.is_file():
        return {}
    text = _NRTL_PATH.read_text(encoding="utf-8")
    out: Dict[Tuple[str, str], dict] = {}
    # Cada sección de par empieza con '## name1-name2'
    sections = re.split(r"^## ([a-z_]+)-([a-z_]+)\s*$", text, flags=re.MULTILINE)
    # sections[0] = preamble; después tuplas (name1, name2, body)
    for i in range(1, len(sections), 3):
        if i + 2 > len(sections):
            break
        name1 = sections[i].strip()
        name2 = sections[i+1].strip()
        body = sections[i+2]
        params = _parse_pair_body(body)
        if params is None:
            continue
        out[(name1, name2)] = params
    return out


def _parse_pair_body(body: str) -> Optional[dict]:
    """Extrae A_12, B_12, A_21, B_21, alpha del cuerpo de una sección."""
    p = {}
    for key, label in [('A_12', 'A_12'), ('B_12', 'B_12'),
                        ('A_21', 'A_21'), ('B_21', 'B_21')]:
        # Patron: '| A_12 (...) | -55.171 | ...'
        m = re.search(rf"\|\s*{re.escape(label)}\s*[^|]*\|\s*([+-]?[\d.eE+-]+)",
                       body)
        if m is None:
            return None
        try:
            p[key] = float(m.group(1))
        except ValueError:
            return None
    # alpha (puede aparecer como '| α_12 = α_21 | 0.3031 | — |')
    m = re.search(r"\|\s*α_12[^|]*\|\s*([+-]?[\d.eE+-]+)", body)
    if m is None:
        return None
    p['alpha'] = float(m.group(1))
    # Rango T válido (opcional)
    m = re.search(r"Rango T válido:\*\*\s*(\d+)-(\d+)\s*K", body)
    if m:
        p['T_min_K'] = float(m.group(1))
        p['T_max_K'] = float(m.group(2))
    else:
        p['T_min_K'] = 273.0
        p['T_max_K'] = 500.0
    return p


def _ensure_loaded() -> Dict[Tuple[str, str], dict]:
    global _PARAMS
    if _PARAMS is None:
        _PARAMS = _parse_nrtl_db()
    return _PARAMS


def has_params(name1: str, name2: str) -> bool:
    """True si hay parámetros NRTL para el par (en cualquier orden)."""
    p = _ensure_loaded()
    return (name1, name2) in p or (name2, name1) in p


def _get_pair(name_i: str, name_j: str) -> Optional[dict]:
    """Devuelve params para i,j respetando dirección.
    Si el .md tiene (1=i, 2=j), retorna {A12, B12, A21, B21, alpha} directo.
    Si tiene (1=j, 2=i), swap (A12↔A21, B12↔B21)."""
    p = _ensure_loaded()
    if (name_i, name_j) in p:
        return p[(name_i, name_j)]
    if (name_j, name_i) in p:
        # Swap: lo que era 1→2 ahora es 2→1
        d = p[(name_j, name_i)]
        return {'A_12': d['A_21'], 'B_12': d['B_21'],
                'A_21': d['A_12'], 'B_21': d['B_12'],
                'alpha': d['alpha'],
                'T_min_K': d['T_min_K'], 'T_max_K': d['T_max_K']}
    return None


# ============================================================
# NRTL multicomponente
# ============================================================

def gamma(names: List[str], x_vec: List[float], T_K: float) -> List[float]:
    """Coeficientes de actividad NRTL para mezcla multicomponente.

    Implementa la forma estándar NRTL multicomponente:
        ln γᵢ = [Σⱼ xⱼ τⱼᵢ Gⱼᵢ] / [Σₖ xₖ Gₖᵢ]
              + Σⱼ (xⱼ Gᵢⱼ / Σₖ xₖ Gₖⱼ) · (τᵢⱼ − Σₘ xₘ τₘⱼ Gₘⱼ / Σₖ xₖ Gₖⱼ)

    Args:
        names: lista de nombres canónicos thermo_db, e.g. ['ethanol','water']
        x_vec: fracciones molares (deben sumar ~1)
        T_K:   temperatura

    Returns:
        list de coef de actividad γᵢ, mismo orden que `names`.
        Si falta un par binario, devuelve None (caller debe decidir
        fallback a Raoult ideal γᵢ = 1).
    """
    n = len(names)
    if n != len(x_vec) or n < 1:
        return None
    # Construir matrices τ y G (n×n)
    tau = [[0.0]*n for _ in range(n)]
    G   = [[1.0]*n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                tau[i][j] = 0.0
                G[i][j]   = 1.0
                continue
            pair = _get_pair(names[i], names[j])
            if pair is None:
                return None    # no hay datos para este par
            # _get_pair retorna A_12, A_21 con convención 1=i, 2=j
            # τ_ij usa A_12 (dirección i→j)
            tau[i][j] = pair['A_12'] / T_K + pair['B_12']
            G[i][j]   = math.exp(-pair['alpha'] * tau[i][j])

    # Pre-cálculos comunes
    # S_k[j] = Σ_k x_k · G_kj
    S = [sum(x_vec[k] * G[k][j] for k in range(n)) for j in range(n)]
    # C_j = Σ_m x_m · τ_mj · G_mj
    C = [sum(x_vec[m] * tau[m][j] * G[m][j] for m in range(n)) for j in range(n)]

    ln_gamma = [0.0] * n
    for i in range(n):
        # Primer término: C_i / S_i
        if S[i] <= 0:
            return None
        t1 = C[i] / S[i]
        # Segundo término: Σ_j (x_j G_ij / S_j) · (τ_ij - C_j / S_j)
        t2 = 0.0
        for j in range(n):
            if S[j] <= 0:
                return None
            t2 += (x_vec[j] * G[i][j] / S[j]) * (tau[i][j] - C[j] / S[j])
        ln_gamma[i] = t1 + t2

    # Cap para no overflow
    return [math.exp(max(min(lg, 30.0), -30.0)) for lg in ln_gamma]


def activity_coeff_binary(names: List[str], x1: float, T_K: float) -> Optional[Tuple[float, float]]:
    """Coef de actividad binario para componente 1 (concentración x1) y 2.

    Atajo más simple que gamma() para uso interactivo y plots.
    """
    if len(names) != 2:
        return None
    res = gamma(names, [x1, 1.0 - x1], T_K)
    if res is None:
        return None
    return (res[0], res[1])


# ============================================================
# Presión de saturación (Antoine) — wrapper
# ============================================================

def _Psat_bar(comp_name: str, T_K: float) -> Optional[float]:
    """Presión de saturación en bar para componente a T_K, usando
    Antoine de thermo_db."""
    try:
        import thermo_db as _td
    except ImportError:
        return None
    c = _td.get(comp_name)
    if c is None:
        return None
    # thermo_db.vapor_pressure_kPa(T_C)
    T_C = T_K - 273.15
    p_kpa = c.vapor_pressure_kPa(T_C)
    if p_kpa is None or p_kpa <= 0:
        return None
    return p_kpa / 100.0   # kPa → bar


# ============================================================
# Punto de burbuja y rocío
# ============================================================

def bubble_point(names: List[str], x_vec: List[float], P_bar: float,
                  T_init_K: float = 350.0, tol: float = 1e-4,
                  max_iter: int = 60) -> Optional[Tuple[float, List[float]]]:
    """Punto de burbuja: dada composición líquida x y P, encontrar T_bub
    tal que Σᵢ xᵢ·γᵢ(T,x)·Pᵢ_sat(T) = P, y luego yᵢ = xᵢ·γᵢ·Pᵢ_sat/P.

    Newton-Raphson sobre T.

    Returns: (T_bub_K, y_vec) o None si no converge / falta data.
    """
    n = len(names)
    if n != len(x_vec):
        return None
    s = sum(x_vec)
    if s <= 0:
        return None
    x = [xi / s for xi in x_vec]   # renormalizar

    T = T_init_K
    for it in range(max_iter):
        g = gamma(names, x, T)
        if g is None:
            return None
        Psats = [_Psat_bar(names[i], T) for i in range(n)]
        if any(p is None for p in Psats):
            return None
        # Función residual: f(T) = Σ xᵢ γᵢ Pᵢ_sat - P
        psum = sum(x[i] * g[i] * Psats[i] for i in range(n))
        f = psum - P_bar
        if abs(f) < tol * P_bar:
            y = [x[i] * g[i] * Psats[i] / P_bar for i in range(n)]
            return (T, y)
        # Derivada numérica (Newton)
        dT = 0.05
        g2 = gamma(names, x, T + dT)
        Psats2 = [_Psat_bar(names[i], T + dT) for i in range(n)]
        if g2 is None or any(p is None for p in Psats2):
            return None
        f2 = sum(x[i] * g2[i] * Psats2[i] for i in range(n)) - P_bar
        df = (f2 - f) / dT
        if abs(df) < 1e-12:
            return None
        T_new = T - f / df
        # Damping para evitar T negativa o explosiva
        if T_new < 200:
            T_new = 0.5 * (T + 200)
        if T_new > 700:
            T_new = 0.5 * (T + 700)
        T = T_new
    return None


def dew_point(names: List[str], y_vec: List[float], P_bar: float,
              T_init_K: float = 350.0, tol: float = 1e-4,
              max_iter: int = 60) -> Optional[Tuple[float, List[float]]]:
    """Punto de rocío: dada composición vapor y y P, encontrar T_dew
    tal que Σᵢ yᵢ·P / (γᵢ·Pᵢ_sat) = 1, con xᵢ correspondiente.

    Resuelto iterativamente: γᵢ depende de xᵢ que depende de γᵢ.
    Fixed-point con damping.
    """
    n = len(names)
    if n != len(y_vec):
        return None
    s = sum(y_vec)
    if s <= 0:
        return None
    y = [yi / s for yi in y_vec]
    # Estimación inicial: x = y (mezcla ideal)
    x = list(y)
    T = T_init_K

    for it in range(max_iter):
        g = gamma(names, x, T)
        if g is None:
            return None
        Psats = [_Psat_bar(names[i], T) for i in range(n)]
        if any(p is None for p in Psats):
            return None
        # Calcular xᵢ asumiendo γ y Psat actuales: xᵢ = yᵢ·P/(γᵢ·Pᵢ_sat)
        x_new = [y[i] * P_bar / (g[i] * Psats[i]) for i in range(n)]
        s_x = sum(x_new)
        # Si suma ≈ 1, T es correcta; si > 1, T baja; si < 1, T sube.
        if abs(s_x - 1.0) < tol:
            # Re-normalizar x y devolver
            x_norm = [xi / s_x for xi in x_new]
            return (T, x_norm)
        # Adjust T: Newton-like sobre log(Σx-1)
        dT = 0.05
        g2 = gamma(names, x, T + dT)
        Psats2 = [_Psat_bar(names[i], T + dT) for i in range(n)]
        if g2 is None or any(p is None for p in Psats2):
            return None
        s_x2 = sum(y[i] * P_bar / (g2[i] * Psats2[i]) for i in range(n))
        df = (s_x2 - s_x) / dT
        if abs(df) < 1e-12:
            return None
        T_new = T - (s_x - 1.0) / df
        if T_new < 200: T_new = 0.5 * (T + 200)
        if T_new > 700: T_new = 0.5 * (T + 700)
        T = T_new
        # Update x para próxima iteración (damped)
        x = [0.5 * (xi + xni / s_x) for xi, xni in zip(x, x_new)]
    return None


# ============================================================
# Flash isotérmico (TP)
# ============================================================

def flash_TP(names: List[str], z_vec: List[float], T_K: float, P_bar: float,
              max_iter: int = 80, tol: float = 1e-6) -> Optional[Dict]:
    """Flash isotérmico: dada composición global z, T y P, calcular
    fracción vapor V/F y composiciones x (líquido) y y (vapor).

    Resuelve Rachford-Rice:
        Σᵢ zᵢ·(Kᵢ−1) / (1 + V·(Kᵢ−1)) = 0

    donde Kᵢ = γᵢ(T,x)·Pᵢ_sat(T) / P.

    Iteramos: dados Kᵢ → resolver R-R por V → x,y → recalcular γ → nuevo K.

    Returns: dict {'V_frac', 'x', 'y', 'K', 'iterations'} o None.
    """
    n = len(names)
    if n != len(z_vec):
        return None
    z = [zi / sum(z_vec) for zi in z_vec]   # renormalizar

    # Estimación inicial: K_i ≈ Pᵢ_sat(T) / P  (Raoult ideal)
    Psats = [_Psat_bar(names[i], T_K) for i in range(n)]
    if any(p is None for p in Psats):
        return None
    K = [Psats[i] / P_bar for i in range(n)]

    V = 0.5
    for it in range(max_iter):
        # Resolver Rachford-Rice por V
        V_new = _solve_rr(z, K)
        if V_new is None:
            return None
        V = V_new
        # Calcular x e y
        x = [z[i] / (1 + V * (K[i] - 1)) for i in range(n)]
        y = [K[i] * x[i] for i in range(n)]
        # Normalizar
        sx = sum(x); sy = sum(y)
        if sx <= 0 or sy <= 0:
            return None
        x = [xi / sx for xi in x]
        y = [yi / sy for yi in y]
        # Recalcular γ y K
        g = gamma(names, x, T_K)
        if g is None:
            return None
        K_new = [g[i] * Psats[i] / P_bar for i in range(n)]
        # Check convergencia
        max_dk = max(abs(K_new[i] - K[i]) / max(K[i], 1e-12)
                      for i in range(n))
        K = K_new
        if max_dk < tol:
            break
    # Si V < 0: todo líquido; V > 1: todo vapor
    if V < 0:
        return dict(V_frac=0.0, x=z, y=[0.0]*n, K=K, iterations=it+1)
    if V > 1:
        return dict(V_frac=1.0, x=[0.0]*n, y=z, K=K, iterations=it+1)
    return dict(V_frac=V, x=x, y=y, K=K, iterations=it+1)


def _solve_rr(z: List[float], K: List[float]) -> Optional[float]:
    """Bisección sobre la ecuación Rachford-Rice
        F(V) = Σᵢ zᵢ(Kᵢ−1)/(1 + V(Kᵢ−1)) = 0
    en V ∈ [0, 1]."""
    n = len(z)
    def F(V):
        try:
            return sum(z[i] * (K[i] - 1) / (1 + V * (K[i] - 1))
                       for i in range(n))
        except ZeroDivisionError:
            return float('nan')
    F0, F1 = F(0.0), F(1.0)
    if F0 <= 0:
        return 0.0
    if F1 >= 0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        Fm = F(mid)
        if abs(Fm) < 1e-10:
            return mid
        if Fm > 0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ============================================================
# Búsqueda de azeotropo
# ============================================================

def find_azeotrope(names: List[str], P_bar: float,
                    n_scan: int = 50) -> Optional[Dict]:
    """Para mezcla binaria, busca azeotropo escaneando T-x-y.

    Un azeotropo es un punto donde xᵢ = yᵢ ∀i.  Para binarias: x₁ = y₁.
    Equivalente: α (volatilidad relativa) = 1 en ese punto.

    Retorna {'x_az', 'T_az_K', 'kind': 'positive'|'negative'|None} o None
    si no hay azeotropo.

    Solo para n=2 (binario).
    """
    if len(names) != 2:
        return None
    xs = [i / n_scan for i in range(1, n_scan)]
    table = []
    for x in xs:
        res = bubble_point(names, [x, 1 - x], P_bar)
        if res is None:
            continue
        T, y = res
        # y[0] - x[0] cambia de signo en azeotropo
        table.append((x, T, y[0]))
    if not table:
        return None
    # Buscar cambio de signo en (y - x)
    for i in range(len(table) - 1):
        x1, T1, y1 = table[i]
        x2, T2, y2 = table[i+1]
        d1 = y1 - x1
        d2 = y2 - x2
        if d1 * d2 < 0:
            # Hay azeotropo entre x1 y x2 — interpolación lineal
            frac = abs(d1) / (abs(d1) + abs(d2))
            x_az = x1 + frac * (x2 - x1)
            T_az = T1 + frac * (T2 - T1)
            # Determinar tipo: positivo si T_az < T_pure de ambos
            T_pure_1 = bubble_point(names, [1.0, 0.0], P_bar)
            T_pure_2 = bubble_point(names, [0.0, 1.0], P_bar)
            kind = "unknown"
            if T_pure_1 and T_pure_2:
                T_min_pure = min(T_pure_1[0], T_pure_2[0])
                if T_az < T_min_pure:
                    kind = "positive"     # min-boiling
                else:
                    kind = "negative"     # max-boiling
            return {'x_az': x_az, 'T_az_K': T_az, 'kind': kind}
    return None
