"""
FLOWSHEET SOLVER — propagación iterativa de balances de masa y
energía sobre el grafo del diagrama de proceso.

ESTRATEGIA

  Sequential modular con propagación por cierre:

    En cada iteración, para cada bloque del flowsheet:
      1. Listar streams in/out con mass_flow conocido (!=0) y desconocido.
      2. Si exactamente UN stream del bloque queda sin valor, deducirlo
         por closure del balance de masa.
      3. Repetir hasta que no haya cambios o se llegue al max de
         iteraciones.

  Topología lineal (1-in-1-out, HX, pumps, tanks):
      out = in            ← caso trivial
  Mixers (N-in-1-out):
      out = Σ ins
  Splitters parciales (1-in-N-out, columna con dos productos):
      el output que falta = in − Σ otros outputs conocidos

  Reciclos (SCCs con > 1 bloque):
      El algoritmo de closure NO resuelve reciclos por sí mismo.  Si
      después de max_iter quedan streams sin propagar dentro de un
      reciclo, se reportan como 'unresolved' — el usuario debe
      declarar manualmente al menos uno (tear stream).
      Futura mejora: tear + Wegstein automático.

ENERGÍA

  Misma estructura.  Con duty del bloque + Cp/T de streams ya
  conocidos:
    Passthrough (1-in-1-out):
        T_out = T_in + duty_kW / (m_kg_s × Cp_kJ_per_kg_K)
    Mixer:
        T_out = (Σ m·Cp·T) / (Σ m·Cp)  (despreciando duty pequeño)
    Splitter:
        T_out_j = T_in (igualdad térmica)

  Cp del output se asume igual al del input dominante (no manejamos
  cambio de fase ni Cp(T)).

USO

    from flowsheet_solver import solve

    result = solve(flowsheet)
    print(result.summary())

    if not result.success:
        # mostrar result.unresolved_streams al user para que declare
        ...

DEPENDENCIAS
    Sólo stdlib (no networkx).  La detección de ciclos se hace
    en una pasada de Tarjan ligera embebida.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


# ======================================================
# CONSTANTES (deben matchear flowsheet_ui)
# ======================================================
T_REF_C       = 25.0
SEC_PER_YEAR  = 8760 * 3600
TM_TO_KG      = 1000.0
MASS_TOL_REL  = 0.005      # 0.5 %  tolerancia de balance de masa
ENERGY_TOL_REL = 0.05      # 5 %    tolerancia de balance de energía
MAX_ITER      = 30

# Rango físico razonable para T en un PFD industrial.
# Si el solver calcula una T fuera de este rango, NO la propaga
# (es señal de que el modelo Cp simple no captura ΔH_vap o ΔH_rxn
# y el duty declarado da una T absurda).
T_MIN_REASONABLE = -100.0    # °C  (refrigeración severa)
T_MAX_REASONABLE = 1500.0    # °C  (hornos de craqueo)


# ======================================================
# RESULTADO
# ======================================================

@dataclass
class RecycleSolution:
    """Resultado del solver Wegstein sobre un reciclo."""
    tear_stream:  str       = ""
    cycle_blocks: List[str] = field(default_factory=list)
    converged:    bool      = False
    iterations:   int       = 0
    final_value:  float     = 0.0
    history:      List[float] = field(default_factory=list)


@dataclass
class SolverResult:
    success:      bool                      = False
    iterations:   int                       = 0
    propagated_mass:    List[Tuple[str, float]] = field(default_factory=list)
    propagated_temp:    List[Tuple[str, float]] = field(default_factory=list)
    unresolved_streams: List[str]           = field(default_factory=list)
    mass_balance_errors: List[str]          = field(default_factory=list)
    energy_balance_errors: List[str]        = field(default_factory=list)
    cycles_detected:    List[List[str]]     = field(default_factory=list)
    recycle_solutions:  List[RecycleSolution] = field(default_factory=list)

    def summary(self):
        lines = []
        if self.success:
            lines.append(f"✓ Solver convergió en {self.iterations} iteraciones.")
        else:
            lines.append(f"⚠ Solver no convergió completamente ({self.iterations} iter).")

        if self.propagated_mass:
            lines.append(f"\nFlujos propagados ({len(self.propagated_mass)}):")
            for name, val in self.propagated_mass:
                lines.append(f"  · {name}: → {val:.4g} tm/año")

        if self.propagated_temp:
            lines.append(f"\nTemperaturas propagadas ({len(self.propagated_temp)}):")
            for name, val in self.propagated_temp:
                lines.append(f"  · {name}: → {val:.1f} °C")

        if self.unresolved_streams:
            lines.append(f"\nStreams sin resolver ({len(self.unresolved_streams)}):")
            for n in self.unresolved_streams:
                lines.append(f"  · {n}")

        if self.cycles_detected:
            lines.append(f"\nReciclos detectados ({len(self.cycles_detected)}):")
            for cyc in self.cycles_detected:
                lines.append(f"  · {' → '.join(cyc)} → (back)")

        if self.recycle_solutions:
            lines.append("")
            for rs in self.recycle_solutions:
                status = "✓ Wegstein convergió" if rs.converged else "⚠ Wegstein NO convergió"
                lines.append(f"{status}  (tear = {rs.tear_stream}, {rs.iterations} iter)")
                lines.append(f"  ciclo: {' → '.join(rs.cycle_blocks)}")
                lines.append(f"  valor final: {rs.final_value:.4g} tm/año")
                if len(rs.history) > 1:
                    hist_str = " → ".join(f"{v:.1f}" for v in rs.history[:5])
                    if len(rs.history) > 5:
                        hist_str += f" → … → {rs.history[-1]:.1f}"
                    lines.append(f"  trayectoria: {hist_str}")

        if self.mass_balance_errors:
            lines.append(f"\nBalance de masa con error:")
            for e in self.mass_balance_errors:
                lines.append(f"  · {e}")

        if self.energy_balance_errors:
            lines.append(f"\nBalance de energía con error:")
            for e in self.energy_balance_errors:
                lines.append(f"  · {e}")

        return "\n".join(lines)


# ======================================================
# DETECCIÓN DE CICLOS (Tarjan SCC simplificado)
# ======================================================

def _build_adjacency(fs):
    """Dict: block_id → set de block_ids alcanzables por un stream."""
    adj = {bid: set() for bid in fs.blocks}
    for s in fs.streams.values():
        if s.src in adj and s.dst in adj:
            adj[s.src].add(s.dst)
    return adj


def _strongly_connected_components(fs):
    """Tarjan SCC.  Devuelve lista de listas de block_ids.
    Cada SCC con > 1 bloque (o 1 bloque con auto-edge) es un reciclo."""
    adj = _build_adjacency(fs)
    index_counter = [0]
    stack = []
    lowlinks = {}
    index = {}
    on_stack = {}
    result = []

    def strongconnect(v):
        index[v] = index_counter[0]
        lowlinks[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack[v] = True
        for w in adj[v]:
            if w not in index:
                strongconnect(w)
                lowlinks[v] = min(lowlinks[v], lowlinks[w])
            elif on_stack.get(w):
                lowlinks[v] = min(lowlinks[v], index[w])
        if lowlinks[v] == index[v]:
            component = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                component.append(w)
                if w == v:
                    break
            result.append(component)

    for v in list(adj.keys()):
        if v not in index:
            strongconnect(v)
    return result


def _detect_cycles(fs):
    """Devuelve lista de ciclos (cada ciclo = lista de nombres de bloques)."""
    sccs = _strongly_connected_components(fs)
    cycles = []
    for scc in sccs:
        if len(scc) > 1:
            cycles.append([fs.blocks[bid].name for bid in scc])
        elif len(scc) == 1:
            # auto-edge: bloque conectado a sí mismo
            bid = scc[0]
            for s in fs.streams.values():
                if s.src == bid and s.dst == bid:
                    cycles.append([fs.blocks[bid].name])
                    break
    return cycles


# ======================================================
# SOLVER DE MASA — propagación por closure
# ======================================================

def _is_mass_locked(s):
    """True SOLO si el user fijó mass_flow (lock explícito).

    La heurística vieja (mass_flow > 0) ya NO se usa aquí: si la usáramos
    como fallback, los valores que el solver PROPAGA (no fijos) quedarían
    marcados como 'lock' en la siguiente iteración y nunca se podrían
    recomputar — eso rompe el unlock UX y la idempotencia del solver.

    Las fuentes legítimas de specs (example builders, from_dict, UI dialog)
    setean explícitamente el lock al crear/cargar.  Para JSONs viejos, la
    migración en Flowsheet.from_dict los infiere por heurística una vez."""
    return getattr(s, "mass_flow_locked", False)


def _is_temp_locked(s):
    """True solo si user fijó T (lock explícito).  Ver _is_mass_locked
    para el razonamiento de no usar heurística como fallback runtime."""
    return getattr(s, "temperature_locked", False)


def _is_comp_locked(s):
    """True solo si user fijó composición (lock explícito)."""
    return getattr(s, "composition_locked", False)


def _is_duty_locked(b):
    """True solo si user fijó duty (lock explícito)."""
    return getattr(b, "duty_locked", False)


def _reset_propagated_values(fs):
    """Limpia todos los valores que el solver propagó en corridas
    anteriores.  Idempotente sobre lo que el USER fijó (sudoku locks):
      - mass_flow → 0 si NOT mass_flow_locked
      - temperature → T_REF_C si NOT temperature_locked
      - composition → {} si NOT composition_locked AND no main_component
      - heat_of_reaction → 0 en bloques con reactions != [] (lo
        recomputa solve_equilibrium_reactors() desde cero).

    Sin este reset, valores propagados en un solve anterior persisten
    como "conocidos" (mass_flow > 0) y el solver no puede distinguirlos
    de specs del user → al editar un input lockeado, los downstream no
    se re-propagan correctamente.
    """
    from flowsheet_model import T_REF_C
    for s in fs.streams.values():
        if not _is_mass_locked(s):
            s.mass_flow = 0.0
        if not _is_temp_locked(s):
            s.temperature = T_REF_C
        # composition: solo limpiar si no está locked Y no hay main_component
        # declarado (que actúa como spec implícita "100% de X").
        if not _is_comp_locked(s) and not s.main_component:
            s.composition = {}
    for b in fs.blocks.values():
        # En reactores de equilibrio (Capa 4) heat_of_reaction lo
        # computa el solver desde 0 — limpiamos antes para que el
        # nuevo cálculo no se mezcle con el viejo.
        if getattr(b, "reactions", None):
            b.heat_of_reaction = 0.0


def _solve_mass_iteration(fs):
    """Una pasada sobre todos los bloques.  Devuelve lista de tuplas
    (stream_name, new_mass_flow) con lo que se propagó esta pasada.

    Reglas sudoku: un stream se considera "no resuelto" si:
       NOT mass_flow_locked  AND  mass_flow == 0
    Es decir, ni el user lo fijó NI el solver lo propagó todavía.

    Si en un bloque hay un único stream no resuelto y el resto está
    resuelto (lock o ya propagado), se deduce desde el balance Σ in =
    Σ out.  Si hay >1 no resuelto, se difiere para próxima pasada
    (otro bloque puede haber propagado para entonces).

    Importante: confiar en mass_flow > 0 como señal de "resuelto"
    requiere que `_reset_propagated_values()` haya corrido al inicio
    de solve(), si no los valores viejos persisten."""
    propagated = []
    for b in fs.blocks.values():
        ins  = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        if not ins or not outs:
            continue

        unknown_ins   = [s for s in ins
                          if not _is_mass_locked(s) and s.mass_flow == 0]
        unknown_outs  = [s for s in outs
                          if not _is_mass_locked(s) and s.mass_flow == 0]

        if not unknown_ins and len(unknown_outs) == 1:
            sum_in        = sum(s.mass_flow for s in ins)
            sum_known_out = sum(s.mass_flow for s in outs
                                 if s is not unknown_outs[0])
            deduced = sum_in - sum_known_out
            if deduced >= 0:    # permitir flujo cero (caso bypass cerrado)
                unknown_outs[0].mass_flow = deduced
                propagated.append((unknown_outs[0].name, deduced))

        elif not unknown_outs and len(unknown_ins) == 1:
            sum_out       = sum(s.mass_flow for s in outs)
            sum_known_in  = sum(s.mass_flow for s in ins
                                 if s is not unknown_ins[0])
            deduced = sum_out - sum_known_in
            if deduced >= 0:
                unknown_ins[0].mass_flow = deduced
                propagated.append((unknown_ins[0].name, deduced))
    return propagated


def _check_mass_balance(fs, tol_rel=MASS_TOL_REL):
    """Devuelve lista de mensajes para bloques cuyo balance falla."""
    errors = []
    for b in fs.blocks.values():
        ins  = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        if not ins or not outs:
            continue
        if any(s.mass_flow <= 0 for s in ins + outs):
            continue
        in_t  = sum(s.mass_flow for s in ins)
        out_t = sum(s.mass_flow for s in outs)
        diff  = abs(in_t - out_t)
        rel   = diff / max(in_t, out_t, 1e-9)
        if rel >= tol_rel:
            errors.append(
                f"{b.name}: ent={in_t:g} sal={out_t:g} Δ={diff:g} ({rel*100:.1f}%)"
            )
    return errors


# ======================================================
# SOLVER DE ENERGÍA — propagación de T por closure
# ======================================================

def _resolve_cp(s, T_eval=None):
    """Devuelve el Cp (kJ/kg·K) de un stream a la temperatura T_eval
    (default = s.temperature).

    Prioridad:
      1. THERMO_DB (DIPPR-100 polinomio cuártico, mucho más preciso a
         alta T) — si el componente está cubierto.
      2. components.py legacy (Cp lineal) — fallback para componentes
         no en thermo_db (genéricos, etc.).
      3. s.cp > 0 (override manual) — constante.
      4. None.
    """
    if T_eval is None:
        T_eval = s.temperature
    phase = s.phase or "liquid"

    # --- Prioridad 1: thermo_db (DIPPR) ---
    try:
        import thermo_db as _td
    except ImportError:
        _td = None
    if _td is not None:
        if s.composition:
            cp = _td.cp_mix_kJ_kg_K(s.composition, T_eval, phase)
            if cp > 0:
                return cp
        if s.main_component:
            cp = _td.cp_kJ_kg_K(s.main_component, T_eval, phase)
            if cp is not None and cp > 0:
                return cp

    # --- Prioridad 2: components.py legacy (Cp lineal) ---
    try:
        import components as comp_mod
    except ImportError:
        comp_mod = None
    if comp_mod is not None:
        if s.composition:
            cp = comp_mod.cp_mix_kJ_kg_K(s.composition, T_eval, phase)
            if cp > 0:
                return cp
        if s.main_component:
            c = comp_mod.get(s.main_component)
            if c is not None:
                return c.cp(T_eval, phase)

    if s.cp > 0:
        return s.cp
    return None


def _resolve_dh_vap(s):
    """ΔH_vap de un stream (kJ/kg).  None si no se puede calcular.

    Prioridad:
      1. s.delta_h_vap_override (manual del user).
      2. THERMO_DB (Clausius-Clapeyron derivado de Antoine — varía con T).
      3. components.py legacy (constante en Tb).
    """
    if s.delta_h_vap_override > 0:
        return s.delta_h_vap_override

    T_eval = s.temperature

    # --- Prioridad 1: thermo_db (Clausius-Clapeyron) ---
    try:
        import thermo_db as _td
    except ImportError:
        _td = None
    if _td is not None:
        if s.composition:
            dh = _td.delta_h_vap_mix_kJ_kg(s.composition, T_eval)
            if dh > 0:
                return dh
        if s.main_component:
            dh = _td.delta_h_vap_kJ_kg(s.main_component, T_eval)
            if dh is not None and dh > 0:
                return dh

    # --- Prioridad 2: components.py legacy ---
    try:
        import components as comp_mod
    except ImportError:
        return None
    if s.composition:
        dh = comp_mod.delta_h_vap_mix(s.composition)
        if dh > 0:
            return dh
    if s.main_component:
        c = comp_mod.get(s.main_component)
        if c is not None:
            return c.dh_vap
    return None


def _stream_enthalpy_kW(s):
    """Entalpía total de una corriente referida a T_REF_C, kW.
    Incluye:
      · sensible heat: m·Cp·(T - T_REF)
      · latente: si phase = 'vapor', sumar ΔH_vap completo
                 si phase = 'two_phase', sumar vapor_fraction × ΔH_vap

    Cp se evalúa a la temperatura promedio entre T_REF y T (mejor
    aproximación que evaluar en T sola, para Cp(T) variable).
    """
    if s.mass_flow <= 0:
        return None

    # Cp a T promedio (mejora vs evaluar solo en T)
    T_avg = (s.temperature + T_REF_C) / 2.0
    cp = _resolve_cp(s, T_eval=T_avg)
    if cp is None or cp <= 0:
        return None

    m_kg_s = (s.mass_flow * TM_TO_KG) / SEC_PER_YEAR
    h_sensible = m_kg_s * cp * (s.temperature - T_REF_C)

    # contribución latente si hay cambio de fase respecto al estado
    # de referencia (líquido a T_REF).
    h_latent = 0.0
    if s.phase in ("vapor", "gas"):
        dh = _resolve_dh_vap(s)
        if dh is not None:
            h_latent = m_kg_s * dh
    elif s.phase == "two_phase":
        dh = _resolve_dh_vap(s)
        if dh is not None:
            h_latent = m_kg_s * s.vapor_fraction * dh

    return h_sensible + h_latent


def _solve_energy_iteration(fs, tol_T=0.5, skipped=None):
    """Una pasada propagando T sobre los bloques.

    A diferencia del solver de masa, el de energía no usa "T_known":
    siempre RECALCULA la T del output a partir de los inputs + duty,
    porque la T es siempre derivable cuando se conocen masas, Cp e
    inputs.  Si la T calculada coincide con la actual (tol 0.5°C),
    no se reporta como propagada.

    Guard: si la T calculada cae fuera de [T_MIN_REASONABLE,
    T_MAX_REASONABLE], NO se propaga (probablemente el duty declarado
    incluye ΔH_vap o ΔH_rxn que el modelo Cp simple no representa).
    Se acumula en `skipped` (lista) para reportar al user.

    Sólo procesa bloques cuyos inputs ya están "listos":
      - todos los inputs tienen Cp > 0 y mass_flow > 0
      - todos los outputs tienen Cp > 0 y mass_flow > 0
    """
    propagated = []
    if skipped is None:
        skipped = []

    def _try_set(s_out, t_new, block_name):
        """Setea T_out si está en rango razonable y NO contradice una
        T ya declarada por el user.

        Caso 'T absurda' (fuera de rango físico): NO propaga, reporta.
        Caso 'T diferente pero razonable': respeta T declarada
                  (probable cambio de fase no modelado), reporta como
                  info no-crítica.
        """
        if not (T_MIN_REASONABLE <= t_new <= T_MAX_REASONABLE):
            skipped.append(
                f"{block_name} → {s_out.name}: T calc = {t_new:.0f} °C "
                f"fuera de rango físico [-100, 1500].  "
                f"Probable que el duty incluya ΔH_vap o ΔH_rxn que el "
                f"modelo Cp simple no captura.  T mantenida en {s_out.temperature:g} °C."
            )
            return False
        # T en rango razonable.  Sudoku lock: si el user lo fijó
        # explícitamente (temperature_locked OR heurística != T_REF),
        # respetamos su declaración.  Si está unlocked, propagamos
        # el valor calculado.
        diff = abs(t_new - s_out.temperature)
        if diff <= tol_T:
            return False
        if not _is_temp_locked(s_out):
            # T del output era libre → asignar la computed.
            s_out.temperature = t_new
            propagated.append((s_out.name, t_new))
            return True
        # T locked pero difiere de la computada → reportar como info
        # (probable cambio de fase, ΔH_vap, ΔH_rxn no modelado, o
        # configuración overdetermined).
        skipped.append(
            f"{block_name} → {s_out.name}: T calc = {t_new:.1f} °C "
            f"pero T declarada = {s_out.temperature:g} °C "
            f"(Δ={diff:.0f} °C).  Se respeta la declaración del user "
            f"(probable cambio de fase parcial)."
        )
        return False

    # importar lazy para evitar circular
    import equipment_ports as _ep_mod

    for b in fs.blocks.values():
        ins  = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        if not ins or not outs:
            continue
        # Que cada stream tenga Cp resoluble (manual, composition o
        # main_component) y mass_flow > 0.
        def _stream_ok(s):
            return s.mass_flow > 0 and _resolve_cp(s) is not None
        if not all(_stream_ok(s) for s in ins + outs):
            continue
        # bombas, compresores y fans tienen duty ELÉCTRICO.
        if _ep_mod.is_electrical_equipment(b.eq_type):
            continue

        duty = b.duty
        # heat_of_reaction: si declarado, se aplica al balance.
        # Convención: heat_of_reaction > 0  → endotérmico (consume calor)
        #             se SUMA al lado izquierdo del balance (como duty
        #             externo positivo).
        if b.heat_of_reaction != 0:
            m_in_total = sum(s.mass_flow * TM_TO_KG / SEC_PER_YEAR for s in ins)
            q_rxn = -m_in_total * b.heat_of_reaction
            # signo invertido porque exotérmico (heat_of_reaction < 0)
            # libera calor → es como un duty positivo.
            duty += q_rxn

        # Passthrough simple: 1 in - 1 out
        if len(ins) == 1 and len(outs) == 1:
            s_in, s_out = ins[0], outs[0]
            h_in = _stream_enthalpy_kW(s_in) or 0.0
            # Cp del output a T promedio (mejor estimación)
            T_guess_avg = (T_REF_C + s_out.temperature) / 2.0
            cp_out = _resolve_cp(s_out, T_eval=T_guess_avg)
            if cp_out is None or cp_out <= 0:
                continue
            m_out_kg_s = (s_out.mass_flow * TM_TO_KG) / SEC_PER_YEAR
            denom = m_out_kg_s * cp_out
            # restar contribución latente del output si está en vapor
            dh_lat_out = 0.0
            if s_out.phase in ("vapor", "gas"):
                dh_v = _resolve_dh_vap(s_out)
                if dh_v is not None:
                    dh_lat_out = m_out_kg_s * dh_v
            elif s_out.phase == "two_phase":
                dh_v = _resolve_dh_vap(s_out)
                if dh_v is not None:
                    dh_lat_out = m_out_kg_s * s_out.vapor_fraction * dh_v
            if denom > 0:
                # H_out = H_in + duty
                # H_out_sensible + H_out_lat = H_in + duty
                # T_out = T_REF + (H_in + duty - H_out_lat) / (m·Cp)
                t_new = T_REF_C + (h_in + duty - dh_lat_out) / denom
                _try_set(s_out, t_new, b.name)
            continue

        # Mixer: N in - 1 out
        if len(outs) == 1:
            s_out = outs[0]
            # entalpía total de los inputs
            h_in_total = sum(_stream_enthalpy_kW(s) or 0.0 for s in ins)
            T_guess_avg = (T_REF_C + s_out.temperature) / 2.0
            cp_out = _resolve_cp(s_out, T_eval=T_guess_avg)
            if cp_out is None or cp_out <= 0:
                continue
            m_out_kg_s = (s_out.mass_flow * TM_TO_KG) / SEC_PER_YEAR
            denom_out  = m_out_kg_s * cp_out
            dh_lat_out = 0.0
            if s_out.phase in ("vapor", "gas"):
                dh_v = _resolve_dh_vap(s_out)
                if dh_v is not None:
                    dh_lat_out = m_out_kg_s * dh_v
            elif s_out.phase == "two_phase":
                dh_v = _resolve_dh_vap(s_out)
                if dh_v is not None:
                    dh_lat_out = m_out_kg_s * s_out.vapor_fraction * dh_v
            if denom_out > 0:
                t_new = T_REF_C + (h_in_total + duty - dh_lat_out) / denom_out
                _try_set(s_out, t_new, b.name)
            continue

        # Splitter: 1 in - N out.
        # NO propagamos T en splitters porque típicamente hay
        # equilibrio L-V o cambios de fase (vapor más caliente que
        # líquido del flash, fondos vs tope de columna, etc.) que
        # el modelo Cp simple no representa.  El user declara las
        # Ts de cada output explícitamente.
        # Si el split es realmente adiabático (caudales paralelos
        # sin cambio de fase), el user declara T_out_j = T_in y
        # listo.
    return propagated


# ======================================================
# INFERENCIA DE DUTY DESDE BALANCE TERMODINÁMICO
# ======================================================
# Cuando un bloque tiene declaradas T, fase, composición y mass_flow
# de TODOS sus in/out, el duty queda determinado por el balance de
# energía.  Útil para:
#   - Auto-calibrar ejemplos (que el user solo declare T's, no duties).
#   - Botón "calcular duty desde balance" en la UI.
#   - Verificar consistencia: si el user declara un duty distinto al
#     inferido, hay algo mal en T's, fases o composiciones.


def is_cross_exchange(fs, b):
    """Detecta heat exchangers proceso-proceso (cross-exchange).

    Un HX cross-exchange tiene 2 corrientes entrantes y 2 salientes:
    una corriente caliente que cede calor y una fría que lo recibe.
    No consume utility — sólo recupera calor entre corrientes.
    Casos típicos: feed/effluent HX en HDA, lean/rich HX en aminas.
    """
    import equipment_costs as _eq_mod
    spec = _eq_mod.EQUIPMENT_DATA.get(b.eq_type, {})
    if spec.get("categoria") != "Heat exchangers":
        return False
    ins  = [s for s in fs.streams.values() if s.dst == b.id]
    outs = [s for s in fs.streams.values() if s.src == b.id]
    return len(ins) >= 2 and len(outs) >= 2


def infer_block_duty(fs, b):
    """Devuelve el duty kW que cierra el balance del bloque, o None si
    no se puede inferir (Cp irresoluble, mass_flow=0, sin in/out).

    Balance: H_out_total = H_in_total + duty_external + Q_rxn_released
    Donde Q_rxn_released = -m_in_total · heat_of_reaction (kJ/kg input).

    Para equipos eléctricos (bombas, compresores, fans) devuelve None
    — su duty es eléctrico, no térmico, y se setea aparte.
    """
    import equipment_ports as _ep_mod
    if _ep_mod.is_electrical_equipment(b.eq_type):
        return None

    ins  = [s for s in fs.streams.values() if s.dst == b.id]
    outs = [s for s in fs.streams.values() if s.src == b.id]
    if not ins or not outs:
        return None

    h_in_total = 0.0
    for s in ins:
        h = _stream_enthalpy_kW(s)
        if h is None:
            return None
        h_in_total += h

    h_out_total = 0.0
    for s in outs:
        h = _stream_enthalpy_kW(s)
        if h is None:
            return None
        h_out_total += h

    q_rxn = 0.0
    if b.heat_of_reaction != 0:
        m_in_total = sum(s.mass_flow * TM_TO_KG / SEC_PER_YEAR for s in ins)
        # exo (h_of_r < 0) → q_rxn > 0 (el medio recibe calor)
        q_rxn = -m_in_total * b.heat_of_reaction

    return h_out_total - h_in_total - q_rxn


def auto_set_duties_from_thermo(fs, only_zero=False, respect_locks=True):
    """Para cada bloque no-eléctrico, computa duty desde balance y lo
    asigna.

    Args:
        only_zero: si True, sólo sobreescribe bloques con duty=0.
        respect_locks: si True (default), SKIP bloques cuyo duty está
            locked por el user (sudoku spec).  Si False, sobreescribe
            todos (modo legacy, para example builders).

    Devuelve dict {block_id: duty_kw} de los duties asignados.
    """
    assigned = {}
    for b in fs.blocks.values():
        if respect_locks and _is_duty_locked(b):
            continue
        if only_zero and b.duty != 0:
            continue
        d = infer_block_duty(fs, b)
        if d is None:
            continue
        if is_cross_exchange(fs, b):
            b.duty = 0.0
            assigned[b.id] = 0.0
            continue
        b.duty = float(d)
        assigned[b.id] = float(d)
    return assigned


# ======================================================
# SETPOINTS / GOAL-SEEK (design targets)
# ======================================================
# Un setpoint declara qué se QUIERE en una corriente:
#   - target_temperature: T objetivo (°C)
#   - target_purity_component + target_purity_fraction: composición objetivo
#
# Hay dos modos de uso:
#   verify_setpoints(fs)     → calcula desviación, NO modifica nada.
#   goal_seek_duty(fs, ...)  → encuentra el duty de un bloque que hace
#                              que la T de salida iguale al setpoint.

# valor centinela: stream sin target_temperature seteado
SETPOINT_TEMP_UNSET = -999.0


def _has_temp_setpoint(s):
    return getattr(s, 'target_temperature', SETPOINT_TEMP_UNSET) > -273.0


def _has_purity_setpoint(s):
    return bool(getattr(s, 'target_purity_component', "")) \
        and getattr(s, 'target_purity_fraction', 0.0) > 0


def verify_setpoints(fs):
    """Verifica todos los setpoints del flowsheet contra los valores
    actuales.  No modifica nada.

    Returns:
        list of dicts: {
            'stream_id', 'stream_name', 'kind' ('T' | 'purity'),
            'target', 'actual', 'deviation', 'within_tol'
        }
    """
    results = []
    for s in fs.streams.values():
        if _has_temp_setpoint(s):
            t_target = s.target_temperature
            t_actual = s.temperature
            dev = t_actual - t_target
            results.append({
                "stream_id": s.id,
                "stream_name": s.name,
                "kind": "T",
                "target": t_target,
                "actual": t_actual,
                "deviation": dev,
                "within_tol": abs(dev) < 1.0,
                "unit": "°C",
            })
        if _has_purity_setpoint(s):
            comp = s.target_purity_component
            target = s.target_purity_fraction
            actual = s.composition.get(comp, 0.0) if s.composition else 0.0
            dev = actual - target
            results.append({
                "stream_id": s.id,
                "stream_name": s.name,
                "kind": "purity",
                "component": comp,
                "target": target,
                "actual": actual,
                "deviation": dev,
                "within_tol": abs(dev) < 0.005,   # 0.5% absoluto
                "unit": "frac",
            })
    return results


def goal_seek_duty(fs, target_stream_id, block_id, t_target, **kwargs):
    """Encuentra el duty kW del block `block_id` que hace que la T
    del stream `target_stream_id` iguale a `t_target` (°C).

    Para bloques con 1 entrada/output: resuelve closed-form desde el
    balance de energía:
        duty = H_out(@T_target) - H_in_total - Q_rxn
    Para multi-output: error (goal-seek 1D no aplica a splits).

    Args:
        fs: Flowsheet (modificado in-place — setea block.duty y
            target.temperature al valor encontrado).
        target_stream_id: stream cuyo T queremos controlar.
        block_id: bloque cuyo duty manipulamos.
        t_target: T objetivo en °C.

    Returns:
        dict: success, duty_found, iterations, t_final, message.
    """
    block = fs.blocks.get(block_id)
    target = fs.streams.get(target_stream_id)
    if block is None or target is None:
        return {"success": False, "message": "bloque o stream no existe",
                "iterations": 0, "duty_found": None, "t_final": None}

    # Si el duty del bloque está LOCKED por el user, no podemos
    # variarlo para hit el setpoint.  Sistema overspecified.
    if _is_duty_locked(block):
        return {"success": False,
                "message": f"duty de {block.name} está locked — "
                           f"conflict con setpoint en {target.name}",
                "iterations": 0, "duty_found": block.duty, "t_final": target.temperature}

    ins  = [s for s in fs.streams.values() if s.dst == block_id]
    outs = [s for s in fs.streams.values() if s.src == block_id]

    if not ins or not outs:
        return {"success": False, "message": "bloque sin in/out",
                "iterations": 0, "duty_found": None, "t_final": None}
    if len(outs) > 1:
        return {"success": False,
                "message": "goal-seek 1D no aplica a splits (>1 output)",
                "iterations": 0, "duty_found": None, "t_final": None}
    if outs[0].id != target_stream_id:
        return {"success": False,
                "message": "target stream no es el único output del bloque",
                "iterations": 0, "duty_found": None, "t_final": None}

    # H_in total
    h_in = 0.0
    for s in ins:
        e = _stream_enthalpy_kW(s)
        if e is None:
            return {"success": False, "message": "Cp no resoluble en inputs",
                    "iterations": 0, "duty_found": None, "t_final": None}
        h_in += e

    # Q_rxn (si hay reacción)
    q_rxn = 0.0
    if block.heat_of_reaction != 0:
        m_in_total = sum(s.mass_flow * TM_TO_KG / SEC_PER_YEAR for s in ins)
        q_rxn = -m_in_total * block.heat_of_reaction

    # H_out @ T_target
    saved_T = target.temperature
    target.temperature = t_target
    h_out = _stream_enthalpy_kW(target)
    target.temperature = saved_T
    if h_out is None:
        return {"success": False, "message": "Cp no resoluble en output",
                "iterations": 0, "duty_found": None, "t_final": None}

    duty = h_out - h_in - q_rxn

    # Aplicar al modelo
    block.duty = float(duty)
    target.temperature = float(t_target)

    return {
        "success": True,
        "duty_found": duty,
        "iterations": 1,
        "t_final": t_target,
        "message": "closed-form OK",
    }


def analyze_dof(fs):
    """Análisis de grados de libertad (sudoku) por bloque.

    Para cada bloque cuenta:
      - n_vars     : total de variables potencialmente libres
                     = streams_count * 3 + 1 (m, T, x por stream + duty)
      - n_constr   : constraints físicos automáticos
                     = 3 si tiene in/out (mass + energy + composition)
      - n_locked   : cuántas variables el user fijó (specifications)
      - dof        : grados de libertad libres = n_vars - n_constr - n_locked

    Status por bloque:
      'OK'              dof == 0 (sistema determinado por specs)
      'underspec'       dof > 0 (faltan specs, solver puede no resolver)
      'overspec'        dof < 0 (demasiadas specs, conflicto potencial)

    Returns:
        list of dicts: {block_id, block_name, n_vars, n_constr, n_locked,
                        dof, status}
    """
    rows = []
    for b in fs.blocks.values():
        ins  = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        streams = ins + outs
        n_streams = len(streams)
        if n_streams == 0:
            continue
        # Variables por stream: mass_flow, T, composition (3 cada uno)
        # Variable del bloque: duty (1)
        n_vars = n_streams * 3 + 1
        # Constraints físicos automáticos del bloque
        n_constr = 0
        if ins and outs:
            n_constr += 1  # mass balance
            n_constr += 1  # energy balance
            n_constr += 1  # composition propagation (para no-reactores)
        # Specs (locks)
        n_locked = 0
        for s in streams:
            if _is_mass_locked(s):   n_locked += 1
            if _is_temp_locked(s):   n_locked += 1
            if _is_comp_locked(s):   n_locked += 1
        if _is_duty_locked(b):       n_locked += 1
        dof = n_vars - n_constr - n_locked
        # Interpretación del DOF:
        #   = 0   : sistema determinado por specs exactas (Aspen-style)
        #   > 0   : faltan specs, solver no puede resolver TODO
        #   < 0   : redundante (más specs que constraints) — está OK
        #           SI los valores son consistentes (verificar con
        #           find_conflicts).  Útil cuando user declara
        #           inlet+outlet+duty (todos redundantes pero consistentes).
        if dof == 0:
            status = "OK (determined)"
        elif dof > 0:
            status = f"underspec (+{dof} libre)"
        else:
            status = f"redundant ({-dof} extra spec)"
        rows.append({
            "block_id":   b.id,
            "block_name": b.name,
            "eq_type":    b.eq_type,
            "n_vars":     n_vars,
            "n_constr":   n_constr,
            "n_locked":   n_locked,
            "dof":        dof,
            "status":     status,
        })
    return rows


def find_conflicts(fs, tol_mass_rel=0.01, tol_energy_rel=0.05):
    """Detecta overspecification numérica: bloques cuyas variables
    locked NO satisfacen el balance físico.

    - Mass conflict: todos los m_in y m_out están locked PERO
                     |sum_in - sum_out| / max > tol_mass_rel.
    - Energy conflict: todas las T's, duty y heat_of_reaction están
                       locked PERO |H_out - H_in - duty - q_rxn| / |duty| > tol_energy_rel.

    Returns:
        list de strings con mensajes legibles.
    """
    conflicts = []
    import equipment_ports as _ep_mod
    for b in fs.blocks.values():
        # Equipos eléctricos (bombas, compresores, fans): el duty es
        # potencia eléctrica al motor, no calor al fluido.  El balance
        # térmico no aplica directamente — skip energía.
        is_electrical = _ep_mod.is_electrical_equipment(b.eq_type)
        ins  = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        if not ins or not outs:
            continue
        # Mass: si TODOS están locked, verificar balance
        all_mass_locked = all(_is_mass_locked(s) for s in ins + outs)
        if all_mass_locked:
            sum_in  = sum(s.mass_flow for s in ins)
            sum_out = sum(s.mass_flow for s in outs)
            diff = abs(sum_in - sum_out)
            denom = max(sum_in, sum_out, 1e-9)
            if diff / denom > tol_mass_rel:
                conflicts.append(
                    f"{b.name}: masa locked overspec — "
                    f"Σm_in={sum_in:g} ≠ Σm_out={sum_out:g} "
                    f"(Δ={diff:g}, {100*diff/denom:.1f}%)"
                )
        # Energy: si TODAS las T están locked Y duty locked
        # (skip electrical — duty no es calor al fluido)
        all_T_locked = all(_is_temp_locked(s) for s in ins + outs)
        if all_T_locked and _is_duty_locked(b) and not is_electrical:
            # Compute residual
            try:
                h_in  = sum(_stream_enthalpy_kW(s) or 0.0 for s in ins)
                h_out = sum(_stream_enthalpy_kW(s) or 0.0 for s in outs)
                m_in = sum(s.mass_flow * TM_TO_KG / SEC_PER_YEAR for s in ins)
                q_rxn = -m_in * b.heat_of_reaction
                residual = h_out - h_in - b.duty - q_rxn
                if abs(b.duty) > 1 and abs(residual) / abs(b.duty) > tol_energy_rel:
                    conflicts.append(
                        f"{b.name}: energía locked overspec — "
                        f"H_out - H_in - duty - Q_rxn = {residual:+.1f} kW "
                        f"(no cierra balance)"
                    )
            except Exception:
                pass
    return conflicts


def solve_equilibrium_reactors(fs):
    """Para cada bloque con `reactions` declaradas (reactor de equilibrio,
    Capa 4):
      1. Agrega los inlets en una composición + mass_flow promedio.
      2. Llama solve_equilibrium_reactor_from_composition (Newton-Raphson
         multi-reacción en fase gas ideal).
      3. Setea composición de los outlets a la composición de equilibrio.
      4. Setea block.heat_of_reaction = ΔH/m_in [kJ/kg input] para que
         el balance de energía existente lo recoja sin tocar el solver.

    Skip si:
      - block.reactions == [] (no es reactor de equilibrio)
      - los inlets no tienen composición ni mass_flow (todavía no
        resueltos por el balance de masa upstream)
      - el solver multi-reacción no converge (e.g. Keq inválido o
        reacciones linealmente dependientes) → reporta y deja
        heat_of_reaction = 0.

    Devuelve lista de mensajes informativos (success/warning) por
    reactor procesado.
    """
    try:
        import reactions_db as _rdb
    except ImportError:
        return []
    msgs = []
    for b in fs.blocks.values():
        if not getattr(b, "reactions", None):
            continue
        ins  = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        if not ins or not outs:
            continue
        m_in_total = sum(s.mass_flow for s in ins if s.mass_flow > 0)
        if m_in_total <= 0:
            msgs.append(f"⚠ Reactor {b.name}: inlets sin mass_flow, skip.")
            continue
        # Composición agregada (mass-weighted) de los inputs
        agg: Dict[str, float] = {}
        for s in ins:
            if s.mass_flow <= 0:
                continue
            comp = s.composition or ({s.main_component: 1.0}
                                       if s.main_component else {})
            if not comp:
                continue
            w = s.mass_flow / m_in_total
            for c, f in comp.items():
                agg[c] = agg.get(c, 0.0) + w * f
        if not agg:
            msgs.append(f"⚠ Reactor {b.name}: inlets sin composition.")
            continue
        # Renormalizar (mass fractions deben sumar 1)
        total = sum(agg.values())
        if total > 0:
            agg = {k: v/total for k, v in agg.items()}
        # T de operación: explicit o promedio ponderado del inlet
        T_K = b.T_op_K if b.T_op_K > 0 else (
            sum(s.temperature * s.mass_flow for s in ins if s.mass_flow > 0)
              / m_in_total + 273.15)
        # mass_flow del flowsheet está en tm/año → kg/s
        from flowsheet_model import SEC_PER_YEAR, TM_TO_KG
        m_in_kg_s = m_in_total * TM_TO_KG / SEC_PER_YEAR

        res = _rdb.solve_equilibrium_reactor_from_composition(
            rxn_ids=b.reactions,
            inlet_composition=agg,
            inlet_mass_kg_s=m_in_kg_s,
            T_K=T_K, P_bar=b.P_op_bar)
        if res is None:
            msgs.append(f"✗ Reactor {b.name}: no convergió "
                         f"(rxns={b.reactions}, T={T_K:.0f}K, P={b.P_op_bar}bar).")
            continue

        # Aplicar resultados a los outlets (todos comparten composición;
        # mass_flow se distribuye según fracción declarada o se reparte
        # uniformemente).
        out_comp = res['outlet_composition']
        for s_out in outs:
            if not _is_comp_locked(s_out):
                s_out.composition = dict(out_comp)
                if not s_out.main_component and out_comp:
                    s_out.main_component = max(out_comp, key=out_comp.get)

        # heat_of_reaction se computa SIEMPRE desde el solver de
        # equilibrio (no hay flag de lock para este campo todavía;
        # el user que quiera override puede vaciar block.reactions
        # y declarar heat_of_reaction manual).  _reset_propagated_values
        # ya lo dejó en 0 al inicio del solve.
        b.heat_of_reaction = res['heat_of_reaction_kJ_per_kg']

        msgs.append(f"✓ Reactor {b.name}: ΔH={res['duty_kW']:+.2f} kW, "
                     f"ξ={res['xi']}, "
                     f"unmapped={res['unmapped'] if res['unmapped'] else 'none'}")
    return msgs


def auto_propagate_compositions(fs):
    """Para cada bloque NO reactivo, calcula la composición de las
    salidas como promedio ponderado por mass_flow de las entradas.

    - Bloques con heat_of_reaction != 0 (reactores): NO se tocan,
      la composición del output la declara el user (estequiometría).
    - Bloques con reactions != [] (reactor de equilibrio Capa 4):
      tampoco — su outlet lo escribe solve_equilibrium_reactors().
    - Splitters / mixers / HX / vessels / columnas: si el output no
      tiene composition declarada (vacío), se hereda de los inputs.
    - Si el output YA tiene composition, no se sobreescribe.

    Sólo se propaga main_component cuando estaba vacío.
    """
    changed = 0
    for b in fs.blocks.values():
        if b.heat_of_reaction != 0:
            continue
        if getattr(b, "reactions", None):
            continue
        ins  = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        if not ins:
            continue
        total_m = sum(s.mass_flow for s in ins if s.mass_flow > 0)
        if total_m <= 0:
            continue
        # composición ponderada de inputs
        agg = {}
        for s in ins:
            if s.mass_flow <= 0:
                continue
            w_stream = s.mass_flow / total_m
            comp_dict = s.composition or {}
            # si solo hay main_component, asumir 100% de ese
            if not comp_dict and s.main_component:
                comp_dict = {s.main_component: 1.0}
            for comp, frac in comp_dict.items():
                agg[comp] = agg.get(comp, 0.0) + w_stream * frac
        # renormalizar por seguridad
        total = sum(agg.values())
        if total > 0:
            agg = {k: v/total for k, v in agg.items()}
        # aplicar a outputs sin composición declarada (sudoku: respeta locks)
        for s_out in outs:
            if _is_comp_locked(s_out):
                continue
            s_out.composition = dict(agg)
            if not s_out.main_component and agg:
                s_out.main_component = max(agg, key=agg.get)
            changed += 1
    return changed


def assign_stream_numbers(fs):
    """Numera streams topológicamente (1, 2, 3, …) recorriendo el grafo
    desde los feeds.  Setea `s._display_number` (cache topológico).

    NOTA: si el user setea `s.display_number` (sin underscore, en el
    modelo), ESE número se usa al mostrar — el topológico queda como
    fallback para streams sin numeración manual.  Acá calculamos
    el topológico para todos, los custom lo sobreescriben en el render.
    """
    n = 0
    visited_streams = set()
    visited_blocks = set()
    starting = []
    for b in fs.blocks.values():
        has_in = any(s.dst == b.id for s in fs.streams.values())
        if not has_in:
            starting.append(b.id)
    queue = list(starting)
    used_customs = set(s.display_number for s in fs.streams.values()
                        if s.display_number > 0)

    def _next_avail():
        nonlocal n
        n += 1
        while n in used_customs:
            n += 1
        return n

    while queue:
        bid = queue.pop(0)
        if bid in visited_blocks:
            continue
        visited_blocks.add(bid)
        out_streams = sorted([s for s in fs.streams.values() if s.src == bid],
                              key=lambda s: s.id)
        for s in out_streams:
            if s.id not in visited_streams:
                s._display_number = _next_avail()
                visited_streams.add(s.id)
                if s.dst not in visited_blocks:
                    queue.append(s.dst)
    for s in fs.streams.values():
        if s.id not in visited_streams:
            s._display_number = _next_avail()


def solve_setpoints_all(fs, max_iter=40):
    """Para CADA stream con target_temperature seteado, ajusta el duty
    del bloque upstream inmediato (el que produce ese stream) para
    matchear el setpoint.

    Returns:
        list of resultados de goal_seek_duty, uno por setpoint resuelto.
    """
    results = []
    for s in list(fs.streams.values()):
        if not _has_temp_setpoint(s):
            continue
        # encontrar bloque upstream (cuyo output es s)
        block_id = s.src
        if block_id is None:
            continue
        res = goal_seek_duty(fs, s.id, block_id, s.target_temperature,
                              max_iter=max_iter)
        res["stream_name"] = s.name
        res["block_name"]  = fs.blocks.get(block_id).name if fs.blocks.get(block_id) else "?"
        res["t_target"]    = s.target_temperature
        results.append(res)
    return results


# ======================================================
# TEAR STREAM + WEGSTEIN (resolución de reciclos)
# ======================================================
# Cuando un SCC tiene > 1 bloque y alguno de sus streams tiene
# mass_flow desconocido, el solver de closure no puede arrancar.
# Wegstein:
#   1. Elegir un tear stream del ciclo.
#   2. Asignarle un guess inicial (estimado por feeds externos al SCC).
#   3. Propagar el resto del ciclo con ese guess (cierre normal).
#   4. Calcular el "nuevo" valor del tear desde el balance del bloque
#      cuyo OUTPUT es el tear stream.
#   5. Si nuevo ≈ guess, convergió.  Si no, actualizar guess con Wegstein:
#         q = s / (s − 1)    donde  s = (f(x_n) − f(x_{n-1})) / (x_n − x_{n-1})
#         x_{n+1} = (1 − q) · f(x_n) + q · x_n
#      (acelera convergencia y previene oscilación)
#   6. Repetir hasta convergencia o max iter.


def _is_recycle_scc(scc_block_ids, fs):
    """Verdadero si el SCC tiene > 1 bloque, o 1 bloque con auto-edge."""
    if len(scc_block_ids) > 1:
        return True
    bid = scc_block_ids[0]
    for s in fs.streams.values():
        if s.src == bid and s.dst == bid:
            return True
    return False


def _streams_in_scc(scc_block_ids, fs):
    """Streams cuyos src y dst están ambos en el SCC."""
    bids = set(scc_block_ids)
    return [s for s in fs.streams.values()
            if s.src in bids and s.dst in bids]


def _choose_tear(scc_streams):
    """Heurística: primer stream sin mass_flow declarado.
    Si todos declarados, devuelve None (no hace falta tear)."""
    unknowns = [s for s in scc_streams if s.mass_flow <= 0]
    if unknowns:
        return unknowns[0]
    return None


def _initial_guess(fs, scc_block_ids, tear_stream):
    """Guess inicial del tear basado en feeds externos al SCC.

    Idea: la masa que circula en el ciclo es del orden de los
    inputs externos.  Si el reciclo es de purga (recycle), suele
    ser una fracción del flujo total.  Empezamos con el total
    externo dividido por 5 — luego Wegstein corrige."""
    bids = set(scc_block_ids)
    external_inputs = [
        s for s in fs.streams.values()
        if s.src not in bids and s.dst in bids and s.mass_flow > 0
    ]
    total_ext = sum(s.mass_flow for s in external_inputs)
    if total_ext > 0:
        return total_ext * 0.2     # 20% del feed externo como guess
    return 1000.0                  # fallback arbitrario


def _propagate_until_stable(fs, max_inner=30):
    """Corre _solve_mass_iteration hasta no haber cambios."""
    for _ in range(max_inner):
        if not _solve_mass_iteration(fs):
            break


def _balance_at_block(fs, block_id, exclude_stream_id=None):
    """Devuelve el balance del bloque ignorando un stream:
    sum_in - sum_out_sin_excluido.
    Útil para inferir el valor de un stream excluido."""
    sum_in = sum(
        s.mass_flow for s in fs.streams.values()
        if s.dst == block_id and s.id != exclude_stream_id and s.mass_flow > 0
    )
    sum_out_otros = sum(
        s.mass_flow for s in fs.streams.values()
        if s.src == block_id and s.id != exclude_stream_id and s.mass_flow > 0
    )
    return sum_in - sum_out_otros


def _solve_recycle_wegstein(fs, scc_block_ids,
                            max_iter=25, tol=0.001):
    """Resuelve un reciclo via tear + Wegstein.

    Returns RecycleSolution con history del tear, convergencia, etc.
    """
    scc_streams = _streams_in_scc(scc_block_ids, fs)
    tear = _choose_tear(scc_streams)
    rs = RecycleSolution(
        cycle_blocks=[fs.blocks[bid].name for bid in scc_block_ids],
    )

    if tear is None:
        rs.converged = True
        return rs

    rs.tear_stream = tear.name

    # guess inicial
    guess = _initial_guess(fs, scc_block_ids, tear)
    tear.mass_flow = guess
    rs.history.append(guess)

    # buffers para Wegstein
    x_prev:     float = guess
    f_prev:     float = guess

    for it in range(max_iter):
        # 1. Propagar el resto del flowsheet con el tear actual
        _propagate_until_stable(fs)

        # 2. Calcular nuevo valor del tear: balance del bloque
        #    cuya OUTPUT es el tear stream.
        #
        #    El tear pertenece al output del bloque tear.src:
        #      sum(in tear.src) = tear.mass_flow + sum(otros out tear.src)
        #      → tear_new = sum(in) - sum(otros out)
        f_new = _balance_at_block(fs, tear.src, exclude_stream_id=tear.id)

        if f_new <= 0:
            # algo está mal — break con no-converged
            rs.converged = False
            rs.iterations = it + 1
            rs.final_value = tear.mass_flow
            return rs

        x_n = tear.mass_flow

        # 3. Test de convergencia
        diff = abs(f_new - x_n)
        scale = max(abs(f_new), abs(x_n), 1e-9)
        if diff / scale < tol:
            tear.mass_flow = f_new
            rs.history.append(f_new)
            # propagar una vez más para que el resto del flowsheet
            # use el valor final del tear
            _propagate_until_stable(fs)
            rs.converged = True
            rs.iterations = it + 1
            rs.final_value = f_new
            return rs

        # 4. Wegstein update
        if it == 0:
            # primera iter: substitution directa
            x_next = f_new
        else:
            denom = (x_n - x_prev)
            if abs(denom) < 1e-12:
                x_next = f_new
            else:
                s = (f_new - f_prev) / denom
                # estabilizar: si s ∉ (−5, 1), usar substitution
                if -5.0 < s < 0.99:
                    q = s / (s - 1.0)
                    x_next = (1.0 - q) * f_new + q * x_n
                else:
                    x_next = f_new

        # actualizar buffers
        x_prev, f_prev = x_n, f_new
        tear.mass_flow = x_next
        rs.history.append(x_next)

    # no convergió
    rs.converged = False
    rs.iterations = max_iter
    rs.final_value = tear.mass_flow
    return rs


# ======================================================
# ENTRYPOINT
# ======================================================

def solve(fs, max_iter=MAX_ITER):
    """Resuelve mass + energy balance sobre el flowsheet in-place.

    Args:
        fs: Flowsheet con blocks y streams.
        max_iter: límite de iteraciones (default 30).

    Returns:
        SolverResult.
    """
    result = SolverResult()

    # 0. Reset de valores propagados en corridas anteriores.  Sin esto,
    #    al editar un valor lockeado y volver a llamar solve(), los
    #    streams downstream que se habían propagado quedan con valores
    #    viejos y la propagación nueva no los re-deduce porque los
    #    encuentra "ya resueltos" (mass_flow > 0).  Idempotente sobre
    #    locks del user.
    _reset_propagated_values(fs)

    # 1. Detectar SCCs y reciclos
    sccs = _strongly_connected_components(fs)
    recycle_sccs = [scc for scc in sccs if _is_recycle_scc(scc, fs)]
    result.cycles_detected = [
        [fs.blocks[b].name for b in scc] for scc in recycle_sccs
    ]

    # 2. Propagación inicial (closure) — resuelve todo lo lineal y
    #    los reciclos cuyos streams ya están todos declarados.
    total_propagated_mass = []
    for it in range(max_iter):
        prop = _solve_mass_iteration(fs)
        total_propagated_mass.extend(prop)
        if not prop:
            break
    result.iterations = it + 1

    # 3. Wegstein por reciclo no resuelto
    for scc in recycle_sccs:
        scc_streams = _streams_in_scc(scc, fs)
        if all(s.mass_flow > 0 for s in scc_streams):
            continue  # ya está resuelto por closure
        rs = _solve_recycle_wegstein(fs, scc)
        result.recycle_solutions.append(rs)

    # 4. Re-propagar después de los tears resueltos (cierra todo lo
    #    que dependía indirectamente de un tear)
    for _ in range(max_iter):
        prop = _solve_mass_iteration(fs)
        total_propagated_mass.extend(prop)
        if not prop:
            break
    result.propagated_mass = total_propagated_mass

    # 4b. Reactores de equilibrio (Capa 4): resuelve composición y
    #     setea heat_of_reaction para que el balance de energía lo
    #     recoja en el siguiente paso.  Idempotente — solo procesa
    #     bloques con b.reactions != [].
    rxn_msgs = solve_equilibrium_reactors(fs)
    for m in rxn_msgs:
        if m.startswith("✗") or m.startswith("⚠"):
            result.energy_balance_errors.append(m)

    # 5. Solver de energía
    total_propagated_temp = []
    skipped_temp = []
    for it_e in range(max_iter):
        prop_e = _solve_energy_iteration(fs, skipped=skipped_temp)
        total_propagated_temp.extend(prop_e)
        if not prop_e:
            break
    result.propagated_temp = total_propagated_temp
    # auto-propagar composiciones para bloques no-reactivos
    auto_propagate_compositions(fs)
    # numerar streams topológicamente (para display en pills)
    assign_stream_numbers(fs)
    # Mensajes de T omitidas por estar fuera de rango razonable
    # (típicamente porque el duty incluye ΔH_vap/ΔH_rxn que el modelo
    # Cp simple no captura).  Reportamos UNA vez cada uno.
    if skipped_temp:
        seen = set()
        for msg in skipped_temp:
            if msg not in seen:
                result.energy_balance_errors.append(msg)
                seen.add(msg)

    # 4. Validación + listado de unresolved
    for s in fs.streams.values():
        if s.mass_flow <= 0:
            result.unresolved_streams.append(s.name)
    result.mass_balance_errors    = _check_mass_balance(fs)
    # energy balance errors quedan deshabilitados (no comparables al Cp
    # simple — comentado en _check_energy_balance del editor)

    result.success = (
        not result.unresolved_streams and
        not result.mass_balance_errors
    )
    return result
