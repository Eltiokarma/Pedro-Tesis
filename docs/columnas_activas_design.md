# Diseño — Columnas activas (Frente B)

**Estado:** PLANO DE ARQUITECTURA + **CAPA 1 (terminales limpias) EJECUTADA**.
El diseño no escribió código de motor; la Capa 1 **activa** la columna terminal
limpia `acetic/T-101` (sin tocar el solver: el motor FUG ya existe) y mueve solo
su golden. Ver §6 (Estado de ejecución).

> **Progreso:** Capa 1 (este frente) — `acetic/T-101` **ACTIVADA** ✅ ;
> `dist_eth_az/T-101` **DIFERIDA** (azeotropía, ver §6). Gate 41/41 (solo el
> golden de acetic cambió).

**Base:** rama viva con #97–#101 mergeados (HEAD = merge #101,
`feat(chloralkali)…`). Gate `python gate_examples.py` → **41/41 verde** al
abrir y al cerrar este PR.

**Hermano de proyecto:** este frente es la pieza que `docs/multitear_design.md`
§3.1 dejó explícitamente **diferida**: *"encenderlo bien exige robustecer la
propagación de columnas en el loop vivo (pieza profunda)"*. Es decir, columnas
activas **es** la "Capa 6 + propagación de columnas en loop vivo" del proyecto
multi-tear.

---

## 0. Línea base (medido, no asumido)

### 0.1 Gate
`python gate_examples.py` → **41/41 round-trippean idéntico** (exit 0). Este PR
agrega solo un doc y un test sintético → el gate sigue 41/41.

### 0.2 Inventario de columnas — medido sobre los 41 JSON (HEAD actual)

Conteo directo (`eq_type == "Tower (column shell)"` ∪ `column_active==True`):

| | n |
|---|---:|
| Columnas totales (Tower) | **19** |
| **Activas** (`column_active=True`) | **6** |
| **Pasivas** (`column_active=False`) | **13** |

> **Reconciliación con el brief y con `inventario_hardcode.md` (que dicen 14
> pasivas):** la 14ª era `hydraulic/T-101`, **re-tipada Tower→Vessel** en el PR
> de "columnas que no separan" (`inventario_hardcode.md` §6.6: agua pura no se
> separa en una columna; golden byte-idéntico). Hoy ya **no es** una columna.
> El universo vigente es **13 pasivas**. El resto del documento usa 13.

#### Las 6 activas (el motor YA calcula la separación)

Todas 1-in/2-out, **ninguna en loop**, método FUG shortcut:

| ejemplo | bloque | LK / HK | en loop |
|---|---|---|:--:|
| air_sep | T-101 | nitrogen / oxygen | no |
| distillation | T-101 | benzene / toluene | no |
| ethanol | T-101 | ethanol / water | no |
| ethylene_crk | T-101 | ethylene / ethane | no |
| industrial | T-201 | methanol / water | no |
| rxn_flash_col | T-101 | ethanol / water | no |

#### Las 13 pasivas (split declarado a mano; `column_LK`/`column_HK` vacíos)

| ejemplo | columna | qué separa (feed → productos) | term./loop | salidas comp-locked |
|---|---|---|:--:|---|
| acetic | T-101 | AcOH/metanol → S-vap (livianos) / S-fondo (AcOH) | **terminal**¹ | S-vap, S-fondo |
| cdu | T-101 | crudo → 4 cortes (nafta/kero/diésel/residuo) | terminal | 4 cortes |
| dist_eth_az | T-101 | etanol/agua (azeotrópica) → tope/fondo | terminal | S-vap-tope, S-fondo-liq |
| gas_sweet | T-101 | absorbedor de aminas: gas+MDEA → gas dulce / amina rica | **loop** | S-gas-dulce, S-rich-amine |
| gas_sweet | T-102 | stripper de aminas: amina rica → ácidos / amina pobre | **loop** | S-top-strip, S-lean-bot |
| hda | T-101 | benceno/tolueno → S-7 / S-8 | **loop** | S-7, S-8 |
| hda_full | T-101 | benceno/H₂/CH₄/tolueno → livianos / S-8 | **loop** | S-7-light, S-8 |
| hda_full | T-102 | benceno/tolueno → S-10 / S-11 | **loop** | S-10, S-11 |
| hda_full | **T-103** | benceno/tolueno → S-13 / S-14 (hoy ≈ pass-through) | **loop** | S-13, S-14 |
| hno3 | T-401 | absorbedor reactivo NOₓ→HNO₃ (placeholder reactivo) | terminal | A13-HNO3-crudo, A14-tail-gas |
| quimpac | T-301 | secado de Cl₂ (Cl₂/H₂SO₄/H₂O) → ácido gastado / Cl₂ seco | terminal | S-acid-spent, S-cl2-dry |
| talara | T-101 | CDU: crudo → 6 cortes | terminal | 6 cortes |
| talara | T-201 | torre de vacío: → VGO / resid-vac (hoy no fracciona) | terminal | C7-VGO, C8-resid-vac |

