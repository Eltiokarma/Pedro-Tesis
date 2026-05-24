"""
equipment_sizing.py — Auto-sizing del parámetro S desde resultados del solver.

Cada categoría de equipo tiene un S característico que correlaciona con
el costo Turton (área para HX, volumen para reactores, potencia para
bombas, etc.).  Hoy el user pone S a mano; esto lo computa desde
condiciones físicas reales (duty, mass_flow, ΔP, T_op, P_op).

Fórmulas:
  · Heat exchangers   A = |Q| / (U · ΔTlm)         [m²]
  · Fired heaters     S = duty                      [kW]
  · Reactors          V = m_in / ρ · τ              [m³]
  · Pumps             W = m · ΔP / (ρ · η)         [kW]
  · Compressors       W politrópico                 [kW]
  · Towers            V = π·D²/4 · H (Souders-B.)  [m³]
  · Vessels           V = m_in/ρ · τ_separator     [m³]
  · Storage tanks     V = caudal · 7 días / ρ      [m³]
  · Evaporators       A = Q / (U·ΔT)               [m²]

Los valores típicos U, τ, η, ρ vienen de Turton Tabla 11.11 y rangos
industriales estándar.  El sizing NO reemplaza un diseño riguroso —
es una primera estimación que reemplaza el número mágico inicial por
algo físicamente coherente.
"""
import math
from typing import Optional, List, Tuple

import equipment_costs as ec
import equipment_design as ed
from flowsheet_model import SEC_PER_YEAR, TM_TO_KG

try:
    import thermo_db as _td
except ImportError:
    _td = None


# ─────────────────────────────────────────────────────────────
# Constantes típicas (Turton § 11.4, Perry Ch 11)
# ─────────────────────────────────────────────────────────────

# Coeficientes globales U (W/m²·K) — valor mid-range por tipo de HX
U_TYPICAL = {
    "Heat exch. — floating head":   500,
    "Heat exch. — fixed tube":      400,
    "Heat exch. — U-tube":          500,
    "Heat exch. — double pipe":     300,
    "Heat exch. — multiple pipe":   300,
    "Heat exch. — flat plate":      800,
    "Heat exch. — spiral plate":    600,
    "Heat exch. — air cooler":      350,
    "Heat exch. — kettle reboiler": 800,
    # Condensación: U alto (transición de fase + agua/aire del lado frío).
    "Heat exch. — condenser shell-tube":  1000,
    "Heat exch. — condenser air-cooled":  600,
    # Evaporadores: ebullición forzada con U alto (Turton §11).  El
    # catálogo solo expone "Evaporator — vertical"; si se agregan otros
    # tipos (forced circ., falling film) declarar acá su U propio.
    "Evaporator — vertical":              1500,
}
U_DEFAULT = 400

# ΔT_lm típicos por tipo de servicio (K)
DTLM_TYPICAL = {
    "Heat exch. — air cooler":      30.0,
    "Heat exch. — kettle reboiler": 25.0,
    "Heat exch. — floating head":   40.0,
    "Heat exch. — fixed tube":      40.0,
    "Heat exch. — U-tube":          40.0,
    "Heat exch. — flat plate":      15.0,   # plate-frame con close-approach
    "Heat exch. — spiral plate":    25.0,
    "Heat exch. — double pipe":     45.0,
    "Heat exch. — multiple pipe":   45.0,
    # Condensación casi isotérmica → ΔT_lm chico (la T del fluido que
    # condensa cambia poco; el lado frío hace la mayor variación).
    "Heat exch. — condenser shell-tube":  15.0,
    "Heat exch. — condenser air-cooled":  20.0,
    # Evaporador: ΔT moderado entre vapor de calefacción y el líquido
    # en ebullición (Turton §11, típico 20 K).
    "Evaporator — vertical":              20.0,
}
DTLM_DEFAULT = 40.0

# Tiempos de residencia τ (s) por tipo de reactor
TAU_REACTOR = {
    "Reactor — autoclave":          1800,    # batch agitado 30 min
    "Reactor — jacketed agitated":  600,     # CSTR 10 min
    "Reactor — jacketed non-agit.": 60,      # tubular ~ 1 min
    "Reactor — CSTR (agitado)":     600,     # CSTR 10 min (igual que jacketed agit.)
    "Reactor — PFR (tubular)":      60,      # tubular ~ 1 min (igual que non-agit.)
}
TAU_REACTOR_DEFAULT = 600

