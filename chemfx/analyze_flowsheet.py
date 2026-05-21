"""Analizador pasivo de flowsheet — Fase 7b opcion (a).

Recorre TODOS los bloques de un Flowsheet, llama a evaluate_block,
guarda el FeedAnalysis en block.feed_analysis_cache (como dict
serializable) y las warnings en block.reaction_warnings.

NO modifica el solver ni el balance. Es 100% lectura/anotacion.
Pensado para ejecutarse DESPUES de flowsheet_solver.solve().

USO:
    import chemfx
    # ... cargar fs, correr fsolv.solve(fs) ...
    chemfx.analyze_flowsheet(fs)
    # Ahora block.reaction_warnings y block.feed_analysis_cache estan
    # poblados para que la UI los lea.

Costo: lineal en numero de bloques. Para 20 bloques y feeds tipicos,
< 2s incluso sin RDKit (curated solo).
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from chemfx.reactivity_engine import equipment_reactivity
from chemfx.predictor.types import FeedAnalysis, DangerWarning, Suggestion

logger = logging.getLogger(__name__)


def _feed_analysis_to_dict(fa: FeedAnalysis) -> Dict:
    """Serializa un FeedAnalysis a dict para guardar en block.

    No serializa los objetos Reaction/PredictedReaction completos (son
    voluminosos y la UI puede recomputarlos). Guarda solo lo esencial
    para mostrar al user: IDs, names, confidences."""
    def _conf_str(c):
        return c.value if hasattr(c, "value") else str(c)

    return {
        "compounds": list(fa.compounds),
        "T_K": fa.T_K,
        "P_bar": fa.P_bar,
        "tau_s": fa.tau_s,
        "n_curated": len(fa.curated),
        "n_auto": len(fa.auto),
        "n_predicted": len(fa.predicted),
        "n_warnings": len(fa.warnings),
        "n_suggestions": len(fa.assistant_suggestions),
        "curated_ids": [getattr(r, "id", "") for r in fa.curated[:20]],
        "curated_names": [getattr(r, "name", "") for r in fa.curated[:20]],
        "predicted_summary": [
            {
                "id": r.id,
                "transformation_id": r.transformation_id,
                "display_label": r.display_label,
                "keq_at_T": r.keq_at_T,
                "favorable_at_T": r.favorable_at_T,
                "confidence_mechanism": _conf_str(r.confidence_mechanism),
                "confidence_thermo": _conf_str(r.confidence_thermo),
                "requires_catalyst": r.requires_catalyst,
                "catalyst_hint": r.catalyst_hint,
            }
            for r in fa.predicted[:20]   # top 20 ranked
        ],
        "warnings": [
            {
                "reaction_id": w.reaction_id,
                "location": w.location,
                "risk_category": w.risk_category,
                "severity": w.severity,
                "message": w.message,
                "keq_at_T": w.keq_at_T,
                "delta_h_kJ_mol": w.delta_h_kJ_mol,
            }
            for w in fa.warnings
        ],
        "suggestions": [
            {
                "location": s.location,
                "suggested_action": s.suggested_action,
                "reasoning": s.reasoning,
                "suggested_reactions": list(s.suggested_reactions),
            }
            for s in fa.assistant_suggestions
        ],
    }


def analyze_flowsheet(fs, only_warnings: bool = False) -> Dict[int, Dict]:
    """Analiza todos los bloques del flowsheet (modo pasivo).

    Args:
        fs: Flowsheet (con bloques + streams ya populados).
        only_warnings: si True, solo guarda warnings (saltea predicciones).
                       Util para flowsheets grandes donde no se quiere
                       el costo de predict_reactions completo.

    Returns: dict {block_id: feed_analysis_dict_serializado} con los
    resultados. Tambien escribe block.feed_analysis_cache y
    block.reaction_warnings en cada Block.

    No modifica streams ni balances.
    """
    results: Dict[int, Dict] = {}
    if not hasattr(fs, "blocks") or not hasattr(fs, "streams"):
        return results

    for bid, block in fs.blocks.items():
        # Inlet streams: src del block tiene id = bid en algun stream
        inlets = [s for s in fs.streams.values()
                  if getattr(s, "dst", -1) == bid]
        try:
            fa = equipment_reactivity.evaluate_block(block, inlets, fs)
        except Exception as e:
            logger.debug(f"evaluate_block({block}) fallo: {e}")
            continue

        fa_dict = _feed_analysis_to_dict(fa)
        results[bid] = fa_dict

        # Anotar en el block (campos ya existentes en flowsheet_model.Block)
        try:
            block.reaction_warnings = fa_dict.get("warnings", [])
            if not only_warnings:
                block.feed_analysis_cache = fa_dict
        except Exception as e:
            logger.debug(f"Failed to annotate block {bid}: {e}")
    return results


def summarize_warnings(fs) -> List[Dict]:
    """Devuelve la lista total de warnings de TODOS los bloques.

    Util para el panel global de warnings de la UI.
    """
    out: List[Dict] = []
    for bid, block in fs.blocks.items():
        for w in getattr(block, "reaction_warnings", []) or []:
            entry = dict(w) if isinstance(w, dict) else {}
            entry["block_id"] = bid
            entry["block_name"] = getattr(block, "name", "")
            out.append(entry)
    # Ordenar por severidad: critical > high > medium > low
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    out.sort(key=lambda w: severity_order.get(w.get("severity", "medium"), 4))
    return out