¹ `acetic/T-101` es terminal en topología, pero su líquido alimenta `V-101`
(separador pasivo) — relevante para FASE 2.2 (cascada de placeholder).

**Reparto loop/terminal:** 6 pasivas en loop de reciclo (gas_sweet ×2, hda ×1,
hda_full ×3) + 7 terminales. **Total de salidas comp-locked de columnas
pasivas: 32 streams** (medido).

---

## 1. ¿El motor de columnas YA existe? — VEREDICTO

### 1.1 El motor existe y está completo

Tres módulos forman un motor de columnas de nivel sequential-modular, **ya
construido, probado e integrado al solver**:

- **`distillation_fug.py` — FUG shortcut (COMPLETO).**
  - `fenske()` (N mínimo a reflujo total), `underwood()` (R mínimo, raíz θ por
    bisección, multicomponente), `gilliland()` (N real, fit Eduljee 1975),
    `kirkbride()` (etapa de feed), `relative_volatility()` (α vía NRTL+Antoine,
    fallback Raoult).
  - `design_column(...)` orquesta todo: balance global D/B por palanca,
    α geométrico tope-fondo, detección de **azeótropo pasado** (α_top<1 →
    warning honesto), Underwood real para feeds multicomp o q≠1, Fenske-
    Hengstebeck para no-keys, estimación de Q_cond/Q_reb.
  - Validado en `tests/test_distillation_p1.py` (binario, azeótropo, multicomp,
    q dinámico).

- **`distillation_wanghenke.py` — MESH riguroso (COMPLETO).**
  - Wang-Henke: balance M por componente vía **Thomas tridiagonal**, corrección
    de T por **bubble-point**, balance de energía para V_n, sub-relajación
    (λ=0.5) cerca de azeótropos, modo `spec` que bisecta D/F hasta la pureza
    objetivo y reporta `converged=False` si es inalcanzable.
  - Validado en `tests/test_distillation_p2.py` / `_p3.py` (convergencia,
    perfil V variable, cierre de energía <5 %, conservación de componentes
    <0.1 %).

- **`distillation_simple.py` — flash binario / Rayleigh / arrastre con vapor**
  (soporte, no diseño de columna).

### 1.2 Cómo lo integra el solver hoy

`flowsheet_solver.solve_columns()` (≈ líneas 2351-2695):

1. Filtra bloques con `column_active==True`.
2. Lee LK/HK y specs del bloque (`column_x_D_LK`, `column_x_B_LK`,
   `column_R_factor`, `column_method`, `column_N_stages`).
3. Identifica feed (1ª corriente con masa+comp en ambos keys) y destila/fondo
   por nombre de puerto ("vapor/tope" vs "liq/fondo") o riqueza en LK.
4. Llama `design_column()` (FUG). Si `column_method=="wanghenke"`, refina con
   Wang-Henke (mol↔masa). Si >2 componentes, distribuye no-keys con
   Fenske-Hengstebeck.
5. **Escribe salidas** a las corrientes: composición (x_D/x_B), mass_flow (si
   no está locked, desde D/F), T (bubble/dew), P, fase, y duty al bloque.

**Integración con reciclos:** `solve_columns(fs)` se llama tanto en el lazo
principal como **dentro del lazo Wegstein** (junto a `solve_flashes`,
`solve_mechanical_separators`, `solve_splitters`, `auto_propagate_compositions`).
Es decir, una columna activa **ya participa** de la iteración de tear como
cualquier flash/separador.

