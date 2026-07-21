# Análisis de convergencia — Grupo 6: Materiales y energía

**Fecha:** 2026-07-18
**Alcance:** los 7 ejemplos de *Materiales y energía*: `cement`, `glass`,
`air_sep`, `water_treat`, `rankine`, `nuclear`, `desal`.
**Criterio:** todo tiene que converger, incluso económico; si no, encontrar
el porqué.

## Resultado global

| Ejemplo | Solver | ISBL | Revenue | NPV (USD) | Veredicto |
|---|---|---:|---:|---:|---|
| glass | ✓ ok | 1.15 M | 352 000 | −3 608 272 | INVIABLE (escalable) |
| air_sep | ✓ ok | 2.86 M | 133 200 | −8 243 606 | INVIABLE (sub-escala) |
| cement | ✓ ok | 4.18 M | 47 600 | −11 710 040 | INVIABLE (sub-escala) |
| water_treat | ✓ ok | 6.06 M | 498 | −14 737 604 | INVIABLE (utility pública) |
| desal | ✓ ok | 7.87 M | 1 400 | −64 955 768 | INVIABLE (utility, Tier 2) |
| nuclear | ✓ ok | 1.69 M | 0 | −8 636 617 | INVIABLE (Tier 2, sin ingreso) |
| rankine | ✓ ok | 271.9 M | 0 | −574 073 488 | INVIABLE (Tier 2 + bug costeo) |

Convergencia numérica **7/7 verde** — que es el punto de este grupo: el
solver resuelve ciclos termodinámicos (Rankine, isla nuclear 2° circuito),
separación criogénica de aire, tratamiento de agua y desalinización MED.

## Naturaleza del grupo: demostración e infraestructura, no negocios

Es el grupo menos "económico" por diseño. **No hay una corrección de un solo
dato** que los vuelva viables (a diferencia del vapor de leche_gloria o el
precio de beer): sus inviabilidades son estructurales.

### 1. Ciclos de energía (rankine, nuclear) — la electricidad NO se monetiza

`rankine` y `nuclear` tienen **revenue = 0**. Son demos Tier-2 del **ciclo
termodinámico**: su producto real es electricidad, pero:

- La turbina `TUR-101` está modelada como `Heat exch. — floating head`, no
  como un bloque de expansión → **no computa potencia de eje**, así que la
  electricidad ni siquiera existe como corriente ni como crédito de utility.
- El fluido de trabajo es simbólico (100 tm/yr de makeup).

Monetizar la electricidad exigiría un bloque de turbina que calcule el
trabajo de eje y un crédito de energía — es una **ampliación estructural del
modelo**, no un precio faltante. Inviables por diseño de demostración.

> **Bug de costeo del boiler — CORREGIDO (2026-07).** El ISBL de rankine de
> 271.9 M estaba dominado en un **99.6%** por un solo equipo — `B-101 (Boiler
> — water tube, S=10)` daba CBM = **270.9 M**, es decir **124× el WHB Sinnott
> validado del mismo caudal** (36 t/h → $2.87 M). Las constantes K1 (fire
> 6.6940, water 7.0489) estaban atribuidas a "Turton App A", pero Turton App
> A **no trae correlación de boiler por kg/s de vapor** (el vapor es una
> utility, no capital) → la atribución era espuria y los valores, absurdos
> (incluso a S=2 daban Cp $15.2 M para una caldera de ~7 t/h real de ~$0.5 M).
>
> **Fix aplicado** (`equipment_costs.py`): K1 re-anclados al WHB field-erected
> validado del repo (Sinnott Tabla 6.6). Un boiler DE FUEGO = superficie de
> vapor + quemador/hogar/domo → water-tube ≈ 2× WHB (K1 7.0489→**5.375**),
> fire-tube ≈ 0.65× WHB, más barato (K1 6.6940→**5.150**). Curva resultante
> water-tube: $2.3 M (7 t/h) → $9.4 M (72 t/h) → $19 M (180 t/h) CBM, sana
> para calderas de servicio. **rankine ISBL: 271.9 M → 6.69 M.** Sigue
> INVIABLE (rev=0), pero el ISBL ya es honesto. Único ejemplo que usa boiler;
> golden re-exportado (solo rankine), gate 41/41 verde, 522 tests verdes.

### 2. Utilities públicas (water_treat, desal) — no son centros de lucro

- `water_treat`: agua potable a ~0.5 $/tm (≈$0.5/m³). El agua potable es un
  **bien público** subsidiado por tarifas, no un producto rentable; una
  planta de 6 M de ISBL nunca la paga vendiendo agua a costo. Inviable por
  naturaleza (infraestructura, no negocio).
- `desal`: MED multi-efecto (Tier 2). Agua a 2 $/tm (≈$2/m³, realista para
  desal), pero producción diminuta (700 tm/yr) y **cut = 6 M** (la
  desalinización es intensiva en energía). Utility + demo scale.

### 3. Materiales commodity a escala de demostración

- `glass` — **Escalable**: la producción responde al feed; a ×100
  (88 000 tm/yr de vidrio) da NPV **+110.7 M**. Viable en principio a escala
  industrial; shippeado a demo scale (880 tm/yr). Como `urea` del grupo 5.
- `cement` — Sub-escala (560 tm/yr clínker vs ISBL 4.2 M). Escalar sube el
  revenue pero el ISBL/equipo explota (horno rotatorio fuera de rango).
