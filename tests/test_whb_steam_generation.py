"""
tests/test_whb_steam_generation.py — waste-heat boiler / generación de vapor.

Cubre el fix del bug estructural donde un HX que cede calor a alta T (WHB)
se modelaba como cooler con cooling-water (o refrigeration por el bug de
T_avg=25), produciendo ΔT_lm absurdos y costo en vez de revenue.
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import heat_exchanger_rigorous as hxr
import equipment_ports as ep
import flowsheet_model as fm
import flowsheet_solver as fsv
import flowsheet_export as fx


class TestWHBAutoselect(unittest.TestCase):
    def test_whb_autoselects_bfw_steam(self):
        # kettle reboiler que extrae calor a 800°C → genera HP steam,
        # NO cooling_water ni refrigeration.
        key = ep.autoselect_heat_source("Heat exch. — kettle reboiler",
                                        duty_kw=-500.0, T_avg=800.0)
        self.assertEqual(key, "bfw_to_steam_HP")
        self.assertEqual(ep.UTILITIES[key]["type"], "generation")

    def test_non_kettle_high_T_stays_cooling_water(self):
        # Un fixed-tube a 400°C NO es WHB estructural → cooling_water
        # (la advertencia la da size_heat_exchanger en diagnostics).
        key = ep.autoselect_heat_source("Heat exch. — fixed tube",
                                        duty_kw=-500.0, T_avg=400.0)
        self.assertEqual(key, "cooling_water")

    def test_whb_tier_by_temperature(self):
        kb = "Heat exch. — kettle reboiler"
        self.assertEqual(ep.autoselect_heat_source(kb, -1, 250), "bfw_to_steam_HP")
        self.assertEqual(ep.autoselect_heat_source(kb, -1, 180), "bfw_to_steam_MP")
        self.assertEqual(ep.autoselect_heat_source(kb, -1, 130), "bfw_to_steam_LP")


class TestWHBLmtd(unittest.TestCase):
    def test_whb_lmtd_uses_tsat(self):
        # Proceso 900→400 contra Tsat=250 (vaporización isotérmica del BFW).
        # ΔT1=900-250=650, ΔT2=400-250=150 → LMTD≈341 K.  Lo importante:
        # MUCHO menor que el absurdo 573 K que daba contra CW a 35°C.
        T_sat = ep.UTILITIES["bfw_to_steam_HP"]["T_sat"]
        self.assertEqual(T_sat, 250)
        lmtd, w = hxr.compute_lmtd_real(900, 400, T_sat, T_sat, flow="counter")
        self.assertIsNone(w)
        self.assertTrue(100 < lmtd < 400,
                        f"LMTD={lmtd:.1f} fuera del rango físico esperado")
        # contraste con el cálculo viejo contra cooling water (35→50)
        lmtd_cw, _ = hxr.compute_lmtd_real(900, 400, 35, 50, flow="counter")
        self.assertLess(lmtd, lmtd_cw)        # Tsat da ΔT_lm menor → más área


class TestWHBRevenue(unittest.TestCase):
    def _whb_flowsheet(self):
        fs = fm.Flowsheet()
        b = fm.Block(id=fs.new_id(), name="E-WHB",
                     eq_type="Heat exch. — kettle reboiler", S=20.0)
        b.duty = -500.0          # extrae calor (proceso se enfría)
        b.duty_locked = True
        fs.blocks[b.id] = b
        src, dst = fs.new_id(), fs.new_id()
        for name, s_, d_, T in (("hot-in", src, b.id, 900.0),
                                 ("hot-out", b.id, dst, 400.0)):
            sid = fs.new_id()
            st = fm.Stream(id=sid, name=name, src=s_, dst=d_,
                           mass_flow=10000.0, temperature=T,
                           phase="gas", role="internal")
            st.mass_flow_locked = True
            st.temperature_locked = True      # que sobreviva al solve
            fs.streams[sid] = st
        return fs, b

    def test_whb_revenue_negative_cost(self):
        fs, b = self._whb_flowsheet()
        fsv.solve(fs)
        rows, summary = fx.compute_utilities_from_duties(fs)
        # el bloque debe haber elegido bfw_to_steam_HP
        whb = [s for s in summary if s[1] == "bfw_to_steam_HP"]
        self.assertEqual(len(whb), 1, f"summary={summary}")
        self.assertLess(whb[0][4], 0.0, "el costo del WHB debe ser negativo (revenue)")
        # y en los rows de opex debe aparecer etiquetado como exportación
        gen_rows = [r for r in rows if "export" in r["name"].lower()
                    or "revenue" in r["name"].lower()]
        self.assertTrue(gen_rows, f"rows={[r['name'] for r in rows]}")
        opex = gen_rows[0]["flowrate"] * gen_rows[0]["price_usd_per_unit"]
        self.assertLess(opex, 0.0, "el opex del vapor exportado debe ser revenue (<0)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
