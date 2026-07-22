# PLAN — Auditoría a fondo del FRONTEND de cada equipo (próxima sesión)

**Fecha de anotación:** 2026-07-22
**Estado:** EN CURSO — continúa la auditoría de equipos/topologías cerrada en
PRs #134–#137 (17 ejemplos nuevos, 12 bugs corregidos, gate 58/58).

| Frente | Estado |
|---|---|
| 5 — Predictor (acople) | ✅ CERRADO (sesión 2026-07-22): BUG 13 + 3 eslabones cableados, ver `BUGS_ENCONTRADOS_EJEMPLOS.md` |
| 3 — DOF/sudoku | ✅ CERRADO (sesión 2026-07-22): 58/58 exactos, status torn, over-spec detectable, ver `BUGS_ENCONTRADOS_EJEMPLOS.md` |
| 1+1b — Matriz frontend + streams | ✅ AUDITADO (sesión 2026-07-22): matriz + 2 mudos corregidos; backlog de 7 tipos sin evidencia + pills sin estado sudoku, ver `BUGS_ENCONTRADOS_EJEMPLOS.md` |
| 2 — Casos de libro | pendiente |
| 4 — Propiedades Perry | pendiente |

## Prompt original del autor

> Necesitamos auditar a fondo el frontend de cada equipo, incluso las flechas
> (streams). ¿Muestra información completa? ¿Esta información es didáctica?
> ¿El frontend está a la altura? Si corremos ejercicios del libro, ¿nos
> mostrará buena data verificable con los solucionarios? ¿El sistema sudoku,
> grados de libertad se cumple? Las mezclas de componentes, ¿tienen
> propiedades verificables? ¿Necesitamos más tablas del manual de Perry?
> Por otro lado, el predictor de reacciones: ¿cómo le va? Hay que acoplarlo
> bien al software restante.

---

## Frente 1 — Frontend por equipo (matriz de auditoría)

Para CADA eq_type del catálogo (≈60 tipos en `equipment_costs.EQUIPMENT_DATA`),
auditar en la UI real (inspector + canvas + tooltips):

| Pregunta | Criterio de aprobación |
|---|---|
| ¿Muestra información COMPLETA? | Todos los campos que el solver usa/produce para ese equipo son visibles (S, duty, T/P efectivas, η, ΔP, specs de unit-op, sizing, costo CBM, warnings propios) |
| ¿La información es DIDÁCTICA? | Unidades explícitas, procedencia del número (declarado/calculado/heurística), fórmula o referencia visible donde aplique (estilo `inspector_evidence` con "evidencia") |
| ¿El frontend está A LA ALTURA? | El glyph del canvas es reconocible (norma PFD), los puertos tienen nombre claro, el inspector no muestra secciones vacías ni campos irrelevantes para el tipo |

Método sugerido (headless-compatible):
1. Generar por script la lista de secciones de evidencia que `block_inspector`
   +`inspector_evidence` producen para un bloque de cada eq_type (los 58
   ejemplos ya cubren la mayoría de tipos; para los que falten, mini-fixtures).
2. Flag: eq_type sin NINGUNA sección de evidencia → hueco didáctico.
3. Revisar `equipment_ports` (nombres de puertos) y `editor_chrome`/glyphs
   contra la simbología PFD (los 30 tipos "nunca usados" son los sospechosos).

### Sub-frente 1b — Las FLECHAS (streams)
- Tooltip/pill del stream: ¿muestra mass_flow, T, P, fase, composición,
  role, locks (sudoku), split_fraction si aplica?
- ¿Distingue visualmente declarado (locked) vs calculado (solver)?
- ¿La dirección/routing es legible en topologías densas (reciclos, HEN)?
- Revisar `test_stream_orthogonality` (hoy falla por entorno GUI, no por
  lógica — verificar en entorno con display).

## Frente 2 — Ejercicios de libro verificables con solucionario

Objetivo: correr problemas CONOCIDOS y comparar contra el solucionario.
Candidatos (elegir 5–8, uno por clase de equipo):
- **Turton** (Analysis, Synthesis and Design): costeo CBM de bomba/HX/torre
  (apéndice A) — ya es la fuente de `equipment_costs`, verificar dígito a dígito.
- **Smith, Van Ness & Abbott**: flash isotérmico binario (vs `nrtl.flash_TP`).
- **McCabe/Seader**: columna binaria FUG (N, R_min) vs `distillation_fug`.
- **Felder & Rousseau**: balances de masa con reciclo y purga (vs solver).
- **GPSA/Perry**: bomba (head/potencia), compresor (T descarga politrópica).
- Formato: cada caso = mini-ejemplo JSON + test que asserta el valor del
  solucionario con tolerancia citada + nota en docs de dónde sale el número.
- **Entregable:** `docs/CASOS_LIBRO.md` + `tests/test_casos_libro.py`.

