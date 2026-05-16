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
    # Warnings informativos (no afectan success):
    #   - T computada vs declarada difiere pero ambas razonables
    #     (probable cambio de fase parcial, ΔH_vap o ΔH_rxn que el
    #      modelo Cp simple no captura).  El solver respeta la T
    #      declarada del user.
    energy_warnings:     List[str]          = field(default_factory=list)
    # Warnings sobre balance POR COMPONENTE en blocks no-reactor.
    # Indica que las composiciones declaradas en los example builders
    # son inconsistentes con un balance riguroso por componente.
    # No degrada overall_status — el balance total sigue siendo OK.
    component_warnings:  List[str]          = field(default_factory=list)
    cycles_detected:    List[List[str]]     = field(default_factory=list)
    recycle_solutions:  List[RecycleSolution] = field(default_factory=list)

    # Estados por bloque y por stream para colorización en la UI.
    # Llave: id del bloque/stream.  Valor: 'ok' | 'warning' | 'error' |
    # 'unrun'.  unrun = bloque/stream no participa del balance (e.g.
    # tanque sin streams) o el solver no lo procesó.  Los populamos
    # al final de solve().
    block_status:  Dict[int, str]           = field(default_factory=dict)
    stream_status: Dict[int, str]           = field(default_factory=dict)
    # Estado global del flowsheet:
    #   'ok'      = balance correcto sin warnings
    #   'warning' = balance correcto con warnings de T/ΔH no modelado
    #   'error'   = mass imbalance o streams sin resolver
    #   'empty'   = no hay bloques/streams
    overall_status: str                     = "ok"

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

        if self.energy_warnings:
            lines.append(f"\nWarnings de energía (no críticos, "
                          f"{len(self.energy_warnings)}):")
            for w in self.energy_warnings:
                lines.append(f"  · {w}")

        if self.component_warnings:
            lines.append(f"\nWarnings de balance por componente "
                          f"({len(self.component_warnings)}):")
            for w in self.component_warnings:
                lines.append(f"  · {w}")

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
    """Devuelve lista de mensajes para bloques cuyo balance TOTAL falla.
    El balance por componente se chequea aparte (_check_component_balance)."""
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


