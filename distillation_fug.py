"""
DISTILLATION_FUG — Diseño shortcut de columnas de destilación.

Implementa el método clásico Fenske-Underwood-Gilliland-Kirkbride
para diseño preliminar de columnas binarias y multicomponente.

API:
    fenske(alpha_avg, x_D_LK, x_D_HK, x_B_LK, x_B_HK) → N_min
    underwood(alphas, z, q, x_D)                       → (θ, R_min)
    gilliland(N_min, R, R_min)                         → N
    kirkbride(alphas, x_F, x_D, x_B, N)                → N_feed (rectif)

    design_column(feed_composition, F, T_K, P_bar,
                   light_key, heavy_key,
                   x_D_LK, x_B_LK,
                   R_factor=1.3, q=1.0)              → dict completo

Hipótesis FUG:
    · Solo binarios y multicomponentes con 2 key components
    · Volatilidad relativa α aproximadamente constante (promedio
      geométrico tope-fondo)
    · Para sistemas no-ideales (NRTL), α se calcula con γ·P_sat
    · No-adiabático (Q_reb y Q_cond se computan separados)
    · Reflujo total entre etapas

Validación: tests vs casos clásicos de Henley-Seader, Perry.
"""

import math
from typing import Dict, List, Optional, Tuple


# ============================================================
# Fenske — Número mínimo de etapas
# ============================================================

def fenske(alpha_avg: float,
           x_D_LK: float, x_B_LK: float,
           x_D_HK: float, x_B_HK: float) -> Optional[float]:
    """Número mínimo de etapas (incluyendo el reboiler como etapa).

    N_min = log[ (x_D_LK/x_D_HK) · (x_B_HK/x_B_LK) ] / log(α_avg)

    Args:
        alpha_avg: volatilidad relativa promedio LK/HK
        x_D_LK, x_B_LK: fracciones del componente LIGHT KEY en tope y fondo
        x_D_HK, x_B_HK: fracciones del componente HEAVY KEY en tope y fondo

    Returns:
        N_min (número mínimo de etapas, incl. reboiler).
        None si α ≤ 1 (no se puede separar) o specs inválidas.
    """
    if alpha_avg <= 1.0001:
        return None
    if min(x_D_LK, x_B_LK, x_D_HK, x_B_HK) <= 0:
        return None
    ratio = (x_D_LK / x_D_HK) * (x_B_HK / x_B_LK)
    if ratio <= 1.0:
        return None
    return math.log(ratio) / math.log(alpha_avg)


# ============================================================
# Underwood — Reflujo mínimo
# ============================================================

