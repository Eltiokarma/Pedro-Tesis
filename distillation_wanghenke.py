"""
DISTILLATION_WANGHENKE — Solver riguroso multicomponente multietapa.

Implementación del método Wang-Henke (Tridiagonal Matrix Method)
para diseño y simulación rigurosa de columnas de destilación con
N etapas, C componentes, y modelado riguroso de:
  · Balance de materia por componente (M)
  · Equilibrio L-V (E) via K = γ·P_sat/P (NRTL Capa 6 + Antoine)
  · Suma de fracciones (S) por fase
  · Balance de entalpía (H) — opcional para versión completa

Algoritmo:
  1. Asume perfiles iniciales de T_n y V_n (vapor flow por etapa)
  2. Resuelve M+E como sistema TRIDIAGONAL por componente
     → fracciones molares x_ij en cada etapa
  3. Bubble-point en cada etapa para corregir T_n (con γ·P_sat = P)
  4. Balance de entalpía → corregir V_n
  5. Itera hasta convergencia (típicamente 5-20 iter)

Hipótesis:
  · Steady state
  · Isobaric (P constante en toda la columna)
  · Stage equilibrio teórico (no Murphree eficiency)
  · Condensador total (V_top = 0, salida tope es líquido)
  · Feed en una etapa única, especificada por el user

API:
    wang_henke(comps, feed_z, F, T_feed_K, P_bar, N,
                feed_stage, D_over_F, R,
                max_iter=30, tol=1e-4)
        → dict {converged, x_profile (etapa × comp),
                T_profile, V_profile, L_profile,
                D_comp, B_comp, Q_cond, Q_reb}

Validación:  vs FUG para casos binarios + comparación con datos
DECHEMA para sistemas eth/water, MeOH/water.

LIMITATIONS v1.0:
  · No considera dimerización (water-acetic acid → error ~5%)
  · Asume condensador total
  · No usa thermo riguroso para entalpías de líquido — usa Cp + ΔH_vap
    aproximaciones de thermo_db
"""

import math
from typing import Dict, List, Optional, Tuple


_R_GAS = 8.314          # J/(mol·K)
_T_REF_K = 298.15       # K — referencia de entalpía


def _cp_liq_J_mol_K(comp_obj, T_K: float) -> float:
    """Cp líquido [J/(mol·K)].  Fallbacks (regla de pulgar, Watson):
    Cp_liq ≈ Cp_gas + R si no hay coefs líquidos; 75 J/mol/K (agua) último."""
    cp = comp_obj.cp_J_mol_K(T_K, "liquid")
    if cp is not None and cp > 0:
        return cp
    cp_gas = comp_obj.cp_J_mol_K(T_K, "gas")
    if cp_gas is not None and cp_gas > 0:
        return cp_gas + _R_GAS
    return 75.0


def _h_form_liq_J_mol(comp_obj) -> float:
    """ΔH_f líquido [J/mol] a T_REF.  Si falta ΔH_f_liq, usa
    ΔH_f_gas − ΔH_vap(T_REF) (Hess).  0 si no hay ninguno."""
    if comp_obj.dh_f_liq_kJ_mol is not None:
        return comp_obj.dh_f_liq_kJ_mol * 1000.0
    if comp_obj.dh_f_gas_kJ_mol is not None:
        dhv = comp_obj.delta_h_vap_kJ_mol(_T_REF_K - 273.15)
        if dhv is not None:
            return (comp_obj.dh_f_gas_kJ_mol - dhv) * 1000.0
        return comp_obj.dh_f_gas_kJ_mol * 1000.0
    return 0.0


def _enthalpy_liquid(comps: List[str], x_vec: List[float], T_K: float) -> float:
    """Entalpía molar del líquido [J/mol], referida a T_REF=298.15 K.
        H_L ≈ Σ xᵢ·Cp_liq,ᵢ·(T−T_REF) + Σ xᵢ·ΔH_f_liq,ᵢ
    Cp evaluado en T_mid=(T+T_REF)/2 como 'Cp_avg' del intervalo."""
    try:
        import thermo_db as _td
    except ImportError:
        return 0.0
    T_mid = 0.5 * (T_K + _T_REF_K)
    H = 0.0
    for i, c in enumerate(comps):
        xi = x_vec[i]
        if xi <= 0:
            continue
        co = _td.get(c)
        if co is None:
            H += xi * 75.0 * (T_K - _T_REF_K)
            continue
        cp = _cp_liq_J_mol_K(co, T_mid)
        H += xi * (cp * (T_K - _T_REF_K) + _h_form_liq_J_mol(co))
    return H


