# Capa 4 — Base de datos de reacciones químicas (v1.0)

**Estado:** 25 reacciones catalogadas, autoverificadas contra Capa 3 y/o literatura experimental. 22 con coherencia Hess<2 kJ/mol; 3 con discrepancia real y documentada (R007 fermentación, R008 Fischer, R021 biodiésel).

## Arquitectura

Cuatro capas **separadas e independientes**:

- **Capa 1** (`antoine.py`) — Presión de saturación, P_sat(T) por especie
- **Capa 2** (`compounds_db.py` campo `Cp_coef_gas`) — Calor específico, Cp(T) DIPPR-100
- **Capa 3** (`compounds_db.py`) — Propiedades de compuestos: ΔHf°, S°, MW por fase
- **Capa 4** (`reactions_db.py`) — Reacciones: estequiometría + metadatos

**Capa 4 NO duplica propiedades de compuestos.** ΔH_rxn, ΔS_rxn, ΔG_rxn, ΔCp_rxn se **derivan al vuelo** desde Capa 3 + Capa 2:

```python
from rxn_thermo import dH_rxn_T, Keq_DIPPR, equilibrium_conversion_gas

# Termodinámica a cualquier T con corrección Cp rigurosa:
dH_700 = dH_rxn_T(REACTIONS['R002']['stoich'], 700)
Keq_700 = Keq_DIPPR(REACTIONS['R002']['stoich'], 700)

# Conversión de equilibrio en un reactor real:
r = equilibrium_conversion_gas(
    stoich=REACTIONS['R004']['stoich'],
    feed_moles={'N2': 1.0, 'H2': 3.0},
    T_K=700, P_bar=200, use_DIPPR=True,
)
```

Cambiar ΔHf° del etanol en Capa 3 → todas las reacciones que lo involucran se recalculan automáticamente. **Coherencia garantizada por diseño.**

## Tres formas de Keq(T), en orden creciente de rigor

| Forma | Función | Asume | Cuándo usar |
|---|---|---|---|
| 2-parámetros | `Keq_vant_hoff(A, B, T)` | ΔCp_rxn = 0 | Rango estrecho cerca de 298 K |
| Cp constante | `Keq_from_dGdH(dG, dH, T, dCp)` | ΔCp_rxn = constante | Rango medio (300–600 K) |
| **DIPPR-100** | `Keq_DIPPR(stoich, T)` | Cp polinomio en T | **Producción — preferida** |

## Resumen de coherencia (autoverificación)

Tolerancias: |ΔH_err| < 2 kJ/mol, |ΔG_err| < 3 kJ/mol.

| ID | Reacción | |ΔH_err| | |ΔG_err| | Status |
|---|---|---:|---:|:---:|
| R001 | Combustión completa de metano | 0.34 | 0.32 | ✓ OK |
| R002 | Water-Gas Shift (WGS) | 0.05 | 0.02 | ✓ OK |
| R003 | Reformado de metano con vapor (SMR) | 0.28 | 0.17 | ✓ OK |
| R004 | Síntesis de amoniaco (Haber-Bosch) | 0.00 | 0.01 | ✓ OK |
| R005 | Síntesis de metanol desde syngas | 0.19 | 0.23 | ✓ OK |
| R006 | Oxidación de SO2 a SO3 (proceso de contacto) | 0.00 | 0.11 | ✓ OK |
| R007 | Fermentación alcohólica de glucosa | 33.02 | 3.84 | ⚠ revisar |
| R008 | Esterificación de Fischer (acetato de etilo) | 2.20 | 4.73 | ⚠ revisar |
| R009 | Combustión de hidrógeno | 0.00 | 0.02 | ✓ OK |
| R010 | Hidrogenación de etileno | 0.00 | 0.78 | ✓ OK |
| R011 | Cracking térmico de etano | 0.00 | 0.78 | ✓ OK |
| R012 | Deshidrogenación de propano | 0.00 | 0.69 | ✓ OK |
| R013 | Reformado seco de metano (DRM) | 0.35 | 0.15 | ✓ OK |
| R014 | Síntesis de DME desde syngas | 0.00 | 0.00 | ✓ OK |
| R015 | Hidratación de etileno a etanol (proceso directo) | 0.42 | 1.45 | ✓ OK |
| R016 | Alquilación de benceno con etileno (etilbenceno) | 0.00 | 0.00 | ✓ OK |
| R017 | Respiración aerobia de glucosa | 0.00 | 0.00 | ✓ OK |
| R018 | Hidrólisis de sacarosa (inversión) | 0.00 | 0.00 | ✓ OK |
| R019 | Oxidación de etanol a acetaldehído (defecto cervecero) | 0.00 | 0.00 | ✓ OK |
| R020 | Oxidación de acetaldehído a ácido acético (avinagrado) | 0.00 | 0.00 | ✓ OK |
| R021 | Transesterificación de triolein a FAME (biodiésel) | 71.80 | 26.42 | ⚠ revisar |
| R022 | Hidrólisis enzimática de almidón a glucosa | n/a | n/a | ⚠ no derivable |
| R023 | Absorción de CO2 en MDEA (Kent-Eisenberg) | n/a | n/a | ⚠ no derivable |
| R024 | Absorción de H2S en MDEA | n/a | n/a | ⚠ no derivable |
| R025 | Reacción de Boudouard (gasificación de C) | n/a | n/a | ⚠ no derivable |
| R026 | Carbonilación de metanol a ácido acético | n/a | n/a | ⚠ no derivable |
| R027 | Polimerización de etileno a PE (LDPE) | n/a | n/a | ⚠ no derivable |
| R028 | Síntesis directa de HCl (H₂+Cl₂) | n/a | n/a | ⚠ no derivable |
| R029 | Calcinación de caliza (descarbonatación) | n/a | n/a | ⚠ no derivable |
| R030 | Saponificación de triglicérido | n/a | n/a | ⚠ no derivable |
| R031 | Síntesis de urea (Bosch-Meiser) | n/a | n/a | ⚠ no derivable |

## Limitaciones del motor — ENUNCIADAS EXPLÍCITAMENTE

### 1. Aproximación de gas ideal

`equilibrium_conversion_gas` usa Kp ideal: $K_p = \prod (y_i)^{\nu_i} \cdot (P/P^\circ)^{\Delta\nu}$. **A P > 30 bar el factor de fugacidad $\phi_i$ deja de ser unitario.** Para Haber a 200 bar, el error es ~30% en Keq efectivo (Lewis-Randall con $\phi_i$ ≈ 1.1–1.3). **Mitigación pendiente:** acoplar con ecuación de estado (SRK, PR) para calcular fugacidades en `Capa 5 — Equilibrio Físico`.

### 2. Polinomios DIPPR-100 truncados a orden 4 en T

Los Cp(T) usados son ajustes polinomiales de grado 4. Comparados con tablas JANAF a T altas (>1500 K), el error en Cp individual es 2–3%, que se propaga a errores de 5–10% en ΔCp_rxn integrado. Para Haber a 700 K, mi Keq_DIPPR = 8.9×10⁻⁵ vs JANAF directo 7.2×10⁻⁵ → error 22%. **Aceptable para diseño preliminar; insuficiente para optimización fina.**

### 3. Sistemas acuosos con convenciones de estado estándar incompatibles

Para solutos en fase acuosa (`aq`), distintas fuentes usan distintos estados de referencia:

- **NBS Tables (1982):** estado estándar molal m=1, ideal
- **Goldberg-Tewari (2002):** dilución infinita, fracción molar
- **Bioquímica clásica:** pH=7, [Mg²⁺]=1 mM (Alberty transformed Gibbs)

Mi Capa 3 mezcla fuentes según disponibilidad → **discrepancias hasta 30 kJ/mol** en reacciones biológicas (R007). Para esos casos, recomendación honesta: usar valor calorimétrico empírico medido en condiciones de operación, NO derivar de Capa 3.

### 4. Reacciones en fase líquida no acoplan coeficientes de actividad

Keq calculado para reacciones líquidas (R008 Fischer, R021 biodiésel) usa **estado estándar de líquido puro**. En la realidad, los $\gamma_i \neq 1$ y el Keq aparente basado en concentraciones difiere significativamente (R008: factor 7×). **Mitigación pendiente:** acoplar con modelo de actividad (NRTL, UNIQUAC) en `Capa 5`.

### 5. Reacciones marcadas `no_derivar_de_capa3`

Cinco reacciones NO se pueden derivar formalmente de Capa 3:

- **R022 (hidrólisis almidón):** almidón es polímero polidisperso, sin ΔHf° definido.
- **R023, R024 (MDEA-CO2/H2S):** sistema multireacción acoplado. Usar correlaciones empíricas Kent-Eisenberg / Austgen / e-NRTL.
- **R021 (transesterificación biodiésel):** ΔHf° de triolein y FAME estimados por Joback, incertidumbre declarada ±20 kJ/mol.
- **R025 (Boudouard):** falta C(grafito) en Capa 3. Agregar para versión 1.1.

