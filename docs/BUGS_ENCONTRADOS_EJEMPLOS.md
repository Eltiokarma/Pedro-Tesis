# Bugs encontrados construyendo ejemplos nuevos

**Fecha:** 2026-07-18
**Contexto:** al crear ejemplos nuevos para estresar equipos poco usados y
topologías raras (más el intento de re-insertar day-tanks del PR #133),
aparecieron dos defectos. Se documentan con reproducción mínima.

## Ejemplo nuevo agregado (limpio)

- **`salt_crystal`** — Sal por cristalización: brine (26% NaCl) → cristalizador
  → filtro de banda → dryer → sal seca. Ejercita los 3 equipos de
  "Solids / sep." (cristalizador, filtro, dryer) que antes solo usaba `sugar`.
  Balance cierra (10 000 t → 7 530 t licor madre + 2 470 t sal), físicamente
  sano. Gate 42/42 verde.

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

## Estado

| Hallazgo | Estado |
|---|---|
| `salt_crystal` (ejemplo nuevo, solids train) | AGREGADO al set (gate 42/42) + bomba de alimentación |
| BUG 1 — splitter mapea fracciones por posición | **CORREGIDO** — `split_fraction` keyed + 5 ejemplos migrados |
| BUG 2 — separador rutea al revés sin warning | **CORREGIDO** — `[W-PHYS-NONVOL]` en el audit |

Ambos bugs quedaron corregidos con reproducción mínima y regresión. Los fixes
son aditivos y backward-compatible (golden 42/42 intacto, 524 tests de lógica
verdes).
