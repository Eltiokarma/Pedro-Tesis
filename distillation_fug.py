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
    # Si falta thermo_db para el LK: asumir no-volátil (P_LK = 0).
    # Si falta para el HK: no podemos calcular α (división por 0).
    if comp_HK is None:
        return None
    T_C = T_K - 273.15
    P_HK = comp_HK.vapor_pressure_kPa(T_C)
    if P_HK is None or P_HK <= 0:
        return None
    if comp_LK is None:
        # LK no en thermo_db: tratar como no-volátil
        P_LK = 1e-10
    else:
        P_LK = comp_LK.vapor_pressure_kPa(T_C)
        if P_LK is None or P_LK <= 0:
            P_LK = 1e-10
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


# ============================================================
# Fenske-Hengstebeck — Distribución multicomponente
# ============================================================

def fenske_hengstebeck(alphas_to_HK: Dict[str, float],
                       z: Dict[str, float],
                       N_min: float,
                       LK: str, HK: str,
                       x_D_LK: float, x_B_LK: float) -> Dict[str, Dict[str, float]]:
    """Distribución de todos los componentes entre destilado y fondo
    usando Fenske-Hengstebeck.

    Para los KEYS (LK, HK): las specs del user determinan la fracción
    en cada producto (vía balance de materia).
    Para los NO-KEYS: la fracción se calcula desde
        log10(d_i/b_i) = log10(d_HK/b_HK) + N_min · log10(α_i,HK)

    Args:
        alphas_to_HK: {comp: α_i_to_HK}  (α_HK = 1.0 por convención)
        z:           {comp: mol_frac feed}
        N_min:       (from Fenske on keys)
        LK, HK:      nombres de los key components
        x_D_LK, x_B_LK: composición de LK en distillate y bottoms

    Returns:
        {'x_D': {comp: frac}, 'x_B': {comp: frac},
         'D_over_F': float, 'B_over_F': float}
    """
    # Balance overall de LK: F·z_LK = D·x_D_LK + B·x_B_LK, F=D+B
    #   → D/F = (z_LK - x_B_LK) / (x_D_LK - x_B_LK)
    z_LK = z[LK]
    if abs(x_D_LK - x_B_LK) < 1e-9:
        return None
    D_over_F = (z_LK - x_B_LK) / (x_D_LK - x_B_LK)
    B_over_F = 1.0 - D_over_F
    if D_over_F <= 0 or B_over_F <= 0:
        return None
    # Para HK: idéntico balance.  Necesitamos x_D_HK, x_B_HK.
    # Asumimos que el resto del HK no se "pierde": x_B_HK = ?
    # Si solo damos x_D_LK, x_B_LK, el HK queda determinado por balance:
    #   z_HK = D_over_F · x_D_HK + B_over_F · x_B_HK
    # Pero faltan x_D_HK y x_B_HK individualmente.  Usamos Hengstebeck:
    # ratio d_HK/b_HK se obtiene del LK por Fenske inverso:
    # (d_LK/b_LK) / (d_HK/b_HK) = α_LK_HK ^ N_min
    # → d_HK/b_HK = (d_LK/b_LK) / α_LK_HK^N_min
    alpha_LK = alphas_to_HK.get(LK, 1.0)
    d_LK = D_over_F * x_D_LK
    b_LK = B_over_F * x_B_LK
    if b_LK <= 0 or d_LK <= 0:
        return None
    ratio_LK = d_LK / b_LK
    ratio_HK = ratio_LK / (alpha_LK ** N_min)
    # Componentes no-keys: ratio_i = α_i^N_min · ratio_HK
    d_i = {}
    b_i = {}
    for c, alpha in alphas_to_HK.items():
        if c == LK:
            d_i[c] = d_LK
            b_i[c] = b_LK
            continue
        r_i = (alpha ** N_min) * ratio_HK
        # d_i + b_i = z_i (en feed basis F=1)
        # d_i / b_i = r_i  →  d_i = r_i·b_i  →  b_i·(r_i+1) = z_i
        z_i = z.get(c, 0.0)
        if z_i <= 0:
            d_i[c] = 0.0
            b_i[c] = 0.0
            continue
        b_i[c] = z_i / (1 + r_i)
        d_i[c] = r_i * b_i[c]

    # Normalizar dentro de cada producto (D y B)
    total_D = sum(d_i.values())
    total_B = sum(b_i.values())
    x_D_dict = {c: d / total_D for c, d in d_i.items() if total_D > 0}
    x_B_dict = {c: b / total_B for c, b in b_i.items() if total_B > 0}
    return dict(
        x_D=x_D_dict,
        x_B=x_B_dict,
        D_over_F=total_D,        # = D/F real recalculado
        B_over_F=total_B,
    )


# ============================================================
# McCabe-Thiele — Solver riguroso binario stage-by-stage
# ============================================================
# Para sistema binario con NRTL: traza la línea de operación de
# rectificación + stripping, y avanza etapa por etapa desde x_D
# hasta x_B contando los saltos.  Devuelve N entero + tabla con
# composiciones (x, y, T) por etapa.

