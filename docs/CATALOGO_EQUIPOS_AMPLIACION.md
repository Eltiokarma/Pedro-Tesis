# Ampliación del catálogo de equipos + gate de cadena completa (2026-07)

Tanda "aumentemos la cantidad de equipos, aseguremos que todos pasarán sin
problemas" — rama `claude/fichas-tecnicas-equipo-tp1qw5`.

## Qué entró (56 → 60 eq_types)

| eq_type nuevo | Fuente | Notas |
|---|---|---|
| `Turbine — steam` | Turton A.1 (K 2.6259/1.4398/−0.1776, 70-7500 kW) | Formaliza la convención "compresor con P_out<P_in = turbina" que el solver, la evidencia (`_expander_case`) e `icons.py` (`eq-expander`) ya anticipaban. Mismo motor isentrópico; duty<0 → `electricity_generated` (revenue). |
| `Turbine — gas (axial)` | Turton A.1 (2.7051/1.4398/−0.1776, 100-4000 kW) | ídem |
| `Turbine — radial expander` | Turton A.1 (2.2476/1.4965/−0.1618, 100-1500 kW) | ídem |
| `Mixer — impeller` | Turton A.1 Mixers: impeller (3.8511/0.7009/−0.0003, 5-150 kW) | Agitador mecánico. Base de costo = POTENCIA (los otros mixers usan volumen) → sizer propio `size_agitator` con regla P/V de Walas (0.5 kW/m³, τ 10 min). |

Cadena registrada por tipo nuevo: catálogo → sizer → puertos (compresor /
mixer) → prefijo ISA (TB / MX) → eléctrico (turbinas) → validación de fases
(gas/gas) → glifo (proxy familia; silueta propia = encargo del ciclo 5 de
Design) → ícono → keywords del editor → guards de despacho por substring
("turbin") en solver, inspector, evidencia, hidráulica, auditoría y diálogo Qt.

Ejemplo nuevo: **`steam_turbine`** (vapor 40 bar/400 °C → TB-101 → 4 bar):
duty **−687 kW** (genera), T descarga 183 °C, S=687 kW en rango. Golden
congelado; gate de ejemplos **62/62 verde**.

## El gate de cadena (`tests/test_equipment_catalog_chain.py`)

La garantía pedida: TODO eq_type del catálogo (actual y futuro) atraviesa
todas las capas — catálogo bien formado con fuente, costeo resoluble
(Cp/FBM/CBM > 0), costo monótono en rango (canario de coeficientes mal
transcritos), puertos resolubles, prefijo ISA, sizer (salvo internos de
columna), glifo e ícono, ΔP default sin excepción — más humo E2E de turbina
(genera, enfría, dimensiona, evidencia) y agitador (potencia en rango).
**Agregar un equipo y olvidar una capa rompe el test, no la UI en runtime.**

Huecos PREEXISTENTES que el gate encontró al nacer:

1. Los dos condensadores no tenían prefijo ISA → corregido ("E").
2. `Reactor — autoclave`: su correlación DECRECE con el volumen en todo su
   rango [1,15] m³ (Cp(1)=36 k$ → Cp(15)=18 k$; K2=−0.3617 domina hasta
   S≈87). Queda en allowlist documentada `_COSTO_NO_MONOTONO_LEGACY` —
   **cotejar la fila contra Turton A.1 con el libro físico**.

## Candidatos que NO entraron (requieren el libro físico)

La verificación web de coeficientes resultó poco confiable (fuentes 403,
snippets contradictorios — p. ej. el signo de K2 del baghouse). Regla de la
tanda: **no se transcribe ninguna correlación sin verificación**. Pendientes
de alta con Turton A.1 / Sinnott & Towler Table 6.6 en mano:

- Dust collectors: baghouse, electrostatic precipitator, venturi/cyclone
  scrubber (encajan con los ejemplos cement/glass).
- Dryers: rotary, tray, spray (hoy solo drum).
- Conveyors: belt, screw (sólidos de cement/sugar/glass).
- Crushers / mills (cement, glass).
- Filter press placa-y-marco y vacuum drum (hoy solo belt).
- Screens (DSM, vibrating).
- Blenders (ribbon, rotary).

El procedimiento para cada alta está congelado por el gate: entrada en
EQUIPMENT_DATA con fuente → correr `tests/test_equipment_catalog_chain.py`
→ registrar cada capa que el test reclame → ejemplo con instancia + golden.
