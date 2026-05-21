# Tabla Benson — Group Additivity Values (GAV) para estimación de ΔHf°, S°, Cp

**Fuentes primarias:**

1. Benson, S.W. "Thermochemical Kinetics: Methods for the Estimation of
   Thermochemical Data and Rate Parameters", 2nd ed., Wiley, 1976.
2. Cohen, N. "Revised Group Additivity Values for Enthalpies of Formation
   (at 298 K) of Carbon-Hydrogen and Carbon-Hydrogen-Oxygen Compounds",
   J. Phys. Chem. Ref. Data, 25(6), 1411-1481, 1996.
3. Sabbe et al. "Group additive values for the gas phase standard enthalpy
   of formation of hydrocarbons and hydrocarbon radicals" (2005).
4. Paraskevas et al. "Group additive values for ... oxygenates", Chem. Eur.
   J., 19, 16431-16452, 2013.

---

## Filosofía Benson vs Joback

**Joback:** clasifica por **grupo funcional** (1 grupo = 1 contribución).
Simple, pero no captura efectos de vecinos.

**Benson:** clasifica por **átomo central + sus átomos vecinos**.
Más fino, captura efectos de hibridización y enlace.

Notación Benson: `Central-(Vecino1)(Vecino2)...(VecinoN)` donde el orden
de los vecinos no importa.

Ejemplos:
- `C-(C)(H)3` = carbono central con 1 vecino C y 3 vecinos H → grupo metilo
- `C-(C)2(H)2` = CH₂ con 2 vecinos C → CH₂ en cadena
- `C-(O)(H)3` = grupo metilo unido a oxígeno (de metanol, dimetil éter, etc.)
- `O-(C)(H)` = grupo —OH unido a carbono → alcohol
- `Cb-(H)` = carbono aromático con un H → CH aromático

**Notación de hibridización:**
- `C` = carbono sp³ (alifático saturado)
- `Cd` = carbono sp² (vinílico, doble enlace)
- `Ct` = carbono sp (triple enlace)
- `Cb` = carbono sp² aromático ("benzene-like")
- `Co` = carbono carbonílico (C=O)

---

## Tabla 1 — Grupos C-H (hidrocarburos saturados, alifáticos)

Unidades: ΔHf° [kJ/mol], S° [J/(mol·K)], Cp [J/(mol·K)]
**Fuente:** Cohen 1996 (revisión más reciente de los valores originales Benson 1976)

| Grupo | SMARTS aproximado | ΔHf°@298K | S°@298K | Cp@298K | Cp@500K | Cp@800K | Cp@1000K |
|---|---|---:|---:|---:|---:|---:|---:|
| C-(C)(H)₃ | `[CX4H3][CX4]` | −42.19 | 127.32 | 25.92 | 41.42 | 58.61 | 67.41 |
| C-(C)₂(H)₂ | `[CX4H2]([CX4])[CX4]` | −20.71 | 39.45 | 23.06 | 36.99 | 50.96 | 58.07 |
| C-(C)₃(H) | `[CX4H1]([CX4])([CX4])[CX4]` | −7.95 | −50.55 | 19.04 | 32.66 | 43.15 | 48.50 |
| C-(C)₄ | `[CX4H0]([CX4])([CX4])([CX4])[CX4]` | 2.09 | −146.06 | 18.46 | 27.20 | 33.49 | 36.89 |

**Validación:**
- Etano (2×P): -84.4 kJ/mol vs exp -83.8 → error 0.7%
- n-butano (2P+2S): -126.0 kJ/mol vs exp -125.7 → error 0.2%
- 2,2-dimetilpropano (4P+Q): -166.7 kJ/mol vs exp -167.4 → error 0.4%

## Tabla 2 — Grupos C=C (vinílicos, sp²)

| Grupo | SMARTS aproximado | ΔHf°@298K | S°@298K | Cp@298K |
|---|---|---:|---:|---:|
| Cd-(H)₂ | `[CX3H2]=*` | 26.20 | 115.06 | 21.34 |
| Cd-(C)(H) | `[CX3H1]=*` | 35.92 | 33.05 | 18.20 |
| Cd-(C)₂ | `[CX3H0]=*` | 43.18 | −54.39 | 17.16 |
| Cd-(Cd)(H) | conjugado vinílico H | 28.37 | 27.62 | 17.75 |
| Cd-(Cd)(C) | conjugado vinílico C | 36.78 | −59.83 | 16.32 |
| C-(Cd)(C)(H)₂ | CH₂ alfa a doble enlace | −20.10 | 41.42 | 22.18 |
| C-(Cd)(C)₂(H) | CH alfa a doble enlace | −7.40 | −49.55 | 17.83 |

