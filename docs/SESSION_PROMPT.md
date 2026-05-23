# SESSION_PROMPT.md — Plantillas de prompt para sesiones nuevas

**Última actualización:** post-PR #19 (P12 mergeado).

---

## Cómo usar este documento

Cuando abrís una sesión nueva con Claude (en claude.ai), copiás la plantilla apropiada según lo que querés hacer, llenás los huecos `[REEMPLAZAR]`, y la pegás como primer mensaje.

Hay **5 plantillas** según el tipo de sesión:

| Plantilla | Para qué | Duración típica |
|-----------|----------|-----------------|
| 1. Auditoría/Diagnóstico | Investigar un problema, hallazgo nuevo | 1-3h |
| 2. Aplicar parche del ROADMAP | Atacar un P<N> ya planeado | 1-3h |
| 3. Discusión de diseño | Decidir cómo abordar algo nuevo | 1-2h |
| 4. Revisión de PR | Validar un PR que Claude Code armó | 30 min - 1h |
| 5. Sesión libre / exploración | Tarea abierta sin plan claro | variable |

**Para todas las plantillas:** Claude (auditor) razona y arma prompts. Claude Code aplica parches por separado, en otra sesión. Esto está documentado en `docs/DECISIONS.md` D-PROJ-1.

---

## Bloque común — Contexto del proyecto (incluir SIEMPRE)

Este bloque es **idéntico para las 5 plantillas**. Lo copiás siempre al inicio:

```
Voy a trabajar en Pedro-Tesis (simulador conceptual de procesos químicos).

Repo: https://github.com/Eltiokarma/Pedro-Tesis
Rama default: claude/understand-document-improve-g8xoM
Entry point: flowsheet_main_qt.py (editor Qt principal)

CONTEXTO DEL PROYECTO

Antes de proponer nada, leé estos 4 archivos del repo, en orden:

1. docs/AUDIT.md
   — Estado del motor de simulación (qué funciona, qué no, hallazgos
     consolidados de la auditoría del Camino D).

2. docs/ROADMAP.md
   — Parches pendientes con prioridad, esfuerzo, dependencias y
     criterios de éxito.

3. docs/DECISIONS.md
   — Decisiones de diseño tomadas y su razón (por qué tray_eff=0.7,
     por qué se mantuvo el alias _LegacyEditor, etc).

4. docs/SESSION_PROMPT.md
   — Este mismo archivo (referencia, no es obligatorio releerlo cada vez).

Si alguno de esos archivos no existe en la rama actual o difiere mucho
del estado del repo en vivo, AVISÁ. No improvisés — preguntame qué
hacer.

REGLAS DE TRABAJO

- Verificá el estado del repo EN VIVO antes de proponer cambios. NO
  trabajes de memoria — el repo tiene 100+ commits y cambia
  frecuentemente.
- Si vas a proponer un parche, primero leé el código actual del
  archivo a modificar. NO asumás líneas que viste en una auditoría
  vieja.
- Si un PR queda abierto al final de la sesión, decímelo
  explícitamente con su URL.
- Si pensás que el ROADMAP / AUDIT / DECISIONS necesitan actualización
  (parche aplicado, prioridad cambiada, deuda nueva descubierta),
  proponé el cambio como diff a los archivos correspondientes.
- Vos sos Claude (auditor). Claude Code aplica los parches en sesión
  separada. Para parches, armás el prompt; yo lo paso a Claude Code.
```

---

## PLANTILLA 1 — Auditoría / Diagnóstico

**Usar cuando:** querés investigar algo específico (un módulo, un hallazgo nuevo, un bug sospechado). NO querés aplicar parches todavía — querés entender primero.

