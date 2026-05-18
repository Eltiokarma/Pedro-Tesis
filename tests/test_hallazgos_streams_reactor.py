"""
tests/test_hallazgos_streams_reactor.py — Suite integrada de los
4 hallazgos de la auditoría técnica de streams + reactor.

Cubre:
  · Hallazgo 1: reactions_from_dict + custom reactions end-to-end
  · Hallazgo 3: REACTOR_PORTS con alimentacion_2, autoselect
  · Hallazgo 4-A: pipe_pressure_drop_compressible (gas)
  · Hallazgo 4-B: densidad de gas con P del stream
  · Hallazgo 4-C: toggle is_pipe

USO:
    python -m unittest tests.test_hallazgos_streams_reactor -v
"""
import math
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import equipment_ports as ep
import flowsheet_model as fm
import flowsheet_solver as fsv
import pressure_drop as pd
import reactions_db as rdb


# ─────────────────────────────────────────────────────────────
# Hallazgo 1 — Reacciones custom
# ─────────────────────────────────────────────────────────────

class TestReactionFromDict(unittest.TestCase):
    def test_ok_con_ds(self):
        # H2 + 1/2 O2 → H2O (balanceado: 2 H2 + O2 → 2 H2O)
        rxn = rdb.reaction_from_dict({
            "id": "T1", "name": "H2 burn",
            "stoich": [
                {"formula": "H2",  "phase": "g", "nu": -2},
                {"formula": "O2",  "phase": "g", "nu": -1},
                {"formula": "H2O", "phase": "g", "nu":  2},
            ],
            "dh_rxn_298_kJ_mol":  -242.0,
            "ds_rxn_298_J_mol_K": -89.0,
        })
        self.assertEqual(rxn.id, "T1")
        self.assertIsNotNone(rxn.vant_hoff_A)
        self.assertIsNotNone(rxn.vant_hoff_B)
        # B = -ΔH/R con R=8.314462618 J/(mol·K) (CODATA 2018)
        self.assertAlmostEqual(rxn.vant_hoff_B, 242000.0 / 8.314462618,
                                  places=0)

    def test_ok_con_keq298(self):
        rxn = rdb.reaction_from_dict({
            "id": "T2", "name": "WGS",
            "stoich": [
                {"formula": "CO",  "phase": "g", "nu": -1},
                {"formula": "H2O", "phase": "g", "nu": -1},
                {"formula": "CO2", "phase": "g", "nu":  1},
                {"formula": "H2",  "phase": "g", "nu":  1},
            ],
            "dh_rxn_298_kJ_mol": -41.0,
            "keq_298":           100.0,
        })
        # Keq(298) reconstruido debe dar 100
        keq298 = math.exp(rxn.vant_hoff_A + rxn.vant_hoff_B / 298.15)
        self.assertAlmostEqual(keq298, 100.0, delta=1.0)

    def test_error_balance(self):
        # H2 + O2 → H2O (sin coefs balanceados; falta 1 H del RHS)
        with self.assertRaises(ValueError) as cm:
            rdb.reaction_from_dict({
                "id": "BAD",
                "stoich": [
                    {"formula": "H2",  "phase": "g", "nu": -1},
                    {"formula": "O2",  "phase": "g", "nu": -1},
                    {"formula": "H2O", "phase": "g", "nu":  1},
                ],
                "dh_rxn_298_kJ_mol": 0.0, "keq_298": 1.0,
            })
        self.assertIn("desbalanceada", str(cm.exception))

    def test_error_ambos_ds_y_keq(self):
        with self.assertRaises(ValueError) as cm:
            rdb.reaction_from_dict({
                "id": "BAD",
                "stoich": [
                    {"formula": "N2", "phase": "g", "nu": -1},
                    {"formula": "N2", "phase": "g", "nu":  1},
                ],
                "dh_rxn_298_kJ_mol":   0.0,
                "ds_rxn_298_J_mol_K":  0.0,
                "keq_298":             1.0,
            })
        self.assertIn("ds_rxn_298_J_mol_K O keq_298", str(cm.exception))

    def test_error_sin_reactante(self):
        with self.assertRaises(ValueError) as cm:
            rdb.reaction_from_dict({
                "id": "BAD",
                "stoich": [{"formula": "A", "phase": "g", "nu": 1}],
                "dh_rxn_298_kJ_mol": 0.0, "ds_rxn_298_J_mol_K": 0.0,
            })
        self.assertIn("reactante", str(cm.exception))


