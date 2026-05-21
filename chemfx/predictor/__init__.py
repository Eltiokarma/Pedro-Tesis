"""Predictor de reacciones (Capa 4b).

Modulos:
  - types: dataclasses publicos (FunctionalGroup, TransformationTemplate,
           ThermoEstimate, PredictedReaction, FeedAnalysis, DangerWarning,
           Suggestion, Confidence, Origin)
  - functional_groups: deteccion de grupos via SMARTS + fallback manual
  - transformations: tabla de templates T01-T20
  - joback: estimador Joback (ΔHf°, ΔS°, Cp)
  - benson: estimador Benson (override mas preciso)
  - thermo_estimator: fachada que elige Joback/Benson/Hess
  - product_builder: aplica template, construye producto, persiste
  - iupac_namer: SMILES → nombre
  - reaction_predictor: API principal predict_reactions(feed, T, P)
  - plausibility_filter: filtros (balance, T range, etc.)
  - confidence_tagger: asigna ALTA/MEDIA/BAJA
"""

from chemfx.predictor.types import (
    Confidence,
    Origin,
    FunctionalGroup,
    TransformationTemplate,
    ThermoEstimate,
    PredictedReaction,
    FeedAnalysis,
    DangerWarning,
    Suggestion,
)

__all__ = [
    "Confidence", "Origin",
    "FunctionalGroup", "TransformationTemplate", "ThermoEstimate",
    "PredictedReaction", "FeedAnalysis", "DangerWarning", "Suggestion",
]
