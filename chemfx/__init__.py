"""
chemfx — Reaction predictor + auto-reactions + reactivity engine.

Capa 4b del simulador: prediccion de reacciones quimicas plausibles
para cualquier combinacion de compuestos del thermo_db, con templates
SMARTS, estimacion termodinamica Joback/Benson, y motor de reactividad
por equipo.

ARQUITECTURA v2.0 — HIBRIDA (ver docs/ARQUITECTURA_v2_predictor.md):
  Backend de calculo: libreria 'thermo' (Caleb Bell) — incluye Joback.
  Cheminformatica:    RDKit (SMARTS, reaction SMARTS).
  Trazabilidad:       tablas .md curadas en chemfx/data/ — auditoria
                      manual de los grupos Joback/Benson y SMILES.
  Validacion:         cruzada thermo vs tablas .md, discrepancias
                      reportadas como warning (tolerancia < 1 kJ/mol).

Tres flags de disponibilidad (cada modulo degrada con fallback):
  RDKIT_AVAILABLE     — para SMARTS + reaction SMARTS
  THERMO_AVAILABLE    — para thermo.Joback wrapper
  CHEMICALS_AVAILABLE — para chemicals (NIST data, opcional)

Estado actual: Fase 0 (estructura + dataclasses + data files). Fases
1-9 en progreso (functional groups, Joback wrapper, Benson, templates,
predictor API, auto-reactions, reactivity engine, UI, integracion).

Filosofia:
  - Fallar silenciosamente (None / lista vacia) ante input no procesable.
  - Fallar ruidosamente solo ante bugs internos.
  - Nunca crashear si falta una dependencia opcional: degradar con
    aviso y permitir simulacion normal sin predictor.
"""

# RDKit: cheminformatica (SMARTS, reaction SMARTS, parsing).
try:
    import rdkit  # noqa: F401
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False

# thermo (Caleb Bell): Joback group contribution + propiedades.
try:
    import thermo  # noqa: F401
    THERMO_AVAILABLE = True
except ImportError:
    THERMO_AVAILABLE = False

# chemicals (Caleb Bell): NIST data, propiedades base.
try:
    import chemicals  # noqa: F401
    CHEMICALS_AVAILABLE = True
except ImportError:
    CHEMICALS_AVAILABLE = False


def verify_dependencies():
    """Reporta el estado de las dependencias del predictor.

    Returns:
        dict {nombre_dependencia: bool}. El predictor puede correr con
        cualquier subset; modulos que requieren una dep faltante degradan
        a fallback manual o devuelven None.
    """
    return {
        "rdkit": RDKIT_AVAILABLE,
        "thermo": THERMO_AVAILABLE,
        "chemicals": CHEMICALS_AVAILABLE,
    }


# Entry point publico para analisis pasivo (Fase 7b opcion a):
# corre evaluate_block sobre todos los bloques del flowsheet despues
# de que el solver termino. NO modifica el balance.
from chemfx.analyze_flowsheet import (
    analyze_flowsheet, summarize_warnings,
)