def underwood(alphas: List[float], z: List[float], q: float,
              x_D: List[float]) -> Optional[Tuple[float, float]]:
    """Reflujo mínimo por Underwood (multicomponente).

    Paso 1: encontrar raíz θ en α_HK < θ < α_LK que satisface:
        Σᵢ (αᵢ · zᵢ) / (αᵢ - θ) = 1 - q

    Paso 2: con θ, calcular R_min:
        R_min + 1 = Σᵢ (αᵢ · x_D_i) / (αᵢ - θ)

    Args:
        alphas: volatilidades relativas (al HK) de todos los componentes
        z: fracciones molares en el feed
        q: factor de feed (1.0 = sat líquido, 0.0 = sat vapor)
        x_D: fracciones molares en el destilado

    Returns: (θ, R_min) o None si no converge.
    """
    n = len(alphas)
    if n != len(z) or n != len(x_D):
        return None
    # Identificar α_LK (mayor) y α_HK (1.0 por convención de Underwood)
    # Para multicomp: θ está entre α_HK y α_LK
    # Buscar θ tal que Σ αᵢ·zᵢ/(αᵢ-θ) = 1-q por bisección
    # entre 1.0+ε y α_max-ε
    alpha_sorted = sorted(alphas, reverse=True)
    a_max = alpha_sorted[0]
    a_HK = min(a for a in alphas if a >= 0.99)  # típicamente HK=1.0
    if a_HK <= 0:
        return None

    def F(theta):
        try:
            return sum(alphas[i] * z[i] / (alphas[i] - theta)
                       for i in range(n)) - (1.0 - q)
        except ZeroDivisionError:
            return float('inf')

    # Buscar raíz en (a_HK, a_LK).  Underwood tiene n-1 raíces; nos
    # interesa la primera, entre los dos α más altos.
    # Para casos binarios o pseudo-binarios, intervalo (1+ε, α_LK-ε).
    eps = 1e-4
    lo = a_HK + eps
    hi = a_max - eps
    if lo >= hi:
        return None
    F_lo, F_hi = F(lo), F(hi)
    # F(θ) tiene polos en los αᵢ; entre dos αᵢ consecutivos cambia de signo
    # Si lo y hi no encierran raíz, buscar en subintervalo
    if F_lo * F_hi > 0:
        # Probar intervalo intermedio
        # Tomar los dos α adyacentes más cercanos al LK
        if len(alpha_sorted) >= 2:
            lo = alpha_sorted[1] + eps
            hi = alpha_sorted[0] - eps
            F_lo, F_hi = F(lo), F(hi)
            if F_lo * F_hi > 0:
                return None
        else:
            return None
    # Bisección
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        Fm = F(mid)
        if abs(Fm) < 1e-9:
            theta = mid
            break
        if F_lo * Fm < 0:
            hi, F_hi = mid, Fm
        else:
            lo, F_lo = mid, Fm
    else:
        theta = 0.5 * (lo + hi)

    # Calcular R_min con esta θ
    try:
        R_min_plus_1 = sum(alphas[i] * x_D[i] / (alphas[i] - theta)
                           for i in range(n))
    except ZeroDivisionError:
        return None
    R_min = R_min_plus_1 - 1.0
    if R_min < 0:
        R_min = 0.0
    return (theta, R_min)


# ============================================================
# Gilliland — Número real de etapas dado R/R_min
# ============================================================

def gilliland(N_min: float, R: float, R_min: float) -> Optional[float]:
    """Correlación de Gilliland (Eduljee 1975 fit) para encontrar
    N real dado N_min, R y R_min.

        X = (R - R_min) / (R + 1)
        Y = 1 - exp[(1 + 54.4·X) / (11 + 117.2·X) · (X - 1) / sqrt(X)]
        Y = (N - N_min) / (N + 1)
        → N = (N_min + Y) / (1 - Y)

    Args:
        N_min: número mínimo de etapas (Fenske)
        R:     reflux ratio de diseño
        R_min: reflux mínimo (Underwood)

    Returns: N real, o None si R <= R_min (imposible).
    """
    if R <= R_min:
        return None
    if N_min <= 0:
        return None
    X = (R - R_min) / (R + 1.0)
    if X <= 0:
        return None
    # Eduljee 1975 simplificada
    Y = 0.75 * (1 - X ** 0.5668)
    # alternativa Gilliland clásica más precisa:
    # if X < 0.0001: Y = 0
    # else: Y = 1 - math.exp(((1 + 54.4*X)/(11 + 117.2*X)) * (X-1)/math.sqrt(X))
    if Y >= 1:
        return None
    N = (N_min + Y) / (1.0 - Y)
    return N


# ============================================================
# Kirkbride — Posición del feed (etapa óptima)
# ============================================================

def kirkbride(z_LK: float, z_HK: float,
              x_D_LK: float, x_B_HK: float,
              N: float, B_over_D: float) -> Optional[float]:
    """Correlación Kirkbride para posición óptima del feed.

        N_R / N_S = [ (z_HK / z_LK) · (x_B_HK / x_D_LK)² · (B/D) ]^0.206

    Returns: N_rectificación (etapas arriba del feed; el resto = N_stripping).
    """
    if N <= 0 or z_LK <= 0 or x_D_LK <= 0:
        return None
    try:
        ratio = (z_HK / z_LK) * ((x_B_HK / x_D_LK) ** 2) * B_over_D
    except ZeroDivisionError:
        return None
    NR_over_NS = ratio ** 0.206
    # N = N_R + N_S → N_R = N · ratio / (1 + ratio)
    N_R = N * NR_over_NS / (1.0 + NR_over_NS)
    return N_R


