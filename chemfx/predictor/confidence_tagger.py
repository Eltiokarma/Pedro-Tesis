"""Asignacion de Confidence (ALTA/MEDIA/BAJA) a reacciones predichas.

Reglas (§4.1, §5.5):

confidence_mechanism (que la reaccion realmente ocurre con este set
de reactantes):
    ALTA  — template T01-T07b, T11, T17-T20 (catalogados, mecanismo
            establecido).
    MEDIA — T10 cracking, T13 combustion incompleta, T15 eterificacion
            (productos multiples o competencia).
    BAJA  — T16 aldol (combinatoria de productos), templates con
            reactantes terciarios + competencia.

confidence_thermo (que las propiedades termo estimadas son correctas):
    ALTA  — todos los compuestos en thermo_db con dHf° experimental.
    MEDIA — al menos uno estimado via Joback con uncertainty < 15 kJ/mol.
    BAJA  — alguno estimado con uncertainty > 15 kJ/mol o sin data.
"""
from __future__ import annotations

from typing import List

from chemfx.predictor.types import (
    PredictedReaction, ThermoEstimate, Confidence,
)


# Override por template_id (sin prefix de slug — solo T01, T02, etc.).
_MECHANISM_OVERRIDE = {
    "T10": Confidence.MEDIA,   # cracking — mezcla productos
    "T13": Confidence.MEDIA,   # combustion incompleta — CO/CO2 mix
    "T15": Confidence.MEDIA,   # eterificacion — compite con T08
    "T16": Confidence.BAJA,    # aldol — multiproducto
}


def tag_mechanism(rxn: PredictedReaction) -> Confidence:
    """Asigna confidence_mechanism segun el template_id."""
    tid = rxn.transformation_id or ""
    # Buscar override por prefix exacto T<digits>
    for prefix, conf in _MECHANISM_OVERRIDE.items():
        if tid.startswith(prefix + "_") or tid == prefix:
            return conf
    # Default
    return rxn.confidence_mechanism or Confidence.MEDIA


def tag_thermo(estimates: List[ThermoEstimate]) -> Confidence:
    """Confidence agregada de un conjunto de estimaciones termo.

    Toma el peor caso: si TODO experimental → ALTA. Si algo es Joback
    con error pequeno → MEDIA. Si algo es BAJA → BAJA.
    """
    if not estimates:
        return Confidence.BAJA
    has_baja = any(e.confidence == Confidence.BAJA for e in estimates)
    if has_baja:
        return Confidence.BAJA
    has_media = any(e.confidence == Confidence.MEDIA for e in estimates)
    if has_media:
        return Confidence.MEDIA
    return Confidence.ALTA


def apply_tags(rxn: PredictedReaction) -> PredictedReaction:
    """Asigna confidence_mechanism + confidence_thermo al PredictedReaction
    en-place. Devuelve el mismo objeto."""
    rxn.confidence_mechanism = tag_mechanism(rxn)
    # confidence_thermo se setea desde los ThermoEstimate del rxn
    estimates = [e for e in (
        rxn.delta_h_298, rxn.delta_s_298, rxn.delta_g_298,
        rxn.delta_h_at_T,
    ) if e is not None]
    rxn.confidence_thermo = tag_thermo(estimates)
    return rxn
