"""
FLOWSHEET MODEL — dataclasses puras del modelo de proceso.

Aislado de UI (no depende de Tkinter ni PySide6).  Tanto el editor
Tk legacy (`flowsheet_ui.py`) como el editor Qt nuevo (`flowsheet_qt.py`)
importan de acá.

Contiene:
  - Constantes geométricas del modelo (BLOCK_W/H, GRID_STEP, etc.)
  - Constantes termodinámicas (T_REF_C, SEC_PER_YEAR, …)
  - Block, Stream, Flowsheet (dataclasses)
  - Colores STREAM_ROLE_COLORS (semánticos, reusables)

Los atributos `canvas_*` de Block/Stream son legacy del editor Tk;
en el editor Qt no se usan (cada item Qt mantiene sus propias
referencias en el QGraphicsScene).  Quedan en el dataclass para
backward compat de JSONs.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict


# ======================================================
# CONSTANTES GEOMÉTRICAS (coordenadas del modelo)
# ======================================================

GRID_STEP   = 20      # paso de la grilla de snap (unidades modelo)
BLOCK_W     = 130     # ancho de un bloque (unidades modelo)
BLOCK_H     = 60      # alto de un bloque
ROUTING_GAP = 30      # distancia desde el bloque al primer codo del stream


# ======================================================
# CONSTANTES TERMODINÁMICAS
# ======================================================

T_REF_C       = 25.0          # referencia para entalpía sensible (°C)
SEC_PER_YEAR  = 8760 * 3600   # operación continua 100%
TM_TO_KG      = 1000.0        # 1 tm = 1000 kg


# ======================================================
# COLORES POR ROL DE CORRIENTE (semánticos)
# ======================================================

STREAM_ROLE_COLORS = {
    "internal": "#0d0d0d",   # process — negro grueso
    "feed":     "#0d0d0d",   # entra al proceso desde afuera, también negro
    "product":  "#c41e3a",   # producto que sale de planta — rojo
    "utility":  "#1e3a8a",   # agua de enfriamiento, vapor, etc. — azul
    "waste":    "#6d4c41",   # residuos, efluentes a tratamiento — marrón
}
STREAM_ROLE_COLORS_SEL = {
    "internal": "#1f6feb",
    "feed":     "#1f6feb",
    "product":  "#7a1428",
    "utility":  "#0f1f4a",
    "waste":    "#3e2723",
}


# ======================================================
# DATACLASSES
# ======================================================

@dataclass
class Block:
    id:        int
    name:      str               # ej "E-101"
    eq_type:   str               # nombre del catálogo equipment_costs.EQUIPMENT_DATA
    S:         float             # parámetro de tamaño
    n:         int = 1           # cantidad en paralelo
    x:         float = 0.0       # posición lógica del modelo
    y:         float = 0.0

    # duty térmico del equipo (kW):
    #   > 0  entrega calor (heater, reboiler, reactor endotérmico)
    #   < 0  extrae calor (cooler, condenser, reactor exotérmico)
    #   = 0  adiabático
    duty:        float = 0.0

    # utility que provee/recibe el duty (clave de equipment_ports.UTILITIES).
    # vacío → autoselect según signo de duty y T promedio.
    heat_source: str = ""

    # Calor de reacción para reactores (kJ/kg de input total).
    #   > 0  reacción endotérmica (consume calor del medio)
    #   < 0  reacción exotérmica (libera calor al medio)
    #   = 0  reactor adiabático o sin reacción declarada
    # Si != 0, el solver de energía suma m_in × heat_of_reaction al
    # balance del bloque (con signo opuesto al duty, porque consumimos
    # del medio = positivo en duty).
    heat_of_reaction: float = 0.0

    # caches del canvas Tk (no se serializan, no se usan en Qt)
    canvas_rect: Optional[int] = field(default=None, repr=False)
    canvas_text: Optional[int] = field(default=None, repr=False)
    canvas_sub:  Optional[int] = field(default=None, repr=False)


@dataclass
class Stream:
    id:        int
    name:      str
    src:       int               # block id origen
    dst:       int               # block id destino
    mass_flow: float = 0.0       # tm/año
    role:      str = "internal"  # "internal" | "feed" | "product"
    src_port:  str = ""          # nombre del puerto en src; "" = autoselect
    dst_port:  str = ""          # nombre del puerto en dst; "" = autoselect
    price_usd_per_tm: float = 0.0

    # termofísicas (balance de energía)
    temperature: float = 25.0    # °C
    cp:          float = 0.0     # kJ/kg·K — override manual; si 0 y hay
                                 # composition, se calcula de components.py

    # ---- Composición y fase (para Cp(T) riguroso y cambio de fase) ----
    # phase: "liquid" | "vapor" | "gas" | "two_phase" | ""
    #   "" (vacío) = no declarado, se usa Cp como Cp_liquid (default).
    phase: str = ""
    # vapor_fraction: solo aplica si phase == "two_phase".  0..1.
    vapor_fraction: float = 0.0
    # composition: Dict[component_name, mass_fraction].  Si vacío y
    # main_component != "", se asume 100% main_component.  Si ambos
    # vacíos, el solver usa el Cp manual (campo cp arriba).
    composition: Dict[str, float] = field(default_factory=dict)
    main_component: str = ""     # atajo para componente puro
    # ΔH_vap override (kJ/kg).  Si 0, se calcula de la composition.
    delta_h_vap_override: float = 0.0

    # ---- SETPOINTS (design targets) ----
    # Si target_temperature está seteado (≥ -273), el solver lo trata
    # como un OBJETIVO de diseño: ajusta el duty del bloque upstream
    # (vía goal_seek) para hacer que la T real iguale al setpoint.
    # Si no está seteado (= None internamente, se persiste como -999),
    # temperature es directo (declarado por user).
    target_temperature: float = -999.0   # -999 = no setpoint (sentinela)
    # Setpoint de pureza (mass fraction) de un componente específico
    # en la corriente.  Vacío = sin setpoint.
    target_purity_component: str = ""
    target_purity_fraction:  float = 0.0

    # Waypoints intermedios para routing manual del stream.  Cada
    # waypoint es [x, y] en coordenadas absolutas de la escena Qt.
    # Si está vacío, el router calcula la polilínea automáticamente
    # (Z-step o detour).  Si tiene puntos, la polilínea es:
    #   src_port → waypoints[0] → … → waypoints[N] → dst_port
    waypoints: List[List[float]] = field(default_factory=list)

    # caches del canvas Tk
    canvas_line:    Optional[int] = field(default=None, repr=False)
    canvas_label:   Optional[int] = field(default=None, repr=False)
    canvas_lbl_bg:  Optional[int] = field(default=None, repr=False)


@dataclass
class Flowsheet:
    blocks:   Dict[int, Block]   = field(default_factory=dict)
    streams:  Dict[int, Stream]  = field(default_factory=dict)
    _next_id: int = 1

    # OPEX extras (utilities, consumibles, raw materials adicionales)
    opex_extras: List[Dict] = field(default_factory=list)
    # Overrides de Fixed Operating Costs por 'Concept' del template Turton
    fixed_overrides: Dict[str, float] = field(default_factory=dict)

    def new_id(self):
        v = self._next_id
        self._next_id += 1
        return v

    # ---- serialización ----
    def to_dict(self):
        return {
            "blocks":   {bid: {k: v for k, v in asdict(b).items()
                                if not k.startswith("canvas_")}
                         for bid, b in self.blocks.items()},
            "streams":  {sid: {k: v for k, v in asdict(s).items()
                                 if not k.startswith("canvas_")}
                         for sid, s in self.streams.items()},
            "_next_id":        self._next_id,
            "opex_extras":     list(self.opex_extras),
            "fixed_overrides": dict(self.fixed_overrides),
        }

    @staticmethod
    def from_dict(d):
        fs = Flowsheet()
        for bid, bdict in d.get("blocks", {}).items():
            b = Block(**{k: v for k, v in bdict.items()
                          if k in Block.__annotations__})
            fs.blocks[int(bid)] = b
        for sid, sdict in d.get("streams", {}).items():
            s = Stream(**{k: v for k, v in sdict.items()
                           if k in Stream.__annotations__})
            fs.streams[int(sid)] = s
        fs._next_id        = d.get("_next_id", 1)
        fs.opex_extras     = list(d.get("opex_extras", []))
        fs.fixed_overrides = dict(d.get("fixed_overrides", {}))
        return fs