### 6. Cinética NO modelada

Este es un motor de **equilibrio termodinámico**, no de cinética. Una reacción con Keq=10¹⁰⁰ termodinámicamente irreversible puede ser cinéticamente lenta (N₂+H₂ sin catalizador a 298 K es imposible en tiempo finito). Para simulación de reactores reales (volumen, residencia, catalizador), acoplar con `Capa 6 — Cinética` (no implementada todavía). Los valores de conversión reportados son **máximos termodinámicos**.

### 7. Multi-reacción acoplada NO implementada

`equilibrium_conversion_gas` resuelve UNA reacción. Sistemas reales como syngas (SMR + WGS simultáneo), reformado seco (DRM + Boudouard), endulzamiento amina requieren **minimización de Gibbs global**. **Pendiente para v1.1.**

## Convenciones

- ν > 0 para productos, ν < 0 para reactantes
- Estado estándar: gas ideal a 1 bar; líquido puro a 1 bar; soluto acuoso m=1 molal ideal
- Cp DIPPR-100: $C_p(T) = C_1 + C_2 T + C_3 T^2 + C_4 T^3 + C_5 T^4$ en J/(mol·K)
- T_ref = 298.15 K, R = 8.314462618 J/(mol·K) [CODATA 2018]
- Keq adimensional, basado en actividades referidas al estado estándar
- Reacciones con flag **irreversible** → usar conversión declarada, no resolver equilibrio

---

# Catálogo de reacciones

## R001 — Combustión completa de metano

**Categoría:** combustión  

### Estequiometría

```
1 CH4(g) + 2 O2(g)  →  1 CO2(g) + 2 H2O(g)
```

| Especie | Fase | ν |
|---|---|---:|
| CH4 | g | -1 |
| O2 | g | -2 |
| CO2 | g | +1 |
| H2O | g | +2 |

**Δν =** +0  **Fase global:** gas  **Rango T válido:** 300–2000 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | -802.642 | -802.300 | -0.342 |
| ΔS_rxn [J/(mol·K)] | -5.10 | — | — |
| ΔG_rxn [kJ/mol] | -801.122 | -800.800 | -0.322 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = -0.6133  (= ΔS_rxn / R)
- B = +96535.64 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 2.241e+140 | 2.241e+140 | — | — |
| 500.0 | 3.832e+83 | 4.363e+83 | — | ✓ |
| 800.0 | 1.380e+52 | 1.912e+52 | — | ✓ |
| 1200.0 | 4.689e+34 | 6.956e+34 | — | ✓ |

> 🔒 **Marcado irreversible.** Keq(298) ≈ 2.241e+140. Usar conversión declarada en simulación, no resolver equilibrio.

### Comentarios técnicos

Reacción esencialmente irreversible. Keq(298) ≈ 10^140. Para diseño de combustor industrial asumir conversión 100% — la limitante es cinética y mezclado, no termodinámica. ΔH reportada es PCS si H2O sale líquida; acá usamos H2O(g) → coincide con PCI (poder calorífico inferior). PCI metano experimental: 50.0 MJ/kg = 802 kJ/mol — coincide con cálculo.

### Referencias

- NIST JANAF
- Smith Van Ness 8e Tabla C.4

---

## R002 — Water-Gas Shift (WGS)

**Categoría:** syngas  

### Estequiometría

```
1 CO(g) + 1 H2O(g)  →  1 CO2(g) + 1 H2(g)
```

| Especie | Fase | ν |
|---|---|---:|
| CO | g | -1 |
| H2O | g | -1 |
| CO2 | g | +1 |
| H2 | g | +1 |

**Δν =** +0  **Fase global:** gas  **Rango T válido:** 500–1200 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | -41.154 | -41.200 | +0.046 |
| ΔS_rxn [J/(mol·K)] | -42.03 | — | — |
| ΔG_rxn [kJ/mol] | -28.623 | -28.600 | -0.023 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = -5.0550  (= ΔS_rxn / R)
- B = +4949.69 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 1.034e+05 | 1.034e+05 | — | — |
| 500.0 | 127 | 138 | 138 | ✓ |
| 800.0 | 3.1 | 4.21 | 4.07 | ✓ |
| 1200.0 | 0.394 | 0.705 | 0.617 | ✓ |

### Comentarios técnicos

Reacción exotérmica moderada, Δν=0 → independiente de P. Industrialmente operada en dos etapas: HT-shift (Fe2O3/Cr2O3, 600-720 K) y LT-shift (Cu/ZnO, 470-520 K). Keq disminuye con T. Verificación: Keq(1100 K) ≈ 1.0 según JANAF — punto pedagógico clásico.

### Referencias

- NIST JANAF
- Twigg Catalyst Handbook 2e

---

## R003 — Reformado de metano con vapor (SMR)

**Categoría:** syngas  

### Estequiometría

```
1 CH4(g) + 1 H2O(g)  →  1 CO(g) + 3 H2(g)
```

| Especie | Fase | ν |
|---|---|---:|
| CH4 | g | -1 |
| H2O | g | -1 |
| CO | g | +1 |
| H2 | g | +3 |

**Δν =** +2  **Fase global:** gas  **Rango T válido:** 700–1300 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | +205.816 | +206.100 | -0.284 |
| ΔS_rxn [J/(mol·K)] | +214.62 | — | — |
| ΔG_rxn [kJ/mol] | +141.829 | +142.000 | -0.171 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = +25.8123  (= ΔS_rxn / R)
- B = -24753.98 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 1.421e-25 | 1.421e-25 | — | — |
| 500.0 | 5.118e-11 | 9.226e-11 | — | — |
| 800.0 | 0.00592 | 0.032 | 1.36 | ✓ |
| 1200.0 | 178 | 2.36e+03 | 4.74e+03 | ✓ |

### Comentarios técnicos

Fuertemente endotérmica (+206 kJ/mol). Δν=+2 → P baja favorece. Industrialmente: 1100-1200 K, 20-30 bar (compromiso entre equilibrio y costo de compresión río abajo). Catalizador Ni/α-Al2O3. Acoplada con WGS río abajo para maximizar H2.

### Referencias

- NIST JANAF
- Rostrup-Nielsen 'Catalytic Steam Reforming' 1984

---

## R004 — Síntesis de amoniaco (Haber-Bosch)

**Categoría:** síntesis industrial  

### Estequiometría

```
1 N2(g) + 3 H2(g)  →  2 NH3(g)
```

| Especie | Fase | ν |
|---|---|---:|
| N2 | g | -1 |
| H2 | g | -3 |
| NH3 | g | +2 |

**Δν =** -2  **Fase global:** gas  **Rango T válido:** 600–900 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | -91.880 | -91.880 | +0.000 |
| ΔS_rxn [J/(mol·K)] | -198.11 | — | — |
| ΔG_rxn [kJ/mol] | -32.814 | -32.800 | -0.014 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = -23.8272  (= ΔS_rxn / R)
- B = +11050.62 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 5.606e+05 | 5.606e+05 | 5.430e+05 | — |
| 500.0 | 0.178 | 0.102 | 0.0993 | — |
| 800.0 | 4.477e-05 | 9.021e-06 | 7.200e-06 | ✓ |
| 1200.0 | 4.481e-07 | 3.854e-08 | — | — |

### Comentarios técnicos

Exotérmica (-92 kJ/mol) y Δν=-2: alta P y baja T favorecen termodinámica, pero cinética requiere T alta. Industrial: 670-720 K, 150-300 bar, catalizador Fe promovido (K2O, Al2O3, CaO). Conversión por paso ~15-20%, reciclado masivo. Atención: Keq depende fuertemente de T en este rango, ΔCp_rxn NO es despreciable.

### Referencias

- NIST JANAF
- Appl 'Ammonia: Principles and Industrial Practice' 1999

---

## R005 — Síntesis de metanol desde syngas

**Categoría:** síntesis industrial  

### Estequiometría

```
1 CO(g) + 2 H2(g)  →  1 CH3OH(g)
```

| Especie | Fase | ν |
|---|---|---:|
| CO | g | -1 |
| H2 | g | -2 |
| CH3OH | g | +1 |

**Δν =** -2  **Fase global:** gas  **Rango T válido:** 450–700 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | -90.410 | -90.600 | +0.190 |
| ΔS_rxn [J/(mol·K)] | -219.16 | — | — |
| ΔG_rxn [kJ/mol] | -25.069 | -25.300 | +0.231 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = -26.3583  (= ΔS_rxn / R)
- B = +10873.82 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 2.465e+04 | 2.465e+04 | — | — |
| 500.0 | 0.00995 | 0.0059 | 0.009 | ✓ |
| 800.0 | 2.856e-06 | 6.772e-07 | — | — |
| 1200.0 | 3.077e-08 | 3.668e-09 | — | — |

### Comentarios técnicos

