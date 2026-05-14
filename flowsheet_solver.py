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


# ======================================================
# RESULTADO
# ======================================================

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
            lines.append("  Para resolver reciclos, declarar manualmente al menos")
            lines.append("  un stream del ciclo (tear stream).")

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

def _stream_enthalpy_kW(s):
    """Entalpía sensible de una corriente, kW."""
    if s.cp <= 0 or s.mass_flow <= 0:
        return None
    m_kg_s = (s.mass_flow * TM_TO_KG) / SEC_PER_YEAR
    return m_kg_s * s.cp * (s.temperature - T_REF_C)


def _solve_energy_iteration(fs, tol_T=0.5):
    """Una pasada propagando T sobre los bloques.

    A diferencia del solver de masa, el de energía no usa "T_known":
    siempre RECALCULA la T del output a partir de los inputs + duty,
    porque la T es siempre derivable cuando se conocen masas, Cp e
    inputs.  Si la T calculada coincide con la actual (tol 0.5°C),
    no se reporta como propagada.

    Sólo procesa bloques cuyos inputs ya están "listos":
      - todos los inputs tienen Cp > 0 y mass_flow > 0
      - todos los outputs tienen Cp > 0 y mass_flow > 0
    """
    propagated = []
    for b in fs.blocks.values():
        ins  = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        if not ins or not outs:
            continue
        # tabla de prerrequisitos para procesar el bloque
        if not all(s.cp > 0 and s.mass_flow > 0 for s in ins + outs):
            continue

        duty = b.duty

        # Passthrough simple: 1 in - 1 out
        if len(ins) == 1 and len(outs) == 1:
            s_in, s_out = ins[0], outs[0]
            h_in        = _stream_enthalpy_kW(s_in) or 0.0
            m_out_kg_s  = (s_out.mass_flow * TM_TO_KG) / SEC_PER_YEAR
            denom = m_out_kg_s * s_out.cp
            if denom > 0:
                t_new = T_REF_C + (h_in + duty) / denom
                if abs(t_new - s_out.temperature) > tol_T:
                    s_out.temperature = t_new
                    propagated.append((s_out.name, t_new))
            continue

        # Mixer: N in - 1 out
        if len(outs) == 1:
            num = den = 0.0
            for s in ins:
                m_kg_s = (s.mass_flow * TM_TO_KG) / SEC_PER_YEAR
                num += m_kg_s * s.cp * (s.temperature - T_REF_C)
                den += m_kg_s * s.cp
            s_out = outs[0]
            m_out_kg_s = (s_out.mass_flow * TM_TO_KG) / SEC_PER_YEAR
            denom_out  = m_out_kg_s * s_out.cp
            if denom_out > 0:
                t_new = T_REF_C + (num + duty) / denom_out
                if abs(t_new - s_out.temperature) > tol_T:
                    s_out.temperature = t_new
                    propagated.append((s_out.name, t_new))
            continue

        # Splitter: 1 in - N out.  T_out_j = T_in (split adiabático)
        if len(ins) == 1:
            t_in = ins[0].temperature
            for s_out in outs:
                if abs(t_in - s_out.temperature) > tol_T:
                    s_out.temperature = t_in
                    propagated.append((s_out.name, t_in))
    return propagated


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

    # 1. Detectar ciclos (warning informativo; el solver puede manejar
    #    algunos vía closure si hay suficientes streams declarados)
    result.cycles_detected = _detect_cycles(fs)

    # 2. Solver de masa — propagación iterativa
    total_propagated_mass = []
    for it in range(max_iter):
        prop = _solve_mass_iteration(fs)
        total_propagated_mass.extend(prop)
        if not prop:
            break
    result.propagated_mass = total_propagated_mass
    result.iterations = it + 1

    # 3. Solver de energía — análogo
    total_propagated_temp = []
    for it_e in range(max_iter):
        prop_e = _solve_energy_iteration(fs)
        total_propagated_temp.extend(prop_e)
        if not prop_e:
            break
    result.propagated_temp = total_propagated_temp

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