def _enthalpy_vapor(comps: List[str], y_vec: List[float], T_K: float) -> float:
    """Entalpía molar del vapor [J/mol], referida a T_REF.
        H_V(T) ≈ H_L(comp=y, T) + Σ yᵢ·ΔH_vap,ᵢ(T)
    (camino de estado: calentar líquido de comp y a T, luego vaporizar a T).
    NOTE: equivalente termodinámico a usar Cp_gas + ΔH_vap(T_REF)."""
    try:
        import thermo_db as _td
    except ImportError:
        return 0.0
    H = _enthalpy_liquid(comps, y_vec, T_K)
    T_C = T_K - 273.15
    for i, c in enumerate(comps):
        yi = y_vec[i]
        if yi <= 0:
            continue
        co = _td.get(c)
        if co is None:
            continue
        dhv = co.delta_h_vap_kJ_mol(T_C)
        if dhv is not None:
            H += yi * dhv * 1000.0
    return H


def _K_values(comps: List[str], x_vec: List[float], T_K: float,
              P_bar: float) -> Optional[List[float]]:
    """Calcula K_i = γ_i · P_i_sat / P para cada componente.
    γ_i de NRTL (Capa 6), P_sat de Antoine (Capa 1)."""
    try:
        import nrtl
        import thermo_db as _td
    except ImportError:
        return None
    g = nrtl.gamma(comps, x_vec, T_K)
    if g is None:
        # Fallback Raoult ideal
        g = [1.0] * len(comps)
    Ks = []
    T_C = T_K - 273.15
    for i, c in enumerate(comps):
        comp_obj = _td.get(c)
        if comp_obj is None:
            Ks.append(1e-10)
            continue
        Psat = comp_obj.vapor_pressure_kPa(T_C)
        if Psat is None or Psat <= 0:
            Ks.append(1e-10)
            continue
        Psat /= 100.0   # kPa → bar
        Ks.append(g[i] * Psat / P_bar)
    return Ks


def _bubble_T_from_x(comps: List[str], x_vec: List[float],
                      P_bar: float, T_init: float = 350.0,
                      max_iter: int = 30) -> Optional[float]:
    """Calcula T_bubble en una etapa con composición líquida x.
    Σ(K_i · x_i) = 1 a T_bub."""
    T = T_init
    for _ in range(max_iter):
        Ks = _K_values(comps, x_vec, T, P_bar)
        if Ks is None:
            return None
        sum_Kx = sum(Ks[i] * x_vec[i] for i in range(len(comps)))
        if abs(sum_Kx - 1.0) < 1e-5:
            return T
        # Newton numérico
        dT = 0.5
        Ks2 = _K_values(comps, x_vec, T + dT, P_bar)
        if Ks2 is None:
            return None
        sum_Kx2 = sum(Ks2[i] * x_vec[i] for i in range(len(comps)))
        df = (sum_Kx2 - sum_Kx) / dT
        if abs(df) < 1e-12:
            return None
        T_new = T - (sum_Kx - 1.0) / df
        if T_new < 200: T_new = 0.5 * (T + 200)
        if T_new > 700: T_new = 0.5 * (T + 700)
        T = T_new
    return T


def _solve_tridiagonal(A: List[float], B: List[float],
                        C: List[float], D: List[float]) -> Optional[List[float]]:
    """Thomas algorithm para sistema tridiagonal:
        B[0]·x[0] + C[0]·x[1] = D[0]
        A[i]·x[i-1] + B[i]·x[i] + C[i]·x[i+1] = D[i]
        A[N]·x[N-1] + B[N]·x[N] = D[N]

    A, B, C son los diagonales sub/diag/sup; D es el RHS.
    Asume len(A) = len(B) = len(C) = len(D) = N.
    A[0] y C[N-1] se ignoran (no usados).
    """
    n = len(B)
    if n == 0:
        return []
    # Forward sweep
    c_prime = [0.0] * n
    d_prime = [0.0] * n
    if abs(B[0]) < 1e-12:
        return None
    c_prime[0] = C[0] / B[0]
    d_prime[0] = D[0] / B[0]
    for i in range(1, n):
        denom = B[i] - A[i] * c_prime[i-1]
        if abs(denom) < 1e-12:
            return None
        c_prime[i] = C[i] / denom
        d_prime[i] = (D[i] - A[i] * d_prime[i-1]) / denom
    # Backward substitution
    x = [0.0] * n
    x[-1] = d_prime[-1]
    for i in range(n - 2, -1, -1):
        x[i] = d_prime[i] - c_prime[i] * x[i+1]
    return x