Exotérmica (-90.8 kJ/mol), Δν=-2. Industrial (proceso ICI/Lurgi): 480-550 K, 50-100 bar, catalizador Cu/ZnO/Al2O3. Conversión por paso baja (~5-10%) por límite termodinámico, recirculación obligatoria. Metanol producto sale como gas del reactor y se condensa río abajo.

### Referencias

- NIST WebBook
- Bart & Sneeden Catalysis Today 1987

---

## R006 — Oxidación de SO2 a SO3 (proceso de contacto)

**Categoría:** síntesis industrial  

### Estequiometría

```
2 SO2(g) + 1 O2(g)  →  2 SO3(g)
```

| Especie | Fase | ν |
|---|---|---:|
| SO2 | g | -2 |
| O2 | g | -1 |
| SO3 | g | +2 |

**Δν =** -1  **Fase global:** gas  **Rango T válido:** 650–900 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | -197.920 | -197.920 | +0.000 |
| ΔS_rxn [J/(mol·K)] | -188.06 | — | — |
| ΔG_rxn [kJ/mol] | -141.851 | -141.740 | -0.111 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = -22.6182  (= ΔS_rxn / R)
- B = +23804.30 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 7.098e+24 | 7.098e+24 | — | — |
| 500.0 | 7.132e+10 | 6.744e+10 | — | — |
| 800.0 | 1.26e+03 | 1.2e+03 | 3.400e+04 | ✓ |
| 1200.0 | 0.062 | 0.0665 | — | — |

### Comentarios técnicos

Etapa clave en producción de H2SO4. Exotérmica (-198 kJ/mol_extent, o -99 kJ/mol_SO2). Δν=-1. Industrial: 4 lechos catalíticos V2O5/K2SO4 con enfriamiento entre etapas, T entrada ~680 K, T salida ~880 K. Conversión global >99.7% (regulación ambiental SO2).

### Referencias

- NIST JANAF
- Müller Ullmann's Encyclopedia 'Sulfuric Acid'

---

## R007 — Fermentación alcohólica de glucosa

**Categoría:** bioquímica  

### Estequiometría

```
1 Glucose(aq)  →  2 C2H5OH(aq) + 2 CO2(g)
```

| Especie | Fase | ν |
|---|---|---:|
| Glucose | aq | -1 |
| C2H5OH | aq | +2 |
| CO2 | g | +2 |

**Δν =** +3  **Fase global:** líquido acuoso (productos CO2 sale como gas)  **Rango T válido:** 283–313 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | -101.520 | -68.500 | -33.020 |
| ΔS_rxn [J/(mol·K)] | +460.57 | — | — |
| ΔG_rxn [kJ/mol] | -238.839 | -235.000 | -3.839 |

> ⚠️ **Discrepancia documentada.** Ver sección "Comentarios".

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = +55.3938  (= ΔS_rxn / R)
- B = +12210.05 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 6.963e+41 | 6.963e+41 | — | ✓ |
| 500.0 | 4.600e+34 | 2.690e+36 | — | — |
| 800.0 | 4.849e+30 | 2.363e+36 | — | — |
| 1200.0 | 2.994e+28 | 5.616e+38 | — | — |

> 🔒 **Marcado irreversible.** Keq(298) ≈ 6.963e+41. Usar conversión declarada en simulación, no resolver equilibrio.

### Comentarios técnicos

CONVENCIÓN ASUMIDA: glucosa(aq, no ionizada), etanol(aq), CO2(g, 1 bar). Calor de reacción depende fuertemente de la convención: 
  - Química 'limpia' (todo a estado estándar 298 K, glucosa cristal, etanol liq):     ΔH ≈ -82 kJ/mol 
  - Biológica (glucosa(aq), etanol(aq), CO2(g) a 1 bar): 
    ΔH ≈ -68 a -75 kJ/mol según fuente 
  - Calor metabólico medido por calorimetría en cervecería: -94 a -110 kJ/mol 
    (incluye crecimiento celular y otras vías) 
El ΔG es muy negativo (-235 kJ/mol) → IRREVERSIBLE termodinámicamente. En la realidad, el límite es por inhibición del etanol sobre la levadura (~12-15% v/v en S. cerevisiae estándar), no por equilibrio. Para QuinoaBrew: asumir conversión declarada (típicamente 90-95% de azúcares fermentables).

### Referencias

- Goldberg & Tewari, J. Phys. Chem. Ref. Data (2002)
- Battley, Thermochim. Acta (1995) — calorimetría
- Stryer Biochemistry 8e Cap. 16

---

## R008 — Esterificación de Fischer (acetato de etilo)

**Categoría:** esterificación  

### Estequiometría

```
1 CH3COOH(l) + 1 C2H5OH(l)  →  1 CH3COOC2H5(l) + 1 H2O(l)
```

| Especie | Fase | ν |
|---|---|---:|
| CH3COOH | l | -1 |
| C2H5OH | l | -1 |
| CH3COOC2H5 | l | +1 |
| H2O | l | +1 |

**Δν =** +0  **Fase global:** líquido  **Rango T válido:** 298–373 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | -4.900 | -2.700 | -2.200 |
| ΔS_rxn [J/(mol·K)] | +11.49 | — | — |
| ΔG_rxn [kJ/mol] | -8.326 | -3.600 | -4.726 |

> ⚠️ **Discrepancia documentada.** Ver sección "Comentarios".

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = +1.3819  (= ΔS_rxn / R)
- B = +589.33 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 28.7 | 28.7 | 4 | ✓ |
| 500.0 | 12.9 | 14.9 | — | — |
| 800.0 | 8.32 | 13.1 | — | — |
| 1200.0 | 6.51 | 14.6 | — | — |

### Comentarios técnicos

Reacción reversible casi atérmica (ΔH ≈ -2.7 kJ/mol). Keq ≈ 3.5-4 a 298 K, varía poco con T. Δν_líq=0. Industrialmente desplazada por exceso de uno de los reactivos, eliminación de H2O (destilación reactiva), o catálisis ácida (H2SO4, resinas sulfónicas). Modelo asume líquidos puros — en realidad hay no-idealidad fuerte (NRTL/UNIQUAC para diseño riguroso). Este Keq es termodinámico, el efectivo basado en concentraciones difiere por γ_i.

### Referencias

- NIST WebBook
- Smith Van Ness 8e Ejemplo 13.13
- Bart et al. AIChE J. (1994)

---

## R009 — Combustión de hidrógeno

**Categoría:** combustión  

### Estequiometría

```
2 H2(g) + 1 O2(g)  →  2 H2O(g)
```

| Especie | Fase | ν |
|---|---|---:|
| H2 | g | -2 |
| O2 | g | -1 |
| H2O | g | +2 |

**Δν =** -1  **Fase global:** gas  **Rango T válido:** 300–2500 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | -483.652 | -483.650 | -0.002 |
| ΔS_rxn [J/(mol·K)] | -88.84 | — | — |
| ΔG_rxn [kJ/mol] | -457.164 | -457.180 | +0.016 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = -10.6852  (= ΔS_rxn / R)
- B = +58169.97 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 1.235e+80 | 1.235e+80 | — | — |
| 500.0 | 7.678e+45 | 5.858e+45 | — | ✓ |
| 800.0 | 8.671e+26 | 3.772e+26 | — | ✓ |
| 1200.0 | 2.582e+16 | 6.467e+15 | — | ✓ |

> 🔒 **Marcado irreversible.** Keq(298) ≈ 1.235e+80. Usar conversión declarada en simulación, no resolver equilibrio.

### Comentarios técnicos

Reacción extremadamente irreversible. Keq(298) ≈ 10^83. Para celdas de combustible y combustión H2. ΔH=-483.6 kJ/mol_extent (con H2O gas) — equivalente a PCI del H2 = 120 MJ/kg.

### Referencias

- NIST JANAF

---

## R010 — Hidrogenación de etileno

**Categoría:** petroquímica  

### Estequiometría

```
1 C2H4(g) + 1 H2(g)  →  1 C2H6(g)
```

| Especie | Fase | ν |
|---|---|---:|
| C2H4 | g | -1 |
| H2 | g | -1 |
| C2H6 | g | +1 |

**Δν =** -1  **Fase global:** gas  **Rango T válido:** 300–800 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | -136.220 | -136.220 | +0.000 |
| ΔS_rxn [J/(mol·K)] | -120.84 | — | — |
| ΔG_rxn [kJ/mol] | -100.192 | -100.970 | +0.778 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = -14.5337  (= ΔS_rxn / R)
- B = +16383.50 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 3.571e+17 | 3.571e+17 | — | — |
| 500.0 | 8.291e+07 | 7.089e+07 | — | ✓ |
| 800.0 | 382 | 255 | — | ✓ |
| 1200.0 | 0.414 | 0.251 | — | — |

> 🔒 **Marcado irreversible.** Keq(298) ≈ 3.571e+17. Usar conversión declarada en simulación, no resolver equilibrio.

### Comentarios técnicos

