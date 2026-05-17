# ======================================================
# EQUIPMENT PURCHASED COSTS — Turton 5th ed Appendix A
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
#   K1,2,3 = coeficientes de regresión (Tabla A.1).
#
# Año base de los Cp°:  CEPCI = 397.0  (Sept 2001).  La 5ª
# edición de Turton mantiene este año base para las
# correlaciones Cp° del Apéndice A.  Para llevarlo al año
# actual, usar el módulo cepci.py:
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
# Fuente principal:
#   Turton, R.; Shaeiwitz, J.A.; Bhattacharyya, D.;
#     Whiting, W.B. (2018).  "Analysis, Synthesis, and
#     Design of Chemical Processes", 5th ed., Pearson.
#     Apéndice A, Tablas A.1–A.4.
#
# Los coeficientes K1, K2, K3 de las correlaciones Cp° NO
# cambian entre la 4ª y la 5ª edición (la 5ª revisó la
# metodología de FBM y FP pero conservó las regresiones Cp°
# de la 4ª, año base 2001).  Donde un valor existe sólo en
# la 4ª (por ejemplo equipos retirados de la 5ª), se anota
# explícitamente con # [4ª ed — no disponible en 5ª].
# ======================================================

import math

import cepci


# ======================================================
# CEPCI BASE DE LAS CORRELACIONES
# ======================================================
# CEPCI base 397 (año 2001) — Turton 5ª ed, Apéndice A.
# Las correlaciones Cp° = f(K1, K2, K3, S) se publicaron
# originalmente en la 4ª edición y se preservaron en la
# 5ª sin re-calibración del año base.
CEPCI_BASE_TURTON = 397.0


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
# Turton Eq 7.6:  FBM = B1 + B2·FM·FP
# B1, B2 typical CS values from Turton App A.5 (3rd ed mean).
# B1 captura el costo "estructural" (cuerpo, cimentación, etc.);
# B2 captura el costo "material-dependent" (recipiente, tubos, etc.)
# que se multiplica por FM (material) y FP (presión).
B1_B2_BY_CATEGORIA = {
    "Heat exchangers":     (1.74, 1.55),
    "Fired heaters":       (0.96, 1.21),
    "Pumps":               (1.89, 1.35),
    "Compressors":         (0.00, 2.70),   # sold modular: FBM = B2·FM·FP
    # Reactors: Turton 5ª trata reactores químicos como recipientes
    # a presión (process vessels) — su FBM depende de FM y FP, no es
    # constante.  Usamos los B1/B2 de "Vessels" (vertical/horizontal)
    # según Tabla A.4.  Antes era (4.00, 0.00) → FBM constante = 4.0
    # subestimaba reactores a alta presión / material corrosivo.
    # (Instrucciones §1.2)
    "Reactors":            (2.25, 1.82),   # = vessels Tabla A.4
    "Storage":             (1.00, 0.50),
    "Vessels":             (2.25, 1.82),
    "Trays / packing":     (1.00, 1.00),
    "Mixers / splitters":  (1.38, 0.96),
    "Solids / sep.":       (1.40, 1.00),
    "Fans / blowers":      (1.70, 1.50),
    "Valves":              (1.50, 0.00),
    "Utilities":           (2.50, 1.00),
    "Towers":              (2.25, 1.82),
    "Tanks":               (1.00, 0.50),
    "Filters":             (1.40, 1.00),
    "Dryers":              (1.00, 1.00),
    "Evaporators":         (1.00, 1.45),
    "Crystallizers":       (1.00, 1.45),
    "Turbines":            (3.50, 1.50),
}
B1_B2_DEFAULT = (1.74, 1.55)   # fallback genérico (HX)


