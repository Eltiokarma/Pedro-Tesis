# ======================================================
# CAPEX — Fuente ÚNICA de Fixed Capital Investment (FCI)
# ======================================================
# Antes había ≥3 rutas paralelas que calculaban FCI con
# números distintos: ISBL pelado, FCI×1.45 inventado,
# CGR Grass Roots, y un huérfano en Income Statement.
# Este módulo es el único permitido para producir FCI.
# Refactorizado según instrucciones del usuario (sección
# "Bugs de consistencia financiera").
#
# Metodología: Grass Roots Capital (Turton 5ª Ec. 7.10).
#     CGR = ΣCBM + 0.18·ΣCBM + 0.50·ΣCBM
# Donde ΣCBM se computa una sola vez por bloque con:
#     · year_target unificado
#     · material auto-detectado (suggested_material)
#     · factor presión FP por categoría
#
# Working capital se trata como CAPEX one-time (year 0)
# que se RECUPERA al cierre del horizonte; NO entra en la
# base depreciable.  Default 15 % de FCI (Turton §7.3).
# ======================================================

from typing import Dict, Optional

import equipment_costs as eq


def _block_material(fs, block_id, default="CS"):
    """Material auto-detectado del bloque (igual heurística que
    flowsheet_export._block_material).  Definido acá también para
    que capex.py sea autocontenido y no dependa de export.
    """
    b = fs.blocks.get(block_id)
    if b is None:
        return default
    if getattr(b, "material", None):
        return b.material
    p_op = float(getattr(b, "P_op_bar", 0.0) or 0.0) or 1.0
    comps = []
    for s in fs.streams.values():
        if s.src == block_id or s.dst == block_id:
            if s.composition:
                comps.append(s.composition)
    return eq.suggested_material(comps, p_op_bar=p_op)


def compute_fci(fs,
                year_target:        int   = 2024,
                isbl_override_usd:  Optional[float] = None,
                contingency_frac:   Optional[float] = None,
                aux_facilities_frac:Optional[float] = None,
                working_capital_frac: Optional[float] = None) -> Dict:
    """Calcula el FCI canónico del flowsheet.  ÚNICA fuente de verdad.

    Args:
        fs:                  Flowsheet con .blocks y .streams.
        year_target:         Año CEPCI destino (default 2024).
        isbl_override_usd:   Si el user provee ISBL ya estimado, se
                              usa ESE valor como ΣCBM (sobreescribe
                              el costing por bloque).  En USD.
        contingency_frac:    Default 0.18 (Turton).
        aux_facilities_frac: Default 0.50 (Turton).
        working_capital_frac:Default 0.15 (Turton).

    Returns:
        dict canónico con:
            sum_cp:                 Σ purchased costs (FOB)
            sum_cbm:                Σ CBM bare module
            contingency:            cont · ΣCBM
            aux_facilities:         aux · ΣCBM
            FCI_grass_roots:        Turton 7.10 (ΣCBM + cont + aux)
            working_capital:        WC · FCI_grass_roots
            CAPEX_total:            FCI_grass_roots + WC (year-0 outflow)
            depreciable_base:       FCI_grass_roots (NO incluye WC)
            year_target, params:    metadata
            by_category:            {cat: (cbm, n, materials_set)}
            isbl_override_used:     bool
    """
    if contingency_frac is None or aux_facilities_frac is None or \
       working_capital_frac is None:
        try:
            import econ_defaults as _ed
            cf = _ed.get_capital_fracs()
            if contingency_frac is None:
                contingency_frac = cf.get("cgr_contingency_pct", 0.18)
            if aux_facilities_frac is None:
                aux_facilities_frac = cf.get("cgr_aux_facilities_pct", 0.50)
            if working_capital_frac is None:
                working_capital_frac = cf.get("working_capital_pct", 0.15)
        except Exception:
            if contingency_frac is None:    contingency_frac    = 0.18
            if aux_facilities_frac is None: aux_facilities_frac = 0.50
            if working_capital_frac is None: working_capital_frac = 0.15

    # ── ΣCBM por bloque (única corrida) ──
    by_cat: Dict[str, list] = {}
    sum_cp  = 0.0
    sum_cbm = 0.0
    for b in fs.blocks.values():
        spec = eq.EQUIPMENT_DATA.get(b.eq_type, {})
        cat  = spec.get("categoria", "Otros")
        p_op = float(getattr(b, "P_op_bar", 0.0) or 0.0) or 1.0
        mat  = _block_material(fs, b.id)
        try:
            res = eq.bare_module_cost(b.eq_type, b.S, P_op_bar=p_op,
                                       year_target=year_target,
                                       material=mat)
            cp_block  = res["Cp_target"] * b.n
            cbm_block = res["CBM"]       * b.n
        except Exception:
            cp_block = cbm_block = 0.0
        sum_cp  += cp_block
        sum_cbm += cbm_block
        if cat not in by_cat:
            by_cat[cat] = [0.0, 0, set()]
        by_cat[cat][0] += cbm_block
        by_cat[cat][1] += int(b.n)
        by_cat[cat][2].add(mat)

    # ── Override ISBL (user-provided) ──
    isbl_override_used = (
        isbl_override_usd is not None and isbl_override_usd > 0
    )
    if isbl_override_used:
        sum_cbm = float(isbl_override_usd)

    # ── Grass Roots Capital (Turton 7.10) ──
    contingency    = contingency_frac    * sum_cbm
    aux_facilities = aux_facilities_frac * sum_cbm
    fci_gr         = sum_cbm + contingency + aux_facilities

    # ── Working capital (no depreciable) ──
    wc          = working_capital_frac * fci_gr
    capex_total = fci_gr + wc

    return {
        "sum_cp":              sum_cp,
        "sum_cbm":             sum_cbm,
        "contingency":         contingency,
        "aux_facilities":      aux_facilities,
        "FCI_grass_roots":     fci_gr,
        "working_capital":     wc,
        "CAPEX_total":         capex_total,
        # Base depreciable: SÓLO el activo fijo (FCI), NO incluye WC.
        # WC se recupera en el último año del horizonte.
        "depreciable_base":    fci_gr,
        "year_target":         year_target,
        "by_category":         by_cat,
        "isbl_override_used":  isbl_override_used,
        "params": {
            "contingency_frac":     contingency_frac,
            "aux_facilities_frac":  aux_facilities_frac,
            "working_capital_frac": working_capital_frac,
        },
    }


# ======================================================
# DEPRECIATION — única función (línea recta)
# ======================================================
def straight_line_depreciation(depreciable_base_usd: float,
                                useful_life_yr: int = 10,
                                salvage_value_usd: float = 0.0) -> float:
    """Depreciación anual línea recta.

    base   = depreciable_base − salvage
    annual = base / useful_life

    SUNAT (Perú) tasas máximas anuales (DS 122-94-EF + modif.):
        · Edificaciones:                   5 % (20 yr)
        · Maquinaria industrial:          10 % (10 yr)  ← default
        · Vehículos:                      20 % (5 yr)
        · Equipos cómputo:                25 % (4 yr)
    Para planta química standalone, 10 yr es el estándar Turton
    (también compatible con SUNAT 10 % maquinaria).  Parametrizable.
    """
    if depreciable_base_usd <= 0 or useful_life_yr <= 0:
        return 0.0
    base = max(0.0, depreciable_base_usd - salvage_value_usd)
    return base / float(useful_life_yr)
