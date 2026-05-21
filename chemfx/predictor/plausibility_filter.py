"""Filtros de plausibilidad para reacciones predichas (§7.3).

Decision D02 del doc: el predictor NO descarta por Keq < 1 — solo
marca favorable_at_T=False. Los filtros son:

  Filtro 1 — balance atomico: la estequiometria debe cerrar (sino es
             bug del template, no del input).
  Filtro 2 — rango T del mecanismo: si T_K esta fuera del rango del
             template, la reaccion no aplica en este equipo.
  Filtro 3 — especies requeridas: si el template necesita reactantes
             que no estan en el feed, descartar.
  Filtro 4 — dedupe estructural: no proponer la misma reaccion con
             isomeros duplicados (e.g. T01 entre acetic_acid+ethanol
             dos veces porque hay dos formas de mapear los atomos).
"""
from __future__ import annotations

from typing import List, Tuple, Set
import re

from chemfx.predictor.types import PredictedReaction, Confidence


def _atom_count_from_formula(formula: str) -> dict:
    """Cuenta atomos de una formula molecular tipo 'C6H12O6'."""
    counts: dict = {}
    for m in re.finditer(r"([A-Z][a-z]?)(\d*)", formula):
        elem, num = m.group(1), m.group(2)
        if not elem:
            continue
        counts[elem] = counts.get(elem, 0) + (int(num) if num else 1)
    return counts


def atom_balance_closes(stoichiometry: List, tol: float = 1e-6) -> bool:
    """Verifica que la estequiometria conserve atomos.

    stoichiometry: lista de StoichEntry (reactions_db) o equivalente
    con campos .formula y .nu (negativo reactante, positivo producto).
    """
    if not stoichiometry:
        return True
    total: dict = {}
    for sp in stoichiometry:
        formula = getattr(sp, "formula", "") or ""
        nu = getattr(sp, "nu", 0)
        if not formula or nu == 0:
            continue
        for elem, n in _atom_count_from_formula(formula).items():
            total[elem] = total.get(elem, 0.0) + nu * n
    return all(abs(v) < tol for v in total.values())


def is_in_T_range(rxn: PredictedReaction, T_K: float) -> bool:
    """True si T_K cae en el rango de T del template."""
    Tmin, Tmax = rxn.T_range_K
    return Tmin <= T_K <= Tmax


def has_required_species(rxn: PredictedReaction,
                         feed_compounds: List[str]) -> bool:
    """True si todos los reactantes (nu<0) del rxn estan en el feed.

    Permite producto-en-feed (un producto puede ser tambien reactante
    si la reaccion es reversible — no descartar por eso)."""
    feed_set = {c.lower() for c in feed_compounds}
    for sp in rxn.stoichiometry:
        nu = getattr(sp, "nu", 0)
        if nu < 0:    # reactante
            name = (getattr(sp, "thermo_name", None) or
                    getattr(sp, "formula", "") or "")
            name = str(name).lower()
            if name and name not in feed_set:
                return False
    return True


def is_plausible(rxn: PredictedReaction,
                 T_K: float,
                 P_bar: float = 1.0,
                 feed_compounds: List[str] = None) -> Tuple[bool, str]:
    """Aplica los 4 filtros. Devuelve (ok, razon_si_no).

    Returns:
        (True, '') si pasa todos los filtros.
        (False, '<razon>') si alguno falla.
    """
    # Filtro 1
    if not atom_balance_closes(rxn.stoichiometry):
        return False, "balance atomico no cierra (template buggy)"
    # Filtro 2
    if not is_in_T_range(rxn, T_K):
        return False, (
            f"T={T_K:.0f}K fuera del rango "
            f"{rxn.T_range_K[0]:.0f}-{rxn.T_range_K[1]:.0f}K del mecanismo"
        )
    # Filtro 3
    if feed_compounds is not None and not has_required_species(rxn, feed_compounds):
        return False, "reactantes requeridos no estan en el feed"
    # Filtro 4 lo aplica rank_reactions (dedup post-ranking)
    return True, ""


def _structural_signature(rxn: PredictedReaction) -> str:
    """Firma para dedupe estructural. Templates iguales con productos
    iguales (en cualquier orden) → misma firma."""
    products: Set[str] = set()
    reactants: Set[str] = set()
    for sp in rxn.stoichiometry:
        formula = getattr(sp, "formula", "") or ""
        nu = getattr(sp, "nu", 0)
        if not formula:
            continue
        if nu > 0:
            products.add(formula)
        elif nu < 0:
            reactants.add(formula)
    return f"{rxn.transformation_id}|R={sorted(reactants)}|P={sorted(products)}"


def deduplicate(reactions: List[PredictedReaction]) -> List[PredictedReaction]:
    """Quita duplicados estructurales (Filtro 4)."""
    seen: Set[str] = set()
    out: List[PredictedReaction] = []
    for r in reactions:
        sig = _structural_signature(r)
        if sig not in seen:
            seen.add(sig)
            out.append(r)
    return out


def _conf_rank(c: Confidence) -> int:
    """Para ordenar: ALTA > MEDIA > BAJA."""
    return {Confidence.ALTA: 0, Confidence.MEDIA: 1, Confidence.BAJA: 2}.get(c, 3)


def rank_reactions(reactions: List[PredictedReaction]) -> List[PredictedReaction]:
    """Ordena por (favorable, confidence, |log Keq|).

    Criterios (en orden lexicografico):
      1. favorable_at_T desc (favorables primero)
      2. confidence_mechanism asc por rank (ALTA primero)
      3. |Keq| desc (mayor magnitud primero — mas espontanea)

    Dedupe estructural antes del orden (no proponer la misma rxn
    dos veces por isomeros)."""
    deduped = deduplicate(reactions)
    import math
    def _key(r: PredictedReaction):
        return (
            not r.favorable_at_T,                  # False (0) > True (1) → favs primero
            _conf_rank(r.confidence_mechanism),    # ALTA primero
            -math.log10(max(abs(r.keq_at_T), 1e-30)),   # |Keq| grande → menor key
        )
    return sorted(deduped, key=_key)