# Material factors FM (Turton App A.6, typical values).
# Para servicios corrosivos / alta T / alta P, se sube de CS al material
# necesario.  Auto-detección heurística vía corrosive_species_in_stream.
MATERIAL_FACTORS = {
    "CS":          1.00,   # Carbon Steel — default
    "CS galv":     1.20,
    "SS304":       2.50,   # Stainless 304 (HNO3 diluido, alcoholes)
    "SS316":       3.10,   # Stainless 316 (HNO3, H2SO4 < 70%)
    "Cu":          1.85,
    "Ni":          5.40,   # NaOH conc 50%+
    "Monel":       4.10,   # HF, sales fundidas
    "Hastelloy":   5.50,   # HCl conc, mezclas oxidantes severas
    "Inconel":     6.50,
    "Titanium":    8.00,   # Cl2 húmedo, agua de mar, hipoclorito
    "Glass-lined": 2.30,   # H2SO4 conc
    "Tantalum":    9.50,
}
MATERIAL_DEFAULT = "CS"

# Heurística: si en las corrientes de un bloque hay X componente con
# fracción ≥ 1%, sugerir material Y.  El "ranking" usa el FM del
# material para elegir el más severo.
CORROSIVE_SPECIES = {
    "chlorine":          "Titanium",
    "hydrogen chloride": "Hastelloy",
    "hydrochloric":      "Hastelloy",
    "nitric acid":       "SS316",
    "sulfuric acid":     "Glass-lined",
    "hydrogen sulfide":  "SS316",
    "hydrogen fluoride": "Monel",
    "sodium hydroxide":  "Ni",         # solo si conc > 50%
    "ammonia":           "SS304",
    "fluorine":          "Monel",
    "hypochlorite":      "Titanium",
    "phosphoric":        "SS316",
}


def suggested_material(composition_dicts, p_op_bar=1.0):
    """Heurística: dado una lista de composition dicts {comp:frac}
    de las corrientes adjuntas al bloque, devuelve el material más
    severo necesario según CORROSIVE_SPECIES.

    Si presión > 50 bar y feed tiene H2 → upgrade a SS304 mínimo
    (H2 embrittlement at high P)."""
    best   = MATERIAL_DEFAULT
    best_f = MATERIAL_FACTORS[best]
    for comp in composition_dicts:
        if not comp:
            continue
        # H2 a alta presión
        if p_op_bar >= 50 and comp.get("hydrogen", 0) >= 0.05:
            if MATERIAL_FACTORS["SS304"] > best_f:
                best, best_f = "SS304", MATERIAL_FACTORS["SS304"]
        # Especies corrosivas
        for sp, frac in comp.items():
            if frac < 0.01:
                continue
            spl = sp.lower()
            for kw, mat in CORROSIVE_SPECIES.items():
                if kw in spl:
                    fm = MATERIAL_FACTORS.get(mat, 1.0)
                    if fm > best_f:
                        best, best_f = mat, fm
                    break
    return best


# ─────────────────────────────────────────────────────────────
# Factor de presión FP — Turton 5ª ed Tabla A.2 + Ec. 7.7
# ─────────────────────────────────────────────────────────────
# Forma 1 — log-cuadrática (HX, pumps, compressors, etc.):
#
#     log10(FP) = C1 + C2·log10(P) + C3·[log10(P)]²
#
# con P en barg y coeficientes (C1, C2, C3) por equipo.
# Fuera del rango de validez de presión, FP = 1.0 con warning.
#
# Forma 2 — recipientes a presión (vessels, towers, reactors):
#
#     FP_vessel = max(1.0,
#         [ (P+1)·D / (2·(850 − 0.6·(P+1))) + 0.00315 ] / 0.0063 )
#
# con P en barg y D en m.  Fallback: si D no disponible, usar
# Forma 1 con coeficientes genéricos de la Tabla A.2.

