# TRABAJOS FUTUROS — hallazgos de la sesión 2026-06 (glyphs · canvas · solver · evidencia)

Pendientes identificados y deliberadamente NO implementados durante la
integración de las ramas `claude/exciting-cori-h239th` (glyphs ISA),
`claude/canvas-interaction-fixes` (interacción del lienzo),
`claude/solver-service-loops` (lazos de servicio) y
`claude/inspector-evidence-figures` (PR #68, evidencia gráfica).
Cada ítem indica dónde está el código y por qué quedó fuera de alcance.

## Solver

1. ✅ **SCC mixto proceso+aux — tear elige corriente auxiliar** —
   RESUELTO como efecto de §3 (verificado 2026-07): con S2-D y el contrato
   fuente/destino del tear, el multitear (Broyden, 11 tears) converge el
   SCC mixto de hda_full+aux en 12 iteraciones sin warnings espurios.
   Regresión congelada en tests/test_tf_pendientes_menores.py.

2. ✅ **`is_cross_exchange` cuenta corrientes auto_aux** (`flowsheet_solver.py`).
   RESUELTO (sesión 2026-07): el conteo estructural ≥2 in / ≥2 out excluye
   ahora las corrientes `auto_aux` — el lazo CW propio del HX ya no lo
   disfraza de cross-exchange y el falso positivo "E-101: cross-exchange no
   cierra energía (>5%)" en metanol+aux desapareció.  Regresión cubierta en
   `test_service_loops.test_metanol_con_aux_sin_warnings_espurios`.

3. ✅ **`_solve_mass_iteration` no aplica fracciones de splitter** —
   RESUELTO (sesión 2026-07).  El tearing ahora es honesto de punta a punta;
   fueron necesarias CUATRO piezas (los ecos se tapaban entre sí):
   · la ecuación del splitter (out_i = frac_i·Σin) vive también en la
     iteración de masa (mismo mapeo frac→stream que solve_splitters);
   · S2-B en el camino MONO de Wegstein con contrato refinado — el tear se
     PRODUCE en su bloque fuente (forward, necesario cuando la fuente es un
     pass-through como el K-202 de industrial) y NUNCA se deduce en su
     bloque destino (el eco RC2 que devolvía el propio guess);
   · S2-D: dentro del SCC activo no hay deducción backward (la succión del
     compresor de reciclo se rellenaba desde el tear inyectado y rebotaba);
   · UPDATE-closure: un bloque resuelto pero desbalanceado con UNA salida
     libre se re-deriva — las cadenas pass-through aguas abajo del lazo
     quedaban stale con masas de iteraciones intermedias.
   El ancla sintética de industrial (§15) se RETIRÓ: su lazo converge VIVO
   por Wegstein (10 iteraciones, punto fijo ~278 000 t/a) y queda como
   regresión permanente en tests/test_splitter_tearing.py.  Goldens
   regenerados (5 ejemplos con refinamientos ≤0.2 kW + industrial vivo).

4. ✅ **Inferencia de duty en HX standalone** — VERIFICADO RESUELTO
   (2026-07): el caso mínimo (HX aislado, agua 80→40 °C con flujo y Ts
   lockeados) infiere duty=−5.3 kW y el lazo de servicio se dimensiona
   analíticamente (m=2 649 tm/año, sin "m pendiente").  Congelado en
   tests/test_tf_pendientes_menores.py.

## Térmica / HX

5. ✅ **E-103 (metanol): F no computable — sugerencia accionable** —
   RESUELTO parcial (2026-07): el warning del fallback F=0.75 ahora explica
   el dominio (P máximo ≈0.59 por casco 1-2 con R≈1) y sugiere n_shell=N+1
   o contracorriente verdadera.  El cambio de T_range del catálogo de CW
   (35→50 vs 30→45 típico) queda como decisión de catálogo aparte
   (re-validar goldens).

## Lienzo / routing

6. ✅ **Lane offset orden-dependiente** — RESUELTO (2026-07): el re-ruteo
   global va ahora en orden DETERMINISTA por id de stream
   (stream_items_iter ordenado + los dos loops bulk de update_path): los
   lanes dominantes (id menor) rutean primero y la asignación converge a
   un punto fijo estable entre repaints (sin saltos de px entre frames).

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

12. ✅ **X_eq vs T — reacciones sin van't Hoff** — RESUELTO sin tocar el
    .md (2026-07): el parser deriva A/B 2-param (ln K = A + B/T, ΔCp=0)
    desde los ΔH/ΔG a 298 K YA curados con fuentes en cada entrada —
    B=−ΔH/R, A=lnK298−B/298.15 (la misma forma de build_custom_reaction).
    GUARD del invariante del seam: sólo derivan las reacciones con TODAS
    sus especies sourceadas (MW>0) → R026 y R028 habilitadas; las demás
    (polietileno, jabón, cal, urea, MDEA) siguen placeholder honesto
    porque su X_eq no sería resoluble de todos modos.

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

17. ✅ **hno3 — T-401 produce más HNO3 del que sus NOx permiten** —
    RESUELTO (sesión 2026-07).  El tren de absorción se RE-DERIVÓ completo
    con extents exactos de R033 (re-oxidación del NO que la absorción
    regenera) + R034 (3NO2+H2O→2HNO3+NO), manteniendo las specs de diseño
    (ácido 60%, slips de abatement NO=10 / NO2=2.5 t/a, colas con 2.5% O2
    y 2.9% agua):
    · producto A13 6 200→5 707.7 t/a (el alcanzable con el N alimentado);
    · aire de blanqueo 500→3 218.7 t/a — la torre necesita el O2 de la
      re-oxidación (ξ1=14.54 kmol), el aire anterior era 6× chico;
    · agua de absorción 3 000→1 532.9 t/a (la que el balance de agua admite
      con el producto al 60%);
    · colas A14 re-derivadas (14 043.9 t/a) y blanqueador V-501 ajustado
      (vent 91.8, producto final 5 615.9 @61%).
    Balance por especie Y elemental 0/0 → el ratchet elemental queda
    **41/41** (catálogo completo limpio, _KNOWN_DIRTY vacío).
