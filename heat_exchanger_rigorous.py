"""
heat_exchanger_rigorous.py — diseño térmico riguroso de intercambiadores.

Reemplaza los ΔT_lm hardcoded (DTLM_TYPICAL) por el ΔT_lm REAL calculado a
partir de las cuatro temperaturas de las corrientes, con el factor de
corrección F para configuraciones multi-paso shell-and-tube y coeficientes
globales U por servicio.  No reemplaza un diseño mecánico (Kern/Bell-Delaware)
— es una estimación de primer orden físicamente coherente que sustituye los
números mágicos del sizing.

Fuentes:
  · Perry's Chemical Engineers' Handbook, 8th ed., Ch. 11 (Heat-Transfer
    Equipment) — Tabla 11-3 (coeficientes globales típicos U).
  · Sinnott & Towler, Chemical Engineering Design, 6th ed., Ch. 19 —
    Tabla 19.1 (typical overall coefficients), §19.4 (ΔT_lm y factor F).
  · Kern, D.Q., Process Heat Transfer, 1950, Ch. 7 (LMTD, correction
    factor charts).
  · Bowman, Mueller & Nagle, "Mean Temperature Difference in Design",
    Trans. ASME 62 (1940): 283-294 — ecuación analítica de F para
    1-shell / 2-tube y reducción multi-carcasa.

Convención de signos: todas las temperaturas en °C (o K, es indiferente
para ΔT).  "hot" = corriente que cede calor (T baja a lo largo del equipo);
"cold" = corriente que lo recibe.
"""
import math
from typing import Optional, Tuple

_SQRT2 = math.sqrt(2.0)


def compute_lmtd_real(T_hot_in, T_hot_out, T_cold_in, T_cold_out,
                      flow: str = "counter") -> Tuple[Optional[float], Optional[str]]:
    """ΔT_lm real desde las 4 temperaturas terminales.

    Args:
        T_hot_in/out:  temperaturas de la corriente caliente (entrada/salida).
        T_cold_in/out: temperaturas de la corriente fría (entrada/salida).
        flow: 'counter' (contracorriente) o 'parallel'/'co' (paralelo).

    Returns:
        (ΔT_lm, warning).  warning es None salvo si hay CRUCE TÉRMICO
        (ΔT₁·ΔT₂ ≤ 0), en cuyo caso ΔT_lm es None y warning describe el
        cruce — un cruce significa que la configuración es termodinámicamente
        imposible para ese flujo (ej. el frío saldría más caliente que el
        caliente en contracorriente sin múltiples pasos).
    """
    if flow in ("parallel", "co", "cocurrent"):
        dT1 = T_hot_in - T_cold_in
        dT2 = T_hot_out - T_cold_out
    else:                                   # counter (default)
        dT1 = T_hot_in - T_cold_out
        dT2 = T_hot_out - T_cold_in

    if dT1 * dT2 <= 0.0:
        return None, (
            f"cruce térmico: ΔT1={dT1:.1f}, ΔT2={dT2:.1f} "
            f"(ΔT_lm indefinido para flujo '{flow}')")

    if abs(dT1 - dT2) < 1e-6:
        return dT1, None                    # límite ΔT1→ΔT2 (LMTD = ΔT)

    lmtd = (dT1 - dT2) / math.log(dT1 / dT2)
    return lmtd, None


def _f_one_shell(R: float, P: float) -> Optional[float]:
    """F para 1 paso de carcasa / 2 (o 2n) pasos de tubo (Bowman 1940)."""
    if P <= 1e-9:
        return 1.0                          # sin cambio de T en el frío → F=1
    if P >= 1.0:
        return None                         # P=1 imposible (ΔT_max alcanzado)

    if abs(R - 1.0) < 1e-6:
        # Límite R→1 (capacidades caloríficas iguales)
        num = 2.0 - P * (2.0 - _SQRT2)
        den = 2.0 - P * (2.0 + _SQRT2)
        if num <= 0.0 or den <= 0.0:
            return None
        ln_part = math.log(num / den)
        if abs(ln_part) < 1e-12:
            return 1.0
        return (_SQRT2 * P / (1.0 - P)) / ln_part

    S = math.sqrt(R * R + 1.0)
    ratio = (1.0 - P) / (1.0 - P * R)
    if ratio <= 0.0:
        return None
    numerator = S * math.log(ratio)
    da = 2.0 - P * (R + 1.0 - S)
    db = 2.0 - P * (R + 1.0 + S)
    if da <= 0.0 or db <= 0.0:
        return None
    denominator = (R - 1.0) * math.log(da / db)
    if abs(denominator) < 1e-12:
        return 1.0
    return numerator / denominator


