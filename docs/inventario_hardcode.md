# Inventario de hardcode — los 41 ejemplos (diagnóstico puro)

> **Modo:** SOLO MEDIR Y REPORTAR. No se tocó ningún JSON, solver ni golden.
> El único cambio en el árbol git es este documento.
> **Fecha de medición:** 2026-06-14, desde el repo actual (HEAD = merge #94,
> cierre multi-tear capas 1-5). **NO** se confió en barridos viejos: todo se
> midió cargando cada `data/examples/*.json`, resolviéndolo headless y leyendo
> la estructura + los warnings de conciencia del solver.
> **Gate al cerrar:** `python gate_examples.py` → **41/41 verde** (este doc no
> toca goldens).

---

## Metodología

Para cada uno de los 41 ejemplos se cargó el JSON (`from_dict`), se corrió
`flowsheet_solver.solve()` headless y se recogió:

1. **Estructura por bloque:** `eq_type`, flags de comportamiento
   (`column_active`, `flash_active`, `separator_active`, `mech_sep_active`,
   `splitter_active`, `reactor_mode`, `reactions`), cardinalidad in/out,
   composiciones/locks de salida, y pertenencia a un SCC de reciclo (misma
   detección de SCC que usa el solver, no un DFS paralelo).
2. **Juicio del propio motor:** los warnings de conciencia `[W-...]` que el
   solver ya emite (`awareness_warnings`). Estos son el "deslockeo
   automático" del motor: marcan dónde la física declarada no la calcula el
   motor.
3. **Test del deslockeo (manual, en copias en memoria, NO commiteado):** para
   una muestra representativa de sospechosos se vació la composición + se
   desbloqueó comp y masa de las salidas, se re-resolvió y se observó si el
   motor **re-deriva** el valor (legítimo/redundante) o **colapsa/queda
   vacío** (hardcode que el motor no puede recomputar).

**Principio rector aplicado:** un valor es *hardcode mentiroso* si, al
soltarlo, el motor NO lo re-deriva (colapsa). Es *legítimo* si es una spec de
diseño declarada (feed, producto terminal, conversión/split de usuario) que el
motor consume como input por diseño.

---

## FASE 0 — Línea base

- **Gate:** `gate_examples.py` → **41/41 round-trippean idéntico** (exit 0).
- **41 ejemplos** en `data/examples/manifest.json`; los JSON `_golden.json` y
  `manifest.json` no cuentan.
- **455 bloques** (excl. auto_aux) y **442 streams** en total.

### Reparto de bloques por `eq_type`

| eq_type | n | eq_type | n |
|---|---:|---|---:|
| Storage tank — cone roof | 133 | Reactor — jacketed non-agit. | 13 |
| Vessel — vertical | 63 | Evaporator — vertical | 13 |
| Heat exch. — floating head | 46 | Reactor — jacketed agitated | 12 |
| Heat exch. — air cooler | 28 | Heat exch. — kettle reboiler | 12 |
| Tower (column shell) | 20 | Reactor — autoclave | 11 |
| Pump — centrifugal | 18 | Storage tank — floating roof | 10 |
| Mixer — static | 16 | Vessel — horizontal | 4 |
| Fired heater — non-reformer | 14 | Filter — belt | 4 |
| Compressor — centrifugal | 13 | Heat exch. — fixed tube | 3 |
| Ambient | 13 | (1 c/u) Decanter, Crystallizer, Dryer, Boiler, Centrifuge, Compressor axial/recip, Pump PD, WHB | 8 |

> El "comportamiento" NO lo fija el `eq_type` sino los flags `*_active` /
> `reactions`. Un "Vessel — vertical" puede ser flash activo, separador
> pasivo o splitter; una "Tower" puede ser columna activa, columna pasiva o
> un splitter de cortes. Por eso la clasificación de abajo va por flag, no por
> tipo.

---

## FASE 1 — Reactores: **el balde 3 (mentiroso sin placeholder) está muerto**

37 bloques con química declarada o `eq_type` de reactor. Reparto:

| Clase | n | Significado |
|---|---:|---|
| **Química REAL** (`reactions` resuelve en `reactions_db`) | **12** | el motor calcula conversión/salida |
| **PLACEHOLDER honesto** (`reactions` declarada que NO resuelve → `[W-PLACEHOLDER]`) | **25** | química hardcodeada vía outputs locked, **declarada como tal** |
| **MENTIROSO** (`reactions=[]` + comps de producto hardcodeadas, sin placeholder) | **0** | ❌ no existe ninguno |

- **Confirmado:** ningún reactor tiene `reactions=[]` fingiendo productos. El
  "balde 3" de la auditoría vieja está **vacío**.
- **Los 3 ex-mentirosos están arreglados:**
  - `hda/R-101` → química real **R035** (`reactor_mode=stoich`). ✅
  - `hda_full/R-101` → química real **R035**. ✅
  - `sugar` → **re-tipado**: ya no hay reactor. El antiguo "reactor" es hoy
    `R-101 = Heat exch. — fixed tube`, `R-102 = Crystallizer`, más
    evaporadores; ningún bloque de sugar declara reacción. ✅

### Química REAL (12) — el motor sí resuelve

`ammonia/R-101 (R004)`, `biodiesel/R-101 (R021)`, `ethane_pfr/R-101 (R011)`,
`ethanol/R-101 (R007)`, `ethylene_crk/R-101 (R011)`, `haber_rec/R-101 (R004)`,
`hda/R-101 (R035)`, `hda_full/R-101 (R035)`, `industrial/R-101 (R005)`,
`methanol/R-101 (R005)`, `rxn_flash_col/R-101 (R007)`, `smr_eq/R-101 (R003+R002)`.

### PLACEHOLDER honesto (25) — química hardcodeada pero declarada

Todos emiten `[W-PLACEHOLDER]` (el motor los exime de balance elemental/energía
y avisa). Dos subgrupos según facilidad de arreglo:

**(a) Base curada YA existe en `reactions_db` (9) — candidatos a mini-PR de química (estilo T29b):**

| ejemplo | bloque | declara | base disponible |
|---|---|---|---|
| acetic | R-101 | R026_PLACEHOLDER | **R026** |
| beer | R-101 | R007_PLACEHOLDER | **R007** |
| bread | R-101 | R007_PLACEHOLDER | **R007** |
| cement | R-101 | R029_PLACEHOLDER | **R029** |
| chloralkali_hcl | R-201 | R028_PLACEHOLDER | **R028** |
| ldpe | R-101 | R027_PLACEHOLDER | **R027** |
| soap | R-101 | R030_PLACEHOLDER | **R030** |
| sulfuric | R-101 | R006_PLACEHOLDER | **R006** |
| urea | R-101 | R031_PLACEHOLDER | **R031** |

**(b) ID custom sin base curada (16) — requieren curar la reacción primero:**

`chloralkali_hcl/R-101 (R_CELDA_CLORALCALI)`, `glass/R-101 (R_FUSION_GLASS)`,
`hno3/R-201 (R_OSTWALD_BURN)`, `hno3/R-301 (R_OXIDATION_NO)`,
`hno3/T-401 (R_ABSORB_NO2, absorbedor reactivo)`,
`penicillin/R-101 (R_FERMENT_PEN)`, `quimpac/R-101 (R_PURIF)`,
`quimpac/R-201 (R_CELDA_CLORALCALI, en loop)`, `water_treat/R-101 (R_FLOCULACION)`,
y la batería de **talara** (7): `R-HTN/R-HTD/R-HTF (R_HDS)`, `R-RCA (R_REFORM)`,
`R-FCC (R_FCC)`, `R-FCK (R_FCK)`, `R-SMR (R_SMR)`.

---

## FASE 2 — Columnas: **el sospechoso grande, confirmado**

20 "Tower (column shell)": **6 activas, 14 pasivas.**

### Activas (6) — el motor calcula la separación (REAL)

`air_sep/T-101`, `distillation/T-101`, `ethanol/T-101`, `ethylene_crk/T-101`,
`industrial/T-201`, `rxn_flash_col/T-101`. Todas 1-in / 2-out, ninguna en loop.

### Pasivas (14) — split declarado a mano (salidas comp-locked)

**Test del deslockeo aplicado (muestra):** se vació+desbloqueó la composición
de salida y se re-resolvió.