```
[BLOQUE COMÚN ARRIBA]

QUÉ HACER EN ESTA SESIÓN

TIPO: Auditoría / Diagnóstico

OBJETIVO:
[REEMPLAZAR con una frase clara, ejemplo: "Investigar por qué el
solver de columnas usa α=1.0 como fallback en lugar de buscar
componentes similares. Quiero entender si es bug, decisión de diseño
o limitación de NRTL."]

CONTEXTO ADICIONAL:
[OPCIONAL — agregar si hay información que no está en AUDIT.md.
Ejemplo: "Esto surgió porque un usuario reportó que su columna de
benceno-tolueno daba composiciones raras en el bottom."]

ALCANCE:
[REEMPLAZAR — qué archivos/módulos mirar. Ejemplo: "flowsheet_solver
solve_columns, distillation_fug, nrtl.py — solo lectura, no modificar
nada."]

LO QUE NECESITO AL FINAL:
[REEMPLAZAR — qué entregable. Ejemplo: "Un mini-reporte con: (a)
diagnóstico del problema, (b) si es bug o feature, (c) si es bug, una
propuesta de parche con líneas exactas a modificar, (d) actualización
sugerida a AUDIT.md y ROADMAP.md si corresponde."]

CONSTRAINT:
- NO modificar código. Solo lectura + análisis.
- Si encontrás otros hallazgos relacionados, mencionalos al final
  pero no los investigues a fondo (otra sesión).
```

**Ejemplo concreto de uso:**

```
[BLOQUE COMÚN]

QUÉ HACER EN ESTA SESIÓN

TIPO: Auditoría / Diagnóstico

OBJETIVO: Investigar por qué `ammonia` y `methanol` reportan duty del
compresor en valores fijos (1200 kW y 800 kW respectivamente) cuando
sus compresores son degenerados (sin P_op_bar declarada). Necesito
entender si esos valores los pone el builder a mano y de dónde vienen.

ALCANCE: examples_library.py (solo la sección de los 2 builders) +
flowsheet_solver.py (cómo procesa duties hardcoded vs calculados).

LO QUE NECESITO AL FINAL: explicación de dónde salen esos números,
y si son defendibles (referencia técnica) o estimaciones del autor.
Esto alimenta el bloqueante T3 del ROADMAP.

CONSTRAINT: solo lectura. No modificar nada.
```

---

## PLANTILLA 2 — Aplicar parche del ROADMAP

**Usar cuando:** vas a atacar un parche P<N> ya documentado. Querés que armemos juntos el prompt para Claude Code.

```
[BLOQUE COMÚN ARRIBA]

QUÉ HACER EN ESTA SESIÓN

TIPO: Aplicar parche del ROADMAP

PARCHE A ATACAR: [REEMPLAZAR con ID del ROADMAP, ej: "P1"]

CONFIRMACIÓN:
- Leé la entrada de [PARCHE] en docs/ROADMAP.md
- Verificá las dependencias (si tiene bloqueantes T<N>, confirmá que
  están resueltas).
- Si la entrada del ROADMAP está desactualizada respecto al estado del
  repo, AVISÁ antes de avanzar.

WORKFLOW:
1. Verificá el estado del repo EN VIVO para los archivos que el
   parche va a tocar.
2. Si hay matices o decisiones de diseño que el ROADMAP no anticipó,
   proponémelos antes de armar el prompt para Claude Code.
3. Armá el prompt para Claude Code (formato similar al de PRs
   anteriores — verificación previa, cambios específicos, criterio de
   aceptación con chequeos verificables).
4. Yo paso el prompt a Claude Code en sesión separada.
5. Cuando vuelva con el reporte de Claude Code, analizamos juntos
   antes de mergear.

ENTREGABLE DE ESTA SESIÓN:
- Prompt completo para Claude Code, listo para copy-paste.
- Predicción honesta de impacto (qué números van a cambiar, qué tests
  pueden romper).
- Si el parche descubrió matices que el ROADMAP no anticipó, propuesta
  de actualizar ROADMAP.md y/o DECISIONS.md.

CONSTRAINT:
- NO armes el prompt si las dependencias del ROADMAP no están resueltas.
  En ese caso, decímelo y discutimos qué hacer.
- NO inventes parches que no están en el ROADMAP. Si querés proponer
  uno nuevo, usá la plantilla 3 (Discusión de diseño).
```

**Ejemplo concreto de uso:**

```
[BLOQUE COMÚN]

QUÉ HACER EN ESTA SESIÓN

TIPO: Aplicar parche del ROADMAP

PARCHE A ATACAR: T1 (implementar is_phase_at_TP en thermo_db.py)

CONFIRMACIÓN: Leé la entrada T1 del ROADMAP. T1 no tiene bloqueantes.

WORKFLOW: estándar de Plantilla 2.

ENTREGABLE: prompt para Claude Code que implemente la función con
Antoine + comparación con P_sat. Una vez aplicado, podemos atacar
P7 (que está bloqueado por T1).

CONSTRAINT: NO mezclar T1 con P7 en el mismo prompt — son tickets
separados.
```