### 1.3 EL VEREDICTO: **CASO ACTIVAR** (no construir)

> **El motor de columnas EXISTE, está COMPLETO y PROBADO, y está INTEGRADO al
> solver de reciclos. Las 6 columnas activas pasan el gate 41/41 hoy. Por lo
> tanto el proyecto es ACTIVAR el motor existente donde corresponde — análogo
> exacto al flash EOS que existía y se activaba por degeneración — NO construir
> un motor de columnas.**

Evidencia: §1.1 (los 3 módulos completos + sus tests verdes), §1.2 (el dispatch
en `solve_columns` + su llamada dentro del Wegstein), §0.2 (6 columnas activas
reales que round-trippean en el gate).

#### Matiz crítico (no es 100 % "activar y listo")

Hay **una** capacidad que el motor NO tiene robusta todavía, medida en
`multitear_design.md` §3.1: **la propagación de una columna DENTRO de un loop
VIVO**. Las 6 columnas activas existentes están **todas fuera de loop**
(terminales). Cuando hda_full se intentó encender vivo, *"el tren de destilación
T-101/102/103 no propaga el reciclo de tolueno en la pasada viva → punto fijo
espurio (el reciclo de tolueno colapsa a 0)"*. O sea:

- **Activar columnas terminales** = puro ACTIVAR (motor probado, riesgo bajo).
- **Activar columnas en loop vivo** = ACTIVAR + endurecer la propagación
  columna↔tear (la pieza no trivial). Sigue siendo "activar+endurecer", no
  "construir desde cero" — el FUG/MESH ya existe; lo que falta es que su salida
  alimente bien el siguiente paso del tear sin colapsar.

**Conclusión de alcance:** proyecto **MEDIANO-GRANDE**, escalonado: la mayoría
es ACTIVAR (terminales), con un núcleo más caro (3-6 columnas en loop) que
requiere endurecer la propagación en vivo. **No** es el proyecto GRANDE de
"construir FUG/MESH".

### 1.4 Cómo lo resuelve DWSIM (referencia, sin copiar código)

- **Shortcut + riguroso:** DWSIM ofrece `Shortcut Column` (FUG, para
  inicializar/estimar N, R, cortes) y columnas rigurosas
  (`Distillation`/`Absorption` con Inside-Out o Simultaneous Correction sobre
  las ecuaciones MESH). El patrón estándar de la industria es **FUG para
  inicializar → riguroso para converger**, exactamente el FUG→Wang-Henke que ya
  tenemos.
- **Columna dentro de un loop:** DWSIM trata la columna como otra unit-op del
  esquema sequential-modular; el bloque lógico `Recycle` en el tear converge el
  vector {T, P, flujo, composición} por Wegstein/eigenvalor, y para reciclos
  acoplados usa el **Broyden global**. La columna se resuelve (rigurosa) en cada
  pasada del tear; su salida es la entrada del siguiente eslabón del lazo. Si la
  columna no propaga bien un componente reciclado, el tear converge a un SS
  espurio — es el mismo fenómeno medido en hda_full/T-103.
- **Lección de diseño:** la columna en loop debe (a) recibir su feed del tear ya
  actualizado, (b) recalcular el split SIEMPRE (no deducirlo por balance — la
  regla S2-B del multi-tear), y (c) propagar TODOS los componentes (incl. los
  que reciclan, p. ej. tolueno sin convertir) hacia el destilado/fondo correcto.

Fuentes: DWSIM docs (Shortcut/Rigorous Column, Recycle block) —
https://dwsim.org/ ; `docs/multitear_design.md` §1 (Recycle + Broyden global);
Henley-Seader, *Separation Process Principles* (FUG y MESH).

---

## 2. Dimensionar el impacto

### 2.1 Clasificación de las 13 pasivas