# Tiempos de residencia para vessels / separadores (s)
TAU_VESSEL_DEFAULT = 300        # 5 min separación bifásica

# Densidades default (kg/m³)
RHO_LIQUID_DEFAULT = 800.0
RHO_GAS_DEFAULT    = 20.0       # gas comprimido típico


def _mw_avg_kg_per_mol(stream) -> float:
    """MW promedio (kg/mol) del stream desde thermo_db, ponderada por la
    composición.  §4.3: ya no usamos M=0.030 hardcoded.  Si la composición
    falta o thermo_db no resuelve, devuelve fallback 0.029 (aire).
    """
    comp = getattr(stream, "composition", None) or (
        {stream.main_component: 1.0} if getattr(stream, "main_component", None) else {}
    )
    if not comp or _td is None:
        return 0.029
    mw_g = 0.0
    total = 0.0
    for c, w in comp.items():
        co = _td.get(c)
        if co is None or getattr(co, "mw", 0) <= 0:
            continue
        mw_g += w * co.mw
        total += w
    if total <= 0:
        return 0.029
    return (mw_g / total) * 1e-3      # g/mol → kg/mol


def _rho_estimate(stream, T_K=None, P_bar=None):
    """Densidad del stream.  Gas via ideal P·M/(R·T) usando MW real de
    componentes (§4.3); liquid 800 kg/m³ default si no hay info mejor.
    """
    phase = (stream.phase or "").lower()
    if "gas" in phase or "vapor" in phase:
        T = T_K or (stream.temperature + 273.15)
        P = P_bar or (getattr(stream, "pressure_bar", 1.0) or 1.0)
        M = _mw_avg_kg_per_mol(stream)
        return P * 1e5 * M / (8.314 * max(T, 100))
    return RHO_LIQUID_DEFAULT


def _flow_kg_s(mass_flow_tm_yr):
    """tm/año → kg/s."""
    return mass_flow_tm_yr * TM_TO_KG / SEC_PER_YEAR


# ─────────────────────────────────────────────────────────────
# Sizers por categoría
# ─────────────────────────────────────────────────────────────

def _process_streams(fs, block):
    """Separa corrientes de proceso (role != utility/ambient) de un HX."""
    ins  = [s for s in fs.streams.values() if s.dst == block.id]
    outs = [s for s in fs.streams.values() if s.src == block.id]
    proc_in  = [s for s in ins  if (s.role or "") not in ("utility", "ambient")]
    proc_out = [s for s in outs if (s.role or "") not in ("utility", "ambient")]
    return ins, outs, proc_in, proc_out


def _pair_by_mass(ins, outs):
    """Empareja entradas con salidas por mass_flow más cercano (misma
    línea física conserva caudal).  Devuelve lista de (in, out)."""
    pairs, used = [], set()
    for i in ins:
        best, bd = None, float("inf")
        for j, o in enumerate(outs):
            if j in used:
                continue
            d = abs((i.mass_flow or 0) - (o.mass_flow or 0))
            if d < bd:
                bd, best = d, j
        if best is not None:
            used.add(best)
            pairs.append((i, outs[best]))
    return pairs


def _rigorous_lmtd_cross(fs, block, diag):
    """ΔT_lm + F + U para un cross-exchange (proceso-proceso).  Devuelve
    (U, dTlm, F) o None si faltan las 4 T coherentes."""
    import heat_exchanger_rigorous as hxr
    ins  = [s for s in fs.streams.values() if s.dst == block.id]
    outs = [s for s in fs.streams.values() if s.src == block.id]
    pairs = _pair_by_mass(ins, outs)
    hot = next(((i, o) for i, o in pairs if i.temperature > o.temperature), None)
    cold = next(((i, o) for i, o in pairs if o.temperature > i.temperature), None)
    if hot is None or cold is None:
        return None
    T_hi, T_ho = hot[0].temperature, hot[1].temperature
    T_ci, T_co = cold[0].temperature, cold[1].temperature
    lmtd, w = hxr.compute_lmtd_real(T_hi, T_ho, T_ci, T_co, flow="counter")
    if w:
        diag["warnings"].append(w)
    if lmtd is None:
        return None
    denom_R = (T_co - T_ci)
    denom_P = (T_hi - T_ci)
    R = (T_hi - T_ho) / denom_R if abs(denom_R) > 1e-9 else 1.0
    P = (T_co - T_ci) / denom_P if abs(denom_P) > 1e-9 else 0.0
    F, wf = hxr.f_correction_factor(R, P, n_shell=1, n_tube=2)
    if wf:
        diag["warnings"].append(wf)
    ap = hxr.check_approach(T_ho, T_ci)
    if ap:
        diag["warnings"].append(ap)
    U = hxr.u_typical_by_service(hot[0].phase, cold[0].phase)
    diag["cross_check"] = "cross-exchange (proceso-proceso)"
    return U, lmtd, F