def _check_component_balance(fs, tol_rel=0.02):
    """Verifica balance POR COMPONENTE en cada bloque.  Devuelve lista
    de mensajes — para WARNINGS (no errores críticos, porque los
    example builders pueden tener composiciones declaradas
    inconsistentes que el solver no recalcula).

    Skipea:
      · Reactores (reactions != []) — la estequiometría cambia comp.
      · Bloques con streams en mass=0 (no resueltos).
      · Bloques inmediatamente downstream de un reactor en el mismo
        flujo (la composición del reactor se propaga, no las specs
        del example builder).

    Reporta si Σ(mass_in·w_i) ≠ Σ(mass_out·w_i) en >tol_rel para
    algún componente significativo (>1% del flujo total).
    """
    warnings_list = []
    # Set de bloques que son reactores
    rxn_blocks = {b.id for b in fs.blocks.values()
                   if getattr(b, "reactions", None)}
    # Bloques downstream de un reactor (vía un stream).  Para esos,
    # los outlets son composición HEREDADA via auto_propagate, los
    # exemplos pueden tener composiciones declaradas que no matcheen.
    downstream_of_rxn = set()
    for s in fs.streams.values():
        if s.src in rxn_blocks and s.dst in fs.blocks:
            downstream_of_rxn.add(s.dst)

    for b in fs.blocks.values():
        if b.id in rxn_blocks:
            continue   # reactores cambian composición
        if b.id in downstream_of_rxn:
            continue   # primera fila después del reactor, hereda
        ins  = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        if not ins or not outs:
            continue
        if any(s.mass_flow <= 0 for s in ins + outs):
            continue
        in_t = sum(s.mass_flow for s in ins)
        out_t = sum(s.mass_flow for s in outs)
        comp_in: Dict[str, float] = {}
        comp_out: Dict[str, float] = {}
        for s in ins:
            comp = s.composition or ({s.main_component: 1.0}
                                       if s.main_component else {})
            for c, w in comp.items():
                comp_in[c] = comp_in.get(c, 0.0) + w * s.mass_flow
        for s in outs:
            comp = s.composition or ({s.main_component: 1.0}
                                       if s.main_component else {})
            for c, w in comp.items():
                comp_out[c] = comp_out.get(c, 0.0) + w * s.mass_flow
        # Identificar componentes desbalanceados (>1% del flujo bloque)
        bad = []
        for c in set(comp_in) | set(comp_out):
            ci, co = comp_in.get(c, 0.0), comp_out.get(c, 0.0)
            if max(ci, co) < 0.01 * max(in_t, out_t):
                continue
            d = abs(ci - co)
            r = d / max(ci, co, 1e-9)
            if r >= tol_rel:
                bad.append(f"{c}: in={ci:.0f} out={co:.0f} ({r*100:.0f}%)")
        if bad:
            warnings_list.append(
                f"{b.name} balance por componente: " + "; ".join(bad[:3])
            )
    return warnings_list


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
        # Reactores con cinética/equilibrio (Capas 4 y 5): la T del
        # outlet está fijada por el modo del reactor (T_op_K).  El
        # balance de energía sensible + ΔH_rxn no puede captar la
        # realidad isothermal/adiabatic-with-duty del reactor — el
        # solver de energía debería skipearlo.  Heat_of_reaction
        # ya se setea via solve_equilibrium_reactors() y el balance
        # del flowsheet downstream lo recoge.
        if getattr(b, "reactions", None):
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

        # Despacho según reactor_mode (Capas 4 vs 5):
        mode = getattr(b, "reactor_mode", "equilibrium") or "equilibrium"
        if mode == "equilibrium":
            res = _rdb.solve_equilibrium_reactor_from_composition(
                rxn_ids=b.reactions,
                inlet_composition=agg,
                inlet_mass_kg_s=m_in_kg_s,
                T_K=T_K, P_bar=b.P_op_bar)
        elif mode in ("pfr", "cstr"):
            V_L = getattr(b, "reactor_volume_L", 0.0) or 0.0
            if V_L <= 0:
                msgs.append(f"✗ Reactor {b.name} ({mode}): falta declarar "
                             f"reactor_volume_L > 0.")
                continue
            res = _rdb.solve_kinetic_reactor_from_composition(
                mode=mode,
                rxn_ids=b.reactions,
                inlet_composition=agg,
                inlet_mass_kg_s=m_in_kg_s,
                T_K=T_K, P_bar=b.P_op_bar,
                V_reactor_L=V_L)
        else:
            msgs.append(f"✗ Reactor {b.name}: modo desconocido '{mode}'.")
            continue
        if res is None:
            msgs.append(f"✗ Reactor {b.name} ({mode}): no convergió "
                         f"(rxns={b.reactions}, T={T_K:.0f}K, "
                         f"P={b.P_op_bar}bar).")
            continue

        # Aplicar resultados a los outlets.  En reactores de equilibrio
        # Capa 4 la composición de salida ESTÁ DETERMINADA por la termo
        # — sobreescribimos siempre, ignorando composition_locked.
        # (composition_locked en outputs de reactor pierde sentido: si
        # el user quiere otra composición, debe vaciar block.reactions
        # y declarar todo manual.)
        # Excepción: outlets con role=='product' que ya tengan composition
        # explícita la respetamos como hint estequiométrico DOWNSTREAM
        # (e.g. para un KO drum cuya separación es declarada por el user).
        out_comp = res['outlet_composition']
        for s_out in outs:
            if s_out.role == "product" and s_out.composition:
                continue   # respetamos override en outputs declarados
            s_out.composition = dict(out_comp)
            if out_comp:
                s_out.main_component = max(out_comp, key=out_comp.get)

        # heat_of_reaction se computa SIEMPRE desde el solver de
        # equilibrio (no hay flag de lock para este campo todavía;
        # el user que quiera override puede vaciar block.reactions
        # y declarar heat_of_reaction manual).  _reset_propagated_values
        # ya lo dejó en 0 al inicio del solve.
        b.heat_of_reaction = res['heat_of_reaction_kJ_per_kg']

        # ---- AUTO-DUTY: calor que el horno/jacket externo provee ----
        # Para mantener el reactor isothermal a T_op_K, el horno debe
        # aportar (o extraer):
        #   Q_externo = Q_sensible_in→T_op + Q_rxn
        # donde:
        #   Q_sensible = m·Cp̄·(T_op − T_in_avg)   [kW]
        #   Q_rxn      = res['duty_kW']            [kW, positivo = endo]
        #
        # Q > 0 → horno aporta calor (SMR endotérmico, cracking)
        # Q < 0 → jacket extrae calor (Haber exotérmico)
        #
        # Esto reemplaza el duty actual del bloque (si no está locked
        # por el user) para que aparezca en el cálculo de utilities.
        # T_out de los outlets se propaga a T_op_C — sin esto, el
        # solver de energía downstream calcula T's absurdas porque
        # no captura el T_op isothermal del reactor.
        from flowsheet_model import T_REF_C
        Q_rxn_kW = res['duty_kW']
        T_in_avg_K = (sum(s.temperature * s.mass_flow
                           for s in ins if s.mass_flow > 0)
                       / m_in_total + 273.15)
        # Cp ponderado del input (kJ/kg·K)
        cp_in_avg = 0.0
        m_with_cp = 0.0
        for s in ins:
            if s.mass_flow <= 0:
                continue
            cp = _resolve_cp(s)
            if cp is None:
                continue
            cp_in_avg += cp * s.mass_flow
            m_with_cp += s.mass_flow
        if m_with_cp > 0:
            cp_in_avg /= m_with_cp
        Q_sensible_kW = m_in_kg_s * cp_in_avg * (T_K - T_in_avg_K)

        Q_total_kW = Q_sensible_kW + Q_rxn_kW

        # Setear duty si no está locked por el user (sudoku).
        if not _is_duty_locked(b):
            b.duty = Q_total_kW
            # No lo lockeamos — es un valor calculado, el solver lo
            # recalcula en próximas iteraciones si las condiciones
            # cambian (T_in, composición input, etc).

        # Propagar T_op_C a los outlet streams no-lockeados, para que
        # el solver de energía downstream tenga T inicial coherente y
        # no calcule valores absurdos.
        T_op_C = T_K - 273.15
        for s_out in outs:
            if not _is_temp_locked(s_out):
                s_out.temperature = T_op_C

        msgs.append(f"✓ Reactor {b.name}: ΔH_rxn={Q_rxn_kW:+.2f} kW, "
                     f"Q_sens={Q_sensible_kW:+.2f} kW, "
                     f"Q_total={Q_total_kW:+.2f} kW, T_out={T_op_C:.0f}°C, "
                     f"ξ={res['xi']}")
    return msgs


