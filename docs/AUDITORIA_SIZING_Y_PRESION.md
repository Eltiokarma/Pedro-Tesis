# Auditoría: dimensionamiento (size/S) y propagación de presión

**Fecha:** 2026-07-18
**Motivo:** (1) entender cómo se calcula el size de los equipos y qué hace el
"botón de autosize antiguo"; (2) un bug reportado de presión — una corriente
entra a un equipo a ~30 bar y sale a ~1 bar, con la caída (ΔP) configurada en
0.5 bar **sin restarse**.

> **Estado:** auditoría (diagnóstico + evidencia + plan de fix). Los fixes de
> presión **NO se aplicaron todavía**: tocan `effective_pressure → factor FP
> de Turton → ISBL`, que es un valor golden de los 41 ejemplos, así que exigen
> re-export deliberado de goldens y re-validación del gate. Se documentan acá
> para aplicarlos como cambio separado y controlado.

---

# Parte 1 — Dimensionamiento (¿cómo se calcula el size?)

## Hay DOS rutas de sizing, asimétricas

| | Botón "Auto-size S" (antiguo) | Solver `_size_heat_exchangers` (actual) |
|---|---|---|
| Cuándo corre | Manual, menú *Simulación → "Auto-size S"* | Automático en cada `solve()` |
| Qué equipos | **Todos** los tipos | **Solo intercambiadores de calor** |
| ¿Respeta `S_locked`? | **NO** — lo ignora y pisa `S` | **Sí** (`flowsheet_solver.py:1224`) |
| Escribe `b.S` | Siempre | Solo si `S_locked=False` |

- **Botón antiguo**: `action_autosize()` (`flowsheet_qt.py:7182-7233`) →
  `equipment_sizing.auto_size_blocks(fs, only_if_unset=False)`
  (`equipment_sizing.py:682-738`). Recorre TODOS los bloques, recalcula `S`
  desde el último solve y **sobreescribe siempre**, ignorando `S_locked`
  (la palabra ni aparece en la función). Es "antiguo/peligroso" porque
  precede a la introducción del lock: puede pisar tamaños fijados a mano.
- **Solver actual**: `_size_heat_exchangers()` (`flowsheet_solver.py:1195-1228`,
  llamado en `:6207`) solo redimensiona la categoría "Heat exchangers" y
  respeta `S_locked`. **Ningún otro equipo** (reactores, torres, bombas,
  vessels, tanques, compresores, hornos) se redimensiona en un `solve()`
  normal — dependen 100% del `S` fijado a mano de los JSON.

## Cómo se calcula S por tipo de equipo

Todas las variables salen del último `solve()` (`mass_flow`, `block.duty`,
`T_op_K`, `P_op_bar`, `delta_p_bar`). Fórmulas en `equipment_sizing.py`:

| Equipo | S = | Variable de proceso | Línea |
|---|---|---|---|
| Intercambiadores | Área `A = |Q|·1000/(U·F·ΔT_lm)` [m²] | `duty` + ΔT_lm | `:326-394` |
| Hornos | `|duty|` [kW], piso 1000 | `duty` | `:397-402` |
| Reactores | `V = (ṁ/ρ)·τ` [m³] o `reactor_volume_L` | ṁ + τ por tipo + ρ | `:405-421` |
| Bombas | Potencia eléctrica [kW] | ṁ, ΔP, ρ, η | `:424-434` |
| Compresores | Potencia al eje [kW] (politrópico) | ṁ, relación de compresión | `:437-447` |
| Torres | `V = π·D²/4·H`; D por Souders-Brown | flujo vapor, ρ_V/ρ_L, N | `:450-533` |
| Vessels/flash | `V = (ṁ/ρ)·τ_sep` (τ=300 s) [m³] | ṁ | `:536-548` |
| Tanques almac. | `V = (ṁ/ρ)·7 días` [m³] | ṁ del stream mayor | `:551-571` |
| Evaporadores | `A = |Q|·1000/(U·ΔT)` [m²] | `duty` | `:574-587` |
| WHB (calderas) | `S = |Q|·3600/ΔH_vap·η` [kg/h vapor] | duty + utility | `:600-645` |

## Por qué desbloquear (S_locked=False, S=0) COLAPSA el ISBL

Es la causa raíz que ya se observó al escalar ejemplos (grupo 1). Dos
mecanismos, ambos verificados:

