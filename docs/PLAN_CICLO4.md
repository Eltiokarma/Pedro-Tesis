# PLAN — Ciclo 4 (backlog anotado)

**Fecha de anotación:** 2026-07-22
**Estado:** EJECUTADO (2026-07-23) — la primera tanda cerró **B
completo** y **C.3**; la segunda cerró **C.1 + C.2** y la auditoría
con libros; la tanda de diseño cerró **A completo** y la pasada
formal de streams_table/stream_inspector con el bundle de Design
ciclo 4 (`docs/design_ciclo4/`, implementación en
`REDISENO_CICLO4_2026-07.md`). Regresión en `tests/test_ciclo4.py`
(14 tests) + `tests/test_ciclo4_design.py` (20 tests); bugs 14-16
documentados en `BUGS_ENCONTRADOS_EJEMPLOS.md`.

## Ampliación 4f (bundle ciclo 4, tanda 2) — Balance de átomos en pantalla

✓ CERRADO (2026-07-23): el chequeo de conservación elemental que solo
vivía como el chip «✓ átomos» del header gana **superficie propia** —
`atom_balance_book_spec` (Qt-free) + `AtomBalanceCard` (comparte el
shell de la tabla de libro). Tabla por elemento C/H/O/N/S (Σ IN /
Σ OUT / Δ / cierre) con la **procedencia molecular** de cada átomo
(de qué moléculas viene, IN y OUT, ×n exacto), base átomo-molar,
aplica a reactores. Reusa el motor `audit_examples_components`. Ver
`REDISENO_CICLO4_2026-07.md` §4f.

## A. ⚡ del bundle de Design ciclo 3 — ✓ CERRADO (bundle ciclo 4, 4d)

| Artboard | Pendiente | Resolución (2026-07-23) |
|---|---|---|
| 3a | Sieve vs valve al límite a 22 px | ✓ Cerrado ratificando el bundle: a 22 px el rasgo es textura invisible — no se diferencia en el badge (el glifo 60 px ya distingue) |
| 3a | Mixer — dynamic | ✓ Cerrado: no está en el catálogo → no se dibuja glifo muerto |
| 3b | Procedencia POR COMPONENTE | ✓ Columna sudoku de 14 px en la tabla de Composición del stream_inspector (▪ declarado / ◦ deducido) + hook `_comp_provenance` |
| 3c | Anclaje de nota que sigue al bloque/corriente | ✓ `guide_anchor` (id + offset relativo); la guía sigue al elemento; ◆ accent al seleccionar |
| 3c | Cuadro de revisiones △N en el export | ✓ `Flowsheet.revisions` + bloque formal en el Marco PFD + Vista ▸ "Registrar revisión △N…" |
| 3d | Gradiente térmico en corrientes de PROCESO | ✓ Eje GLOBAL por proyecto (cold_deep → ink_ghost → hot_deep) + banda en la leyenda |

## B. Remanentes ⚡ del ciclo 2 aún vivos

- ✓ **`solver_report.py`** duplicaba una paleta light-only propia (§G.5
  de `AUDITORIA_UI_2.md`) → CERRADO: consume `tokens.TOK` vivo (el
  fallback murió — tokens.py es headless-safe) y las severidades se
  leen en caliente (`_sev()`); mueren también los px sueltos y el
  `color: white`.
- ✓ **`hx_edu.py`** y las **curvas matplotlib** de `inspector_evidence`
  → CERRADO: inspector_evidence quedó en 0 hex (patrón `_tok()` +
  `_style_fig`/`_legend` theme-aware, mismo sistema que econ_figures);
  hx_edu ya estaba tokenizado vía `var(--token)` (auditoría 2 §G.5) —
  se mató su `color:white` y los defaults `#000` de `hx_icons.py`.
- ✓ **`streams_table` / `stream_inspector`**: pasada formal de diseño
  → CERRADO (2026-07-23) con el artboard 4c del bundle ciclo 4:
  escala de celda definitiva (FONT_VALUE + FONT_LABEL — muere el 8pt
  suelto), sudoku de masa en la celda de flujo, path a FONT_LABEL,
  densidades 8/10/13. Ver `REDISENO_CICLO4_2026-07.md`.