def _rigorous_lmtd_simple(fs, block, diag):
    """ΔT_lm + U para un HX simple (proceso + utility implícita).  La
    utility se modela isotérmica a la T representativa de su T_range.
    Devuelve (U, dTlm, F=1.0) o None si faltan datos."""
    import heat_exchanger_rigorous as hxr
    import equipment_ports as ep
    _, _, proc_in, proc_out = _process_streams(fs, block)
    if len(proc_in) != 1 or len(proc_out) != 1:
        return None
    T_pin, T_pout = proc_in[0].temperature, proc_out[0].temperature
    duty = float(block.duty or 0.0)
    T_avg = (T_pin + T_pout) / 2.0
    util_key = ep.resolve_heat_source(block, T_avg)
    if not util_key or util_key not in ep.UTILITIES:
        return None
    util = ep.UTILITIES[util_key]
    t_lo, t_hi = util.get("T_range", (None, None))
    if t_lo is None:
        return None
    util_type = util.get("type", "")

    # Cambio de fase del PROCESO: vapor→líquido = condensación;
    # líquido→vapor = evaporación.  Define el U de servicio.
    ph_in  = (proc_in[0].phase  or "").lower()
    ph_out = (proc_out[0].phase or "").lower()
    _is_vap = lambda p: any(k in p for k in ("vap", "gas"))
    pc = None
    if _is_vap(ph_in) and not _is_vap(ph_out):
        pc = "condensation"
    elif _is_vap(ph_out) and not _is_vap(ph_in):
        pc = "evaporation"

    if duty > 0:
        # calentamiento: la utility (vapor/horno) es el lado CALIENTE,
        # isotérmica a la T alta de su rango.
        T_hi = T_ho = t_hi
        T_ci, T_co = T_pin, T_pout
        if pc is None and util.get("type") == "heating" \
                and util_key.startswith("steam"):
            pc = "condensation"        # vapor de calefacción condensa
    elif util_type == "generation":
        # waste-heat boiler: el lado frío VAPORIZA BFW a T constante
        # (Tsat del vapor producido) — no es el rango sensible de CW.
        T_sat = float(util.get("T_sat", t_lo))
        T_ci = T_co = T_sat
        T_hi, T_ho = T_pin, T_pout
    else:
        # enfriamiento: la utility (agua/refrigerante) es el lado FRÍO,
        # entra a la T baja del rango y sube ~ΔT sensible.
        T_ci = t_lo
        T_co = min(t_lo + 15.0, t_hi)
        T_hi, T_ho = T_pin, T_pout
        if pc is None and util_key == "refrigeration":
            pc = "refrigerant"

    lmtd, w = hxr.compute_lmtd_real(T_hi, T_ho, T_ci, T_co, flow="counter")
    if w:
        diag["warnings"].append(w)
    if lmtd is None:
        return None
    ap = hxr.check_approach(T_ho, T_ci)
    if ap:
        diag["warnings"].append(ap)

    # Guard de rango (punto 5): si la T del proceso excede el T_max de la
    # utility por >50°C, advertir (típico WHB modelado como cooler normal).
    t_proc_max = max(T_pin, T_pout)
    if t_proc_max > t_hi + 50.0:
        extra = (" — verificar si debería ser un WHB/steam-generator"
                 if util_type == "cooling" else "")
        diag["warnings"].append(
            f"utility '{util_key}' fuera de rango: T_proceso="
            f"{t_proc_max:.0f}°C vs T_max_util={t_hi:.0f}°C{extra}")

    # U por servicio: si hay cambio de fase usar el U del servicio; si no,
    # preferir el U calibrado por tipo de equipo (U_TYPICAL) — coherente
    # con el catálogo y con el sizing previo.
    if pc is not None:
        U = hxr.u_typical_by_service(proc_in[0].phase, "water",
                                     phase_change=pc)
    else:
        U = U_TYPICAL.get(block.eq_type) or hxr.u_typical_by_service(
            proc_in[0].phase, "liquid")
    diag["cross_check"] = f"simple HX (utility={util_key})"
    return U, lmtd, 1.0