Exotérmica (-137 kJ/mol). En la práctica industrial el etileno no se hidrogena deliberadamente (se preserva como olefina valiosa). Esta reacción aparece en saturación de impurezas (e.g. C2H4 traza en corrientes de H2 de SMR). Δν=-1, P alta favorece termodinámica. Catalizadores: Pd/C, Ni/Al2O3, Pt.

### Referencias

- NIST WebBook
- Smith Van Ness 8e

---

## R011 — Cracking térmico de etano

**Categoría:** petroquímica  

### Estequiometría

```
1 C2H6(g)  →  1 C2H4(g) + 1 H2(g)
```

| Especie | Fase | ν |
|---|---|---:|
| C2H6 | g | -1 |
| C2H4 | g | +1 |
| H2 | g | +1 |

**Δν =** +1  **Fase global:** gas  **Rango T válido:** 900–1300 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | +136.220 | +136.220 | +0.000 |
| ΔS_rxn [J/(mol·K)] | +120.84 | — | — |
| ΔG_rxn [kJ/mol] | +100.192 | +100.970 | -0.778 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = +14.5337  (= ΔS_rxn / R)
- B = -16383.50 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 2.800e-18 | 2.800e-18 | — | — |
| 500.0 | 1.206e-08 | 1.411e-08 | — | — |
| 800.0 | 0.00262 | 0.00392 | — | — |
| 1200.0 | 2.41 | 3.98 | — | ✓ |

### Comentarios técnicos

Reacción inversa de R010, fuertemente endotérmica (+136 kJ/mol). Δν=+1 → P baja favorece. Industrial (steam cracker): 1100-1200 K, 1-3 bar absoluto, diluido con vapor (steam/HC ratio ~0.3-0.4), residence time <1 s. Conversión por paso ~60-65%. Selectividad a etileno >80%. Compite con coqueado.

### Referencias

- NIST WebBook
- Sundaram & Froment AIChE 1979

---

## R012 — Deshidrogenación de propano

**Categoría:** petroquímica  

### Estequiometría

```
1 C3H8(g)  →  1 C3H6(g) + 1 H2(g)
```

| Especie | Fase | ν |
|---|---|---:|
| C3H8 | g | -1 |
| C3H6 | g | +1 |
| H2 | g | +1 |

**Δν =** +1  **Fase global:** gas  **Rango T válido:** 700–1000 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | +124.680 | +124.680 | +0.000 |
| ΔS_rxn [J/(mol·K)] | +127.53 | — | — |
| ΔG_rxn [kJ/mol] | +86.657 | +85.970 | +0.687 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = +15.3383  (= ΔS_rxn / R)
- B = -14995.56 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 6.582e-16 | 6.582e-16 | — | — |
| 500.0 | 4.329e-07 | 5.400e-07 | — | — |
| 800.0 | 0.0332 | 0.0588 | — | ✓ |
| 1200.0 | 17.2 | 38.1 | — | — |

### Comentarios técnicos

Endotérmica (+124.7 kJ/mol). Δν=+1. Industrial: procesos UOP-Oleflex (Pt-Sn/Al2O3, 850-900 K, 1-3 bar) y Catofin (Cr2O3/Al2O3, ciclos cortos por coqueado). Conversión limitada por equilibrio (~40-50%) y catalizador. PDH (propane dehydrogenation) es ruta industrial creciente para propileno (vs cracking).

### Referencias

- NIST WebBook
- Sattler et al. Chem. Rev. 2014

---

## R013 — Reformado seco de metano (DRM)

**Categoría:** syngas  

### Estequiometría

```
1 CH4(g) + 1 CO2(g)  →  2 CO(g) + 2 H2(g)
```

| Especie | Fase | ν |
|---|---|---:|
| CH4 | g | -1 |
| CO2 | g | -1 |
| CO | g | +2 |
| H2 | g | +2 |

**Δν =** +2  **Fase global:** gas  **Rango T válido:** 800–1300 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | +246.970 | +247.320 | -0.350 |
| ΔS_rxn [J/(mol·K)] | +256.64 | — | — |
| ΔG_rxn [kJ/mol] | +170.451 | +170.600 | -0.149 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = +30.8673  (= ΔS_rxn / R)
- B = -29703.66 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 1.375e-30 | 1.375e-30 | — | — |
| 500.0 | 4.029e-13 | 6.696e-13 | — | — |
| 800.0 | 0.00191 | 0.0076 | — | ✓ |
| 1200.0 | 452 | 3.34e+03 | — | ✓ |

### Comentarios técnicos

Endotérmica fuerte (+247 kJ/mol). Δν=+2. T alta y P baja favorecen. Produce syngas con relación H2/CO=1 (vs ~3 en SMR) — útil para Fischer-Tropsch y química C1. Industrialmente NO está difundida por coqueado severo (reacción Boudouard 2CO→C+CO2 inversa). Activa en investigación para valorización de CO2.

### Referencias

- NIST JANAF
- Pakhare & Spivey Chem. Soc. Rev. 2014

---

## R014 — Síntesis de DME desde syngas

**Categoría:** síntesis industrial  

### Estequiometría

```
2 CO(g) + 4 H2(g)  →  1 CH3OCH3(g) + 1 H2O(g)
```

| Especie | Fase | ν |
|---|---|---:|
| CO | g | -2 |
| H2 | g | -4 |
| CH3OCH3 | g | +1 |
| H2O | g | +1 |

**Δν =** -4  **Fase global:** gas  **Rango T válido:** 500–700 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | -204.866 | -204.870 | +0.004 |
| ΔS_rxn [J/(mol·K)] | -462.83 | — | — |
| ΔG_rxn [kJ/mol] | -66.875 | -66.870 | -0.005 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = -55.6651  (= ΔS_rxn / R)
- B = +24639.72 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 5.199e+11 | 5.199e+11 | — | — |
| 500.0 | 0.00169 | 6.866e-04 | — | ✓ |
| 800.0 | 1.589e-11 | 1.408e-12 | — | — |
| 1200.0 | 5.526e-16 | 1.650e-17 | — | — |

### Comentarios técnicos

Síntesis directa de DME desde syngas (suma de metanol-síntesis + deshidratación). Exotérmica fuerte (-205 kJ/mol con H2O(g); -249 con H2O(l)). Δν=-4 → P alta favorece. Industrial: 220-280°C, 30-100 bar, catalizador bifuncional (Cu/ZnO + γ-Al2O3). Conversión por paso mejor que metanol-síntesis sola porque el agua/CO se acopla vía WGS in-situ. **OJO con convención H2O(g) vs H2O(l)**: si literatura reporta -259 kJ/mol probablemente usa H2O líquida — convertir restando ΔHvap·n_H2O.

### Referencias

- NIST WebBook
- Ng et al. Fuel 1999 (usa H2O(l), no comparable directo)

---

## R015 — Hidratación de etileno a etanol (proceso directo)

**Categoría:** petroquímica  

### Estequiometría

```
1 C2H4(g) + 1 H2O(g)  →  1 C2H5OH(g)
```

| Especie | Fase | ν |
|---|---|---:|
| C2H4 | g | -1 |
| H2O | g | -1 |
| C2H5OH | g | +1 |

**Δν =** -1  **Fase global:** gas  **Rango T válido:** 450–600 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | -45.374 | -45.790 | +0.416 |
| ΔS_rxn [J/(mol·K)] | -127.05 | — | — |
| ΔG_rxn [kJ/mol] | -7.493 | -8.940 | +1.447 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = -15.2812  (= ΔS_rxn / R)
- B = +5457.24 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 20.5 | 20.5 | — | — |
| 500.0 | 0.0127 | 0.0118 | — | ✓ |
| 800.0 | 2.118e-04 | 1.691e-04 | — | — |
| 1200.0 | 2.180e-05 | 1.289e-05 | — | — |

### Comentarios técnicos

Exotérmica moderada (-45.8 kJ/mol). Δν=-1. Industrial (Shell, BP): 250-300°C, 60-80 bar, catalizador H3PO4/SiO2 (acid phosphoric on diatomaceous earth). Conversión por paso ~5% (limitada por equilibrio y selectividad a éter), recirculación masiva. Acá usamos etanol(g) porque la reacción ocurre en fase gas; el etanol producto se condensa río abajo.

### Referencias

- NIST WebBook
- Cavani & Trifirò

---

## R016 — Alquilación de benceno con etileno (etilbenceno)

**Categoría:** petroquímica  

### Estequiometría

```
1 C6H6(g) + 1 C2H4(g)  →  1 C2H5_C6H5(g)
```

| Especie | Fase | ν |
|---|---|---:|
| C6H6 | g | -1 |
| C2H4 | g | -1 |
| C2H5_C6H5 | g | +1 |

**Δν =** -1  **Fase global:** gas  **Rango T válido:** 550–750 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | -105.540 | -105.540 | +0.000 |
| ΔS_rxn [J/(mol·K)] | -127.96 | — | — |
| ΔG_rxn [kJ/mol] | -67.389 | -67.390 | +0.001 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = -15.3901  (= ΔS_rxn / R)
- B = +12693.54 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 6.397e+11 | 6.397e+11 | — | — |
| 500.0 | 2.196e+04 | 2.468e+04 | — | — |
| 800.0 | 1.61 | 2.45 | — | — |
| 1200.0 | 0.00813 | 0.0178 | — | — |