| clase | columnas | nota |
|---|---|---|
| **A. Activar limpio** (terminal, par LK/HK claro) | acetic/T-101 ✅ activada (Capa 1); dist_eth_az/T-101 ⏸ diferida | acetic = binario metanol/acético limpio (α=6.1), activado. dist_eth_az pide x_D=0.956 etanol = **el azeótropo** (FUG mide α_top=0.95<1) → necesita destilación azeotrópica/extractiva con entrainer (frente aparte) |
| **B. Activar con pseudo-cortes** (terminal, multi-corte sobre pseudo-componente) | cdu/T-101, talara/T-101, talara/T-201 | NO son columnas binarias: son fraccionadoras de crudo. Requieren **pseudo-componentes/cortes por punto de ebullición**, no FUG binario → dependen de otro frente |
| **C. Placeholder reactivo** | hno3/T-401 | absorbedor reactivo (NOₓ→HNO₃); pertenece al frente de química, no al de separación |
| **D. Acopladas a loop vivo** | gas_sweet/T-101, gas_sweet/T-102, hda/T-101, hda_full/T-101, hda_full/T-102, hda_full/T-103 | el núcleo caro: requieren la propagación en loop vivo (§1.3 matiz) + el multi-tear FROZEN |
| **E. Legítima pasiva por ahora** | quimpac/T-301 | "secado" de Cl₂ con H₂SO₄ — más absorción/contacto que destilación; activarla como FUG sería mis-modelo |

> Las clases B (pseudo-cortes) y C (reactivo) y E (no-destilación) **no son
> destilación binaria** → no las habilita este motor; se documentan como
> fuera-de-alcance del frente "columnas activas". El frente real son **A**
> (2 limpias) + **D** (6 en loop).

### 2.2 Impacto sobre el hardcode (cruce con `inventario_hardcode.md`)

- **Salidas de columnas pasivas comp-locked: 32 streams** (medido, §0.2). Son
  composiciones que el motor recomputaría al activar.
- De esas, las de clase A+D (acetic, hda, hda_full ×3, gas_sweet ×2) suman
  **~12 streams intermedios** que hoy son hardcode dentro/cerca de loops y que
  el motor resolvería; el resto (B/C/E: cdu, talara ×8, hno3, quimpac) son
  cortes/terminales que **no** dependen de este motor.
- **12 puntos de hardcode en loops vivos** (`inventario_hardcode.md` §3.3): 6
  columnas pasivas + 6 separadores pasivos en loop. Activar las columnas en loop
  es **prerequisito** para encender gas_sweet/hda/hda_full (hoy FROZEN).
- **Placeholders desbloqueados (acetic/beer):** `inventario_hardcode.md` §6.7
  los dejó DIFERIDOS porque el reactor conecta pero su salida cae en un
  **separador pasivo aguas abajo** cuyo split el motor no calcula. Activar esa
  separación (columna acetic/T-101 + flash V-101) es lo que desbloquea
  acetic/beer → **2 placeholders** dependen de este frente.

### 2.3 ¿Mueve goldens? ¿faltan parámetros?

- **Sí, activar mueve el golden** de cada ejemplo afectado: hoy las salidas son
  hardcode; al calcularlas, los números cambiarán (salvo que coincidan con el
  hardcode dentro de tolerancia). Cada activación es un golden nuevo, **uno por
  capa** (§4.5).
- **Parámetros faltantes:** las pasivas tienen `column_LK=""`, `column_HK=""`,
  `column_N_stages=0` y specs default (x_D=0.95, x_B=0.05, R=1.3). Faltan:
  - **LK/HK:** derivables del feed (los 2 componentes de mayor caudal con α>1).
  - **x_D/x_B (pureza):** son specs de diseño; donde el ejemplo declara una
    pureza de producto, usarla; si no, spec `[típico]` citada (p. ej. 0.95/0.05).
  - **R_factor:** `[típico] 1.3×R_min` (Turton/Seader) — ya es el default.
  - **N_stages:** lo calcula el FUG (Gilliland); no hace falta declararlo.
  - **q (fase del feed):** derivable del estado T/P del feed.
  Conclusión: **ningún parámetro es bloqueante**; todos son derivables o specs
  `[típico]` citables.

---

## 3. Ancla sintética (único código permitido)

`tests/test_columna_ancla_sintetica.py` — columna binaria **benceno/tolueno**
con **α=2.5 constante**, balance cerrado EXACTO a mano. Es ancla de regresión
del motor FUG **independiente del thermo_db** (si alguien toca
`distillation_fug.py`, este test lo clava contra el cálculo manual). NO es
ejemplo de producción, NO toca goldens.