def size_heat_exchanger(block, fs):
    """A = |Q| / (U · F · ΔT_lm).  Q de block.duty [kW], devuelve
    (A_m², diagnostics).

    Cálculo riguroso (heat_exchanger_rigorous):
      · cross-exchange → ΔT_lm real de las 4 T + factor F (Bowman 1940)
        + U por servicio (Perry 11-3 / Sinnott 19.1).
      · HX simple      → ΔT_lm proceso vs T de la utility (T_range).
    Fallback a U_TYPICAL/DTLM_TYPICAL si faltan datos (con warning).

    Overrides del bloque (U_override / dtlm_override > 0) siempre ganan.

    diagnostics = {U_used, dTlm, F, cross_check, warnings}.
    """
    diag = {"U_used": None, "dTlm": None, "F": 1.0,
            "cross_check": None, "warnings": []}
    # Los WHB dedicados (Sinnott) se dimensionan por caudal de vapor [kg/h],
    # no por área — los maneja size_whb.  Acá NO computamos área para ellos.
    if block.eq_type in WHB_STEAM_SIZED:
        diag["cross_check"] = "WHB (dimensionado por caudal de vapor, ver size_whb)"
        return None, diag
    Q = abs(float(block.duty or 0.0))
    if Q <= 0:
        return None, diag

    U_user  = getattr(block, "U_override",    None)
    dT_user = getattr(block, "dtlm_override", None)

    rig = None
    try:
        import flowsheet_solver as _fsv
        if _fsv.is_cross_exchange(fs, block):
            rig = _rigorous_lmtd_cross(fs, block, diag)
        else:
            rig = _rigorous_lmtd_simple(fs, block, diag)
    except Exception as e:               # nunca romper el sizing por esto
        diag["warnings"].append(f"cálculo riguroso falló ({e!r})")
        rig = None

    if rig is not None:
        U, dT, F = rig
    else:
        diag["warnings"].append(
            "fallback: U/ΔT_lm de tabla (datos insuficientes para "
            "cálculo riguroso)")
        U = U_TYPICAL.get(block.eq_type, U_DEFAULT)
        dT = DTLM_TYPICAL.get(block.eq_type, DTLM_DEFAULT)
        F = 1.0

    # overrides del usuario tienen precedencia absoluta
    if U_user is not None and U_user > 0:
        U = U_user
    if dT_user is not None and dT_user > 0:
        dT = dT_user

    diag["U_used"], diag["dTlm"], diag["F"] = U, dT, F
    A = Q * 1000.0 / (U * F * dT)        # Q en kW → W
    return max(A, 0.5), diag


def size_fired_heater(block, fs) -> Optional[float]:
    """S = duty térmico [kW] directo (Turton usa Q como sizing param)."""
    Q = abs(float(block.duty or 0.0))
    if Q <= 0:
        return None
    return max(Q, 1000.0)


def size_reactor(block, fs) -> Optional[float]:
    """V = m_in/ρ · τ.  Si block.reactor_volume_L declarado, usar."""
    if getattr(block, "reactor_volume_L", 0) > 0:
        return float(block.reactor_volume_L) / 1000.0
    ins = [s for s in fs.streams.values() if s.dst == block.id]
    if not ins:
        return None
    m_yr = sum(s.mass_flow for s in ins)
    if m_yr <= 0:
        return None
    m_s = _flow_kg_s(m_yr)
    rho = _rho_estimate(ins[0],
                          T_K=getattr(block, "T_op_K", 0) or None,
                          P_bar=getattr(block, "P_op_bar", 0) or None)
    tau = TAU_REACTOR.get(block.eq_type, TAU_REACTOR_DEFAULT)
    V = m_s / rho * tau
    return max(V, 0.1)


def size_pump(block, fs) -> Optional[float]:
    """Delega a equipment_design.design_pump_for_block (§4.1).
    Una sola fuente de verdad para hidráulica de bombas.  Devuelve
    potencia eléctrica [kW]."""
    res = ed.design_pump_for_block(block, fs)
    if res is None:
        return None
    W = res.get("W_elec_kW") or res.get("W_shaft_kW")
    if W is None or W <= 0:
        return None
    return max(W, 1.0)