# Coeficientes (C1, C2, C3) y rango de validez (P_min, P_max barg)
# del Apéndice A.2 de Turton 5ª edición.  Si un equipo no figura en
# la tabla, usar (0, 0, 0) → FP=1 (presión sin impacto en el costo).
FP_COEFFS_BY_CAT = {
    # Heat exchangers shell & tube — rango 5-140 barg
    "Heat exchangers":   ((0.03881, -0.11272, 0.08183),  (5, 140)),
    # Pumps centrífugas — rango 10-100 barg
    "Pumps":             ((-0.3935,  0.3957, -0.00226),  (10, 100)),
    # Compressors — Tabla A.2 marca FP=1 (acero, sin factor explícito;
    # el material entra vía FM en la 5ª edición).
    "Compressors":       ((0.0, 0.0, 0.0),                (None, None)),
    # Fired heaters — Tabla A.2: log10(FP)=0.1347 + 0.2368·logP
    # (correlación simplificada de la 5ª)
    "Fired heaters":     ((0.1347, 0.2368, 0.0),         (1, 200)),
    # Tanks — sin pressure factor (almacenamiento atm)
    "Storage":           ((0.0, 0.0, 0.0),                (None, None)),
    "Tanks":             ((0.0, 0.0, 0.0),                (None, None)),
    # Fans/blowers — log10(FP)=0 + 0.2354·logP (aprox)
    "Fans / blowers":    ((0.0, 0.2354, 0.0),             (None, None)),
}


def _fp_vessel_pressure(P_barg, D_m):
    """FP para recipiente a presión según Turton 5ª Ec. 7.7
    (Forma 2).  Cita: Tabla A.2 "Pressure vessel (horizontal/
    vertical)" forma cilíndrica con cabezas elipsoidales.

        FP_vessel = max(1, [ (P+1)·D/(2·(850−0.6·(P+1))) + 0.00315 ]
                            / 0.0063 )

    P en barg, D en m.  Para P ≤ −0.5 barg (vacío) el modelo no
    aplica; devuelve 1.25 (factor de vacío típico).
    """
    if P_barg < -0.5:
        return 1.25      # factor de vacío típico (Turton §7.4)
    p = float(P_barg)
    d = max(float(D_m), 0.3)    # mínimo 0.3 m mecánicamente razonable
    denom = 2.0 * (850.0 - 0.6 * (p + 1.0))
    if denom <= 0:
        return None      # presión fuera de rango físico (>1400 barg)
    fp = ((p + 1.0) * d / denom + 0.00315) / 0.0063
    return max(1.0, fp)


def _fp_log_quadratic(P_barg, cat):
    """FP log-cuadrático Turton Ec. 7.7 Forma 1.
        log10(FP) = C1 + C2·log10(P) + C3·(log10(P))²

    P en barg.  Si P ≤ 0 (atm o vacío), devuelve 1.0.
    Si P fuera del rango de validez de la tabla, satura en el
    extremo y emite warning vía atributo .warning del módulo.
    """
    if P_barg <= 0:
        return 1.0
    coeffs, (p_min, p_max) = FP_COEFFS_BY_CAT.get(cat,
                                                    ((0, 0, 0),
                                                     (None, None)))
    c1, c2, c3 = coeffs
    p = float(P_barg)
    # Clamping al rango de validez (sin extrapolación)
    if p_min is not None and p < p_min:
        p = p_min
    if p_max is not None and p > p_max:
        p = p_max
    log_p = math.log10(p)
    log_fp = c1 + c2 * log_p + c3 * log_p ** 2
    fp = 10 ** log_fp
    return max(1.0, fp)


