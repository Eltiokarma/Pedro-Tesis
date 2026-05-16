# ======================================================
# EQUIPMENT PURCHASED COSTS — Turton Apx A correlations
# + Lang factor for FCI estimation
# ======================================================
#
# Modelo de Turton para cada equipo:
#
#     log10(Cp°) = K1 + K2·log10(S) + K3·[log10(S)]²
#
# donde:
#   Cp°  = purchased cost a presión atmosférica, material
#          base (CS normalmente), en USD del año base.
#   S    = parámetro de tamaño (área, volumen, potencia,
#          flujo) — varía por equipo.
#   K1,2,3 = coeficientes de regresión del libro.
#
# Año base de los Cp°:  CEPCI = 397  (Sept 2001, Turton 4th
# ed).  Para llevarlo al año actual, usar el módulo cepci.py:
#
#     Cp°(año_actual) = Cp°(2001) · CEPCI[año_actual] / 397
#
# ------------------------------------------------------
# Lang factor (FCI total, instalado, desde Σ Cp°):
#
#     FCI = f_Lang · Σ Cp°
#
# Tres factores típicos:
#   fluid processing       → 4.74
#   solid-fluid processing → 3.63
#   solid processing       → 3.10
#
# ------------------------------------------------------
# Fuentes:
#   Turton, R.; Bailie, R.C.; Whiting, W.B.; Shaeiwitz,
#     J.A.; Bhattacharyya, D. (2018).  "Analysis, Synthesis,
#     and Design of Chemical Processes", 5th ed., Pearson.
#     Apéndice A, Tabla A.1.
#
# IMPORTANTE: los coeficientes acá listados son del 4th ed
# (CEPCI base = 397).  Verificalos contra tu edición antes
# de defender la tesis.  La estructura es la misma; solo
# actualizá los números si tu edición tiene otros.
# ======================================================

import math

import cepci


# ======================================================
# CEPCI BASE DE LAS CORRELACIONES
# ======================================================

CEPCI_BASE_TURTON = 397.0  # Septiembre 2001 (Turton 4th ed)


# ======================================================
# EQUIPMENT DATA
# ======================================================
# Cada entry:
#   {
#       K1, K2, K3:  coeficientes de regresión
#       S_param:     descripción del parámetro de tamaño
#       S_unit:      unidad de S (string)
#       S_min, S_max: rango de validez (extrapolar fuera
#                     genera warning)
#       categoria:   para agrupar en UI
#   }
# ======================================================

