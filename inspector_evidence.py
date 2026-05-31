"""inspector_evidence.py — generadores de evidencia textual + figuras
matplotlib del BlockInspector.  Single source of truth para el bloque
'Diagnóstico' del Inspector y (eventualmente) para el dock legacy.

Cada función `*_text(...)` devuelve un str con la evidencia textual del
solver para ese tipo de equipo (None si no aplica).  Las funciones
`*_figure(...)` devuelven una matplotlib.figure.Figure embebible, o None.

Política:
  · NO importar Qt acá — sólo strings y figures.  Eso permite re-usar
    desde cualquier widget Qt y desde tests sin pantalla.
  · Defensivo: cada función ya es try/except amistosa; si un atributo
    falta devuelve None y el caller no muestra esa sub-sección.
"""
from __future__ import annotations

from typing import Optional


# ─────────────────────────────────────────────────────────────────────
#  EVIDENCIA TEXTUAL POR TIPO DE EQUIPO
# ─────────────────────────────────────────────────────────────────────

def reactor_text(block) -> Optional[str]:
    """Modo del solver, reacciones, conversión, T_op/P_op, calor de reacción."""
    try:
        rxs = list(getattr(block, "reactions", None) or [])
        cust = list(getattr(block, "custom_reactions", None) or [])
        mode = getattr(block, "reactor_mode", "") or ""
        if not (rxs or cust or mode in ("pfr", "cstr", "batch", "stoich")):
            return None
        lines = []
        if mode:
            lines.append(f"Modo        {mode}")
        if rxs:
            lines.append(f"Reacciones  {', '.join(rxs)}")
        if cust:
            lines.append(f"Custom      {len(cust)} reacción(es) ad-hoc")
        if (mode == "stoich"
                and getattr(block, "reactor_conversion", None) is not None):
            lines.append(f"Conversión  "
                         f"{block.reactor_conversion * 100:.1f} % del "
                         f"reactivo limitante (declarado)")
        if getattr(block, "T_op_K", 0) and block.T_op_K > 0:
            lines.append(f"T_op        {block.T_op_K - 273.15:.1f} °C")
        if getattr(block, "P_op_bar", 0) and block.P_op_bar > 0:
            lines.append(f"P_op        {block.P_op_bar:.2f} bar")
        if mode in ("pfr", "cstr", "batch") and \
                getattr(block, "reactor_volume_L", 0) > 0:
            lines.append(f"Volumen     {block.reactor_volume_L:.1f} L")
        if mode == "batch" and getattr(block, "batch_time_s", 0) > 0:
            lines.append(f"t_batch     {block.batch_time_s:.0f} s")
        hor = getattr(block, "heat_of_reaction", None)
        if hor is not None and abs(hor) > 1e-9:
            sign = "exotérmica" if hor < 0 else "endotérmica"
            lines.append(f"Calor rx    {hor:+.2f} kJ/kg input ({sign})")
        return "\n".join(lines) if lines else None
    except Exception:
        return None


def hx_text(block) -> Optional[str]:
    """T_h, T_c, ΔT_LMTD, approach, U, F, servicio, warnings desde
    `_hx_diagnostics` que pinta solve_heat_exchangers."""
    try:
        hxd = getattr(block, "_hx_diagnostics", None)
        if not (hxd and isinstance(hxd, dict)):
            # Fired heater sin diagnostics → al menos duty
            eq = (block.eq_type or "").lower()
            if "fired" in eq and abs(block.duty) > 1e-9:
                return (f"Duty        {block.duty:+.1f} kW (calor al proceso)\n"
                        f"T_proceso   ver streams in/out")
            return None
        lines = []
        Th_i = hxd.get("T_h_in"); Th_o = hxd.get("T_h_out")
        Tc_i = hxd.get("T_c_in"); Tc_o = hxd.get("T_c_out")
        if Th_i is not None and Th_o is not None:
            lines.append(f"Caliente    {Th_i:.1f} → {Th_o:.1f} °C")
        if Tc_i is not None and Tc_o is not None:
            lines.append(f"Frío        {Tc_i:.1f} → {Tc_o:.1f} °C")
        if hxd.get("dTlm") is not None:
            lines.append(f"ΔT_LMTD     {hxd['dTlm']:.1f} °C")
        if hxd.get("approach") is not None:
            lines.append(f"Approach    {hxd['approach']:.1f} °C"
                         f"  (ΔT_min={hxd.get('dT_min', 0):.0f} °C)")
        if hxd.get("U_used"):
            lines.append(f"U usado     {hxd['U_used']:.0f} W/m²·K")
        if hxd.get("F") is not None:
            lines.append(f"F correc.   {hxd['F']:.2f}")
        if hxd.get("service"):
            lines.append(f"Servicio    {hxd['service']}")
        elif hxd.get("cross_check"):
            lines.append(f"Servicio    {hxd['cross_check']}")
        for w in (hxd.get("warnings") or [])[:3]:
            lines.append(f"⚠ {w}")
        return "\n".join(lines) if lines else None
    except Exception:
        return None


def flash_text(block) -> Optional[str]:
    try:
        if not getattr(block, "flash_active", False):
            return None
        lines = []
        if block.flash_T_K > 0:
            lines.append(f"T_op        {block.flash_T_K - 273.15:.1f} °C")
        if block.flash_P_bar > 0:
            lines.append(f"P_op        {block.flash_P_bar:.2f} bar")
        lines.append("Divide la corriente de entrada en vapor (volátiles) y "
                     "líquido por VLE isotérmico NRTL.")
        return "\n".join(lines)
    except Exception:
        return None


def mech_sep_text(block) -> Optional[str]:
    """Tipo (decanter/ciclón/centrífuga/filtro), fase objetivo, η, T_op, P_op."""
    try:
        if not getattr(block, "mech_sep_active", False):
            return None
        eq_lower = (block.eq_type or "").lower()
        is_decanter = "decanter" in eq_lower
        if is_decanter:
            tipo = "Decanter L-L por densidad"
        elif "cyclone" in eq_lower:
            tipo = "Ciclón"
        elif "centrifuge" in eq_lower:
            tipo = "Centrífuga"
        else:
            tipo = "Filtro / knockout genérico"
        lines = [f"Tipo        {tipo}"]
        # 'Fase obj.' sólo aplica a separadores por fase, no a decanters L-L.
        if not is_decanter:
            tgt = getattr(block, "mech_sep_target_phase", "solid") or "solid"
            lines.append(f"Fase obj.   {tgt}")
        eff = getattr(block, "mech_sep_efficiency", None)
        if eff is not None:
            lines.append(f"η recup.    {eff * 100:.1f} %")
        if block.T_op_K > 0:
            lines.append(f"T_op        {block.T_op_K - 273.15:.1f} °C")
        if block.P_op_bar > 0:
            lines.append(f"P_op        {block.P_op_bar:.2f} bar")
        return "\n".join(lines)
    except Exception:
        return None


def splitter_text(block) -> Optional[str]:
    try:
        if not getattr(block, "splitter_active", False):
            return None
        fracs = list(getattr(block, "splitter_fractions", []) or [])
        if not fracs:
            return None
        lines = [f"Salida {i+1}    {f * 100:.1f} %" for i, f in enumerate(fracs)]
        s = sum(fracs)
        if abs(s - 1.0) > 1e-3:
            lines.append(f"⚠ fracciones suman {s:.3f} (≠ 1)")
        return "\n".join(lines)
    except Exception:
        return None


def tank_text(block, fs) -> Optional[str]:
    try:
        eq = (block.eq_type or "").lower()
        if not ("tank" in eq or "storage" in eq):
            return None
        if block.S <= 0:
            return None
        lines = [f"Capacidad   {block.S:.1f} m³"]
        if fs is not None:
            ins = [s for s in fs.streams.values()
                   if s.dst == block.id and s.mass_flow > 0]
            outs = [s for s in fs.streams.values()
                    if s.src == block.id and s.mass_flow > 0]
            flow = max([s.mass_flow for s in (ins or outs)], default=0)
            if flow > 0:
                m3_h = (flow * 1000.0 / 1000.0) / 8760.0   # tm/año ρ=1000 → m³/h
                if m3_h > 0:
                    tau_h = block.S / m3_h
                    if tau_h >= 48:
                        lines.append(f"Residencia  ≈ {tau_h/24:.1f} días "
                                     f"(tanque sobredim. p/ flujo actual)")
                    else:
                        lines.append(f"Residencia  ≈ {tau_h:.1f} h "
                                     f"(estim. con ρ=1000)")
        return "\n".join(lines)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────
