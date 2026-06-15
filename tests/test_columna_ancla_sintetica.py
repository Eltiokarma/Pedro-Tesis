"""
tests/test_columna_ancla_sintetica.py — ANCLA SINTÉTICA del motor de columnas.

Fase de DISEÑO del proyecto "columnas activas" (ver
docs/columnas_activas_design.md).  Esta NO es una columna de producción: es
un caso binario benceno/tolueno con volatilidad relativa CONSTANTE (α=2.5),
elegido porque toda la mecánica FUG (Fenske-Underwood-Gilliland) y el balance
de componentes cierran EXACTO a mano.  Sirve de ancla de regresión para el
motor de columnas independiente del thermo_db (NRTL/Antoine): si un cambio
futuro toca distillation_fug.py, este test lo clava contra el cálculo manual.

NO toca ningún golden de los 41 ejemplos.  NO activa ninguna columna pasiva.

────────────────────────────────────────────────────────────────────────────
CÁLCULO MANUAL (caso cerrado, benceno=LK / tolueno=HK, α=2.5 constante)
────────────────────────────────────────────────────────────────────────────
Datos de diseño:
    F      = 100        (base; mismo basis a la salida)
    z_LK   = 0.50       (feed 50/50 mol)
    x_D_LK = 0.95       (destilado: 95 % benceno)
    x_B_LK = 0.05       (fondo:      5 % benceno)
    q      = 1.0        (feed líquido saturado)
    α      = 2.5        (constante tope-fondo)

1) BALANCE GLOBAL (regla de la palanca) — exacto:
       D = F·(z_LK − x_B_LK)/(x_D_LK − x_B_LK)
         = 100·(0.50 − 0.05)/(0.95 − 0.05)
         = 100·0.45/0.90 = 50.0
       B = F − D = 50.0
   Comprobación del balance de LK:
       entra: F·z_LK            = 100·0.50 = 50.0
       sale : D·x_D_LK + B·x_B_LK = 50·0.95 + 50·0.05 = 47.5 + 2.5 = 50.0  ✓

2) FENSKE (N mínimo, reflujo total) — exacto:
       x_D_HK = 1 − 0.95 = 0.05 ;  x_B_HK = 1 − 0.05 = 0.95
       N_min = ln[(x_D_LK/x_D_HK)·(x_B_HK/x_B_LK)] / ln(α)
             = ln[(0.95/0.05)·(0.95/0.05)] / ln(2.5)
             = ln(19·19) / ln(2.5) = ln(361)/ln(2.5)
             = 5.888878.../0.916291... = 6.426866...

3) UNDERWOOD (R mínimo), q=1, binario α_LK=2.5, α_HK=1.0 — exacto:
       raíz θ de:  Σ αᵢ·zᵢ/(αᵢ−θ) = 1−q = 0
       2.5·0.5/(2.5−θ) + 1.0·0.5/(1.0−θ) = 0
       1.25·(1−θ) + 0.5·(2.5−θ) = 0  →  2.5 − 1.75·θ = 0  →  θ = 10/7 = 1.428571...
       R_min + 1 = Σ αᵢ·x_D_i/(αᵢ−θ)
                 = 2.5·0.95/(2.5−10/7) + 1.0·0.05/(1.0−10/7)
                 = 2.375/1.071428... + 0.05/(−0.428571...)
                 = 2.216666... − 0.116666... = 2.100000...
       R_min = 1.100000...   (exacto)

4) GILLILAND (N real) con R = 1.3·R_min = 1.43 — vía el fit Eduljee del código:
       X = (R − R_min)/(R + 1) = (1.43 − 1.10)/(1.43 + 1) = 0.33/2.43 = 0.135802...
       Y = 0.75·(1 − X^0.5668) = 0.507915...
       N = (N_min + Y)/(1 − Y) = (6.426866 + 0.507915)/(1 − 0.507915) ≈ 14.0991
   (Gilliland es una correlación, no un cerrado físico: se ancla contra la
    propia fórmula del código, no contra un número "de mano" arbitrario.)

USO:  python -m pytest tests/test_columna_ancla_sintetica.py -v
"""
import os
import sys
import math
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import distillation_fug as fug


