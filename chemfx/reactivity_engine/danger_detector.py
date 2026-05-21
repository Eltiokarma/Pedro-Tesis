"""Detector de reacciones peligrosas (Capa 5b §5.13, decision D11).

Regla: las reacciones PELIGROSAS se reportan siempre como warnings,
incluso si block.allow_reactions = False. La simulacion continua
(no bloquea), pero el user ve el warning en la UI.

Categorias detectadas:
  - 'explosive':  combustion espontanea (Keq>1e20 ∧ ΔH<-200 kJ/mol + O2 en feed)
  - 'pyrophoric': feed con H2 o alcalinos + O2 en condiciones reactivas
  - 'runaway':    ΔH<-300 kJ/mol ∧ τ del bloque grande
  - 'toxic_product': producto en lista negra (HF, HCN, AsH3, fosgeno, etc.)
  - 'polymerization': monomero (estireno, butadieno) + iniciador

Severities:
  'critical' — peligro inmediato (explosion, deflagracion)
  'high'     — riesgo serio (runaway termico controlable)
  'medium'   — atencion requerida (productos toxicos en concentracion baja)
"""
from __future__ import annotations

from typing import List, Optional

from chemfx.predictor.types import (
    FeedAnalysis, DangerWarning, PredictedReaction,
)


# Productos toxicos: SMILES o nombre canonico (thermo_db).
_TOXIC_SMILES = {
    "F",         # ion fluoride (en HF)
    "[C-]#N",    # cianuro
    "C(=O)(Cl)Cl",  # fosgeno COCl2
    "[As]",      # arsenicos
    "[H]N=[N+]=[N-]",   # acida hidrazoica
}
_TOXIC_FORMULAS = {"HF", "HCN", "AsH3", "COCl2", "PH3", "HN3", "B2H6"}

# Monomeros polimerizables
_MONOMERS = {"styrene", "1_3_butadiene", "vinyl_chloride", "acrylonitrile",
             "ethylene_oxide", "methacrylate"}

# Pirofloricos / fuertemente reductores que con O2 son criticos
_PYROPHORIC = {"hydrogen", "ph3", "b2h6", "sih4"}


def _has_compound(feed: List[str], target: str) -> bool:
    target = target.lower()
    return any(c.lower() == target for c in feed)


def _has_any(feed: List[str], targets) -> bool:
    feed_set = {c.lower() for c in feed}
    return bool(feed_set & {t.lower() for t in targets})


def detect_dangers(
    feed_analysis: FeedAnalysis,
    location: str = "(unknown)",
    block_tau_s: Optional[float] = None,
) -> List[DangerWarning]:
    """Identifica reacciones peligrosas en el FeedAnalysis.

    Args:
        feed_analysis: resultado de predict_reactions.
        location: 'M-101', 'S-feed-mixer', etc.
        block_tau_s: tiempo de residencia del bloque (para runaway).

    Returns: lista de DangerWarning (puede estar vacia).
    """
    warns: List[DangerWarning] = []
    feed = feed_analysis.compounds
    has_O2 = _has_compound(feed, "oxygen") or _has_compound(feed, "o2") or \
             _has_compound(feed, "air")
    has_H2 = _has_compound(feed, "hydrogen")

    # 1. Combustion / explosivos (cualquier rxn predicha con
    #    Keq > 1e10 AND dh < -200 AND O2 en feed)
    for rxn in feed_analysis.predicted:
        dh = rxn.delta_h_298.value if rxn.delta_h_298 else 0.0
        if has_O2 and rxn.keq_at_T > 1e10 and dh < -200:
            sev = "critical" if dh < -500 else "high"
            warns.append(DangerWarning(
                reaction_id=rxn.id,
                location=location,
                keq_at_T=rxn.keq_at_T,
                delta_h_kJ_mol=dh,
                risk_category="explosive",
                message=(
                    f"Combustion potencialmente explosiva: "
                    f"ΔH={dh:.0f} kJ/mol, Keq={rxn.keq_at_T:.1e}. "
                    f"Feed contiene O2 + combustible."
                ),
                severity=sev,
            ))

    # 2. Pirofloricos: H2 (o similares) + O2 en condiciones reactivas
    if has_H2 and has_O2 and feed_analysis.T_K > 400:
        warns.append(DangerWarning(
            reaction_id="DANGER_pyrophoric_H2_O2",
            location=location,
            keq_at_T=0.0, delta_h_kJ_mol=-241.8,
            risk_category="pyrophoric",
            message=(
                "H2 + O2 a T>400K: mezcla explosiva (LEL 4%, UEL 75%). "
                "Verificar atmosfera inerte o ventilacion."
            ),
            severity="critical",
        ))
    for pyr in _PYROPHORIC:
        if _has_compound(feed, pyr) and has_O2:
            warns.append(DangerWarning(
                reaction_id=f"DANGER_pyrophoric_{pyr}_O2",
                location=location,
                keq_at_T=0.0, delta_h_kJ_mol=0.0,
                risk_category="pyrophoric",
                message=(
                    f"{pyr} + O2: combinacion piroforica. "
                    f"Ignicion espontanea probable a T ambiente."
                ),
                severity="critical",
            ))

    # 3. Runaway termico: rxn fuertemente exotermica + τ grande
    if block_tau_s is not None and block_tau_s > 60:    # > 1 min
        for rxn in feed_analysis.curated + feed_analysis.predicted:
            dh = getattr(rxn, "dh_rxn_298_kJ_mol", None)
            if dh is None and hasattr(rxn, "delta_h_298") and rxn.delta_h_298:
                dh = rxn.delta_h_298.value
            if dh is not None and dh < -300:
                warns.append(DangerWarning(
                    reaction_id=getattr(rxn, "id", "unknown"),
                    location=location,
                    keq_at_T=getattr(rxn, "keq_at_T", 0.0),
                    delta_h_kJ_mol=dh,
                    risk_category="runaway",
                    message=(
                        f"Reaccion fuertemente exotermica (ΔH={dh:.0f} "
                        f"kJ/mol) con τ={block_tau_s:.0f}s: riesgo de "
                        f"runaway termico. Verificar control de T."
                    ),
                    severity="high",
                ))

    # 4. Productos toxicos
    for rxn in feed_analysis.predicted:
        # Buscar en notes (donde guardamos products_smiles) y stoich
        notes = rxn.notes or ""
        if any(t in notes for t in _TOXIC_SMILES):
            warns.append(DangerWarning(
                reaction_id=rxn.id,
                location=location,
                keq_at_T=rxn.keq_at_T,
                delta_h_kJ_mol=rxn.delta_h_298.value if rxn.delta_h_298 else 0.0,
                risk_category="toxic_product",
                message=(
                    f"Reaccion {rxn.transformation_id} produce especies "
                    f"potencialmente toxicas. Verificar manejo y exposicion."
                ),
                severity="medium",
            ))

    # 5. Polimerizacion (monomero + iniciador / T alta)
    for m in _MONOMERS:
        if _has_compound(feed, m):
            warns.append(DangerWarning(
                reaction_id=f"DANGER_polymerization_{m}",
                location=location,
                keq_at_T=0.0, delta_h_kJ_mol=-80.0,   # tipico
                risk_category="polymerization",
                message=(
                    f"Monomero {m} en feed: riesgo de polimerizacion "
                    f"espontanea (acumulacion termica + escape de control). "
                    f"Verificar inhibidor presente."
                ),
                severity="medium",
            ))
    return warns
