"""Frente 4 (auditoría frontend) — propiedades de mezcla verificables.

Congela las propiedades clave contra valores de manual (CRC Handbook
97ª tabla 3 / Perry 8ª cap. 2 / NIST), después de la calibración
Spencer-Danner-Yamada de densidades (sesión 2026-07-22): la capa 7
(`rho_ref` experimental) existía pero solo 3/108 compuestos la usaban —
el agua salía 876.5 kg/m³ (Rackett puro, −12%). Se poblaron los 7
líquidos más usados de los ejemplos.

La decisión de alcance (¿más tablas de Perry?) está documentada en
docs/CASOS_LIBRO.md §Frente 4.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import thermo_db as td


# ρ líquida a 20 °C — CRC 97ª tabla 3 (el punto de calibración exacto)
RHO_20C = {
    "water":    998.2,
    "benzene":  876.5,
    "toluene":  866.9,
    "methanol": 791.8,
    "ethanol":  789.3,
    "acetone":  790.0,
}

# ρ líquida a 25 °C — literatura; ahora sale de la Rackett CALIBRADA
# (extrapolación desde el punto de 20 °C): error < 1%.
RHO_25C = {
    "water":    997.0,
    "benzene":  873.6,
    "toluene":  862.2,
    "ethanol":  785.3,
}


@pytest.mark.parametrize("name,ref", sorted(RHO_20C.items()))
def test_densidad_liquida_20C_calibrada(name, ref):
    rho = td.density_kg_m3(name, 20.0)
    assert rho is not None, f"{name} sin densidad"
    assert abs(rho - ref) / ref < 0.001, (
        f"{name}: ρ(20°C)={rho:.1f} ≠ CRC {ref}")


@pytest.mark.parametrize("name,ref", sorted(RHO_25C.items()))
def test_densidad_liquida_25C_extrapolada(name, ref):
    rho = td.density_kg_m3(name, 25.0)
    assert rho is not None
    assert abs(rho - ref) / ref < 0.01, (
        f"{name}: ρ(25°C)={rho:.1f}, lit {ref} (>1%)")


def test_cp_liquido_agua_y_etanol_perry():
    # Perry 8ª / NIST: Cp_liq(25°C) agua 4.18, etanol 2.44 kJ/(kg·K)
    assert abs(td.cp_mix_kJ_kg_K({"water": 1.0}, 25.0, "liquid")
               - 4.18) < 0.05
    assert abs(td.cp_mix_kJ_kg_K({"ethanol": 1.0}, 25.0, "liquid")
               - 2.44) < 0.15


def test_dhvap_agua_en_tb():
    # ΔHvap del agua a 100 °C: 2256.5 kJ/kg (Perry 8ª, steam tables)
    dh = td.delta_h_vap_kJ_kg("water", 100.0)
    assert dh is not None
    assert abs(dh - 2256.5) / 2256.5 < 0.02, f"ΔHvap agua {dh:.0f}"


def test_cp_mezcla_es_promedio_masico():
    # Regla de mezcla: Cp_mix = Σ wᵢ·Cpᵢ (Perry 8ª §2 — mezcla ideal)
    w = {"water": 0.7, "ethanol": 0.3}
    cp_mix = td.cp_mix_kJ_kg_K(w, 25.0, "liquid")
    cp_hand = (0.7 * td.cp_mix_kJ_kg_K({"water": 1.0}, 25.0, "liquid")
               + 0.3 * td.cp_mix_kJ_kg_K({"ethanol": 1.0}, 25.0, "liquid"))
    assert abs(cp_mix - cp_hand) < 1e-9


def test_densidad_mezcla_volumenes_aditivos():
    # ρ_mix por volúmenes aditivos: 1/ρ = Σ wᵢ/ρᵢ (ideal)
    w = {"water": 0.5, "ethanol": 0.5}
    rho_mix = td.density_mix_kg_m3(w, 20.0, "liquid")
    rho_hand = 1.0 / (0.5 / td.density_kg_m3("water", 20.0)
                      + 0.5 / td.density_kg_m3("ethanol", 20.0))
    assert rho_mix is not None
    assert abs(rho_mix - rho_hand) / rho_hand < 0.01