def size_compressor(block, fs) -> Optional[float]:
    """Delega a equipment_design.design_compressor_for_block (§4.1).
    Una sola fuente de verdad para isentrópica de compresores.
    Devuelve potencia real al eje [kW]."""
    res = ed.design_compressor_for_block(block, fs)
    if res is None:
        return None
    W = res.get("W_act_kW")
    if W is None or W <= 0:
        return None
    return max(W, 5.0)


def size_tower(block, fs) -> Optional[float]:
    """V = π·D²/4 · H para columnas de destilación.

    Souders-Brown (Perry 8ª §14, Walas §13.1):

        v_max = K · sqrt( (ρ_L − ρ_V) / ρ_V )    [m/s]

    Con K en m/s.  Defaults canónicos en econ_defaults.COLUMN_DEFAULTS:
        K_SB           0.06 m/s  (24" tray spacing, sin foaming severo)
        tray_spacing   0.6 m     (24")
        head_height    3.0 m     (sumidero + cabezal)
        tray_eff       1.0       (asume N_real = N_teorico)
        HETP           0.5 m     (random packing; estructurado ~0.3)

    Precedencia por parámetro:
        1. block.{tray_spacing_m, K_souders_brown, ...} si > 0
        2. econ_defaults.COLUMN_DEFAULTS[*]
        3. fallback hardcoded conservador

    Si block.packing_type ∈ {'random','structured'}, la altura por
    etapa se calcula con HETP_m en lugar de tray_spacing_m, y
    N_real = N_teorico (no se aplica tray_efficiency).
    """
    # Defaults canónicos centralizados
    try:
        import econ_defaults as _ed
        defaults = _ed.get_column_defaults()
    except Exception:
        defaults = {"K_souders_brown": 0.06, "tray_spacing_m": 0.6,
                     "column_head_height_m": 3.0, "tray_efficiency": 1.0,
                     "HETP_m": 0.5}
    def _pick(attr, key):
        v = getattr(block, attr, None)
        return v if (v is not None and v > 0) else defaults[key]
    K_SB        = _pick("K_souders_brown",      "K_souders_brown")
    tray_space  = _pick("tray_spacing_m",       "tray_spacing_m")
    head        = _pick("column_head_height_m", "column_head_height_m")
    tray_eff    = _pick("tray_efficiency",      "tray_efficiency")
    HETP        = _pick("HETP_m",               "HETP_m")

    # N teóricas: del solver FUG (column_N) o declarado por el user.
    N_th = (getattr(block, "_column_N", 0)
            or getattr(block, "column_N_stages", 0) or 10)
    # Convertir a N reales según tipo de columna.
    packing_type = (getattr(block, "packing_type", "") or "").lower()
    if packing_type in ("random", "structured"):
        # Empacada: H = N_teorico · HETP + head (tray_eff ignorada,
        # HETP ya incorpora la eficiencia del relleno).
        H = N_th * HETP + head
    else:
        # Platos: N_real = N_teorico / tray_eff (eff < 1 → más platos
        # reales que teóricos para alcanzar la separación).
        N_real = N_th / max(tray_eff, 1e-3)
        H = N_real * tray_space + head
    # Vapor flow (preferir corriente declarada vapor/gas)
    vap = next((s for s in fs.streams.values()
                if s.dst == block.id
                and any(k in (s.phase or "").lower()
                          for k in ("vap", "gas"))), None)
    if vap is None:
        feeds = [s for s in fs.streams.values() if s.dst == block.id]
        if not feeds:
            return None
        vap = feeds[0]
    m_s = _flow_kg_s(vap.mass_flow)
    # ρ_V con MW real (§4.3).  Forzamos fase gas en _rho_estimate.
    T_vap = (vap.temperature or 25.0) + 273.15
    P_vap = getattr(vap, "pressure_bar", 1.0) or 1.0
    M_vap = _mw_avg_kg_per_mol(vap)
    rho_v = P_vap * 1e5 * M_vap / (8.314 * max(T_vap, 100))
    # ρ_L: si tenemos stream líquido (bottoms o reflux), tomarlo; si no, 800.
    liq = next((s for s in fs.streams.values()
                if s.src == block.id
                and "liq" in (s.phase or "").lower()), None)
    rho_l = _rho_estimate(liq) if liq is not None else RHO_LIQUID_DEFAULT
    if m_s <= 0 or rho_v <= 0 or rho_l <= rho_v:
        D = 1.0
    else:
        Q_v = m_s / rho_v          # m³/s
        v_max = K_SB * math.sqrt((rho_l - rho_v) / rho_v)
        D = math.sqrt(4 * Q_v / (math.pi * v_max))
        D = max(D, 0.3)
    V = math.pi * D**2 / 4 * H
    return max(V, 0.5)