## Frente 3 — Sistema sudoku / grados de libertad

- `dof_audit.analyze_flowsheet` sobre los 58 ejemplos: ¿todos quedan
  exactamente determinados (0 DOF libres, 0 sobre-especificados)?
- Perturbación: quitar un lock → ¿el DOF audit lo detecta como bajo-spec?
  Agregar un lock redundante → ¿detecta el conflicto (sobre-spec)?
- ¿La UI COMUNICA el estado sudoku por stream (locked vs derivado) de forma
  visible y didáctica? (pills, colores, tooltip).
- El caso keyed split_fraction ya quedó cubierto (commit 7d69f7f).

## Frente 4 — Propiedades de mezclas verificables (¿más tablas de Perry?)

- Inventario de propiedades hoy: `components.py` (Cp, Tb, ΔHvap, MW, ρ?),
  `thermo_db` (Antoine, Tc/Pc/ω), `nrtl` (pares binarios).
- Verificar mezclas de los 58 ejemplos: Cp de mezcla, ρ de mezcla, ΔHvap
  ponderado vs valores de Perry (cap. 2) / NIST para 5–10 mezclas típicas
  (brine, jugo de caña, gas de síntesis, aire húmedo, crudo liviano).
- Huecos conocidos a evaluar:
  - ρ líquida por componente (hoy default 800 kg/m³ en sizing — ¿tabla?)
  - Viscosidad (para ΔP de tubería Darcy-Weisbach — hoy ¿fija?)
  - Conductividad/Prandtl (para U de HX más honesto)
  - Antoine faltantes (los no-volátiles usan sentinela — OK deliberado)
- Decisión a tomar: ¿agregar tablas Perry (cap. 2: Cp(T) polinomios, ρ(T),
  μ(T)) como `perry_tables.py` con procedencia por tabla, o basta con lo
  que hay para el alcance de la tesis? Documentar el criterio.

## Frente 5 — Predictor de reacciones (chemfx): estado y acople

**Estado encontrado (recon 2026-07-22):**
- Vive en `chemfx/`: `predictor/` (reaction_predictor con RDKit/SMILES,
  thermo_estimator Joback, plausibility_filter, confidence_tagger),
  `reactivity_engine/` (equipment_reactivity, stream_kinetics,
  danger_detector, assistant), `auto_reactions/` (combustión completa/
  incompleta, cracking térmico, generator), `ui/reactivity_dock_qt.py`.
- Tests: `tests/test_predictor_e2e.py` → **9/9 verdes**.
- Acople actual con el resto del software (3 puntos):
  1. `flowsheet_qt` ~2015: diálogo "predecir productos" → llama
     `chemfx.predictor.reaction_predictor.predict_reactions` (requiere
     rdkit+thermo instalados; si no, mensaje de no-disponible).
  2. `flowsheet_qt` ~7369: `chemfx.analyze_flowsheet(fs)` como ANOTACIÓN
     (no toca el balance).
  3. `reactions_db` capa 4b: procedencia/confianza de reacciones 'auto'
     generadas por `chemfx.auto_reactions`.

**Auditoría de acople pendiente:**
- ¿Las reacciones predichas fluyen hasta `Block.reactions`/`custom_reactions`
  y el solver las usa, o mueren en la anotación? Trazar el camino completo
  predictor → reactions_db → block → solve_equilibrium_reactors.
- ¿El danger_detector/reactivity_dock aparece en la UI actual o quedó
  huérfano? (verificar que el dock se monta y con qué trigger).
- ¿auto_reactions se dispara al construir ejemplos (p.ej. hornos con
  combustión) o hay que invocarlo a mano?
- ΔH de reacción del thermo_estimator (Joback) vs `heat_of_reaction` del
  bloque: ¿misma fuente o pueden divergir? Unificar procedencia.
- rdkit/thermo como dependencias opcionales: ¿el degradado sin ellas es
  limpio en TODOS los puntos de acople (no solo el diálogo)?
- Gate: los 58 ejemplos NO deben cambiar por acoplar el predictor
  (anotación ≠ modelo, salvo opt-in explícito del user).

## Orden sugerido de ejecución

1. Frente 5 (predictor) — trazado de acople, es lo más acotado.
2. Frente 3 (DOF/sudoku sobre los 58) — script + fixes puntuales.
3. Frente 1 + 1b (matriz frontend por equipo + streams) — el grueso.
4. Frente 2 (casos de libro) — cierra con verificación externa citable.
5. Frente 4 (Perry) — decisión de alcance al final, con datos de 1–2.

**Regla de la casa:** todo cambio pasa por el gate (58/58) + suite (547
tests) + regresión nueva por bug encontrado; los hallazgos se documentan en
`docs/BUGS_ENCONTRADOS_EJEMPLOS.md` con reproducción mínima.