1. **Solo `solve()`**: recalcula solo HX. Todo lo demás queda en `S=0` →
   `capex.py:117` llama `bare_module_cost(eq_type, S=0)` →
   `purchased_cost` lanza `ValueError` si `S≤0` (`equipment_costs.py:1245`)
   → el `except` de `capex.py:122-123` lo traga y pone `cbm=0`. Cada equipo
   no-HX aporta **CERO** al ΣCBM → ISBL se desploma **en silencio**.
2. **Con el botón**: los sizers son estimaciones gruesas; sin datos finos
   caen a sus pisos y `auto_size_blocks` los clampa a `S_min`
   (`equipment_sizing.py:721-726`) — el punto más barato de la correlación.

**Conclusión práctica:** los 41 ejemplos vienen con `S_locked=True` a
propósito, porque el auto-sizer es una primera aproximación y, para las 7 de
8 categorías que el solver no redimensiona, la única alternativa (el botón)
ignora el lock. Para escalar un ejemplo hay que escalar `S` **a mano** en
proporción al caudal (como se hizo y verificó en el grupo 1), vigilando que
cada equipo quede dentro del rango válido de su correlación (si no, usar
N unidades en paralelo).

---

# Parte 2 — Bug de presión (entra 30 bar, sale ~1 bar)

## Reproducción (confirmada end-to-end)

Reactor con `P_op_bar` en su default (1.0), feed a 30 bar, ΔP configurada
−0.5 bar:

| feed `pressure_locked` | `delta_p_bar` | salida | esperado |
|---|---|---|---|
| **False** | −0.5 | **1.000 bar** ← BUG | 29.5 |
| False | 0.0 | 1.000 bar ← BUG | ~30 |
| True | −0.5 | 29.500 ✓ | 29.5 |
| True | 0.0 | 30.000 ✓ | ~30 |

El síntoma exacto ("entra 30, sale 1, ignora el ΔP") aparece cuando la
corriente de entrada **NO está `pressure_locked`**.

## Convención de ΔP

El campo es **`block.delta_p_bar`** (`flowsheet_model.py:123`) — **no existe**
`pressure_drop_bar`. Es un sumando **con signo**: bombas/compresores positivo
(sube P), columnas/HX/hornos **negativo** (pérdida). La propagación correcta
(`flowsheet_solver.py:3791`) hace `P_out = P_in + delta_p_bar - ΔP_pipe`, con
`delta_p_bar` negativo → 30 + (−0.5) = 29.5. La fórmula en sí es correcta;
el bug está en que esa ruta **no siempre corre** o es **pisada**.

## Son DOS bugs independientes con el mismo síntoma

### Bug A — el reactor estampa `P_op_bar` default (1.0) en sus salidas

`flowsheet_solver.py:2426-2429` (`solve_equilibrium_reactors`):

```python
if b.P_op_bar > 0:                    # default P_op_bar = 1.0 → SIEMPRE True
    for s_out in proc_outs:
        if not _is_pressure_locked(s_out):
            s_out.pressure_bar = b.P_op_bar   # pisa la salida con 1.0
```

El default de `P_op_bar` es **1.0** (`flowsheet_model.py:141`), así que
`1.0 > 0` siempre se cumple: **cualquier reactor sin `P_op_bar` declarado
estampa 1.0 bar en todas sus salidas de proceso no-locked**, descartando la
presión de entrada y sin restar el ΔP. Es **inconsistente** con
`_seed_reactor_pressures` (`:3297`), que para lo mismo usa el umbral correcto
`P_op_bar > ATM+1e-6` (ATM=1.01325) — es decir, trata el default 1.0 como
"no declarado". Ese desalineamiento de umbral (`> 0` vs `> ATM`) es el
disparador.

Y la corrección no llega: `solve_pressure_hydraulic` hace early-return si
**ningún** stream está `pressure_locked` (`:3388-3396`), así que
`solve_pressure_propagation` (que restaría el ΔP) **nunca corre** cuando el
feed no está locked. En equipos no-reactivos es el mismo Defecto 2: sin
ningún stream locked, la propagación no corre y la salida se queda en su
default `pressure_bar = 1.013` (`flowsheet_model.py:444`), sin heredar los
30 bar de entrada.

### Bug B — intercambiador multi-corriente colapsa al `min` de las entradas

