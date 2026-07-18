# Análisis de convergencia — Grupo 5: Química

**Fecha:** 2026-07-18
**Alcance:** los 7 ejemplos de *Química*: `sulfuric`, `acetic`, `ldpe`,
`chloralkali_hcl`, `urea`, `soap`, `ethylene_crk`.
**Criterio:** todo tiene que converger, incluso económico; si no, encontrar
el porqué. Misma metodología que los grupos 1-4.

## Resultado global

| Ejemplo | Solver | ISBL | NPV (USD) | Veredicto |
|---|---|---:|---:|---|
| soap | ✓ ok | 1.39 M | +50 000 | **VIABLE** (marginal, corregido) |
| sulfuric | ✓ ok | 1.18 M | −8 054 462 | INVIABLE (sub-escala + feedstock) |
| ldpe | ✓ ok | 2.45 M | −9 993 565 | INVIABLE (sin reciclo) |
| acetic | ✓ ok | 3.52 M | −10 774 517 | INVIABLE (demo, prod. pinneada) |
| urea | ✓ ok | 5.13 M | −12 221 098 | INVIABLE (demo, escalable) |
| chloralkali_hcl | ✓ ok | 7.07 M | −16 339 180 | INVIABLE (sub-escala) |
| ethylene_crk | ✓ ok | 6.76 M | −18 115 100 | INVIABLE (sin reciclo) |

Convergencia numérica **7/7 verde**. Los precios de producto están todos en
rango de mercado (H₂SO₄ 140, AcOH 600, urea 550, LDPE 1400, NaOH 400, soap
1800, etileno 950): **no hay bug de datos** como el vapor de leche_gloria.
Aire sin precio en `sulfuric` es correcto (gratis).

## El grupo es química commodity a escala de demostración

Todos parten de 1 000 tm/yr de feed y producen cantidades simbólicas de
químicos commodity, que solo pagan a escala mundial (100 000+ tm/yr). Como en
el grupo 2, γ apenas mueve la aguja (materiales dominan y el margen es
estructural), salvo en el caso marginal:

## Corrección aplicada (golden-neutral — gate 41/41 verde)

- **soap → γ=1.10** (commodity oleoquímico bulk): saponificación de aceite
  vegetal. Margen sano (rev 1.94 M, crm 0.95 M, labor baja 120 k). A γ=1.23
  quedaba en −0.48 M (marginal inviable); a γ=1.10 → **VIABLE marginal**
  (+0.05 M, IRR 10.4%). Es break-even: soap es un commodity de margen
  delgadísimo. Único del grupo que γ vuelve viable.

## El porqué de los inviables (verificado por simulación)

Tres sub-causas, todas confirmadas escalando/repriceando:

### Escalables — demo-scale de un commodity que sí paga a escala

- **urea** — Producción **responde al feed**: a ×100 (167 500 tm/yr, planta
  real) da NPV +13.8 M. El ejemplo shippeado está a escala de demostración
  (1 675 tm/yr); es viable en principio a escala industrial, pero escalarlo
  limpio exige rediseñar equipos (a ×100 caen 6 fuera del rango de costeo →
  trenes en paralelo). Se documenta, no se fuerza (lección de biodiesel G1).

### Producción pinneada — escalar NO ayuda (como grupo 2)

- **acetic** (Cativa) y **sulfuric** (contacto): el revenue **no crece** al
  escalar el feed (queda clavado en 1.1 M y 0.2 M) — la salida de producto
  está capada por spec del reactor. Inviables por diseño de demostración.
  `sulfuric` además parte de SO₂ comprado a 180 $/tm (feedstock caro; las
  plantas reales parten de azufre barato o SO₂ de fundición con crédito).
- **chloralkali_hcl** — Sub-escala (684 tm/yr NaOH vs ISBL 7 M), igual que
  `quimpac` del grupo 3: topología completa de celda + HCl a escala simbólica.

### Sin reciclo — venden el feed sin convertir con pérdida

- **ldpe** — Autoclave de alta presión con **30% de conversión** y **sin
  reciclo**: de 1 000 tm/yr de etileno, 700 salen como purga vendida a
  600 $/tm... comprada a 900. Se vende el 70% del feed **a pérdida**. El LDPE
  real recircula el etileno no reaccionado; sin eso, es negativo por diseño.
- **ethylene_crk** — Cracking de etano de un solo paso: 428 tm/yr de offgas
  (97% etano sin reaccionar). Mismo caso que `ethane_pfr` del grupo 2 — demo
  de cinética sin separación/reciclo downstream.

## Verificación

```
python gate_examples.py               # 41/41 verde (γ no entra al golden)
python simulate_cli.py data/examples/soap.json --economics   # VIABLE
```

## Estado acumulado (grupos 1-5, 34 ejemplos)

| Grupo | VIABLE | Inviable con porqué |
|---|---|---|
| G1 Introductorios (7) | methanol, distillation, cdu | hda, ammonia, ethanol, biodiesel |
| G2 Reactores/solver (6) | — (demos de solver) | los 6 |
| G3 Plantas industriales (7) | industrial, hda_full, gas_sweet | talara, sugar, quimpac, hno3 |
| G4 Alimentaria (7) | bread, beer | pasteurizer, potato_chips, penicillin, pineapple, leche_gloria |
| G5 Química (7) | soap | sulfuric, acetic, ldpe, chloralkali_hcl, urea, ethylene_crk |

Patrón consolidado: la química commodity a escala de demostración es
mayoritariamente inviable por escala (o por no-reciclo). γ solo salva los que
ya están al borde del break-even (soap). No hay bugs de precio en este grupo.
