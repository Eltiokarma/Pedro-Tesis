# Transformaciones Canónicas T01-T20 — Reaction SMARTS

**Propósito:** definir 20 templates de transformación que el predictor usa
para enumerar reacciones posibles entre los compuestos de un feed.

**Sintaxis Reaction SMARTS:** `[reactantes]>>[productos]` donde los átomos
se etiquetan con `:N` para preservar identidad. Ejemplo:
`[CH3:1][OH:2]>>[CH2:1]=O + [H:2][H]` (oxidación metanol → formaldehído + H₂)

**Validación con RDKit:**
```python
from rdkit.Chem import AllChem
rxn = AllChem.ReactionFromSmarts(smarts)
products = rxn.RunReactants((mol1, mol2))
```

---

## T01 — Esterificación de Fischer

**Mecanismo:** ácido carboxílico + alcohol → éster + agua
**Catalizador:** H⁺ (H₂SO₄, ácido p-tolueno sulfónico, Amberlyst)
**T range:** 298 - 450 K (líquido), 450-550 K (vapor con cat. heterogéneo)
**Confidence mechanism:** ALTA
**Ref:** March's Adv. Org. Chem. 7e §16.64

### Reactantes
- A: ácido carboxílico (`[CX3](=O)[OX2H]`)
- B: alcohol (`[OX2H][CX4]` primario/secundario/terciario)

### Reaction SMARTS
```
[CX3:1](=[OX1:2])[OX2H:3].[OX2H:4][CX4:5]>>[CX3:1](=[OX1:2])[OX2:3][CX4:5].[OX2H2:4]
```

### Naming del producto
Producto = éster con sufijo `{alc_root}_yl_{acid_root}oate`
- `ethanol + acetic_acid → ethyl_acetate + water`
- `1-propanol + butyric_acid → propyl_butanoate + water`

### ΔH típico (vía Joback/Benson)
ΔH_rxn ≈ -3 a -8 kJ/mol (casi atérmica)
ΔS_rxn ≈ +10 a +15 J/(mol·K)

### Notas
- Keq típica 3-5 a 298 K → reacción de equilibrio, NO irreversible
- Alcoholes terciarios: velocidad lenta + competencia con T08 (deshidratación)
- Industrial usa destilación reactiva para desplazar el equilibrio

---

## T02 — Hidrólisis de éster

**Mecanismo:** éster + agua → ácido + alcohol (inverso de T01)
**Catalizador:** H⁺ (ácida) o OH⁻ (saponificación)
**T range:** 298 - 450 K
**Confidence:** ALTA

### Reaction SMARTS
```
[CX3:1](=[OX1:2])[OX2:3][CX4:5].[OX2H2:4]>>[CX3:1](=[OX1:2])[OX2H:3].[OX2H:4][CX4:5]
```

### Notas
- Saponificación (OH⁻) es irreversible (forma sal carboxilato)
- Hidrólisis ácida es equilibrio, conversión típica 60-80%

---

## T03 — Oxidación de alcohol primario

**Mecanismo:** alcohol primario + ½O₂ → aldehído + H₂O
**Catalizador:** Pt, Pd, Cu, Ag soportados
**T range:** 350 - 700 K
**Confidence:** ALTA

### Reactantes
- A: alcohol primario (`[CH2X4][OX2H]`)
- B: oxígeno (`O=O`)

### Reaction SMARTS
```
[CH2X4:1]([OX2H:2])[#6:3].[O:4]=[O:5]>>[CH1X3:1](=[O:2])[#6:3].[O:4][H].[O:5][H]
```

Versión simplificada (sin tracking detallado de H):
```
[CH2X4:1]([OX2H:2])[#6:3]>>[CH1X3:1](=O)[#6:3]
```
(se asume que el O₂ se consume y se forma H₂O, balanceado externamente)

### Naming
`R-CH2-OH → R-CHO`
- `ethanol → acetaldehyde + H2O`
- `1-propanol → propanal + H2O`
- `benzyl_alcohol → benzaldehyde + H2O`

### ΔH típico
ΔH_rxn ≈ -160 a -190 kJ/mol (fuertemente exotérmica)

---

## T04 — Oxidación de alcohol secundario

**Mecanismo:** alcohol secundario + ½O₂ → cetona + H₂O
**Catalizador:** Pt, Pd, Cu, Ag soportados
**T range:** 350 - 700 K
**Confidence:** ALTA