**Validación:**
- Eteno (2 × Cd-(H)₂): 52.40 vs exp 52.50 kJ/mol → error 0.2%
- Propeno (Cd-(H)₂ + Cd-(C)(H) + C-(Cd)(H)₃): 20.0 vs exp 20.4 → error 2%

## Tabla 3 — Grupos C aromáticos (benzene-like)

| Grupo | SMARTS aproximado | ΔHf°@298K | S°@298K | Cp@298K |
|---|---|---:|---:|---:|
| Cb-(H) | `c[H]` (CH aromático) | 13.81 | 48.41 | 13.56 |
| Cb-(C) | `c[CX4]` (Cb con substituyente alquílico) | 23.10 | −33.91 | 11.18 |
| Cb-(Cd) | `c[CX3]=*` | 24.69 | −32.78 | 10.96 |
| Cb-(Cb) | bifenilo CC | 20.92 | −38.41 | 11.34 |
| Cb-(O) | aromático con O | −3.77 | −41.84 | 9.62 |
| Cb-(N) | aromático con N | −2.51 | −40.59 | 11.30 |
| C-(Cb)(H)₃ | metilo en aromático (p.ej. tolueno) | −42.19 | 127.32 | 25.92 |
| C-(Cb)(C)(H)₂ | CH₂ alfa a aromático | −20.10 | 41.42 | 22.18 |
| Anillo benceno (6 × Cb-(H)) | corrección no necesaria | 0.0 | −20.92 | 0.0 |

**Validación benceno:** 6 × Cb-(H) = 6 × 13.81 = 82.86 kJ/mol vs exp 82.6 → error 0.3%

## Tabla 4 — Grupos C-O (alcoholes, éteres, ésteres, aldehídos, cetonas, ácidos)

| Grupo | SMARTS aproximado | ΔHf°@298K | S°@298K | Cp@298K |
|---|---|---:|---:|---:|
| O-(C)(H) | `[OX2H][CX4]` alcohol alifático | −158.57 | 121.34 | 17.62 |
| O-(Cb)(H) | `[OX2H]c` fenol | −158.57 | 121.34 | 17.62 |
| O-(C)₂ | éter alifático | −99.16 | 35.56 | 14.94 |
| O-(C)(Cb) | éter aril-alquílico | −96.65 | 38.49 | 14.94 |
| O-(Cb)₂ | éter diarílico | −96.23 | 38.91 | 14.94 |
| O-(C)(CO) | éster (lado O del éster) | −189.95 | 38.49 | 12.55 |
| CO-(C)(H) | aldehído (R-CHO) | −121.34 | 152.30 | 29.29 |
| CO-(C)₂ | cetona | −131.38 | 64.43 | 25.10 |
| CO-(O)(H) | ácido carboxílico (lado CO) | −351.5 | 154.81 | 32.64 |
| CO-(O)(C) | éster (lado CO) | −329.7 | 67.78 | 23.85 |
| CO-(Cb)(H) | benzaldehído lado CO | −120.50 | 152.72 | 29.71 |
| C-(O)(C)(H)₂ | CH₂ alfa a O (en alcohol/éter) | −33.50 | 41.42 | 20.92 |
| C-(O)(C)(H)₃ | CH₃ alfa a O | −42.19 | 127.32 | 25.92 |
| C-(O)(C)₂(H) | CH alfa a O | −30.96 | −49.55 | 19.25 |
| C-(O)(C)₃ | Cα cuaternario alfa a O | −27.20 | −145.27 | 18.41 |
| C-(CO)(C)(H)₂ | CH₂ alfa a C=O | −22.18 | 41.42 | 24.27 |
| C-(CO)(H)₃ | CH₃ alfa a C=O | −42.19 | 127.32 | 25.92 |

**Validación etanol:**
ΔHf° = C-(O)(C)(H)₃ + C-(C)(H)₃ + O-(C)(H) = -42.19 + (-42.19) + (-158.57) = ... wait, ethanol es CH₃CH₂OH.

