"""Independent physical invariants, not saved-output snapshots."""
import math
import unittest

import eos
import nrtl
import stream_enthalpy as se
import thermo_db as td
from flowsheet_model import Stream, SEC_PER_YEAR, TM_TO_KG


class PhaseEquilibriumTests(unittest.TestCase):
    def test_dense_supercritical_fugacity_does_not_depend_on_z_threshold(self):
        Tc, Pc, w = eos._eos_consts("methane")
        # T>Tc, a single physical root has Z<0.307. Previously rejected
        # as a vapor trial solely because of its compressibility factor.
        phi = eos.fugacity_coeff_pure(191., 60e5, Tc, Pc, w, "vapor")
        self.assertIsNotNone(phi)
        self.assertGreater(phi, 0.)

    def assert_material_balance(self, z, r):
        beta = r["V_frac"]
        for i, zi in enumerate(z):
            self.assertAlmostEqual(zi, (1-beta)*r["x"][i]+beta*r["y"][i], places=8)

    def test_lle_isoactivity_and_lever_rule(self):
        names, z = ["water", "benzene"], [.3, .7]
        r = nrtl.flash_LLE(names, z, 298.15)
        self.assertIsNotNone(r)
        self.assertTrue(r["two_phase"])
        self.assertLess(r["iterations"], 30)
        a, b = r["x_alpha"], r["x_beta"]
        ga, gb = nrtl.gamma(names, a, 298.15), nrtl.gamma(names, b, 298.15)
        for i in range(2):
            self.assertLess(abs(math.log(a[i]*ga[i]/(b[i]*gb[i]))), 1e-6)
            self.assertAlmostEqual(z[i], r["L_alpha"]*a[i]+(1-r["L_alpha"])*b[i], places=9)

    def test_iteration_limit_is_not_success(self):
        self.assertIsNone(nrtl.flash_LLE(["water", "benzene"], [.3, .7], 298.15, max_iter=1))
        self.assertIsNone(nrtl.flash_TP(["water", "ethanol"], [.5, .5], 355., 1., max_iter=1))
        self.assertIsNone(eos.flash_TP_eos(
            ["toluene", "hydrogen", "benzene", "methane"],
            [.0652, .3982, .2683, .2683], 311.15, 25., max_iter=1))

    def test_wilson_single_phase_guess_must_be_refined(self):
        # Wilson predicts all liquid; PR fugacity equality gives a small
        # but real vapor phase.  This used to return V=0 on iteration 1.
        names, z, T, P = ["methane", "benzene"], [.1, .9], 250., 20.
        r = eos.flash_TP_eos(names, z, T, P)
        self.assertIsNotNone(r)
        self.assertGreater(r["V_frac"], .001)
        self.assertLess(r["V_frac"], .1)
        self.assert_material_balance(z, r)
        props = [eos._eos_consts(n) for n in names]
        pl = eos.fugacity_coeff_mix(props, r["x"], T, P*1e5, "liquid")
        pv = eos.fugacity_coeff_mix(props, r["y"], T, P*1e5, "vapor")
        for i in range(2):
            self.assertLess(abs(math.log(r["x"][i]*pl[i]/(r["y"][i]*pv[i]))), 1e-7)

    def test_invalid_flash_inputs_fail_cleanly(self):
        for flash in (nrtl.flash_TP, eos.flash_TP_eos):
            for z, T, P in (([0., 0.], 300., 1.), ([-.1, 1.1], 300., 1.),
                            ([.5, .5], 0., 1.), ([.5, .5], 300., 0.),
                            ([math.nan, .5], 300., 1.)):
                self.assertIsNone(flash(["water", "ethanol"], z, T, P))
            self.assertIsNone(flash([], [], 300., 1.))


