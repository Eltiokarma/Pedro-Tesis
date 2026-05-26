"""mccabe_thiele.py — diseño gráfico de columnas binarias (McCabe-Thiele).

Calcula el diagrama McCabe-Thiele de un par LK/HK a partir de la VLE NRTL del
repo (nrtl.bubble_point) y de las specs que el bloque columna ya tiene
(z_F, x_D, x_B, R, q).  Es el motor del panel "Recomendación de columna":
dado el feed y las purezas objetivo, recomienda el número de etapas teóricas,
la etapa de alimentación y el reflujo mínimo, y devuelve las curvas/rectas
listas para dibujar.

Todo en FRACCIÓN MOLAR del componente liviano (LK), eje estándar McCabe-Thiele.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple


def equilibrium_curve(LK: str, HK: str, P_bar: float = 1.013,
                      n: int = 41) -> Optional[Tuple[List[float], List[float]]]:
    """Curva de equilibrio y_LK vs x_LK del binario LK/HK a P (vía NRTL)."""
    try:
        import nrtl
    except ImportError:
        return None
    xs: List[float] = []
    ys: List[float] = []
    for i in range(n + 1):
        x = i / n
        bp = nrtl.bubble_point([LK, HK], [x, 1.0 - x], P_bar)
        if bp is None:
            return None
        y = bp[1][0]
        xs.append(x)
        ys.append(max(0.0, min(1.0, y)))
    # Forzar extremos exactos (x=0→y=0, x=1→y=1)
    ys[0] = 0.0
    ys[-1] = 1.0
    return xs, ys


def _interp(xq: float, xs: List[float], ys: List[float]) -> float:
    """Interpolación lineal monótona (xs creciente)."""
    if xq <= xs[0]:
        return ys[0]
    if xq >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if xq <= xs[i]:
            t = (xq - xs[i - 1]) / (xs[i] - xs[i - 1])
            return ys[i - 1] + t * (ys[i] - ys[i - 1])
    return ys[-1]


def _x_from_y(yq: float, xs: List[float], ys: List[float]) -> float:
    """Inverso de la curva de equilibrio: dado y, el x tal que yEq(x)=y.
    Asume ys creciente (binario no-azeotrópico en la región de interés)."""
    if yq <= ys[0]:
        return xs[0]
    if yq >= ys[-1]:
        return xs[-1]
    for i in range(1, len(ys)):
        if yq <= ys[i]:
            dy = ys[i] - ys[i - 1]
            t = (yq - ys[i - 1]) / dy if abs(dy) > 1e-12 else 0.0
            return xs[i - 1] + t * (xs[i] - xs[i - 1])
    return xs[-1]


def design_from_block(block, fs) -> Optional[Dict]:
    """Construye el diagrama McCabe-Thiele de un bloque columna directamente
    desde el modelo: z_F del feed (fracción molar de LK en el binario LK/HK),
    x_D/x_B/R_factor de las specs del bloque.  None si no es una columna
    binaria resoluble.  Esta es la API que usa la UI para 'recomendar el
    diagrama' automáticamente al abrir la columna."""
    LK = getattr(block, "column_LK", "") or ""
    HK = getattr(block, "column_HK", "") or ""
    if not LK or not HK:
        return None
    x_D = float(getattr(block, "column_x_D_LK", 0.0) or 0.0)
    x_B = float(getattr(block, "column_x_B_LK", 0.0) or 0.0)
    R_factor = float(getattr(block, "column_R_factor", 1.3) or 1.3)
    ins = [s for s in fs.streams.values()
           if s.dst == block.id and (s.composition or {})]
    feed = next((s for s in ins if s.mass_flow > 0), ins[0] if ins else None)
    if feed is None:
        return None
    comp = feed.composition or {}
    try:
        import thermo_db as _td
    except ImportError:
        return None

    def _mol(name):
        m = comp.get(name, 0.0)
        o = _td.get(name)
        return (m / o.mw) if (o and o.mw > 0 and m > 0) else 0.0

    n_lk, n_hk = _mol(LK), _mol(HK)
    if n_lk + n_hk <= 0:
        return None
    z_F = n_lk / (n_lk + n_hk)
    P = float(getattr(feed, "pressure_bar", 1.013) or 1.013)
    return design(LK, HK, z_F, x_D, x_B, R=None, R_factor=R_factor,
                  q=1.0, P_bar=P)


