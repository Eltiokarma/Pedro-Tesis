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

    # ---- HIDRÁULICA: ΔP a través del bloque ----
    # Positivo si el bloque SUMA presión (bomba, compresor).
    # Negativo si la PIERDE (HX, columna, válvula, filter).
    # 0 si pasa P inalterada (mixer, splitter, vessel sin pérdida).
    # Si el block es Pump/Compressor, el solver puede calcular este
    # delta_p desde efficiency + flow + ΔP target.
    delta_p_bar: float  = 0.0
    # Eficiencia para bombas/compresores (η_hidráulica · η_motor).
    # Default 0.75 (típico bomba centrífuga), 0.70 compresor.
    # Solver calcula W_elec = m·ΔP/(ρ·η) y la setea como duty.
    efficiency:  float  = 0.75

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
    #   'batch'       — integración RK4 dN/dt, V constante, P emergente
    #                    (Capa 5).  Requiere reactor_volume_L > 0 y
    #                    batch_time_s > 0.  P NO constante.
    reactor_mode: str = "equilibrium"
    # Volumen del reactor en LITROS (no m³, para valores amigables).
    # Solo aplica si reactor_mode ∈ {'pfr', 'cstr', 'batch'}.
    reactor_volume_L: float = 0.0
    # Tiempo de tanda [s].  Solo aplica si reactor_mode == 'batch'.
    # El batch integra dN/dt de 0 a este tiempo a V constante.
    batch_time_s: float = 3600.0

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
    # Método de cálculo:
    #   'fug'        — Fenske-Underwood-Gilliland shortcut (default,
    #                  rápido, válido para binarios y aprox multicomp)
    #   'wanghenke'  — MESH riguroso multicomp por etapa (Capa 6+).
    #                  Necesita N (column_N_stages) y feed_stage.
    column_method:    str   = "fug"
    column_N_stages:  int   = 0         # solo para 'wanghenke', 0 = usa N de FUG

    # ---- FLASH DRUM (vessel con VLE, Capa 6) ----
    # Si flash_active es True y el bloque es tipo Vessel, el solver
    # calcula AUTOMÁTICAMENTE las composiciones de los outputs
    # (vapor y líquido) usando flash isotérmico NRTL (γ·P_sat).
    flash_active:  bool  = False
    flash_T_K:     float = 298.15
    flash_P_bar:   float = 1.013

    # ---- SPLITTER automático (mezcla pasa, mass distribuido) ----
    # Si splitter_active=True, el solver distribuye mass_flow del
    # input según splitter_fractions (deben sumar 1.0 entre los
    # outputs en el orden que aparezcan en fs.streams).
    # La composición se PROPAGA idéntica a todos los outputs (split
    # físico, no separación).
    # Aplica a bloques tipo Mixer, splitter genérico, manifold.
    splitter_active:    bool       = False
    splitter_fractions: List[float] = field(default_factory=list)

    # ---- SEPARADOR MECÁNICO sólido/líquido (filtro, centrífuga) ----
    # Si separator_active=True y eq_type es Filter — belt o Centrifuge,
    # el solver computa AUTOMÁTICAMENTE el split entre torta (cake)
    # y madre (filtrate/liquor) usando recovery + humedad declaradas.
    # Sin esto, el user debe declarar manualmente las composiciones.
    #   solids_recovery:  fracción del sólido (solid_components) que
    #                     va a la torta.  El resto va a la madre.
    #   cake_moisture:    fracción másica de líquido (resto de comps)
    #                     en la torta (humedad residual).
    #   solid_components: keys de los componentes considerados "sólido"
    #                     (el resto del catálogo se trata como líquido).
    separator_active:   bool       = False
    solids_recovery:    float      = 0.95
    cake_moisture:      float      = 0.30
    solid_components:   List[str]  = field(default_factory=list)

    # ---- SECADOR (Dryer — drum) ----
    # Si dryer_active=True y eq_type es Dryer — drum, el solver computa
    # AUTOMÁTICAMENTE el producto seco a humedad final + venteo de
    # vapor del componente humectante.
    #   final_moisture:     frac másica del moisture_component en producto
    #   moisture_component: key del componente que se evapora (default
    #                       "water"; otro: "ethanol" en secado azeotrópico)
    dryer_active:        bool   = False
    final_moisture:      float  = 0.02
    moisture_component:  str    = "water"

    # ---- CRISTALIZADOR (Crystallizer) ----
    # Si crystallizer_active=True y eq_type es Crystallizer, el solver
    # extrae solute_component a producto (cristales) según crystal_yield
    # y manda el resto a la madre (venteo).
    #   solute_component: key del compuesto que cristaliza
    #   crystal_yield:    fracción de solute que pasa a cristales
    crystallizer_active: bool   = False
    solute_component:    str    = ""
    crystal_yield:       float  = 0.80

    # ---- EVAPORADOR (Evaporator — vertical) ----
    # Si evaporator_active=True y eq_type es Evaporator — vertical, el
    # solver computa AUTOMÁTICAMENTE el concentrado + vapor de salida
    # usando concentration_factor.
    #   concentration_factor: ratio de sólidos out/in (e.g. 2.0 → la
    #                         masa cae a la mitad por evaporación)
    #   volatile_component:   key del compuesto volátil que se evapora
    #                         (default "water")
    evaporator_active:    bool   = False
    concentration_factor: float  = 2.0
    volatile_component:   str    = "water"

    # ---- CICLÓN (Cyclone — gas/solid) ----
    # Si cyclone_active=True y eq_type es Cyclone — gas/solid, el solver
    # separa sólidos del gas portador según collection_efficiency.
    #   collection_efficiency: fracción del sólido recolectado en
    #                          producto (sólido).  El resto + gas → venteo.
    # Los sólidos se identifican igual que en separator (solid_components),
    # pero como ciclones suelen tratar UN polvo dominante, también acepta
    # main_component del feed como sólido si solid_components está vacío.
    cyclone_active:        bool      = False
    collection_efficiency: float     = 0.90

    # ---- OPERACIÓN POR LOTES (batch) — declarativo, Capa 1+3 ----
    # Clasificación del bloque respecto al modo batch:
    #   "continuous" (default) — opera en steady state aunque exista
    #                            una sección batch en el flowsheet.
    #                            Comportamiento idéntico al pre-batch.
    #   "native"               — equipo batch-nativo (reactor batch,
    #                            cristalizador, secador drum, vessel
    #                            usado como tanque de carga).  Se
    #                            dimensiona por volumen de lote.
    #   "auxiliary"            — continuo por naturaleza pero opera
    #                            en ventanas intermitentes del ciclo
    #                            (bomba de carga/descarga, HX del
    #                            chaqueta, mixer).  Se dimensiona por
    #                            su PICO durante la ventana, no por
    #                            el promedio anual.
    # task_ref: nombre de la Task de BatchRecipe a la que el bloque
    #           está vinculado (para native/auxiliary).  El cruce
    #           Block↔Task se usa en Capa 2 (sizing) y Capa 3
    #           (utility peaks por bloque), NO en Capa 1.
    # Regla aditiva: un proyecto sin batch tiene batch_role
    # "continuous" en todos los bloques → comportamiento legacy.
    batch_role: str = "continuous"
    task_ref:   str = ""

    # ---- REACCIONES CUSTOM (in-memory, NO en data/reactions_db.md) ----
    # Lista de dicts con esquema reaction_from_dict() (reactions_db.py).
    # Cada dict: {id, name, stoich, dh_rxn_298_kJ_mol, ds_rxn_298_J_mol_K
    # ó keq_298, T_min_K, T_max_K, irreversible}.
    # El solver las fusiona con b.reactions (IDs del catálogo) en
    # solve_equilibrium_reactors antes de invocar el equilibrio.
    # Persiste en JSON automáticamente (List[dict] de primitivos).
    # Default [] → compat con flowsheets viejos.
    custom_reactions: List[dict] = field(default_factory=list)

    # ---- OVERRIDES de transferencia de calor (HX sizing) ----
    # Solo aplican a bloques con categoria='Heat exchangers'.  Cuando
    # están seteados (>0), size_heat_exchanger los usa en lugar de las
    # tablas U_TYPICAL / DTLM_TYPICAL.  Default None = "no override"
    # (el solver usa el valor típico de tabla por eq_type).
    #
    # Casos donde el user quiere override:
    #   · Condensación de vapor de agua puro: U ≈ 1500 W/m²·K
    #   · Aceite térmico denso a baja vel.:   U ≈ 200 W/m²·K
    #   · Close-approach con plate-frame:     ΔT_lm ≈ 5 K
    U_override:     Optional[float] = None     # W/m²·K
    dtlm_override:  Optional[float] = None     # K

    # ---- OVERRIDES de columnas de destilación (size_tower) ----
    # Solo aplican a bloques eq_type='Tower (column shell)'.  None
    # (default) → el solver usa los defaults canónicos de
    # econ_defaults.COLUMN_DEFAULTS (K_SB=0.06, tray_spacing=0.6 m,
    # head=3.0 m, tray_eff=1.0, HETP=0.5 m).
    #
    # Casos de uso:
    #   · tray_spacing 0.46 m (18") para columnas chicas
    #   · tray_spacing 0.76 m (30") para columnas con high foaming
    #   · K_souders_brown 0.04 con foaming severo
    #   · tray_efficiency 0.65 para etanol/agua, 0.50 para amine
    #   · HETP 0.30 m para empaque estructurado de alta eficiencia
    #   · column_head_height_m=5 m si hay condensador externo grande
    # packing_type:
    #   ""        → columna de platos (default, usa N · tray_spacing)
    #   "random"  → empacada con anillos (usa N · HETP)
    #   "structured" → empacada Mellapak (usa N · HETP)
    tray_spacing_m:        Optional[float] = None
    K_souders_brown:       Optional[float] = None
    column_head_height_m:  Optional[float] = None
    tray_efficiency:       Optional[float] = None
    HETP_m:                Optional[float] = None
    packing_type:          str             = ""

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

    # ---- PRESIÓN (Capa de hidráulica) ----
    # Presión absoluta de la corriente.  Se propaga por el solver:
    #   bombas/compresores SUMAN delta_p_bar al input
    #   columnas/HX RESTAN delta_p_bar (pérdida por equipo)
    #   tuberías RESTAN ΔP calculado por pressure_drop (Darcy-Weisbach)
    pressure_bar: float = 1.013      # default 1 atm
    pressure_locked: bool = False    # spec: True si el user la fijó

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

    # ---- Pérdida de carga (tubería del stream) ----
    # Para calcular ΔP via Darcy-Weisbach.  Si pipe_length_m=0 (default),
    # el cálculo asume 10 m, suficiente para un primer estimado.
    pipe_length_m:    float = 0.0     # longitud equivalente m (0 = default 10)
    pipe_diameter_m:  float = 0.0     # diámetro interno m (0 = default 0.05 = 2")
    pipe_roughness_m: float = 4.5e-5  # rugosidad — acero comercial default
    # Suma de K de accesorios (codos, válvulas, T, reducciones, etc).
    # ΔP_local = K_total · ρ · v² / 2  (suma al ΔP friccional).
    # Valores típicos (suma manual):
    #   Codo 90° estándar: 0.75
    #   Codo 45°: 0.35
    #   Tee (paso recto): 0.6
    #   Válvula globo abierta: 10
    #   Válvula gate abierta: 0.17
    #   Reducción gradual: 0.04
    #   Expansión brusca: 1
    #   Entrada brusca a tanque: 1
    pipe_K_local:     float = 0.0     # K total de accesorios

    # ---- Modo de la corriente (Hallazgo 4-C) ----
    # False (default) = corriente CONCEPTUAL: solo estado termo
    #                   (mass_flow, T, P, composition).  El solver NO
    #                   calcula ΔP de tubería para esta corriente.
    #                   Mantiene la UX exploratoria limpia (sin ΔP
    #                   fantasma en flowsheets escolares/conceptuales).
    # True  = TUBERÍA física: el solver calcula ΔP Darcy-Weisbach
    #         con pipe_length_m / pipe_diameter_m / pipe_roughness_m
    #         / pipe_K_local.  Para flowsheets de diseño detallado.
    # Compat JSON viejo: default False; loader puede inferir True si
    # hay geometría no-default + pressure_locked (heurística).
    is_pipe: bool = False

    # ---- OPERACIÓN POR LOTES (declarativo, hook transitorio) ----
    # Ventana de actividad batch:
    #   None (default) → corriente CONTINUA, comportamiento idéntico
    #                    al pre-batch (solver y validación la tratan
    #                    como permanente).
    #   {"task_ref": <nombre_tarea>, "active": bool}
    #                  → la corriente existe físicamente solo durante
    #                    esa tarea del ciclo.  PURAMENTE DECLARATIVO
    #                    en esta fase: ni solver ni flowsheet_validation
    #                    lo leen.  Es el equivalente a ode_hook pero
    #                    para corrientes — deja la metadata para que
    #                    la dinámica transitoria futura (Capa 4+) la
    #                    use sin tener que rediseñar la estructura.
    # Regla aditiva: un Stream sin batch_window se comporta byte-
    # idéntico a hoy.  Lectura defensiva con .get() en consumers.
    batch_window: Optional[dict] = field(default=None)

    # ---- TIPO DE CORRIENTE (mass / energy) ----
    # "mass"  (default) → corriente material clásica.  El solver
    #                     calcula balance de masa y energía vía
    #                     entalpía sensible del fluido.
    # "energy" → corriente PURA DE CALOR (Q en kW).  No transporta
    #            materia.  energy_kW > 0 indica calor que sale del
    #            block src y entra al block dst.  El solver:
    #              · block.src.duty += energy_kW  (extrae calor)
    #              · block.dst.duty -= energy_kW  (recibe calor)
    #            Útil para representar cross-exchange explícito o
    #            integración térmica (Pinch).  Conservación
    #            automática por construcción.  Si la corriente está
    #            flotante (src<=0 o dst<=0), se IGNORA.
    stream_kind: str   = "mass"
    energy_kW:   float = 0.0

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
