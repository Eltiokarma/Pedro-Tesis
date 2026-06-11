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

2. **`is_cross_exchange` cuenta corrientes auto_aux** (`flowsheet_solver.py:1571`).
   El test estructural ≥2 in / ≥2 out cuenta el lazo CW propio del HX como si
   fuera proceso → falso positivo "E-101: cross-exchange no cierra energía
   (>5%)" en metanol+aux (el "par" es su propia cooling water).  El tratamiento
   final (utility de trim) es correcto; el mensaje es engañoso.  Fix natural:
   excluir auto_aux del conteo estructural.  Auditado en la Tarea B (FASE 1.5);
   no implementado por estar fuera del mandato.

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
