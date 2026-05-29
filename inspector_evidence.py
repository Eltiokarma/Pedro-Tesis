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
