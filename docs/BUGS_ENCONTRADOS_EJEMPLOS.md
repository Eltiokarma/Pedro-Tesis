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

Gate 49/49 verde.

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

> **Patrón transversal (BUG 4–7):** varios eq_types del catálogo tienen K1/K2/K3
> de costo pero no estaban conectados a ningún sizer, así que un bloque de esos
> tipos usado *standalone* costeaba cero en silencio. Se cerraron los 4 huecos
> vistos (ciclón, mixer/splitter, centrífuga, cooling tower). Quedan otros
> eq_types del catálogo aún no ejercitados por ningún ejemplo — candidatos a
> nuevas rondas.

---

## Estado

| Hallazgo | Estado |
|---|---|
| `salt_crystal`/`decanter`/`cyclone`/`bypass`/`parallel`/`centrifuge`/`cooling`/`pfr` | AGREGADOS al set (gate 49/49) |
| BUG 1 — splitter mapea fracciones por posición | **CORREGIDO** — `split_fraction` keyed + 5 ejemplos migrados |
| BUG 2 — separador rutea al revés sin warning | **CORREGIDO** — `[W-PHYS-NONVOL]` en el audit |
| BUG 3 — ciclón mal-etiqueta fases de salida | **CORREGIDO** — fase del carrier desde el feed |
| BUG 4 — ciclón sin sizer → costo cero | **CORREGIDO** — `size_cyclone` (m³/s gas) |
| BUG 5 — mixers/splitters standalone sin sizer → costo cero | **CORREGIDO** — `size_mixer_splitter` |
| BUG 6 — centrífuga sin sizer → costo cero | **CORREGIDO** — `size_centrifuge` |
| BUG 7 — cooling tower sin sizer → costo cero | **CORREGIDO** — `size_cooling_tower` |

Los 7 bugs quedaron corregidos con reproducción mínima y regresión. Los fixes
son aditivos y backward-compatible (goldens existentes intactos, gate 49/49,
531 tests de lógica verdes). Método: "agregar al set + gate" — se agregaron 8
ejemplos limpios (equipos poco usados + topologías raras) y los defectos que
destaparon se corrigieron en el mismo ciclo.
