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

def _solve_mass_iteration(fs):
    """Una pasada sobre todos los bloques.  Devuelve lista de tuplas
    (stream_name, new_mass_flow) con lo que se propagó esta pasada."""
    propagated = []
    for b in fs.blocks.values():
        ins  = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        if not ins or not outs:
            continue  # source/sink — sin balance posible

        unknown_ins   = [s for s in ins  if s.mass_flow <= 0]
        unknown_outs  = [s for s in outs if s.mass_flow <= 0]

        if not unknown_ins and len(unknown_outs) == 1:
            # cierre por output desconocido
            sum_in        = sum(s.mass_flow for s in ins)
            sum_known_out = sum(s.mass_flow for s in outs if s.mass_flow > 0)
            deduced = sum_in - sum_known_out
            if deduced > 0:
                unknown_outs[0].mass_flow = deduced
                propagated.append((unknown_outs[0].name, deduced))

        elif not unknown_outs and len(unknown_ins) == 1:
            # cierre por input desconocido (poco común pero válido)
            sum_out       = sum(s.mass_flow for s in outs)
            sum_known_in  = sum(s.mass_flow for s in ins if s.mass_flow > 0)
            deduced = sum_out - sum_known_in
            if deduced > 0:
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
      1. Si s.composition tiene fracciones → Cp(T) ponderado de
         components.py.
      2. Si s.main_component está declarado → Cp(T) puro.
      3. Si s.cp > 0 (override manual) → constante.
      4. None (sin datos).
    """
    if T_eval is None:
        T_eval = s.temperature
    phase = s.phase or "liquid"   # default líquido si no declarado

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
    """ΔH_vap de un stream (kJ/kg).  None si no se puede calcular."""
    if s.delta_h_vap_override > 0:
        return s.delta_h_vap_override
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
        # T en rango razonable: si difiere significativamente de la
        # declarada, respetamos la declaración (puede haber cambio de
        # fase parcial que el Cp simple no represente).  Solo
        # propagamos si la T del stream era el default T_REF (=25)
        # y la calculada es distinta.
        diff = abs(t_new - s_out.temperature)
        if diff <= tol_T:
            return False  # ya coincide
        # Si la T actual es default T_REF (25) y la calculada da algo
        # diferente y razonable → propagar (el stream estaba sin T
        # declarada).  Si la T actual es != T_REF → la respeto
        # (declaración del user).
        if abs(s_out.temperature - T_REF_C) < 0.01:
            s_out.temperature = t_new
            propagated.append((s_out.name, t_new))
            return True
        # T declarada existe pero difiere de la calculada → solo info
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


def auto_set_duties_from_thermo(fs, only_zero=False):
    """Para cada bloque no-eléctrico, computa duty desde balance y lo
    asigna.  Si only_zero=True, sólo sobrescribe bloques con duty=0
    (respeta declaraciones del user).

    Devuelve dict {block_id: duty_kw} de los duties asignados.
    """
    assigned = {}
    for b in fs.blocks.values():
        if only_zero and b.duty != 0:
            continue
        d = infer_block_duty(fs, b)
        if d is None:
            continue
        b.duty = float(d)
        assigned[b.id] = float(d)
    return assigned


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

    # 5. Solver de energía
    total_propagated_temp = []
    skipped_temp = []
    for it_e in range(max_iter):
        prop_e = _solve_energy_iteration(fs, skipped=skipped_temp)
        total_propagated_temp.extend(prop_e)
        if not prop_e:
            break
    result.propagated_temp = total_propagated_temp
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
