"""
audit_temperatures.py — auditoría de coherencia térmica de compresores.

Compara la T de descarga DECLARADA de cada compresor/fan del flowsheet con
la T isentrópica REAL que computa equipment_design.compressor_sizing.  Si la
diferencia supera la tolerancia, lo reporta — útil para detectar T_descarga
físicamente imposibles (compresor adiabático que "enfría", o T muy por debajo
de la isentrópica).

No modifica nada: solo audita.  Lo usa validate_ui.py (Feature 9).
"""
from flowsheet_model import TM_TO_KG, SEC_PER_YEAR


def audit_compressor_temperatures(fs, tol_C=30.0):
    """Audita la T de descarga de cada compresor/fan vs la isentrópica.

    Returns:
        list de dicts {block, P_in, P_out, T_declared, T_isen, delta}
        SOLO para los que superan tol_C (los coherentes no se reportan).
    """
    import flowsheet_solver as _fsv
    import equipment_design as _ed
    issues = []
    for b in fs.blocks.values():
        et = (b.eq_type or "").lower()
        if "compressor" not in et and "fan" not in et:
            continue
        ins = [s for s in fs.streams.values() if s.dst == b.id]
        outs = [s for s in fs.streams.values() if s.src == b.id]
        if len(ins) != 1 or len(outs) != 1:
            continue
        feed, out = ins[0], outs[0]
        P_in, P_out = feed.pressure_bar, out.pressure_bar
        if P_in <= 0 or P_out <= P_in + 1e-6:
            continue   # solo compresión (P_out > P_in)
        comp = feed.composition or (
            {feed.main_component: 1.0} if feed.main_component else {})
        if not comp:
            continue
        T_in_K = feed.temperature + 273.15
        mw, k = _fsv._compressible_props(comp, T_in_K)
        m_kg_s = feed.mass_flow * TM_TO_KG / SEC_PER_YEAR
        eta = float(getattr(b, "efficiency", 0.75) or 0.75)
        res = _ed.compressor_sizing(m_kg_s, P_in, P_out, T_in_K, mw,
                                     k=k, eta_isen=eta)
        if not res:
            continue
        T_isen = res["T_out_C"]
        T_decl = out.temperature
        if abs(T_isen - T_decl) > tol_C:
            issues.append({
                "block": b.name, "P_in": P_in, "P_out": P_out,
                "T_declared": T_decl, "T_isen": T_isen,
                "delta": T_isen - T_decl,
            })
    return issues
