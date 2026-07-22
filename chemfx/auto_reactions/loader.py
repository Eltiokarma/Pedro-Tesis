"""Loader del cache auto_reactions_db.md (Capa 4c → Fase 6).

Contraparte de lectura de generator.write_auto_reactions_md(): parsea el
cache persistido y lo expone como lista de dicts en memoria, para que
predict_reactions(include_auto=True) pueda ofrecer las combustiones y
crackings generados mecanicamente.

Formato de cada seccion (ver generator._rxn_to_md_section):

    ## AUTO_C_methane_0001 — Combustion completa de CH4

    - category: combustion
    - T_min_K: 700.0
    - T_max_K: 2500.0
    - thermo_name: methane
    - stoich:
        CH4 | g | -1
        O2 | g | -2
        CO2 | g | 1
        H2O | g | 2

      Comentario: Auto-generada T12: ...
    ---

Shape de retorno: {'id', 'name', 'category', 'T_min_K', 'T_max_K',
'thermo_name', 'stoich': [StoichEntry], 'comments'} — mismo shape en
memoria que devuelve generator.generate_all_auto_reactions().
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from chemfx.auto_reactions.generator import _DATA_PATH

logger = logging.getLogger(__name__)

_CACHE: Optional[List[Dict]] = None


def _stoich_cls():
    try:
        from reactions_db import StoichEntry
        return StoichEntry
    except ImportError:
        from collections import namedtuple
        return namedtuple("StoichEntry", ["formula", "phase", "nu"])


def _parse_md(text: str) -> List[Dict]:
    cls = _stoich_cls()
    out: List[Dict] = []
    rxn: Optional[Dict] = None
    in_stoich = False
    for raw in text.splitlines():
        line = raw.rstrip()
        m = re.match(r"^## (\S+) — (.+)$", line)
        if m:
            rxn = {"id": m.group(1), "name": m.group(2), "stoich": [],
                   "comments": "", "origin": "auto"}
            out.append(rxn)
            in_stoich = False
            continue
        if rxn is None:
            continue
        if line.strip() == "---":
            rxn = None
            in_stoich = False
            continue
        s = line.strip()
        if s.startswith("- stoich:"):
            in_stoich = True
            continue
        if s.startswith("- "):
            in_stoich = False
            key, _, val = s[2:].partition(":")
            key, val = key.strip(), val.strip()
            if key in ("T_min_K", "T_max_K"):
                try:
                    rxn[key] = float(val)
                except ValueError:
                    pass
            elif key in ("category", "thermo_name"):
                rxn[key] = val
            continue
        if s.startswith("Comentario:"):
            in_stoich = False
            rxn["comments"] = s[len("Comentario:"):].strip()
            continue
        if in_stoich and "|" in s:
            parts = [p.strip() for p in s.split("|")]
            if len(parts) == 3:
                try:
                    rxn["stoich"].append(
                        cls(formula=parts[0], phase=parts[1],
                            nu=int(parts[2])))
                except ValueError:
                    logger.debug(f"stoich ilegible en {rxn['id']}: {s}")
    # Descartar secciones sin estequiometria util (id sin cuerpo)
    return [r for r in out if r.get("stoich")]


def load_auto_reactions(force_reload: bool = False) -> List[Dict]:
    """Lee el cache auto_reactions_db.md (lazy, memoizado).

    Devuelve [] si el cache no existe o no se puede leer — el predictor
    degrada a curated+predicted, igual que sin rdkit.
    """
    global _CACHE
    if _CACHE is not None and not force_reload:
        return _CACHE
    try:
        text = _DATA_PATH.read_text(encoding="utf-8")
    except OSError:
        logger.debug(f"cache AUTO no disponible: {_DATA_PATH}")
        _CACHE = []
        return _CACHE
    try:
        _CACHE = _parse_md(text)
    except Exception as e:
        logger.debug(f"parse del cache AUTO fallo: {e}")
        _CACHE = []
    return _CACHE
