"""
equipment_auxiliaries.py — corrientes auxiliares por defecto.

Al instanciar un equipo, materializa sus corrientes de SERVICIO (utility:
cooling water, steam, fuel gas, BFW) y de AMBIENTE (aire, chimenea/flue gas,
blowdown, evaporación) con un bloque source/sink colocado automáticamente
cerca del puerto correspondiente.  Así el PFD no "miente" (un HX muestra su
cooling water; un horno su combustible y chimenea) y el solver puede modelar
el ciclo de utilities.

Diseño:
  · AUX_STREAMS[eq_type] = [AuxStreamSpec, ...] declara qué corrientes
    auxiliares requiere cada tipo de equipo.
  · instantiate_auxiliaries(fs, block) las crea (source/sink + stream),
    marcando todo con auto_aux=True.

Reglas (cross-cutting):
  · Solo se llama al CREAR un bloque de cero (no retroactivo al cargar).
  · Si block.aux_user_edited → no se (re)crea (respeta intención del user).
  · Si el bloque está en cross-exchange (heat integration) → no se crean
    las auxiliares de utility (el calor viene de otro proceso).
  · No se duplica una aux si el puerto ya tiene un stream conectado.
"""
from dataclasses import dataclass
from typing import Optional, Dict, List


@dataclass
class AuxStreamSpec:
    """Describe una corriente auxiliar requerida por un equipo."""
    port_name: str                       # puerto del bloque principal
    direction: str                       # 'in' (source→bloque) | 'out' (bloque→sink)
    sink_kind: str                       # 'utility_source'|'utility_sink'|
                                         #   'ambient_intake'|'ambient_vent'
    utility_key: Optional[str] = None    # clave en UTILITIES, o None = resolver por duty
    phase: str = "liquid"                # 'vapor'|'liquid'|'gas'|'fuel'|'flue_gas'
    role: str = "utility"                # 'utility' | 'ambient'
    composition_hint: Optional[dict] = None
    label: str = "AUX"                   # etiqueta corta del source/sink


# Composiciones típicas
_CW   = {"water": 1.0}
_AIR  = {"air": 1.0}
_FUEL = {"methane": 1.0}                 # fuel gas ≈ metano
_FLUE = {"nitrogen": 0.74, "carbon dioxide": 0.14, "water": 0.12}
_STEAM = {"water": 1.0}


def _hx_shell():
    """Par utility shell-side de un HX shell-and-tube (resolver por duty)."""
    return [
        AuxStreamSpec("shell_in",  "in",  "utility_source", None, "liquid",
                      "utility", _CW, "UT"),
        AuxStreamSpec("shell_out", "out", "utility_sink",   None, "liquid",
                      "utility", _CW, "UT"),
    ]


def _air():
    return [
        AuxStreamSpec("aire_in",  "in",  "ambient_intake", None, "gas",
                      "ambient", _AIR, "Aire"),
        AuxStreamSpec("aire_out", "out", "ambient_vent",   None, "gas",
                      "ambient", _AIR, "Aire"),
    ]


def _jacket():
    """Chaqueta de reactor (utility por duty)."""
    return [
        AuxStreamSpec("util_in",  "in",  "utility_source", None, "liquid",
                      "utility", _CW, "UT"),
        AuxStreamSpec("util_out", "out", "utility_sink",   None, "liquid",
                      "utility", _CW, "UT"),
    ]


def _furnace():
    return [
        AuxStreamSpec("combustible", "in",  "utility_source", "fuel_gas",
                      "fuel", "utility", _FUEL, "Fuel"),
        AuxStreamSpec("chimenea",    "out", "ambient_vent",   None,
                      "flue_gas", "ambient", _FLUE, "Stack"),
    ]


def _boiler():
    return [
        AuxStreamSpec("agua_in",     "in",  "utility_source", None,
                      "liquid", "utility", _CW, "BFW"),
        AuxStreamSpec("combustible", "in",  "utility_source", "fuel_gas",
                      "fuel", "utility", _FUEL, "Fuel"),
        AuxStreamSpec("blowdown",    "out", "ambient_vent",   None,
                      "liquid", "ambient", _CW, "BD"),
        AuxStreamSpec("chimenea",    "out", "ambient_vent",   None,
                      "flue_gas", "ambient", _FLUE, "Stack"),
    ]


def _cooling_tower():
    return [
        AuxStreamSpec("makeup",     "in",  "utility_source", None,
                      "liquid", "utility", _CW, "Makeup"),
        AuxStreamSpec("blowdown",   "out", "ambient_vent",   None,
                      "liquid", "ambient", _CW, "BD"),
        AuxStreamSpec("vapor_loss", "out", "ambient_vent",   None,
                      "vapor", "ambient", _STEAM, "Evap"),
    ]


# Catálogo: eq_type → especificaciones de corrientes auxiliares.
AUX_STREAMS: Dict[str, List[AuxStreamSpec]] = {}
for _et in ("Heat exch. — U-tube", "Heat exch. — floating head",
            "Heat exch. — fixed tube", "Heat exch. — flat plate",
            "Heat exch. — multiple pipe", "Heat exch. — double pipe",
            "Heat exch. — spiral plate", "Heat exch. — condenser shell-tube"):
    AUX_STREAMS[_et] = _hx_shell()