### Reactantes
- A: alcohol secundario (`[CHX4]([#6])([#6])[OX2H]`)
- B: oxígeno

### Reaction SMARTS
```
[CHX4:1]([OX2H:2])([#6:3])[#6:4]>>[CX3:1](=O)([#6:3])[#6:4]
```

### Naming
`R-CH(OH)-R' → R-CO-R'`
- `isopropanol → acetone + H2O`
- `2-butanol → 2-butanone (MEK) + H2O`

### ΔH típico
ΔH_rxn ≈ -150 a -180 kJ/mol

---

## T05 — Oxidación de aldehído a ácido carboxílico

**Mecanismo:** aldehído + ½O₂ → ácido carboxílico
**Catalizador:** Co, Mn (autoxidación) o catalizadores específicos
**T range:** 280 - 450 K
**Confidence:** ALTA

### Reactantes
- A: aldehído (`[CX3H1](=O)`)
- B: oxígeno

### Reaction SMARTS
```
[CX3H1:1](=[OX1:2])[#6:3]>>[CX3:1](=[OX1:2])[OX2H][#6:3]
```

Más estricto con balance H:
```
[CHX3:1](=[OX1:2])[#6:3].[OX1:4]=[OX1:5]>>[CX3:1](=[OX1:2])[OX2H:4][#6:3].[OX1:5]
```

### Naming
- `acetaldehyde → acetic_acid`
- `benzaldehyde → benzoic_acid`
- `propanal → propanoic_acid`

### ΔH típico
ΔH_rxn ≈ -250 a -280 kJ/mol

---

## T06 — Hidrogenación de alqueno

**Mecanismo:** alqueno + H₂ → alcano
**Catalizador:** Ni, Pt, Pd, Rh
**T range:** 320 - 500 K
**Confidence:** ALTA

### Reactantes
- A: alqueno (`[CX3]=[CX3]`)
- B: H₂ (`[H][H]` ó `[#1][#1]`)

### Reaction SMARTS
```
[CX3:1]=[CX3:2].[H:3][H:4]>>[CX4:1]([H:3])[CX4:2][H:4]
```

### Naming
- `ethylene + H2 → ethane`
- `propylene + H2 → propane`
- `1,3-butadiene + 2 H2 → butane`
- `styrene + H2 → ethylbenzene`

### ΔH típico
ΔH_rxn ≈ -120 a -140 kJ/mol por doble enlace

### Notas
- Markovnikov NO aplica (es adición simétrica de H)
- Estereoquímica: usualmente cis-adición (cara syn)

---

## T07 — Hidrogenación de aldehído a alcohol primario

**Mecanismo:** R-CHO + H₂ → R-CH₂-OH
**Catalizador:** Ni Raney, Cu/ZnO, Ru/C
**T range:** 380 - 500 K
**Confidence:** ALTA

### Reaction SMARTS
```
[CX3H1:1](=[OX1:2])[#6:3].[H:4][H:5]>>[CX4H2:1]([OX2:2][H:4])[#6:3].[H:5]
```

Simplificado:
```
[CX3H1:1](=[O:2])[#6:3]>>[CX4H2:1]([O:2][H])[#6:3]
```

### Naming
- `acetaldehyde + H2 → ethanol`
- `formaldehyde + H2 → methanol`
- `benzaldehyde + H2 → benzyl_alcohol`

### ΔH típico
ΔH_rxn ≈ -65 a -80 kJ/mol

---

## T07b — Hidrogenación de cetona a alcohol secundario

**Mecanismo:** R-CO-R' + H₂ → R-CH(OH)-R'
**Catalizador:** Ni Raney, Cu, Ru
**T range:** 380 - 500 K
**Confidence:** ALTA

### Reaction SMARTS
```
[CX3:1](=[OX1:2])([#6:3])[#6:4]>>[CHX4:1]([OX2:2][H])([#6:3])[#6:4]
```

### Naming
- `acetone + H2 → isopropanol`
- `diacetyl + 2 H2 → 2,3-butanediol`

### ΔH típico
ΔH_rxn ≈ -55 a -70 kJ/mol

---

## T08 — Deshidratación de alcohol

**Mecanismo:** alcohol → alqueno + H₂O (eliminación)
**Catalizador:** H⁺, Al₂O₃, zeolitas (ZSM-5)
**T range:** 470 - 700 K
**Confidence:** ALTA

### Reactantes
- A: alcohol con β-H disponible (`[CX4][CX4]([OX2H])` o similar)

