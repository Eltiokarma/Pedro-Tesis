"""
COMPONENTS — catálogo de propiedades termofísicas de componentes
comunes en procesos químicos.

Cada componente tiene:
  · MW       peso molecular (g/mol)
  · Tb_C     punto de ebullición a 1 atm (°C)
  · Cp_L(T)  Cp líquido como polinomio lineal en T (°C): A + B·T   (kJ/kg·K)
  · Cp_V(T)  Cp vapor   como polinomio lineal en T (°C): A + B·T   (kJ/kg·K)
  · ΔH_vap   calor latente a Tb (kJ/kg)

Los coeficientes vienen de Reid, Prausnitz & Poling — "Properties
of Gases and Liquids" (5ª ed.) Apéndice A, ajustados a polinomio
lineal en el rango típico de proceso (0–300 °C para líquidos,
25–500 °C para vapores).

Aproximación: Cp(T) lineal en vez de polinomio cúbico DIPPR.
Para screening (este editor), 1-3% de error en el rango común.

API:

  get(name)                          → Component
  cp_kJ_kg_K(name, T_C, phase)       → Cp del componente puro
  cp_mix_kJ_kg_K(comp_dict, T_C, phase)  → Cp ponderado por w
  delta_h_vap_mix(comp_dict)         → ΔH_vap ponderado por w
  mw_mix(comp_dict)                  → MW promedio ponderado por w
  list_names()                       → lista de keys ordenadas (para combos UI)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Component:
    name:     str        # clave interna ("toluene")
    label:    str        # display ("Tolueno (C₇H₈)")
    mw:       float      # g/mol
    tb_c:     float      # punto de ebullición normal (°C)
    cp_l_a:   float      # Cp_liquid = A + B·T  (T en °C, Cp en kJ/kg·K)
    cp_l_b:   float
    cp_v_a:   float      # Cp_vapor  = A + B·T
    cp_v_b:   float
    dh_vap:   float      # kJ/kg a Tb
    valid:    bool = True   # si False, "no usar" (placeholder)

    def cp_liquid(self, T_c: float) -> float:
        return self.cp_l_a + self.cp_l_b * T_c

    def cp_vapor(self, T_c: float) -> float:
        return self.cp_v_a + self.cp_v_b * T_c

    def cp(self, T_c: float, phase: str) -> float:
        """Cp en kJ/kg·K según fase ('liquid' | 'vapor' | 'gas')."""
        if phase in ("vapor", "gas"):
            return self.cp_vapor(T_c)
        return self.cp_liquid(T_c)


# ======================================================
# CATÁLOGO
# ======================================================
# Fuentes: Reid-Prausnitz-Poling 5e, Perry's 9e, NIST WebBook.
# Cp_liquid: ajustado en 0-150 °C; Cp_vapor: ajustado en 25-500 °C.

COMPONENTS: Dict[str, Component] = {

    # ---- Aromáticos ----
    "toluene":   Component(
        name="toluene", label="Tolueno (C₇H₈)", mw=92.14, tb_c=110.6,
        cp_l_a=1.595, cp_l_b=0.00255,
        cp_v_a=0.965, cp_v_b=0.00370,
        dh_vap=363.0,
    ),
    "benzene":   Component(
        name="benzene", label="Benceno (C₆H₆)", mw=78.11, tb_c=80.1,
        cp_l_a=1.640, cp_l_b=0.00290,
        cp_v_a=0.850, cp_v_b=0.00345,
        dh_vap=394.0,
    ),
    "xylene":    Component(
        name="xylene", label="Xileno (mix C₈H₁₀)", mw=106.17, tb_c=140.0,
        cp_l_a=1.590, cp_l_b=0.00240,
        cp_v_a=1.000, cp_v_b=0.00380,
        dh_vap=343.0,
    ),
    "ethylbenzene": Component(
        name="ethylbenzene", label="Etilbenceno (C₈H₁₀)", mw=106.17, tb_c=136.2,
        cp_l_a=1.620, cp_l_b=0.00250,
        cp_v_a=1.000, cp_v_b=0.00380,
        dh_vap=339.0,
    ),

    # ---- Alcoholes ----
    "methanol":  Component(
        name="methanol", label="Metanol (CH₃OH)", mw=32.04, tb_c=64.7,
        cp_l_a=2.450, cp_l_b=0.00340,
        cp_v_a=1.200, cp_v_b=0.00440,
        dh_vap=1100.0,
    ),
    "ethanol":   Component(
        name="ethanol", label="Etanol (C₂H₅OH)", mw=46.07, tb_c=78.4,
        cp_l_a=2.350, cp_l_b=0.00280,
        cp_v_a=1.180, cp_v_b=0.00500,
        dh_vap=838.0,
    ),

    # ---- Agua ----
    "water":     Component(
        name="water", label="Agua (H₂O)", mw=18.02, tb_c=100.0,
        cp_l_a=4.184, cp_l_b=0.00000,
        cp_v_a=1.865, cp_v_b=0.00040,
        dh_vap=2257.0,
    ),

    # ---- Gases livianos ----
    "hydrogen":  Component(
        name="hydrogen", label="Hidrógeno (H₂)", mw=2.016, tb_c=-252.9,
        cp_l_a=9.700, cp_l_b=0.0,        # líquido criogénico, raro
        cp_v_a=14.310, cp_v_b=0.0001,
        dh_vap=446.0,
    ),
    "methane":   Component(
        name="methane", label="Metano (CH₄)", mw=16.04, tb_c=-161.5,
        cp_l_a=3.480, cp_l_b=0.0,
        cp_v_a=2.220, cp_v_b=0.0048,
        dh_vap=511.0,
    ),
    "ethane":    Component(
        name="ethane", label="Etano (C₂H₆)", mw=30.07, tb_c=-88.6,
        cp_l_a=2.580, cp_l_b=0.0,
        cp_v_a=1.750, cp_v_b=0.0060,
        dh_vap=489.0,
    ),
    "ethylene":  Component(
        name="ethylene", label="Etileno (C₂H₄)", mw=28.05, tb_c=-103.7,
        cp_l_a=2.430, cp_l_b=0.0,
        cp_v_a=1.550, cp_v_b=0.0050,
        dh_vap=482.0,
    ),
    "propane":   Component(
        name="propane", label="Propano (C₃H₈)", mw=44.10, tb_c=-42.1,
        cp_l_a=2.500, cp_l_b=0.0,
        cp_v_a=1.670, cp_v_b=0.0050,
        dh_vap=425.0,
    ),
    "nitrogen":  Component(
        name="nitrogen", label="Nitrógeno (N₂)", mw=28.01, tb_c=-195.8,
        cp_l_a=2.040, cp_l_b=0.0,
        cp_v_a=1.040, cp_v_b=0.00005,
        dh_vap=199.0,
    ),
    "oxygen":    Component(
        name="oxygen", label="Oxígeno (O₂)", mw=32.00, tb_c=-183.0,
        cp_l_a=1.700, cp_l_b=0.0,
        cp_v_a=0.910, cp_v_b=0.00010,
        dh_vap=213.0,
    ),
    "co":        Component(
        name="co", label="Monóxido de C (CO)", mw=28.01, tb_c=-191.5,
        cp_l_a=2.180, cp_l_b=0.0,
        cp_v_a=1.040, cp_v_b=0.00010,
        dh_vap=216.0,
    ),
    "co2":       Component(
        name="co2", label="Dióxido de C (CO₂)", mw=44.01, tb_c=-78.5,  # sublim.
        cp_l_a=2.500, cp_l_b=0.0,
        cp_v_a=0.844, cp_v_b=0.00075,
        dh_vap=574.0,
    ),
    "air":       Component(
        name="air", label="Aire (N₂+O₂)", mw=28.96, tb_c=-194.0,
        cp_l_a=2.000, cp_l_b=0.0,
        cp_v_a=1.005, cp_v_b=0.00008,
        dh_vap=205.0,
    ),
    "syngas":    Component(
        # mezcla típica CO + 2 H₂  para síntesis de metanol
        name="syngas", label="Syngas (CO + 2 H₂)", mw=10.0, tb_c=-200.0,
        cp_l_a=5.000, cp_l_b=0.0,
        cp_v_a=4.000, cp_v_b=0.00100,
        dh_vap=300.0,
    ),

    # ---- Inorgánicos / industriales ----
    "ammonia":   Component(
        name="ammonia", label="Amoníaco (NH₃)", mw=17.03, tb_c=-33.4,
        cp_l_a=4.450, cp_l_b=0.0,
        cp_v_a=2.130, cp_v_b=0.00100,
        dh_vap=1370.0,
    ),
    "glucose":   Component(
        name="glucose", label="Glucosa (C₆H₁₂O₆)", mw=180.16, tb_c=146.0,
        cp_l_a=1.250, cp_l_b=0.00200,
        cp_v_a=1.000, cp_v_b=0.00200,
        dh_vap=300.0,
    ),
    "sucrose":   Component(
        # sacarosa — disuelta en jugo de caña / remolacha
        name="sucrose", label="Sacarosa (C₁₂H₂₂O₁₁)",
        mw=342.30, tb_c=186.0,
        cp_l_a=1.250, cp_l_b=0.00200,
        cp_v_a=1.000, cp_v_b=0.00200,
        dh_vap=400.0,
    ),
    "h2s":       Component(
        # ácido sulfhídrico, contaminante en gas natural
        name="h2s", label="Ácido sulfhídrico (H₂S)",
        mw=34.08, tb_c=-60.3,
        cp_l_a=2.10, cp_l_b=0.0,
        cp_v_a=1.00, cp_v_b=0.00050,
        dh_vap=540.0,
    ),
    "mdea":      Component(
        # MDEA, amina típica para endulzamiento de gas
        name="mdea", label="MDEA (metildietanolamina)",
        mw=119.16, tb_c=247.0,
        cp_l_a=2.70, cp_l_b=0.00300,
        cp_v_a=1.85, cp_v_b=0.00250,
        dh_vap=520.0,
    ),

    # ---- Biodiesel / oleo ----
    "vegetable_oil": Component(
        # Triglicérido típico (soja/palma).  MW ~880 (3× ácido C18).
        name="vegetable_oil", label="Aceite vegetal (triglicérido)",
        mw=880.0, tb_c=300.0,
        cp_l_a=1.900, cp_l_b=0.00300,
        cp_v_a=1.400, cp_v_b=0.00200,
        dh_vap=350.0,
    ),
    "biodiesel":   Component(
        # FAME (Fatty Acid Methyl Ester) — metil oleato, mayoritario.
        name="biodiesel", label="Biodiesel (FAME C19H36O2)",
        mw=296.5, tb_c=343.0,
        cp_l_a=2.100, cp_l_b=0.00300,
        cp_v_a=1.500, cp_v_b=0.00200,
        dh_vap=230.0,
    ),
    "glycerin":    Component(
        name="glycerin", label="Glicerina (C₃H₈O₃)",
        mw=92.09, tb_c=290.0,
        cp_l_a=2.400, cp_l_b=0.00500,
        cp_v_a=1.500, cp_v_b=0.00200,
        dh_vap=663.0,
    ),

    # ---- Cortes de crudo (proxies para CDU) ----
    "naphtha":     Component(
        # nafta liviana, mezcla C5-C10 (Tb avg ~130°C)
        name="naphtha", label="Nafta (C₅-C₁₀)",
        mw=100.0, tb_c=130.0,
        cp_l_a=2.050, cp_l_b=0.00280,
        cp_v_a=1.600, cp_v_b=0.00350,
        dh_vap=310.0,
    ),
    "kerosene":    Component(
        # querosén, C10-C16 (Tb avg ~215°C)
        name="kerosene", label="Querosén (C₁₀-C₁₆)",
        mw=170.0, tb_c=215.0,
        cp_l_a=2.100, cp_l_b=0.00300,
        cp_v_a=1.700, cp_v_b=0.00350,
        dh_vap=275.0,
    ),
    "diesel":      Component(
        # diésel, C12-C22 (Tb avg ~290°C)
        name="diesel", label="Diésel (C₁₂-C₂₂)",
        mw=210.0, tb_c=290.0,
        cp_l_a=2.150, cp_l_b=0.00310,
        cp_v_a=1.800, cp_v_b=0.00340,
        dh_vap=250.0,
    ),
    "crude_oil":   Component(
        # crudo medio (mezcla); promedios aproximados de ASTM D2887
        name="crude_oil", label="Crudo (mezcla)",
        mw=280.0, tb_c=280.0,
        cp_l_a=1.900, cp_l_b=0.00310,
        cp_v_a=1.700, cp_v_b=0.00330,
        dh_vap=250.0,
    ),
    "atmospheric_residue": Component(
        # residuo atmosférico (>360°C), no se vaporiza
        name="atmospheric_residue",
        label="Residuo atmosférico (>360°C)",
        mw=400.0, tb_c=450.0,
        cp_l_a=2.300, cp_l_b=0.00320,
        cp_v_a=1.900, cp_v_b=0.00300,
        dh_vap=180.0,
    ),

    # ---- Olefinas / monómeros (E08, E09, E20) ----
    "propylene": Component(
        name="propylene", label="Propileno (C₃H₆)",
        mw=42.08, tb_c=-47.6,
        cp_l_a=2.500, cp_l_b=0.00000,
        cp_v_a=1.500, cp_v_b=0.00500,
        dh_vap=438.0,
    ),
    "carbon_monoxide": Component(
        name="carbon_monoxide", label="Monóxido de carbono (CO)",
        mw=28.01, tb_c=-191.5,
        cp_l_a=2.000, cp_l_b=0.00000,
        cp_v_a=1.040, cp_v_b=0.00008,
        dh_vap=216.0,
    ),
    "acetic_acid": Component(
        name="acetic_acid", label="Ácido acético (C₂H₄O₂)",
        mw=60.05, tb_c=118.1,
        cp_l_a=1.960, cp_l_b=0.00240,
        cp_v_a=1.100, cp_v_b=0.00240,
        dh_vap=405.0,
    ),
    "polyethylene": Component(
        # No volátil (Tb=99999 marca no-vaporizable, como atmospheric_residue).
        name="polyethylene", label="Polietileno (−C₂H₄−)ₙ",
        mw=28000.0, tb_c=99999.0,
        cp_l_a=2.300, cp_l_b=0.00300,
        cp_v_a=2.300, cp_v_b=0.00300,
        dh_vap=0.0,
    ),

    # ---- Sólidos minerales / materiales (E11, E12) ----
    "silica": Component(
        name="silica", label="Sílice / arena (SiO₂)",
        mw=60.08, tb_c=99999.0,
        cp_l_a=0.700, cp_l_b=0.00030,
        cp_v_a=0.700, cp_v_b=0.00030,
        dh_vap=0.0,
    ),
    "soda_ash": Component(
        name="soda_ash", label="Carbonato de sodio (Na₂CO₃)",
        mw=105.99, tb_c=99999.0,
        cp_l_a=1.050, cp_l_b=0.00000,
        cp_v_a=1.050, cp_v_b=0.00000,
        dh_vap=0.0,
    ),
    "limestone": Component(
        name="limestone", label="Caliza (CaCO₃)",
        mw=100.09, tb_c=99999.0,
        cp_l_a=0.840, cp_l_b=0.00000,
        cp_v_a=0.840, cp_v_b=0.00000,
        dh_vap=0.0,
    ),
    "quicklime": Component(
        name="quicklime", label="Cal viva (CaO)",
        mw=56.08, tb_c=99999.0,
        cp_l_a=0.750, cp_l_b=0.00000,
        cp_v_a=0.750, cp_v_b=0.00000,
        dh_vap=0.0,
    ),
    "glass": Component(
        # Pseudo vidrio sodocálcico (proxy fundido/sólido).
        name="glass", label="Vidrio sodocálcico (pseudo)",
        mw=60.0, tb_c=99999.0,
        cp_l_a=1.000, cp_l_b=0.00020,
        cp_v_a=1.000, cp_v_b=0.00020,
        dh_vap=0.0,
    ),
    "clinker": Component(
        name="clinker", label="Clínker de cemento (pseudo)",
        mw=100.0, tb_c=99999.0,
        cp_l_a=0.850, cp_l_b=0.00000,
        cp_v_a=0.850, cp_v_b=0.00000,
        dh_vap=0.0,
    ),

    # ---- Sólidos orgánicos / alimentos (E02, E03, E14, E23) ----
    "starch": Component(
        # Pseudo (C₆H₁₀O₅)ₙ, sólido no volátil.
        name="starch", label="Almidón (pseudo C₆H₁₀O₅)ₙ",
        mw=162.14, tb_c=99999.0,
        cp_l_a=1.200, cp_l_b=0.00200,
        cp_v_a=1.200, cp_v_b=0.00200,
        dh_vap=0.0,
    ),
    "urea": Component(
        name="urea", label="Urea (CH₄N₂O)",
        mw=60.06, tb_c=99999.0,
        cp_l_a=1.550, cp_l_b=0.00000,
        cp_v_a=1.550, cp_v_b=0.00000,
        dh_vap=0.0,
    ),
    "potato_solids": Component(
        name="potato_solids", label="Sólidos de papa (pseudo)",
        mw=150.0, tb_c=99999.0,
        cp_l_a=1.500, cp_l_b=0.00200,
        cp_v_a=1.500, cp_v_b=0.00200,
        dh_vap=0.0,
    ),
    "pineapple_solids": Component(
        # Sólidos solubles tipo azúcar (proxy sucrose).
        name="pineapple_solids", label="Sólidos de piña (pseudo)",
        mw=180.0, tb_c=99999.0,
        cp_l_a=1.300, cp_l_b=0.00200,
        cp_v_a=1.300, cp_v_b=0.00200,
        dh_vap=0.0,
    ),

    # ---- Pseudo-componentes lácteos (E04 Leche Gloria) ----
    # Calibrados para que la mezcla reproduzca Cp_leche entera ≈3.93
    # y Cp_crema 40% ≈3.35 kJ/kg·K (dossier §6).
    "milk_fat": Component(
        name="milk_fat", label="Materia grasa láctea (pseudo)",
        mw=850.0, tb_c=99999.0,
        cp_l_a=2.100, cp_l_b=0.00300,
        cp_v_a=2.100, cp_v_b=0.00300,
        dh_vap=0.0,
    ),
    "milk_protein": Component(
        name="milk_protein", label="Proteína láctea (pseudo)",
        mw=25000.0, tb_c=99999.0,
        cp_l_a=2.000, cp_l_b=0.00200,
        cp_v_a=2.000, cp_v_b=0.00200,
        dh_vap=0.0,
    ),
    "lactose": Component(
        # Disacárido (C₁₂H₂₂O₁₁), sólido tipo sacarosa.
        name="lactose", label="Lactosa (C₁₂H₂₂O₁₁)",
        mw=342.30, tb_c=99999.0,
        cp_l_a=1.250, cp_l_b=0.00200,
        cp_v_a=1.250, cp_v_b=0.00200,
        dh_vap=0.0,
    ),
    "milk_ash": Component(
        name="milk_ash", label="Minerales lácteos (pseudo cenizas)",
        mw=100.0, tb_c=99999.0,
        cp_l_a=0.900, cp_l_b=0.00000,
        cp_v_a=0.900, cp_v_b=0.00000,
        dh_vap=0.0,
    ),

    # ---- Pseudo-componentes biológicos / ambientales (E22, E24) ----
    "raw_water_solids": Component(
        name="raw_water_solids", label="Sólidos suspendidos agua cruda (pseudo)",
        mw=100.0, tb_c=99999.0,
        cp_l_a=1.000, cp_l_b=0.00000,
        cp_v_a=1.000, cp_v_b=0.00000,
        dh_vap=0.0,
    ),
    "penicillin": Component(
        name="penicillin", label="Penicilina (pseudo C₁₆H₁₈N₂O₄S)",
        mw=334.39, tb_c=99999.0,
        cp_l_a=1.500, cp_l_b=0.00100,
        cp_v_a=1.500, cp_v_b=0.00100,
        dh_vap=0.0,
    ),
    "biomass": Component(
        name="biomass", label="Biomasa / micelio (pseudo)",
        mw=100.0, tb_c=99999.0,
        cp_l_a=1.200, cp_l_b=0.00200,
        cp_v_a=1.200, cp_v_b=0.00200,
        dh_vap=0.0,
    ),

    # ⚠ Electrolito/iónico. Propiedades de fase líquida/sólida pura como
    # proxy. Química asociada NO derivable de Capa 3 — modelar con outputs
    # locked (Modo B). Mismo régimen documentado para MDEA/H2S en
    # reactions_db.md.
    "chlorine": Component(
        name="chlorine", label="Cloro (Cl₂)",
        mw=70.91, tb_c=-34.0,
        cp_l_a=0.950, cp_l_b=0.00000,
        cp_v_a=0.480, cp_v_b=0.00010,
        dh_vap=288.0,
    ),
    "hydrogen_chloride": Component(
        name="hydrogen_chloride", label="Cloruro de hidrógeno (HCl)",
        mw=36.46, tb_c=-85.0,
        cp_l_a=1.500, cp_l_b=0.00000,
        cp_v_a=0.800, cp_v_b=0.00002,
        dh_vap=444.0,
    ),
    "sodium_hydroxide": Component(
        # Tb_C alto (sólido fundido) — no se vaporiza en condiciones de proceso.
        name="sodium_hydroxide", label="Hidróxido de sodio (NaOH)",
        mw=40.00, tb_c=1388.0,
        cp_l_a=1.490, cp_l_b=0.00000,
        cp_v_a=1.490, cp_v_b=0.00000,
        dh_vap=0.0,
    ),
    "sodium_chloride": Component(
        name="sodium_chloride", label="Cloruro de sodio (NaCl)",
        mw=58.44, tb_c=1465.0,
        cp_l_a=0.850, cp_l_b=0.00000,
        cp_v_a=0.850, cp_v_b=0.00000,
        dh_vap=0.0,
    ),
    "sulfuric_acid": Component(
        name="sulfuric_acid", label="Ácido sulfúrico (H₂SO₄)",
        mw=98.08, tb_c=337.0,
        cp_l_a=1.380, cp_l_b=0.00000,
        cp_v_a=1.000, cp_v_b=0.00000,
        dh_vap=510.0,
    ),
    "nitric_acid": Component(
        name="nitric_acid", label="Ácido nítrico (HNO₃)",
        mw=63.01, tb_c=83.0,
        cp_l_a=1.740, cp_l_b=0.00000,
        cp_v_a=1.200, cp_v_b=0.00000,
        dh_vap=480.0,
    ),
    "sodium_carbonate_sol": Component(
        # Solución acuosa — Cp y ΔHvap dominados por el agua.
        name="sodium_carbonate_sol", label="Solución de soda (Na₂CO₃ aq)",
        mw=105.99, tb_c=102.0,
        cp_l_a=3.500, cp_l_b=0.00000,
        cp_v_a=2.000, cp_v_b=0.00000,
        dh_vap=2200.0,
    ),

    # ---- Inorgánicos para SO2/SO3 (E06 ácido sulfúrico) ----
    "sulfur_dioxide": Component(
        name="sulfur_dioxide", label="Dióxido de azufre (SO₂)",
        mw=64.07, tb_c=-10.0,
        cp_l_a=1.350, cp_l_b=0.00000,
        cp_v_a=0.630, cp_v_b=0.00020,
        dh_vap=389.0,
    ),
    "sulfur_trioxide": Component(
        name="sulfur_trioxide", label="Trióxido de azufre (SO₃)",
        mw=80.06, tb_c=45.0,
        cp_l_a=1.400, cp_l_b=0.00000,
        cp_v_a=0.760, cp_v_b=0.00020,
        dh_vap=540.0,
    ),

    # ---- Jabón (E13) ----
    "soap": Component(
        # Pseudo estearato sódico (proxy de jabones de Na).  No volátil.
        name="soap", label="Jabón (pseudo C₁₈H₃₅O₂Na)",
        mw=306.46, tb_c=99999.0,
        cp_l_a=2.000, cp_l_b=0.00200,
        cp_v_a=2.000, cp_v_b=0.00200,
        dh_vap=0.0,
    ),

    # ---- Genéricos (fallback si el user no sabe el componente) ----
    "generic_liquid": Component(
        name="generic_liquid", label="Líquido genérico (hidrocarburo)",
        mw=100.0, tb_c=120.0,
        cp_l_a=2.000, cp_l_b=0.00200,
        cp_v_a=1.500, cp_v_b=0.00300,
        dh_vap=400.0,
    ),
    "generic_vapor": Component(
        name="generic_vapor", label="Vapor genérico",
        mw=50.0, tb_c=30.0,
        cp_l_a=2.000, cp_l_b=0.00200,
        cp_v_a=1.500, cp_v_b=0.00300,
        dh_vap=300.0,
    ),
}


def get(name: str) -> Optional[Component]:
    """Devuelve un Component por nombre.  None si no existe."""
    return COMPONENTS.get(name)


def list_names() -> List[str]:
    """Lista de claves en orden alfabético + genéricos al final."""
    keys = [k for k in COMPONENTS if not k.startswith("generic")]
    keys.sort(key=lambda k: COMPONENTS[k].label.lower())
    keys += [k for k in COMPONENTS if k.startswith("generic")]
    return keys


def list_labels() -> List[tuple]:
    """Lista de (clave, label) para combos UI."""
    return [(k, COMPONENTS[k].label) for k in list_names()]


# ======================================================
# CÁLCULOS PARA MEZCLAS
# ======================================================
# composition: Dict[str, float] = {component_name: mass_fraction}
# La suma de fracciones debe ser ≈ 1.0 (validamos con tolerancia).

def normalize_composition(comp_dict: Dict[str, float]) -> Dict[str, float]:
    """Renormaliza una composición para que las fracciones sumen 1.0.
    Si la suma es 0, devuelve dict vacío."""
    if not comp_dict:
        return {}
    total = sum(v for v in comp_dict.values() if v > 0)
    if total <= 0:
        return {}
    return {k: v / total for k, v in comp_dict.items() if v > 0}


def cp_mix_kJ_kg_K(comp_dict: Dict[str, float], T_C: float,
                    phase: str) -> float:
    """Cp de la mezcla ponderado por fracción másica."""
    if not comp_dict:
        return 0.0
    cp = 0.0
    for name, w in comp_dict.items():
        c = COMPONENTS.get(name)
        if c is None or w <= 0:
            continue
        cp += w * c.cp(T_C, phase)
    return cp


def delta_h_vap_mix(comp_dict: Dict[str, float]) -> float:
    """ΔH_vap de la mezcla ponderado por fracción másica (kJ/kg).
    Aproximación: usa el ΔH_vap a Tb de cada componente puro."""
    if not comp_dict:
        return 0.0
    return sum(
        w * COMPONENTS[name].dh_vap
        for name, w in comp_dict.items()
        if name in COMPONENTS and w > 0
    )


def mw_mix(comp_dict: Dict[str, float]) -> float:
    """MW promedio ponderado por fracción másica.
    Para gases ideales: 1/MW_mix = Σ w_i/MW_i  (regla de Kay).
    Acá usamos promedio simple ponderado (suficiente para screening)."""
    if not comp_dict:
        return 0.0
    return sum(
        w * COMPONENTS[name].mw
        for name, w in comp_dict.items()
        if name in COMPONENTS and w > 0
    )


def tb_dominant(comp_dict: Dict[str, float]) -> float:
    """Temperatura de ebullición del componente dominante en la
    mezcla (ponderado por w).  Útil para detectar cambio de fase."""
    if not comp_dict:
        return 0.0
    return sum(
        w * COMPONENTS[name].tb_c
        for name, w in comp_dict.items()
        if name in COMPONENTS and w > 0
    )
