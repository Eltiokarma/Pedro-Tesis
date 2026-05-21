# Arquitectura del Predictor de Reacciones — Capa 4b
## **Versión 2.0 — HÍBRIDA**

**Documento técnico para implementación**
**Versión:** 2.0 (actualiza v1.0 con decisión híbrida `thermo` + tablas .md)
**Fecha:** 2026-05-20
**Audiencia:** Claude Code (otra sesión) — implementación directa

---

## 0. Cambios respecto a v1.0

Esta versión incorpora la decisión D12 tomada al final de la discusión:
**arquitectura híbrida con librería `thermo` como backend + tablas `.md`
para trazabilidad**.

Cambios clave:
- Agregada dependencia `thermo` (incluye RDKit, OPSIN, Joback, Benson)
- Las tablas Joback/Benson se cargan desde `.md` para auditoría manual
- Validación cruzada: cada cálculo se hace con `thermo` Y se compara contra
  la tabla `.md` (debe coincidir dentro de tolerancia numérica)
- SMILES no se buscan en runtime: están todos en `smiles_compounds_db.md`
- Templates de reacciones se cargan desde `transformations_db.md`

---

## 1. Stack tecnológico

### Dependencias nuevas

```
# requirements_predictor.txt
thermo>=0.4.0          # Caleb Bell's thermo library (incluye Joback, group contrib)
rdkit-pypi>=2023.3.1   # cheminformática (SMARTS, reaction SMARTS)
chemicals>=1.1.0       # base de propiedades (NIST data)
```

Total: ~250 MB instalado. Las tres están en pip.

### Verificación de instalación

```python
def verify_dependencies():
    """Test al iniciar el predictor. Si falta algo, mensaje claro al user."""
    missing = []
    try:
        import thermo
        from thermo.group_contribution.joback import Joback
    except ImportError:
        missing.append('thermo')
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
    except ImportError:
        missing.append('rdkit-pypi')
    if missing:
        raise ImportError(
            f"El predictor requiere: {missing}\n"
            f"Instalar con: pip install {' '.join(missing)}\n"
            f"El simulador funciona sin estas dependencias, pero el predictor estará deshabilitado."
        )
```

---

## 2. Archivos del paquete

### 2.1 Estructura final

```
chemfx/                                       # paquete nuevo
├── __init__.py
│
├── predictor/
│   ├── __init__.py
│   ├── functional_groups.py                 # detector con thermo + RDKit
│   ├── transformations.py                   # carga desde transformations_db.md
│   ├── thermo_estimator.py                  # fachada que usa thermo.Joback / thermo.Benson
│   ├── product_builder.py                   # apply_transformation con RDKit RxnSmarts
│   ├── iupac_namer.py                       # smiles → IUPAC (intenta OPSIN, fallback templates)
│   ├── reaction_predictor.py                # API: predict_reactions(feed, T, P, τ)
│   ├── plausibility_filter.py               # filtros (rango T, balance, etc.)
│   ├── confidence_tagger.py                 # ALTA/MEDIA/BAJA
│   ├── validation.py                        # test contra tablas .md
│   └── types.py                             # dataclasses
│
├── auto_reactions/
│   ├── __init__.py
│   ├── combustion_complete.py
│   ├── combustion_incomplete.py
│   ├── thermal_cracking.py
│   └── generator.py
│
├── reactivity_engine/
│   ├── __init__.py
│   ├── equipment_reactivity.py
│   ├── stream_kinetics.py
│   ├── danger_detector.py
│   ├── assistant.py
│   └── defaults.py                          # ALLOW_REACTIONS_DEFAULTS
│
└── data/                                    # tablas .md, ya generadas
    ├── joback_groups.md                     # ✅ ENTREGADO
    ├── benson_groups.md                     # ✅ ENTREGADO
    ├── smiles_compounds_db.md               # ✅ ENTREGADO (~87 verificados)
    ├── transformations_db.md                # ✅ ENTREGADO (20 templates)
    ├── functional_groups_db.md              # generado por Claude Code (corre 1 vez)
    ├── predicted_compounds_db.md            # cache, vacío al inicio
    └── auto_reactions_db.md                 # generado, ~300 reacciones AUTO
```