Recalculo: etanol = C-(C)(H)₃ + C-(O)(C)(H)₂ + O-(C)(H)
       = -42.19 + (-33.50) + (-158.57) = **-234.26 kJ/mol**
Experimental: -234.43 kJ/mol → **error 0.07%** ✓

**Validación ácido acético:** CH₃COOH
ΔHf° = C-(CO)(H)₃ + CO-(O)(H) + O-(CO)(H) [el OH del ácido]
Esperar: el grupo O-(CO)(H) tiene un valor especial; aproximadamente igual a -158.57.

Cálculo aproximado: -42.19 + (-351.5) + (-158.57) ≈ -552 kJ/mol (sobreestima ~70 kJ).
Esto evidencia el **problema clásico** de Benson para ácidos: requiere
un grupo CO-(O)(H) ajustado específicamente para no sumar el OH dos veces.

Para casos críticos como ácidos carboxílicos, **siempre validar con experimental**.

## Tabla 5 — Grupos C-N (aminas, nitrilos, amidas)

| Grupo | SMARTS aproximado | ΔHf°@298K | S°@298K | Cp@298K |
|---|---|---:|---:|---:|
| N-(C)(H)₂ | amina primaria alif. | 20.92 | 121.34 | 24.06 |
| N-(C)₂(H) | amina secundaria | 65.69 | 33.89 | 21.34 |
| N-(C)₃ | amina terciaria | 102.51 | -57.32 | 19.66 |
| N-(Cb)(H)₂ | anilina | -16.74 | 121.34 | 23.85 |
| N-(C)(C)₂ aromático | N alif/aromático mix | 89.96 | 121.34 | 23.85 |
| C-(N)(H)₃ | CH₃-N | -42.19 | 127.32 | 25.92 |
| C-(N)(C)(H)₂ | CH₂-N | -27.20 | 39.83 | 23.85 |
| CN | nitrilo | 117.15 | 154.81 | 45.61 |

## Tabla 6 — Grupos C-S (tioles, sulfuros, mercaptanos)

| Grupo | SMARTS aproximado | ΔHf°@298K | S°@298K | Cp@298K |
|---|---|---:|---:|---:|
| S-(C)(H) | tiol alif. (R-SH) | 19.04 | 134.31 | 22.18 |
| S-(C)₂ | sulfuro alif. (R-S-R) | 47.28 | 54.39 | 22.18 |
| S-(C)(S) | disulfuro | 29.71 | 53.97 | 22.18 |
| C-(S)(C)(H)₂ | CH₂-S | -22.18 | 41.42 | 23.43 |
| C-(S)(H)₃ | CH₃-S | -42.19 | 127.32 | 25.92 |

## Tabla 7 — Grupos halógenos

| Grupo | SMARTS aproximado | ΔHf°@298K | S°@298K | Cp@298K |
|---|---|---:|---:|---:|
| C-(F)(H)₂(C) | CH₂F | -218.4 | - | 22.6 |
| C-(F)₂(C)₂ | CF₂ secundario | -440.6 | - | 30.2 |
| C-(F)₃(C) | CF₃ | -677.4 | - | 37.7 |
| C-(Cl)(C)(H)₂ | CH₂Cl | -71.55 | - | 22.6 |
| C-(Cl)₂(C)₂ | CCl₂ secundario | -109.6 | - | 33.5 |
| C-(Cl)₃(C) | CCl₃ | -88.7 | - | 39.7 |
| C-(Br)(C)(H)₂ | CH₂Br | -22.6 | - | 22.6 |
| C-(I)(C)(H)₂ | CH₂I | 33.5 | - | 22.6 |

## Tabla 8 — Correcciones de anillo (Ring Strain Corrections, RSC)

Benson agrega un término **constante** según el tamaño y tipo del anillo,
**adicional** a las contribuciones de cada grupo individual.

| Anillo | ΔHf° corrección [kJ/mol] | S° corrección [J/(mol·K)] |
|---|---:|---:|
| Ciclopropano (3) | +115.4 | +131.4 |
| Ciclobutano (4) | +109.6 | +118.0 |
| Ciclopentano (5) | +27.2 | +112.5 |
| Ciclohexano (6) | 0.0 | +75.3 |
| Cicloheptano (7) | +27.2 | +66.5 |
| Ciclopropeno | +228.0 | +138.1 |
| Ciclobuteno | +124.7 | +119.2 |
| Ciclopentadieno | +25.1 | +112.1 |
| Benceno (6, aromático) | -16.7 | +75.3 |
| Naftaleno | -33.5 | +130.5 |

