"""
GATE EOS — validación honesta de la fundación Peng-Robinson (eos.py, PR-1).

Prueba la CORRECCIÓN de la maquinaria PR (no que PR iguale a Antoine: PR sin
volume-translation es pobre para polares/asociativos — eso se REPORTA, no se
esconde ni se tunea).

Uso
---
    python gate_eos.py     # imprime anclas (PASS/FAIL) + tabla de desviaciones
    echo $?                # 0 = todas las anclas pasan y mediana < 25 %

Estructura
----------
2.1  Anclas de corrección (tol estricta; FALLAN el gate si no pasan).
2.2  Barrido cruzado vs Antoine (breadth; REPORTA, no falla, salvo la
     aserción suave de mediana < 25 %).
"""

from __future__ import annotations

import sys
from statistics import median

import eos
import thermo_db as td
import nrtl


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


# ============================================================
# 2.1 — Anclas de corrección
# ============================================================

def run_anchors() -> bool:
    print("=" * 78)
    print("2.1  ANCLAS DE CORRECCIÓN PR (deben pasar)")
    print("=" * 78)
    ok = True

    # (a) Benceno hierve a 80 °C / 1 atm → Psat ≈ 1.013 bar ± 5 %.
    p = eos.psat_bar("benzene", 80.0)
    a_ok = p is not None and abs(p - 1.013) / 1.013 <= 0.05
    ok &= a_ok
    print(f"  [{'PASS' if a_ok else 'FAIL'}] benzene Psat(80°C) = "
          f"{p:.5f} bar  (esperado 1.013 ± 5%)" if p is not None
          else "  [FAIL] benzene Psat(80°C) = None")

    # (b) Monotonía estricta de psat_pr(benzene) en [300 K, Tc−1].
    consts = eos._eos_consts("benzene")
    Tc_K, Pc_Pa, omega = consts
    Ts = [300.0 + i for i in range(0, int(Tc_K - 1 - 300) + 1, 10)]
    Ts.append(Tc_K - 1.0)
    ps = [eos.psat_pr(Tc_K, Pc_Pa, omega, T) for T in Ts]
    mono = all(p is not None for p in ps) and all(
        ps[i + 1] > ps[i] for i in range(len(ps) - 1))
    ok &= mono
    print(f"  [{'PASS' if mono else 'FAIL'}] benzene psat_pr estrictamente "
          f"creciente en [300 K, Tc−1]  ({len(Ts)} puntos)")

    # (c) Supercrítico: CO2 a 40 °C (T > Tc = 31 °C) → None.
    p_co2 = eos.psat_bar("carbon dioxide", 40.0)
    sc_ok = p_co2 is None
    ok &= sc_ok
    print(f"  [{'PASS' if sc_ok else 'FAIL'}] CO2 Psat(40°C) = {p_co2} "
          f"(esperado None: supercrítico, Tc=31°C)")

    # (d) Límite gas ideal: φ → 1 cuando P → 0 (chequear a P = 1 Pa).
    phi = eos.fugacity_coeff_pure(353.15, 1.0, Tc_K, Pc_Pa, omega, "vapor")
    id_ok = phi is not None and abs(phi - 1.0) <= 1e-3
    ok &= id_ok
    print(f"  [{'PASS' if id_ok else 'FAIL'}] φ_vapor(P=1 Pa) = "
          f"{phi:.8f}  (esperado 1.0 ± 1e-3)" if phi is not None
          else "  [FAIL] φ_vapor(P=1 Pa) = None")

    return ok


# ============================================================
# 2.2 — Barrido cruzado vs Antoine
# ============================================================

def run_cross_sweep() -> bool:
    print()
    print("=" * 78)
    print("2.2  BARRIDO CRUZADO PR vs ANTOINE (breadth — reporta, no falla)")
    print("=" * 78)

    rows = []   # (name, T_C, p_pr, p_ant, dev_rel)
    skipped = 0
    for name in td.list_names():
        c = td.get(name)
        if c is None or c.antoine_A is None:
            continue
        lo, hi = c.antoine_range_C
        if not (hi > lo):           # rango Antoine inválido / (0,0)
            continue
        if eos._eos_consts(name) is None:
            continue                # sin data EOS (tc_c/pc_bar/omega)

        T_C = 0.5 * (lo + hi)       # punto medio del rango Antoine
        p_pr = eos.psat_bar(name, T_C)
        p_ant = nrtl._Psat_bar(name, T_C + 273.15)
        if p_pr is None or p_ant is None or p_ant <= 1e-9:
            skipped += 1            # supercrítico en el midpoint, o no-volátil
            continue
        dev = abs(p_pr - p_ant) / p_ant
        rows.append((name, T_C, p_pr, p_ant, dev))

    n = len(rows)
    if n == 0:
        print("  (sin pares comparables — esto es anómalo)")
        return False

    devs = sorted(r[4] for r in rows)
    med = median(devs)
    p90 = devs[min(n - 1, int(round(0.90 * (n - 1))))]
    mx = devs[-1]

    print(f"  Compuestos comparados (Antoine + EOS): {n}   "
          f"(saltados: {skipped})")
    print(f"  Desviación relativa PR vs Antoine en el midpoint del rango:")
    print(f"    mediana = {_pct(med)}    P90 = {_pct(p90)}    máx = {_pct(mx)}")

    print()
    print("  10 PEORES OUTLIERS (limitación conocida de PR: polares/"
          "asociativos):")
    worst = sorted(rows, key=lambda r: r[4], reverse=True)[:10]
    print(f"    {'compuesto':<26}{'T[°C]':>8}{'PR[bar]':>12}"
          f"{'Antoine[bar]':>14}{'dev':>9}")
    for (name, T_C, p_pr, p_ant, dev) in worst:
        print(f"    {name:<26}{T_C:>8.1f}{p_pr:>12.4g}"
              f"{p_ant:>14.4g}{_pct(dev):>9}")

    soft_ok = med < 0.25
    print()
    print(f"  Aserción suave: mediana ({_pct(med)}) < 25%  → "
          f"{'PASS' if soft_ok else 'FAIL (investigar la implementación)'}")
    return soft_ok


def main() -> int:
    anchors_ok = run_anchors()
    sweep_ok = run_cross_sweep()

    print()
    print("=" * 78)
    if anchors_ok and sweep_ok:
        print("✓ GATE EOS VERDE: anclas PASS y mediana de desviación < 25%.")
        print("=" * 78)
        return 0
    print("✗ GATE EOS ROJO: revisar anclas y/o desviación mediana.")
    print("=" * 78)
    return 1


if __name__ == "__main__":
    sys.exit(main())