### 2.2 Archivos provistos por este documento

Los 4 archivos `.md` siguientes ya están disponibles y deben copiarse al
directorio `chemfx/data/`:

1. **`joback_groups.md`** — Tabla Joback completa (41 grupos)
2. **`benson_groups.md`** — Tabla Benson (40 grupos principales)
3. **`smiles_compounds_db.md`** — SMILES de los 108 compuestos del thermo_db
4. **`transformations_db.md`** — Templates T01-T20 con reaction SMARTS

### 2.3 Archivos a modificar (mínimo invasivo)

```python
# thermo_db.py — agregar 2 campos a ComponentThermo
@dataclass
class ComponentThermo:
    # ... existentes ...
    smiles: str = ''                          # nuevo
    functional_groups: List[str] = field(default_factory=list)  # nuevo
    origin: str = 'experimental'              # nuevo: 'experimental'|'estimated'|'predicted'
    estimation_uncertainty: Dict = field(default_factory=dict)  # nuevo

# reactions_db.py — agregar 4 campos a Reaction
@dataclass
class Reaction:
    # ... existentes ...
    origin: str = 'curated'                   # nuevo: 'curated'|'auto'|'predicted'
    confidence_mechanism: str = 'alta'        # nuevo
    confidence_thermo: str = 'alta'           # nuevo
    transformation_id: Optional[str] = None   # nuevo

# flowsheet_model.py — agregar campos a Block y Stream
@dataclass
class Block:
    # ... existentes ...
    allow_reactions: bool = False             # default según tipo
    active_reactions: List[str] = field(default_factory=list)
    reaction_warnings: List[dict] = field(default_factory=list)

@dataclass
class Stream:
    # ... existentes ...
    allow_reactions: bool = False
    residence_time_s: Optional[float] = None
    active_reactions: List[str] = field(default_factory=list)
    reaction_warnings: List[dict] = field(default_factory=list)
    pipe_length_m: float = 0.0                # para calcular τ
    pipe_diameter_m: float = 0.0
```

---

## 3. Implementación: fases revisadas

### Fase 0 — Setup (½ día)

**Acciones:**
1. `pip install thermo rdkit-pypi chemicals` (o equivalente conda)
2. Crear `chemfx/` con subdirectorios
3. Copiar los 4 archivos `.md` a `chemfx/data/`
4. Crear `chemfx/__init__.py` con `verify_dependencies()` al import

**Test de aceptación:**
```python
import chemfx
from chemfx.predictor import functional_groups, thermo_estimator
# No debe lanzar excepciones
```

### Fase 1 — Detección de grupos funcionales (1 día) ⬇️ tiempo reducido

**Razón del recorte:** ya tenemos SMILES en `smiles_compounds_db.md`, solo
queda implementar el detector usando RDKit.

**Archivos a crear:**
- `chemfx/predictor/functional_groups.py`
- `chemfx/predictor/types.py`
- `chemfx/data/functional_groups_db.md` (generado por script una vez)

**Implementación:**

