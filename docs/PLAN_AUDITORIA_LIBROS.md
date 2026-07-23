# PLAN — Auditoría con ejercicios de libros + didáctica en el software

**Fecha:** 2026-07-22
**Estado:** EN EJECUCIÓN — Frente R arrancado (tabla estequiométrica ✓).
**Antecedente directo:** `CASOS_LIBRO.md` (Frente 2 del plan de
auditoría frontend) ya instaló el método: 7 casos de libro congelados
como tests que recomputan el valor de referencia **a mano dentro del
test** (la ecuación del libro con coeficientes copiados del libro, no
leídos de los catálogos del repo). Este plan lo extiende de "tests" a
"tests + superficie didáctica en el inspector".

## Método (regla para TODO caso nuevo)

1. **Checkpoint independiente**: el test recomputa el número del libro
   con la fórmula del libro (estilo `test_casos_libro.py`). Si el
   catálogo o la implementación derivan, el test falla contra el libro.
2. **Superficie didáctica**: lo que el libro muestra como tabla/figura
   canónica se muestra igual en el inspector (evidence de
   `inspector_evidence`), con la **fuente citada al pie** (patrón del
   popover educativo de hx_edu: "Fuente: …").
3. **Gate intacto**: si el caso amerita un ejemplo nuevo del set, entra
   por el flujo C.2 (JSON + manifest + golden re-export + 61/61→N/N).

---

## Frente R — Fogler (reactores)

### R.1 ✓ Tabla estequiométrica (Fogler §3.4, tablas 3-3/3-5) — HECHO