def wang_henke(comps:       List[str],
                feed_z:      List[float],
                F:           float,
                T_feed_K:    float,
                P_bar:       float,
                N:           int,
                feed_stage:  int,
                D_over_F:    float,
                R:           float,
                max_iter:    int   = 30,
                tol:         float = 1e-4) -> Optional[Dict]:
    """Solver Wang-Henke (Sum-Rates) para columna multicomponente.

    Args:
        comps:      lista de C componentes (nombres canónicos thermo_db)
        feed_z:     fracciones molares del feed (deben sumar ~1)
        F:          caudal molar feed (mol/s)
        T_feed_K:   T del feed (asume sat liquido q=1)
        P_bar:      presión columna
        N:          número de etapas (incluye reboiler y condensador)
        feed_stage: número de etapa del feed (1 = tope, N = reboiler)
        D_over_F:   D/F (fracción del feed que sale por el tope)
        R:          reflux ratio (L_top / D)
        max_iter, tol: control de convergencia

    Returns dict {
        converged:   bool
        iterations:  int
        x_profile:   list[N] of list[C]  fracciones molares líquido
        y_profile:   list[N] of list[C]  fracciones molares vapor
        T_profile:   list[N]  T_K por etapa
        V_profile:   list[N]  vapor flow por etapa (mol/s)
        L_profile:   list[N]  liquid flow por etapa
        D_comp:      list[C]  caudal molar de cada comp en distillate
        B_comp:      list[C]  caudal molar en bottom
        Q_cond_kW:   estimado del condensador
        Q_reb_kW:    estimado del reboiler
    } o None si no converge.
    """
    C = len(comps)
    if N < 2 or feed_stage < 1 or feed_stage > N:
        return None
    if abs(sum(feed_z) - 1.0) > 0.01:
        s = sum(feed_z)
        if s <= 0: return None
        feed_z = [z / s for z in feed_z]
    D = F * D_over_F
    B = F - D
    if D <= 0 or B <= 0:
        return None

    # Convención de etapas (P2/P3): etapa 0 = CONDENSADOR total,
    # etapa N-1 = REBOILER parcial, etapas 1..N-2 = bandejas.  El feed
    # entra en feed_idx (debe ser una bandeja interior).
    feed_idx = min(max(feed_stage - 1, 1), N - 2) if N >= 3 else feed_stage - 1

    # Initial guess perfiles T y V.  T_top ≈ T_feed − 20K, T_bot ≈ T_feed + 30K
    T_profile = [T_feed_K - 20 + 50.0 * (n / max(N - 1, 1)) for n in range(N)]
    # V: Constant Molal Overflow inicial.  V_0=0 (condensador total, no sube
    # vapor); V_1 = D(R+1) (vapor que entra al condensador); resto = V_1.
    V_top = D * (R + 1.0)
    V_profile = [0.0] + [V_top] * (N - 1)
    # L por balance de materia acumulado desde el tope: L_j = V_{j+1}+ΣF_j−D
    cumF0 = [F if n >= feed_idx else 0.0 for n in range(N)]
    L_profile = []
    for n in range(N):
        Vnext = V_profile[n + 1] if n + 1 < N else 0.0
        L_profile.append(Vnext + cumF0[n] - D)

    # Initial x: composición ≈ feed con perfil gradient
    x_profile = [list(feed_z) for _ in range(N)]

    # Para el balance de entalpía (P2): H del feed (sat líquido a T_feed_K).
    H_F = _enthalpy_liquid(comps, feed_z, T_feed_K)

    converged = False
    for it in range(max_iter):
        # 1) Calcular K_n para cada etapa con (T_n, x_n)
        Ks_per_stage = []
        for n in range(N):
            K = _K_values(comps, x_profile[n], T_profile[n], P_bar)
            if K is None:
                return None
            Ks_per_stage.append(K)

        # 2) Resolver sistema tridiagonal por componente, con el cond/reb
        #    tratados RIGUROSAMENTE como etapas (P2/P3 — no se fija x_0=x_D):
        #
        #   · Etapa 0 (condensador total): x_0,i = y_1,i (la condensación
        #     total preserva composición).  Fila: x_0,i − (K_1,i/S_1)·x_1,i = 0
        #     con S_1 = Σ_k K_1,k·x_1,k (normalización, linealizada con x_1
        #     del iter previo).  El reflujo L_0=R·D entra a la etapa 1 vía
        #     el término subdiagonal A_1 = L_0 acoplado a x_0 (=condensado).
        #   · Etapas 1..N-1 (equilibrio; reboiler en N-1 con V_N=0):
        #       L_{n-1}·x_{n-1} − (L_n + V_n·K_n,i)·x_n + V_{n+1}·K_{n+1,i}·x_{n+1}
        #       = −F·z_i  (feed sólo en feed_idx)
        S1 = (sum(Ks_per_stage[1][k] * x_profile[1][k] for k in range(C))
              if N >= 2 else 1.0)
        if S1 <= 0:
            S1 = 1.0
        new_x = [list(x_profile[n]) for n in range(N)]
        for i in range(C):
            A_diag = [0.0] * N
            Bdiag = [0.0] * N
            Cdiag = [0.0] * N
            Dvec  = [0.0] * N
            for n in range(N):
                if n == 0:
                    # Condensador total: x_0 = y_1
                    Bdiag[0] = 1.0
                    if N >= 2:
                        Cdiag[0] = -Ks_per_stage[1][i] / S1
                    Dvec[0] = 0.0
                    continue
                A_diag[n] = L_profile[n - 1]
                Bdiag[n] = -(L_profile[n] + V_profile[n] * Ks_per_stage[n][i])
                if n < N - 1:
                    Cdiag[n] = V_profile[n + 1] * Ks_per_stage[n + 1][i]
                Dvec[n] = -F * feed_z[i] if n == feed_idx else 0.0
            sol = _solve_tridiagonal(A_diag, Bdiag, Cdiag, Dvec)
            if sol is None:
                return None
            for n in range(N):
                new_x[n][i] = max(sol[n], 0.0)

        # 3) Normalizar x_n (Σx=1) + under-relaxation, y ajustar T_n via bubble.
        # NOTE: la sustitución sucesiva sin amortiguar oscila cerca de un
        # azeótropo (K-T fuertemente acoplados); el factor LAM∈(0,1] estabiliza
        # (Henley-Seader §10.4 — under-relaxation estándar de Wang-Henke).
        LAM = 0.5
        max_dT = 0.0
        for n in range(N):
            s = sum(new_x[n])
            if s <= 0:
                continue
            xn_norm = [xi / s for xi in new_x[n]]
            # under-relaxation de la composición
            new_x[n] = [x_profile[n][i] + LAM * (xn_norm[i] - x_profile[n][i])
                        for i in range(C)]
            T_bub = _bubble_T_from_x(comps, new_x[n], P_bar, T_profile[n])
            if T_bub is None:
                T_bub = T_profile[n]
            T_new = T_profile[n] + LAM * (T_bub - T_profile[n])
            max_dT = max(max_dT, abs(T_new - T_profile[n]))
            T_profile[n] = T_new

        # 4) Balance de entalpía por etapa → corregir V_n (y L_n).
        #    "Constant molal overflow corregida": V_{j+1} sale de la
        #    envolvente de energía tope→etapa j (Henley-Seader §10.4),
        #    con Q_cond del propio balance del condensador.  Activado
        #    desde el 2º iter (it>=1); el 1º usa V constante.
        max_dV = float("inf")
        if it >= 1:
            # y por etapa (vapor en equilibrio con new_x a la T actual)
            y_stage = []
            for n in range(N):
                Kn = _K_values(comps, new_x[n], T_profile[n], P_bar)
                if Kn is None:
                    y_stage.append(list(new_x[n])); continue
                yv = [Kn[i] * new_x[n][i] for i in range(C)]
                sy = sum(yv)
                y_stage.append([v / sy for v in yv] if sy > 0 else list(new_x[n]))
            H_L = [_enthalpy_liquid(comps, new_x[n], T_profile[n]) for n in range(N)]
            H_V = [_enthalpy_vapor(comps, y_stage[n], T_profile[n]) for n in range(N)]
            H_D = H_L[0]                      # destilado = condensado (etapa 0)
            V1 = D * (R + 1.0)                # vapor al condensador (fijo por R)
            # Condensador: V_1·H_V_1 + Q_cond = (D+L_0)·H_D = V_1·H_D
            Q_cond_it = V1 * (H_D - H_V[1]) if N >= 2 else 0.0   # < 0
            cumF = [F if n >= feed_idx else 0.0 for n in range(N)]
            newV = [0.0] * N           # V[0]=0 (condensador total)
            if N >= 2:
                newV[1] = V1
            # Recursión de energía: V_{j+1} desde la envolvente tope→etapa j
            for j in range(1, N - 1):
                denom = H_V[j + 1] - H_L[j]
                if abs(denom) < 1e-6:
                    newV[j + 1] = newV[j]; continue
                num = (D * (H_D - H_L[j])
                       + cumF[j] * (H_L[j] - H_F) - Q_cond_it)
                vj1 = num / denom
                if not math.isfinite(vj1) or vj1 <= 0:
                    vj1 = newV[j]             # guard contra V negativo/explosivo
                newV[j + 1] = vj1
            # L por balance de materia (envolvente desde tope): L_j = V_{j+1}+ΣF_j−D
            newL = [0.0] * N
            for n in range(N):
                Vnext = newV[n + 1] if n + 1 < N else 0.0
                Ln = Vnext + cumF[n] - D
                newL[n] = Ln if Ln > 0 else max(L_profile[n] * 0.5, 1e-6)
            # Damping para estabilidad numérica
            beta = 0.5
            max_dV = 0.0
            for n in range(N):
                Vd = (1 - beta) * V_profile[n] + beta * newV[n]
                max_dV = max(max_dV, abs(Vd - V_profile[n]) / max(V_profile[n], 1e-9))
                V_profile[n] = Vd
                L_profile[n] = (1 - beta) * L_profile[n] + beta * newL[n]

        # Convergencia (M+E+S + H): Δx, ΔT y ΔV
        max_dx = 0.0
        for n in range(N):
            for i in range(C):
                max_dx = max(max_dx, abs(new_x[n][i] - x_profile[n][i]))
        x_profile = new_x
        if max_dx < tol and max_dT < 0.5 and max_dV < 1e-3:
            converged = True
            break

    # Calcular y_profile desde y = K·x
    y_profile = []
    for n in range(N):
        K = _K_values(comps, x_profile[n], T_profile[n], P_bar)
        if K is None:
            y_profile.append([0.0] * C)
            continue
        y_n = [K[i] * x_profile[n][i] for i in range(C)]
        s = sum(y_n)
        if s > 0:
            y_n = [yi / s for yi in y_n]
        y_profile.append(y_n)

    # Caudales por componente en distillate y bottom
    # D_i = D · y_top_i (asumiendo condensador total, distillate=x_0)
    D_comp = [D * x_profile[0][i] for i in range(C)]
    B_comp = [B * x_profile[-1][i] for i in range(C)]

    # Duties por balance REAL de entalpía en los extremos (P2.4).
    # Unidades: V [mol/s] · H [J/mol] = W → /1000 = kW.
    H_L_fin = [_enthalpy_liquid(comps, x_profile[n], T_profile[n]) for n in range(N)]
    H_V_fin = [_enthalpy_vapor(comps, y_profile[n], T_profile[n]) for n in range(N)]
    H_D = H_L_fin[0]      # destilado (líquido, condensador total)
    H_B = H_L_fin[-1]     # fondo (líquido)
    V1 = D * (R + 1.0)    # vapor que entra al condensador (desde etapa 1)
    # Condensador (etapa 0): V1·H_V1 + Q_cond = (D+L0)·H_D = V1·H_D, L0=R·D
    Q_cond_kW = (V1 * (H_D - H_V_fin[1])) / 1000.0 if N >= 2 else 0.0
    # Reboiler (etapa N-1): L_{N-2}·H_L + Q_reb = V_{N-1}·H_V + B·H_B
    if N >= 2:
        Q_reb_kW = (V_profile[-1] * H_V_fin[-1] + B * H_B
                    - L_profile[-2] * H_L_fin[-2]) / 1000.0
    else:
        Q_reb_kW = -Q_cond_kW
    # Indicador MES vs MESH: varianza relativa del perfil de vapor en las
    # etapas con flujo de vapor (1..N-1; la 0 es el condensador, V_0=0).
    V_active = V_profile[1:] if N >= 2 else V_profile
    V_avg = sum(V_active) / len(V_active) if V_active else 0.0
    if V_avg > 0:
        V_var = (max(V_active) - min(V_active)) / V_avg
    else:
        V_var = 0.0

    return dict(
        converged=converged,
        iterations=it + 1,
        x_profile=x_profile,
        y_profile=y_profile,
        T_profile=T_profile,
        V_profile=V_profile,
        L_profile=L_profile,
        D_comp=D_comp,
        B_comp=B_comp,
        Q_cond_kW=Q_cond_kW,
        Q_reb_kW=Q_reb_kW,
        D=D, B=B,
        V_var=V_var,
    )
