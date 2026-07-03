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

## Verificación

- `gate_examples.py` 41/41 verde (directo y `--registry`).
- `tests/test_examples_clean.py` limpio; `tests/test_examples_start.py`
  congela inicios (corriente/bomba/compresor + succión).
- Balance por componente: 2 CRÍTICO / 12 MAYOR — idéntico a antes de la
  auditoría (preexistentes, catalogados en `component_balance_audit.json`).
- Suite unittest = línea base; tests estilo-función de los ejemplos
  tocados en verde (`test_solver_awareness` reapuntado: el caso didáctico
  del detector pasó de ammonia-duty-espurio a methanol-intercooler).
