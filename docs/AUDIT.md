# AUDIT.md — Estado del motor de Pedro-Tesis

**Última actualización:** post-PR del ticket isentrópico (P14 mergeado).
**Mantenido por:** Claude (audita) + Claude Code (parches) + revisión humana.

---

## Propósito de este documento

Estado consolidado del motor de simulación de Pedro-Tesis después de una auditoría sistemática del solver, los módulos de sizing/costing y el catálogo de 41 ejemplos. Sirve como contexto para sesiones futuras: cualquier Claude que lea este archivo entiende qué funciona, qué no, y por qué.

Convención:
- **H<N>** = Hallazgo (observación, puede ser positiva o negativa).
- **P<N>** = Parche identificado (acción potencial).
- **F<N>** = Hallazgo de Fase 2 (dataset 41 ejemplos).

---

## 1. Arquitectura general

Pedro-Tesis es un simulador conceptual de procesos químicos con interfaz Qt. Después de la migración Tk→Qt (PRs C1-L4), el proyecto es 100% Qt sin código legacy en el camino crítico.

**Entry point:** `flowsheet_main_qt.py`.
**Editor:** `flowsheet_qt.py` (~8900 líneas).
**Motor:** `flowsheet_solver.py` (~3460 líneas) — sequential modular.
**Biblioteca de ejemplos:** `examples_library.ExampleBuilder` con 41 builders.
**Costing:** Turton 5ª ed (`equipment_costs.py`, ~1140 líneas).
**Sizing:** funciones por categoría en `equipment_sizing.py` (~410 líneas).
**Termo:** `thermo_db.py`, `nrtl.py`, `chemfx/`.

El motor es **UI-agnóstico** — el editor Qt y el script `validate_ui.py` comparten el mismo motor.

---

## 2. Estado del solver (`flowsheet_solver.py`)

### 2.1 Orquestación general (función `solve()`)

El solver corre en **7 fases secuenciales**:

```
0. Reset valores propagados
1. Detectar SCCs (Tarjan) y reciclos
2. Closure inicial: balance de masa lineal
3. Wegstein para reciclos no resueltos
4. Re-propagar después de tears
4b. Propagar composiciones antes del reactor
4c. Reactores con LOOP composicional (hasta 30 iter externos)
4cb. Unit ops en orden: splitters → flashes → ciclones →
     separadores → secadores → cristalizadores → evaporadores → columnas
4d. Auto-inferir duties de HX
4d-bis. Aplicar energy streams (heat integration explícito)
4e. Solver hidráulico acoplado (bombas/compresores)
5. Solver de energía (T propagada)
```

**Hallazgos clave:**

- **H16** — Arquitectura two-tier (masa primero, energía después sobre la masa convergida). Correcto para sequential modular.
- **H17** — Wegstein automático SÍ funciona (el docstring del solver está desactualizado, decía "futura mejora" pero ya está implementado).
- **H18** — Loop composicional para reactores en reciclo es ingenioso: hasta 30 iter externos con criterio `max_diff < 1e-4` en composiciones. Crítico para Talara (reciclo H₂ del reformer).
- **H19** — Orden topológico de unit ops refleja conocimiento de dominio: separadores mecánicos antes que columnas.
- **H22** — Sistema de severidad implementado con strings prefijo (`✗`/`⚠`). Funciona pero frágil — si alguien escribe un mensaje sin prefijo, se ignora silenciosamente.
- **H26** — `result.success` depende SOLO de balance de masa + unresolved. Balance de energía global NO afecta `success`.

### 2.2 Locks y propagación (sudoku locks)

El solver tiene 4 tipos de lock:
- `_is_mass_locked(stream)` — caudal declarado por usuario, no se modifica
- `_is_temp_locked(stream)` — T declarada
- `_is_comp_locked(stream)` — composición declarada
- `_is_duty_locked(block)` — duty declarado

**Hallazgo clave H7:** existe `T_MIN/MAX_REASONABLE`. Si el solver calcula T fuera de este rango, **no propaga** (entiende que el modelo Cp simple no captura ΔH_vap o ΔH_rxn y reporta el síntoma en vez de propagar números absurdos). Patrón fail-clean maduro.

### 2.3 Validación de balances

**Tres niveles de severidad:**