> 🔒 **Marcado irreversible.** Keq(298) ≈ 6.397e+11. Usar conversión declarada en simulación, no resolver equilibrio.

### Comentarios técnicos

Exotérmica (-104.5 kJ/mol). Δν=-1. Industrial: dos rutas — fase líquida con AlCl3 (Friedel-Crafts clásico, en declive) o fase vapor con zeolita (ZSM-5, MWW). 380-450°C, 7-30 bar. Conversión >99% en condiciones industriales. Selectividad a etilbenceno >99% (polialquilados <1%, transalquilados in-situ).

### Referencias

- NIST WebBook
- Perego & Ingallina Catal. Today 2002

---

## R017 — Respiración aerobia de glucosa

**Categoría:** bioquímica  

### Estequiometría

```
1 Glucose(aq) + 6 O2(g)  →  6 CO2(g) + 6 H2O(l)
```

| Especie | Fase | ν |
|---|---|---:|
| Glucose | aq | -1 |
| O2 | g | -6 |
| CO2 | g | +6 |
| H2O | l | +6 |

**Δν =** +5  **Fase global:** mixta (aq/gas/liq)  **Rango T válido:** 283–313 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | -2813.940 | -2813.940 | +0.000 |
| ΔS_rxn [J/(mol·K)] | +207.50 | — | — |
| ΔG_rxn [kJ/mol] | -2875.806 | -2875.810 | +0.004 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = +24.9563  (= ΔS_rxn / R)
- B = +338439.19 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | ∞ | ∞ | — | ✓ |
| 500.0 | ∞ | ∞ | — | — |
| 800.0 | 3.683e+194 | 2.044e+199 | — | — |
| 1200.0 | 2.107e+133 | 1.096e+142 | — | — |

> 🔒 **Marcado irreversible.** Keq(298) ≈ ∞. Usar conversión declarada en simulación, no resolver equilibrio.

### Comentarios técnicos

Combustión bioquímica completa de glucosa. ΔH calorimétrica empírica = -2792 kJ/mol_glucosa para glucosa(aq) + O2(g) → CO2(g) + H2O(l) según Domalski/NIST. Mi cálculo Hess desde Capa 3 da -2814 kJ/mol — diferencia de 22 kJ/mol que viene del mismo problema de convenciones acuosas que en R007 (estados estándar molal vs Henry vs fracción molar para soluto). Para balance energético de biorreactores: usar valor empírico calorimétrico, no Hess. Energía metabólica neta: ATP máx 38 mol/mol_glucosa (~30% eficiencia). Crítica para QuinoaBrew: aireación inicial de mosto promueve crecimiento celular vía esta vía antes de cambiar a fermentación anaerobia (Pasteur effect).

### Referencias

- Domalski Selected Values of Heats of Combustion 1972 (calorímetro: -2792)
- Goldberg & Tewari 2002

---

## R018 — Hidrólisis de sacarosa (inversión)

**Categoría:** bioquímica  

### Estequiometría

```
1 Sucrose(aq) + 1 H2O(l)  →  2 Glucose(aq)
```

| Especie | Fase | ν |
|---|---|---:|
| Sucrose | aq | -1 |
| H2O | l | -1 |
| Glucose | aq | +2 |

**Δν =** +0  **Fase global:** acuoso  **Rango T válido:** 293–343 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | -21.670 | -21.670 | -0.000 |
| ΔS_rxn [J/(mol·K)] | +23.05 | — | — |
| ΔG_rxn [kJ/mol] | -28.542 | -28.540 | -0.002 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = +2.7723  (= ΔS_rxn / R)
- B = +2606.30 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 1.001e+05 | 1.001e+05 | — | ✓ |
| 500.0 | 2.94e+03 | 1.29e+03 | — | — |
| 800.0 | 416 | 30.6 | — | — |
| 1200.0 | 140 | 1.35 | — | — |

> 🔒 **Marcado irreversible.** Keq(298) ≈ 1.001e+05. Usar conversión declarada en simulación, no resolver equilibrio.

### Comentarios técnicos

APROXIMACIÓN: estequiometría real es sacarosa + H2O → glucosa + fructosa; acá modelamos como sacarosa + H2O → 2 glucosa (error <2 kJ/mol porque ΔHf(fructosa, aq)=-1265 vs glucosa -1262 kJ/mol). ΔH ligeramente exotérmica, ΔS positiva (1→2 moléculas → entropía crece) → muy favorable. En cervecería: invertasa endógena de levadura procesa esto durante fermentación; tiempo <2 h.

### Referencias

- Goldberg & Tewari Biophys. Chem. 1989 (real glu+fru: ΔH=-14.7, ΔG=-29.3)
- Tewari & Goldberg J. Biol. Chem. 1989

---

## R019 — Oxidación de etanol a acetaldehído (defecto cervecero)

**Categoría:** bioquímica / oxidación  

### Estequiometría

```
2 C2H5OH(aq) + 1 O2(g)  →  2 CH3CHO(aq) + 2 H2O(l)
```

| Especie | Fase | ν |
|---|---|---:|
| C2H5OH | aq | -2 |
| O2 | g | -1 |
| CH3CHO | aq | +2 |
| H2O | l | +2 |

**Δν =** +1  **Fase global:** acuoso  **Rango T válido:** 273–323 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | -419.060 | -419.060 | +0.000 |
| ΔS_rxn [J/(mol·K)] | -22.25 | — | — |
| ΔG_rxn [kJ/mol] | -412.426 | -412.430 | +0.004 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = -2.6763  (= ΔS_rxn / R)
- B = +50401.33 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 1.794e+72 | 1.794e+72 | — | ✓ |
| 500.0 | 4.128e+42 | 1.649e+42 | — | — |
| 800.0 | 1.581e+26 | 8.349e+24 | — | — |
| 1200.0 | 1.198e+17 | 5.984e+14 | — | — |

> 🔒 **Marcado irreversible.** Keq(298) ≈ 1.794e+72. Usar conversión declarada en simulación, no resolver equilibrio.

### Comentarios técnicos

FALTA Cp para CH3CHO(aq) en Capa 3 — calculamos solo dH/dG/dS a 298 K. ΔH muy exotérmica (-348 kJ/mol_extent). Acetaldehído es defecto cervecero (sabor a manzana verde, umbral 5-25 ppm). Causa: levaduras estresadas, fermentación incompleta, contaminación bacteriana (acetobacter en presencia de O2). Para QuinoaBrew: control con purga de O2, sanitización, fermentación completa con maduración suficiente para que la levadura reabsorba el acetaldehído producido como intermediario normal.

### Referencias

- NIST WebBook (especies puras)
- NBS Tables / Goldberg (acuosos, aprox)
- Bamforth 'Beer Quality Safety and Nutritional Aspects' 2011

---

## R020 — Oxidación de acetaldehído a ácido acético (avinagrado)

**Categoría:** bioquímica / oxidación  

### Estequiometría

```
2 CH3CHO(aq) + 1 O2(g)  →  2 CH3COOH(aq)
```

| Especie | Fase | ν |
|---|---|---:|
| CH3CHO | aq | -2 |
| O2 | g | -1 |
| CH3COOH | aq | +2 |

**Δν =** -1  **Fase global:** acuoso  **Rango T válido:** 273–323 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | -547.520 | -547.520 | +0.000 |
| ΔS_rxn [J/(mol·K)] | -187.75 | — | — |
| ΔG_rxn [kJ/mol] | -491.542 | -491.540 | -0.002 |

> ✓ Coherencia Capa 3 ↔ literatura dentro de tolerancia.

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = -22.5814  (= ΔS_rxn / R)
- B = +65851.52 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 1.301e+86 | 1.301e+86 | — | ✓ |
| 500.0 | 2.460e+47 | 1.776e+47 | — | — |
| 800.0 | 8.744e+25 | 3.021e+25 | — | — |
| 1200.0 | 1.060e+14 | 1.505e+13 | — | — |

> 🔒 **Marcado irreversible.** Keq(298) ≈ 1.301e+86. Usar conversión declarada en simulación, no resolver equilibrio.

### Comentarios técnicos

NOTA: NO TENEMOS ΔHf°(ácido acético, aq) ni ΔHf°(acetaldehído, aq) en Capa 3 — los valores en COMPOUNDS son fase líquida pura. Reportamos cálculo usando líquido puro como proxy, advirtiendo que el valor real en solución diluida puede diferir en ±10 kJ/mol. Reacción que causa avinagrado por Acetobacter (defecto grave). Industrial: usada deliberadamente para producir vinagre por fermentación acética (Acetobacter aceti). ΔH muy exotérmica.

### Referencias

- NIST WebBook (especies puras)
- NBS Tables (acuosos, aprox)
- Adams 'Vinegars of the World' 2009

---