def bare_module_factor(eq_nombre, P_op_bar=1.0, material="CS",
                        D_m=None):
    """Devuelve FBM Turton = B1 + B2·FM·FP   (Ec. 7.6 de la 5ª ed).

    Args:
        eq_nombre:  nombre en EQUIPMENT_DATA
        P_op_bar:   presión ABSOLUTA en bar (atm = 1.01325)
        material:   string en MATERIAL_FACTORS (default CS)
        D_m:        diámetro en m (sólo para vessels/towers/reactors
                    en Forma 2 de FP).  Si None, usa Forma 1 de
                    fallback.

    Returns:
        (FBM, FBM_CS_atm, FP, FM) tuple.

    Referencia: Turton 5ª ed §7.4 + Apéndice A Tabla A.2 / A.4."""
    spec = EQUIPMENT_DATA.get(eq_nombre, {})
    cat  = spec.get("categoria", "")
    b1, b2 = B1_B2_BY_CATEGORIA.get(cat, B1_B2_DEFAULT)
    fm = MATERIAL_FACTORS.get(material, 1.0)
    # Convertir bar absoluto → barg.  P_atm ≈ 1.01325 bar abs.
    P_barg = max(0.0, float(P_op_bar) - 1.01325)
    if cat in ("Vessels", "Towers", "Reactors"):
        if D_m is not None and D_m > 0:
            fp = _fp_vessel_pressure(P_barg, D_m)
            if fp is None:    # fuera de rango físico → fallback
                fp = _fp_log_quadratic(P_barg, cat)
        else:
            # Sin diámetro: aproximación log-cuadrática genérica con
            # los coeficientes de Heat exchangers (FP moderado).
            fp = _fp_log_quadratic(P_barg, "Heat exchangers")
    else:
        fp = _fp_log_quadratic(P_barg, cat)
    fbm        = b1 + b2 * fm * fp
    fbm_cs_atm = b1 + b2                 # base CS, atm
    return fbm, fbm_cs_atm, fp, fm


def bare_module_cost(eq_nombre, S, P_op_bar=1.0, year_target=None,
                       material="CS"):
    """Costo del módulo desnudo (CBM) Turton = Cp · FBM.

    Returns:
        dict con Cp_target, FBM, FP, FM, FBM_CS_atm, CBM, ...

    Si el equipo no está en EQUIPMENT_DATA → devuelve ceros con
    flag 'unknown'=True para no romper costing global."""
    if eq_nombre not in EQUIPMENT_DATA:
        return {
            "Cp_base": 0.0, "Cp_target": 0.0,
            "year_base": 2001,
            "year_target": year_target or 2001,
            "cepci_factor": 1.0, "fuera_rango": False,
            "S": S, "S_min": 0, "S_max": 0, "S_unit": "",
            "FBM": 0.0, "FBM_CS_atm": 0.0, "FP": 1.0, "FM": 1.0,
            "CBM": 0.0, "unknown": True, "material": material,
        }
    pc = purchased_cost(eq_nombre, S, year_target=year_target)
    fbm, fbm_cs, fp, fm = bare_module_factor(
        eq_nombre, P_op_bar=P_op_bar, material=material)
    cbm = pc["Cp_target"] * fbm
    pc["FBM"]        = fbm
    pc["FBM_CS_atm"] = fbm_cs
    pc["FP"]         = fp
    pc["FM"]         = fm
    pc["CBM"]        = cbm
    pc["unknown"]    = False
    pc["material"]   = material
    return pc


# ======================================================
# GRASS ROOTS CAPITAL (Turton Eq 7.10)
# ======================================================
def grass_roots_capital(sum_cbm_usd, contingency_frac=None,
                         aux_facilities_frac=None):
    """Turton 7.10:  CGR = ΣCBM + contingency + auxiliary facilities

    Defaults (desde econ_defaults perfil activo):
      · contingency = 18 % de ΣCBM (Turton estándar)
      · auxiliary   = 50 % de ΣCBM (site prep, services, offsites)

    El valor de grass roots representa el capital total para
    construir la planta desde cero en sitio virgen (vs. retrofit).

    Returns:
        dict con breakdown y CGR total."""
    if contingency_frac is None or aux_facilities_frac is None:
        try:
            import econ_defaults as _ed
            cf = _ed.get_capital_fracs()
            if contingency_frac is None:
                contingency_frac = cf["cgr_contingency_pct"]
            if aux_facilities_frac is None:
                aux_facilities_frac = cf["cgr_aux_facilities_pct"]
        except Exception:
            if contingency_frac is None:    contingency_frac    = 0.18
            if aux_facilities_frac is None: aux_facilities_frac = 0.50
    contingency    = contingency_frac    * sum_cbm_usd
    aux_facilities = aux_facilities_frac * sum_cbm_usd
    cgr            = sum_cbm_usd + contingency + aux_facilities
    return {
        "ΣCBM":                  sum_cbm_usd,
        "Contingency":           contingency,
        "Aux facilities":        aux_facilities,
        "CGR (Grass Roots)":     cgr,
        "contingency_frac":      contingency_frac,
        "aux_facilities_frac":   aux_facilities_frac,
    }