**Cálculo manual (todo cierra exacto):**

| magnitud | fórmula | valor |
|---|---|---|
| D (palanca) | F·(z−x_B)/(x_D−x_B) = 100·0.45/0.90 | **50.0** |
| B | F−D | **50.0** |
| balance LK | F·z = D·x_D + B·x_B → 50 = 47.5+2.5 | **cierra** |
| N_min (Fenske) | ln[(0.95/0.05)²]/ln(2.5) = ln(361)/ln(2.5) | **6.42687** |
| θ (Underwood, q=1) | raíz de 1.25/(2.5−θ)+0.5/(1−θ)=0 | **10/7 = 1.42857** |
| R_min | Σαx_D/(α−θ) − 1 = 2.1 − 1 | **1.10** |
| N (Gilliland, R=1.3·R_min) | fit Eduljee | **≈14.10** |

Verificado contra las funciones del motor: coinciden a ~1e-9 (ver el
docstring del test para el desarrollo completo). **8/8 tests verdes.**

---

## 4. Arquitectura

### 4.1 Veredicto activar-vs-construir
**ACTIVAR** (§1.3). El motor FUG+Wang-Henke existe, está probado e integrado;
las 6 columnas activas pasan el gate. La única pieza a *endurecer* (no
construir) es la propagación de columnas en loop vivo.

### 4.2 Estrategia de columna
**Híbrido FUG→MESH, ya disponible:**
- **FUG (`design_column`)** para el split rápido y la inicialización (N, R,
  cortes, D/B). Es el default (`column_method="fug"`).
- **Wang-Henke (MESH)** opcional para refinar la distribución de no-keys y
  cerrar energía (`column_method="wanghenke"`), exactamente como DWSIM
  Shortcut→Rigorous.
- **Inputs:** LK/HK (derivados del feed si vacíos), x_D_LK/x_B_LK (spec o
  `[típico]`), R_factor (1.3 típico), q (del estado del feed), P_op.
- **Calcula:** N_min/N/N_feed, R_min/R, α, D/B, x_D/x_B (multicomp),
  Q_cond/Q_reb, T tope/fondo.
- **Escribe:** composición + masa + T + fase de destilado y fondo, duty al
  bloque (respetando locks: nunca pisa un stream `*_locked` por spec).

### 4.3 Integración con el resto del motor (multi-tear + flash EOS)
- **Fuera de loop (terminales):** `solve_columns` corre una vez en el lazo
  principal; el flash EOS y la propagación de composición ya consumen su salida.
  Riesgo bajo (es el patrón de las 6 activas actuales).
- **Dentro de loop (el caso clave hda_full/T-103):** la columna se resuelve en
  CADA pasada del tear (ya ocurre: `solve_columns` está en el lazo Wegstein).
  Reglas de diseño para que NO rompa el frozen ni el multi-tear:
  1. **Recalcular siempre, no deducir** (regla S2-B del multi-tear): el split de
     la columna se computa, nunca se infiere por balance del tear.
  2. **Propagar TODOS los componentes**, incl. los que reciclan (tolueno sin
     convertir). El bug medido es que T-103 hoy re-deriva a pass-through y el
     tolueno colapsa a 0 → SS espurio. La columna activa debe enviar el tolueno
     al fondo (reciclo) y el benceno al tope (producto).
  3. **Convergencia simultánea Broyden** (ya existe, capas 1-5 del multi-tear)
     sobre el vector de tears; la columna activa es una unit-op más en ese lazo.
  4. **Invariante de aceptación** (regla de oro): interior del loop > 0 **y**
     balance elemental cierra — nunca un "converged" falso a 0.
- **No tocar el frozen en diseño:** hda_full/gas_sweet siguen FROZEN con sus
  goldens hand-tuned (físicamente correctos). Encenderlos vivos es la última
  capa, y solo tras validar la propagación contra el ancla.

> **Re-validación Capa 1 (2026-06-15):** las 4 reglas siguen **vigentes** — se
> re-confirmó que `solve_columns()` corre dentro del lazo de reciclos
> (`flowsheet_solver.py:5104` lazo principal, `:5282` lazo Wegstein, `:5621`),
> así que una columna en loop ya se resuelve por pasada del tear; lo que falta
> (capas 3-5) es endurecer la propagación, no reescribir el dispatch. No hay
> desfasaje que corregir.

