# Análisis de convergencia — Grupo 1: Introductorios

**Fecha:** 2026-07-18
**Alcance:** los 7 ejemplos de la categoría *Introductorios* del manifest
(`hda`, `methanol`, `distillation`, `ammonia`, `ethanol`, `biodiesel`, `cdu`).
**Criterio:** todo tiene que converger, *incluso a nivel económico*; si no,
encontrar el porqué.

## Metodología

Cada ejemplo se resolvió headless con el camino real de producción:

```bash
python simulate_cli.py data/examples/<clave>.json --economics
```

Perfil económico activo: `PE_2024` (defaults de `econ_defaults.py`), Turton
Eq. 8.2 (`COM_d = α·FCI + β·COL + γ·(CRM+CUT+CWT)` con α=0.180, β=2.73,
γ=1.23), horizonte 10 años, tasa 10 %, impuesto 30 %, CEPCI 2024→2023
(797.9, nearest-neighbor). Las hipótesis de causa raíz se verificaron
re-simulando con el parámetro sospechoso modificado (sensibilidad puntual),
sin tocar los JSON del repo ni los goldens.

## Resultado global

| Ejemplo | Solver | Balances M/E | Reciclo | Economía | NPV (USD) | IRR | Veredicto |
|---|---|---|---|---|---:|---|---|
| hda | ✓ ok (2 it) | 0 / 0 | ✓ tear S-9-recic, 3 it | ✗ | −4 694 033 | 4.4 % | INVIABLE |
| methanol | ✓ ok (2 it) | 0 / 0 | — | ✓ | +11 855 168 | 31.4 % | **VIABLE** |
| distillation | ✓ ok (2 it) | 0 / 0 | — | ✗ | −19 306 328 | no existe | INVIABLE |
| ammonia | ✓ ok (2 it) | 0 / 0 | — | ✗ | −24 918 281 | no existe | INVIABLE |
| ethanol | ⚠ warning (3 it) | 0 / 0 | — | ✗ | −16 507 914 | no existe | INVIABLE |
| biodiesel | ✓ ok (3 it) | 0 / 0 | — | ✗ | −7 066 328 | no existe | INVIABLE |
| cdu | ✓ ok (2 it) | 0 / 0 | — | ✗ | −48 541 636 | no existe | INVIABLE |

**Conclusión de convergencia numérica: 7/7 verde.** Cero errores de masa y
energía, el único reciclo (HDA) converge en 3 iteraciones, y el único
warning (ethanol, E-101: T calculada 99 °C vs declarada 92 °C, Δ=7 °C,
probable cambio de fase parcial — el solver respeta la declaración) no
afecta balances.

**Conclusión económica: 1/7 viable.** El problema NO está en el motor
económico — la cadena `categorize_opex → compute_fci → COM (Turton 8.2) →
profitability_indicators` es aritméticamente consistente en los 7 casos
(verificado término a término). El problema está en los *datos de entrada*
de cada ejemplo: precios, escala, topología.

## Descomposición del COM_d (dónde muere cada uno)

| Ejemplo | Revenue | γ·materiales (1.23) | β·COL (2.73) | α·FCI (0.18) | COM_d | Gross |
|---|---:|---:|---:|---:|---:|---:|
| hda | 12 285 113 | 8 423 301 | 955 500 | 3 048 213 | 12 427 014 | −141 901 |
| methanol | 8 719 543 | 2 852 737 | 887 250 | 1 695 277 | 5 435 264 | **+3 284 279** |
| distillation | 8 750 000 | 10 494 423 | 887 250 | 453 089 | 11 834 762 | −3 084 762 |
| ammonia | 2 108 543 | 2 578 089 | 887 250 | 2 395 798 | 5 861 137 | −3 752 594 |
| ethanol | 540 781 | 1 242 305 | 887 250 | 974 653 | 3 104 208 | −2 563 427 |
| biodiesel | 1 418 187 | 1 246 038 | 819 000 | 446 712 | 2 511 751 | −1 093 564 |
| cdu | 69 420 000 | 74 170 228 | 955 500 | 1 948 039 | 77 073 767 | −7 653 767 |

## El porqué, ejemplo por ejemplo

### methanol — VIABLE (la referencia de cómo debe cerrar)

Syngas a 150 $/tm → MeOH a 1 100 $/tm. Margen de materiales 6.6 M/yr que
absorbe con holgura el overhead γ, el labor y el 18 % del FCI (9.4 M).
Payback 3.0 años, ROI 28 %. Es la prueba de que el motor económico premia
un flowsheet bien calibrado.