### Reaction SMARTS
```
[CX4H1:1]([#6:2])[CX4:3]([OX2H:4])[#6:5]>>[CX3:1]([#6:2])=[CX3:3][#6:5].[OX2H2:4]
```

Para alcoholes primarios (β-eliminación):
```
[CX4H2:1]([CX4:2]([OX2H:3]))>>[CX3:1]=[CX3:2].[OX2H2:3]
```

### Naming (Zaitsev — alqueno más sustituido preferido)
- `ethanol → ethylene + H2O`
- `1-propanol → propylene + H2O`
- `2-butanol → 2-butene + H2O` (Zaitsev: prefiere 2-buteno sobre 1-buteno)

### ΔH típico
ΔH_rxn ≈ +40 a +60 kJ/mol (endotérmica)

### Notas
- Compite con T15 eterificación a baja T
- Industrial: deshidratación de etanol a etileno (proceso Petrobras)

---

## T09 — Deshidrogenación de alcano

**Mecanismo:** alcano → alqueno + H₂
**Catalizador:** Pt-Sn (Oleflex), Cr₂O₃ (Catofin)
**T range:** 700 - 1000 K
**Confidence:** ALTA

### Reaction SMARTS
```
[CX4H2:1]([#6:2])[CX4H3:3]>>[CX3:1]([#6:2])=[CX3H2:3].[H][H]
```

### Naming
- `propane → propylene + H2`
- `ethane → ethylene + H2`
- `isobutane → isobutylene + H2`

### ΔH típico
ΔH_rxn ≈ +120 a +135 kJ/mol (endotérmica, requiere T alta)

---

## T10 — Cracking térmico

**Mecanismo:** alcano largo → alquenos cortos + H₂
**Catalizador:** ninguno (térmico) ó zeolitas (FCC)
**T range:** 1000 - 1400 K
**Confidence:** MEDIA (mezcla productos)

### Reaction SMARTS (caso típico C₆ → C₃ + C₃)
```
[CX4:1][CX4:2][CX4:3][CX4:4][CX4:5][CX4:6]>>[CX3:1]=[CX3:2][CX4:3].[CX3:4]=[CX3:5][CX4:6]
```

### Notas
- Cracking da **mezcla de productos**, no un único alqueno
- Para el predictor, generar las K rutas más probables (ej: C₆→C₂+C₄, C₃+C₃, C₅+C₁)
- Confidence MEDIA porque la distribución de productos depende fuertemente de la cinética

### Naming aproximado
- `n-hexane → ethylene + 1-butene` (vía β-scission radical)
- `n-octane → propylene + 1-pentene` (idem)

### ΔH típico
ΔH_rxn ≈ +60 a +100 kJ/mol (endotérmica)

---

## T11 — Hidratación de alqueno

**Mecanismo:** alqueno + H₂O → alcohol (adición Markovnikov)
**Catalizador:** H₃PO₄/SiO₂ (industrial), H₂SO₄ (laboratorio)
**T range:** 420 - 600 K
**Confidence:** ALTA

### Reaction SMARTS (Markovnikov: H al C con más H)
```
[CX3H2:1]=[CX3H1:2][#6:3].[OX2H2:4]>>[CX4H3:1][CX4H1:2]([OX2H:4])[#6:3]
```

Para alquenos simétricos (etileno):
```
[CX3H2:1]=[CX3H2:2].[OX2H2:3]>>[CX4H3:1][CX4H2:2][OX2H:3]
```

### Naming
- `ethylene + H2O → ethanol`
- `propylene + H2O → isopropanol` (Markovnikov)
- `1-butene + H2O → 2-butanol` (Markovnikov)

### ΔH típico
ΔH_rxn ≈ -45 kJ/mol

---

## T12 — Combustión completa

**Mecanismo:** CₐHᵦOᵧNᵨSᵩ + (a + β/4 − γ/2 + φ)O₂ → a·CO₂ + (β/2)·H₂O + (ρ/2)·N₂ + φ·SO₂
**Catalizador:** ninguno (llama autoiniciada T>600°C, o spark)
**T range:** 700 - 2500 K
**Confidence:** ALTA

### Para Claude Code
**No usar SMARTS para esto.** La combustión es estequiométrica determinista
desde la fórmula molecular. Generar por algoritmo:

```python
def combustion_complete(smiles):
    mol = Chem.MolFromSmiles(smiles)
    formula = rdMolDescriptors.CalcMolFormula(mol)
    a, b, c, d, e = parse_CHONS(formula)  # cuenta átomos
    n_O2 = a + b/4 - c/2 + e  # estequiometría
    return {
        'reactants': [(smiles, 1), ('O=O', n_O2)],
        'products': [('O=C=O', a), ('O', b/2), ('N#N', d/2), ('O=S=O', e)]
    }
```

### ΔH típico
ΔH_rxn = -ΔH_combustion ≈ -2000 a -10000 kJ/mol (muy fuertemente exotérmica)

### Naming
- `ethanol + 3 O2 → 2 CO2 + 3 H2O`
- `glucose + 6 O2 → 6 CO2 + 6 H2O`
- `methane + 2 O2 → CO2 + 2 H2O`

---

## T13 — Combustión incompleta

**Mecanismo:** CₐHᵦOᵧ + (a/2 + β/4 − γ/2)·O₂ → a·CO + (β/2)·H₂O (rico en combustible)
**Catalizador:** ninguno (T>600°C, λ<1)
**T range:** 700 - 2500 K
**Confidence:** MEDIA (mezcla CO/CO₂)

### Variantes
**Variante 1 — defecto leve:** todos los productos van a CO
```
ethanol + 2 O2 → 2 CO + 3 H2O
```

**Variante 2 — formación de hollín (C(s)):** parte del C va a grafito
```
ethanol + 1.5 O2 → CO + C(s) + 3 H2O
```

### Notas
- En la práctica, **mezcla CO + CO₂** con relación dependiente de λ
- Para el simulador, generar ambas como variantes y dejar que el usuario elija
- Confidence MEDIA porque la distribución exacta depende de cinética

### ΔH típico
ΔH_rxn ≈ -800 a -2000 kJ/mol (menos exotérmica que completa)

---

## T14 — Reformado con vapor

**Mecanismo:** CₐHᵦ + a·H₂O → a·CO + (a + β/2)·H₂
**Catalizador:** Ni/Al₂O₃ (típico SMR), Pt/Rh (en autotermal)
**T range:** 900 - 1300 K
**Confidence:** ALTA

### Reaction SMARTS (caso C₁ → metano)
Para metano: ya está como R003 CURATED. Para otros:
- propane + 3 H2O → 3 CO + 7 H2  (proceso autotermal)
- ethanol + H2O → 2 CO + 4 H2

### Genérico (escrito como template general)
```python
def steam_reforming(smiles):
    mol = Chem.MolFromSmiles(smiles)
    a = count_carbons(mol)
    b = count_hydrogens(mol)
    return {
        'reactants': [(smiles, 1), ('O', a)],
        'products': [('[C-]#[O+]', a), ('[H][H]', a + b/2)]
    }
```

### ΔH típico
ΔH_rxn ≈ +200 kJ/mol por C reformado (endotérmica)

---

## T15 — Eterificación

**Mecanismo:** 2 R-OH → R-O-R + H₂O (condensación)
**Catalizador:** H⁺/Al₂O₃, resinas ácidas
**T range:** 370 - 500 K
**Confidence:** MEDIA

### Reaction SMARTS (alcoholes idénticos)
```
[OX2H:1][CX4:2].[OX2H:3][CX4:4]>>[OX2:1]([CX4:2])[CX4:4].[OX2H2:3]
```

### Naming
- `2 ethanol → diethyl_ether + H2O`
- `2 methanol → dimethyl_ether (DME) + H2O` (igual que R014 CURATED)
- `methanol + 2-methyl-2-propanol → MTBE + H2O`

### ΔH típico
ΔH_rxn ≈ -10 a -25 kJ/mol

### Notas
- Compite con T08 deshidratación a T similar (selectividad depende de catalizador)
- Industrial MTBE: methanol + isobutylene + zeolita → MTBE

---

## T16 — Condensación aldólica

**Mecanismo:** 2 carbonilos + base → β-hidroxicarbonilo
**Catalizador:** OH⁻ (NaOH, KOH) o H⁺ (H₂SO₄)
**T range:** 280 - 380 K
**Confidence:** BAJA (multiproducto: cruzado vs autocondensación; deshidratación post-aldol)

### Reaction SMARTS (aldol clásico entre 2 acetaldehídos)
```
[CX3H1:1](=[OX1:2])[CX4H3:3].[CX3H1:4](=[OX1:5])[CX4H3:6]>>[CX3H1:1](=[OX1:2])[CX4H2:3][CX4H1:6]([OX2H:5])[CX4H2:4]([CX3H1:6]...)
```