### 4.4 Manejo de parámetros faltantes
Ver §2.3. Resumen: LK/HK derivables del feed; x_D/x_B = spec del ejemplo o
`[típico]` citada; R_factor=1.3 `[típico]`; N por Gilliland; q del feed.
**Ninguno bloquea.** Cada spec `[típico]` se documenta en el JSON/golden con su
fuente (Turton/Seader), igual que el resto del proyecto.

### 4.5 Plan de capas verificables (secuencia de PRs)

Cada capa es medible contra el **ancla sintética** y deja el gate verde salvo
los goldens que mueve esa capa (declarados de antemano).

| capa | qué activa | ancla / verificación | goldens |
|:--:|---|---|---|
| **1** | Ancla + diseño | 8/8 anchor verdes; gate 41/41 | ninguno |
| **2** ✅ | **Terminales limpias clase A**: acetic/T-101 ✅ activada; dist_eth_az/T-101 ⏸ diferida (azeótropo) | split FUG D=9.94/B=1847 ≈ hardcode 10/1847; ancla intacta; gate 41/41 | **acetic** (sum_duty 16.6→36.4) |
| **3** ✅ | **Columnas en loop**: hda/T-101 (1 reciclo) — benceno/tolueno, lazo vivo | converge en ~3 iters; P-101 balancea (Σin=Σout=10858); S-8 benceno 7503 @ 0.98; mass_err=0 | **hda** (sum_duty −90.8→14.7) |
| **4** | **hda_full tren T-101/102/103** con propagación en loop vivo | el reciclo de tolueno NO colapsa; multi-tear converge a SS físico | hda_full (sale de FROZEN) |
| **5** | **gas_sweet T-101/T-102** (absorción/stripping de aminas) | lazo de aminas converge; gas dulce sin fuga de amina | gas_sweet (sale de FROZEN) |
| **6** | **Desbloquear placeholders** acetic/beer (separación activa aguas abajo) | reactor+separador computan; `[W-PLACEHOLDER]` baja | acetic, beer |
| **—** | clase B (pseudo-cortes cdu/talara), C (hno3 reactivo), E (quimpac) | **fuera de alcance** → frentes propios | — |

**Orden no negociable:** 1→2 (terminales, riesgo bajo) antes de 3→4→5 (loops
vivos, riesgo alto). La capa 4 (hda_full) depende de la propagación que la capa
3 valida en un lazo aislado.

### 4.6 Riesgos y anclas

| riesgo | mitigación / ancla |
|---|---|
| romper las 6 activas existentes | son ancla dura en cada PR (gate 41/41); el path FUG no cambia para terminales |
| columna en loop colapsa el reciclo (tolueno→0) | ancla sintética + lazo aislado hda/T-101 (capa 3) antes de hda_full; invariante interior>0 |
| "converged" falso a 0 (bug histórico) | invariante de aceptación: interior>0 **y** balance elemental cierra |
| mover goldens de más | cada capa declara qué ejemplos mueve; los demás byte-idénticos o se investiga |
| pseudo-cortes (cdu/talara) mal modelados como binarios | clase B explícitamente FUERA de alcance → frente de pseudo-componentes |
| azeótropo (dist_eth_az) | el motor ya emite warning honesto (α_top<1); spec azeotrópica documentada, no forzada |
| spec `[típico]` enmascarando física | toda spec citada (Turton/Seader) y marcada `[típico]` en el golden |

**Columnas activas existentes como referencia:** distillation/T-101
(benceno/tolueno) es el espejo directo del ancla y de hda/hda_full;
ethanol/T-101 (etanol/agua) espeja dist_eth_az; industrial/T-201
(metanol/agua) espeja la mecánica multicomp. Son las 6 pruebas vivas de que el
motor funciona — el frente solo lo **extiende a loops**, no lo reinventa.

---

## 5. Resumen ejecutivo

- **Veredicto:** **CASO ACTIVAR.** El motor de columnas (FUG shortcut +
  Wang-Henke MESH) **ya existe, está probado e integrado** al solver de
  reciclos; 6 columnas activas pasan el gate 41/41. No hay que construir un
  motor.
