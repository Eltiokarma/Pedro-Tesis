"""Fachada termodinamica del predictor (Capa 4b §5.5).

API publica:
    estimate_compound(compound_name) -> Dict[str, ThermoEstimate]
    estimate_reaction_thermo(reactants, products, T_K, P_bar) -> dict

Politica de prioridad para cada compuesto (§5.5 v1, §5 v2):
    1. thermo_db con dHf° experimental    → confidence ALTA
    2. thermo_db con dHf° estimado        → confidence segun uncertainty
    3. SMILES via smiles_loader → Joback (thermo lib o manual fallback)
    4. Si ninguno: None → reaccion no se estima

Para reacciones: aplica ley de Hess
    ΔH_rxn = Σ νi · ΔHf_i (productos) − Σ νi · ΔHf_i (reactantes)
    ΔS_rxn idem con S298
    ΔG_rxn = ΔH_rxn − T·ΔS_rxn
    Keq    = exp(−ΔG_rxn / (R·T))

Correccion Kirchhoff de ΔH(T) si Cp disponible:
    ΔH(T) = ΔH(298) + ∫_298^T ΔCp dT
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Optional, Tuple

from chemfx.predictor.types import ThermoEstimate, Confidence
from chemfx.predictor import smiles_loader, joback_wrapper

logger = logging.getLogger(__name__)

R_GAS_J_mol_K = 8.314462618


def estimate_compound(compound_name: str) -> Optional[Dict[str, ThermoEstimate]]:
    """Estima propiedades termodinamicas de un compuesto.

    Prioridad:
      1. Si thermo_db tiene ΔHf° experimental → wrap como ThermoEstimate
         con confidence ALTA y method='experimental'.
      2. Si no, intentar Joback via SMILES.

    Returns: dict con keys principales (dh_f_298_kJ_mol, tb_K, etc).
    None si compuesto no esta en ningun lado.
    """
    # Paso 1: intentar thermo_db (experimental)
    try:
        import thermo_db as _td
        comp = _td.get(compound_name)
    except ImportError:
        comp = None

    if comp is not None and comp.dh_f_gas_kJ_mol is not None:
        # Confidence segun origin
        origin = getattr(comp, "origin", "experimental")
        if origin == "experimental":
            conf = Confidence.ALTA
            method = "experimental (thermo_db)"
            unc = 1.0   # ~1 kJ/mol tipico NIST
        elif origin == "estimated":
            conf = Confidence.MEDIA
            method = f"estimated ({getattr(comp, 'estimation_method', 'unknown')})"
            est_unc = getattr(comp, "estimation_uncertainty", {})
            unc = est_unc.get("dh_f", 12.0) if isinstance(est_unc, dict) else 12.0
        else:
            conf = Confidence.BAJA
            method = "predicted (thermo_db)"
            unc = 20.0
        return {
            "dh_f_298_kJ_mol": ThermoEstimate(
                value=comp.dh_f_gas_kJ_mol,
                uncertainty=unc, method=method, confidence=conf,
            ),
            # Otros campos del thermo_db si quieres exponerlos aca…
        }

    # Paso 2: estimar via Joback desde SMILES
    smiles = smiles_loader.get_smiles(compound_name)
    if not smiles:
        return None
    # Preferir libreria thermo si disponible; sino fallback manual.
    via_thermo = joback_wrapper.estimate_via_joback(smiles)
    if via_thermo:
        return via_thermo
    return joback_wrapper.estimate_via_md_fallback(smiles)


def estimate_reaction_thermo(
    reactants: List[Tuple[str, int]],   # [(compound_name, stoich_coef)]
    products:  List[Tuple[str, int]],
    T_K: float = 298.15,
    P_bar: float = 1.0,                  # noqa: ARG001 (futuro: correccion P)
) -> Dict:
    """Calcula ΔH_rxn, ΔS_rxn, ΔG_rxn, Keq para una reaccion.

    Coeficientes estequiometricos siempre positivos en ambos lados
    (no se usa la convencion negativa para reactantes — explicito).

    Returns dict con keys:
        'delta_h_298_kJ_mol': ThermoEstimate
        'delta_g_298_kJ_mol': ThermoEstimate
        'keq_298':            float
        'method_used':        str ('hess_exp' | 'hess_estimated' |
                                   'pure_estimation' | 'unknown')
        'overall_confidence': Confidence
        'missing_compounds':  list[str]  (los que no se pudieron estimar)
    """
    dH = 0.0
    dG = 0.0
    err2_sum_H = 0.0   # suma de varianzas para propagar
    err2_sum_G = 0.0
    methods_used = []
    missing: List[str] = []
    has_any_estimated = False

    # Productos contribuyen +νi · ΔHf_i, reactantes −νi · ΔHf_i.
    for (compound, nu), sign in (
        [(t, +1) for t in products] + [(t, -1) for t in reactants]
    ):
        est = estimate_compound(compound)
        if est is None:
            missing.append(compound)
            continue
        dh_est = est.get("dh_f_298_kJ_mol")
        if dh_est is None:
            missing.append(compound)
            continue
        dH += sign * nu * dh_est.value
        err2_sum_H += (nu * dh_est.uncertainty) ** 2
        methods_used.append(dh_est.method)
        if "estimated" in dh_est.method or "joback" in dh_est.method:
            has_any_estimated = True
        dg_est = est.get("dg_f_298_kJ_mol")
        if dg_est is not None:
            dG += sign * nu * dg_est.value
            err2_sum_G += (nu * dg_est.uncertainty) ** 2

    if missing:
        return {
            "delta_h_298_kJ_mol": None,
            "delta_g_298_kJ_mol": None,
            "keq_298": None,
            "method_used": "missing_compounds",
            "overall_confidence": Confidence.BAJA,
            "missing_compounds": missing,
        }

    unc_H = math.sqrt(err2_sum_H) if err2_sum_H > 0 else 1.0
    unc_G = math.sqrt(err2_sum_G) if err2_sum_G > 0 else unc_H * 1.2

    # Confianza global: si TODO experimental → ALTA. Si algun estimado →
    # MEDIA (o BAJA si la incertidumbre acumulada es enorme).
    if not has_any_estimated:
        conf = Confidence.ALTA
        method = "hess_exp"
    elif unc_H < 10.0:
        conf = Confidence.MEDIA
        method = "hess_estimated"
    else:
        conf = Confidence.BAJA
        method = "pure_estimation"

    # Keq @ 298.15 K (sin correccion Kirchhoff por ahora).
    # ΔG_298 → Keq. Si Gf no estaba disponible, usar ΔH (aproximacion).
    if err2_sum_G > 0:
        dG_use = dG
    else:
        dG_use = dH   # peor pero al menos un orden de magnitud
    try:
        keq = math.exp(-dG_use * 1000.0 / (R_GAS_J_mol_K * 298.15))
    except OverflowError:
        keq = float("inf") if dG_use < 0 else 0.0

    return {
        "delta_h_298_kJ_mol": ThermoEstimate(
            value=dH, uncertainty=unc_H, method=method, confidence=conf),
        "delta_g_298_kJ_mol": ThermoEstimate(
            value=dG, uncertainty=unc_G, method=method, confidence=conf),
        "keq_298": keq,
        "method_used": method,
        "overall_confidence": conf,
        "missing_compounds": [],
    }
