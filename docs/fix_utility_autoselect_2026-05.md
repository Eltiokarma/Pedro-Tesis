# Fix de autoselección de utilities + generación de vapor (WHB) — mayo 2026

Evidencia auditable del cambio en la selección automática de servicios
(utilities) de los intercambiadores de calor. Resume un bug latente que
distorsionaba el OPEX de utilities en el showcase y el fix de generación de
vapor (waste-heat boiler) que lo expuso.

## (a) El bug original — `block_avg_temperature` devolvía 25 °C

`flowsheet_export.block_avg_temperature` (flowsheet_export.py:506) calculaba
la temperatura media de un bloque filtrando **sólo** las corrientes con
`cp > 0`:

```python
ts = [s.temperature for s in fs.streams.values()
      if (s.src == block_id or s.dst == block_id) and s.cp > 0]
return sum(ts) / len(ts) if ts else t_ref   # t_ref = 25.0
```

Los example builders declaran **composición**, no `cp` explícito (el solver
resuelve `cp` desde `thermo_db`). Por eso, para la inmensa mayoría de los
bloques, `ts` quedaba vacío y la función devolvía el fallback de **25 °C**,
sin relación con la temperatura real del proceso.

## (b) Utilities mal seleccionadas a causa de esto

`compute_utilities_from_duties` usa esa T media para `autoselect_heat_source`
(equipment_ports.py). Con `T_avg = 25 °C`, la rama de enfriamiento elegía:

```
duty < 0 y T_avg(=25) > 35  → False  →  refrigeration
```

Es decir: **cualquier cooler sin `cp` explícito se costeaba como
refrigeración** (precio 8.0 USD/tm), aunque enfriara un gas a 400–900 °C que
físicamente se enfría con agua de torre (0.30 USD/tm) o, mejor aún, generando
vapor. Ejemplo extremo: el WHB E-201 del proceso Ostwald (HNO₃), que enfría
gas de 900 → 400 °C, se costeaba con **refrigerante** y un ΔT_lm de 573 K
(900 °C contra agua a 35 °C).

## (c) Magnitud del impacto agregado

Reporte completo en `outputs/whb_fix_impact.csv` (41 ejemplos, antes/después).
El CAPEX es **byte-idéntico** en los 41 (el fix es 100 % OPEX-side; columna de
control). Resultados:

- **31 de 41** ejemplos cambian el OPEX de utilities; **10** quedan idénticos.
- El cambio es siempre una **corrección a la baja** (refrigeración → agua de
  torre / generación de vapor), en un rango desde ~300 USD/yr (biodiesel) hasta
  **−23.3 MUSD/yr** (industrial_complete: 22.7 M → −0.54 M, pasa a ingreso
  neto por exportación de vapor). Otros casos grandes: gas_sweetening
  (5.30 M → 0.66 M), hda_full (2.69 M → 0.71 M), methanol (1.58 M → 0.82 M).
- **1 solo ejemplo cambia de signo de NPV**: `industrial_complete`
  (NPV −153.2 M → +10.9 M, IRR cruza el hurdle de 10 % a 15.8 %). Era inviable
  por el sobrecosto de refrigeración espurio; con el fix es viable.
- Ningún ejemplo se rompe (192 tests OK, validate_ui 41/41).

## (d) El fix aplicado

1. **`block_avg_temperature`** (flowsheet_export.py:506) ahora promedia la T
   real de las corrientes de **proceso** (excluye `utility`/`ambient`),
   independiente de `cp`.
2. **`autoselect_heat_source`** (equipment_ports.py): para `duty < 0` en un
   `Heat exch. — kettle reboiler` elige `bfw_to_steam_{HP,MP,LP}` según T
   (generación de vapor); el resto cae a agua/refrigerante como antes.
3. **Utilities de generación** nuevas en `UTILITIES`: `bfw_to_steam_{HP,MP,LP}`
   con `type='generation'`, `price` **negativo** (ingreso por exportación),
   `T_sat` para el LMTD y `efficiency` de generación.
4. **`size_heat_exchanger`** (equipment_sizing.py) usa `T_sat` (lado frío
   isotérmico) para el ΔT_lm de los servicios de generación, y emite un
   warning si la T del proceso excede el `T_range` de la utility elegida.
5. **`compute_utilities_from_duties`**: las utilities `generation` entran al
   OPEX con costo negativo (revenue), etiquetadas "exportado (revenue)", sin
   factor de heat-integration (ya son recuperación).
6. **`Block.heat_source_locked`** permite forzar la utility desde la UI
   (saltea el autoselect).

En el caso canónico HNO₃, E-201 pasa de refrigeración a `bfw_to_steam_HP`,
con ΔT_lm de 573 → 341 K, y aparece ingreso por vapor exportado en el OPEX.

## (e) Separación entre los dos fixes

Conviene dejar explícito que **son dos cambios distintos**, aunque viajan
juntos:

- **Fix WHB** (lo pedido): `autoselect_heat_source` + utilities `generation`
  + `T_sat` en el LMTD. Afecta sólo a kettle reboilers con `duty < 0` a alta T.
- **Fix latente** (`block_avg_temperature`): el fix WHB lo **expuso** —
  necesitábamos la T media real para que el autoselect viera 650 °C en E-201
  en vez de 25 °C. Al corregir `block_avg_temperature` corregimos también la
  mis-selección refrigeración→agua de torre en **todos** los coolers sin `cp`,
  no sólo en los WHB. De ahí que cambien 31 ejemplos y no sólo HNO₃: el
  grueso del impacto agregado proviene del fix latente, no del WHB en sí.

## Pendiente conocido — doble conteo en HNO₃

El builder de HNO₃ ya tenía un crédito de vapor **hardcodeado a mano**
(examples_library.py:2876):

```python
self._add_example_extra("Vapor AP recuperado (crédito WHB)",
                        flowrate=4000, price=-25.0,  # negativo = ingreso
                        stream="Utilities")
```

Era el workaround del autor ante la falta de autoselección de WHB
(≈ −100 000 USD/yr). Ahora que E-201 genera `bfw_to_steam_HP`
automáticamente (≈ −115 000 USD/yr), **ese extra manual duplica el crédito**.
No lo tocamos (decisión del autor del ejemplo): hay que **eliminar el
`_add_example_extra`** o bloquear la utility de E-201, pero no ambos.
