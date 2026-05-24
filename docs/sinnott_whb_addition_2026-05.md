# Adición de Waste Heat Boilers al catálogo (Sinnott) — mayo 2026

Documenta la incorporación de dos clases de waste-heat boiler (WHB) al
catálogo de equipos, tomadas de Sinnott & Towler, *Chemical Engineering
Design*, 6th ed (2019), Tabla 6.6.

## (a) Limitación detectada en Turton

El catálogo `equipment_costs.EQUIPMENT_DATA` era 100 % Turton (4th ed,
correlación `log10(Cp°) = K1 + K2·log10(S) + K3·[log10(S)]²`, CEPCI base
397/2001). Turton **no incluye** waste-heat boilers gas-vapor industriales.
En `docs/fix_utility_autoselect_2026-05.md` se documentó que, sin un tipo
de equipo apropiado, los WHB se modelaban como *kettle reboiler* — cuya
correlación Turton a áreas grandes (≥300 m²) dispara el CAPEX de forma
desproporcionada (+4.4 M USD en HNO₃ Ostwald). Sinnott sí cubre WHBs.

## (b) Decisión: catálogo de fuentes mixtas

Se agrega Sinnott como fuente **complementaria**, sin tocar ninguna entry
Turton. Cada registro de `EQUIPMENT_DATA` declara ahora dos claves de
auditabilidad:

- `correlation`: `"turton"` (default) o `"sinnott"`.
- `source`: `"Turton_2018_AppA"` (default) o `"Sinnott_2019_Table_6.6"`.

`purchased_cost` despacha a la correlación correcta según `correlation`.

## (c) Coeficientes Sinnott (transcripción literal de Tabla 6.6)

Correlación: **C_e = a + b · S^n** (purchased cost en GBP 2010, S en las
unidades indicadas).

| Tipo | S units | S_lower | S_upper | a | b | n |
|------|---------|---------|---------|---|---|---|
| Packaged 15-40 bar | kg/h steam | 5 000 | 200 000 | 4 600 | 62 | 0.8 |
| Field erected 10-70 bar | kg/h steam | 20 000 | 800 000 | −90 000 | 93 | 0.8 |

Entradas en `EQUIPMENT_DATA`: `"Heat exch. — WHB packaged"` y
`"Heat exch. — WHB field erected"`, categoría `"Heat exchangers"`.

## (d) Conversiones (con fuente declarada)

```
cost_usd_target = (a + b·S^n) · GBP_TO_USD_2010 · (CEPCI[year] / CEPCI_BASE_SINNOTT)
```

- **CEPCI 2010 annual avg = 550.8** (Chemical Engineering magazine) →
  `CEPCI_BASE_SINNOTT`.
- **GBP/USD avg 2010 = 1.5458** (Bank of England spot rates 2010) →
  `GBP_TO_USD_2010`.
- `CEPCI[year_target]` vía `cepci.py` (igual que las correlaciones Turton).

**Costos verificados (year_target = 2026, CEPCI = 797.9):**

| Equipo | S | GBP 2010 | **USD 2026 (Cp)** |
|--------|---|----------|-------------------|
| WHB packaged | 50 000 kg/h | 360 696 | **807 699** |
| WHB field erected | 100 000 kg/h | 840 000 | **1 880 993** |

> Nota: una estimación previa situaba el field-erected a 100 000 kg/h en
> 1.0–1.2 M USD. El valor **verificado** es ~1.88 M: la curva field-erected
> (`93·S^0.8 − 90 000`) es empinada y a 100 000 kg/h ya está en 840 k GBP.
> El test `test_field_erected_cost_verified` fija el valor real.

> Caveat metodológico: el pipeline aplica el factor de módulo desnudo
> Turton (FBM ≈ 3.47 para HX) sobre el Cp Sinnott al calcular CBM. Sinnott
> usaría factores de Hand, no FBM Turton. Los tests verifican el Cp
> (purchased cost), no el CBM; el CBM de un WHB es por tanto aproximado.

## (e) Rangos de validez

- Packaged: 5 000 – 200 000 kg/h de vapor, 15–40 bar.
- Field erected: 20 000 – 800 000 kg/h, 10–70 bar.

Fuera de rango, `purchased_cost` emite `UserWarning` (igual que Turton).

## Integración

- `equipment_ports.WHB_EQ_TYPES` agrupa kettle reboiler + las dos clases
  WHB; `autoselect_heat_source` les habilita la rama `bfw_to_steam_*`.
- `equipment_sizing.size_whb` dimensiona el WHB por caudal de vapor
  generado: `S [kg/h] = |Q| · 3600 / ΔH_vap · η_gen`. Se despacha vía
  `SIZER_BY_EQTYPE` (prioridad sobre la categoría), porque el S de un WHB
  es kg/h, no área.
- `equipment_sizing.autoselect_whb_subtype` (Packaged ≤ 50 000 kg/h, si no
  Field erected) queda **exportable pero sin cablear** a UI/autoselect.
- Puertos: `HX_PORTS` (tube = proceso caliente, shell = BFW/steam). Iconos:
  reusan el visual *kettle* (TODO: SVG dedicado).

## (f) Trabajo futuro

- **Refit de ejemplos**: migrar HNO₃ E-202 (y el tren E-201/E-203) a las
  clases WHB; eliminar el crédito de vapor hardcodeado. (Pasada separada.)
- Otros equipos de la Tabla 6.6 de Sinnott (thermosyphon, propeller, etc.).
- Cablear `autoselect_whb_subtype` a la UI / a `autoselect_heat_source`.
- SVG dedicado para WHB.