---

## PLANTILLA 3 — Discusión de diseño

**Usar cuando:** tenés una idea nueva, querés evaluar un cambio arquitectónico, o estás considerando un parche que NO está en el ROADMAP. Necesitás razonar antes de cualquier código.

```
[BLOQUE COMÚN ARRIBA]

QUÉ HACER EN ESTA SESIÓN

TIPO: Discusión de diseño

TEMA: [REEMPLAZAR — frase corta describiendo el tema]

CONTEXTO:
[REEMPLAZAR — explicar qué dispara la discusión. Ejemplo: "Estoy
pensando en agregar soporte para reactores de membrana al motor.
Quiero saber si es factible, qué implicaría, y si tiene sentido
hacerlo dado el estado actual."]

PREGUNTAS CONCRETAS:
[REEMPLAZAR — lista numerada de preguntas específicas. Las preguntas
abiertas tipo "qué opinás" rinden poco. Mejor:
  1. ¿Existe ya algo parecido en el motor (reactores de capa 5)?
  2. ¿Qué archivos habría que tocar?
  3. ¿Hay precedente en sim-comerciales (Aspen, Hysys)?
  4. ¿Es proyecto de 1 semana o 1 mes?]

LO QUE NECESITO AL FINAL:
- Respuestas a las preguntas concretas.
- Si es razonable hacerlo: propuesta de cómo se vería, estimación de
  esfuerzo, riesgos.
- Si NO es razonable: razón clara y alternativas si las hay.
- Si la conclusión es "sí pero más adelante": entrada nueva en
  ROADMAP.md (P<N+1>) con la propuesta.

CONSTRAINT:
- NO armes prompts para Claude Code en esta sesión. Es discusión.
- NO modifiques archivos del repo, ni los .md.
- Si la discusión termina en una decisión de diseño tomada, agregala
  como entrada D-<CAT>-<N> al DECISIONS.md (solo la entrada, no
  cambies otras).
```

**Ejemplo concreto de uso:**

```
[BLOQUE COMÚN]

QUÉ HACER EN ESTA SESIÓN

TIPO: Discusión de diseño

TEMA: ¿Vale la pena implementar Rachford-Rice multi-fase para
flash trifásico (V-L-L)?

CONTEXTO: Hoy `solve_flashes` usa Rachford-Rice estándar V-L. Un
usuario me preguntó si Pedro-Tesis soporta separación trifásica
(agua + hidrocarburo + vapor). Hoy NO. Quiero saber si vale la
pena agregarlo.

PREGUNTAS CONCRETAS:
1. ¿Hay procesos en los 41 ejemplos que necesiten trifásico?
2. ¿Qué esfuerzo es agregar V-L-L a `solve_flashes`?
3. ¿Cómo lo hace Aspen y por qué?
4. ¿Hay un atajo (e.g., asumir miscibilidad total en algunos casos)
   que cubra 80% del valor con 20% del esfuerzo?

ENTREGABLE: respuestas + recomendación. Si sí, entrada P14 en ROADMAP.

CONSTRAINT: solo discusión, sin prompts ni cambios.
```

---

## PLANTILLA 4 — Revisión de PR

**Usar cuando:** Claude Code ya armó un PR y querés que lo revise antes de mergear. Especialmente útil si el reporte de Claude Code es ambiguo o el diff es complejo.

