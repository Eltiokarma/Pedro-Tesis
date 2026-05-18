# Deuda técnica — Ejemplos con flujos hardcoded

> **Origen:** Hallazgo 2 de la auditoría de streams/reactor (2026).
> **Estado:** Infraestructura implementada. Reescritura de ejemplos
> pendiente, ejemplo por ejemplo, con verificación de convergencia.

## El problema

Los 41 builders `_example_*` en `flowsheet_ui.py` declaran todos los
flujos intermedios con valores literales precalculados a mano:

```python
# Recycle: 5000 tm/año (5× feed_fresh — ratio típico industrial)
# to-rx = 6000 tm/año (M-101 mezcla)
self._add_example_stream(rec, mx, "S-recycle", mass_flow=5000, ...)
self._add_example_stream(mx, e1, "S-to-rx",   mass_flow=6000, ...)
```

`_add_example_stream` aplica la heurística:

```python
s.mass_flow_locked = (mass_flow > 0)
```

→ TODOS los streams quedan **lockeados**. El solver no los recalcula,
solo verifica que la aritmética declarada cuadra.

**Consecuencia:** el balance "cierra" porque los números ya venían
cuadrados de antemano. El solver no está **resolviendo el proceso**;
está verificando aritmética pre-hecha.

## La infraestructura (ya implementada)

Tres parámetros opcionales nuevos en `_add_example_stream`:

```python
def _add_example_stream(self, ..., lock_mass=None, lock_T=None, lock_comp=None):
    s.mass_flow_locked = ((mass_flow > 0) if lock_mass is None
                          else bool(lock_mass))
    s.temperature_locked = ((abs(T - 25.0) > 0.01) if lock_T is None
                            else bool(lock_T))
    s.composition_locked = ((bool(composition) or bool(main_component))
                            if lock_comp is None else bool(lock_comp))
```

- `lock_*=None` (default) → heurística legacy (back-compat 100 %).
- `lock_*=bool` → respetar el bool explícito.

Aplicado en los **tres sitios**: `flowsheet_ui.py`, `flowsheet_qt.py`
shim, y `validate_ui.py` delega al primero.

Tests de regresión en `tests/test_example_locks.py` verifican que la
heurística legacy se preserva y que los nuevos params funcionan.

## La deuda técnica

**Reescribir los 41 builders existentes** para lockear SOLO los grados
de libertad reales del problema, dejando que el solver compute todo
lo demás. Esto es lo que el brief llama "el de mayor riesgo de
regresión" y por eso quedó como tarea aparte.

## Regla física para builders nuevos / reescritura

| Tipo de stream | Acción |
|---|---|
| **Feed fresco** (entra al proceso desde TK externo) | `lock_mass=True, lock_comp=True, lock_T=True` |
| **Spec de diseño** (target de pureza, conversión, etc.) | `lock_*` solo en lo que el user declara |
| **Output de producto** (vendible al cliente) | `lock_comp=True` si es spec; mass_flow normalmente calculado |
| **Stream intermedio** (entre dos unit ops) | `mass_flow=0.0` (sin lock); el solver propaga |
| **Output de reactor Modo A** (catalog o custom) | `composition=None` (solver calcula via Keq) |
| **Recycle** | `mass_flow=0.0`; el solver Wegstein converge desde 0 |
| **Vapor / venteo de utility** | `lock_mass=False` (separator/dryer/evap lo calcula) |

## Checklist por ejemplo (regla §2.3 del brief)

Tras reescribir cada builder y antes de hacer commit:

1. ✅ `python -c "import flowsheet_ui as fu, flowsheet_solver as fs; ..."` → `result.success == True`
2. ✅ Flujos calculados ≈ los hardcoded antes (tolerancia 0.5 %). Si difieren mucho:
   - Los números "industriales típicos" del comentario estaban mal → corregir
   - O el modelo no captura algo → documentarlo en el docstring (no maquillarlo)
3. ✅ Ningún stream intermedio quedó `*_locked`
4. ✅ Recycles convergen (Wegstein < 50 iter)
5. ✅ `python validate_ui.py` → 41/41 PASAN sin regresión

## Sugerencia de orden de reescritura (riesgo creciente)

| # | Ejemplo | Por qué primero | Riesgo |
|---|---|---|---|
| 1 | E01 `pasteurizer` | Sin reciclo, lineal | 🟢 Bajo |
| 2 | E22 `water_treatment` | Sin reciclo, separaciones declaradas | 🟢 Bajo |
| 3 | E20 `ethylene_cracking` | R011 Modo A; el solver calcula outlet del reactor | 🟡 Medio |
| 4 | E08 `acetic_acid` | Modo B + 1 reciclo simple | 🟡 Medio |
| 5 | `_example_methanol` legacy | Reciclo + Modo A R005 | 🟠 Alto |
| 6 | `_example_haber_recycle` | El más complejo: SCC + reciclo + Wegstein | 🔴 Alto |
| ... | resto del catálogo | uno por uno | mixto |

## Riesgos conocidos del solver Wegstein

Cuando un stream de recycle pasa de `mass_flow=5000 (locked)` a
`mass_flow=0.0 (unlocked)`, el solver SCC debe converger desde cero:

- **Convergencia rápida** (≤ 10 iter): caso ideal.
- **Convergencia lenta** (50–200 iter): aceptable, marcar `max_iter` en
  el bloque.
- **Divergencia**: típicamente porque hay un loop algebraico singular
  o un tear stream mal elegido. Documentar y volver al lock.

## Referencias

- Brief §2 — auditoría streams + reactor (2026).
- `flowsheet_solver.py` → `_solve_recycle_wegstein`.
- `tests/test_example_locks.py` → patrón de reescritura validado.
