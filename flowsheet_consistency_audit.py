"""Auditor unificado de consistencia (Frente A).

Una sola pasada al final de solve() que reporta cuatro clases de
inconsistencia en un resultado estructurado:

  (1) phase            — phase declarada incompatible con (T, P, composición)
  (2) component_balance — balance por componente roto en bloques no-reactor
  (3) pseudo            — pseudo-componentes en uso (sin Antoine/DIPPR reales)
  (4) redundant_lock    — composiciones lockeadas que el solver pudo calcular

Diseño: un módulo, una pasada, un AuditReport.  Sustituye al viejo
_check_component_balance del solver (Detector 2 lo integra).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List

# Fases válidas para clasificar una phase declarada (gas == vapor).
VALID_PHASES = {"liquid", "vapor", "gas", "two_phase"}

# Componentes "agua" para la excepción de cambio de fase en el balance.
_WATER_NAMES = {"water", "h2o", "agua"}

# Fallback hardcoded si no existe data/pseudo_components.json.
INDUSTRIAL_PSEUDO_FALLBACK = {
    'syngas', 'vegetable_oil', 'biodiesel', 'glycerin', 'naphtha',
    'kerosene', 'diesel', 'atmospheric_residue', 'crude_oil',
}
FOOD_PSEUDO_FALLBACK = {'sucrose', 'glucose'}
# Especies inorgánicas / materiales sin modelo VLE razonable (sales, óxidos,
# minerales, polímeros, mezclas).  Son reales pero el solver VLE no las modela
# rigurosamente → auditor genera INFO (no error), no hay nada que "arreglar".
MATERIAL_PSEUDO_FALLBACK = set()

_PSEUDO_CACHE = None


def _load_pseudo_sets():
    """Carga (lazy) los sets de pseudo-componentes desde el JSON curado.
    Fallback a los sets hardcoded si el archivo no existe o es inválido.
    Devuelve (industrial, food, material)."""
    global _PSEUDO_CACHE
    if _PSEUDO_CACHE is not None:
        return _PSEUDO_CACHE
    industrial = set(INDUSTRIAL_PSEUDO_FALLBACK)
    food = set(FOOD_PSEUDO_FALLBACK)
    material = set(MATERIAL_PSEUDO_FALLBACK)
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "pseudo_components.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        if isinstance(d.get("industrial_pseudo"), list):
            industrial = set(d["industrial_pseudo"])
        if isinstance(d.get("food_pseudo_allowed"), list):
            food = set(d["food_pseudo_allowed"])
        if isinstance(d.get("material_pseudo_allowed"), list):
            material = set(d["material_pseudo_allowed"])
    except (OSError, ValueError):
        pass
    _PSEUDO_CACHE = (industrial, food, material)
    return _PSEUDO_CACHE


# ======================================================================
# DATACLASSES
# ======================================================================

@dataclass
class AuditFinding:
    category: str       # 'phase' | 'component_balance' | 'pseudo' | 'redundant_lock'
    severity: str       # 'info' | 'warning' | 'error'
    target_kind: str    # 'stream' | 'block'
    target_name: str
    message: str
    data: Dict = field(default_factory=dict)


@dataclass
class AuditReport:
    findings: List[AuditFinding] = field(default_factory=list)
    n_errors: int = 0
    n_warnings: int = 0
    n_infos: int = 0

    def by_category(self, cat: str) -> List[AuditFinding]:
        return [f for f in self.findings if f.category == cat]

    def by_severity(self, sev: str) -> List[AuditFinding]:
        return [f for f in self.findings if f.severity == sev]

    def summary_text(self) -> str:
        """Texto formateado para la UI / consola."""
        if not self.findings:
            return "Auditoría de consistencia: sin hallazgos."
        lines = [f"Auditoría de consistencia ({self.n_errors} errores, "
                 f"{self.n_warnings} warnings, {self.n_infos} infos):"]
        for cat in ('phase', 'component_balance', 'pseudo', 'redundant_lock'):
            cat_f = self.by_category(cat)
            if not cat_f:
                continue
            ne = sum(1 for f in cat_f if f.severity == 'error')
            nw = sum(1 for f in cat_f if f.severity == 'warning')
            ni = sum(1 for f in cat_f if f.severity == 'info')
            lines.append(f"  · {cat}: {len(cat_f)} hallazgo(s) "
                         f"({ne}E/{nw}W/{ni}I)")
            for f in cat_f[:5]:
                lines.append(f"      [{f.severity}] {f.message[:120]}")
        return "\n".join(lines)


# ======================================================================
# HELPERS DE THERMO
# ======================================================================

def _thermo(name):
    try:
        import thermo_db as _td
        return _td.get(name)
    except Exception:
        return None


def _has_antoine(comp) -> bool:
    return (comp is not None and comp.antoine_A is not None
            and comp.antoine_B is not None and comp.antoine_C is not None)


def _t_out_of_antoine_range(main_component, T_C) -> bool:
    """True si T_C cae fuera del rango Antoine del componente principal
    (la inferencia de fase entonces extrapola y no es confiable)."""
    comp = _thermo(main_component)
    if not _has_antoine(comp):
        return True
    lo, hi = getattr(comp, "antoine_range_C", (0, 0)) or (0, 0)
    if hi <= lo:
        return False   # rango no informado → no podemos afirmar fuera de rango
    return T_C < lo - 1e-6 or T_C > hi + 1e-6


def _stream_components(s):
    """Componentes presentes en el stream (composición o main_component)."""
    comp = s.composition or {}
    if comp:
        return [c for c, w in comp.items() if w and w > 0]
    if s.main_component:
        return [s.main_component]
    return []


# ======================================================================
# DETECTOR 1 — PHASE vs (T, P, composición)
# ======================================================================

def _audit_phase(fs, findings):
    try:
        from flowsheet_solver import _infer_phase_from_TP
    except Exception:
        return
    for s in fs.streams.values():
        if s.mass_flow <= 0:
            continue
        comp = s.composition or {}
        if not comp:
            continue                       # sin composición → nada que comparar
        if not (s.phase or ""):
            continue                       # phase no declarada → el solver puede setearla
        # Solo auditamos phases DECLARADAS (locked) por el builder/user — el
        # objetivo es cazar hardcodes inconsistentes.  Las phases que el
        # solver calculó (column/flash/reactor) son consistentes con SU termo
        # por construcción; re-chequearlas con otro método da falsos positivos.
        if not getattr(s, "phase_locked", False):
            continue
        T_C = s.temperature
        P = float(getattr(s, "pressure_bar", 0.0) or 0.0)
        if T_C <= -273.0 or P <= 0:
            continue
        T_K = T_C + 273.15
        inferred, vfrac = _infer_phase_from_TP(comp, T_K, P)
        if not inferred:
            continue                       # termo no pudo resolver → sin hallazgo
        decl = (s.phase or "").lower()
        decl_cmp = "vapor" if decl == "gas" else decl
        if decl_cmp == inferred:
            continue                       # consistente
        # Saturación: una corriente EN su frontera (V_frac≈0 = líquido
        # saturado en el punto de burbuja; V_frac≈1 = vapor saturado en
        # el punto de rocío) declarada liquid/vapor es consistente — la
        # termo la marca 'two_phase' por estar exactamente en el borde.
        if inferred == "two_phase":
            if vfrac <= 0.02 and decl_cmp == "liquid":
                continue
            if vfrac >= 0.98 and decl_cmp == "vapor":
                continue
            # Componente ~puro en su punto de ebullición (vapor o líquido
            # saturado): la termo lo marca 'two_phase' por estar en el borde,
            # pero declarar liquid o vapor es físicamente válido (vapor de un
            # evaporador, vapor saturado de una caldera, etc.).
            if comp and max(comp.values()) > 0.95 and decl_cmp in ("liquid", "vapor"):
                continue
        # Excepción: T fuera del rango Antoine → la inferencia extrapola.
        if _t_out_of_antoine_range(s.main_component, T_C):
            findings.append(AuditFinding(
                category='phase', severity='info', target_kind='stream',
                target_name=s.name,
                message=(f"{s.name}: phase='{s.phase}' a T={T_C:.1f}°C, "
                         f"P={P:.2f}bar; verificación de fase no confiable "
                         f"(T fuera del rango Antoine del componente "
                         f"principal '{s.main_component}')."),
                data={'T_C': T_C, 'P_bar': P, 'expected': inferred,
                      'declared': s.phase, 'V_frac': vfrac,
                      'reason': 'antoine_range'}))
            continue
        sev = 'warning' if decl in VALID_PHASES else 'error'
        findings.append(AuditFinding(
            category='phase', severity=sev, target_kind='stream',
            target_name=s.name,
            message=(f"{s.name}: declarado phase='{s.phase}' a T={T_C:.1f}°C, "
                     f"P={P:.2f}bar, pero la composición está en "
                     f"phase='{inferred}' (V_frac={vfrac:.3f}). Posibles "
                     f"causas: (a) phase hardcoded en ejemplo, (b) T/P "
                     f"incorrectas, (c) cambio de fase no modelado."),
            data={'T_C': T_C, 'P_bar': P, 'expected': inferred,
                  'declared': s.phase, 'V_frac': vfrac}))


# ======================================================================
# DETECTOR 2 — BALANCE POR COMPONENTE (integra el viejo _check_component_balance)
# ======================================================================

def _audit_component_balance(fs, findings, tol_rel=0.02):
    rxn_blocks = {b.id for b in fs.blocks.values()
                  if getattr(b, "reactions", None)}
    # Bloques downstream transitivo de un reactor: heredan composición.
    downstream_of_rxn: set = set()
    frontier = set(rxn_blocks)
    while frontier:
        nxt = set()
        for s in fs.streams.values():
            if (s.src in frontier and s.dst in fs.blocks
                    and s.dst not in downstream_of_rxn
                    and s.dst not in rxn_blocks):
                nxt.add(s.dst)
        downstream_of_rxn |= nxt
        frontier = nxt

    for b in fs.blocks.values():
        if b.id in rxn_blocks or b.id in downstream_of_rxn:
            continue
        if getattr(b, "splitter_active", False):
            continue
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
        # ¿el bloque cruza el Tb del agua? (in/out straddle 100°C)
        T_in = [s.temperature for s in ins]
        T_out = [s.temperature for s in outs]
        crosses_water_tb = (min(T_in) < 100.0 < max(T_out)
                            or min(T_out) < 100.0 < max(T_in))
        for c in set(comp_in) | set(comp_out):
            ci, co = comp_in.get(c, 0.0), comp_out.get(c, 0.0)
            if max(ci, co) < 0.01 * max(in_t, out_t):
                continue
            d = abs(ci - co)
            r = d / max(ci, co, 1e-9)
            if r < tol_rel:
                continue
            sev = 'error' if r > 0.10 else 'warning'
            # Cambio de fase legítimo del agua no modelado → baja severity.
            if c.lower() in _WATER_NAMES and crosses_water_tb:
                sev = 'warning' if sev == 'error' else 'info'
            findings.append(AuditFinding(
                category='component_balance', severity=sev,
                target_kind='block', target_name=b.name,
                message=(f"{b.name} balance por componente: {c} in={ci:.0f} "
                         f"out={co:.0f} ({r*100:.0f}%)"),
                data={'component': c, 'in': ci, 'out': co,
                      'percent_off': r * 100.0}))


# ======================================================================
# DETECTOR 3 — PSEUDO-COMPONENTES
# ======================================================================

def _audit_pseudo(fs, findings):
    industrial, food, material = _load_pseudo_sets()
    for s in fs.streams.values():
        seen = set()
        for c in _stream_components(s):
            if c in seen:
                continue
            seen.add(c)
            if c in industrial:
                findings.append(AuditFinding(
                    category='pseudo', severity='warning',
                    target_kind='stream', target_name=s.name,
                    message=(f"{s.name}: usa pseudo-componente '{c}' (sin "
                             f"Antoine/DIPPR completos). Reemplazar por "
                             f"molécula real (ver Frente C). Balances por "
                             f"componente y VLE no son físicamente "
                             f"significativos para este stream."),
                    data={'component': c}))
            elif c in food:
                findings.append(AuditFinding(
                    category='pseudo', severity='info',
                    target_kind='stream', target_name=s.name,
                    message=(f"{s.name}: usa pseudo-componente "
                             f"alimentario/biológico '{c}' — comportamiento "
                             f"aproximado, mantener como tal."),
                    data={'component': c}))
            elif c in material:
                findings.append(AuditFinding(
                    category='pseudo', severity='info',
                    target_kind='stream', target_name=s.name,
                    message=(f"{s.name}: especie inorgánica/material '{c}' "
                             f"(sal, óxido, mineral, polímero o mezcla) sin "
                             f"modelo VLE — balances por componente y VLE no "
                             f"son físicamente significativos; tratar como "
                             f"pseudo aproximado."),
                    data={'component': c}))
            elif _thermo(c) is None:
                findings.append(AuditFinding(
                    category='pseudo', severity='error',
                    target_kind='stream', target_name=s.name,
                    message=(f"{s.name}: componente '{c}' desconocido. "
                             f"Agregar a thermo_db o reemplazar por uno "
                             f"existente."),
                    data={'component': c}))


# ======================================================================
# DETECTOR 4 — COMPOSICIONES LOCKEADAS REDUNDANTES (soft, orienta Frente C)
# ======================================================================

def _block_has_inputs(fs, bid):
    return any(s.dst == bid for s in fs.streams.values())


def _any_reaction_resolves(rxn_ids):
    """True si al menos una reacción del bloque existe en el catálogo.
    Las reacciones placeholder (R*_PLACEHOLDER, R_CELDA_*, R_FUSION_*, …) NO
    resuelven: el reactor NO recalcula composición (especies fuera de
    thermo_db), así que un lock downstream es load-bearing, no redundante."""
    if not rxn_ids:
        return False
    try:
        import reactions_db as _rdb
    except ImportError:
        return True                        # sin catálogo → comportamiento previo
    for rid in rxn_ids:
        try:
            if _rdb.get(rid) is not None:
                return True
        except Exception:
            pass
    return False


def _audit_redundant_locks(fs, findings):
    for s in fs.streams.values():
        if not getattr(s, "composition_locked", False):
            continue
        # Feed (spec del problema, no redundante):
        if (s.role or "") == "feed":
            continue
        if s.src not in fs.blocks:
            continue                       # entra del exterior → spec
        src = fs.blocks[s.src]
        is_tank = "tank" in (src.eq_type or "").lower()
        if is_tank and not _block_has_inputs(fs, src.id):
            continue                       # tanque feeder sin upstream → spec
        # ¿El upstream RECALCULA la composición? Solo si tiene una reacción
        # real (no placeholder) o una unit op automática activa.
        rxn_ids = list(getattr(src, "reactions", None) or [])
        has_custom = bool(getattr(src, "custom_reactions", None))
        rxn_recalcs = has_custom or _any_reaction_resolves(rxn_ids)
        has_rxn_tags = bool(rxn_ids or has_custom)
        active = (getattr(src, "column_active", False)
                  or getattr(src, "flash_active", False)
                  or getattr(src, "splitter_active", False))
        if rxn_recalcs or active:
            # ¿El unit op realmente PUEDE recalcular esta composición? Un
            # flash/column necesita thermo (Antoine) de cada componente; si
            # alguno no está en thermo_db (NOx, cortes de petróleo, sales,
            # sólidos), el unit op se saltea y la composición queda
            # hardcodeada → load-bearing, no redundante.
            computable = all(_thermo(c) is not None
                             for c in _stream_components(s))
            if active and not rxn_recalcs and not computable:
                continue
            kind = ("reactor de equilibrio/cinético" if rxn_recalcs
                    else "unit op automática (column/flash/splitter)")
            findings.append(AuditFinding(
                category='redundant_lock', severity='info',
                target_kind='stream', target_name=s.name,
                message=(f"{s.name}: composition_locked=True pero el bloque "
                         f"upstream {src.name} es un {kind}. El lock se "
                         f"ignoró: la composición fue recalculada por la "
                         f"termodinámica."),
                data={'src_block': src.name, 'reason': 'recalculated'}))
            continue
        if has_rxn_tags:
            # Reactor con reacción placeholder/no resoluble: la composición
            # hardcodeada representa química que el solver no puede calcular
            # (especies fuera de thermo_db). El lock es load-bearing.
            continue
        # Equipo no-reactivo (mixer/pump/HX): el lock SÍ se respeta, pero si
        # ningún input tiene composición lockeada el solver pudo propagarla.
        inputs = [t for t in fs.streams.values() if t.dst == src.id]
        if inputs and not any(getattr(t, "composition_locked", False)
                              for t in inputs):
            findings.append(AuditFinding(
                category='redundant_lock', severity='info',
                target_kind='stream', target_name=s.name,
                message=(f"{s.name}: composition_locked=True pero {src.name} "
                         f"es un equipo no-reactivo. El solver pudo haber "
                         f"propagado composición desde los inputs. Considerar "
                         f"quitar el lock para que la UI muestre el cálculo "
                         f"automático."),
                data={'src_block': src.name, 'reason': 'propagable'}))


# ======================================================================
# ENTRY POINT
# ======================================================================

def audit_flowsheet(fs) -> AuditReport:
    """Pasada única que detecta los 4 tipos de inconsistencia."""
    findings: List[AuditFinding] = []
    _audit_phase(fs, findings)
    _audit_component_balance(fs, findings)
    _audit_pseudo(fs, findings)
    _audit_redundant_locks(fs, findings)
    report = AuditReport(findings=findings)
    report.n_errors = sum(1 for f in findings if f.severity == 'error')
    report.n_warnings = sum(1 for f in findings if f.severity == 'warning')
    report.n_infos = sum(1 for f in findings if f.severity == 'info')
    return report