for _et in ("Heat exch. — air cooler", "Heat exch. — condenser air-cooled"):
    AUX_STREAMS[_et] = _air()
AUX_STREAMS["Heat exch. — kettle reboiler"] = [
    AuxStreamSpec("steam_in", "in",  "utility_source", "steam_LP", "vapor",
                  "utility", _STEAM, "Steam"),
    AuxStreamSpec("cond_out", "out", "utility_sink",   "steam_LP", "liquid",
                  "utility", _STEAM, "Cond"),
]
for _et in ("Reactor — jacketed agitated", "Reactor — jacketed non-agit."):
    AUX_STREAMS[_et] = _jacket()
for _et in ("Fired heater — non-reformer", "Fired heater — reformer"):
    AUX_STREAMS[_et] = _furnace()
for _et in ("Boiler — fire tube", "Boiler — water tube"):
    AUX_STREAMS[_et] = _boiler()
for _et in ("Cooling tower — induced draft", "Cooling tower — natural draft"):
    AUX_STREAMS[_et] = _cooling_tower()


_SIDE_OUT = {"right": (1, 0), "left": (-1, 0), "top": (0, -1), "bottom": (0, 1)}

# Bloque ligero usado como source/sink visual (tanque pequeño marcado
# auto_aux → excluido del capex).  Phase 2 reemplaza ambient por íconos de
# atmósfera.
_AUX_BLOCK_EQ = "Storage tank — cone roof"
_AUX_OFFSET   = 110.0     # px del puerto hacia afuera


def _port_xy(block, w, h, side, frac):
    if side == "right":
        return block.x + w, block.y + h * frac
    if side == "left":
        return block.x, block.y + h * frac
    if side == "top":
        return block.x + w * frac, block.y
    return block.x + w * frac, block.y + h        # bottom


def _unique_name(fs, base):
    existing = {b.name for b in fs.blocks.values()}
    if base not in existing:
        return base
    i = 2
    while f"{base}-{i}" in existing:
        i += 1
    return f"{base}-{i}"


def instantiate_auxiliaries(fs, block):
    """Crea las corrientes auxiliares (source/sink + stream) para `block`.

    Devuelve la lista de ids creados (bloques y streams).  No-op si el
    bloque no tiene specs, fue editado por el user, o (para utilities) está
    en cross-exchange.
    """
    if getattr(block, "aux_user_edited", False):
        return []
    specs = AUX_STREAMS.get(block.eq_type)
    if not specs:
        return []

    # Heat integration: si el calor lo entrega otro proceso, no instanciar
    # las auxiliares de UTILITY (las de ambiente sí, p.ej. chimenea).
    try:
        from flowsheet_solver import is_cross_exchange
        if is_cross_exchange(fs, block):
            specs = [sp for sp in specs if sp.role != "utility"]
    except Exception:
        pass
    if not specs:
        return []

    import pfd_symbols as pfd
    import equipment_ports as ep
    from flowsheet_model import Block, Stream
    try:
        w, h = pfd.block_dims(block.eq_type)
    except Exception:
        w, h = 80.0, 80.0
    ports = ep.get_ports(block.eq_type)

    created: List[int] = []
    for sp in specs:
        # No duplicar si el puerto ya tiene un stream conectado.
        taken = any(
            (s.src == block.id and (s.src_port or "") == sp.port_name) or
            (s.dst == block.id and (s.dst_port or "") == sp.port_name)
            for s in fs.streams.values())
        if taken:
            continue

        side, frac = ports.get(sp.port_name, ("top", 0.5))
        px, py = _port_xy(block, w, h, side, frac)
        dx, dy = _SIDE_OUT.get(side, (0, -1))
        sx = px + dx * _AUX_OFFSET - 30.0
        sy = py + dy * _AUX_OFFSET - 30.0

        # Source/sink (tanque ligero auto_aux).
        bid = fs.new_id()
        aux_b = Block(id=bid, name=_unique_name(fs, sp.label),
                      eq_type=_AUX_BLOCK_EQ, S=1.0,
                      x=float(sx), y=float(sy))
        aux_b.auto_aux = True
        fs.blocks[bid] = aux_b
        created.append(bid)

        # Stream auxiliar.
        comp = dict(sp.composition_hint or {})
        sid = fs.new_id()
        if sp.direction == "in":
            src, dst, src_port, dst_port = bid, block.id, "salida", sp.port_name
        else:
            src, dst, src_port, dst_port = block.id, bid, sp.port_name, "entrada"
        sname = _aux_stream_name(fs, sp)
        s = Stream(id=sid, name=sname, src=src, dst=dst,
                   src_port=src_port, dst_port=dst_port, mass_flow=0.0,
                   role=sp.role, phase=sp.phase, composition=comp,
                   main_component=(max(comp, key=comp.get) if comp else ""))
        s.auto_aux = True
        s.mass_flow_locked = False           # se calcula desde el duty
        s.composition_locked = bool(comp)    # hint conocido (water/air/fuel)
        fs.streams[sid] = s
        created.append(sid)
    return created


def _aux_stream_name(fs, sp):
    pref = {"utility": "U", "ambient": "A"}.get(sp.role, "X")
    n = 1 + sum(1 for s in fs.streams.values()
                 if (s.name or "").startswith(f"{pref}-aux"))
    return f"{pref}-aux-{n}"