EQUIPMENT_DATA = {

    # -------- HEAT EXCHANGERS --------
    "Heat exch. — fixed tube":
        dict(K1=4.3247, K2=-0.3030, K3=0.1634,
             S_param="Heat transfer area", S_unit="m²",
             S_min=10,  S_max=1000, categoria="Heat exchangers"),
    "Heat exch. — U-tube":
        dict(K1=4.1884, K2=-0.2503, K3=0.1974,
             S_param="Heat transfer area", S_unit="m²",
             S_min=10,  S_max=1000, categoria="Heat exchangers"),
    "Heat exch. — floating head":
        dict(K1=4.8306, K2=-0.8509, K3=0.3187,
             S_param="Heat transfer area", S_unit="m²",
             S_min=10,  S_max=1000, categoria="Heat exchangers"),
    "Heat exch. — kettle reboiler":
        dict(K1=4.4646, K2=-0.5277, K3=0.3955,
             S_param="Heat transfer area", S_unit="m²",
             S_min=10,  S_max=100,  categoria="Heat exchangers"),
    "Heat exch. — double pipe":
        dict(K1=3.3444, K2=0.2745, K3=-0.0472,
             S_param="Heat transfer area", S_unit="m²",
             S_min=1,   S_max=10,   categoria="Heat exchangers"),
    "Heat exch. — multiple pipe":
        dict(K1=2.7652, K2=0.7282, K3=0.0783,
             S_param="Heat transfer area", S_unit="m²",
             S_min=10,  S_max=100,  categoria="Heat exchangers"),
    "Heat exch. — air cooler":
        dict(K1=4.0336, K2=0.2341, K3=0.0497,
             S_param="Heat transfer area", S_unit="m²",
             S_min=10,  S_max=10000, categoria="Heat exchangers"),
    "Heat exch. — flat plate":
        dict(K1=4.6656, K2=-0.1557, K3=0.1547,
             S_param="Heat transfer area", S_unit="m²",
             S_min=10,  S_max=1000, categoria="Heat exchangers"),
    "Heat exch. — spiral plate":
        dict(K1=4.6561, K2=-0.2947, K3=0.2207,
             S_param="Heat transfer area", S_unit="m²",
             S_min=1,   S_max=100,  categoria="Heat exchangers"),

    # -------- COMPRESSORS --------
    "Compressor — centrifugal":
        dict(K1=2.2897, K2=1.3604, K3=-0.1027,
             S_param="Power", S_unit="kW",
             S_min=450, S_max=3000, categoria="Compressors"),
    "Compressor — axial":
        dict(K1=2.2897, K2=1.3604, K3=-0.1027,
             S_param="Power", S_unit="kW",
             S_min=450, S_max=3000, categoria="Compressors"),
    "Compressor — reciprocating":
        dict(K1=2.2897, K2=1.3604, K3=-0.1027,
             S_param="Power", S_unit="kW",
             S_min=450, S_max=3000, categoria="Compressors"),
    "Compressor — rotary":
        dict(K1=5.0355, K2=-1.8002, K3=0.8253,
             S_param="Power", S_unit="kW",
             S_min=18,  S_max=950,  categoria="Compressors"),

    # -------- PUMPS --------
    "Pump — centrifugal":
        dict(K1=3.3892, K2=0.0536, K3=0.1538,
             S_param="Shaft power", S_unit="kW",
             S_min=1,   S_max=300,  categoria="Pumps"),
    "Pump — positive displacement":
        dict(K1=3.4771, K2=0.1350, K3=0.1438,
             S_param="Shaft power", S_unit="kW",
             S_min=1,   S_max=100,  categoria="Pumps"),
    "Pump — reciprocating":
        dict(K1=3.8696, K2=0.3161, K3=0.1220,
             S_param="Shaft power", S_unit="kW",
             S_min=0.1, S_max=200,  categoria="Pumps"),

    # -------- VESSELS & TANKS --------
    "Vessel — horizontal":
        dict(K1=3.5565, K2=0.3776, K3=0.0905,
             S_param="Volume", S_unit="m³",
             S_min=0.1, S_max=628,  categoria="Vessels"),
    "Vessel — vertical":
        dict(K1=3.4974, K2=0.4485, K3=0.1074,
             S_param="Volume", S_unit="m³",
             S_min=0.3, S_max=520,  categoria="Vessels"),
    "Tower (column shell)":
        dict(K1=3.4974, K2=0.4485, K3=0.1074,
             S_param="Volume", S_unit="m³",
             S_min=0.3, S_max=520,  categoria="Vessels"),
    "Storage tank — cone roof":
        dict(K1=4.8509, K2=-0.3973, K3=0.1445,
             S_param="Volume", S_unit="m³",
             S_min=90,  S_max=30000, categoria="Storage"),
    "Storage tank — floating roof":
        dict(K1=4.7843, K2=-0.5970, K3=0.1727,
             S_param="Volume", S_unit="m³",
             S_min=90,  S_max=30000, categoria="Storage"),

    # -------- REACTORS --------
    "Reactor — autoclave":
        dict(K1=4.5587, K2=-0.3617, K3=0.0931,
             S_param="Volume", S_unit="m³",
             S_min=1,   S_max=15,   categoria="Reactors"),
    "Reactor — jacketed agitated":
        dict(K1=4.1052, K2=0.5320, K3=-0.0005,
             S_param="Volume", S_unit="m³",
             S_min=0.1, S_max=35,   categoria="Reactors"),
    "Reactor — jacketed non-agit.":
        dict(K1=3.3496, K2=0.7235, K3=-0.0025,
             S_param="Volume", S_unit="m³",
             S_min=0.1, S_max=35,   categoria="Reactors"),

    # -------- FIRED HEATERS --------
    "Fired heater — reformer":
        dict(K1=7.3488, K2=-1.1666, K3=0.2028,
             S_param="Heat duty", S_unit="kW",
             S_min=3000, S_max=100000, categoria="Fired heaters"),
    "Fired heater — non-reformer":
        dict(K1=7.3488, K2=-1.1666, K3=0.2028,
             S_param="Heat duty", S_unit="kW",
             S_min=1000, S_max=100000, categoria="Fired heaters"),

    # -------- DRYERS / EVAPORATORS / CRYSTALLIZERS --------
    "Crystallizer":
        dict(K1=4.6900, K2=-0.0490, K3=0.1390,
             S_param="Volume", S_unit="m³",
             S_min=1,   S_max=200,  categoria="Solids / sep."),
    "Dryer — drum":
        dict(K1=4.5472, K2=0.2731, K3=0.1340,
             S_param="Heat-transfer area", S_unit="m²",
             S_min=5,   S_max=100,  categoria="Solids / sep."),
    "Evaporator — vertical":
        dict(K1=4.6973, K2=0.3098, K3=0.1257,
             S_param="Heat-transfer area", S_unit="m²",
             S_min=10,  S_max=1000, categoria="Solids / sep."),
    "Filter — belt":
        dict(K1=5.5670, K2=-0.6092, K3=0.5413,
             S_param="Filtration area", S_unit="m²",
             S_min=10,  S_max=80,   categoria="Solids / sep."),

    # -------- FANS / BLOWERS --------
    "Fan — centrifugal radial":
        dict(K1=3.5391, K2=-0.3533, K3=0.4477,
             S_param="Fluid flow", S_unit="m³/s",
             S_min=1,   S_max=100,  categoria="Fans / blowers"),
    "Fan — axial":
        dict(K1=3.1761, K2=-0.1373, K3=0.3414,
             S_param="Fluid flow", S_unit="m³/s",
             S_min=1,   S_max=100,  categoria="Fans / blowers"),

    # -------- TRAYS (per tray, columna se cobra aparte) --------
    "Tray — sieve":
        dict(K1=2.9949, K2=0.4465, K3=0.3961,
             S_param="Tray area", S_unit="m²",
             S_min=0.07, S_max=12.3, categoria="Trays / packing"),
    "Tray — valve":
        dict(K1=3.3322, K2=0.4838, K3=0.3434,
             S_param="Tray area", S_unit="m²",
             S_min=0.07, S_max=12.3, categoria="Trays / packing"),

    # -------- MIXERS / SPLITTERS --------
    "Mixer — inline":
        dict(K1=3.4974, K2=0.4485, K3=0.1074,
             S_param="Volume", S_unit="m³",
             S_min=0.1, S_max=10, categoria="Mixers / splitters"),
    "Mixer — static":
        dict(K1=3.0566, K2=0.4485, K3=0.1074,
             S_param="Volume", S_unit="m³",
             S_min=0.05, S_max=2, categoria="Mixers / splitters"),
    "Splitter — flow divider":
        dict(K1=2.5000, K2=0.3500, K3=0.0500,
             S_param="Flow", S_unit="kg/s",
             S_min=0.1, S_max=50, categoria="Mixers / splitters"),

    # -------- SEPARADORES sólidos/líquidos extra --------
    "Centrifuge — disc stack":
        dict(K1=4.8210, K2=0.6710, K3=0.0780,
             S_param="Volume", S_unit="m³",
             S_min=0.05, S_max=2.5, categoria="Solids / sep."),
    "Centrifuge — decanter":
        dict(K1=4.4500, K2=0.5990, K3=0.0480,
             S_param="Flow", S_unit="m³/h",
             S_min=1, S_max=100, categoria="Solids / sep."),
    "Cyclone — gas/solid":
        dict(K1=3.5400, K2=0.3060, K3=0.0260,
             S_param="Flow", S_unit="m³/s",
             S_min=0.1, S_max=15, categoria="Solids / sep."),
    "Decanter — gravity":
        dict(K1=3.4974, K2=0.4485, K3=0.1074,
             S_param="Volume", S_unit="m³",
             S_min=0.3, S_max=520, categoria="Vessels"),

    # -------- VÁLVULAS (proceso) --------
    "Valve — control globe":
        dict(K1=2.3700, K2=1.2840, K3=0.0,
             S_param="Flow", S_unit="m³/h",
             S_min=0.1, S_max=200, categoria="Valves"),
    "Valve — relief":
        dict(K1=2.5670, K2=0.4500, K3=0.0,
             S_param="Capacity", S_unit="m³/h",
             S_min=0.5, S_max=100, categoria="Valves"),
    "Valve — 3-way":
        dict(K1=2.4500, K2=0.5000, K3=0.0,
             S_param="Flow", S_unit="m³/h",
             S_min=0.1, S_max=100, categoria="Valves"),

    # -------- UTILITIES (planta de servicios auxiliares) --------
    # Caldera de vapor — equipo industrial que produce steam para el
    # proceso a partir de combustible y agua tratada.
    "Boiler — fire tube":
        dict(K1=6.6940, K2=0.1801, K3=0.0942,
             S_param="Steam output", S_unit="kg/s",
             S_min=0.1, S_max=20, categoria="Utilities"),
    "Boiler — water tube":
        dict(K1=7.0489, K2=0.4071, K3=0.1296,
             S_param="Steam output", S_unit="kg/s",
             S_min=2,   S_max=50, categoria="Utilities"),

    # Torre de enfriamiento — produce agua fría circulante para todos
    # los HX/condensadores de cooling water del proceso.
    "Cooling tower — induced draft":
        dict(K1=4.9090, K2=0.5990, K3=0.0440,
             S_param="Cooling duty", S_unit="MW",
             S_min=1,   S_max=80,  categoria="Utilities"),
    "Cooling tower — natural draft":
        dict(K1=5.1330, K2=0.6280, K3=0.0480,
             S_param="Cooling duty", S_unit="MW",
             S_min=10,  S_max=200, categoria="Utilities"),
}