def size_vessel(block, fs) -> Optional[float]:
    """V = m_in/ρ · τ_separator (5 min default)."""
    ins = [s for s in fs.streams.values() if s.dst == block.id]
    if not ins:
        return None
    m_s = _flow_kg_s(sum(s.mass_flow for s in ins))
    if m_s <= 0:
        return None
    rho = _rho_estimate(ins[0],
                          T_K=getattr(block, "flash_T_K", None),
                          P_bar=getattr(block, "flash_P_bar", None))
    V = m_s / rho * TAU_VESSEL_DEFAULT
    return max(V, 0.5)


def size_storage_tank(block, fs) -> Optional[float]:
    """V = caudal · 7 días / ρ — buffer típico de almacenamiento.

    Usa _rho_estimate(stream) para detectar gas vs líquido en lugar de
    asumir siempre RHO_LIQUID_DEFAULT. Esto corrige el sub-sizing 400x
    de tanques de gas comprimido (e.g., H₂ a 25 bar tiene ρ≈2 kg/m³,
    no 800).
    """
    streams = [s for s in fs.streams.values()
                if s.src == block.id or s.dst == block.id]
    if not streams:
        return None
    # Tomar el stream con mayor flow para dimensionar
    stream_ref = max(streams, key=lambda s: s.mass_flow)
    if stream_ref.mass_flow <= 0:
        return None
    m_s = _flow_kg_s(stream_ref.mass_flow)
    rho = _rho_estimate(stream_ref)
    tau = 7 * 86400         # 7 días
    V = m_s / rho * tau
    return max(V, 10.0)


def size_evaporator(block, fs) -> Optional[float]:
    """A = |Q| / (U·ΔT_lm).  Mismo patrón que size_heat_exchanger,
    permite override por bloque y catálogo por tipo."""
    Q = abs(float(block.duty or 0.0))
    if Q <= 0:
        return None
    U_user  = getattr(block, "U_override",    None)
    dT_user = getattr(block, "dtlm_override", None)
    U  = (U_user  if (U_user  is not None and U_user  > 0)
          else U_TYPICAL.get(block.eq_type, 1500))
    dT = (dT_user if (dT_user is not None and dT_user > 0)
          else DTLM_TYPICAL.get(block.eq_type, 20.0))
    A = Q * 1000.0 / (U * dT)
    return max(A, 1.0)


# Clases WHB dedicadas (Sinnott): el parámetro de tamaño S es el caudal de
# vapor generado [kg/h], no área — se dimensionan con size_whb, no con
# size_heat_exchanger.  (El kettle reboiler NO está acá: su S sigue siendo
# área m² y usa el sizer de HX normal.)
WHB_STEAM_SIZED = (
    "Heat exch. — WHB packaged",
    "Heat exch. — WHB field erected",
)


def size_whb(block, fs) -> Optional[float]:
    """Dimensiona un waste-heat boiler por el caudal de vapor que genera.

        S [kg/h] = |Q [kW]| · 3600 / ΔH_vap [kJ/kg] · η_gen

    ΔH_vap y η salen de la utility de generación elegida (bfw_to_steam_*).
    Si el bloque no resuelve a una utility de generación, devuelve None.
    """
    import equipment_ports as ep
    Q_kW = abs(float(block.duty or 0.0))
    if Q_kW <= 0:
        return None
    _, _, proc_in, proc_out = _process_streams(fs, block)
    proc_T = [s.temperature for s in (proc_in + proc_out)]
    T_avg = (sum(proc_T) / len(proc_T)) if proc_T else 200.0
    heat_src = ep.resolve_heat_source(block, T_avg)
    util = ep.UTILITIES.get(heat_src)
    if not util or util.get("type") != "generation":
        return None
    dh_vap = util["delta_h"]
    eff    = util.get("efficiency", 0.85)
    S_kg_per_h = Q_kW * 3600.0 / dh_vap * eff
    return max(S_kg_per_h, 5_000.0)        # clamp al S_min del Packaged