### hda — escala sub-industrial + purga sobrevalorada

- Margen de materiales sano (12.29 M revenue vs 6.62 M crm), pero
  `α·FCI = 3.05 M/yr` se lo come: FCI grass-roots de 16.9 M para producir
  solo 7 503 tm/yr de benceno (~0.94 t/h). El HDA de Douglas es ~20× más
  grande; a esta escala el overhead fijo de Turton no se amortiza. Para
  NPV≥0 el cash anual necesario es ≈3.17 M (anualidad 10 %/10 yr sobre
  FCI+WC = 19.5 M) vs 2.25 M actual → falta ~0.9 M/yr ≈ escalar ×2–3
  (el margen escala lineal, el FCI a la ~0.6).
- **Además, la viabilidad aparente depende de un precio ficticio**: la
  purga `S-purga-H2` (84 % metano) está a 2 000 $/tm — precio de H₂ puro —
  y aporta el 30 % del revenue (3.66 M/yr). Repriceada como fuel gas
  (300 $/tm, el propio default de `UTILITY_PRICES`): gross −3.25 M,
  NPV −22.3 M (verificado por simulación). El ejemplo es mucho menos
  viable de lo que su NPV sugiere.

### distillation — precio de la alimentación estructuralmente imposible

Feed 50/50 benceno/tolueno a **850 $/tm** vs canasta de productos
0.5·1 050 + 0.5·700 = **875 $/tm**: spread de 25 $/tm → 250 k/yr de valor
agregado total. Solo el overhead γ sobre el crudo de alimentación
(0.23·8.5 M = 1.96 M/yr) ya es 8× ese margen; ni con γ=1.0 y opex regalado
cierra. Break-even de gross: feed ≤ **599 $/tm**; para NPV≥0, ≈590 $/tm
(−31 % vs el precio actual). El porqué de fondo: una columna que solo
separa no es un negocio standalone comprando la mezcla casi al precio de
la canasta — o el feed se pricea como corriente interna (γ=1.0 y precio de
transferencia bajo), o el ejemplo es didáctico y su economía no puede
exigirse.

### ammonia — sin reciclo, el 86 % del feed se va por la purga

Conversión single-pass del loop de síntesis: de 10 000 tm/yr de feed solo
1 442 tm salen como NH₃ (14.4 %); 8 558 tm/yr salen por `S-purga` a
120 $/tm. Revenue 2.11 M vs potencial con reciclo total ≈7.5 M (el mismo
feed convertido a NH₃ a 750 $/tm). Haber-Bosch sin reciclo no existe
industrialmente — este es el porqué pedagógico perfecto para contrastar
con `haber_rec` (grupo 2). *Hallazgo colateral:* `haber_rec` hoy tampoco
sirve de contraste porque su feed no tiene precio (crm = 0) y produce solo
950 tm/yr — ver §Colaterales.

### ethanol — doble causa: mosto caro para su azúcar y escala de micro-destilería

- Revenue (541 k) < crm (800 k) *antes* de cualquier overhead: se necesitan
  18.2 tm de mosto por tm de etanol → costo de feed de 1 454 $/tm de EtOH
  vs precio de venta 950 $/tm. Con 12 % de glucosa, el mosto a 80 $/tm es
  inconsistente: el break-even de contenido/precio es ≈52 $/tm.
- Pero incluso con mosto **gratis** el gross sería ≈−1.6 M/yr: 550 tm/yr
  de EtOH (~70 L/h) es una micro-destilería cargando estructura de costos
  de planta industrial (β·COL = 887 k + α·FCI = 975 k).

### biodiesel — escala piloto (125 kg/h) con costos fijos de planta

El spread de materiales es positivo (margen tras γ: ~172 k/yr ≈ 168 $/tm
de biodiesel), pero los términos fijos suman 1.27 M/yr
(β·COL = 819 k + α·FCI = 447 k). Break-even de gross a margen constante:
≈7 500 tm/yr → hace falta ~un orden de magnitud de escala (1 000 → 8 000–
10 000 tm/yr de aceite; con FCI^0.6 el NPV acompaña).

### cdu — γ=1.23 de química standalone aplicado a una refinería

