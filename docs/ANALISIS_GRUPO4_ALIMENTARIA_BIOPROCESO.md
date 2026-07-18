# Análisis de convergencia — Grupo 4: Alimentaria y bioproceso

**Fecha:** 2026-07-18
**Alcance:** los 7 ejemplos de *Alimentaria y bioproceso*: `pasteurizer`,
`pineapple`, `potato_chips`, `bread`, `beer`, `penicillin`, `leche_gloria`.
**Criterio:** todo tiene que converger, incluso económico; si no, encontrar
el porqué. Misma metodología que los grupos 1-3.

## Resultado global

| Ejemplo | Solver | ISBL | NPV (USD) | IRR | Veredicto |
|---|---|---:|---:|---|---|
| bread | ✓ ok | 1.96 M | +682 403 | 13.9% | **VIABLE** |
| beer | ✓ ok | 1.76 M | +1 530 000 | 19.3% | **VIABLE** (corregido) |
| pasteurizer | ✓ ok | 0.67 M | −3 662 518 | — | INVIABLE (demo) |
| potato_chips | ✓ ok | 1.17 M | −3 486 716 | — | INVIABLE (marginal) |
| penicillin | ✓ ok | 4.53 M | −13 811 624 | — | INVIABLE (demo) |
| pineapple | ✓ ok | 4.35 M | −30 992 999 | — | INVIABLE (sub-escala) |
| leche_gloria | ✓ ok | 12.2 M | −40 030 000 | — | INVIABLE (sub-escala) |

Convergencia numérica **7/7 verde**.

## Diferencia clave con los grupos 1 y 3: γ NO es la palanca

En alimentaria/bioproceso las **materias primas son baratas** (mosto, papa,
medio de cultivo), así que el overhead variable γ·(crm+cut) es chico y bajar
γ casi no mueve la aguja (verificado: beer, potato_chips, pasteurizer no
cambian de veredicto entre γ=1.23 y γ=1.00). El problema es otro: **los
costos FIJOS (labor + capital) dominan sobre una producción de escala
pequeña/piloto**. `bread` es viable justamente porque tiene labor baja
(140 k) y buen revenue (1.83 M).

## Correcciones aplicadas (golden-neutral — gate 41/41 verde)

### beer — precio de granel industrial aplicado a una microcervecería

`S-cerveza` estaba a **1 500 $/tm** = $1.5/L, que es precio de **lager
industrial a granel**. Pero el ejemplo es una microcervecería de 930 tm/yr
(~9 300 hL/yr), escala que vende a precio **premium/craft** ($2.5–6/L).
Corregido a **2 200 $/tm** ($2.2/L, conservador incluso para craft): el
margen de materiales era sano (rev 1.4 M vs crm 90 k), solo faltaba pricear
el producto a su escala. → **VIABLE** (+1.53 M, IRR 19%).

### leche_gloria — bug de magnitud en el vapor (×100)

Un `opex_extra` "Vapor de servicio (calderas)" tenía `flowrate = 1 500 000`
tm/yr × 15 $/tm = **22.5 M/yr** de cut. Eso es **150 tm de vapor por tm de
leche** — físicamente absurdo (los evaporadores reales del flowsheet suman
~390 kW). Claramente le faltan dos ceros: corregido a **15 000 tm/yr**
(cost 225 k, consistente con una planta con evaporación). El cut cae de
22.6 M a 0.35 M y el gross mejora de −33.4 M a −6.05 M.

**Sigue INVIABLE** tras el fix, por causa estructural (ver abajo): el fix es
de **correctitud**, no vuelve viable el ejemplo.

## El porqué de los inviables

Todos comparten el patrón **escala pequeña + costos fijos altos**:

- **pasteurizer** — Pasteurizador HTST de jugo, 6 bloques. Revenue 600 k vs
  labor (col) 300 k + capital: los fijos se comen el margen. Planta de
  demostración.
- **potato_chips** — **Marginal**, break-even sensible al precio. A los
  2 500 $/tm modelados ($2.5/kg, bajo para snack) da gross −0.52 M; a precio
  mayorista honesto (~$3.5/kg) queda en break-even, y a retail (~$4.5/kg)
  sería viable. Combina precio bajo + escala chica (526 tm/yr). Se deja el
  precio original y se documenta la sensibilidad (no se fuerza el veredicto).
- **penicillin** — Fermentación de penicilina, **5 tm/yr** de producto a
  50 000 $/tm. Escala de demostración farmacéutica (una planta real produce
  cientos de tm/yr); labor 300 k vs revenue 250 k.
- **pineapple** — Jugo concentrado, **343 tm/yr** con auto-labor Turton de
  **1.325 M** (≈ 20 operadores para una planta de 8 bloques diminuta). El
  auto-labor asume una planta continua real; a escala de demostración queda
  desproporcionado. Sub-escala.
- **leche_gloria** — Tras el fix del vapor, sigue inviable por **margen
  lácteo delgadísimo + sub-escala**: leche cruda a 600 $/tm vs canasta de
  productos de ~613 $/tm → margen de materiales de solo 130 k. Y es una
  planta integrada de 21 bloques (fluida + evaporada + mantequilla) para solo
  10 000 tm/yr de leche — las plantas reales de Gloria procesan cientos de
  miles. Aun con leche a precio de campo (~400 $/tm) y γ=1.10, la NPV se
  queda en −18 M: capital-intensiva y sub-escala, como `sugar` del grupo 3.

## Verificación

```
python gate_examples.py               # 41/41 verde (precio y opex_extra no entran al golden)
python simulate_cli.py data/examples/beer.json --economics   # VIABLE
```

## Estado acumulado (grupos 1-4, 27 ejemplos)

| Grupo | VIABLE | Inviable con porqué |
|---|---|---|
| G1 Introductorios (7) | methanol, distillation, cdu | hda, ammonia, ethanol, biodiesel |
| G2 Reactores/solver (6) | — (demos de solver) | los 6 |
| G3 Plantas industriales (7) | industrial, hda_full, gas_sweet | talara, sugar, quimpac, hno3 |
| G4 Alimentaria/bioproceso (7) | bread, beer | pasteurizer, potato_chips, penicillin, pineapple, leche_gloria |

Patrón por grupo: G1/G3 se corrigen con **γ sectorial + precios**; G2/G4 son
mayormente **escala de demostración** donde los costos fijos dominan. Bugs de
datos reales encontrados y corregidos al pasar: haber_rec (feed sin precio),
leche_gloria (vapor ×100), beer (precio de granel vs microcervecería).