- ✓ **Remate post-tanda-1 (2026-07-22): últimos hex + tipografía.**
  Murió la clase "hex suelto en superficie UI" completa: diálogo de
  reacción "estilo iPhone" y diálogo de composición de `flowsheet_qt`
  (9 hex → tokens; el botón + adopta el patrón primario del
  dialog_kit) y los 2 fallbacks de `reactivity_dock_qt` (patrón "sin
  fallback hex"). Tipografía: el popover de `hx_edu` adopta qfont
  (FONT_TITLE/UI/VALUE/HINT), el combo del inspector pasa a FONT_HINT,
  y los micro-tags de tooltips (AUTO/[spec]/puertos) suben de 7-8pt a
  FONT_LABEL. El resto de tamaños numéricos que sobreviven son
  excepciones deliberadas ya anotadas en el código: glifos-ícono
  (✕ + × → ▸ ◆), escala de plano del papel PFD (2g), labels on-canvas
  que zooman con la escena, y micro-tipografía de tarjetas compactas
  (burbujas/pills/celdas — anotadas ahora; se revisan si algún día
  reciben artboard). Regresión: censo hex=0 sobre 21 archivos UI en
  `test_ciclo4.py`.
- ✓ Menores (§G de la auditoría 2) → CERRADOS: el chip leía atributos
  fantasma (`iter_count`/`elapsed_s` — BUG 14) → ahora recibe
  `iterations` + wall-time real, y Ctrl+U resetea el chip tras sus
  solves internos; payback pasa a `spec_ink` (+bold); el fallback
  `#000000` de `inspector_widgets._tok` cae a `TOK["ink"]`.

(La herramienta de anotación y el gradiente térmico, que estaban en
esta lista, se cerraron en el ciclo 3 ✓.)

## C. Del plan de auditoría frontend (fuera de alcance declarado)

- ✓ **Viscosidad μ(T) y conductividad k/Prandtl** (Frente 4,
  `CASOS_LIBRO.md`) → CERRADO (2026-07-22): capa 8 del `.md`
  (`mu_ref`/`k_liq`, patrón `rho_ref` — CRC 97ª @ 25 °C para los 10
  líquidos más usados, kerosene de Perry por ser pseudo-corte);
  μ(T) por Lewis-Squires desde el punto, mezcla de Arrhenius,
  `pressure_drop` consume la capa con fallback a su heurística; k al
  punto (sin pendiente inventada) + `prandtl_liq` → `Pr_process`
  informativo en el diagnóstico del HX. La U de sizing sigue saliendo
  de rangos por servicio (decisión documentada en CASOS_LIBRO §F4).
  Goldens intactos (la hidráulica viva solo corre con tubería
  declarada). Regresión: 5 tests capa 8 en `test_ciclo4.py`.
- ✓ **21 eq_types sin instancia en los 58 ejemplos** → CERRADO
  (2026-07-22) con 3 ejemplos nuevos que instancian los 17 tipos
  standalone (los 4 internos de columna — trays/packing — quedan como
  excepción deliberada: no son bloques de flowsheet):
  · `solvent_rec` — tren de condensación de hexano: condenser
    air-cooled → compresor rotary → condenser shell-tube → spiral
    plate → centrifuge decanter (status warning: el aviso pedagógico
    de cambio de fase, mismo precedente que boiler_ft/ethanol).
  · `reformer_whb` — fired heater reformer → WHB field erected
    (66 t/h de vapor HP) → U-tube.
  · `cw_natural` — torre de tiro natural (con evaporación/purga
    keyed como cw_loop) → splitter → mixer inline → valve 3-way;
    dosificación con pump reciprocating + valve relief; coolers
    double pipe / multiple pipe / flat plate; fan axial.
  Destapó el **BUG 16** (WHB desbloqueado nunca se dimensionaba en
  solve → S=0 y costo colapsado en silencio) — corregido en
  `_size_process_equipment`. Gate 61/61; goldens existentes
  byte-idénticos; cobertura vigilada por regresión
  (`test_cobertura_catalogo_solo_internos_sin_ejemplo`).
- ✓ **Origin-tagging de reacciones custom nacidas del predictor**
  (Frente 5) → CERRADO: el esquema del dict acepta `origin`
  (`user`/`curated`/`auto`/`predicted`, default `user`),
  `estimation_method`, `estimation_uncertainty_kJ_mol`,
  `transformation_id` y las dos confianzas; `CustomReactionDialog`
  registra la procedencia al aceptar una sugerencia y la evidencia del
  reactor distingue "(N del predictor)". Round-trip testeado.

## D. Sugerencia de arranque

1. **B** primero (mecánico, sin decisiones de diseño): solver_report +
   hx_edu/matplotlib + menores §G — muere la última clase de hex
   sueltos.
2. **C.3** (origin-tagging) — chico y cierra procedencia end-to-end.
3. **A** requiere o un mini-prompt de Design (procedencia por
   componente, revisiones △N) o decisión propia acotada (anclaje de
   notas).
4. **C.1/C.2** al final — dependen de si el alcance de la tesis pide
   ΔP/U más honestos o más cobertura de catálogo.

**Regla de la casa:** todo cambio pasa por el gate (58/58) + suite +
regresión nueva por hallazgo; los bugs se documentan en
`BUGS_ENCONTRADOS_EJEMPLOS.md` con reproducción mínima.