class TestCustomReactionSolverEndToEnd(unittest.TestCase):
    """Block con custom_reactions resolviendo equilibrio."""

    def test_wgs_custom_resuelve_equilibrio(self):
        fs = fm.Flowsheet()
        b = fm.Block(id=1, name="R-T", eq_type="Reactor — jacketed non-agit.",
                      S=10.0, T_op_K=800.0, P_op_bar=1.0)
        b.custom_reactions = [{
            "id": "WGS-T", "name": "WGS",
            "stoich": [
                {"formula": "CO",  "phase": "g", "nu": -1},
                {"formula": "H2O", "phase": "g", "nu": -1},
                {"formula": "CO2", "phase": "g", "nu":  1},
                {"formula": "H2",  "phase": "g", "nu":  1},
            ],
            "dh_rxn_298_kJ_mol": -41.0, "keq_298": 100.0,
        }]
        fs.blocks[1] = b
        s_in = fm.Stream(id=2, name="S-in", src=0, dst=1, mass_flow=1000,
                          composition={"co": 0.6098, "water": 0.3902},
                          main_component="co", phase="gas", temperature=527)
        s_in.mass_flow_locked = True; s_in.composition_locked = True
        fs.streams[2] = s_in
        s_out = fm.Stream(id=3, name="S-out", src=1, dst=0)
        fs.streams[3] = s_out

        res = fsv.solve(fs)
        self.assertEqual(len(res.mass_balance_errors), 0)
        # La reacción avanza (composición cambia respecto al feed)
        self.assertIn("co2", s_out.composition)
        self.assertIn("hydrogen", s_out.composition)
        # b.reactions NO contaminado
        self.assertEqual(b.reactions, [])

    def test_pfr_con_custom_degrada_a_equilibrium(self):
        # Mode pfr + custom_reactions (sin Arrhenius) → degrada a
        # equilibrium con warning explícito (no crashea).
        fs = fm.Flowsheet()
        b = fm.Block(id=1, name="R", eq_type="Reactor — jacketed non-agit.",
                      S=10.0, T_op_K=800.0, P_op_bar=1.0)
        b.reactor_mode = "pfr"
        b.reactor_volume_L = 100.0
        b.custom_reactions = [{
            "id": "CR", "name": "custom",
            "stoich": [
                {"formula": "CO",  "phase": "g", "nu": -1},
                {"formula": "H2O", "phase": "g", "nu": -1},
                {"formula": "CO2", "phase": "g", "nu":  1},
                {"formula": "H2",  "phase": "g", "nu":  1},
            ],
            "dh_rxn_298_kJ_mol": -41.0, "keq_298": 10.0,
        }]
        fs.blocks[1] = b
        s_in = fm.Stream(id=2, name="S", src=0, dst=1, mass_flow=1000,
                          composition={"co": 0.5, "water": 0.5},
                          main_component="co", phase="gas", temperature=527)
        s_in.mass_flow_locked = True; s_in.composition_locked = True
        fs.streams[2] = s_in
        fs.streams[3] = fm.Stream(id=3, name="O", src=1, dst=0)

        res = fsv.solve(fs)
        # No crash, mensaje de degradación presente
        all_msgs = res.energy_warnings + res.energy_balance_errors
        self.assertTrue(any("Degradando a 'equilibrium'" in m
                              for m in all_msgs),
                          f"no warning de degradación en: {all_msgs[:5]}")


# ─────────────────────────────────────────────────────────────
# Hallazgo 3 — REACTOR_PORTS con alimentacion_2
# ─────────────────────────────────────────────────────────────

class TestReactorPorts(unittest.TestCase):
    def test_segundo_puerto_existe(self):
        self.assertIn("alimentacion_2", ep.REACTOR_PORTS)
        side, _ = ep.REACTOR_PORTS["alimentacion_2"]
        self.assertEqual(side, "left")

    def test_autoselect_distribuye_dos_feeds(self):
        # alimentacion ocupado → autoselect debe ir a alimentacion_2
        port = ep.autoselect_inlet("Reactor — autoclave",
                                     used_ports=["alimentacion"])
        self.assertEqual(port, "alimentacion_2")

    def test_autoselect_ambos_usados_fallback(self):
        # Ambos puertos left ocupados → cae a top (util_in)
        port = ep.autoselect_inlet("Reactor — autoclave",
                                     used_ports=["alimentacion", "alimentacion_2"])
        self.assertEqual(port, "util_in")


# ─────────────────────────────────────────────────────────────
# Hallazgo 4-B — Densidad gas con P del stream
# ─────────────────────────────────────────────────────────────