# ============================================================
# Helper: volatilidad relativa con NRTL
# ============================================================

def relative_volatility(LK: str, HK: str, x_vec: Dict[str, float],
                        T_K: float, P_bar: float) -> Optional[float]:
    """α_LK_HK = (γ_LK · P_LK_sat) / (γ_HK · P_HK_sat) usando NRTL.

    Si NRTL no tiene parámetros, fallback a Raoult (γ=1).
    """
    try:
        import nrtl
        import thermo_db as _td
    except ImportError:
        return None
    comp_LK = _td.get(LK)
    comp_HK = _td.get(HK)
    if comp_LK is None or comp_HK is None:
        return None
    # Pᵢ_sat en bar
    T_C = T_K - 273.15
    P_LK = comp_LK.vapor_pressure_kPa(T_C)
    P_HK = comp_HK.vapor_pressure_kPa(T_C)
    if P_LK is None or P_HK is None or P_HK <= 0:
        return None
    P_LK /= 100.0   # kPa → bar
    P_HK /= 100.0
    # γ via NRTL si hay parámetros, sino Raoult ideal (γ=1)
    names_present = [n for n in x_vec.keys() if x_vec[n] > 0.001]
    x_list = [x_vec[n] for n in names_present]
    s = sum(x_list)
    if s > 0:
        x_list = [x / s for x in x_list]
    g = None
    if all(nrtl.has_params(LK, n) or n == LK for n in names_present) and \
       all(nrtl.has_params(HK, n) or n == HK for n in names_present):
        g_full = nrtl.gamma(names_present, x_list, T_K)
        if g_full is not None:
            try:
                idx_LK = names_present.index(LK)
                idx_HK = names_present.index(HK)
                gamma_LK = g_full[idx_LK]
                gamma_HK = g_full[idx_HK]
                g = (gamma_LK, gamma_HK)
            except ValueError:
                pass
    if g is None:
        # Raoult ideal
        gamma_LK = gamma_HK = 1.0
    else:
        gamma_LK, gamma_HK = g
    return (gamma_LK * P_LK) / (gamma_HK * P_HK)


# ============================================================
# Diseño completo de columna shortcut
# ============================================================