def f_correction_factor(R: float, P: float, n_shell: int = 1,
                        n_tube: int = 2) -> Tuple[float, Optional[str]]:
    """Factor de corrección F del ΔT_lm para shell-and-tube multi-paso.

    Definiciones (Bowman 1940):
        R = (T_hot_in − T_hot_out) / (T_cold_out − T_cold_in)
        P = (T_cold_out − T_cold_in) / (T_hot_in  − T_cold_in)

    Para n_shell > 1 se reduce P por carcasa con la fórmula de Bowman y se
    evalúa F de una sola carcasa con ese P equivalente.

    Returns:
        (F, warning).  F clamped a [0.75, 1.0].  warning ≠ None si el F
        crudo cae por debajo de 0.75 — señal de que el diseño 1-2 es pobre
        y conviene más pasos de carcasa (o contracorriente verdadero).
    """
    try:
        N = max(int(n_shell), 1)
        if N == 1:
            F_raw = _f_one_shell(R, P)
        else:
            if abs(R - 1.0) < 1e-6:
                P_eq = P / (N - P * (N - 1))
            else:
                base = (1.0 - P * R) / (1.0 - P)
                if base <= 0.0:
                    F_raw = None
                    raise ValueError
                W = base ** (1.0 / N)
                P_eq = (W - 1.0) / (W - R)
            F_raw = _f_one_shell(R, P_eq)
    except (ValueError, ZeroDivisionError):
        F_raw = None

    if F_raw is None:
        return 0.75, ("F no computable (P/R fuera de dominio físico) — "
                      "asumido 0.75 conservador")
    warning = None
    if F_raw < 0.75:
        warning = (f"F={F_raw:.3f} < 0.75 — diseño shell-tube ineficiente "
                   f"(cruce de temperaturas); considerar {n_shell + 1} "
                   f"pasos de carcasa o configuración a contracorriente")
    F = min(1.0, max(0.75, F_raw))
    return F, warning


# ─────────────────────────────────────────────────────────────
# Coeficientes globales U por servicio (Perry 11-3 / Sinnott 19.1)
# Valores mid-range en W/m²·K.
# ─────────────────────────────────────────────────────────────
_U_SENSIBLE = {
    ("gas", "gas"):       55,     # gas-gas (baja P): 10-50; (alta P) hasta 500
    ("gas", "liquid"):    120,    # gas-líquido
    ("liquid", "gas"):    120,
    ("liquid", "liquid"): 500,    # líquido-líquido (orgánicos): 250-750
}
_U_CONDENSATION = 900             # condensación de vapor (orgánico ~700, steam ~1200)
_U_EVAPORATION  = 1000            # evaporación / ebullición forzada
_U_REFRIGERANT  = 400             # servicios con refrigerante
_U_DEFAULT      = 300             # conservador si no matchea


def _norm_phase(fluid: str) -> str:
    f = (fluid or "").lower()
    if any(k in f for k in ("gas", "vapor", "vap")):
        return "gas"
    return "liquid"


def u_typical_by_service(hot_fluid: str, cold_fluid: str,
                         phase_change=None) -> int:
    """Coeficiente global U (W/m²·K) según el servicio.

    Args:
        hot_fluid/cold_fluid: descripción de fase ('gas','vapor','liquid',...).
        phase_change: None | 'condensation' | 'evaporation' | 'refrigerant'.
                      (También acepta True como sinónimo de 'condensation'
                       cuando el lado caliente condensa.)

    Returns:
        U mid-range del servicio; default conservador (300) si no matchea.
    """
    pc = phase_change
    if pc is True:
        pc = "condensation"
    if isinstance(pc, str):
        pcl = pc.lower()
        if "cond" in pcl:
            return _U_CONDENSATION
        if "evap" in pcl or "boil" in pcl:
            return _U_EVAPORATION
        if "refrig" in pcl:
            return _U_REFRIGERANT
    key = (_norm_phase(hot_fluid), _norm_phase(cold_fluid))
    return _U_SENSIBLE.get(key, _U_DEFAULT)


def check_approach(T_hot_out, T_cold_in, dT_min: float = 10.0
                   ) -> Optional[str]:
    """Verifica el approach mínimo (pinch) en el extremo frío.

    En contracorriente el menor ΔT suele darse entre la salida del caliente
    y la entrada del frío.  Si T_hot_out − T_cold_in < dT_min el diseño
    requiere área infinita / es infactible.

    Returns:
        None si OK, o un warning describiendo la violación.
    """
    approach = T_hot_out - T_cold_in
    if approach < dT_min:
        return (f"approach mínimo violado: ΔT={approach:.1f} K "
                f"< {dT_min:.0f} K (T_hot_out={T_hot_out:.1f}, "
                f"T_cold_in={T_cold_in:.1f})")
    return None