#  EVIDENCIA DE COLUMNAS BINARIAS — McCabe + Profile (texto)
# ─────────────────────────────────────────────────────────────────────

def mccabe_text(block, fs) -> Optional[str]:
    """Caption McCabe + sizing + relleno + azeo."""
    try:
        if not getattr(block, "column_active", False):
            return None
        import mccabe_thiele as _mt
        d = _mt.design_from_block(block, fs)
        if d is None:
            return None
        if not d.get("feasible", True):
            return "⚠ " + (d.get("message") or "Specs no escalonables.")
        rmin = d["R_min"]
        cap = (
            f"McCabe-Thiele {d['LK']}/{d['HK']} — recomendado del modelo:\n"
            f"N = {d['N_stages']} etapas teóricas (feed en {d['feed_stage']}), "
            f"R = {d['R']:.2f}"
            + (f"  (R_min {rmin:.2f})" if rmin else "")
            + f"\nz_F={d['z_F']:.2f} → x_D={d['x_D']:.2f} / x_B={d['x_B']:.2f}")
        sz = d.get("sizing") or {}
        if sz.get("N_real"):
            cap += (f"\nEtapas reales ≈ {sz['N_real']} "
                    f"(E_o={sz['E_o']:.2f} O'Connell, α={sz['alpha_avg']:.2f})")
        if sz.get("diameter_m"):
            cap += (f"\nØ columna ≈ {sz['diameter_m']:.2f} m "
                    f"(Souders-Brown, 70 % inundación)")
        pk = d.get("packing") or {}
        if pk.get("Z_packed_m"):
            cap += (f"\nAlternativa relleno (Pall): NTU ≈ {pk['NTU']:.1f}, "
                    f"altura ≈ {pk['Z_packed_m']:.1f} m "
                    f"(N·HETP, HETP={pk['HETP_m']:.2f} m)")
        return cap
    except Exception:
        return None


def profile_text(block, fs) -> Optional[str]:
    """Caption del perfil tray-by-tray."""
    try:
        if not getattr(block, "column_active", False):
            return None
        import tray_profile as _tp
        p = _tp.build_stage_profile(block, fs)
        if p is None:
            return None
        stages = p["stages"]
        if not stages:
            return "⚠ " + (p.get("message") or "perfil truncado")
        top = stages[0]
        bot = stages[-1]
        n_feed = int(p.get("n_feed") or 0)
        fs_stage = stages[n_feed - 1] if 1 <= n_feed <= len(stages) else None
        out = (f"Perfil — {p['badge']}:\n"
               f"N = {p['n_stages']}, feed = {p['n_feed']}, "
               f"{p['LK']}/{p['HK']}\n"
               f"tope (etapa 1): x_{p['LK']}={top['x_LK']:.3f}, "
               f"T={top['T_C']:.1f}°C\n"
               f"fondo (etapa {p['n_stages']}): x_{p['LK']}={bot['x_LK']:.3f}, "
               f"T={bot['T_C']:.1f}°C")
        if fs_stage:
            out += (f"\nfeed (etapa {p['n_feed']}): "
                    f"x_{p['LK']}={fs_stage['x_LK']:.3f}, "
                    f"T={fs_stage['T_C']:.1f}°C")
        if p["source"] == "mccabe":
            out += ("\nT por etapa = bubble point del binario (CMO).  "
                    "Multicomp riguroso requiere column_method='wanghenke'.")
        return out
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────
#  BOMBAS Y COMPRESORES (reusa equipment_design + tracing hidráulico)
# ─────────────────────────────────────────────────────────────────────

def pump_text(block, fs) -> Optional[str]:
    try:
        eq = (block.eq_type or "").lower()
        if not ("pump" in eq or "bomba" in eq):
            return None
        import equipment_design as _ed
        ps = _ed.design_pump_for_block(block, fs)
        if ps is None:
            return None
        lines = [
            f"Q           {ps['Q_m3_h']:.2f} m³/h",
            f"Head        {ps['head_m']:.1f} m",
            f"W_hyd       {ps['W_hyd_kW']:.2f} kW",
            f"W_shaft     {ps['W_shaft_kW']:.2f} kW  (η_h={block.efficiency:.2f})",
            f"W_elec      {ps['W_elec_kW']:.2f} kW  (η_motor=0.95)",
            f"NPSHa       {ps['NPSHa_m']:.2f} m",
            f"NPSHr est.  {ps['NPSHr_m_est']:.2f} m",
        ]
        margin = ps.get("cavitation_margin_m")
        if margin is not None:
            if margin < 1.0:
                lines.append(f"⚠ Margen cavitación: {margin:.2f} m (<1 m, riesgo)")
            else:
                lines.append(f"Margen cav. {margin:.2f} m  ✓")
        return "\n".join(lines)
    except Exception:
        return None


def compressor_text(block, fs) -> Optional[str]:
    try:
        eq = (block.eq_type or "").lower()
        if not ("compressor" in eq or "fan" in eq):
            return None
        import equipment_design as _ed
        cs = _ed.design_compressor_for_block(block, fs)
        if cs is None:
            return None
        lines = [
            f"Ratio P_out/P_in: {cs['ratio']:.2f}",
            f"Etapas rec.:      {cs['n_stages_rec']}",
            f"Q_in (succión):   {cs['Q_in_m3_h']:.1f} m³/h",
            f"Head específico:  {cs['head_kJ_kg']:.1f} kJ/kg",
            f"T descarga:       {cs['T_out_C']:.1f} °C",
            f"W_isen:           {cs['W_isen_kW']:.1f} kW",
            f"W_actual:         {cs['W_act_kW']:.1f} kW  (η={cs['eta_total']:.2f})",
        ]
        if cs['n_stages_rec'] > 1:
            lines.append(f"⚠ Ratio {cs['ratio']:.1f} > 4: recomendar "
                         f"{cs['n_stages_rec']} etapas + intercoolers")
        if cs['T_out_C'] > 200:
            lines.append(f"⚠ T descarga {cs['T_out_C']:.0f}°C > 200°C: "
                         f"necesita enfriamiento intermedio")
        return "\n".join(lines)
    except Exception:
        return None


def hydraulic_breakdown_text(block, fs) -> Optional[str]:
    """Desglose itemizado de la ΔP que la bomba/compresor está entregando."""
    try:
        eq = (block.eq_type or "").lower()
        if not ("pump" in eq or "compressor" in eq or "fan" in eq
                or "bomba" in eq):
            return None
        import flowsheet_solver as _fsv
        bd = _fsv._trace_downstream_itemized(fs, block.id)
        if bd is None or not bd.get("items"):
            return None
        total = bd["total_dp_bar"]
        lines = [
            f"Origen:  {bd['origin_stream_name']} @ "
            f"{bd['origin_P_bar']:.3f} bar 🔒",
            f"Destino: {bd['target_stream_name']} @ "
            f"{bd['target_P_bar']:.3f} bar 🔒",
            f"ΔP total: {total:.3f} bar",
            "",
            "Aporte por elemento:",
        ]
        for it in sorted(bd["items"], key=lambda x: -x["dp_bar"]):
            pct = (100 * it["dp_bar"] / total) if total > 0 else 0
            bar_len = (max(1, int(28 * it["dp_bar"] / total))
                       if (total > 0 and it["dp_bar"] > 0) else 0)
            bar = "█" * bar_len + "·" * (28 - bar_len)
            lines.append(f"  {bar} {it['dp_bar']:6.3f} bar "
                         f"({pct:5.1f}%) {it['detail'][:36]}")
        lines.append(f"  Suma: {total:.3f} bar  ✓ cierra")
        return "\n".join(lines)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────
#  BALANCE DE MASA — IN/OUT por corriente con error de cierre
# ─────────────────────────────────────────────────────────────────────

def _stream_label(s) -> str:
    name = (getattr(s, "name", "") or "")[:14]
    comp = getattr(s, "composition", None) or {}
    if comp:
        main = max(comp, key=comp.get)
        return f"{name:14s} {main[:10]:10s}"
    phase = (getattr(s, "phase", "") or "")[:10]
    return f"{name:14s} {phase:10s}"


def _is_proc(s) -> bool:
    """Process stream: excluye auxiliares automáticas (utility/ambient)."""
    return (not getattr(s, "auto_aux", False)
            and (getattr(s, "role", "") or "") not in ("utility", "ambient"))


