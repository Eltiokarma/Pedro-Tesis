# Diseño — Motor de reciclos multi-tear

**Estado:** PLANO DE ARQUITECTURA (fase de diseño). Cero código de motor escrito.
Entregable para aprobar la arquitectura ANTES de construir el solver multi-tear.

**Base:** main de facto con S1 (#87, `_choose_tear` excluye lockeados), EOS (#85)
y flash+selector (#86) mergeados.

---

## 0. Problema (medido, no asumido)

El Wegstein del motor (`_solve_recycle_wegstein`) **tea un solo stream escalar
por SCC**. Funciona para SCCs con **un** reciclo independiente, pero **colapsa**
cuando un SCC contiene **varios** reciclos: un tear no puede romper N lazos.

### 0.1 Dimensionamiento sobre los 41 (circuit rank = E_int − V + 1)

| ejemplo    | #SCC | maxSCC (bloques) | reciclos indep. | tipo | resuelve hoy |
|------------|:----:|:----------------:|:---------------:|------|--------------|
| haber_rec  | 1 | 5  | 1 | mono | Wegstein ✓ (ancla mono) |
| hda        | 1 | 8  | 1 | mono | closure (sobre-pinneo) |
| quimpac    | 1 | 7  | 1 | mono | closure |
| industrial | 3 | 7  | 3 | **paralelos** (3 SCC separados, 1 ciclo c/u) | closure |
| gas_sweet  | 1 | 9  | 3 | **acoplados** (1 SCC) | closure (sobre-pinneo) |
| hda_full   | 1 | 14 | 3 | **acoplados** (1 SCC: gas + tolueno + reactor) | closure (sobre-pinneo) |

**Lectura:**
- **3 mono-reciclo** (haber_rec, hda, quimpac): el motor actual ya basta.
- **industrial** es "multi" pero **trivial**: 3 SCC *separados* → el loop
  `for scc in recycle_sccs` ya los trata independientemente. **No** es el problema.
- **El problema real son los reciclos ACOPLADOS dentro de un SCC**: `gas_sweet`
  (3 ciclos / 9 bloques) y `hda_full` (3 ciclos / 14 bloques). Hoy sobreviven
  solo porque están **sobre-pinneados** con locks internos que dejan que el
  closure los deduzca por balance ("frozen workaround").

### 0.2 Caso real más simple para validación: `gas_sweet`
3 ciclos en 9 bloques (vs. 14 de hda_full). Es el primer caso *acoplado* real
contra el que probar el motor, además del ancla sintética (§3).

### 0.3 Síntoma del colapso (medido en hda_full y en el ancla sintética)
Al deslockear los internos para "encender" el loop:
- `_choose_tear` (incluso con S1) elige **`S-2`** —la línea de feed al reactor—,
  no un reciclo real, porque S-2 también es back-edge (su destino F-101 recibe
  feed externo) y rankea igual que los reciclos verdaderos.
- Wegstein corre **1 iteración**, el tear se congela en el guess (`14263.5`), la
  fuente del tear da 0 → sale con `converged=False`.
- El interior colapsa a 0 (`S-gas-recic`, `S-gas-pre`, `S-liq` = 0); `status=error`.
- **Activar el flash de V-101 (S2-C) NO rescata** mientras el tear esté mal
  elegido y Wegstein aborte en 1 iter. → S2-B/S2-C son **insuficientes solos**.

---

## 1. Cómo lo resuelven los simuladores serios (DWSIM + teoría)

**DWSIM** (sequential-modular, open source). El usuario coloca **bloques
lógicos `Recycle`** explícitos en los puntos de corte (tears). Cada `Recycle`
converge por **sustitución sucesiva / Wegstein / autovalor dominante**, teando
el vector completo {T, P, mass flow, composición}. Para reciclos **acoplados**,
DWSIM ofrece un **Global/Simultaneous solver** que resuelve **todos los tears a
la vez con Broyden** (cuasi-Newton); usuarios reportan que el modo Broyden
converge casos donde el Wegstein local no.

> "There are two methods for the recycle block — the Wegstein algorithm and the
> Dominant eigenvalue method... The recycle block works much better if you use
> the **Broyden Global Convergence** method." (DWSIM manual / foro)

**Teoría de tearing** (selección de tears mínima):
- **Barkley & Motard (1973):** buscar el **menor número de tears** que rompan
  todos los ciclos.
- **Upadhye & Grens (1975):** familias **no-redundantes** de tears; elegir el
  set que **minimiza el máximo nº de veces que un unit loop es teado**.
- El nº mínimo de tears de un SCC = su **circuit rank** `E_int − V + 1`
  (= los 3 que medimos en hda_full / gas_sweet).

**Adaptación al motor propio (no copiar código):** partición del flowsheet en
SCCs (ya tenemos Tarjan) + dentro de cada SCC, selección de un **set de tears
mínimo** (circuit rank) reciclo-aware + convergencia **simultánea** (Broyden)
sobre el vector apilado de todos los tears del SCC.

**Fuentes:**
- DWSIM Recycle.vb — https://github.com/DanWBR/dwsim/blob/windows/DWSIM.UnitOperations/LogicalBlocks/Recycle.vb
- DWSIM repo — https://github.com/DanWBR/dwsim
- Motard, *Exclusive tear sets for flowsheets*, AIChE J. 27(5) (1981) — https://aiche.onlinelibrary.wiley.com/doi/10.1002/aic.690270504
- *Partitioning and Tearing of Networks Applied to Process Flowsheeting* — https://www.researchgate.net/publication/41719546

---

## 2. Decisiones de arquitectura

### 2.1 Descomposición del SCC → set de tears mínimo
1. Tarjan (ya existe) → SCCs. Cada SCC con circuit rank ≥ 1 es un reciclo.
2. Dentro del SCC, calcular el **set de tears mínimo** de tamaño `E_int − V + 1`
   que rompe TODOS los ciclos. Algoritmo: enumeración de ciclos fundamentales
   (spanning tree → back-edges) y selección greedy/Motard de back-edges que
   cubran cada ciclo, con desempate por la heurística reciclo-aware (§2.2).
   - El **spanning tree** de un grafo conexo deja exactamente `E_int − V + 1`
     back-edges → ése es un set de tears válido de tamaño mínimo. Es el punto de
     partida natural y barato; Motard solo si querés optimizar el desempate.

### 2.2 Selección de tear reciclo-aware (extiende S1)
Ranking de candidatos a tear (de mayor a menor preferencia):
1. `role == "recycle"` **y NO `mass_flow_locked`** (S1 ya excluye lockeados).
2. back-edge cuya composición es de **reciclo real** (gas/purga/recycle), no una
   línea de proceso troncal.
3. **penalizar** back-edges que son meramente "feed lines" (destino con feed
   externo) como `S-2` — hoy ganan por empate; deben perder frente a un reciclo.
4. preferir el stream de **menor caudal esperado** (rompe el lazo con el menor
   error de arranque) — heurística clásica de tearing.

> Esto corrige el bug medido: hoy `_choose_tear` elige `S-2` sobre el reciclo de
> gas. La extensión debe elegir `S-gas-pre` y `S-tol-recic` (un tear por ciclo).

### 2.3 Estrategia de convergencia
- **Por SCC mono-reciclo:** mantener el Wegstein escalar actual (haber_rec sigue
  igual → ancla protegida, golden byte-idéntico).
- **Por SCC multi-reciclo acoplado:** **simultáneo con Broyden** sobre el vector
  apilado de los N tears (N = circuit rank). Broyden porque los tears acoplados
  **interactúan** (cambiar el gas mueve el tolueno) — Wegstein por-tear ignora el
  acoplamiento y oscila/colapsa.
- **Vector de estado del tear:** {mass, composición (vector), T}. La composición
  cambia con la reacción/separación → es el "caso vectorial pendiente". Broyden
  global tea el vector completo; el jacobiano aproximado captura el acoplamiento
  composición↔masa.
- **Fallback:** si Broyden no converge en K iters, degradar a sustitución
  sucesiva amortiguada (damping) y reportar honestamente `converged=False`
  (nunca un "converged" falso a 0 — la regla de oro medida en este proyecto).

### 2.4 Manejo de los locks internos (el "frozen workaround")
hda_full tiene 5 locks internos (`S-2, S-4, S-gas-recic, S-11, S-tol-recic`) que
hoy hacen al SCC closure-solvable. Clasificación propuesta:
- **Frontera de diseño legítima (CONSERVAR):** specs del usuario — caudal de
  feed externo, **purga** (`S-purga`, como `S-NH3` en haber_rec), producto. Estos
  pinean el split de forma física y son correctos.
- **Parche de congelamiento (RACIONALIZAR):** locks de streams *internos* puestos
  solo para que el closure dedujera el SS sin Wegstein (`S-2, S-4, S-gas-recic,
  S-11, S-tol-recic`). Una vez que el motor converja el loop vivo, estos se
  **deslockean** y pasan a ser variables resueltas.
- **Decisión:** la racionalización de locks se hace **en la capa que enciende el
  loop** (ver §3, capa 5), no antes — para que cada deslockeo esté respaldado por
  un motor que ya converge el caso. **No tocar locks en la fase de diseño.**

---

## 3. Plan de capas verificables (secuencia de PRs)

Cada capa es un PR medible contra el ancla sintética (`tests/test_multitear_anchor.py`)
y/o gas_sweet/hda_full, con haber_rec como ancla mono intacta.

| capa | PR | qué construye | ancla / verificación | goldens |
|:----:|----|---------------|----------------------|---------|
| 1 | partición | enumeración de ciclos fundamentales + set de tears mínimo (circuit rank) por SCC | unit test: el ancla sintética arroja 2 tears; hda_full arroja 3 | ninguno |
| 2 | tear reciclo-aware | extender `_choose_tear` → devolver **lista** de tears, ranking §2.2 | unit test: elige R1+R2 (ancla), S-gas-pre+S-tol-recic (hda_full), NO S-2 | ninguno (mono sigue igual) |
| 3 | Wegstein/Broyden multi-tear | bucle simultáneo sobre el vector de N tears | **ancla sintética converge a SS exacto** (xfail→pass); haber_rec byte-idéntico | ninguno aún |
| 4 | S2-B (no-deducción) | el tear no se deduce por balance en `_solve_mass_iteration` | ancla + hda_full live: interior >0, balance cierra | ninguno aún |
| 5 | S2-C (flash por degeneración) | separador pasivo degenerado → flash activo (vía `_flash_method` de #86) | gas_sweet/hda_full: V-101 produce vapor real | ninguno aún |
| 6 | racionalizar locks + encender | deslockear los parches internos de hda_full/gas_sweet; loops vivos | gate: **solo hda_full/gas_sweet** mueven golden; otros 39 byte-idénticos | **hda_full, gas_sweet** |

**Orden no negociable:** 1→2→3 deben estar antes de 4→5 (S2-B/S2-C son inútiles
si el tear está mal elegido y Wegstein aborta, como medimos). La capa 6 (mover
goldens) es la última y solo después de que el motor converja el loop vivo.

---

## 4. Riesgos y anclas

| riesgo | mitigación / ancla |
|--------|--------------------|
| romper mono-reciclo (haber_rec, hda, quimpac) | capa 1-3 dejan el path mono **byte-idéntico**; haber_rec es ancla dura en cada PR |
| Broyden no converge / oscila | fallback a sustitución amortiguada + `converged=False` honesto; nunca "converged" a 0 |
| "converged" falso (el bug histórico) | invariante de aceptación: **interior del loop > 0 Y balance elemental cierra**, no solo norma del tear |
| mover goldens de más | capa 6: assert **solo** hda_full+gas_sweet cambian; los otros 39 byte-idénticos o se investiga |
| caso vectorial composición | Broyden tea el vector {mass, comp, T}; el ancla sintética es mono-componente (aísla la mecánica de masa); gas_sweet/hda_full ejercitan composición |
| sobre-pinneo enmascarando bugs | el ancla sintética NO está pinneada → fuerza el motor de verdad (hoy colapsa, como debe) |

### Anclas de regresión por tipo
- **Mono-reciclo:** `haber_rec` (golden de producción) — protege el path escalar.
- **Multi acoplado sintético:** `tests/test_multitear_anchor.py` — SS exacto a
  mano, no pinneado, mono-componente. **xfail hoy** (motor no existe), debe
  **flipear a pass** en la capa 3.
- **Multi acoplado real:** `gas_sweet` (más simple) y `hda_full` — validación de
  composición/flash; sus goldens se mueven recién en la capa 6.

---

## 5. Resumen ejecutivo

- El problema NO es "multi-reciclo" en general (industrial = 3 SCC paralelos ya
  funciona); es **reciclos acoplados en un mismo SCC** (gas_sweet, hda_full).
- El plan original S2-B+S2-C es **insuficiente**: primero hay que arreglar
  **selección de tear (set mínimo, reciclo-aware)** y **convergencia simultánea
  (Broyden)**. Medido: con el tear mal elegido, ni el flash activo rescata.
- Approach validado contra DWSIM (Recycle blocks + Global Broyden) y la teoría de
  tearing (Motard / circuit rank).
- Ancla sintética lista: dos reciclos acoplados, SS exacto a mano, hoy colapsa
  (xfail) → será la prueba dura de la capa 3.
- Secuencia de 6 capas, cada una medible; los goldens se mueven recién en la
  última, y solo hda_full+gas_sweet.
