# hno3/E-203 — oxidación NO→NO₂ como override de diseño (decisión documentada)

> **Estado:** override **intencional y declarado**, no física calculada.
> **Decisión:** Camino B (documentar) — el Camino A (química real) NO es un
> quick-win, se difiere como proyecto de cadena (ver §4).
> **Gate al cerrar:** `gate_examples.py` 41/41 byte-idéntico — esta nota no
> toca cálculo, JSON computado ni golden.
> **Fecha:** 2026-06-15.

---

## 1. El hallazgo (del inventario de hardcode)

`docs/inventario_hardcode.md` marcó **hno3/E-203** como el "mentiroso de
física": un enfriador (`Heat exch. — air cooler`, pass-through) cuya
composición de salida cambia —aparece NO₂— **sin reacción declarada**. El
solver lo expone con `[W-COMP-OVERRIDE]` (gracias a T30):

```
[W-COMP-OVERRIDE] A8-gas-cool: composición declarada difiere del inlet en un
equipo pass-through (E-203) — override manual conservado. Si hay transformación
química, declarar una reacción; si no, considerar dejar que el motor propague.
```

## 2. Auditoría: el número es FINGIDO pero FÍSICAMENTE CONSISTENTE

E-203 enfría los gases nitrosos del proceso Ostwald (salida a 50 °C, duty
−248.8 kW). La oxidación `NO + ½O₂ → NO₂` ocurre realmente al enfriar (es
favorecida a baja T), así que la composición declarada NO es absurda. Balance
verificado a mano sobre el feed A7b-gas-eco (15 000 t/a):

| componente | inlet (frac / t·a⁻¹) | outlet (frac / t·a⁻¹) | Δ |
|---|---|---|---|
| nitric oxide (NO) | 0.112 / 1680 | 0.080 / 1200 | **−480** |
| oxygen (O₂)       | 0.062 / 930  | 0.0449 / 673.5 | **−256.5** |
| nitrogen dioxide (NO₂) | 0 / 0   | 0.0491 / 736.5 | **+736.5** |
| N₂, N₂O, H₂O      | sin cambio   | sin cambio     | 0 |

Chequeos (MW: NO 30.01, O₂ 32.00, NO₂ 46.01):

- **Estequiometría:** O₂_cons / NO_cons (mol) = 8.016 / 15.995 = **0.501 ≈ 0.5** ✓
  (`NO + ½O₂ → NO₂`); NO consumido (16.0 mol) = NO₂ producido (16.0 mol) ✓.
- **Masa:** NO_cons + O₂_cons = 480 + 256.5 = **736.5 = NO₂ producido** ✓.
  Global `res.mass_balance_errors == 0`.
- **O₂ disponible:** inlet 930 t/a, consumido 256.5 → **674 t/a remanente > 0**.
  El feed sostiene el NO₂ que aparece — el número NO es imposible.
- **Conversión de NO:** 480 / 1680 = **28.6 %** (oxidación parcial; el resto
  del NO se oxida aguas abajo, ver §3).

**Conclusión:** es un número *fingido* (escrito a mano, no calculado por una
reacción) pero *posible y consistente*, no un balance falso.

## 3. Por qué Camino A (química real) NO es un quick-win

El proceso Ostwald de hno3 tiene la oxidación NO→NO₂ modelada en DOS lugares:

| bloque | rol | estado actual |
|---|---|---|
| **E-203** (air cooler) | oxidación **parcial** al enfriar | override hardcodeado → `[W-COMP-OVERRIDE]` |
| **R-301** (reactor) | oxidación **dedicada** | declara `R_OXIDATION_NO` → `[W-PLACEHOLDER]` |
| **T-401** (torre absorción) | `3NO₂ + H₂O → 2HNO₃ + NO` | declara `R_ABSORB_NO2` → `[W-PLACEHOLDER]` |

`R_OXIDATION_NO` **no existe** en `reactions_db` (`rdb.get(...)` → `None`);
por eso R-301 es placeholder. **El problema de acotamiento:** crear
`R_OXIDATION_NO` como reacción real (estilo T29a/R035) la activaría también en
**R-301**, que comparte el id → cambiaría el comportamiento y el golden de
R-301, violando "no tocar otros bloques de hno3".

Peor: la oxidación NO/NO₂ y la absorción T-401 están **acopladas** (T-401
regenera NO que recicla), y O₂/NO/NO₂ se reparten a lo largo de E-203→R-301→
T-401. Un Camino A riguroso exige modelar la cadena completa de oxidación +
absorción de forma coherente, no un bloque aislado. **Eso es un proyecto, no
un quick-win.**

Se midió además una variante intermedia (declarar el placeholder
`R_OXIDATION_NO` en E-203 para que muestre `[W-PLACEHOLDER]` como R-301):
**rechazada** porque exime a E-203 del balance de energía y le **borra su duty
real de enfriamiento** (−248.8 kW; `sum_duty` −778.4 → −529.6). E-203 ES un
enfriador, no un reactor — esa variante es físicamente incorrecta.

## 4. Decisión: Camino B (override documentado)

Se conserva la composición declarada de `A8-gas-cool` **tal cual** (el número
es consistente, §2) y se la trata como **override intencional de diseño**: una
oxidación parcial (28.6 %) que ocurre durante el enfriamiento, escrita a mano
porque la cadena de oxidación de hno3 todavía no se calcula.

- **Transparencia:** el override sigue **marcado en el simulador** por
  `[W-COMP-OVERRIDE]` sobre `A8-gas-cool` — no se silencia. Cualquiera que
  resuelva hno3 ve que esa composición es un override, no física calculada.
- **Sin tocar cálculo:** no se mueve masa, duty, ni golden (byte-idéntico).
- **JSON sin comentario inline:** el formato JSON no admite comentarios y los
  campos fuera del schema de `Stream` se descartan en el round-trip
  `to_dict` (sin precedente en los ejemplos), así que la documentación
  autoritativa vive en esta nota, no en un campo fantasma del JSON.

## 5. Trabajo futuro (Camino A diferido)

Proyecto **"cadena de oxidación + absorción de hno3"** (no este PR):

1. Curar `R_OXIDATION_NO` (`NO + ½O₂ → NO₂`) en `reactions_db` con ΔH desde
   `thermo_db` (ΔHf NO, O₂, NO₂), T_range citado (oxidación favorecida a baja
   T — Ostwald clásico), trazable estilo R035.
2. Curar la absorción `R_ABSORB_NO2` (`3NO₂ + H₂O → 2HNO₃ + NO`).
3. Modelar oxidación en E-203 (parcial, kinética/T del enfriador) **y** R-301
   (oxidación dedicada) de forma coherente, con O₂ repartido y el recycle de
   NO de T-401 cerrando el lazo.
4. Verificar que H/N/O cierran a lo largo de toda la cadena y regenerar el
   golden de hno3.

Hasta entonces, E-203 queda como override declarado y visible.
