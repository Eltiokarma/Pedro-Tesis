"""Orquestador del generador AUTO (Capa 4c).

Recorre todos los compuestos del thermo_db, corre los 3 generadores
(combustion completa, incompleta, cracking) sobre cada uno, y devuelve
la lista de reacciones AUTO generadas.

Persiste en chemfx/data/auto_reactions_db.md (output, no escrito a mano).
Regenera si el hash del thermo_db cambia.
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional

from chemfx.auto_reactions import (
    combustion_complete, combustion_incomplete, thermal_cracking,
)

logger = logging.getLogger(__name__)


_DATA_PATH = Path(__file__).parent.parent / "data" / "auto_reactions_db.md"
_HASH_PATH = Path(__file__).parent.parent / "data" / ".auto_reactions_hash"


def _thermo_db_hash() -> str:
    """SHA1 del thermo_db.md para detectar cambios."""
    try:
        import thermo_db as _td
        return hashlib.sha1(_td._DB_PATH.read_bytes()).hexdigest()[:16]
    except Exception:
        return ""


def _list_thermo_compounds() -> List:
    """Lista de (name, formula) de todos los compuestos del thermo_db."""
    try:
        import thermo_db as _td
        names = _td.list_names()
        out = []
        for n in names:
            comp = _td.get(n)
            if comp and comp.formula:
                out.append((n, comp.formula))
        return out
    except Exception:
        return []


def generate_all_auto_reactions() -> List[Dict]:
    """Genera todas las reacciones AUTO sobre el thermo_db actual.

    Para cada compuesto organico:
      1. Combustion completa (si tiene C y H)
      2. Combustion incompleta (idem)
      3. Cracking termico (si es alcano puro >= 3C)

    Returns: lista de dicts con shape:
        {'id': 'AUTO_<idx>', 'name': str, 'stoich': [...], ...}
    No persiste — devuelve en memoria. Para persistir, llamar
    write_auto_reactions_md().
    """
    compounds = _list_thermo_compounds()
    out: List[Dict] = []
    idx = 0
    for name, formula in compounds:
        for gen_module, suffix in (
            (combustion_complete, "C"),
            (combustion_incomplete, "Ci"),
            (thermal_cracking, "Crk"),
        ):
            try:
                rxn = gen_module.generate(formula)
            except Exception as e:
                logger.debug(f"{gen_module.__name__}.generate({formula}) "
                             f"fallo: {e}")
                continue
            if rxn is None:
                continue
            idx += 1
            rxn["id"] = f"AUTO_{suffix}_{name}_{idx:04d}"
            rxn["origin"] = "auto"
            rxn["thermo_name"] = name
            out.append(rxn)
    return out


def _rxn_to_md_section(rxn: Dict) -> str:
    """Serializa una reaccion AUTO a un bloque markdown."""
    lines = []
    lines.append(f"## {rxn['id']} — {rxn['name']}")
    lines.append("")
    lines.append(f"- category: {rxn.get('category', 'auto')}")
    lines.append(f"- T_min_K: {rxn.get('T_min_K', 0)}")
    lines.append(f"- T_max_K: {rxn.get('T_max_K', 0)}")
    lines.append(f"- thermo_name: {rxn.get('thermo_name', '')}")
    lines.append("- stoich:")
    for sp in rxn.get("stoich", []):
        lines.append(f"    {sp.formula} | {sp.phase} | {sp.nu}")
    lines.append("")
    if rxn.get("comments"):
        lines.append(f"  Comentario: {rxn['comments']}")
    lines.append("---")
    return "\n".join(lines)


def write_auto_reactions_md(reactions: Optional[List[Dict]] = None) -> int:
    """Persiste las reacciones AUTO en chemfx/data/auto_reactions_db.md.

    Args:
        reactions: lista pre-generada o None (regenera).

    Returns: numero de reacciones escritas.
    """
    if reactions is None:
        reactions = generate_all_auto_reactions()
    if not reactions:
        return 0
    header = (
        "<!--\n"
        "====================================================================\n"
        " auto_reactions_db.md - Cache de reacciones AUTO generadas\n"
        " mecanicamente (combustiones, cracking).\n"
        " NO escribir a mano - este archivo es output del generator.\n"
        "====================================================================\n"
        "-->\n"
        "\n"
        f"# Reacciones AUTO ({len(reactions)} total)\n"
        "\n"
        "<!-- Generado por chemfx.auto_reactions.generator -->\n"
        "\n"
    )
    body = "\n".join(_rxn_to_md_section(r) for r in reactions)
    _DATA_PATH.write_text(header + body, encoding="utf-8")
    # Guardar hash para detectar cambios
    h = _thermo_db_hash()
    if h:
        _HASH_PATH.write_text(h, encoding="utf-8")
    return len(reactions)


def regenerate_if_thermo_changed() -> bool:
    """Si thermo_db.md cambio desde la ultima generacion, regenera.

    Returns: True si se regenero, False si no fue necesario.
    """
    current = _thermo_db_hash()
    if not current:
        return False
    try:
        last = _HASH_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        last = ""
    if current != last:
        write_auto_reactions_md()
        return True
    return False