class CaloricConsistencyTests(unittest.TestCase):
    def test_property_edits_do_not_reuse_stale_calorics(self):
        c = td.get("water")
        old = c.cp_liq_coefs
        before = se.specific_enthalpy_kJ_kg({"water":1.}, 80., "liquid")
        try:
            c.cp_liq_coefs = (old[0] + 1000., *old[1:])
            after = se.specific_enthalpy_kJ_kg({"water":1.}, 80., "liquid")
            self.assertAlmostEqual(after - before, 55. / c.mw, places=7)
        finally:
            c.cp_liq_coefs = old

    def test_graphite_particle_calorics(self):
        c = td.get("carbon")
        self.assertAlmostEqual(c.cp_J_mol_K(300, "solid"), 8.6186, delta=.09)
        T, eps = 1000., .001
        hl = se.specific_enthalpy_kJ_kg({"carbon":1.}, T-eps, "solid")
        hh = se.specific_enthalpy_kJ_kg({"carbon":1.}, T+eps, "solid")
        self.assertAlmostEqual((hh-hl)/(2*eps), c.cp_kJ_kg_K(T, "solid"), places=6)
        self.assertEqual(se.specific_enthalpy_kJ_kg({"carbon":1.}, T, "solid"),
                         se.specific_enthalpy_kJ_kg({"carbon":1.}, T, "gas"))

    def test_co2_alias_and_phase_pressure_anchors(self):
        self.assertIs(td.get("carbon dioxide"), td.get("co2"))
        self.assertGreater(td.cp_kJ_kg_K("carbon_dioxide", 25, "gas"), .8)
        c = td.get("co2")
        # NIST phase anchors: triple point ~216.58 K/5.185 bar;
        # critical ~304.18 K/73.8 bar. Approximate Antoine fit: 2%.
        self.assertAlmostEqual(c.vapor_pressure_kPa(-56.6), 518.5, delta=10.4)
        self.assertAlmostEqual(c.vapor_pressure_kPa(31.), 7380., delta=147.6)

    def test_partial_duplicate_gas_entries_use_complete_properties(self):
        for long_name, short_name in (("carbon_monoxide", "co"),
                                      ("hydrogen_sulfide", "h2s"),
                                      ("sulfur_dioxide", "so2")):
            self.assertIs(td.get(long_name), td.get(short_name))
            self.assertIsNotNone(se.specific_enthalpy_kJ_kg({long_name:1.}, 340., "gas"))
        # Trace H2S must not invalidate an otherwise known petroleum stream.
        self.assertIsNotNone(se.specific_enthalpy_kJ_kg(
            {"naphtha":.99997, "hydrogen_sulfide":.00003}, 40., "liquid"))

    def test_mixture_cp_resolves_legacy_species_without_dropping_mass(self):
        from components import get
        comp = {"chlorine": .9999953277, "water": 4.6723e-6}
        s = Stream(1, "wet chlorine", 0, 1, composition=comp,
                   temperature=15., phase="gas")
        expected = (comp["chlorine"] * get("chlorine").cp(15., "gas")
                    + comp["water"] * td.cp_kJ_kg_K("water", 15., "gas"))
        self.assertAlmostEqual(se._resolve_cp(s), expected, places=12)
        eps = .001
        derivative = (se.specific_enthalpy_kJ_kg(comp, 15+eps, "gas")
                      - se.specific_enthalpy_kJ_kg(comp, 15-eps, "gas")) / (2*eps)
        self.assertAlmostEqual(se._resolve_cp(s), derivative, places=7)
        s.composition = {"unknown_caloric_species": .99, "water": .01}
        self.assertIsNone(se._resolve_cp(s))

    def test_cryogenic_liquids_share_the_permanent_gas_reference(self):
        for name in ("nitrogen", "oxygen"):
            tb = td.get(name).tb_c
            hl = se.specific_enthalpy_kJ_kg({name: 1.}, tb, "liquid")
            hg = se.specific_enthalpy_kJ_kg({name: 1.}, tb, "gas")
            self.assertAlmostEqual(hg - hl, td.delta_h_vap_kJ_kg(name, tb), places=9)
            # Boiling latent heats are ~200-213 kJ/kg; allow 10% for the
            # existing Antoine-derived latent approximation, not thousands.
            self.assertGreater(hg - hl, 180.)
            self.assertLess(hg - hl, 235.)
            self.assertGreater(hl, -500.)
            eps, temperature = .001, tb - 2.
            dh = (se.specific_enthalpy_kJ_kg({name: 1.}, temperature+eps, "liquid")
                  - se.specific_enthalpy_kJ_kg({name: 1.}, temperature-eps, "liquid")) / (2*eps)
            self.assertAlmostEqual(dh, td.cp_kJ_kg_K(name, temperature, "liquid"), places=6)

    def test_explicit_species_phases_preserve_enthalpy_and_derive_mass_quality(self):
        from flowsheet_model import Flowsheet
        comp = {"nitrogen": .7, "water": .2, "nitrogen_dioxide": .1}
        s = Stream(1, "absorber", 0, 1, mass_flow=SEC_PER_YEAR/TM_TO_KG,
                   composition=comp, temperature=50., phase="two_phase",
                   vapor_fraction=0., component_vapor_fractions={
                       "nitrogen": 1., "nitrogen_dioxide": 1., "water": 0.,
                       "nitric_acid": 0.})  # future reaction product allowed
        expected = sum(w * se.specific_enthalpy_kJ_kg(
            {name: 1.}, 50., "liquid" if name == "water" else "gas")
            for name, w in comp.items())
        self.assertAlmostEqual(se.stream_enthalpy_kW(s), expected, places=10)
        self.assertAlmostEqual(se.resolved_vapor_fraction(s), .8, places=12)
        eps = .001
        s.temperature = 50. + eps
        high = se.stream_enthalpy_kW(s)
        s.temperature = 50. - eps
        low = se.stream_enthalpy_kW(s)
        self.assertAlmostEqual(se._resolve_cp(s, 50.), (high-low)/(2*eps), places=7)
        fs = Flowsheet()
        fs.streams[s.id] = s
        restored = Flowsheet.from_dict(fs.to_dict()).streams[s.id]
        self.assertEqual(restored.component_vapor_fractions, s.component_vapor_fractions)
        self.assertAlmostEqual(se.stream_enthalpy_kW(restored), se.stream_enthalpy_kW(s))
        s.composition = {"nitrogen": .5, "water": .4, "nitrogen_dioxide": .1}
        self.assertAlmostEqual(se.resolved_vapor_fraction(s), .6)

    def test_explicit_species_phases_reject_missing_or_invalid_allocations(self):
        s = Stream(1, "mixed", 0, 1, mass_flow=100,
                   composition={"nitrogen": .8, "water": .2}, temperature=50.,
                   phase="two_phase", component_vapor_fractions={"nitrogen": 1.})
        self.assertIsNone(se.stream_enthalpy_kW(s))
        self.assertIsNone(se._resolve_cp(s))
        for bad in (-.1, 1.1, float("nan"), float("inf")):
            s.component_vapor_fractions["water"] = bad
            self.assertIsNone(se.stream_enthalpy_kW(s))
            self.assertIsNone(se.resolved_vapor_fraction(s))

    def test_nitrogen_oxide_calorics_from_nist(self):
        # Values from the published NIST Shomate equations at 298.15 K.
        self.assertAlmostEqual(td.get("nitric_oxide").cp_J_mol_K(298.15, "gas"), 29.856, delta=.002)
        self.assertAlmostEqual(td.get("nitrogen_dioxide").cp_J_mol_K(298.15, "gas"), 36.974, delta=.002)
        for name in ("nitric_oxide", "nitrogen_dioxide"):
            eps, T = .001, 1000.
            h1 = se.specific_enthalpy_kJ_kg({name:1.}, T-eps, "gas")
            h2 = se.specific_enthalpy_kJ_kg({name:1.}, T+eps, "gas")
            self.assertAlmostEqual((h2-h1)/(2*eps), td.cp_kJ_kg_K(name,T,"gas"), places=5)

    def test_fixed_phase_dh_dt_equals_cp(self):
        for name, T, phase in (("water", 130., "vapor"), ("ethanol", 100., "vapor"),
                               ("water", 80., "liquid"), ("hydrogen", 300., "gas")):
            eps = 1e-3
            hm = se.specific_enthalpy_kJ_kg({name: 1.}, T-eps, phase)
            hp = se.specific_enthalpy_kJ_kg({name: 1.}, T+eps, phase)
            self.assertAlmostEqual((hp-hm)/(2*eps), td.cp_kJ_kg_K(name, T, phase), places=5)

    def test_water_boiling_latent_is_physical(self):
        hl = se.specific_enthalpy_kJ_kg({"water": 1.}, 100., "liquid")
        hv = se.specific_enthalpy_kJ_kg({"water": 1.}, 100., "vapor")
        # IAPWS/NIST ~2257 kJ/kg at 1 atm; ideal Cp model allowed 2%.
        self.assertAlmostEqual(hv-hl, 2257., delta=45.)

    def test_quality_is_linear_in_phase_enthalpies(self):
        hl = se.specific_enthalpy_kJ_kg({"water": 1.}, 100., "liquid")
        hv = se.specific_enthalpy_kJ_kg({"water": 1.}, 100., "vapor")
        hm = se.specific_enthalpy_kJ_kg({"water": 1.}, 100., "two_phase", .3)
        self.assertAlmostEqual(hm, .7*hl+.3*hv, places=9)

    def test_inverse_energy_and_zero_flow(self):
        s = Stream(id=1, name="steam", src=0, dst=1,
                   mass_flow=SEC_PER_YEAR/TM_TO_KG, composition={"water": 1.},
                   phase="vapor", temperature=130.)
        h = se.stream_enthalpy_kW(s)
        s.temperature = 90.
        self.assertAlmostEqual(se.temperature_for_enthalpy(s, h), 130., places=6)
        self.assertEqual(s.temperature, 90.)
        s.mass_flow = 0.
        self.assertEqual(se.stream_enthalpy_kW(s), 0.)


if __name__ == "__main__":
    unittest.main()