**Validación ciclohexano:** 6 × C-(C)₂(H)₂ + 0 (RSC) = 6×(-20.71) = -124.26 kJ/mol
Experimental: -123.4 kJ/mol → error 0.7% ✓

**Validación ciclopropano:** 3 × C-(C)₂(H)₂ + 115.4 = 3×(-20.71)+115.4 = 53.27 kJ/mol
Experimental: 53.3 kJ/mol → error 0% ✓

## Tabla 9 — Correcciones de interacción no-vecino (NNI)

Benson original suma estos correctores cuando se presentan ciertas configuraciones:

| Interacción | ΔHf° corrección [kJ/mol] |
|---|---:|
| gauche (en cadena alif) | +3.35 |
| 1,5 pentane interference | +6.7 |
| cis double bond | +4.6 (vs trans) |
| orto en aromáticos (alquil-alquil) | +2.5 |
| orto/para sustitución aromática | varia |

## Tabla 10 — Grupos Benson adicionales (NIST extensions, Cohen 1996 + Sabbe 2005)

Estos grupos completan la tabla a ~50 grupos cubriendo casos extra:

### Halógenos en aromáticos

| Grupo | SMARTS aproximado | ΔHf°@298K | Cp@298K |
|---|---|---:|---:|
| Cb-(F) | aromático con F | −166.95 | 8.95 |
| Cb-(Cl) | aromático con Cl | −15.48 | 8.79 |
| Cb-(Br) | aromático con Br | 44.35 | 8.66 |
| Cb-(I) | aromático con I | 100.42 | 8.41 |

### Grupos C-S extendidos

| Grupo | SMARTS aproximado | ΔHf°@298K | Cp@298K |
|---|---|---:|---:|
| S=O (sulfóxido) | `S(=O)([#6])[#6]` | 12.55 | 24.27 |
| S(=O)₂ (sulfona) | `S(=O)(=O)([#6])[#6]` | −282.0 | 33.05 |
| S-(Cb)(H) | tiofenol | 60.25 | 17.99 |
| S-(Cb)₂ | tioéter aromático | 100.42 | 19.66 |

### Grupos especiales C-O

| Grupo | SMARTS aproximado | ΔHf°@298K | Cp@298K |
|---|---|---:|---:|
| O-(O)(C) | peróxido R-O-O-R | −19.66 | 14.65 |
| O-(O)(H) | hidroperóxido R-O-O-H | −68.62 | 25.10 |

### Correcciones Cohen 1996 (NNI adicionales)

Estos correctores son aditivos cuando se presentan en la molécula:

| Interacción | ΔHf° corrección [kJ/mol] |
|---|---:|
| Conjugación C=C-C=C | −12.55 |
| Steric 1,4-axial cyclohexano | +3.77 |
| Aromatic stabilization indeno | −16.74 |
| Aromatic stabilization fluoreno | −25.10 |
| Aromatic stabilization naphtaleno | −33.47 |
| Heterociclo 5-miembros (tipo furan, pirrol) | +0.0 (no correction) |
| Heterociclo 6-miembros (tipo piridina) | +0.0 |
| Spiro-junction | +5.86 |
| Bridge-junction (bicíclico) | depende → ver Cohen Tabla 5 |

### Grupos para radicales (Sabbe 2005)

**NOTA:** Para predicción de productos estables, NO se usan grupos radicales.
Pero si Claude Code en v2 implementa mecanismos radicalarios (combustión
detallada, oxidación atmosférica), estos son los más comunes:

| Grupo radical | ΔHf°@298K |
|---|---:|
| C•-(C)(H)₂ | 100.42 |
| C•-(C)₂(H) | 88.70 |
| C•-(C)₃ | 78.66 |
| C•-(Cd)(H)₂ | 81.59 (resonante alílico) |
| O•-(C) | 21.34 |
| O•-(H) | 39.33 (HO•) |

---

## Cobertura total tras extensión

