"""
estimated_overlay.py — Overlay de compuestos ESTIMADOS para thermo_db.

CIMIENTO de la Capa 4b (predictor): los compuestos producto que NO están en
el thermo_db sourceado (data/thermo_db.md) se estiman (Joback) y se persisten
acá, en data/estimated_compounds.json, con trazabilidad completa
(method, smiles origen, incertidumbre por campo, origin='estimated').

Contrato:
  · thermo_db.get() consulta el SOURCEADO primero y este overlay DESPUÉS:
    un compuesto del .md NUNCA es sombreado por un estimado.
  · NUNCA se escribe en data/thermo_db.md.
  · Cada registro es JSON-serializable y autodescriptivo.

NO reimplementa el estimador: estimate_and_add() reusa el Joback de
chemfx.predictor (lazy import; el overlay base no depende de rdkit/thermo).
"""
import os
import json
import threading
from typing import Dict, Optional, Any

OVERLAY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "data", "estimated_compounds.json")

_cache: Optional[Dict[str, dict]] = None
_lock = threading.Lock()


def _norm(name: str) -> str:
    """Misma normalización que thermo_db.get (lower + underscores)."""
    return name.lower().replace("-", "_").replace(" ", "_")


def _load_raw() -> Dict[str, dict]:
    if not os.path.exists(OVERLAY_PATH):
        return {}
    try:
        with open(OVERLAY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load(force_reload: bool = False) -> Dict[str, dict]:
    """Dict {nombre_normalizado: registro}.  Cacheado."""
    global _cache
    with _lock:
        if _cache is None or force_reload:
            _cache = _load_raw()
        return _cache


def _save(data: Dict[str, dict]) -> None:
    os.makedirs(os.path.dirname(OVERLAY_PATH), exist_ok=True)
    with open(OVERLAY_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)


def _record_to_component(name: str, rec: dict):
    """Construye un thermo_db.ComponentThermo a partir de un registro JSON.
    Lazy import de thermo_db para evitar ciclo de importación."""
    import thermo_db as _td
    cp = rec.get("cp_gas_coefs")
    return _td.ComponentThermo(
        name=name,
        label=rec.get("label", name),
        cas=rec.get("cas", ""),
        formula=rec.get("formula", ""),
        mw=float(rec.get("mw", 0.0)),
        tb_c=float(rec.get("tb_c", 0.0)),
        tc_c=rec.get("tc_c"),
        pc_bar=rec.get("pc_bar"),
        omega=rec.get("omega"),
        cp_gas_coefs=(tuple(cp) if cp else None),
        cp_gas_range_K=tuple(rec.get("cp_gas_range_K", (0, 0))),
        dh_f_gas_kJ_mol=rec.get("dh_f_gas_kJ_mol"),
        dh_f_liq_kJ_mol=rec.get("dh_f_liq_kJ_mol"),
        quality=rec.get("quality", "Joback"),
        smiles=rec.get("smiles", ""),
        origin="estimated",
        estimation_method=rec.get("estimation_method", "joback"),
        estimation_uncertainty=dict(rec.get("estimation_uncertainty", {})),
    )


def get(name: str):
    """ComponentThermo estimado (origin='estimated') o None.
    Pensado para ser llamado por thermo_db.get() tras fallar el sourceado."""
    rec = load().get(_norm(name))
    if rec is None:
        return None
    return _record_to_component(_norm(name), rec)


def has(name: str) -> bool:
    return _norm(name) in load()


def names() -> list:
    return sorted(load().keys())


def upsert(name: str, *, mw: float, smiles: str = "",
           dh_f_gas_kJ_mol: Optional[float] = None,
           cp_gas_coefs: Optional[list] = None,
           cp_gas_range_K=(200.0, 1500.0),
           formula: str = "", cas: str = "", tb_c: float = 0.0,
           estimation_method: str = "joback",
           estimation_uncertainty: Optional[Dict[str, float]] = None,
           **extra: Any) -> dict:
    """Inserta/actualiza un compuesto estimado y persiste a disco.
    'source'/'origin'='estimated' se fijan siempre (trazabilidad)."""
    key = _norm(name)
    rec = {
        "label": extra.get("label", name),
        "mw": float(mw),
        "smiles": smiles,
        "formula": formula,
        "cas": cas,
        "tb_c": float(tb_c),
        "dh_f_gas_kJ_mol": dh_f_gas_kJ_mol,
        "cp_gas_coefs": (list(cp_gas_coefs) if cp_gas_coefs else None),
        "cp_gas_range_K": list(cp_gas_range_K),
        "quality": "Joback",
        "source": "estimated",
        "origin": "estimated",
        "estimation_method": estimation_method,
        "estimation_uncertainty": dict(estimation_uncertainty or {}),
    }
    for k, v in extra.items():
        if k not in rec:
            rec[k] = v
    with _lock:
        data = _load_raw()
        data[key] = rec
        _save(data)
        global _cache
        _cache = data
    return rec


def remove(name: str) -> bool:
    with _lock:
        data = _load_raw()
        if _norm(name) in data:
            del data[_norm(name)]
            _save(data)
            global _cache
            _cache = data
            return True
    return False


def clear() -> None:
    """Vacía el overlay (deja {} en disco).  Útil en tests."""
    with _lock:
        _save({})
        global _cache
        _cache = {}


def estimate_and_add(name: str, smiles: Optional[str] = None,
                     cas: Optional[str] = None, formula: str = "") -> Optional[dict]:
    """Estima un compuesto vía el Joback de chemfx.predictor y lo persiste.
    Bridge opt-in (lazy import de chemfx/rdkit/chemicals; el overlay base no
    los requiere).  Devuelve el registro o None si no se pudo estimar.

    'El predictor PROPONE; este overlay guarda con trazabilidad.'
    """
    # Derivar SMILES desde CAS si hace falta (lib chemicals).
    if smiles is None and cas:
        try:
            from chemicals import search_chemical
            smiles = search_chemical(cas).smiles
        except Exception:
            return None
    if not smiles:
        return None

    # MW desde el SMILES (rdkit).
    try:
        from rdkit import Chem
        from rdkit.Chem import Descriptors
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        mw = float(Descriptors.MolWt(mol))
    except Exception:
        return None

    # Estimación Joback (reusa chemfx.predictor, sin reimplementar).
    try:
        from chemfx.predictor import joback_wrapper as _jw
        est = _jw.estimate_via_joback(smiles)
    except Exception:
        return None
    if not est:
        return None

    def _val(k):
        e = est.get(k)
        return getattr(e, "value", None) if e is not None else None

    def _unc(k):
        e = est.get(k)
        return getattr(e, "uncertainty", None) if e is not None else None

    dh_f = _val("dh_f_298_kJ_mol")
    cp298 = _val("cp_298_J_mol_K")          # J/(mol·K) puntual
    tb_K = _val("tb_K")
    # Cp constante de Joback como polinomio DIPPR (C1 en J/(kmol·K), resto 0).
    cp_coefs = [cp298 * 1000.0, 0.0, 0.0, 0.0, 0.0] if cp298 else None
    unc = {}
    if _unc("dh_f_298_kJ_mol") is not None:
        unc["dh_f"] = _unc("dh_f_298_kJ_mol")
    if _unc("cp_298_J_mol_K") is not None:
        unc["cp_gas_298"] = _unc("cp_298_J_mol_K")

    return upsert(
        name, mw=mw, smiles=smiles, formula=formula,
        cas=(cas or ""),
        tb_c=((tb_K - 273.15) if tb_K else 0.0),
        dh_f_gas_kJ_mol=dh_f, cp_gas_coefs=cp_coefs,
        estimation_method="joback", estimation_uncertainty=unc,
    )
