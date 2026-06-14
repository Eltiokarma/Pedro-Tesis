"""
GATE EOS-FLASH — valida el flash φ-φ Peng-Robinson (eos.flash_TP_eos) y el
selector de método de solve_flashes (PR-2).

No depende de igualar literatura exacta: chequea conservación de masa,
asignación de fase correcta, manejo de single-phase, idempotencia y la
lógica de selección NRTL vs EOS.

Uso
---
    python gate_eos_flash.py     # PASS/FAIL por chequeo
    echo $?                      # 0 = todos pasan
"""

from __future__ import annotations

import sys

import eos
from flowsheet_solver import _flash_method

# Feed real del V-101 del hda (molar), consumidor de validación.
V101_NAMES = ["toluene", "hydrogen", "benzene", "methane"]
V101_Z = [0.0652, 0.3982, 0.2683, 0.2683]


def _check(label, cond):
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
    return bool(cond)


def main() -> int:
    ok = True
    print("=" * 78)
    print("GATE EOS-FLASH — flash φ-φ Peng-Robinson + selector de método")
    print("=" * 78)

    # ── 1. Balance por componente (V-101 a 38°C, 25 bar) ──
    print("1) Balance por componente  z_i ≈ (1−V)·x_i + V·y_i  (38°C, 25 bar)")
    r = eos.flash_TP_eos(V101_NAMES, V101_Z, 38 + 273.15, 25.0)
    if r is None:
        ok &= _check("flash convergió", False)
    else:
        V = r["V_frac"]
        bal = all(
            abs(V101_Z[i] - ((1 - V) * r["x"][i] + V * r["y"][i])) < 1e-6
            for i in range(len(V101_NAMES)))
        ok &= _check(f"conservación (V/F={V:.4f}, iters={r['iterations']})", bal)

        # ── 2. Asignación de fase correcta ──
        print("2) Asignación de fase (gases → vapor, aromáticos → líquido)")
        K = {V101_NAMES[i]: r["K"][i] for i in range(len(V101_NAMES))}
        ok &= _check(f"K(hydrogen)={K['hydrogen']:.3g} > 1", K["hydrogen"] > 1)
        ok &= _check(f"K(methane)={K['methane']:.3g} > 1", K["methane"] > 1)
        ok &= _check(f"K(benzene)={K['benzene']:.3g} < 1", K["benzene"] < 1)
        ok &= _check(f"K(toluene)={K['toluene']:.3g} < 1", K["toluene"] < 1)
        ok &= _check(f"0 < V/F={V:.4f} < 1", 0.0 < V < 1.0)

    # ── 3. Single-phase (no crashea, V∈[0,1]) ──
    print("3) Single-phase: 10°C/25bar (frío) y 300°C/25bar (caliente)")
    r_cold = eos.flash_TP_eos(V101_NAMES, V101_Z, 10 + 273.15, 25.0)
    r_hot = eos.flash_TP_eos(V101_NAMES, V101_Z, 300 + 273.15, 25.0)
    ok &= _check("10°C: no None y V∈[0,1]",
                 r_cold is not None and 0.0 <= r_cold["V_frac"] <= 1.0)
    ok &= _check("300°C: no None y V∈[0,1]",
                 r_hot is not None and 0.0 <= r_hot["V_frac"] <= 1.0)
    if r_cold and r_hot:
        ok &= _check(
            f"V_frac(10°C)={r_cold['V_frac']:.3f} ≤ V_frac(300°C)="
            f"{r_hot['V_frac']:.3f}", r_cold["V_frac"] <= r_hot["V_frac"])

    # ── 4. Idempotencia (bit a bit) ──
    print("4) Idempotencia: dos corridas idénticas → mismo resultado")
    r_a = eos.flash_TP_eos(V101_NAMES, V101_Z, 38 + 273.15, 25.0)
    r_b = eos.flash_TP_eos(V101_NAMES, V101_Z, 38 + 273.15, 25.0)
    ok &= _check("resultado bit a bit idéntico", r_a == r_b)

    # ── 5. Selección de método ──
    print("5) Selector _flash_method")
    m_eth = _flash_method(["ethanol", "water", "co2", "glucose"], 305.1)
    m_v101 = _flash_method(["toluene", "hydrogen", "benzene", "methane"], 311.15)
    ok &= _check(f"ethanol/water/co2/glucose → '{m_eth}' (esperado 'nrtl')",
                 m_eth == "nrtl")
    ok &= _check(f"toluene/hydrogen/benzene/methane → '{m_v101}' "
                 f"(esperado 'eos')", m_v101 == "eos")

    print("=" * 78)
    if ok:
        print("✓ GATE EOS-FLASH VERDE: todos los chequeos pasan.")
        print("=" * 78)
        return 0
    print("✗ GATE EOS-FLASH ROJO.")
    print("=" * 78)
    return 1


if __name__ == "__main__":
    sys.exit(main())