```python
# functional_groups.py

from rdkit import Chem

# SMARTS canónicos para grupos funcionales (más simples que Joback porque
# acá queremos identificar para reacciones, no estimar)
GROUP_SMARTS = {
    'alcohol_primario':    '[CX4H2][OX2H]',
    'alcohol_secundario':  '[CX4H1]([#6])[OX2H]',
    'alcohol_terciario':   '[CX4H0]([#6])([#6])[OX2H]',
    'alcohol_aromatico':   '[c][OX2H]',
    'acido_carboxilico':   '[CX3](=O)[OX2H]',
    'ester':               '[CX3](=O)[OX2][#6]',
    'aldehido':            '[CX3H1](=O)',
    'cetona':              '[CX3H0](=O)([#6])[#6]',
    'eter':                '[OX2]([#6])[#6]',
    'amina_primaria':      '[NX3H2][#6]',
    'amina_secundaria':    '[NX3H1]([#6])[#6]',
    'amina_terciaria':     '[NX3H0]([#6])([#6])[#6]',
    'amida':               '[CX3](=O)[NX3]',
    'alqueno':             '[CX3]=[CX3]',
    'alquino':             '[CX2]#[CX2]',
    'aromatico':           'c1ccccc1',
    'nitro':               '[N+](=O)[O-]',
    'nitrilo':             '[CX2]#N',
    'halogenuro':          '[F,Cl,Br,I][#6]',
    'tiol':                '[SX2H]',
    'sulfuro':             '[#6][SX2][#6]',
    'hemiacetal':          '[CX4]([OX2H])[OX2][#6]',
    'acetal':              '[CX4]([OX2][#6])[OX2][#6]',
}

def detect_groups(smiles: str) -> List[FunctionalGroup]:
    """Detecta grupos funcionales en una molécula desde su SMILES."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return []

    detected = []
    for group_name, smarts in GROUP_SMARTS.items():
        pattern = Chem.MolFromSmarts(smarts)
        matches = mol.GetSubstructMatches(pattern)
        if matches:
            detected.append(FunctionalGroup(
                name=group_name,
                smarts=smarts,
                count=len(matches),
                atoms_match=matches[0]  # primer match
            ))
    return detected
```

**Test de aceptación:**
```python
def test_detect_groups():
    assert any(g.name == 'alcohol_primario' for g in detect_groups('CCO'))  # ethanol
    assert any(g.name == 'alcohol_aromatico' for g in detect_groups('Oc1ccccc1'))  # phenol
    assert any(g.name == 'acido_carboxilico' for g in detect_groups('CC(=O)O'))  # acetic
    glucose = detect_groups('OCC1OC(O)C(O)C(O)C1O')
    assert sum(g.count for g in glucose if 'alcohol' in g.name) >= 4  # 5 -OH
```

### Fase 2 — Joback estimator vía `thermo` (½ día) ⬇️ tiempo reducido

**Razón del recorte:** `thermo.Joback` ya está implementado. Solo armamos
fachada y validamos contra tabla `.md`.

**Archivos a crear:**
- `chemfx/predictor/thermo_estimator.py`
- `chemfx/predictor/joback_wrapper.py`

**Implementación:**

```python
# joback_wrapper.py

from thermo.group_contribution.joback import Joback
from .types import ThermoEstimate, Confidence

def estimate_via_joback(smiles: str) -> Dict[str, ThermoEstimate]:
    """Estima propiedades vía Joback usando `thermo` library."""
    try:
        J = Joback(smiles)
        if J.status != 'OK':
            return None
    except Exception:
        return None

    return {
        'dh_f_298_kJ_mol': ThermoEstimate(
            value=J.Hf() / 1000,  # thermo devuelve J/mol, convertir
            uncertainty=_estimate_joback_error(J),
            method='joback (thermo lib)',
            confidence=Confidence.MEDIA
        ),
        'tb_K': ThermoEstimate(
            value=J.Tb(),
            uncertainty=12.9,
            method='joback',
            confidence=Confidence.MEDIA
        ),
        'tc_K': ThermoEstimate(
            value=J.Tc(),
            uncertainty=J.Tc() * 0.048,  # 4.8% error medio
            method='joback',
            confidence=Confidence.MEDIA
        ),
        'cp_298': ThermoEstimate(
            value=J.Cpig(298.15),
            uncertainty=J.Cpig(298.15) * 0.014,  # 1.4% error
            method='joback',
            confidence=Confidence.ALTA
        ),
        # ...
    }

def _estimate_joback_error(J: Joback) -> float:
    """Estima error según número de grupos identificados."""
    n_groups = len(J.counts)
    if n_groups <= 2:
        return 5.0   # kJ/mol - molécula simple
    elif n_groups <= 5:
        return 12.0  # típico
    else:
        return 25.0  # polifuncional
```