# Parámetros del caso (un único lugar de verdad para el cálculo manual).
ALPHA = 2.5
Z_LK = 0.50
X_D_LK = 0.95
X_B_LK = 0.05
F = 100.0
Q = 1.0
R_FACTOR = 1.3


class TestBalanceGlobal(unittest.TestCase):
    """Regla de la palanca: D=B=50, balance de LK cierra exacto."""

    def test_lever_rule_D_B(self):
        D = F * (Z_LK - X_B_LK) / (X_D_LK - X_B_LK)
        B = F - D
        self.assertAlmostEqual(D, 50.0, places=10)
        self.assertAlmostEqual(B, 50.0, places=10)

    def test_balance_LK_cierra(self):
        D = F * (Z_LK - X_B_LK) / (X_D_LK - X_B_LK)
        B = F - D
        entra = F * Z_LK
        sale = D * X_D_LK + B * X_B_LK
        self.assertAlmostEqual(entra, 50.0, places=10)
        self.assertAlmostEqual(sale, entra, places=9)


class TestFenske(unittest.TestCase):
    """N_min = ln(361)/ln(2.5) exacto."""

    def test_Nmin_vs_mano(self):
        n = fug.fenske(ALPHA, X_D_LK, X_B_LK, 1.0 - X_D_LK, 1.0 - X_B_LK)
        self.assertIsNotNone(n)
        self.assertAlmostEqual(n, math.log(361.0) / math.log(2.5), places=9)

    def test_alpha_uno_no_separa(self):
        # α≤1 → no factible (la función devuelve None).
        self.assertIsNone(fug.fenske(1.0, X_D_LK, X_B_LK,
                                     1.0 - X_D_LK, 1.0 - X_B_LK))


class TestUnderwood(unittest.TestCase):
    """θ = 10/7, R_min = 1.1 exactos (binario, q=1)."""

    def test_theta_y_Rmin(self):
        res = fug.underwood([ALPHA, 1.0], [Z_LK, 1.0 - Z_LK], Q,
                            [X_D_LK, 1.0 - X_D_LK])
        self.assertIsNotNone(res)
        theta, r_min = res
        self.assertAlmostEqual(theta, 10.0 / 7.0, places=6)
        self.assertAlmostEqual(r_min, 1.10, places=6)


class TestGilliland(unittest.TestCase):
    """N real contra el fit Eduljee del propio código."""

    def test_N_vs_formula_codigo(self):
        r_min = 1.10
        R = R_FACTOR * r_min
        n_min = math.log(361.0) / math.log(2.5)
        n = fug.gilliland(n_min, R, r_min)
        self.assertIsNotNone(n)
        # Recompute Eduljee fit Y = 0.75·(1 − X^0.5668)
        X = (R - r_min) / (R + 1.0)
        Y = 0.75 * (1.0 - X ** 0.5668)
        n_expected = (n_min + Y) / (1.0 - Y)
        self.assertAlmostEqual(n, n_expected, places=9)
        # Sanidad física: N entre N_min y ~3·N_min.
        self.assertGreater(n, n_min)
        self.assertLess(n, 3.0 * n_min)

    def test_R_igual_Rmin_imposible(self):
        n_min = math.log(361.0) / math.log(2.5)
        self.assertIsNone(fug.gilliland(n_min, 1.10, 1.10))


class TestDesignColumnIntegrado(unittest.TestCase):
    """El balance global de design_column() reproduce la palanca exacta.

    design_column calcula α vía thermo_db (NRTL/Antoine), así que N/R dependen
    del thermo y NO se anclan a mano aquí; lo que SÍ es independiente del thermo
    y cierra exacto es el balance D/B (regla de la palanca), que el método
    resuelve algebraicamente igual que arriba.
    """

    def test_balance_DB_independiente_de_alpha(self):
        res = fug.design_column(
            feed_composition={"benzene": Z_LK, "toluene": 1.0 - Z_LK},
            F=F, T_K=380.0, P_bar=1.013,
            light_key="benzene", heavy_key="toluene",
            x_D_LK=X_D_LK, x_B_LK=X_B_LK, R_factor=1.5, q=Q)
        self.assertIsNotNone(res)
        # Si el thermo da α>1 (benceno/tolueno lo da), hay diseño completo.
        if res.get("D") is not None:
            self.assertAlmostEqual(res["D"], 50.0, places=6)
            self.assertAlmostEqual(res["B"], 50.0, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
