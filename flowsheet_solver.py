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

  COMPRESORES / TURBINAS / FANS (gas compresible):
    Estos NO usan el balance sensible de arriba — propagan T_out vía
    relación isentrópica de gas ideal (Cengel cap 7-9), en
    _propagate_T_compressor_isentropic:
        T_out_isen = T_in · (P_out/P_in)^((k−1)/k)
        T_out_real = T_in + (T_out_isen − T_in) / η   (compresor)
        T_out_real = T_in − η·(T_in − T_out_isen)     (turbina)
    con k=Cp/Cv y MW de la composición (_compressible_props, usa Cp(T)
    real de thermo_db — más preciso que el cold-air-standard de k=1.4
    constante).  Convención: P_out>P_in → compresor (duty>0); P_out<P_in
    → turbina/expansor (duty<0).  El compresor delega a
    equipment_design.compressor_sizing (single source of truth con el
    sizing).  Habilita ciclos Brayton, recompresión de gas caliente y
    expansores.  Bombas siguen con T_out ≈ T_in (líquido incompresible).
    Requiere que la presión esté resuelta ANTES (solve_pressure_hydraulic
    corre antes que _solve_energy_iteration en solve()).

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
from typing import Any, Dict, List, Optional, Tuple


# ======================================================
# CONSTANTES — importadas de flowsheet_model (única fuente)
# ======================================================
# Antes T_REF_C / SEC_PER_YEAR / TM_TO_KG estaban duplicadas
# en flowsheet_model.py, flowsheet_solver.py, equipment_design.py
# y equipment_ports.py.  Si una se editaba, las otras quedaban
# desactualizadas y los balances + sizing usaban factores distintos
# silenciosamente.  Ahora todas importan de flowsheet_model.
# (Instrucciones §6.3)
from flowsheet_model import T_REF_C, SEC_PER_YEAR, TM_TO_KG  # noqa: E402

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
    # Auditoría de consistencia unificada (Frente A): phase, balance por
    # componente, pseudo-componentes y locks redundantes.  audit_report
    # tiene el detalle estructurado; las listas planas son para compat UI.
    audit_report:        Optional['AuditReport'] = None
    consistency_warnings: List[str]         = field(default_factory=list)
    consistency_errors:   List[str]         = field(default_factory=list)
    # Warnings de auditoría térmica de HX (cruces imposibles, approach
    # mínimo violado, F<0.75, cross-exchange que no cierra energía).
    # No degradan success — son advisory de diseño.
    hx_warnings:         List[str]          = field(default_factory=list)
    # Conciencia física del solver (PR-A): warnings advisory tagged
    # [W-...] que EXPONEN inconsistencias físicas latentes sin corregir
    # ningún balance — cierre de energía por bloque, T de descarga de
    # compresor, T declarada pisada, duty espurio en equipo pasivo,
    # reactor estructural placeholder, flujo lockeado vs fracción de
    # splitter, duty>S, signo de duty.  Canal SEPARADO de energy_warnings
    # a propósito: NO alteran overall_status (un warning no debe cambiar
    # el estado golden — invariante de regresión), pero SÍ se renderizan
    # en solver_report para que el usuario los vea.  Cada línea lleva un
    # tag estable para grepear en tests.
    awareness_warnings:  List[str]          = field(default_factory=list)
    # Diagnósticos de diseño térmico por HX (block_id → dict con U_used,
    # dTlm, F, cross_check, warnings).  Lo puebla solve() corriendo
    # size_heat_exchanger sobre cada HX (respeta S_locked: computa los
    # diagnostics aunque no re-dimensione).
    hx_diagnostics:     Dict[int, dict]     = field(default_factory=dict)
    cycles_detected:    List[List[str]]     = field(default_factory=list)
    recycle_solutions:  List[RecycleSolution] = field(default_factory=list)
    # Lazos de circulación de servicio (bomba→header→HX, 100% aristas
    # auto_aux) exentos del tearing Wegstein: su caudal es analítico
    # (m = Q/(cp·ΔT) desde el duty, via size_utility_streams).  Líneas
    # informativas ya formateadas para summary()/UI.
    service_loops:      List[str]           = field(default_factory=list)

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

        if self.service_loops:
            lines.append("")
            for sl in self.service_loops:
                lines.append(sl)

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

        if self.hx_warnings:
            lines.append(f"\nWarnings de intercambiadores "
                          f"({len(self.hx_warnings)}):")
            for w in self.hx_warnings:
                lines.append(f"  · {w}")

        if self.awareness_warnings:
            lines.append(f"\nConciencia física del solver "
                          f"({len(self.awareness_warnings)}):")
            for w in self.awareness_warnings:
                lines.append(f"  · {w}")

        if self.audit_report:
            r = self.audit_report
            if r.n_errors or r.n_warnings:
                lines.append(f"\nAuditoría de consistencia "
                             f"({r.n_errors} errores, {r.n_warnings} warnings, "
                             f"{r.n_infos} infos):")
                for cat in ('phase', 'component_balance', 'pseudo',
                            'redundant_lock'):
                    relevant = [f for f in r.by_category(cat)
                                if f.severity in ('warning', 'error')]
                    if relevant:
                        lines.append(f"  · {cat}: {len(relevant)} hallazgo(s)")
                        for f in relevant[:5]:
                            lines.append(f"      {f.message[:120]}")

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


def _is_pressure_locked(s):
    """True solo si user fijó presión (lock explícito)."""
    return getattr(s, "pressure_locked", False)


def _is_phase_locked(s):
    """True solo si user/builder declaró phase explícita."""
    return getattr(s, "phase_locked", False)


def _mass_to_mol(mass_frac: Dict[str, float]) -> Dict[str, float]:
    """Convierte fracciones másicas → molares vía thermo_db (MW). Normaliza.
    Componentes sin MW resuelto usan MW=1.0 (degrada con gracia)."""
    try:
        import thermo_db as _td
    except ImportError:
        return {}
    mol: Dict[str, float] = {}
    for c, w in mass_frac.items():
        if w <= 0:
            continue
        co = _td.get(c)
        mw = co.mw if (co and co.mw > 0) else 1.0
        mol[c] = w / mw
    tot = sum(mol.values())
    if tot <= 0:
        return {}
    return {c: v / tot for c, v in mol.items()}


def _mol_to_mass(mol_frac: Dict[str, float]) -> Dict[str, float]:
    """Inverso de _mass_to_mol: fracciones molares → másicas. Normaliza."""
    try:
        import thermo_db as _td
    except ImportError:
        return {}
    mass: Dict[str, float] = {}
    for c, n in mol_frac.items():
        if n <= 0:
            continue
        co = _td.get(c)
        mw = co.mw if (co and co.mw > 0) else 1.0
        mass[c] = n * mw
    tot = sum(mass.values())
    if tot <= 0:
        return {}
    return {c: v / tot for c, v in mass.items()}


# Gases no-condensables a P/T típicas de columna: no condensan en un
# condensador total, así que se excluyen del cálculo de bubble point de
# los productos (su presencia traza hundiría la T a valores absurdos).
_NONCONDENSABLE_GASES = {
    "co2", "carbon dioxide", "hydrogen", "h2", "nitrogen", "n2",
    "oxygen", "o2", "methane", "ch4", "co", "carbon monoxide", "argon",
}


def _drop_noncondensables(mol_frac: Dict[str, float]) -> Dict[str, float]:
    """Quita gases no-condensables de una composición molar y renormaliza.
    Si todo era no-condensable, devuelve la composición original."""
    filt = {k: v for k, v in mol_frac.items()
            if k.lower() not in _NONCONDENSABLE_GASES}
    tot = sum(filt.values())
    if tot <= 0:
        return mol_frac
    return {k: v / tot for k, v in filt.items()}


def _boiling_point_K(comp: str, P_bar: float):
    """Tb de un componente puro a P_bar por bisección sobre Antoine
    (nrtl._Psat_bar es monótona creciente en T).  None si falta Antoine."""
    try:
        import nrtl as _nrtl
    except ImportError:
        return None
    lo, hi = 150.0, 800.0
    if _nrtl._Psat_bar(comp, lo) is None or _nrtl._Psat_bar(comp, hi) is None:
        return None
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        pm = _nrtl._Psat_bar(comp, mid)
        if pm is None:
            return None
        if pm < P_bar:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-3:
            break
    return 0.5 * (lo + hi)


def _infer_phase_from_TP(composition_mass: Dict[str, float],
                         T_K: float, P_bar: float) -> Tuple[str, float]:
    """Infiere (phase, vapor_fraction_másica) de una corriente desde su
    composición (mass frac), T y P usando NRTL + Antoine.

    phase ∈ {'liquid', 'vapor', 'two_phase'}.  vapor_fraction sólo es
    significativa si phase == 'two_phase'.  Si no se puede resolver
    (falta Antoine/NRTL) devuelve ('', 0.0) — el caller deja lo que había.
    NO toca el stream.
    """
    if not composition_mass or T_K <= 0 or P_bar <= 0:
        return ('', 0.0)
    x_mol = _mass_to_mol(composition_mass)
    if not x_mol:
        return ('', 0.0)
    try:
        import nrtl as _nrtl
        import thermo_db as _td
    except ImportError:
        return ('', 0.0)
    names = list(x_mol.keys())
    z = [x_mol[c] for c in names]

    # Single component (alguno domina con frac molar > 0.99)
    dominant = [c for c, v in x_mol.items() if v > 0.99]
    if len(names) == 1 or dominant:
        comp = dominant[0] if dominant else names[0]
        Tb = _boiling_point_K(comp, P_bar)
        if Tb is None:
            return ('', 0.0)
        if T_K < Tb - 0.5:
            return ('liquid', 0.0)
        if T_K > Tb + 0.5:
            return ('vapor', 1.0)
        return ('two_phase', 0.5)

    # Multicomponente: bubble/dew + flash si bifásico
    bp = _nrtl.bubble_point(names, z, P_bar)
    dp = _nrtl.dew_point(names, z, P_bar)
    if bp is None or dp is None:
        return ('', 0.0)
    T_bub, T_dew = bp[0], dp[0]
    if T_K < T_bub:
        return ('liquid', 0.0)
    if T_K > T_dew:
        return ('vapor', 1.0)
    fl = _nrtl.flash_TP(names, z, T_K, P_bar)
    if fl is None or fl.get("V_frac") is None:
        return ('two_phase', 0.5)
    V = fl["V_frac"]
    x_l, y_v = fl["x"], fl["y"]
    mws = []
    for c in names:
        co = _td.get(c)
        mws.append(co.mw if (co and co.mw > 0) else 1.0)
    L_mass = sum((1 - V) * x_l[i] * mws[i] for i in range(len(names)))
    V_mass = sum(V * y_v[i] * mws[i] for i in range(len(names)))
    tot = L_mass + V_mass
    if tot <= 0:
        return ('two_phase', 0.5)
    return ('two_phase', V_mass / tot)


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
        # [W-T-OVERRIDE] captura runtime (NO persistida) de la T que el
        # stream traía del JSON ANTES de que el solver la pise.  Se guarda
        # una sola vez (la primera corrida sobre el fs recién cargado), de
        # modo que re-solves idempotentes no la sobreescriban con la T ya
        # propagada.  La consume _compute_awareness_warnings.
        if not hasattr(s, "_t_declared"):
            try:
                s._t_declared = s.temperature
            except Exception:
                pass
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
        # Perfiles runtime de PFR/batch — siempre limpiar antes del
        # solve para que un reactor que ya no es PFR (o un solve viejo)
        # no muestre datos obsoletos en el panel de propiedades.
        b._pfr_profile = None
        b._batch_profile = None


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

        # Las corrientes de SERVICIO AUTO-GENERADAS (auto_aux con role
        # utility/ambient: agua de enfriamiento shell-side, aire de un
        # air-cooler) están en el lado OPUESTO al proceso de un HX y NO se
        # mezclan con él: forman su propio balance (in=out) y se dimensionan
        # desde el duty (size_utility_streams / size_air_cooler_streams).
        # Excluirlas del balance de PROCESO para que no bloqueen la deducción
        # de la corriente de proceso cuando el servicio aún no tiene flujo (si
        # no, con 2 incógnitas —proc + servicio— el balance no cierra y toda
        # la cadena aguas abajo queda sin resolver).
        #
        # SOLO las auto_aux: una corriente role='utility' declarada por el
        # builder que en realidad es de proceso —p.ej. el vapor evaporado de
        # un evaporador, tagueado utility para no entrar al OPEX— SÍ debe
        # contar en el balance de masa.
        def _is_hx_service(s):
            return getattr(s, "auto_aux", False) and (s.role or "") in ("utility", "ambient")
        proc_ins  = [s for s in ins  if not _is_hx_service(s)]
        proc_outs = [s for s in outs if not _is_hx_service(s)]
        if not proc_ins or not proc_outs:
            continue          # bloque puramente de servicio (header CW, etc.)

        unknown_ins   = [s for s in proc_ins
                          if not _is_mass_locked(s) and s.mass_flow == 0]
        unknown_outs  = [s for s in proc_outs
                          if not _is_mass_locked(s) and s.mass_flow == 0]

        if not unknown_ins and len(unknown_outs) == 1:
            sum_in        = sum(s.mass_flow for s in proc_ins)
            sum_known_out = sum(s.mass_flow for s in proc_outs
                                 if s is not unknown_outs[0])
            deduced = sum_in - sum_known_out
            if deduced >= 0:    # permitir flujo cero (caso bypass cerrado)
                unknown_outs[0].mass_flow = deduced
                propagated.append((unknown_outs[0].name, deduced))

        elif not unknown_outs and len(unknown_ins) == 1:
            sum_out       = sum(s.mass_flow for s in proc_outs)
            sum_known_in  = sum(s.mass_flow for s in proc_ins
                                 if s is not unknown_ins[0])
            deduced = sum_out - sum_known_in
            if deduced >= 0:
                unknown_ins[0].mass_flow = deduced
                propagated.append((unknown_ins[0].name, deduced))
    return propagated


def _check_stream_roles(fs):
    """Devuelve warnings para streams con role inconsistente con su
    comportamiento físico.  Detecta los typos comunes que ensucian
    el análisis económico:

      · feed/product con composition=agua y precio bajo entrando a
        un loop cerrado → probablemente es utility recirculante,
        no Raw Material/Producto.
      · utility entrando al puerto PROCESO de un HX 4-port
        (cool_in/steam_in son los correctos para utility).
      · stream con price > 0 y role='internal' (se pierde en costing).
    """
    warnings = []
    UTILITY_PORTS = {"cool_in", "cool_out", "steam_in", "steam_out",
                       "shell_in", "shell_out"}

    for s in fs.streams.values():
        # Streams flotantes (src o dst sin conectar): no participan
        # del balance ni del check de roles.  Convención sentinel
        # src<=0 o dst<=0 (incluye -1 explícito y 0 legacy).
        if s.src <= 0 or s.dst <= 0:
            continue
        comp  = s.composition or {}
        is_water = (len(comp) <= 2
                     and comp.get("water", 0) >= 0.95)
        is_steam_like = (len(comp) <= 2 and comp.get("water", 0) >= 0.95
                          and (s.phase or "").lower() in ("vapor", "gas"))

        # Caso A: stream agua/vapor con role feed/product que va a un
        # tanque de servicios (TK-xxx con BFW/cond/CW/steam en el nombre)
        if s.role in ("feed", "product") and is_water:
            b_dst = fs.blocks.get(s.dst)
            b_src = fs.blocks.get(s.src)
            dst_name = (b_dst.name if b_dst else "").upper()
            src_name = (b_src.name if b_src else "").upper()
            looks_utility = any(
                k in dst_name + src_name
                for k in ("BFW", "COND", "CW", "STEAM", "BLOWDOWN",
                            "MAKEUP", "HEADER")
            )
            if looks_utility and not is_steam_like:
                warnings.append(
                    f"⚠ {s.name}: role='{s.role}' pero parece make-up "
                    f"de utility (agua pura, conectado a tanque de "
                    f"servicios).  Sugerencia: usar role='utility' "
                    f"para no inflar Raw Materials/Products en opex."
                )

        # Caso B: stream role='utility' entrando al PROCESO de un HX
        if s.role == "utility" and s.dst_port:
            dst_port = s.dst_port.lower()
            # heurística: si el puerto NO es cool_in/steam_in/shell_in,
            # probablemente está mal conectado al lado proceso
            is_util_port = any(k in dst_port for k in
                                ("cool_in", "steam_in", "shell_in",
                                 "entrada"))   # entrada de tanque OK
            b_dst = fs.blocks.get(s.dst)
            if b_dst and not is_util_port:
                eq_l = (b_dst.eq_type or "").lower()
                is_hx = any(k in eq_l for k in
                              ("exch", "heater", "cooler",
                               "fired heater", "evap"))
                if is_hx and dst_port not in ("alimentacion",):
                    warnings.append(
                        f"⚠ {s.name}: role='utility' pero entra por "
                        f"puerto '{s.dst_port}' del HX {b_dst.name}.  "
                        f"Los HX 4-port tienen puertos separados "
                        f"(cool_in/steam_in para utility); revisar "
                        f"para que no contamine composición del proceso."
                    )

        # Caso C: stream con price > 0 y role='internal' (no llega
        # ni a feeds ni a products en el costing)
        if (s.role == "internal" and s.price_usd_per_tm
                and abs(s.price_usd_per_tm) > 0.01):
            warnings.append(
                f"⚠ {s.name}: role='internal' pero price=${s.price_usd_per_tm}/tm.  "
                f"Los streams 'internal' se IGNORAN en el costing.  "
                f"Cambiar a role='feed' (compra) o 'product' (venta) "
                f"para que entre al opex."
            )

    return warnings


def _check_mass_balance(fs, tol_rel=MASS_TOL_REL):
    """Devuelve lista de mensajes para bloques cuyo balance TOTAL falla.
    El balance por componente se chequea aparte (auditor de consistencia,
    flowsheet_consistency_audit._audit_component_balance)."""
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


# NOTA: el viejo _check_component_balance fue REEMPLAZADO por el Detector 2
# del auditor unificado (flowsheet_consistency_audit._audit_component_balance).
# solve() lo invoca vía audit_flowsheet() y vuelca sus hallazgos a
# result.component_warnings (compat) y result.audit_report (estructurado).


def _check_heat_exchangers(fs):
    """Auditoría térmica de los intercambiadores: cruces imposibles,
    approach mínimo y factor F<0.75 en configuraciones multi-paso.

    Devuelve list[str] de WARNINGS (no errores — no rompe flujos legacy).
    Incluye también los warnings acumulados en fs._solver_warnings
    (ej. cross-exchange que no cierra energía).
    """
    import equipment_costs as _eq_mod
    try:
        import heat_exchanger_rigorous as hxr
    except ImportError:
        return list(getattr(fs, "_solver_warnings", []) or [])

    warnings_list = []
    for b in fs.blocks.values():
        spec = _eq_mod.EQUIPMENT_DATA.get(b.eq_type, {})
        if spec.get("categoria") != "Heat exchangers":
            continue
        ins  = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        if not ins or not outs:
            continue

        if is_cross_exchange(fs, b):
            # 4 T reales: verificar cruce + approach + F
            pairs = _pair_hx_streams(ins, outs)
            hot = next(((i, o) for i, o in pairs
                        if i.temperature > o.temperature), None)
            cold = next(((i, o) for i, o in pairs
                         if o.temperature > i.temperature), None)
            if hot is None or cold is None:
                continue
            T_hi, T_ho = hot[0].temperature, hot[1].temperature
            T_ci, T_co = cold[0].temperature, cold[1].temperature
            _, w = hxr.compute_lmtd_real(T_hi, T_ho, T_ci, T_co, "counter")
            if w:
                warnings_list.append(f"{b.name}: {w}")
            ap = hxr.check_approach(T_ho, T_ci)
            if ap:
                warnings_list.append(f"{b.name}: {ap}")
            dR = (T_co - T_ci)
            dP = (T_hi - T_ci)
            R = (T_hi - T_ho) / dR if abs(dR) > 1e-9 else 1.0
            P = (T_co - T_ci) / dP if abs(dP) > 1e-9 else 0.0
            _, wf = hxr.f_correction_factor(R, P)
            if wf:
                warnings_list.append(f"{b.name}: {wf}")

    # incorporar warnings acumulados durante el solve (dedupe)
    for w in (getattr(fs, "_solver_warnings", []) or []):
        if w not in warnings_list:
            warnings_list.append(w)
    return warnings_list