class TestDensityGasPressure(unittest.TestCase):
    def test_gas_density_scales_with_P(self):
        rho_1 = pd._density_kg_m3({"nitrogen": 1.0}, 298.15, "gas",
                                    P_Pa=1e5)
        rho_25 = pd._density_kg_m3({"nitrogen": 1.0}, 298.15, "gas",
                                     P_Pa=25e5)
        self.assertAlmostEqual(rho_25 / rho_1, 25.0, delta=0.1)

    def test_gas_density_default_es_1atm(self):
        rho_def = pd._density_kg_m3({"nitrogen": 1.0}, 298.15, "gas")
        rho_1bar = pd._density_kg_m3({"nitrogen": 1.0}, 298.15, "gas",
                                       P_Pa=101325.0)
        self.assertAlmostEqual(rho_def, rho_1bar, places=3)


# ─────────────────────────────────────────────────────────────
# Hallazgo 4-C — Toggle is_pipe
# ─────────────────────────────────────────────────────────────

class TestIsPipeGate(unittest.TestCase):
    def test_is_pipe_false_devuelve_None(self):
        s = fm.Stream(id=1, name="S", src=0, dst=1, mass_flow=1000,
                       temperature=25, phase="liquid",
                       composition={"water": 1.0}, main_component="water",
                       pipe_length_m=10.0, pipe_diameter_m=0.05)
        # is_pipe=False por default
        self.assertFalse(s.is_pipe)
        self.assertIsNone(pd.stream_pressure_drop(s))

    def test_is_pipe_true_calcula(self):
        s = fm.Stream(id=1, name="S", src=0, dst=1, mass_flow=1000,
                       temperature=25, phase="liquid",
                       composition={"water": 1.0}, main_component="water",
                       pipe_length_m=10.0, pipe_diameter_m=0.05)
        s.is_pipe = True
        res = pd.stream_pressure_drop(s)
        self.assertIsNotNone(res)
        self.assertGreaterEqual(res["delta_P_Pa"], 0.0)

    def test_is_pipe_legacy_default_False(self):
        old = {
            "blocks": {}, "streams": {"1": {"id": 1, "name": "S",
                                              "src": 0, "dst": 1}},
            "_next_id": 2, "opex_extras": [], "fixed_overrides": {},
        }
        fs = fm.Flowsheet.from_dict(old)
        s = fs.streams[1]
        self.assertFalse(s.is_pipe)


# ─────────────────────────────────────────────────────────────
# Hallazgo 4-A — Gas compresible
# ─────────────────────────────────────────────────────────────

class TestCompressibleGas(unittest.TestCase):
    def test_compresible_da_mas_dp_que_incompresible(self):
        # ΔP relevante (>10% P_in) → compresible debe dar MÁS ΔP
        # (densidad cae y velocidad sube)
        c = pd.pipe_pressure_drop_compressible(
            mass_flow_kg_s=1.0, P_in_Pa=20e5, T_K=298,
            MW_kg_mol=0.028, mu_Pa_s=1.8e-5,
            diameter_m=0.05, length_m=200,
        )
        rho_in = 20e5 * 0.028 / (8.314 * 298)
        i = pd.pipe_pressure_drop(
            mass_flow_kg_s=1.0, rho_kg_m3=rho_in, mu_Pa_s=1.8e-5,
            diameter_m=0.05, length_m=200,
        )
        self.assertGreater(c["delta_P_bar"], i["delta_P_bar"])
        self.assertEqual(c["model"], "compressible_isothermal")

    def test_compresible_dp_chico_degrada(self):
        # ΔP < 10 % P_in → degrada a 'incompressible_ok'
        r = pd.pipe_pressure_drop_compressible(
            mass_flow_kg_s=0.1, P_in_Pa=20e5, T_K=298,
            MW_kg_mol=0.028, mu_Pa_s=1.8e-5,
            diameter_m=0.05, length_m=10,
        )
        self.assertEqual(r["model"], "incompressible_ok")

    def test_compresible_choked_no_crashea(self):
        # Caso de bloqueo sónico (P2² <= 0): devuelve dict con flag
        # 'near_sonic_or_choked', no None ni excepción.
        r = pd.pipe_pressure_drop_compressible(
            mass_flow_kg_s=50.0, P_in_Pa=10e5, T_K=298,
            MW_kg_mol=0.028, mu_Pa_s=1.8e-5,
            diameter_m=0.05, length_m=10000,
        )
        self.assertIsNotNone(r)
        self.assertIn(r.get("warning", ""), ("near_sonic", "near_sonic_or_choked"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