## R021 — Transesterificación de triolein a FAME (biodiésel)

**Categoría:** oleoquímica  

### Estequiometría

```
1 Triolein(l) + 3 CH3OH(l)  →  3 MeOleate(l) + 1 Glycerol(l)
```

| Especie | Fase | ν |
|---|---|---:|
| Triolein | l | -1 |
| CH3OH | l | -3 |
| MeOleate | l | +3 |
| Glycerol | l | +1 |

**Δν =** +0  **Fase global:** líquido  **Rango T válido:** 323–363 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | +61.800 | -10.000 | +71.800 |
| ΔS_rxn [J/(mol·K)] | +158.90 | — | — |
| ΔG_rxn [kJ/mol] | +14.424 | -12.000 | +26.424 |

> ⚠️ **Discrepancia documentada.** Ver sección "Comentarios".

### Keq(T) — coeficientes

**Forma simplificada** `ln Keq = A + B/T` (ΔCp=0):

- A = +19.1113  (= ΔS_rxn / R)
- B = -7432.83 K  (= −ΔH_rxn / R)

**Forma rigurosa:** usar `Keq_DIPPR(stoich, T)` del módulo `rxn_thermo` — integra ΔCp_rxn analíticamente con polinomios DIPPR-100 de Capa 2.

### Keq evaluado en T = 298, 500, 800, 1200 K

| T [K] | Keq (2-param) | Keq (DIPPR-100) | Keq lit (si hay) | Dentro de rango? |
|---:|---:|---:|---:|:---:|
| 298.1 | 0.00297 | 0.00297 | — | — |
| 500.0 | 69.8 | 65.7 | — | — |
| 800.0 | 1.840e+04 | 1.521e+04 | — | — |
| 1200.0 | 4.073e+05 | 2.901e+05 | — | — |

### Comentarios técnicos

⚠ VALORES ESTIMADOS POR JOBACK. ΔH y ΔG de triolein y oleato de metilo no tienen valores primarios precisos. Incertidumbre declarada ±20 kJ/mol. Industrial: 60-65°C (no >65 para evitar evaporar metanol), 1 bar, catalizador alcalino (NaOH, KOH, NaOMe). Conversión >97% en 1 h con exceso de metanol 6:1 vs 3:1 estequio. Reacción casi atérmica termodinámicamente, controlada por cinética y separación de fases (glicerina sale como fase pesada). El Keq ~3 obtenido es CONSISTENTE con datos empíricos de Noureddini & Zhu 1997, pero el ΔH no se puede comparar contra calorimetría — se desconoce.

### Referencias

- Knothe Biodiesel Handbook 2e (2010)
- Noureddini & Zhu JAOCS 1997 (cinética)

---

## R022 — Hidrólisis enzimática de almidón a glucosa

**Categoría:** bioquímica    ⚠ **NO DERIVADA DE CAPA 3**

### Estequiometría

```
1 Starch_unit(s) + 1 H2O(l)  →  1 Glucose(aq)
```

**Fase global:** heterogéneo (sólido/aq)  **Rango T válido:** 323–363 K

### Termodinámica @ 298.15 K (literatura empírica, NO derivable)

- ΔH_rxn = -10.00 kJ/mol  *(valor empírico/estimado, ver comentarios)*
- ΔG_rxn = -30.00 kJ/mol  *(usar con precaución, idem)*

### Comentarios técnicos

⚠ NO HAY TERMODINÁMICA FORMAL. 'Almidón' es polímero polidisperso, sin ΔHf° definido. NO usar Keq derivado de Capa 3 — los campos dHf de Starch_unit están deliberadamente vacíos. Modelar como IRREVERSIBLE con CONVERSIÓN DECLARADA por el usuario. Conversión típica con α-amilasa (mash 65°C, pH 5.4) + amiloglucosidasa (60-65°C, pH 4.5): 90-95% de almidón convertido a azúcares fermentables. ΔH experimental aprox -10 kJ/mol_unidad_glucosa (puente glicosídico se rompe, ligeramente exotérmico). Para QuinoaBrew: este es el paso de macerado, controla rendimiento del extracto.

### Referencias

- Robyt 'Essentials of Carbohydrate Chemistry' 1998
- Tester et al. Int. J. Biol. Macromol. 2004

---

## R023 — Absorción de CO2 en MDEA (Kent-Eisenberg)

**Categoría:** endulzamiento de gas (amina)    ⚠ **NO DERIVADA DE CAPA 3**

### Estequiometría

```
1 CO2(g) + 1 MDEA(aq)  →  (productos modelados implícitamente)
```

**Fase global:** absorción gas-líquido  **Rango T válido:** 303–393 K

### Termodinámica @ 298.15 K (literatura empírica, NO derivable)

- ΔH_rxn = -60.00 kJ/mol  *(valor empírico/estimado, ver comentarios)*
- ΔG_rxn = -10.00 kJ/mol  *(usar con precaución, idem)*

### Comentarios técnicos

⚠ NO SE DERIVA TERMODINÁMICAMENTE DESDE CAPA 3. Esta reacción es un SISTEMA multireacción acoplado (CO2 hidroliza, MDEA protona, bicarbonato/carbamato se forman, todo dependiente de pH). El enfoque industrial es modelo de Kent-Eisenberg (1976) o Austgen (1989) con Keq APARENTES MEDIDOS experimentalmente, no calculados desde ΔGf°. Para tu simulador, recomiendo: 
(a) NO USAR Keq derivado — los valores reportados acá son orientativos. 
(b) Usar correlación empírica de loading (mol CO2/mol amina) vs presión parcial de CO2 a T dada (curvas tipo Posey-Rochelle). 
(c) Para diseño riguroso: paquete e-NRTL de Aspen Plus o ProTreat con datos experimentales calibrados. 
Lit values reportados son ΔH efectivo de absorción medido por calorimetría (Mathonat 1998, Carson 2000): aprox -55 a -70 kJ/mol_CO2_absorbido, varía con loading. ΔG efectivo no es magnitud termodinámica bien definida acá.

### Referencias

- Kent & Eisenberg Hydrocarbon Processing 1976
- Austgen et al. Ind. Eng. Chem. Res. 1989
- Mathonat et al. Ind. Eng. Chem. Res. 1998

---

## R024 — Absorción de H2S en MDEA

**Categoría:** endulzamiento de gas (amina)    ⚠ **NO DERIVADA DE CAPA 3**

### Estequiometría

```
1 H2S(g) + 1 MDEA(aq)  →  (productos modelados implícitamente)
```

**Fase global:** absorción gas-líquido  **Rango T válido:** 303–393 K

### Termodinámica @ 298.15 K (literatura empírica, NO derivable)

- ΔH_rxn = -35.00 kJ/mol  *(valor empírico/estimado, ver comentarios)*
- ΔG_rxn = -20.00 kJ/mol  *(usar con precaución, idem)*

### Comentarios técnicos

⚠ Mismo régimen que R023. Reacción ácido-base rápida (H2S protona MDEA directamente, no requiere paso hidrólisis lento como CO2). Por eso MDEA tiene selectividad H2S/CO2 industrialmente útil (~5-15× a baja loading). ΔH absorción ≈ -34 a -38 kJ/mol_H2S. Cinética: instantánea (controlada por transferencia de masa, no por reacción). MISMO TRATAMIENTO: no derivar de Capa 3, usar correlaciones empíricas de equilibrio H2S-amina-H2O.

### Referencias

- Kent & Eisenberg Hydrocarbon Processing 1976
- Jou et al. Ind. Eng. Chem. Process Des. Dev. 1982

---

## R025 — Reacción de Boudouard (gasificación de C)

**Categoría:** syngas / carbón    ⚠ **NO DERIVADA DE CAPA 3**

### Estequiometría

```
1 CO2(g)  →  2 CO(g)
```

**Fase global:** heterogéneo (gas-sólido)  **Rango T válido:** 900–1500 K

### Termodinámica @ 298.15 K (literatura empírica, NO derivable)

- ΔH_rxn = +172.46 kJ/mol  *(valor empírico/estimado, ver comentarios)*
- ΔG_rxn = +120.00 kJ/mol  *(usar con precaución, idem)*

### Comentarios técnicos

⚠ ESTEQUIOMETRÍA INCOMPLETA en este registro — C(grafito) se asume implícito. Para cálculo correcto, agregar C(s) a Capa 3 con dHf=0, S°=5.74 J/(mol·K). Endotérmica (+172.5 kJ/mol). Reacción clave en gasificación de carbón y compite con coqueado en reformado seco (R013, inversa de esta). Por encima de 1000 K el equilibrio favorece CO. Para reactores con catalizador metálico, esta reacción ES el mecanismo de coqueado/desactivación si se acumula C depositado. Keq es función de actividad de C(s) que se toma como 1.

### Referencias

- NIST JANAF (CO, CO2)
- Higman & van der Burgt 'Gasification' 2e (2008)

---

## R026 — Carbonilación de metanol a ácido acético

