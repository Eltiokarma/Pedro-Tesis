# Hidráulica de presión en el flowsheet

Cómo el simulador resuelve presiones, dimensiona bombas/compresores y evalúa
cavitación. Implementado en `pressure_drop.py`, `equipment_design.py`,
`flowsheet_solver.py` (`solve_pressure_propagation`, `solve_pressure_hydraulic`)
e inicializado en los ejemplos por `hydraulic_defaults.py`.

## 1. Teoría — de qué se compone el ΔP de una bomba

Una bomba/compresor debe levantar la presión lo suficiente para que la
corriente llegue a su destino con la presión requerida, venciendo todas las
pérdidas del camino:

```
ΔP_bomba = (P_destino − P_succión)            ← salto neto requerido
         + Σ ΔP_tubería   (Darcy-Weisbach)    ← fricción + accesorios
         + Σ ΔP_equipos   (HX, columnas, …)   ← caídas por equipo
         + ρ·g·Δz          (altura)            ← elevación
```

- **ΔP_tubería**: Darcy-Weisbach con factor de fricción de Churchill
  (`pressure_drop.py`, validado vs Perry). `ΔP = f·(L/D)·ρv²/2 + K·ρv²/2`.
- **ΔP_equipos**: caída de carga por cada equipo intermedio (ver tabla).
- El solver hace este balance automáticamente (sección 3).

## 2. ΔP típicas por tipo de equipo

Defaults aplicados por `hydraulic_defaults.apply_typical_pressures`
(negativo = pérdida). Idempotente: si el equipo ya declara `delta_p_bar`, no
se sobrescribe.

| Equipo                              | ΔP [bar] |
|-------------------------------------|----------|
| Heat exch. — floating/fixed tube    | −0.5     |
| Heat exch. — air cooler             | −0.3     |
| Heat exch. — kettle reboiler        | −0.2     |
| Heat exch. — plate frame            | −0.4     |
| Tower / column (sin trays)          | −0.3     |
| Tower / column (con N etapas)       | −0.3 − N·0.007 |
| Fired heater (cualquier variante)   | −0.3     |
| Reactor — packed / jacketed non-agit| −1.0     |
| Reactor — autoclave                 | −0.2     |
| Reactor — jacketed agitated (CSTR)  | −0.1     |
| Vessel / drum / knockout            | −0.05    |
| Decanter — gravity                  | −0.05    |
| Filter                              | −0.5     |
| Centrifuge                          | −1.0     |
| Cyclone                             | −0.1     |
| Válvula de control                  | −0.7     |
| Válvula de alivio / mixer / splitter / tanques | 0 |

Bombas y compresores **no** tienen ΔP fija: la auto-dimensiona el solver.

## 3. Cómo el solver auto-dimensiona

`solve_pressure_hydraulic(fs)` es **opt-in**: solo corre si hay alguna presión
*locked* aguas abajo. Hay dos fuentes de locks:

1. **Reactores a alta P**: `_seed_reactor_pressures` siembra como lock la P de
   las corrientes de proceso de todo bloque con `P_op_bar > 1 atm` (ammonia 200,
   methanol 80, HDA 25, SMR 25…). Eso da el anchor downstream del compresor.
2. **`hydraulic_defaults`**: lockea feeds (1.013 bar) y productos-a-tanque
   (1.5 bar), y los anchors por ejemplo de `EXAMPLE_PRESETS` (trenes
   bomba→columna casi atmosféricos).

Workflow del solver:

1. **Forward pass** (`solve_pressure_propagation`): propaga P desde los feeds
   locked usando los ΔP declarados (equipos suman/restan, tuberías restan).
2. Para cada bomba/compresor sin ΔP, busca el próximo stream locked downstream
   (`_find_downstream_target`, BFS) y calcula
   `ΔP_necesaria = (P_target − P_succión) + Σ pérdidas intermedias`.
3. Setea `block.delta_p_bar` y re-propaga. Itera hasta converger.
4. Calcula `W_elec`: bombas `m·ΔP/(ρ·η)`; compresores trabajo politrópico.

La filosofía es "sudoku": se declara lo mínimo (feed P + un anchor) y el solver
infiere todo el ΔP intermedio. Para anclar un tren a mano:

```python
from hydraulic_defaults import lock_pump_train
lock_pump_train(fs, feed_stream_name="S-feed", target_stream_name="S-rx-in",
                target_P_bar=25.0)   # bomba/compresor entre medio se dimensiona
```

## 4. NPSH y cavitación

`equipment_design.pump_sizing` calcula:

- **NPSHa** (disponible) `= (P_succión − P_vapor)/(ρg) + Δz`. Es la energía neta
  por encima de la presión de vapor en la succión.
- **NPSHr** (requerido, estimado) por velocidad específica de succión (Karassik).
- **Margen de cavitación** `= NPSHa − NPSHr`.

Interpretación:
- **Margen ≥ 1.0 m**: ok.
- **0.5–1.0 m**: ajustado (warning) — subir la succión o bajar T.
- **< 0.5 m / NPSHa < 0**: riesgo de cavitación. Causas típicas: succión bajo
  vacío (evaporadores), líquido cerca de su punto de burbuja, o columna de
  succión insuficiente. Solución: presurizar/elevar el tanque de succión,
  subcoolar, o reducir caudal.

## 5. Ejemplo paso a paso — planta hidráulica

`_example_hydraulic_plant` es el caso de referencia (ya instanciaba el sistema
correctamente). Tanque de succión → bomba P-101 → tubería + HX → producto con P
locked. El solver:

1. Lockea feed y producto.
2. Propaga P; detecta que P-101 no tiene ΔP.
3. BFS encuentra el producto locked, suma pérdidas de tubería + HX.
4. Dimensiona ΔP_P-101 para cerrar el balance.
5. Calcula W_elec, head y NPSHa.

Verificable headless con:

```bash
python validate_ui.py    # imprime la tabla ΔP / W_elec / NPSHa por bomba
```