El crack spread del ejemplo es 9.42 M/yr (15.7 % sobre 60 M de crudo) —
razonable para una CDU simple — pero γ=1.23 carga 0.23·60 M = **13.8 M/yr
de overhead comercial sobre el costo del crudo**, más que todo el margen.
El propio `econ_defaults.py` (líneas 212-217) documenta γ=1.10 para
refinería integrada y 1.05 para commodity con offtake. Verificado por
simulación:

| γ | Gross | NPV | Veredicto |
|---|---:|---:|---|
| 1.23 (default) | −7 653 767 | −48 541 636 | INVIABLE |
| 1.10 (refinería integrada) | +185 363 | −1 812 506 | INVIABLE (marginal) |
| 1.05 (offtake) | +3 200 413 | +11 155 817 | **VIABLE** |

El porqué es de *parametrización sectorial*, no de flowsheet. (Nota: que
γ=1.10 quede marginal es incluso fiel a la realidad — una hydroskimming de
2 000 bpd con 32 % de residuo a 350 $/tm no es un gran negocio.)

## Causas raíz transversales

1. **Escala didáctica vs estructura de costos industrial** (hda, ethanol,
   biodiesel): los términos fijos de Turton (α·FCI, β·COL) presuponen
   planta industrial; a escala de banco/piloto siempre ganan.
2. **Precios de corrientes sin calibrar** (distillation feed 850,
   hda purga 2 000, ethanol mosto 80): un solo precio mal puesto invierte
   el veredicto en ambas direcciones.
3. **Topología incompleta** (ammonia): sin reciclo la conversión
   single-pass condena la economía por diseño.
4. **γ sectorial** (cdu): el multiplicador de overhead sobre materiales es
   el parámetro más sensible en flowsheets materials-dominated y el
   default no aplica a refinerías.

## Recomendaciones (decisión pendiente — tocan goldens)

Cualquier cambio en los JSON altera `_golden.json` (gate de regresión):
aplicar solo con re-export deliberado de goldens, no como parche.

| Ejemplo | Acción propuesta | Efecto esperado |
|---|---|---|
| hda | Purga a 300 $/tm (honesto) **+** escalar feed ×2–3, o documentar como "marginal por diseño (Douglas)" | Economía honesta; viable solo con escala |
| distillation | Feed a ≤590 $/tm o declararlo unidad interna (γ=1.0 + precio de transferencia) | NPV ≥ 0 alcanzable |
| ammonia | Dejarlo INVIABLE **documentado** como contraste pedagógico con `haber_rec` (y arreglar el pricing de `haber_rec`) | Narrativa reciclo=viabilidad |
| ethanol | Mosto ≈40–50 $/tm **+** escalar ×10 (o convertirlo en destilería 5 000 tm/yr EtOH) | Cierra solo con ambas |
| biodiesel | Escalar ×8–10 (aceite 8 000–10 000 tm/yr) | Gross > 0 y NPV acompaña |
| cdu | Perfil económico con γ=1.05–1.10 para el ejemplo (soporte de γ por flowsheet/perfil) | VIABLE con 1.05; marginal-realista con 1.10 |
| methanol | Nada — es la referencia | — |

## Hallazgos colaterales (fuera del grupo 1, anotados al pasar)

- `haber_rec` (grupo 2): feed **sin precio** → crm = 0 y revenue 712 k con
  gross −4.5 M; su economía es hoy incomparable con `ammonia`.
- CDU: dos WHB packaged costean fuera del rango válido de Sinnott
  (S = 200–220 kg/h vs rango [5 000, 200 000]) → "costo extrapolado, NO
  confiable" (warning del propio `equipment_costs.py`).
- CEPCI 2024 sin valor oficial → todos los costeos usan 2023 (797.9) con
  warning. Cosmético pero aparece en cada corrida.

---

# Correcciones aplicadas (2026-07-18)

Se aplicaron las correcciones **físicamente honestas** — las que no dependen
de precios ficticios ni de costeos fuera del rango validado de las
correlaciones. Resultado: **3 ejemplos corregidos a VIABLE** y **4 dejados
INVIABLE con su porqué documentado y demostrado** (no se fuerzan a viables
apilando supuestos injustificables).

## Cambio de infraestructura: γ de manufactura por flowsheet

Turton 8.2 usa γ (overhead comercial sobre costos variables) = 1.23 para
química standalone. El propio `econ_defaults.py` documenta γ=1.05–1.10 para
refinería integrada / commodity con offtake, pero antes ese valor era un
**global** de módulo: no había forma de que un ejemplo declarara su γ
sectorial. Se añadió el campo `Flowsheet.econ_overrides["com_gamma"]`:

