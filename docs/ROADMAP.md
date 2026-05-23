# ROADMAP.md — Parches pendientes de Pedro-Tesis

**Última actualización:** post-PR del ticket isentrópico (P14 mergeado).
**Estado actual del motor:** ver `docs/AUDIT.md`.

---

## Cómo usar este documento

- **Estado**: cada parche tiene uno de: `pendiente`, `bloqueado`, `decisión-pendiente`.
- **Prioridad**: `alta` / `media` / `baja`.
- **Esfuerzo**: estimación honesta en horas de trabajo Claude+Code+revisión.
- **Riesgo**: `bajo` (parche aislado, fácil revertir) / `medio` (cambia números) / `alto` (puede romper otros parches o cambiar API).
- **Dependencias**: parches que tienen que estar hechos antes.
- **Criterio de aceptación**: qué tiene que pasar para considerarlo cerrado.

Cuando aplicamos un parche, se mueve a `AUDIT.md` tabla 6.1.

**Nota sobre tickets ad-hoc:** parches que no estaban en el ROADMAP planificado pero que se aplicaron (ejemplo: P14 propagación isentrópica, agregado después del PR #19 sin entrada previa) **se documentan retroactivamente en AUDIT.md tabla 6.1**. No requieren entrada previa en ROADMAP — eso es para planificación, no inventario. La decisión de aceptarlos sin planificación previa está documentada en DECISIONS D-PROJ-4.

---

## Tabla resumen

| ID | Descripción | Prioridad | Esfuerzo | Riesgo | Bloqueado por |
|----|-------------|-----------|----------|--------|----------------|
| P1 | DOF audit automático pre-solve | media | ~1h | bajo | — |
| P3 | Setpoints integrado al solve principal | media | ~1h | medio | — |
| P7 | Phase detection rigurosa via `is_phase_at_TP` | baja | ~0.5h | bajo | T1 |
| P8 | Reactions_db: R_FCC, R_HDS, R_REFORM, R_SMR, R_FCK | alta | ~10-20h | alto | T2 |
| P9 | Balance térmico por bloque como warning | media | ~2-3h | medio | — |
| P11 | Agregar Turbinas al catálogo Turton | alta | ~3-4h | medio | — |
| P2 | DOF audit bloqueante con dialog modal | baja | ~1h | bajo | D1 |
| D1 | Corregir P_op_bar / delta_p_bar de 11 compresores | alta | ~2-3h | medio | T3 |
| D2 | Auditar abreviaturas de componentes en builders | media | ~2h | bajo | — |
| T1 | Implementar `is_phase_at_TP` en `thermo_db.py` | alta | ~1h | bajo | — |
| T2 | Buscar literatura cinética FCC/HDS/SMR | alta | ~5-10h | — | — |
| T3 | Decidir presiones operativas por proceso (referencias) | alta | ~3-5h | — | — |

**T**asks = trabajo previo de datos/literatura (no es código).
**D**ata = parches al catálogo de ejemplos.

---

## Parches del motor

### P1 — DOF audit automático pre-solve

**Estado:** pendiente.
**Prioridad:** media.
**Esfuerzo:** ~1h.
**Riesgo:** bajo.

**Qué:** llamar `dof_audit.analyze_flowsheet(fs)` automáticamente antes de cada `solve()`. Si hay errores estructurales (DOF < 0 o composiciones sin source), agregar un warning visible al `result.energy_warnings` sin abortar el solve.

**Ubicación:** `flowsheet_solver.py`, función `solve()` línea ~3076 (al inicio, después del reset).

**Criterio de aceptación:**
- Talara + los 41 ejemplos siguen pasando (los warnings nuevos no afectan `success`).
- Si construyo un flowsheet under-specced sintético, el warning aparece en `result.energy_warnings`.
- 120 tests verdes.

**Notas:**
- El parche es solo agregar warnings, NO hacerlo bloqueante. La versión bloqueante con modal es P2.
- Aprovechar la oportunidad para mover el botón "Validar DOF" del menú a "Diagnóstico" para que quede más claro que ahora se hace solo.

---

### P3 — Setpoints integrado al solve principal

**Estado:** pendiente.
**Prioridad:** media.
**Esfuerzo:** ~1h.
**Riesgo:** medio (cambia números si hay setpoints declarados en algún ejemplo).

**Qué:** detectar si el flowsheet tiene `target_temperature` en algún stream. Si sí, llamar `solve_setpoints_all(fs)` automáticamente después de la fase 5 (energía propagada). Hoy el usuario debe llamarlo manualmente vía botón "Setpoints…".

**Ubicación:** `flowsheet_solver.py`, función `solve()`, entre fase 5 y el cálculo de `overall_status`.

**Criterio de aceptación:**
- Si NINGÚN stream tiene `target_temperature`, comportamiento idéntico a hoy.
- Si hay setpoints, el solver los resuelve automáticamente y los reporta en el resultado.
- Verificar que ningún ejemplo del catálogo declare setpoints inadvertidamente (un grep rápido a `examples_library.py` por `target_temperature`).

**Riesgo conocido:** si un ejemplo declara un setpoint **incompatible** con su flowsheet (ej. T target imposible por balance), el solve va a fallar donde antes pasaba silenciosamente. Eso es desejable pero hay que confirmar que no rompe ejemplos existentes.

---

### P7 — Phase detection rigurosa via `is_phase_at_TP`

**Estado:** bloqueado por T1.
**Prioridad:** baja.
**Esfuerzo:** ~0.5h (una vez T1 esté hecho).
**Riesgo:** bajo.

**Qué:** en `solve_equilibrium_reactors` (línea ~1428), reemplazar el umbral arbitrario "T > 80°C → gas" por una llamada a `thermo_db.is_phase_at_TP(comp, T, P)`. Mantener el umbral como fallback si la función no resuelve.

**Bloqueante T1:** implementar `is_phase_at_TP()` en `thermo_db.py` primero. Sin eso, P7 no tiene sentido aplicarlo.

**Criterio de aceptación:**
- Los 41 ejemplos siguen pasando.
- Para un reactor con feed a 75°C y P=10 bar (donde a 1 atm sería líquido pero a 10 bar es gas), el Cp usado debe ser el correcto.

---

### P8 — Reactions_db: R_FCC, R_HDS, R_REFORM, R_SMR, R_FCK

**Estado:** bloqueado por T2.
**Prioridad:** alta (es el de mayor impacto para Talara).
**Esfuerzo:** ~10-20h.
**Riesgo:** alto.

**Qué:** agregar 5 entradas a `reactions_db.py` con estequiometría aproximada y `heat_of_reaction` tabulado:

- **R_HDS** (hidrodesulfurización): `R-SH + H₂ → R-H + H₂S`, ΔH ≈ -55 kJ/mol S
- **R_REFORM** (reformado catalítico): `nafta → aromáticos + H₂`, ΔH ≈ +150 kJ/mol H₂
- **R_SMR** (steam methane reforming): `CH₄ + H₂O → CO + 3H₂`, ΔH ≈ +206 kJ/mol
- **R_FCC** (catalytic cracking): `C₂₀-C₃₅ → C₃-C₁₂ + coke`, ΔH ≈ +280 kJ/kg crudo
- **R_FCK** (flexicoking): `residuo pesado → gas + nafta + coke`, ΔH ≈ +350 kJ/kg

**Bloqueante T2:** literatura técnica para validar estequiometría y ΔH_rxn. Sin referencias, los números son "estimaciones razonables" — no defendibles en tesis.

**Criterio de aceptación:**
- Talara post-parche reporta `heat_of_reaction` no-cero para los reactores HTN, HTD, HTF, RCA, FCC, FCK, SMR.
- El balance global de Talara incluye estos calores.
- FCI de Talara probablemente sube (los reactores ahora necesitan mayor duty de horno o sistema de enfriamiento) — esto es esperado, NO regresión.
- 41 ejemplos siguen pasando (los otros 40 no usan estos R_*).

**Notas:**
- Este es trabajo de **termoquímica**, no de software. Si nos equivocamos con los ΔH, el motor da resultados peores que con placeholders (que al menos eran honestamente cero).
- Considerar si Talara también debería pasar de modo `equilibrium` a `pfr` con cinética — eso es otro proyecto encima.

---

### P9 — Balance térmico por bloque como warning

**Estado:** pendiente.
**Prioridad:** media.
**Esfuerzo:** ~2-3h.
**Riesgo:** medio (puede generar muchos warnings en ejemplos con Cp simple no comparable).

**Qué:** re-habilitar el check de balance térmico, pero solo a nivel **por bloque** (no global) y como **warning informativo** (no error duro). Algo como:
```
Q_sens_in + Q_rxn + duty_externo ≈ Q_sens_out  (tolerancia laxa ~15%)
Si falla: warning "balance térmico inconsistente — verificar duty o Cp"
```

**Ubicación:** función nueva `_check_thermal_balance_per_block` en `flowsheet_solver.py`, llamada al final de `solve()`.

**Criterio de aceptación:**
- Cuenta cuántos bloques de cada ejemplo del catálogo tienen warning térmico.
- Talara, ammonia, methanol probablemente tendrán warnings (reactores con Cp simple).
- El campo `result.success` NO cambia por estos warnings.
- Los 120 tests siguen pasando.

**Notas:**
- Complementa H25/H26 ("balance E global deshabilitado").
- Probable interacción con P8: si agregamos heat_of_reaction real, varios warnings van a desaparecer.

---

### P11 — Agregar Turbinas al catálogo Turton

**Estado:** pendiente.
**Prioridad:** alta (arregla outlier de Rankine + futuras plantas con turbinas).
**Esfuerzo:** ~3-4h.
**Riesgo:** medio.

**Qué:** agregar al `EQUIPMENT_DATA` de `equipment_costs.py`:
- `"Turbine — steam (small)"`: para turbinas <1 MW
- `"Turbine — steam (large)"`: para turbinas 1-100 MW
- `"Turbine — gas"`: gas turbines
- `"Turbine — hydraulic"`: turbinas hidroeléctricas

Y agregar dispatcher en `equipment_sizing.SIZER_BY_CAT` para categoría "Turbines" → función nueva `size_turbine(block, fs)`.

**Fuente:** Turton 5ª ed Capítulo 8, Tabla A.1 (coeficientes K1/K2/K3 para "Turbine, steam", "Gas turbine").

**Criterio de aceptación:**
- Rankine se puede re-modelar con `Turbine — steam (small)` en vez de hack como HX.
- FCI de Rankine pasa de $135M → algo razonable (~$3-15M para planta piloto).
- Si se mantiene Rankine como TIER 2 (escala piloto) o se re-escala a TIER 1 — decisión separada.

**Dependencia futura:** una vez P11 está hecho, conviene modificar `_example_rankine_cycle` para usar las nuevas categorías. Eso es trabajo de builder, no de motor.

---

### P2 — DOF audit bloqueante con dialog modal

**Estado:** decisión-pendiente.
**Prioridad:** baja.
**Esfuerzo:** ~1h.
**Riesgo:** bajo.

**Qué:** versión más invasiva de P1. Si `dof_audit.analyze_flowsheet()` detecta errores estructurales críticos, mostrar un dialog modal "Tu flowsheet tiene N errores estructurales. ¿Resolver de todas formas?" antes de hacer `solve()`.

**Decisión pendiente:** ¿queremos forzar al usuario a confirmar, o solo informar (P1)? Esto es UX, no técnico.

**Recomendación:** hacer P1 primero, ver si los warnings son suficientes. Si los usuarios siguen ignorando flowsheets under-specced, ahí evaluar P2.

---

## Parches al catálogo de ejemplos (data)

### D1 — Corregir P_op_bar / delta_p_bar de 11 compresores

**Estado:** bloqueado por T3.
**Prioridad:** alta (activa P12 retroactivamente).
**Esfuerzo:** ~2-3h.
**Riesgo:** medio.

**Qué:** declarar `P_op_bar` o `delta_p_bar` realista en los 11 compresores del catálogo:
- `ammonia` K-101
- `methanol` K-101
- `hda_full` K-101
- `industrial_complete` K-101, K-202
- `hno3_ostwald` K-101, K-301, K-501
- `quimpac_chloralkali` K-301
- `acetic_acid` K-101
- `polyethylene` K-101 (LDPE, ~2000 bar)
- `urea` K-101 (~150 bar)
- `ethylene_cracking` K-101
- `air_separation` K-101

**Bloqueante T3:** referencias técnicas para validar cada presión. Sin esto, las decisiones son "estimación razonable" pero no defendibles.

**Criterio de aceptación:**
- Después del parche, P12 (ya aplicado en PR #19) deja de estar dormante.
- Los 11 ejemplos reportan duty calculado por ecuación politrópica (vía `design_compressor_for_block`).
- El audit `phase2.py` muestra duties realistas (en kW, comparables con la realidad industrial).
- FCI cambia poco (sizing ya usaba politrópica vía `size_compressor`).
- OPEX eléctrico cambia significativamente para los compresores a alta P.

---

### D2 — Auditar abreviaturas de componentes en builders

**Estado:** pendiente.
**Prioridad:** media.
**Esfuerzo:** ~2h.
**Riesgo:** bajo.

**Qué:** grep sistemático a `examples_library.py` buscando composiciones con abreviaturas:
- `h2` vs `hydrogen`
- `ch4` vs `methane`
- `co2` vs `carbon_dioxide`
- `n2`, `o2`, `co`, `nh3`, `so2`, `h2s`, etc.

Estandarizar todo a nombres canónicos de `thermo_db.py` (que probablemente son ingleses descriptivos).

**Criterio de aceptación:**
- Cero matches de abreviaturas en `examples_library.py` que no sean nombres canónicos.
- Los 41 ejemplos siguen pasando.
- Componentes ahora resuelven en thermo_db sin fallbacks silenciosos (varios warnings de P4 podrían desaparecer).

**Notas:**
- Hay que verificar primero qué nombres canónicos usa `thermo_db.py`. Posiblemente algunos pueden tener alias (consultar).
- Si la BD tiene `hydrogen` pero los builders usan `h2`, no es bug del motor — es deuda de los builders.

---

## Trabajos previos de datos/literatura

### T1 — Implementar `is_phase_at_TP` en `thermo_db.py`

**Estado:** pendiente.
**Prioridad:** alta (desbloquea P7).
**Esfuerzo:** ~1h.
**Riesgo:** bajo.

**Qué:** función nueva en `thermo_db.py`:
```python
def is_phase_at_TP(comp_name, T_K, P_bar):
    """Determina la phase ('gas'/'liquid'/'two-phase'/'solid') de un
    componente puro a T, P dadas, usando Antoine + comparación con
    P_sat. Devuelve None si no hay datos."""
```

**Criterio de aceptación:**
- Función disponible en `thermo_db`.
- Para agua a 25°C 1bar → "liquid"; a 200°C 1bar → "gas"; a 200°C 50bar → "liquid" (porque P > P_sat).
- Para H₂ a cualquier T razonable → "gas".

---

### T2 — Buscar literatura cinética FCC/HDS/SMR

**Estado:** pendiente.
**Prioridad:** alta (desbloquea P8).
**Esfuerzo:** ~5-10h.
**Riesgo:** —

**Qué:** investigar y compilar referencias para:
- **FCC**: Sadeghbeigi "Fluid Catalytic Cracking Handbook", Avidan "FCC Catalysis", Wojciechowski "Catalytic Cracking"
- **HDS**: Topsoe "Hydrotreating Catalysis", Speight "Petroleum Refining"
- **SMR**: Rostrup-Nielsen "Steam Reforming"
- **Reformer catalítico**: Antos "Catalytic Naphtha Reforming"
- **Flexicoking**: literatura de Exxon

**Criterio:** para cada R_*, tener al menos 2 referencias con ΔH_rxn validado.

---

### T3 — Decidir presiones operativas por proceso (referencias)

**Estado:** pendiente.
**Prioridad:** alta (desbloquea D1).
**Esfuerzo:** ~3-5h.
**Riesgo:** —

**Qué:** para cada uno de los 11 compresores del catálogo, documentar:
- Presión de succión típica (P₁)
- Presión de descarga típica (P₂)
- Referencia bibliográfica

**Procesos a investigar:**
- Síntesis de amoníaco (Haber-Bosch): ~150-300 bar
- Síntesis de metanol: ~50-100 bar (Lurgi: bajo, ICI: alto)
- HDA (hidrodesalquilación): ~25-35 bar
- HNO₃ (Ostwald): bajo-medio (3-12 bar)
- Cloro-álcali: variable
- Ácido acético (Monsanto): ~30-60 bar
- LDPE: 1500-3000 bar (alta presión real)
- Urea (Stamicarbon/Snamprogetti): ~150-200 bar
- Ethylene cracker: depende de etapa
- Air separation: bajo (5-10 bar primaria, hasta 50 para criogénica)

**Fuente recomendada:** Ulmann's Encyclopedia of Industrial Chemistry, Kirk-Othmer, Speight "Petroleum Refining", Couper "Chemical Process Equipment".

---

## Próximas sesiones — orden sugerido

Si volvés con tiempo limitado por sesión (~1-2h):

**Sesión próxima (~1h):** T1 + P7 (chico, demuestra continuidad del sistema, desbloquea un parche).

**Sesión siguiente (~2h):** P1 (DOF audit automático). UX clara, bajo riesgo, defendible en tesis.

**Sesión siguiente (~3h):** P11 (agregar Turbinas al catálogo). Resuelve outlier Rankine, futuro-proof para plantas con turbinas.

Si volvés con tiempo largo (sesión de 1+ días):

**P8 + T2** combinado. Trabajo serio de termoquímica + datos. Es el de mayor impacto en Talara pero requiere investigación seria.

**D1 + T3** combinado. Activar P12 retroactivamente con referencias reales.

---

## Hallazgos abiertos (no son parches todavía)

Cosas que vimos durante la auditoría que merecen seguimiento pero no son parches accionables todavía:

- **El verdadero fallback NRTL→Raoult vive dentro de `distillation_fug.relative_volatility()`** (función externa). Surfacearlo requiere modificar `distillation_fug.py`. Si lo hacés, sumá P14 al ROADMAP.
- **El catálogo Turton tiene rangos `S_min/S_max` estrechos** para algunos eq_types (8/38 ejemplos tienen bloques fuera de rango). Considerar extender rangos con datos adicionales (proyecto largo).
- **Pedro-Tesis NO modela ΔH_mix** (mezclas no-ideales pierden calor de mezclado). Para procesos con agua + ácido fuerte, alcohol + agua, etc. el balance térmico subestima. No es bug crítico para conceptual design, pero documentado.

---

**Próxima sesión:** ver `docs/SESSION_PROMPT.md` para plantilla.
**Decisiones de diseño:** ver `docs/DECISIONS.md`.
**Estado del motor:** ver `docs/AUDIT.md`.