def mccabe_thiele(LK: str, HK: str,
                   z_LK: float, x_D_LK: float, x_B_LK: float,
                   R: float, q: float, P_bar: float,
                   max_stages: int = 200) -> Optional[Dict]:
    """Solver McCabe-Thiele binario con curva de equilibrio NRTL.

    Args:
        LK, HK:       componentes
        z_LK:         frac mol feed LK
        x_D_LK:       frac mol distillate LK (mayor que z)
        x_B_LK:       frac mol bottoms LK (menor que z)
        R:            reflux ratio operativo
        q:            factor de feed (1=sat liq, 0=sat vap)
        P_bar:        presión columna
        max_stages:   límite máximo (default 200, para evitar bucles
                      en specs imposibles)

    Returns:
        dict {N, N_feed, stages: list of (x_LK, y_LK, T_K)} o None.
        N: etapas reales incluyendo reboiler
        N_feed: etapa óptima del feed (1 = tope)
        stages: tabla detallada del perfil de la columna
    """
    if not (x_B_LK < z_LK < x_D_LK):
        return None
    if R <= 0:
        return None
    # Línea de operación rectificación: y = (R/(R+1))·x + x_D/(R+1)
    m_rect = R / (R + 1.0)
    b_rect = x_D_LK / (R + 1.0)
    # q-line: y = (q/(q-1))·x − z/(q-1)  si q≠1
    # Intersección rect-line y q-line:
    #   x_int = (b_rect + z_LK / (q-1)) / (q/(q-1) - m_rect)
    # Caso q=1 (líquido sat): q-line vertical en x = z. Intersección
    # rect-line a x=z: y = m_rect·z + b_rect.
    if abs(q - 1.0) < 1e-6:
        x_int = z_LK
        y_int = m_rect * z_LK + b_rect
    else:
        m_q = q / (q - 1.0)
        b_q = -z_LK / (q - 1.0)
        # m_rect·x + b_rect = m_q·x + b_q → x = (b_q - b_rect)/(m_rect - m_q)
        if abs(m_rect - m_q) < 1e-9:
            return None
        x_int = (b_q - b_rect) / (m_rect - m_q)
        y_int = m_rect * x_int + b_rect
    # Línea de stripping: pasa por (x_int, y_int) y (x_B, x_B)
    if abs(x_int - x_B_LK) < 1e-9:
        return None
    m_strip = (y_int - x_B_LK) / (x_int - x_B_LK)
    b_strip = x_B_LK - m_strip * x_B_LK
    # Avanzar etapa por etapa desde (x_D, x_D) bajando por la curva de eq
    try:
        import nrtl
    except ImportError:
        return None
    stages = []
    x = x_D_LK
    y = x_D_LK   # tope: y_top = x_D (condensador total)
    N_feed = None
    for step in range(max_stages):
        # Etapa actual: dado y, encontrar x_equilibrium (curva NRTL inversa)
        # Resolvemos: P_bar · y = γ_LK(x) · P_LK_sat(T_bub) · x_LK donde
        # T_bub se ajusta a la composición x.
        # Approach: dado y_LK = y, buscar x_LK tal que el bubble_point
        # de [x_LK, 1-x_LK] dé y_LK = y.  Bisección.
        if not (0 < y < 1):
            return None
        x_new = _find_x_from_y_eq(LK, HK, y, P_bar)
        if x_new is None:
            return None
        # Get T de la etapa para tabla
        T_stage = nrtl.bubble_point([LK, HK], [x_new, 1-x_new], P_bar)
        T_stage_K = T_stage[0] if T_stage else None
        stages.append((x_new, y, T_stage_K))
        x = x_new
        # ¿Llegamos al fondo?
        if x <= x_B_LK + 1e-4:
            break
        # ¿Cambio de sección? Si x cae debajo de x_int, pasar a stripping
        # y registrar N_feed si no se hizo antes.
        if N_feed is None and x < x_int:
            N_feed = len(stages)
        # Próximo y desde la línea de operación apropiada
        if x >= x_int:
            y = m_rect * x + b_rect
        else:
            y = m_strip * x + b_strip
    else:
        # No llegó al x_B → specs imposibles (probable azeo)
        return dict(N=max_stages, N_feed=N_feed or max_stages,
                     stages=stages, converged=False)
    return dict(
        N=len(stages),
        N_feed=N_feed or len(stages),
        stages=stages,
        converged=True,
    )


def _find_x_from_y_eq(LK: str, HK: str, y_LK: float,
                       P_bar: float) -> Optional[float]:
    """Inversa de y(x) en la curva VLE: dado y_LK, encontrar x_LK
    tal que en equilibrio yL_K(x_LK) = y_LK.

    Usa bubble_point + bisección.  Asume que la curva es monotónica
    en x ∈ [x_B, x_D] (cierto fuera del azeotropo)."""
    try:
        import nrtl
    except ImportError:
        return None
    # f(x) = y_predicted(x) - y_LK
    def y_at_x(x):
        if not (0 < x < 1):
            return None
        bp = nrtl.bubble_point([LK, HK], [x, 1 - x], P_bar)
        if bp is None:
            return None
        return bp[1][0]   # y_LK

    # Bisección en x ∈ (0.001, 0.999)
    lo, hi = 0.001, 0.999
    y_lo = y_at_x(lo); y_hi = y_at_x(hi)
    if y_lo is None or y_hi is None:
        return None
    # y_LK creciente con x_LK (normal) o puede no ser monótona si azeo
    # Asegurar que y_LK esté en el rango
    if y_LK <= y_lo:
        return lo
    if y_LK >= y_hi:
        return hi
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        y_mid = y_at_x(mid)
        if y_mid is None:
            return None
        if abs(y_mid - y_LK) < 1e-5:
            return mid
        if y_mid < y_LK:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)