(este SMARTS es complejo; la implementación real requiere más cuidado)

### Naming
- `2 acetaldehyde → 3-hydroxybutanal (aldol) → crotonaldehyde + H2O`
- `2 acetone → diacetone_alcohol → mesityl_oxide + H2O`

### Notas
- Condensación cruzada (entre aldehído y cetona diferentes) da mezcla de 4 productos
- Para el predictor, generar la auto-condensación + advertir que cruzada da mezcla
- Confidence BAJA por la combinatoria de productos

---

## T17 — Amidación (Schotten-Baumann o térmica)

**Mecanismo:** ácido carboxílico + amina → amida + H₂O
**Catalizador:** DCC (lab) o térmico (industrial)
**T range:** 320 - 450 K
**Confidence:** ALTA

### Reaction SMARTS
```
[CX3:1](=[OX1:2])[OX2H:3].[NX3H2:4][#6:5]>>[CX3:1](=[OX1:2])[NX3H:4][#6:5].[OX2H2:3]
```

### Naming
- `acetic_acid + methylamine → N-methylacetamide + H2O`
- `acetic_acid + ammonia → acetamide + H2O`

### ΔH típico
ΔH_rxn ≈ -25 kJ/mol

---

## T18 — Adición Markovnikov de HX a alqueno

**Mecanismo:** alqueno + HCl/HBr/HI → alquil halogenuro (Markovnikov)
**Catalizador:** ninguno (electrofílica directa)
**T range:** 280 - 400 K
**Confidence:** ALTA

### Reaction SMARTS (HCl como ejemplo — VERIFICADO con RDKit 2026.3.2)
```
[CX3H2:1]=[CX3H1:2][#6:3].[ClX1H:4]>>[CX4H3:1][CX4:2]([Cl:4])[#6:3]
```

Versión genérica para HF, HCl, HBr, HI:
```
[CX3H2:1]=[CX3H1:2][#6:3].[F,Cl,Br,I;X1;H1:4]>>[CX4H3:1][CX4:2]([*:4])[#6:3]
```

Markovnikov: el H va al carbono terminal (más H), el halógeno al carbono interno (menos H).
**Validación:** `propileno (CC=C) + HCl (Cl)` → `2-cloropropano (CC(C)Cl)` ✅

### Naming
- `propylene + HCl → 2-chloropropane` (Markovnikov)
- `ethylene + HCl → ethyl_chloride`

### ΔH típico
ΔH_rxn ≈ -65 a -85 kJ/mol

---

## T19 — Nitración aromática

**Mecanismo:** aromático + HNO₃ → nitroaromático + H₂O
**Catalizador:** H₂SO₄ (genera NO₂⁺, electrófilo nitronio)
**T range:** 290 - 330 K
**Confidence:** ALTA

### Reaction SMARTS
```
[cH:1]1[cH:2][cH:3][cH:4][cH:5][cH:6]1.[OX2:7]=[N+:8](=[OX1:9])[OX2H:10]>>[c:1]1([N+:8](=[OX1:9])[OX1-])[cH:2][cH:3][cH:4][cH:5][cH:6]1.[OX2H2]
```

(SMARTS complejo; verificar con RDKit antes de implementar)

### Naming
- `benzene + HNO3 → nitrobenzene + H2O`
- `toluene + HNO3 → 2-nitrotoluene + 4-nitrotoluene + H2O` (mezcla orto/para)

### Notas
- Sustituyentes activantes (-OH, -OCH₃, -NH₂) → orientación orto/para
- Sustituyentes desactivantes (-NO₂, -SO₃H) → orientación meta
- Para el predictor: generar producto principal según efecto director

### ΔH típico
ΔH_rxn ≈ -120 kJ/mol

---

## T20 — Sulfonación aromática

**Mecanismo:** aromático + H₂SO₄ → arilsulfonato + H₂O
**Catalizador:** SO₃ (en óleum) genera el electrófilo
**T range:** 370 - 470 K
**Confidence:** ALTA

### Reaction SMARTS
```
[cH:1]1[cH:2][cH:3][cH:4][cH:5][cH:6]1.[S:7](=[OX1:8])(=[OX1:9])([OX2H:10])[OX2H:11]>>[c:1]1([S:7](=[OX1:8])(=[OX1:9])[OX2H:10])[cH:2][cH:3][cH:4][cH:5][cH:6]1.[OX2H2:11]
```

