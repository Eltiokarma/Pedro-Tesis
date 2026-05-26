"""hydraulic_defaults.py — inicialización hidráulica de flowsheets.

El solver hidráulico (flowsheet_solver.solve_pressure_hydraulic) es OPT-IN:
sólo auto-dimensiona bombas/compresores si hay alguna presión LOCKED downstream
(o un reactor con P_op_bar > 1 atm, que el solver siembra como lock).  La
mayoría de los ejemplos no fijaban presiones → las bombas quedaban con
ΔP=0 / W_elec=0 y la topología hidráulica quedaba sin resolver.

Este módulo aplica defaults razonables (idempotentes) a un flowsheet recién
construido para que el solver tenga con qué trabajar, manteniendo la filosofía
"sudoku": se declara lo mínimo (feed P, anchor downstream, ΔP típicas por
equipo, geometría de tubería) y el solver infiere el ΔP de cada bomba y su
W_elec / head / NPSHa.

API:
    apply_typical_pressures(fs, presets=None) -> List[str]
    lock_pump_train(fs, feed_stream_name, target_stream_name,
                    target_P_bar, feed_P_bar=1.013) -> List[str]
    apply_example_hydraulics(fs, example_name) -> List[str]
"""
from __future__ import annotations

from typing import Dict, List, Optional

ATM = 1.01325

# ΔP típica por tipo de equipo [bar], negativa = pérdida de carga.
# Se evalúan en orden: el primer substring que matchea el eq_type gana
# (los más específicos van primero).  Bombas/compresores NO están: su ΔP
# la auto-dimensiona el solver desde el target downstream.
_DP_RULES = [
    ("air cooler",        -0.3),
    ("kettle reboiler",   -0.2),
    ("plate",             -0.4),
    ("heat exch",         -0.5),   # floating head / fixed tube genérico
    ("tower",             -0.3),   # base; se ajusta por N de etapas abajo
    ("column",            -0.3),
    ("fired heater",      -0.3),
    ("fired",             -0.3),
    ("packed",            -1.0),
    ("jacketed non-agit", -1.0),   # lecho fijo / packed
    ("autoclave",         -0.2),
    ("jacketed agitated", -0.1),   # CSTR
    ("decanter",          -0.05),
    ("vessel",            -0.05),   # drum / knockout
    ("knock",             -0.05),
    ("centrifuge",        -1.0),
    ("filter",            -0.5),
    ("cyclone",           -0.1),
    ("control",           -0.7),   # válvula de control (autoridad)
    ("relief",             0.0),
    ("mixer",              0.0),
    ("splitter",           0.0),
    ("tank",               0.0),
    ("storage",            0.0),
]


def _is_rotative(eq_type: str) -> bool:
    e = (eq_type or "").lower()
    return ("pump" in e or "compressor" in e or "bomba" in e
            or "fan" in e or "blower" in e)


def _typical_dp(b) -> Optional[float]:
    """ΔP default [bar] para un bloque por su eq_type, o None si no aplica
    (bombas/compresores → auto-size; tipos desconocidos → sin default)."""
    e = (b.eq_type or "").lower()
    if _is_rotative(b.eq_type):
        return None
    for kw, dp in _DP_RULES:
        if kw in e:
            if kw in ("tower", "column"):
                n = int(getattr(b, "column_N_stages", 0) or 0)
                if n > 0:
                    return round(-0.3 - n * 0.007, 4)
            return dp
    return None


def _pipe_diameter_m(phase: str, mass_flow_tm_yr: float) -> float:
    """Diámetro interno default [m] por fase y caudal másico [tm/año]."""
    is_gas = (phase or "").lower() in ("gas", "vapor", "two_phase")
    if is_gas:
        return 0.150 if mass_flow_tm_yr >= 5000 else 0.075
    if mass_flow_tm_yr >= 10000:
        return 0.100
    if mass_flow_tm_yr >= 1000:
        return 0.050
    return 0.025


def _block_by_id(fs, bid):
    return fs.blocks.get(bid)


