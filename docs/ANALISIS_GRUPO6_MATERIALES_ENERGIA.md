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

> **Bug de costeo flageado (rankine):** su ISBL de 271.9 M está dominado en
> un **99.6%** por un solo equipo — `B-101 (Boiler — water tube, S=10)` da
> CBM = **270.9 M**. La correlación Turton del boiler es sistemáticamente
> alta (incluso a S=2, el mínimo, da Cp=15.2 M para una caldera de ~7 t/h que
> en realidad cuesta ~$0.5 M), y además el S=10 del demo no matchea su flujo
> simbólico. `nuclear` NO tiene este blowup (su ISBL 1.69 M es razonable).
> **Recomendación:** revisar las constantes K1 de `Boiler — fire tube` /
> `Boiler — water tube` en `equipment_costs.py:386-393` contra Turton
> Apéndice A, y/o el S del boiler de rankine. No se corrigió acá (requiere la
> referencia Turton y toca golden; rankine es inviable igual). Se documenta
> como hallazgo accionable, igual que se hizo con el bug de presión.

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

**Ninguna.** No hay un fix de dato defendible: los ciclos de energía necesitan
modelar la generación eléctrica (estructural), las utilities de agua no son
negocios, y los materiales son demo-scale (glass escalaría). Se flaguean dos
hallazgos de ingeniería para trabajo futuro: (a) turbina-como-HX sin potencia
de eje → sin ingreso eléctrico; (b) correlación de costeo del boiler
(rankine ISBL 99.6% un boiler mal costeado).

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
| Costeo del boiler (rankine ISBL 99.6%) | **FLAGEADO** (requiere ref. Turton) |
| Turbina-como-HX sin potencia de eje (rankine/nuclear) | **FLAGEADO** (ampliación estructural) |

Infraestructura añadida: campo `Flowsheet.econ_overrides["com_gamma"]` para
declarar el γ sectorial por flowsheet. Gate 41/41 verde en todo el recorrido;
el único re-export deliberado de goldens fue por el fix de presión.
