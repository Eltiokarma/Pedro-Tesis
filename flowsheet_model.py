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

    # ---- SUDOKU LOCK ----
    # True si el user fijó este duty (specification).  False si lo
    # debe inferir el solver desde el balance de energía.  Cargado
    # desde JSON / examples mediante heurística (duty != 0 → locked).
    duty_locked: bool = False

    # ---- REACTOR DE EQUILIBRIO (Capa 4) ----
    # Lista de IDs de reactions_db que ocurren en este bloque (e.g.
    # ['R003','R002'] para un reformador SMR+WGS).  Si está vacía,
    # el bloque NO es reactor de equilibrio (pero puede seguir siendo
    # reactor "manual" via heat_of_reaction declarado).
    # Si tiene reacciones, el solver:
    #   1. Lee composición del inlet
    #   2. Resuelve equilibrio multi-reacción a (T_op_K, P_op_bar)
    #   3. Setea composición del outlet
    #   4. Setea heat_of_reaction automáticamente desde Σ ξ·ΔH(T)
    reactions: List[str] = field(default_factory=list)
    T_op_K:    float = 0.0     # 0 = usar T promedio del input
    P_op_bar:  float = 1.0
    # Modo del solver (Capas 4 y 5):
    #   'equilibrium' — Newton-Raphson minimización Gibbs (Capa 4).
    #                    Ignora reactor_volume_L.  Default backward-compat.
    #   'pfr'         — integración RK4 con cinética Arrhenius (Capa 5).
    #                    Requiere reactor_volume_L > 0 y cinética
    #                    disponible para todas las reacciones del set.
    #   'cstr'        — algebraico Newton-Raphson con cinética (Capa 5).
    #                    Robusto incluso para cinéticas stiff.
    reactor_mode: str = "equilibrium"
    # Volumen del reactor en LITROS (no m³, para valores amigables).
    # Solo aplica si reactor_mode ∈ {'pfr', 'cstr'}.
    reactor_volume_L: float = 0.0

    # ---- COLUMNA DE DESTILACIÓN (FUG / McCabe-Thiele, Capa 6) ----
    # Si column_active es True y el bloque es tipo Tower/column, el
    # solver computa AUTOMÁTICAMENTE las composiciones de los outputs
    # (distillate y bottom) y los duties (Q_cond, Q_reb) desde el
    # feed via FUG + Fenske-Hengstebeck.  Sin esto, el user debe
    # declarar manualmente.
    column_active:    bool  = False
    column_LK:        str   = ""        # light key (más volátil)
    column_HK:        str   = ""        # heavy key
    column_x_D_LK:    float = 0.95      # pureza objetivo LK en destilado
    column_x_B_LK:    float = 0.05      # frac LK en fondo (= 1 - recovery)
    column_R_factor:  float = 1.3       # ratio R/R_min (1.2-1.5 típico)

    # ---- FLASH DRUM (vessel con VLE, Capa 6) ----
    # Si flash_active es True y el bloque es tipo Vessel, el solver
    # calcula AUTOMÁTICAMENTE las composiciones de los outputs
    # (vapor y líquido) usando flash isotérmico NRTL (γ·P_sat).
    flash_active:  bool  = False
    flash_T_K:     float = 298.15
    flash_P_bar:   float = 1.013

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

    # ---- SUDOKU LOCKS ----
    # True si el user FIJÓ este valor (es una specification del problema).
    # False si el solver lo computa desde balance de masa/energía/composición.
    # En load de JSONs viejos, se infiere por heurística:
    #   mass_flow_locked   = (mass_flow > 0)
    #   temperature_locked = (temperature != T_REF_C)
    #   composition_locked = bool(composition)
    mass_flow_locked:   bool = False
    temperature_locked: bool = False
    composition_locked: bool = False

    # ---- DISPLAY (UI) ----
    # Número que muestra la pill en el editor.  0 = auto (numeración
    # topológica desde feeds asignada por assign_stream_numbers).
    # Si el user lo setea manualmente, ese número se respeta.
    display_number: int = 0

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

    # ---- ENDPOINTS FLOTANTES (streams desconectados) ----
    # Convención:
    #   src == -1  ⇒  endpoint START desconectado, usa start_xy
    #   dst == -1  ⇒  endpoint END desconectado,   usa end_xy
    # Cuando un endpoint está flotante, el solver SKIPEA el stream del
    # balance de masa (no entra en Σ in ni Σ out de ningún bloque).
    # El stream se sigue mostrando en la UI con status 'unrun' (azul
    # punteado).  Útil para borradores o conexiones pendientes durante
    # la edición.
    # Si src != -1 (conectado), start_xy se ignora y la posición se
    # calcula del puerto del bloque.  Lo mismo end_xy.
    start_xy: List[float] = field(default_factory=list)  # [x,y] o []
    end_xy:   List[float] = field(default_factory=list)  # [x,y] o []

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
            # Sudoku lock migration: si el JSON no traía duty_locked,
            # inferir desde valor (duty != 0 → user lo declaró).
            if "duty_locked" not in bdict:
                b.duty_locked = (abs(b.duty) > 1e-9)
            fs.blocks[int(bid)] = b
        for sid, sdict in d.get("streams", {}).items():
            s = Stream(**{k: v for k, v in sdict.items()
                           if k in Stream.__annotations__})
            # Sudoku lock migration: heurística desde valores.
            if "mass_flow_locked" not in sdict:
                s.mass_flow_locked = (s.mass_flow > 0)
            if "temperature_locked" not in sdict:
                s.temperature_locked = abs(s.temperature - T_REF_C) > 0.01
            if "composition_locked" not in sdict:
                s.composition_locked = bool(s.composition) or bool(s.main_component)
            fs.streams[int(sid)] = s
        fs._next_id        = d.get("_next_id", 1)
        fs.opex_extras     = list(d.get("opex_extras", []))
        fs.fixed_overrides = dict(d.get("fixed_overrides", {}))
        return fs