def apply_typical_pressures(fs, presets: Optional[Dict] = None) -> List[str]:
    """Aplica defaults de presión/hidráulica a un flowsheet recién construido.
    Idempotente: nunca sobrescribe lo que ya está locked/declarado.

    presets: dict opcional {nombre_bloque: {"delta_p_bar": x}} o
             {nombre_stream: {"P": x}} para overrides puntuales.
    """
    presets = presets or {}
    msgs: List[str] = []

    # ---- 1+2) Presiones de feeds y productos --------------------------
    for s in fs.streams.values():
        if presets.get(s.name, {}).get("P") is not None:
            s.pressure_bar = float(presets[s.name]["P"])
            s.pressure_locked = True
            continue
        if getattr(s, "pressure_locked", False):
            continue
        role = (s.role or "")
        if role == "feed":
            s.pressure_bar = ATM
            s.pressure_locked = True
            msgs.append(f"feed {s.name}: P={ATM:.3f} bar (lock)")
        elif role == "product":
            dst = _block_by_id(fs, s.dst)
            if dst is not None and any(k in (dst.eq_type or "").lower()
                                       for k in ("tank", "storage")):
                s.pressure_bar = 1.5
                s.pressure_locked = True
                msgs.append(f"product {s.name}→tanque: P=1.5 bar (lock)")

    # ---- 3) ΔP típica por equipo --------------------------------------
    for b in fs.blocks.values():
        ov = presets.get(b.name, {}).get("delta_p_bar")
        if ov is not None:
            b.delta_p_bar = float(ov)
            continue
        if abs(getattr(b, "delta_p_bar", 0.0)) > 1e-9:
            continue                       # ya declarado → respetar
        dp = _typical_dp(b)
        if dp is not None and abs(dp) > 1e-9:
            b.delta_p_bar = dp
            msgs.append(f"{b.name} ({b.eq_type}): ΔP={dp:+.2f} bar")

    # ---- 5+6) Bombas/compresores: liberar el duty manual ---------------
    # El duty manual (placeholder) bloquea el W_elec hidráulico.  Lo
    # liberamos para que el solver compute W_elec real desde el ΔP que
    # auto-dimensiona (bombas: m·ΔP/ρη; compresores: trabajo politrópico).
    # delta_p_bar se deja en 0 (modo auto-size) salvo override del user.
    for b in fs.blocks.values():
        if not _is_rotative(b.eq_type):
            continue
        if b.name in presets and "duty" in presets[b.name]:
            continue
        if getattr(b, "duty_locked", False):
            b.duty = 0.0
            b.duty_locked = False
            msgs.append(f"{b.name}: duty liberado → W_elec hidráulico")

    # ---- 4) Geometría de tubería (habilita Darcy-Weisbach) ------------
    for s in fs.streams.values():
        if s.mass_flow <= 0:
            continue
        src = _block_by_id(fs, s.src)
        dst = _block_by_id(fs, s.dst)
        # Sólo tramos inter-equipo de proceso (no utilities/ambient).
        if (s.role or "") in ("utility", "ambient"):
            continue
        if src is None or dst is None:
            continue
        if getattr(s, "is_pipe", False):
            continue                       # ya configurado
        if getattr(s, "pipe_length_m", 0.0) <= 0:
            s.pipe_length_m = 30.0
        if getattr(s, "pipe_diameter_m", 0.0) <= 0:
            s.pipe_diameter_m = _pipe_diameter_m(s.phase, s.mass_flow)
        if getattr(s, "pipe_K_local", 0.0) <= 0:
            s.pipe_K_local = 3.0
        s.is_pipe = True

    if msgs:
        msgs.insert(0, f"apply_typical_pressures: {len(msgs)} defaults")
    return msgs


def lock_pump_train(fs, feed_stream_name: str, target_stream_name: str,
                    target_P_bar: float, feed_P_bar: float = 1.013) -> List[str]:
    """Lockea la P del feed y del target de un tren para que el solver
    hidráulico auto-dimensione las bombas/compresores intermedios.

    API recomendada para los ejemplos: en 1-2 líneas el tren queda listo.
    """
    msgs: List[str] = []
    by_name = {s.name: s for s in fs.streams.values()}
    feed = by_name.get(feed_stream_name)
    tgt = by_name.get(target_stream_name)
    if feed is not None:
        feed.pressure_bar = float(feed_P_bar)
        feed.pressure_locked = True
        msgs.append(f"feed {feed_stream_name}: P={feed_P_bar:.3f} bar (lock)")
    else:
        msgs.append(f"⚠ lock_pump_train: feed '{feed_stream_name}' no existe")
    if tgt is not None:
        tgt.pressure_bar = float(target_P_bar)
        tgt.pressure_locked = True
        msgs.append(f"target {target_stream_name}: P={target_P_bar:.2f} bar (lock)")
    else:
        msgs.append(f"⚠ lock_pump_train: target '{target_stream_name}' no existe")
    return msgs


# Anchors de presión por ejemplo (método → (target_stream, target_P_bar)).
# Sólo para trenes SIN reactor de alta P (el solver siembra P_op_bar de los
# reactores automáticamente, así que ammonia/methanol/hda/smr/etc. ya tienen
# anchor).  Acá van los trenes bomba→columna casi atmosféricos y similares.
EXAMPLE_PRESETS: Dict[str, Dict] = {
    "_example_distillation":              {"target": ("S-3", 1.2)},
    "_example_ethanol":                   {"target": ("S-4", 1.1)},
    "_example_distillation_ethanol_water": {"target": ("S-feed-hot", 1.5)},
    "_example_crude_distillation":        {"target": ("S-crude-hot", 2.5)},
    "_example_biodiesel":                 {"target": ("S-1", 4.0)},
    "_example_reactor_flash_column":      {"target": ("S-fermentado", 10.0)},
}


def apply_example_hydraulics(fs, example_name: str) -> List[str]:
    """Conveniencia para los ejemplos: aplica defaults típicos + el anchor
    downstream específico del ejemplo (si lo necesita)."""
    msgs = apply_typical_pressures(fs)
    preset = EXAMPLE_PRESETS.get(example_name)
    if preset and preset.get("target"):
        tgt_name, tgt_P = preset["target"]
        by_name = {s.name: s for s in fs.streams.values()}
        if tgt_name in by_name and not by_name[tgt_name].pressure_locked:
            by_name[tgt_name].pressure_bar = float(tgt_P)
            by_name[tgt_name].pressure_locked = True
            msgs.append(f"anchor {tgt_name}: P={tgt_P:.2f} bar (lock)")
    return msgs