| ejemplo | columna | en loop | resultado deslockeo | clase |
|---|---|:--:|---|---|
| acetic | T-101 | no | **COLAPSA** (ambas salidas → 0, solve falla) | SOSPECHOSO (split real hardcodeado) |
| cdu | T-101 | no | **COLAPSA** (4 cortes → crude_oil → 0) | SOSPECHOSO (4-cut hardcodeado) |
| dist_eth_az | T-101 | no | separa (azeotrópica) | SOSPECHOSO |
| gas_sweet | T-101 | **sí** | **CAMBIA mal** (amina/agua fugan al gas dulce) | SOSPECHOSO (absorción amina no modelada) |
| gas_sweet | T-102 | **sí** | (stripper de amina) | SOSPECHOSO |
| hda | T-101 | **sí** | separa | SOSPECHOSO |
| hda_full | T-101 | **sí** | **COLAPSA** (S-8 → 0, solve falla) | SOSPECHOSO |
| hda_full | T-102 | **sí** | separa | SOSPECHOSO |
| hda_full | **T-103** | **sí** | **RE-DERIVA** (ambas salidas ≈ inlet) | ⚠ **MIS-MODELO: no separa** |
| hno3 | T-401 | no | absorbedor reactivo (placeholder, ver Fase 1b) | PLACEHOLDER |
| hydraulic | T-101 | no | **RE-DERIVA** (1-in/1-out = inlet) | ⚠ **MIS-MODELO: no separa** |
| quimpac | T-301 | no | separa (secado Cl2) | SOSPECHOSO |
| talara | T-101 | no | separa (6 cortes, splitter_active con comps distintas) | SOSPECHOSO/split |
| talara | **T-201** | no | **RE-DERIVA** (VGO ≈ resid ≈ inlet) | ⚠ **MIS-MODELO: torre vacío que no fracciona** |

### 2.3 — Columnas que NO separan (entrada ≈ ambas salidas)

Tres confirmadas (el T-103 de hda_full ya descubierto, más dos):

- **`hda_full/T-103`** — S-13 y S-14 ≈ inlet (Δcomp 0.0008 / 0.014). Está
  **en un loop vivo**. Al deslockear, el motor la re-deriva como pass-through
  → **es una columna que no hace nada**. Debería ser splitter o
  `column_active`, o eliminarse.
- **`talara/T-201`** — torre de vacío `splitter_active=True`: VGO y resid-vac
  salen con **composición idéntica al inlet** (Δ 0.0). Es un splitter de masa
  que NO fracciona; físicamente una torre de vacío debería separar por punto
  de ebullición.
- **`hydraulic/T-101`** — 1-in / 1-out con salida = inlet. Es un pass-through
  etiquetado como columna; no separa nada.

### 2.4 — Resumen columnas

| | activas | pasivas-separan | pasivas-no-separan | placeholder reactivo |
|---|---:|---:|---:|---:|
| total | 6 | 10 | 3 | 1 |
| en loop de reciclo | 0 | **6** | 1 (T-103) | 0 |

**6 columnas pasivas viven en loops de reciclo** (gas_sweet T-101/T-102, hda
T-101, hda_full T-101/T-102/T-103). El test del deslockeo confirma que
**colapsan o producen basura** si se sueltan en vivo → son las que romperían
un "encendido" del motor sobre esos loops. Son el corazón del proyecto
"columnas activas".

---

## FASE 3 — Separadores / vessels / flash

73 bloques Vessel/Decanter/Centrifuge/Filter; **37 con ≥2 salidas** (separadores
v/l reales). Reparto por comportamiento:

| Comportamiento | n | Clase |
|---|---:|---|
| `flash_active` (VLE calculado) | 2 (`ethanol/V-101`, `rxn_flash_col/V-101`) | REAL |
| `separator_active` | 1 (`sugar/FL-101`) | REAL |
| `mech_sep_active` | 3 (`ammonia/V-101`, `biodiesel/V-101`, `methanol/V-101`) | REAL |
| `splitter_active` (split declarado honesto) | varios (ver Fase 5) | LEGÍTIMO/split |
| **pasivo con salidas comp-locked** | **~23** | SOSPECHOSO / LEGÍTIMO-por-spec |

### Test del deslockeo en separadores pasivos (muestra)