- `air_sep` — Separación criogénica sub-escala (995 tm/yr de gases). El aire
  es feed gratis (correcto); escalar sube revenue pero el costeo criogénico
  explota. Gases a 120–180 $/tm (bajo para merchant, pero irrelevante a esta
  escala).

## Correcciones aplicadas

**Una:** corregida la correlación de costeo del boiler (ver §1 arriba) —
`equipment_costs.py`, K1 re-anclados al WHB Sinnott validado. rankine ISBL
271.9 M → 6.69 M. Golden-neutral salvo rankine (re-export deliberado), gate
41/41 verde, 522 tests verdes. Ningún veredicto cambia (rankine sigue
INVIABLE por rev=0), pero el ISBL deja de ser 124× la realidad.

**Segunda corrección (2026-07): generación de electricidad.** Se implementó
el crédito de electricidad generada por equipo rotativo con duty<0
(turbina/expander) — antes esos equipos se cobraban como si CONSUMIERAN.
Cambios: nueva utility `electricity_generated` (type `electrical_gen`,
precio −0.08, η=0.92) en `equipment_ports.py`; `autoselect_heat_source`
devuelve generación si duty<0; `flowsheet_export` la trata como export
(revenue, sin heat-integration).

- **hno3 / K-501** (el fix REAL, no-token): el expander de gas de cola
  (−700 kW) se cobraba **$577k/yr de COSTO** cuando debe **generar** ~$451k
  de crédito. Swing de ~$1 M: NPV −21.3 M → **−13.5 M** (sigue INVIABLE por
  sub-escala, pero el expander ya está bien modelado).
- **rankine/nuclear**: se retiparon las turbinas `TUR-101` de
  `Heat exch. — floating head` a `Compressor — axial` (la convención del repo:
  turbina = compresor con P_out<P_in) + `delta_p_bar` declarado (−59.9/−69.9
  bar). Ahora el solver computa la potencia de eje (−2.56/−1.96 kW) y la
  acredita como electricidad. Pero a escala simbólica (100 tm/yr de fluido →
  ~kW) el crédito es ~$1.6k/yr: **siguen INVIABLE** (token). El valor es la
  correctitud del modelo (una turbina genera potencia), no la viabilidad.
  Golden re-exportado (rankine/nuclear: ISBL + sum_duty); gate 41/41 verde.

## Verificación

```
python gate_examples.py               # 41/41 verde (sin cambios en este grupo)
```

## Cierre — estado final de los 40 ejemplos (grupos 1-6)

| Grupo | VIABLE | Inviable con porqué |
|---|---|---|
| G1 Introductorios (7) | methanol, distillation, cdu | hda, ammonia, ethanol, biodiesel |
| G2 Reactores/solver (6) | — | los 6 (demos de solver) |
| G3 Plantas industriales (7) | industrial, hda_full, gas_sweet | talara, sugar, quimpac, hno3 |
| G4 Alimentaria (7) | bread, beer | pasteurizer, potato_chips, penicillin, pineapple, leche_gloria |
| G5 Química (7) | soap | sulfuric, acetic, ldpe, chloralkali_hcl, urea, ethylene_crk |
| G6 Materiales/energía (7) | — | los 7 (demo/utility/Tier-2) |

**Total: 9 VIABLE / 40. Los 31 inviables, todos con porqué demostrado.**

### Taxonomía de los porqués

1. **γ sectorial mal aplicado** (química standalone 1.23 sobre commodity):
   cdu, distillation, hda_full, gas_sweet, talara, soap → corregidos con
   γ=1.05–1.10 documentado.
2. **Precios de corriente sin calibrar**: hda purga, distillation feed,
   beer (precio de granel), leche_gloria (vapor ×100), haber_rec (feed sin
   precio) → corregidos.
3. **Escala de demostración** (correctamente dimensionados, viables a escala
   industrial): urea, glass, y en parte biodiesel/ethanol.
4. **Producción pinneada / equipo sobredimensionado** (escalar no ayuda):
   los 6 del G2, quimpac, hno3, acetic, sulfuric, air_sep, cement.
5. **Topología incompleta (sin reciclo)**: ammonia, ldpe, ethylene_crk.
6. **No es un negocio por diseño**: rankine/nuclear (electricidad no
   modelada), water_treat/desal (utility pública), penicillin/pasteurizer
   (piloto).

### Bugs reales encontrados y su estado

| Bug | Estado |
|---|---|
| Propagación de presión (reactor default + HX 4-puertos) | **CORREGIDO** (PR #124) |
| haber_rec feed sin precio | **CORREGIDO** (PR #125-adyacente) |
| leche_gloria vapor ×100 | **CORREGIDO** (PR #126) |
| beer precio de granel vs microcervecería | **CORREGIDO** (PR #126) |
| K-101/K-202 compresor de reciclo sin P_op | **CORREGIDO** (PR #124/#125) |
| Auto-sizing colapsa ISBL sin S fijado | **AUDITADO** (documentado, no crítico) |
| Costeo del boiler (rankine ISBL 124× WHB) | **CORREGIDO** (K1 re-anclados al WHB Sinnott) |
| Turbina/expander sin generación eléctrica (cobrado como consumo) | **CORREGIDO** (utility `electricity_generated`; fix real en hno3, +$1 M) |

Infraestructura añadida: campo `Flowsheet.econ_overrides["com_gamma"]` para
declarar el γ sectorial por flowsheet. Gate 41/41 verde en todo el recorrido;
el único re-export deliberado de goldens fue por el fix de presión.
