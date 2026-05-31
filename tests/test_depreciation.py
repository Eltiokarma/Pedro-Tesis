"""
GATE 1a — depreciation.py (tablas MACRS rescatadas).

  · Cada clase MACRS suma 1.0 (±1e-9): toda la base depreciable se recupera.
  · Factor-por-factor IDÉNTICO a flujoflujoclass.calcular_depreciacion
    (la fuente legacy de la que se rescató).
  · Valores IRS conocidos (Pub. 946 GDS half-year).
  · straight_line: base/years repetido years veces, suma = base.
"""
import unittest

import depreciation as dep


# Valores IRS Pub. 946 (GDS, half-year convention) — referencia externa.
IRS_MACRS = {
    5:  [0.20, 0.32, 0.192, 0.1152, 0.1152, 0.0576],
    7:  [0.1429, 0.2449, 0.1749, 0.1249, 0.0893, 0.0892, 0.0893, 0.0446],
    15: [0.05, 0.095, 0.0855, 0.077, 0.0693, 0.0623, 0.059, 0.059, 0.0591,
         0.059, 0.0591, 0.059, 0.0591, 0.059, 0.0591, 0.0295],
}


class TestMacrsTables(unittest.TestCase):

    def test_suman_uno(self):
        for clase, factores in dep.MACRS_TABLES.items():
            self.assertAlmostEqual(sum(factores), 1.0, delta=1e-9,
                                   msg=f"MACRS{clase} no suma 1.0")

    def test_factores_irs(self):
        for clase, esperado in IRS_MACRS.items():
            self.assertEqual(len(dep.MACRS_TABLES[clase]), len(esperado))
            for got, exp in zip(dep.MACRS_TABLES[clase], esperado):
                self.assertAlmostEqual(got, exp, places=12)

    def test_factor_por_factor_vs_flujoflujoclass(self):
        # La fuente legacy: tipo_macrs 0/1/2 → clase 5/7/15.
        legacy = {
            0: [0.20, 0.32, 0.192, 0.1152, 0.1152, 0.0576],
            1: [0.1429, 0.2449, 0.1749, 0.1249, 0.0893, 0.0892, 0.0893, 0.0446],
            2: [0.05, 0.095, 0.0855, 0.077, 0.0693, 0.0623, 0.059, 0.059,
                0.0591, 0.059, 0.0591, 0.059, 0.0591, 0.059, 0.0591, 0.0295],
        }
        for tipo, clase in [(0, 5), (1, 7), (2, 15)]:
            self.assertEqual(dep.MACRS_TABLES[clase], legacy[tipo])

    def test_schedule_macrs_suma_base(self):
        base = 12_345_678.0
        for clase in (5, 7, 15):
            sched = dep.depreciation_schedule(base, method="macrs",
                                              macrs_class=clase)
            self.assertAlmostEqual(sum(sched), base, delta=base * 1e-9)

    def test_schedule_lineal(self):
        base, years = 10_000_000.0, 8
        sched = dep.depreciation_schedule(base, method="straight_line",
                                          years=years)
        self.assertEqual(len(sched), years)
        self.assertTrue(all(abs(d - base / years) < 1e-9 for d in sched))
        self.assertAlmostEqual(sum(sched), base, delta=1e-6)

    def test_macrs_class_invalida(self):
        with self.assertRaises(ValueError):
            dep.depreciation_schedule(1.0, method="macrs", macrs_class=10)

    def test_method_invalido(self):
        with self.assertRaises(ValueError):
            dep.depreciation_schedule(1.0, method="doble_declinante")


if __name__ == "__main__":
    unittest.main()
