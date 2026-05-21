"""API principal del predictor de reacciones (Capa 4b §5.8).

predict_reactions(feed_compounds, T_K, P_bar, tau_s) -> FeedAnalysis

Pipeline:
  1. Para cada compuesto del feed: detectar grupos funcionales via
     functional_groups.detect_groups (con SMILES de smiles_loader).
  2. Cargar templates T01-T20 aplicables al T_K (filtro por rango).
  3. Cargar reactions_db.Reaction.find_by_species — para cada compuesto
     del feed, encontrar reacciones curadas que lo involucran.
  4. Para cada template aplicable + combinacion de reactantes:
       a. apply_to_compounds → productos SMILES (RDKit).
       b. Estimar termodinamica via thermo_estimator.
       c. Construir PredictedReaction.
       d. Filtrar via plausibility_filter (rango T, balance, especies).
       e. Taggear confidence via confidence_tagger.
  5. Rankear, dedupe.
  6. Retornar FeedAnalysis.

Limitaciones Fase 5:
  - auto-reactions (combustion/cracking generados): Fase 6.
  - danger_detector + assistant: Fase 7.
  - product_builder + IUPAC namer no estan integrados — los productos
    quedan como SMILES en notes (no se persisten en thermo_db).
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Tuple

from chemfx import RDKIT_AVAILABLE
from chemfx.predictor.types import (
    Confidence, Origin,
    FunctionalGroup, FeedAnalysis,
    PredictedReaction, TransformationTemplate,
    DangerWarning, Suggestion,
)
from chemfx.predictor import (
    functional_groups, transformations,
    smiles_loader, thermo_estimator,
    plausibility_filter, confidence_tagger,
)

logger = logging.getLogger(__name__)


# ======================================================
# CURATED (de reactions_db) — busqueda por especie del feed
# ======================================================
def _find_curated_for_feed(feed_compounds: List[str], T_K: float) -> List:
    """Busca reacciones curadas en reactions_db.md que involucren al
    menos un compuesto del feed y aplican a T_K."""
    try:
        import reactions_db as _rdb
    except ImportError:
        return []

    feed_set = {c.lower() for c in feed_compounds}
    matched = set()
    matched_rxns = []

    # Iterar todas las reacciones del catalogo
    try:
        all_ids = _rdb.list_ids()
    except Exception:
        return []

    for rxn_id in all_ids:
        rxn = _rdb.get(rxn_id)
        if rxn is None:
            continue
        # T range check
        T_min = getattr(rxn, "T_min_K", 0)
        T_max = getattr(rxn, "T_max_K", 10000)
        if not (T_min <= T_K <= T_max):
            continue
        # Verificar que TODOS los reactantes (nu<0) esten en el feed
        # Y que la reaccion tenga AL MENOS un reactante (sino el loop
        # vacio matchearia vacuosamente y devolveriamos toda reaccion
        # con stoich vacio).
        reactants_found = 0
        reactants_in_feed = True
        for sp in getattr(rxn, "stoich", []):
            if sp.nu < 0:
                reactants_found += 1
                # buscar por formula y por thermo_name si existe
                tn = None
                try:
                    tn = _rdb.thermo_name(sp.formula)
                except Exception:
                    pass
                names = {sp.formula.lower()}
                if tn:
                    names.add(tn.lower())
                if not names & feed_set:
                    reactants_in_feed = False
                    break
        if (reactants_found > 0 and reactants_in_feed
                and rxn_id not in matched):
            matched.add(rxn_id)
            matched_rxns.append(rxn)
    return matched_rxns


# ======================================================
# PREDICTED — aplica templates T01-T20
# ======================================================
def _build_stoich_entries(reactants: List[Tuple[str, int]],
                           products: List[Tuple[str, int]]) -> List:
    """Construye lista de StoichEntry compatible con reactions_db.

    Devuelve una lista de objetos con campos .formula, .phase, .nu —
    si reactions_db disponible usa StoichEntry, sino usa una namedtuple
    minimal."""
    try:
        from reactions_db import StoichEntry
        cls = StoichEntry
    except ImportError:
        from collections import namedtuple
        cls = namedtuple("StoichEntry", ["formula", "phase", "nu"])

    entries = []
    for formula, nu in reactants:
        entries.append(cls(formula=formula, phase="g", nu=-int(nu)))
    for formula, nu in products:
        entries.append(cls(formula=formula, phase="g", nu=int(nu)))
    return entries


def _smiles_to_formula(smiles: str) -> str:
    """SMILES → formula molecular usando RDKit. Vacio si falla."""
    if not RDKIT_AVAILABLE or not smiles:
        return ""
    try:
        from rdkit import Chem
        from rdkit.Chem import rdMolDescriptors
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return ""
        return rdMolDescriptors.CalcMolFormula(mol)
    except Exception:
        return ""


def _apply_template_to_feed(
    template: TransformationTemplate,
    feed_smiles: Dict[str, str],
    T_K: float,
) -> List[PredictedReaction]:
    """Para un template dado, intenta aplicarlo a todas las combinaciones
    posibles de reactantes del feed. Devuelve lista de PredictedReaction.

    Limitacion Fase 5: combinatoria simple (cada compuesto por separado;
    para templates de 2 reactantes pruebo pairs unicos). No aplica el
    template a si mismo (un compuesto con dos grupos no se cruza con
    su propio otro grupo — eso es para Fase 6 con product_builder).
    """
    out: List[PredictedReaction] = []
    if not template.reaction_smarts:
        return out
    if not RDKIT_AVAILABLE:
        return out

    feed_items = list(feed_smiles.items())
    n = len(feed_items)
    if n == 0:
        return out

    # Inferir aridad del template del SMARTS: cuenta '.' en el lado
    # izquierdo de '>>' (numero de reactantes).
    smarts = template.reaction_smarts
    lhs = smarts.split(">>")[0] if ">>" in smarts else smarts
    n_reactants = lhs.count(".") + 1

    counter = 0
    if n_reactants == 1:
        combos = [(feed_items[i],) for i in range(n)]
    elif n_reactants == 2:
        combos = []
        for i in range(n):
            for j in range(n):
                # Permitir (A, B) y (A, A) — el template decide
                combos.append((feed_items[i], feed_items[j]))
    else:
        # >2 reactantes: no soportado por ahora (T16 aldol, T19 mezcla
        # con varios reactivos — el template SMARTS suele tener =2).
        return out

    for combo in combos:
        names = [item[0] for item in combo]
        smis  = [item[1] for item in combo]
        # Aplicar template
        products_sets = transformations.apply_to_compounds(template, smis)
        if not products_sets:
            continue
        for product_smis in products_sets:
            counter += 1
            # Convertir cada producto SMILES a formula
            product_formulas = [_smiles_to_formula(s) for s in product_smis]
            if "" in product_formulas:
                continue   # algun producto no parsea
            reactant_formulas = [_smiles_to_formula(s) for s in smis]
            if "" in reactant_formulas:
                continue

            # Construir stoich (asumimos 1:1 si template no especifica)
            stoich = _build_stoich_entries(
                reactants=[(f, 1) for f in reactant_formulas],
                products=[(f, 1) for f in product_formulas],
            )

            # Estimar termodinamica de la reaccion via thermo_estimator.
            # NOTA: usamos NAMES (no formulas) porque estimate_compound
            # espera nombres del thermo_db. Para productos predichos que
            # NO estan en thermo_db, el estimator devolvera missing.
            # Para evitar 'missing_compounds' por productos predichos,
            # generamos nombres provisionales y los mapeamos via SMILES.
            # En Fase 6 product_builder los va a persistir; por ahora
            # los etiquetamos como 'P_<formula>_<idx>'.
            new_products = [
                f"P_{f}_{counter}" for f in product_formulas
            ]
            rxn_thermo = thermo_estimator.estimate_reaction_thermo(
                reactants=[(n_, 1) for n_ in names],
                products=[(n_, 1) for n_ in new_products],
                T_K=T_K,
            )
            # Si missing_compounds tiene los new_products solo, no
            # podemos estimar. La opcion: usar Joback directo sobre el
            # SMILES del producto.
            if rxn_thermo.get("missing_compounds"):
                # Intentar fallback: Joback directo sobre cada producto
                # SMILES, sumar Hess manualmente.
                dh_r_kJ = 0.0
                err2 = 0.0
                ok = True
                for s in smis:
                    est = thermo_estimator.estimate_compound(
                        name_from_smiles=None,
                    ) if False else None
                    # Forzamos via SMILES directo
                    from chemfx.predictor import joback_wrapper
                    e = (joback_wrapper.estimate_via_joback(s) or
                         joback_wrapper.estimate_via_md_fallback(s))
                    if e is None or "dh_f_298_kJ_mol" not in e:
                        ok = False
                        break
                    dh_r_kJ -= e["dh_f_298_kJ_mol"].value
                    err2 += e["dh_f_298_kJ_mol"].uncertainty ** 2
                if ok:
                    for s in product_smis:
                        from chemfx.predictor import joback_wrapper
                        e = (joback_wrapper.estimate_via_joback(s) or
                             joback_wrapper.estimate_via_md_fallback(s))
                        if e is None or "dh_f_298_kJ_mol" not in e:
                            ok = False
                            break
                        dh_r_kJ += e["dh_f_298_kJ_mol"].value
                        err2 += e["dh_f_298_kJ_mol"].uncertainty ** 2
                if ok:
                    from chemfx.predictor.types import ThermoEstimate
                    rxn_thermo = {
                        "delta_h_298_kJ_mol": ThermoEstimate(
                            value=dh_r_kJ, uncertainty=math.sqrt(err2),
                            method="joback (predictor fallback)",
                            confidence=Confidence.MEDIA),
                        "delta_g_298_kJ_mol": None,
                        "keq_298": math.exp(-dh_r_kJ * 1000.0 /
                                            (8.314 * T_K)) if abs(dh_r_kJ) < 200
                                   else (float("inf") if dh_r_kJ < 0 else 0.0),
                        "method_used": "joback",
                        "overall_confidence": Confidence.MEDIA,
                        "missing_compounds": [],
                    }
                else:
                    # Joback fallo. NO descartar la reaccion: reportarla
                    # con thermo desconocida (dh=0, confidence BAJA). El
                    # template SI matcheo (RDKit produjo productos), asi
                    # que la reaccion ESTRUCTURALMENTE existe. Solo no
                    # podemos predecir su termodinamica.
                    from chemfx.predictor.types import ThermoEstimate
                    rxn_thermo = {
                        "delta_h_298_kJ_mol": ThermoEstimate(
                            value=0.0, uncertainty=50.0,
                            method="placeholder (thermo no disponible)",
                            confidence=Confidence.BAJA),
                        "delta_g_298_kJ_mol": None,
                        "keq_298": 1.0,    # neutro
                        "method_used": "placeholder",
                        "overall_confidence": Confidence.BAJA,
                        "missing_compounds": [],
                    }

            # Construir PredictedReaction
            display = " + ".join(names) + " → " + " + ".join(product_smis)
            keq_T = rxn_thermo.get("keq_298") or 0.0
            dh_est = rxn_thermo.get("delta_h_298_kJ_mol")
            dg_est = rxn_thermo.get("delta_g_298_kJ_mol")
            fav = (dg_est is not None and dg_est.value < 0) or \
                  (dg_est is None and dh_est is not None and dh_est.value < 0)
            rxn = PredictedReaction(
                id=f"P_{template.id[:10]}_{counter:04d}",
                transformation_id=template.id,
                origin=Origin.PREDICTED,
                stoichiometry=stoich,
                delta_h_298=dh_est,
                delta_s_298=None,    # Fase 5 no estima ΔS aun
                delta_g_298=dg_est,
                delta_h_at_T=dh_est, # sin Kirchhoff por ahora
                keq_at_T=float(keq_T),
                favorable_at_T=bool(fav),
                requires_catalyst=template.requires_catalyst,
                catalyst_hint=template.catalyst_hint,
                T_range_K=template.T_range_K,
                new_products_introduced=new_products,
                products_added_to_db=False,
                display_label=display,
                notes=(
                    f"template={template.id}, "
                    f"products_smiles={product_smis}, "
                    f"method={rxn_thermo.get('method_used', 'unknown')}"
                ),
            )
            confidence_tagger.apply_tags(rxn)
            ok, reason = plausibility_filter.is_plausible(rxn, T_K)
            if ok:
                out.append(rxn)
    return out


# ======================================================
# API PRINCIPAL
# ======================================================
def predict_reactions(
    feed_compounds: List[str],
    T_K: float,
    P_bar: float = 1.0,
    tau_s: Optional[float] = None,
    include_curated: bool = True,
    include_auto: bool = True,    # noqa: ARG001 (Fase 6)
    include_predicted: bool = True,
) -> FeedAnalysis:
    """API principal del predictor. Devuelve FeedAnalysis con:
      - reacciones curadas aplicables (de reactions_db)
      - reacciones AUTO aplicables (Fase 6 — placeholder ahora)
      - reacciones PREDICTED detectadas (templates T01-T20)
      - warnings de peligros (Fase 7 — placeholder)
      - sugerencias del asistente (Fase 7 — placeholder)

    Args:
        feed_compounds: nombres canonicos del thermo_db.
        T_K: temperatura del equipo.
        P_bar: presion (no usado para filtros aun).
        tau_s: tiempo de residencia (Fase 7 — kinetic filter).
        include_*: toggles para incluir cada nivel.

    Returns:
        FeedAnalysis poblado.
    """
    feed_compounds = [c for c in feed_compounds if c]
    fa = FeedAnalysis(
        compounds=list(feed_compounds),
        T_K=T_K, P_bar=P_bar, tau_s=tau_s,
    )

    # 1. Curated (de reactions_db.md)
    if include_curated:
        try:
            fa.curated = _find_curated_for_feed(feed_compounds, T_K)
        except Exception as e:
            logger.debug(f"_find_curated_for_feed fallo: {e}")
            fa.curated = []

    # 2. AUTO (Fase 6 — placeholder)
    fa.auto = []

    # 3. PREDICTED (templates T01-T20)
    if include_predicted and RDKIT_AVAILABLE:
        # Resolver SMILES de cada compuesto del feed
        feed_smiles: Dict[str, str] = {}
        for c in feed_compounds:
            s = smiles_loader.get_smiles(c)
            if s:
                feed_smiles[c] = s
        # Filtrar templates por T
        applicable = transformations.find_applicable_transformations({}, T_K)
        predicted: List[PredictedReaction] = []
        for tpl in applicable:
            preds = _apply_template_to_feed(tpl, feed_smiles, T_K)
            predicted.extend(preds)
        # Rankear + dedupe
        predicted = plausibility_filter.rank_reactions(predicted)
        fa.predicted = predicted

    # 4. Warnings + suggestions (Fase 7)
    fa.warnings = []
    fa.assistant_suggestions = []
    return fa
