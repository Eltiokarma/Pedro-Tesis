# Arranque — cosecha lote 4 (sesión con red abierta)

**Contexto para la sesión nueva:** este documento es el punto de partida
de la cosecha del catálogo comercial "Plan 6×". La política de red del
environment ya se abrió, así que ESTA sesión SÍ puede leer los PDFs de
fabricante que las sesiones anteriores no podían (daban CONNECT 403).

## Qué ya está hecho (no rehacer)

- Rama de trabajo: `claude/fichas-tecnicas-equipo-tp1qw5`, alineada con
  la default `claude/understand-document-improve-g8xoM` en el commit que
  contiene toda la iniciativa Fichas Técnicas.
- Catálogo `data/equipos_comerciales.json` con **28 entradas verificadas**
  (esquema v2 + granularidad): Compressor — rotary ×14, Turbine — steam
  ×7, Boiler — fire tube ×3, Heat exch. — flat plate ×3, Pump — positive
  displacement ×1.
- El gate `tests/test_equipos_comerciales.py` valida todo lo que entre.
- El motor de verificación (`datasheet.py`) y la UI (sección Ficha
  técnica del inspector + selector en el diálogo de bloque) ya consumen
  el catálogo — cada entrada nueva aparece en la UI sin tocar código.

## El encargo (leer `docs/BRIEF_CATALOGO_COMERCIAL.md`, sección "PLAN 6×")

Meta: **≥6 opciones por tipo, ≥2 marcas por tipo**, cosechando por SERIE
(un leaflet rinde 4-10 entradas). Objetivo total ~60-80 entradas desde
~15-25 documentos oficiales.

Prioridad sugerida (mayor impacto pedagógico primero):
1. **Pump — centrifugal** (categoría nueva, `punto_de_operacion`) —
   le da selector a ~30 bombas del set de ejemplos. Grundfos NK/NB, KSB
   Etanorm.
2. **Valve — control globe** (categoría nueva) — Samson/Fisher, Kvs por
   tamaño. Aparece en letdown, cw_natural.
3. **Centrifuge — disc stack** — GEA (¡los separadores de leche_gloria
   son GEA reales!).
4. Completar los 5 tipos existentes a ≥6 y ≥2 marcas (Elliott turbinas,
   Viessmann calderas, SWEP/GEA placas, SEEPEX bombas PD — reemplazar la
   NEMO de familia por envolventes por tamaño).
5. Fans, compresor reciprocante (Ariel), torres paquete (Evapco/BAC).

## Reglas duras (el gate las hace cumplir)

- Solo documentos OFICIALES del fabricante (no distribuidores, no
  marketplaces). `fuente` = URL del PDF/página; `fecha_consulta` AAAA-MM-DD.
- `eq_type` EXACTO de `equipment_costs.EQUIPMENT_DATA`.
- XOR: `S` (escalar publicado) O `S_no_publicado` (motivo cerrado:
  configurable / punto_de_operacion / otra_magnitud) — nunca ambos.
- Sin S → `granularidad` (modelo|familia) obligatoria + ≥1 param de
  envolvente. Preferir SIEMPRE envolvente por TAMAÑO (modelo); familia
  solo con nota explicando por qué.
- `S` en la unidad del tipo (`S_unit`). Conversiones de unidad
  documentadas en `notas` (kg/h→kg/s, hp→kW), nunca estimaciones.
- Entre fabricantes equivalentes, preferir el que publica en la unidad
  del repo.

## Flujo por lote

1. Cosechar N entradas nuevas, appendearlas al array `equipos`.
2. `python -m unittest tests.test_equipos_comerciales
   tests.test_equipos_a_pedido tests.test_datasheet
   tests.test_ficha_ejemplos_reales -v` → verde.
   **Los dos últimos NO son opcionales.** El lote 4 los omitió y la
   cosecha rompió 6 tests sin tocar una línea de motor: retirar
   `NETZSCH|NEMO L.Cap` y abrir `Reactor — CSTR (agitado)` invalidó
   fixtures que nombraban esas entradas.  Hoy esos fixtures se resuelven
   en vivo contra el catálogo (`_tipo_sin_catalogo`, `_entrada_familia`,
   `_caso_familia`), pero el gate sigue siendo el que avisa.
   Correrlos **con PySide6 real** (`QT_QPA_PLATFORM=offscreen`): sin Qt,
   los tests de la sección Ficha y del diálogo se SALTAN y una rotura de
   UI pasa inadvertida — así se colaron 2 de los 6.
3. `python tools/preview_catalogo.py` → censo + qué ejemplos ganan
   selector (helper, no toca nada).
4. `python gate_examples.py` → 64/64 (el catálogo no afecta física, pero
   confirma que nada se rompió).
5. Commit en la rama de trabajo. Al terminar la cosecha: PR a main +
   merge main→understand (el patrón de los ciclos anteriores).

## Cierre pedagógico (opcional, alto valor)

Cuando haya ≥6 por tipo: en la sección Ficha técnica, el selector podría
mostrar el rango de la serie ("6 modelos · 30-90 kW") como invitación a
comparar. Eso es un ciclo de UI aparte — anotarlo, no bloquear la cosecha.
