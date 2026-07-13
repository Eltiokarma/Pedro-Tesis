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

14. ✅ **hda_full — inconsistencia estructural del lazo** — RESUELTO en
    sesiones previas (el ítem quedó obsoleto): R-101 corre la química real
    R035 (tolueno+H2→benceno+CH4), existe el makeup de H2 (S-H2-makeup,
    tests test_hda_full_makeup/test_hda_full_reactor) y el ejemplo audita
    0 CRÍTICO / 0 MAYOR en especie Y elemental con mass_errors=0.
    Verificado 2026-07 al re-auditar el catálogo completo.

15. ✅ **industrial — V-201 mal modelado como splitter** — RESUELTO (sesión
    2026-07).  V-201 es ahora un FLASH real (40 °C / 80 bar, patrón V-202):
    el metanol+agua condensan al crudo (89% MeOH) y el gas de reciclo queda
    magro (83% H2, 7% MeOH) — desapareció el carrusel de 113 000 t/a de
    metanol que recirculaba sin salida.  El punto fijo del lazo se iteró por
    fuera (el tearing no aplica fracciones de splitter — ítem 3) y se
    congeló como ANCLA SINTÉTICA (patrón de la campaña): S-recycle
    250 000→280 930.3, S-crude 25 000→21 840.8, fracciones de V-203
    ajustadas exactas (purga 28 159 t/a).  El V-202 aguas abajo quedó sin
    gases que ventear (el HP separator los saca todos) → pasa a tambor de
    producto (vent muerto eliminado, flash off); el destilado de T-201 es
    líquido (condensador total a 80 bar).  Producto: 9 061 → 21 280 t/a de
    metanol crudo (91.5%) — consistente con el CO alimentado.  NPV:
    −67.3M → **+7.36M** (la "no rentabilidad honesta" era el artefacto de
    arreglar V-202 dejando el carrusel); el sanity MACRS≠lineal del gate
    económico vuelve a aplicar por sí solo.  Balance 0/0 especie y
    elemental.

16. ✅ **talara — R-SMR crea H y destruye C** — RESUELTO (sesión 2026-07).
    El tren de hidrógeno tiene ahora su feed de vapor de proceso
    (`C21-steam`, 12 051.5 t/a desde el header TK-STM) y el CH4/CO2
    re-dimensionados por estequiometría exacta CH4+2H2O→CO2+4H2:
    C20-CH4 3 000→5 368.9 t/a, C20b-CO2 300→14 720.4 t/a, manteniendo
    los 2 700 t/a de H2 que consumen los HDT (800/1 500/400 intactos).
    Balance elemental EXACTO (ratchet 40/41); ISBL +0.36% (compresor de
    CH4 re-dimensionado al caudal real).

17. **hno3 — T-401 produce más HNO3 del que sus NOx permiten (elemental
    MAYOR, confinado)**: con los feeds actuales (NOx de R-301 + agua +
    aire de blanqueo), el N reactivo disponible (~52 kmol/a NO+NO2) no
    alcanza para el producto declarado (6 200 t/a @60% = 59 kmol de HNO3
    + colas).  El spec del ejemplo excede el balance atómico: cerrar exige
    re-derivar el tren de absorción completo (conversión de R-301, caudal
    de crudo/colas, y el turboexpansor K-501 aguas abajo).  Emparentado
    con el acople oxidación/absorción documentado en
    docs/hno3_e203_oxidacion_override.md.  Confinado en el ratchet.
