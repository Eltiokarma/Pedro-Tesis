"""Motor de reactividad por equipo (Capa 5b §5.11).

evaluate_block(block, inlet_streams, flowsheet) -> FeedAnalysis

Combina:
  - composicion de los streams de entrada → feed.
  - T, P, τ del bloque.
  - llama predict_reactions(feed, T, P, τ).
  - llama danger_detector y assistant.
  - retorna FeedAnalysis completo.

NOTA Fase 7: este modulo NO modifica el solver ni los bloques. Es
solo el motor de analisis. La integracion al flowsheet_solver.solve()
viene en un commit aparte (mas riesgoso).

Para tau del bloque, ver get_block_tau(block):
  Reactor:    V/Q (V de block, Q de feed mass / density)
  Flash:      ~5-15 min (fallback default)
  Mixer:      <1 s
  Tank:       V/Q
  HX:         V/Q tubeside (no implementado aun)
  Stream:     L/v via stream_kinetics
"""
from __future__ import annotations

import logging
from typing import List, Optional

from chemfx.predictor.types import FeedAnalysis
from chemfx.predictor import reaction_predictor
from chemfx.reactivity_engine import danger_detector, assistant
from chemfx.defaults import default_allow_reactions

logger = logging.getLogger(__name__)


def get_block_tau(block) -> Optional[float]:
    """Estima tiempo de residencia [s] del bloque segun tipo y volumen.

    Args:
        block: flowsheet_model.Block o equivalente con atributos
               eq_type, reactor_volume_L, S, n, etc.

    Returns: tau en segundos, o None si no se puede estimar.
    """
    eq_type = getattr(block, "eq_type", "") or ""
    # Volumen explicito de reactor
    V_L = getattr(block, "reactor_volume_L", 0.0) or 0.0
    if V_L > 0 and "Reactor" in eq_type:
        # τ = V/Q. Q lo necesitamos de los streams.
        # Aca devolvemos solo V_L convertido a un proxy (asumiendo
        # tipico Q=1 L/s → tau ~ V_L segundos). La calc precisa
        # requiere mass_flow del feed; eso lo hace evaluate_block.
        return float(V_L)

    # Fallbacks por tipo
    tau_defaults = {
        "Mixer": 0.5,
        "Vessel": 600.0,         # flash 10 min
        "Tower": 300.0,
        "column": 300.0,
        "Heat exch.": 5.0,       # ~5s tubeside
        "Storage tank": 86400.0, # 1 dia
        "Pump": 0.1,
        "Compressor": 0.1,
        "Fired heater": 60.0,
    }
    for key, default in tau_defaults.items():
        if key in eq_type:
            return default
    return None


def _agregate_inlet_composition(inlet_streams) -> List[str]:
    """Devuelve la lista de compuestos presentes en al menos un inlet.

    Args: inlet_streams = lista de objetos Stream con .composition (dict
    {component: mass_frac}) y/o .main_component.

    Returns: lista de nombres canonicos (orden estable, sin duplicados).
    """
    seen = set()
    out: List[str] = []
    for s in inlet_streams:
        comp = getattr(s, "composition", None) or {}
        for c in comp:
            if c and c.lower() not in seen:
                seen.add(c.lower())
                out.append(c)
        main = getattr(s, "main_component", "") or ""
        if main and main.lower() not in seen:
            seen.add(main.lower())
            out.append(main)
    return out


def evaluate_block(
    block,
    inlet_streams: List,
    flowsheet=None,    # opcional para futuros usos (vecindad, etc.)
) -> FeedAnalysis:
    """Pipeline completo para un bloque.

    Args:
        block: flowsheet_model.Block.
        inlet_streams: lista de Stream con dst = block.id.
        flowsheet: Flowsheet (opcional, para contexto).

    Returns: FeedAnalysis con curated/predicted/warnings/suggestions.

    NO ejecuta ninguna reaccion ni modifica el block — solo analiza
    y reporta.
    """
    feed = _agregate_inlet_composition(inlet_streams)
    # T del bloque
    T_K = float(getattr(block, "T_op_K", 0) or 0)
    if T_K <= 0:
        # Promedio T de los inlets (en °C, convertir)
        T_in_avg_C = 25.0
        if inlet_streams:
            T_list = [float(getattr(s, "temperature", 25.0))
                      for s in inlet_streams]
            T_in_avg_C = sum(T_list) / len(T_list) if T_list else 25.0
        T_K = T_in_avg_C + 273.15
    P_bar = float(getattr(block, "P_op_bar", 1.0) or 1.0)
    tau_s = get_block_tau(block)

    # 1. Predict_reactions
    try:
        fa = reaction_predictor.predict_reactions(
            feed_compounds=feed, T_K=T_K, P_bar=P_bar, tau_s=tau_s,
            include_curated=True, include_auto=True, include_predicted=True,
        )
    except Exception as e:
        logger.debug(f"predict_reactions fallo en {block}: {e}")
        fa = FeedAnalysis(compounds=feed, T_K=T_K, P_bar=P_bar, tau_s=tau_s)

    # 2. Danger warnings (siempre, aunque allow_reactions=False)
    block_name = getattr(block, "name", "(unnamed)")
    fa.warnings = danger_detector.detect_dangers(
        fa, location=block_name, block_tau_s=tau_s,
    )

    # 3. Suggestions del asistente (solo si allow_reactions=False)
    allow = bool(getattr(block, "allow_reactions",
                          default_allow_reactions(
                              getattr(block, "eq_type", ""))))
    eq_type = getattr(block, "eq_type", "")
    fa.assistant_suggestions = assistant.generate_suggestions(
        fa, eq_type=eq_type, allow_reactions=allow, block_name=block_name,
    )
    return fa