La herramienta didáctica canónica para plantear el balance molar,
ahora en el inspector de todo reactor con reacción y feed resolubles
(`inspector_evidence.stoich_table/_text`, sección "Tabla
estequiométrica (Fogler §3.4)"):

- Base 1 mol del reactivo limitante A (ν normalizado por |ν_A|,
  detectado por min F_i0/|ν_i|).
- Columnas del libro: especie, ν/|ν_A|, F_i0 [kmol/h], θ_i, cambio,
  F_i(X); inertes marcados (I), limitante (A).
- Pie: δ = Σν/|ν_A|, ε = y_A0·δ (factor de expansión de gas), X con
  procedencia (**declarada** en modo stoich / **alcanzada (solver)** en
  el resto — exacta vía 1 − w_out/w_in porque la masa total se
  conserva).
- Caso de libro congelado: oxidación de SO₂ 28 %/72 % aire
  (θ_O2 = 0.54, θ_N2 = 2.03, δ = −0.5, ε = −0.14) +
  remanentes a X = 0.5 — `tests/test_libros_fogler.py`.

### R.2 Backlog Fogler (por prioridad didáctica)

| Caso | Libro | Superficie | Esfuerzo |
|---|---|---|---|
| X_eq(T) van't Hoff vs adiabática | Fogler §8 (ya existe la figura `equilibrium_figure` ✓) | agregar el checkpoint numérico de un ejemplo del libro | test solo |
| Levenspiel plot (F_A0/−r_A vs X) para dimensionar CSTR vs PFR | Fogler §2 (tabla 2-1/2-2) | figura nueva en inspector para reactores con cinética (`kinetics_available`) | medio |
| τ, Da y V de CSTR/PFR con cinética de catálogo | Fogler §4-5 | métricas en la evidencia del reactor (τ ya se muestra parcialmente) | chico |
| Perfil adiabático T-X (línea de operación sobre X_eq) | Fogler §8.3 (la línea ya se dibuja ✓) | checkpoint numérico | test solo |

## Frente S — Separadores a "nivel ChemSep"

### Qué hay HOY (más de lo que parece)

| Pieza | Estado | Rigor |
|---|---|---|
| FUG (Fenske-Underwood-Gilliland) | ✓ validado (casos 3-4 de CASOS_LIBRO) | shortcut |
| McCabe-Thiele binario | ✓ figura + datos en inspector | gráfico binario |
| **Wang-Henke** (`distillation_wanghenke.py`) | ✓ implementado | **MESH real**: tridiagonal por componente, K = γ·P_sat/P con NRTL (capa 6), bubble-point por etapa, balance de entalpía → perfil V, Q_cond/Q_reb, indicador MES-vs-MESH |
| Flash binario proyectado | ✓ (`distillation_simple` + `nrtl.flash_TP`) | binario |
| Perfil tray-by-tray en inspector | ✓ (`tray_profile`) | consume WH |

### Gap honesto vs ChemSep

ChemSep tiene dos modos: **equilibrium-stage** y **rate-based
(Maxwell-Stefan)**. El objetivo realista de la tesis es el primero;
el segundo (transferencia de masa multicomponente, HETP desde
correlaciones de empaque) queda **declarado fuera de alcance** — es un
proyecto en sí mismo y no cambia el balance/economía del set.

Para igualar el modo equilibrium-stage faltan, en orden:

1. ✓ **S.1 — Validación del Wang-Henke** (2026-07-22,
   `tests/test_libros_seader_wh.py`): checkpoints anclados a
   literatura EXTERNA — azeótropo etanol-agua vs CRC/Horsley (el
   barrido de burbuja NRTL da x=0.913 vs 0.894 publicado, T=78.18 °C
   vs 78.17 ✓), teorema de reflujo total (a R=15 con 7 etapas de
   equilibrio, el N_min de Fenske con α media geométrica —Seader
   ec. 9-85, recomputado a mano— da 6.5 vs 7 ✓), y cierre MESH del
   ternario benceno/tolueno/xileno (D+B=F·z ≤0.5 %, T monótona,
   duties con signo). **Destapó el BUG 17** (componente sin Antoine
   → converged=True con balance roto; ahora se rehúsa explícito).
   PENDIENTE DE EJEMPLAR FÍSICO: los perfiles tabulados de Seader
   ej. 10.x — cuando el autor pase los números del libro se congelan
   como checkpoint adicional (T por etapa ±2 K, D/B ±0.01).
2. ✓ **S.2 — Tabla de reparto del flash TP** (2026-07-22,
   `tests/test_libros_flash_s2.py`): el flash del solver YA era
   multicomponente (hallazgo del relevamiento: Rachford-Rice
   C-componente con γ NRTL sobre los volátiles; la proyección binaria
   era solo la figura del inspector) — lo que faltaba era VERLO. El
   solver ahora persiste el reparto molar (`_flash_diagnostics`) y el
   inspector muestra la tabla estilo ChemSep (z/x/y/K por componente,
   V/F, no-volátiles al líquido, fuente al pie). Checkpoints: las
   identidades del libro sobre los números persistidos (Σx=Σy=1,
   residual R-R=0, K_i=γ_i·P_sat,i/P recomputado a mano).
3. **S.3 — Eficiencia de Murphree por etapa** en WH (parámetro por
   bloque, default 1.0 = teórico): N_real = N_teo/E_o cierra el
   puente con el sizing de internos (trays/packing — los 4 eq_types
   sin ejemplo de C.2).
4. **S.4 — Condensador parcial / side-draws** en WH (si algún ejemplo
   de la tesis lo pide; si no, documentar como limitación).

### Superficie didáctica del frente S

- Tabla de etapas estilo ChemSep en el inspector de columna (etapa,
  T, x_LK, y_LK, L, V) — hoy el perfil se grafica; la TABLA numérica
  con formato de libro es lo que falta.
- En el flash: tabla x/y/K por componente + V/F (S.2).
- Cita al pie en cada tabla (Seader/Henley §10; King §…).

## Frente E — rigor de libro en el resto del catálogo

Decisión 2026-07-22: la misma vara (identidad del libro + checkpoint
recomputado a mano + superficie didáctica) aplica a TODO el catálogo,
no solo reactores/separadores. Regla de esta pasada: **aditivo** — se
agregan identidades y evidencia sin tocar la física que fija goldens;
lo que movería goldens queda en backlog con bandera.

### Hecho (2026-07-22, `tests/test_libros_equipos.py`)

| Familia | Identidad del libro | Dónde vive |
|---|---|---|
| Bombas | **N_s = N·√Q[gpm]/H[ft]^0.75** + clasificación de rodete (Perry 8ª fig. 10-32 / Karassik §2: <500 despl. positivo · <4000 radial · 4000-9000 mixto · >9000 axial) | `pump_sizing` devuelve `Ns_us`/`impeller_type`; la evidencia de bomba lo muestra con la regla de Perry citada. Se suma a lo ya validado (caso 5: W/head/NPSHr por N_ss) |
| Válvulas | **C_v de Crane TP-410 ec. 3-16** (C_v = Q[gpm]·√(SG/ΔP[psi]); 1 gpm agua @ 1 psi ⇒ C_v=1 por definición) | `_valve_cv_liquid` + línea en la evidencia de válvula (servicio líquido) |
| HX | **Factor F de Bowman (1940)** — la implementación contra la fórmula cerrada publicada, transcripta independiente en el test (3 puntos R≠1 + límite F(P→0)=1 + F≤1) | ya se usaba en sizing; ahora está anclado al libro |
| Compresores | **k = Cp/(Cp−R) del aire = 1.400** (Cengel A-2) — valida la capa Cp que alimenta el isentrópico (caso 6 ya validaba T_out) | checkpoint de datos |

### Backlog Frente E (⚠ = mueve goldens; requiere re-export justificado)

- ⚠ **k real por composición** en `design_compressor_for_block`: hoy
  usa la heurística documentada (1.4 diatómicos / 1.30 CO2-agua);
  computarlo de Cp de mezcla (k = Cp/(Cp−R)) es 1 línea pero cambia
  T_out/W de compresores → duties → goldens (mismo protocolo que el
  episodio rho_ref).
- ⚠ **Souders-Brown para vessels/separadores V-L** (GPSA §7 / Svrcek):
  v_max = K_SB·√((ρ_L−ρ_V)/ρ_V) — hoy el vessel se dimensiona por
  tiempo de residencia; agregar el cross-check de velocidad de vapor
  (y el K_SB con demister) cambia S de vessels flash → goldens.
- **Fan laws** (Perry §10): identidades ΔP∝N², W∝N³ como checkpoint
  del sizer de fans (aditivo, solo test).
- **Cooling tower**: rango/approach/efectividad como evidencia (los
  datos ya están en los streams; aditivo). Merkel/NTU queda fuera de
  alcance (pide curva de saturación entálpica del aire húmedo).
- **Cv de gas** (Crane ec. 3-20, flujo compresible con Y): solo si un
  ejemplo lo pide; el C_v líquido cubre las válvulas del set.

## Frente D — dónde vive lo didáctico (convención)

- **Evidencia por bloque** (`inspector_evidence` + `evidence_specs` del
  inspector): tablas monoespaciadas estilo libro con fuente al pie —
  el patrón que estrenó la tabla estequiométrica.
- **Figuras**: matplotlib theme-aware (`_style_fig`/`_legend`, ciclo 4).
- **Popovers educativos** (`hx_edu.EDU_TOPICS`): prosa + fórmula +
  diagrama + fuente, para conceptos (no para números del caso). Si un
  frente lo amerita se agregan topics (p. ej. "tabla estequiométrica"
  y "MESH vs shortcut").

### ⚡ Derivación a Design (decisión 2026-07-22)

Las tablas didácticas nuevas (estequiométrica de Fogler, reparto del
flash x/y/K, y la futura tabla de etapas del WH) hoy salen por el
camino **texto monoespaciado** de la evidencia — fieles al libro pero
por debajo del nivel visual de las tarjetas ricas del inspector
(MetricCards, kickers, ribbons). El MVP mecánico queda; el salto a
"tabla como tarjeta del sistema" (columnas alineadas con FONT_VALUE,
limitante/inerte como pills, δ/ε como chips, fuente como footer del
kit) **entra al mini-prompt de Design pendiente** junto con
streams_table/stream_inspector y el bloque A del ciclo 4 — es la misma
familia de superficie tabular sin artboard.

## Orden sugerido

1. ✓ R.1 (hecho — este commit).
2. **S.1** — auditoría WH vs Seader publicado (solo tests: máximo valor
   por esfuerzo; habilita el claim ChemSep-equilibrium).
3. **S.2** — flash multicomponente + su tabla (código acotado, cierra
   la proyección binaria que hoy es la aproximación más gruesa).
4. R.2 según lo pida la escritura de la tesis (Levenspiel es el más
   vistoso; los checkpoints de equilibrio son gratis).
5. S.3/S.4 solo si el alcance lo pide.

**Regla de la casa:** gate N/N + suite + regresión nueva por hallazgo;
bugs a `BUGS_ENCONTRADOS_EJEMPLOS.md` con reproducción mínima.