def _r_min(xs, ys, z_F, x_D, q):
    """Reflujo mínimo: pinch = q-line ∩ curva de equilibrio.  None si no
    se puede determinar."""
    try:
        if abs(q - 1.0) < 1e-6:
            x_p = z_F
            y_p = _interp(z_F, xs, ys)
        else:
            q_slope = q / (q - 1.0)
            q_int = -z_F / (q - 1.0)
            x_p = z_F
            for i in range(1, len(xs)):
                f0 = (q_slope * xs[i - 1] + q_int) - ys[i - 1]
                f1 = (q_slope * xs[i] + q_int) - ys[i]
                if f0 == 0 or (f0 < 0) != (f1 < 0):
                    t = f0 / (f0 - f1) if (f0 - f1) != 0 else 0.0
                    x_p = xs[i - 1] + t * (xs[i] - xs[i - 1])
                    break
            y_p = _interp(x_p, xs, ys)
        if x_D - y_p > 1e-9 and y_p - x_p > 1e-9:
            return (x_D - y_p) / (y_p - x_p)
    except Exception:
        pass
    return None


def design(LK: str, HK: str, z_F: float, x_D: float, x_B: float,
           R: Optional[float] = None, R_factor: float = 1.3,
           q: float = 1.0, P_bar: float = 1.013,
           max_stages: int = 100) -> Optional[Dict]:
    """Diseño McCabe-Thiele binario.

    Args (todas fracción molar de LK):
        z_F, x_D, x_B: feed, destilado, fondo
        R:        reflujo absoluto.  Si None, se usa R = R_factor · R_min.
        R_factor: múltiplo de R_min (default 1.3, como el solver FUG).
        q:        1=feed líq. saturado, 0=vapor saturado, etc.

    Returns dict | None (None si la VLE no resuelve o las specs son
    degeneradas / no-escalonables — p.ej. azeótropo entre x_B y x_D):
        equilibrium, rect, strip, feed_point, stages, N_stages,
        feed_stage, R_min, x_D, x_B, z_F, R, q, P_bar, LK, HK.
    """
    if not (0.0 < x_B < z_F < x_D < 1.0):
        return None
    eq = equilibrium_curve(LK, HK, P_bar)
    if eq is None:
        return None
    xs, ys = eq
    # La curva debe estar por encima de la diagonal (LK más volátil).
    if ys[len(ys) // 2] <= xs[len(xs) // 2]:
        return None

    R_min = _r_min(xs, ys, z_F, x_D, q)
    if R is None:
        if R_min is None or R_min <= 0:
            return None
        R = R_factor * R_min
    if R <= 0:
        return None

    rect_slope = R / (R + 1.0)
    rect_int = x_D / (R + 1.0)

    def rect(x):
        return rect_slope * x + rect_int

    # Intersección rect ∩ q-line → punto de alimentación
    if abs(q - 1.0) < 1e-6:
        x_int = z_F
        y_int = rect(z_F)
    else:
        q_slope = q / (q - 1.0)
        q_int = -z_F / (q - 1.0)
        denom = (q_slope - rect_slope)
        if abs(denom) < 1e-9:
            x_int = z_F
            y_int = rect(z_F)
        else:
            x_int = (rect_int - q_int) / denom
            y_int = rect(x_int)

    if not (x_B < x_int < x_D):
        return None

    strip_slope = (y_int - x_B) / (x_int - x_B)
    strip_int = x_B - strip_slope * x_B

    def op_line(x):
        return rect(x) if x >= x_int else strip_slope * x + strip_int

    # Escalonado desde (x_D, x_D) en la diagonal.
    stages: List[Tuple[float, float]] = [(x_D, x_D)]
    x_cur, y_cur = x_D, x_D
    feed_stage = None
    N = 0
    for _ in range(max_stages):
        x_new = _x_from_y(y_cur, xs, ys)
        if x_new >= x_cur:        # no avanza → pinch (R < R_min)
            return None
        stages.append((x_new, y_cur))
        N += 1
        if feed_stage is None and x_new <= x_int:
            feed_stage = N
        if x_new <= x_B:
            break
        y_new = op_line(x_new)
        stages.append((x_new, y_new))
        x_cur, y_cur = x_new, y_new
    else:
        return None

    return dict(
        equilibrium=(xs, ys),
        rect=(rect_slope, rect_int),
        strip=(strip_slope, strip_int),
        feed_point=(x_int, y_int),
        stages=stages,
        N_stages=N,
        feed_stage=feed_stage if feed_stage is not None else N,
        R_min=R_min,
        x_D=x_D, x_B=x_B, z_F=z_F, R=R, q=q, P_bar=P_bar,
        LK=LK, HK=HK,
    )