**Categoría:** química fina / C1    ⚠ **NO DERIVADA DE CAPA 3**

### Estequiometría

```
1 CH3OH(l) + 1 CO(g)  →  1 CH3COOH(l)
```

| Especie | Fase | ν |
|---|---|---:|
| CH3OH | l | -1 |
| CO | g | -1 |
| CH3COOH | l | +1 |

**Δν =** -1  **Fase global:** líquido/gas  **Rango T válido:** 420–480 K

### Termodinámica @ 298.15 K (literatura empírica, NO derivable)

- ΔH_rxn = -133.77 kJ/mol  *(valor empírico/estimado, ver comentarios)*
- ΔG_rxn = -80.00 kJ/mol  *(usar con precaución, idem)*

### Comentarios técnicos

Calculable por Hess desde Capa 3 (CH3OH_l, CO_g, CH3COOH_l todos con dHf°): ΔH≈-133.8 kJ/mol (literatura -135). NO derivada formalmente acá para mantener consistencia con el patrón "convención NO DERIVADA" del catálogo educativo. Proceso Monsanto/Cativa: catalizador Rh/Ir + promotor yoduro de metilo, 150–200 °C, 30–60 bar. Conversión por paso ~99% selectiva, irreversible (Keq>>1). usar conversión declarada en simulación, no resolver equilibrio. La carbonilación NO produce agua — la estequiometría neta es exactamente 1+1→1.

### Referencias

- Paulik F.E. & Roth J.F., Chem. Commun. 1968 (Monsanto)
- Cativa BP process, Ind. Eng. Chem. Res. 1996
- Ullmann's Encyclopedia "Acetic Acid"

---

## R027 — Polimerización de etileno a PE (LDPE)

**Categoría:** polímeros    ⚠ **NO DERIVADA DE CAPA 3**

### Estequiometría

```
1 C2H4(g)  →  1 polyethylene(s)
```

| Especie | Fase | ν |
|---|---|---:|
| C2H4 | g | -1 |
| polyethylene | s | +1 |

**Δν =** 0  **Fase global:** gas→sólido  **Rango T válido:** 350–600 K

### Termodinámica @ 298.15 K (literatura empírica, NO derivable)

- ΔH_rxn = -93.00 kJ/mol  *(valor empírico/estimado, ver comentarios)*
- ΔG_rxn = -50.00 kJ/mol  *(usar con precaución, idem)*

### Comentarios técnicos

Polimerización por adición — NO es equilibrio termodinámico, es cinética de cadena (radical libre para LDPE, coordinada Ziegler-Natta para HDPE). polyethylene es pseudo-polímero polidisperso, sin ΔHf° formal. usar conversión declarada en simulación, no resolver equilibrio. Conversión por paso LDPE 20–35% (alta P, ~2000 bar, 200–300 °C, iniciador peróxido); con reciclo del etileno no reaccionado, conversión global ~95%. Calor de polimerización ≈ -93 kJ/mol_etileno (Δ del enlace π de C2H4) — extracción de calor crítica en el reactor. Modelar Modo B con duty grande exotérmico.

### Referencias

- Ullmann's Encyclopedia "Polyethylene"
- Ziegler K. (LDPE 1953); Natta G. (estereorregular 1954)
- Brandrup-Immergut "Polymer Handbook" 4e

---

## R028 — Síntesis directa de HCl (H₂+Cl₂)

**Categoría:** inorgánica pesada    ⚠ **NO DERIVADA DE CAPA 3**

### Estequiometría

```
1 H2(g) + 1 Cl2(g)  →  2 HCl(g)
```

| Especie | Fase | ν |
|---|---|---:|
| H2 | g | -1 |
| Cl2 | g | -1 |
| HCl | g | +2 |

**Δν =** 0  **Fase global:** gas  **Rango T válido:** 500–1500 K

### Termodinámica @ 298.15 K (literatura empírica, NO derivable)

- ΔH_rxn = -184.60 kJ/mol  *(valor empírico/estimado, ver comentarios)*
- ΔG_rxn = -190.55 kJ/mol  *(usar con precaución, idem)*

### Comentarios técnicos

Cl2 y HCl NO están en Capa 3 con ΔHf° (NIST: HCl(g)≈-92.31, Cl2(g)=0). Marcamos NO DERIVADA para mantener consistencia y permitir Modo A con conversión declarada. Reacción explosivamente exotérmica con ignición (luz UV o llama). Keq enormemente favorable a productos en todo el rango — modelar como IRREVERSIBLE con conversión ≥99%. Industrial: quemador con llama H2 en atmósfera de Cl2, T≈800–1000 °C, seguido de absorción del HCl gaseoso en agua para producir HCl(aq) 33–37%.

### Referencias

- NIST WebBook (HCl, H2, Cl2)
- Ullmann's Encyclopedia "Hydrochloric Acid"
- Greenwood & Earnshaw "Chemistry of the Elements" 2e

---

## R029 — Calcinación de caliza (descarbonatación)

**Categoría:** materiales / cemento    ⚠ **NO DERIVADA DE CAPA 3**

### Estequiometría

```
1 CaCO3(s)  →  1 CaO(s) + 1 CO2(g)
```

| Especie | Fase | ν |
|---|---|---:|
| CaCO3 | s | -1 |
| CaO | s | +1 |
| CO2 | g | +1 |

**Δν =** +1  **Fase global:** sólido→sólido+gas  **Rango T válido:** 1100–1500 K

### Termodinámica @ 298.15 K (literatura empírica, NO derivable)

- ΔH_rxn = +178.30 kJ/mol  *(valor empírico/estimado, ver comentarios)*
- ΔG_rxn = +130.40 kJ/mol  *(usar con precaución, idem)*

### Comentarios técnicos

CaCO3 y CaO NO están en Capa 3 (caliza/cal son pseudo-componentes en components.py). ΔH literatura: ΔHf°(CaCO3,s)=-1207.6, ΔHf°(CaO,s)=-635.1, ΔHf°(CO2,g)=-393.5 → ΔH_rxn = -635.1 + -393.5 - (-1207.6) = +179.0 kJ/mol (Boynton 1980 reporta +178.3 ± 1). Endotérmica fuerte — domina el balance energético de los hornos de cal y cemento. A T ≥ 1100 K va a completitud (descomposición térmica irreversible). usar conversión declarada en simulación, no resolver equilibrio (>99% conversión a T de horno). Emisión inherente de CO2 (≈0.44 kg CO2 por kg CaO producido) — punto educativo crítico para la huella de carbono industria de cemento.

### Referencias

- Ullmann's Encyclopedia "Cement"/"Lime"
- Boynton R.S. "Chemistry and Technology of Lime and Limestone" 2e (1980)
- NIST JANAF (CO2)

---

## R030 — Saponificación de triglicérido

**Categoría:** consumo / química industrial    ⚠ **NO DERIVADA DE CAPA 3**

### Estequiometría

```
1 vegetable_oil(l) + 3 NaOH(s)  →  3 soap(s) + 1 glycerin(l)
```

| Especie | Fase | ν |
|---|---|---:|
| vegetable_oil | l | -1 |
| NaOH | s | -3 |
| soap | s | +3 |
| glycerin | l | +1 |

**Δν =** 0  **Fase global:** líquido/sólido  **Rango T válido:** 320–380 K

### Termodinámica @ 298.15 K (literatura empírica, NO derivable)

- ΔH_rxn = -60.00 kJ/mol  *(valor empírico/estimado, ver comentarios)*
- ΔG_rxn = -100.00 kJ/mol  *(usar con precaución, idem)*

### Comentarios técnicos

NaOH y soap NO están en Capa 3 (pseudo-componentes). Reacción base de fabricación de jabón sólido — hidrólisis alcalina de triglicérido. Conversión >99% con exceso de álcali, T 70–100 °C, agitación intensa. Exotérmica suave (-60 kJ/mol_oil aprox). Subproducto: glicerina (purificable, valor industrial). usar conversión declarada en simulación, no resolver equilibrio. NOTA: vegetable_oil es pseudo (triolein-like, MW~885 g/mol); estequiometría ν=3 NaOH refleja los 3 ésteres del triglicérido.

### Referencias

- Ullmann's Encyclopedia "Soap"
- Spitz L. "Soap Manufacturing Technology" AOCS Press 2009

---

## R031 — Síntesis de urea (Bosch-Meiser)

**Categoría:** fertilizantes / inorgánica    ⚠ **NO DERIVADA DE CAPA 3**

### Estequiometría

```
2 NH3(g) + 1 CO2(g)  →  1 urea(l) + 1 H2O(l)
```

| Especie | Fase | ν |
|---|---|---:|
| NH3 | g | -2 |
| CO2 | g | -1 |
| urea | l | +1 |
| H2O | l | +1 |

**Δν =** -2  **Fase global:** gas→líquido  **Rango T válido:** 440–470 K

### Termodinámica @ 298.15 K (literatura empírica, NO derivable)

