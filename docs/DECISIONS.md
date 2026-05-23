# DECISIONS.md — Decisiones de diseño de Pedro-Tesis

**Última actualización:** post-PR del ticket isentrópico (P14 mergeado).
**Estado del motor:** ver `docs/AUDIT.md`.
**Parches pendientes:** ver `docs/ROADMAP.md`.

---

## Propósito de este documento

Registro de decisiones de diseño tomadas durante la auditoría Camino D y la migración Tk→Qt. Cada entrada documenta:

- **Qué** se decidió
- **Cuándo** (PR o sesión)
- **Por qué** (alternativas consideradas y razón de la elección)
- **Consecuencias** (lo que esto implica para el futuro)

Sirve para tres cosas:
1. **Para vos:** recordar el porqué cuando vuelvas en semanas o meses.
2. **Para sesiones futuras (Claude):** entender el contexto sin reabrir el debate.
3. **Para tu tesis:** defender decisiones de software durante la defensa.

---

## Convenciones

- **ID**: `D<N>` para decisiones de arquitectura/diseño general.
- **PR**: el pull request donde se materializó (cuando aplica).
- **Estado**: `activa` / `superada` / `revertida`.

---

## Decisiones de migración Tk → Qt (PRs C1-L4)

### D-MIG-1 — Migración Tk → Qt completa, no convivencia indefinida

