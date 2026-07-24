# Rediseño del frontend — ciclo 4, implementación (julio 2026)

Implementación del paquete de Design "Ciclo 4" (artboards 4a–4f,
`docs/design_ciclo4/ciclo4_tablas_libro_deuda_tabular.html` +
componentes `BookTable.dc.html` / `MetricScene.dc.html` /
`AtomBalance.dc.html`, respuesta a `docs/PROMPT_DESIGN_CICLO4.md`).
Evidencia visual renderizada por el sistema real:
`outputs/design4_booktable_{stoich,flash,wh}_{light,dark}.png`,
`outputs/design4_ns_metriccard_{light,dark}.png` y
`outputs/design4_atombalance_smr_{light,dark}.png`.  Regresión:
`tests/test_ciclo4_design.py` (25 tests) + censo hex ampliado en
`test_ciclo4.py`.  Suite verde · gate 61/61.

## 4a — «Tabla de libro» como componente del sistema

- Nace **`book_table.py`** (`BookTable`): UN componente para las tres
  tablas didácticas, con la anatomía exacta del bundle — kicker con
  dot accent, strip de contexto (`bg_sunk`), grilla pintada con
  columnas MEDIDAS por QFontMetrics (muere el `<pre>` que "bailaba"
  dentro de fuente proporcional — bug 1 resuelto en la raíz), filas
  destacables (ribbon 3 px + pill), fila Σ como footer visual, chips
  de escalares derivados, pill de procedencia sudoku, nota y pie de
  fuente estándar (▤).
- Los datos son specs Qt-free construidos en `inspector_evidence`
  (testeables sin pantalla): **`stoich_book_spec`** (Fogler §3.4),
  **`flash_book_spec`** (estilo ChemSep) y **`wh_stage_book_spec`**
  (estreno: etapa | T | x_LK | y_LK | L | V desde `_wh_result`, en
  kmol/h).  El render monoespaciado `*_text` queda como fallback.
- Decisiones del bundle encarnadas:
  · (A) limitante = pill accent + ribbon de fila · (I) inerte = pill
    `tag_bg/tag_ink` + especie en `ink_mute`.
  · **«Cambio» negativo = tinta neutra + signo + ↓** (`ink_mute`) —
    consumo, NO el rojo semántico (reservado al desbalance).
  · **K_i en el eje frío/cálido existente**: K>1 ↑ `service_hot_deep`
    · K<1 ↓ `service_cold_deep`, solo tinta + glifo (sin fondo).
  · **Procedencia de X = vocabulario sudoku**: ▪ declarada (spec) /
    ◦ alcanzada (solver).
  · **WH: tabla ↔ figura por toggle** (`_profile_toggle` en la sección
    Columna del inspector) — misma fuente de datos, nada se recomputa.
    Solo con Wang-Henke convergido (jamás etiquetamos McCabe como WH).

## 4b — Identidades de selección como métricas ricas

- **`MetricCard` pasa a columna que fluye** (bug 3): el sub es una
  fila propia con word-wrap y la tarjeta CRECE — muere la posición
  absoluta a h−16 que recortaba "Perry fig. 10-32".  Pad 9/12/10/15,
  min-height 58, ribbon intacto.
- Nace **`ClassificationScale`** (barra 9 px de bandas
  `service_cold_pale` / `accent_tint` / `service_hot_pale`, marcador
  2 px `ink` con halo, ticks por banda), parámetro `scale` de la
  MetricCard.
- **N_s** entra como MetricCard `accent` span 2 con la escala
  radial·mixto·axial de Perry 8ª fig. 10-32 y el rodete en el sub.
  **C_v de Crane** como tarjeta `spec` a lo ancho con la ec. 3-16
  citada.  **Caudal de vapor del WHB** (S, la variable de costeo
  Sinnott) como tarjeta `sinnott` span 2 con flag HP.
- **Convivencia alerta ↔ identidad** (la pregunta del prompt): la
  cavitación vive en la banda de encabezado como pill `danger` CON el
  margen ("Riesgo de cavitación · margen −8.19 m") — registro
  semántico; N_s vive en la grilla — registro didáctico.  Registros,
  colores y jerarquías distintos: no compiten.

## 4c — streams_table + stream_inspector · pasada formal