```
[BLOQUE COMÚN ARRIBA]

QUÉ HACER EN ESTA SESIÓN

TIPO: Revisión de PR

PR A REVISAR: [REEMPLAZAR con URL, ej: "https://github.com/Eltiokarma/Pedro-Tesis/pull/20"]

QUÉ DEBERÍA HACER EL PR:
[REEMPLAZAR — qué parche o cambio estaba implementando. Idealmente
con referencia al ID del ROADMAP. Ej: "Implementar P7 (phase
detection rigurosa) usando is_phase_at_TP."]

WORKFLOW:
1. Mirá el diff del PR (bajá los archivos modificados del head del PR).
2. Verificá que:
   - El cambio coincide con lo que el ROADMAP especifica.
   - No toca archivos que no debería tocar.
   - Los tests siguen pasando (mirar la sección de CI del PR si
     existe, o pedirme que confirme).
   - La lógica es correcta (no hay shortcuts ni hacks).
3. Listá:
   - LO BUENO: qué hizo bien Claude Code.
   - LO PREOCUPANTE: cualquier matiz que requiera atención (no
     necesariamente bloqueante, pero notable).
   - LO BLOQUEANTE: cualquier cosa que requiera fix antes de mergear.
4. Recomendación: MERGEAR / PEDIR CAMBIOS / RECHAZAR.

ENTREGABLE:
- Reporte de revisión con las 3 listas de arriba.
- Si hay que pedir cambios: redacción del comentario para devolverle
  a Claude Code.
- Si todo OK: confirmar que se puede mergear + actualizar ROADMAP.md
  moviendo la entrada de pendiente a aplicada.

CONSTRAINT:
- NO mergees el PR vos. Eso lo hago yo.
- Si el PR cambia archivos del catálogo o números clave, recomendá
  que corramos audit_phase2.py post-merge para validar.
```

---

## PLANTILLA 5 — Sesión libre / exploración

**Usar cuando:** no tenés un objetivo claro pero querés trabajar en el proyecto. Esta es la plantilla menos estructurada — útil cuando estás "viendo qué hacer".

```
[BLOQUE COMÚN ARRIBA]

QUÉ HACER EN ESTA SESIÓN

TIPO: Sesión libre / exploración

ESTADO MENTAL:
[REEMPLAZAR — describí cómo estás. Ejemplo: "No tengo plan claro,
pero quiero avanzar algo. Estoy mirando el ROADMAP y dudo entre
P1 y T1." O: "Hace 2 semanas no toco esto, recordame dónde estábamos."]

OPCIONES QUE ESTOY CONSIDERANDO:
[REEMPLAZAR — si tenés varias opciones, listalas. Si no, decímelo.
Ejemplo:
  - Atacar P1 (DOF audit automático)
  - Atacar T1 (is_phase_at_TP)
  - Hacer una limpieza del catálogo (D2)
  - Otra cosa que sugieras]

CONSTRAINT DE TIEMPO:
[REEMPLAZAR — cuánto tiempo tenés. Ej: "1h", "tarde libre",
"semana entera"]

QUÉ NECESITO DE VOS:
1. Refresh rápido del estado del proyecto (qué está hecho, qué
   pendiente, qué prioritario).
2. Recomendación de qué hacer en esta sesión según mi tiempo
   disponible y prioridades del ROADMAP.
3. Una vez que decidamos, cambiar a otra plantilla (1, 2, 3 o 4)
   según corresponda.

CONSTRAINT:
- Esta plantilla es solo para arrancar. La conversación real va a
  derivar a otra plantilla en algún momento.
```

---

## Cómo actualizar este documento

Si en alguna sesión descubrís que falta un tipo de plantilla común que no está cubierto, agregala acá con:

- Nombre claro
- "Usar cuando..." (criterio de uso)
- Estructura completa
- Ejemplo concreto

No agregar plantillas para casos one-off — solo si vas a usar el patrón al menos 3 veces.

---

## Notas operativas

**Sobre el bloque común:**
- Si en alguna sesión las reglas de trabajo no se cumplieron (Claude trabajó de memoria, no leyó los .md), eso es señal de prompt mal armado. Mejorar la plantilla, no improvisar.

**Sobre las plantillas:**
- Si te encontrás escribiendo el mismo tipo de prompt varias veces sin usar plantilla, **agregalo acá**.
- Las plantillas son patrones. Si una sesión real necesita mezclar dos plantillas (ej: discusión + parche al final), está bien — usá la base más cercana y aclará el matiz en "QUÉ HACER".

**Sobre la mantención:**
- Cada vez que se agrega un parche al ROADMAP, este archivo NO necesita actualización (las plantillas son agnósticas al contenido del ROADMAP).
- Este archivo solo cambia cuando descubrimos un patrón nuevo o ajustamos el workflow Claude / Claude Code / tu rol.

---

**Estado del motor:** ver `docs/AUDIT.md`.
**Parches pendientes:** ver `docs/ROADMAP.md`.
**Decisiones de diseño:** ver `docs/DECISIONS.md`.