- **Matiz:** la única pieza a *endurecer* (no construir) es la **propagación de
  columnas en loop vivo** — la misma que `multitear_design.md` §3.1 dejó
  diferida (el reciclo de tolueno de hda_full colapsa a 0 hoy).
- **Universo:** 13 columnas pasivas (no 14 — `hydraulic/T-101` ya se re-tipó a
  Vessel). De ellas, el frente real son **2 terminales limpias** (clase A) +
  **6 en loop** (clase D). Las otras 5 (pseudo-cortes, reactivo, no-destilación)
  son fuera de alcance.
- **Impacto:** ~32 salidas de columna hoy hardcode; ~12 dentro de loops vivos;
  desbloquea acetic/beer (placeholders) y es prerequisito para encender
  gas_sweet/hda/hda_full (hoy FROZEN).
- **Plan:** 6 capas, terminales primero (riesgo bajo) y loops después (riesgo
  alto), cada una medible contra el ancla sintética, goldens uno por capa.
- **Entregable del PR de diseño:** este documento + el ancla sintética
  (`tests/test_columna_ancla_sintetica.py`, 8/8 verde) + el inventario y
  dimensionamiento medidos. Es el PLANO de la arquitectura.

---

## 6. Estado de ejecución — CAPA 1 (terminales limpias)

> **Modo de la Capa 1:** auditar antes de tocar; re-validar el diseño contra el
> repo (no confiar en el doc a ciegas); gate antes de commit. Solo se activó la
> columna **terminal limpia** confirmada; la enredada se difirió.

### 6.1 Re-validación del diseño (FASE 0)
- Gate 41/41 verde y ancla sintética 8/8 verde al abrir.
- **Universo re-medido desde los JSON:** sigue siendo **6 activas + 13 pasivas**
  (no 14: `hydraulic/T-101` ya es Vessel). Clase A = `acetic/T-101` +
  `dist_eth_az/T-101`.
- **Motor integrado:** re-confirmado `solve_columns()` en el lazo principal y en
  el Wegstein (§4.3, nota). Las 4 reglas de loop vivo siguen vigentes.

### 6.2 `acetic/T-101` — ACTIVADA ✅
- **Qué separa:** feed S-4 (de V-101) = 99.46 % ácido acético / 0.54 % metanol →
  destilado metanol (LK, bp 65 °C) / fondo ácido acético (HK, bp 118 °C).
  Terminal (productos a tanques TK-104/TK-105 vía coolers E-102/E-103).
- **Parámetros (derivados del split declarado, `[típico]` citado):**
  `column_LK=methanol`, `column_HK=acetic_acid` (los 2 componentes del feed,
  α=6.1>1); `column_x_D_LK=0.99` (recuperación alta de metanol overhead,
  `[típico]`); `column_x_B_LK=0.0001` (ácido acético producto ≈ libre de
  metanol, spec de diseño); `column_R_factor=1.5` (`[típico]` Turton/Seader,
  igual que las 6 activas hermanas); `column_method=fug`, `N` por Gilliland.
- **Reproduce el split declarado:** FUG da D=9.94 / B=1847.06 vs. hardcode
  10 / 1847 (Δ<0.6 %). El hardcode previo era "puro" idealizado (metanol 1.0 /
  acético 1.0); el FUG da 99 % / 99.99 %, físicamente más honesto.
- **Streams liberados:** se quitaron los locks de composición de las salidas de
  la columna (S-vap, S-fondo) y de los 2 productos terminales aguas abajo
  (S-livianos, S-AcOH, que estaban clavados "puros" — el cooler pass-through no
  separa; ahora propagan el split calculado). 4 comps intermedias/terminales
  pasan de hardcode a calculadas.
- **Golden:** solo `acetic` cambió — `sum_duty` 16.57 → 36.44 (la columna ahora
  computa su reboiler/condensador real, R≈1.5·R_min con R_min alto por ser una
  separación de traza a alta pureza). `overall_status`, `n_blocks`, `n_streams`,
  `mass_errors=0`, `energy_errors=0`, `ISBL` **idénticos**. Los otros 40
  byte-idénticos.
