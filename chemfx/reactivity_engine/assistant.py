"""Asistente proactivo (Capa 5b §5.14, decision D09 Filosofia B).

Sugiere al usuario activar el toggle 'allow_reactions' en equipos
donde el predictor detecta reactantes complementarios + condiciones
favorables (T, P, tau).

Casos cubiertos:
  - Mezclador con alcohol + acido a T>320K → sugerir T01 esterificacion
  - Columna de destilacion con reactantes complementarios → sugerir
    modo reactivo
  - HX a T_pared > 600K → sugerir evaluar cracking
  - Stream con tau > 60s y T > 200°C → sugerir activar predictor
"""
from __future__ import annotations

from typing import List, Optional

from chemfx.predictor.types import FeedAnalysis, Suggestion


def generate_suggestions(
    feed_analysis: FeedAnalysis,
    eq_type: str = "",
    allow_reactions: bool = False,
    block_name: str = "",
) -> List[Suggestion]:
    """Genera sugerencias proactivas para un bloque/stream.

    Args:
        feed_analysis: resultado de predict_reactions.
        eq_type: tipo de equipo ('Mixer — static', etc.).
        allow_reactions: estado actual del toggle.
        block_name: nombre del bloque (e.g. 'M-101').

    Returns: lista de Suggestion.
    """
    sugs: List[Suggestion] = []
    location = block_name or eq_type or "(unknown)"

    # Si allow_reactions ya esta True, no hay nada que sugerir.
    if allow_reactions:
        return sugs

    n_predicted_favorable = sum(
        1 for r in feed_analysis.predicted if r.favorable_at_T
    )
    n_predicted_total = len(feed_analysis.predicted)
    n_curated_applicable = len(feed_analysis.curated)
    T = feed_analysis.T_K
    tau = feed_analysis.tau_s

    is_mixer = "Mixer" in eq_type
    is_column = ("Tower" in eq_type or "column" in eq_type.lower()
                 or "distillation" in eq_type.lower())
    is_hx = "Heat exch" in eq_type
    is_tank = "tank" in eq_type.lower() or "Vessel" in eq_type
    is_stream = eq_type.lower() == "stream"

    # Caso 1: Mezclador con reactantes complementarios a T>320 K
    if is_mixer and n_predicted_favorable > 0 and T > 320:
        rxn_ids = [r.id for r in feed_analysis.predicted
                   if r.favorable_at_T][:3]
        sugs.append(Suggestion(
            location=location,
            suggested_action="enable_allow_reactions",
            reasoning=(
                f"El mezclador a {T:.0f}K detecta {n_predicted_favorable} "
                f"reacciones favorables. Si la mezcla permanece > 1 min "
                f"a esta T, la reaccion progresa parcialmente. Activar "
                f"el predictor para incluir en el balance."
            ),
            suggested_reactions=rxn_ids,
        ))

    # Caso 2: Columna destilacion con reactantes complementarios
    if is_column and n_predicted_favorable > 0:
        rxn_ids = [r.id for r in feed_analysis.predicted
                   if r.favorable_at_T][:3]
        sugs.append(Suggestion(
            location=location,
            suggested_action="enable_allow_reactions",
            reasoning=(
                f"La columna recibe reactantes que pueden formar productos "
                f"in-situ. Si el reboiler trabaja a >400 K y la columna "
                f"tiene >10 platos, considerar modo destilacion reactiva."
            ),
            suggested_reactions=rxn_ids,
        ))

    # Caso 3: HX a T_pared alta (proxy via T inlet)
    if is_hx and T > 600:
        sugs.append(Suggestion(
            location=location,
            suggested_action="enable_allow_reactions",
            reasoning=(
                f"Intercambiador a T={T:.0f}K: posible cracking termico "
                f"si T_pared > 700°C. Verificar metalurgia y considerar "
                f"el predictor para detectar formacion de coque."
            ),
            suggested_reactions=[],
        ))

    # Caso 4: Stream con tau > 60s y T > 200°C
    if is_stream and tau is not None and tau > 60 and T > 473:
        sugs.append(Suggestion(
            location=location,
            suggested_action="enable_allow_reactions",
            reasoning=(
                f"Tuberia con τ={tau:.0f}s a {T:.0f}K. Tiempo de residencia "
                f"suficiente para reacciones en gas o vapor. Activar el "
                f"predictor sobre el stream para incluir."
            ),
            suggested_reactions=[],
        ))

    # Caso 5: Tanque con τ muy largo
    if is_tank and tau is not None and tau > 3600 and n_predicted_total > 0:
        sugs.append(Suggestion(
            location=location,
            suggested_action="enable_allow_reactions",
            reasoning=(
                f"Tanque con τ={tau/3600:.1f} h. Aunque T sea baja, "
                f"reacciones lentas pueden completarse durante el "
                f"almacenamiento. Considerar el predictor para detectar."
            ),
            suggested_reactions=[],
        ))

    return sugs
