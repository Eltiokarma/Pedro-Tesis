"""
EOS — Ecuación de estado cúbica Peng-Robinson (1976).

Fundación EOS del repo (PR-1).  Módulo ESTRICTAMENTE ADITIVO: no toca el VLE
por modelo de actividad (nrtl.py + Antoine).  La integración al flash (φ-φ) es
un PR aparte (PR-2); aquí solo se provee — y se valida — la maquinaria PR pura.

Trazabilidad
------------
- Peng, D.Y. & Robinson, D.B. "A New Two-Constant Equation of State".
  Ind. Eng. Chem. Fundam. 15(1):59-64 (1976).
- Expresión del coeficiente de fugacidad: Smith, Van Ness & Abbott,
  "Introduction to Chemical Engineering Thermodynamics", 7ª ed., Cap. 14.

Unidades internas (SI): T [K], P [Pa], V [m³/mol], R = 8.314 J/mol·K.
Los wrappers que leen thermo_db convierten desde tc_c [°C] y pc_bar [bar].

Limitación documentada
----------------------
PR sin volume-translation subestima la densidad del líquido y es pobre para
compuestos polares/asociativos (agua, ácidos, alcoholes).  Para esos casos,
NRTL+Antoine sigue siendo el camino.  El EOS gana en gases / no-condensables
y a alta presión, donde Antoine no aplica (y donde el repo hoy devuelve
1e-10 "no-volátil", mandando gases supercríticos 100% al líquido).
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

R = 8.314  # J/mol·K  (== thermo_db.R_GAS)

_SQRT2 = math.sqrt(2.0)


# ============================================================
# Cúbica: raíces reales (Cardano / método trigonométrico)
# ============================================================

def _cbrt(v: float) -> float:
    """Raíz cúbica real con signo (math.cbrt es 3.11+, pero esto es portable)."""
    return math.copysign(abs(v) ** (1.0 / 3.0), v)


def _cubic_real_roots(b: float, c: float, d: float) -> List[float]:
    """Raíces reales del cúbico mónico  z³ + b·z² + c·z + d = 0.

    Sustitución deprimida z = t − b/3 → t³ + p·t + q = 0, y resolución
    analítica por el discriminante (Cardano para 1 raíz real; método
    trigonométrico para 3 raíces reales).
    """
    p = c - b * b / 3.0
    q = 2.0 * b ** 3 / 27.0 - b * c / 3.0 + d
    shift = -b / 3.0
    disc = (q * q) / 4.0 + (p ** 3) / 27.0

    if disc > 1e-14:
        # Una raíz real.
        sq = math.sqrt(disc)
        u = _cbrt(-q / 2.0 + sq)
        v = _cbrt(-q / 2.0 - sq)
        return [u + v + shift]

    if disc < -1e-14:
        # Tres raíces reales distintas (método trigonométrico).
        r3 = math.sqrt(-(p ** 3) / 27.0)
        cosarg = max(-1.0, min(1.0, (-q / 2.0) / r3))
        phi = math.acos(cosarg)
        m = 2.0 * math.sqrt(-p / 3.0)
        return [m * math.cos((phi + 2.0 * math.pi * k) / 3.0) + shift
                for k in range(3)]

    # disc ≈ 0: raíz múltiple.
    if abs(p) < 1e-14:
        return [shift]
    u = _cbrt(-q / 2.0)
    return [2.0 * u + shift, -u + shift]


def z_roots(A: float, B: float) -> List[float]:
    """Raíces reales físicas de la cúbica PR en Z (factor de compresibilidad):

        Z³ − (1−B)·Z² + (A − 3B² − 2B)·Z − (A·B − B² − B³) = 0

    Filtra reales con Z > B (requisito de ln(Z−B)) y ordena ascendente.
    Líquido = menor raíz física, vapor = mayor.  Si el sistema es monofásico
    (una sola raíz real) devuelve esa única raíz; no inventa una segunda.
    """
    b2 = -(1.0 - B)
    b1 = (A - 3.0 * B * B - 2.0 * B)
    b0 = -(A * B - B * B - B ** 3)
    raw = _cubic_real_roots(b2, b1, b0)
    # Físicas: Z real > B (volumen positivo, argumento de log válido).
    phys = sorted(z for z in raw if z > B + 1e-12)
    return phys


# ============================================================
# Parámetros PR puros
# ============================================================

def pr_a_b(Tc_K: float, Pc_Pa: float, omega: float,
           T_K: float) -> Tuple[float, float]:
    """Parámetros PR del componente puro a temperatura T.

    Devuelve (a(T) [Pa·m⁶/mol²], b [m³/mol]).
    """
    b = 0.07780 * R * Tc_K / Pc_Pa
    kappa = 0.37464 + 1.54226 * omega - 0.26992 * omega * omega
    alpha = (1.0 + kappa * (1.0 - math.sqrt(T_K / Tc_K))) ** 2
    a = 0.45724 * R * R * Tc_K * Tc_K / Pc_Pa * alpha
    return a, b


def _ln_phi_from_Z(Z: float, A: float, B: float) -> float:
    """ln φ puro a partir de una raíz Z y de (A, B)."""
    return (
        (Z - 1.0)
        - math.log(Z - B)
        - A / (2.0 * _SQRT2 * B)
        * math.log((Z + (1.0 + _SQRT2) * B) / (Z + (1.0 - _SQRT2) * B))
    )


def _AB(a: float, b: float, T_K: float, P_Pa: float) -> Tuple[float, float]:
    A = a * P_Pa / (R * T_K) ** 2
    B = b * P_Pa / (R * T_K)
    return A, B


def fugacity_coeff_pure(T_K: float, P_Pa: float, Tc_K: float, Pc_Pa: float,
                        omega: float, phase: str) -> Optional[float]:
    """Coeficiente de fugacidad φ del componente puro a (T, P).

    phase ∈ {'liquid', 'vapor'}.  Elige la raíz Z correspondiente (líquido =
    menor, vapor = mayor).  Devuelve None si no hay raíz física para esa fase
    a esa (T, P) — p.ej. pedir líquido cuando solo existe la raíz vapor.
    """
    a, b = pr_a_b(Tc_K, Pc_Pa, omega, T_K)
    A, B = _AB(a, b, T_K, P_Pa)
    roots = z_roots(A, B)
    if not roots:
        return None

    if len(roots) == 1:
        # Monofásico: clasificar la única raíz por su Z (Z_c PR ≈ 0.307).
        z = roots[0]
        is_vapor = z > 0.307
        if phase == "vapor" and not is_vapor:
            return None
        if phase == "liquid" and is_vapor:
            return None
        return math.exp(_ln_phi_from_Z(z, A, B))

    z = roots[0] if phase == "liquid" else roots[-1]
    return math.exp(_ln_phi_from_Z(z, A, B))


# ============================================================
# Presión de saturación pura (igualdad de fugacidad líq = vap)
# ============================================================

def psat_pr(Tc_K: float, Pc_Pa: float, omega: float, T_K: float,
            tol: float = 1e-8, max_iter: int = 100) -> Optional[float]:
    """Presión de saturación [Pa] del componente puro por igualdad de
    fugacidad líquido = vapor.

    Semilla de Wilson  P0 = Pc·exp(5.373·(1+ω)·(1 − Tc/T))  y punto fijo
    P ← P·(φ_liq/φ_vap), que converge dentro de la ventana bifásica (tres
    raíces Z).  Fallback de bisección sobre ln(φ_liq/φ_vap) si el punto fijo
    cae fuera de la ventana.

    Devuelve None si T ≥ Tc (supercrítico: NO existe Psat; correcto, no se
    fuerza), o si no converge a una raíz física.
    """
    if T_K >= Tc_K:
        return None

    a, b = pr_a_b(Tc_K, Pc_Pa, omega, T_K)
    Tr = T_K / Tc_K

    def g(P: float) -> Optional[float]:
        """ln(φ_liq/φ_vap) en P; None si no hay ventana bifásica (≥2 raíces)."""
        A, B = _AB(a, b, T_K, P)
        roots = z_roots(A, B)
        if len(roots) < 2:
            return None
        zL, zV = roots[0], roots[-1]
        return _ln_phi_from_Z(zL, A, B) - _ln_phi_from_Z(zV, A, B)

    # --- Punto fijo desde la semilla de Wilson ---
    P = Pc_Pa * math.exp(5.373 * (1.0 + omega) * (1.0 - 1.0 / Tr))
    P = min(max(P, 1.0), Pc_Pa)
    for _ in range(max_iter):
        A, B = _AB(a, b, T_K, P)
        roots = z_roots(A, B)
        if len(roots) >= 2:
            zL, zV = roots[0], roots[-1]
            lnphiL = _ln_phi_from_Z(zL, A, B)
            lnphiV = _ln_phi_from_Z(zV, A, B)
            ratio = math.exp(lnphiL - lnphiV)
            if abs(lnphiL - lnphiV) < tol:
                return P
            P_new = P * ratio
            if P_new <= 0 or not math.isfinite(P_new):
                break
            P = P_new
        else:
            break  # fuera de ventana bifásica → ir a bisección

    # --- Fallback: bisección sobre g(P) escaneando la ventana bifásica ---
    lo, hi = 1.0, Pc_Pa
    n_scan = 400
    prev_P = None
    prev_g = None
    for i in range(1, n_scan + 1):
        Pi = lo * (hi / lo) ** (i / n_scan)  # malla log
        gi = g(Pi)
        if gi is None:
            prev_P, prev_g = None, None
            continue
        if prev_g is not None and prev_g * gi <= 0:
            a_lo, a_hi = prev_P, Pi
            for _ in range(200):
                mid = math.sqrt(a_lo * a_hi)
                gm = g(mid)
                if gm is None:
                    break
                if abs(gm) < tol:
                    return mid
                g_lo = g(a_lo)
                if g_lo is None:
                    break
                if g_lo * gm <= 0:
                    a_hi = mid
                else:
                    a_lo = mid
            return math.sqrt(a_lo * a_hi)
        prev_P, prev_g = Pi, gi

    return None


# ============================================================
# Mezcla — reglas de van der Waals de un fluido (kij = 0 por defecto)
# ============================================================

def mix_a_b(a_list: Sequence[float], b_list: Sequence[float],
            x: Sequence[float],
            kij: Optional[Sequence[Sequence[float]]] = None
            ) -> Tuple[float, float]:
    """Reglas de mezcla vdW de un fluido:

        a_mix = Σ_i Σ_j  x_i·x_j·√(a_i·a_j)·(1 − k_ij)
        b_mix = Σ_i  x_i·b_i

    kij = None → todos 0 (no hay binarios EOS en el repo).
    """
    n = len(a_list)
    a_mix = 0.0
    for i in range(n):
        for j in range(n):
            k = 0.0 if kij is None else kij[i][j]
            a_mix += x[i] * x[j] * math.sqrt(a_list[i] * a_list[j]) * (1.0 - k)
    b_mix = sum(x[i] * b_list[i] for i in range(n))
    return a_mix, b_mix


def fugacity_coeff_mix(comps_props: Sequence[Tuple[float, float, float]],
                       x: Sequence[float], T_K: float, P_Pa: float,
                       phase: str,
                       kij: Optional[Sequence[Sequence[float]]] = None
                       ) -> Optional[List[float]]:
    """Coeficientes de fugacidad φ_i en mezcla (regla vdW de un fluido).

    comps_props = lista de (Tc_K, Pc_Pa, omega).  phase ∈ {'liquid','vapor'}.
    Fórmula PR multicomponente estándar:

        ln φ_i = (b_i/b_m)·(Z−1) − ln(Z−B)
                 − A/(2√2·B)·[ 2·Σ_j x_j·a_ij / a_m − b_i/b_m ]
                   · ln[ (Z+(1+√2)B) / (Z+(1−√2)B) ]

    con a_ij = √(a_i·a_j)·(1−k_ij).  Devuelve None si no hay raíz física
    para la fase pedida.
    """
    n = len(comps_props)
    a_list: List[float] = []
    b_list: List[float] = []
    for (Tc_K, Pc_Pa, omega) in comps_props:
        a_i, b_i = pr_a_b(Tc_K, Pc_Pa, omega, T_K)
        a_list.append(a_i)
        b_list.append(b_i)

    a_m, b_m = mix_a_b(a_list, b_list, x, kij)
    A = a_m * P_Pa / (R * T_K) ** 2
    B = b_m * P_Pa / (R * T_K)

    roots = z_roots(A, B)
    if not roots:
        return None
    if len(roots) == 1:
        Z = roots[0]
        is_vapor = Z > 0.307
        if phase == "vapor" and not is_vapor:
            return None
        if phase == "liquid" and is_vapor:
            return None
    else:
        Z = roots[0] if phase == "liquid" else roots[-1]

    term_log = math.log((Z + (1.0 + _SQRT2) * B) / (Z + (1.0 - _SQRT2) * B))
    out: List[float] = []
    for i in range(n):
        sum_aij = 0.0
        for j in range(n):
            k = 0.0 if kij is None else kij[i][j]
            sum_aij += x[j] * math.sqrt(a_list[i] * a_list[j]) * (1.0 - k)
        bi_bm = b_list[i] / b_m
        ln_phi = (
            bi_bm * (Z - 1.0)
            - math.log(Z - B)
            - A / (2.0 * _SQRT2 * B)
            * (2.0 * sum_aij / a_m - bi_bm)
            * term_log
        )
        out.append(math.exp(ln_phi))
    return out


# ============================================================
# Wrappers de conveniencia que leen thermo_db
# ============================================================

def _eos_consts(name: str) -> Optional[Tuple[float, float, float]]:
    """(Tc_K, Pc_Pa, omega) desde thermo_db, o None si falta data EOS."""
    try:
        import thermo_db as _td
    except ImportError:
        return None
    c = _td.get(name)
    if c is None:
        return None
    if c.tc_c is None or c.pc_bar is None or c.omega is None:
        return None
    return (c.tc_c + 273.15, c.pc_bar * 1e5, c.omega)


def psat_bar(name: str, T_C: float) -> Optional[float]:
    """Psat [bar] de un compuesto de thermo_db a T_C [°C], vía Peng-Robinson.

    None si falta data EOS (tc_c/pc_bar/omega) o si T_C ≥ Tc (supercrítico).
    """
    consts = _eos_consts(name)
    if consts is None:
        return None
    Tc_K, Pc_Pa, omega = consts
    P = psat_pr(Tc_K, Pc_Pa, omega, T_C + 273.15)
    if P is None:
        return None
    return P / 1e5  # Pa → bar