- **Error duro** (afecta `success=False`): `_check_mass_balance` tolerancia 0.5% relativa
- **Warning informativo**: `_check_component_balance` tolerancia 2%, pero **skipea reactores y todo lo downstream de reactor transitivamente** (correcto: química propagada cambia composición)
- **No chequeado**: balance de energía global está **deshabilitado** (H25) porque el Cp simple no permite comparación rigurosa

**Implicación operativa (H75-H77):** para flowsheets con muchos reactores y splitters (como Talara), el check por componente cubre solo ~20% del flowsheet. Honesto pero limitado.

### 2.4 Solvers especializados

**11 solvers especializados** invocados desde `solve()`:

- `solve_equilibrium_reactors` (Capa 4-7: equilibrium/PFR/CSTR/batch + adiabatic con Newton-Raphson)
- `solve_columns` (FUG default + Wang-Henke opcional + Fenske-Hengstebeck multicomponente)
- `solve_flashes` (VLE con Antoine + Rachford-Rice)
- `solve_pressure_hydraulic` (acopla bombas/compresores ↔ ΔP downstream)
- `solve_pressure_propagation` (forward pass de P con ΔP declarados)
- `solve_splitters`, `solve_separators`, `solve_dryers`, `solve_crystallizers`, `solve_evaporators`, `solve_cyclones`

**Hallazgo clave H13:** los 11 solvers están al mismo nivel de rigor general, pero hay diferencias importantes según la profundidad de modelado disponible (ver subsecciones siguientes).

### 2.5 Reactores (`solve_equilibrium_reactors`)

**Lo bueno:**
- 4 modos: equilibrium, PFR (cinética), CSTR, batch
- **Reactor adiabático real**: Newton-Raphson interno con damping 50%, 8 iter máximas (H60). Aspen-level.
- **Reacciones custom in-memory** (H55): el usuario puede definir su propia química sin contaminar la BD global. Patrón muy maduro.
- **Detección de placeholder** (H56): si las reacciones declaradas no existen en `reactions_db`, el solver trata el bloque como "marcador estructural" y respeta composiciones declaradas en outputs. Esto permite que Talara funcione con químicas no implementadas (R_FCC, R_HDS, R_REFORM, R_SMR, R_FCK).
- **Outputs con `role="product"`** y composition explícita SE RESPETAN (H67) — escape hatch para builders con química desconocida.

**Lo limitante:**
- **H68 (importante para Talara):** reactores con placeholder no escriben `heat_of_reaction`. Calor del FCC, HDS, SMR, REFORM, FCK se pierde del balance global. OPEX de utilities probablemente sub-estimado para Talara.
- **H62 (P7):** phase detection a 80°C es un umbral arbitrario. Funciona para hidrocarburos livianos pero no para sistemas a alta presión. Mejora propuesta: usar `thermo_db.is_phase_at_TP()` rigurosamente.

### 2.6 Columnas (`solve_columns`)

**Lo bueno:**
- FUG (Fenske-Underwood-Gilliland) shortcut + Wang-Henke tray-by-tray (opcional con `column_method="wanghenke"`).
- Fenske-Hengstebeck para multicomponente (>2 componentes). Nivel sim-comercial.
- Identificación distillate/bottom en 3 capas: por puerto, por composición (LK), por orden.

