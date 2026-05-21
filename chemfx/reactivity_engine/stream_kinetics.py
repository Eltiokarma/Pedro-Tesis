"""Reactividad en streams (tuberias) — Capa 5b §5.12.

Calcula tau de residencia desde geometria de la tuberia y mass_flow,
y llama predict_reactions con ese tau.

Solo aplica si:
  - stream.pipe_length_m > 0
  - stream.pipe_diameter_m > 0
  - stream.mass_flow > 0

Si tau < 1 s, descarta (no hay tiempo para reaccion).
"""
from __future__ import annotations

import math
import logging
from typing import Optional

from chemfx.predictor.types import FeedAnalysis
from chemfx.predictor import reaction_predictor
from chemfx.reactivity_engine import danger_detector

logger = logging.getLogger(__name__)


def calculate_residence_time(stream, density_kg_m3: float = 1.0) -> Optional[float]:
    """Tiempo de residencia [s] de un fluido en una tuberia.

    τ = L · A_cross · ρ / m_dot
    donde A_cross = π/4 · D²

    Args:
        stream: flowsheet_model.Stream con pipe_length_m, pipe_diameter_m,
                mass_flow [tm/año o kg/s segun el modelo].
        density_kg_m3: densidad de la mezcla. Default 1 kg/m³ (gas ideal
                ~aire), debe pasarse el valor real desde el solver.

    Returns: tau en segundos, o None si falta data.
    """
    L = float(getattr(stream, "pipe_length_m", 0.0) or 0.0)
    D = float(getattr(stream, "pipe_diameter_m", 0.0) or 0.0)
    m = float(getattr(stream, "mass_flow", 0.0) or 0.0)
    # mass_flow del flowsheet esta en tm/año (1 tm = 1000 kg, 1 año = 3.156e7 s)
    if L <= 0 or D <= 0 or m <= 0 or density_kg_m3 <= 0:
        return None
    A_cross = math.pi / 4.0 * D * D    # m²
    V_pipe = L * A_cross               # m³
    m_dot_kg_s = m * 1000.0 / 3.156e7  # kg/s
    if m_dot_kg_s <= 0:
        return None
    Q_m3_s = m_dot_kg_s / density_kg_m3
    if Q_m3_s <= 0:
        return None
    tau = V_pipe / Q_m3_s
    return float(tau)


def evaluate_stream(
    stream,
    density_kg_m3: float = 1.0,
    min_tau_s: float = 1.0,
) -> Optional[FeedAnalysis]:
    """Pipeline para evaluar reactividad en un stream.

    Args:
        stream: Stream con composition + T + P + geometria.
        density_kg_m3: densidad del fluido (de thermo_db).
        min_tau_s: umbral minimo para considerar el stream reactivo.

    Returns: FeedAnalysis o None si tau < min_tau_s (no reactivo).
    """
    # Calcular tau o usar el explicito del stream
    tau = float(getattr(stream, "residence_time_s", 0.0) or 0.0)
    if tau <= 0:
        tau = calculate_residence_time(stream, density_kg_m3) or 0.0
    if tau < min_tau_s:
        return None

    # Aggregate composition
    comp = getattr(stream, "composition", None) or {}
    feed = list(comp.keys())
    main = getattr(stream, "main_component", "")
    if main and main not in feed:
        feed.append(main)
    if not feed:
        return None

    T_C = float(getattr(stream, "temperature", 25.0))
    T_K = T_C + 273.15
    P_bar = float(getattr(stream, "pressure_bar", 1.013) or 1.013)

    try:
        fa = reaction_predictor.predict_reactions(
            feed_compounds=feed, T_K=T_K, P_bar=P_bar, tau_s=tau,
        )
    except Exception as e:
        logger.debug(f"predict_reactions fallo en stream {stream}: {e}")
        return None

    # Warnings de peligros (especialmente combustion espontanea en pipes
    # con O2 + combustible a alta T)
    location = getattr(stream, "name", "stream")
    fa.warnings = danger_detector.detect_dangers(
        fa, location=location, block_tau_s=tau,
    )
    return fa
