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

### Fix recomendado (cambio de modelo, no aplicado aún)

Mapear las fracciones a las salidas por **identidad estable**, no por posición.
Opciones:
1. `splitter_fractions` como dict `{nombre_o_id_de_salida: fracción}` en vez de
   lista posicional (requiere migrar los ejemplos con splitter: haber_rec,
   hno3, industrial, quimpac, talara).
2. Un campo `split_fraction` por stream de salida.

Un simple ordenamiento por id NO alcanza: al reemplazar una salida por un stream
insertado, el conjunto de salidas cambia de identidad. Hay que anclar la
fracción a la salida.

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

### Fix recomendado (no aplicado aún)

Agregar al audit de consistencia del solver un chequeo de **sanity físico**:
- Componente no-volátil (sal, azúcar, clínker, polímero, carbón…) con fracción
  significativa en una corriente de fase `vapor`/`gas` → warning.
- (Ya probado sobre los 41 ejemplos existentes: **0 anomalías** — todos están
  bien configurados; el chequeo protegería ejemplos NUEVOS y ediciones de UI.)

Script de auditoría física usado (corre sobre cualquier ejemplo):
`scratchpad/physcheck.py` — lista no-volátiles + chequea Σx≈1, fracciones ≥0 y
no-volátil-en-vapor.

---

## Estado

| Hallazgo | Estado |
|---|---|
| `salt_crystal` (ejemplo nuevo, solids train) | AGREGADO al set (gate 42/42) |
| BUG 1 — splitter mapea fracciones por posición | DOCUMENTADO (fix = fracciones keyed) |
| BUG 2 — separador rutea al revés sin warning | DOCUMENTADO (fix = sanity físico en el audit) |

Ambos bugs tienen reproducción mínima y fix recomendado; no se aplicaron para
no mezclar hallazgo con cambio de modelo. Son buenos candidatos para el
próximo ciclo.