**Lo limitante:**
- **H45 (P5b):** la heurística #3 (orden) es frágil — depende del orden de declaración en el builder, no de la realidad física. **Ya parchado con warning visible** (PR #18).
- **H50 (P4):** fallback `α=1.0` cuando NRTL no resuelve un componente. **Parchado con warning** (PR #18), pero el verdadero fallback silencioso (NRTL→Raoult) vive más adentro en `distillation_fug.py` y queda como deuda.
- **H51:** composiciones de outputs se sobreescriben siempre (no respeta `composition_locked`). Coherente con filosofía "auto-calculated by solver", pero puede confundir al usuario.
- **H46:** si `T_top`/`T_bot` no se declaran, se estiman como `T_feed ± 15°C`. Razonable para columnas binarias cercanas al punto de ebullición del agua/solventes, **rompe para Talara** (atmospheric tower con T_feed ≈ 350°C, T_top ≈ 100°C, T_bot ≈ 400°C).

**Caveat importante para Talara:** las columnas T-101 (atmospheric) y T-201 (vacuum) del builder de Talara **NO usan `solve_columns`**. Son splitters con fracciones TBP empíricas declaradas. Esto está documentado en el docstring del builder.

### 2.7 Hidráulica (`solve_pressure_hydraulic`)

**Lo bueno (H80-H84):**
- Solver iterativo acoplado: dimensiona ΔP de bombas/compresores buscando próximo stream con `pressure_locked` downstream.
- Detección de bombas/compresores dentro de SCCs (reciclos).
- Memoria de bombas dimensionadas para re-iterar cuando ΔP de tubería cambia.

**Lo limitante:**
- **H84:** requiere AL MENOS un stream con `pressure_locked=True`. Si ningún stream lo tiene, retorna `[]` sin hacer nada. **Solo `hydraulic_plant` del catálogo declara `pressure_locked`** — el resto de los compresores quedan sin auto-dimensionado.
- **H113 (P12, PARCHADO PR #19):** El cálculo de duty eléctrico usaba la fórmula incompresible `W = m·ΔP/(ρ·η)` para todos. **Físicamente correcto para bombas, erróneo para compresores** (debería ser politrópica). **Parchado:** ahora delega a `equipment_design.design_compressor_for_block()` para compresores. **Estado del parche:** activo pero **dormante sobre el catálogo actual** — todos los compresores del catálogo son degenerados (sin `P_op_bar` ni `delta_p_bar` declarados). El parche se activará cuando algún builder declare un compresor bien especificado.

### 2.7.1 Propagación isentrópica de T para compresores/turbinas/fans (P14)

**Estado:** ✅ aplicado (commit `e8ff002`, ticket isentrópico).

**Qué hace:** los bloques tipo Compressor / Fan ahora propagan `T_out` vía relación isentrópica de gas ideal en lugar de ser skipeados por el solver de energía. Habilita modelar correctamente:
- Ciclos Brayton (gas turbine + recuperador)
- Recompresión de gases calientes (HNO3 K-501 expansor)
- Cualquier flujo compresible con cambio significativo de P

**Implementación:**
- `_compressible_props(comp, T_K)`: helper que calcula MW promedio (regla de Kay) y `k=Cp/Cv` usando `Cp(T)` real de `thermo_db`. Fallback heurístico por familia (CO₂ 1.28 / H₂O 1.33 / HC livianos 1.30 / aire 1.40) si thermo_db no resuelve.
- `_propagate_T_compressor_isentropic(...)`: distingue COMPRESOR (`P_out > P_in`, duty > 0, sube T) de TURBINA (`P_out < P_in`, duty < 0, baja T). Compresor delega a `equipment_design.compressor_sizing` (consistente con P12). Turbina implementa expansión manual.
- Integración en `_solve_energy_iteration`: bombas siguen skipeadas (líquido incompresible, ΔT despreciable); compresores/fans pasan por el nuevo helper.

**Hallazgos nuevos del parche:**
- **H115** — `compressor_sizing` clampea internamente `η_isen ≤ 0.95`. Esto es defensivo (ningún compresor real es 100% isentrópico) pero significa que aunque el usuario declare `efficiency=1.0`, el código usa 0.95. Para casos isentrópicos ideales (validación con Cengel), la turbina implementa la expansión manual SIN clamp.
- **H116** — El código usa `Cp(T)` real de `thermo_db`, no la cold-air-standard de Cengel (k=1.4 constante). Esto produce diferencias **físicamente más precisas pero numéricamente distintas** a los libros de texto. Ejemplo: turbina de aire 1300K → 1bar da exhaust 799K (k≈1.30 a esa T) vs los 717K de Cengel (k=1.4 constante). Decisión documentada en DECISIONS D-PARCHE-6.

**Validación:** `validate_ui.check_isentropic_compression()` con 3 casos verifica el parche:
- Caso 1: compresor aire ideal → 555.3K / 2718.9 kW
- Caso 2: turbina aire 1300K → 798.6K / -5880.9 kW
- Caso 3: compresor η=0.85 → 585.3K / 3038.7 kW

**Compatibilidad:** los 41 ejemplos siguen pasando. HNO3 K-501 (único expansor pre-existente) intacto — la función detecta `duty_locked + T_out locked + P_out==P_in` y retorna `False` sin modificar.

**Pre-existente NO relacionado con el parche:** `test_batch_bridge.py` falla en collection por falta de `openpyxl`. Esto es deuda del entorno de testing, no del motor.

### 2.8 Inferencia de duty (`infer_block_duty`, `auto_set_duties_from_thermo`)

**H31-H36:** el motor calcula `duty = H_out - H_in - Q_rxn` cuando el usuario no declara duty. Tres puertas de salida `None` (fail-clean) si no se puede inferir. Detecta cross-exchange automáticamente. Skipea reactores (su duty viene del solver de reactores, no del balance global).

### 2.9 Goal-seek y setpoints (`goal_seek_duty`, `solve_setpoints_all`)

**Modo design existe:** el usuario puede declarar `target_temperature` en un stream y el solver calcula el duty del bloque upstream que lo cumple. **Closed-form** para bloques 1-in-1-out (no iterativo). Detecta over-spec.

**Limitación operativa (H41):** `solve_setpoints_all` NO se llama automáticamente desde `solve()`. Es opt-in vía botón "Setpoints…" en menú/toolbar. Parche P3 propuesto: integrar al solve principal cuando hay setpoints declarados.

### 2.10 Análisis DOF (`analyze_dof` + `dof_audit.py`)

Pedro-Tesis tiene **dos análisis de DOF complementarios**:
- `analyze_dof()` en el solver: cálculo matemático puro de grados de libertad.
- `dof_audit.analyze_flowsheet()` en módulo separado: análisis topológico estructural (propagación BFS desde streams lockeados, detección de reactores sin T_op, HX sin specs, etc).

**Hallazgo clave H30:** el DOF audit existe, está conectado al UI Qt vía botón "Validar DOF" en menú y toolbar, **pero no es bloqueante pre-solve**. El usuario puede correr `solve()` sin haber validado. Parche P1 propuesto: llamarlo automáticamente antes de cada solve.

### 2.11 Heat integration explícita (`apply_energy_streams`)

**Hallazgo importante H89-H92:** Pedro-Tesis tiene heat integration **declarativa por stream**. El usuario puede declarar un stream entre HX-1 (caliente) y HX-2 (frío) con `stream_kind="energy"`, `energy_kW=500`. El solver:
- Resta 500 al duty de HX-1
- Suma 500 al duty de HX-2
- Mantiene `Σ Δduty = 0` por construcción
- **Es idempotente:** trackea contribuciones previas vía `_energy_streams_delta` para evitar duplicar en re-solve

Esto es lo que permite hacer Pinch real en el solver (complementario al factor global `HEAT_INTEGRATION["factor"] = 0.4` de `econ_defaults`).

---

## 3. Estado del sizing (`equipment_sizing.py`)

### 3.1 Catálogo de constantes

**Hallazgos H93-H97:**
- `U_TYPICAL`, `DTLM_TYPICAL`, `TAU_REACTOR` con valores canónicos de Turton 5ª ed
- Tres niveles de precedencia: `block.X_override` → catálogo → default
- `_rho_estimate(stream)` con detección de phase + lookup en thermo_db
- `_mw_avg_kg_per_mol(stream)` con MW real (parchado, antes era 0.030 hardcoded)

### 3.2 Funciones de sizing por categoría

**Bien implementadas:**
- `size_heat_exchanger`: `A = |Q|/(U·ΔT_lm)` con override del usuario (H99)
- `size_fired_heater`: `S = duty` directo (H100). El reporte original que decía "Cp=2.0 hardcoded" era falso.
- `size_reactor`: usa `_rho_estimate(T_op, P_op)` para reactores a alta T/P (H101)
- `size_pump`/`size_compressor`: delegan a `equipment_design.py` (single source of truth, H102)
- `size_tower`: Souders-Brown correcto, distingue tray vs packing (H103-H108)

**Parchados en PR Pa1 (#17):**
- `size_evaporator` ahora usa los diccionarios `U_TYPICAL`/`DTLM_TYPICAL` en vez de magic numbers (P5)
- `size_storage_tank` ahora usa `_rho_estimate` en vez de asumir ρ=800 kg/m³ (P6) — relevante para tanques de gas comprimido (H₂)

### 3.3 Defaults globales (`econ_defaults.COLUMN_DEFAULTS`)

**Parchado en PR Pa1 (#17):** `tray_efficiency` cambió de 1.0 → 0.7 (valor industrial genérico). Impactó la altura de todas las columnas con FUG en el catálogo (+43%). Cuatro tests del solver se actualizaron a fórmula en vez de número literal, para no codificar el valor del default como invariante físico.

---

## 4. Estado del costing (`equipment_costs.py`)

### 4.1 Correlación Turton

Pedro-Tesis implementa Turton 5ª ed:
- `bare_module_cost(eq_type, S, P_op_bar, material)` devuelve dict con CBM, Cp_base, Cp_target, factor CEPCI, fuera_rango, warning_msg
- Coeficientes K1/K2/K3 con `purchased_cost` polinomial
- Factores FBM por categoría (Heat exchangers, Reactors, Compressors, etc.)
- Material correction `FM` por aleación
- Pressure correction `FP` para vessels y otros

### 4.2 Catálogo `EQUIPMENT_DATA`

Tiene ~40 `eq_types` con sus rangos de validez `S_min/S_max`. Categorías cubiertas: Heat exchangers (10 subtipos), Pumps, Compressors, Reactors, Vessels, Storage tanks, Fired heaters, Boilers, Dryers, Evaporators, Filters, Fans, Trays, Packing, Mixers, Splitters, Centrifuges, Cyclones, Decanters, Valves, Cooling towers.

**Deuda identificada P11:** falta categoría "Turbines" con tipos específicos (steam turbine, gas turbine). Existe `LANG_FACTORS["Turbines"]` pero no hay `eq_types` que la usen. Esto fuerza al builder de Rankine a hackear modelando turbina como HX.

### 4.3 Funciones económicas

- `grass_roots_capital` (FCI con contingency)
- `cost_of_manufacture` (Turton Eq 8.2)
- `profitability_indicators` (NPV, IRR, payback)

---

## 5. Estado del catálogo de ejemplos (Fase 2)

### 5.1 Resumen de la auditoría sobre 41 builders

Después de los PRs C1-L4 + Pa1 + Tanda chica + P12:

**TIER 1 — 38 ejemplos industriales:**
- 38/38 build OK, solve OK, mass balance OK
- 5/38 con `status=warning` (industrial_complete, quimpac_chloralkali, hno3_ostwald, hda_full, ammonia) — todos triggereados por warnings de compresor degenerado
- 8/38 con bloques fuera del rango Turton (~20%)
- **FCI agregado: $155.2M USD, promedio $4.1M USD**

**TIER 2 — 3 ejemplos ilustrativos (excluidos del agregado):**
- `rankine_cycle` ($135M, outlier — turbina modelada como HX por falta de eq_type Turbine)
- `desalination` ($3.8M)
- `nuclear_steam` ($0.34M)

Los ilustrativos se detectan automáticamente en `audit_phase2.py` buscando "TIER 2", "ILUSTRATIVO", "piloto", "plant-scale" en la **primera línea** del docstring.

### 5.2 Hallazgos del catálogo

- **F1:** salud estructural perfecta. 41/41 sin mass_errors ni unresolved. **El motor está sano sobre el catálogo.**
- **F2:** outlier Rankine ($135M) explicado: turbina modelada como `Heat exch. — floating head` con S=150 m² (luego recalculado a ~1500 m² por el solver, fuera de rango Turton, extrapolación absurda). **NO es bug del motor**, es workaround del builder ante falta de eq_type Turbine.
- **F3:** Talara con FCI=$12.5M para 32 bloques. **Sub-estimado por factor ~40-60x** respecto a PMRT real escalada (1/10). Causa: columnas DP1/DV3 modeladas como splitters (no como Wang-Henke con cortes TBP reales), FCC modelado como splitter con rendimientos típicos. Esto está documentado en el docstring del builder ("MODELO ILUSTRATIVO de refino").
- **F8:** **todos los compresores del catálogo (11 ejemplos, 15 compresores totales) son degenerados** — declaran `delta_p_bar=0` y `P_op_bar=1.0`. Sus duties están seteados manualmente por el builder, no calculados por el motor. P12 está implementado pero dormante sobre este catálogo.
- **Deuda adicional descubierta:** algunos builders usan **abreviaturas de componentes** (`h2`, `ch4`) en vez de nombres canónicos (`hydrogen`, `methane`). Esto hace que thermo_db no resuelva propiedades y se apliquen fallbacks silenciosos.

---

## 6. Tabla consolidada de parches

### 6.1 Aplicados ✅

| ID | Descripción | PR | Impacto medido |
|----|-------------|-----|----------------|
| C1-L4 | Migración Tk → Qt completa | #8, #9, #10, #11, #12, #13, #14 | −9292 líneas netas |
| P5 | `size_evaporator` a diccionarios | #17 | Consistencia interna |
| P6 | `size_storage_tank` usa `_rho_estimate` | #17 | Tanques de gas dimensionados correctamente |
| P10 | `tray_efficiency` default 1.0 → 0.7 | #17 | Altura de columnas +43% en ejemplos con FUG |
| P4 | Warning fallback MW=1.0 / α=1.0 en columnas | #18 | Safety net (no triggea sobre catálogo curado) |
| P5b | Warning heurística orden distillate/bottom | #18 | Safety net (idem) |
| P13 | Warning compresor sin P_op_bar declarada | #18 | 14 warnings activos en 11 ejemplos |
| P12 | Distinguir pump/compressor en duty hidráulico (ec. politrópica) | #19 | Activo pero dormante sobre catálogo actual |
| **P14** | **Propagación isentrópica de T para compresores/turbinas/fans** | **commit `e8ff002`** | **Habilita ciclos Brayton, validado con 3 casos Cengel** |

### 6.2 Pendientes ⏳

Ver `docs/ROADMAP.md` para prioridades, esfuerzo y dependencias.

### 6.3 Bloqueados/postergados ⏸️

- **P7** (phase detection rigurosa): requiere implementar `is_phase_at_TP()` en `thermo_db.py` primero.
- **P2** (DOF audit bloqueante con modal): decisión de UX pendiente.

---

## 7. Lo que NO está implementado (limitaciones honestas)

### 7.1 Modelado

- **Cinética real de FCC, HDS, REFORM, SMR, FCK**: los IDs `R_FCC`, `R_HDS`, etc. no existen en `reactions_db.py`. El motor los detecta como placeholder y usa composiciones declaradas en outputs. Calor de reacción se pierde del balance global.
- **Modelo de combustión para fired heaters**: el solver toma `duty` directo, no balancea combustión con aire/exceso.
- **Turbinas (vapor, gas)**: ausentes del catálogo Turton. Fuerza workarounds en builders.
- **Modelo NRTL completo para pseudo-componentes de refino** (diesel_cut, vacuum_gasoil): fallback silencioso a Raoult.

### 7.2 Validación

- **Balance de energía global no se verifica** (deshabilitado intencionalmente por Cp simple). Un `success=True` solo certifica balance de masa.
- **Componentes < 1% del flujo** se ignoran en el check por componente.
- **Reactores y todo lo downstream transitivamente** se skipea en el check por componente.

### 7.3 Datos del catálogo (deuda de builders)

- **11 compresores sin P_op_bar / delta_p_bar declarados** (P12 está dormante por esto)
- **N builders usan abreviaturas (`h2`, `ch4`) en vez de nombres canónicos** — falta auditar cuántos exactamente
- **Talara modela columnas como splitters** (limitación declarada del builder, no del motor)

---

## 8. Para sesiones futuras

Antes de proponer cambios al solver o al catálogo:

1. **Verificá el estado actual del repo en vivo** — este documento se actualiza pero puede quedar desfasado entre merges.
2. **Leé el código que vas a modificar** — no asumas líneas que viste en una auditoría vieja.
3. **Si encontrás un hallazgo nuevo, agregalo a este AUDIT.md** con un ID nuevo (continuá la numeración H115+).
4. **Si proponés un parche nuevo**, agregalo a `ROADMAP.md` con ID P14+ y criterios de aceptación claros.
5. **Si aplicaste un parche del ROADMAP**, moverlo a la tabla 6.1 acá con su PR y métrica de impacto.

---

**Próxima sesión sugerida:** ver `docs/ROADMAP.md` para parches pendientes.
**Decisiones de diseño:** ver `docs/DECISIONS.md`.
**Plantilla de prompt para nueva sesión:** ver `docs/SESSION_PROMPT.md`.
