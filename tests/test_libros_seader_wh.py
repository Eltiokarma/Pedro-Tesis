"""Auditoría con libros — Frente S.1: validación del Wang-Henke (MESH).

Checkpoints ANCLADOS A LITERATURA EXTERNA (método CASOS_LIBRO: la
referencia se recomputa/copia del libro dentro del test, no de los
catálogos del repo):

1. Azeótropo etanol-agua a 1 atm — constante física publicada
   (CRC/Horsley: x_EtOH ≈ 0.894 molar, T ≈ 78.17 °C).  Valida el
   núcleo K = γ(NRTL)·P_sat/P que WH usa en cada etapa.
2. Teorema de reflujo total (Seader/Henley §9, Fenske): a R >> R_min,
   las etapas de equilibrio efectivas de la columna rigurosa deben
   coincidir con N_min de Fenske evaluado con α media geométrica
   (Seader ec. 9-85) — la identidad se recomputa acá a mano.
3. Cierre MESH multicomponente (benceno/tolueno/xileno): converged
   implica D+B = F·z por componente, perfil T monótono y duties con
   signo físico.  (El clásico ternario de Seader §10; los perfiles
   tabulados del ejemplar físico quedan pendientes como checkpoint
   adicional — ver PLAN_AUDITORIA_LIBROS.)
4. BUG 17: un componente sin Antoine debe RECHAZARSE explícitamente
   (antes: converged=True con el balance por componente roto).
"""
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest

import nrtl
import thermo_db as td
import distillation_wanghenke as wh


def test_azeotropo_etanol_agua_vs_crc():
    """Barrido de burbuja: el cruce y=x reproduce el azeótropo
    publicado (CRC 97ª / Horsley: 89.4 % mol EtOH, 78.17 °C)."""
    prev = None
    x_az = T_az = None
    for i in range(41):
        x1 = 0.80 + i * 0.005
        r = nrtl.bubble_point(["ethanol", "water"], [x1, 1 - x1], 1.013)
        assert r is not None, f"bubble_point falló en x={x1}"
        T_K, y = r
        d = y[0] - x1
        if prev is not None and prev[1] * d <= 0:
            x_az = prev[0] + (0 - prev[1]) * (x1 - prev[0]) / (d - prev[1])
            T_az = nrtl.bubble_point(["ethanol", "water"],
                                     [x_az, 1 - x_az], 1.013)[0] - 273.15
            break
        prev = (x1, d)
    assert x_az is not None, "no se encontró el azeótropo en el barrido"
    assert x_az == pytest.approx(0.894, abs=0.025), \
        f"x_azeótropo={x_az:.4f} vs CRC 0.894"
    assert T_az == pytest.approx(78.17, abs=1.5), \
        f"T_azeótropo={T_az:.2f} °C vs CRC 78.17"


def test_reflujo_total_reproduce_fenske():
    """A R=15 (≈11×R_min) con 7 etapas de equilibrio, el N_min
    equivalente de Fenske (α media geométrica, Seader ec. 9-85)
    recomputado de las composiciones del riguroso debe quedar a ≤1.5
    etapas del N disponible."""
    N = 8                    # total: condensador total + 7 de equilibrio
    r = wh.wang_henke(["benzene", "toluene"], [0.5, 0.5], F=10.0,
                      T_feed_K=365.0, P_bar=1.013, N=N, feed_stage=4,
                      D_over_F=0.5, R=15.0, max_iter=200)
    assert r["converged"], f"WH no convergió ({r['iterations']} iter)"
    xD, xB = r["x_profile"][0], r["x_profile"][-1]
    T_top, T_bot = r["T_profile"][0], r["T_profile"][-1]

    def alpha(T_K):          # identidad del libro con el Antoine del repo
        return (td.vapor_pressure_kPa("benzene", T_K - 273.15)
                / td.vapor_pressure_kPa("toluene", T_K - 273.15))
    a_gm = math.sqrt(alpha(T_top) * alpha(T_bot))
    N_min_eq = (math.log((xD[0] / xD[1]) * (xB[1] / xB[0]))
                / math.log(a_gm))
    N_eq = N - 1             # el condensador total no es etapa de equilibrio
    assert abs(N_eq - N_min_eq) <= 1.5, \
        f"N_min_eq={N_min_eq:.2f} vs N_eq={N_eq} (α_gm={a_gm:.3f})"
    # sanity del split a reflujo alto
    assert xD[0] > 0.94 and xB[0] < 0.06


def test_mesh_ternario_cierra_por_componente():
    """Ternario clásico benceno/tolueno/xileno: converged ⇒ cierre por
    componente ≤0.5 %, T monótona creciente tope→fondo, Q_reb>0>Q_cond."""
    comps = ["benzene", "toluene", "xylene"]
    z = [0.3, 0.4, 0.3]
    F = 10.0
    r = wh.wang_henke(comps, z, F=F, T_feed_K=380.0, P_bar=1.013,
                      N=14, feed_stage=7, D_over_F=0.3, R=4.0,
                      max_iter=400)
    assert r["converged"], f"no convergió ({r['iterations']} iter)"
    for i, c in enumerate(comps):
        tot = r["D_comp"][i] + r["B_comp"][i]
        assert tot == pytest.approx(F * z[i], rel=5e-3), \
            f"{c}: D+B={tot:.4f} vs F·z={F * z[i]:.4f}"
    Ts = r["T_profile"]
    assert all(Ts[i + 1] >= Ts[i] - 0.2 for i in range(len(Ts) - 1)), \
        "perfil T no monótono tope→fondo"
    assert r["Q_reb_kW"] > 0 > r["Q_cond_kW"]
    # el liviano se va casi entero por tope, el pesado por fondo
    assert r["D_comp"][0] / (F * z[0]) > 0.9      # recuperación benceno
    assert r["B_comp"][2] / (F * z[2]) > 0.98     # xileno al fondo


def test_bug17_componente_sin_antoine_se_rechaza():
    """BUG 17: p_xylene no tiene Antoine (el genérico 'xylene' sí) —
    antes WH lo trataba como no-volátil por sentinela y reportaba
    converged=True con el balance por componente roto al 100 %."""
    r = wh.wang_henke(["benzene", "toluene", "p_xylene"], [0.3, 0.4, 0.3],
                      F=10.0, T_feed_K=380.0, P_bar=1.013, N=14,
                      feed_stage=7, D_over_F=0.3, R=4.0, max_iter=50)
    assert r["converged"] is False
    assert any("sin Antoine" in w for w in r["warnings"]), r["warnings"]
    assert any("p_xylene" in w for w in r["warnings"])