---

# Addendum (2026-05): Hand factor, refit E-103, guard de sub-escala

## 1. Fix del F_BM: método de Hand para equipos Sinnott

Aplicar el factor de módulo desnudo de Turton (F_BM ≈ 3.47 para HX, con
base de presión/material distinta) sobre un Cp Sinnott era inconsistente.
Sinnott usa el **método de Hand** (§6.3.3) con factores propios.

`bare_module_cost` ahora ramifica por `correlation`:

- `sinnott` → `CBM = Cp · installation_factor` (Hand), con `FP=FM=1.0` y
  `install_method="Hand (Sinnott §6.3.3)"`.
- `turton` (default) → F_BM tradicional como siempre.

Factores de Hand declarados en cada entry (con comment + fuente):

| Equipo | Hand factor | Razón |
|--------|------------:|-------|
| WHB packaged | 3.5 | HX a presión pre-armado |
| WHB field erected | 4.0 | boiler estructural montado in situ (≈ pressure vessel) |

CBM verificado (year 2026): packaged 807 699 × 3.5 = **2 826 948**;
field erected 1 880 993 × 4.0 = **7 523 971**.

## 2. Refit aceptado: `industrial_complete` E-103 → WHB packaged

E-103 es el WHB del loop de síntesis de metanol: recupera ~22.7 MW del
efluente del reactor Cu/ZnO generando vapor LP.

| | E-103 kettle reboiler (antes) | E-103 WHB packaged (después) |
|--|------------------------------:|------------------------------:|
| S | 95 m² (área, sub-dimensionada) | 31 583 kg/h (caudal de vapor) |
| Cp (2024) | 186 667 | 562 457 |
| CBM | 614 135 (F_BM 3.29) | 1 968 600 (Hand 3.5) |
| heat_source | bfw_to_steam_LP | bfw_to_steam_LP (sin cambio) |
| capex planta | 39 908 374 | 41 243 799 (+1.34 M) |
| NPV | 10 950 820 | **9 771 743** |
| IRR | 15.8 % | **15.0 %** (VIABLE) |

El refit **sube** el CAPEX (+1.34 M) porque el kettle reboiler a 95 m²
estaba sub-valuado para 22.7 MW (área física requerida ≈190 m²); el WHB
packaged dimensionado por caudal de vapor es el modelo realista.  El
revenue de vapor (−5.53 M/yr) no cambia (depende del duty).  NPV/IRR
bajan levemente pero el proyecto sigue VIABLE.

## 3. Caso donde NO aplica WHB: HNO3 Ostwald E-202

**Criterio de escala (Sinnott Tabla 6.6):**

- WHB packaged: válido para **5 000 – 200 000 kg/h** de vapor (≈3–130 MW).
- WHB field erected: válido para **20 000 – 800 000 kg/h** (≈13–520 MW).

HNO3 E-202 es un economizador de gas (400→200 °C) con duty **92.6 kW →
~167 kg/h** de vapor: **30× por debajo** del floor del WHB packaged.
Refitearlo sería:

- a S real (167 kg/h): extrapolación inválida de la correlación Sinnott
  (`fuera_rango=True`), Cp irreal;
- a S floor (5 000 kg/h): modelar un cooler de 0.09 MW como un boiler de
  ~3 MW (CBM 250 k → 478 k), sobre-estimación catastrófica.

**Decisión: E-202 queda como `Heat exch. — fixed tube` + cooling_water.**
Es un trade-off de scope explícito (el ejemplo HNO3 es piloto/laboratorio,
sub-MW), no un error de modelado.  El warning del módulo térmico señala
que a escala industrial sería un WHB.

### Tabla didáctica: cuándo refitear a WHB

| HX | duty | steam-rate | vs floor 5 000 kg/h | Decisión |
|----|-----:|-----------:|---------------------|----------|
| `industrial_complete` E-103 | 22.7 MW | 31 583 kg/h | 6.3× **dentro** | ✅ refit a WHB packaged |
| `hno3_ostwald` E-202 | 0.09 MW | 167 kg/h | 30× **debajo** | ❌ queda fixed tube |
| `hno3_ostwald` E-201 | 0.26 MW | 470 kg/h | 11× debajo | (kettle reboiler — área, sin floor) |

> Nota: el kettle reboiler (correlación Turton por **área**) no tiene
> floor de caudal de vapor, por eso sirve como proxy de WHB a escalas
> chicas donde Sinnott no aplica.  El WHB Sinnott (por **caudal**) es
> para escala industrial.

## 4. Guard de sub-escala en `size_whb`

`equipment_sizing.size_whb` ahora compara el caudal de vapor calculado
contra el `S_min` de la correlación del eq_type.  Si cae por debajo:

- emite `UserWarning` ("WHB sub-escala: …");
- persiste `block._whb_diagnostics` con `steam_rate_kg_h`, `S_min`,
  `warning` y `scale_mismatch` (True si la diferencia es >5×);
- devuelve `S` clampeado al floor (no extrapola en silencio).

Esto evita que un futuro WHB sub-escala dispare la correlación Sinnott
fuera de rango sin avisar.

## 5. Impacto en el sweep de 41 ejemplos

`outputs/whb_fix_impact.csv` regenerado con el refit de E-103 y la nueva
columna `cbm_method` (Turton / Turton+Hand).  **Único ejemplo que cambió
vs el CSV anterior: `industrial_complete`** (NPV 10.95 M → 9.77 M, IRR
15.8 % → 15.0 %, capex +1.34 M).  Ningún ejemplo nuevo con
`sign_flipped=True`.  40/41 idénticos.