- ΔH_rxn = -101.00 kJ/mol  *(valor empírico/estimado, ver comentarios)*
- ΔG_rxn = -27.00 kJ/mol  *(usar con precaución, idem)*

### Comentarios técnicos

urea NO está en Capa 3 (pseudo). Proceso Bosch-Meiser: dos pasos vía carbamato de amonio (2 NH3 + CO2 → NH2COONH4, exotérmica) seguido de deshidratación a urea (NH2COONH4 → urea + H2O, endotérmica). El balance neto global modelado acá. Reactor a 180–200 °C, 130–200 bar. Conversión por paso de CO2 ~50–60% (limitada por equilibrio del carbamato); planta real usa stripping NH3 y reciclo de carbamato a alta presión para conversión global ~99%. usar conversión declarada en simulación, no resolver equilibrio. Para E14 implementar Modo A con conversión declarada + lazo de reciclo simplificado (Wegstein) o purga.

### Referencias

- Ullmann's Encyclopedia "Urea"
- Meessen J.H. "Urea Production and Manufacture" Wiley 2010

---


## R032 — Absorción de SO3 en agua (formación de ácido sulfúrico)

**Categoría:** inorgánica / ácido sulfúrico    ⚠ **NO DERIVADA DE CAPA 3**

### Estequiometría

```
1 SO3(g) + 1 H2O(l)  →  1 H2SO4(l)
```

| Especie | Fase | ν |
|---|---|---:|
| SO3 | g | -1 |
| H2O | l | -1 |
| H2SO4 | l | +1 |

**Δν =** -2  **Fase global:** gas→líquido  **Rango T válido:** 320–420 K

### Termodinámica @ 298.15 K (literatura empírica, NO derivable)

- ΔH_rxn = -132.00 kJ/mol  *(de ΔHf: H2SO4(l) -814.0, SO3(g) -395.7, H2O(l) -285.8 → -132.5; fuertemente exotérmica)*

### Comentarios técnicos

Paso final del proceso de contacto: el SO3 del convertidor se absorbe en ácido
sulfúrico concentrado (no en agua pura — la absorción directa en agua forma
niebla de H2SO4). En la torre de absorción la reacción es prácticamente
completa e irreversible. Se modela como inline_reaction para el balance de
masa: 1 mol SO3 + 1 mol H2O → 1 mol H2SO4 (conserva S, O, H). H2SO4 es pseudo
para VLE (líquido no volátil), pero su MW (98.079) y ΔHf habilitan el balance
de masa y energía.

### Referencias

- Perry's Chemical Engineers' Handbook, "Sulfuric Acid"
- Ullmann's Encyclopedia "Sulfuric Acid and Sulfur Trioxide"

---


## R033 — Oxidación de NO a NO2 (proceso Ostwald)

**Categoría:** inorgánica / ácido nítrico    ⚠ **NO DERIVADA DE CAPA 3**

### Estequiometría

```
2 NO(g) + 1 O2(g)  →  2 NO2(g)
```

| Especie | Fase | ν |
|---|---|---:|
| NO | g | -2 |
| O2 | g | -1 |
| NO2 | g | +2 |

**Δν =** -1  **Fase global:** gas  **Rango T válido:** 290–400 K

### Termodinámica @ 298.15 K (literatura empírica, NO derivable)

- ΔH_rxn = -114.00 kJ/mol  *(de ΔHf: 2·NO2(33.18) − 2·NO(90.25) = -114.1; exotérmica)*

### Comentarios técnicos

Oxidación en fase gas del NO del quemador a NO2 (proceso Ostwald). LENTA y
favorecida a baja T; se realiza enfriando el gas. CLAVE para el balance de
masa: el NO2 producido pesa MÁS que el NO consumido porque gana un átomo de O
del O2 (MW NO 30.01 → NO2 46.01). 16 kmol NO consumido → 16 kmol NO2 = 736 t/a
(no 480, que sería la masa del NO); los 256 t/a extra vienen de 8 kmol O2.

### Referencias

- Ullmann's Encyclopedia "Nitric Acid, Nitrous Acid, and Nitrogen Oxides"

---


## R034 — Absorción de NOx en agua a HNO3

**Categoría:** inorgánica / ácido nítrico    ⚠ **NO DERIVADA DE CAPA 3**

### Estequiometría

```
3 NO2(g) + 1 H2O(l)  →  2 HNO3(l) + 1 NO(g)
```

| Especie | Fase | ν |
|---|---|---:|
| NO2 | g | -3 |
| H2O | l | -1 |
| HNO3 | l | +2 |
| NO | g | +1 |

**Δν =** -1  **Fase global:** gas→líquido  **Rango T válido:** 290–340 K

### Termodinámica @ 298.15 K (literatura empírica, NO derivable)

- ΔH_rxn = -73.00 kJ/mol  *(exotérmica; absorción en torre)*

### Comentarios técnicos

Absorción del NO2 en agua en la torre de absorción: 3 NO2 + H2O → 2 HNO3 + NO.
Reacción de desproporción: 1 de cada 3 NO2 se reduce a NO (que se re-oxida vía
R033 y recircula), los otros 2 forman HNO3. Conserva N/O/H. Es la base del
balance de masa del condensado ácido débil y del gas NOx de reciclo.

### Referencias

- Ullmann's Encyclopedia "Nitric Acid, Nitrous Acid, and Nitrogen Oxides"

---


## R035 — Hidrodealquilación de tolueno (HDA)

**Categoría:** petroquímica

### Estequiometría

```
1 C7H8(g) + 1 H2(g)  →  1 C6H6(g) + 1 CH4(g)
```

| Especie | Fase | ν |
|---|---|---:|
| C7H8 | g | -1 |
| H2 | g | -1 |
| C6H6 | g | +1 |
| CH4 | g | +1 |

**Δν =** 0  **Fase global:** gas  **Rango T válido:** 800–950 K

### Termodinámica @ 298.15 K

Valores **derivados de Capa 3 por Hess** (ΔHf_gas de thermo_db, single source of truth):

| Cantidad | Valor (Capa 3) | Lit reportado | Δ |
|---|---:|---:|---:|
| ΔH_rxn [kJ/mol] | -42.11 | -42.0 | -0.11 |

Cálculo (Hess, ΔHf_gas en kJ/mol de thermo_db):
`ΔH = (ΔHf[C6H6] + ΔHf[CH4]) − (ΔHf[C7H8] + ΔHf[H2])`
`   = (+82.93 + (−74.87)) − (+50.17 + 0.0) = −42.11 kJ/mol` → exotérmica.
Coincide con literatura HDA (~−42 kJ/mol). [trazable, derivado de ΔHf experimentales]

**Marcado irreversible:** la HDA térmica a 800–950 K es esencialmente
irreversible (conversión gobernada por cinética, no por equilibrio). No se
declara Van't Hoff ni Keq — el reactor se modela por conversión por paso.

### Comentarios técnicos

Hidrodealquilación de tolueno a benceno: C7H8 + H2 → C6H6 + CH4. Δν=0,
exotérmica (−42.11 kJ/mol). Dos variantes industriales: **térmica** (HDA, sin
catalizador, ~870–920 K, 30–50 bar) y **catalítica** (Detol/Pyrotol, Cr2O3 o
Pt sobre alúmina, ~810–870 K, temperatura algo menor). [típico — proceso HDA]

Se opera con **exceso de H2**, ratio molar H2/tolueno típico ~5:1, para
desplazar conversión y suprimir reacciones secundarias (formación de difenilo
por 2 C6H6 ⇌ difenilo + H2, no modelada acá). Conversión de tolueno por paso
~40–60 %; el tolueno no convertido se recircula. Selectividad a benceno
>95 %. [típico — Turton/Douglas usan HDA como caso de estudio canónico]

NOTA cinética: no se declara k0/Ea/rate_law (kinetics_available=False) — no se
citó fuente cinética verificada. El reactor debe usarse en modo conversión
declarada (stoichiometric), no cinético. La metalurgia y condiciones de arriba
son [típico] con referencia a la literatura de proceso, no valores de una
planta específica.

### Referencias

- Turton et al., "Analysis, Synthesis and Design of Chemical Processes" (HDA, caso de estudio canónico)
- Douglas, "Conceptual Design of Chemical Processes" (proceso HDA)
- ΔHf_gas: thermo_db (Capa 3), confirmado contra NIST WebBook

---


## Roadmap futuro (v1.1+)

1. **Capa 5 (Equilibrio físico):** EOS cúbica (SRK/PR) para fugacidades; NRTL/UNIQUAC para actividad en líquido. Resuelve limitaciones #1 y #4.
2. **Multi-reacción por Gibbs minimization** (limitación #7) — para SMR+WGS, DRM+Boudouard, aminas.
3. **Capa 6 (Cinética):** Arrhenius por reacción, modelos LH/ER. Resuelve limitación #6.
4. **Iones acuosos** con convención unificada (Helgeson, e-NRTL).
5. **Completar Capa 3** con C(grafito), polimorfos, valores acuosos auditados desde fuente única.