**Validación contra tabla `.md`:**

```python
def validate_joback_against_md():
    """Para cada grupo en joback_groups.md, verificar que thermo.Joback
    da el mismo valor de ΔHf°. Tolerancia: 0.1 kJ/mol."""
    table = load_md_table('chemfx/data/joback_groups.md')
    from thermo.group_contribution.joback import J_BIGGS_JOBACK_SMARTS_id_dict

    for group_name, expected in table.items():
        # buscar el grupo en thermo
        ...

    # Test sencillo: ΔHf° de etanol
    J = Joback('CCO')
    expected = -42.19 + (-20.64) + (-208.04) + 68.29  # = -202.58
    assert abs(J.Hf()/1000 - expected) < 0.5  # kJ/mol
```

### Fase 3 — Benson (1 día) — opcional según tiempo

Implementación más simple porque Benson en `thermo` no está completo:
implementamos nuestra propia versión leyendo `benson_groups.md`.

```python
# benson.py

def estimate_via_benson(smiles: str) -> Optional[ThermoEstimate]:
    """Benson como override cuando Joback da error alto.
    Requiere identificar grupos con SMARTS específicos de Benson."""
    groups = detect_benson_groups(smiles)
    if not groups:
        return None

    table = load_benson_table()
    dh_f = sum(count * table[g]['dh_f'] for g, count in groups.items())
    dh_f += apply_ring_strain_corrections(smiles, table)
    dh_f += apply_NNI_corrections(smiles, table)

    return ThermoEstimate(
        value=dh_f,
        uncertainty=_benson_error(groups),
        method='benson',
        confidence=Confidence.ALTA if _benson_error(groups) < 10 else Confidence.MEDIA
    )
```

### Fase 4 — Templates T01-T20 (2 días) ⬇️ tiempo reducido

**Razón del recorte:** ya tenemos los 20 reaction SMARTS escritos en
`transformations_db.md`. Solo queda parsearlos y aplicarlos con RDKit.

**Test crítico:**
```python
def test_all_templates_with_rdkit():
    """Cada template debe poder cargarse en RDKit y aplicarse a casos test."""
    from rdkit.Chem import AllChem

    for template in load_transformations():
        rxn = AllChem.ReactionFromSmarts(template.reaction_smarts)
        assert rxn is not None, f"Template {template.id} no parsea"
        assert rxn.GetNumReactantTemplates() > 0
        assert rxn.GetNumProductTemplates() > 0

    # Tests específicos por template
    test_T01_esterification()
    test_T03_oxidation_primary()
    test_T06_hydrogenation()
    # ... etc
```

**Si algún template falla en RDKit**, parar y reportar al usuario humano.
Los SMARTS de `transformations_db.md` son "mejor esfuerzo" del autor y
pueden tener bugs sutiles.

### Fase 5-9 — Sin cambios significativos respecto a v1.0

(predict_reactions API, generador AUTO, reactivity engine, UI, QA)

Tiempos estimados: **5-6 días total** restantes (vs 9 días en v1.0).

---

## 4. Validación cruzada: thermo vs tablas .md

Este es el componente clave de la arquitectura híbrida.

### Concepto

Cada vez que el predictor usa `thermo.Joback` para estimar, ANTES de
devolver el resultado, verifica que coincide con lo que daría la tabla
`.md`. Si discrepan más allá de tolerancia, **lanza un warning** y
reporta cuál método se está usando.