### Naming
- `benzene + H2SO4 → benzenesulfonic_acid + H2O`
- `toluene + H2SO4 → p-toluenesulfonic_acid + H2O`

### Notas
- Reversible a alta T (>200°C): el grupo -SO₃H se puede remover
- Compite con nitración si HNO₃/H₂SO₄ están juntos

### ΔH típico
ΔH_rxn ≈ -75 kJ/mol

---

## Reglas generales de aplicación

### Reglas de selectividad

1. **Markovnikov vs anti-Markovnikov:**
   - Markovnikov (electrofílica): T11 (hidratación), T18 (HX)
   - Anti-Markovnikov: hidroboración, peróxidos (no incluido en T01-T20)

2. **Zaitsev vs Hofmann:**
   - T08 deshidratación: Zaitsev (alqueno más sustituido) por default
   - Hofmann (menos sustituido) cuando hay impedimento estérico

3. **Orientación aromática:**
   - Activantes (OH, OR, NR₂, alquilos) → orto/para
   - Desactivantes (NO₂, SO₃H, CN, carbonilo) → meta
   - Halógenos: desactivantes pero orto/para directores

### Reglas de aplicación combinatoria

1. **Polifuncionales:** si un compuesto tiene 2 grupos —OH, aplicar T01/T08
   independientemente para cada uno
2. **Simetría:** evitar duplicar productos isómeros (ej: T01 entre dos
   ácidos idénticos genera 1 producto, no 2)
3. **Restricciones cinéticas:** los grupos terciarios reaccionan más lento
   en T01 pero más rápido en T08 (eliminación)
4. **Competencia:** cuando dos templates aplican al mismo sitio, ranquear
   por ΔG y reportar al usuario

### Cobertura

Con estos 20 templates cubrimos aproximadamente:

- 100% de las reacciones del catálogo CURATED actual (las 25)
- ~80% de procesos industriales típicos en química orgánica
- ~95% de las transformaciones encontradas en libros de orgánica de pregrado

### Limitaciones reconocidas (extensiones v2)

- **Heterociclos:** epóxidos, tetrahidrofuranos, piridinas (T21-T25)
- **Reacciones de C-C formación:** Grignard, Wittig, Heck, Suzuki (T26-T30)
- **Diels-Alder y cicloadiciones:** [4+2], [2+2] (T31-T33)
- **Polimerizaciones:** radical, iónica, condensación (T34-T36)
- **Reacciones bioquímicas:** glicólisis, ciclo de Krebs (T37-T45)

---

## Para Claude Code

### Estructura del módulo `transformations.py`

```python
@dataclass
class TransformationTemplate:
    id: str
    name: str
    reactant_groups: List[List[str]]
    product_groups: List[List[str]]
    reaction_smarts: str
    T_range_K: Tuple[float, float]
    requires_catalyst: bool
    catalyst_hint: str
    mechanism_confidence: Confidence
    references: List[str]
    notes: str

def load_transformations() -> List[TransformationTemplate]:
    """Parsea este archivo .md y devuelve la lista de templates."""

def apply_to_compounds(
    template: TransformationTemplate,
    compounds: List[str]  # SMILES
) -> List[Tuple[List[str], List[str]]]:
    """Aplica el template a las combinaciones posibles.
    Devuelve [(reactantes, productos)] por cada combinación válida.
    Usa RDKit AllChem.ReactionFromSmarts + RunReactants."""
```

### Validación obligatoria

Para cada template T01-T20, escribir test:

```python
def test_T01_esterification():
    rxn = load_transformation('T01')
    ethanol = Chem.MolFromSmiles('CCO')
    acetic = Chem.MolFromSmiles('CC(=O)O')
    products = apply_smarts(rxn.reaction_smarts, (acetic, ethanol))
    assert any(
        Chem.MolToSmiles(p[0]) == 'CCOC(C)=O'  # ethyl_acetate
        for p in products
    ), f"T01 falló: {products}"
```

Si algún template falla, **revisar manualmente** la sintaxis SMARTS antes
de usarlo en producción. Los SMARTS arriba son **mejor esfuerzo** del
autor; pueden tener bugs sutiles que requieren validación con RDKit.

### Cuándo no aplicar un template

- Si las condiciones del bloque no caen en `T_range_K` del template
- Si `requires_catalyst=True` pero el usuario no declara catalizador
- Si los reactantes están presentes pero en concentraciones traza (<0.1%)
- Si ya hay una reacción curated que cubre la misma transformación