# ======================================================
# LANG FACTORS
# ======================================================

LANG_FACTORS = {
    "Fluid processing":        4.74,
    "Solid-fluid processing":  3.63,
    "Solid processing":        3.10,
}

LANG_DEFAULT = "Fluid processing"


# ======================================================
# BARE MODULE FACTORS (Turton App A.5)
# ======================================================
# FBM = B1 + B2·FM·FP — acá usamos valores típicos a CS / atm
# como base.  FP se computa aparte de la presión de operación.
# FM=1 (carbon steel) por default; user puede override por material
# de construcción si tiene servicio corrosivo (Cl2, HNO3, etc.).
FBM_BY_CATEGORIA = {
    # Keys exactos como aparecen en EQUIPMENT_DATA["categoria"]
    "Heat exchangers":     3.17,   # shell & tube CS
    "Fired heaters":       2.19,
    "Pumps":               3.30,   # centrifugal CS
    "Compressors":         2.70,   # motor-driven
    "Reactors":            4.00,   # autoclave / jacketed CS
    "Storage":             1.50,   # tanques cone/floating
    "Vessels":             4.16,   # process vessels horiz/vert
    "Trays / packing":     1.00,
    "Mixers / splitters":  2.10,
    "Solids / sep.":       2.50,   # filtros, ciclones, decantadores
    "Fans / blowers":      2.40,
    "Valves":              1.50,
    "Utilities":           3.50,   # boiler, cooling tower
    # Aliases por si el user usa nombres alt
    "Towers":              4.16,
    "Tanks":               1.50,
    "Filters":             2.50,
    "Dryers":              2.06,
    "Evaporators":         2.45,
    "Crystallizers":       2.06,
    "Turbines":            6.10,
}
FBM_DEFAULT = 3.17     # fallback genérico (≈ HX)