- **Warnings:** el único warning nuevo es `[W-ENERGY-BLOCK] T-101` — que es
  **intrínseco a TODA columna activa** en este motor (medido: las 6 activas
  existentes lo emiten también; el cierre de energía advisory no contabiliza
  reboiler/condensador igual que el FUG). NO es regresión: es el mismo advisory
  que las hermanas. El `[W-COMP-OVERRIDE]` de cascada se eliminó liberando los
  2 productos terminales.

### 6.3 `dist_eth_az/T-101` — DIFERIDA ⏸
- Su destilado objetivo declarado es **etanol 0.956 = el azeótropo etanol/agua**.
  Medido con FUG: α_top = **0.95 < 1** → warning `AZEOTROPO PASADO`. La
  destilación simple (FUG/MESH) **no puede** cruzar/alcanzar el azeótropo;
  requiere destilación **azeotrópica/extractiva con entrainer** (tercer
  componente) — un frente propio, fuera del alcance "activar limpio".
- **No se forzó** (regla: no forzar una columna enredada). Queda pasiva con su
  golden intacto.

### 6.4 Verificación (FASE 2)
- **Gate:** 41/41 verde; solo el golden de `acetic` se regeneró (Δ sum_duty),
  los 40 restantes byte-idénticos.
- **Ancla sintética:** 8/8 verde (intacta).
- **Tests:** `tests/test_columna_capa1_acetic.py` (5/5) — columna activa, split
  físico, balance por componente cierra, reproduce el split declarado, sin
  errores de balance. Suites de destilación (p1/p2/p3, columns, simple, mccabe)
  verdes (p4 falla solo por `PySide6` ausente en el entorno headless — UI test,
  no relacionado).

### 6.5 Capa 3 — `hda/T-101` ACTIVADA en loop vivo ✅

Primera columna **en loop** activada. Resultó un fix de **DATOS**, no de motor:

- **Root cause real (corrige el diagnóstico previo):** el lazo NO necesitaba
  "construir solver" (Wegstein vectorial + nodo mixer ya existen y funcionan).
  El bug era **selección de tear**: `_choose_tear` elegía `S-2` (arista forward
  E-101→F-101) en vez del reciclo físico, porque `S-9-recic` estaba mal
  etiquetado `role="internal"`. hda tiene dos puntos de mezcla con feed externo
  (tolueno en P-101, makeup H₂ en F-101) → dos back-edges; sin el tag, el
  desempate mispickea. Con `role="recycle"` el ranking de `_choose_tear` elige
  el reciclo y todo converge.
- **Fix (DATOS, 4 cambios + cleanup):** `S-9-recic.role`=recycle + des-lockear
  el tear (mass+comp); activar T-101 (LK=benzene/HK=toluene, FUG, R=1.5,
  x_D=0.98, x_B=0.02); des-lockear comp de S-7/S-8; propagar el producto
  terminal S-benceno (patrón capa 1).
- **Medido:** converge en ~3 iters (tear 1866→1978→2002→2008); P-101 Σin=Σout
  =10858; S-8 benceno 7503 @ 0.98 (= flujo del SS frozen); **mass_err=0**;
  validate_ui hda ok (mass 0, eng 0). Solo el golden de hda se movió
  (sum_duty −90.8→14.7, la columna computa reboiler/condensador real); los
  otros 40 byte-idénticos.
- **Warnings:** `[W-ENERGY-BLOCK] T-101` intrínseco a columnas activas (no
  regresión); `[W-ENERGY-BLOCK] P-101` **pre-existente** (ya estaba en baseline).
- **Bug latente anotado (fuera de alcance):** `_choose_tear`/`_choose_tears`
  mispickea el back-edge en topologías con ≥2 puntos de mezcla cuando el reciclo
  NO está taggeado `role="recycle"`. Endurecer el selector para que elija el
  back-edge físico sin depender del tag es una mejora SEPARADA — relevante para
  la capa agéntica (flowsheets sin roles pre-taggeados). NO se tocó acá.

**Próxima capa:** clase D restante — `hda_full` (3 columnas) y `gas_sweet`
(absorbers de amina). Antes de aplicarles el mismo camino mínimo, verificar si
sus reciclos están bien taggeados `role="recycle"` (si no → taggear, o endurecer
el selector). `dist_eth_az` espera el frente de destilación azeotrópica.
