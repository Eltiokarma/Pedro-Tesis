"""
Análisis de grados de libertad (DOF) de un flowsheet.

Audita la estructura del flowsheet ANTES de correr el solver:
  · Determina qué streams quedan con mass_flow indeterminable
    (no lockeado ni propagable topológicamente).
  · Identifica bloques con energy balance no cerrable (reactor
    isotermal sin T_op_K, HX sin specs energéticos).
  · Identifica composiciones que no pueden inferirse.

NO reemplaza al solver — es un análisis estructural a priori.
Detecta los casos donde el solver va a fallar por subspecificación,
ignorando los casos donde el solver tiene defaults razonables
(ej. HX sin duty → Q=0; pump sin ΔP → ΔP=0).

Referencia: análogo al "Solver Status" / DOF report de Aspen Plus,
pero adaptado a las heurísticas de nuestro solver.
"""
from dataclasses import dataclass, field
from typing import List, Set, Dict
from flowsheet_model import Flowsheet


@dataclass
class StreamStatus:
    name: str
    mass_status: str = "unknown"   # locked | propagated | unknown
    comp_status: str = "unknown"
    T_status:    str = "default"
    P_status:    str = "default"


@dataclass
class BlockStatus:
    name: str
    eq_type: str
    mass_dof:   int = 0
    energy_dof: int = 0
    comp_dof:   int = 0
    overall:    str = "ok"   # ok | under | over
    notes:      List[str] = field(default_factory=list)

    @property
    def total_dof(self) -> int:
        return self.mass_dof + self.energy_dof + self.comp_dof