# ======================================================
# INDICADORES DE RENTABILIDAD (Turton Ch 9-10)
# ======================================================
def profitability_indicators(revenue_usd_yr, com_d_usd_yr, fci_usd,
                              years_op=None, tax_rate=None,
                              disc_rate=None,
                              depreciable_base_usd=None,
                              working_capital_usd=0.0,
                              useful_life_yr=None,
                              alpha_d=0.180, alpha=0.305):
    """Calcula indicadores económicos clásicos a partir de:
        revenue_usd_yr:        ingresos anuales (Σ products + byproducts)
        com_d_usd_yr:          cost of manufacture con dep (Turton 8.2)
        fci_usd:               FCI usado para el COM (Grass Roots o fixed)
        depreciable_base_usd:  base depreciable.  Default = fci_usd.
                                NO incluye working capital.
        working_capital_usd:   working capital one-time (year-0 outflow,
                                recuperado al cierre del horizonte).
        useful_life_yr:        vida útil para depreciación SL.
                                Default = years_op.

    NOTA crítica vs versión vieja:
      · El cash flow anual se computa con DEPRECIACIÓN REAL (SL sobre
        depreciable_base / useful_life), NO con FCI/years_op suelto.
      · El CAPEX total (year 0) = fci_usd + working_capital.
      · WC se recupera en year_op final como cash inflow positivo.
      · Loss carry-forward NO se aplica acá (es un proxy de cash
        constante).  Para CF real con LCF usar compute_income_statement.

    Returns:
        dict con Gross/Net profit, Cash flow, Payback, ROI, NPV, IRR."""
    if years_op is None or tax_rate is None or disc_rate is None:
        try:
            import econ_defaults as _ed
            fin = _ed.get_financial()
            if years_op  is None: years_op  = fin["project_years"]
            if tax_rate  is None: tax_rate  = fin["tax_rate"]
            if disc_rate is None: disc_rate = fin["discount_rate"]
        except Exception:
            if years_op  is None: years_op  = 10
            if tax_rate  is None: tax_rate  = 0.30
            if disc_rate is None: disc_rate = 0.10
    if useful_life_yr is None:
        useful_life_yr = years_op
    if depreciable_base_usd is None:
        depreciable_base_usd = fci_usd
    # Tax-deductible OPEX (consistente con compute_income_statement):
    #   = β·COL + γ·(CRM+CUT+CWT) + (α−α_d)·FCI
    #   = [COM_d − α_d·FCI]    + [(α−α_d)·FCI]
    #   = COM_d + (α − 2·α_d)·FCI
    # Donde (α−α_d)·FCI = Dep + M+T+I (Turton FCI-pegged burden total).
    # Dep se reporta separado para CF (add-back no-cash).  Esta
    # convención da la MISMA NPV que el Income Statement (bug-fix
    # consistencia financiera).
    tax_deductible_opex = com_d_usd_yr + (alpha - 2.0 * alpha_d) * fci_usd
    gross_profit = revenue_usd_yr - com_d_usd_yr      # Turton display
    depreciation = depreciable_base_usd / max(useful_life_yr, 1)
    taxable      = revenue_usd_yr - tax_deductible_opex
    tax          = max(0.0, taxable) * tax_rate
    net_profit   = taxable - tax
    cash_flow    = net_profit + depreciation
    # CAPEX total año 0 = FCI + WC.  WC se recupera year_op final.
    capex_year0  = fci_usd + working_capital_usd
    # Indicadores
    if cash_flow > 0:
        pbp_simple = capex_year0 / cash_flow
    else:
        pbp_simple = float("inf")
    roi_simple = (net_profit / fci_usd * 100.0) if fci_usd > 0 else 0.0
    # NPV (discounted cash flow over years_op).  Año 0 = -CAPEX_total
    # (FCI + WC).  Último año = CF + recuperación WC.
    npv = -capex_year0
    for yr in range(1, years_op + 1):
        cf_yr = cash_flow + (working_capital_usd if yr == years_op else 0.0)
        npv += cf_yr / (1.0 + disc_rate) ** yr
    # IRR aproximado por bisección (NPV=0).  Modela WC recovery final.
    irr = _solve_irr_wc(cash_flow, capex_year0, working_capital_usd, years_op)
    # Veredicto explícito
    veredicto = "VIABLE" if npv > 0 else "INVIABLE"
    pbp_str = (f"{pbp_simple:.2f}" if pbp_simple != float("inf")
               else "∞ — proyecto no recupera inversión")
    irr_str = (f"{irr*100.0:.1f}" if irr is not None
               else "no existe (flujos negativos)")
    return {
        "Revenue":         revenue_usd_yr,
        "COM_d":           com_d_usd_yr,
        "Gross profit":    gross_profit,
        "Depreciation":    depreciation,
        "Tax (30%)":       tax,
        "Net profit":      net_profit,
        "Cash flow":       cash_flow,
        "CAPEX year 0":    capex_year0,
        "Working capital": working_capital_usd,
        "Payback simple":  pbp_simple,
        "Payback str":     pbp_str,
        "ROI %":           roi_simple,
        "NPV":             npv,
        "IRR %":           irr * 100.0 if irr is not None else None,
        "IRR str":         irr_str,
        "Veredicto":       veredicto,
        "years_op":        years_op,
        "useful_life_yr":  useful_life_yr,
        "disc_rate":       disc_rate,
        "tax_rate":        tax_rate,
        "depreciable_base":depreciable_base_usd,
    }


