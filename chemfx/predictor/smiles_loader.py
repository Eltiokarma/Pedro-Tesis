"""SMILES loader — parsea chemfx/data/smiles_compounds_db.md.

Devuelve dict {compound_name: {'smiles': str, 'cas': str, 'verified': bool}}.

El nombre canonico se normaliza con thermo_db._normalize_name() asi que
coincide con thermo_db.list_names(). Si un compuesto no tiene SMILES,
el predictor lo trata como inerte y lo reporta en unmapped_compounds.

Formato esperado por linea dentro de bloques fenced:
    nombre | CAS | SMILES | comentario
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re


_SMILES_CACHE: Optional[Dict[str, dict]] = None
_DB_PATH = Path(__file__).parent.parent / "data" / "smiles_compounds_db.md"


def _normalize_name_local(name: str) -> str:
    """Versión local del normalize de thermo_db para evitar import circular.

    Replica el comportamiento de thermo_db._normalize_name (ya fixeado):
    lowercase, '-' → '_', 'o '/'n ' al inicio se eliminan, espacios → '_'.
    """
    base = name.split("(")[0].strip()
    base = base.lower().replace("-", "_").replace(" ", "_")
    base = re.sub(r"^[on]_+", "", base)
    return base


def _parse_md() -> Dict[str, dict]:
    """Parsea el .md y devuelve el dict canonico."""
    if not _DB_PATH.is_file():
        return {}
    text = _DB_PATH.read_text(encoding="utf-8")

    out: Dict[str, dict] = {}
    # Buscar bloques fenced con lineas tipo:
    #    nombre | CAS | SMILES | comentario
    in_fence = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            continue
        if "|" not in stripped:
            continue
        parts = [p.strip() for p in stripped.split("|")]
        if len(parts) < 3:
            continue
        name, cas, smiles = parts[0], parts[1], parts[2]
        comment = parts[3] if len(parts) > 3 else ""
        # Saltar headers tipo "nombre_canónico | CAS | SMILES | comentario"
        if name.lower() in ("nombre_canónico", "nombre", "compuesto"):
            continue
        # Pseudo-componentes y placeholders: el SMILES no es real.
        # Detectar: vacio, N/A, comienza con "(" (literal "(sin SMILES — ...)"),
        # contiene " " (todo SMILES valido es contiguo), o "—" (em dash).
        is_pseudo = (
            not smiles
            or smiles.upper() == "N/A"
            or smiles.startswith("(")
            or " " in smiles
            or "—" in smiles
            or "no usar" in smiles.lower()
            or "sin smiles" in smiles.lower()
        )
        if not name or is_pseudo:
            out[_normalize_name_local(name)] = {
                "smiles": "",
                "cas": cas if cas != "--" else "",
                "comment": comment,
                "verified": False,
            }
            continue
        # 'verified' True para los que tienen SMILES + CAS no N/A.
        # Los compuestos con NOTA: o pendientes quedan False (ver el .md).
        verified = not (
            "verification_required" in comment.lower()
            or "verificar" in comment.lower()
            or "pendiente" in comment.lower()
        )
        out[_normalize_name_local(name)] = {
            "smiles": smiles,
            "cas": cas if cas != "--" else "",
            "comment": comment,
            "verified": verified,
        }
    return out


def load_smiles_db(force_reload: bool = False) -> Dict[str, dict]:
    """Devuelve el dict completo de SMILES indexado por nombre canonico."""
    global _SMILES_CACHE
    if _SMILES_CACHE is None or force_reload:
        _SMILES_CACHE = _parse_md()
    return _SMILES_CACHE


def get_smiles(thermo_name: str) -> Optional[str]:
    """SMILES canonico de un compuesto thermo_db. None si no esta mapeado
    o si el SMILES esta vacio (pseudo-componente)."""
    entry = load_smiles_db().get(_normalize_name_local(thermo_name))
    if entry is None:
        return None
    s = entry.get("smiles") or ""
    return s or None


def is_verified(thermo_name: str) -> bool:
    """True si el SMILES del compuesto fue verificado contra PubChem/NIST."""
    entry = load_smiles_db().get(_normalize_name_local(thermo_name))
    return bool(entry and entry.get("verified", False))


def list_unmapped(thermo_names: List[str]) -> List[str]:
    """Dado el universo de compuestos del thermo_db, devuelve cuales
    no tienen SMILES en el .md (para reporte al user)."""
    db = load_smiles_db()
    return sorted([
        n for n in thermo_names
        if _normalize_name_local(n) not in db
        or not db[_normalize_name_local(n)].get("smiles")
    ])


def list_all() -> List[Tuple[str, str]]:
    """Devuelve [(name, smiles), ...] de todos los compuestos con SMILES."""
    return [
        (name, entry["smiles"])
        for name, entry in load_smiles_db().items()
        if entry.get("smiles")
    ]
