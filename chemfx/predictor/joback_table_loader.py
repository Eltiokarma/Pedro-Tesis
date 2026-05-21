"""Parser de chemfx/data/joback_groups.md.

Carga la tabla Joback (41 grupos) como dict en memoria para:
  - Fallback manual cuando libreria 'thermo' no esta instalada
  - Validacion cruzada thermo vs .md (detectar discrepancias)
  - Auditoria humana de las contribuciones usadas

Formato esperado del .md: secciones con tablas markdown que tienen
columnas: Grupo, SMARTS, ΔTc, ΔPc, ΔVc, ΔTb, ΔTm, ΔHform, ΔGform,
Cp_a, Cp_b, Cp_c, Cp_d, ΔHfus, ΔHvap, ηa, ηb.

Cache lazy: la primera llamada parsea, las siguientes devuelven cache.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional


_TABLE_CACHE: Optional[Dict[str, dict]] = None
_DB_PATH = Path(__file__).parent.parent / "data" / "joback_groups.md"


# Columnas esperadas en la tabla. Map de header en .md → key en el dict.
# Unicode 'Δ' aparece en headers; tambien 'η'.
_COLUMN_MAP = {
    "Grupo":   "name",
    "SMARTS":  "smarts",
    "ΔTc":     "dTc",
    "ΔPc":     "dPc",
    "ΔVc":     "dVc",
    "ΔTb":     "dTb",
    "ΔTm":     "dTm",
    "ΔHform":  "dHform",
    "ΔGform":  "dGform",
    "Cp_a":    "cp_a",
    "Cp_b":    "cp_b",
    "Cp_c":    "cp_c",
    "Cp_d":    "cp_d",
    "ΔHfus":   "dHfus",
    "ΔHvap":   "dHvap",
    "ηa":      "eta_a",
    "ηb":      "eta_b",
}


def _parse_number(s: str) -> Optional[float]:
    """Parsea un valor de celda. None si 'n.a.' o vacio."""
    s = s.strip()
    if not s or s.lower() in ("n.a.", "n/a", "-", "—"):
        return None
    # Unicode minus → ASCII minus
    s = s.replace("−", "-").replace("–", "-")
    # E+/E- notation: '1.95E+1' o '−2.30E+1'
    try:
        return float(s)
    except ValueError:
        return None


def _strip_backticks(s: str) -> str:
    """Quita backticks del SMARTS: `[CX4H3]` → [CX4H3]."""
    s = s.strip()
    if s.startswith("`") and s.endswith("`"):
        return s[1:-1]
    return s


def _parse_table_row(line: str, headers: list) -> Optional[dict]:
    """Parsea una fila de tabla markdown."""
    if not line.strip().startswith("|"):
        return None
    # Separar por |, descartar primer y ultimo (espacios vacios)
    cells = [c.strip() for c in line.split("|")]
    cells = cells[1:-1] if cells[0] == "" and cells[-1] == "" else cells
    if len(cells) != len(headers):
        return None
    row = {}
    for header, cell in zip(headers, cells):
        key = _COLUMN_MAP.get(header.strip())
        if key is None:
            continue
        if key in ("name", "smarts"):
            row[key] = _strip_backticks(cell)
        else:
            row[key] = _parse_number(cell)
    return row


def _is_separator(line: str) -> bool:
    """True si es la linea separador de tabla markdown (|---|---|...)."""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return False
    return bool(re.fullmatch(r"[\s\|:\-]+", stripped))


def _parse_md() -> Dict[str, dict]:
    """Parsea joback_groups.md, devuelve dict {group_name: row_dict}."""
    if not _DB_PATH.is_file():
        return {}
    text = _DB_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()

    out: Dict[str, dict] = {}
    headers: list = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # Detectar header de tabla: linea | con "Grupo" como primera columna
        if line.strip().startswith("| Grupo |") or line.strip().startswith("|Grupo|"):
            headers = [c.strip() for c in line.split("|")[1:-1]]
            # Saltar separador
            if i + 1 < len(lines) and _is_separator(lines[i + 1]):
                i += 2
            else:
                i += 1
            # Parsear filas hasta end-of-table
            while i < len(lines):
                row_line = lines[i]
                if not row_line.strip().startswith("|"):
                    break
                if _is_separator(row_line):
                    i += 1
                    continue
                row = _parse_table_row(row_line, headers)
                if row and row.get("name"):
                    out[row["name"]] = row
                i += 1
            continue
        i += 1
    return out


def load_joback_table(force_reload: bool = False) -> Dict[str, dict]:
    """Devuelve {group_name: {smarts, dHform, dGform, dTb, ...}}.

    Cache lazy. force_reload=True para tests o si se editara el .md.
    """
    global _TABLE_CACHE
    if _TABLE_CACHE is None or force_reload:
        _TABLE_CACHE = _parse_md()
    return _TABLE_CACHE


def get_group(name: str) -> Optional[dict]:
    """Contribuciones de un grupo Joback. None si no esta."""
    return load_joback_table().get(name)


def list_group_names() -> list:
    """Lista todos los grupos cargados."""
    return list(load_joback_table().keys())