```python
def cross_validate(smiles: str, property: str) -> ThermoEstimate:
    """Estima con thermo Y con tabla .md, compara, reporta el método principal."""
    via_thermo = estimate_via_joback(smiles)
    via_md = estimate_via_md_table(smiles)

    if via_thermo and via_md:
        diff = abs(via_thermo[property].value - via_md[property].value)
        if diff > 0.5:  # tolerancia kJ/mol
            logger.warning(
                f"Discrepancia {property} para {smiles}: "
                f"thermo={via_thermo[property].value:.2f}, "
                f"md_table={via_md[property].value:.2f}, "
                f"diff={diff:.2f} kJ/mol"
            )
        # devolver thermo como primario (es el oficial)
        return via_thermo[property]

    return via_thermo or via_md  # cualquiera que funcione
```

### Casos esperados de discrepancia

Estos son **esperados** y no son bugs:

1. **Errores de redondeo:** thermo usa más decimales internos
2. **Grupos ambiguos:** algunos grupos Joback se identifican distinto en
   thermo vs nuestra tabla (ej: ring vs non-ring para anillos pequeños)
3. **Implementación de extensiones:** thermo a veces usa Joback-extendido
   (Diky-Joback) en lugar del original

Si la discrepancia es < 5 kJ/mol, **continuar normalmente**.
Si es > 10 kJ/mol, **investigar manualmente** antes del próximo release.

---

## 5. Tabla Joback en runtime

La tabla `.md` se carga **una vez** al iniciar y se cachea:

```python
# joback_table_loader.py

_JOBACK_TABLE_CACHE = None

def load_joback_table() -> Dict[str, dict]:
    """Parsea joback_groups.md y devuelve dict {grupo: {prop: valor, ...}}."""
    global _JOBACK_TABLE_CACHE
    if _JOBACK_TABLE_CACHE is not None:
        return _JOBACK_TABLE_CACHE

    md_path = Path(__file__).parent.parent / 'data' / 'joback_groups.md'
    table = parse_markdown_tables(md_path)

    _JOBACK_TABLE_CACHE = {}
    for group_name, row in table.items():
        _JOBACK_TABLE_CACHE[group_name] = {
            'smarts': row['SMARTS'],
            'dTc': row['ΔTc'],
            'dPc': row['ΔPc'],
            'dHf': row['ΔHform'],
            'dGf': row['ΔGform'],
            'Cp_a': row['Cp_a'],
            'Cp_b': row['Cp_b'],
            'Cp_c': row['Cp_c'],
            'Cp_d': row['Cp_d'],
            # ...
        }
    return _JOBACK_TABLE_CACHE
```

### Detección de grupos Joback (fallback sin `thermo`)

```python
def fragment_joback_manual(smiles: str) -> Dict[str, int]:
    """Identifica grupos Joback en un SMILES usando RDKit + SMARTS de la tabla.
    Devuelve {group_name: count}.

    Usado como fallback si `thermo` no está disponible o si queremos
    auditoría manual de qué grupos identificó.
    """
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return {}

    table = load_joback_table()
    counts = {}
    for group_name, row in table.items():
        pattern = Chem.MolFromSmarts(row['smarts'])
        if pattern:
            matches = mol.GetSubstructMatches(pattern)
            if matches:
                counts[group_name] = len(matches)
    return counts
```

### Test de coherencia

```python
def test_joback_table_self_consistency():
    """Para varios compuestos conocidos, comparar:
    - thermo.Joback (oficial)
    - fragment_joback_manual + suma desde tabla .md
    Deben dar valores cercanos."""

    for smiles, expected_dHf in [
        ('CCO', -234.4),      # ethanol exp
        ('CC(C)=O', -217.1),  # acetone exp
        ('c1ccccc1', 82.6),   # benzene exp
    ]:
        # Vía thermo
        J = Joback(smiles)
        dHf_thermo = J.Hf() / 1000

        # Vía tabla manual
        groups = fragment_joback_manual(smiles)
        table = load_joback_table()
        dHf_manual = 68.29 + sum(table[g]['dHf'] * c for g, c in groups.items())

        assert abs(dHf_thermo - dHf_manual) < 1.0, \
            f"{smiles}: thermo={dHf_thermo}, manual={dHf_manual}"
```