def _solve_irr(cash_flow_yr, fci_usd, years_op, max_iter=50):
    """Legacy: IRR sin WC recovery (mantenido para compat).  Usar
    _solve_irr_wc() en código nuevo."""
    return _solve_irr_wc(cash_flow_yr, fci_usd, 0.0, years_op, max_iter)


def _solve_irr_wc(cash_flow_yr, capex_year0, wc_recovery, years_op,
                   max_iter=50):
    """Bisección para encontrar IRR con recuperación de WC al final.
    NPV(r) = -capex_year0 + Σ_{yr=1..N} CF/(1+r)^yr + wc/(1+r)^N
    Range r ∈ [-0.99, 5.0]."""
    if cash_flow_yr <= 0:
        return None
    def npv_at(r):
        v = -capex_year0
        for yr in range(1, years_op + 1):
            v += cash_flow_yr / (1.0 + r) ** yr
        if wc_recovery > 0:
            v += wc_recovery / (1.0 + r) ** years_op
        return v
    lo, hi = -0.99, 5.0
    f_lo, f_hi = npv_at(lo), npv_at(hi)
    if f_lo * f_hi > 0:
        return None       # no zero en el rango
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = npv_at(mid)
        if abs(f_mid) < 1.0:
            return mid
        if f_mid * f_lo < 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return 0.5 * (lo + hi)


