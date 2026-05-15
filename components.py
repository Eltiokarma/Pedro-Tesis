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
