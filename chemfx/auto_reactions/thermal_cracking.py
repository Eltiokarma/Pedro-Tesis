"""Generador de cracking termico (T10).

Para alcanos C_n con n >= 3:
    C_n H_(2n+2) → C_(n-k) H_(2(n-k)+2) (alcano corto) + C_k H_(2k) (alqueno)

Generamos UNA variante representativa por compuesto: corte en el medio
(n_alcano = n/2 o (n-1)/2, n_alqueno = n - n_alcano).

Confidence MEDIA porque la distribucion de productos del cracking real
depende fuertemente de la cinetica radicalaria; este es solo un
representante de la familia de productos.
"""
from __future__ import annotations

from collections import namedtuple
from typing import Dict, List, Optional

from chemfx.auto_reactions.combustion_complete import _parse_formula_chnos


SE = namedtuple("SE", ["formula", "phase", "nu"])


def _is_pure_alkane(counts: Dict[str, int]) -> bool:
    """True si la formula es C_n H_(2n+2) (alcano puro lineal o ramificado)."""
    if "C" not in counts or "H" not in counts:
        return False
    if len([e for e in counts if e not in ("C", "H")]) > 0:
        return False
    n = counts["C"]
    return counts["H"] == 2 * n + 2 and n >= 3


def generate(formula: str) -> Optional[Dict]:
    """Cracking termico — corte en el medio.

    Args:
        formula: 'C4H10', 'C8H18', etc. Debe ser alcano puro C >= 3.

    Returns:
        dict con stoich del cracking, o None si no aplica.
    """
    counts = _parse_formula_chnos(formula)
    if not _is_pure_alkane(counts):
        return None
    n = counts["C"]
    # Cortar en el medio
    n_alcano = n // 2
    n_alqueno = n - n_alcano
    if n_alcano < 1 or n_alqueno < 2:
        return None    # alqueno necesita al menos C2

    # Alcano corto: C_n_alcano H_(2*n_alcano+2)
    alcano_formula = f"C{n_alcano}H{2*n_alcano + 2}" if n_alcano > 1 else "CH4"
    # Alqueno: C_n_alqueno H_(2*n_alqueno)
    alqueno_formula = f"C{n_alqueno}H{2*n_alqueno}"

    # NOTA: solo agregamos H2 si los carbonos no balancean los H.
    # Para C_n → C_k + C_(n-k) con cracking simple:
    #   alcano: 2*k+2 H
    #   alqueno: 2*(n-k) H
    # total: 2*k+2 + 2*(n-k) = 2n+2 H ✓ (no necesita H2 extra)
    stoich = [
        SE(formula=formula, phase="g", nu=-1),
        SE(formula=alcano_formula, phase="g", nu=1),
        SE(formula=alqueno_formula, phase="g", nu=1),
    ]

    return {
        "name": f"Cracking termico de {formula} (representante)",
        "stoich": stoich,
        "T_min_K": 1000.0,
        "T_max_K": 1400.0,
        "category": "cracking",
        "comments": (
            f"Auto-generada T10: {formula} -> {alcano_formula} + "
            f"{alqueno_formula}. Confidence MEDIA — distribucion real "
            f"de productos depende de cinetica radicalaria (β-scission)."
        ),
    }
