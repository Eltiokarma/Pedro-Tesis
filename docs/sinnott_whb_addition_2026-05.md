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
- SVG dedicado para WHB; factores de Hand para el CBM de equipos Sinnott.
