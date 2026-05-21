"""Detector de grupos funcionales (Fase 1 — pendiente).

API:
    detect_groups(compound_name) -> List[FunctionalGroup]
    get_smarts_pattern(group_name) -> Optional[str]
    list_known_groups() -> List[str]
    match_smarts(smiles, smarts) -> List[Tuple[int, ...]]

Estrategia:
    1. RDKit con patron SMARTS si SMILES disponible y RDKit instalado.
    2. Fallback manual: lookup en data/functional_groups_db.md.

Estado: SKELETON. Implementacion completa en Fase 1.
"""
from typing import List, Optional, Tuple

from chemfx import RDKIT_AVAILABLE
from chemfx.predictor.types import FunctionalGroup


# Patrones SMARTS canonicos para los grupos funcionales soportados.
# Ver §9.3 Apendice C de la arquitectura.
SMARTS_PATTERNS = {
    "alcohol_primario":    "[CX4H2][OX2H]",
    "alcohol_secundario":  "[CX4H1]([#6])[OX2H]",
    "alcohol_terciario":   "[CX4H0]([#6])([#6])([#6])[OX2H]",
    "alcohol_aromatico":   "[c][OX2H]",
    "acido_carboxilico":   "[CX3](=O)[OX2H]",
    "ester":               "[CX3](=O)[OX2][#6]",
    "aldehido":            "[CX3H1](=O)",
    "cetona":              "[CX3H0](=O)([#6])[#6]",
    "eter":                "[OX2]([#6])[#6]",
    "amina_primaria":      "[NX3H2][#6]",
    "amina_secundaria":    "[NX3H1]([#6])[#6]",
    "amina_terciaria":     "[NX3H0]([#6])([#6])[#6]",
    "alqueno":             "[CX3]=[CX3]",
    "alquino":             "[CX2]#[CX2]",
    "aromatico":           "c",
    "amida":               "[CX3](=O)[NX3]",
    "nitro":               "[N+](=O)[O-]",
    "nitrilo":             "[CX2]#N",
    "halogenuro_alquilo":  "[CX4][F,Cl,Br,I]",
    "sulfonato":           "S(=O)(=O)[O-,OH]",
    "tiol":                "[SX2H]",
    "fosfato":             "P(=O)(O)(O)O",
    "hemiacetal":          "[CX4]([OX2H])([OX2][#6])",
    "acetal":              "[CX4]([OX2][#6])([OX2][#6])",
}


def list_known_groups() -> List[str]:
    """Lista todos los grupos funcionales que el sistema sabe detectar."""
    return list(SMARTS_PATTERNS.keys())


def get_smarts_pattern(group_name: str) -> Optional[str]:
    """Devuelve el patron SMARTS estandar para un grupo funcional."""
    return SMARTS_PATTERNS.get(group_name)


def match_smarts(smiles: str, smarts: str) -> List[Tuple[int, ...]]:
    """Devuelve tuplas de indices atomicos que matchean el SMARTS.

    Implementacion: usa RDKit si esta disponible. Sino, fallback manual
    (lookup limitado) o lista vacia.

    Args:
        smiles: SMILES canonico del compuesto.
        smarts: patron SMARTS a buscar.

    Returns: lista de tuplas de indices atomicos. Vacia si no hay match
    o si no se puede procesar (sin levantar excepcion).
    """
    if not smiles or not smarts:
        return []
    if RDKIT_AVAILABLE:
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(smiles)
            patt = Chem.MolFromSmarts(smarts)
            if mol is None or patt is None:
                return []
            return [tuple(m) for m in mol.GetSubstructMatches(patt)]
        except Exception:
            return []
    # Fallback manual: TODO en Fase 1 (lookup table simplificada).
    return []


def detect_groups(compound_name: str) -> List[FunctionalGroup]:
    """Detecta grupos funcionales en un compuesto del thermo_db.

    PENDIENTE (Fase 1):
        1. Cargar SMILES del compuesto desde thermo_db
           (extension ComponentThermo.smiles).
        2. Si RDKit disponible: iterar SMARTS_PATTERNS, llamar
           match_smarts para cada uno.
        3. Si NO RDKit o SMILES vacio: lookup en
           data/functional_groups_db.md (asignaciones manuales).
        4. Cache lazy: detectar solo una vez por compuesto por sesion
           (memoizar en un dict modulo-level).

    Returns: lista de FunctionalGroup detectados. Vacia si compuesto
    no existe o no se pudo analizar.
    """
    # TODO Fase 1: implementacion completa
    return []
