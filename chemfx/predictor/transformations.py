"""Loader y aplicador de templates de transformacion T01-T20 (Fase 4).

Parsea chemfx/data/transformations_db.md → lista de TransformationTemplate.

API publica:
    load_transformations() -> List[TransformationTemplate]
    get_transformation(t_id) -> Optional[TransformationTemplate]
    list_transformations() -> List[TransformationTemplate]
    find_applicable_transformations(compounds_groups, T_K) -> list

    apply_to_compounds(template, smiles_list) -> List[List[str]]
        Aplica el reaction SMARTS via RDKit, devuelve productos.
        Requiere RDKit. Sin RDKit devuelve [].

Estructura esperada del .md por template:
    ## T01 — Esterificacion ...
    **T range:** 298 - 450 K
    **Confidence mechanism:** ALTA
    **Catalizador:** H+ ...
    ### Reaction SMARTS
    ```
    <smarts>
    ```

El parser tolera variaciones de formato — busca por encabezados
**bold** y bloques fenced.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from chemfx import RDKIT_AVAILABLE
from chemfx.predictor.types import (
    TransformationTemplate, Confidence, FunctionalGroup,
)


_TEMPLATES_CACHE: Optional[List[TransformationTemplate]] = None
_DB_PATH = Path(__file__).parent.parent / "data" / "transformations_db.md"


# ======================================================
# PARSER
# ======================================================
def _parse_confidence(s: str) -> Confidence:
    s = s.upper().strip()
    if s.startswith("ALTA") or s == "HIGH":
        return Confidence.ALTA
    if s.startswith("MEDIA") or s == "MEDIUM":
        return Confidence.MEDIA
    if s.startswith("BAJA") or s == "LOW":
        return Confidence.BAJA
    return Confidence.MEDIA


def _parse_T_range(s: str) -> Tuple[float, float]:
    """Parsea 'T range: 298 - 450 K' o '298-450 K'. Devuelve (Tmin, Tmax)."""
    nums = re.findall(r"\d+(?:\.\d+)?", s)
    if len(nums) >= 2:
        try:
            return (float(nums[0]), float(nums[1]))
        except ValueError:
            pass
    return (298.15, 1000.0)


def _extract_section(text: str, start_idx: int, end_idx: int,
                       label: str) -> str:
    """Extrae el primer bloque ``` ... ``` que aparece despues de un
    header dado (case-insensitive). Vacio si no se encuentra."""
    section = text[start_idx:end_idx]
    # Buscar el header → bloque fenced que le sigue
    m = re.search(rf"###\s+{label}.*?```(?:[^\n]*)\n(.*?)\n```",
                  section, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return ""


def _parse_one_template(block: str) -> Optional[TransformationTemplate]:
    """Parsea una seccion '## T01 — ...' completa."""
    # ID del template: 'T01' (primera palabra despues de ## )
    m = re.match(r"##\s+(T\d+\w*)\s*[—\-]\s*(.+?)(?:\n|$)", block)
    if not m:
        return None
    t_id_short = m.group(1).strip()    # 'T01', 'T07b'
    name = m.group(2).strip()
    # ID completo: t_id_short + '_' + slug del nombre
    slug = re.sub(r"[^\w]+", "_", name.lower()).strip("_")
    full_id = f"{t_id_short}_{slug}"[:64]

    # T range
    m = re.search(r"\*\*T range:\*\*\s*(.+?)(?:\n|$)", block)
    T_range = _parse_T_range(m.group(1)) if m else (298.15, 1000.0)

    # Confidence
    m = re.search(r"\*\*Confidence[^:]*:\*\*\s*(\w+)", block)
    conf = _parse_confidence(m.group(1)) if m else Confidence.MEDIA

    # Catalizador
    m = re.search(r"\*\*Catalizador:\*\*\s*(.+?)(?:\n|$)", block)
    cat_text = m.group(1).strip() if m else ""
    requires_cat = bool(cat_text) and "ninguno" not in cat_text.lower()

    # Ref
    refs = []
    m = re.search(r"\*\*Ref:?\*\*\s*(.+?)(?:\n|$)", block)
    if m:
        refs = [m.group(1).strip()]

    # Reaction SMARTS: primer bloque fenced bajo "### Reaction SMARTS".
    # Tolera texto extra en el header (e.g. "### Reaction SMARTS (caso típico)")
    # y texto explicativo entre el header y el primer bloque fenced.
    smarts = ""
    m = re.search(
        r"###\s+Reaction SMARTS[^\n]*\n.*?```(?:[^\n]*)\n(.*?)\n```",
        block, re.DOTALL | re.IGNORECASE,
    )
    if m:
        smarts = m.group(1).strip()

    return TransformationTemplate(
        id=full_id,
        name=name,
        reactant_groups=[],   # se infiere por SMARTS al aplicar; no
                              # lo poblamos del .md (es informativo solo)
        product_groups=[],
        stoich_template="",
        reaction_smarts=smarts,
        T_range_K=T_range,
        requires_catalyst=requires_cat,
        catalyst_hint=cat_text,
        mechanism_confidence=conf,
        references=refs,
    )


def _parse_md() -> List[TransformationTemplate]:
    """Parsea transformations_db.md → lista de templates."""
    if not _DB_PATH.is_file():
        return []
    text = _DB_PATH.read_text(encoding="utf-8")

    # Split por '## T' (cabecera de template). Toma los bloques que
    # empiezan con 'T<digits>'.
    blocks = re.split(r"(?=^##\s+T\d+)", text, flags=re.MULTILINE)
    out: List[TransformationTemplate] = []
    for block in blocks:
        if not block.lstrip().startswith("## T"):
            continue
        tpl = _parse_one_template(block)
        if tpl:
            out.append(tpl)
    return out


def load_transformations(force_reload: bool = False) -> List[TransformationTemplate]:
    """Devuelve la lista de templates. Cache lazy."""
    global _TEMPLATES_CACHE
    if _TEMPLATES_CACHE is None or force_reload:
        _TEMPLATES_CACHE = _parse_md()
    return _TEMPLATES_CACHE


def get_transformation(t_id: str) -> Optional[TransformationTemplate]:
    """Busca por id completo o por prefix 'T01'."""
    templates = load_transformations()
    # Match exacto
    for tpl in templates:
        if tpl.id == t_id:
            return tpl
    # Match por prefix (e.g. 'T01' → T01_esterificacion_de_fischer)
    for tpl in templates:
        if tpl.id.startswith(t_id + "_") or tpl.id.startswith(t_id.lower() + "_"):
            return tpl
    return None


def list_transformations() -> List[TransformationTemplate]:
    return load_transformations()


def validate_smarts(force_log: bool = False) -> Dict[str, bool]:
    """Valida cada SMARTS de los templates contra RDKit ReactionFromSmarts.

    Devuelve {template_id: True/False} indicando cuales parsean.
    Si force_log=True, imprime cuales fallan (util para debug).

    Templates con SMARTS invalido (e.g. T16 aldol con literal '...') quedan
    en False y deben skipearse en apply_to_compounds. Sin esto, RDKit
    spammea stderr con cada intento."""
    if not RDKIT_AVAILABLE:
        return {}
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit import RDLogger
    # Silenciar RDKit durante la validacion — los SMARTS invalidos
    # (e.g. T16 con literal "...") spammean stderr y no es util.
    RDLogger.DisableLog("rdApp.error")
    RDLogger.DisableLog("rdApp.warning")
    try:
        result: Dict[str, bool] = {}
        for tpl in load_transformations():
            if not tpl.reaction_smarts:
                result[tpl.id] = False
                continue
            try:
                rxn = AllChem.ReactionFromSmarts(tpl.reaction_smarts)
                ok = rxn is not None and rxn.GetNumReactantTemplates() > 0
            except Exception:
                ok = False
            result[tpl.id] = ok
            if force_log and not ok:
                print(f"  T-SMARTS invalido: {tpl.id}")
    finally:
        RDLogger.EnableLog("rdApp.error")
        RDLogger.EnableLog("rdApp.warning")
    return result


# Cache lazy: {template_id: bool}, populado al primer uso.
_SMARTS_VALID_CACHE: Optional[Dict[str, bool]] = None


def is_smarts_valid(template_id: str) -> bool:
    """Cache de validacion: True si el SMARTS del template parsea OK."""
    global _SMARTS_VALID_CACHE
    if _SMARTS_VALID_CACHE is None:
        _SMARTS_VALID_CACHE = validate_smarts()
    return _SMARTS_VALID_CACHE.get(template_id, False)


# ======================================================
# APLICACION (RDKit)
# ======================================================
def apply_to_compounds(template: TransformationTemplate,
                        smiles_list: List[str]) -> List[List[str]]:
    """Aplica el reaction SMARTS del template a un conjunto de reactantes.

    Args:
        template: TransformationTemplate cargado.
        smiles_list: lista de SMILES de reactantes (orden importa para
            templates de >1 reactante).

    Returns:
        Lista de tuplas-de-productos. Cada elemento es la lista de
        SMILES canonicos de UNA aplicacion del template. Vacia si:
          - RDKit no disponible
          - template sin reaction_smarts
          - smiles_list invalido
          - el template no aplica a estos reactantes
    """
    if not RDKIT_AVAILABLE:
        return []
    if not template.reaction_smarts:
        return []
    if not smiles_list:
        return []
    # Skip templates con SMARTS invalido (e.g. T16 aldol con literal
    # '...') ANTES de pasar a RDKit — evita spam de stderr.
    if not is_smarts_valid(template.id):
        return []
    try:
        from rdkit import Chem
        from rdkit.Chem import AllChem
        # Suprimir error+warning de RDKit durante todo el ciclo: tanto el
        # ReactionFromSmarts como MolFromSmiles pueden spammear cuando el
        # usuario tiene compuestos con SMILES pseudo o templates rotos.
        from rdkit import RDLogger
        RDLogger.DisableLog("rdApp.error")
        RDLogger.DisableLog("rdApp.warning")
        try:
            rxn = AllChem.ReactionFromSmarts(template.reaction_smarts)
            if rxn is None:
                return []
            mols = [Chem.MolFromSmiles(s) for s in smiles_list]
            if any(m is None for m in mols):
                return []
            product_sets = rxn.RunReactants(tuple(mols))
        finally:
            RDLogger.EnableLog("rdApp.error")
            RDLogger.EnableLog("rdApp.warning")
        out: List[List[str]] = []
        for ps in product_sets:
            try:
                smis = [Chem.MolToSmiles(p) for p in ps]
                if smis and smis not in out:
                    out.append(smis)
            except Exception:
                continue
        return out
    except Exception:
        return []


def find_applicable_transformations(
    compounds_groups: Dict[str, List[FunctionalGroup]],
    T_K: float,
) -> List[TransformationTemplate]:
    """Devuelve templates cuya T_range incluye T_K.

    NOTA Fase 4: el filtro por grupos detectados (compounds_groups) es
    aproximado por ahora — la real combinatoria de reactantes vs
    templates la hace reaction_predictor en Fase 5, usando los SMARTS
    de los reactantes del template. Aca solo filtramos por temperatura
    para no devolver T19 nitracion en un mezclador a 25°C, por ejemplo.
    """
    templates = load_transformations()
    out: List[TransformationTemplate] = []
    for tpl in templates:
        Tmin, Tmax = tpl.T_range_K
        if Tmin <= T_K <= Tmax:
            out.append(tpl)
    return out
