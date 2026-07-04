# Auditoría de datos hardcodeados en los ejemplos (2026-07)

> **Principio:** todo lo que el solver puede calcular debe calcularse; los
> únicos datos declarados+lockeados legítimos son condiciones de frontera
> (feeds, llegadas a batería de límites) y especificaciones de diseño
> (targets de pureza, anclas de presión, tears de reciclo).
>
> Continúa la línea de `DEUDA_TECNICA_EJEMPLOS_HARDCODED.md` (flujos masa,
> ✅ resuelta) y del programa de columnas activas (Frente C / capas).

## Inventario (post bombas/compresores de alimentación)

| Clase | Hallados | Estado |
|---|---|---|
| Duties hardcodeados en bombas/compresores | 10 | ✅ 9 resueltos, 1 legítimo (expander) |
| `P_op_bar` hardcodeado en compresor (anula el dimensionamiento) | 1 (methanol) | ✅ resuelto |
| Anclas de presión sin procedencia (`pressure_lock_origin`) | 20 | ✅ marcadas `'user'` (son specs de diseño) |
| Saltos térmicos ficticios en descargas de bomba | 2 (cdu +5°, hda 27° vs mezcla real 43.9°) | ✅ corregidos |
| Composiciones lockeadas redundantes (aguas abajo de columnas/flash/reactores) | 20 | ⏳ diferido → programa de columnas activas |
| `mass_flow` locked en corrientes internas | 43 | ⏳ verificar que todas sean tears/split-specs |
| `W-ENERGY-BLOCK` en torres/mixers (Ts declaradas no cierran) | ~15 | ⏳ diferido → energía de columnas (capa 3) |
| Interenfriamiento implícito en compresores (T descarga lockeada) | 6 máquinas | 📌 simplificación documentada (abajo) |

## Lo resuelto en esta auditoría

### 1. Duties de máquinas → calculados (9 máquinas)

`ammonia/K-101 (1200 kW), cdu/P-101 (50), distillation/P-101 (8),
ethanol/P-101 (10), gas_sweet/P-101 (40), hda/P-101 (15),
hda_full/P-101 (30) y K-101 (300), methanol/K-101 (800)` declaraban
`duty_locked=True` con valores redondos precalculados a mano.  Ahora
`duty=0, duty_locked=False`: el solver computa el trabajo hidráulico/
politrópico real (p.ej. ammonia K-101: 1200 hardcodeado → **332.7 kW
calculados**; gas_sweet P-101: 40 → **526.5 kW** — la bomba de amina a
50 bar era 13× lo declarado).

**Excepción legítima:** `hno3/K-501` (duty = −700 kW) es un
**turboexpansor** de gas de cola que RECUPERA trabajo; el modelo
politrópico del solver solo comprime, así que el duty negativo declarado
es la única representación disponible.  Se mantiene lockeado.

### 2. methanol: `P_op_bar=80` en el compresor

El K-101 de methanol declaraba `P_op_bar=80`, y `_seed_reactor_pressures`
sembraba 80 bar **también en su succión** → ΔP=0, duty=0: el compresor
existía pero no hacía nada (dato en vez de cálculo).  Con `P_op_bar=1.0`
(patrón ammonia) el solver lo dimensiona: **ΔP=79.3 bar, duty=361.5 kW**.

### 3. Procedencia de las 20 anclas de presión

`acetic (35 bar), desal (vacío 0.12–0.31), haber_rec (200), hydraulic (4),
industrial (80/30/5), leche_gloria (homogeneización 180, vacío),
nuclear (70/0.1), rankine (60/0.1)` son especificaciones de diseño reales
pero el detector `pressure_source` las reportaba como heurísticas.
Marcadas `pressure_lock_origin='user'` → **0 warnings de pressure_source
en todo el catálogo** (antes 20).

### 4. Saltos térmicos ficticios

- `cdu/S-1`: descarga de bomba a 30 °C con succión a 25 °C (+5 °C que una
  bomba no produce) → 25 °C.
- `hda/S-1`: P-101 mezcla tolueno fresco (25 °C) + reciclo (110 °C); la T
  declarada 27 °C era aritmética manual incorrecta.  T consistente con la
  entalpía (bisección sobre `stream_enthalpy`): **43.9 °C**.

Resultado neto: los warnings del catálogo bajaron en ~40 (desal 12→6,
nuclear 7→1, rankine 6→0, hydraulic 2→0, acetic 11→7, industrial 34→28,
haber_rec 8→4, leche_gloria 82→76…) sin ningún cambio de `overall_status`.

## Simplificación documentada: interenfriamiento implícito