`flowsheet_solver.py:3772` + `:3791` (`solve_pressure_propagation`):

```python
P_in_min = min(s.pressure_bar for s in ins)   # min de TODAS las entradas
...
for s_out in outs:                             # aplicado a TODAS las salidas
    P_out = P_in_min + dp_block - dp_pipe_bar
```

En un intercambiador de dos corrientes (rich/lean, 4 puertos), esto toma el
**mínimo** de ambos lados y lo aplica a **ambas** salidas. Evidencia real —
`gas_sweet` E-101 (intercambiador lean/rich):

```
INLETS  : S-rich-cold=50.00 bar , S-lean-hot=1.01 bar   → min = 1.01
OUTLETS : S-rich-hot=1.01 (¡debería ~50!) , S-lean-warm=1.01
```

El lado rich (amina rica a 50 bar) sale a 1.01 porque el código usó la
presión del lado lean. La propagación ignora `src_port`/`dst_port` (tube/shell),
que es justo la info que distinguiría los dos lados.

## Qué resets SÍ son legítimos (no tocar)

No todo "alto→1 bar" es bug. Verificados como **físicamente correctos**:

- **Anclaje a atmósfera** de streams conectados a bloques `Ambient`
  (`anchor_ambient_pressures:3680`): venteos/chimeneas (ej. `hno3` A15-stack
  → TK-301 Ambient: el expander K-501 ventea a 1 atm, correcto).
- **Tanques de almacenamiento atmosféricos** (ej. `industrial` TK-301:
  condensado 30 bar → BFW 1 bar; el tanque está a atmósfera, luego bombea).
- **Overhead de columnas** a su P_op (ej. `acetic` T-101: S-fondo mantiene
  35 bar, S-vap sale a 1.0 = P_op de la columna).
- **Purgas/let-down** a atmósfera (ej. `haber_rec` V-102: purga a 1 atm).

El fix debe corregir A y B **sin** romper estos casos legítimos.

## Trampa de convención de signo (defecto latente aparte)

El docstring del modelo (`flowsheet_model.py:441-443`) dice "columnas/HX
**RESTAN** delta_p_bar" (implicando valor positivo), pero el código **suma**
`delta_p_bar` con su signo y `hydraulic_defaults.py` lo guarda **negativo**.
Si alguien configura ΔP como **+0.5** siguiendo el docstring, la salida da
**30.5** en vez de 29.5 (dirección invertida). No causa el "1 bar" reportado,
pero es una inconsistencia doc↔código que conviene unificar.

## Plan de fix propuesto (a aplicar como cambio separado y validado)

1. **Bug A** — en `flowsheet_solver.py:2426`, cambiar el guard
   `if b.P_op_bar > 0:` por `if b.P_op_bar > 1.01325 + 1e-6:` (coherente con
   `_seed_reactor_pressures:3297`), para no estampar el default 1.0.
2. **Bug A (corrección)** — que `solve_pressure_hydraulic` (`:3388-3396`) NO
   dependa solo de `pressure_locked`: correr `solve_pressure_propagation`
   también cuando exista algún bloque con `delta_p_bar` declarado (ese
   chequeo ya existe dentro de `solve_pressure_propagation:3738-3749`, solo
   falta no hacer el early-return antes de llamarlo).
3. **Bug B** — propagar por **puertos**: la salida del lado tube toma la
   presión del inlet tube; la del lado shell, del inlet shell. Con
   `src_port`/`dst_port` ya disponibles en el modelo. Alternativa mínima:
   emparejar cada outlet con el inlet del mismo lado en vez de usar el `min`
   global.
4. **Convención de signo** — alinear docstring `flowsheet_model.py:441-443`
   con el código (sumar con signo; ΔP de pérdida es negativo), o normalizar
   el signo en un solo lugar.

### Validación obligatoria del fix

Tras aplicar: `python gate_examples.py` — la presión alimenta
`effective_pressure → FP → ISBL` (golden), así que **es esperable que algunos
ISBL cambien**. Cada cambio hay que verificarlo caso por caso (¿el nuevo ISBL
es el físicamente correcto?) y luego `python export_examples.py` para
regenerar goldens **deliberadamente**. Los ejemplos con presión alta y
reactores/intercambiadores multi-corriente (gas_sweet, hno3, industrial,
haber_rec, ethane_pfr, ethylene_crk, hda) son los candidatos a moverse.