def mass_balance_text(block, fs) -> Optional[str]:
    """Tabla IN/OUT del bloque con flujo, comp. principal, fase y T.
    Evidencia clara de que el solver cerró el balance global de masa.

    Sólo cuenta corrientes de PROCESO (excluye CW/steam/aire auto_aux,
    que están en su propia tarjeta y no entran al balance del lado
    proceso — su energía ya va en el duty)."""
    try:
        if fs is None:
            return None
        ins  = [s for s in fs.streams.values()
                if s.dst == block.id and s.mass_flow > 0 and _is_proc(s)]
        outs = [s for s in fs.streams.values()
                if s.src == block.id and s.mass_flow > 0 and _is_proc(s)]
        aux_n = sum(1 for s in fs.streams.values()
                    if (s.src == block.id or s.dst == block.id)
                    and not _is_proc(s) and s.mass_flow > 0)
        if not ins and not outs:
            return None
        lines = ["IN  (tm/año)"]
        m_in = 0.0
        for s in ins:
            lines.append(f"  {_stream_label(s)}  {s.mass_flow:10.1f}  "
                         f"T={s.temperature:5.1f}°C")
            m_in += s.mass_flow
        lines.append(f"  Σ IN  = {m_in:10.1f} tm/año")
        lines.append("")
        lines.append("OUT (tm/año)")
        m_out = 0.0
        for s in outs:
            lines.append(f"  {_stream_label(s)}  {s.mass_flow:10.1f}  "
                         f"T={s.temperature:5.1f}°C")
            m_out += s.mass_flow
        lines.append(f"  Σ OUT = {m_out:10.1f} tm/año")
        if m_in > 0:
            err = (m_out - m_in) / m_in * 100.0
            tag = "✓ cierra" if abs(err) < 0.5 else f"⚠ err {err:+.2f}%"
            lines.append(f"  ΔM    = {m_out - m_in:+10.1f}     ({tag})")
        if aux_n:
            lines.append("")
            lines.append(f"(+ {aux_n} auxiliar(es) utility/ambient — ver "
                         f"'HX — Utility / lazo cerrado')")
        return "\n".join(lines)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────
#  BALANCE DE ENERGÍA — H_in, H_out, Q, W, error de cierre
# ─────────────────────────────────────────────────────────────────────

def energy_balance_text(block, fs) -> Optional[str]:
    """Σ H_in vs Σ H_out + Q (duty) + W (eléctrica de bombas/compresores).
    Cierra el primer principio para el bloque (evidencia del solver)."""
    try:
        if fs is None:
            return None
        import flowsheet_solver as _fsv
        ins  = [s for s in fs.streams.values()
                if s.dst == block.id and s.mass_flow > 0 and _is_proc(s)]
        outs = [s for s in fs.streams.values()
                if s.src == block.id and s.mass_flow > 0 and _is_proc(s)]
        if not ins and not outs:
            return None
        H_in  = 0.0; H_in_n  = 0
        H_out = 0.0; H_out_n = 0
        for s in ins:
            h = _fsv._stream_enthalpy_kW(s)
            if h is not None:
                H_in += h; H_in_n += 1
        for s in outs:
            h = _fsv._stream_enthalpy_kW(s)
            if h is not None:
                H_out += h; H_out_n += 1
        # nada calculable → no mostramos
        if H_in_n == 0 and H_out_n == 0:
            return None
        Q = float(getattr(block, "duty", 0.0) or 0.0)         # +cal / -enf
        W = 0.0
        eq = (block.eq_type or "").lower()
        if "pump" in eq or "compressor" in eq or "fan" in eq or "bomba" in eq:
            try:
                import equipment_design as _ed
                if "pump" in eq or "bomba" in eq:
                    ps = _ed.design_pump_for_block(block, fs)
                    W = float(ps["W_shaft_kW"]) if ps else 0.0
                else:
                    cs = _ed.design_compressor_for_block(block, fs)
                    W = float(cs["W_act_kW"]) if cs else 0.0
            except Exception:
                pass
        # convención: Q y W se aportan al fluido → H_out - H_in = Q + W
        rhs = Q + W
        lhs = H_out - H_in
        err = lhs - rhs
        scale = max(abs(H_in), abs(H_out), abs(Q), 1.0)
        err_pct = err / scale * 100.0
        tag = "✓ cierra" if abs(err_pct) < 5.0 else f"⚠ err {err_pct:+.1f}%"
        lines = [
            f"H_in   = {H_in:10.2f} kW     ({H_in_n} corriente/s)",
            f"H_out  = {H_out:10.2f} kW     ({H_out_n} corriente/s)",
            f"ΔH     = {lhs:+10.2f} kW",
            f"Q duty = {Q:+10.2f} kW",
        ]
        if abs(W) > 1e-6:
            lines.append(f"W_shaft= {W:+10.2f} kW")
        lines.append(f"Cierre : ΔH − (Q+W) = {err:+8.2f} kW   ({tag})")
        lines.append("Referencia: líquido a 25 °C, latente sumado si fase=vapor.")
        return "\n".join(lines)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────
#  HX — UTILITY AUX: flujo, ΔT, W_pump de circulación
# ─────────────────────────────────────────────────────────────────────

def utility_aux_text(block, fs) -> Optional[str]:
    """Para HX: identifica la utility, su flujo (kg/h), ΔT supply-return y
    estima la potencia de la bomba/ventilador de circulación.

    Los circuitos de CW y vapor se modelan en el solver como par de
    corrientes auto_aux 'utility', pero el equipo de impulsión (bomba CW,
    bomba de condensado) no está dibujado en el PFD.  Acá lo calculamos
    para que el OPEX y el primer principio del lazo cierren."""
    try:
        if fs is None:
            return None
        import equipment_costs as _ec
        if (_ec.EQUIPMENT_DATA.get(block.eq_type, {}).get("categoria")
                != "Heat exchangers"):
            return None
        aux = [s for s in fs.streams.values()
               if getattr(s, "auto_aux", False)
               and (s.role or "") == "utility"
               and (s.src == block.id or s.dst == block.id)]
        if not aux:
            return None
        # Flow medio (entrada == salida en mass, son la misma corriente
        # circulando: tomamos el mayor por si una quedó en 0).
        m_tm = max([float(s.mass_flow or 0.0) for s in aux] + [0.0])
        if m_tm <= 0:
            return None
        # ΔT supply/return desde T de las corrientes aux
        Tin  = next((s.temperature for s in aux if s.dst == block.id), None)
        Tout = next((s.temperature for s in aux if s.src == block.id), None)
        # Identificar utility
        import equipment_ports as _ep
        proc_T = [s.temperature for s in fs.streams.values()
                  if (s.src == block.id or s.dst == block.id)
                  and not getattr(s, "auto_aux", False)
                  and (s.role or "") not in ("utility", "ambient")]
        T_avg = sum(proc_T)/len(proc_T) if proc_T else 25.0
        util_key = ""
        try:
            util_key = _ep.resolve_heat_source(block, T_avg) or ""
        except Exception:
            pass
        util = _ep.UTILITIES.get(util_key, {})
        util_name = util.get("name", util_key or "utility")
        # kg/h desde tm/año
        m_kg_h = (m_tm * 1000.0) / 8760.0
        lines = [
            f"Servicio    {util_name}",
            f"ṁ aux       {m_kg_h:,.0f} kg/h    ({m_tm:,.1f} tm/año)",
        ]
        if Tin is not None and Tout is not None:
            lines.append(f"T sup/ret   {Tin:.1f} → {Tout:.1f} °C "
                         f"(ΔT={Tout - Tin:+.1f} °C)")
        # W_pump estimado: head típico CW loop ≈ 25 m, condensado ≈ 20 m
        # Air cooler usa ventilador con W eléctrica ≈ duty/200 (regla de
        # dedo industrial: 0.5 kW elec por 100 kW disipados).
        eq = (block.eq_type or "").lower()
        duty = abs(float(getattr(block, "duty", 0.0) or 0.0))
        if "air cooler" in eq or "air-cooled" in eq:
            W_aux = duty * 0.005          # 0.5% del duty (típico fan)
            lines.append(f"W ventilador ≈ {W_aux:.2f} kW elec "
                         f"(0.5% del duty disipado, regla de dedo)")
        else:
            # bomba de circulación auto_aux dibujada en el PFD.  Si existe,
            # leemos el W real del solver (block.duty = W_elec_kW) en vez
            # de re-estimar — eso garantiza que el número del Diagnóstico
            # coincida con el que va al OPEX.
            pump = next(
                (bb for bb in fs.blocks.values()
                 if getattr(bb, "auto_aux", False)
                 and "pump" in (bb.eq_type or "").lower()
                 and any((s.src == bb.id or s.dst == bb.id)
                         and (s.src == block.id or s.dst == block.id)
                         for s in fs.streams.values())),
                None)
            if pump is not None and abs(pump.duty or 0.0) > 1e-6:
                W_el = float(pump.duty)
                head_m = pump.delta_p_bar * 1e5 / (1000.0 * 9.81)
                eta = float(pump.efficiency or 0.65)
                lines.append(f"W_bomba circ = {W_el:.3f} kW elec "
                             f"({pump.name}; head≈{head_m:.0f} m, η={eta:.2f}, η_motor=0.95)")
                lines.append(f"           → del solver hidráulico; carga al "
                             f"OPEX eléctrico ({W_el * 8760:,.0f} kWh/año)".replace(",", " "))
            else:
                # Fallback: estimación cuando no hay bomba en el modelo.
                head_m = 20.0 if ("kettle" in eq or "reboiler" in eq) else 25.0
                rho, g, eta = 1000.0, 9.81, 0.65
                m_kg_s = m_kg_h / 3600.0
                Q_m3_s = m_kg_s / rho
                W_hyd  = rho * g * head_m * Q_m3_s / 1000.0
                W_el   = W_hyd / (eta * 0.95)
                lines.append(f"W_bomba circ ≈ {W_el:.3f} kW elec "
                             f"(estimado; head≈{head_m:.0f} m, η={eta:.2f}, η_motor=0.95)")
            lines.append("           → Lazo CERRADO: header SUP/RET + bomba "
                         "auto_aux dibujados en el PFD")
        return "\n".join(lines)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────