| ejemplo | sep | en loop | deslockeo | lectura |
|---|---|:--:|---|---|
| **haber_rec/V-101** | V-101 | **sí** | **COLAPSA** (S-NH3, S-gases → 0) | hardcode; *legítimo por spec de producto* (pureza NH3) pero el motor NO lo re-deriva |
| hda/V-101 | V-101 | **sí** | **COLAPSA** (S-6, S-purga → 0) | hardcode; flash de separación no modelado |

**Hallazgo clave:** incluso el separador "legítimo" del brief (`haber_rec/V-101`)
**colapsa** al deslockear. La legitimidad aquí es **semántica** (el split ES la
spec de pureza del producto), no computacional: el motor hoy no tiene flash
activo para re-derivarlo. Es decir, todos los separadores pasivos son
"hardcode declarado"; lo que cambia es si su lock representa una spec de diseño
honesta (legítimo) o una física que el motor debería calcular (sospechoso).

### 3.3 — Separadores pasivos EN LOOP (prioridad para encendido)

`gas_sweet/V-101`, `gas_sweet/V-102`, `haber_rec/V-101`, `hda/V-101`,
`hda_full/V-101`, `industrial/V-201`. Estos 6 + las 6 columnas pasivas en loop
= **12 puntos de hardcode dentro de loops vivos**.

Los demás separadores pasivos son **terminales** (no en loop): acetic, air_sep,
beer, ldpe, leche_gloria (×3), penicillin (×2), potato_chips, smr_eq, soap,
sugar, sulfuric, talara/TK-214, urea, water_treat. Muchos remueven un componente
declarado (agua, sólidos) = spec de diseño razonable.

---

## FASE 4 — Pass-through que cambian composición sin reacción

Se corrió el solve y se listaron **todos** los `[W-COMP-OVERRIDE]`:

- **`hno3/E-203` → `A8-gas-cool`** (Heat exch.): **único** disparo.
  Composición declarada difiere del inlet en un cooler.
  **Test del deslockeo:** al soltar, el NO₂ **desaparece** (fracción
  0.049 → 0) y el NO sube (0.08 → 0.112): confirma que el cooler **hardcodea
  la oxidación NO→NO₂**. **MENTIROSO** — química real falseada en un equipo
  pass-through. Arreglo: declarar la reacción de oxidación o re-tipar a
  reactor.

No hay otros pass-through con override de composición (los ~120 pass-through
restantes propagan inlet→outlet idéntico, byte-correctos).

### Anexo Fase 4 — otros overrides que el motor marca (no son comp, pero son hardcode)

- `[W-T-OVERRIDE]` (7): T declarada pisada por el solver — `acetic/S-CO-HP`,
  `ammonia/S-1`, `hno3/A4-aire-hp`, `hno3/A10-NOx-hp`, `ldpe/S-HP`,
  `quimpac/S-cl2-hp`, `urea/S-HP`. Casi todos son descargas de compresor
  isentrópicas (la T "de diseño" no coincide con la isentrópica). No es
  hardcode de composición; es intención de T perdida.
- `[W-MIXER-DUTY]`/`[W-TANK-DUTY]` (10): duty espurio en equipo pasivo (mixers
  estáticos y tanques con duty≠0 hardcodeado). Energía fantasma, no comp.
- `[W-SPLIT-LOCK]` (2): ver Fase 6 (talara/V-101, número falso visible).

---

## FASE 5 — Composiciones de corriente hardcodeadas (patrón base)

**363 de 442 streams** tienen `composition_locked=True`. Reparto por rol:

| Rol | n | ¿Inevitable? |
|---|---:|---|
| **Feed externo** (`role=feed` o `src=-1`) | 66 | ✅ inevitable (input de diseño) |
| **Producto terminal** (`role=product` o `dst=-1`) | 67 | ✅ mayormente legítimo (spec de venta) |
| **Intermedio** (entre dos unit-ops) | **230** | ⚠ el patrón a revisar |
| `mass_flow_locked` (referencia) | 159 | feeds + 1 salida/split + tears (deuda de masa ya cerrada) |

Las **230 composiciones intermedias lockeadas** son el patrón base: comp
escrita en el JSON que el motor no recalcula. Se concentran en los ejemplos
"plantas completas": **talara (30), hda_full (18), hno3 (17), leche_gloria
(16), quimpac (16), industrial (12), sugar (12), gas_sweet (11), acetic (10)**.

