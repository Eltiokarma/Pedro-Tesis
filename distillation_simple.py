"""distillation_simple.py — operaciones simples de destilación (widget P-SAD,
pestañas 1-3): flash binario, batch/Rayleigh y arrastre con vapor.

Todas usan la VLE NRTL del repo (vía mccabe_thiele.equilibrium_curve y
nrtl.flash_TP) y se computan desde el modelo cuando hay un equipo que las
soporta (el flash mapea a un Vessel con flash_active).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

from mccabe_thiele import equilibrium_curve, _interp


def flash_binary(LK: str, HK: str, z_F: float, T_K: float,
                 P_bar: float = 1.013) -> Optional[Dict]:
    """Flash isotérmico binario: dado z_F (frac molar de LK), T y P, devuelve
    V_frac y las composiciones de las fases (vía NRTL), más la curva de
    equilibrio y la recta de operación del flash (pendiente −L/V por (z_F,z_F)).
    None si la VLE no resuelve o z_F fuera de (0,1)."""
    if not (0.0 < z_F < 1.0):
        return None
    try:
        import nrtl
    except ImportError:
        return None
    fl = nrtl.flash_TP([LK, HK], [z_F, 1.0 - z_F], T_K, P_bar)
    if fl is None or fl.get("V_frac") is None:
        return None
    V = max(0.0, min(1.0, fl["V_frac"]))
    eq = equilibrium_curve(LK, HK, P_bar)
    if eq is None:
        return None
    return dict(V_frac=V, x_LK=fl["x"][0], y_LK=fl["y"][0], z_F=z_F,
                equilibrium=eq, T_K=T_K, P_bar=P_bar, LK=LK, HK=HK)


def flash_from_block(block, fs) -> Optional[Dict]:
    """Flash binario de un Vessel con flash_active, proyectado a los 2
    componentes volátiles (con Antoine) dominantes del feed.  z_F, T y P salen
    del modelo (flash_T_K/flash_P_bar).  None si no es flash o el feed no es
    aproximadamente binario (los 2 dominantes < 85% molar)."""
    if not getattr(block, "flash_active", False):
        return None
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
    mols = {}
    for c, mf in comp.items():
        o = _td.get(c)
        if o and o.mw > 0 and o.antoine_A is not None and mf > 0:
            mols[c] = mf * 1000.0 / o.mw
    tot = sum(mols.values())
    if tot <= 0:
        return None
    mf_mol = {c: v / tot for c, v in mols.items()}
    top2 = sorted(mf_mol.items(), key=lambda kv: -kv[1])[:2]
    if len(top2) < 2 or (top2[0][1] + top2[1][1]) < 0.85:
        return None
    a, b = top2[0][0], top2[1][0]
    ta, tb = _td.get(a).tb_c, _td.get(b).tb_c
    LK, HK = (a, b) if ta <= tb else (b, a)        # LK = más volátil (Tb menor)
    z_F = mf_mol[LK] / (mf_mol[LK] + mf_mol[HK])
    T_K = float(getattr(block, "flash_T_K", 298.15) or 298.15)
    P = float(getattr(block, "flash_P_bar", 1.013) or 1.013)
    f = flash_binary(LK, HK, z_F, T_K, P)
    # Solo mostrar un flash GENUINO bifásico (la proyección binaria de un
    # knockout de gases multicomponente daría V/F≈0/1, no ilustrativo).
    if f is None or not (0.02 < f["V_frac"] < 0.98):
        return None
    return f


def rayleigh_batch(LK: str, HK: str, x0: float, xf: float,
                   P_bar: float = 1.013, n: int = 400) -> Optional[Dict]:
    """Destilación batch (Rayleigh):  ln(W0/W) = ∫_{xf}^{x0} dx/(y_eq(x) − x).

    x0 = composición inicial del calderín, xf = composición final (xf < x0
    para LK que se enriquece en el destilado).  Devuelve la fracción residual
    W/W0, la fracción destilada y la composición media del destilado por
    balance de masa.  None si el integrando diverge (azeótropo en el camino)."""
    if not (0.0 < xf < x0 < 1.0):
        return None
    eq = equilibrium_curve(LK, HK, P_bar)
    if eq is None:
        return None
    xs, ys = eq
    # ∫_{xf}^{x0} dx/(y_eq − x) por trapezoidal
    integral = 0.0
    dx = (x0 - xf) / n
    prev = None
    for i in range(n + 1):
        x = xf + i * dx
        yv = _interp(x, xs, ys)
        denom = yv - x
        if denom <= 1e-4:                 # azeótropo / pinch en el camino
            return None
        f = 1.0 / denom
        if prev is not None:
            integral += 0.5 * (prev + f) * dx
        prev = f
    W_over_W0 = math.exp(-integral)       # W = W0·exp(−∫)
    frac_dist = 1.0 - W_over_W0
    if frac_dist <= 1e-9:
        return None
    # Composición media del destilado (balance global LK): x_D = (x0 − (W/W0)·xf)/(1−W/W0)
    x_D_avg = (x0 - W_over_W0 * xf) / frac_dist
    return dict(W_over_W0=W_over_W0, frac_distilled=frac_dist,
                x_D_avg=min(1.0, x_D_avg), x0=x0, xf=xf, P_bar=P_bar,
                LK=LK, HK=HK)


def steam_distillation(organic: str, P_total_bar: float = 1.013,
                       water: str = "water") -> Optional[Dict]:
    """Arrastre con vapor de un orgánico inmiscible en agua.

    La mezcla hierve cuando Psat_water(T) + Psat_org(T) = P_total.  A esa T:
        y_org = Psat_org / P_total
        moles de vapor de agua por mol de orgánico = Psat_water / Psat_org
    Devuelve T de ebullición, y_org y la relación de vapor.  None si falta
    Antoine del orgánico."""
    try:
        import thermo_db as _td
    except ImportError:
        return None
    o_org = _td.get(organic)
    o_w = _td.get(water)
    if o_org is None or o_w is None:
        return None
    if o_org.antoine_A is None or o_w.antoine_A is None:
        return None

    def Ptot(T_C):
        pw = o_w.vapor_pressure_kPa(T_C)
        po = o_org.vapor_pressure_kPa(T_C)
        if pw is None or po is None:
            return None
        return (pw + po) / 100.0, pw / 100.0, po / 100.0   # bar

    # Bisección en T para Ptot = P_total
    lo, hi = -50.0, 400.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        r = Ptot(mid)
        if r is None:
            return None
        if r[0] < P_total_bar:
            lo = mid
        else:
            hi = mid
    T_C = 0.5 * (lo + hi)
    r = Ptot(T_C)
    if r is None:
        return None
    _, pw, po = r
    if po <= 0:
        return None
    y_org = po / P_total_bar
    steam_ratio = pw / po                  # mol vapor agua / mol orgánico
    # masa de vapor por masa de orgánico
    mass_ratio = (steam_ratio * o_w.mw / o_org.mw) if o_org.mw > 0 else None
    return dict(T_boil_C=T_C, y_org=y_org, steam_ratio_mol=steam_ratio,
                steam_ratio_mass=mass_ratio, P_total_bar=P_total_bar,
                organic=organic)
