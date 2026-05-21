"""Joback wrapper (Fase 2).

API publica:
    estimate_via_joback(smiles) -> Dict[str, ThermoEstimate] | None
    estimate_via_md_fallback(smiles) -> Dict[str, ThermoEstimate] | None
    cross_validate(smiles) -> dict
    joback_groups_in_molecule(smiles) -> Dict[str, int]

Backend principal: libreria 'thermo' (Caleb Bell), via thermo.Joback.
Fallback: parser .md + RDKit para matchear SMARTS de la tabla.

ARQUITECTURA v2 §3 Fase 2 + §4 Validacion cruzada:
  estimate_via_joback usa thermo (oficial).
  estimate_via_md_fallback usa la tabla .md con SMARTS matching manual.
  cross_validate corre ambos y reporta discrepancia.

Tolerancia de cross-validation: < 0.5 kJ/mol en ΔHform (warning si >).
Discrepancia > 10 kJ/mol → bug serio.
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from chemfx import RDKIT_AVAILABLE, THERMO_AVAILABLE
from chemfx.predictor.types import ThermoEstimate, Confidence
from chemfx.predictor import joback_table_loader

logger = logging.getLogger(__name__)


def _estimate_joback_error(n_groups: int) -> float:
    """Banda de error estimada en kJ/mol segun complejidad de la molecula.
    Source: §5.3 v1 + Reid-Prausnitz-Poling 5e §2.4."""
    if n_groups <= 2:
        return 5.0    # molecula simple (e.g. ethanol)
    elif n_groups <= 5:
        return 12.0   # tipico
    else:
        return 25.0   # polifuncional


def _confidence_from_error(err_kJ_mol: float) -> Confidence:
    if err_kJ_mol <= 5.0:
        return Confidence.ALTA
    if err_kJ_mol <= 15.0:
        return Confidence.MEDIA
    return Confidence.BAJA


def _safe_get(obj, name, *call_args):
    """Acceso defensivo a un atributo de thermo.Joback.

    En versiones distintas de la libreria, Hf/Tb/Tc/... pueden ser:
      - metodos (J.Hf()) — version clasica
      - propiedades (J.Hf) — version mas reciente
      - metodos con argumento (J.Cpig(298.15))
    Esta funcion intenta los tres patrones en orden y devuelve el
    primer valor numerico que obtenga. None si todo falla.
    """
    try:
        attr = getattr(obj, name, None)
    except Exception:
        return None
    if attr is None:
        return None
    if callable(attr):
        try:
            return attr(*call_args) if call_args else attr()
        except Exception as e:
            logger.debug(f"safe_get({name}) callable fallo: {e}")
            return None
    # No callable: es propiedad/valor
    try:
        return float(attr)
    except (TypeError, ValueError):
        return None


def estimate_via_joback(smiles: str) -> Optional[Dict[str, ThermoEstimate]]:
    """Backend thermo.Joback (Caleb Bell).

    Returns:
        Dict con keys: 'dh_f_298_kJ_mol', 'dg_f_298_kJ_mol', 'tb_K',
        'tc_K', 'pc_bar', 'cp_298_J_mol_K', 'dh_vap_kJ_mol'. None si:
          - thermo no instalado
          - SMILES no parsea o tiene grupos no reconocidos
          - ningun valor numerico se puede extraer del objeto Joback
    """
    if not THERMO_AVAILABLE or not smiles:
        return None
    # IMPORTANTE: thermo>=0.2 requiere Mol object (no string SMILES).
    # Si pasamos string directo, J.Hf() devuelve None silenciosamente
    # porque no pudo parsear los grupos. Bug detectado en testing.
    J = None
    try:
        from thermo.group_contribution.joback import Joback
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            logger.debug(f"RDKit no parseo {smiles!r}")
            return None
        # Primer intento: Mol object (API moderna)
        try:
            J = Joback(mol)
        except Exception:
            # Fallback: string SMILES (API legacy)
            try:
                J = Joback(smiles)
            except Exception as e:
                logger.debug(f"thermo.Joback fallo para {smiles!r}: {e}")
                return None
    except ImportError as e:
        logger.debug(f"import fallo: {e}")
        return None
    if J is None:
        return None
    # status puede ser str ('OK'), lista ['OK'], o no existir. Defendemos.
    status = getattr(J, "status", "OK")
    if isinstance(status, str) and status.upper() not in ("OK", ""):
        return None
    if isinstance(status, (list, tuple)) and status and "OK" not in status:
        # Algunos versions devuelven lista de warnings; OK como elemento ok.
        # Si no hay 'OK' en la lista, asumimos fallo.
        non_ok = [s for s in status if not (isinstance(s, str) and s.upper() == "OK")]
        if non_ok and not any(isinstance(s, str) and s.upper() == "OK" for s in status):
            logger.debug(f"thermo.Joback status no OK: {status}")
            # No bail — intentamos extraer valores igual

    # Numero de grupos identificados (para banda de error).
    counts = getattr(J, "counts", {}) or {}
    n_groups = len(counts) if counts else 1
    err_dHf = _estimate_joback_error(n_groups)

    out: Dict[str, ThermoEstimate] = {}

    def _add(label, value, unc, conf=None, method="joback (thermo lib)"):
        if value is None:
            return
        try:
            value = float(value)
        except (TypeError, ValueError):
            return
        if conf is None:
            conf = _confidence_from_error(abs(unc) if unc else 5.0)
        out[label] = ThermoEstimate(
            value=value, uncertainty=abs(unc) if unc else 0.0,
            method=method, confidence=conf,
        )

    # ΔHf°: thermo devuelve J/mol → dividir por 1000 para kJ/mol.
    # Algunos versions tienen Hf como metodo con arg T (Hf(T=298.15));
    # otros como propiedad. _safe_get cubre ambos.
    hf = _safe_get(J, "Hf")
    if hf is None:
        # Algunos thermo Joback requieren T como argumento explicito.
        hf = _safe_get(J, "Hf", 298.15)
    if hf is None:
        logger.debug(
            f"thermo.Joback({smiles!r}): no se obtuvo Hf. "
            f"status={getattr(J, 'status', '?')}, "
            f"counts={getattr(J, 'counts', '?')}"
        )
    if hf is not None:
        _add("dh_f_298_kJ_mol", hf / 1000.0, err_dHf,
             conf=_confidence_from_error(err_dHf))
    gf = _safe_get(J, "Gf")
    if gf is None:
        gf = _safe_get(J, "Gf", 298.15)
    if gf is not None:
        _add("dg_f_298_kJ_mol", gf / 1000.0, err_dHf * 1.2)
    tb = _safe_get(J, "Tb")
    if tb is not None:
        _add("tb_K", tb, 12.9, conf=Confidence.MEDIA)
    tc = _safe_get(J, "Tc")
    if tc is not None:
        _add("tc_K", tc, tc * 0.048, conf=Confidence.MEDIA)
    pc = _safe_get(J, "Pc")
    if pc is not None:
        _add("pc_bar", pc / 1e5, pc / 1e5 * 0.052, conf=Confidence.MEDIA)
    cp298 = _safe_get(J, "Cpig", 298.15)
    if cp298 is not None:
        _add("cp_298_J_mol_K", cp298, cp298 * 0.014, conf=Confidence.ALTA)
    hvap = _safe_get(J, "Hvap")
    if hvap is not None:
        _add("dh_vap_kJ_mol", hvap / 1000.0, 3.9, conf=Confidence.MEDIA)

    return out if out else None



def joback_groups_in_molecule(smiles: str) -> Dict[str, int]:
    """Identifica grupos Joback en un SMILES via RDKit + SMARTS de la
    tabla .md. Devuelve {group_name: count}.

    Usado por el fallback manual y por la validacion cruzada (verificar
    que thermo identifica los mismos grupos que nuestra tabla)."""
    if not RDKIT_AVAILABLE or not smiles:
        return {}
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {}
    except Exception:
        return {}

    table = joback_table_loader.load_joback_table()
    counts: Dict[str, int] = {}
    for group_name, row in table.items():
        smarts = row.get("smarts")
        if not smarts:
            continue
        try:
            patt = Chem.MolFromSmarts(smarts)
            if patt is None:
                continue
            matches = mol.GetSubstructMatches(patt)
            if matches:
                counts[group_name] = len(matches)
        except Exception:
            continue
    return counts


def estimate_via_md_fallback(smiles: str) -> Optional[Dict[str, ThermoEstimate]]:
    """Fallback manual: identifica grupos via SMARTS + suma contribuciones
    desde joback_groups.md.

    Aplica las formulas de §15 del .md:
      ΔHf°  = 68.29 + Σ ΔHform_i
      ΔGf°  = 53.88 + Σ ΔGform_i
      Tb    = 198.2 + Σ ΔTb_i
      Cp(T) = (Σa_i − 37.93) + (Σb_i + 0.210)·T + (Σc_i − 3.91e-4)·T²
              + (Σd_i + 2.06e-7)·T³
      ΔHvap = 15.30 + Σ ΔHvap_i

    Returns: dict de ThermoEstimate. None si:
      - RDKit no disponible
      - SMILES no parsea o no se identifica ningun grupo
    """
    counts = joback_groups_in_molecule(smiles)
    if not counts:
        return None

    table = joback_table_loader.load_joback_table()
    # Sumar contribuciones
    sum_dHform = 0.0
    sum_dGform = 0.0
    sum_dTb    = 0.0
    sum_a = sum_b = sum_c = sum_d = 0.0
    sum_dHvap  = 0.0
    n_groups_total = 0
    for group_name, c in counts.items():
        row = table[group_name]
        n_groups_total += c
        for sum_key, row_key in (
            ("sum_dHform", "dHform"), ("sum_dGform", "dGform"),
            ("sum_dTb", "dTb"), ("sum_a", "cp_a"), ("sum_b", "cp_b"),
            ("sum_c", "cp_c"), ("sum_d", "cp_d"), ("sum_dHvap", "dHvap"),
        ):
            v = row.get(row_key)
            if v is not None:
                if   sum_key == "sum_dHform": sum_dHform += v * c
                elif sum_key == "sum_dGform": sum_dGform += v * c
                elif sum_key == "sum_dTb":    sum_dTb    += v * c
                elif sum_key == "sum_a":      sum_a += v * c
                elif sum_key == "sum_b":      sum_b += v * c
                elif sum_key == "sum_c":      sum_c += v * c
                elif sum_key == "sum_d":      sum_d += v * c
                elif sum_key == "sum_dHvap":  sum_dHvap += v * c

    # Aplicar formulas Joback
    dHf = 68.29 + sum_dHform
    dGf = 53.88 + sum_dGform
    Tb  = 198.2 + sum_dTb
    dHvap = 15.30 + sum_dHvap
    # Cp(298)
    T = 298.15
    cp_a_eff = sum_a - 37.93
    cp_b_eff = sum_b + 0.210
    cp_c_eff = sum_c - 3.91e-4
    cp_d_eff = sum_d + 2.06e-7
    cp_298 = cp_a_eff + cp_b_eff*T + cp_c_eff*T**2 + cp_d_eff*T**3

    err_dHf = _estimate_joback_error(len(counts))
    conf_dHf = _confidence_from_error(err_dHf)

    return {
        "dh_f_298_kJ_mol": ThermoEstimate(
            value=dHf, uncertainty=err_dHf,
            method="joback (manual .md)", confidence=conf_dHf),
        "dg_f_298_kJ_mol": ThermoEstimate(
            value=dGf, uncertainty=err_dHf * 1.2,
            method="joback (manual .md)", confidence=Confidence.MEDIA),
        "tb_K": ThermoEstimate(
            value=Tb, uncertainty=12.9,
            method="joback (manual .md)", confidence=Confidence.MEDIA),
        "cp_298_J_mol_K": ThermoEstimate(
            value=cp_298, uncertainty=cp_298 * 0.014,
            method="joback (manual .md)", confidence=Confidence.ALTA),
        "dh_vap_kJ_mol": ThermoEstimate(
            value=dHvap, uncertainty=3.9,
            method="joback (manual .md)", confidence=Confidence.MEDIA),
    }


def cross_validate(smiles: str, tolerance_kJ_mol: float = 0.5) -> Dict:
    """Compara estimate_via_joback (thermo) vs estimate_via_md_fallback.

    Returns:
        {
            'thermo':   estimaciones via thermo, o None,
            'md':       estimaciones via manual, o None,
            'discrepancies': {property: diff_value} para ΔHf°/ΔGf°/Tb/Cp/ΔHv,
            'warnings': list[str] para los que exceden tolerancia.
        }
    """
    via_thermo = estimate_via_joback(smiles)
    via_md     = estimate_via_md_fallback(smiles)
    result = {
        "thermo": via_thermo,
        "md": via_md,
        "discrepancies": {},
        "warnings": [],
    }
    if via_thermo and via_md:
        for prop in ("dh_f_298_kJ_mol", "dg_f_298_kJ_mol",
                     "tb_K", "cp_298_J_mol_K", "dh_vap_kJ_mol"):
            if prop in via_thermo and prop in via_md:
                diff = via_thermo[prop].value - via_md[prop].value
                result["discrepancies"][prop] = diff
                tol = tolerance_kJ_mol if "kJ_mol" in prop else max(
                    abs(via_thermo[prop].value) * 0.05, 1.0)
                if abs(diff) > tol:
                    result["warnings"].append(
                        f"{prop}: thermo={via_thermo[prop].value:.3f}, "
                        f"md={via_md[prop].value:.3f}, diff={diff:+.3f}"
                    )
    return result