### 5.2 — Inevitables vs "el motor debería calcularlas"

- **Inevitables (~133):** los 66 feeds + 67 productos terminales.
- **"El motor debería"** (subconjunto de las 230 intermedias): las que son
  **salidas de columnas/separadores pasivos** (se eliminarían con columnas y
  flash activos) y las **propagables** (downstream de bloques activos que, si
  no estuvieran lockeadas, se re-derivarían).

### 5.3 — Ejemplos "engine-driven" vs "fully declarative"

En el otro extremo, **8 ejemplos casi sin locks intermedios** (solo el feed):
`ammonia, biodiesel, distillation, ethanol, methanol, pasteurizer,
rxn_flash_col, ethane_pfr`. Son las vitrinas donde el motor realmente resuelve
el proceso. Los 5 "fully hardcoded" (todos los streams locked) son
`talara, hno3, leche_gloria, quimpac, gas_sweet`.

---

## FASE 6 — Reporte consolidado

### 6.1 Tabla maestra — clasificación de equipos transformacionales

Conteo por clase (excluye tanques de almacenamiento, ambient, mixers,
pass-through HX idénticos y splitters honestos consistentes, que no
transforman composición ilegítimamente):

| Clase | n | Detalle |
|---|---:|---|
| **REAL** (motor calcula) | 24 | 12 reactores + 6 columnas activas + 2 flash + 1 sep + 3 mech-sep |
| **PLACEHOLDER honesto** | 25 | 9 con base curada (mini-PR) + 16 custom (curar primero) |
| **SOSPECHOSO** (split/sep pasivo hardcodeado) | 34 | 11 columnas pasivas + 23 separadores pasivos |
| **MENTIROSO confirmado** | 2 | `hno3/E-203`, `talara/V-101` |
| **MIS-MODELO** (no separa / contradicción) | 3 | `hda_full/T-103`, `talara/T-201`, `hydraulic/T-101` |

### 6.2 Ranking de monstruos (gravedad decreciente)

1. **`talara/V-101` (desalador)** — `[W-SPLIT-LOCK]` ×2: los flujos lockeados
   **contradicen las fracciones del splitter** (S-brine=25 000 t/a vs fracción
   0.952 que esperaría 499 800; C1-desalado=500 000 vs fracción 0.048). Los
   números están **cruzados**. Es el caso más grave: **un usuario ve un número
   falso hoy** (reparto del desalador invertido).
2. **`hno3/E-203`** — `[W-COMP-OVERRIDE]`: oxidación NO→NO₂ hardcodeada en un
   cooler. Física química falseada; el deslockeo lo prueba (el NO₂ se evapora).
3. **`hda_full/T-103`** — columna **en loop vivo** que no separa (re-deriva a
   pass-through). Inofensiva al balance hoy (no cambia números) pero es un
   bloque-fantasma que bloquearía/confundiría el encendido del loop.
4. **`talara/T-201`** — torre de vacío que no fracciona (split de masa con
   comp idéntica). Reporta cortes (VGO/resid) que en realidad no se separaron.
5. **`hydraulic/T-101`** — columna 1-in/1-out que no separa (cosmético; bajo
   impacto, es un ejemplo de hidráulica).
6. **Las 6 columnas + 6 separadores pasivos EN LOOP** (gas_sweet, hda,
   hda_full, haber_rec, industrial) — no reportan número falso hoy (los
   goldens cuadran), pero colapsan al deslockear → son los que impiden
   "encender" el motor sobre esos reciclos.

> Nota: los `[W-MIXER-DUTY]`/`[W-TANK-DUTY]` (10) y `[W-T-OVERRIDE]` (7) son
> monstruos **menores** (energía/T fantasma, no composición). No alteran
> balances de masa ni los goldens; son ruido físico advisory.

### 6.3 Agrupación por tipo de arreglo