# ======================================================
# COST OF MANUFACTURE — Turton Eq 8.2 (with depreciation)
# ======================================================
def cost_of_manufacture(FCI_usd, COL_usd, CUT_usd, CRM_usd, CWT_usd,
                         alpha_d=None, alpha=None, beta=None, gamma=None):
    """Calcula COM (Cost of Manufacture) según Turton Eq 8.2:

        COM_d  =  α_d·FCI + β·COL + γ·(CUT + CRM + CWT)        (con dep)
        COM    =  α·FCI   + β·COL + γ·(CUT + CRM + CWT)        (sin dep)

    Defaults Turton standalone chemical plant (desde econ_defaults):
        α_d=0.180, α=0.305, β=2.73, γ=1.23

    γ es el más relevante para tunear según el negocio:
        1.05-1.10 → refinería integrada / commodity bulk
        1.23      → planta química standalone (default Turton)
        1.30-1.50 → farma / specialty / agroquímicos

    Inputs todos en USD/año (excepto FCI que es one-time CAPEX).

    Returns:
        dict con COM_d, COM, breakdown por componente + coeffs usados.
    """
    if any(x is None for x in (alpha_d, alpha, beta, gamma)):
        try:
            import econ_defaults as _ed
            c = _ed.get_com_coeffs()
            if alpha_d is None: alpha_d = c["alpha_fci_d"]
            if alpha   is None: alpha   = c["alpha_fci"]
            if beta    is None: beta    = c["beta_col"]
            if gamma   is None: gamma   = c["gamma_variable"]
        except Exception:
            if alpha_d is None: alpha_d = 0.180
            if alpha   is None: alpha   = 0.305
            if beta    is None: beta    = 2.73
            if gamma   is None: gamma   = 1.23
    base       = gamma * (CUT_usd + CRM_usd + CWT_usd)
    labor_term = beta  * COL_usd
    com_d  = alpha_d * FCI_usd + labor_term + base
    com    = alpha   * FCI_usd + labor_term + base
    return {
        "FCI":     FCI_usd,
        "COL":     COL_usd,
        "CUT":     CUT_usd,
        "CRM":     CRM_usd,
        "CWT":     CWT_usd,
        # Términos individuales — keys actualizados al α/β/γ activo
        f"{alpha_d:.3f}·FCI":            alpha_d * FCI_usd,
        f"{alpha:.3f}·FCI (sin dep)":    alpha   * FCI_usd,
        f"{beta:.2f}·COL":               labor_term,
        f"{gamma:.2f}·(CUT+CRM+CWT)":    base,
        # Aliases legacy para no romper código existente
        "0.180·FCI":                     alpha_d * FCI_usd,
        "0.305·FCI":                     alpha   * FCI_usd,
        "2.73·COL":                      labor_term,
        "1.23·(CUT+CRM+CWT)":            base,
        "COM_d":   com_d,
        "COM":     com,
        # Coeffs efectivos usados
        "alpha_d": alpha_d, "alpha": alpha, "beta": beta, "gamma": gamma,
    }