- **Escala de celda definitiva**: valor FONT_VALUE (mono 600) ·
  unidad FONT_LABEL `ink_soft` — muere la clase "8pt suelto" de la
  celda (T·P apilados, flujo, leyenda de composición).  Es la misma
  escala de las cards: no hay "tamaño de celda" aparte.
- **Path** sube de mono 9pt libre a FONT_LABEL mono `ink_mute`;
  flecha glifo-ícono 12 px.
- **Procedencia sudoku en la celda de flujo**: se extiende de
  "solo P" a la MASA — ▪ locked (`spec`) · ◦ derivada (`ink_mute`) ·
  ↻ torn (`phase_2ph`), misma fuente que el DOF audit
  (`_recycle_stream_ids`) y mismos glifos que la burbuja on-canvas.
- **Densidades**: pad vertical de fila 8/10/13 (compact/cozy/comfy)
  desde las preferencias del sistema.

## 4d — Deuda ⚡ del bundle ciclo 3 (bloque A del plan)

- **Procedencia POR componente** → tabla de Composición del
  stream_inspector: columna nueva de 14 px antes del dot de color,
  ▪ declarado / ◦ deducido con tooltip.  Fuente: el lock de la
  corriente (`composition_locked`) + hook fino `_comp_provenance`
  {componente: 'declared'|'derived'} para cuando el solver publique
  el caso mixto.
- **Cuadro de revisiones △N** → `Flowsheet.revisions` (persistido,
  round-trip limpio de JSONs viejos) + bloque formal en el Marco PFD
  (REV | DESCRIPCIÓN | FECHA | POR, columnas 34/1fr/66/44 del spec),
  a la izquierda del cuadro de título, última revisión marcada △ en
  `danger` (la tinta "Revisión △" de la anotación es la que enlaza el
  elemento cambiado a la fila).  El REV del título refleja la última
  letra.  Alta por Vista ▸ "Registrar revisión △N…" (letra
  automática + fecha de hoy).  Pantalla y export (el marco va en
  ambos).
- **Anclaje de notas** → `guide_anchor` en el dict de la anotación:
  `(kind block/stream + id + offset relativo)`, NUNCA coordenada
  absoluta — al mover el bloque la guía se re-dibuja siguiéndolo
  (hook en `_refresh_all_stream_paths`).  El click que fija la guía
  ancla automáticamente si cae sobre un bloque/corriente.  ◆ Ø5
  `accent` en el extremo anclado, visible SOLO con la nota
  seleccionada.  El estilo de la guía del ciclo 3 no cambia.
- **Gradiente térmico en corrientes de PROCESO** → eje acordado:
  **global por proyecto** (T_min/T_max de todas las corrientes de
  proceso), escala lineal `service_cold_deep` → `ink_ghost` (medio
  neutro que lo separa del servicio) → `service_hot_deep`.  Mismo
  mecanismo del ciclo 3 (stops por longitud acumulada, se apaga a
  zoom < 0.6, semáforo con prioridad); el sólido de fallback es el
  color del ROL (el lenguaje del ciclo 2 no se pisa).  Nueva banda
  "T PROCESO · eje global" en la leyenda del Marco PFD (+22 px).
- **Sieve vs valve a 22 px · mixer dynamic** → CERRADOS ratificando
  el criterio del bundle: a 22 px el rasgo es textura invisible (el
  glifo de 60 px ya los distingue); mixer dynamic no está en el
  catálogo (no se dibuja glifo muerto).  Cero trabajo nuevo.

## 4e — Escala de tarjeta compacta on-canvas (oficializada)

- La excepción de `stream_bubbles`/`hx_bubbles` se **ratifica como 4ª
  escala documentada** en `tokens.py`: `COMPACT_VALUE_PX = 9` ·
  `COMPACT_LABEL_PX = 8` · `COMPACT_MIN_PX = 7`.  Regla que la separa
  del sistema tipográfico: *físico fijo → FONT_\**; *escala con la
  escena → compacta on-canvas*.
- **Degradación** (`BUBBLE_COLLAPSE_ZOOM = 0.5`): a zoom < 0.5 la
  burbuja colapsa a solo número + dot de fase
  (`set_zoom_degraded`, aplicado por los managers en
  `_refresh_leaders`).  El estado del user (collapsed, toggles) no se
  toca: al volver el zoom la burbuja se restituye.

## 4f — Balance de átomos en pantalla · conservación elemental