def design_column(feed_composition: Dict[str, float],
                   F: float,
                   T_K: float, P_bar: float,
                   light_key: str, heavy_key: str,
                   x_D_LK: float, x_B_LK: float,
                   R_factor: float = 1.3,
                   q: float = 1.0,
                   T_top_K: Optional[float] = None,
                   T_bot_K: Optional[float] = None) -> Optional[Dict]:
    """Diseño shortcut completo de una columna binaria/multicomponente.

    Args:
        feed_composition: {comp_name: mass_fraction} del feed
        F:                caudal del feed (mass o molar, mismo basis salida)
        T_K, P_bar:       T y P de operación (T se usa para α si T_top/T_bot
                          no se dan)
        light_key:        nombre del LK (más volátil de los keys)
        heavy_key:        nombre del HK
        x_D_LK:           pureza objetivo de LK en destilado (mass frac)
        x_B_LK:           fracción objetivo de LK en fondo (recovery=1-x_B)
        R_factor:         ratio R/R_min (default 1.3, típico industrial)
        q:                factor de feed (1=líquido sat, 0=vapor sat)
        T_top_K, T_bot_K: opcional, T en tope y fondo para mejor α_avg
                          (si None, usa T_K para ambos)

    Returns dict con:
        N_min, N, N_feed
        R_min, R
        alpha_avg, alpha_top, alpha_bot
        D, B  (caudales destilado y fondo, mismo basis que F)
        x_D, x_B  (composiciones, mass fractions multi-componente)
        Q_cond, Q_reb  (kW si F en kg/s, sino caudal·ΔH_vap)
        warnings (lista de strings)

    None si specs imposibles (α≤1, etc).
    """
    warnings_list = []
    # Verificar keys en el feed
    if light_key not in feed_composition or heavy_key not in feed_composition:
        return None
    z_LK = feed_composition[light_key]
    z_HK = feed_composition[heavy_key]
    if z_LK <= 0 or z_HK <= 0:
        return None

    # Balance global por LK:
    #   F · z_LK = D · x_D_LK + B · x_B_LK
    #   F = D + B
    # 2 eqs, 2 unknowns
    #   D = F · (z_LK - x_B_LK) / (x_D_LK - x_B_LK)
    #   B = F - D
    if abs(x_D_LK - x_B_LK) < 1e-6:
        return None
    D = F * (z_LK - x_B_LK) / (x_D_LK - x_B_LK)
    B = F - D
    if D <= 0 or B <= 0:
        return None

    # Balance por HK (con el assumption de separación perfecta entre keys):
    #   F · z_HK = D · x_D_HK + B · x_B_HK
    # Como x_D_HK = 1 - x_D_LK - x_(otros_D) y idem para B:
    # Para FUG binario simplificado: x_D_HK = 1 - x_D_LK, x_B_HK = 1 - x_B_LK
    x_D_HK = 1.0 - x_D_LK
    x_B_HK = 1.0 - x_B_LK

    # ---- Volatilidad relativa α_LK/HK ----
    T_t = T_top_K if T_top_K is not None else T_K
    T_b = T_bot_K if T_bot_K is not None else T_K
    # Volatilidad a las composiciones de tope/fondo
    x_top = {light_key: x_D_LK, heavy_key: x_D_HK}
    x_bot = {light_key: x_B_LK, heavy_key: x_B_HK}
    alpha_top = relative_volatility(light_key, heavy_key, x_top, T_t, P_bar)
    alpha_bot = relative_volatility(light_key, heavy_key, x_bot, T_b, P_bar)
    if alpha_top is None or alpha_bot is None:
        return None
    # Promedio geométrico
    alpha_avg = math.sqrt(alpha_top * alpha_bot)
    if alpha_avg <= 1.0001:
        warnings_list.append(
            f"⚠ α_LK/HK ≈ {alpha_avg:.3f} ≤ 1 — la separación NO es factible "
            f"con destilación simple (puede haber azeotropo o componentes "
            f"con volatilidades casi iguales).")
        return dict(alpha_avg=alpha_avg, alpha_top=alpha_top,
                     alpha_bot=alpha_bot, warnings=warnings_list)

    # CRITICAL: detectar AZEOTROPO pasado.  Si α_top < 1, significa
    # que la composición pedida en el destilado está MÁS ALLÁ del
    # azeotropo (volatilidad invertida cerca del tope).  El método
    # FUG da un N "razonable" pero la columna físicamente NO puede
    # operar — destilación simple no pasa el azeo.
    if alpha_top < 1.0:
        warnings_list.append(
            f"⚠ AZEOTROPO PASADO: α en tope = {alpha_top:.3f} < 1. "
            f"La composición pedida (x_D_LK={x_D_LK}) está más allá del "
            f"azeotropo eth-water (~0.89) o similar. Destilación simple NO "
            f"puede alcanzar esta pureza. Usar destilación azeotrópica/"
            f"extractiva con un tercer componente."
        )
    if alpha_bot < 1.0:
        warnings_list.append(
            f"⚠ AZEOTROPO en FONDO: α en fondo = {alpha_bot:.3f} < 1. "
            f"La composición pedida en fondo es no-alcanzable.")

    # ---- Fenske: N_min ----
    N_min = fenske(alpha_avg, x_D_LK, x_B_LK, x_D_HK, x_B_HK)
    if N_min is None:
        return dict(warnings=warnings_list + ["Fenske falló"])

    # ---- Underwood: R_min ----
    # Para versión binaria simplificada:
    #   R_min = (1/(α-1)) · (x_D_LK / z_LK - α · x_D_HK / z_HK)
    # Para multicomp: Σ αᵢ·x_D_i / (αᵢ-θ) = R_min + 1
    # Usamos versión simplificada binaria (más robusta sin solver)
    R_min_bin = (1.0 / (alpha_avg - 1.0)) * (
        x_D_LK / z_LK - alpha_avg * x_D_HK / z_HK
    )
    if R_min_bin < 0:
        R_min_bin = 0.05    # mínimo práctico

    # ---- R real = R_factor × R_min ----
    R = R_factor * R_min_bin

    # ---- Gilliland: N real ----
    N = gilliland(N_min, R, R_min_bin)
    if N is None:
        warnings_list.append(
            f"⚠ R={R:.3f} ≤ R_min={R_min_bin:.3f}: imposible.  "
            f"Aumentar R_factor (>{R_min_bin/R_factor:.2f} requerido).")
        N = N_min * 2    # fallback heurístico

    # ---- Kirkbride: posición del feed ----
    N_feed = kirkbride(z_LK, z_HK, x_D_LK, x_B_HK, N, B/D)
    if N_feed is None:
        N_feed = N / 2    # fallback medio

    # ---- Estimación duties Q_cond, Q_reb ----
    # Q_cond = (R + 1) · D · ΔH_vap_avg
    # Q_reb  = Q_cond + F·(1-q)·ΔH_vap_avg  (energy balance overall, q=1 → Q_reb≈Q_cond)
    # ΔH_vap se obtiene de los componentes principales
    try:
        import thermo_db as _td
        # Promedio ponderado por composición destilado
        dh_avg_kJ_kg = 0.0
        total_w = 0.0
        for c, w in feed_composition.items():
            comp_obj = _td.get(c)
            if comp_obj is None:
                continue
            dh = comp_obj.delta_h_vap_kJ_mol(T_K - 273.15)
            if dh is None or comp_obj.mw <= 0:
                continue
            dh_kg = dh / comp_obj.mw * 1000  # kJ/mol / (g/mol) · 1000 = kJ/kg
            dh_avg_kJ_kg += w * dh_kg
            total_w += w
        if total_w > 0:
            dh_avg_kJ_kg /= total_w
        else:
            dh_avg_kJ_kg = 800.0  # default ~ agua/etanol promedio
    except ImportError:
        dh_avg_kJ_kg = 800.0

    # Q en kW si F en kg/s (mass basis)
    # Si F está en tm/año, convertir
    # F [tm/año] · 1000 / (8760·3600) = kg/s
    F_kg_s = F * 1000.0 / (8760 * 3600)
    D_kg_s = D * 1000.0 / (8760 * 3600)
    # V vapor en tope = D·(R+1)
    V_kg_s = D_kg_s * (R + 1.0)
    Q_cond_kW = -V_kg_s * dh_avg_kJ_kg     # negativo: extrae calor
    Q_reb_kW  = V_kg_s * dh_avg_kJ_kg + F_kg_s * (1.0 - q) * dh_avg_kJ_kg

    return dict(
        # Etapas
        N_min=N_min,
        N=N,
        N_feed=N_feed,    # contando desde tope; rectificación = N_feed
        # Reflujos
        R_min=R_min_bin,
        R=R,
        R_factor=R_factor,
        # Volatilidad
        alpha_avg=alpha_avg,
        alpha_top=alpha_top,
        alpha_bot=alpha_bot,
        # Caudales
        F=F, D=D, B=B,
        # Composiciones
        x_D={light_key: x_D_LK, heavy_key: x_D_HK},
        x_B={light_key: x_B_LK, heavy_key: x_B_HK},
        # Duties
        Q_cond_kW=Q_cond_kW,
        Q_reb_kW=Q_reb_kW,
        dh_vap_avg_kJ_kg=dh_avg_kJ_kg,
        # Warnings
        warnings=warnings_list,
    )
