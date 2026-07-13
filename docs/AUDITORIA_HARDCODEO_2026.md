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

## Notas — warnings restantes (esperados, NO se persiguen a cero)

Cierre de la campaña: **237 → 105 warnings surfaced**.  Los balances y
pseudos que podían enseñar algo FALSO en la lección básica están en **0**.
Los 105 restantes son awareness de diseño, defaults conservadores o
programas con nombre — se dejan visibles a propósito (el simulador es
honesto sobre sus aproximaciones), no son bugs:

| Familia | n | Naturaleza / por qué se deja |
|---|---|---|
| W-PLACEHOLDER | 24 | Reactores estructurales (química vía outputs locked): diseño intencional; su programa es la química conectada (PR #101). Awareness, no error. |
| HX-fallback-U | 21 | El HX usa U/ΔT_lm de tabla cuando faltan datos rigurosos (utility de un solo punto). Default conservador declarado — el número es defendible, el warning avisa que no es riguroso. |
| HX-cruce-termico | 20 | El perfil ΔT proceso/utility se cruza porque las utilities se modelan a T constante (no zonificadas). Correcto en energía; el perfil fino requiere HX multi-zona. |
| W-ENERGY-BLOCK | 16 | 5 columnas (energía tray-by-tray, documentado); 6 compresores (aftercooler implícito, documentado); 2 reactores (signo de Q_rxn); 3 vessels/horno. |
| HX-approach | 13 | Approach < 10 K con agua de enfriamiento a 35 °C — política de utilities, no error de modelo. Bajar el approach = subir área/costo (trade-off real). |
| otro / T-calc / W-COMP-T / W-PURGE-ABS / W-MIXER-DUTY | 11 | Singletons documentados: haber_rec K-101 (máquina genuinamente caliente), hda E-102 (diferido), hda_full purga (PR-G2), urea M-101 (mezcla bifásica NH₃-líq+CO₂-gas). |

**Criterio:** un warning se persigue a cero si puede hacer que el
estudiante aprenda algo incorrecto en un balance de masa o energía básico
(esos están resueltos).  Un warning que documenta honestamente una
aproximación de método (FUG, U de tabla, utility de un punto) o una
decisión de diseño (approach, placeholder) se DEJA visible — esconderlo
sería menos honesto que mostrarlo.

## Verificación

- `gate_examples.py` 41/41 verde (directo y `--registry`).
- `tests/test_examples_clean.py` limpio; `tests/test_examples_start.py`
  congela inicios (corriente/bomba/compresor + succión).
- Balance por componente: 2 CRÍTICO / 12 MAYOR — idéntico a antes de la
  auditoría (preexistentes, catalogados en `component_balance_audit.json`).
- Suite unittest = línea base; tests estilo-función de los ejemplos
  tocados en verde (`test_solver_awareness` reapuntado: el caso didáctico
  del detector pasó de ammonia-duty-espurio a methanol-intercooler).

---

# Sesión 2 (2026-07) — mejoras altas/medias

Continuación tras el merge del PR #108.  Foco: cerrar los programas
grandes que quedaron diferidos.

## ALTA — Energía de columna por PRIMERA LEY (W-ENERGY-BLOCK columnas 5→0)

Las 5 columnas que el fix column-aware no había cerrado (el ΔH riguroso no
coincidía con el Q_reb del FUG) ahora cierran EXACTO.  Para cada columna
adiabática se computa Q_cond por su latente (ajustado por fase del
destilado: condensador parcial si sale vapor, total si líquido) y se
DERIVA Q_reb = ΔH_corrientes − Q_cond (primera ley).  El caso testigo
industrial T-201 (destilado vapor) pasó de Q_reb=271 FUG (condensador total
ficticio) a Q_reb=699, Q_cond≈0 (físico).  W-ENERGY-BLOCK total 16→11.

## ALTA — Química conectada: triage 4 conectables / 20 legítimos

De los 24 W-PLACEHOLDER, sólo **4** son técnicamente conectables (acetic
R026, beer+bread R007, sulfuric R006): reacción curada con MW completo en
todas las especies.  Los otros **20 son legítimos** — el motor
estequiométrico no puede resolverlos porque usan pseudo-componentes sin MW
(polietileno, jabón, cal, cortes de petróleo) o química no modelable
(electrólisis, fusión, HDS/FCC/reformado).  Nuevo helper
`_reaction_all_species_have_mw` + mensaje que lo dice.  Conectar los 4
requiere re-propagar su cadena downstream (separadores hardcodeados) — es
Frente C acotado a 4 ejemplos, no se hizo en batch para no arriesgar el
balance 0/0.

## MEDIA — redundant_lock 18→0

Triage empírico (¿desbloquear cambia el resultado?).  Dos guards nuevos en
el detector (separador multi-salida y reactor-placeholder son load-bearing,
no redundantes) + 7 locks genuinamente redundantes quitados de los datos
(propagan idéntico: air_sep N2/O2, hda_full S-4, industrial blowdown/steam/
supply, y toda la cadena de syngas de smr_eq aguas abajo del reactor de
equilibrio R003/R002).  Golden intacto.

## MEDIA — hda/E-102 WHB: diferido con razón

Reintentado con mid locked + recálculo iterativo de S-6 por-diferencia; no
converge.  E-102 alimenta el KO drum V-101 (separador spec'd con purga de
masa locked) DENTRO del loop de reciclo de tolueno; el bloque extra corre
la convergencia del tear y descuadra el balance ~45 t/a.  Requiere
re-anclar el tear del reciclo — cambio a nivel de solver, fuera del alcance
de esta limpieza.  Queda 1 HX-utility-rango documentado.

## Pendiente opcional — caracterización TBP de cortes de petróleo

Los 6 cortes (crude_oil, naphtha, diesel, kerosene, gasoline_97,
atmospheric_residue) son hoy pseudo-componentes INFO legítimos.  Darles VLE
riguroso requiere caracterización por curva de destilación (TBP → pseudo-
componentes con Tb/SG/MW y correlaciones de Lee-Kesler/Riazi) — una adición
de termodinámica sustancial y de bajo retorno (ya son INFO, no warning).
Documentado como mejora futura, no bloqueante.

## MEDIA/ALTA (sesión 3) — química conectada en los 4 reactores tratables (W-PLACEHOLDER 24→20)

Los 4 reactores que el triage marcó CONECTABLES (todas las especies con MW)
ahora corren química real, con su cadena downstream re-propagada:

- **beer / R007** (fermentación glucosa→2 etanol+2 CO₂): V-101 separa el CO₂
  (único gas) del vino por-diferencia.
- **acetic / R026** (carbonilación metanol+CO→ácido acético): V-101 quita el
  CO gas; T-101 (columna activa) se auto-resuelve.  El output honesto
  (acetic_acid 0.9456 a conv 0.95, antes 0.99 hardcodeado) sube el destilado
  de metanol sin reaccionar de D≈10 a D≈58.
- **bread / R007**: H-101 (horno) evapora los volátiles (CO₂, etanol) + la
  fracción de agua del original; S-pan pass-through desbloqueado.
- **sulfuric / R006** (2SO₂+O₂→2SO₃): la cadena de coolers desbloqueada
  propaga; ABS-101 mantiene la estequiometría SO₃+H₂O→H₂SO₄ recalculada a
  mano (la hidratación no está curada en el catálogo — no se tocó
  reactions_db para no arrastrar termo por Hess).

Método: `reactions=[real]`, `reactor_mode='stoich'`, `heat_of_reaction=0`
(el solver lo computa), output del reactor desbloqueado, y cada separador
downstream recalculado por-diferencia (iterando hasta converger).  Balance
por componente **0/0** en los 4; el calor de reacción ahora es calculado
(acetic sum_duty 16→−105, sulfuric −77→−98 exotérmicos); ISBL intacto.

**Restan 20 W-PLACEHOLDER legítimos** (química no modelable por el motor:
pseudo-componentes sin MW, electrólisis, fusión, cortes de petróleo).

## Estado de W-ENERGY-BLOCK restantes (12) — awareness legítimo

Tras cerrar las columnas por primera ley, quedan 12, todos honestos:

- **6 compresores**: el modelo multi-etapa (Q_intercool) cierra los que
  comprimen gas ideal, pero NO los casos con quirks físicos: urea K-101
  (descarga a fase densa/líquida a 150 bar — el gas se licúa, el ΔH incluye
  latente que el modelo gaseoso no captura), hno3 K-501 (turboexpansor,
  duty<0), haber_rec K-101 (máquina genuinamente caliente a 333 °C),
  industrial K-202 (duty≈0 sobre reciclo). No son bugs — el warning avisa
  que el modelo isentrópico simple no aplica a esos regímenes.
- **3 reactores** (ammonia, methanol, sulfuric R-101): "posible signo de
  Q_rxn o Ts de producto". El balance de energía de reactor depende de la
  convención de signo del calor de reacción y la T de producto declarada;
  es un programa aparte (energía de reactor, análogo a energía de columna).
- **3 vessels/otros**: potato_chips FR-101 (freidora), sulfuric ABS-101
  (absorbedor con calor de absorción implícito), etc.

Estos se dejan visibles a propósito (el simulador es honesto sobre los
regímenes donde su modelo simplificado no aplica), coherente con el
criterio de la campaña: perseguir a cero sólo lo que puede enseñar algo
falso en un balance básico (masa/energía → ya en 0), documentar el resto.

---

# Sesión 4 (2026-07) — el gate rojo, la suite verde y dos bugs reales

Continuación tras el merge del PR #110.  Al retomar, `gate_component_balance`
estaba ROJO (2/41) y la suite pytest tenía 12 fallos preexistentes.

## Gate de balance por componente: 41/41 verde otra vez

- **hno3/V-201** (0/3 MAYOR): el condensador Ostwald hace DOS químicas — la
  oxidación 2NO+O₂→2NO₂ (que antes vivía como override en E-203) y la
  absorción R034.  Sólo declaraba R034.  Verificado numéricamente que
  R033+R034 explican el cambio exacto (agua −36.6, NO −420, NO₂ +457 t/a);
  declarar ambas cierra el LSQ del auditor a 0/0.
- **sulfuric/ABS-101** (0/2 MAYOR): las salidas lockeadas de la sesión 3 no
  arrastraban el SO₂ no convertido (55.2 t/a entraban, 20.0 salían) y el
  H₂SO₄ excedía el SO₃ disponible.  Re-derivadas por estequiometría R032
  exacta sobre el gas forward de los feeds (2065.0 t/a) y agua de absorción
  ajustada a la spec de producto 98%: S-H2O 306.34→295.1, S-H2SO4
  1532.3→1475.3, S-vent 840.6→884.8.  Además el trim cooler E-101T ya no
  queda con masa retro-propagada inconsistente (2055.6 vs 2065.0).

## Suite completa verde: 12 fallos preexistentes con dos bugs reales

**Bugs de código encontrados por los tests:**

1. `thermo_db._pseudo_names()` no leía `petroleum_pseudo_allowed` (categoría
   creada en el triage de pseudos al sacar los cortes de `industrial_pseudo`)
   → los 6 cortes de petróleo habían perdido su procedencia `origin='pseudo'`
   y volvían a `unverified`.
2. `equipment_auxiliaries._AUX_STACK_GAP=36` px: el corredor header↔bomba era
   más angosto que las bandas padded del router (12 px por lado) y el retorno
   del lazo de CW clipeaba el tope de la bomba (3 cruces en metanol).  36→60.

**Tests desactualizados por sesiones deliberadas (actualizados al estado
nuevo, con el patrón detector-sigue-vivo donde aplica):** t30 (el override de
E-203 fue retirado — el mecanismo se prueba re-introduciéndolo en memoria y
el catálogo se verifica sin overrides), placeholders (4 conectados vs 4
diferidos), example_locks (hda S-9-recic es tear real convergido), service
loops (3 lazos con el trim del split WHB), inspector (air_sep con ancla de
6 bar), y `gate_economics_panel` (el sanity MACRS≠lineal sólo aplica con
NPV>0 — un proyecto sin renta imponible no paga impuestos y la igualdad es
aritmética correcta; industrial quedó honestamente no rentable tras el
retipado de V-202).

## TRABAJOS_FUTUROS §2 resuelto: is_cross_exchange y las auto_aux

El conteo estructural ≥2in/≥2out de `is_cross_exchange` contaba el lazo CW
propio del HX como si fuera proceso → falso positivo "E-101: cross-exchange
no cierra energía (>5%)" en metanol+aux.  Las corrientes `auto_aux` se
excluyen ahora del conteo; el tratamiento (utility de trim) no cambia, sólo
desaparece el mensaje engañoso.  Regresión cubierta en test_service_loops.

## Verificación

pytest **586 passed** / unittest **OK** / gates **7/7 verdes** (examples
directo y --registry, component_balance, eos, eos_flash, simulate,
pressure_source, economics_panel).


## Energía de reactor por PRIMERA LEY (W-ENERGY-BLOCK 12→9)

El programa anunciado en la sesión 3 ("energía de reactor, análogo a energía
de columna").  El AUTO-DUTY de los reactores con química real aproximaba el
duty externo con `Q_sens = m·c̄p_in·(T_op − T_in)` — el cp de la ENTRADA:

- ignoraba el cambio de composición (Cp y latente de los PRODUCTOS: el NH₃
  del efluente no tiene el ΔH_vap del N₂+H₂ del feed);
- ignoraba cualquier T de salida DECLARADA ≠ T_op (ammonia opera con
  T_op=450 °C pero su efluente de diseño sale a 500 °C: los 85 kW de ese
  calentamiento quedaban sin dueño → residual espurio).

**Fix (flowsheet_solver, AUTO-DUTY):** con Ts, composición y fase de los
outlets ya resueltas, el duty se DERIVA por primera ley con el MISMO modelo
entálpico de corrientes que usa el chequeo: `duty = H_out − H_in + Q_rxn`
(endo+).  Fallback al Q_sensible previo si alguna entalpía no es resoluble
(iteraciones tempranas).  Adiabático sigue en duty=0.

Efecto: los duties de 17 reactores del catálogo se refinaron (golden
regenerado; ISBL intacto en TODOS — el duty de reactor no alimenta el
costeo).  Casos testigo: ammonia R-101 −146.6→−61.8 kW (la reacción libera
146.6; 84.8 calientan el efluente 450→500 °C y el jacket sólo quita 61.8),
methanol −808.9→−616.8, sulfuric −20.9→−45.8.  Los 3 W-ENERGY-BLOCK de
reactor desaparecen; quedan **9** (6 compresores con quirks físicos + 3
vessels: freidora, absorbedor, horno F-301), todos awareness documentado.
Detector vivo: `test_energia_reactor_detector_sigue_vivo` re-introduce el
duty isotermo en memoria y exige que vuelva a disparar.


## Chequeo ELEMENTAL de balance (TRABAJOS_FUTUROS §13 — estreno)

Nuevo en `audit_examples_components`: conservación de ÁTOMOS por bloque
(`audit_block_elements`, mode='element').  A diferencia del chequeo por
especie, aplica también a reactores con química real y placeholders — los
átomos se conservan aunque haya reacción — y caza reacciones mal balanceadas
u outputs de reactor escritos a mano que crean/destruyen elementos.  La masa
de cada componente se reparte por fracción másica de FÓRMULA (thermo_db ya
trae las 310), así los bloques de pura conservación dan 0 exacto; los
pseudo sin fórmula ('Mix') saltean el bloque silenciosamente.

**Estreno sobre el catálogo: 8 hallazgos en 3 ejemplos, triage:**

- **air_sep/V-101 (arreglado)**: el secador quitaba 5 t/a de agua de un
  aire SIN humedad declarada (agua creada de la nada).  El feed declara
  ahora 0.5% de humedad ({N2 0.763165, O2 0.231835, H2O 0.005}) y el
  balance cierra EXACTO; S-pure queda seco e idéntico aguas abajo.
- **hno3/R-301 (arreglado)**: la composición de salida del oxidador estaba
  redondeada a mano a 2–3 decimales (el O no cerraba 1.4%; el agua "perdía"
  245 t/a en una oxidación que no la toca).  Recomputada EXACTA con
  2NO+O₂→2NO₂ manteniendo la spec de diseño (NO out = 0.009).
- **talara/R-SMR y hno3/T-401 (diferidos, documentados)**: estructurales —
  el SMR declara más H2 del que su CH4 permite (sin steam), y la torre de
  absorción produce más HNO3 del que el N alimentado alcanza.  Cirugías de
  tren completo (TRABAJOS_FUTUROS §16–17), confinadas en el ratchet.

**Ratchet:** `tests/test_element_balance.py` — 39/41 elemental-limpios;
cualquier hallazgo nuevo o fuera del bloque documentado es regresión.
Baseline versionado en outputs/element_balance_baseline.json.


## talara R-SMR: el tren de H2 re-dimensionado (§16 resuelto)

El chequeo elemental había destapado el peor hallazgo del catálogo: el
reformador declaraba 2 700 t/a de H2 + 300 de CO2 desde 3 000 t/a de CH4
sin vapor — atómicamente imposible (el H salía de la nada y el 96% del C
desaparecía).  Cirugía aplicada manteniendo la demanda de H2 de los tres
hidrotratadores (800+1 500+400 = 2 700 t/a) como spec de diseño:

- **Nuevo feed de vapor de proceso** `C21-steam` (12 051.5 t/a, fase
  vapor a 300 °C) desde el header TK-STM — la regla de arranque lo acepta
  sin excepción (el vapor se genera a presión, no se comprime).
- **CH4 re-dimensionado**: C20-CH4 3 000 → 5 368.9 t/a (334.49 kmol/a
  reaccionan + el slip de 2.7 t/a que sale con el H2).
- **CO2 honesto**: C20b-CO2 300 → 14 720.4 t/a (la relación másica CO2/H2
  del SMR es ~5.5 — el número chico anterior escondía el carbono).

Balance elemental EXACTO (C/H/O en 0.0); el ratchet pasa a **40/41**
(queda sólo hno3/T-401, §17).  ISBL de talara +0.36% (el compresor K-101
ahora dimensionado al caudal real de CH4); golden regenerado.


## industrial V-201: separador real y fin del carrusel de metanol (§15)

El último gran estructural del catálogo.  V-201 repartía el efluente del
reactor en crudo (25 000 t/a) y reciclo (275 000) con la MISMA composición
(41% metanol): un splitter de caudal, no un separador — 113 000 t/a de
metanol recirculaban a perpetuidad sin salida física, y el producto real
había caído a 9 061 t/a cuando V-202 se volvió honesto.

**Cirugía:**
- V-201 re-tipado a **flash real** (40 °C / 80 bar, patrón V-202): condensa
  metanol+agua (crudo 89% MeOH) y deja el gas magro (83% H2 / 7% MeOH).
- El punto fijo del lazo (reciclo 280 930 t/a) se iteró POR FUERA del
  solver — el tearing aún no aplica fracciones de splitter
  (TRABAJOS_FUTUROS §3), Wegstein se quedaba en el valor semilla — y se
  congeló como ancla sintética junto con el crudo (21 840.8).  Fracciones
  de V-203 ajustadas exactas (0.091103/0.908897) para que el reciclo
  cierre con 0.0 de slack.
- V-202 sin gases que ventear → tambor de producto (vent eliminado);
  S-vap re-faseado líquido (condensador total a 80 bar).

**Resultado:** producto 9 061 → **21 280 t/a** de metanol crudo al 91.5%
(consistente con el CO alimentado: el feed es H2/CO molar ≈ 19, el CO
limita), balance por especie Y elemental 0/0 en una sola pasada de solve,
idempotente.  NPV −67.3M → **+7.36M**: la "no rentabilidad honesta"
documentada era el artefacto de arreglar V-202 dejando el carrusel; con
TODA la física correcta el ejemplo vuelve a ser rentable y el sanity
MACRS≠lineal del gate económico aplica de nuevo por sí solo.


## hno3 T-401: el tren de absorción re-derivado (§17 — ratchet elemental 41/41)

El último estructural del catálogo.  Los outputs a mano de T-401 producían
más HNO3 del que el N alimentado permitía (y el aire de blanqueo era 6×
chico para la re-oxidación).  Re-derivación con extents exactos:

- **R034** (3NO2+H2O→2HNO3+NO) fija ξ2=25.16 kmol por el N reactivo
  disponible → producto 6 200→**5 707.7 t/a @60%**.
- **R033** (2NO+O2→2NO2) debe re-oxidar el NO regenerado: ξ1=14.54 kmol →
  el aire de blanqueo sube 500→**3 218.7 t/a** (O2 estequiométrico + 2.5%
  de exceso en colas, el diseño real de una torre Ostwald).
- Agua de absorción 3 000→**1 532.9** (la que admite el balance con ácido
  al 60% y colas al 2.9% de humedad).
- Colas A14 re-derivadas (14 043.9 t/a, comp exacta hasta el stack) y
  blanqueador V-501 ajustado (vent 91.8 t/a, producto final 5 615.9 @61%).

**El catálogo completo audita limpio en especie Y elemental: ratchet
41/41, _KNOWN_DIRTY vacío.**  Con esto cierran los cuatro estructurales
históricos (§14 hda_full, §15 industrial, §16 talara, §17 hno3).