def bare_module_factor(eq_nombre, P_op_bar=1.0):
    """Devuelve FBM corregido por presión para un equipo.

    Usa la categoría del equipo (Turton App A.5 mean) y aplica un
    factor de presión simplificado:
      · vessels/towers/reactors:  FP_v = 1 + 0.0175·(P - 1)
      · heat exchangers:          FP_hx = 1 + 0.012·(P - 1)
      · otros (pumps, compres, tanks): no FP correction
    Cap a P=200 bar (correlaciones Turton son válidas hasta ~150).

    Es una APROXIMACIÓN — la Eq 7.5 de Turton tiene coeficientes
    específicos por D, MoC, tipo de servicio; acá damos un primer
    orden razonable para visualización en el xlsx de costing."""
    spec = EQUIPMENT_DATA.get(eq_nombre, {})
    cat  = spec.get("categoria", "")
    fbm_base = FBM_BY_CATEGORIA.get(cat, FBM_DEFAULT)
    p = max(1.0, min(200.0, float(P_op_bar)))
    if cat in ("Vessels", "Towers", "Reactors"):
        fp = 1.0 + 0.0175 * (p - 1.0)
    elif cat == "Heat exchangers":
        fp = 1.0 + 0.012 * (p - 1.0)
    else:
        fp = 1.0
    return fbm_base * fp, fbm_base, fp


