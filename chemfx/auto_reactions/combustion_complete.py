"""Generador de combustiones COMPLETAS (T12).

C_a H_b O_c N_d S_e + (a + b/4 − c/2 + e) O2 → a CO2 + b/2 H2O + d/2 N2 + e SO2

Aplicable a cualquier compuesto organico (con al menos C y H).
NO usa SMARTS — es estequiometria determinista sobre la formula molecular.
"""
from __future__ import annotations

import re
from collections import namedtuple
from typing import Dict, List, Optional


# StoichEntry-compatible (formula, phase, nu)
SE = namedtuple("SE", ["formula", "phase", "nu"])


def _parse_formula_chnos(formula: str) -> Dict[str, int]:
    """Parsea 'C6H12O6' → {'C':6, 'H':12, 'O':6}."""
    counts: Dict[str, int] = {}
    for m in re.finditer(r"([A-Z][a-z]?)(\d*)", formula):
        elem, num = m.group(1), m.group(2)
        if not elem:
            continue
        counts[elem] = counts.get(elem, 0) + (int(num) if num else 1)
    return counts


def generate(formula: str) -> Optional[Dict]:
    """Combustion completa para una formula molecular.

    Args:
        formula: 'C2H6O', 'CH4', 'C6H6', etc.

    Returns:
        dict con:
          'name': 'Combustion completa de <formula>'
          'stoich': [SE(formula, 'g', nu), ...]
          'dh_rxn_298_kJ_mol': None (se calcula despues via Hess)
          'T_min_K', 'T_max_K'
        None si la formula no tiene al menos 1 C y 1 H (no combustible).
    """
    counts = _parse_formula_chnos(formula)
    a = counts.get("C", 0)
    b = counts.get("H", 0)
    c = counts.get("O", 0)
    d = counts.get("N", 0)
    e = counts.get("S", 0)
    if a == 0 or b == 0:
        return None
    # O2 estequiometrico
    n_O2 = a + b/4.0 - c/2.0 + e
    if n_O2 <= 0:
        return None    # no se necesita O2 (raro pero defensivo)

    stoich: List = []
    stoich.append(SE(formula=formula, phase="g", nu=-1))
    # nu de O2 puede ser fraccionario; reactions_db tipicamente usa
    # enteros, asi que escalamos × 2 si es necesario.
    scale = 2 if (n_O2 % 1 != 0 or (b/2.0) % 1 != 0 or (d/2.0) % 1 != 0
                  or (e/1.0) % 1 != 0) else 1
    n_O2_int = int(n_O2 * scale)
    a_int = int(a * scale)
    b_int = int((b/2.0) * scale)
    d_int = int((d/2.0) * scale)
    e_int = int(e * scale)
    # Compuesto principal en stoich con nu = -scale
    stoich[0] = SE(formula=formula, phase="g", nu=-scale)
    stoich.append(SE(formula="O2", phase="g", nu=-n_O2_int))
    stoich.append(SE(formula="CO2", phase="g", nu=a_int))
    if b_int > 0:
        stoich.append(SE(formula="H2O", phase="g", nu=b_int))
    if d_int > 0:
        stoich.append(SE(formula="N2", phase="g", nu=d_int))
    if e_int > 0:
        stoich.append(SE(formula="SO2", phase="g", nu=e_int))

    return {
        "name": f"Combustion completa de {formula}",
        "stoich": stoich,
        "T_min_K": 700.0,
        "T_max_K": 2500.0,
        "category": "combustion",
        "comments": (
            f"Auto-generada T12: {formula} + {n_O2_int} O2 -> "
            f"{a_int} CO2 + {b_int} H2O" + (f" + {d_int} N2" if d_int else "")
            + (f" + {e_int} SO2" if e_int else "")
        ),
    }
