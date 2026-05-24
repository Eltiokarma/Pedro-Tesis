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


def _has_heat_source_upstream(fs, b):
    """True si algún bloque directamente upstream del reactor es un heater
    o fired heater (provee el calor para llegar a T_op)."""
    for s in fs.streams.values():
        if s.dst != b.id:
            continue
        src = fs.blocks.get(s.src)
        if src is None:
            continue
        et = (src.eq_type or "").lower()
        if "fired" in et or "heater" in et:
            return True
    return False


def audit_reactor_feed_temperatures(fs, gap_C=50.0):
    """Detecta "reactores usados como horno": declaran T_op_K muy por encima
    de la T del feed pero NO tienen un heater/fired_heater upstream que
    aporte ese calor.  Es la T análoga al bug de los compresores (gap entre
    T declarada y la física, sin fuente de calor que lo justifique).

    Regla: si T_op − T_feed_max > gap_C y no hay heater/fired upstream → flag.

    Returns:
        list de dicts {block, T_op, T_feed, gap}.
    """
    issues = []
    for b in fs.blocks.values():
        if "reactor" not in (b.eq_type or "").lower():
            continue
        T_op_K = float(getattr(b, "T_op_K", 0.0) or 0.0)
        if T_op_K <= 0:
            continue
        T_op_C = T_op_K - 273.15
        ins = [s for s in fs.streams.values()
                if s.dst == b.id and (s.role or "") not in ("utility", "ambient")]
        if not ins:
            continue
        T_feed = max(s.temperature for s in ins)
        gap = T_op_C - T_feed
        if gap <= gap_C:
            continue
        # El reactor SÍ tiene fuente de calor (no es defecto) si:
        #   · hay heater/fired upstream, o
        #   · tiene duty propio > 0 (jacketed/fired: la chaqueta lo calienta), o
        #   · la reacción es exotérmica (heat_of_reaction < 0 → autotérmico).
        duty = float(getattr(b, "duty", 0.0) or 0.0)
        hor = float(getattr(b, "heat_of_reaction", 0.0) or 0.0)
        if (_has_heat_source_upstream(fs, b) or duty > 1.0 or hor < -1.0):
            continue
        # tipo de defecto: si la reacción DEBERÍA ser exotérmica (combustión/
        # oxidación) pero hor=0, el fix es declarar hor; si es endotérmica/
        # neutra, falta un precalentador.
        issues.append({"block": b.name, "T_op": T_op_C,
                        "T_feed": T_feed, "gap": gap})
    return issues