def autoselect_whb_subtype(steam_kg_per_h):
    """Elige variante Packaged vs Field erected según producción de vapor.
    Regla simple: ≤50 000 kg/h → Packaged, >50 000 → Field erected.
    Función auxiliar exportable (todavía NO cableada a la UI ni a
    autoselect_heat_source)."""
    return ("Heat exch. — WHB packaged" if steam_kg_per_h <= 50_000
            else "Heat exch. — WHB field erected")


# ─────────────────────────────────────────────────────────────
# Dispatch + función pública
# ─────────────────────────────────────────────────────────────

SIZER_BY_CAT = {
    "Heat exchangers":   size_heat_exchanger,
    "Fired heaters":     size_fired_heater,
    "Reactors":          size_reactor,
    "Pumps":             size_pump,
    "Compressors":       size_compressor,
    "Vessels":           size_vessel,
    "Towers":            size_tower,
    "Storage":           size_storage_tank,
    "Evaporators":       size_evaporator,
}

# Sizers específicos por eq_type — tienen prioridad sobre SIZER_BY_CAT.
# Los WHB son categoría "Heat exchangers" pero su S es caudal de vapor
# [kg/h], no área, así que usan size_whb (no size_heat_exchanger).
SIZER_BY_EQTYPE = {
    "Heat exch. — WHB packaged":      size_whb,
    "Heat exch. — WHB field erected": size_whb,
}


def auto_size_blocks(fs, only_if_unset=False) -> List[Tuple[str, float, float, str, str]]:
    """Recorre fs.blocks y actualiza b.S desde las condiciones de
    operación (duty, mass_flow, ΔP, T_op, P_op).

    Args:
        only_if_unset: si True, solo updates blocks fuera de rango
                       Turton o con S=0.  Si False, sobreescribe siempre.

    Returns:
        Lista de tuples (block_name, S_old, S_new, unit, reason) para log.
    """
    results = []
    for b in fs.blocks.values():
        spec = ec.EQUIPMENT_DATA.get(b.eq_type, {})
        cat  = spec.get("categoria", "")
        # eq_type específico (ej. WHB → size_whb) tiene prioridad sobre cat.
        sizer = SIZER_BY_EQTYPE.get(b.eq_type) or SIZER_BY_CAT.get(cat)
        if sizer is None:
            continue
        try:
            S_new = sizer(b, fs)
        except Exception:
            S_new = None
        # size_heat_exchanger devuelve (A, diagnostics); el resto float.
        diag = None
        if isinstance(S_new, tuple):
            S_new, diag = S_new
            b._hx_diagnostics = diag      # inspeccionable desde la UI
        if S_new is None or S_new <= 0:
            continue
        S_old = float(b.S)
        if only_if_unset:
            S_min = spec.get("S_min", 0)
            S_max = spec.get("S_max", float("inf"))
            if S_min <= S_old <= S_max:
                continue
        # Clamp al rango Turton para que no caiga "fuera_rango"
        S_min = spec.get("S_min", 0)
        S_max = spec.get("S_max", float("inf"))
        if S_new < S_min:
            reason = f"computed {S_new:.2f}, clamped al S_min"
            S_new = S_min
        elif S_new > S_max:
            reason = f"computed {S_new:.2f}, clamped al S_max"
            S_new = S_max
        else:
            reason = "in range"
        if diag is not None and (diag.get("U_used") or diag.get("warnings")):
            extra = (f" [U={diag['U_used']:.0f} ΔTlm={diag['dTlm']:.1f} "
                     f"F={diag['F']:.2f}]") if diag.get("U_used") else ""
            if diag.get("warnings"):
                extra += " ⚠ " + "; ".join(diag["warnings"][:2])
            reason += extra
        b.S = S_new
        results.append((b.name, S_old, S_new, spec.get("S_unit", ""),
                          reason))
    return results


def format_sizing_log(results) -> str:
    """Format el log para mostrar en dialog/consola."""
    if not results:
        return "Auto-sizing: no se actualizó ningún bloque."
    out = [f"Auto-sizing: {len(results)} bloque(s) actualizados\n"]
    out.append(f"  {'Block':10} {'Old':>10} {'→':>3} {'New':>10}  Unit   Notes")
    out.append("  " + "─" * 60)
    for name, s_old, s_new, unit, reason in results:
        out.append(f"  {name:10} {s_old:>10.2f} {'→':>3} {s_new:>10.2f}  "
                    f"{unit:6} {reason}")
    return "\n".join(out)
