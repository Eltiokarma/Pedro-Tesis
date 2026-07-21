# Auditoría: dimensionamiento (size/S) y propagación de presión

**Fecha:** 2026-07-18
**Motivo:** (1) entender cómo se calcula el size de los equipos y qué hace el
"botón de autosize antiguo"; (2) un bug reportado de presión — una corriente
entra a un equipo a ~30 bar y sale a ~1 bar, con la caída (ΔP) configurada en
0.5 bar **sin restarse**.

> **Estado:** auditoría + **fixes APLICADOS** (2026-07-18, ver §Parte 3 al
> final). Gate 41/41 verde con goldens re-exportados deliberadamente; 522
> tests no-GUI verdes. Solo cambiaron de ISBL los dos ejemplos esperados
> (gas_sweet +0.57%, hda_full −5.31%), ambos verificados como correcciones
> físicas. Los grupos 1-2 (economía ya analizada) no se movieron.

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

### FIX aplicado (2026-07) — auto-sizing de equipos no-HX + swallow visible

Se cerró la deuda del auto-sizing en tres partes (gate 41/41 verde, 522
tests verdes; los ejemplos `S_locked=True` no se tocan → golden intacto
salvo `talara`, que tenía 3 bombas placeholder desbloqueadas → re-export):

1. **El solver ahora auto-dimensiona TODOS los equipos sin `S_locked`**, no
   solo los HX. Nueva `flowsheet_solver._size_process_equipment(fs)` (llamada
   en `solve()` tras `_size_heat_exchangers`): despacha al sizer por eq_type
   o categoría (reactores, torres, bombas, compresores, vessels, tanques,
   hornos, evaporadores) y escribe `b.S` solo si el bloque NO está locked.
   Un equipo desbloqueado con `S=0` ya no anula su costo en silencio → el
   ISBL **degrada con gracia** en vez de colapsar (methanol desbloqueado:
   antes ~0, ahora 1.05× del baseline; sugar: 0.09× → 0.69×).

2. **Sizers reconectados** (`equipment_sizing.SIZER_BY_EQTYPE`): los equipos
   de "Solids / sep." (evaporador, dryer, crystallizer) no tenían su
   categoría en `SIZER_BY_CAT`, pero su `S` lo calcula un sizer existente —
   área de transferencia (`size_evaporator`) para evaporador/dryer, volumen
   por residencia (`size_vessel`) para crystallizer. Antes un evaporador
   desbloqueado quedaba en `S=0` (caso sugar: 4 evaporadores grandes sin
   costo). El filtro de banda queda sin sizer aplicable (S = área de
   filtración) → lo reporta el canal de abajo.

3. **El swallow silencioso es ahora visible**: `capex.compute_fci` devuelve
   `zero_cost_blocks` — lista de bloques cuyo costo salió 0 (S≤0 sin
   dimensionar, eq_type sin correlación, o excepción de costeo), excluyendo
   nodos virtuales `Ambient`. Se expone en `economics.capex.zero_cost_blocks`
   del resultado del solver. Los 41 ejemplos shippeados salen **limpios**
   (cero bloques sin costo).

**Deuda restante (menor):** faltan sizers para 2 tipos de "Solids / sep." —
`Filter — belt` (área de filtración desde caudal de slurry) y una correlación
de residencia propia para `Crystallizer` (hoy usa `size_vessel` como proxy).
Son equipos de pocos ejemplos; el canal `zero_cost_blocks` los hace visibles.

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

---

# Parte 3 — Fixes aplicados (2026-07-18)

Se aplicaron los tres fixes de presión + la alineación de convención de
signo, más dos correcciones colaterales que el fix destapó. Todo validado.

## Cambios en el solver

1. **Bug A — guard del reactor** (`flowsheet_solver.py`,
   `solve_equilibrium_reactors`): el guard `if b.P_op_bar > 0` pasó a
   `if b.P_op_bar > ATM+1e-6` (ATM=1.01325), coherente con
   `_seed_reactor_pressures`. Un reactor sin `P_op_bar` declarado (default
   1.0) ya no estampa 1.0 en sus salidas: deja que la propagación resuelva
   salida = entrada + ΔP.