def solve_columns(fs):
    """Para cada bloque tipo Tower con column_active=True, computa
    automáticamente las composiciones del distillate y el bottom usando
    FUG + Fenske-Hengstebeck (Capa 6 NRTL).

    El user declara solo: LK, HK, x_D_LK, x_B_LK, R_factor.
    El solver calcula y escribe:
      · x_D (composición multicomponente del distillate)
      · x_B (composición del bottom)
      · mass_flow de D y B (balance global)
      · block.duty (= Q_reb + Q_cond, total externo)
      · attribs informativos: column_N, column_R, column_N_feed

    Skipea si:
      · column_active = False
      · falta LK o HK
      · feed no tiene composición / mass_flow

    Devuelve lista de mensajes.
    """
    try:
        import distillation_fug as _fug
    except ImportError:
        return []
    msgs = []
    for b in fs.blocks.values():
        if not getattr(b, "column_active", False):
            continue
        LK = getattr(b, "column_LK", "")
        HK = getattr(b, "column_HK", "")
        if not LK or not HK or LK == HK:
            continue
        ins  = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        if not ins or len(outs) < 2:
            continue
        # Feed: el primer input con composición y mass_flow > 0
        feed = next((s for s in ins
                       if s.mass_flow > 0 and (s.composition or {})),
                      None)
        if feed is None or LK not in feed.composition or HK not in feed.composition:
            msgs.append(f"⚠ Column {b.name}: feed sin composición de "
                         f"{LK} y {HK}, skip.")
            continue

        # Identificar distillate vs bottom — por nombre del puerto o
        # por la composición declarada (más rica en LK → distillate).
        # Si los outputs no tienen composition declarada, usar port:
        #   src_port == 'vapor' o 'destilado' o 'tope' → distillate
        dist_stream = None
        bot_stream = None
        for s_out in outs:
            port = (s_out.src_port or "").lower()
            if any(k in port for k in ("vapor", "dest", "tope", "top",
                                          "shell_in", "cond_in")):
                dist_stream = s_out
            elif any(k in port for k in ("liq", "fondo", "bot", "reb",
                                            "liq_in")):
                bot_stream = s_out
        if dist_stream is None or bot_stream is None:
            # Fallback: si las composiciones declaradas tienen más LK,
            # ese es el distillate
            outs_with_comp = [s for s in outs if (s.composition or {}).get(LK, 0) > 0]
            if len(outs_with_comp) >= 2:
                outs_sorted = sorted(outs, key=lambda s: -((s.composition or {}).get(LK, 0)))
                dist_stream = outs_sorted[0]
                bot_stream = outs_sorted[1]
            else:
                # Heurística final: primer output = distillate, segundo = bottom
                dist_stream = outs[0]
                bot_stream = outs[1]

        # Llamar al diseño FUG completo (siempre, como reference)
        T_feed_K = feed.temperature + 273.15
        T_top_K  = dist_stream.temperature + 273.15 if dist_stream.temperature else T_feed_K - 10
        T_bot_K  = bot_stream.temperature + 273.15 if bot_stream.temperature else T_feed_K + 20
        try:
            res = _fug.design_column(
                feed_composition=feed.composition,
                F=feed.mass_flow,
                T_K=T_feed_K, P_bar=1.013,
                light_key=LK, heavy_key=HK,
                x_D_LK=b.column_x_D_LK,
                x_B_LK=b.column_x_B_LK,
                R_factor=b.column_R_factor,
                q=1.0, T_top_K=T_top_K, T_bot_K=T_bot_K)
        except Exception as e:
            msgs.append(f"✗ Column {b.name}: error {type(e).__name__}: {e}")
            continue
        if res is None or res.get("N") is None:
            msgs.append(f"✗ Column {b.name}: FUG no convergió")
            continue

        # Si el método es 'wanghenke', refinamos los resultados con
        # el solver riguroso multicomp.  FUG provee N y R como
        # estimación inicial; WH refina la distribución de no-keys
        # con balance MESH por etapa.
        method = getattr(b, "column_method", "fug")
        if method == "wanghenke":
            try:
                import distillation_wanghenke as _wh
                import thermo_db as _td_wh
                # Convertir mass → mol para WH (que trabaja en mol)
                comps = list(feed.composition.keys())
                z_mass = [feed.composition[c] for c in comps]
                mws = []
                for c in comps:
                    co = _td_wh.get(c)
                    mws.append(co.mw if co and co.mw > 0 else 1.0)
                z_mol = [zi / m for zi, m in zip(z_mass, mws)]
                z_sum = sum(z_mol)
                if z_sum > 0:
                    z_mol = [z / z_sum for z in z_mol]
                F_mol = sum(feed.mass_flow * zi / m * 1000 / (8760 * 3600)
                              for zi, m in zip(z_mass, mws))
                N_wh = b.column_N_stages or max(int(res["N"]) + 2, 10)
                fs_wh = max(2, N_wh // 2)
                wh_res = _wh.wang_henke(
                    comps=comps, feed_z=z_mol, F=F_mol,
                    T_feed_K=T_feed_K, P_bar=1.013,
                    N=N_wh, feed_stage=fs_wh,
                    D_over_F=res["D"] / res["F"],
                    R=res["R"], max_iter=20)
                if wh_res is not None and wh_res.get("converged"):
                    # Reemplazar res con composiciones WH
                    # Convertir x_top, x_bot de mol → mass
                    x_top_mol = wh_res["x_profile"][0]
                    x_bot_mol = wh_res["x_profile"][-1]
                    x_D_mass = {comps[i]: x_top_mol[i] * mws[i]
                                 for i in range(len(comps))}
                    s_d = sum(x_D_mass.values())
                    if s_d > 0:
                        x_D_mass = {k: v/s_d for k, v in x_D_mass.items()}
                    x_B_mass = {comps[i]: x_bot_mol[i] * mws[i]
                                 for i in range(len(comps))}
                    s_b = sum(x_B_mass.values())
                    if s_b > 0:
                        x_B_mass = {k: v/s_b for k, v in x_B_mass.items()}
                    res["x_D"] = x_D_mass
                    res["x_B"] = x_B_mass
                    res["_wanghenke"] = True
                    res["_wh_iterations"] = wh_res.get("iterations")
                    msgs.append(f"  Column {b.name}: WH refinó composiciones "
                                 f"({wh_res.get('iterations')} iter)")
            except Exception as e:
                msgs.append(f"⚠ Column {b.name}: WH falló ({e}), usa FUG")

        # Extender a multicomponente via Fenske-Hengstebeck si hay >2
        # componentes en el feed
        full_comp = feed.composition
        if len(full_comp) > 2:
            # Calcular α_i_to_HK para todos los componentes
            alphas = {}
            for comp in full_comp:
                if comp == HK:
                    alphas[comp] = 1.0
                else:
                    a = _fug.relative_volatility(comp, HK, full_comp,
                                                   T_feed_K, 1.013)
                    if a is not None:
                        alphas[comp] = a
                    else:
                        alphas[comp] = 1.0   # fallback si NRTL falta
            fh = _fug.fenske_hengstebeck(alphas, full_comp,
                                            res["N_min"], LK, HK,
                                            b.column_x_D_LK, b.column_x_B_LK)
            if fh is not None:
                x_D_full = fh["x_D"]
                x_B_full = fh["x_B"]
                D_F = fh["D_over_F"]
                B_F = fh["B_over_F"]
            else:
                # Fallback binario
                x_D_full = {LK: b.column_x_D_LK, HK: 1 - b.column_x_D_LK}
                x_B_full = {LK: b.column_x_B_LK, HK: 1 - b.column_x_B_LK}
                D_F = res["D"] / res["F"]
                B_F = res["B"] / res["F"]
        else:
            x_D_full = res["x_D"]
            x_B_full = res["x_B"]
            D_F = res["D"] / res["F"]
            B_F = res["B"] / res["F"]

        # Escribir composiciones de outputs (sobreescribe ya que es
        # auto-calculado por el solver — análogo a reactor)
        dist_stream.composition = dict(x_D_full)
        dist_stream.main_component = max(x_D_full, key=x_D_full.get)
        if not _is_mass_locked(dist_stream):
            dist_stream.mass_flow = feed.mass_flow * D_F

        bot_stream.composition = dict(x_B_full)
        bot_stream.main_component = max(x_B_full, key=x_B_full.get)
        if not _is_mass_locked(bot_stream):
            bot_stream.mass_flow = feed.mass_flow * B_F

        # Duty del bloque: Q_reb + Q_cond (Q_cond es negativo).  Para
        # columna adiabática, el "duty externo total" es Q_reb (el
        # condensador es un HX separado en el flowsheet típicamente).
        # Aquí asignamos Q_reb al bloque Tower (representa el calor
        # neto consumido).
        Q_total = (res.get("Q_reb_kW", 0) or 0)
        if not _is_duty_locked(b):
            b.duty = Q_total

        # Atributos informativos (no persistidos, runtime)
        b._column_N = res.get("N")
        b._column_R = res.get("R")
        b._column_N_feed = res.get("N_feed")
        b._column_alpha_avg = res.get("alpha_avg")

        msgs.append(
            f"✓ Column {b.name}: N={res['N']:.1f}, R={res['R']:.2f}, "
            f"Q_reb={Q_total:+.1f}kW, "
            f"D={feed.mass_flow*D_F:.0f} B={feed.mass_flow*B_F:.0f}"
        )
        if res.get("warnings"):
            for w in res["warnings"]:
                msgs.append(f"⚠ Column {b.name}: {w[:120]}")
    return msgs


def solve_flashes(fs):
    """Para cada bloque tipo Vessel con flash_active=True, computa
    automáticamente las composiciones de salida vapor/líquido usando
    flash isotérmico NRTL (Capa 6).

    El user declara solo: T_K, P_bar.
    El solver calcula:
      · V/F (fracción vapor)
      · x (líquido), y (vapor)
      · mass_flow distribuido según VLE
    """
    try:
        import nrtl as _nrtl
    except ImportError:
        return []
    msgs = []
    for b in fs.blocks.values():
        if not getattr(b, "flash_active", False):
            continue
        ins  = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        if not ins or len(outs) < 2:
            continue
        feed = next((s for s in ins
                       if s.mass_flow > 0 and (s.composition or {})), None)
        if feed is None:
            continue
        names = list(feed.composition.keys())
        if len(names) < 2:
            continue
        z = [feed.composition[c] for c in names]
        T_K = b.flash_T_K or (feed.temperature + 273.15)
        P_bar = b.flash_P_bar or 1.013
        try:
            res = _nrtl.flash_TP(names, z, T_K, P_bar)
        except Exception as e:
            msgs.append(f"✗ Flash {b.name}: {type(e).__name__}: {e}")
            continue
        if res is None:
            msgs.append(f"⚠ Flash {b.name}: NRTL no convergió "
                         f"(falta par binario?)")
            continue

        # Identificar vapor vs líquido por port o phase declarada
        vap_out = next((s for s in outs
                         if "vap" in (s.src_port or "").lower()
                         or s.phase in ("vapor", "gas")), None)
        liq_out = next((s for s in outs if s is not vap_out), None)
        if vap_out is None:
            vap_out, liq_out = outs[0], outs[1]
        # Convertir mass fractions → mass_flow
        V_frac = res["V_frac"]
        # Para masa: necesitamos MW para convertir mol→mass
        try:
            import thermo_db as _td
            mws = []
            for c in names:
                comp = _td.get(c)
                mws.append(comp.mw if comp and comp.mw > 0 else 1.0)
        except ImportError:
            mws = [1.0] * len(names)
        # Masas en cada fase (relativas a F mol totales = 1)
        L_mass = sum((1 - V_frac) * res["x"][i] * mws[i] for i in range(len(names)))
        V_mass = sum(V_frac * res["y"][i] * mws[i] for i in range(len(names)))
        total_mass = L_mass + V_mass
        if total_mass <= 0:
            continue
        L_frac_mass = L_mass / total_mass
        V_frac_mass = V_mass / total_mass

        # Composiciones de salida en mass fractions
        x_mass = {names[i]: ((1 - V_frac) * res["x"][i] * mws[i] / L_mass)
                   for i in range(len(names))} if L_mass > 0 else {}
        y_mass = {names[i]: (V_frac * res["y"][i] * mws[i] / V_mass)
                   for i in range(len(names))} if V_mass > 0 else {}

        if vap_out is not None:
            vap_out.composition = y_mass
            vap_out.main_component = max(y_mass, key=y_mass.get) if y_mass else ""
            vap_out.phase = "vapor"
            if not _is_mass_locked(vap_out):
                vap_out.mass_flow = feed.mass_flow * V_frac_mass
            if not _is_temp_locked(vap_out):
                vap_out.temperature = T_K - 273.15
        if liq_out is not None:
            liq_out.composition = x_mass
            liq_out.main_component = max(x_mass, key=x_mass.get) if x_mass else ""
            liq_out.phase = "liquid"
            if not _is_mass_locked(liq_out):
                liq_out.mass_flow = feed.mass_flow * L_frac_mass
            if not _is_temp_locked(liq_out):
                liq_out.temperature = T_K - 273.15

        msgs.append(
            f"✓ Flash {b.name}: V/F_mass={V_frac_mass:.3f}  T={T_K-273.15:.1f}°C  "
            f"P={P_bar:.2f}bar"
        )
    return msgs


def solve_pressure_propagation(fs):
    """Propaga presión P a través del flowsheet.

    Reglas:
      - Stream P locked (user spec): no se toca.
      - Bloque pasivo (mixer, splitter, vessel, tank, HX sin ΔP):
        P_out = P_in - ΔP_pipe_calc (Darcy-Weisbach del propio stream)
      - Bloque con delta_p_bar declarado:
        P_out = P_in + block.delta_p_bar - ΔP_pipe del output
      - Bomba/compresor (eq_type contiene 'pump' o 'compressor'):
        Si delta_p_bar > 0 declarado: usar directo.
        Si efficiency declarado y P_out spec (downstream): calcular
        delta_p y W_eléctrica = m·ΔP/(ρ·η).
      - Reactor con P_op_bar: la P de input se ajusta para que la
        de output coincida con P_op_bar.

    Para no romper flowsheets viejos, esta función es OPT-IN: solo
    se ejecuta si al menos UN bloque/stream tiene presión declarada
    (P != 1.013 default).
    """
    # Check si vale la pena correrla (algún spec de P)
    has_pressure_specs = False
    for s in fs.streams.values():
        if getattr(s, "pressure_locked", False):
            has_pressure_specs = True
            break
    for b in fs.blocks.values():
        if abs(getattr(b, "delta_p_bar", 0)) > 1e-6:
            has_pressure_specs = True
            break
    if not has_pressure_specs:
        return []

    try:
        import pressure_drop as _pd
    except ImportError:
        return []

    msgs = []
    # Pasada topológica simple: para cada stream con P resuelta,
    # propagar al destino vía su bloque.  Iterar hasta no haber cambios.
    for _ in range(20):
        changed = False
        for b in fs.blocks.values():
            ins  = [s for s in fs.streams.values() if s.dst == b.id]
            outs = [s for s in fs.streams.values() if s.src == b.id]
            if not ins or not outs:
                continue
            # P_in disponible?  Necesita TODOS los inputs con P resuelta
            ins_with_p = [s for s in ins if s.pressure_bar > 0]
            if len(ins_with_p) != len(ins):
                continue
            # P_in_min: si hay varios inlets, el output toma la menor
            # (asumimos que las P se igualan en el mixer)
            P_in_min = min(s.pressure_bar for s in ins)
            # ΔP del bloque
            dp_block = getattr(b, "delta_p_bar", 0.0)
            # Es bomba/compresor con η declarada y dp positivo? Sí → setear duty
            eq_lower = b.eq_type.lower()
            is_pump_or_compressor = ("pump" in eq_lower
                                      or "compressor" in eq_lower
                                      or "fan" in eq_lower
                                      or "bomba" in eq_lower)
            # Output P = P_in + dp_block - ΔP_pipe_calc del output
            for s_out in outs:
                if getattr(s_out, "pressure_locked", False):
                    continue
                # ΔP de la tubería del output (pérdida después del bloque)
                try:
                    dp_pipe = _pd.stream_pressure_drop(s_out)
                    dp_pipe_bar = dp_pipe["delta_P_bar"] if dp_pipe else 0.0
                except Exception:
                    dp_pipe_bar = 0.0
                P_out = P_in_min + dp_block - dp_pipe_bar
                if abs(P_out - s_out.pressure_bar) > 1e-4:
                    s_out.pressure_bar = max(P_out, 0.01)
                    changed = True

            # Para bombas/compresores con ΔP positivo declarado,
            # calcular duty eléctrico
            if is_pump_or_compressor and dp_block > 0 and not _is_duty_locked(b):
                # W_hyd [kW] = m_kg_s · ΔP_Pa / (ρ · η · 1000)
                from flowsheet_model import SEC_PER_YEAR, TM_TO_KG
                m_kg_s = sum(s.mass_flow for s in ins) * TM_TO_KG / SEC_PER_YEAR
                # ρ: usa el primer inlet con composition
                rho = None
                for s_in in ins:
                    if s_in.composition or s_in.main_component:
                        try:
                            comp = s_in.composition or {s_in.main_component: 1.0}
                            rho = _pd._density_kg_m3(comp, s_in.temperature + 273.15,
                                                       s_in.phase or "liquid")
                            if rho: break
                        except Exception:
                            pass
                if rho and rho > 0:
                    eta = getattr(b, "efficiency", 0.75) or 0.75
                    W_elec_kW = m_kg_s * dp_block * 1e5 / (rho * eta * 1000.0)
                    b.duty = W_elec_kW
                    changed = True

        if not changed:
            break
    return msgs


def solve_splitters(fs):
    """Para cada bloque con splitter_active=True, distribuye el feed
    según splitter_fractions y propaga composición idéntica a todos
    los outputs (separación física, no termodinámica).

    Si splitter_fractions está vacío o no suma 1: split uniforme.
    """
    msgs = []
    for b in fs.blocks.values():
        if not getattr(b, "splitter_active", False):
            continue
        ins  = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        if not ins or len(outs) < 2:
            continue
        feed = next((s for s in ins if s.mass_flow > 0), None)
        if feed is None:
            continue
        # Fracciones: validar
        fracs = list(getattr(b, "splitter_fractions", []) or [])
        if len(fracs) != len(outs):
            # Uniform split como fallback
            fracs = [1.0 / len(outs)] * len(outs)
        total = sum(fracs)
        if total <= 0:
            continue
        fracs = [f / total for f in fracs]
        # Distribuir mass_flow y propagar composición
        for s_out, frac in zip(outs, fracs):
            if not _is_mass_locked(s_out):
                s_out.mass_flow = feed.mass_flow * frac
            if not _is_comp_locked(s_out):
                s_out.composition = dict(feed.composition or {})
                if feed.main_component:
                    s_out.main_component = feed.main_component
        msgs.append(f"✓ Splitter {b.name}: fracs={fracs}")
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
        # Skip columnas y flashes activos — sus outputs los escriben
        # solve_columns / solve_flashes con composiciones específicas
        # (no promedio ponderado).
        if getattr(b, "column_active", False):
            continue
        if getattr(b, "flash_active", False):
            continue
        if getattr(b, "splitter_active", False):
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

    # 4b. Propagar composiciones ANTES del reactor.  Sin esto, mixers
    #     o splits entre el feed y un reactor no llevan composición
    #     a los inlets del reactor → solve_equilibrium_reactors falla
    #     con 'inlets sin composition'.  Crítico para flowsheets con
    #     mixer-de-feeds o reciclos que pasan por mixers.
    auto_propagate_compositions(fs)

    # 4c. Reactores (Capas 4 y 5): resuelve composición + auto-duty.
    #     LOOP COMPOSICIONAL para flowsheets con reciclos donde el
    #     reactor está en un SCC.  Cada iteración:
    #       1) propagate composition (mixer aguas arriba del reactor)
    #       2) solve_equilibrium_reactors con composición actual
    #       3) propagate composition de los outlets (puede llegar al
    #          recycle via splitter)
    #     Convergencia: composición de los streams del SCC no cambia
    #     más allá de tol.  Para flowsheets sin reciclo o sin reactor
    #     en SCC, converge en 1 iteración.
    reactor_in_scc = any(
        getattr(fs.blocks[bid], "reactions", None)
        for scc in recycle_sccs for bid in scc
    )
    n_outer_iter = 30 if reactor_in_scc else 1
    rxn_msgs = []
    for outer in range(n_outer_iter):
        # Snapshot de composiciones actuales
        prev_comps = {sid: dict(s.composition or {})
                       for sid, s in fs.streams.items()}
        rxn_msgs = solve_equilibrium_reactors(fs)
        # Propagar composición a los downstream del reactor (split
        # gases → recycle, etc.)
        auto_propagate_compositions(fs)
        # Re-propagar masa por si la composición cambió y eso afecta
        # algún balance (no debería en mass-balance puro, pero por
        # seguridad)
        for _ in range(3):
            if not _solve_mass_iteration(fs):
                break
        # Resolver Wegstein de nuevo si el recycle cambió (composición
        # alteró el flujo del reactor → tear cambia)
        if reactor_in_scc:
            for scc in recycle_sccs:
                scc_streams = _streams_in_scc(scc, fs)
                if not all(s.mass_flow > 0 for s in scc_streams):
                    _solve_recycle_wegstein(fs, scc, max_iter=10)
        # Check convergencia: compare composiciones
        if outer > 0:
            max_diff = 0.0
            for sid, prev in prev_comps.items():
                curr = fs.streams[sid].composition or {}
                all_keys = set(prev) | set(curr)
                for k in all_keys:
                    diff = abs(curr.get(k, 0.0) - prev.get(k, 0.0))
                    if diff > max_diff:
                        max_diff = diff
            if max_diff < 1e-4:
                break
    for m in rxn_msgs:
        if m.startswith("✗") or m.startswith("⚠"):
            result.energy_balance_errors.append(m)

    # 4cb. Unit ops automáticos (splitters, flashes, columnas) — loop
    #      topológico para que cada unit op tenga su feed resuelto
    #      cuando se ejecuta.  Repetimos hasta no haber cambios.
    flash_msgs = []
    col_msgs = []
    split_msgs = []
    for outer in range(5):
        prev_count = sum(1 for s in fs.streams.values() if s.composition)
        # Splitters: distribuyen mass, propagan composición igual
        split_msgs = solve_splitters(fs)
        for _ in range(3):
            if not _solve_mass_iteration(fs):
                break
        # Flash drums (separación VLE)
        flash_msgs = solve_flashes(fs)
        for _ in range(3):
            if not _solve_mass_iteration(fs):
                break
        auto_propagate_compositions(fs)
        # Columnas (separación FUG)
        col_msgs = solve_columns(fs)
        for _ in range(3):
            if not _solve_mass_iteration(fs):
                break
        auto_propagate_compositions(fs)
        new_count = sum(1 for s in fs.streams.values() if s.composition)
        if new_count == prev_count:
            break

    for m in split_msgs + flash_msgs + col_msgs:
        if m.startswith("✗"):
            result.energy_balance_errors.append(m)
        elif m.startswith("⚠"):
            result.energy_warnings.append(m)

    # 4d. Auto-inferir duties de HX/equipos sin duty declarado, ahora
    #     que el reactor escribió T_out y composition.  only_zero=True
    #     respeta los duties que el user ya seteó.  Esto cierra el
    #     balance de los coolers/heaters downstream del reactor que
    #     antes no podían calcularse porque les faltaba T del input.
    auto_set_duties_from_thermo(fs, only_zero=True, respect_locks=True)

    # 4e. Propagación de presión (Darcy-Weisbach + ΔP de equipos).
    #     OPT-IN: solo se ejecuta si hay specs de P (P locked o
    #     algún block con delta_p_bar != 0).  Para bombas/compresores
    #     calcula además duty eléctrico desde W_hyd / η.
    p_msgs = solve_pressure_propagation(fs)
    for m in p_msgs:
        if m.startswith("✗"):
            result.energy_balance_errors.append(m)
        elif m.startswith("⚠"):
            result.energy_warnings.append(m)

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
        # Set de bloques que son reactores Capa 4/5 con T_op fija — sus
        # downstream tienen balance de energía menos confiable porque el
        # Cp simple no capta ΔH_rxn correctamente con T isothermal.
        rxn_block_names = {b.name for b in fs.blocks.values()
                            if getattr(b, "reactions", None)}
        # Construir set de bloques que están downstream de reactor
        # (BFS desde reactores siguiendo streams).
        downstream_of_rxn = set(rxn_block_names)
        changed = True
        while changed:
            changed = False
            for s in fs.streams.values():
                src_b = fs.blocks.get(s.src)
                dst_b = fs.blocks.get(s.dst)
                if src_b is None or dst_b is None:
                    continue
                if src_b.name in downstream_of_rxn and dst_b.name not in downstream_of_rxn:
                    downstream_of_rxn.add(dst_b.name)
                    changed = True

        seen = set()
        for msg in skipped_temp:
            if msg in seen:
                continue
            seen.add(msg)
            # Extraer nombre del bloque del mensaje (formato 'B-NAME → ...')
            block_name = msg.split("→")[0].strip() if "→" in msg else ""
            # Reglas de categorización:
            # - "T calc... pero T declarada..." → siempre WARNING
            #   (informativo: cambio de fase o ΔH no modelado).
            # - "fuera de rango físico" → ERROR, EXCEPTO si el bloque
            #   está downstream de un reactor con reactions != [], en
            #   cuyo caso el Cp simple no puede capturar T_op del reactor
            #   y el "fuera de rango" es consecuencia esperada.
            if "fuera de rango físico" in msg:
                if block_name in downstream_of_rxn:
                    result.energy_warnings.append(msg)
                else:
                    result.energy_balance_errors.append(msg)
            else:
                result.energy_warnings.append(msg)

    # 4. Validación + listado de unresolved
    #    Streams con endpoint flotante (src=-1 o dst=-1) se skipean —
    #    son borradores no conectados, no entran en ningún balance ni
    #    se reportan como problema.
    for s in fs.streams.values():
        if s.src not in fs.blocks or s.dst not in fs.blocks:
            continue
        if s.mass_flow <= 0:
            result.unresolved_streams.append(s.name)
    result.mass_balance_errors    = _check_mass_balance(fs)
    result.component_warnings     = _check_component_balance(fs)
    # energy balance errors quedan deshabilitados (no comparables al Cp
    # simple — comentado en _check_energy_balance del editor)

    result.success = (
        not result.unresolved_streams and
        not result.mass_balance_errors
    )

    # 5. Calcular estados visuales (color UI: verde/azul/amarillo/rojo)
    _compute_status_per_item(fs, result)
    return result


def _compute_status_per_item(fs, result):
    """Asigna a cada bloque y stream un status según el resultado del
    solver.  Lo escribe en `result.block_status` y `result.stream_status`
    para que la UI lo consulte y coloree.

    Reglas streams:
      'error'   = listado en unresolved_streams (mass_flow=0 después
                  del solve) o el bloque destino tiene mass error.
      'warning' = pertenece a un bloque listado en energy_warnings.
      'ok'      = mass_flow > 0 y sin issues.
      'unrun'   = mass_flow = 0 sin estar en unresolved (raro;
                  típicamente streams sin src/dst conectados).

    Reglas bloques:
      'error'   = aparece en mass_balance_errors o energy_balance_errors.
      'warning' = aparece en energy_warnings o tiene reciclo no convergido.
      'ok'      = todos sus streams tienen mass_flow > 0 y sin errors.
      'unrun'   = no tiene streams in y out (orfanato).
    """
    # Set rápido de nombres con error
    err_block_names: set = set()
    for msg in result.mass_balance_errors:
        # mensaje formato: "B-NAME: ent=X sal=Y Δ=Z (W%)"
        name = msg.split(":", 1)[0].strip()
        err_block_names.add(name)
    for msg in result.energy_balance_errors:
        # mensaje formato: "B-NAME → S-name: T calc..."
        name = msg.split("→")[0].strip() if "→" in msg else msg.split(":")[0].strip()
        err_block_names.add(name)

    warn_block_names: set = set()
    for msg in result.energy_warnings:
        name = msg.split("→")[0].strip() if "→" in msg else msg.split(":")[0].strip()
        warn_block_names.add(name)
    for rs in result.recycle_solutions:
        if not rs.converged:
            for bname in rs.cycle_blocks:
                warn_block_names.add(bname)

    unresolved_set = set(result.unresolved_streams)

    # Streams primero
    for s in fs.streams.values():
        if s.name in unresolved_set or s.mass_flow <= 0:
            # ¿Realmente unresolved (orfanato) o solo no procesado?
            has_src = s.src in fs.blocks
            has_dst = s.dst in fs.blocks
            if not (has_src and has_dst):
                result.stream_status[s.id] = "unrun"
            else:
                result.stream_status[s.id] = "error"
            continue
        # Mass_flow > 0.  Verificar status del bloque destino.
        dst_block = fs.blocks.get(s.dst)
        if dst_block:
            if dst_block.name in err_block_names:
                result.stream_status[s.id] = "error"
                continue
            if dst_block.name in warn_block_names:
                result.stream_status[s.id] = "warning"
                continue
        result.stream_status[s.id] = "ok"

    # Bloques
    for b in fs.blocks.values():
        ins  = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        if not ins and not outs:
            result.block_status[b.id] = "unrun"
            continue
        if b.name in err_block_names:
            result.block_status[b.id] = "error"
            continue
        # Si algún stream conectado tiene error, el bloque también
        if any(result.stream_status.get(s.id) == "error"
               for s in ins + outs):
            result.block_status[b.id] = "error"
            continue
        if b.name in warn_block_names:
            result.block_status[b.id] = "warning"
            continue
        result.block_status[b.id] = "ok"

    # Estado global
    if not fs.blocks:
        result.overall_status = "empty"
    elif result.mass_balance_errors or result.unresolved_streams \
            or result.energy_balance_errors:
        result.overall_status = "error"
    elif result.energy_warnings or any(not rs.converged
                                        for rs in result.recycle_solutions):
        result.overall_status = "warning"
    else:
        result.overall_status = "ok"