@dataclass
class DOFReport:
    n_blocks:     int = 0
    n_streams:    int = 0
    n_components: int = 0
    total_dof:    int = 0
    n_ok:         int = 0
    n_under:      int = 0
    n_over:       int = 0
    blocks:       List[BlockStatus]  = field(default_factory=list)
    streams:      List[StreamStatus] = field(default_factory=list)
    n_indeterminable_mass: int = 0
    summary:      str = ""
    suggestions:  List[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _is_hx(eq_type: str) -> bool:
    s = (eq_type or "").lower()
    return any(k in s for k in (
        "exch", "heater", "cooler", "evap", "reboiler", "condenser"
    ))


def _is_column(eq_type: str) -> bool:
    s = (eq_type or "").lower()
    return "tower" in s or "column" in s


# ─────────────────────────────────────────────────────────────
# Propagación topológica de mass_flow
# ─────────────────────────────────────────────────────────────

def _determinable_masses(fs: Flowsheet) -> Set[int]:
    """Devuelve set de stream.id cuya mass_flow se puede determinar
    desde locks + balance topológico (recursivo).

    Reglas:
      · Stream lockeado → determinable.
      · Bloque con todos los inputs determinables + N-1 outputs
        determinables (o N-1 fracciones de splitter) → último output
        determinable.
      · Bloque con N-1 streams determinables y 1 unknown → el unknown
        es determinable por balance.
      · Bloque con 1 input + 1 output: si uno está determinable, el
        otro también (pass-through).
    """
    det: Set[int] = {s.id for s in fs.streams.values()
                       if getattr(s, "mass_flow_locked", False)}

    # Iterar hasta convergencia
    for _ in range(50):   # límite defensivo
        changed = False
        for b in fs.blocks.values():
            ins  = [s for s in fs.streams.values() if s.dst == b.id]
            outs = [s for s in fs.streams.values() if s.src == b.id]
            all_streams = ins + outs
            if not all_streams:
                continue

            # ── Caso splitter_active: con N fracciones e input determinable
            if getattr(b, "splitter_active", False):
                fracs = getattr(b, "splitter_fractions", []) or []
                if len(fracs) == len(outs) and len(ins) >= 1:
                    main_in = next((s for s in ins if s.mass_flow > 0
                                      or s.id in det), None)
                    if main_in and main_in.id in det:
                        for s in outs:
                            if s.id not in det:
                                det.add(s.id); changed = True
                        continue

            # ── Caso flash_active / column_active / separadores
            # mecánicos: solver dedicado propaga conservando masa.
            # Si los inputs son determinables, los outputs los pone
            # el solver salvo que estén lockeados.
            if (getattr(b, "flash_active", False)
                    or getattr(b, "column_active", False)
                    or getattr(b, "separator_active", False)
                    or getattr(b, "dryer_active", False)
                    or getattr(b, "crystallizer_active", False)
                    or getattr(b, "evaporator_active", False)
                    or getattr(b, "cyclone_active", False)):
                if all(s.id in det for s in ins):
                    for s in outs:
                        if s.id not in det:
                            det.add(s.id); changed = True
                    continue

            # ── Caso general: balance estándar.
            # Source (0 ins) y sink (0 outs) NO tienen ec. de balance:
            # son tanques de almacenamiento que no aportan info de masa.
            if len(ins) == 0 or len(outs) == 0:
                continue
            unknown = [s for s in all_streams if s.id not in det]
            if len(unknown) == 1:
                det.add(unknown[0].id)
                changed = True

        if not changed:
            break

    return det


def _determinable_compositions(fs: Flowsheet) -> Set[int]:
    """Propaga composiciones topológicamente: un stream tiene
    composition determinable si está declarada, o si su src es un
    bloque con todos sus inputs comp-determinables, o si es output
    de un reactor / splitter / flash / column (esos bloques setean
    composiciones de sus outputs aunque los inputs estén vacíos)."""
    det: Set[int] = set()
    for s in fs.streams.values():
        if s.composition or s.main_component:
            det.add(s.id)

    for _ in range(50):
        changed = False
        for b in fs.blocks.values():
            ins  = [s for s in fs.streams.values() if s.dst == b.id]
            outs = [s for s in fs.streams.values() if s.src == b.id]
            if not outs:
                continue
            # Bloques chemistry-aware: outputs siempre se computan
            chem_aware = (bool(getattr(b, "reactions", None))
                          or getattr(b, "splitter_active", False)
                          or getattr(b, "flash_active", False)
                          or getattr(b, "column_active", False)
                          or getattr(b, "separator_active", False)
                          or getattr(b, "dryer_active", False)
                          or getattr(b, "crystallizer_active", False)
                          or getattr(b, "evaporator_active", False)
                          or getattr(b, "cyclone_active", False))
            ins_have = any(s.id in det for s in ins)
            if chem_aware or ins_have:
                for s in outs:
                    if s.id not in det:
                        det.add(s.id); changed = True
        if not changed:
            break
    return det


# ─────────────────────────────────────────────────────────────
# Análisis principal
# ─────────────────────────────────────────────────────────────

def analyze_flowsheet(fs: Flowsheet) -> DOFReport:
    """Audita DOF estructural y reporta problemas."""
    report = DOFReport()
    report.n_blocks  = len(fs.blocks)
    report.n_streams = len(fs.streams)

    # Componentes únicos
    all_comps: Set[str] = set()
    for s in fs.streams.values():
        all_comps.update((s.composition or {}).keys())
        if s.main_component:
            all_comps.add(s.main_component)
    report.n_components = len(all_comps)

    # Propagación de masa y composición
    det_mass = _determinable_masses(fs)
    det_comp = _determinable_compositions(fs)
    report.n_indeterminable_mass = len(fs.streams) - len(det_mass)

    # Stream-level status
    for s in fs.streams.values():
        ss = StreamStatus(name=s.name)
        if getattr(s, "mass_flow_locked", False):
            ss.mass_status = "locked"
        elif s.id in det_mass:
            ss.mass_status = "propagated"
        elif s.mass_flow > 0:
            ss.mass_status = "known"
        if getattr(s, "composition_locked", False):
            ss.comp_status = "locked"
        elif s.composition:
            ss.comp_status = "known"
        if getattr(s, "temperature_locked", False):
            ss.T_status = "locked"
        elif abs(s.temperature - 25.0) > 0.01:
            ss.T_status = "known"
        if getattr(s, "pressure_locked", False):
            ss.P_status = "locked"
        elif getattr(s, "pressure_bar", 0) > 0:
            ss.P_status = "known"
        report.streams.append(ss)

    # Block-level análisis
    for b in fs.blocks.values():
        ins  = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        bs   = BlockStatus(name=b.name, eq_type=b.eq_type)

        # ── MASS DOF: streams ligados a este bloque sin masa determinable
        all_streams = ins + outs
        indet = [s for s in all_streams if s.id not in det_mass]
        if len(indet) > 1:
            # Más de 1 stream indeterminable y el balance solo aporta 1 ec
            bs.mass_dof = len(indet) - 1
            indet_names = ", ".join(s.name for s in indet[:4])
            bs.notes.append(
                f"Mass balance no cierra: {len(indet)} streams "
                f"indeterminables ({indet_names})")

        # ── ENERGY DOF: solo reactores isotermales sin T_op_K
        is_reactor   = bool(getattr(b, "reactions", None))
        is_adiabatic = is_reactor and (not b.T_op_K or b.T_op_K < 100)
        if is_reactor and not is_adiabatic:
            if not (b.T_op_K and b.T_op_K > 0):
                bs.energy_dof = 1
                bs.notes.append("Reactor isotermal sin T_op_K declarado")

        # HX/heater: si AMBOS T_in y T_out son default (=25°C),
        # el solver no sabe qué hacer (Q=0 default, igual no cambia
        # nada).  Solo flageamos si tampoco hay duty lockeado.
        if _is_hx(b.eq_type) and not is_reactor:
            t_in  = any(getattr(s, "temperature_locked", False) for s in ins)
            t_out = any(getattr(s, "temperature_locked", False) for s in outs)
            d_lk  = getattr(b, "duty_locked", False)
            if not (t_in or t_out or d_lk):
                bs.energy_dof = 1
                bs.notes.append(
                    "HX sin specs energéticos: T_in, T_out y duty todos "
                    "default → solver asume Q=0 (sin cambio)")

        # ── COMPOSITION DOF: outputs cuya comp no propagable
        if outs:
            outs_indet = [s for s in outs if s.id not in det_comp]
            if outs_indet:
                bs.comp_dof = len(outs_indet)
                names = ", ".join(s.name for s in outs_indet[:3])
                bs.notes.append(
                    f"{len(outs_indet)} output(s) sin composition "
                    f"determinable ({names})")

        # Status
        if bs.total_dof > 0:
            bs.overall = "under"; report.n_under += 1
        elif bs.total_dof < 0:
            bs.overall = "over";  report.n_over += 1
        else:
            bs.overall = "ok";    report.n_ok += 1
        report.blocks.append(bs)

    report.total_dof = sum(b.total_dof for b in report.blocks)

    if report.total_dof == 0 and report.n_indeterminable_mass == 0:
        report.summary = (
            f"✓ Flowsheet BIEN ESPECIFICADO  "
            f"({report.n_ok}/{report.n_blocks} bloques ok)")
    elif report.total_dof > 0:
        report.summary = (
            f"⚠ UNDER-SPECIFICADO — DOF = {report.total_dof}  "
            f"({report.n_under} bloque(s) con specs faltantes)")
        report.suggestions.append(
            "Cada bloque con DOF>0 necesita locks adicionales para que "
            "el solver lo cierre sin warnings.")
    else:
        report.summary = (
            f"✗ OVER-SPECIFICADO — DOF = {report.total_dof}  "
            f"(conflicto entre locks)")
        report.suggestions.append(
            "Quitar locks redundantes: el balance del bloque ya determina "
            "esos valores y el lock crea conflicto.")

    return report


def format_report(report: DOFReport, max_blocks: int = 50) -> str:
    """Formatea el report como texto plano para mostrar en dialog."""
    out = []
    out.append("=" * 76)
    out.append("ANÁLISIS DE GRADOS DE LIBERTAD")
    out.append("=" * 76)
    out.append("")
    out.append(report.summary)
    out.append("")
    out.append(f"  Bloques: {report.n_blocks}   "
                f"Streams: {report.n_streams}   "
                f"Componentes: {report.n_components}")
    out.append(f"  Status:  ✓ {report.n_ok}    "
                f"⚠ {report.n_under}    ✗ {report.n_over}")
    if report.n_indeterminable_mass > 0:
        out.append(f"  Streams sin mass determinable: "
                    f"{report.n_indeterminable_mass}")
    out.append("")

    problems = [b for b in report.blocks if b.overall != "ok"]
    if problems:
        out.append("BLOQUES CON SPECS FALTANTES:")
        out.append("-" * 76)
        for b in problems[:max_blocks]:
            icon = "⚠" if b.overall == "under" else "✗"
            out.append(f"  {icon} {b.name:14}  {b.eq_type:32}  "
                        f"DOF={b.total_dof:+d}")
            for note in b.notes:
                out.append(f"        · {note}")
        out.append("")
    if report.suggestions:
        out.append("SUGERENCIAS:")
        out.append("-" * 76)
        for s in report.suggestions:
            out.append(f"  · {s}")
        out.append("")
    return "\n".join(out)