---

## 6. SMILES en runtime

`smiles_compounds_db.md` se parsea una vez al inicio. Para cada compuesto
del thermo_db, se busca su SMILES.

```python
# smiles_loader.py

_SMILES_CACHE = None

def load_smiles_db() -> Dict[str, dict]:
    """Devuelve {compound_name: {'smiles': str, 'cas': str, 'verified': bool}}."""
    global _SMILES_CACHE
    if _SMILES_CACHE is not None:
        return _SMILES_CACHE
    # ... parse markdown ...

def get_smiles(thermo_name: str) -> Optional[str]:
    """SMILES canónico de un compuesto, o None si no está mapeado."""
    db = load_smiles_db()
    entry = db.get(thermo_name)
    return entry['smiles'] if entry else None

def get_unmapped() -> List[str]:
    """Compuestos del thermo_db que NO tienen SMILES.
    Para reporte al usuario."""
    thermo_compounds = set(thermo_db.list_names())
    smiles_compounds = set(load_smiles_db().keys())
    return sorted(thermo_compounds - smiles_compounds)
```

### Compuestos sin SMILES

Si un compuesto está en thermo_db pero no en smiles_db, el predictor:

1. **No puede determinar grupos funcionales** → no genera predicciones
2. **Trata el compuesto como inerte** en cualquier reacción
3. **Reporta en `unmapped_compounds`** al final de cada predicción
4. **Sugiere al usuario** agregar el SMILES manualmente

```python
result = predict_reactions(feed=['ethanol', 'unknown_compound'], T=350, P=1.0)
# result.unmapped_compounds == ['unknown_compound']
# result.predicted contiene solo reacciones que involucren ethanol
```

---

## 7. Plan revisado de implementación

### Resumen de tiempos

| Fase | Original v1.0 | Revisado v2.0 | Razón del cambio |
|---|---:|---:|---|
| 0. Setup | ½ día | ½ día | Sin cambio |
| 1. Grupos funcionales | 1.5 día | **1 día** | SMILES ya provistos |
| 2. Joback | 1 día | **½ día** | thermo lo tiene |
| 3. Benson | 1 día | 1 día | thermo no lo tiene, implementamos |
| 4. Templates T01-T20 | 3 días | **2 días** | SMARTS ya escritos |
| 5. predict_reactions API | 2 días | 2 días | Sin cambio |
| 6. AUTO reactions | 1.5 día | 1.5 día | Sin cambio |
| 7. Reactivity engine | 2 días | 2 días | Sin cambio |
| 8. UI | 1.5 día | 1.5 día | Sin cambio |
| 9. QA | 2 días | 2 días | Sin cambio |
| **TOTAL** | **16 días** | **13 días** | -3 días |

### Checkpoints obligatorios

Después de cada fase, antes de avanzar:

1. **Fase 1:** `detect_groups()` reconoce todos los 23 grupos del catálogo
   en al menos 5 compuestos conocidos
2. **Fase 2:** `estimate_via_joback('CCO')['dh_f_298_kJ_mol'].value` ≈ -235 ± 5 kJ/mol
3. **Fase 3:** Benson reduce error vs Joback en al menos 5 compuestos polifuncionales testeados
4. **Fase 4:** 20 templates cargan con RDKit sin errores, y 5 templates pasan tests específicos
5. **Fase 5:** `predict_reactions(['ethanol', 'acetic_acid'], 350, 1.0)` devuelve esterificación
6. **Fase 6:** 300+ reacciones AUTO generadas, todas balanceadas atómicamente
7. **Fase 7:** Reactor existente sigue corriendo idénticamente con defaults
8. **Fase 8:** Usuario puede activar/desactivar reacciones desde UI
9. **Fase 9:** Cero regresiones en 5 ejemplos predefinidos

Si algún checkpoint falla, **no avanzar**. Pedir ayuda al usuario humano.

---

## 8. Resumen de archivos entregados

