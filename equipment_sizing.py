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

def size_heat_exchanger(block, fs) -> Optional[float]:
    """A = |Q| / (U · ΔT_lm).  Q de block.duty [kW], devuelve m².

    Precedencia para U y ΔT_lm:
      1. block.U_override / block.dtlm_override (si > 0)
      2. U_TYPICAL[eq_type] / DTLM_TYPICAL[eq_type]
      3. U_DEFAULT (400) / DTLM_DEFAULT (40)
    """
    Q = abs(float(block.duty or 0.0))
    if Q <= 0:
        return None
    U_user  = getattr(block, "U_override",    None)
    dT_user = getattr(block, "dtlm_override", None)
    U  = (U_user  if (U_user  is not None and U_user  > 0)
          else U_TYPICAL.get(block.eq_type, U_DEFAULT))
    dT = (dT_user if (dT_user is not None and dT_user > 0)
          else DTLM_TYPICAL.get(block.eq_type, DTLM_DEFAULT))
    A = Q * 1000.0 / (U * dT)            # Q en kW → W
    return max(A, 0.5)


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
    """V = caudal · 7 días / ρ — buffer típico de almacenamiento."""
    flows = [s.mass_flow for s in fs.streams.values()
              if s.src == block.id or s.dst == block.id]
    if not flows:
        return None
    m_yr = max(flows)
    if m_yr <= 0:
        return None
    m_s = _flow_kg_s(m_yr)
    tau = 7 * 86400         # 7 días
    V = m_s / RHO_LIQUID_DEFAULT * tau
    return max(V, 10.0)


def size_evaporator(block, fs) -> Optional[float]:
    """A = Q / (U·ΔT).  U=1500, ΔT=20 K típico."""
    Q = abs(float(block.duty or 0.0))
    if Q <= 0:
        return None
    A = Q * 1000.0 / (1500 * 20.0)
    return max(A, 1.0)


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
        sizer = SIZER_BY_CAT.get(cat)
        if sizer is None:
            continue
        try:
            S_new = sizer(b, fs)
        except Exception:
            S_new = None
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
