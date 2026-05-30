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
    """Describe una corriente auxiliar requerida por un equipo.

    `cycle_id` agrupa specs en pares supply/return que forman UN lazo cerrado
    (típicamente CW shell, chaqueta, vapor del kettle).  Cuando dos specs
    comparten cycle_id no nulo, ``instantiate_auxiliaries`` crea UN solo
    bloque tipo "Utility header" y conecta ambas corrientes a él — el lazo
    se ve como tal en el PFD — y agrega una bomba de circulación auto_aux
    sobre la rama supply.  Los streams con cycle_id=None se mantienen como
    estaban: par source/sink separado (caso abierto: aire, fuel, chimenea)."""
    port_name: str                       # puerto del bloque principal
    direction: str                       # 'in' (source→bloque) | 'out' (bloque→sink)
    sink_kind: str                       # 'utility_source'|'utility_sink'|
                                         #   'ambient_intake'|'ambient_vent'
    utility_key: Optional[str] = None    # clave en UTILITIES, o None = resolver por duty
    phase: str = "liquid"                # 'vapor'|'liquid'|'gas'|'fuel'|'flue_gas'
    role: str = "utility"                # 'utility' | 'ambient'
    composition_hint: Optional[dict] = None
    label: str = "AUX"                   # etiqueta corta del source/sink
    cycle_id: Optional[str] = None       # agrupa supply/return de un lazo CERRADO


# Composiciones típicas
_CW   = {"water": 1.0}
_AIR  = {"air": 1.0}
_FUEL = {"methane": 1.0}                 # fuel gas ≈ metano
_FLUE = {"nitrogen": 0.74, "carbon dioxide": 0.14, "water": 0.12}
_STEAM = {"water": 1.0}


def _hx_shell():
    """Par utility shell-side de un HX shell-and-tube — LAZO CERRADO (CW)."""
    return [
        AuxStreamSpec("shell_in",  "in",  "utility_source", None, "liquid",
                      "utility", _CW, "UT", cycle_id="shell"),
        AuxStreamSpec("shell_out", "out", "utility_sink",   None, "liquid",
                      "utility", _CW, "UT", cycle_id="shell"),
    ]


def _air():
    """Par aire intake/vent — ABIERTO (no es ciclo)."""
    return [
        AuxStreamSpec("aire_in",  "in",  "ambient_intake", None, "gas",
                      "ambient", _AIR, "Aire"),
        AuxStreamSpec("aire_out", "out", "ambient_vent",   None, "gas",
                      "ambient", _AIR, "Aire"),
    ]