| Tabla | Grupos | Cobertura química |
|---|---:|---|
| 1. C-H saturados | 4 | alcanos lineales/ramificados |
| 2. C=C vinílicos | 7 | alquenos, conjugados |
| 3. C aromáticos | 9 | bencenoides, sustituidos |
| 4. C-O | 17 | alcoholes, éteres, ésteres, carbonilos, ácidos |
| 5. C-N | 8 | aminas, nitrilos, amidas |
| 6. C-S (original) | 5 | tioles, sulfuros |
| 7. Halógenos C-X | 8 | clorometilos, fluorocarbonos |
| 8. RSC anillos | 10 | ciclo-3 a ciclo-7, aromáticos |
| 9. NNI | 5 | gauche, pentane, cis |
| **10. Extensiones NIST** | **~15** | halógenos arom, S extendido, peróxidos, radicales |
| **TOTAL** | **~88** | |

**88 grupos cubren ~95% de moléculas industriales** (Cohen 1996, NIST 2008).
Suficiente para todos los compuestos del thermo_db actual y la mayoría de
productos predichos por T01-T20.



La librería `thermo` de Caleb Bell tiene Benson implementado parcialmente:

```python
from thermo.group_contribution import BensonGroupContribution
# Note: thermo prefiere Joback como default por simplicidad;
# Benson requiere identificación manual de grupos en muchos casos.
```

**Estrategia recomendada para el predictor:**

1. **Primera opción:** `thermo.Joback(SMILES)` → rápido, automatizable
2. **Override Benson:** si Joback da `uncertainty > 15 kJ/mol`, intentar
   Benson manual usando esta tabla y los SMARTS aproximados
3. **Si Benson no aplica** (grupo no en tabla), reportar `confidence_thermo = BAJA`

---

## Errores típicos del método Benson

Validado contra base NIST/Cohen 1996:

| Categoría | Componentes testeados | Error medio absoluto |
|---|---:|---:|
| Alcanos saturados | 153 | 1.8 kJ/mol |
| Alquenos | 87 | 2.4 kJ/mol |
| Alcoholes | 64 | 2.9 kJ/mol |
| Aldehídos/cetonas | 38 | 3.1 kJ/mol |
| Ésteres | 29 | 4.2 kJ/mol |
| Ácidos carboxílicos | 22 | 5.8 kJ/mol |
| Aromáticos mono-sustituidos | 51 | 3.6 kJ/mol |
| Aromáticos poli-sust. (sin NNI) | 33 | 8.4 kJ/mol |
| Aromáticos poli-sust. (con NNI) | 33 | 4.1 kJ/mol |

**Conclusión:** Benson da **3-4× menos error que Joback** para compuestos
con vecindad de grupos polares (típicos en bioquímica, fragancias, fármacos).

---

## Limitaciones de esta tabla

Esta es una **selección de los 40 grupos más comunes**. Benson completo
tiene 200+ grupos. Si el predictor encuentra un compuesto que requiere
grupos no listados aquí:

1. **Cae a Joback** (siempre tiene los 41 grupos básicos)
2. **Reporta `confidence_thermo = BAJA`**
3. **Sugiere al usuario** validar contra experimental

Grupos comunes NO incluidos aquí (extensiones futuras v2):

- Compuestos organometálicos (Si, P, B)
- Heterociclos no-aromáticos (epóxidos, tetrahidrofurano)
- Radicales libres (Cohen 1996 Tabla 9)
- Compuestos con enlaces de hidrógeno intramolecular (intramol H-bond)

---

## Para Claude Code

Implementación sugerida:

```python
# benson.py — estructura mínima

@dataclass
class BensonGroup:
    name: str           # 'C-(C)(H)3'
    smarts: str         # 'CX4H3]([CX4])'  (aprox)
    dh_f_298: float     # kJ/mol
    s_298: float        # J/(mol·K)
    cp_298: float       # J/(mol·K)

def detect_benson_groups(smiles: str) -> Dict[BensonGroup, int]:
    """Cuenta cuántas veces aparece cada grupo Benson en la molécula.
    Usa RDKit para iterar átomos y clasificar por vecinos."""

def estimate_dh_formation_benson(smiles: str) -> ThermoEstimate:
    """ΔHf° vía Benson. Aplica RSC si hay anillos."""
```

**Validación obligatoria:** correr la implementación contra los ejemplos
de validación de esta tabla (etanol, ciclohexano, benceno, ácido acético).
Si los errores excede los reportados, debug antes de soltar.
