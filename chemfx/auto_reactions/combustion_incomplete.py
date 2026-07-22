"""Generador de combustiones INCOMPLETAS (T13).

C_a H_b O_c + (a/2 + b/4 − c/2) O2 → a CO + b/2 H2O (rico en combustible)

Confidence MEDIA — la distribucion CO/CO2 real depende de cinetica
y relacion aire/combustible (lambda < 1). Aca generamos la variante
'todo a CO' como caso limite. Variantes con hollin (C(s)) quedan para
v2.
"""
from __future__ import annotations

from collections import namedtuple
from typing import Dict, List, Optional

from chemfx.auto_reactions.combustion_complete import _parse_formula_chnos


SE = namedtuple("SE", ["formula", "phase", "nu"])


def generate(formula: str) -> Optional[Dict]:
    """Combustion incompleta — variante 'todo a CO'.

    Args:
        formula: formula molecular.

    Returns:
        dict similar al de combustion_complete o None si no aplica.
    """
    counts = _parse_formula_chnos(formula)
    a = counts.get("C", 0)
    b = counts.get("H", 0)
    c = counts.get("O", 0)
    if a == 0 or b == 0:
        return None
    # La variante simple solo balancea C/H/O: un compuesto con N, S u
    # otro heteroátomo daría una reaccion desbalanceada (el N/S no tiene
    # a dónde ir sin productos extra) — esos quedan solo con su
    # combustion COMPLETA, que sí los maneja.
    if any(el not in ("C", "H", "O") for el in counts):
        return None
    n_O2 = a/2.0 + b/4.0 - c/2.0
    if n_O2 <= 0:
        return None

    # Escalar al primer factor que deja TODOS los coeficientes enteros
    # (b/4 exige hasta ×4; con ×2 un b impar truncaba el O2).
    scale = 1
    for s in (1, 2, 4):
        if all(v * s % 1 == 0 for v in (n_O2, b / 2.0)):
            scale = s
            break
    n_O2_int = int(round(n_O2 * scale))
    a_int = int(a * scale)
    b_int = int((b/2.0) * scale)

    stoich = [
        SE(formula=formula, phase="g", nu=-scale),
        SE(formula="O2", phase="g", nu=-n_O2_int),
        SE(formula="CO", phase="g", nu=a_int),
    ]
    if b_int > 0:
        stoich.append(SE(formula="H2O", phase="g", nu=b_int))

    return {
        "name": f"Combustion incompleta de {formula} (a CO)",
        "stoich": stoich,
        "T_min_K": 700.0,
        "T_max_K": 2500.0,
        "category": "combustion_incomplete",
        "comments": (
            f"Auto-generada T13 variante 1: deficit de O2, todos los C "
            f"van a CO en vez de CO2. Confidence MEDIA — relacion "
            f"CO/CO2 real depende de lambda (aire/combustible)."
        ),
    }