def _jacket():
    """Chaqueta de reactor — LAZO CERRADO (CW)."""
    return [
        AuxStreamSpec("util_in",  "in",  "utility_source", None, "liquid",
                      "utility", _CW, "UT", cycle_id="jacket"),
        AuxStreamSpec("util_out", "out", "utility_sink",   None, "liquid",
                      "utility", _CW, "UT", cycle_id="jacket"),
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
    # Lazo CERRADO: vapor sale de un header, condensado vuelve al mismo
    # header del boiler.  cycle_id agrupa ambas corrientes en UN header.
    AuxStreamSpec("steam_in", "in",  "utility_source", "steam_LP", "vapor",
                  "utility", _STEAM, "Steam", cycle_id="kettle_steam"),
    AuxStreamSpec("cond_out", "out", "utility_sink",   "steam_LP", "liquid",
                  "utility", _STEAM, "Cond", cycle_id="kettle_steam"),
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

# Bloques ligeros usados como source/sink visual (marcados auto_aux →
# excluidos del capex):
#   · utility abierta (fuel, BFW, makeup) → tanque pequeño.
#   · utility cerrada (CW shell, chaqueta, vapor del kettle) → header SUP/RET
#     compartido entre supply y return — el lazo se ve como tal.
#   · ambiente (aire, chimenea, blowdown, evaporación) → ícono atmósfera.
_UTIL_BLOCK_EQ    = "Storage tank — cone roof"
_HEADER_BLOCK_EQ  = "Utility header"
_AMBIENT_BLOCK_EQ = "Ambient"
_PUMP_BLOCK_EQ    = "Pump — centrifugal"
_AUX_OFFSET       = 110.0     # px del puerto hacia afuera
_PUMP_INSET       = 55.0      # px entre header y bomba de circulación


def _aux_block_eq(sink_kind):
    return (_AMBIENT_BLOCK_EQ if sink_kind in ("ambient_intake", "ambient_vent")
            else _UTIL_BLOCK_EQ)


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

    # Partition: specs con cycle_id (lazo cerrado, comparten header) vs sin.
    by_cycle: Dict[str, List[AuxStreamSpec]] = {}
    open_specs: List[AuxStreamSpec] = []
    for sp in specs:
        if sp.cycle_id:
            by_cycle.setdefault(sp.cycle_id, []).append(sp)
        else:
            open_specs.append(sp)

    created: List[int] = []

    # ── A) Lazos CERRADOS: un header compartido por cycle_id ────────────
    for cycle, sps in by_cycle.items():
        # Si ya existe algún stream auto_aux conectado a uno de los puertos
        # del lazo, no duplicar nada para este cycle.
        already = any(
            (s.src == block.id and (s.src_port or "") in {p.port_name for p in sps}) or
            (s.dst == block.id and (s.dst_port or "") in {p.port_name for p in sps})
            for s in fs.streams.values())
        if already:
            continue
        # Posición del header: al lado del primer puerto del cycle.
        anchor_sp = sps[0]
        side, frac = ports.get(anchor_sp.port_name, ("right", 0.5))
        px, py = _port_xy(block, w, h, side, frac)
        dx, dy = _SIDE_OUT.get(side, (1, 0))
        hx_x = px + dx * _AUX_OFFSET - 40.0
        hx_y = py + dy * _AUX_OFFSET - 15.0

        # Header (utility) block — compartido por todas las corrientes
        # del lazo (mismo bloque).
        hid = fs.new_id()
        header = Block(id=hid, name=_unique_name(fs, f"HDR-{cycle[:6]}"),
                       eq_type=_HEADER_BLOCK_EQ, S=1.0,
                       x=float(hx_x), y=float(hx_y))
        header.auto_aux = True
        fs.blocks[hid] = header
        created.append(hid)

        # Bomba de circulación auto_aux, intercalada en la rama SUPPLY.
        # Se ubica entre el header y el equipo, sobre la línea supply.
        pump_x = hx_x - dx * _PUMP_INSET if side in ("right", "left") \
            else hx_x + 25.0
        pump_y = hx_y + 20.0 if side in ("right", "left") else hx_y - dy * _PUMP_INSET
        pid = fs.new_id()
        pump = Block(id=pid, name=_unique_name(fs, f"P-{cycle[:5]}"),
                     eq_type=_PUMP_BLOCK_EQ, S=0.5,
                     x=float(pump_x), y=float(pump_y))
        pump.auto_aux = True
        pump.efficiency = 0.65          # bomba CW típica
        fs.blocks[pid] = pump
        created.append(pid)

        # Crear streams del lazo: supply (header → pump → block) +
        # return (block → header).  La bomba va sólo en la rama supply.
        supply_specs = [sp for sp in sps if sp.direction == "in"]
        return_specs = [sp for sp in sps if sp.direction == "out"]
        for sp in supply_specs:
            comp = dict(sp.composition_hint or {})
            # Tramo 1: header → pump
            s1id = fs.new_id()
            s1 = Stream(id=s1id, name=_aux_stream_name(fs, sp),
                        src=hid, dst=pid,
                        src_port="salida", dst_port="in",
                        mass_flow=0.0, role=sp.role, phase=sp.phase,
                        composition=comp,
                        main_component=(max(comp, key=comp.get) if comp else ""))
            s1.auto_aux = True
            s1.mass_flow_locked = False
            s1.composition_locked = bool(comp)
            fs.streams[s1id] = s1
            created.append(s1id)
            # Tramo 2: pump → block
            s2id = fs.new_id()
            s2 = Stream(id=s2id, name=_aux_stream_name(fs, sp),
                        src=pid, dst=block.id,
                        src_port="out", dst_port=sp.port_name,
                        mass_flow=0.0, role=sp.role, phase=sp.phase,
                        composition=comp,
                        main_component=(max(comp, key=comp.get) if comp else ""))
            s2.auto_aux = True
            s2.mass_flow_locked = False
            s2.composition_locked = bool(comp)
            fs.streams[s2id] = s2
            created.append(s2id)
        for sp in return_specs:
            comp = dict(sp.composition_hint or {})
            sid = fs.new_id()
            s = Stream(id=sid, name=_aux_stream_name(fs, sp),
                       src=block.id, dst=hid,
                       src_port=sp.port_name, dst_port="entrada",
                       mass_flow=0.0, role=sp.role, phase=sp.phase,
                       composition=comp,
                       main_component=(max(comp, key=comp.get) if comp else ""))
            s.auto_aux = True
            s.mass_flow_locked = False
            s.composition_locked = bool(comp)
            fs.streams[sid] = s
            created.append(sid)

    # ── B) Aux abiertas (sin cycle_id): par source/sink separado, como antes
    for sp in open_specs:
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

        bid = fs.new_id()
        aux_b = Block(id=bid, name=_unique_name(fs, sp.label),
                      eq_type=_aux_block_eq(sp.sink_kind), S=1.0,
                      x=float(sx), y=float(sy))
        aux_b.auto_aux = True
        fs.blocks[bid] = aux_b
        created.append(bid)

        comp = dict(sp.composition_hint or {})
        sid = fs.new_id()
        if sp.direction == "in":
            src, dst, src_port, dst_port = bid, block.id, "salida", sp.port_name
        else:
            src, dst, src_port, dst_port = block.id, bid, sp.port_name, "entrada"
        s = Stream(id=sid, name=_aux_stream_name(fs, sp), src=src, dst=dst,
                   src_port=src_port, dst_port=dst_port, mass_flow=0.0,
                   role=sp.role, phase=sp.phase, composition=comp,
                   main_component=(max(comp, key=comp.get) if comp else ""))
        s.auto_aux = True
        s.mass_flow_locked = False
        s.composition_locked = bool(comp)
        fs.streams[sid] = s
        created.append(sid)
    return created


def _aux_stream_name(fs, sp):
    pref = {"utility": "U", "ambient": "A"}.get(sp.role, "X")
    n = 1 + sum(1 for s in fs.streams.values()
                 if (s.name or "").startswith(f"{pref}-aux"))
    return f"{pref}-aux-{n}"
