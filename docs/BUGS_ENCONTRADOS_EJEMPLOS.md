# Bugs encontrados construyendo ejemplos nuevos

**Fecha:** 2026-07-18
**Contexto:** al crear ejemplos nuevos para estresar equipos poco usados y
topologías raras (más el intento de re-insertar day-tanks del PR #133),
aparecieron dos defectos. Se documentan con reproducción mínima.

## Ejemplos nuevos agregados (limpios)

- **`salt_crystal`** — Sal por cristalización: brine (26% NaCl) → bomba →
  cristalizador → filtro de banda → dryer → sal seca. Ejercita los 3 equipos de
  "Solids / sep." (cristalizador, filtro, dryer) que antes solo usaba `sugar`.
  Balance cierra (10 000 t → 7 530 t licor madre + 2 470 t sal), físicamente
  sano.
- **`decanter`** — Decantador L-L por gravedad: mezcla agua/benceno → bomba →
  `Decanter — gravity` → agua (fase pesada) + aceite (fase liviana, η=0.95).
  Equipo poco usado (`_sep_liquid_liquid`, clasificación por densidad).
- **`cyclone`** — Ciclón gas/sólido: gases de combustión con sílice → compresor
  → `Cyclone — gas/solid` → gas limpio + polvo. Equipo poco usado; **destapó
  BUG 3 y BUG 4** (ver abajo).
- **`bypass`** — Topología rara: bomba → splitter (KEYED 70/30) → [horno |
  bypass] → mixer → producto. Control de T de mezcla por bypass. Ejercita el
  splitter keyed + recombinación en mixer a distinta T. **Destapó BUG 5.**
- **`parallel`** — Topología rara: dos CSTR en paralelo (debottlenecking) desde
  un mismo splitter, salidas recombinadas en un mixer.
- **`centrifuge`** — `Centrifuge — disc stack`, deshidratación de lodos de CaCO₃
  (sólido/líquido). Equipo poco usado; **destapó BUG 6.**
- **`cooling`** — `Cooling tower — induced draft`, agua de proceso 45→28 °C
  (~2 MW) con bomba de circulación. Equipo poco usado; **destapó BUG 7.**
- **`pfr`** — `Reactor — PFR (tubular)` de glicol. Ejercita el sizing de PFR.
- **`boiler_ft`** — `Boiler — fire tube`, BFW → vapor de proceso (6 MW). **BUG 9.**
- **`letdown`** — `Valve — control globe`, letdown de presión de metanol. **BUG 10.**
- **`blower`** — `Fan — centrifugal radial`, aire de combustión. **BUG 8.**
- **`feed_effluent`** — Intercambio feed-efluente: HX 4 puertos standalone
  (tube: feed frío / shell: efluente del reactor). Lazo TÉRMICO sin reciclo de
  masa — audita la detección de ciclos port-aware fuera de un SCC real.
- **`double_effect`** — Evaporador doble efecto (jugo 12% → 48% sólidos):
  cadena evaporador→evaporador con composición derivada dos veces.
- **`nested_recycle`** — Dos reciclos anidados al MISMO mixer (vapor con purga
  vía compresor + reflujo líquido). **Destapó BUG 11 — el hallazgo más
  importante de la auditoría** (multitear con convergencia falsa).
- **`hen`** — Red de integración térmica: 2 HX feed-efluente **cruzados** en
  contracorriente (el efluente cede calor primero a la etapa caliente E-102 y
  después a la fría E-101). Audita la cadena de HX 4-puertos encadenados.
- **`sidedraw`** — Columna con extracción lateral (metanol/etanol/agua, patrón
  sancionado tipo talara T-101: `splitter_active` + fracciones keyed +
  composiciones lockeadas que cierran por componente).
- **`cw_loop`** — Lazo de cooling water CERRADO con makeup/blowdown/evaporación
  y bomba de reposición. **Destapó BUG 12** (splitter multi-entrada).

Gate 58/58 verde.

---

## BUG 1 — Splitter: las fracciones se mapean a las salidas por ORDEN, no por identidad

**Severidad:** correctitud. Aparece al **editar la topología** alrededor de un
splitter (insertar/reordenar streams desde la UI o transformaciones). Es la
causa raíz del flip de `talara` al re-insertar day-tanks (PR #133).

### Reproducción mínima

```python
import flowsheet_model as fm, flowsheet_solver as fsv, copy
def build(insert_tank=False):
    fs = fm.Flowsheet()
    sp = fm.Block(id=fs.new_id(), name="SP-101", eq_type="Splitter", S=0.0,
                  splitter_active=True, splitter_fractions=[0.5, 0.3, 0.2])
    fs.blocks[sp.id] = sp
    feed = fm.Stream(id=fs.new_id(), name="S-feed", src=0, dst=sp.id,
                     mass_flow=10000, mass_flow_locked=True, phase="liquid",
                     main_component="water", composition={"water": 1.0})
    fs.streams[feed.id] = feed
    p1 = fm.Stream(id=fs.new_id(), name="S-p1", src=sp.id, dst=0, role="product")
    p2 = fm.Stream(id=fs.new_id(), name="S-p2", src=sp.id, dst=0, role="product")
    p3 = fm.Stream(id=fs.new_id(), name="S-p3", src=sp.id, dst=0, role="product")
    for s in (p1, p2, p3): fs.streams[s.id] = s
    if insert_tank:                       # tanque pass-through en S-p1
        tk = fm.Block(id=fs.new_id(), name="TK-x",
                      eq_type="Storage tank — cone roof", S=0.0)
        fs.blocks[tk.id] = tk
        internal = copy.deepcopy(p1); internal.id = fs.new_id()
        internal.name = "S-p1-int"; internal.role = "internal"; internal.dst = tk.id
        fs.streams[internal.id] = internal
        p1.src = tk.id
    return fs

for tag, ins in (("sin tank", False), ("con tank en S-p1", True)):
    fs = build(ins); fsv.solve(fs)
    print(tag, {s.name: round(s.mass_flow) for s in fs.streams.values() if s.role == 'product'})
# sin tank        {'S-p1': 5000, 'S-p2': 3000, 'S-p3': 2000}   ✓ correcto
# con tank en S-p1 {'S-p1': 2000, 'S-p2': 5000, 'S-p3': 3000}   ✗ ROTADO
```

Insertar un tanque transparente en `S-p1` **rota** la asignación: las
fracciones `[0.5, 0.3, 0.2]` terminan en salidas equivocadas.

### Causa raíz

`flowsheet_solver.solve_splitters` (línea ~4010):

```python
outs = [s for s in fs.streams.values() if s.src == b.id]   # orden de enumeración
...
for s_out, frac in zip(outs, fracs):                        # mapea por POSICIÓN
    s_out.mass_flow = feed.mass_flow * frac
```

`outs` depende del orden de `fs.streams.values()` (orden de inserción / id). Al
insertar un bloque, ese orden cambia y `zip(outs, fracs)` empareja cada fracción
con la salida equivocada. La identidad "esta salida lleva esta fracción" es
**posicional**, no estable.

### Fix aplicado — fracciones ancladas por salida (`split_fraction`)

Se agregó el campo opcional **`Stream.split_fraction`** (default `None`). El
solver ahora resuelve el splitter así:

- Si **todas** las salidas del bloque traen `split_fraction` → se usa ese mapeo
  **por identidad de stream** (estable ante inserción/reordenamiento).
- Si no → cae al reparto posicional legacy (`splitter_fractions`) — 100 %
  compatible con los flowsheets viejos.

El mismo criterio keyed se aplica en las 3 rutas que tocaban el splitter:
`solve_splitters`, la deducción durante el tearing (`_solve_mass_iteration`) y
el audit `[W-SPLIT-LOCK]`.

Los 5 ejemplos con splitter (`haber_rec`, `hno3`, `industrial`, `quimpac`,
`talara`) fueron **migrados**: cada salida lleva su `split_fraction`. Golden
idéntico (gate 42/42), pero ahora son robustos a la re-inserción de day-tanks.

> Un simple ordenamiento por id NO alcanzaba: al reemplazar una salida por un
> stream insertado, el conjunto de salidas cambia de identidad. Por eso la
> fracción se ancla a la salida, no a una posición.

Reproducción/regresión: `tests/test_splitter_tearing.py`
(`test_splitter_posicional_rota_al_insertar_bloque` documenta el bug,
`test_splitter_keyed_estable_ante_insercion` verifica el fix).

### Respaldo en la UI (auditoría posterior)

Tres consumidores UI-adyacentes leían **solo** la lista posicional y quedaban
ciegos ante flowsheets keyed-only (los 5 ejemplos nuevos con splitter):

| Consumidor | Antes | Ahora |
|---|---|---|
| `inspector_evidence.splitter_text/metrics` | "Salida 1/2/3 …%" o **nada** | nombre de stream + % (se ve QUÉ salida lleva QUÉ fracción) |
| `flowsheet_export` (xlsx Equipment) | celda vacía | `S-top:0.300,S-side:0.240,…` |
| `dof_audit._determinable_masses` | salidas keyed-only NO determinables | keyed cuenta igual que posicional |

Fuente única nueva: `flowsheet_solver.effective_split_fractions(fs, block)` —
el mismo criterio keyed-else-posicional que usa el solver. No hay editor de
fracciones en la UI (solo display), así que no existe riesgo de edición
ignorada. El resto de los cambios de la auditoría no necesita UI: los
awareness warnings nuevos ([W-PHYS-NONVOL]) se renderizan genéricamente en
`solver_report`, y el botón Auto-size recoge los sizers nuevos del registry.

---

## BUG 2 — Separador mal configurado rutea al revés en SILENCIO

**Severidad:** robustez / diagnóstico. Un separador (filtro/dryer/cristalizador)
**sin los puertos correctos** (`src_port` = `producto` / `venteo`) rutea los
componentes al lado equivocado sin emitir ningún error ni warning, produciendo
salidas **físicamente imposibles**.

### Síntoma observado

Al construir `salt_crystal` sin los puertos `producto`/`venteo`, el solver
produjo (status = warning, balances OK):

```
S-vapor (fase vapor): sodium chloride = 0.99   ← ¡la sal no se evapora!
S-salt  (producto)  : water = 1.00             ← el "producto sal" es agua
```

El balance de masa cerraba y no hubo error — la nonsense física pasó
inadvertida. Con los puertos correctos, todo se rutea bien.

### Fix aplicado — chequeo `[W-PHYS-NONVOL]` en el audit

Se agregó al audit de consistencia del solver un chequeo de **sanity físico**:
un componente **no-volátil** con fracción > 0.02 en una salida de fase
`vapor`/`gas` dispara `[W-PHYS-NONVOL]`, localizado al bloque/stream.

No-volátil se define de forma **data-driven** (no lista hardcodeada):
- `Tb_C ≥ 700 °C` en el catálogo `components.py` (los sólidos usan la sentinela
  99999; NaCl 1465 y NaOH 1388 también caen acá), **o**
- el componente está declarado en `solid_components` del bloque.

El nombre se normaliza (`espacios → '_'`) para el catálogo. Probado sobre los
42 ejemplos: **0 falsos positivos** (golden intacto, gate 42/42). El warning es
advisory — NO cambia `overall_status`.

Regresión: `tests/test_solver_awareness.py`
(`test_phys_nonvol_detecta_solido_en_vapor` y
`test_phys_nonvol_no_falso_positivo_agua_en_vapor`).

---

---

## BUG 3 — Ciclón gas/sólido: mal-etiqueta las fases de salida

**Severidad:** correctitud. `_sep_by_phase` fijaba las etiquetas de fase de las
salidas a `liquid` para cualquier `target_phase != gas`. En un ciclón gas/sólido
(feed GAS) eso dejaba el **gas limpio etiquetado `liquid`** y el **polvo sólido
etiquetado `liquid`** — físicamente absurdo y con Cp equivocado aguas abajo.

### Fix aplicado

`_sep_by_phase` ahora deriva la fase del carrier del **feed**: si el feed es
gas (ciclón), el reject queda `gas` y el target `solid`; si el feed es líquido
(filtro/centrífuga) el comportamiento previo se mantiene intacto (reject/target
`liquid`) → **ningún golden existente cambia** (0/42 usan mech_sep con feed gas).

## BUG 4 — Ciclón sin sizer → costo cero

**Severidad:** costeo. `Cyclone — gas/solid` no tenía sizer (ni por eq_type ni
por categoría "Solids / sep."), así que un ciclón desbloqueado quedaba en `S=0`
→ CBM nulo (mismo patrón que el evaporador/filtro antes de cerrar la deuda de
auto-sizing).

### Fix aplicado

Nuevo `size_cyclone` (S = caudal volumétrico de gas en m³/s, densidad por gas
ideal P·M/RT) registrado en `SIZER_BY_EQTYPE`. El ciclón del ejemplo `cyclone`
ahora dimensiona S≈1.0 m³/s y se costea. Regresión:
`tests/test_costing_honesto.py::test_cyclone_fases_gas_solido_y_costeado`.

---

## BUG 5 — Mixers/splitters standalone sin sizer → costo cero

**Severidad:** costeo. La categoría `Mixers / splitters` (eq_types
`Splitter — flow divider`, `Mixer — static`, `Mixer — inline`) **sí** tiene
correlación de costo Turton (K1), pero **no tenía sizer** (ni en `SIZER_BY_CAT`
ni en `SIZER_BY_EQTYPE`), así que un mixer/splitter standalone quedaba en `S=0`
→ CBM nulo. Los 42 ejemplos no lo notaban porque modelan el split con
`splitter_active` sobre un **vessel real** (V-101, V-102…), nunca un bloque
`Splitter — flow divider` suelto.

### Fix aplicado

Nuevo `size_mixer_splitter` (despacha por `S_param`: `Flow`→kg/s del feed;
`Volume`→Q·τ con τ de mezclador) registrado en
`SIZER_BY_CAT["Mixers / splitters"]`. Los ejemplos `bypass`/`parallel` ahora
costean su splitter/mixer. 0/42 ejemplos existentes afectados (ninguno usa
bloques de esa categoría).

**Nota de autoría (no es bug):** un mixer con la T de salida SIN lockear queda
en T_ref y arrastra un duty espurio — lo detecta `[W-MIXER-DUTY]`. Es el modelo
sudoku pidiendo la spec: se declara la T de salida (adiabática) lockeada, como
en el resto de ejemplos.

---

## BUG 6 y BUG 7 — Más equipos con costo pero sin sizer → costo cero

Misma clase que BUG 4/5 (correlación de costo Turton presente, sizer ausente →
`S=0` → CBM nulo), destapados por los ejemplos `centrifuge` y `cooling`:

- **BUG 6** — `Centrifuge — disc stack` / `Centrifuge — decanter` (categoría
  `Solids / sep.`, S=Volume o Flow) sin sizer. → `size_centrifuge` (despacha por
  `S_param`: Volume→Q·τ del bowl, Flow→m³/h).
- **BUG 7** — `Cooling tower — induced draft` / `natural draft` (categoría
  `Utilities`, S=Cooling duty MW) sin sizer. → `size_cooling_tower` (S=|duty|/
  1000 MW; si no hay duty lo estima del ΔT del agua, Cp≈4.18).

0/46 ejemplos existentes afectados (ninguno usaba esos equipos). Regresión:
`tests/test_costing_honesto.py::test_centrifuge_y_cooling_tower_costeados`.

> **Patrón transversal (BUG 4–10):** varios eq_types del catálogo tienen
> K1/K2/K3 de costo pero no estaban conectados a ningún sizer, así que un bloque
> de esos tipos usado *standalone* costeaba cero en silencio.

### Auditoría sistemática del catálogo (cierre del patrón)

En vez de descubrir los huecos uno por uno, se auditó **todo** el catálogo
cruzando `EQUIPMENT_DATA` (tiene costo) contra `SIZER_BY_CAT`/`SIZER_BY_EQTYPE`
(tiene sizer). Huecos encontrados y cerrados:

| Categoría / eq_type | Bug | Sizer nuevo |
|---|---|---|
| `Cyclone — gas/solid` | 4 | `size_cyclone` (m³/s gas) |
| `Mixers / splitters` | 5 | `size_mixer_splitter` (Flow/Volume) |
| `Centrifuge — disc stack/decanter` | 6 | `size_centrifuge` (Volume/Flow) |
| `Cooling tower — induced/natural` | 7 | `size_cooling_tower` (MW) |
| `Fans / blowers` | 8 | `size_fan` (m³/s gas) |
| `Boiler — fire/water tube` | 9 | `size_boiler_steam` (kg/s vapor) |
| `Valves` | 10 | `size_valve` (m³/h) |

**Único hueco restante (documentado, no cerrado):** `Trays / packing`
(`Tray — sieve/valve`, `Packing — random/structured`). Son **internos de
columna**, no equipos standalone — su costo se contabiliza dentro del shell de
la torre. Quedan sin sizer a propósito (usarlos como bloque suelto es atípico).

**Refinamiento de convención:** los `Fan`/`Blower` se reconocen ahora como
impulsores válidos de un **feed gaseoso** (tiro forzado = trabajo que fija la P
de llegada, igual que un compresor) — antes la convención solo aceptaba
`Compressor` (`tests/test_examples_start.py`, `_MOVEDORES_GAS`).

---

## BUG 11 — Multitear: convergencia FALSA con estado final desbalanceado

**Severidad:** correctitud del solver (corazón del multitear). Destapado por
`nested_recycle` (2 tears de fases distintas al mismo mixer, con el VF del
flash dependiente de la composición del lazo). Dos defectos compuestos:

### (a) El UPDATE-closure excluía al bloque FUENTE del tear

El guard del closure saltaba **cualquier** bloque que tocara un tear activo
(`proc_ins + proc_outs`). Eso protege al mixer **destino** (donde el tear
transitorio en 0 es un sentinel), pero también bloqueaba al **fuente**
pass-through: el compresor de reciclo C-101 quedaba con su salida-tear stale
(`in=9353 / out=63983`, 6.8×) y las rondas declaraban "no hay más trabajo".
G(x) devolvía el valor viejo → el "punto fijo" de G ni siquiera era físico
(purga+producto = 63 016 con feed = 20 000).

**Fix:** el guard ahora solo excluye tears en las **entradas** (`proc_ins`).
Re-derivar la salida-tear stale en su fuente es la "producción forward honesta"
que el propio diseño del tearing sanciona. En fase (c) los tears están LOCKED →
`_is_mass_locked` los protege igual que antes (S2-B intacto).

### (b) Broyden declaraba converged=True con un residuo transitorio

G depende también del estado de **composición** (el VF del flash usa la
composición de la ronda anterior) → G no es estacionaria y un residuo chico
puede ser un artefacto. Broyden aceptaba el primer `|G(x)−x| < tol` y la pasada
final de fijado producía un estado lejos del punto fijo (R-101 con Δ=49%,
`status=error` pero `converged=True` — contradictorio).

**Fix:** VERIFICACIÓN de estacionariedad — se exigen **dos residuos
consecutivos** chicos antes de declarar convergencia; si el segundo regresa
grande, se sigue iterando (nunca un "converged" falso). Más un **polish** de
sustitución post-convergencia (hasta 6 pasadas x←G(x), corte en tol/10).

### (c) Las salidas del flash quedaban un paso de composición atrás

Dentro de cada ronda del forward-pass, el orden era `flash → … →
auto_propagate_compositions`: el flash computaba su split con la composición
del feed de la ronda ANTERIOR, y el ratchet elemental (`test_element_balance`)
lo detectó — 1.45 % de C no conservado en V-101 (metanol: entra 31 436, sale
30 979). Re-correr `solve_flashes` sobre el estado final cerraba exacto
(Δ=0.0) → era orden de última escritura, no el modelo VLE.

**Fix:** reordenar la ronda — `auto_propagate_compositions` PRIMERO, unit-ops
después, cierre de masa al final. La ronda que rompe el loop (sin más trabajo
de masa) deja flash/separadores consistentes con la composición final; en un
punto estacionario es equivalente (goldens existentes intactos).

### Resultado

`nested_recycle` ahora converge de verdad en ~5 iteraciones Broyden (la
aceleración cuasi-Newton real, una vez que G es consistente), con balance
global cerrado (Δ=0.005 %), **elemental-limpio** (ratchet C/H/O verde) y
VF≈0.53 en el punto fijo físico (el lazo enriquece metanol hasta que
purga+producto igualan al feed — sensato).

Regresión: `tests/test_multitear_broyden.py::test_nested_recycle_converge_con_estado_consistente`
(consistencia por bloque + balance global) + el ratchet elemental existente.
Los 29 tests previos de multitear/tearing (S2-B/C/D, anchor, Broyden,
Wegstein vectorial) pasan intactos y el gate 55/55 no movió ningún golden
existente.

---

## BUG 12 — Splitter multi-entrada: distribuía solo la PRIMERA entrada

**Severidad:** correctitud. `solve_splitters` tomaba `feed = next(ins con
masa)` y repartía `feed.mass_flow · frac` — **ignorando las demás entradas**.
El path del splitter durante el tearing y el audit `[W-SPLIT-LOCK]` ya usaban
la SUMA de entradas: tres rutas inconsistentes entre sí.

### Síntoma observado (cw_loop)

Torre de enfriamiento con dos entradas (retorno 100 000 + makeup 3 000):
evaporación salía 1 747.6 (diseño 1 800) y blowdown 1 165.0 (diseño 1 200) —
el splitter repartió solo el retorno. Los 87.4 t/a de descuadre quedaban
ESCONDIDOS como desbalance del HX aguas arriba (0.05 %, bajo la tolerancia),
así que ningún error saltaba.

### Fix aplicado

`solve_splitters` distribuye la **suma de todas las entradas** (idéntico para
1 entrada → los 12 splitters de los ejemplos existentes no cambian, gate
verde). Las tres rutas quedan alineadas.

Regresión: `tests/test_splitter_tearing.py::test_splitter_multientrada_distribuye_la_suma`
(valores de diseño exactos + balance por bloque a <1 t/a).

---

## BUG 13 — Generador AUTO: 89/567 combustiones desbalanceadas átomo a átomo

**Severidad:** correctitud (datos). Encontrado en el Frente 5 de la auditoría
de frontend (acople del predictor chemfx) al escribir el test de balance
atómico del cache `auto_reactions_db.md`. Dos defectos independientes en
`chemfx/auto_reactions/`:

1. **Heteroátomos no manejados**: `generate()` parsea TODOS los elementos de
   la fórmula pero la estequiometría solo balancea C/H/O/N/S. Un compuesto
   clorado producía basura: `2 C2H3Cl3 + 5 O2 → 4 CO2 + 3 H2O` (pierde 6 Cl,
   sobra 1 O). La variante incompleta ni siquiera maneja N/S (el N de
   acetonitrilo desaparecía).
2. **Escala ×2 insuficiente**: `n_O2 = a + b/4 - c/2 + e` tiene denominador 4;
   con `b` impar el escalado ×2 dejaba `n_O2·2 = 5.5` y el `int()` truncaba a
   5 → O desbalanceado (acetamida, acetonitrilo, anilina...).

### Fix aplicado

- `combustion_complete`: rechaza fórmulas con elementos fuera de C/H/O/N/S;
  escala ∈ {1,2,4} eligiendo el primer factor que deja TODOS los coeficientes
  enteros (+ `round` antes de `int`).
- `combustion_incomplete`: rechaza fórmulas fuera de C/H/O (los compuestos
  N/S conservan solo su combustión completa, que sí los maneja); misma escala.
- Cache regenerado: 567 → **504 reacciones, 0 desbalanceadas**.

Regresión: `tests/test_predictor_acople.py::test_loader_balance_atomico_muestral`.

---

## Acople del predictor (Frente 5) — tres eslabones sin cablear

No son bugs de cálculo sino integración muerta, detectada trazando
predictor → reactions_db → block → solver (plan `PLAN_AUDITORIA_FRONTEND_EQUIPOS.md`):

1. **`include_auto` ignorado**: `predict_reactions()` aceptaba el flag con
   `# noqa: ARG001` y `fa.auto` siempre era `[]` — las 504 combustiones/
   crackings del cache no tenían loader y jamás llegaban al predictor ni al
   diálogo "Sugerir productos". **Fix:** `chemfx/auto_reactions/loader.py`
   (parser del cache, lazy/memoizado, degrada a `[]` sin archivo) +
   `_find_auto_for_feed` (mismo contrato de matching que curated: todos los
   reactantes en el feed, rango T) con ΔH por Hess local sobre thermo_db —
   misma fuente que el resto del sistema. El diálogo ahora ofrece
   curated + auto + predicted.
2. **`ReactivityDock` huérfano**: definido en `chemfx/ui/reactivity_dock_qt.py`
   pero NUNCA instanciado — el menú Vista, el hide inicial y el refresh
   post-solve lo tomaban con `getattr(..., None)` y degradaban a no-op
   silencioso (el badge del canvas sí funcionaba; el dock con navegación y
   sugerencias, no). **Fix:** `_build_reactivity_dock()` en la ventana
   principal (guardado: sin chemfx/Qt no se crea), oculto al arrancar,
   toggle en Vista ▸ "Predictor de reactividad".
3. **ΔH del predictor descartado**: al aceptar una reacción sugerida, el
   diálogo recalcula ΔH por Hess con thermo_db; si una especie no tiene ΔHf
   el ΔH quedaba **0 silencioso** aunque el predictor traía su estimación
   Joback/Benson con incertidumbre. **Fix:** fallback a la estimación del
   predictor con procedencia visible en el badge ("joback ±15"), que muere
   apenas el user edita ΔH a mano.

Verificado: degradado limpio sin rdkit/thermo en TODOS los puntos de acople
(subprocess con import bloqueado); gate 58/58 intacto (anotación ≠ modelo).
Regresión: `tests/test_predictor_acople.py` (10 tests: loader, matching por
feed, rango T, ΔH Hess ≈ −802 kJ/mol para CH4, include_auto=False, montaje
del dock y refresh con ejemplo real).

---

## Sistema sudoku / DOF (Frente 3) — el audit era ciego a reciclos y a la sobre-especificación

Auditoría de `dof_audit.analyze_flowsheet` sobre los 58 ejemplos + tests de
perturbación (quitar/agregar locks). Tres defectos:

1. **Falsos under-specificados en los 7 ejemplos con reciclo** (hda,
   haber_rec, industrial, feed_effluent, nested_recycle, hen, cw_loop —
   hasta DOF=14 en industrial): `_determinable_masses` propagaba solo
   forward y no sabía que el solver determina los lazos por convergencia
   del tearing. **Fix:** `_recycle_stream_ids` reutiliza el Tarjan del
   solver (`_strongly_connected_components` + `_streams_in_scc`); los
   streams con ambos extremos en un SCC se siembran como determinables con
   status nuevo **"torn"** (visible en el reporte: "Streams de reciclo
   (convergen por tearing): N"). Resultado: **58/58 exactamente
   determinados** (0 DOF, 0 masa indeterminable).
2. **La rama "over" era código muerto**: los tres `*_dof` eran siempre ≥0,
   así que `total_dof < 0` era inalcanzable — agregar un lock conflictivo
   NO se detectaba jamás. **Fix:** un bloque con TODOS sus streams
   lockeados cuyo balance no cierra (>1 %) es conflicto entre locks
   (`mass_dof = -1`). El patrón sancionado de los ejemplos (locks que
   cierran por diseño) no se flagea — verificado en los 58.
3. **Veredicto por total en vez de por contadores**: un under y un over
   simultáneos cancelaban `total_dof` a 0 → "BIEN ESPECIFICADO"; y total 0
   con masa indeterminable caía por descarte en la rama "OVER". **Fix:**
   summary y diálogo DOF deciden por `n_under`/`n_over`/indeterminables
   (nuevo estado "mixto (sub + sobre)").

Regresión: `tests/test_dof_audit_sudoku.py` (15 tests: 58/58 exactos,
reciclos torn, quitar lock → under en soap/distillation/methanol, quitar
todos → under masivo, lock ×2 en sugar R-102 → over, sin falsos over).

---

## Estado

| Hallazgo | Estado |
|---|---|
| 17 ejemplos nuevos (`salt_crystal`…`cw_loop`) | AGREGADOS al set (gate 58/58) |
| BUG 1 — splitter mapea fracciones por posición | **CORREGIDO** — `split_fraction` keyed + 5 ejemplos migrados |
| BUG 2 — separador rutea al revés sin warning | **CORREGIDO** — `[W-PHYS-NONVOL]` en el audit |
| BUG 3 — ciclón mal-etiqueta fases de salida | **CORREGIDO** — fase del carrier desde el feed |
| BUG 4 — ciclón sin sizer → costo cero | **CORREGIDO** — `size_cyclone` (m³/s gas) |
| BUG 5 — mixers/splitters standalone sin sizer → costo cero | **CORREGIDO** — `size_mixer_splitter` |
| BUG 6 — centrífuga sin sizer → costo cero | **CORREGIDO** — `size_centrifuge` |
| BUG 7 — cooling tower sin sizer → costo cero | **CORREGIDO** — `size_cooling_tower` |
| BUG 8 — fan/blower sin sizer → costo cero | **CORREGIDO** — `size_fan` |
| BUG 9 — caldera piro/acuotubular sin sizer → costo cero | **CORREGIDO** — `size_boiler_steam` |
| BUG 10 — válvulas sin sizer → costo cero | **CORREGIDO** — `size_valve` |
| BUG 11 — multitear: convergencia falsa (fuente stale + G no-estacionaria) | **CORREGIDO** — closure fuente-del-tear + verificación de estacionariedad |
| BUG 12 — splitter multi-entrada reparte solo la primera entrada | **CORREGIDO** — suma de entradas (3 rutas alineadas) |
| BUG 13 — generador AUTO: 89/567 combustiones desbalanceadas | **CORREGIDO** — heteroátomos rechazados + escala {1,2,4}; cache 504/0 |
| Acople predictor — include_auto ignorado / dock huérfano / ΔH descartado | **CORREGIDO** — loader + dock montado + fallback con procedencia |
| DOF audit — ciego a reciclos (7 falsos under) / rama over muerta / veredicto por total | **CORREGIDO** — status torn vía SCC + conflicto entre locks + veredicto por contadores |

Los 12 bugs quedaron corregidos con reproducción mínima y regresión. Los fixes
son aditivos y backward-compatible (goldens existentes intactos, gate 58/58,
534 tests de lógica verdes). Método: "agregar al set + gate" — se agregaron 17
ejemplos limpios (equipos poco usados + topologías raras) y los defectos que
destaparon se corrigieron en el mismo ciclo. La auditoría sistemática del
catálogo cerró **toda** la clase de huecos de sizing salvo los internos de
columna (trays/packing), documentados como excepción deliberada.