| Frente de arreglo | equipos | esfuerzo |
|---|---|---|
| **Columnas activas** (proyecto grande) | 10 columnas pasivas-que-separan + 23 separadores pasivos (flash activo) | 🔴 Alto — motor de separación riguroso + tearing en vivo |
| **Mini-PR de química** (estilo T29b) | 9 placeholders con base curada (acetic, beer, bread, cement, chloralkali R-201, ldpe, soap, sulfuric, urea) | 🟢 Bajo c/u — cambiar `RNNN_PLACEHOLDER`→`RNNN` y validar |
| **Curar reacción + activar** | 16 placeholders custom (talara ×7, hno3 ×3, quimpac ×2, glass, penicillin, water_treat, chloralkali R-101) | 🟡 Medio — falta la reacción en `reactions_db` |
| **Re-tipar equipo** (estilo sugar) | `hda_full/T-103`, `talara/T-201`, `hydraulic/T-101` → splitter o eliminar | 🟢 Bajo |
| **Mini-PR de química en pass-through** | `hno3/E-203` (declarar oxidación NO→NO₂ o re-tipar a reactor) | 🟢 Bajo |
| **Corregir números cruzados** | `talara/V-101` (alinear flujos lockeados con fracciones del splitter) | 🟢 Bajo (1 JSON) |
| **Documentar** (legítimos por spec) | feeds (66), productos terminales (67), separadores terminales que remueven comp declarado, splitters honestos | — |

### 6.4 Veredicto

- **Monstruos "duros" que reportan un número FALSO visible hoy: 1** →
  **`talara/V-101`** (desalador con flujos/fracciones cruzados,
  `[W-SPLIT-LOCK]`). Es el único que un usuario vería mal en un balance hoy.
- **Mentirosos de física (química falseada): 1** → `hno3/E-203` (no cambia el
  golden, pero finge una oxidación).
- **Mis-modelos estructurales: 3** → columnas que no separan (`hda_full/T-103`,
  `talara/T-201`, `hydraulic/T-101`).
- **¿Concentrados o dispersos?** Concentrados en **un tipo: separación pasiva**
  (columnas + flashes hardcodeados, ~34 equipos), y secundariamente en
  **reactores placeholder** (25). El "balde 3" (reactor mentiroso sin
  placeholder) está **muerto** (0). Los pass-through están **limpios** salvo el
  único `hno3/E-203`.
- **Riesgo de encendido en vivo:** 12 equipos pasivos viven dentro de loops de
  reciclo y colapsan al deslockear. Son el bloqueo real para "encender" el
  motor sobre gas_sweet/hda/hda_full/haber_rec/industrial.

### 6.5 Recomendación de prioridad

1. **🟢 Quick wins (1 PR pequeño cada uno, alto valor / bajo riesgo):**
   - `talara/V-101`: corregir los flujos cruzados del desalador (único número
     falso visible). **Prioridad #1.**
   - `hno3/E-203`: declarar la oxidación NO→NO₂ (quita el único
     `[W-COMP-OVERRIDE]`).
   - Re-tipar `hda_full/T-103`, `talara/T-201`, `hydraulic/T-101` a splitter /
     eliminar la columna-fantasma.
2. **🟢 Batch de química placeholder (1 PR, estilo T29b):** activar los **9
   placeholders con base curada** (`RNNN_PLACEHOLDER`→`RNNN`). Reduce los
   monstruos de 25 a 16 reactores placeholder de un golpe.
3. **🟡 Curar reacciones faltantes:** los 16 placeholders custom — empezar por
   los que están en loop (`quimpac/R-201`) y por familias repetidas
   (`talara` HDS×3, reformado, FCC).
4. **🔴 Proyecto "columnas/flash activos":** el frente grande (~34 equipos,
   ~230 comps intermedias lockeadas). Priorizar los **12 equipos pasivos en
   loops** (gas_sweet, hda, hda_full, haber_rec, industrial) porque son los que
   habilitan el encendido de reciclos en vivo; los terminales pueden quedar
   como spec declarada y solo **documentarse**.

---

### Apéndice — cómo reproducir esta medición

Toda la medición se hizo con scripts efímeros (no commiteados) que:
cargan cada `data/examples/*.json`, corren `flowsheet_solver.solve()`, leen
`result.awareness_warnings` y la estructura de bloques/streams, y aplican el
test del deslockeo en copias en memoria (vaciar comp + desbloquear + re-solve).
Los warnings `[W-...]` son emitidos por `_compute_awareness_warnings()` en
`flowsheet_solver.py`. Ningún JSON, solver ni golden fue modificado.