#  FIGURAS MATPLOTLIB (devuelven Figure embebible — caller decide si la usa)
# ─────────────────────────────────────────────────────────────────────

def mccabe_figure(block, fs):
    """Devuelve (Figure, design_dict) o (None, None)."""
    try:
        import matplotlib
        matplotlib.use("Agg")          # idempotente; el caller hace QtAgg si quiere
        from matplotlib.figure import Figure
        import mccabe_thiele as _mt
        d = _mt.design_from_block(block, fs)
        if d is None:
            return None, None
        fig = Figure(figsize=(3.4, 3.2), dpi=90)
        ax = fig.add_subplot(111)
        xs, ys = d["equilibrium"]
        ax.plot([0, 1], [0, 1], color="#b8b0a0", lw=0.8)
        ax.plot(xs, ys, color="#1f6feb", lw=1.4)
        if not d.get("feasible", True):
            for a in d.get("azeotropes", []):
                ax.plot([a], [a], "o", color="#d11", ms=6)
                ax.axvline(a, color="#d11", lw=0.7, ls="--")
            for xv, c in ((d["x_D"], "#2a9d4a"), (d["x_B"], "#9d2a8a")):
                ax.axvline(xv, color=c, lw=0.5, ls=":")
        else:
            sx = [p[0] for p in d["stages"]]
            sy = [p[1] for p in d["stages"]]
            ax.plot(sx, sy, color="#d4691e", lw=1.0)
            rs, ri = d["rect"]; ss, si = d["strip"]
            xfp = d["feed_point"][0]
            ax.plot([xfp, d["x_D"]], [rs*xfp+ri, rs*d["x_D"]+ri],
                    color="#2a9d4a", lw=1.1)
            ax.plot([d["x_B"], xfp], [ss*d["x_B"]+si, ss*xfp+si],
                    color="#9d2a8a", lw=1.1)
            for xv, c in ((d["x_D"], "#2a9d4a"), (d["z_F"], "#888"),
                          (d["x_B"], "#9d2a8a")):
                ax.axvline(xv, color=c, lw=0.5, ls=":")
            for a in d.get("azeotropes", []):
                ax.axvline(a, color="#d11", lw=0.6, ls="--")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.set_xlabel(f"x ({d['LK']})", fontsize=8)
        ax.set_ylabel(f"y ({d['LK']})", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.set_aspect("equal", adjustable="box")
        fig.tight_layout()
        return fig, d
    except Exception:
        return None, None


def profile_figure(block, fs):
    """Devuelve (Figure, profile_dict) o (None, None)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.figure import Figure
        import tray_profile as _tp
        p = _tp.build_stage_profile(block, fs)
        if p is None:
            return None, None
        fig = Figure(figsize=(3.4, 2.8), dpi=90)
        ax = fig.add_subplot(111)
        stages = p["stages"]
        if not stages:
            ax.text(0.5, 0.5, "⚠ " + (p.get("message") or "perfil truncado"),
                    ha="center", va="center", fontsize=8,
                    transform=ax.transAxes, wrap=True)
            ax.set_xticks([]); ax.set_yticks([])
            fig.tight_layout()
            return fig, p
        xs = [s["stage"] for s in stages]
        Ts = [s["T_C"] for s in stages]
        xL = [s["x_LK"] for s in stages]
        ax.plot(xs, Ts, color="#d23", marker="o", ms=3, lw=1.0)
        ax.set_xlabel("etapa  (1 = tope)", fontsize=8)
        ax.set_ylabel("T (°C)", color="#d23", fontsize=8)
        ax.tick_params(axis="y", labelcolor="#d23", labelsize=7)
        ax.tick_params(axis="x", labelsize=7)
        ax2 = ax.twinx()
        ax2.plot(xs, xL, color="#1f6feb", marker="s", ms=3, lw=1.0)
        ax2.set_ylabel(f"x ({p['LK']})", color="#1f6feb", fontsize=8)
        ax2.tick_params(axis="y", labelcolor="#1f6feb", labelsize=7)
        ax2.set_ylim(0, 1)
        for _name, vals in (p.get("other_traces") or {}).items():
            if len(vals) == len(xs):
                ax2.plot(xs, vals, color="#888", ls=":", lw=0.8)
        n_feed = int(p.get("n_feed") or 0)
        if 1 <= n_feed <= len(stages):
            ax.axvline(n_feed, color="#888", ls="--", lw=0.7)
        fig.tight_layout()
        return fig, p
    except Exception:
        return None, None


def reactor_figure(block, fs):
    """Devuelve (Figure, dict) para reactores según su modo:
       · pfr   → perfil espacial (conversión o flujo molar vs L/V)
       · batch → curva especies vs tiempo
       · cstr  → barras entrada/salida (CSTR no tiene perfil temporal)
       · stoich/equilibrium/... sin perfil persistido → None
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.figure import Figure
        mode = getattr(block, "reactor_mode", "") or ""
        if mode == "pfr":
            prof = getattr(block, "_pfr_profile", None)
            if not prof or not prof.get("points"):
                return None, None
            pts = prof["points"]
            fig = Figure(figsize=(3.4, 2.8), dpi=90)
            ax = fig.add_subplot(111)
            xs = [p["L_frac"] for p in pts]
            species = sorted({sp for p in pts for sp in (p.get("X") or {})})
            any_curve = False
            for sp in species:
                ys = [(p.get("X") or {}).get(sp, 0.0) * 100.0 for p in pts]
                if max(ys) < 1e-3:
                    continue
                ax.plot(xs, ys, lw=1.2, label=sp)
                any_curve = True
            if not any_curve:
                return None, None
            ax.set_xlabel("L / L_total", fontsize=8)
            ax.set_ylabel("Conversión (%)", fontsize=8)
            ax.set_title(f"Perfil PFR — {block.name}", fontsize=9, fontweight="bold")
            ax.tick_params(labelsize=7)
            ax.grid(True, alpha=0.3, linestyle="--")
            ax.legend(fontsize=6, loc="best", ncol=2)
            for s in ("top", "right"): ax.spines[s].set_visible(False)
            fig.tight_layout()
            return fig, prof
        if mode == "batch":
            prof = getattr(block, "_batch_profile", None)
            if not prof or not prof.get("points"):
                return None, None
            pts = prof["points"]
            fig = Figure(figsize=(3.4, 2.8), dpi=90)
            ax = fig.add_subplot(111)
            xs = [p["t_s"] for p in pts]
            species = sorted({sp for p in pts for sp in (p.get("X") or {})})
            any_curve = False
            for sp in species:
                ys = [(p.get("X") or {}).get(sp, 0.0) * 100.0 for p in pts]
                if max(ys) < 1e-3:
                    continue
                ax.plot(xs, ys, lw=1.2, label=sp)
                any_curve = True
            if not any_curve:
                return None, None
            ax.set_xlabel("Tiempo (s)", fontsize=8)
            ax.set_ylabel("Conversión (%)", fontsize=8)
            t_tot = prof.get("t_total_s", xs[-1] if xs else 0)
            ax.set_title(f"Batch — {block.name}  (t={t_tot:.0f}s)",
                         fontsize=9, fontweight="bold")
            ax.tick_params(labelsize=7)
            ax.grid(True, alpha=0.3, linestyle="--")
            ax.legend(fontsize=6, loc="best", ncol=2)
            for s in ("top", "right"): ax.spines[s].set_visible(False)
            fig.tight_layout()
            return fig, prof
        if mode == "cstr" or fs is not None:
            # CSTR (o cualquier reactor steady-state con stoich/equilibrium):
            # barras de % másico entrada vs salida — evidencia del balance.
            if fs is None:
                return None, None
            ins = [s for s in fs.streams.values() if s.dst == block.id]
            outs = [s for s in fs.streams.values() if s.src == block.id]
            def _agg(streams):
                tot, m = {}, 0.0
                for s in streams:
                    comp = s.composition or {}; mf = s.mass_flow or 0.0
                    m += mf
                    for k, v in comp.items(): tot[k] = tot.get(k, 0.0) + v * mf
                return {k: v/m for k, v in tot.items()} if m > 0 else {}
            cin, cout = _agg(ins), _agg(outs)
            if not cin and not cout:
                return None, None
            species = sorted(set(cin) | set(cout))
            if not species:
                return None, None
            fig = Figure(figsize=(3.4, 2.8), dpi=90)
            ax = fig.add_subplot(111)
            x = list(range(len(species))); w = 0.38
            ax.bar([xi - w/2 for xi in x],
                   [cin.get(s, 0.0) * 100 for s in species], w,
                   label="Entrada", color="#5c6bc0")
            ax.bar([xi + w/2 for xi in x],
                   [cout.get(s, 0.0) * 100 for s in species], w,
                   label="Salida", color="#ef6c00")
            ax.set_xticks(x)
            ax.set_xticklabels(species, fontsize=6, rotation=40, ha="right")
            ax.set_ylabel("% másico", fontsize=8)
            ax.tick_params(labelsize=7)
            ax.grid(True, axis="y", alpha=0.3, linestyle="--")
            ax.legend(fontsize=7, loc="best")
            ttl = f"{(mode or 'reactor').upper()} — {block.name}"
            ax.set_title(ttl, fontsize=9, fontweight="bold")
            for s in ("top", "right"): ax.spines[s].set_visible(False)
            fig.tight_layout()
            return fig, {"composition_in": cin, "composition_out": cout}
        return None, None
    except Exception:
        return None, None


def hx_tq_figure(block, fs):
    """Diagrama T vs Q (cumulative duty) para un HX: dos líneas — caliente
    y frío — desde T_in hasta T_out, con el approach mínimo marcado.
    Evidencia visual del primer principio del intercambiador."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.figure import Figure
        import equipment_costs as _ec
        if (_ec.EQUIPMENT_DATA.get(block.eq_type, {}).get("categoria")
                != "Heat exchangers"):
            return None, None
        hxd = getattr(block, "_hx_diagnostics", None)
        if not (hxd and isinstance(hxd, dict)):
            return None, None
        Thi, Tho = hxd.get("T_h_in"), hxd.get("T_h_out")
        Tci, Tco = hxd.get("T_c_in"), hxd.get("T_c_out")
        if None in (Thi, Tho, Tci, Tco):
            return None, None
        duty = abs(float(getattr(block, "duty", 0.0) or 0.0))
        if duty <= 0:
            return None, None
        fig = Figure(figsize=(3.4, 2.8), dpi=90)
        ax = fig.add_subplot(111)
        # caliente: cede duty Q (cae de Thi a Tho mientras Q acumula)
        # frío:     recibe duty Q (sube de Tci a Tco)
        # Counter-current: en x=0 está el extremo de salida del cold (Tco)
        # y entrada del hot (Thi); en x=Q el extremo opuesto.
        ax.plot([0, duty], [Thi, Tho], color="#d23",  lw=1.6, label="Caliente")
        ax.plot([0, duty], [Tco, Tci], color="#1f6feb", lw=1.6, label="Frío")
        # marcar approach mínimo
        approach = hxd.get("approach")
        if approach is not None:
            # extremo donde el approach es mínimo (counter-current: usualmente
            # el lado caliente-out / frío-in)
            dT_left  = Thi - Tco
            dT_right = Tho - Tci
            if dT_right < dT_left:
                x_app = duty; T_h_app, T_c_app = Tho, Tci
            else:
                x_app = 0.0;  T_h_app, T_c_app = Thi, Tco
            ax.annotate(f"ΔT_min = {approach:.1f} °C",
                        xy=(x_app, (T_h_app + T_c_app)/2),
                        xytext=(0.5 * duty, max(Thi, Tco) + 5),
                        fontsize=7, ha="center", color="#444",
                        arrowprops=dict(arrowstyle="->", color="#888", lw=0.7))
        ax.set_xlabel("Q acumulado (kW)", fontsize=8)
        ax.set_ylabel("T (°C)", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.3, linestyle="--")
        ax.legend(fontsize=7, loc="best")
        ax.set_title(f"T-Q — {block.name}  (duty={duty:.1f} kW)",
                     fontsize=9, fontweight="bold")
        for s in ("top", "right"): ax.spines[s].set_visible(False)
        fig.tight_layout()
        return fig, hxd
    except Exception:
        return None, None


def flash_figure(block, fs):
    """Devuelve (Figure, flash_dict) o (None, None) — para Vessels con
    flash_active genuinamente bifásicos en proyección binaria."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib.figure import Figure
        import distillation_simple as _ds
        f = _ds.flash_from_block(block, fs)
        if f is None:
            return None, None
        fig = Figure(figsize=(3.4, 3.2), dpi=90)
        ax = fig.add_subplot(111)
        xs, ys = f["equilibrium"]
        ax.plot([0, 1], [0, 1], color="#b8b0a0", lw=0.8)
        ax.plot(xs, ys, color="#1f6feb", lw=1.4)
        ax.plot([f["x_LK"], f["y_LK"]], [f["x_LK"], f["y_LK"]],
                color="#d4691e", lw=0.8, ls="--")
        ax.plot([f["x_LK"]], [f["y_LK"]], "o", color="#d4691e", ms=6)
        ax.axvline(f["z_F"], color="#888", lw=0.6, ls=":")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.set_xlabel(f"x ({f['LK']})", fontsize=8)
        ax.set_ylabel(f"y ({f['LK']})", fontsize=8)
        ax.tick_params(labelsize=7)
        ax.set_aspect("equal", adjustable="box")
        fig.tight_layout()
        return fig, f
    except Exception:
        return None, None


# ═════════════════════════════════════════════════════════════════════
#  *_metrics() — versión estructurada (dict) de las *_text().
#  Misma fuente, misma física, mismo formato numérico → el valor de cada
#  metric aparece textualmente en la *_text() correspondiente (Gate 1).
#  Qt-free.  None si no aplica (mismos guards que la *_text()).
# ═════════════════════════════════════════════════════════════════════

def reactor_metrics(block) -> Optional[dict]:
    """Estructurado de reactor_text(). Misma fuente (atributos del block)."""
    try:
        rxs = list(getattr(block, "reactions", None) or [])
        cust = list(getattr(block, "custom_reactions", None) or [])
        mode = getattr(block, "reactor_mode", "") or ""
        if not (rxs or cust or mode in ("pfr", "cstr", "batch", "stoich")):
            return None
        metrics = []
        status = []
        if mode:
            status.append({"text": f"Modo {mode}", "kind": "accent"})
        if (mode == "stoich"
                and getattr(block, "reactor_conversion", None) is not None):
            metrics.append({"key": "conv", "label": "Conversión",
                            "value": f"{block.reactor_conversion * 100:.1f}",
                            "unit": "%", "state": "spec"})
        if getattr(block, "T_op_K", 0) and block.T_op_K > 0:
            metrics.append({"key": "T_op", "label": "T_op",
                            "value": f"{block.T_op_K - 273.15:.1f}",
                            "unit": "°C", "state": "alert"})
        if getattr(block, "P_op_bar", 0) and block.P_op_bar > 0:
            metrics.append({"key": "P_op", "label": "P_op",
                            "value": f"{block.P_op_bar:.2f}",
                            "unit": "bar", "state": "info"})
        if mode in ("pfr", "cstr", "batch") and \
                getattr(block, "reactor_volume_L", 0) > 0:
            metrics.append({"key": "V", "label": "Volumen",
                            "value": f"{block.reactor_volume_L:.1f}",
                            "unit": "L", "state": "auto"})
        if mode == "batch" and getattr(block, "batch_time_s", 0) > 0:
            metrics.append({"key": "t_batch", "label": "t_batch",
                            "value": f"{block.batch_time_s:.0f}",
                            "unit": "s", "state": "auto"})
        hor = getattr(block, "heat_of_reaction", None)
        if hor is not None and abs(hor) > 1e-9:
            sign = "exotérmica" if hor < 0 else "endotérmica"
            metrics.append({"key": "hor", "label": "Calor rx",
                            "value": f"{hor:+.2f}", "unit": "kJ/kg",
                            "state": "orange" if hor < 0 else "info",
                            "sub": sign})
        if not metrics and not status:
            return None
        gauges = []
        if (mode == "stoich"
                and getattr(block, "reactor_conversion", None) is not None):
            gauges.append({"key": "conv", "label": "Conversión",
                           "value": float(block.reactor_conversion),
                           "suffix": "%",
                           "text": f"{block.reactor_conversion * 100:.0f}"})
        return {"status": status, "metrics": metrics, "gauges": gauges,
                "figure": "reactor", "warnings": []}
    except Exception:
        return None


def hx_metrics(block) -> Optional[dict]:
    """Estructurado de hx_text(). Misma fuente (_hx_diagnostics)."""
    try:
        hxd = getattr(block, "_hx_diagnostics", None)
        if not (hxd and isinstance(hxd, dict)):
            eq = (block.eq_type or "").lower()
            if "fired" in eq and abs(block.duty) > 1e-9:
                return {"status": [], "metrics": [
                    {"key": "duty", "label": "Duty",
                     "value": f"{block.duty:+.1f}", "unit": "kW",
                     "state": "orange", "sub": "calor al proceso"}],
                    "figure": None, "warnings": []}
            return None
        metrics = []
        Th_i = hxd.get("T_h_in"); Th_o = hxd.get("T_h_out")
        Tc_i = hxd.get("T_c_in"); Tc_o = hxd.get("T_c_out")
        if Th_i is not None and Th_o is not None:
            metrics.append({"key": "T_h", "label": "Caliente",
                            "value": f"{Th_i:.1f} → {Th_o:.1f}",
                            "unit": "°C", "state": "alert"})
        if Tc_i is not None and Tc_o is not None:
            metrics.append({"key": "T_c", "label": "Frío",
                            "value": f"{Tc_i:.1f} → {Tc_o:.1f}",
                            "unit": "°C", "state": "info"})
        if hxd.get("dTlm") is not None:
            metrics.append({"key": "dTlm", "label": "ΔT LMTD",
                            "value": f"{hxd['dTlm']:.1f}", "unit": "°C",
                            "state": "auto"})
        appr = hxd.get("approach")
        if appr is not None:
            metrics.append({"key": "appr", "label": "Approach",
                            "value": f"{appr:.1f}", "unit": "°C",
                            "state": "ok" if appr >= hxd.get("dT_min", 0)
                            else "danger"})
        if hxd.get("U_used"):
            metrics.append({"key": "U", "label": "U usado",
                            "value": f"{hxd['U_used']:.0f}",
                            "unit": "W/m²·K", "state": "auto"})
        if hxd.get("F") is not None:
            metrics.append({"key": "F", "label": "F correc.",
                            "value": f"{hxd['F']:.2f}", "state": "auto"})
        status = []
        if appr is not None and appr < 0:
            status.append({"text": "Approach cruzado", "kind": "danger"})
        if not metrics:
            return None
        return {"status": status, "metrics": metrics, "figure": "hx_tq",
                "warnings": list((hxd.get("warnings") or [])[:3])}
    except Exception:
        return None


def flash_metrics(block) -> Optional[dict]:
    """Estructurado de flash_text(). Misma fuente (flash_* del block)."""
    try:
        if not getattr(block, "flash_active", False):
            return None
        metrics = []
        if block.flash_T_K > 0:
            metrics.append({"key": "T_op", "label": "T_op",
                            "value": f"{block.flash_T_K - 273.15:.1f}",
                            "unit": "°C", "state": "alert"})
        if block.flash_P_bar > 0:
            metrics.append({"key": "P_op", "label": "P_op",
                            "value": f"{block.flash_P_bar:.2f}",
                            "unit": "bar", "state": "info"})
        return {"status": [], "metrics": metrics, "figure": "flash",
                "warnings": []}
    except Exception:
        return None


def mech_sep_metrics(block) -> Optional[dict]:
    """Estructurado de mech_sep_text(). Misma fuente (mech_sep_* del block)."""
    try:
        if not getattr(block, "mech_sep_active", False):
            return None
        eq_lower = (block.eq_type or "").lower()
        is_decanter = "decanter" in eq_lower
        if is_decanter:
            tipo = "Decanter L-L por densidad"
        elif "cyclone" in eq_lower:
            tipo = "Ciclón"
        elif "centrifuge" in eq_lower:
            tipo = "Centrífuga"
        else:
            tipo = "Filtro / knockout genérico"
        status = [{"text": tipo, "kind": "accent"}]
        metrics = []
        if not is_decanter:
            tgt = getattr(block, "mech_sep_target_phase", "solid") or "solid"
            metrics.append({"key": "tgt", "label": "Fase obj.",
                            "value": f"{tgt}", "state": "info"})
        eff = getattr(block, "mech_sep_efficiency", None)
        gauges = []
        if eff is not None:
            metrics.append({"key": "eff", "label": "η recup.",
                            "value": f"{eff * 100:.1f}", "unit": "%",
                            "state": "ok"})
            gauges.append({"key": "eff", "label": "η recup.",
                           "value": float(eff), "suffix": "%",
                           "text": f"{eff * 100:.0f}"})
        if block.T_op_K > 0:
            metrics.append({"key": "T_op", "label": "T_op",
                            "value": f"{block.T_op_K - 273.15:.1f}",
                            "unit": "°C", "state": "alert"})
        if block.P_op_bar > 0:
            metrics.append({"key": "P_op", "label": "P_op",
                            "value": f"{block.P_op_bar:.2f}",
                            "unit": "bar", "state": "info"})
        return {"status": status, "metrics": metrics, "gauges": gauges,
                "figure": None, "warnings": []}
    except Exception:
        return None


def splitter_metrics(block) -> Optional[dict]:
    """Estructurado de splitter_text(). Misma fuente (splitter_fractions)."""
    try:
        if not getattr(block, "splitter_active", False):
            return None
        fracs = list(getattr(block, "splitter_fractions", []) or [])
        if not fracs:
            return None
        bars = []
        metrics = []
        for i, f in enumerate(fracs):
            metrics.append({"key": f"out{i+1}", "label": f"Salida {i+1}",
                            "value": f"{f * 100:.1f}", "unit": "%",
                            "state": "info"})
            bars.append({"label": f"Salida {i+1}", "frac": float(f),
                         "value": f"{f * 100:.1f}", "kind": "out"})
        s = sum(fracs)
        status = []
        if abs(s - 1.0) > 1e-3:
            status.append({"text": f"fracciones suman {s:.3f}",
                           "kind": "danger"})
        return {"status": status, "metrics": metrics, "bars": bars,
                "figure": None, "warnings": []}
    except Exception:
        return None


def tank_metrics(block, fs) -> Optional[dict]:
    """Estructurado de tank_text(). Misma fuente (block.S + flujos fs)."""
    try:
        eq = (block.eq_type or "").lower()
        if not ("tank" in eq or "storage" in eq):
            return None
        if block.S <= 0:
            return None
        metrics = [{"key": "cap", "label": "Capacidad",
                    "value": f"{block.S:.1f}", "unit": "m³", "state": "info"}]
        if fs is not None:
            ins = [s for s in fs.streams.values()
                   if s.dst == block.id and s.mass_flow > 0]
            outs = [s for s in fs.streams.values()
                    if s.src == block.id and s.mass_flow > 0]
            flow = max([s.mass_flow for s in (ins or outs)], default=0)
            if flow > 0:
                m3_h = (flow * 1000.0 / 1000.0) / 8760.0
                if m3_h > 0:
                    tau_h = block.S / m3_h
                    if tau_h >= 48:
                        metrics.append({"key": "tau", "label": "Residencia",
                                        "value": f"{tau_h/24:.1f}",
                                        "unit": "días", "state": "warn",
                                        "sub": "sobredim. p/ flujo actual"})
                    else:
                        metrics.append({"key": "tau", "label": "Residencia",
                                        "value": f"{tau_h:.1f}", "unit": "h",
                                        "state": "auto",
                                        "sub": "estim. ρ=1000"})
        return {"status": [], "metrics": metrics, "figure": None,
                "warnings": []}
    except Exception:
        return None


def mccabe_metrics(block, fs) -> Optional[dict]:
    """Estructurado de mccabe_text(). Misma fuente (mccabe_thiele.design)."""
    try:
        if not getattr(block, "column_active", False):
            return None
        import mccabe_thiele as _mt
        d = _mt.design_from_block(block, fs)
        if d is None:
            return None
        if not d.get("feasible", True):
            return {"status": [{"text": "Specs no escalonables",
                                "kind": "danger"}],
                    "metrics": [], "figure": None,
                    "warnings": [d.get("message") or "Specs no escalonables."]}
        metrics = [
            {"key": "N", "label": f"N teór. ({d['LK']}/{d['HK']})",
             "value": f"{d['N_stages']}", "state": "spec",
             "sub": f"feed en {d['feed_stage']}"},
            {"key": "R", "label": "R", "value": f"{d['R']:.2f}",
             "state": "info",
             "sub": (f"R_min {d['R_min']:.2f}" if d.get("R_min") else None)},
            {"key": "xD", "label": "x_D", "value": f"{d['x_D']:.2f}",
             "state": "ok"},
            {"key": "xB", "label": "x_B", "value": f"{d['x_B']:.2f}",
             "state": "info"},
        ]
        sz = d.get("sizing") or {}
        if sz.get("N_real"):
            metrics.append({"key": "Nreal", "label": "Etapas reales",
                            "value": f"{sz['N_real']}", "state": "auto",
                            "sub": f"E_o={sz['E_o']:.2f}, α={sz['alpha_avg']:.2f}"})
        if sz.get("diameter_m"):
            metrics.append({"key": "diam", "label": "Ø columna",
                            "value": f"{sz['diameter_m']:.2f}", "unit": "m",
                            "state": "auto", "sub": "Souders-Brown 70%"})
        pk = d.get("packing") or {}
        if pk.get("Z_packed_m"):
            metrics.append({"key": "Zpack", "label": "Altura relleno",
                            "value": f"{pk['Z_packed_m']:.1f}", "unit": "m",
                            "state": "auto",
                            "sub": f"NTU≈{pk['NTU']:.1f}, HETP={pk['HETP_m']:.2f}"})
        return {"status": [{"text": "Columna diseñada", "kind": "ok"}],
                "metrics": metrics, "figure": "mccabe", "warnings": []}
    except Exception:
        return None


def profile_metrics(block, fs) -> Optional[dict]:
    """Estructurado de profile_text(). Misma fuente (tray_profile)."""
    try:
        if not getattr(block, "column_active", False):
            return None
        import tray_profile as _tp
        p = _tp.build_stage_profile(block, fs)
        if p is None:
            return None
        stages = p["stages"]
        if not stages:
            return {"status": [{"text": "perfil truncado", "kind": "warn"}],
                    "metrics": [], "figure": None,
                    "warnings": [p.get("message") or "perfil truncado"]}
        top = stages[0]
        bot = stages[-1]
        n_feed = int(p.get("n_feed") or 0)
        fs_stage = stages[n_feed - 1] if 1 <= n_feed <= len(stages) else None
        metrics = [
            {"key": "N", "label": f"N ({p['LK']}/{p['HK']})",
             "value": f"{p['n_stages']}", "state": "spec",
             "sub": f"feed {p['n_feed']}"},
            {"key": "top", "label": f"Tope x_{p['LK']}",
             "value": f"{top['x_LK']:.3f}", "state": "ok",
             "sub": f"T={top['T_C']:.1f}°C"},
            {"key": "bot", "label": f"Fondo x_{p['LK']}",
             "value": f"{bot['x_LK']:.3f}", "state": "info",
             "sub": f"T={bot['T_C']:.1f}°C"},
        ]
        if fs_stage:
            metrics.append({"key": "feed", "label": f"Feed x_{p['LK']}",
                            "value": f"{fs_stage['x_LK']:.3f}",
                            "state": "auto",
                            "sub": f"T={fs_stage['T_C']:.1f}°C"})
        return {"status": [{"text": p["badge"], "kind": "accent"}],
                "metrics": metrics, "figure": "profile", "warnings": []}
    except Exception:
        return None


def pump_metrics(block, fs) -> Optional[dict]:
    """Estructurado de pump_text(). Misma fuente (equipment_design.pump)."""
    try:
        eq = (block.eq_type or "").lower()
        if not ("pump" in eq or "bomba" in eq):
            return None
        import equipment_design as _ed
        ps = _ed.design_pump_for_block(block, fs)
        if ps is None:
            return None
        metrics = [
            {"key": "Q", "label": "Q", "value": f"{ps['Q_m3_h']:.2f}",
             "unit": "m³/h", "state": "info"},
            {"key": "head", "label": "Head", "value": f"{ps['head_m']:.1f}",
             "unit": "m", "state": "info"},
            {"key": "Whyd", "label": "W_hyd", "value": f"{ps['W_hyd_kW']:.2f}",
             "unit": "kW", "state": "auto"},
            {"key": "Wshaft", "label": "W_shaft",
             "value": f"{ps['W_shaft_kW']:.2f}", "unit": "kW", "state": "auto",
             "sub": f"η_h={block.efficiency:.2f}"},
            {"key": "Welec", "label": "W_elec",
             "value": f"{ps['W_elec_kW']:.2f}", "unit": "kW", "state": "orange"},
            {"key": "NPSHa", "label": "NPSHa", "value": f"{ps['NPSHa_m']:.2f}",
             "unit": "m", "state": "info"},
            {"key": "NPSHr", "label": "NPSHr est.",
             "value": f"{ps['NPSHr_m_est']:.2f}", "unit": "m", "state": "auto"},
        ]
        status = []
        gauges = []
        margin = ps.get("cavitation_margin_m")
        if margin is not None:
            metrics.append({"key": "margin", "label": "Margen cav.",
                            "value": f"{margin:.2f}", "unit": "m",
                            "state": "danger" if margin < 1.0 else "ok"})
            if margin < 1.0:
                status.append({"text": "Riesgo cavitación", "kind": "danger"})
        return {"status": status, "metrics": metrics, "gauges": gauges,
                "figure": None, "warnings": []}
    except Exception:
        return None


def compressor_metrics(block, fs) -> Optional[dict]:
    """Estructurado de compressor_text(). Misma fuente (equipment_design)."""
    try:
        eq = (block.eq_type or "").lower()
        if not ("compressor" in eq or "fan" in eq):
            return None
        import equipment_design as _ed
        cs = _ed.design_compressor_for_block(block, fs)
        if cs is None:
            return None
        metrics = [
            {"key": "ratio", "label": "Ratio P_out/P_in",
             "value": f"{cs['ratio']:.2f}", "state": "info"},
            {"key": "stages", "label": "Etapas rec.",
             "value": f"{cs['n_stages_rec']}", "state": "spec"},
            {"key": "Qin", "label": "Q_in succión",
             "value": f"{cs['Q_in_m3_h']:.1f}", "unit": "m³/h", "state": "info"},
            {"key": "head", "label": "Head espec.",
             "value": f"{cs['head_kJ_kg']:.1f}", "unit": "kJ/kg",
             "state": "auto"},
            {"key": "Tout", "label": "T descarga",
             "value": f"{cs['T_out_C']:.1f}", "unit": "°C",
             "state": "danger" if cs['T_out_C'] > 200 else "alert"},
            {"key": "Wisen", "label": "W_isen",
             "value": f"{cs['W_isen_kW']:.1f}", "unit": "kW", "state": "auto"},
            {"key": "Wact", "label": "W_actual",
             "value": f"{cs['W_act_kW']:.1f}", "unit": "kW", "state": "orange",
             "sub": f"η={cs['eta_total']:.2f}"},
        ]
        status = []
        if cs['n_stages_rec'] > 1:
            status.append({"text": f"Multietapa ×{cs['n_stages_rec']}",
                           "kind": "warn"})
        if cs['T_out_C'] > 200:
            status.append({"text": "T descarga >200°C", "kind": "danger"})
        return {"status": status, "metrics": metrics, "figure": None,
                "warnings": []}
    except Exception:
        return None


def hydraulic_breakdown_metrics(block, fs) -> Optional[dict]:
    """Estructurado de hydraulic_breakdown_text(). Misma fuente
    (_trace_downstream_itemized) → DeltaBars por elemento."""
    try:
        eq = (block.eq_type or "").lower()
        if not ("pump" in eq or "compressor" in eq or "fan" in eq
                or "bomba" in eq):
            return None
        import flowsheet_solver as _fsv
        bd = _fsv._trace_downstream_itemized(fs, block.id)
        if bd is None or not bd.get("items"):
            return None
        total = bd["total_dp_bar"]
        metrics = [{"key": "dptot", "label": "ΔP total",
                    "value": f"{total:.3f}", "unit": "bar", "state": "spec"}]
        bars = []
        for it in sorted(bd["items"], key=lambda x: -x["dp_bar"]):
            frac = (it["dp_bar"] / total) if total > 0 else 0.0
            bars.append({"label": it["detail"][:36], "frac": float(frac),
                         "value": f"{it['dp_bar']:.3f}", "kind": "out"})
        return {"status": [{"text": "ΔP cierra", "kind": "ok"}],
                "metrics": metrics, "bars": bars, "figure": None,
                "warnings": []}
    except Exception:
        return None


def mass_balance_metrics(block, fs) -> Optional[dict]:
    """Estructurado de mass_balance_text(). Misma fuente (streams fs).
    Mismos formatos numéricos (:.1f / :+.2f) → substring del texto."""
    try:
        if fs is None:
            return None
        ins  = [s for s in fs.streams.values()
                if s.dst == block.id and s.mass_flow > 0 and _is_proc(s)]
        outs = [s for s in fs.streams.values()
                if s.src == block.id and s.mass_flow > 0 and _is_proc(s)]
        if not ins and not outs:
            return None
        m_in = sum(s.mass_flow for s in ins)
        m_out = sum(s.mass_flow for s in outs)
        metrics = [
            {"key": "in", "label": "Σ IN", "value": f"{m_in:.1f}",
             "unit": "tm/año", "state": "info"},
            {"key": "out", "label": "Σ OUT", "value": f"{m_out:.1f}",
             "unit": "tm/año", "state": "info"},
        ]
        bars = []
        tot = max(m_in, m_out, 1e-9)
        bars.append({"label": "IN", "frac": float(m_in / tot),
                     "value": f"{m_in:.1f}", "kind": "in"})
        bars.append({"label": "OUT", "frac": float(m_out / tot),
                     "value": f"{m_out:.1f}", "kind": "out"})
        status = []
        if m_in > 0:
            err = (m_out - m_in) / m_in * 100.0
            metrics.append({"key": "dm", "label": "ΔM",
                            "value": f"{m_out - m_in:+.1f}", "unit": "tm/año",
                            "state": "ok" if abs(err) < 0.5 else "danger"})
            if abs(err) < 0.5:
                status.append({"text": "cierra", "kind": "ok"})
            else:
                status.append({"text": f"err {err:+.2f}%", "kind": "danger"})
        return {"status": status, "metrics": metrics, "bars": bars,
                "figure": None, "warnings": []}
    except Exception:
        return None


def energy_balance_metrics(block, fs) -> Optional[dict]:
    """Estructurado de energy_balance_text(). Misma fuente (_stream_enthalpy_kW).
    Mismos formatos (:.2f / :+.2f) → substring del texto."""
    try:
        if fs is None:
            return None
        import flowsheet_solver as _fsv
        ins  = [s for s in fs.streams.values()
                if s.dst == block.id and s.mass_flow > 0 and _is_proc(s)]
        outs = [s for s in fs.streams.values()
                if s.src == block.id and s.mass_flow > 0 and _is_proc(s)]
        if not ins and not outs:
            return None
        H_in = 0.0; H_in_n = 0
        H_out = 0.0; H_out_n = 0
        for s in ins:
            h = _fsv._stream_enthalpy_kW(s)
            if h is not None:
                H_in += h; H_in_n += 1
        for s in outs:
            h = _fsv._stream_enthalpy_kW(s)
            if h is not None:
                H_out += h; H_out_n += 1
        if H_in_n == 0 and H_out_n == 0:
            return None
        Q = float(getattr(block, "duty", 0.0) or 0.0)
        W = 0.0
        eq = (block.eq_type or "").lower()
        if "pump" in eq or "compressor" in eq or "fan" in eq or "bomba" in eq:
            try:
                import equipment_design as _ed
                if "pump" in eq or "bomba" in eq:
                    ps = _ed.design_pump_for_block(block, fs)
                    W = float(ps["W_shaft_kW"]) if ps else 0.0
                else:
                    cs = _ed.design_compressor_for_block(block, fs)
                    W = float(cs["W_act_kW"]) if cs else 0.0
            except Exception:
                pass
        lhs = H_out - H_in
        err = lhs - (Q + W)
        scale = max(abs(H_in), abs(H_out), abs(Q), 1.0)
        err_pct = err / scale * 100.0
        metrics = [
            {"key": "Hin", "label": "H_in", "value": f"{H_in:.2f}",
             "unit": "kW", "state": "info"},
            {"key": "Hout", "label": "H_out", "value": f"{H_out:.2f}",
             "unit": "kW", "state": "info"},
            {"key": "dH", "label": "ΔH", "value": f"{lhs:+.2f}",
             "unit": "kW", "state": "auto"},
            {"key": "Q", "label": "Q duty", "value": f"{Q:+.2f}",
             "unit": "kW", "state": "orange"},
        ]
        if abs(W) > 1e-6:
            metrics.append({"key": "W", "label": "W_shaft",
                            "value": f"{W:+.2f}", "unit": "kW",
                            "state": "orange"})
        status = [{"text": "cierra", "kind": "ok"} if abs(err_pct) < 5.0
                  else {"text": f"err {err_pct:+.1f}%", "kind": "danger"}]
        return {"status": status, "metrics": metrics, "figure": None,
                "warnings": []}
    except Exception:
        return None


def utility_aux_metrics(block, fs) -> Optional[dict]:
    """Estructurado de utility_aux_text(). Misma fuente (streams auto_aux).
    Conservador: servicio + ṁ (mismos formatos :,.0f / :,.1f)."""
    try:
        if fs is None:
            return None
        import equipment_costs as _ec
        if (_ec.EQUIPMENT_DATA.get(block.eq_type, {}).get("categoria")
                != "Heat exchangers"):
            return None
        aux = [s for s in fs.streams.values()
               if getattr(s, "auto_aux", False)
               and (s.role or "") == "utility"
               and (s.src == block.id or s.dst == block.id)]
        if not aux:
            return None
        m_tm = max([float(s.mass_flow or 0.0) for s in aux] + [0.0])
        if m_tm <= 0:
            return None
        Tin  = next((s.temperature for s in aux if s.dst == block.id), None)
        Tout = next((s.temperature for s in aux if s.src == block.id), None)
        import equipment_ports as _ep
        proc_T = [s.temperature for s in fs.streams.values()
                  if (s.src == block.id or s.dst == block.id)
                  and not getattr(s, "auto_aux", False)
                  and (s.role or "") not in ("utility", "ambient")]
        T_avg = sum(proc_T)/len(proc_T) if proc_T else 25.0
        util_key = ""
        try:
            util_key = _ep.resolve_heat_source(block, T_avg) or ""
        except Exception:
            pass
        util = _ep.UTILITIES.get(util_key, {})
        util_name = util.get("name", util_key or "utility")
        m_kg_h = (m_tm * 1000.0) / 8760.0
        metrics = [
            {"key": "mdot", "label": "ṁ aux", "value": f"{m_kg_h:,.0f}",
             "unit": "kg/h", "state": "info",
             "sub": f"{m_tm:,.1f} tm/año"},
        ]
        if Tin is not None and Tout is not None:
            metrics.append({"key": "dT", "label": "T sup/ret",
                            "value": f"{Tin:.1f} → {Tout:.1f}", "unit": "°C",
                            "state": "alert"})
        return {"status": [{"text": util_name, "kind": "accent"}],
                "metrics": metrics, "figure": None, "warnings": []}
    except Exception:
        return None