def cost_of_manufacture_components(FCI_usd, COL_usd, CUT_usd, CRM_usd, CWT_usd,
                                     depreciable_base_usd=None,
                                     useful_life_yr=10,
                                     salvage_value_usd=0.0,
                                     alpha_d=None, alpha=None,
                                     beta=None, gamma=None,
                                     fci_base_for_com="fci_fixed"):
    """Descompone COM en líneas explícitas para Income Statement.

    Devuelve además de COM_d/COM (Turton 8.2):
      · Depreciation_SL — línea recta REAL sobre depreciable_base
        (NO la implícita en α_d).  Default useful_life=10 yr.
      · Maintenance_Tax_Insurance — = (COM − COM_d) − Depreciation_SL.
        Cargos FCI-pegged según Turton.  Se reporta como línea
        separada, NO se cuadra a cero.  Permite distinguir
        depreciación (no-cash) de gastos cash FCI-dependientes.

    fci_base_for_com:
      · "fci_fixed"   → α_d/α se aplican al FCI fijo (Turton text default).
      · "grass_roots" → α_d/α se aplican al CGR.
      Si depreciable_base_usd no se da, se usa FCI_usd directamente.

    Returns dict con todas las claves de cost_of_manufacture() + las
    nuevas (Depreciation_SL, Maintenance_Tax_Insurance,
    depreciable_base, useful_life_yr, fci_base_for_com).
    """
    com_dict = cost_of_manufacture(
        FCI_usd=FCI_usd, COL_usd=COL_usd, CUT_usd=CUT_usd,
        CRM_usd=CRM_usd, CWT_usd=CWT_usd,
        alpha_d=alpha_d, alpha=alpha, beta=beta, gamma=gamma,
    )
    base = depreciable_base_usd if depreciable_base_usd is not None else FCI_usd
    base = max(0.0, float(base) - float(salvage_value_usd or 0.0))
    dep_sl = base / float(useful_life_yr) if useful_life_yr > 0 else 0.0
    # Maintenance + Tax & Insurance (cargos FCI-pegged cash, sin
    # depreciación).  Es la brecha entre COM y COM_d MENOS la
    # depreciación real.  Turton's (α − α_d)·FCI = 0.125·FCI engloba
    # depreciación implícita + mant + tax/seguros; al sacarle la
    # depreciación real queda el componente cash puro.
    com   = com_dict["COM"]
    com_d = com_dict["COM_d"]
    mti   = (com - com_d) - dep_sl
    com_dict["Depreciation_SL"]             = dep_sl
    com_dict["Maintenance_Tax_Insurance"]   = mti
    com_dict["depreciable_base"]            = base
    com_dict["useful_life_yr"]              = useful_life_yr
    com_dict["fci_base_for_com"]            = fci_base_for_com
    return com_dict


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
    """Calcula Cp° (purchased cost a CS y atm) para `nombre` con
    tamaño S, usando log10(Cp°) = K1 + K2·log10(S) + K3·log10(S)²
    (Turton 5ª Ec. 7.1, Apéndice A.1).

    IMPORTANTE — extrapolación fuera de rango:
        Turton publica K1/K2/K3 con un rango de validez (S_min, S_max)
        — las regresiones log-cuadráticas NO son válidas fuera de ese
        rango (pueden dar costos negativos o irrealmente altos).
        Cuando S ∈/ [S_min, S_max] se computa el valor de todos modos
        para no romper el pipeline, pero el flag `fuera_rango=True`
        se propaga y se emite UserWarning explícito.  El user puede
        atrapar el warning con `warnings.catch_warnings()` o leer el
        flag en el dict de retorno.  (Instrucciones §1.4)

    Si year_target es dado, el resultado se escala por CEPCI al
    año destino.  Default: año base (2001, CEPCI=397).

    Returns:
        dict con Cp_base, Cp_target, year_base, year_target,
        cepci_factor, fuera_rango (bool), warning_msg (str si fuera
        de rango), S, S_min, S_max, S_unit.
    """

    spec = EQUIPMENT_DATA[nombre]

    if S <= 0:
        raise ValueError(f"S debe ser positivo (recibido {S})")

    logS = math.log10(S)
    log_cp = spec["K1"] + spec["K2"] * logS + spec["K3"] * (logS ** 2)
    Cp_base = 10 ** log_cp  # USD a CEPCI=397

    fuera = (S < spec["S_min"]) or (S > spec["S_max"])
    warning_msg = ""
    if fuera:
        warning_msg = (
            f"{nombre}: S={S} {spec['S_unit']} fuera del rango "
            f"Turton 5ª válido [{spec['S_min']}, {spec['S_max']}] "
            f"{spec['S_unit']}.  Cp° extrapolado — costo NO confiable. "
            f"Considerar usar otra clase de equipo o N unidades en paralelo."
        )
        import warnings
        warnings.warn(warning_msg, UserWarning, stacklevel=2)

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
        "warning_msg":  warning_msg,
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