- El motor ya auditaba la conservación de átomos por bloque
  (`audit_examples_components.audit_block_elements`) — hoy solo vivía
  como el chip «✓ átomos» del header.  Se le da **superficie propia**:
  nace **`atom_balance_book_spec`** (spec Qt-free) + **`AtomBalanceCard`**
  (widget que comparte el shell de la tabla de libro: kicker con dot
  `green` y chip ✓/⚠ átomos, strip de contexto, pie de fuente ▤).
- **Tabla por elemento** (C/H/O/N/S): badge `accent_tint`/`accent`,
  nombre + A_E, Σ IN, Σ OUT, Δ (`ink_mute` si cierra <1 % rel,
  `danger` si no) y dot de cierre Ø9 verde/rojo (crítico si
  Δ > 5 % del flujo — mismo umbral del motor).
- **Procedencia molecular**: bajo cada elemento, dos cajas `bg_mute`
  (IN · viene de `spec` / OUT · va a `orange`) con chips
  `fórmula ×n valor` — abre las moléculas de las que viene cada átomo,
  en `_FlowLayout` que envuelve.
- Decisiones del bundle: **base átomo-molar (kmol átomo/h)** — el motor
  cierra en masa (fracción de fórmula n_E·A_E/Σn·A), pero la lectura
  didáctica es en moles de átomo (cuadra con la tabla estequiométrica
  y hace el «×n» exacto; el cierre es equivalente).  **Reactores
  incluidos** (el único chequeo que corre a través de la química —
  donde el balance por especie se saltea).  El chip del header queda
  como resumen colapsado y esta tabla es su expansión (patrón
  chip → tabla, igual que DOF → diálogo).  Sin fórmula parseable el
  elemento no aparece y el bloque cae al balance de masa total (no se
  fabrica un desbalance falso → spec `None`).

## Defectos de las capturas — los 3 del prompt

1. **Columnas que bailan** → resuelto en 4a (la tabla ES un
   componente con columnas medidas, no un `<pre>`).
2. **Barras de balance recortadas** ("00000.0") → `DeltaBar` pasa a
   3 celdas `[label 38+][track flex, min 0][valor auto]`: el valor
   mide su propio ancho con QFontMetrics y NUNCA se recorta; el track
   es lo que colapsa.
3. **Sub de MetricCard recortado** → columna que fluye (4b).

## Divergencias razonadas respecto al bundle

1. **Encabezados en caps solo si son ASCII**: el `text-transform:
   uppercase` del bundle convertiría ν→Ν y θ→Θ ("N/|N_A|") — la
   notación del libro manda sobre la convención tipográfica.
2. **Gradiente de proceso solo cuando el destino cambia la T
   (>1 °C)**: el bundle define el eje pero no el umbral; sin él,
   cualquier ruido térmico pisaría el color de rol del ciclo 2.
3. **La fila REB de la tabla WH muestra la L real** (los fondos B)
   en vez del "—" del mockup — el dato existe y es didáctico; el "—"
   queda para los ceros verdaderos (V del condensador total).
4. **Cuadro △N a la izquierda del cuadro de título** (no debajo de la
   leyenda): la esquina inferior derecha ya apila leyenda + título;
   la convención de plano acepta ambos y así no se solapan.
5. **Procedencia por componente**: la granularidad fina por
   componente hoy deriva del lock de la corriente (todo ▪ o todo ◦);
   el dict `_comp_provenance` queda como contrato para el caso mixto
   cuando el solver lo publique — no se inventa procedencia que el
   motor no rastrea.
6. **AtomBalanceCard como componente hermano** (no una variante de
   BookTable): la fila de elemento + las dos cajas de procedencia
   molecular son una estructura distinta a la grilla genérica, pero
   comparten el shell (kicker/contexto/footer) — "misma familia
   visual" sin forzar un solo widget. Los chips que envuelven usan un
   `_FlowLayout` (patrón estándar de Qt).

## ⚡ Dejado fuera por Design (sin cambios, con su razón)

- Rate-based / Maxwell-Stefan en WH (fuera del alcance de la tesis).
- K_i con fondo tintado (competiría con el ribbon de fila).
- Migrar burbujas a FONT_VALUE/LABEL (rompería la densidad de 50+).
- Sieve/valve · mixer dynamic en badge 22 px (cerrado, ver 4d).
- △N con historial versionado / firmas (el MVP es rev. manual).
- Souders-Brown · k real por composición (mueven goldens → backlog
  de ingeniería con bandera, protocolo rho_ref).