- `flowsheet_model.py`: nuevo campo `econ_overrides` (serializado en
  `to_dict`/`from_dict`).
- `simulate_engine._economics`: lee `fs.econ_overrides["com_gamma"]` (o el
  override del CLI, que tiene precedencia) y lo pasa a
  `cost_of_manufacture_components(gamma=…)` y al split variable del ramp-up.
  Se reporta en `economics.inputs.com_gamma`. Si no se declara, `None` →
  el default 1.23 se resuelve como antes (el caso química-standalone **no
  cambia en nada**; 40/41 goldens intactos).

Ningún cambio afecta `_golden.json` (precios y γ no entran en el golden:
status, bloques, corrientes, errores M/E, sum_duty, ISBL). **Gate 41/41
verde** por ambos caminos (directo y vía registry); **522 tests no-GUI
verdes**.

## Estado final del grupo 1

| Ejemplo | Cambio aplicado | NPV | Veredicto |
|---|---|---:|---|
| methanol | ninguno (referencia) | +11.86 M | **VIABLE** |
| distillation | feed 850→600 $/tm (aromáticos mezclados con descuento realista) + `com_gamma`=1.10 | +2.72 M | **VIABLE** |
| cdu | `com_gamma`=1.05 (refinería con offtake) | +11.16 M | **VIABLE** |
| hda | purga 2 000→350 $/tm (correctitud: gas 84 % metano ≠ H₂ puro) | −21.78 M | INVIABLE (documentado) |
| ammonia | ninguno | −24.92 M | INVIABLE (documentado) |
| ethanol | ninguno | −16.51 M | INVIABLE (documentado) |
| biodiesel | ninguno (revertido) | −7.07 M | INVIABLE (documentado) |

### Por qué NO se forzaron los 4 restantes

- **hda** — Con la purga a precio honesto (gas de purga 84 % metano vale
  ~fuel gas, no 2 000 $/tm de H₂ puro), la viabilidad aparente
  (NPV −4.7 M) se desploma a −21.8 M: **descansaba en un precio ficticio**.
  Converge solo apilando 3 supuestos simultáneos (escala ×5 con equipo
  re-dimensionado + γ=1.10 + tolueno más barato), y γ=1.0 no es defendible
  para una planta que vende benceno al mercado. La versión industrial
  Douglas ya existe como ejemplo aparte (`hda_full`); el HDA introductorio
  queda como el caso pedagógico de "la ruta tolueno→benceno no paga a
  escala de aula". Solo se aplicó el **fix de correctitud** (purga a 350).
- **ammonia** — Sin reciclo, el 86 % del feed sale por la purga; γ no puede
  arreglar una topología que tira la mayor parte de la materia prima
  (inviable incluso a γ=1.0). Es el contraste pedagógico con `haber_rec`.
- **ethanol** — Cerveza diluida: el reboiler (1 581 kW para 550 t/yr de
  EtOH) da una energía específica enorme; el reactor convierte glucosa por
  estequiometría fija, así que enriquecer el mosto no sube el rendimiento
  por tonelada. Inviable a toda escala y γ.
- **biodiesel** — **Falso positivo destapado:** escalar ×10 daba NPV +1.4 M,
  pero con un **único reactor de 300 m³ costeado por extrapolación fuera
  del rango Turton [0.1, 35] m³** (warning "costo NO confiable"). Costeado
  honestamente con 10 reactores en paralelo dentro de rango, el ISBL sube
  de 4.8 M a 9.0 M y vuelve a INVIABLE (−6.4 M). Su reactor ya está en el
  techo del rango a escala piloto: no hay escala que sea a la vez viable y
  dentro de la envolvente validada. Se **revirtió** el escalado.

## Verificación

```
python gate_examples.py               # 41/41 verde
python gate_examples.py --registry    # 41/41 verde (camino UI)
python -m pytest tests/ (no-GUI)      # 522 passed, 1 skipped
for k in distillation cdu; do python simulate_cli.py data/examples/$k.json --economics; done  # VIABLE
```

Warnings pre-existentes sin relación con estos cambios (ya anotados en
§Colaterales): WHB de cdu/methanol fuera de rango Sinnott, CEPCI 2024→2023.
No afectan las conclusiones (NPV de millones vs equipos marginales).
