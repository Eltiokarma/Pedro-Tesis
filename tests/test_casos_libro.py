"""Frente 2 (auditoría frontend) — casos de libro verificables.

Cada test recomputa el valor de referencia DE FORMA INDEPENDIENTE
dentro del test (la ecuación del libro, evaluada a mano — no la del
módulo bajo prueba) y lo compara contra lo que produce el software.
Fuente y tolerancia citadas caso por caso; el detalle narrativo vive
en docs/CASOS_LIBRO.md.

Casos:
  1. Turton Tabla A.1 — costo de compra de bomba centrífuga (S=10 kW).
  2. Turton Tabla A.1 — costo de compra de compresor centrífugo
     (S=1000 kW).
  3. Fenske (Seader/Henley cap. 9) — N_min para split 95/95 con α=2.5.
  4. Underwood binario q=1 — R_min con raíz θ hallada por bisección
     independiente.
  5. Perry §10 / GPSA — bomba: potencia hidráulica, head y NPSHr por
     suction specific speed.
  6. Turton §6.5 / Cengel — compresor: T de descarga isentrópica con η.
  7. SVA (Smith-Van Ness-Abbott) — flash isotérmico binario
     benceno/tolueno: Rachford-Rice independiente + identidades de
     balance.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ══════════════════════════════════════════════════════════════════════
# 1-2. Turton Tabla A.1 — log10 Cp = K1 + K2·log10 S + K3·(log10 S)²
#      Base CEPCI 397 (año 2001). Coeficientes copiados DEL LIBRO acá,
#      no de EQUIPMENT_DATA (si el catálogo se corrompe, esto falla).
# ══════════════════════════════════════════════════════════════════════
def _cp_turton(K1, K2, K3, S):
    lg = math.log10(S)
    return 10.0 ** (K1 + K2 * lg + K3 * lg * lg)


def test_turton_a1_bomba_centrifuga_digito_a_digito():
    import equipment_costs as ec
    S = 10.0    # kW de eje, rango válido 1-300
    cp_libro = _cp_turton(3.3892, 0.0536, 0.1538, S)   # ≈ 3 950 USD
    pc = ec.purchased_cost("Pump — centrifugal", S, year_target=2001)
    cp_repo_base = pc["Cp_target"] / pc["cepci_factor"]   # → base CEPCI 397
    assert abs(cp_repo_base - cp_libro) / cp_libro < 0.005, (
        f"Cp repo {cp_repo_base:.1f} ≠ Turton {cp_libro:.1f}")
    assert 3900 < cp_libro < 4000   # sanity del propio número del libro


def test_turton_a1_compresor_centrifugo_digito_a_digito():
    import equipment_costs as ec
    S = 1000.0    # kW, rango válido 450-3000
    cp_libro = _cp_turton(2.2897, 1.3604, -0.1027, S)
    pc = ec.purchased_cost("Compressor — centrifugal", S, year_target=2001)
    cp_repo_base = pc["Cp_target"] / pc["cepci_factor"]
    assert abs(cp_repo_base - cp_libro) / cp_libro < 0.005


# ══════════════════════════════════════════════════════════════════════
# 3. Fenske — N_min = ln[(xD_LK/xD_HK)·(xB_HK/xB_LK)] / ln(α)
# ══════════════════════════════════════════════════════════════════════
def test_fenske_split_95_95_alpha_2_5():
    from distillation_fug import fenske
    alpha, xD, xB = 2.5, 0.95, 0.05
    n_libro = math.log((xD / (1 - xD)) * ((1 - xB) / xB)) / math.log(alpha)
    n_repo = fenske(alpha, x_D_LK=xD, x_B_LK=xB,
                    x_D_HK=1 - xD, x_B_HK=1 - xB)
    assert n_repo is not None
    assert abs(n_repo - n_libro) < 1e-9
    # Valor clásico (Seader/Henley): ≈ 6.42 etapas mínimas
    assert 6.3 < n_repo < 6.6


# ══════════════════════════════════════════════════════════════════════
# 4. Underwood binario, feed líquido saturado (q=1)
# ══════════════════════════════════════════════════════════════════════
def test_underwood_binario_q1_contra_biseccion_independiente():
    from distillation_fug import underwood
    alphas, z, x_D, q = [2.5, 1.0], [0.5, 0.5], [0.95, 0.05], 1.0

    # Raíz θ de Σ αᵢzᵢ/(αᵢ-θ) = 1-q = 0, con 1 < θ < 2.5 — bisección
    # propia del test (no la del módulo).
    def F(th):
        return sum(a * zi / (a - th) for a, zi in zip(alphas, z))
    lo, hi = 1.0 + 1e-6, 2.5 - 1e-6
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if F(lo) * F(mid) <= 0:
            hi = mid
        else:
            lo = mid
    theta_libro = 0.5 * (lo + hi)
    rmin_libro = sum(a * xd / (a - theta_libro)
                     for a, xd in zip(alphas, x_D)) - 1.0

    res = underwood(alphas, z, q, x_D)
    assert res is not None
    theta_repo, rmin_repo = res
    assert abs(theta_repo - theta_libro) < 1e-3
    assert abs(rmin_repo - rmin_libro) < 1e-2
    assert rmin_libro > 0


# ══════════════════════════════════════════════════════════════════════
# 5. Bomba — Perry §10 / GPSA
# ══════════════════════════════════════════════════════════════════════
def test_bomba_potencia_head_npshr_perry():
    from equipment_design import pump_sizing
    m, dp, rho = 10.0, 5.0, 1000.0          # kg/s, bar, kg/m³ (agua)
    res = pump_sizing(m, dp, rho, eta_hyd=0.75, eta_motor=0.95)
    assert res is not None
    # W_hyd = m·ΔP/ρ = 10·5e5/1000 = 5 000 W
    assert abs(res["W_hyd_kW"] - 5.0) < 1e-9
    assert abs(res["W_shaft_kW"] - 5.0 / 0.75) < 1e-9
    assert abs(res["W_elec_kW"] - 5.0 / 0.75 / 0.95) < 1e-9
    # head = ΔP/(ρg) = 5e5/(1000·9.81) = 50.968 m
    assert abs(res["head_m"] - 5e5 / (1000 * 9.81)) < 1e-6
    # NPSHr por suction specific speed (Perry 8ª §10.4):
    #   NPSHr[ft] = (N·√Q[gpm]/N_ss)^(4/3),  N=3550, N_ss=9000
    Q_gpm = res["Q_m3_h"] * 4.40287
    npshr_libro = ((3550.0 * math.sqrt(Q_gpm) / 9000.0) ** (4.0 / 3.0)
                   * 0.3048)
    assert abs(res["NPSHr_m_est"] - npshr_libro) < 1e-6


# ══════════════════════════════════════════════════════════════════════
# 6. Compresor — T descarga isentrópica con η (Turton §6.5 / Cengel)
# ══════════════════════════════════════════════════════════════════════
def test_compresor_t_descarga_aire_1_a_5_bar():
    from equipment_design import compressor_sizing
    # Aire k=1.4, T_in=300 K, 1→5 bar, η_isen=0.75 (single-stage para
    # comparar con la relación isentrópica pura: ratio_per_stage=10).
    res = compressor_sizing(m_kg_s=1.0, P_in_bar=1.0, P_out_bar=5.0,
                            T_in_K=300.0, mw_avg=28.97, k=1.4,
                            eta_isen=0.75, eta_mech=0.95,
                            max_ratio_per_stage=10.0)
    assert res is not None
    exponent = 0.4 / 1.4
    dT_isen = 300.0 * (5.0 ** exponent - 1.0)          # = 175.13 K
    T_out_libro = 300.0 + dT_isen / 0.75               # = 533.50 K
    assert abs(res["T_out_K"] - T_out_libro) < 0.1
    # W_isen = m·R/MW·T·k/(k-1)·[(P2/P1)^((k-1)/k) − 1]
    R_spec = 8.314 / (28.97e-3)
    w_isen_libro = R_spec * 300.0 * 3.5 * (5.0 ** exponent - 1.0) / 1e3
    assert abs(res["W_isen_kW"] - w_isen_libro) / w_isen_libro < 1e-6
    assert abs(res["W_act_kW"] - w_isen_libro / (0.75 * 0.95)) \
        / res["W_act_kW"] < 1e-6


# ══════════════════════════════════════════════════════════════════════
# 7. Flash isotérmico binario (SVA) — benceno/tolueno
# ══════════════════════════════════════════════════════════════════════
def test_flash_binario_benceno_tolueno_rachford_rice():
    import thermo_db as td
    from nrtl import flash_TP, _Psat_bar

    # 98°C: entre el punto de burbuja (~92°C) y el de rocío de la
    # mezcla 50/50 a 1 atm → flash bifásico real (a 92°C V=0 y el caso
    # degenera).
    T_K, P_bar = 98.0 + 273.15, 1.013
    names, z = ["benzene", "toluene"], [0.5, 0.5]
    res = flash_TP(names, z, T_K, P_bar)
    assert res is not None, "flash_TP no convergió"
    V, x, y = res["V_frac"], res["x"], res["y"]

    # Identidades de balance (solucionario SVA — deben cerrar exacto):
    assert abs(sum(x) - 1.0) < 1e-6
    assert abs(sum(y) - 1.0) < 1e-6
    for i in range(2):
        assert abs(V * y[i] + (1 - V) * x[i] - z[i]) < 1e-6

    # Referencia Raoult ideal (γ=1): K = Psat/P con el MISMO Antoine,
    # Rachford-Rice binario resuelto por bisección propia del test.
    K = [_Psat_bar(n, T_K) / P_bar for n in names]
    assert K[0] > 1.0 > K[1], f"a 92°C benceno volátil, tolueno no: {K}"

    def rr(v):
        return sum(zi * (ki - 1.0) / (1.0 + v * (ki - 1.0))
                   for zi, ki in zip(z, K))
    lo, hi = 1e-9, 1.0 - 1e-9
    assert rr(lo) > 0 > rr(hi), (
        f"el caso no es bifásico a {T_K - 273.15:.0f}°C: "
        f"rr(0)={rr(lo):.3f}, rr(1)={rr(hi):.3f}")
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if rr(lo) * rr(mid) <= 0:
            hi = mid
        else:
            lo = mid
    V_raoult = 0.5 * (lo + hi)
    # benceno/tolueno ≈ ideal: NRTL no debería desviarse más de 0.05
    assert abs(V - V_raoult) < 0.05, (
        f"V_frac NRTL {V:.3f} vs Raoult {V_raoult:.3f}")