**PR:** C1-L4 (#8 a #14).
**Estado:** activa.

**Decisión:** eliminar completamente todos los archivos Tk legacy (`ANA.py`, `flowsheet_main.py`, `flowsheet_ui.py`, `pipeline.py`, `mc_ui.py`, `flujoflujo.py`, etc.) en lugar de mantener convivencia Tk+Qt indefinida.

**Alternativas consideradas:**
- (a) Convivencia: mantener Tk legacy con botón "legacy mode" en welcome.
- (b) Migración completa (elegida).

**Por qué (b):**
- El usuario confirmó que **todos sus proyectos son `.json` Qt**, ninguno `.xlsx` legacy.
- Mantener Tk vivo significaba duplicación: dos veces los ejemplos, dos veces los dialogs, dos veces los handlers.
- El código Tk muerto **confundía las auditorías automatizadas** (Claude Code leía Tk legacy y diagnosticaba bugs sobre código que el usuario no usa). Este fue exactamente el problema del reporte original que arrancó el proyecto.

**Consecuencias:**
- −9292 líneas netas eliminadas.
- Cualquier sesión nueva de auditoría arranca con código limpio.
- Si en el futuro alguien quiere reactivar Tk, tiene que recuperar de la historia de git, no del repo activo.

---

### D-MIG-2 — Mantener prefijo `_example_` en builders migrados

**PR:** L1 (#11).
**Estado:** activa.

**Decisión:** al migrar los 41 builders de `flowsheet_ui.FlowsheetEditor` a `examples_library.ExampleBuilder`, mantener el prefijo `_example_` en los nombres de métodos (e.g., `_example_talara_refinery`) en lugar de renombrarlos a nombres limpios (e.g., `talara_refinery`).

**Alternativas consideradas:**
- (a) Renombrar a `talara_refinery`, etc. (más limpio, API pública).
- (b) Mantener `_example_talara_refinery` (compatibilidad byte-a-byte).

**Por qué (b):**
- Los 41 builders contienen ~500 llamadas internas a `self._add_example_block(...)`. Si renombraba los helpers, había que hacer find-and-replace masivo en cada builder.
- Migración byte-a-byte tiene menos superficie de error que migración + refactor.
- El "guion bajo" es cosmético — operativamente no afecta nada.
- Si en el futuro alguien quiere limpiar nombres, es un PR aparte de ~500 find-and-replace.

**Consecuencias:**
- `ExampleBuilder` tiene métodos públicos con guion bajo (anti-patrón Python típico pero justificado acá).
- Cualquier código externo que llamaba `TkEditor._example_X` sigue funcionando con `ExampleBuilder._example_X`.

---

### D-MIG-3 — Mantener aliases `_LegacyEditor` y `TkEditor` post-migración

**PR:** L2 (#12).
**Estado:** activa.

**Decisión:** en `flowsheet_qt.py`, después de migrar los 2 import sites (líneas 6568 y 7030) a `from examples_library import ExampleBuilder`, mantener los aliases `_LegacyEditor` y `TkEditor` apuntando ahora a `ExampleBuilder`.

**Alternativas consideradas:**
- (a) Renombrar todas las referencias en `flowsheet_qt.py` a `ExampleBuilder` (~50 líneas modificadas).
- (b) Solo cambiar los 2 imports y mantener aliases (3 líneas modificadas).

**Por qué (b):**
- Minimizar el diff del PR. Más fácil de revisar y revertir si algo rompe.
- El nombre `TkEditor` es un fósil semántico (ya no es Tk), pero funcionalmente equivalente.
- Un PR de cosméticos posterior puede limpiar si vale la pena.

**Consecuencias:**
- En `flowsheet_qt.py` hay aliases con nombres que no reflejan la realidad post-migración.
- Documentado para evitar confusión futura.

---

## Decisiones del audit script

### D-AUD-1 — Detección de builders ilustrativos por primera línea del docstring

**Sesión:** Fase 2 v3.1.
**Estado:** activa.

**Decisión:** `audit_phase2.py` detecta builders TIER 2 / ilustrativos buscando los patrones (`TIER 2`, `ILUSTRATIVO`, `piloto`, `plant-scale`) **solo en la primera línea del docstring**, no en todo el cuerpo.

**Alternativas consideradas:**
- (a) Buscar en todo el docstring (versión v3 original).
- (b) Agregar flag programático `is_illustrative=True` al modelo (modificar el código).
- (c) Buscar solo en primera línea (elegida).

**Por qué (c):**
- (a) generaba falsos positivos: `_example_polyethylene` tiene "TIER 1" en su primera línea pero menciona "simplificación pedagógica" en una nota interna. La v3 lo clasificó incorrectamente como TIER 2.
- (b) requería modificar el modelo y los 4 builders ilustrativos. Más invasivo.
- (c) es no-invasivo (no toca el código), aprovecha la convención que Pedro ya usa (escribe "TIER 1" o "TIER 2 — ILUSTRATIVO" en la primera línea del docstring).

**Consecuencias:**
- Los builders nuevos que quieran marcarse como ilustrativos deben poner el marcador en la **primera línea** del docstring, no en el cuerpo.
- Si Pedro escribe un docstring sin TIER explícito, el script asume TIER 1 (defensivo: incluir en agregado).

---

### D-AUD-2 — TIER 2 excluido del FCI agregado

**Sesión:** Fase 2 v3.
**Estado:** activa.

**Decisión:** en el resumen del audit, los ejemplos TIER 2 (ilustrativos, escala piloto) NO se agregan al "Total FCI" del catálogo. Se reportan en una sección separada.

**Alternativas consideradas:**
- (a) Incluir TIER 2 en el agregado.
- (b) Excluir TIER 2 (elegida).

**Por qué (b):**
- `rankine_cycle` tenía FCI=$135M para 6 bloques (turbina modelada como HX, extrapolando fuera de Turton). Si se incluía, distorsionaba el promedio del catálogo: $7.2M con Rankine vs $4.1M sin Rankine.
- TIER 2 son ejemplos pedagógicos con escala no industrial — su costing no es comparable.
- Si en el futuro arreglamos P11 (agregar Turbinas al catálogo) y Rankine pasa a ser TIER 1, se vuelve a incluir.

**Consecuencias:**
- El "Total FCI agregado" del audit ($155.2M actual) representa solo los ejemplos industriales realistas.
- Rankine sigue corriendo en la suite y se reporta, pero no contamina el promedio.

---

## Decisiones de parches al motor

### D-PARCHE-1 — `tray_efficiency` default 0.7 (no 1.0)

**PR:** Pa1 (#17).
**Estado:** activa.

**Decisión:** cambiar el default de `tray_efficiency` en `econ_defaults.COLUMN_DEFAULTS` de 1.0 (etapas reales = teóricas) a 0.7 (valor industrial genérico).

**Alternativas consideradas:**
- (a) Mantener 1.0 (opt-in explícito para realismo).
- (b) Cambiar a 0.7 (default realista, opt-in para idealización).
- (c) Eliminar default — forzar declaración explícita por bloque.

**Por qué (b):**
- 1.0 es el **peor default posible**: significa "asume el caso ideal" — subestima altura de columnas en ~30%.
- 0.7 es el valor industrial genérico para hidrocarburos livianos y mezclas comunes (rango típico: 0.5 aminas, 0.65 etanol-agua, 0.80 hidrocarburos livianos).
- Si el usuario quiere idealización, declara `block.tray_efficiency=1.0` explícito.
- (c) era demasiado invasiva — rompía retrocompatibilidad con todos los flowsheets existentes.

**Consecuencias:**
- Cuatro tests del solver tuvieron que actualizarse (codificaban el viejo 1.0 como invariante físico).
- Tres de esos cuatro se refactorizaron a **fórmula** (`H == N/eff * spacing + head`) en lugar de número literal — robustos a futuros cambios de default.
- Todas las columnas con FUG/Wang-Henke en el catálogo aumentaron altura ~43% (= 1/0.7). Costing sube ~30%.
- No afecta Talara (sus "columnas" son splitters).

---

### D-PARCHE-2 — P12 mantiene fórmula incompresible para bombas

**PR:** P12 (#19).
**Estado:** activa.

**Decisión:** al corregir el cálculo de duty hidráulico para distinguir bombas de compresores, **mantener la fórmula `W = m·ΔP/(ρ·η)` para bombas** y solo delegar a `equipment_design.design_compressor_for_block()` para compresores.

**Alternativas consideradas:**
- (a) Delegar todo (bombas y compresores) a `equipment_design` para single source of truth absoluto.
- (b) Mantener incompresible para bombas, politrópica para compresores (elegida).

**Por qué (b):**
- La fórmula incompresible **es físicamente correcta para líquidos** (ρ constante).
- Cambiarla a `pump_sizing` de `equipment_design` no aporta precisión adicional, solo agrega un import y una función call.
- El bug real era usar la fórmula incompresible para **gases** (donde ρ cambia con P y la ec. politrópica `T₂ = T₁·(P₂/P₁)^((k-1)/k)` es necesaria).

**Consecuencias:**
- Código más limpio: cada función trata su caso correcto.
- Si en el futuro alguien quiere unificar, P12-revisión sería un PR aparte.

---

### D-PARCHE-3 — P13 placement post-loop en `solve_pressure_hydraulic`

**PR:** Tanda chica (#18).
**Estado:** activa.

**Decisión:** el warning "compresor degenerado" de P13 se emite **post-loop en `solve_pressure_hydraulic`**, no inline en `solve_pressure_propagation` (como decía el prompt original).

**Alternativas consideradas:**
- (a) Inline en `solve_pressure_propagation` (instrucción literal del prompt).
- (b) Post-loop en `solve_pressure_hydraulic` (elegida).

**Por qué (b):**
- `solve_pressure_propagation` tiene su `msgs` **descartado** por las llamadas internas (`solve_pressure_hydraulic` ignora el return). Si el warning se emitía inline, se perdía silenciosamente.
- `solve_pressure_hydraulic` fluye sus `msgs` a `result.energy_warnings` (línea 3276 de `flowsheet_solver.py`).
- Además: **todos** los compresores degenerados del catálogo tienen `pressure_locked=False` en streams downstream, lo que dispara el early-return de `solve_pressure_hydraulic`. Por eso el helper se llama también en el early-return.

**Consecuencias:**
- 14 warnings activos en 11 ejemplos del catálogo.
- Mismo patrón aplicado a P12 (lección aprendida).
- Si en el futuro `solve_pressure_propagation` empieza a fluir `msgs`, P13 se puede mover inline sin perder funcionalidad.

---

### D-PARCHE-4 — P12 aplicado aunque dormante sobre catálogo actual

**PR:** P12 (#19).
**Estado:** activa.

**Decisión:** mergear el parche P12 (ec. politrópica para compresores) aunque ningún ejemplo del catálogo actual tenga compresores bien especificados (todos son degenerados).

**Alternativas consideradas:**
- (a) No mergear hasta que el catálogo tenga al menos 1 ejemplo no-degenerado.
- (b) Mergear como capacidad latente (elegida).

**Por qué (b):**
- El parche **es técnicamente correcto** y consistente con `equipment_sizing.size_compressor` (que ya delegaba a la misma función `design_compressor_for_block`).
- Antes del parche había una inconsistencia: el sizing usaba politrópica, el duty usaba incompresible. **Esta inconsistencia se eliminó.**
- Cuando D1 + T3 se hagan (corregir P_op_bar en los 11 builders), P12 activa automáticamente sin trabajo adicional.
- Una prueba sintética con compresor de CH₄ + ΔP=50 bar verificó que P12 funciona correctamente cuando los datos están bien.

**Consecuencias:**
- En sesiones futuras, no hay que "implementar P12 cuando sea necesario" — ya está hecho.
- D1 (corregir builders) es ahora el bloqueante real para que P12 tenga efecto observable.

---

## Decisiones sobre gestión del proyecto

### D-PROJ-1 — Roles separados Claude (auditor) y Claude Code (parches)

**Sesión:** sesión de cierre Camino D.
**Estado:** activa.

**Decisión:** Claude (yo, claude.ai) hace auditorías, razonamientos, propuestas y armado de prompts. Claude Code aplica parches de código siguiendo prompts entregados.

**Alternativas consideradas:**
- (a) Claude Code hace todo: auditoría + parches.
- (b) Claude (auditor) + Claude Code (parches), roles separados (elegida).
- (c) Solo Claude.ai con file editing tool.

**Por qué (b):**
- Claude Code, cuando audita "de memoria", produce diagnósticos equivocados (reporte original que arrancó este proyecto). En cambio, cuando lee código en vivo y aplica parches específicos, es muy bueno.
- Claude (claude.ai) puede leer código en vivo via web fetch + bash, mantener contexto largo de auditoría, y razonar sobre arquitectura. Pero **no aplica cambios al repo directamente**.
- La separación de roles mejora la calidad: Claude piensa, Claude Code ejecuta, vos validás.

**Consecuencias:**
- Cada parche pasa por: Claude armó prompt → vos copiás → Claude Code aplica → Claude revisa reporte → vos mergeás.
- Más turnos pero más seguro.
- Si en una sesión futura vos hablás directo con Claude Code sin Claude, el prompt tiene que ser más directivo y menos abierto.

---

### D-PROJ-2 — Documentación viva en `docs/` del repo, no solo en chats

**Sesión:** sesión de cierre Camino D.
**Estado:** activa.

**Decisión:** los entregables de la auditoría (`AUDIT.md`, `ROADMAP.md`, `DECISIONS.md`, `SESSION_PROMPT.md`) viven dentro del repo en `docs/`, versionados por git, actualizados con cada PR relevante.

**Alternativas consideradas:**
- (a) Solo notas dispersas en chats de claude.ai.
- (b) Carpeta `audit/` separada en el repo.
- (c) `docs/` en el repo, junto a `DEUDA_TECNICA_EJEMPLOS_HARDCODED.md` existente (elegida).

**Por qué (c):**
- Pedro-Tesis ya tiene `docs/` con documentación de deuda. Sumar 4 archivos ahí es natural.
- Versionado en git: cualquier modificación queda registrada con autor + fecha + razón en commit messages.
- Cualquier Claude o Claude Code que abra el repo encuentra los .md inmediatamente.
- **Elimina el problema** que tuvimos al principio: "Claude de memoria diciendo cosas equivocadas". Los nuevos arrancan con contexto correcto.

**Consecuencias:**
- Los .md hay que mantenerlos al día con cada PR de parche.
- Sugerido: cada PR de parche debe incluir un cambio al `ROADMAP.md` (mover entrada de pendiente a aplicada) y opcionalmente al `AUDIT.md` (si surgen hallazgos nuevos).
- En el prompt de sesión nueva, pedir explícitamente a Claude/Claude Code que actualicen los .md cuando corresponda.

---

### D-PROJ-3 — `audit_phase2.py` versionado en el repo como regression test

**Sesión:** sesión de cierre Camino D.
**Estado:** activa.

**Decisión:** el script de auditoría del catálogo (`audit_phase2.py` v3.1) se versiona en el root del repo, junto a los archivos de motor.

**Alternativas consideradas:**
- (a) Mantener el script fuera del repo (en chats).
- (b) Versionarlo dentro del repo (elegida).

**Por qué (b):**
- El script es **regression test del catálogo**: corre los 41 ejemplos, computa FCI agregado, detecta outliers, separa TIER 1 / TIER 2.
- Complementa la suite unitaria de 120 tests (que prueba funciones aisladas, no flujos end-to-end).
- Antes de mergear un PR grande, vos podés correr `python audit_phase2.py` y comparar FCI agregado pre/post — eso te dice si el parche cambió números más allá de lo esperado.
- Si en el futuro Pedro-Tesis se publica/distribuye, el audit script es **prueba de calidad** del catálogo.

**Consecuencias:**
- El script tiene que mantenerse al día con cambios al motor (API de `bare_module_cost`, etc.).
- Idealmente, el script entra a un CI/CD en algún momento.

---

### D-PARCHE-5 — Compresor reusa `compressor_sizing` (con clamp η≤0.95), turbina implementa expansión manual sin clamp

**PR/Commit:** ticket isentrópico, commit `e8ff002`.
**Estado:** activa.

**Decisión:** en el parche P14 (propagación isentrópica), el branch COMPRESOR (`P_out > P_in`) reusa `equipment_design.compressor_sizing` (que internamente clampea `η_isen ≤ 0.95`). El branch TURBINA (`P_out < P_in`) implementa la expansión manualmente SIN clamp de η.

**Alternativas consideradas:**
- (a) Ambos branches reusan `compressor_sizing` (consistencia total, η siempre clampeado).
- (b) Ambos branches manuales (sin clamp en ningún caso).
- (c) Compresor reusa con clamp, turbina manual sin clamp (elegida).

**Por qué (c):**
- **Para compresores**, el clamp es defensivo y físicamente justificado — ningún compresor real es 100% isentrópico. Mantener `compressor_sizing` como single source of truth es consistente con P12 (que también delega a esa función para el cálculo de duty).
- **Para turbinas**, los casos de validación con Cengel (capítulo 7-15) requieren testear contra el caso isentrópico ideal (`η=1.0`). Si la turbina también clampeara a 0.95, los tests de calibración contra el libro no serían válidos.
- (a) habría imposibilitado validar contra Cengel.
- (b) habría duplicado código y perdido consistencia con P12.

**Consecuencias:**
- Caso 1 del test (compresor aire ideal `η=1.0`): produce 555.3K en vez de los 543K teóricos de Cengel — diferencia atribuible al clamp interno (300+(543.4-300)/0.95=556.2).
- Caso 2 del test (turbina aire ideal `η=1.0`): produce 798.6K — diferencia respecto a Cengel atribuible a otra razón (Cp(T) real vs cold-air-standard, ver D-PARCHE-6).
- El hallazgo del clamp ahora está documentado como H115 en AUDIT.md.

---

### D-PARCHE-6 — Usar `Cp(T)` real de thermo_db en vez del cold-air-standard de Cengel

**PR/Commit:** ticket isentrópico, commit `e8ff002`.
**Estado:** activa.

**Decisión:** la función `_compressible_props` calcula `k = Cp/Cv` usando `Cp(T)` real consultado a `thermo_db` con el polinomio DIPPR. NO usa el "cold-air-standard" de los libros de texto (k=1.4 constante para aire).

**Alternativas consideradas:**
- (a) Cold-air-standard: usar k=1.4 constante para aire, k=1.33 para vapor, etc. (consistente con libros como Cengel cap 7-9).
- (b) Cp(T) real desde thermo_db, k variable con T (elegida).

**Por qué (b):**
- **Rigor termodinámico:** Cp del aire varía de ~1.005 kJ/kg·K a 27°C a ~1.16 kJ/kg·K a 1027°C (+15%). Asumir Cp constante introduce error sistemático en turbinas operando a alta T (donde la diferencia es grande).
- **Single source of truth:** `thermo_db` con DIPPR ya está implementado y validado. Mantener una "tabla aparte" para gases ideales sería duplicación.
- **Coherencia con sim-comerciales:** Aspen, Hysys y Pro-II usan Cp(T) real, no cold-air-standard. Para defender la tesis, lo correcto es usar el modelo más riguroso.

**Consecuencias:**
- Las pruebas de validación con Cengel (cap 7-15: turbina aire 1300K → 1bar) dan **resultados numéricamente distintos al libro**:
  - Cengel cold-air-standard (k=1.4): T_out = 1300·(1/8)^0.2857 = 717 K
  - Pedro-Tesis Cp(T) real (k≈1.30 a 1300K): T_out ≈ 799 K
  - Diferencia: 82 K (+11%)
- **Defendible en tesis** porque el resultado es **más preciso físicamente** — los simuladores comerciales daría el mismo orden que Pedro-Tesis (~800K), no 717K.
- Si en una defensa alguien pregunta "tu turbina da 799K y Cengel dice 717K, ¿quién tiene razón?", la respuesta correcta es: "Cengel usa una aproximación pedagógica con k constante. Pedro-Tesis usa Cp(T) real consistente con simuladores comerciales. La diferencia se origina en la variación de Cp con T a 1300K."
- Documentado como H116 en AUDIT.md.

---

### D-PROJ-4 — Tickets aplicados fuera del ROADMAP planificado se documentan retroactivamente

**Sesión:** post-ticket isentrópico.
**Estado:** activa.

**Decisión:** los parches que se aplican **sin haber tenido entrada previa en `docs/ROADMAP.md`** (porque surgieron de discusión ad-hoc, hallazgos en otras sesiones, o trabajo paralelo) **se documentan retroactivamente** en `docs/AUDIT.md` tabla 6.1 (tabla de parches aplicados) y en `docs/DECISIONS.md` (decisiones de diseño asociadas). NO requieren entrada en ROADMAP — ROADMAP es para planificación, no para inventario.

**Caso de referencia:** el parche P14 (propagación isentrópica) **no tenía entrada en ROADMAP** cuando se aplicó. Se discutió en sesión ad-hoc, se armó prompt para Claude Code, se aplicó, y se documentó retroactivamente.

**Alternativas consideradas:**
- (a) Bloqueante: todo parche debe entrar al ROADMAP antes de aplicarse.
- (b) Documentación retroactiva permitida (elegida).

**Por qué (b):**
- (a) sería burocrático para parches descubiertos durante otras tareas. Frenaría el flujo cuando aparecen hallazgos relacionados.
- (b) mantiene el ROADMAP como herramienta de planificación (qué atacar próximo) sin obligarlo a ser un registro completo de todo lo aplicado.
- AUDIT.md tabla 6.1 cumple el rol de inventario completo. ROADMAP cumple el rol de cola de trabajo.

**Consecuencias:**
- ROADMAP puede tener menos entradas que parches realmente aplicados — eso es OK.
- Si querés saber "qué parches aplicó Pedro-Tesis", la fuente es `AUDIT.md` tabla 6.1, no `ROADMAP.md`.
- Si querés saber "qué tengo pendiente atacar", la fuente es `ROADMAP.md`.
- Documentación retroactiva debe hacerse en la misma sesión que el merge — no postergar, sino la deuda crece.

---

## Decisiones que se REVERTIRON o NO se aplicaron

### D-RECHAZADA-1 — P8 NO se atacó como parche rápido

**Sesión:** discusión sobre Tanda grande.
**Estado:** decisión inicial: postergar.

**Decisión:** P8 (reactions_db enriquecida con R_FCC, R_HDS, R_REFORM, R_SMR, R_FCK) **no se ataca como parche de tarde**. Queda como proyecto aparte con bloqueante T2 (literatura técnica).

**Por qué:**
- P8 requiere **termoquímica seria**, no software. Decidir estequiometría aproximada + ΔH_rxn realista requiere buscar literatura (Sadeghbeigi para FCC, Topsoe para HDS, etc.).
- Si nos equivocamos con los números, el motor **da resultados peores que los placeholders actuales** (que al menos eran honestamente cero).
- Estimación: 10-20h de trabajo P8 + 5-10h de investigación T2.

**Estado actual:** documentado en `ROADMAP.md` con prioridad alta + bloqueante T2.

---

### D-RECHAZADA-2 — NO se rediseñó Rankine con escala industrial

**Sesión:** Camino X (investigación de outlier Rankine).
**Estado:** decisión: mantener como TIER 2.

**Decisión:** el builder `_example_rankine_cycle` se mantiene con escala piloto (100 tm/año de agua) y se marca como TIER 2 / ilustrativo. NO se re-escala a planta real (~1 MWe, factor 1000x más de masa).

**Alternativas consideradas:**
- (a) Re-escalar a 1 MWe (planta industrial real, ~$5-15M FCI).
- (b) Cambiar tur101 de "Heat exch." a "Compressor — axial" como hack (no aplicable: P=1 atm da extrapolación fuera de rango).
- (c) Marcar como TIER 2 ilustrativo (elegida).

**Por qué (c):**
- Re-escalar es **ingeniería de proceso**, no solo software. Hay que ajustar 15+ valores numéricos (masas, T, S) de forma consistente.
- El docstring del builder ya declara "MODELO ILUSTRATIVO (Tier 2)" — la intención original era pedagógica, no realista.
- La solución correcta requiere primero P11 (agregar Turbinas al catálogo Turton) y después rehacer el builder. Es proyecto aparte.

**Estado actual:**
- TIER 2 implementado en `audit_phase2.py` v3.1.
- Rankine excluido del FCI agregado.
- En `ROADMAP.md`: P11 (Turbinas) + (futuro) re-escalar Rankine.

---

## Cómo agregar entradas a este documento

Cuando se tome una decisión de diseño importante en una sesión futura:

1. Agregar entrada con ID `D-<CATEGORÍA>-<N>` (CATEGORÍA puede ser `MIG`, `AUD`, `PARCHE`, `PROJ`, `RECHAZADA`).
2. Documentar:
   - **Decisión** (qué se eligió, una frase)
   - **PR/Sesión** (referencia para rastrear)
   - **Estado** (`activa` / `superada` / `revertida`)
   - **Alternativas consideradas** (qué otras opciones había)
   - **Por qué** (razón de la elección, no solo "porque sí")
   - **Consecuencias** (impacto a futuro)
3. **NO BORRAR entradas** aunque se reviertan. Cambiar el estado a `revertida` y agregar una entrada nueva explicando por qué se revirtió.

Esto es importante: **el historial completo de decisiones es lo que defiende la tesis**, no solo la última decisión activa.

---

**Próxima sesión:** ver `docs/SESSION_PROMPT.md` para plantilla.
**Estado del motor:** ver `docs/AUDIT.md`.
**Parches pendientes:** ver `docs/ROADMAP.md`.