def size_aux_circulation_pumps(fs):
    """Para cada bomba auto_aux de un lazo cerrado (creada por
    equipment_auxiliaries con delta_p_bar fijo), computa
    ``duty = W_elec_kW`` desde m·ΔP/(ρ·η).

    Se llama DESPUÉS de ``size_utility_streams`` porque depende del
    mass_flow del lazo recién dimensionado.  El duty queda como kW
    eléctrica → ``compute_utilities_from_duties`` lo recoge automáticamente
    como consumo de la utility "electricity" y lo carga al OPEX.
    """
    try:
        import pressure_drop as _pd
    except ImportError:
        return []
    from flowsheet_model import SEC_PER_YEAR, TM_TO_KG
    msgs = []
    for b in fs.blocks.values():
        if not getattr(b, "auto_aux", False):
            continue
        eq_lower = (b.eq_type or "").lower()
        if "pump" not in eq_lower:
            continue
        if _is_duty_locked(b):
            continue
        dp_block = float(getattr(b, "delta_p_bar", 0.0) or 0.0)
        if dp_block <= 1e-6:
            continue
        ins = [s for s in fs.streams.values() if s.dst == b.id]
        if not ins:
            continue
        feed = ins[0]
        m_tm = float(feed.mass_flow or 0.0)
        if m_tm <= 0:
            b.duty = 0.0
            continue
        comp = feed.composition or {feed.main_component: 1.0}
        try:
            rho = _pd._density_kg_m3(comp, feed.temperature + 273.15,
                                       feed.phase or "liquid")
        except Exception:
            rho = None
        if not rho or rho <= 0:
            continue
        eta = float(getattr(b, "efficiency", 0.65) or 0.65)
        m_kg_s = m_tm * TM_TO_KG / SEC_PER_YEAR
        # W_shaft [kW] = m·ΔP/(ρ·η) — fórmula incompresible (líquidos).
        # Convertimos a eléctrica con η_motor 0.95 para que el OPEX use kW
        # consumidos del transformador, no kW al eje.
        W_shaft = m_kg_s * dp_block * 1e5 / (rho * eta * 1000.0)
        W_elec  = W_shaft / 0.95
        if abs(W_elec - (b.duty or 0.0)) > 1e-4:
            b.duty = float(W_elec)
            msgs.append(f"  {b.name}: lazo cerrado ṁ={m_tm:,.0f} tm/año, "
                        f"W_elec={W_elec:.3f} kW (head≈{dp_block * 1e5 / (rho * 9.81):.1f} m, η={eta:.2f})".replace(",", " "))
    return msgs


def size_utility_streams(fs):
    """Puebla el mass_flow de las corrientes de SERVICIO auto-generadas
    (auto_aux, role='utility') de los intercambiadores de calor desde su
    duty: ṁ_utility = utility_consumption(util_key, duty).

    equipment_auxiliaries.instantiate_auxiliaries() crea estas corrientes
    (cooling water / steam shell-side) al instanciar el HX pero las deja en
    mass_flow=0 ('se calcula desde el duty').  Acá se completa ese cálculo,
    materializando el flujo másico que transporta el calor de/hacia el HX.

    Sólo HX (categoría 'Heat exchangers'): un único loop de utility por
    bloque.  Hornos/calderas (fuel+aire+chimenea) necesitan estequiometría
    de combustión y quedan fuera de alcance.  Respeta mass_flow_locked.
    Devuelve lista de mensajes.
    """
    try:
        import equipment_ports as ep
        import equipment_costs as ec
    except ImportError:
        return []
    msgs = []
    for b in fs.blocks.values():
        if ec.EQUIPMENT_DATA.get(b.eq_type, {}).get("categoria") != "Heat exchangers":
            continue
        duty = float(getattr(b, "duty", 0.0) or 0.0)
        # Bloques auxiliares directamente conectados al HX (header SUP/RET,
        # bomba de circulación en lazo cerrado).  Expandimos el "aux" del
        # HX para incluir todos los streams del lazo (también el tramo
        # HDR→pump que no toca el HX) y así dimensionar el ciclo entero.
        aux_near = set()
        for s in fs.streams.values():
            if not (getattr(s, "auto_aux", False) and (s.role or "") == "utility"):
                continue
            if s.src == b.id and s.dst in fs.blocks \
                    and getattr(fs.blocks[s.dst], "auto_aux", False):
                aux_near.add(s.dst)
            elif s.dst == b.id and s.src in fs.blocks \
                    and getattr(fs.blocks[s.src], "auto_aux", False):
                aux_near.add(s.src)
        aux = [s for s in fs.streams.values()
               if getattr(s, "auto_aux", False) and (s.role or "") == "utility"
               and (s.src == b.id or s.dst == b.id
                    or s.src in aux_near or s.dst in aux_near)]
        if not aux:
            continue
        if abs(duty) < 1e-9:
            for s in aux:
                if not getattr(s, "mass_flow_locked", False):
                    s.mass_flow = 0.0
            continue
        # T promedio de las corrientes de PROCESO del bloque (para resolver
        # qué utility aplica: cooling water vs steam vs refrigerante)
        proc_T = [s.temperature for s in fs.streams.values()
                  if (s.src == b.id or s.dst == b.id)
                  and not getattr(s, "auto_aux", False)
                  and (s.role or "") not in ("utility", "ambient")]
        T_avg = sum(proc_T) / len(proc_T) if proc_T else 25.0
        try:
            util_key = ep.resolve_heat_source(b, T_avg)
        except Exception:
            util_key = None
        if not util_key:
            continue
        cons = ep.utility_consumption(util_key, duty)   # tm/año
        if cons is None or cons <= 0:
            continue
        # T de suministro/retorno desde el catálogo de utilities (para que
        # la corriente quede resuelta y muestre un estado térmico sensato).
        util = ep.UTILITIES.get(util_key, {})
        t_lo, t_hi = util.get("T_range", (None, None))
        utype = util.get("type", "")
        for s in aux:
            if not getattr(s, "mass_flow_locked", False):
                s.mass_flow = float(cons)
            if t_lo is not None and not getattr(s, "temperature_locked", False):
                # supply = sale del header / entra al HX; return = sale del HX
                # / entra al header.  Para tramos intermedios (HDR→pump) usar
                # tipo del bloque conectado: si proviene del header es supply.
                src_b = fs.blocks.get(s.src)
                dst_b = fs.blocks.get(s.dst)
                if s.dst == b.id:
                    is_supply = True
                elif s.src == b.id:
                    is_supply = False
                elif src_b is not None and src_b.eq_type == "Utility header":
                    is_supply = True
                elif dst_b is not None and dst_b.eq_type == "Utility header":
                    is_supply = False
                else:
                    is_supply = True
                if utype == "cooling":
                    s.temperature = float(t_lo if is_supply else min(t_lo + 15.0, t_hi or t_lo + 15.0))
                elif utype == "heating":
                    s.temperature = float((t_hi or t_lo) if is_supply else t_lo)
                else:
                    s.temperature = float(t_lo)
        msgs.append(f"  {b.name}: utility {util_key} ṁ={cons:,.0f} tm/año "
                    f"(de duty {duty:+.0f} kW)".replace(",", " "))
    return msgs


# Propiedades del aire ambiente para dimensionar el lado-aire de los
# air-coolers.  El aire es un baño atmosférico (role='ambient'): NO entra
# al OPEX como utility con precio, pero su corriente necesita un flujo
# másico real para (a) cerrar el balance del air-cooler y deducir la
# corriente de proceso de salida, y (b) mostrar un estado térmico sensato.
_CP_AIR_KJ_KGK = 1.005     # cp aire seco
_DT_AIR_C      = 15.0      # ΔT típico del aire a través del haz de un air-cooler


def size_air_cooler_streams(fs):
    """Puebla mass_flow + T de las corrientes de AMBIENTE (aire) de los
    air-coolers desde su duty:  ṁ_air = |Q| / (cp_air · ΔT_air).

    Las crea ``equipment_auxiliaries`` con role='ambient' y mass_flow=0
    ('se calcula desde el duty').  A diferencia de las utilities de lazo
    cerrado (cooling water shell-side), el aire es abierto y no tiene
    utility_key ni precio, por lo que ``size_utility_streams`` —que sólo
    procesa role='utility'— las ignora.  Esta función las completa.

    El intake queda a T ambiente y el venteo a T_ambiente + ΔT (el aire
    absorbe el calor cedido por el proceso).  Respeta los locks del user.
    Devuelve lista de mensajes.
    """
    from flowsheet_model import SEC_PER_YEAR
    msgs = []
    T_ambient = 25.0
    AIR_COOLERS = ("Heat exch. — air cooler", "Heat exch. — condenser air-cooled")
    for b in fs.blocks.values():
        if (b.eq_type or "") not in AIR_COOLERS:
            continue
        air = [s for s in fs.streams.values()
               if getattr(s, "auto_aux", False) and (s.role or "") == "ambient"
               and (s.src == b.id or s.dst == b.id)]
        if not air:
            continue
        duty = float(getattr(b, "duty", 0.0) or 0.0)
        if abs(duty) < 1e-9:
            for s in air:
                if not getattr(s, "mass_flow_locked", False):
                    s.mass_flow = 0.0
            continue
        # Q[kW] = ṁ[kg/s]·cp·ΔT  →  ṁ; luego kg/s → tm/año.
        m_kg_s = abs(duty) / (_CP_AIR_KJ_KGK * _DT_AIR_C)
        cons = m_kg_s * SEC_PER_YEAR / 1000.0          # tm/año
        for s in air:
            if not getattr(s, "mass_flow_locked", False):
                s.mass_flow = float(cons)
            if not getattr(s, "temperature_locked", False):
                # intake = entra al bloque (dst==b); venteo = sale (src==b)
                is_intake = (s.dst == b.id)
                s.temperature = float(T_ambient if is_intake
                                       else T_ambient + _DT_AIR_C)
        msgs.append(f"  {b.name}: aire ṁ={cons:,.0f} tm/año "
                    f"(de duty {duty:+.0f} kW, ΔT={_DT_AIR_C:.0f}°C)".replace(",", " "))
    return msgs


def _size_heat_exchangers(fs, result):
    """Corre size_heat_exchanger sobre cada HX y persiste los diagnósticos
    térmicos (U, ΔT_lm, F, warnings) en block._hx_diagnostics y en
    result.hx_diagnostics[block_id].

    Re-dimensiona block.S SÓLO si el bloque NO está S_locked (área fijada a
    mano).  Si está locked, igual computa y persiste los diagnostics para
    que la UI los muestre — sólo no toca S.
    """
    try:
        import equipment_sizing as _es
        import equipment_costs as _ec
    except ImportError:
        return
    for b in fs.blocks.values():
        spec = _ec.EQUIPMENT_DATA.get(b.eq_type, {})
        if spec.get("categoria") != "Heat exchangers":
            continue
        try:
            out = _es.size_heat_exchanger(b, fs)
        except Exception:
            continue
        if not isinstance(out, tuple):
            continue                      # contrato inesperado → skip
        A, diag = out
        b._hx_diagnostics = diag
        result.hx_diagnostics[b.id] = diag
        if A is None or A <= 0:
            continue
        if getattr(b, "S_locked", False):
            continue                      # área fijada por el user: no tocar
        S_min = spec.get("S_min", 0)
        S_max = spec.get("S_max", float("inf"))
        b.S = max(S_min, min(A, S_max))


# ======================================================
# SOLVER DE ENERGÍA — propagación de T por closure
# ======================================================

# ──────────────────────────────────────────────────────────────────────
# Entalpía de corriente — FUENTE ÚNICA en stream_enthalpy.py (PR-C).
#
# _resolve_cp / _resolve_dh_vap / _stream_enthalpy_kW eran la versión
# CANÓNICA (resolvía cp a T promedio, latente por fase, two_phase con
# vapor_fraction y fallbacks main_component / components.py / overrides).
# Se movieron tal cual a stream_enthalpy.py para que la UI (bubbles,
# inspector, flowsheet_qt) consuma EXACTAMENTE los mismos números que el
# solver — antes la copia de la UI caía a 0 silencioso en ~8/12 streams.
# Acá sólo se re-exportan con los nombres internos que usa el resto del
# solver; el cuerpo es idéntico al anterior (goldens byte-idénticos).
# ──────────────────────────────────────────────────────────────────────
from stream_enthalpy import (                                  # noqa: E402
    _resolve_cp,
    _resolve_dh_vap,
    stream_enthalpy_kW as _stream_enthalpy_kW,
)


def _compressible_props(comp: dict, T_K: float):
    """Devuelve (mw_avg [g/mol], k=Cp/Cv) para una composición de gas.

    MW: Kay's rule (regla aditiva por w_i).
    k: Cp/(Cp − R/MW) usando thermo_db.cp_mix_kJ_kg_K(phase='gas').
    R = 8.314 J/(mol·K).

    Fallback si thermo_db no resuelve Cp: k típicos por familia
    (CO2 1.28, vapor de agua 1.33, hidrocarburos livianos 1.30,
    diatómicos/aire 1.40)."""
    try:
        import thermo_db as _td
    except ImportError:
        return (28.96, 1.40)
    mw_avg = 0.0
    total_w = 0.0
    for c, w in comp.items():
        co = _td.get(c)
        if co is None or co.mw <= 0:
            continue
        mw_avg += w * co.mw
        total_w += w
    if total_w <= 0:
        return (28.96, 1.40)   # fallback aire
    mw_avg /= total_w

    T_C = T_K - 273.15
    try:
        cp_kJ_kg_K = _td.cp_mix_kJ_kg_K(comp, T_C, "gas")
    except Exception:
        cp_kJ_kg_K = None
    if cp_kJ_kg_K is None or cp_kJ_kg_K <= 0:
        # Fallback heurístico por composición dominante
        if comp.get("co2", 0) > 0.5 or comp.get("carbon dioxide", 0) > 0.5:
            k = 1.28
        elif comp.get("water", 0) > 0.5:
            k = 1.33
        elif (comp.get("methane", 0) + comp.get("ethane", 0)
              + comp.get("propane", 0)) > 0.5:
            k = 1.30
        else:
            k = 1.40   # aire / N2 / O2 / H2
        return (mw_avg, k)

    R_specific_kJ_kg_K = 8.314 / (mw_avg * 1e-3) / 1000.0
    cv = cp_kJ_kg_K - R_specific_kJ_kg_K
    if cv <= 0:
        return (mw_avg, 1.40)
    return (mw_avg, cp_kJ_kg_K / cv)


def _propagate_T_compressor_isentropic(b, fs, propagated=None, skipped=None,
                                        tol_T=0.5):
    """Propaga T_out de un compresor/fan/turbina vía relación isentrópica
    de gas ideal (Cengel cap 7-9).  Reemplaza el skip silencioso del
    solver de energía para equipos eléctricos compresibles.

    Convención del proyecto (no hay tipo 'Turbine' separado):
      · P_out > P_in → COMPRESOR (consume W, sube T, duty > 0)
      · P_out < P_in → TURBINA/EXPANSOR (genera W, baja T, duty < 0)

    Compresor: delega a equipment_design.compressor_sizing (single source
    of truth, mismo cálculo que el sizing/duty P12; η_isen clampeado a
    ≤0.95 ahí).  Turbina: expansión isentrópica manual (η sin clamp).

    NO aplica a bombas (líquido incompresible — T_out ≈ T_in).
    Respeta temperature_locked / pressure_locked / duty_locked y el rango
    físico [T_MIN, T_MAX]_REASONABLE.  Devuelve True si propagó algo."""
    if propagated is None: propagated = []
    if skipped is None: skipped = []
    ins  = [s for s in fs.streams.values() if s.dst == b.id]
    outs = [s for s in fs.streams.values() if s.src == b.id]
    if len(ins) != 1 or len(outs) != 1:
        return False
    feed, out = ins[0], outs[0]
    if feed.mass_flow <= 0 or feed.pressure_bar <= 0:
        return False
    comp = feed.composition or (
        {feed.main_component: 1.0} if feed.main_component else {})
    if not comp:
        return False

    P_in = feed.pressure_bar
    if getattr(out, "pressure_locked", False) and out.pressure_bar > 0:
        P_out = out.pressure_bar
    elif b.delta_p_bar != 0:
        P_out = P_in + b.delta_p_bar      # delta_p_bar negativo si turbina
    else:
        return False                       # falta info de P
    if P_out <= 0 or abs(P_out - P_in) < 1e-6:
        return False

    T_in_K = feed.temperature + 273.15
    from flowsheet_model import SEC_PER_YEAR, TM_TO_KG
    m_kg_s = feed.mass_flow * TM_TO_KG / SEC_PER_YEAR
    mw_avg, k = _compressible_props(comp, T_in_K)

    if P_out > P_in:
        # COMPRESOR — equipment_design (consistente con sizing/duty)
        try:
            from equipment_design import compressor_sizing
            res = compressor_sizing(
                m_kg_s=m_kg_s, P_in_bar=P_in, P_out_bar=P_out,
                T_in_K=T_in_K, mw_avg=mw_avg, k=k,
                eta_isen=b.efficiency or 0.75)
        except Exception:
            res = None
        if res is None:
            return False
        T_out_K = res["T_out_K"]
        W_elec_kW = res["W_act_kW"]        # POSITIVO (consume)
    else:
        # TURBINA / EXPANSOR — expansión isentrópica
        exponent = (k - 1.0) / k
        ratio = P_out / P_in
        T_out_isen = T_in_K * (ratio ** exponent)
        eta = b.efficiency or 0.85         # turbinas tienden a η más alta
        T_out_K = T_in_K - eta * (T_in_K - T_out_isen)
        T_avg_C = ((T_in_K + T_out_K) / 2.0) - 273.15
        try:
            import thermo_db as _td
            cp = _td.cp_mix_kJ_kg_K(comp, T_avg_C, "gas")
        except Exception:
            cp = None
        if cp is None or cp <= 0:
            R = 8.314
            cp = (R / (mw_avg * 1e-3)) * (k / (k - 1.0)) / 1000.0
        W_isen_kW = m_kg_s * cp * (T_in_K - T_out_isen)
        W_elec_kW = -(eta * W_isen_kW)     # NEGATIVO (genera)

    # ── Aplicar resultados (respetando locks + rango) ──
    t_new_C = T_out_K - 273.15
    if not (T_MIN_REASONABLE <= t_new_C <= T_MAX_REASONABLE):
        skipped.append(
            f"{b.name} → {out.name}: T isentrópica = {t_new_C:.0f} °C fuera "
            f"de rango físico [-100, 1500].  T mantenida en {out.temperature:g} °C."
        )
    elif not _is_temp_locked(out) and abs(t_new_C - out.temperature) > tol_T:
        out.temperature = t_new_C
        propagated.append((out.name, t_new_C))
    # P_out (si no locked)
    if not getattr(out, "pressure_locked", False) and abs(out.pressure_bar - P_out) > 1e-4:
        out.pressure_bar = max(P_out, 0.01)
    # duty (si no locked) — el solver puede re-iterarlo si P cambia upstream
    if not getattr(b, "duty_locked", False):
        b.duty = W_elec_kW
    return True


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
        # Equipos eléctricos (bombas, compresores, fans, turbinas).
        # Antes se skipeaban sin propagar T.  Ahora:
        #   · Compresor/Fan/Turbina → propagación isentrópica de gas
        #     ideal (T_out vía Cengel cap 7-9, ver
        #     _propagate_T_compressor_isentropic).  Habilita ciclos
        #     Brayton, recompresión de gas caliente, expansores.
        #   · Bomba → T_out ≈ T_in (líquido incompresible; ΔT por
        #     ineficiencia ~1-3 °C, despreciable a P < 100 bar).
        if _ep_mod.is_electrical_equipment(b.eq_type):
            eq_lower = b.eq_type.lower()
            if "compressor" in eq_lower or "fan" in eq_lower:
                _propagate_T_compressor_isentropic(
                    b, fs, propagated, skipped, tol_T)
            elif "pump" in eq_lower:
                if (not _is_temp_locked(outs[0])
                        and abs(ins[0].temperature - outs[0].temperature) > tol_T):
                    outs[0].temperature = ins[0].temperature
                    propagated.append((outs[0].name, ins[0].temperature))
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


def _hx_energy_closes(fs, b, ins, outs, tol=0.05):
    """Verifica que un candidato a cross-exchange cierre energía: el calor
    cedido por las corrientes que se enfrían ≈ el absorbido por las que se
    calientan, dentro de `tol` (5%).

    Returns:
        True  → cierra (recuperador real).
        False → no cierra (debe consumir utility).
        None  → no se pudo evaluar (faltan Cp/composición) → indeterminado;
                el caller conserva el resultado estructural.
    """
    pairs = _pair_hx_streams(ins, outs)
    q_hot = q_cold = 0.0
    for s_in, s_out in pairs:
        h_in  = _stream_enthalpy_kW(s_in)
        h_out = _stream_enthalpy_kW(s_out)
        if h_in is None or h_out is None:
            return None
        dq = h_in - h_out                 # >0: la línea se enfría (cede)
        if dq > 0:
            q_hot += dq
        else:
            q_cold += -dq
    if max(q_hot, q_cold) < 1e-6:
        return None
    if q_cold < 1e-6 or q_hot < 1e-6:
        return False                      # un solo sentido térmico → no recupera
    rel = abs(q_hot - q_cold) / max(q_hot, q_cold)
    return rel < tol


def _pair_hx_streams(ins, outs):
    """Empareja entradas con salidas por mass_flow más cercano."""
    pairs, used = [], set()
    for i in ins:
        best, bd = None, float("inf")
        for j, o in enumerate(outs):
            if j in used:
                continue
            d = abs((i.mass_flow or 0) - (o.mass_flow or 0))
            if d < bd:
                bd, best = d, j
        if best is not None:
            used.add(best)
            pairs.append((i, outs[best]))
    return pairs


