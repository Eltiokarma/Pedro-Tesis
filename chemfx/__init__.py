"""
chemfx — Reaction predictor + auto-reactions + reactivity engine.

Capa 4b del simulador: prediccion de reacciones quimicas plausibles
para cualquier combinacion de compuestos del thermo_db, con templates
SMARTS, estimacion termodinamica Joback/Benson, y motor de reactividad
por equipo.

Estado actual: Fase 0 (estructura + dataclasses). Fases 1-9 pendientes
(functional groups, Joback, Benson, transformations T01-T20, predictor,
auto-reactions, reactivity engine, UI, integracion).

Importar componentes (cuando esten implementados):
    from chemfx.predictor import reaction_predictor
    from chemfx.predictor.types import (
        FunctionalGroup, TransformationTemplate, PredictedReaction,
        ThermoEstimate, FeedAnalysis, DangerWarning, Confidence, Origin,
    )
    from chemfx.defaults import ALLOW_REACTIONS_DEFAULTS

Filosofia:
  - RDKit es la libreria preferida (D07) pero TODO el modulo debe degradar
    con fallback manual si RDKit no esta disponible.
  - Fallar silenciosamente (None / lista vacia) ante input que no se puede
    procesar.
  - Fallar ruidosamente solo ante bugs internos.
"""

# Flag opcional: RDKit disponible o no. Las funciones que dependen
# de RDKit deben chequear este flag y caer a fallback manual.
try:
    import rdkit  # noqa: F401
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False
