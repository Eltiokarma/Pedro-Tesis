# TRABAJOS FUTUROS — hallazgos de la sesión 2026-06 (glyphs · canvas · solver · evidencia)

Pendientes identificados y deliberadamente NO implementados durante la
integración de las ramas `claude/exciting-cori-h239th` (glyphs ISA),
`claude/canvas-interaction-fixes` (interacción del lienzo),
`claude/solver-service-loops` (lazos de servicio) y
`claude/inspector-evidence-figures` (PR #68, evidencia gráfica).
Cada ítem indica dónde está el código y por qué quedó fuera de alcance.

## Solver

1. **SCC mixto proceso+aux — tear elige corriente auxiliar** (`flowsheet_solver.py`,
   `_choose_tear` ~4380).  En `hda_full`+aux, Tarjan fusiona el reciclo de
   gas/tolueno con dos lazos CW (comparten HXs) en un SCC de 18 bloques.  Todos
   los DESCONOCIDOS del SCC son corrientes aux (el proceso está declarado),
   pero el criterio conservador mandatado ("solo eximir SCC 100% aux") lo manda
   a Wegstein, que elige `U-aux-1` de tear y falla en 1 iter (igual que antes
   del fix — preexistente).  Mejoras candidatas: (a) `_choose_tear` prefiere
   desconocidos NO-aux; (b) eximir también cuando todos los desconocidos del
   SCC son auto_aux.  Ambas requieren revisar los 41 goldens.

2. ✅ **`is_cross_exchange` cuenta corrientes auto_aux** (`flowsheet_solver.py`).
   RESUELTO (sesión 2026-07): el conteo estructural ≥2 in / ≥2 out excluye
   ahora las corrientes `auto_aux` — el lazo CW propio del HX ya no lo
   disfraza de cross-exchange y el falso positivo "E-101: cross-exchange no
   cierra energía (>5%)" en metanol+aux desapareció.  Regresión cubierta en
   `test_service_loops.test_metanol_con_aux_sin_warnings_espurios`.

3. **`_solve_mass_iteration` no aplica fracciones de splitter** durante el
   tearing (solo `solve_splitters` corre después, en el loop de unit ops).
   Los reciclos con purga fraccional convergen hoy por caminos indirectos.
   Integrar la distribución del splitter a la iteración de masa haría el
   Wegstein converger a la solución real con menos vueltas.

4. **Inferencia de duty en HX standalone**: con un HX aislado (agua 80→40 °C,
   flujo y T lockeados) el solver no infiere el duty → el lazo de servicio
   reporta "m pendiente (HX sin duty)".  Revisar las condiciones de
   `_infer_duty` para ese caso mínimo (hoy solo se puebla en flowsheets
   completos).

## Térmica / HX

5. **E-103 (metanol): F no computable — límite real del modelo 1-2.**
   Con proceso 60→45 °C y cooling water 35→50 °C (catálogo), R=1 y P=0.6
   exceden la factibilidad de un casco 1-2 (P_max(R=1)≈0.586) → F cae al
   0.75 conservador con warning honesto.  Mejoras: sugerir `n_shell=2` en el
   propio warning, y/o revisar el `T_range` de cooling water del catálogo de
   utilities (35→50; lo típico es 30→45 [típico], que haría F computable ≈0.9).
   Cambio de catálogo = re-validar goldens.

## Lienzo / routing

6. **Lane offset orden-dependiente**: `_apply_lane_offset` depende de los
   `_last_pts` vigentes de los demás streams, que evolucionan entre repaints
   (el timer de animación re-rutea) → un path autoruteado puede desplazarse
   unos px entre frames.  No afecta la interacción (el hit-test usa la
   geometría del momento del press), pero explica "saltos" visuales.
   Determinizar el orden de asignación de lanes (p. ej. por id, en una pasada
   global) o cachear lanes por par de streams.

7. **Undo para edición de streams**: el drag de bloques integra el undo_stack
   (`begin_action`/`end_action`); el drag de segmento, el translate de
   flotantes y los waypoint handles no.  Integrarlos para Ctrl+Z consistente.

## Glyphs / paleta

8. **Variantes HX restantes**: shell-tube, U-tube, floating head, double/
   multiple pipe y condenser shell-tube comparten el glyph HX genérico
   (misma familia geométrica — decisión deliberada).  Evaporator usa el flash
   vertical (defendible).  Diferenciarlos solo si el uso pedagógico lo pide.

9. **Equipos futuros (steam trap, strainer, deaerator)**: exigirán entrada en
   `EQ_TYPE_TO_ISA` + glyph (o caerán al fallback honesto SVG/rect neutro).
   `tests/test_glyph_coverage.py` obliga a registrarlos al agregarlos al
   catálogo.

10. **Iconitos del menú "+más" para tipos sin silueta nativa**:
    `EditorPalette._icon_for_eq_type` dibuja rect neutro cuando no hay glyph;
    podría reusar el SVG de pfd_symbols (como hace `IsaGlyphItem`) para que
    el menú muestre el símbolo real.

## Inspector / evidencia

11. **Curvas características de bombas**: descartadas a propósito (no hay
    datos de fabricante en el repo; la evidencia textual es lo honesto).
    Si algún día se cargan curvas H-Q reales al catálogo, `pump_text` es el
    punto de partida.

12. **X_eq vs T — 10 reacciones sin van't Hoff** (R022–R031): hoy producen el
    placeholder honesto con la lista de ids.  Completar A/B en
    `data/reactions_db.md` con fuentes para habilitarlas.

## Balance de masa por componente (auditoría — harness audit_examples_components.py)

13. ✅ **Chequeo elemental C/H/O por bloque** — RESUELTO (sesión 2026-07).
    No hizo falta tocar components.py: thermo_db ya trae `formula` para los
    310 compuestos.  `audit_examples_components.audit_block_elements` reparte
    la masa de cada componente por fracción másica de fórmula y verifica
    conservación de átomos por bloque — TAMBIÉN en reactores con química
    real y placeholders (los átomos se conservan aunque haya reacción).
    Hallazgos de estreno: air_sep V-101 (secador que creaba agua de aire
    seco → humedad 0.5% declarada en el feed) y hno3 R-301 (composición
    redondeada a mano → recomputada exacta).  Ratchet en
    `tests/test_element_balance.py`: 39/41 elemental-limpios; los 2
    estructurales quedan confinados y documentados (ítems 16–17).

14. **hda_full — inconsistencia ESTRUCTURAL del lazo (no resoluble por
    composición)**: el ejemplo quedó PARCIALMENTE corregido (F-101 ya no
    transmuta tolueno; T-103 sin el `atmospheric_residue` fantasma), pero
    T-102/V-101/T-101 siguen con desbalance porque la raíz está en la salida
    del reactor R-101 (excluido del chequeo por su química): S27 declara
    benzene=0.78 (68.640 t/a), MÁS benceno del que el tolueno fresco (60.000
    t/a → ~50.870 t/a de benceno por estequiometría 78/92) puede producir.
    Además el lazo fuerza un reciclo de 20.000 t/a (para alimentar 80.000 al
    reactor) cuando sólo ~11.440 t/a de tolueno quedan sin reaccionar, y NO hay
    corriente de H2 de reposición (la HDA consume H2). Con todas las
    composiciones lockeadas y ancladas (S25 tolueno puro, S41=21.400, S44=
    20.000), el exceso de benceno (~10.000 t/a) no tiene salida física. Fix
    correcto (fuera del scope "recomputar composiciones"): corregir S27 a la
    producción real de benceno y re-dimensionar reciclo + agregar makeup de H2.
    Por eso hda_full NO entra a la whitelist del ratchet todavía.

15. **industrial — V-201 mal modelado como splitter (no separador)**: el flash
    V-201 reparte el efluente del reactor en "crudo" (25.000 t/a) y "vapor de
    reciclo" (275.000 t/a) con la MISMA composición (41% metanol cada uno) — es
    un splitter de flujo, no una separación. El metanol (no-volátil relativo)
    debería condensar al líquido (crudo grande), pero la masa del crudo está
    lockeada en 25.000, demasiado chica para los ~124.000 t/a de metanol. Como
    consecuencia el producto final (V-202) recibe sólo ~10.257 t/a de metanol
    (el resto recircula sin converger a steady state, igual que hda_full).
    Un balance correcto de V-202 (que NO cree metanol) reduce el producto de
    20.154 a ~10.086 t/a → el ejemplo se vuelve no rentable (NPV << 0) y rompe
    gate_economics_panel (que lo usa como caso rentable). Fix correcto (fuera del
    scope "recomputar composiciones por bloque"): re-derivar V-201 como
    separador real (crudo ≈ metanol+agua condensados, vapor = gases ligeros) y
    converger el reciclo. Por eso industrial NO entra a la whitelist todavía.
    El chequeo de balance lo sigue reportando en el baseline (2 CRÍTICO en V-202).

16. **talara — R-SMR crea H y destruye C (elemental CRÍTICO, confinado)**:
    el tren de hidrógeno declara 2 700 t/a de H2 + 300 de CO2 desde 3 000 t/a
    de CH4 SIN alimentación de vapor.  Imposible atómicamente: 3 000 t/a de
    CH4 rinden a lo sumo ~1 508 t/a de H2 (CH4+2H2O→CO2+4H2) y producirían
    ~8 231 t/a de CO2 consumiendo ~6 739 t/a de steam.  Fix correcto:
    agregar el feed de vapor y RE-DIMENSIONAR el tren (CH4 5 372 t/a para
    sostener los 2 700 de H2 que consumen los HDT aguas abajo, CO2 14 738)
    — cirugía mayor en un ejemplo de 48 bloques (compresor, OPEX, golden).
    Detectado por el chequeo elemental (§13); confinado en el ratchet.

17. **hno3 — T-401 produce más HNO3 del que sus NOx permiten (elemental
    MAYOR, confinado)**: con los feeds actuales (NOx de R-301 + agua +
    aire de blanqueo), el N reactivo disponible (~52 kmol/a NO+NO2) no
    alcanza para el producto declarado (6 200 t/a @60% = 59 kmol de HNO3
    + colas).  El spec del ejemplo excede el balance atómico: cerrar exige
    re-derivar el tren de absorción completo (conversión de R-301, caudal
    de crudo/colas, y el turboexpansor K-501 aguas abajo).  Emparentado
    con el acople oxidación/absorción documentado en
    docs/hno3_e203_oxidacion_override.md.  Confinado en el ratchet.
