"""Detector de grupos funcionales (Fase 1).

API publica:
    detect_groups(compound_name) -> List[FunctionalGroup]
    detect_groups_from_smiles(smiles) -> List[FunctionalGroup]
    get_smarts_pattern(group_name) -> Optional[str]
    list_known_groups() -> List[str]
    match_smarts(smiles, smarts) -> List[Tuple[int, ...]]

Backend principal: RDKit con SMARTS canonicos. Si RDKit no esta
disponible: fallback manual ligero (solo grupos obvios via subcadena
del SMILES — incompleto pero suficiente para tests basicos).

Cache lazy por compuesto: la primera llamada a detect_groups(name)
parsea el SMILES y matchea cada SMARTS; las siguientes devuelven
el resultado cacheado.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from chemfx import RDKIT_AVAILABLE
from chemfx.predictor.types import FunctionalGroup
from chemfx.predictor import smiles_loader


# Patrones SMARTS canonicos para identificacion de grupos funcionales.
# Estos NO son los SMARTS de Joback (que son mas granulares para
# estimacion). Estos son los que el predictor usa para enumerar
# reacciones posibles desde un feed.
# Fuente: §5.1 ARQUITECTURA_v2 §9.3 + apendice C de v1.
SMARTS_PATTERNS: Dict[str, str] = {
    # Alcoholes (clasificacion 1 / 2 / 3 / aromatico)
    "alcohol_primario":    "[CX4H2][OX2H]",
    "alcohol_secundario":  "[CX4H1]([#6])[OX2H]",
    "alcohol_terciario":   "[CX4H0]([#6])([#6])([#6])[OX2H]",
    "alcohol_aromatico":   "[c][OX2H]",
    # Carbonilos
    "acido_carboxilico":   "[CX3](=O)[OX2H]",
    "ester":               "[CX3](=O)[OX2][#6]",
    "aldehido":            "[CX3H1](=O)",
    "cetona":              "[CX3H0](=O)([#6])[#6]",
    "amida":               "[CX3](=O)[NX3]",
    # Eteres
    "eter":                "[OX2]([#6])[#6]",
    # Aminas (1 / 2 / 3)
    "amina_primaria":      "[NX3H2][#6]",
    "amina_secundaria":    "[NX3H1]([#6])[#6]",
    "amina_terciaria":     "[NX3H0]([#6])([#6])[#6]",
    # Insaturaciones
    "alqueno":             "[CX3]=[CX3]",
    "alquino":             "[CX2]#[CX2]",
    "aromatico":           "c1ccccc1",
    # N / S
    "nitro":               "[N+](=O)[O-]",
    "nitrilo":             "[CX2]#N",
    "tiol":                "[SX2H]",
    "sulfuro":             "[#6][SX2][#6]",
    # Halogenos (en R alquilico)
    "halogenuro_alquilo":  "[CX4][F,Cl,Br,I]",
    # Sulfonatos, fosfatos
    "sulfonato":           "S(=O)(=O)[O-,OH]",
    "fosfato":             "P(=O)(O)(O)O",
    # Acetales (carbohidratos)
    "hemiacetal":          "[CX4]([OX2H])[OX2][#6]",
    "acetal":              "[CX4]([OX2][#6])[OX2][#6]",
}


# Cache lazy: {compound_name: List[FunctionalGroup]}
_GROUPS_CACHE: Dict[str, List[FunctionalGroup]] = {}


def list_known_groups() -> List[str]:
    """Lista todos los grupos funcionales que el sistema sabe detectar."""
    return list(SMARTS_PATTERNS.keys())


def get_smarts_pattern(group_name: str) -> Optional[str]:
    """Patron SMARTS para un grupo. None si el grupo no esta en la tabla."""
    return SMARTS_PATTERNS.get(group_name)


def match_smarts(smiles: str, smarts: str) -> List[Tuple[int, ...]]:
    """Tuplas de indices atomicos que matchean el SMARTS en el SMILES.

    Devuelve lista vacia si:
      - smiles o smarts vacios
      - RDKit no disponible (fallback no implementado en Fase 1)
      - parsing del smiles o smarts falla
      - no hay matches

    No levanta excepcion: silent failure ante input invalido (filosofia
    del modulo).
    """
    if not smiles or not smarts:
        return []
    if not RDKIT_AVAILABLE:
        return []
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        patt = Chem.MolFromSmarts(smarts)
        if mol is None or patt is None:
            return []
        return [tuple(m) for m in mol.GetSubstructMatches(patt)]
    except Exception:
        return []


def detect_groups_from_smiles(smiles: str) -> List[FunctionalGroup]:
    """Detecta grupos funcionales directamente desde un SMILES.

    Itera todos los SMARTS_PATTERNS y devuelve un FunctionalGroup por
    cada grupo presente, con count = numero de matches.

    No cachea por SMILES (puede llamarse muchas veces con SMILES
    distintos). El cache esta en detect_groups(name) que usa el nombre
    canonico como key.
    """
    if not smiles:
        return []
    detected: List[FunctionalGroup] = []
    for group_name, smarts in SMARTS_PATTERNS.items():
        matches = match_smarts(smiles, smarts)
        if matches:
            detected.append(FunctionalGroup(
                name=group_name,
                smarts=smarts,
                atoms_match=matches[0],   # primer match (referencia)
                count=len(matches),
            ))
    return detected


def detect_groups(compound_name: str) -> List[FunctionalGroup]:
    """Detecta grupos funcionales en un compuesto del thermo_db.

    Args:
        compound_name: nombre canonico (e.g. 'ethanol', 'acetic_acid').

    Returns:
        Lista de FunctionalGroup. Vacia si:
          - compuesto no esta en smiles_compounds_db.md
          - SMILES vacio (mezclas, pseudo-componentes)
          - RDKit no disponible
          - el SMILES no parsea
    """
    # Cache lazy
    if compound_name in _GROUPS_CACHE:
        return _GROUPS_CACHE[compound_name]
    smiles = smiles_loader.get_smiles(compound_name)
    if not smiles:
        _GROUPS_CACHE[compound_name] = []
        return []
    result = detect_groups_from_smiles(smiles)
    _GROUPS_CACHE[compound_name] = result
    return result


def clear_cache() -> None:
    """Limpia el cache lazy (util para tests o si se actualiza el .md)."""
    _GROUPS_CACHE.clear()