def is_cross_exchange(fs, b):
    """Detecta heat exchangers proceso-proceso (cross-exchange).

    Un HX cross-exchange tiene ≥2 corrientes entrantes y ≥2 salientes:
    una corriente caliente que cede calor y una fría que lo recibe.
    No consume utility — sólo recupera calor entre corrientes.
    Casos típicos: feed/effluent HX en HDA, lean/rich HX en aminas.

    Además del chequeo estructural, valida TERMODINÁMICAMENTE que el calor
    cedido ≈ el recibido (cierre 5%).  Si no cierra, devuelve False y deja
    que el bloque consuma utility (con warning en fs._solver_warnings).
    Si no hay datos para evaluar (Cp/comp faltantes), conserva el resultado
    estructural para no romper flujos legacy.
    """
    import equipment_costs as _eq_mod
    spec = _eq_mod.EQUIPMENT_DATA.get(b.eq_type, {})
    if spec.get("categoria") != "Heat exchangers":
        return False
    ins  = [s for s in fs.streams.values() if s.dst == b.id]
    outs = [s for s in fs.streams.values() if s.src == b.id]
    if not (len(ins) >= 2 and len(outs) >= 2):
        return False

    closes = _hx_energy_closes(fs, b, ins, outs)
    if closes is False:
        _log_solver_warning(
            fs, f"{b.name}: cross-exchange no cierra energía (>5%) — "
                f"tratado como HX con utility de trim")
        return False
    return True


def _log_solver_warning(fs, msg):
    """Agrega un warning de solver a fs._solver_warnings (dedupe)."""
    wl = getattr(fs, "_solver_warnings", None)
    if wl is None:
        wl = []
        try:
            fs._solver_warnings = wl
        except Exception:
            return
    if msg not in wl:
        wl.append(msg)


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

    # Las corrientes de servicio auto-generadas (auto_aux) TRANSPORTAN el
    # duty; incluirlas en el balance lo vuelve circular (H_out−H_in≈0) y,
    # si están sin dimensionar (ṁ=0 / Cp irresoluble), fuerzan duty=0.
    # Se excluyen: el duty se infiere del lado de proceso.
    ins  = [s for s in fs.streams.values()
            if s.dst == b.id and not getattr(s, "auto_aux", False)]
    outs = [s for s in fs.streams.values()
            if s.src == b.id and not getattr(s, "auto_aux", False)]
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
        # Skipear reactores: su duty ya lo seteó solve_equilibrium_reactors
        # (sea Q externo de horno isothermal, o 0 de adiabático).
        # Sobreescribirlo aquí lleva a duties absurdos.
        if getattr(b, "reactions", None):
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
        # Hallazgo 1: aceptar b.reactions (IDs del catálogo) Y/O
        # b.custom_reactions (definidas por el user, in-memory).
        if not (getattr(b, "reactions", None)
                or getattr(b, "custom_reactions", None)):
            continue
        # Reactor estructural / placeholder: si NINGUNA de las reacciones
        # declaradas existe en el DB de Capa 4, asumimos que el user usó
        # IDs simbólicos para marcar el bloque como reactor (chemistry
        # via outputs locked) — saltamos la chemistry sin error.  El
        # block sigue siendo "reactor" para el component balance skip.
        known = [rid for rid in b.reactions if _rdb.get(rid) is not None]
        # Hallazgo 1: fusionar custom_reactions del bloque.  Las
        # registramos temporalmente en el cache de reactions_db con
        # IDs únicos para que solve_*_from_composition (que toma IDs)
        # las pueda resolver vía _rdb.get().  Después del solve las
        # desregistramos para no polucionar la DB global.
        custom_rxn_ids: List[str] = []
        try:
            _cache = _rdb._ensure_loaded()    # dict module-level
            for i, d in enumerate(getattr(b, "custom_reactions", []) or []):
                try:
                    rxn_obj = _rdb.reaction_from_dict(d)
                except (ValueError, KeyError) as _e:
                    msgs.append(f"⚠ Reactor {b.name}: custom_reactions[{i}] "
                                 f"inválida ({_e}), saltada.")
                    continue
                # ID único in-memory para evitar colisión con catálogo
                rid_uniq = f"_BLOCK{b.id}_CUSTOM{i}"
                rxn_obj.id = rid_uniq
                _cache[rid_uniq] = rxn_obj
                custom_rxn_ids.append(rid_uniq)
        except Exception as _e:
            msgs.append(f"⚠ Reactor {b.name}: error fusionando custom_reactions: {_e}")
        all_rxn_ids = known + custom_rxn_ids
        if not all_rxn_ids:
            continue
        # NOTA: usamos all_rxn_ids (fusión catalog + custom) en las
        # llamadas downstream a solve_*_from_composition.  NO mutamos
        # b.reactions para no contaminar el modelo persistido.
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
        T_in_avg_K = (sum(s.temperature * s.mass_flow
                            for s in ins if s.mass_flow > 0)
                       / m_in_total + 273.15)
        T_K = b.T_op_K if b.T_op_K > 0 else T_in_avg_K
        # mass_flow del flowsheet está en tm/año → kg/s
        from flowsheet_model import SEC_PER_YEAR, TM_TO_KG
        m_in_kg_s = m_in_total * TM_TO_KG / SEC_PER_YEAR

        # CAPA 7 — REACTOR ADIABÁTICO:
        # Si T_op_K = 0 (no isothermal) y el bloque tiene reactions,
        # el solver itera T y composición acopladas:
        #   T_out = T_in + (-Q_rxn) / (m·Cp_mix(T_avg))
        # con Q_rxn > 0 endo → enfría; Q_rxn < 0 exo → calienta.
        # En ese caso usamos T_in como T_op inicial y refinamos.
        is_adiabatic = (not b.T_op_K or b.T_op_K < 100)
        if is_adiabatic:
            # T inicial = T promedio del input
            T_K = T_in_avg_K
            # Iterar T ↔ composición hasta convergencia
            for adiab_it in range(8):
                # Llamar al solver con T actual
                mode = getattr(b, "reactor_mode", "equilibrium") or "equilibrium"
                try:
                    if mode == "equilibrium":
                        res_iter = _rdb.solve_equilibrium_reactor_from_composition(
                            rxn_ids=all_rxn_ids, inlet_composition=agg,
                            inlet_mass_kg_s=m_in_kg_s,
                            T_K=T_K, P_bar=b.P_op_bar)
                    elif mode in ("pfr", "cstr"):
                        V_L = getattr(b, "reactor_volume_L", 0.0) or 0.0
                        if V_L <= 0:
                            break
                        res_iter = _rdb.solve_kinetic_reactor_from_composition(
                            mode=mode, rxn_ids=all_rxn_ids,
                            inlet_composition=agg, inlet_mass_kg_s=m_in_kg_s,
                            T_K=T_K, P_bar=b.P_op_bar, V_reactor_L=V_L)
                    elif mode == "stoich":
                        res_iter = _rdb.solve_stoichiometric_reactor(
                            rxn_ids=all_rxn_ids, inlet_composition=agg,
                            inlet_mass_kg_s=m_in_kg_s, T_K=T_K,
                            P_bar=b.P_op_bar,
                            conversion=getattr(b, "reactor_conversion", 0.95))
                    else:
                        break
                except Exception:
                    res_iter = None
                if res_iter is None:
                    break
                # Cp promedio del input (kJ/kg·K).
                # Para reactores adiabáticos, el feed casi siempre es
                # gas (T > 100°C, presiones moderadas).  Forzamos
                # phase='gas' al consultar Cp para evitar valores
                # absurdos del Cp líquido extrapolado fuera de su rango.
                cp_avg = 0.0; mw = 0.0
                try:
                    import thermo_db as _td_cp
                    for s_in_ in ins:
                        if s_in_.mass_flow <= 0: continue
                        comp_in = s_in_.composition or (
                            {s_in_.main_component: 1.0}
                            if s_in_.main_component else {})
                        # Phase: 'gas' si T > 80°C o phase declarado
                        # contiene 'gas'/'vapor', sino respetar.
                        ph = (s_in_.phase or "").lower()
                        if "gas" in ph or "vap" in ph:
                            use_phase = "gas"
                        elif (s_in_.temperature + 273.15) > 353:
                            use_phase = "gas"   # > 80°C → asumir vapor
                        else:
                            use_phase = "liquid"
                        cp_i = _td_cp.cp_mix_kJ_kg_K(comp_in,
                                                        T_K - 273.15,
                                                        use_phase)
                        if cp_i is None or cp_i <= 0 or cp_i > 50:
                            # Fallback agua vapor / aire
                            cp_i = 2.0 if use_phase == "gas" else 4.18
                        cp_avg += cp_i * s_in_.mass_flow
                        mw += s_in_.mass_flow
                except ImportError:
                    pass
                if mw > 0:
                    cp_avg /= mw
                else:
                    cp_avg = 2.0    # fallback ~ vapor genérico
                # Q_rxn [kW] = res_iter['duty_kW'] (positivo endo)
                Q_rxn_kW = res_iter.get('duty_kW', 0.0) or 0.0
                # Adiabatic: T_out = T_in + (-Q_rxn)/(m·Cp)
                # Q_rxn > 0 (endo): T baja → -Q_rxn negativo → ΔT<0
                # Q_rxn < 0 (exo): T sube → -Q_rxn positivo → ΔT>0
                delta_T = -Q_rxn_kW / (m_in_kg_s * cp_avg)
                T_new = T_in_avg_K + delta_T
                # Cap T en rango físico
                T_new = max(min(T_new, 2500.0), 100.0)
                if abs(T_new - T_K) < 2.0:
                    T_K = T_new
                    break
                # Damping para estabilidad (50% del paso)
                T_K = 0.5 * (T_K + T_new)
            # Usar el res_iter de la última iter como res
            res = res_iter if 'res_iter' in dir() else None
            if res is None:
                msgs.append(f"✗ Reactor adiabático {b.name}: no convergió T")
                continue
            # Marcar que el reactor es adiabático: duty externo = 0
            b._adiabatic_T_final_K = T_K
        else:
            # Comportamiento isothermal (T_op_K declarado): igual que antes
            T_K = b.T_op_K

        # Despacho según reactor_mode (Capas 4 vs 5):
        mode = getattr(b, "reactor_mode", "equilibrium") or "equilibrium"
        # Hallazgo 1 (nota de scope): si el user eligió pfr/cstr pero
        # alguna reacción NO tiene cinética Arrhenius (custom o R022-R025
        # NO derivadas), degradar a 'equilibrium' con aviso.  Evita
        # crash y refleja la limitación real (no hay k0/Ea para esa rxn).
        if mode in ("pfr", "cstr") and custom_rxn_ids:
            # Las custom nunca traen cinética → si hay alguna, degradar.
            msgs.append(f"⚠ Reactor {b.name}: modo '{mode}' incompatible "
                         f"con reacciones custom (sin cinética Arrhenius). "
                         f"Degradando a 'equilibrium'.")
            mode = "equilibrium"
        if mode == "equilibrium":
            res = _rdb.solve_equilibrium_reactor_from_composition(
                rxn_ids=all_rxn_ids,
                inlet_composition=agg,
                inlet_mass_kg_s=m_in_kg_s,
                T_K=T_K, P_bar=b.P_op_bar)
        elif mode == "stoich":
            res = _rdb.solve_stoichiometric_reactor(
                rxn_ids=all_rxn_ids,
                inlet_composition=agg,
                inlet_mass_kg_s=m_in_kg_s,
                T_K=T_K, P_bar=b.P_op_bar,
                conversion=getattr(b, "reactor_conversion", 0.95))
        elif mode in ("pfr", "cstr"):
            V_L = getattr(b, "reactor_volume_L", 0.0) or 0.0
            if V_L <= 0:
                msgs.append(f"✗ Reactor {b.name} ({mode}): falta declarar "
                             f"reactor_volume_L > 0.")
                continue
            res = _rdb.solve_kinetic_reactor_from_composition(
                mode=mode,
                rxn_ids=all_rxn_ids,
                inlet_composition=agg,
                inlet_mass_kg_s=m_in_kg_s,
                T_K=T_K, P_bar=b.P_op_bar,
                V_reactor_L=V_L)
        elif mode == "batch":
            V_L = getattr(b, "reactor_volume_L", 0.0) or 0.0
            t_b = getattr(b, "batch_time_s", 3600.0) or 0.0
            if V_L <= 0:
                msgs.append(f"✗ Reactor {b.name} (batch): falta declarar "
                             f"reactor_volume_L > 0.")
                continue
            if t_b <= 0:
                msgs.append(f"✗ Reactor {b.name} (batch): falta declarar "
                             f"batch_time_s > 0.")
                continue
            res = _rdb.solve_batch_from_composition(
                rxn_ids=all_rxn_ids,
                inlet_composition=agg,
                inlet_mass_kg_s=m_in_kg_s,
                T_K=T_K, P_bar=b.P_op_bar,
                V_reactor_L=V_L,
                t_batch_s=t_b)
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

        # Guardar el perfil espacial del PFR / temporal del batch en el
        # bloque para que el panel de propiedades los pueda graficar.
        # CSTR → ambos None (no tiene perfil). Runtime con guion bajo:
        # NO se serializan.
        b._pfr_profile = res.get("pfr_profile")
        b._batch_profile = res.get("batch_profile")

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
        # T_in_avg_K ya calculado arriba (en el setup del bloque)
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

        # Capa 7 — reactor ADIABÁTICO: no hay duty externo (Q_total=0).
        # T_out se ajustó iterando hasta que Q_sensible compensa Q_rxn.
        # Para isothermal (T_op_K declarado): Q_total = Q_sens + Q_rxn,
        # el horno/jacket provee/extrae ese calor.
        if is_adiabatic:
            Q_total_kW = 0.0
            adiab_tag = " [ADIABÁTICO]"
        else:
            Q_total_kW = Q_sensible_kW + Q_rxn_kW
            adiab_tag = ""

        if not _is_duty_locked(b):
            b.duty = Q_total_kW

        T_op_C = T_K - 273.15
        for s_out in outs:
            if not _is_temp_locked(s_out):
                s_out.temperature = T_op_C

        # ── Propagar P de operación + inferir phase de los outlets ──
        # (Frente B).  Sólo corrientes de proceso (no utility/ambient).
        proc_outs = [s for s in outs
                     if (s.role or "") not in ("utility", "ambient")]
        if b.P_op_bar > 0:
            for s_out in proc_outs:
                if not _is_pressure_locked(s_out):
                    s_out.pressure_bar = b.P_op_bar
        # La composición del outlet a (T_op, P_op) puede caer en cualquier
        # región; el reactor no decide la fase — la infiere la termo.
        if out_comp:
            phase_inf, vfrac = _infer_phase_from_TP(out_comp, T_K, b.P_op_bar)
            if phase_inf:
                for s_out in proc_outs:
                    if not _is_phase_locked(s_out):
                        s_out.phase = phase_inf
                        s_out.vapor_fraction = vfrac

        msgs.append(f"✓ Reactor {b.name}{adiab_tag}: ΔH_rxn={Q_rxn_kW:+.2f} kW, "
                     f"Q_sens={Q_sensible_kW:+.2f} kW, "
                     f"Q_total={Q_total_kW:+.2f} kW, T_out={T_op_C:.0f}°C, "
                     f"ξ={res['xi']}")
    return msgs


