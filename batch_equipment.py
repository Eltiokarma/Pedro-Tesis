"""
batch_equipment.py — Diseño/sizing de equipo batch (Capa 2).

Reactor batch: ODE de moles totales en volumen constante.

      dN_i / dt = (Σⱼ νᵢⱼ · rⱼ(C, T)) · V_reactor          [mol/s]

PFR (reactions_db.solve_pfr):
      dF_i / dV = (Σⱼ νᵢⱼ · rⱼ(C, T))                     [mol/s/m³]

Mismo RHS multiplicado por V; integramos en t en lugar de V.  REUSA
las primitivas de reactions_db (Reaction.rate_net, R_GAS, get,
_check_kinetics_compatibility).  NO se escribe un integrador RK4
nuevo — se replica el lazo de solve_pfr cambiando la variable de
integración.

API:
    solve_batch_reactor(rxn_ids, N_in, T_K, P_bar, V_reactor,
                          t_final_s, n_steps=200, rho_b=None)
        → dict con N_out, conversion, t_final_s, profile_t, profile_N.

    time_to_conversion(rxn_ids, N_in, T_K, P_bar, V_reactor,
                        target_species, target_conversion,
                        t_max_s=86400, n_steps=400, ...)
        → duración (s) hasta alcanzar la conversión objetivo del
          target_species.  Sirve como ode_hook de Capa 1.

    make_ode_hook(rxn_ids, N_in_per_batch, T_K, P_bar, V_reactor,
                   target_species, target_conversion, ...)
        → callable(Task) → float  compatible con
          batch_schedule.resolve_dynamic_durations.

Notación: usamos N (mol) para diferenciar de F (mol/s) del PFR.

Conexión con el flowsheet: el caller convierte mass_flow → N_in
multiplicando por cycle_time_s/batches y dividiendo por MW.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

import reactions_db as _rdb


# ─────────────────────────────────────────────────────────────
# Reactor batch — ODE en moles totales, V constante
# ─────────────────────────────────────────────────────────────

def solve_batch_reactor(rxn_ids:    List[str],
                          N_in:       Dict[str, float],
                          T_K:        float,
                          P_bar:      float,
                          V_reactor:  float,
                          t_final_s:  float,
                          n_steps:    int = 200,
                          rho_b:      Optional[float] = None,
                          ) -> Optional[Dict]:
    """Reactor batch isotérmico, V constante, RK4 explícito en t.

    Args:
        rxn_ids:    reacciones (e.g. ['R008']).  Deben tener cinética
                    Arrhenius compatible (mismo check que solve_pfr).
        N_in:       {formula: mol_totales} carga inicial al reactor.
        T_K, P_bar: condiciones (P_bar solo relevante para fase
                    gaseosa o reacciones con uses_partial_pressure).
        V_reactor:  volumen del reactor [m³] (constante en batch).
        t_final_s:  tiempo de integración [s].
        n_steps:    pasos RK4 (default 200).
        rho_b:      ρ_b [kg_cat/m³] para reacciones cat_mass.

    Returns:
        dict con:
          'N_out':      {formula: mol_totales} al t_final
          'conversion': {formula: x} para reactantes (positivo)
          't_final_s':  duración real integrada
          'profile_t':  [t_0, t_1, ..., t_N]
          'profile_N':  [{formula: N} en cada paso]
        None si la cinética falla (T fuera de rango, falta rate, ...).
    """
    err = _rdb._check_kinetics_compatibility(rxn_ids)
    if err is not None:
        return None
    # Default rho_b
    if rho_b is None:
        for rid in rxn_ids:
            r = _rdb.get(rid)
            if r and r.rho_b_cat:
                rho_b = r.rho_b_cat
                break

    # Coleccionar especies
    species = set(N_in.keys())
    rxns: List[_rdb.Reaction] = []
    for rid in rxn_ids:
        r = _rdb.get(rid)
        if r is None:
            return None
        rxns.append(r)
        for sp in r.stoich:
            species.add(sp.formula)

    uses_pp = rxns[0].uses_partial_pressure

    # Estado inicial
    N = {s: float(N_in.get(s, 0.0)) for s in species}

    if V_reactor <= 0:
        return None
    if t_final_s <= 0 or n_steps <= 0:
        return None

    dt = t_final_s / n_steps
    profile_t: List[float] = [0.0]
    profile_N: List[Dict[str, float]] = [dict(N)]

    def _deriv(N_state: Dict[str, float]) -> Optional[Dict[str, float]]:
        """dN_i/dt = Σⱼ νᵢⱼ · rⱼ(C) · V_reactor   [mol/s]"""
        # Concentración instantánea C_i = N_i / V
        N_tot = sum(max(N_state[k], 0.0) for k in N_state) or 1e-12
        conc: Dict[str, float] = {}
        if uses_pp:
            # Presión parcial: P_i = (N_i / N_tot) · P_bar [bar]
            for k in N_state:
                conc[k] = P_bar * max(N_state[k], 0.0) / N_tot
        else:
            # Concentración volumétrica: C_i = N_i / V [mol/m³]
            for k in N_state:
                conc[k] = max(N_state[k], 0.0) / V_reactor

        dN_dt: Dict[str, float] = {k: 0.0 for k in species}
        for rxn in rxns:
            r_rate = rxn.rate_net(T_K, conc)        # mol/(m³·s) o mol/(kg·s)
            if r_rate is None:
                return None
            if rxn.rate_basis == 'cat_mass':
                if rho_b is None:
                    return None
                r_rate = r_rate * rho_b              # mol/(m³·s)
            for sp in rxn.stoich:
                if sp.formula not in dN_dt:
                    dN_dt[sp.formula] = 0.0
                dN_dt[sp.formula] += sp.nu * r_rate * V_reactor
        return dN_dt

    # RK4 (mismo patrón que solve_pfr lineas 1334-1353)
    for step in range(n_steps):
        k1 = _deriv(N)
        if k1 is None:
            return None
        N_2 = {k: max(N[k] + 0.5 * dt * k1[k], 0.0) for k in species}
        k2 = _deriv(N_2)
        if k2 is None:
            return None
        N_3 = {k: max(N[k] + 0.5 * dt * k2[k], 0.0) for k in species}
        k3 = _deriv(N_3)
        if k3 is None:
            return None
        N_4 = {k: max(N[k] + dt * k3[k], 0.0) for k in species}
        k4 = _deriv(N_4)
        if k4 is None:
            return None
        N = {k: max(N[k] + dt / 6.0 *
                     (k1[k] + 2 * k2[k] + 2 * k3[k] + k4[k]), 0.0)
             for k in species}
        profile_t.append((step + 1) * dt)
        profile_N.append(dict(N))

    # Conversiones de reactantes (cuando N disminuyó)
    conv: Dict[str, float] = {}
    for sp in species:
        Nin = N_in.get(sp, 0.0)
        if Nin > 1e-12 and N[sp] < Nin:
            conv[sp] = (Nin - N[sp]) / Nin
    return {
        "N_out":      N,
        "conversion": conv,
        "t_final_s":  t_final_s,
        "profile_t":  profile_t,
        "profile_N":  profile_N,
    }


# ─────────────────────────────────────────────────────────────
# Búsqueda binaria en t hasta alcanzar conversión objetivo
# ─────────────────────────────────────────────────────────────

def time_to_conversion(rxn_ids:           List[str],
                        N_in:              Dict[str, float],
                        T_K:               float,
                        P_bar:             float,
                        V_reactor:         float,
                        target_species:    str,
                        target_conversion: float,
                        t_max_s:           float = 86400.0,
                        n_steps_eval:      int   = 400,
                        rho_b:             Optional[float] = None,
                        ) -> Optional[float]:
    """Duración (s) hasta que conversion[target_species] >= target.

    Estrategia: integra UNA vez hasta t_max_s con n_steps_eval pasos
    y busca linealmente el primer paso donde la conversión cruza el
    umbral.  Devuelve el tiempo del paso (interpolación lineal para
    refinar).  None si nunca alcanza el target en t_max_s
    (cinética demasiado lenta a esa T).
    """
    if not (0 < target_conversion < 1):
        return None
    target_Nin = N_in.get(target_species, 0.0)
    if target_Nin <= 0:
        return None
    target_N_remaining = target_Nin * (1.0 - target_conversion)

    res = solve_batch_reactor(
        rxn_ids=rxn_ids, N_in=N_in,
        T_K=T_K, P_bar=P_bar, V_reactor=V_reactor,
        t_final_s=t_max_s, n_steps=n_steps_eval, rho_b=rho_b,
    )
    if res is None:
        return None

    profile_t = res["profile_t"]
    profile_N = res["profile_N"]
    for i in range(1, len(profile_t)):
        N_now  = profile_N[i].get(target_species, target_Nin)
        N_prev = profile_N[i - 1].get(target_species, target_Nin)
        if N_now <= target_N_remaining:
            # Interpolación lineal entre paso i-1 e i
            if N_prev <= N_now:
                return profile_t[i]
            frac = (N_prev - target_N_remaining) / (N_prev - N_now)
            return profile_t[i - 1] + frac * (profile_t[i] - profile_t[i - 1])
    return None     # nunca alcanzó la conversión en t_max_s


# ─────────────────────────────────────────────────────────────
# Hook ODE compatible con batch_schedule.resolve_dynamic_durations
# ─────────────────────────────────────────────────────────────

def make_ode_hook(rxn_ids:           List[str],
                   N_in_per_batch:    Dict[str, float],
                   T_K:               float,
                   P_bar:             float,
                   V_reactor:         float,
                   target_species:    str,
                   target_conversion: float,
                   t_max_s:           float = 86400.0,
                   rho_b:             Optional[float] = None,
                   ) -> Callable:
    """Construye un callable(Task) → float que Capa 1 puede usar
    en resolve_dynamic_durations() para resolver la duración de
    una tarea de tipo REACCION.

    Uso:
        hook = make_ode_hook(['R008'], {'CH3COOH': 5, 'C2H5OH': 5},
                              T_K=353, P_bar=1.013, V_reactor=2.0,
                              target_species='CH3COOH',
                              target_conversion=0.80)
        task_react = Task('react', TaskKind.REACCION, ode_hook=hook)
        recipe = BatchRecipe('ester', tasks=[..., task_react, ...])
        batch_schedule.resolve_dynamic_durations(recipe)
        # ahora task_react.duration_s tiene el valor real
    """
    def _hook(_task) -> float:
        dur = time_to_conversion(
            rxn_ids=rxn_ids, N_in=N_in_per_batch,
            T_K=T_K, P_bar=P_bar, V_reactor=V_reactor,
            target_species=target_species,
            target_conversion=target_conversion,
            t_max_s=t_max_s, rho_b=rho_b,
        )
        if dur is None:
            # Indeterminable → señal explícita; Capa 1 lanzará
            # ValueError al medir cycle_time porque la duración
            # quedó None.  Default seguro: t_max_s ajusta de manera
            # conservadora.  Aquí preferimos devolver t_max_s y
            # documentar; el user puede subir t_max_s o aumentar T.
            return float(t_max_s)
        return float(dur)
    return _hook