def bare_module_cost(eq_nombre, S, P_op_bar=1.0, year_target=None):
    """Costo del módulo desnudo (CBM) Turton = Cp × FBM.

    Returns:
        dict con Cp_target, FBM, FP, FBM_base, CBM, fuera_rango, ...

    Si el equipo no está en EQUIPMENT_DATA (custom type, mock o
    typo), devuelve costos cero con flag 'unknown'=True para no
    romper el costing global.  El user ve el warning en el xlsx."""
    if eq_nombre not in EQUIPMENT_DATA:
        return {
            "Cp_base": 0.0, "Cp_target": 0.0,
            "year_base": 2001,
            "year_target": year_target or 2001,
            "cepci_factor": 1.0, "fuera_rango": False,
            "S": S, "S_min": 0, "S_max": 0, "S_unit": "",
            "FBM": 0.0, "FBM_base": 0.0, "FP": 1.0,
            "CBM": 0.0, "unknown": True,
        }
    pc = purchased_cost(eq_nombre, S, year_target=year_target)
    fbm, fbm_base, fp = bare_module_factor(eq_nombre, P_op_bar=P_op_bar)
    cbm = pc["Cp_target"] * fbm
    pc["FBM"]      = fbm
    pc["FBM_base"] = fbm_base
    pc["FP"]       = fp
    pc["CBM"]      = cbm
    pc["unknown"]  = False
    return pc


# ======================================================
# COST OF MANUFACTURE — Turton Eq 8.2 (with depreciation)
# ======================================================
def cost_of_manufacture(FCI_usd, COL_usd, CUT_usd, CRM_usd, CWT_usd):
    """Calcula COM (Cost of Manufacture) según Turton Eq 8.2:

        COM_d  =  0.180·FCI + 2.73·COL + 1.23·(CUT + CRM + CWT)

    Y la versión sin depreciación (COM):
        COM    =  0.305·FCI + 2.73·COL + 1.23·(CUT + CRM + CWT)

    Inputs todos en USD/año (excepto FCI que es one-time CAPEX).

    Returns:
        dict con COM_d, COM, breakdown por componente.
    """
    base = 1.23 * (CUT_usd + CRM_usd + CWT_usd)
    labor_term = 2.73 * COL_usd
    com_d  = 0.180 * FCI_usd + labor_term + base
    com    = 0.305 * FCI_usd + labor_term + base
    return {
        "FCI":     FCI_usd,
        "COL":     COL_usd,
        "CUT":     CUT_usd,
        "CRM":     CRM_usd,
        "CWT":     CWT_usd,
        "0.180·FCI": 0.180 * FCI_usd,
        "0.305·FCI": 0.305 * FCI_usd,
        "2.73·COL":  labor_term,
        "1.23·(CUT+CRM+CWT)": base,
        "COM_d":   com_d,   # con depreciación (recomendado)
        "COM":     com,     # sin depreciación
    }


# ======================================================
# CONSULTAS
# ======================================================

def listar_equipos():
    """Devuelve la lista ordenada de nombres de equipos."""
    return sorted(EQUIPMENT_DATA.keys())


def por_categoria():
    """Devuelve dict categoría → [nombres]."""
    cats = {}
    for nombre, spec in EQUIPMENT_DATA.items():
        cats.setdefault(spec["categoria"], []).append(nombre)
    for nombres in cats.values():
        nombres.sort()
    return cats


def info(nombre):
    """Devuelve el dict de spec del equipo."""
    return EQUIPMENT_DATA[nombre]


# ======================================================
# CÁLCULO DE Cp°
# ======================================================

def purchased_cost(nombre, S, year_target=None):
    """Calcula Cp° (purchased cost a CS y atm) para `nombre`
    con tamaño S.

    Si year_target es dado, el resultado queda escalado
    por CEPCI al año destino.  Default: año base (2001).

    Devuelve dict con:
        Cp_base, Cp_target, year_base, year_target,
        cepci_factor, fuera_rango (bool), S, S_min, S_max
    """

    spec = EQUIPMENT_DATA[nombre]

    if S <= 0:
        raise ValueError(f"S debe ser positivo (recibido {S})")

    logS = math.log10(S)
    log_cp = spec["K1"] + spec["K2"] * logS + spec["K3"] * (logS ** 2)
    Cp_base = 10 ** log_cp  # USD a CEPCI=397

    fuera = (S < spec["S_min"]) or (S > spec["S_max"])

    if year_target is None:
        year_target = 2001
        factor = 1.0
        Cp_target = Cp_base
    else:
        factor = cepci.CEPCI.get(year_target, cepci._valor_cepci(year_target)) / CEPCI_BASE_TURTON
        Cp_target = Cp_base * factor

    return {
        "Cp_base":      Cp_base,
        "Cp_target":    Cp_target,
        "year_base":    2001,
        "year_target":  year_target,
        "cepci_factor": factor,
        "fuera_rango":  fuera,
        "S":            S,
        "S_min":        spec["S_min"],
        "S_max":        spec["S_max"],
        "S_unit":       spec["S_unit"],
    }