def _column_feed_q(feed, T_feed_K, P_bar):
    """Factor de calidad q del feed para el diseño FUG (P1.2).

    q = L/F:  1.0 = líquido saturado · 0.0 = vapor saturado ·
    0<q<1 = bifásico.  Detecta la fase real del feed; si es bifásico o
    no está declarada, hace un flash isotérmico (NRTL) a T_feed, P para
    estimar V/F.  Clamp a [0, 1].  Fallback q=1.0 (compat previa)."""
    phase = (getattr(feed, "phase", "") or "").lower()
    if phase == "liquid":
        return 1.0
    if phase in ("vapor", "gas"):
        return 0.0
    # two_phase con vapor_fraction ya resuelta → q = 1 - V/F directo
    vf = getattr(feed, "vapor_fraction", None)
    if phase == "two_phase" and vf is not None:
        try:
            return max(0.0, min(1.0, 1.0 - float(vf)))
        except (TypeError, ValueError):
            pass
    # bifásico/mixed/no declarado → flash isotérmico para estimar V/F
    try:
        import nrtl as _nrtl
        import thermo_db as _td
        comps = list((feed.composition or {}).keys())
        if not comps:
            return 1.0
        z_mol = []
        for c in comps:
            co = _td.get(c)
            mw = co.mw if (co and co.mw > 0) else 1.0
            z_mol.append(feed.composition[c] / mw)   # mass → mol
        s = sum(z_mol)
        if s <= 0:
            return 1.0
        z_mol = [zi / s for zi in z_mol]
        fl = _nrtl.flash_TP(comps, z_mol, T_feed_K, P_bar)
        if fl is not None and fl.get("V_frac") is not None:
            return max(0.0, min(1.0, 1.0 - float(fl["V_frac"])))
    except Exception:
        pass
    return 1.0


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
                # Heurística final: primer output = distillate, segundo = bottom.
                # Esto es FRÁGIL — depende del orden de declaración en el
                # builder, no de la realidad física.  Emitir warning visible.
                msgs.append(
                    f"⚠ {b.name}: identificación distillate/bottom por "
                    f"ORDEN (no por port ni composition). Verificar "
                    f"manualmente: outs[0]='{outs[0].name}' (asumido "
                    f"distillate), outs[1]='{outs[1].name}' (asumido "
                    f"bottom). Para evitar este warning declarar "
                    f"src_port='vapor'/'liq' o composition con LK."
                )
                dist_stream = outs[0]
                bot_stream = outs[1]

        # Llamar al diseño FUG completo (siempre, como reference)
        T_feed_K = feed.temperature + 273.15
        T_top_K  = dist_stream.temperature + 273.15 if dist_stream.temperature else T_feed_K - 10
        T_bot_K  = bot_stream.temperature + 273.15 if bot_stream.temperature else T_feed_K + 20
        # q dinámico del feed (P1.2): detecta fase real / flash si bifásico
        q_feed = _column_feed_q(feed, T_feed_K, 1.013)
        try:
            res = _fug.design_column(
                feed_composition=feed.composition,
                F=feed.mass_flow,
                T_K=T_feed_K, P_bar=1.013,
                light_key=LK, heavy_key=HK,
                x_D_LK=b.column_x_D_LK,
                x_B_LK=b.column_x_B_LK,
                R_factor=b.column_R_factor,
                q=q_feed, T_top_K=T_top_K, T_bot_K=T_bot_K)
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
        wh_conv = None      # None = no se corrió WH; True/False = resultado
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
                    mw = co.mw if co and co.mw > 0 else None
                    if mw is None:
                        msgs.append(
                            f"⚠ {b.name} (WH): MW de '{c}' no resuelto vía "
                            f"thermo_db, fallback MW=1.0 — conversión "
                            f"mass/mol puede dar composiciones incorrectas."
                        )
                        mw = 1.0
                    mws.append(mw)
                z_mol = [zi / m for zi, m in zip(z_mass, mws)]
                z_sum = sum(z_mol)
                if z_sum > 0:
                    z_mol = [z / z_sum for z in z_mol]
                F_mol = sum(feed.mass_flow * zi / m * 1000 / (8760 * 3600)
                              for zi, m in zip(z_mass, mws))
                N_wh = b.column_N_stages or max(int(res["N"]) + 2, 10)
                fs_wh = max(2, N_wh // 2)
                # max_iter más alto: cerca de azeótropos WH converge lento
                wh_res = _wh.wang_henke(
                    comps=comps, feed_z=z_mol, F=F_mol,
                    T_feed_K=T_feed_K, P_bar=1.013,
                    N=N_wh, feed_stage=fs_wh,
                    D_over_F=res["D"] / res["F"],
                    R=res["R"], max_iter=80)
                if wh_res is not None:
                    # Métricas para la UI (P4): etapa de feed + cierre global
                    wh_res["feed_stage"] = fs_wh
                    try:
                        H_F = _wh._enthalpy_liquid(comps, z_mol, T_feed_K)
                        H_D = _wh._enthalpy_liquid(comps, wh_res["x_profile"][0],
                                                   wh_res["T_profile"][0])
                        H_B = _wh._enthalpy_liquid(comps, wh_res["x_profile"][-1],
                                                   wh_res["T_profile"][-1])
                        lhs = (F_mol * H_F / 1000.0 + wh_res["Q_reb_kW"]
                               + wh_res["Q_cond_kW"])
                        rhs = (wh_res["D"] * H_D + wh_res["B"] * H_B) / 1000.0
                        wh_res["balance_err"] = (abs(lhs - rhs)
                                                 / max(abs(wh_res["Q_reb_kW"]), 1e-9))
                    except Exception:
                        wh_res["balance_err"] = None
                    # Persistir para el panel (igual que _column_N, _column_R)
                    b._wh_result = wh_res
                    wh_conv = bool(wh_res.get("converged"))
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
                        msgs.append(
                            f"⚠ {b.name} (FH): α relativo de '{comp}' no "
                            f"resuelto vía NRTL, fallback α=1.0 — "
                            f"distribución de este componente puede ser "
                            f"incorrecta."
                        )
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

        # ── Propagación T/P/phase de los outputs (Frente B) ──
        # T_top = bubble point del distillate a P_col (condensador total);
        # T_bot = bubble point del bottom a P_col + 0.1 bar (gradiente).
        # Los gases no-condensables (CO₂, H₂, N₂, CH₄…) que el FUG manda al
        # tope NO condensan en un condensador total: se excluyen del cálculo
        # de T para no hundir el bubble point a valores absurdos (-60°C).
        import nrtl as _nrtl_col
        P_col_bar = feed.pressure_bar if feed.pressure_bar > 0 else 1.013
        x_D_mol = _drop_noncondensables(_mass_to_mol(x_D_full))
        x_B_mol = _drop_noncondensables(_mass_to_mol(x_B_full))
        # ¿el destilado sale como VAPOR (tope) o como LÍQUIDO (condensador)?
        port_low = (dist_stream.src_port or "").lower()
        dist_is_vapor = any(k in port_low for k in ("vapor", "tope", "top"))
        # Destilado vapor → su T es el punto de ROCÍO; destilado líquido →
        # punto de BURBUJA.  El fondo siempre sale como líquido saturado.
        if dist_is_vapor:
            bp_top = (_nrtl_col.dew_point(list(x_D_mol.keys()),
                                          list(x_D_mol.values()), P_col_bar)
                      if x_D_mol else None)
        else:
            bp_top = (_nrtl_col.bubble_point(list(x_D_mol.keys()),
                                             list(x_D_mol.values()), P_col_bar)
                      if x_D_mol else None)
        bp_bot = (_nrtl_col.bubble_point(list(x_B_mol.keys()),
                                         list(x_B_mol.values()), P_col_bar + 0.1)
                  if x_B_mol else None)
        T_top_old = dist_stream.temperature
        T_bot_old = bot_stream.temperature
        if bp_top:
            T_top_C = bp_top[0] - 273.15
            if not _is_temp_locked(dist_stream):
                dist_stream.temperature = T_top_C
            if abs(T_top_C - T_top_old) > 10:
                msgs.append(f"ℹ Column {b.name}: T_top "
                            f"{'rocío' if dist_is_vapor else 'burbuja'} "
                            f"{T_top_C:.1f}°C (declarado {T_top_old:.1f}°C).")
        else:
            msgs.append(f"⚠ Column {b.name}: dew/bubble point del distillate no "
                        f"convergió (falta NRTL o Antoine). T_top no propagada.")
        if bp_bot:
            T_bot_C = bp_bot[0] - 273.15
            if not _is_temp_locked(bot_stream):
                bot_stream.temperature = T_bot_C
            if abs(T_bot_C - T_bot_old) > 10:
                msgs.append(f"ℹ Column {b.name}: T_bot bubble point "
                            f"{T_bot_C:.1f}°C (declarado {T_bot_old:.1f}°C).")
        else:
            msgs.append(f"⚠ Column {b.name}: bubble_point del bottom no "
                        f"convergió. T_bot no propagada.")
        # P de outputs
        if not _is_pressure_locked(dist_stream):
            dist_stream.pressure_bar = P_col_bar
        if not _is_pressure_locked(bot_stream):
            bot_stream.pressure_bar = P_col_bar + 0.1
        # Phase del distillate por puerto (vapor_tope → vapor;
        # condensador líquido → liquid).  Bottom siempre líquido saturado.
        if not _is_phase_locked(dist_stream):
            if dist_is_vapor:
                dist_stream.phase = "vapor"
                dist_stream.vapor_fraction = 1.0
            else:
                dist_stream.phase = "liquid"
                dist_stream.vapor_fraction = 0.0
        if not _is_phase_locked(bot_stream):
            bot_stream.phase = "liquid"
            bot_stream.vapor_fraction = 0.0

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
        b._column_q = res.get("q", 1.0)

        # Flag de convergencia WH para la lista de mensajes (P4.5)
        if wh_conv is True:
            _wh_flag = ", WH:conv"
        elif wh_conv is False:
            _wh_flag = ", WH:NO conv"
        else:
            _wh_flag = ""
        if wh_conv is False:
            msgs.append(
                f"⚠ Column {b.name}: FUG OK pero WH no convergió")
        else:
            msgs.append(
                f"✓ Column {b.name}: N={res['N']:.1f}, R={res['R']:.2f}, "
                f"Q_reb={Q_total:+.1f}kW, "
                f"D={feed.mass_flow*D_F:.0f} B={feed.mass_flow*B_F:.0f}{_wh_flag}"
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
        all_names = list(feed.composition.keys())
        if len(all_names) < 2:
            continue
        # Separar VOLÁTILES (con Antoine) de NO-VOLÁTILES (azúcares, sólidos
        # sin presión de vapor: glucosa, sacarosa…).  El NRTL sólo modela los
        # volátiles; un no-volátil metido en el Rachford-Rice con un Psat≈0
        # distorsiona la conversión mol→masa y "concentra" mal el componente
        # (p.ej. glucosa subía 9×).  Los no-volátiles van ENTEROS al líquido.
        try:
            import thermo_db as _td
        except ImportError:
            _td = None

        def _mw(c):
            comp = _td.get(c) if _td is not None else None
            return comp.mw if (comp and comp.mw > 0) else 1.0

        def _is_volatile(c):
            comp = _td.get(c) if _td is not None else None
            return (comp is not None and comp.antoine_A is not None
                    and comp.antoine_B is not None and comp.antoine_C is not None)

        vol_names = [c for c in all_names if _is_volatile(c)]
        nonvol_names = [c for c in all_names if c not in vol_names]
        if len(vol_names) < 2:
            continue   # sin suficientes volátiles no hay flash que resolver
        mws = [_mw(c) for c in vol_names]
        # feed.composition son fracciones MÁSICAS; flash_TP espera fracciones
        # MOLARES.  Convertir (zᵢ_mol ∝ wᵢ/MWᵢ) — antes se pasaban másicas como
        # molares, inflando CO2/etanol en el Rachford-Rice.
        z_moles = [feed.composition[vol_names[i]] / mws[i]
                   for i in range(len(vol_names))]
        zt = sum(z_moles) or 1.0
        z = [zm / zt for zm in z_moles]
        T_K = b.flash_T_K or (feed.temperature + 273.15)
        P_bar = b.flash_P_bar or 1.013
        try:
            res = _nrtl.flash_TP(vol_names, z, T_K, P_bar)
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
        V_frac = res["V_frac"]
        # Masas de los VOLÁTILES en cada fase (base: 1 mol de volátiles),
        # reescaladas a la masa volátil real del feed.
        L_mass_v = sum((1 - V_frac) * res["x"][i] * mws[i] for i in range(len(vol_names)))
        V_mass_v = sum(V_frac * res["y"][i] * mws[i] for i in range(len(vol_names)))
        tot_v = L_mass_v + V_mass_v
        if tot_v <= 0:
            continue
        vol_feed_mass = sum(feed.composition[c] for c in vol_names) * feed.mass_flow
        scale = vol_feed_mass / tot_v
        liq_masses = {vol_names[i]: (1 - V_frac) * res["x"][i] * mws[i] * scale
                      for i in range(len(vol_names))}
        vap_masses = {vol_names[i]: V_frac * res["y"][i] * mws[i] * scale
                      for i in range(len(vol_names))}
        # No-volátiles: masa completa del feed → líquido.
        for c in nonvol_names:
            liq_masses[c] = liq_masses.get(c, 0.0) + feed.composition[c] * feed.mass_flow
        L_mass = sum(liq_masses.values())
        V_mass = sum(vap_masses.values())
        total_mass = L_mass + V_mass
        if total_mass <= 0:
            continue
        L_frac_mass = L_mass / total_mass
        V_frac_mass = V_mass / total_mass
        x_mass = {c: liq_masses[c] / L_mass for c in liq_masses} if L_mass > 0 else {}
        y_mass = {c: vap_masses[c] / V_mass for c in vap_masses} if V_mass > 0 else {}

        # composition_locked en una salida = especificación del usuario (p.ej.
        # composiciones recomputadas por balance para componentes que el NRTL
        # no modela, como azúcares no volátiles).  Se RESPETA: el flash no la
        # sobreescribe (antes la pisaba siempre → "creaba" glucosa/etanol).
        if vap_out is not None:
            if not getattr(vap_out, "composition_locked", False):
                vap_out.composition = y_mass
                vap_out.main_component = max(y_mass, key=y_mass.get) if y_mass else ""
            vap_out.phase = "vapor"
            if not _is_mass_locked(vap_out):
                vap_out.mass_flow = feed.mass_flow * V_frac_mass
            if not _is_temp_locked(vap_out):
                vap_out.temperature = T_K - 273.15
        if liq_out is not None:
            if not getattr(liq_out, "composition_locked", False):
                liq_out.composition = x_mass
                liq_out.main_component = max(x_mass, key=x_mass.get) if x_mass else ""
            liq_out.phase = "liquid"
            if not _is_mass_locked(liq_out):
                liq_out.mass_flow = feed.mass_flow * L_frac_mass
            if not _is_temp_locked(liq_out):
                liq_out.temperature = T_K - 273.15

        # ── Propagar P de operación a los outputs (Frente B) ──
        if vap_out is not None and not _is_pressure_locked(vap_out):
            vap_out.pressure_bar = P_bar
        if liq_out is not None and not _is_pressure_locked(liq_out):
            liq_out.pressure_bar = P_bar

        # Si V_frac es extremo (0 o 1) el flash produjo single-phase:
        # reportar y dejar el output complementario con mass≈0.
        if V_frac_mass < 0.005:
            msgs.append(
                f"⚠ Flash {b.name}: V/F_mass={V_frac_mass:.4f} → single-phase "
                f"liquid a {T_K-273.15:.1f}°C, {P_bar:.2f}bar. Vapor stream "
                f"{vap_out.name if vap_out else '?'} con mass≈0; revisar si el "
                f"flash es necesario o si T/P son correctas."
            )
            if vap_out is not None:
                if not _is_mass_locked(vap_out):
                    vap_out.mass_flow = 0.0
                if not _is_phase_locked(vap_out):
                    vap_out.phase = "vapor"
        elif V_frac_mass > 0.995:
            msgs.append(
                f"⚠ Flash {b.name}: V/F_mass={V_frac_mass:.4f} → single-phase "
                f"vapor a {T_K-273.15:.1f}°C, {P_bar:.2f}bar. Líquido stream "
                f"{liq_out.name if liq_out else '?'} con mass≈0; revisar."
            )
            if liq_out is not None:
                if not _is_mass_locked(liq_out):
                    liq_out.mass_flow = 0.0
                if not _is_phase_locked(liq_out):
                    liq_out.phase = "liquid"

        msgs.append(
            f"✓ Flash {b.name}: V/F_mass={V_frac_mass:.3f}  T={T_K-273.15:.1f}°C  "
            f"P={P_bar:.2f}bar"
        )
    return msgs


def _compressor_polytropic_warnings(fs):
    """P12: warning para compresores con ΔP>0 cuyo cálculo politrópico
    (equipment_design.design_compressor_for_block) no resuelve por datos
    insuficientes (mw_avg, k, composición).  El duty queda sin actualizar
    (NO se usa la fórmula incompresible — sería peor para gases).

    Se chequea post-loop en solve_pressure_hydraulic porque el msgs de
    solve_pressure_propagation (donde se calcula el duty) se descarta en
    las llamadas del loop.  Un compresor con ΔP=0 NO entra acá — ese caso
    lo cubre _compressor_degenerate_warnings (P13)."""
    out = []
    try:
        import equipment_design as _ed
    except ImportError:
        return out
    for b in fs.blocks.values():
        if "compressor" not in b.eq_type.lower():
            continue
        if getattr(b, "delta_p_bar", 0.0) <= 0:
            continue   # degenerado (ΔP=0) → lo cubre P13
        try:
            res = _ed.design_compressor_for_block(b, fs)
        except Exception:
            res = None
        if not res or res.get("W_act_kW", 0) <= 0:
            out.append(
                f"⚠ {b.name}: compresor con datos insuficientes para "
                f"cálculo politrópico (mw, k, comp). Duty no actualizado."
            )
    return out


def _compressor_degenerate_warnings(fs):
    """P13: lista de warnings para compresores con sizing degenerado —
    ΔP≈0 Y sin P_op_bar declarada (≤1 bar).  Datos incompletos del
    builder: el compresor se dimensiona trivialmente (ΔP=0) y su costing
    no es realista.  Una entrada por compresor afectado.

    Se llama desde solve_pressure_hydraulic en TODOS sus return points
    (incluso cuando no hay streams con P locked y el auto-sizing no
    corre) para que el warning sea visible siempre."""
    out = []
    for b in fs.blocks.values():
        if "compressor" not in b.eq_type.lower():
            continue
        if abs(b.delta_p_bar) >= 1e-6:
            continue   # tiene ΔP (declarado o auto-sized) — OK
        p_op = getattr(b, "P_op_bar", 0) or 0
        if p_op <= 1.0:
            out.append(
                f"⚠ {b.name}: compresor sin P_op_bar ni delta_p_bar "
                f"declarados. Sizing degenerado (ΔP=0). Declarar "
                f"P_op_bar en el bloque para costing realista."
            )
    return out


def _seed_reactor_pressures(fs):
    """Pinta (lock) la presión de las corrientes de PROCESO I/O de los
    bloques que declaran P_op_bar > 1 atm, para que la sección de alta P
    propague su presión real.  El solver hidráulico NO usaba P_op_bar
    (solo pressure_locked/delta_p_bar), así que reactores a 25/80/200 bar
    dejaban sus corrientes en 1.013 → CAPEX/material adyacentes mal.

    Reglas:
      · Solo corrientes de proceso (role ≠ utility/ambient).
      · Respeta los locks del user (no sobreescribe).
      · Idempotente.  Devuelve la cantidad de corrientes fijadas.
    """
    ATM = 1.01325
    # No tocar las corrientes que el USER fijó explícitamente.
    user_locked = {s.id for s in fs.streams.values()
                    if getattr(s, "pressure_locked", False)}
    hi = [b for b in fs.blocks.values()
           if float(getattr(b, "P_op_bar", 0.0) or 0.0) > ATM + 1e-6]

    def _proc(b, s):
        return (s.role or "") not in ("utility", "ambient") \
               and s.id not in user_locked

    n = 0
    # Pasada 1: salidas.  Pasada 2: entradas — éstas GANAN sobre las salidas
    # cuando una corriente es salida de un bloque de P_a y entrada de otro de
    # P_b distinta (let-down/compresor implícito): la corriente entra al
    # bloque destino a SU presión.  Para el costing del bloque upstream,
    # effective_pressure ya usa el máximo de sus corrientes, así que no
    # pierde su sección.
    for is_input in (False, True):
        for b in hi:
            pop = float(b.P_op_bar)
            for s in fs.streams.values():
                attached = (s.dst == b.id) if is_input else (s.src == b.id)
                if attached and _proc(b, s):
                    s.pressure_bar = pop
                    s.pressure_locked = True
                    # lock de origen SOLVER (no es spec del user ni heurística
                    # de carga): el seed lo deriva de P_op_bar del bloque.
                    if not getattr(s, "pressure_lock_origin", "") or \
                            s.pressure_lock_origin == "heuristic":
                        s.pressure_lock_origin = "solver"
                    n += 1
    return n


def effective_pressure(fs, b):
    """Presión efectiva [bar] de un bloque para costing/material: el máximo
    entre su P_op_bar declarada y la presión de sus corrientes de proceso
    conectadas.  Así un HX/vessel/columna en una sección de alta presión
    hereda la P real aunque no declare P_op_bar (el FP de Turton la usa)."""
    p = float(getattr(b, "P_op_bar", 0.0) or 0.0)
    for s in fs.streams.values():
        if (s.src == b.id or s.dst == b.id) and \
                (s.role or "") not in ("utility", "ambient"):
            p = max(p, float(getattr(s, "pressure_bar", 0.0) or 0.0))
    return p if p >= 1.0 else 1.0


def effective_temperature(fs, b):
    """Temperatura efectiva [K] de un bloque para PRESENTACIÓN: su T_op_K
    declarada, o si no la declara (0/None), el promedio de las temperaturas
    de sus corrientes de PROCESO conectadas (in + out).  Mismo criterio de
    corrientes que effective_pressure (excluye utility/ambient).  Devuelve
    0.0 si no hay ninguna T disponible (no se puede derivar).

    OJO unidades: block.T_op_K está en KELVIN, pero stream.temperature está
    en °C — se convierte (°C + 273.15) para devolver siempre Kelvin."""
    t_decl = float(getattr(b, "T_op_K", 0.0) or 0.0)
    if t_decl:
        return t_decl
    temps = []
    for s in fs.streams.values():
        if (s.src == b.id or s.dst == b.id) and \
                (s.role or "") not in ("utility", "ambient"):
            t = getattr(s, "temperature", None)
            if t is not None:                       # °C → K
                temps.append(float(t) + 273.15)
    return sum(temps) / len(temps) if temps else 0.0


def solve_pressure_hydraulic(fs, max_iter=8):
    """Solver hidráulico iterativo — acopla bombas + tuberías +
    downstream para auto-dimensionar bombas/compresores.

    Workflow:
      1. Forward pass: solve_pressure_propagation(fs) — propaga P
         desde feeds locked usando los ΔP DECLARADOS.
      2. Para cada pump/compressor SIN delta_p_bar declarado, busca
         el próximo stream locked downstream.  Calcula el ΔP que la
         bomba debe levantar:
            ΔP_pump_needed = P_target - P_in_available + Σ ΔP_pipe_intermedios
                              + Σ ΔP_block_intermedios (HX/cols con ΔP<0)
      3. Setea block.delta_p_bar y recalcula propagación.
      4. Itera hasta convergencia (ΔP_pipe cambia poco con ΔP_pump,
         pero gases tienen densidad variable).

    USE CASE típico:
      Feed (P=1 bar locked) → Pump (no spec) → 50 m tubería con K=5
      → HX (-0.5) → 30 m tubería → Producto (P=3 bar locked)
    El solver calcula automáticamente ΔP necesaria de la bomba.

    Returns list de mensajes (✓/⚠/✗).
    """
    # Sembrar P_op_bar de reactores/equipos de alta P como locks en sus
    # corrientes de proceso (el solver no la usaba) → la sección propaga
    # su presión real.  Crea locks ⇒ el solver opt-in se activa.
    _seed_reactor_pressures(fs)
    # Check si vale la pena
    has_locked = any(getattr(s, "pressure_locked", False)
                      for s in fs.streams.values())
    if not has_locked:
        # Sin streams con P locked el solver no auto-dimensiona ΔP, pero
        # los compresores degenerados (sin P_op_bar ni delta_p_bar) siguen
        # siendo deuda visible → emitir el warning P13 igual.
        return _compressor_degenerate_warnings(fs)

    try:
        import pressure_drop as _pd
    except ImportError:
        return _compressor_degenerate_warnings(fs)

    msgs = []
    sized_pumps = set()
    # Detectar SCCs (reciclos) — útil para indicar al user que la bomba
    # está dentro de un loop y su auto-sizing implica balance del recycle.
    try:
        sccs = _strongly_connected_components(fs)
        recycle_sccs = [scc for scc in sccs if _is_recycle_scc(scc, fs)]
        blocks_in_recycle = set()
        for scc in recycle_sccs:
            for bid in scc:
                blocks_in_recycle.add(bid)
    except Exception:
        blocks_in_recycle = set()
    for outer in range(max_iter):
        # 1) Propagación forward con ΔP declarados
        solve_pressure_propagation(fs)

        # 2) Para cada bomba/compresor sin ΔP, calcular el que falta
        any_sized = False
        for b in fs.blocks.values():
            eq_lower = b.eq_type.lower()
            is_rotative = ("pump" in eq_lower or "compressor" in eq_lower
                            or "fan" in eq_lower or "bomba" in eq_lower)
            if not is_rotative:
                continue
            # Skip si ya tiene ΔP declarado (no None, no 0) Y no fue auto-sized
            # antes (queremos re-iterar los auto-sized si cambia ΔP_pipe).
            if (abs(b.delta_p_bar) > 1e-6 and b.id not in sized_pumps):
                continue
            ins  = [s for s in fs.streams.values() if s.dst == b.id]
            outs = [s for s in fs.streams.values() if s.src == b.id]
            if not ins or not outs:
                continue
            # P de entrada
            P_in_min = min(s.pressure_bar for s in ins if s.pressure_bar > 0)
            # Buscar próximo stream locked downstream — BFS
            target_P, accumulated_dp = _find_downstream_target(fs, b.id,
                                                                _pd)
            if target_P is None:
                continue
            # ΔP que la bomba debe entregar para llegar al target
            # considerando ΔP positivos (que también suben) y negativos
            # (HX, columnas) downstream.
            # accumulated_dp = Σ (ΔP_pipe + ΔP_blocks downstream del bloque
            #                       hasta el target).  Si downstream hay
            #                       bombas, sus ΔP también suman.
            dp_needed = (target_P - P_in_min) + accumulated_dp
            if dp_needed <= 0.05:
                continue   # downstream P_target ya está cubierto
            new_dp = round(dp_needed, 3)
            old_dp = b.delta_p_bar
            if abs(new_dp - old_dp) > 0.05:
                b.delta_p_bar = new_dp
                sized_pumps.add(b.id)
                any_sized = True
                # FASE 2.4: recomputar el duty politrópico del rotativo con
                # el ΔP recién dimensionado (sólo compresor/fan; las bombas
                # ya tienen su propia ruta).  Sólo si NO está duty_locked.
                if (("compressor" in eq_lower or "fan" in eq_lower)
                        and not getattr(b, "duty_locked", False)):
                    w = _auto_hydraulic_compressor_duty(b, fs)
                    if w is not None:
                        b.duty = w
                        b.duty_origin = "auto-hidraulico"
                in_recycle = b.id in blocks_in_recycle
                rec_tag = " (en recycle)" if in_recycle else ""
                msgs.append(
                    f"✓ {b.name}{rec_tag} auto-sized: ΔP={new_dp:.2f} bar "
                    f"(P_in={P_in_min:.2f}, target_dn={target_P:.2f}, "
                    f"Σ losses={accumulated_dp:.2f})"
                )
        if not any_sized:
            break
        # 3) Re-propagar con las ΔP nuevas
        solve_pressure_propagation(fs)

    # P13: warning post auto-sizing (compresores que quedaron degenerados
    # PESE a que el solver intentó dimensionarlos via downstream targets).
    msgs.extend(_compressor_degenerate_warnings(fs))
    # P12: warning para compresores con ΔP>0 cuyo cálculo politrópico
    # falló por datos insuficientes (duty no actualizado).
    msgs.extend(_compressor_polytropic_warnings(fs))
    return msgs


def _auto_hydraulic_compressor_duty(b, fs):
    """FASE 2.4 — duty politrópico de un compresor/fan auto-dimensionado.

    Usa el MISMO modelo isentrópico que el paso de energía
    (compressor_sizing + _compressible_props), tomando la M de la mezcla
    desde la composición MÁSICA del feed.  Devuelve W_elec_kW (>0) o None.
    Se computa con el ΔP recién auto-dimensionado; el paso de energía lo
    refina luego con la T propagada (valor final idéntico al previo →
    golden-safe), pero deja la marca duty_origin='auto-hidraulico'."""
    try:
        from equipment_design import compressor_sizing
        from flowsheet_model import SEC_PER_YEAR, TM_TO_KG
    except Exception:
        return None
    ins = [s for s in fs.streams.values() if s.dst == b.id and s.mass_flow > 0]
    if not ins:
        return None
    feed = ins[0]
    comp = feed.composition or ({feed.main_component: 1.0}
                                if feed.main_component else {})
    if not comp:
        return None
    P_in = feed.pressure_bar if feed.pressure_bar > 0 else 1.013
    P_out = P_in + float(getattr(b, "delta_p_bar", 0.0) or 0.0)
    if P_out <= P_in:
        return None
    m_kg_s = feed.mass_flow * TM_TO_KG / SEC_PER_YEAR
    mw_avg, k = _compressible_props(comp, feed.temperature + 273.15)
    res = compressor_sizing(m_kg_s=m_kg_s, P_in_bar=P_in, P_out_bar=P_out,
                            T_in_K=feed.temperature + 273.15, mw_avg=mw_avg,
                            k=k, eta_isen=(b.efficiency or 0.75))
    if not res or res.get("W_act_kW", 0) <= 0:
        return None
    return res["W_act_kW"]


def _find_downstream_target(fs, start_block_id, _pd):
    """BFS desde el bloque start_block_id buscando el próximo stream
    con pressure_locked=True.  Devuelve (target_P_bar, accumulated_dp)
    donde accumulated_dp es la suma de pérdidas (ΔP_pipe + ΔP_block
    negativos) entre el start y el target.

    Si no hay target locked downstream, retorna (None, 0).
    """
    visited_blocks = {start_block_id}
    visited_streams = set()
    accumulated = 0.0
    target_P = None
    # Cola: list de tuples (stream_to_visit, dp_acc_until_now)
    queue = []
    for s in fs.streams.values():
        if s.src == start_block_id:
            queue.append((s, 0.0))
    while queue:
        stream, dp_acc = queue.pop(0)
        if stream.id in visited_streams:
            continue
        visited_streams.add(stream.id)
        # ΔP_pipe del propio stream
        try:
            pd_res = _pd.stream_pressure_drop(stream)
            dp_pipe = pd_res["delta_P_bar"] if pd_res else 0.0
        except Exception:
            dp_pipe = 0.0
        dp_acc_new = dp_acc + dp_pipe
        # Si el stream está locked → es nuestro target
        if getattr(stream, "pressure_locked", False):
            target_P = stream.pressure_bar
            accumulated = dp_acc_new
            return (target_P, accumulated)
        # Sino, continuar BFS al destino
        dst_block_id = stream.dst
        if dst_block_id in visited_blocks or dst_block_id not in fs.blocks:
            continue
        visited_blocks.add(dst_block_id)
        dst_block = fs.blocks[dst_block_id]
        # ΔP del bloque destino (negativo = pérdida, positivo = otra bomba)
        dp_block = getattr(dst_block, "delta_p_bar", 0.0)
        # Si dst es OTRA bomba con ΔP positivo: para por ahí (esa bomba
        # se encarga del resto downstream); no agregamos su contribución
        eq_dst = dst_block.eq_type.lower()
        is_pump_compr = ("pump" in eq_dst or "compressor" in eq_dst
                          or "fan" in eq_dst or "bomba" in eq_dst)
        if is_pump_compr and dp_block > 0:
            continue   # la siguiente bomba auto-sizing se encarga
        # Agregar ΔP del bloque (negativo = perdida = sumamos su valor abs)
        if dp_block < 0:
            dp_acc_new += abs(dp_block)
        # Continuar BFS por outs del bloque destino
        for s2 in fs.streams.values():
            if s2.src == dst_block_id and s2.id not in visited_streams:
                queue.append((s2, dp_acc_new))
    return (None, 0.0)


def _trace_downstream_itemized(fs, start_block_id):
    """Como _find_downstream_target, pero devuelve el desglose itemizado de
    la ΔP que la bomba/compresor entrega: cada tramo de tubería y cada caída
    de equipo entre la succión y el anchor downstream, más un item
    'destination_delta' = (P_target − P_origin) que captura la subida neta de
    presión del sistema.

    Invariante: sum(items.dp_bar) == ΔP que el solver dimensionó para el
    bloque (= block.delta_p_bar), porque usa el MISMO BFS y los mismos ΔP que
    _find_downstream_target.

    Returns dict | None (None si el bloque no tiene succión o no hay anchor
    downstream locked).
    """
    try:
        import pressure_drop as _pd
    except ImportError:
        _pd = None
    blk = fs.blocks.get(start_block_id)
    if blk is None:
        return None
    ins = [s for s in fs.streams.values()
           if s.dst == start_block_id and s.mass_flow >= 0]
    if not ins:
        return None
    origin = min(ins, key=lambda s: (s.pressure_bar if s.pressure_bar > 0
                                      else float("inf")))
    origin_P = origin.pressure_bar
    origin_name = origin.name

    def _pipe_dp(stream):
        if _pd is None:
            return 0.0
        try:
            r = _pd.stream_pressure_drop(stream)
            return r["delta_P_bar"] if r else 0.0
        except Exception:
            return 0.0

    visited_blocks = {start_block_id}
    visited_streams = set()
    # Cola: (stream, items_acumulados_en_esta_rama)
    queue = [(s, []) for s in fs.streams.values()
             if s.src == start_block_id]
    while queue:
        stream, items_acc = queue.pop(0)
        if stream.id in visited_streams:
            continue
        visited_streams.add(stream.id)
        new_items = list(items_acc)
        dp_pipe = _pipe_dp(stream)
        if dp_pipe > 1e-9:
            new_items.append({
                "kind": "pipe", "ref": stream.name, "dp_bar": dp_pipe,
                "detail": (f"Pipe {stream.name} "
                           f"({getattr(stream,'pipe_length_m',0):.0f} m, "
                           f"D={getattr(stream,'pipe_diameter_m',0)*1000:.0f} mm, "
                           f"K={getattr(stream,'pipe_K_local',0):.1f})")})
        if getattr(stream, "pressure_locked", False):
            dd = stream.pressure_bar - origin_P
            cand = new_items + [{
                "kind": "destination_delta", "ref": stream.name, "dp_bar": dd,
                "detail": (f"Δ destino−origen "
                           f"({stream.name} − {origin_name})")}]
            total = sum(it["dp_bar"] for it in cand)
            # Mirror del solver: si el ΔP necesario hacia este anchor es ≤0
            # (succión ya por encima del target, p.ej. compresor de reciclo en
            # sección de alta P), este target NO dimensiona la bomba → no hay
            # desglose atribuible.
            if total <= 0.05:
                return None
            return dict(
                target_P_bar=stream.pressure_bar,
                target_stream_name=stream.name,
                origin_P_bar=origin_P, origin_stream_name=origin_name,
                items=cand, total_dp_bar=total)
        dst_id = stream.dst
        if dst_id in visited_blocks or dst_id not in fs.blocks:
            continue
        visited_blocks.add(dst_id)
        dst = fs.blocks[dst_id]
        dp_block = getattr(dst, "delta_p_bar", 0.0)
        eq_dst = dst.eq_type.lower()
        is_pump_compr = ("pump" in eq_dst or "compressor" in eq_dst
                         or "fan" in eq_dst or "bomba" in eq_dst)
        if is_pump_compr and dp_block > 0:
            continue                       # la próxima bomba se encarga
        if dp_block < 0:
            new_items.append({
                "kind": "block", "ref": dst.name, "dp_bar": abs(dp_block),
                "detail": f"{dst.name} {dst.eq_type}"})
        for s2 in fs.streams.values():
            if s2.src == dst_id and s2.id not in visited_streams:
                queue.append((s2, list(new_items)))
    return None


def anchor_ambient_pressures(fs, P_atm: float = 1.013):
    """Ancla a presión atmosférica los streams conectados a bloques Ambient.

    Físicamente la atmósfera es un baño infinito a 1 atm.  Cualquier stream
    que la tenga como origen (intake de aire) o destino (venteo / chimenea /
    blowdown) debe estar a P_atm en ese extremo — el ΔP entre la planta
    presurizada y la atmósfera lo absorbe una válvula de let-down (vent) o
    el sopladero (intake) implícito en la línea.

    Sin este anclaje el solver propaga la P upstream hasta la nube
    (p.ej. 200 bar de un purge de Haber), lo cual es no físico y confunde
    al lector del PFD.

    Respeta `pressure_locked` — si el user fijó otra P explícitamente, no
    se sobrescribe.  Marca el stream con pressure_locked=True al final
    para que las pasadas siguientes del solver no la pisen.
    """
    n_anchored = 0
    for b in fs.blocks.values():
        if (b.eq_type or "") != "Ambient":
            continue
        for s in fs.streams.values():
            if s.src != b.id and s.dst != b.id:
                continue
            if getattr(s, "pressure_locked", False):
                continue
            # SIEMPRE lockear, aunque ya esté en P_atm — sin el lock la
            # propagation downstream del solver pisa el valor con la P de
            # upstream (p.ej. 200 bar de un purge de Haber).
            s.pressure_bar = float(P_atm)
            try:
                s.pressure_locked = True
            except Exception:
                pass
            n_anchored += 1
    return n_anchored


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

            # Para bombas/compresores con ΔP positivo declarado, calcular
            # duty.  Distinguimos por tipo de equipo:
            #   · Compresor: delegamos a equipment_design (ec. politrópica
            #     isentrópica, físicamente correcta para gases — P12).
            #   · Bomba: fórmula incompresible W = m·ΔP/(ρ·η) (correcta
            #     para líquidos).
            if is_pump_or_compressor and dp_block > 0 and not _is_duty_locked(b):
                if "compressor" in eq_lower:
                    # Single source of truth: equipment_design.  El sizing
                    # (size_compressor) ya usa esta misma función → duty y
                    # sizing quedan consistentes.  Si falla (None/excepción),
                    # NO caemos a la fórmula incompresible (sería peor para
                    # gases); dejamos el duty intacto y el warning lo emite
                    # _compressor_polytropic_warnings post-loop (el msgs de
                    # ESTA función se descarta en las llamadas del solver
                    # hidráulico, así que el warning iría perdido acá).
                    try:
                        import equipment_design as _ed
                        res = _ed.design_compressor_for_block(b, fs)
                        if res and res.get("W_act_kW", 0) > 0:
                            b.duty = res["W_act_kW"]
                            changed = True
                    except Exception:
                        pass
                else:
                    # Bomba: fórmula incompresible (correcta para líquidos).
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

    # Post-iteración: detectar bloques que MEZCLAN físicamente sus entradas
    # con presiones disparejas (Δ > 0.5 bar).  El modelo no es físico — el
    # lado de alta P se throttla implícitamente (work desperdicio) o el de
    # baja necesita compresión/bombeo upstream.
    #
    # NO aplica a HXs (shell y tube son lados separados, no se mezclan),
    # ni a torres (puertos diferenciados feed/reflujo/vapor), ni a auto_aux
    # (headers de utility por diseño reciben dispares).
    for b in fs.blocks.values():
        eq_l = (b.eq_type or "").lower()
        if getattr(b, "auto_aux", False):
            continue
        if "heat exch" in eq_l or "fired heater" in eq_l or "boiler" in eq_l \
                or "cooling tower" in eq_l:
            continue
        if "tower" in eq_l or "column" in eq_l:
            continue
        ins = [s for s in fs.streams.values() if s.dst == b.id]
        if len(ins) < 2:
            continue
        # Filtrar streams sin presión resuelta o de utility/ambient (que
        # entran por puertos distintos al de proceso).
        proc_ins = [s for s in ins
                    if s.pressure_bar > 0
                    and (s.role or "") not in ("utility", "ambient")
                    and not getattr(s, "auto_aux", False)]
        if len(proc_ins) < 2:
            continue
        # Para tanques/vessels (NO mixers): si las entradas van a puertos
        # distintos (vapor-in vs liquid-in en un knock-out, p.ej.), no se
        # mezclan físicamente.  Los mixers en cambio SIEMPRE mezclan todos
        # sus inlets, incluso si usan entrada1/entrada2 labelados.
        is_mixer = ("mixer" in eq_l or "mix " in eq_l
                    or getattr(b, "mixer_active", False))
        if not is_mixer:
            ports = {s.dst_port for s in proc_ins if s.dst_port}
            if len(ports) > 1:
                continue
        ps = [s.pressure_bar for s in proc_ins]
        P_hi = max(ps); P_lo = min(ps)
        if P_hi - P_lo <= 0.5:
            continue
        hi = next(s for s in proc_ins if s.pressure_bar == P_hi)
        lo = next(s for s in proc_ins if s.pressure_bar == P_lo)
        _log_solver_warning(
            fs,
            f"⚠ {b.name} ({b.eq_type}): mezcla '{lo.name}' a {P_lo:.2f} bar "
            f"con '{hi.name}' a {P_hi:.2f} bar (Δ={P_hi - P_lo:.1f} bar).  "
            f"Físicamente '{lo.name}' debería pasar por bomba/compresor para "
            f"igualar la presión antes del mezclador, o '{hi.name}' por una "
            f"válvula de control (implícitamente throttled — work desperdicio).")
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


# ─────────────────────────────────────────────────────────────
# SEPARADORES MECÁNICOS — modelos internos basados en split/recovery
# (filtro, centrífuga, secador, cristalizador, evaporador, ciclón)
# Patrón: respetan locks (mass/composition), conservan masa global +
# por componente, devuelven List[str] con prefijos ✓/⚠/✗ igual que
# los solvers existentes.
# ─────────────────────────────────────────────────────────────

def _pick_feed(fs, b):
    """Helper: stream de entrada al bloque con mass>0 y composition."""
    ins = [s for s in fs.streams.values() if s.dst == b.id]
    return next((s for s in ins
                   if s.mass_flow > 0 and (s.composition or {})), None)


def _pick_outs_by_port(fs, b, primary_port_kws, secondary_port_kws):
    """Helper: identifica dos outputs de b por nombre de puerto.
    Devuelve (primary_out, secondary_out).  Si los puertos no
    coinciden, fallback al orden de aparición."""
    outs = [s for s in fs.streams.values() if s.src == b.id]
    if len(outs) < 2:
        return outs[0] if outs else None, None
    def _match(s, kws):
        port = (s.src_port or "").lower()
        return any(k in port for k in kws)
    primary = next((s for s in outs if _match(s, primary_port_kws)), None)
    secondary = next((s for s in outs
                        if _match(s, secondary_port_kws) and s is not primary),
                       None)
    if primary is None and secondary is None:
        primary, secondary = outs[0], outs[1]
    elif primary is None:
        primary = next((s for s in outs if s is not secondary), None)
    elif secondary is None:
        secondary = next((s for s in outs if s is not primary), None)
    return primary, secondary


def _comp_masses(stream):
    """Dict {comp: mass_kg/y} desde stream.composition × mass_flow."""
    if not stream.composition or stream.mass_flow <= 0:
        return {}
    return {c: f * stream.mass_flow for c, f in stream.composition.items()}


def _write_output(s_out, total_mass, comp_masses, phase=None):
    """Setea composition + main_component + mass_flow del stream
    respetando _is_mass_locked y _is_comp_locked.  comp_masses son
    masas absolutas; se normalizan a fracciones internamente."""
    if total_mass <= 0:
        return
    if not _is_comp_locked(s_out):
        comp_frac = {c: m / total_mass for c, m in comp_masses.items()
                       if m > 1e-12}
        s_out.composition = comp_frac
        if comp_frac:
            s_out.main_component = max(comp_frac, key=comp_frac.get)
        if phase:
            s_out.phase = phase
    if not _is_mass_locked(s_out):
        s_out.mass_flow = total_mass


def _passthrough_to(feed, primary_out, secondary_out, phase=None):
    """Cuando un separador no puede operar (falta material esperado),
    pasa el feed completo al primary_out y deja secondary_out en 0.
    Preserva el balance global de masa (cero invención).  El warning
    explicativo lo emite el caller en `msgs`."""
    if feed is None or feed.mass_flow <= 0:
        return
    feed_comp_mass = {c: f * feed.mass_flow
                       for c, f in (feed.composition or {}).items()}
    _write_output(primary_out, feed.mass_flow, feed_comp_mass, phase=phase)
    if secondary_out is not None and not _is_mass_locked(secondary_out):
        secondary_out.mass_flow = 0.0
    if secondary_out is not None and not _is_comp_locked(secondary_out):
        secondary_out.composition = {}


# ── Separación mecánica unificada — helpers de fase/densidad ──
_SOLID_HINT = {
    "nacl", "sodium chloride", "salt", "sucrose", "sugar", "glucose_solid",
    "biomass", "cellulose", "starch", "potato_solids", "raw_water_solids",
    "pineapple_solids", "catalyst", "coke", "carbon", "silica", "sand",
    "caco3", "calcium carbonate", "clinker", "cement", "crystals", "solids",
    "gypsum", "ash", "lime",
}
_GAS_HINT = {
    "air", "nitrogen", "oxygen", "hydrogen", "methane", "ethane", "propane",
    "co", "carbon monoxide", "co2", "carbon dioxide", "ammonia", "chlorine",
    "cl2", "hcl", "so2", "so3", "nox", "no", "no2", "steam", "flue_gas",
    "natural gas", "syngas", "ethylene", "propylene",
}


def get_component_phase(name, T_C=None, P_bar=None):
    """Fase de un componente para separación mecánica: 'solid'|'liquid'|'gas'.

    Si se dan T_C y P_bar, usa un criterio de condensabilidad consciente de la
    presión (condensador a alta P): un componente condensa (→ 'liquid') si NO
    es supercrítico (T < Tc) y su presión de vapor Psat(T) < P_op.  Esto deja
    condensar NH3/metanol a 200/80 bar y mantiene N2/H2/CO (supercríticos) como
    gas, sin depender de parámetros NRTL binarios poco confiables.

    Sin T/P, cae al heurístico por nombre (hints + Tb)."""
    n = (name or "").strip().lower()
    if not n:
        return "liquid"
    if n in _SOLID_HINT or "solid" in n or n.endswith("_s"):
        return "solid"
    # Criterio de condensabilidad por presión (override de los gas-hints:
    # NH3/CO2/metanol son "gases" a ambiente pero condensan a alta P).
    if T_C is not None and P_bar is not None:
        try:
            import thermo_db as _td
            c = _td.get(name)
            if c is not None:
                if c.tc_c is not None and T_C >= c.tc_c:
                    return "gas"                # supercrítico → no condensa
                psat_kpa = c.vapor_pressure_kPa(T_C)
                if psat_kpa is not None:
                    return "liquid" if (psat_kpa / 100.0) < P_bar else "gas"
        except Exception:
            pass
    if n in _GAS_HINT or n.endswith("_g"):
        return "gas"
    try:
        import thermo_db as _td
        c = _td.get(name)
        if c is not None and c.tb_c and c.tb_c < 25.0:
            return "gas"
    except Exception:
        pass
    return "liquid"


def _component_density(name, T_C=25.0):
    """Densidad líquida [kg/m³] de un componente; thermo_db si está, si no
    heurística por nombre.  Usada para el split del decanter por densidad."""
    try:
        import thermo_db as _td
        c = _td.get(name)
        if c is not None:
            d = c.density_kg_m3(T_C)
            if d and d > 0:
                return float(d)
    except Exception:
        pass
    n = (name or "").lower()
    if "water" in n or "agua" in n:
        return 1000.0
    if "glycer" in n:
        return 1260.0
    if any(k in n for k in ("oil", "aceite", "biodiesel", "fame", "hexane",
                              "benzene", "toluene", "ethanol", "methanol",
                              "gasolin", "naphtha", "kerosene", "diesel")):
        return 850.0
    return 1000.0


def _sep_by_phase(b, feed, target_out, reject_out, target_phase, eff):
    """Reparte el feed entre target_out (fase objetivo × η) y reject_out
    (resto + fuga).  target_phase ∈ {'solid','liquid','vapor'} ('vapor' se
    compara contra fase 'gas').  Respeta locks vía _write_output."""
    if target_out is None or reject_out is None:
        return f"⚠ MechSep {b.name}: faltan 2 salidas conectadas"
    want = "gas" if target_phase in ("vapor", "gas") else target_phase
    comp_in = _comp_masses(feed)
    if not comp_in:
        return f"⚠ MechSep {b.name}: feed sin composición"
    # El user puede declarar explícitamente los componentes de la fase
    # objetivo (solid_components) y así override del heurístico get_component_phase.
    override = set(getattr(b, "solid_components", []) or [])
    # Condiciones de operación del separador para el criterio de
    # condensabilidad (condensador a alta P).  T_op_K del bloque si está;
    # si no, la T del feed.  P del bloque (P_op_bar / flash_P_bar).
    T_op_K = getattr(b, "T_op_K", 0.0) or 0.0
    T_C = (T_op_K - 273.15) if T_op_K > 0 else getattr(feed, "temperature", 25.0)
    P_bar = (getattr(b, "P_op_bar", 0.0) or getattr(b, "flash_P_bar", 0.0)
             or 1.013)

    def _is_target(c):
        if want == "solid" and override:
            return c in override
        return get_component_phase(c, T_C, P_bar) == want

    m_target_phase = sum(m for c, m in comp_in.items() if _is_target(c))
    if m_target_phase <= 0:
        phase_out = "gas" if want == "gas" else "liquid"
        _passthrough_to(feed, reject_out, target_out, phase=phase_out)
        return (f"⚠ MechSep {b.name}: feed sin fase '{target_phase}' "
                f"→ pass-through a reject")
    tgt_masses, rej_masses = {}, {}
    for c, m in comp_in.items():
        if _is_target(c):
            tgt_masses[c] = m * eff
            rej_masses[c] = m * (1.0 - eff)
        else:
            rej_masses[c] = m
    m_t = sum(tgt_masses.values())
    m_r = sum(rej_masses.values())
    tgt_phase_lbl = "liquid" if want != "gas" else "gas"
    rej_phase_lbl = "gas" if want == "gas" else "liquid"
    _write_output(target_out, m_t, tgt_masses, phase=tgt_phase_lbl)
    _write_output(reject_out, m_r, rej_masses, phase=rej_phase_lbl)
    return (f"✓ MechSep {b.name}: target={m_t:.0f} (fase {target_phase}, "
            f"η={eff:.2f}), reject={m_r:.0f}")


def _sep_liquid_liquid(fs, b, feed, eff):
    """Decanter por densidad: clasifica componentes en fase pesada/liviana
    según su densidad vs el promedio másico del feed.  La fase pesada
    (fase_pesada, target) recupera η de los componentes pesados; el resto
    fuga a la liviana."""
    heavy_out, light_out = _pick_outs_by_port(
        fs, b, ("pesada", "fondo", "solido", "producto"),
        ("liviana", "liviano", "tope", "liquido", "venteo"))
    if heavy_out is None or light_out is None:
        return f"⚠ Decanter {b.name}: faltan 2 salidas conectadas"
    comp_in = _comp_masses(feed)
    if not comp_in:
        return f"⚠ Decanter {b.name}: feed sin composición"
    T_C = getattr(feed, "temperature", 25.0)
    dens = {c: _component_density(c, T_C) for c in comp_in}
    m_tot = sum(comp_in.values())
    rho_avg = sum(dens[c] * comp_in[c] for c in comp_in) / m_tot if m_tot else 0
    heavy = {c for c in comp_in if dens[c] >= rho_avg + 1e-6}
    if not heavy or len(heavy) == len(comp_in):
        # Densidades indistinguibles → no se puede decantar; pass-through.
        _passthrough_to(feed, light_out, heavy_out, phase="liquid")
        return (f"⚠ Decanter {b.name}: densidades no separan "
                f"(ρ_avg={rho_avg:.0f}) → pass-through")
    h_masses, l_masses = {}, {}
    for c, m in comp_in.items():
        if c in heavy:
            h_masses[c] = m * eff
            l_masses[c] = m * (1.0 - eff)
        else:
            l_masses[c] = m
    m_h = sum(h_masses.values())
    m_l = sum(l_masses.values())
    _write_output(heavy_out, m_h, h_masses, phase="liquid")
    _write_output(light_out, m_l, l_masses, phase="liquid")
    return (f"✓ Decanter {b.name}: pesada={m_h:.0f}, liviana={m_l:.0f} "
            f"(η={eff:.2f}, ρ_avg={rho_avg:.0f})")


def solve_separators(fs):
    """Filtros y centrífugas con separator_active=True.

    Modelo:  feed con sólidos y líquidos → torta (cake) + madre.
    Parámetros del bloque:
        solids_recovery:  frac de los sólidos que se recupera en torta
        cake_moisture:    frac másica de líquido en la torta
        solid_components: lista de keys consideradas sólido (el resto
                          se trata como líquido madre)
    Si solid_components está vacío, usa el main_component del feed
    como sólido (heurística reasonable para procesos con un sólido
    dominante: azúcar, sal, almidón, biomasa).

    Puertos:
        Filter — belt:  producto=torta, venteo=madre
        Centrifuge — *: solido=torta, liquido=madre
    """
    msgs = []
    for b in fs.blocks.values():
        if getattr(b, "mech_sep_active", False):
            continue   # el modelo nuevo (solve_mechanical_separators) tiene prioridad
        if not getattr(b, "separator_active", False):
            continue
        feed = _pick_feed(fs, b)
        if feed is None:
            continue
        # Identificar puertos según eq_type
        if "centrifuge" in (b.eq_type or "").lower():
            cake_out, mother_out = _pick_outs_by_port(
                fs, b, ("solido",), ("liquido",))
        else:
            cake_out, mother_out = _pick_outs_by_port(
                fs, b, ("producto",), ("venteo", "liquido"))
        if cake_out is None or mother_out is None:
            msgs.append(f"⚠ Separator {b.name}: faltan 2 salidas conectadas")
            continue

        # Componentes sólido vs líquido
        solids = set(b.solid_components or [])
        if not solids and feed.main_component:
            solids = {feed.main_component}
        comp_in = _comp_masses(feed)
        m_solid_total  = sum(m for c, m in comp_in.items() if c in solids)
        m_liquid_total = sum(m for c, m in comp_in.items() if c not in solids)

        if m_solid_total <= 0:
            # Sin sólidos en el feed → pass-through al primer output
            # (preserva balance global; emite warning explicativo).
            _passthrough_to(feed, cake_out, mother_out, phase="liquid")
            msgs.append(f"⚠ Separator {b.name}: feed no tiene sólidos "
                         f"(solid_components={list(solids)}) → pass-through")
            continue

        rec = max(min(b.solids_recovery, 1.0), 0.0)
        moist = max(min(b.cake_moisture, 0.95), 0.0)
        # Reparto del sólido
        m_solid_cake = m_solid_total * rec
        m_solid_mother = m_solid_total - m_solid_cake
        # Reparto del líquido (la torta arrastra moist·M_cake_total)
        if (1 - moist) > 1e-6:
            m_cake_total = m_solid_cake / (1 - moist)
        else:
            m_cake_total = m_solid_cake
        m_liquid_cake = max(0.0, m_cake_total - m_solid_cake)
        if m_liquid_cake > m_liquid_total:
            m_liquid_cake = m_liquid_total      # no inventes líquido
        m_liquid_mother = m_liquid_total - m_liquid_cake

        # Composición por componente en cada salida
        cake_masses = {}
        mother_masses = {}
        for c, m in comp_in.items():
            if c in solids:
                if m_solid_total > 0:
                    cake_masses[c]   = m * rec
                    mother_masses[c] = m * (1 - rec)
            else:
                if m_liquid_total > 0:
                    frac = m / m_liquid_total
                    cake_masses[c]   = m_liquid_cake   * frac
                    mother_masses[c] = m_liquid_mother * frac
        m_cake_final   = sum(cake_masses.values())
        m_mother_final = sum(mother_masses.values())
        _write_output(cake_out,   m_cake_final,   cake_masses,   phase="liquid")
        _write_output(mother_out, m_mother_final, mother_masses, phase="liquid")
        msgs.append(
            f"✓ Separator {b.name}: cake={m_cake_final:.0f}, "
            f"mother={m_mother_final:.0f}, recov={rec:.2f}, "
            f"moist_cake={moist:.2f}"
        )
    return msgs


def solve_dryers(fs):
    """Secadores con dryer_active=True (Dryer — drum).

    Modelo:  feed húmedo → producto seco a final_moisture + venteo
    de vapor del moisture_component.

    Puertos: alimentacion → producto (seco) + venteo (vapor agua).
    """
    msgs = []
    for b in fs.blocks.values():
        if not getattr(b, "dryer_active", False):
            continue
        feed = _pick_feed(fs, b)
        if feed is None:
            continue
        dry_out, vent_out = _pick_outs_by_port(
            fs, b, ("producto",), ("venteo", "vapor"))
        if dry_out is None or vent_out is None:
            msgs.append(f"⚠ Dryer {b.name}: faltan 2 salidas conectadas")
            continue

        moist_c = b.moisture_component or "water"
        target_frac = max(min(b.final_moisture, 0.5), 0.0)
        comp_in = _comp_masses(feed)
        m_moist_in = comp_in.get(moist_c, 0.0)
        m_dry_solids = sum(m for c, m in comp_in.items() if c != moist_c)

        if m_moist_in <= 0:
            # Feed seco — nada que evaporar.  Pass-through al producto.
            _passthrough_to(feed, dry_out, vent_out, phase="liquid")
            msgs.append(f"⚠ Dryer {b.name}: feed sin '{moist_c}' "
                         f"(nada que evaporar) → pass-through")
            continue
        # Si la humedad actual del feed ya es ≤ target, NO hay que
        # evaporar nada (el dryer no PUEDE añadir moisture).  Pass-
        # through.  Sin este check, el solver inventaría agua para
        # alcanzar target_frac mayor → masa rota (bug fix).
        moist_actual = m_moist_in / feed.mass_flow
        if moist_actual <= target_frac:
            _passthrough_to(feed, dry_out, vent_out, phase="liquid")
            msgs.append(
                f"⚠ Dryer {b.name}: humedad actual {moist_actual*100:.1f}% "
                f"≤ target {target_frac*100:.1f}% — no se evapora, "
                f"pass-through")
            continue
        # M_dry_out_total: producto incluye solids + final_moisture·total
        if (1 - target_frac) > 1e-6:
            m_dry_out = m_dry_solids / (1 - target_frac)
        else:
            m_dry_out = m_dry_solids
        m_moist_in_dry = m_dry_out * target_frac
        if m_moist_in_dry > m_moist_in:
            m_moist_in_dry = m_moist_in    # final_moisture inalcanzable
        m_vapor = m_moist_in - m_moist_in_dry

        # Composición del producto seco
        dry_masses = {c: m for c, m in comp_in.items() if c != moist_c}
        if m_moist_in_dry > 0:
            dry_masses[moist_c] = m_moist_in_dry
        _write_output(dry_out, m_dry_out, dry_masses, phase="liquid")
        _write_output(vent_out, m_vapor, {moist_c: m_vapor}, phase="vapor")
        msgs.append(
            f"✓ Dryer {b.name}: dry={m_dry_out:.0f} ({target_frac*100:.1f}% "
            f"{moist_c}), vapor={m_vapor:.0f}"
        )
    return msgs


def solve_crystallizers(fs):
    """Cristalizadores con crystallizer_active=True.

    Modelo:  solute_component cristaliza con crystal_yield; el resto
    + solvente + impurezas van al licor madre.

    Puertos: alimentacion → producto (cristales) + venteo (madre).
    """
    msgs = []
    for b in fs.blocks.values():
        if not getattr(b, "crystallizer_active", False):
            continue
        feed = _pick_feed(fs, b)
        if feed is None:
            continue
        xtal_out, mother_out = _pick_outs_by_port(
            fs, b, ("producto",), ("venteo", "liquido"))
        if xtal_out is None or mother_out is None:
            msgs.append(f"⚠ Crystallizer {b.name}: faltan 2 salidas conectadas")
            continue

        solute = b.solute_component or feed.main_component
        if not solute:
            # Sin solute_component declarado → pass-through (no se
            # puede cristalizar lo desconocido).  Preserva balance.
            _passthrough_to(feed, mother_out, xtal_out, phase="liquid")
            msgs.append(f"⚠ Crystallizer {b.name}: solute_component vacío "
                         f"→ pass-through al licor madre")
            continue
        yield_ = max(min(b.crystal_yield, 1.0), 0.0)
        comp_in = _comp_masses(feed)
        m_solute_in = comp_in.get(solute, 0.0)
        if m_solute_in <= 0:
            # Solute no presente en feed → mismo manejo.
            _passthrough_to(feed, mother_out, xtal_out, phase="liquid")
            msgs.append(f"⚠ Crystallizer {b.name}: feed sin '{solute}' "
                         f"→ pass-through al licor madre")
            continue
        m_xtal = m_solute_in * yield_
        m_solute_mother = m_solute_in - m_xtal
        # Cristales = puro solute (modelo simple); madre = resto del feed
        xtal_masses = {solute: m_xtal}
        mother_masses = {c: m for c, m in comp_in.items() if c != solute}
        if m_solute_mother > 0:
            mother_masses[solute] = m_solute_mother
        m_mother = sum(mother_masses.values())
        _write_output(xtal_out, m_xtal, xtal_masses, phase="liquid")
        _write_output(mother_out, m_mother, mother_masses, phase="liquid")
        msgs.append(
            f"✓ Crystallizer {b.name}: xtals={m_xtal:.0f} "
            f"({solute}, yield={yield_:.2f}), mother={m_mother:.0f}"
        )
    return msgs


def solve_evaporators(fs):
    """Evaporadores con evaporator_active=True.

    Modelo:  feed → concentrado con concentration_factor (ratio de
    composición de sólidos) + vapor de volatile_component.

    Topología: la masa total se reduce M_out_total = M_in / CF;
    la diferencia se evapora como volatile_component puro.

    Puertos: alimentacion → producto (concentrado) + venteo (vapor).
    """
    msgs = []
    for b in fs.blocks.values():
        if not getattr(b, "evaporator_active", False):
            continue
        feed = _pick_feed(fs, b)
        if feed is None:
            continue
        conc_out, vap_out = _pick_outs_by_port(
            fs, b, ("producto",), ("venteo", "vapor"))
        if conc_out is None or vap_out is None:
            msgs.append(f"⚠ Evaporator {b.name}: faltan 2 salidas conectadas")
            continue

        cf = max(b.concentration_factor, 1.0)
        vol_c = b.volatile_component or "water"
        comp_in = _comp_masses(feed)
        m_vol_in   = comp_in.get(vol_c, 0.0)
        m_nonvol   = sum(m for c, m in comp_in.items() if c != vol_c)
        # M_concentrate = M_feed / CF
        m_concentrate = feed.mass_flow / cf
        m_vapor = feed.mass_flow - m_concentrate
        if m_vapor > m_vol_in:
            msgs.append(
                f"⚠ Evaporator {b.name}: CF={cf:.2f} requiere "
                f"{m_vapor:.0f} t de {vol_c}, feed solo tiene "
                f"{m_vol_in:.0f}.  Clampeando.")
            m_vapor = m_vol_in
            m_concentrate = feed.mass_flow - m_vapor
        m_vol_remaining = m_vol_in - m_vapor

        conc_masses = {c: m for c, m in comp_in.items() if c != vol_c}
        if m_vol_remaining > 0:
            conc_masses[vol_c] = m_vol_remaining
        _write_output(conc_out, m_concentrate, conc_masses, phase="liquid")
        _write_output(vap_out, m_vapor, {vol_c: m_vapor}, phase="vapor")
        msgs.append(
            f"✓ Evaporator {b.name}: conc={m_concentrate:.0f} (CF={cf:.2f}), "
            f"vapor={m_vapor:.0f} {vol_c}"
        )
    return msgs


def solve_cyclones(fs):
    """Ciclones gas/sólido con cyclone_active=True.

    Modelo: feed (gas + polvo) → producto (sólidos colectados) +
    venteo (gas limpio con escape de finos).

    El sólido se identifica por solid_components o por feed.main_component
    si la lista está vacía.  Todo lo demás se trata como gas portador.

    Puertos: alimentacion → producto (sólidos) + venteo (gas).
    """
    msgs = []
    for b in fs.blocks.values():
        if getattr(b, "mech_sep_active", False):
            continue   # el modelo nuevo (solve_mechanical_separators) tiene prioridad
        if not getattr(b, "cyclone_active", False):
            continue
        feed = _pick_feed(fs, b)
        if feed is None:
            continue
        sol_out, gas_out = _pick_outs_by_port(
            fs, b, ("producto",), ("venteo", "vapor", "gas"))
        if sol_out is None or gas_out is None:
            msgs.append(f"⚠ Cyclone {b.name}: faltan 2 salidas conectadas")
            continue

        solids = set(b.solid_components or [])
        if not solids and feed.main_component:
            solids = {feed.main_component}
        eff = max(min(b.collection_efficiency, 1.0), 0.0)
        comp_in = _comp_masses(feed)
        m_solid_total = sum(m for c, m in comp_in.items() if c in solids)
        if m_solid_total <= 0:
            # Sin sólidos en feed → todo el gas sale por venteo
            # (preserva balance global, no inventa polvo).
            _passthrough_to(feed, gas_out, sol_out, phase="gas")
            msgs.append(f"⚠ Cyclone {b.name}: feed sin sólido declarado "
                         f"({list(solids)}) → pass-through al gas")
            continue

        sol_masses = {}
        gas_masses = {}
        for c, m in comp_in.items():
            if c in solids:
                sol_masses[c] = m * eff
                gas_masses[c] = m * (1 - eff)
            else:
                gas_masses[c] = m       # gas portador todo a venteo
        m_sol = sum(sol_masses.values())
        m_gas = sum(gas_masses.values())
        _write_output(sol_out, m_sol, sol_masses, phase="liquid")
        _write_output(gas_out, m_gas, gas_masses, phase="gas")
        msgs.append(
            f"✓ Cyclone {b.name}: solids={m_sol:.0f} (η={eff:.2f}), "
            f"gas={m_gas:.0f}"
        )
    return msgs


def solve_mechanical_separators(fs):
    """Solver UNIFICADO de separadores mecánicos (filtro, centrífuga,
    ciclón, decanter).  Es el único punto que llama el loop de solve().

    - Honra los flags LEGACY separator_active / cyclone_active llamando a
      solve_separators / solve_cyclones (comportamiento idéntico al
      anterior → flowsheets viejos y ejemplos sin cambios).
    - Resuelve el modelo NUEVO mech_sep_active (phase-based, η declarada)
      para los 4 eq_types, incluido el Decanter — gravity (líquido-líquido
      por densidad) que antes no tenía solver.

    Un bloque nunca se procesa dos veces: los legacy usan separator_active/
    cyclone_active y los nuevos mech_sep_active (excluyentes en la práctica;
    si coexistieran, mech_sep_active tiene prioridad y se saltea el legacy)."""
    mech_ids = {b.id for b in fs.blocks.values()
                 if getattr(b, "mech_sep_active", False)}
    msgs = []
    msgs += solve_separators(fs)
    msgs += solve_cyclones(fs)
    for b in fs.blocks.values():
        if b.id not in mech_ids:
            continue
        feed = _pick_feed(fs, b)
        if feed is None:
            continue
        et = (b.eq_type or "").lower()
        eff = max(min(getattr(b, "mech_sep_efficiency", 0.95), 1.0), 0.0)
        target_phase = getattr(b, "mech_sep_target_phase", "solid") or "solid"
        if "decanter" in et:
            msgs.append(_sep_liquid_liquid(fs, b, feed, eff))
        elif "cyclone" in et:
            sol_out, gas_out = _pick_outs_by_port(
                fs, b, ("producto", "solido"), ("venteo", "vapor", "gas"))
            msgs.append(_sep_by_phase(b, feed, sol_out, gas_out,
                                       target_phase, eff))
        elif "centrifuge" in et:
            t_out, r_out = _pick_outs_by_port(
                fs, b, ("solido", "producto"), ("liquido", "venteo"))
            msgs.append(_sep_by_phase(b, feed, t_out, r_out,
                                       target_phase, eff))
        elif target_phase in ("liquid", "vapor", "gas"):
            # Knockout / condensador V-L: la fase objetivo se recupera por su
            # puerto (líquido condensado o vapor) y el resto sale por el otro.
            liq_kws = ("liquido", "liquid", "fondo", "pesada", "producto")
            vap_kws = ("vapor", "gas", "venteo", "tope", "liviana")
            if target_phase in ("vapor", "gas"):
                t_out, r_out = _pick_outs_by_port(fs, b, vap_kws, liq_kws)
            else:
                t_out, r_out = _pick_outs_by_port(fs, b, liq_kws, vap_kws)
            msgs.append(_sep_by_phase(b, feed, t_out, r_out,
                                       target_phase, eff))
        else:  # filtro y genéricos (sólido/líquido)
            t_out, r_out = _pick_outs_by_port(
                fs, b, ("producto", "solido"), ("venteo", "liquido"))
            msgs.append(_sep_by_phase(b, feed, t_out, r_out,
                                       target_phase, eff))
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
        # Separadores mecánicos (filtro/centrífuga/secador/cristalizador/
        # evaporador/ciclón) — sus outputs los escriben los solvers
        # dedicados con composiciones específicas (no promedio ponderado).
        if getattr(b, "separator_active", False):
            continue
        if getattr(b, "dryer_active", False):
            continue
        if getattr(b, "crystallizer_active", False):
            continue
        if getattr(b, "evaporator_active", False):
            continue
        if getattr(b, "cyclone_active", False):
            continue
        if getattr(b, "mech_sep_active", False):
            continue
        ins  = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        if not ins:
            continue
        # SEPARAR inputs proceso de inputs utility.  En un HX 4-port
        # (cool_in/cool_out separados de proceso_in/proceso_out), o
        # un reboiler con steam shell-side, los streams utility NO
        # deben mezclarse con los del proceso al calcular composición
        # del output proceso — sino contamina (ej. CW agua mezclada
        # con syngas reactor genera comp con 80 % water absurdo).
        ins_proc = [s for s in ins if s.role != "utility"]
        ins_util = [s for s in ins if s.role == "utility"]
        # outputs análogos (por nombre de puerto típico)
        utility_port_kw = ("cool_out", "steam_out", "cool_in",
                            "steam_in", "shell_in", "shell_out")
        outs_util = [s for s in outs
                       if any(k in (s.src_port or "").lower()
                                for k in utility_port_kw)
                       or s.role == "utility"]
        outs_proc = [s for s in outs if s not in outs_util]

        def _agg_comp(streams):
            total_m = sum(s.mass_flow for s in streams if s.mass_flow > 0)
            if total_m <= 0:
                return None
            agg = {}
            for s in streams:
                if s.mass_flow <= 0:
                    continue
                w_stream = s.mass_flow / total_m
                comp_dict = s.composition or {}
                if not comp_dict and s.main_component:
                    comp_dict = {s.main_component: 1.0}
                for comp, frac in comp_dict.items():
                    agg[comp] = agg.get(comp, 0.0) + w_stream * frac
            total = sum(agg.values())
            if total > 0:
                agg = {k: v/total for k, v in agg.items()}
            return agg

        # Propagar proceso → outputs proceso
        agg_proc = _agg_comp(ins_proc) if ins_proc else _agg_comp(ins)
        if agg_proc:
            for s_out in outs_proc:
                if _is_comp_locked(s_out):
                    continue
                s_out.composition = dict(agg_proc)
                if not s_out.main_component and agg_proc:
                    s_out.main_component = max(agg_proc, key=agg_proc.get)
                changed += 1

        # Propagar utility → outputs utility (mass-weighted de inputs
        # utility solamente)
        if outs_util and ins_util:
            agg_util = _agg_comp(ins_util)
            if agg_util:
                for s_out in outs_util:
                    if _is_comp_locked(s_out):
                        continue
                    s_out.composition = dict(agg_util)
                    if not s_out.main_component and agg_util:
                        s_out.main_component = max(agg_util,
                                                     key=agg_util.get)
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


def _is_pure_service_scc(scc_block_ids, fs):
    """True si el SCC existe SOLO vía corrientes auto_aux: es un lazo
    de CIRCULACIÓN DE SERVICIO (bomba→header→HX de cooling water /
    steam, creado por equipment_auxiliaries), no un reciclo de proceso.

    Un lazo así NO se resuelve por tear+Wegstein: no tiene feed externo
    (el balance en sus bloques da 0 con las auto_aux excluidas de la
    propagación) y su caudal es ANALÍTICO — m = Q/(cp·ΔT) desde el duty
    del HX, fijado por size_utility_streams.  Correr Wegstein producía
    el warning espurio "NO convergió (1 iter)" con el guess inicial.

    Criterio CONSERVADOR: todas las aristas internas del SCC deben ser
    auto_aux y debe haber al menos una.  Un SCC mixto (cualquier
    corriente de proceso en el ciclo) no se exime — va a Wegstein como
    siempre.  Nótese que los BLOQUES del lazo incluyen al HX de proceso
    (no es auto_aux): por eso el criterio es sobre las corrientes, no
    sobre los bloques."""
    streams = _streams_in_scc(scc_block_ids, fs)
    return bool(streams) and all(getattr(s, "auto_aux", False)
                                 for s in streams)


def _streams_in_scc(scc_block_ids, fs):
    """Streams cuyos src y dst están ambos en el SCC."""
    bids = set(scc_block_ids)
    return [s for s in fs.streams.values()
            if s.src in bids and s.dst in bids]


def _choose_tear(scc_streams, fs=None, scc_block_ids=None):
    """Elige el stream a tearear en un reciclo.

    Criterio reaction-aware (PR-G1): preferir el BACK-EDGE que cierra el
    ciclo — el stream del SCC cuyo bloque destino TAMBIÉN recibe un input
    externo al SCC (el mixer donde el recycle se reincorpora al feed
    fresco).  Ese es el recycle de diseño (p.ej. S-recycle→M-101 en
    haber_rec), NO el primer stream con flujo 0 (que el heurístico viejo
    elegía — típicamente S-mix, rompiendo el balance del loop).  Entre
    varios candidatos, se prefiere el marcado con role recycle/internal.

    Fallback (compat): primer stream sin mass_flow declarado.
    """
    if fs is not None and scc_block_ids is not None:
        bids = set(scc_block_ids)

        def _has_external_input(bid):
            return any(s.src not in bids and s.dst == bid and s.mass_flow > 0
                       for s in fs.streams.values())

        back_edges = [s for s in scc_streams if _has_external_input(s.dst)]
        if back_edges:
            def _rank(s):
                role = (getattr(s, "role", "") or "").lower()
                return (role in ("recycle",), role in ("recycle", "internal"))
            back_edges.sort(key=_rank, reverse=True)
            return back_edges[0]

    unknowns = [s for s in scc_streams if s.mass_flow <= 0]
    if unknowns:
        return unknowns[0]
    return None


def _nearest_external_feed(fs, scc_block_ids):
    """El feed externo de mayor caudal que entra al SCC (para el guess
    inicial de composición y T del tear)."""
    bids = set(scc_block_ids)
    cands = [s for s in fs.streams.values()
             if s.src not in bids and s.dst in bids and s.mass_flow > 0]
    if not cands:
        return None
    return max(cands, key=lambda s: s.mass_flow)


def _wegstein_scalar(x_n, f_new, x_prev, f_prev, lo=-5.0, hi=0.9995):
    """Paso Wegstein sobre un escalar.  Devuelve el próximo guess.

    q = s/(s−1) con s = (f_new−f_prev)/(x_n−x_prev).  Si s ∉ (lo, hi) o
    no hay historial, cae a sustitución directa (x_next = f_new).

    Nota PR-G1: hi=0.9995 (no 0.99) — los reciclos CON REACCIÓN son
    contracciones de factor cercano a 1 (p.ej. el lazo de amoníaco tiene
    pendiente ≈0.99 por la purga pequeña); con el clamp viejo en 0.99 esos
    casos caían a sustitución pura y NO convergían en 50 iter.  El método
    Wegstein es exacto para mapas afines, así que acelerar pendientes
    cercanas a 1 es seguro y es justo donde más se necesita."""
    if x_prev is None:
        return f_new
    denom = x_n - x_prev
    if abs(denom) < 1e-12:
        return f_new
    s = (f_new - f_prev) / denom
    if lo < s < hi:
        q = s / (s - 1.0)
        return (1.0 - q) * f_new + q * x_n
    return f_new


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


def _propagate_loop_with_chemistry(fs, max_inner=15):
    """Propaga el flowsheet COMPLETO incluyendo la química, para una
    iteración del tear: mixer (mass + composición mass-weighted), reactor
    (reactions_db/equilibrio → cambia composición; mass conservada) y la
    propagación de composición.  NO corre los splitters/separadores acá —
    esos se usan DESPUÉS para recalcular el tear (ver _recompute_tear)."""
    for _ in range(max_inner):
        changed = bool(_solve_mass_iteration(fs))
        auto_propagate_compositions(fs)
        solve_equilibrium_reactors(fs)
        auto_propagate_compositions(fs)
        if not changed:
            break


def _solve_recycle_wegstein(fs, scc_block_ids,
                            max_iter=50, tol=0.001):
    """Resuelve un reciclo via tear + Wegstein VECTORIAL (PR-G1).

    A diferencia del Wegstein escalar viejo (que tearaba sólo mass_flow con
    un balance Σin−Σout ciego a la reacción y elegía mal el tear), acá:

      1. _choose_tear elige el BACK-EDGE de diseño (reaction-aware).
      2. El estado del tear es un VECTOR {mass, composición, T}.
      3. Cada iteración propaga el loop ENTERO con la química (mixer +
         reactor de equilibrio/conversión) y RECALCULA el tear resolviendo
         su bloque fuente (splitter/separador), NO con un balance ingenuo.
      4. Convergencia por norma = max(|Δmass|/escala, max_i|Δx_i|, |ΔT|/esc).
      5. Wegstein sobre el ESCALAR masa total (mapa afín limpio — converge
         en pocos pasos); composición y T por sustitución directa (el lazo
         con reacción fija la composición en ~1 paso).

    Sólo se ejercita cuando el tear NO está lockeado (loops de diseño con
    el recycle deslockeado).  Los 40 ejemplos con tear lockeado resuelven
    por closure y nunca llegan acá (guard en solve()).

    Returns RecycleSolution con la trayectoria de masa del tear.
    """
    bids = set(scc_block_ids)
    scc_streams = _streams_in_scc(scc_block_ids, fs)
    tear = _choose_tear(scc_streams, fs, scc_block_ids)
    rs = RecycleSolution(
        cycle_blocks=[fs.blocks[bid].name for bid in scc_block_ids],
    )

    if tear is None:
        rs.converged = True
        return rs

    rs.tear_stream = tear.name

    # --- guess inicial del vector ---
    feed = _nearest_external_feed(fs, scc_block_ids)
    x_mass = _initial_guess(fs, scc_block_ids, tear)
    if tear.composition:
        x_comp = dict(tear.composition)
    elif feed and feed.composition:
        x_comp = dict(feed.composition)
    else:
        x_comp = {}
    x_T = tear.temperature if tear.temperature else (
        feed.temperature if feed else T_REF_C)
    rs.history.append(x_mass)

    # buffers Wegstein (sólo masa)
    xm_prev = None
    fm_prev = None

    for it in range(max_iter):
        # (a) limpiar los streams internos NO lockeados del SCC para que se
        #     recomputen desde el tear inyectado (si no, _solve_mass_iteration
        #     los ve "ya resueltos" y no los actualiza entre iteraciones).
        for s in scc_streams:
            if s.id != tear.id and not getattr(s, "mass_flow_locked", False):
                s.mass_flow = 0.0

        # (b) inyectar el guess y CONGELAR el tear (lock temporal) para que
        #     la propagación forward no lo pise antes de leer S-gases.
        x_mass = max(x_mass, 1e-6)
        tear.mass_flow = x_mass
        if x_comp:
            tear.composition = dict(x_comp)
        tear.temperature = x_T
        _was_locked = getattr(tear, "mass_flow_locked", False)
        tear.mass_flow_locked = True

        # (c) propagar el loop con química (mixer + reactor)
        _propagate_loop_with_chemistry(fs)

        # (d) recalcular el tear: desbloquear y dejar que su bloque fuente
        #     (splitter/separador) lo produzca desde el estado POST-reacción.
        tear.mass_flow_locked = _was_locked
        tear.mass_flow = 0.0
        solve_splitters(fs)
        solve_flashes(fs)
        solve_mechanical_separators(fs)
        solve_columns(fs)
        for _ in range(3):
            if not _solve_mass_iteration(fs):
                break
        auto_propagate_compositions(fs)

        f_mass = tear.mass_flow
        f_comp = dict(tear.composition or {})
        f_T = tear.temperature

        # bloque fuente sin caudal recomputable → no se puede tearear
        if f_mass <= 0:
            rs.converged = False
            rs.iterations = it + 1
            rs.final_value = x_mass
            return rs

        # (e) norma de convergencia sobre el vector completo
        scale = max(abs(x_mass), abs(f_mass), 1e-9)
        d_mass = abs(f_mass - x_mass) / scale
        keys = set(f_comp) | set(x_comp)
        d_x = max((abs(f_comp.get(k, 0.0) - x_comp.get(k, 0.0))
                   for k in keys), default=0.0)
        d_T = abs(f_T - x_T) / max(abs(f_T), 1.0)
        rs.history.append(f_mass)

        if max(d_mass, d_x, d_T) < tol:
            x_mass, x_comp, x_T = f_mass, f_comp, f_T
            rs.converged = True
            rs.iterations = it + 1
            rs.final_value = f_mass
            # propagación final con el tear convergido
            tear.mass_flow = f_mass
            tear.composition = dict(f_comp)
            tear.temperature = f_T
            return rs

        # (f) Wegstein sobre la masa total; composición/T por sustitución.
        x_next = _wegstein_scalar(x_mass, f_mass, xm_prev, fm_prev)
        xm_prev, fm_prev = x_mass, f_mass
        x_mass = x_next
        x_comp = f_comp
        x_T = f_T

    rs.converged = False
    rs.iterations = max_iter
    rs.final_value = x_mass
    return rs


# ======================================================
# ENTRYPOINT
# ======================================================

def apply_energy_streams(fs) -> List[str]:
    """E3 — Aplica las corrientes de energía (stream_kind='energy')
    al duty de los bloques conectados.

    Convención: para un Stream con stream_kind='energy', src=A, dst=B,
    energy_kW=Q (Q > 0):
        block_A.duty -= Q     (A cede Q kW → más enfriador)
        block_B.duty += Q     (B recibe Q kW → más calentador)

    Σ delta_duty = 0 por construcción → conservación de energía
    automática.

    IDEMPOTENCIA: la función guarda la última contribución aplicada
    en `block._energy_streams_delta` (attr runtime, NO serializado
    al JSON).  Al re-invocarse (re-solve), RESTA primero la
    contribución previa antes de sumar la nueva.  Sin esto, dos
    solves seguidos duplicarían el efecto (bug crítico).

    Streams flotantes (src<=0 o dst<=0) o con energy_kW=0 se ignoran.
    Bloques con duty_locked=True NO se tocan (respeta override del user).

    Devuelve lista de mensajes ✓/⚠ con los acoplamientos aplicados.
    """
    msgs: List[str] = []
    # 1. Restar contribuciones previas para garantizar idempotencia.
    for b in fs.blocks.values():
        prev = getattr(b, "_energy_streams_delta", 0.0)
        if abs(prev) > 1e-12 and not _is_duty_locked(b):
            b.duty -= prev
        b._energy_streams_delta = 0.0
    # 2. Aplicar las nuevas contribuciones, tracking en attr runtime.
    for s in fs.streams.values():
        if getattr(s, "stream_kind", "mass") != "energy":
            continue
        if s.src <= 0 or s.dst <= 0:
            continue          # flotante o sentinel
        Q = float(getattr(s, "energy_kW", 0.0) or 0.0)
        if abs(Q) < 1e-9:
            continue
        b_src = fs.blocks.get(s.src)
        b_dst = fs.blocks.get(s.dst)
        if b_src is None or b_dst is None:
            msgs.append(f"⚠ Energy stream {s.name}: bloque src/dst "
                         f"inexistente, saltado.")
            continue
        # src cede Q kW (más negativo)
        if not _is_duty_locked(b_src):
            b_src.duty -= Q
            b_src._energy_streams_delta = (
                getattr(b_src, "_energy_streams_delta", 0.0) - Q)
        # dst recibe Q kW (más positivo)
        if not _is_duty_locked(b_dst):
            b_dst.duty += Q
            b_dst._energy_streams_delta = (
                getattr(b_dst, "_energy_streams_delta", 0.0) + Q)
        msgs.append(f"✓ Energy stream {s.name}: {b_src.name} → "
                     f"{b_dst.name}, Q={Q:.1f} kW (duties acoplados)")
    return msgs


def solve(fs, max_iter=MAX_ITER):
    """Resuelve mass + energy balance sobre el flowsheet in-place.

    Args:
        fs: Flowsheet con blocks y streams.
        max_iter: límite de iteraciones (default 30).

    Returns:
        SolverResult.
    """
    result = SolverResult()
    fs._solver_warnings = []      # reset de warnings acumulados por corrida

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

    # 3. Wegstein por reciclo no resuelto.  Los lazos PUROS de
    #    servicio (todas las aristas auto_aux) quedan exentos: su
    #    caudal lo fija analíticamente size_utility_streams desde el
    #    duty del HX — el tearing ahí solo producía un "NO convergió"
    #    espurio (sin feed externo, _balance_at_block da 0).
    service_loop_sccs = []
    for scc in recycle_sccs:
        scc_streams = _streams_in_scc(scc, fs)
        if all(s.mass_flow > 0 for s in scc_streams):
            continue  # ya está resuelto por closure
        if _is_pure_service_scc(scc, fs):
            service_loop_sccs.append(scc)
            continue
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

    # Mensajes de los unit ops (4cb).  Declarados ACÁ porque
    # _run_unit_ops_loop (definida más abajo) los escribe vía nonlocal y
    # puede invocarse desde DENTRO del loop de reactores cuando el recycle
    # del reactor pasa por un separador/columna.
    flash_msgs = []
    col_msgs = []
    split_msgs = []
    sep_msgs = []
    dry_msgs = []
    cry_msgs = []
    evp_msgs = []
    cyc_msgs = []

    def _run_unit_ops_loop():
        """Una corrida completa del loop de unit ops (splitters, flashes,
        separadores, columnas).  Extraída como función para poder llamarla
        TAMBIÉN dentro del loop de reactores (4c): cuando un reactor está en
        un recycle loop cuyo tear pasa por un flash/columna (p.ej. el
        recycle de metanol de industrial_complete vuelve por V-201/V-203),
        los separadores deben correr ENTRE iteraciones del reactor para
        propagar la composición del recycle de vuelta al inlet.  Sin esto el
        reactor veía un inlet sin recycle y el solve no era idempotente
        (1er solve ≠ 2do)."""
        nonlocal split_msgs, flash_msgs, sep_msgs, cyc_msgs
        nonlocal dry_msgs, cry_msgs, evp_msgs, col_msgs
        for _outer in range(5):
            prev_count = sum(1 for s in fs.streams.values() if s.composition)
            # También rastrear masa resuelta: en un segundo solve (p.ej. tras
            # instanciar auxiliares) las composiciones PERSISTEN de la corrida
            # anterior, así que cortar solo por 'composición estable' puede
            # terminar el loop ANTES de que un splitter/flash reciba su feed ya
            # propagado en esta pasada (su salida quedaría en 0).  Seguir
            # iterando mientras se resuelva masa nueva evita ese corte temprano.
            prev_mass = sum(1 for s in fs.streams.values() if s.mass_flow > 0)
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
            # Separadores mecánicos UNIFICADOS (filtro/centrífuga/ciclón/
            # decanter) — un solo solver que honra los flags legacy y el
            # modelo nuevo mech_sep_active.  Luego secadores, cristalizadores,
            # evaporadores.
            sep_msgs = solve_mechanical_separators(fs)
            cyc_msgs = []
            for _ in range(3):
                if not _solve_mass_iteration(fs):
                    break
            dry_msgs = solve_dryers(fs)
            for _ in range(3):
                if not _solve_mass_iteration(fs):
                    break
            cry_msgs = solve_crystallizers(fs)
            for _ in range(3):
                if not _solve_mass_iteration(fs):
                    break
            evp_msgs = solve_evaporators(fs)
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
            new_mass = sum(1 for s in fs.streams.values() if s.mass_flow > 0)
            if new_count == prev_count and new_mass == prev_mass:
                break

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
                if _is_pure_service_scc(scc, fs):
                    continue   # lazo de servicio: caudal analítico
                scc_streams = _streams_in_scc(scc, fs)
                if not all(s.mass_flow > 0 for s in scc_streams):
                    _solve_recycle_wegstein(fs, scc, max_iter=10)
            # Correr los separadores/columnas AHORA para propagar la
            # composición del recycle de vuelta al inlet del reactor antes
            # de la próxima iteración.  Sin esto, si el tear del recycle
            # pasa por un flash/columna (industrial_complete: el metanol
            # vuelve por V-201/V-203), el reactor veía un inlet sin recycle
            # y el solve no era idempotente.  _run_unit_ops_loop se define
            # más abajo pero ya está ligada en este scope al ejecutarse.
            _run_unit_ops_loop()
            auto_propagate_compositions(fs)
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

    # 4cb. Unit ops automáticos (splitters, flashes, columnas).  La función
    #      _run_unit_ops_loop ya corrió DENTRO del loop de reactores cuando
    #      había reactor en SCC; acá se asegura una pasada final (idempotente)
    #      para flowsheets sin reactor en recycle.
    _run_unit_ops_loop()

    for m in (split_msgs + flash_msgs + col_msgs
              + cyc_msgs + sep_msgs + dry_msgs + cry_msgs + evp_msgs):
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

    # 4d-bis.  Corrientes de energía (E3): aplican acoplamiento de
    # duties entre bloques conectados.  Conservación automática
    # (Σ delta_duty = 0).  Solo procesa streams kind='energy' con
    # src/dst válidos; los flotantes (src<=0 o dst<=0) se ignoran.
    e_msgs = apply_energy_streams(fs)
    for m in e_msgs:
        if m.startswith("✗"):
            result.energy_balance_errors.append(m)
        elif m.startswith("⚠"):
            result.energy_warnings.append(m)

    # 4e. Solver hidráulico acoplado: bombas/compresores se auto-
    #     dimensionan iterativamente para cubrir ΔP de tuberías +
    #     equipos downstream hasta el próximo stream con P locked.
    #     Si no hay nada locked, usa los ΔP declarados directamente.
    p_msgs = solve_pressure_hydraulic(fs)
    # POST-PASO: anclar a 1 atm los streams conectados a bloques Ambient
    # (intakes de aire, venteos, chimeneas).  Se hace DESPUÉS de
    # solve_pressure_hydraulic porque su propagation ignora locks que
    # añadimos artificialmente y termina pisando gradientes que setean
    # los unit-op solvers (p.ej. el +0.1 bar del bottom de columna).
    # Al final del flujo: bottoms con su gradiente correcto + venteos
    # a P atmosférica, ambos coherentes.
    try:
        anchor_ambient_pressures(fs)
    except Exception:
        pass
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

    # Materializar el flujo de las corrientes de servicio (utility) de HX
    # desde el duty ANTES de listar unresolved (si no, quedarían marcadas
    # como sin resolver por tener mass_flow=0 al momento del chequeo).
    try:
        size_utility_streams(fs)
    except Exception:
        pass

    # Reporte informativo de los lazos de servicio exentos de Wegstein
    # (paso 3).  Se emite ACÁ, después de size_utility_streams, para
    # poder mostrar el caudal de circulación ya fijado analíticamente.
    for scc in service_loop_sccs:
        try:
            names = [fs.blocks[bid].name for bid in scc]
            flows = [s.mass_flow for s in _streams_in_scc(scc, fs)
                     if s.mass_flow > 0]
            m_txt = f"m = {max(flows):.4g} tm/año" if flows                 else "m pendiente (HX sin duty)"
            result.service_loops.append(
                f"ℹ Lazo de servicio detectado ({' → '.join(names)}): "
                f"circulación fija analítica, {m_txt}")
        except Exception:
            pass

    # Lado-aire de los air-coolers (role='ambient'): dimensionar desde el
    # duty.  size_utility_streams sólo cubre role='utility', así que el aire
    # quedaba en mass_flow=0 → marcado unresolved y, peor, bloqueaba la
    # deducción de la corriente de PROCESO de salida del air-cooler (con el
    # intake/venteo sin resolver el balance Σin=Σout tenía >1 incógnita).
    try:
        size_air_cooler_streams(fs)
    except Exception:
        pass

    # Re-cerrar el balance de masa ahora que las auxiliares (utility + aire)
    # tienen flujo: corrientes de proceso que dependían de ellas (p.ej. el
    # condensado de un condensador air-cooled) ya pueden deducirse.
    try:
        for _ in range(MAX_ITER):
            if not _solve_mass_iteration(fs):
                break
    except Exception:
        pass

    # Computar duty de las bombas de circulación auto_aux (lazos cerrados
    # CW/jacket/kettle) ahora que el flujo del lazo está dimensionado.
    # compute_utilities_from_duties lo carga al OPEX eléctrico abajo.
    try:
        size_aux_circulation_pumps(fs)
    except Exception:
        pass

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
    # Auditoría de consistencia unificada (Frente A).  Reemplaza al viejo
    # _check_component_balance: el Detector 2 del auditor integra esa
    # lógica.  No rompe solve() si el auditor falla.
    try:
        from flowsheet_consistency_audit import audit_flowsheet
        result.audit_report = audit_flowsheet(fs)
        for f in result.audit_report.findings:
            line = f"[{f.category}] {f.message}"
            if f.severity == 'error':
                result.consistency_errors.append(line)
            elif f.severity == 'warning':
                result.consistency_warnings.append(line)
            # 'info' sólo queda en el report estructurado
        # compat UI vieja: component_warnings se nutre del auditor
        result.component_warnings = [
            f.message
            for f in result.audit_report.by_category('component_balance')]
    except Exception as e:
        result.consistency_errors.append(
            f"[audit] auditor falló: {type(e).__name__}: {e}")
    # role hygiene — warnings (no errors) sobre streams con role
    # inconsistente que pueden ensuciar costing económico
    result.component_warnings.extend(_check_stream_roles(fs))
    # sizing + diagnósticos térmicos de HX (persiste block._hx_diagnostics;
    # re-dimensiona sólo los HX sin S_locked)
    _size_heat_exchangers(fs, result)
    # auditoría térmica de HX (advisory, no rompe success)
    result.hx_warnings            = _check_heat_exchangers(fs)
    # Conciencia física del solver (PR-A): barrido advisory de cierre de
    # energía por bloque + checks de equipo (T descarga, duty espurio,
    # placeholder, split-lock, duty>S, signo).  Canal separado que NO
    # altera overall_status (preserva el invariante golden byte-idéntico).
    try:
        result.awareness_warnings = _compute_awareness_warnings(fs)
    except Exception as e:
        result.awareness_warnings = [
            f"[W-AWARE-ERR] auditoría de conciencia falló: "
            f"{type(e).__name__}: {e}"]
    # energy balance errors quedan deshabilitados (no comparables al Cp
    # simple — comentado en _check_energy_balance del editor)

    result.success = (
        not result.unresolved_streams and
        not result.mass_balance_errors
    )

    # 5. Calcular estados visuales (color UI: verde/azul/amarillo/rojo)
    _compute_status_per_item(fs, result)
    return result


def _eq_categoria(b):
    """Categoría de costeo del bloque (equipment_costs.EQUIPMENT_DATA)."""
    try:
        import equipment_costs as _ec
        return (_ec.EQUIPMENT_DATA.get(b.eq_type, {}) or {}).get("categoria", "")
    except Exception:
        return ""


def _block_reaction_status(b):
    """Clasifica las reactions declaradas del bloque.

    Devuelve (has_rxn_tags, any_resolves, placeholder_bonus):
      has_rxn_tags    — el bloque declara al menos una reacción.
      any_resolves    — alguna existe curada en reactions_db (reacción REAL).
      placeholder_bonus — lista de (rid_placeholder, rid_base) donde el id
                        tiene forma RNNN_PLACEHOLDER y RNNN SÍ existe en la DB
                        (p.ej. ldpe usa R027_PLACEHOLDER y R027 está curada).
    """
    rids = list(getattr(b, "reactions", None) or [])
    if not rids:
        return (False, False, [])
    try:
        import reactions_db as _rdb
    except Exception:
        return (True, True, [])        # sin catálogo → asumir reacción real
    any_resolves = False
    bonus = []
    suf = "_PLACEHOLDER"
    for rid in rids:
        resolved = False
        try:
            resolved = _rdb.get(rid) is not None
        except Exception:
            resolved = False
        if resolved:
            any_resolves = True
            continue
        if rid.endswith(suf):
            base = rid[:-len(suf)]
            try:
                if base and _rdb.get(base) is not None:
                    bonus.append((rid, base))
            except Exception:
                pass
    return (True, any_resolves, bonus)


def _comp_approx_equal(c1, c2, tol=0.02):
    """True si dos composiciones (dict componente→fracción másica) son
    aproximadamente iguales: ambas no vacías, MISMO conjunto de componentes
    y |Δx_i| < tol para todos.  Se usa en [W-PURGE-ABS] (PR-A2.2) para
    distinguir un SPLIT FÍSICO (purga: misma comp en ambas ramas) de un
    SEPARADOR (comp distinta).  Conservador: comp vacía/None → False."""
    c1 = c1 or {}
    c2 = c2 or {}
    if not c1 or not c2:
        return False
    if set(c1) != set(c2):
        return False
    return all(abs(c1[k] - c2.get(k, 0.0)) < tol for k in c1)


def _compute_awareness_warnings(fs):
    """PR-A — Conciencia física del solver.

    Barrido advisory que EXPONE inconsistencias físicas latentes SIN
    corregir ningún balance (no toca duties, Ts, composición ni masa) y
    SIN alterar overall_status.  Cada línea lleva un tag estable [W-...]
    para poder grepearla en tests.  Devuelve list[str].

    Checks:
      [W-ENERGY-BLOCK] cierre global de energía por bloque
      [W-COMP-T]       T de descarga de compresor > 250 °C
      [W-T-OVERRIDE]   T declarada pisada por el solver
      [W-MIXER-DUTY]/[W-TANK-DUTY] duty espurio en equipo pasivo
      [W-PLACEHOLDER]  reactor estructural (química via outputs locked)
      [W-SPLIT-LOCK]   flujo lockeado vs fracción de splitter
      [W-DUTY-S]       |duty| > S (costeo subestimado)
      [W-SIGN]         signo de duty inconsistente con el tipo de equipo
      [W-PURGE-ABS]    purga absoluta lockeada dentro de un loop de reciclo
    """
    from flowsheet_model import T_REF_C
    try:
        import equipment_ports as _ep
    except Exception:
        _ep = None
    warns = []

    def _ins(b):
        return [s for s in fs.streams.values()
                if s.dst == b.id and not getattr(s, "auto_aux", False)]
    def _outs(b):
        return [s for s in fs.streams.values()
                if s.src == b.id and not getattr(s, "auto_aux", False)]

    # ── Mapa de loops de reciclo (REUSA la detección de SCC del solver,
    #    NO un DFS paralelo) para [W-PURGE-ABS].  Para cada bloque guarda:
    #      scc_of[bid]      → set de bids de su SCC de reciclo (o None)
    #      determined_bids  → loops YA controlados por un splitter
    #                          recirculante (no subdeterminados → no avisar)
    #    Los lazos de servicio puro (cooling water, etc.) se excluyen: su
    #    caudal es analítico, no hay subdeterminación de proceso.
    scc_of: Dict[int, set] = {}
    determined_bids: set = set()
    try:
        for scc in _strongly_connected_components(fs):
            if not _is_recycle_scc(scc, fs):
                continue
            if _is_pure_service_scc(scc, fs):
                continue
            sccset = set(scc)
            determined = any(
                getattr(fs.blocks[bid], "splitter_active", False)
                and any(s.src == bid and s.dst in sccset
                        for s in fs.streams.values())
                for bid in scc)
            for bid in scc:
                scc_of[bid] = sccset
                if determined:
                    determined_bids.add(bid)
    except Exception:
        scc_of = {}
        determined_bids = set()

    for b in fs.blocks.values():
        if getattr(b, "auto_aux", False):
            continue
        cat        = _eq_categoria(b)
        eqt        = b.eq_type or ""
        duty       = float(getattr(b, "duty", 0.0) or 0.0)
        has_rxn, rxn_resolves, ph_bonus = _block_reaction_status(b)
        is_placeholder = has_rxn and not rxn_resolves
        is_electrical  = bool(_ep and _ep.is_electrical_equipment(eqt))
        ins  = _ins(b)
        outs = _outs(b)

        # ── 1.5 [W-PLACEHOLDER] reactor estructural ──────────────────
        if is_placeholder:
            msg = (f"[W-PLACEHOLDER] {b.name}: reactor estructural "
                   f"(chemistry via outputs locked): exento de balance "
                   f"elemental y de energía.")
            for rid, base in ph_bonus:
                msg += (f" La reacción {base} existe curada en reactions_db "
                        f"— considerar usarla (hoy declarada como {rid}).")
            warns.append(msg)

        # ── 1.1 [W-ENERGY-BLOCK] cierre global de energía por bloque ──
        # Los reactores placeholder están EXENTOS (química hardcodeada via
        # outputs locked; su balance de energía no es evaluable) — los
        # cubre [W-PLACEHOLDER].  El resto de bloques con ins Y outs se
        # barre con _stream_enthalpy_kW.
        if ins and outs and not is_placeholder:
            h_in = h_out = 0.0
            ok = True
            for s in ins:
                h = _stream_enthalpy_kW(s)
                if h is None:
                    ok = False; break
                h_in += h
            if ok:
                for s in outs:
                    h = _stream_enthalpy_kW(s)
                    if h is None:
                        ok = False; break
                    h_out += h
            if ok:
                q_rxn = 0.0
                hor = float(getattr(b, "heat_of_reaction", 0.0) or 0.0)
                if hor != 0:
                    m_in = sum(s.mass_flow * TM_TO_KG / SEC_PER_YEAR
                               for s in ins)
                    q_rxn = -m_in * hor
                resid = h_out - h_in - duty - q_rxn
                scale = max(abs(h_in), abs(h_out), abs(duty), 10.0)
                if abs(resid) > 10.0 and abs(resid) / scale > 0.10:
                    if has_rxn and rxn_resolves:
                        cause = ("reactor con reacción real → posible signo "
                                 "de Q_rxn o Ts de producto inconsistentes")
                    elif is_electrical:
                        cause = (f"duty declarado ({duty:.0f} kW) ≠ ΔH de "
                                 f"corrientes ({h_out - h_in:.0f} kW)")
                    else:
                        cause = "Ts de corrientes no cierran el balance"
                    warns.append(
                        f"[W-ENERGY-BLOCK] {b.name}: cierre de energía "
                        f"resid={resid:+.0f} kW (escala {scale:.0f}, "
                        f"{resid / scale * 100:+.0f}%) — {cause}")

        # ── 1.2 [W-COMP-T] T de descarga de compresor/turbina ────────
        if cat == "Compressors":
            hot = None
            for s in outs:
                if hot is None or s.temperature > hot.temperature:
                    hot = s
            if hot is not None and hot.temperature > 250.0:
                warns.append(
                    f"[W-COMP-T] {b.name}/{hot.name}: descarga isentrópica "
                    f"de 1 etapa = {hot.temperature:.0f} °C (>250 °C, límite "
                    f"mecánico API 618). Planta real usa compresión "
                    f"multietapa con intercooling. Considerar dividir en N "
                    f"etapas o declarar T_descarga con lock.")

        # ── 1.4 [W-MIXER-DUTY]/[W-TANK-DUTY] duty en equipo pasivo ───
        if abs(duty) > 5.0:
            if eqt.startswith("Mixer"):
                warns.append(
                    f"[W-MIXER-DUTY] {b.name}: equipo pasivo (mixer "
                    f"estático) con duty espurio {duty:.0f} kW — revisar Ts "
                    f"de entrada/salida.")
            elif cat == "Storage" or "tank" in eqt.lower():
                warns.append(
                    f"[W-TANK-DUTY] {b.name}: equipo pasivo (tanque de "
                    f"almacenamiento) con duty espurio {duty:.0f} kW — "
                    f"revisar Ts de entrada/salida.")

        # ── 1.6 [W-SPLIT-LOCK] fracción vs flujo lockeado ────────────
        if getattr(b, "splitter_active", False):
            fr = list(getattr(b, "splitter_fractions", []) or [])
            sum_in = sum(s.mass_flow for s in ins)
            if sum_in > 0:
                for k, s in enumerate(outs):
                    if k >= len(fr):
                        break
                    if not getattr(s, "mass_flow_locked", False):
                        continue
                    expected = sum_in * fr[k]
                    rel = abs(s.mass_flow - expected) / max(abs(expected), 1.0)
                    if rel > 0.02:
                        warns.append(
                            f"[W-SPLIT-LOCK] {b.name}/{s.name}: flujo lockeado "
                            f"({s.mass_flow:.0f} t/a) contradice la fracción "
                            f"splitter {fr[k]:.3f} (esperado {expected:.0f} "
                            f"t/a) — posible error de orden fracción↔stream.")

        # ── 1.7 [W-DUTY-S] duty > S ──────────────────────────────────
        if cat in ("Fired heaters", "Compressors"):
            S = float(getattr(b, "S", 0.0) or 0.0)
            if S > 0 and abs(duty) > S * 1.02:
                warns.append(
                    f"[W-DUTY-S] {b.name}: S declarado ({S:.0f} kW) menor que "
                    f"|duty| calculado ({abs(duty):.0f} kW) — costeo "
                    f"subestimado.")

        # ── 1.8 [W-SIGN] signo de duty inconsistente ─────────────────
        if cat == "Fired heaters" and duty < -1.0:
            warns.append(
                f"[W-SIGN] {b.name}: duty {duty:+.0f} kW (fired heater debería "
                f"APORTAR calor, duty>0) — signo inconsistente con el tipo de "
                f"equipo ({eqt}).")
        elif "air cooler" in eqt and duty > 1.0:
            warns.append(
                f"[W-SIGN] {b.name}: duty {duty:+.0f} kW (air cooler debería "
                f"EXTRAER calor, duty<0) — signo inconsistente con el tipo de "
                f"equipo ({eqt}).")

        # ── [W-PURGE-ABS] purga absoluta dentro de un loop (PR-A2) ────
        # Convención PR-G1: una purga que reparte el gas de un loop de
        # reciclo debe modelarse como FRACCIÓN (splitter_active), no como
        # stream de flujo absoluto lockeado — con purga absoluta el caudal
        # de recirculación queda SUBDETERMINADO (cualquier valor cierra el
        # balance, sin punto fijo único → Wegstein no converge).  Patrón
        # detectado: bloque NO-splitter en un SCC de reciclo de proceso aún
        # NO determinado por un splitter recirculante, con una salida
        # lockeada TERMINAL (sale del loop = purga) Y una salida hermana
        # que RECIRCULA (vuelve al loop).  Las purgas TERMINALES (bloque
        # fuera de todo loop) son specs de diseño legítimas → no avisar.
        #
        # PR-A2.2 — discriminador por COMPOSICIÓN (no por rol): una PURGA
        # es un SPLIT FÍSICO — la salida que purga y la que recircula
        # llevan la MISMA composición (mismo gas dividido).  Un SEPARADOR
        # reparte composiciones DISTINTAS a cada salida (cada una es una
        # fase/producto/corte).  Solo el split físico subdetermina el
        # caudal del reciclo, así que [W-PURGE-ABS] solo dispara cuando la
        # composición POST-solve de la purga ≈ la de una hermana
        # recirculante (|Δx_i|<tol, mismo set de componentes).  El rol
        # (product/waste/...) NO discrimina: la purga canónica de haber_rec
        # es role=waste.  Si alguna comp está sin resolver → conservador,
        # no dispara.
        sccset = scc_of.get(b.id)
        if (sccset is not None
                and b.id not in determined_bids
                and not getattr(b, "splitter_active", False)
                and len(outs) >= 2):
            locked_terminal = [s for s in outs
                               if getattr(s, "mass_flow_locked", False)
                               and s.dst not in sccset]
            recirc = [s for s in outs if s.dst in sccset]
            purga = next(
                (s for s in locked_terminal
                 if any(_comp_approx_equal(s.composition, r.composition)
                        for r in recirc)),
                None)
            if purga is not None:
                warns.append(
                    f"[W-PURGE-ABS] {b.name}: purga/reparto con flujo absoluto "
                    f"lockeado ({purga.name} = {purga.mass_flow:.0f} t/a) "
                    f"dentro de un loop de reciclo. El caudal de recirculación "
                    f"queda subdeterminado — modelar como fracción de split "
                    f"(splitter_active) para que el balance tenga punto fijo "
                    f"único (ver convención PR-G1).")

    # ── 1.3 [W-T-OVERRIDE] T declarada pisada por el solver ──────────
    for s in fs.streams.values():
        td = getattr(s, "_t_declared", None)
        if td is None:
            continue
        if abs(td - T_REF_C) < 0.01:
            continue                       # T declarada == 25 → sin intención
        if getattr(s, "temperature_locked", False):
            continue                       # locked → el solver la respeta
        if abs(s.temperature - td) > 10.0:
            warns.append(
                f"[W-T-OVERRIDE] {s.name}: T declarada {td:.0f}°C fue "
                f"recalculada a {s.temperature:.0f}°C (intención de diseño "
                f"perdida — lockear si {td:.0f}°C es correcta).")

    return warns


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