Los compresores de alimentación (hda, hda_full, smr_eq, talara, methanol,
más los sopladores) llevan la **T de descarga lockeada = T de succión**
(o al valor de diseño).  Esto modela una máquina multi-etapa con
inter/after-cooler sin dibujar el intercambiador; el costo es un
`W-ENERGY-BLOCK` de conciencia (el calor politrópico "desaparece" en el
enfriador implícito).  Se probó liberar la T: el solver calcula la
descarga adiabática de UNA etapa (628 °C en hda, 1154 °C en talara) —
físicamente absurda sin inter-etapas.  **Trabajo futuro:** aftercoolers
explícitos (E-xxx) tras cada compresor de alimentación.

## Deuda restante (diferida con razón)

1. **20 composiciones lockeadas redundantes** (`air_sep S-N2/S-O2`,
   `dist_eth_az`, `haber_rec S-NH3/S-gases`, `hda S-6/S-purga-H2`,
   `hda_full S-4/S-gas-recic/S-liq`, `industrial`, `smr_eq S-syngas-hot`,
   `talara` cortes FCC/FCK): desbloquearlas significa activar la
   termodinámica de columna/flash/reactor correspondiente.  Ese es
   exactamente el programa incremental de columnas activas (capas 1–3,
   PRs #102–#106) — una por una, con ancla sintética y verificación.
   No se hace en bloque.
2. **43 `mass_flow` locked internos**: la deuda original documentó 41
   legítimos (split-specs y tears).  Verificar los 2 extra y congelar la
   lista con un test (análogo a `test_examples_start`).
3. **`W-ENERGY-BLOCK` en torres/mixers**: las Ts declaradas de varios
   perfiles de columna no cierran el balance entálpico (acetic T-101,
   ethanol T-101, distillation T-101…).  Se resuelve al activar la
   energía de columnas (capa 3), no maquillando las Ts.

## Campaña de warnings (fase 2 — nivel DWSIM)

Censo catálogo-completo: **237 → 196 warnings** y 4 ejemplos pasaron de
`warning` a `ok` (acetic, air_sep, ammonia, hno3).

### Capacidad nueva del solver: compresión multi-etapa con interenfriamiento

`equipment_design.compressor_sizing` ahora modela el tren completo cuando
el ratio total supera 4 (práctica industrial API 617): N etapas de ratio
igual, intercooler a T_succión entre etapas.  Devuelve `n_stages`,
`Q_intercool_kW` y el W/T_out del tren; con ratio ≤ 4 degenera exactamente
en el cálculo de 1 etapa previo (validado en `test_equipos_referencia`:
caso de libro 1→5 bar con `max_ratio_per_stage` desactivado, y el caso
multi-etapa default).  El cierre de energía de bloques descuenta
`Q_intercool` (W_in = ΔH + Q_intercoolers) y `[W-COMP-T]` reporta las
etapas del modelo.

Efecto: descargas de 628–1322 °C (adiabática 1 etapa) pasaron a 84–210 °C;
`W-COMP-T` 7→1 (queda haber_rec, máquina genuinamente caliente),
`W-T-OVERRIDE` 7→0, `W-DUTY-S` 2→0.

### Datos: temperaturas calculadas y congeladas

- Descargas de compresor (13 corrientes en 11 ejemplos): resueltas con el
  modelo multi-etapa y **congeladas al valor resuelto** (lock = snapshot
  del propio solver; evita el desorden de iteración aguas abajo).
- Salidas de mixers/tanques pasivos (8 sitios): T entálpicamente
  consistente por bisección sobre `stream_enthalpy` (duty espurio → 0).
  `W-MIXER-DUTY` 7→1, `W-TANK-DUTY` 3→0.  Excepción: urea M-101 (mezcla
  NH₃-líquido + CO₂-gas: las referencias de entalpía de fases distintas no
  admiten una T adiabática representable; +44 kW residuales documentados).
- rxn_flash_col E-101 re-tipado air cooler → floating head (calienta
  25→87 °C antes del flash; `W-SIGN` 1→0).
- air_sep: ancla de diseño 6 bar en el compresor de aire (sizing ya no
  degenerado) — descarga y duty calculados.
- hda S-5 re-faseado a two_phase; hno3 A8-gas-cool composición propagada
  (no declarada); industrial K-101 y talara F-HTN redimensionados al duty
  calculado.

Los detectores siguen vivos: los tests de `test_solver_awareness` que
usaban estos defectos del catálogo como fixture ahora RE-INTRODUCEN el
defecto en memoria (patrón `test_split_lock_detector_sigue_vivo`) y
verifican que el catálogo quedó limpio.

### Warnings restantes (200) — programas propios

| Familia | n | Programa |
|---|---|---|
| pseudo-componentes | 63 | Frente C (moléculas reales) |
| W-PLACEHOLDER (reactores estructurales) | 24 | química conectada (PR #101) |
| fallback U/ΔT_lm + varios | 26 | HX riguroso (datos completos) |
| HX utility fuera de rango | 14 | partir en WHB + trim cooler (14 coolers que terminan a 40–80 °C) |
| HX cruce térmico | 18 | perfiles T de columnas (capa 3) |
| balance por componente estricto | 0 | ✅ resuelto (ver sección) |
| HX approach < 10 K | 13 | política de utilities (CW 35 °C) |
| W-ENERGY-BLOCK (torres/reactores) | 19 | energía de columnas (capa 3) |
| haber W-COMP-T, hda_full W-PURGE-ABS (PR-G2), urea M-101 | 3 | documentados arriba |

### WHB / utilities de generación

El guard de rango de utility ya no aplica a utilities de generación
(`bfw_to_steam_*`): un WHB enfría gas mucho más caliente que la Tsat del
vapor que genera — ese es su propósito.  Asignados servicios de generación
donde la T de salida del proceso lo permite: ethane_pfr E-101 (827→400 °C,
vapor HP — el TLE clásico del cracker), glass E-101 (1500→200, MP, WHR),
hno3 E-202 (400→200, MP).  Las turbinas de nuclear/rankine (TUR-101,
modeladas como HX) quedaron sin utility (`heat_source_locked` con fuente
vacía: máquina adiabática).  Los 14 `HX-utility-rango` restantes son
coolers que enfrían hasta 40–80 °C: colapsan un WHB + trim cooler reales
en un solo bloque; partirlos es la cirugía sugerida como siguiente paso
(misma mecánica que las bombas/compresores de alimentación).

## Balance por componente — triage (14 → 0)

Los 14 hallazgos (2 CRÍTICO / 12 MAYOR) eran de dos naturalezas:

**CRÍTICO — `industrial/V-202` (metanol 49% off, H₂ 83% off):** estaba
tipado como *splitter* (fracciones 0.85/0.15) pero declaraba composiciones
DISTINTAS en cada salida (S-MeOH 98% metanol, S-vent gas).  Un splitter
fuerza composición idéntica, así que las composiciones locked distintas
fabricaban metanol de la nada (S-MeOH pedía 19 751 t/a de metanol con solo
10 257 en la alimentación).  **Fix:** re-tipado a *flash* real (80 bar,
40 °C) — la termodinámica separa metanol+agua (líquido) de H₂/CO/metano
(vapor) y conserva cada componente a Δ≈0, sin hardcode.  El producto de
metanol pasó de 20 154 (fabricado) a 9 061 t/a (88% de recuperación en un
flash — número honesto).

**MAYOR — 12 redondeos de fracciones hardcodeadas (Δ 1–5%):** dos patrones:
- Mixers y el calentador-mezclador (`leche_gloria/M-101`, `quimpac/M-101`,
  `hda/F-101`) + pass-throughs (HX `leche_gloria/E-102`, homogeneizador
  `S-homog`): **desbloquear la composición de salida** → el solver la
  computa por conservación exacta.
- Separadores reales (`penicillin/F-101` filtro, `hda/V-101` KO drum,
  `quimpac/T-301` torre de secado): la composición de salida ES una spec
  de separación (no se puede propagar).  **Se recalcula la salida
  por-diferencia** (alimentación − productos spec) y se congela exacta.
  En T-301 el cloro seco quedó como spec {Cl₂, agua} y el ácido gastado
  como by-difference {H₂SO₄, agua}.

**Resultado:** catálogo completo **0 CRÍTICO / 0 MAYOR**.  El gate ratchet
`gate_component_balance.py` protege ahora los 41 ejemplos (whitelist =
catálogo completo); cualquier regresión de balance lo pone rojo.

## Pseudo-componentes — triage (63 warnings → 0)

Los 63 warnings colapsaban en **7 pseudo-componentes** y el diagnóstico era
que casi todos son legítimos:

- **Cortes de petróleo** (`crude_oil`, `naphtha`, `kerosene`, `diesel`,
  `gasoline_97`, `atmospheric_residue` — 57 streams en cdu/talara/sugar):
  son pseudo-componentes LEGÍTIMOS caracterizados por rango de ebullición
  (TBP), exactamente como los modela DWSIM/Aspen/Pro-II.  El mensaje viejo
  ("reemplazar por molécula real") era guía ERRÓNEA — un corte lumpea
  cientos de hidrocarburos, no hay una molécula que lo sustituya.  Nueva
  categoría `petroleum_pseudo_allowed` → **INFO** con mensaje honesto.
- **`vegetable_oil`** (6 streams en potato_chips/soap): resultó ser un
  alias de `triolein` en thermo_db (mismo MW 885.4, **con** Antoine) — es
  modelable, no un pseudo sin VLE.  Movido a `food_pseudo_allowed` (aceite
  bio ~triolein) → INFO.  (No se renombró a `triolein` porque la reacción
  R030 de saponificación referencia `vegetable_oil` por nombre.)
- **`syngas`**: único que queda en `industrial_pseudo` → warning genuino
  (mezcla H₂/CO/CO₂/CH₄ variable; modelar como componentes reales cuando
  la composición esté fija).  Hoy 0 streams lo usan.

**Resultado:** 63 → **0 warnings de pseudo**; el total de warnings
surfaced del catálogo bajó de 196 a **119**.  cdu, potato_chips y soap
quedaron completamente limpios y entraron a `CLEAN_EXAMPLES`.  La
clasificación vive en `data/pseudo_components.json` (curada, versionada);
`test_consistency_audit` verifica petróleo→INFO y syngas→warning.

## Integración energética — WHB + trim cooler (14 → 1)

Los 14 coolers que enfriaban un stream caliente (260–1450 °C) hasta
40–130 °C en UN bloque disparaban `HX-utility-rango` (el agua de
enfriamiento no toma un gas a 800 °C).  La planta real recupera ese calor
de alta: **caldera de recuperación (WHB) que genera vapor** + **trim cooler
con agua** para el acercamiento final.  Cada cooler se partió en dos:

- WHB (`Heat exch. — WHB packaged`, `bfw_to_steam_MP`): enfría hasta 200 °C
  generando vapor MP (Tsat 184 °C).
- Trim cooler (`floating head`, `cooling_water`): 200 °C → T final.

El stream intermedio hereda la composición locked de la salida (un cooler
no cambia composición) → cero propagación distinta, cero `redundant_lock`.
**13 de 14 aplicados** (cdu ×2, cement, ethane_pfr, ethylene_crk,
haber_rec, hda_full, methanol, smr_eq, sulfuric, talara ×3).  ISBL de esos
ejemplos cae 1–6% (el vapor recuperado descuenta OPEX) salvo donde el WHB
agrega CAPEX neto (sulfuric +4.6%).

**Diferido — `hda/E-102`:** alimenta un flash spec'd (V-101) dentro de un
loop de reciclo; el bloque extra corre la convergencia del tear ~45 t/a y
descuadra el balance.  Requiere re-anclar el tear, fuera del alcance de
esta cirugía.  Queda 1 `HX-utility-rango` documentado.

**Nota de simplificación:** los servicios muy calientes (cement 1450 °C,
cracking 827 °C) generan solo vapor MP en este modelo de 2 bloques; una
planta real cascada HP→MP→LP en varios WHB.  El modelo es correcto en masa
y energía; la integración multi-nivel es refinamiento futuro.

## Energía de columnas — condensador contabilizado (W-ENERGY-BLOCK 19→16)

Una columna es un equipo de DOS duties: reboiler (Q_reb > 0, vapor) y
condensador (Q_cond < 0, agua).  El solver FUG ya computaba AMBOS
(`design_column` devuelve `Q_reb_kW` y `Q_cond_kW`) pero asignaba solo
`b.duty = Q_reb` y **descartaba el condensador**, así que el chequeo de
energía trataba la columna como equipo de un solo duty y reportaba un
residual espurio = −Q_cond (ethanol T-101: −1578 kW, el peor del catálogo).

**Fix:** el solver ahora almacena `_Q_reb_kW` y `_Q_cond_kW`; el chequeo
`W-ENERGY-BLOCK` es column-aware (balance neto = Q_reb + Q_cond).  Cerró 3
de 8 columnas (acetic, air_sep, ethanol — incluido el residual gigante).
Golden intacto (b.duty sin cambio; solo el chequeo y un atributo runtime).

**Diferido — 5 columnas (el programa grande):** distillation, ethylene_crk,
hda, industrial, rxn_flash_col.  Su residual es la brecha entre el método
FUG (Q_reb = R·D·ΔH_vap promedio, condensador total) y el ΔH riguroso de
las corrientes — se destapa cuando el destilado sale VAPOR (industrial
T-201 vaporiza 23 711 t/a y FUG da Q_reb=271 vs ΔH~800 kW).  Cerrarlo
requiere **energía de columna rigurosa (tray-by-tray)** con el mismo modelo
entálpico que las corrientes.  El mensaje del warning ahora lo dice
explícitamente (no "Ts no cierran", que era engañoso) para que el
estudiante entienda que es la aproximación del método, no un error de masa.

## Verificación

- `gate_examples.py` 41/41 verde (directo y `--registry`).
- `tests/test_examples_clean.py` limpio; `tests/test_examples_start.py`
  congela inicios (corriente/bomba/compresor + succión).
- Balance por componente: 2 CRÍTICO / 12 MAYOR — idéntico a antes de la
  auditoría (preexistentes, catalogados en `component_balance_audit.json`).
- Suite unittest = línea base; tests estilo-función de los ejemplos
  tocados en verde (`test_solver_awareness` reapuntado: el caso didáctico
  del detector pasó de ammonia-duty-espurio a methanol-intercooler).
