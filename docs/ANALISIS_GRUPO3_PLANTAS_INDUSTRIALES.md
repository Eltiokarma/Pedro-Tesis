# Análisis de convergencia — Grupo 3: Plantas industriales completas

**Fecha:** 2026-07-18
**Alcance:** los 7 ejemplos de *Plantas industriales completas*: `hda_full`,
`gas_sweet`, `sugar`, `industrial`, `quimpac`, `hno3`, `talara`.
**Criterio:** todo tiene que converger, incluso económico; si no, encontrar
el porqué. Misma metodología que los grupos 1-2. **Importante:** este grupo
se analiza DESPUÉS del fix de presión (PR #124), así que gas_sweet y hda_full
parten de un ISBL ya corregido.

## Resultado global

| Ejemplo | Solver | Balances | ISBL | γ | NPV (USD) | IRR | Veredicto |
|---|---|---|---:|---|---:|---|---|
| industrial | ✓ warning¹ | 0/0 (recycle✓) | 27.7 M | 1.23 | +7 783 983 | 13.1% | **VIABLE** |
| hda_full | ✓ ok | 0/0 | 31.2 M | 1.05 | +7 673 000 | 12.7% | **VIABLE** |
| gas_sweet | ✓ ok | 0/0 | 12.8 M | 1.05 | +1 500 000 | 11.3% | **VIABLE** (marginal) |
| talara | ✓ ok | 0/0 | 42.4 M | 1.10 | −14 840 000 | 5.9% | INVIABLE (marginal) |
| sugar | ✓ ok | 0/0 | 56.9 M | 1.10 | −17 620 000 | 6.4% | INVIABLE (capital) |
| hno3 | ✓ ok | 0/0 | 11.0 M | 1.23 | −21 314 399 | — | INVIABLE (demo) |
| quimpac | ✓ ok | 0/0 | 51.3 M | 1.23 | −102 556 370 | — | INVIABLE (demo) |

¹ `industrial` queda en `warning` por un advisory pre-existente (F-301:
T declarada 250 °C vs calc 360.8 — el solver respeta la declaración del
user); no altera la economía. Convergencia numérica: **7/7 verde**.

## Correcciones aplicadas

Todas son **golden-neutral** (γ es solo económico; el fix de presión de
K-202 no cambió ISBL/duty): **gate 41/41 verde**, sin re-export.

### γ sectorial (commodity / refinería / procesamiento)

Igual que la CDU del grupo 1, el γ=1.23 de "química standalone" no aplica a
commodity/petroquímica/refinería: castiga con 23% de overhead comercial las
materias primas gigantes. Se aplicó el γ **documentado en `econ_defaults`**
por sector:

- **hda_full → γ=1.05** ("commodity bulk con offtake"): benceno de un
  complejo aromático Douglas. Margen de materiales 17.9 M; a γ=1.23 el
  overhead (61 M sobre crm 49.8 M) lo hundía. → VIABLE (+7.7 M).
- **gas_sweet → γ=1.05**: endulzamiento de gas. Está modelado como
  compra-gas-ácido / vende-gas-dulce (crm 185 M, rev 202 M, margen 9%), pero
  es en realidad **procesamiento** — el gas ácido no se "compra" a 185 M, es
  gas propio o de un tercero por peaje. Cargar 23% de G&A sobre esos 185 M no
  tiene sentido. γ=1.05 (procesamiento, feed esencialmente interno) → VIABLE
  marginal (+1.5 M). Nota: γ=1.00 (uso interno estricto) daría +41.5 M.
- **talara → γ=1.10** ("refinería integrada (Petroperú)", valor **literal**
  del `econ_defaults`): a diferencia de la CDU genérica (grupo 1, γ=1.05),
  Talara ES Petroperú → el valor documentado es 1.10. Resultado: **marginal
  inviable** (gross +0.54 M, NPV −14.8 M, IRR 5.9% < hurdle 10%). Es un
  hallazgo honesto y fiel a la realidad: la PMRT de Talara es notoriamente
  marginal. La viabilidad es knife-edge en el supuesto de overhead — a
  γ=1.05 daría +50 M; el swing de ~65 M por 5 puntos de γ ES el porqué.

### Fix de presión colateral

- **industrial / K-202** (`P_op_bar = 80.0`): el compresor de reciclo del
  loop de MeOH (80 bar) tenía P_op sin declarar → warning de compresor
  degenerado (mismo patrón que hda_full/K-101 en el PR #124). Declarado a la
  presión del loop; limpia el warning. ISBL sin cambio (su effective_pressure
  ya era 80). `industrial` sigue VIABLE.

## El porqué de los inviables

### talara — refinería marginal (ver γ arriba)

Gross-positivo pero IRR 5.9% < 10%. El cut (utilities) de 66 M/yr es enorme
(reboiler de T-101 a 8.7 MW + varios hornos de fuego): energía-intensiva
como toda refinería. Viable solo si el overhead comercial baja a γ=1.05.

### sugar — capital-intensiva, sin cogeneración

`COM_d = 48.2 M ≈ revenue 47.4 M`: empatados. El problema es el **capital y
el labor**, no el overhead variable — ni γ=1.00 lo salva:

- FCI = 95.5 M → α·FCI = 17.2 M/yr
- COL = 4.45 M → β·COL = 12.15 M/yr (ingenio con mucho personal)

75 377 tm/yr de azúcar a 550 $/tm es un ingenio real de tamaño medio, pero
el modelo **omite la cogeneración de bagazo** (venta de electricidad), que es
el ingreso que vuelve rentables a los ingenios reales. Con γ=1.10 (commodity
alimentario) el gross se vuelve positivo (+1.26 M) pero la NPV sigue negativa
(−17.6 M): es una limitación **estructural del modelo** (falta el balance de
bagazo/cogen), no un precio mal puesto.

### quimpac y hno3 — topología completa a escala de demostración

Igual que el grupo 2: son showcases de una planta industrial **completa**
(cloro-álcali de celda de membrana, 28 bloques; Ostwald dual-presión, 25
bloques) pero con producción **simbólica**:

- **quimpac**: 602 tm/yr de Cl₂ + 2 145 tm/yr de NaOH, con un ISBL de 51 M
  (ratio capital:revenue de **30:1**). El equipo tiene tamaño de planta real;
  los caudales, de laboratorio.
- **hno3**: 5 616 tm/yr de HNO₃ al 60% con 3 compresores grandes (dual-
  presión Ostwald) → ISBL 11 M, revenue 2.5 M.

**Ni escalar los arregla** (verificado por simulación): la producción está
**pinneada** — subir los feeds ×20–100 no aumenta el revenue (hno3 queda
clavado en 2.5 M; quimpac apenas crece y cae en `error`), porque la salida de
producto está capada por spec del reactor/celda. Y escalar feeds+equipo los
empeora (ISBL explota, 13–17 equipos fuera del rango de costeo válido). Su
convergencia relevante es la **numérica** (topología completa que resuelve),
no la económica. Forzar viabilidad exigiría rediseñar el ejemplo, no
corregirlo.

## Aires/steam sin precio — NO son bugs

`hno3` (A3-aire, A12b-bleach-air) y `talara` (C21-steam) tienen feeds a
precio 0. Es **correcto**: el aire atmosférico es gratis y el steam de
proceso es una utility (BFW), no una materia prima comprada. No se tocaron.

## Verificación

```
python gate_examples.py               # 41/41 verde (todo golden-neutral)
python simulate_cli.py data/examples/<k>.json --economics
```

## Estado acumulado (grupos 1-3, 20 ejemplos analizados)

| | VIABLE | Inviable con porqué |
|---|---|---|
| G1 Introductorios (7) | methanol, distillation, cdu | hda, ammonia, ethanol, biodiesel |
| G2 Reactores/solver (6) | — (demos de solver) | los 6 (escala didáctica) |
| G3 Plantas industriales (7) | industrial, hda_full, gas_sweet | talara, sugar, quimpac, hno3 |

Patrón transversal confirmado: el γ sectorial (1.05–1.10) es la corrección
más recurrente y de mayor impacto en flowsheets materials-dominated; el
default 1.23 solo aplica a química standalone.