# ======================================================
# FCI VÍA LANG
# ======================================================

def lang_fci(equipment_list, plant_type="Fluid processing", year_target=None):
    """Estima FCI con Lang factor.

    equipment_list: lista de dicts {"nombre": str, "S": float, "n": int=1}
    plant_type:     una de LANG_FACTORS
    year_target:    año al que escalar Cp° (CEPCI).  Si None,
                    usa el año base (2001).

    Devuelve dict con:
        items:        lista de items con detalle por equipo
                      (Cp_unitario, Cp_total = n × Cp,
                      fuera_rango, etc.)
        sum_Cp:       Σ Cp en el año destino
        lang_factor:  f_L aplicado
        FCI:          f_L × Σ Cp en USD
        FCI_MMUSD:    FCI / 1e6
        warnings:     lista de strings (equipos fuera de
                      rango, etc.)
    """

    if plant_type not in LANG_FACTORS:
        raise ValueError(
            f"plant_type debe ser uno de {list(LANG_FACTORS)} "
            f"(recibido {plant_type!r})"
        )

    items = []
    sum_Cp = 0.0
    warnings = []

    for item in equipment_list:
        nombre = item["nombre"]
        S = float(item["S"])
        n = int(item.get("n", 1))

        if nombre not in EQUIPMENT_DATA:
            warnings.append(f"Equipo desconocido: {nombre}")
            continue

        if n <= 0:
            warnings.append(f"{nombre}: cantidad debe ser ≥ 1 (saltado)")
            continue

        try:
            r = purchased_cost(nombre, S, year_target=year_target)
        except ValueError as e:
            warnings.append(f"{nombre}: {e}")
            continue

        Cp_unit = r["Cp_target"]
        Cp_total = Cp_unit * n
        sum_Cp += Cp_total

        if r["fuera_rango"]:
            warnings.append(
                f"{nombre}: S={S} {r['S_unit']} fuera de rango "
                f"[{r['S_min']}, {r['S_max']}] — extrapolación"
            )

        items.append({
            "nombre":       nombre,
            "n":            n,
            "S":            S,
            "S_unit":       r["S_unit"],
            "Cp_unitario":  Cp_unit,
            "Cp_total":     Cp_total,
            "fuera_rango":  r["fuera_rango"],
        })

    f_L = LANG_FACTORS[plant_type]
    FCI = f_L * sum_Cp

    return {
        "items":       items,
        "sum_Cp":      sum_Cp,
        "plant_type":  plant_type,
        "lang_factor": f_L,
        "year_target": year_target if year_target else 2001,
        "FCI":         FCI,
        "FCI_MMUSD":   FCI / 1e6,
        "warnings":    warnings,
    }


# ======================================================
# DESCOMPOSICIÓN ISBL / OSBL / ENG / CONT desde FCI Lang
# ======================================================
# Lang asume que el FCI ya incluye todo: ISBL, OSBL,
# engineering, contingency.  Pero el modelo económico de
# este software pide ISBL como input y deriva el resto por
# porcentajes.  Esta función hace la inversa: dado FCI_lang
# y los % de OSBL/ENG/CONT del proyecto, devuelve el ISBL
# implícito.
#
#     FCI = ISBL × (1 + OSBL%) × (1 + ENG% + CONT%)
#
# →   ISBL = FCI / [(1 + OSBL%) × (1 + ENG% + CONT%)]
# ======================================================

def isbl_implicito(FCI, OSBL_pct, ENG_pct, CONT_pct):
    """Despeja ISBL del FCI estimado por Lang, dados los
    porcentajes que usa el resto del modelo.

    Args (todos como fracción, no %):
        FCI, OSBL_pct, ENG_pct, CONT_pct

    Devuelve: ISBL (mismas unidades que FCI).
    """
    factor = (1 + OSBL_pct) * (1 + ENG_pct + CONT_pct)
    return FCI / factor
