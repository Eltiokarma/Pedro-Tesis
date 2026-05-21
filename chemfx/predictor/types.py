"""Tipos publicos del predictor (Capa 4b).

Dataclasses inmutables (frozen=False para permitir mutacion controlada,
pero ningun consumidor debe mutar fuera del modulo que los creo).

Estructura segun §4 de la arquitectura del predictor.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any


# ======================================================
# ENUMS
# ======================================================
class Confidence(Enum):
    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


class Origin(Enum):
    CURATED = "curated"        # 25 reacciones literatura
    AUTO = "auto"              # generadas mecanicamente (combustiones, cracking)
    PREDICTED = "predicted"    # generadas por templates + Joback/Benson


# ======================================================
# DATACLASSES — entidades del predictor
# ======================================================
@dataclass
class FunctionalGroup:
    """Un grupo funcional detectado en un compuesto.

    Args:
        name: 'alcohol_primario', 'acido_carboxilico', etc.
        smarts: patron SMARTS si vino de RDKit (vacio si fue manual).
        atoms_match: indices de atomos en la molecula (vacio si fallback).
        count: cuantas veces aparece el grupo en la molecula.
    """
    name: str
    smarts: str = ""
    atoms_match: Tuple[int, ...] = field(default_factory=tuple)
    count: int = 1


@dataclass
class TransformationTemplate:
    """Template de una transformacion canonica (T01-T20).

    Args:
        id: 'T01_esterification_fischer' (unico).
        name: nombre legible.
        reactant_groups: grupos requeridos por reactante.
            Cada elemento es una lista de grupos alternativos para ese
            reactante. Ej: [['acido_carboxilico'],
            ['alcohol_primario', 'alcohol_secundario', 'alcohol_terciario']].
        product_groups: grupos esperados en productos (informativo).
        stoich_template: patron textual 'A + B -> C + D'.
        reaction_smarts: SMARTS de reaccion (formato RDKit RxnSmarts).
        T_range_K: rango de T donde aplica el mecanismo.
        requires_catalyst: si el template requiere catalizador.
        catalyst_hint: 'H+ acido', 'Cu/ZnO', etc.
        mechanism_confidence: ALTA/MEDIA/BAJA.
        references: libros, papers.
    """
    id: str
    name: str
    reactant_groups: List[List[str]] = field(default_factory=list)
    product_groups: List[List[str]] = field(default_factory=list)
    stoich_template: str = ""
    reaction_smarts: str = ""
    T_range_K: Tuple[float, float] = (298.15, 1000.0)
    requires_catalyst: bool = False
    catalyst_hint: str = ""
    mechanism_confidence: Confidence = Confidence.MEDIA
    references: List[str] = field(default_factory=list)


@dataclass
class ThermoEstimate:
    """Resultado de una estimacion termodinamica.

    Args:
        value: valor estimado [kJ/mol o J/(mol·K), segun campo].
        uncertainty: banda de error estandar (+/-).
        method: 'experimental', 'joback', 'benson', 'hess_from_layer3'.
        confidence: ALTA si experimental o |unc| < 5 kJ/mol; MEDIA si
                    5-15; BAJA si > 15.
    """
    value: float
    uncertainty: float = 0.0
    method: str = "unknown"
    confidence: Confidence = Confidence.MEDIA


@dataclass
class PredictedReaction:
    """Una reaccion predicha lista para evaluacion."""
    id: str
    transformation_id: str
    origin: Origin
    # Estequiometria: list de StoichEntry (tipo de reactions_db).
    # Tipo Any para evitar import circular; el contenido es
    # reactions_db.StoichEntry.
    stoichiometry: List[Any] = field(default_factory=list)
    # Termodinamica
    delta_h_298: Optional[ThermoEstimate] = None
    delta_s_298: Optional[ThermoEstimate] = None
    delta_g_298: Optional[ThermoEstimate] = None
    delta_h_at_T: Optional[ThermoEstimate] = None
    keq_at_T: float = 0.0
    favorable_at_T: bool = False
    # Metadata
    confidence_mechanism: Confidence = Confidence.MEDIA
    confidence_thermo: Confidence = Confidence.MEDIA
    requires_catalyst: bool = False
    catalyst_hint: str = ""
    T_range_K: Tuple[float, float] = (298.15, 1000.0)
    # Productos nuevos
    new_products_introduced: List[str] = field(default_factory=list)
    products_added_to_db: bool = False
    # Display
    display_label: str = ""
    notes: str = ""


@dataclass
class DangerWarning:
    """Advertencia de reaccion peligrosa detectada donde no esta activada."""
    reaction_id: str
    location: str                       # 'M-101', 'S-feed-mixer', etc.
    keq_at_T: float
    delta_h_kJ_mol: float
    risk_category: str                  # 'pyrophoric', 'explosive', 'runaway', 'toxic_product'
    message: str
    severity: str = "medium"            # 'critical' | 'high' | 'medium'


@dataclass
class Suggestion:
    """Sugerencia del asistente proactivo."""
    location: str
    suggested_action: str               # 'enable_allow_reactions'
    reasoning: str
    suggested_reactions: List[str] = field(default_factory=list)


@dataclass
class FeedAnalysis:
    """Analisis completo de un feed: que reacciones detecta el predictor.

    Args:
        compounds: lista de nombres canonicos (thermo_db names).
        T_K: temperatura.
        P_bar: presion.
        tau_s: tiempo de residencia (si aplica, None para mixers).
        curated: reacciones de reactions_db existente aplicables.
        auto: reacciones AUTO generadas aplicables.
        predicted: reacciones PREDICTED detectadas por templates.
        warnings: peligros detectados.
        assistant_suggestions: sugerencias del asistente proactivo.
    """
    compounds: List[str]
    T_K: float
    P_bar: float = 1.0
    tau_s: Optional[float] = None
    # Tipo Any para evitar import circular; contenido = reactions_db.Reaction
    curated: List[Any] = field(default_factory=list)
    auto: List[Any] = field(default_factory=list)
    predicted: List[PredictedReaction] = field(default_factory=list)
    warnings: List[DangerWarning] = field(default_factory=list)
    assistant_suggestions: List[Suggestion] = field(default_factory=list)