2. **Bug A — early-return de la propagación** (`solve_pressure_hydraulic`):
   antes salía sin propagar si ningún stream estaba `pressure_locked`. Ahora
   también corre la propagación si existe algún bloque con `delta_p_bar`
   declarado (`has_block_dp`), así el ΔP configurado se aplica aunque no haya
   locks.

3. **Bug B — HX de 4 puertos por lado** (`solve_pressure_propagation`): la
   presión de referencia de cada salida ya no es `min(TODAS las entradas)`.
   Para un HX de 4 puertos (`_four_port_hx_ids`) cada salida hereda la
   presión de la entrada de SU lado (`_stream_side` sobre tube/shell); el
   resto de bloques usa el min de sus entradas como antes. Elimina el
   colapso del lado de alta P al de baja (gas_sweet E-101: rich amine ahora
   50 bar en vez de 1.01).

4. **Convención de signo** (`flowsheet_model.py`): docstring alineado con el
   código — `delta_p_bar` es un sumando CON SIGNO (positivo bombas/compresores,
   negativo columnas/HX/hornos); no un módulo "a restar".

## Correcciones colaterales que el fix destapó

- **hda_full / K-101** (`data/examples/hda_full.json`): al corregir la
  propagación, el compresor de reciclo K-101 dejó de sizearse a un target
  espurio (48.99 bar, ~2× la presión del loop) y quedó a 25 bar (correcto).
  Eso reveló que K-101 estaba **sub-especificado** (sin P_op_bar ni ΔP): su
  compresión espuria previa era lo que "cerraba" la energía del loop. Fix de
  datos honesto: `K-101.P_op_bar = 25.0` (el compresor de reciclo opera a la
  presión del loop). Restaura status `ok`, sin warnings de energía. ISBL de
  hda_full baja de 32.94 M a 31.19 M (se elimina el sobre-costeo por la
  sobre-presión ficticia).

- **inspector_evidence.compressor_text**: el fix cambió qué compresor
  inspecciona un test, destapando una divergencia **pre-existente** —
  `compressor_metrics` emitía `Q intercool` (multietapa) pero
  `compressor_text` no lo imprimía. Se agregó la línea al texto para que
  ambos coincidan.

## Impacto en goldens (re-export deliberado)

| Ejemplo | ISBL antes | ISBL después | sum_duty |
|---|---:|---:|---|
| gas_sweet | 12 772 946 | 12 845 908 (+0.57%) | sin cambio |
| hda_full | 32 940 734 | 31 190 228 (−5.31%) | −438.9 → −553.9 |

Ambos verificados como **correcciones físicas**: gas_sweet ahora conserva la
presión de la amina rica por el lado tube del HX; hda_full elimina la
sobre-presión ficticia del compresor de reciclo. Ningún ejemplo cambió de
`overall_status`. Los grupos 1-2 (economía analizada) **no se movieron** —
solo gas_sweet y hda_full (grupo 3) tenían el patrón del bug.

## Verificación

```
python gate_examples.py               # 41/41 verde
python gate_examples.py --registry    # 41/41 verde
python -m pytest tests/ (no-GUI)      # 522 passed, 1 skipped
# repro del bug reportado (entra 30 bar, HX ΔP=-0.5):
#   feed no-locked ΔP=-0.5 → 29.5 bar  (antes: 1.0)  ✓
```

## Pendiente conocido (no crítico, fuera del bug reportado)

- Un stream con presión no-default (ej. feed a 30 bar) pero SIN lock y SIN
  ningún ΔP de bloque en el flowsheet no propaga (la propagación es opt-in:
  requiere un lock o un ΔP declarado). El bug reportado —ΔP configurado que
  no se restaba— sí quedó resuelto. Ampliar el opt-in a "feed con P
  declarada" es un cambio de diseño separado.
- La exclusión de utilities del `min` en bloques no-HX (evitar que el vapor
  de un reboiler arrastre la salida de proceso) se dejó SIN aplicar: ningún
  ejemplo la necesita hoy y ampliaba la superficie de cambio. Anotado por si
  aparece un flowsheet que lo requiera.