Estos 4 archivos `.md` están en `chemfx/data/` listos para usar:

| Archivo | Contenido | Líneas aprox |
|---|---|---:|
| `joback_groups.md` | 41 grupos Joback con todas las propiedades | 200 |
| `benson_groups.md` | 40 grupos Benson principales con RSC + NNI | 250 |
| `smiles_compounds_db.md` | 87 SMILES verificados + 21 pendientes | 300 |
| `transformations_db.md` | 20 templates con reaction SMARTS + naming | 600 |

Plus este documento de arquitectura.

---

## 9. Riesgos y mitigaciones

### Riesgo 1: SMARTS de reacciones complejas son frágiles

**Problema:** T16 (aldol), T19 (nitración), T20 (sulfonación) tienen SMARTS
escritos por el autor que pueden tener bugs sutiles.

**Mitigación:** Tests obligatorios por template. Si falla, marcar template
como `confidence_mechanism = BAJA` y desactivar por default.

### Riesgo 2: `thermo` library puede tener bugs

**Problema:** `thermo` es mantenido pero no es perfecto. Algunas funciones
están marcadas como experimentales.

**Mitigación:** validación cruzada constante con tablas `.md`. Si discrepan,
investigar y reportar a maintainer.

### Riesgo 3: 21 compuestos del thermo_db sin SMILES

**Problema:** El archivo entregado cubre 87/108 compuestos. Los 21 restantes
quedan como `unmapped`.

**Mitigación:**
- Implementar `get_unmapped()` que reporta al usuario los faltantes
- Pedir SMILES al usuario en runtime si activa el predictor
- O usar PubChem API en runtime (requiere internet)

### Riesgo 4: Performance en flowsheets grandes

**Problema:** Para 50 bloques y 100 streams, evaluar predicciones puede
ser lento (segundos a minutos).

**Mitigación:**
- Cache agresivo de feed_analysis por hash(composition, T, P)
- Análisis pasivo solo cuando el usuario cambia algo (no en cada iteración)
- Modo "predictor desactivado" como default para flowsheets > 20 bloques

---

## 10. Para Claude Code

### Reglas de implementación

1. **No tocar Capa 3 termodinámica** salvo agregar campos al dataclass
2. **No romper compatibilidad** con los 41 ejemplos del flowsheet
3. **Validar con tests** después de cada módulo
4. **Reportar progreso** al humano después de cada fase
5. **Parar y preguntar** si:
   - Algún template SMARTS no parsea en RDKit
   - `thermo` library tiene un comportamiento inesperado
   - Necesitás más SMILES (los 21 pendientes)
   - Algún test del checkpoint falla

### Estructura de commits sugerida

```
feat(predictor): Fase 0 - setup paquete chemfx
feat(predictor): Fase 1 - detector de grupos funcionales
test(predictor): Fase 1 - tests de detect_groups
feat(predictor): Fase 2 - wrapper sobre thermo.Joback
feat(predictor): Fase 2 - validación cruzada vs tabla .md
...
```

### Métricas de éxito

Al final del proyecto:

- ✅ Cargar feed `(ethanol, acetic_acid)` a 350 K → predice T01 (etil acetato)
- ✅ Cargar feed `(propane, H2, oxygen)` a 700 K → predice T06 (hidrogenación) + T12 (combustión)
- ✅ Mezclador con H₂ + O₂ a 700 K → genera DangerWarning
- ✅ Cargar flowsheet de QuinoaBrew → idéntico al actual (sin regresiones)
- ✅ Tiempo de análisis predictor < 2s para flowsheet de 20 bloques
- ✅ 0 errores de SMARTS al cargar transformations_db.md
- ✅ Validación cruzada thermo vs tabla .md: < 1% discrepancia en ΔHf°

---

**Fin del documento de arquitectura v2.0.**

Si surgen dudas durante implementación, contactar al usuario humano (Hernan)
quien diseñó esta arquitectura junto con Claude.
