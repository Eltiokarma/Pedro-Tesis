"""
tests/test_batch_equipment.py — Tests Capa 2 batch_equipment.

Verifica que solve_batch_reactor reusa el RK4 de reactions_db
correctamente, conserva masa, y conecta con Capa 1 via
make_ode_hook.

NOTA caso esterificación: el brief menciona R008 (Esterificación
de Fischer) como caso de prueba, pero R008 NO tiene cinética
Arrhenius cargada en data/reactions_db.md (k0/Ea = None).  Los
tests aquí usan R010 (hidrogenación de etileno) que SÍ tiene
cinética compatible — verifica el camino completo Capa 1 ↔
Capa 2 sin tocar la DB de reacciones (responsabilidad fuera de
esta tarea).  Cuando se cargue cinética a R008, basta cambiar
'R010' por 'R008' en el caso de esterificación abajo.

USO:
    python -m unittest tests.test_batch_equipment -v
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import batch_equipment as be
import batch_schedule as bs
from batch_schedule import TaskKind, Task, BatchRecipe


# ─────────────────────────────────────────────────────────────
# solve_batch_reactor — integración correcta
# ─────────────────────────────────────────────────────────────

class TestSolveBatchReactor(unittest.TestCase):
    def test_conversion_finita_R010(self):
        """Hidrogenación de etileno (R010), reactor batch:
            1 C2H4 + 1 H2 → 1 C2H6
        Carga 10 mol C2H4 + 10 mol H2 a 300 K (límite inferior del
        rango cinético válido), 1 bar, V=10 m³, 10 s.  Cinética muy
        rápida → conversión intermedia (~40 %).
        """
        res = be.solve_batch_reactor(
            rxn_ids=['R010'],
            N_in={'C2H4': 10.0, 'H2': 10.0},
            T_K=300.0, P_bar=1.0,
            V_reactor=10.0,
            t_final_s=10.0,
            n_steps=100,
        )
        self.assertIsNotNone(res, "R010 batch no resolvió")
        # Conversión de etileno entre 0 y 1
        x_C2H4 = res["conversion"].get("C2H4", 0.0)
        self.assertGreater(x_C2H4, 0.0)
        self.assertLess(x_C2H4, 1.0)
        # Estequiometría: etano formado = C2H4 consumido
        N_C2H4_in  = 10.0
        N_C2H4_out = res["N_out"]["C2H4"]
        N_C2H6_out = res["N_out"]["C2H6"]
        self.assertAlmostEqual(N_C2H6_out, N_C2H4_in - N_C2H4_out, places=2)
        # Conservación de átomos C: in=20, out= C2H4·2 + C2H6·2 = constante
        C_atoms_in = 2 * 10.0
        C_atoms_out = 2 * N_C2H4_out + 2 * N_C2H6_out
        self.assertAlmostEqual(C_atoms_in, C_atoms_out, places=2)

    def test_profile_estructura(self):
        res = be.solve_batch_reactor(
            rxn_ids=['R010'],
            N_in={'C2H4': 5.0, 'H2': 5.0},
            T_K=300.0, P_bar=1.0,
            V_reactor=10.0,
            t_final_s=600.0,
            n_steps=50,
        )
        self.assertEqual(len(res["profile_t"]), 51)   # 0..n_steps
        self.assertEqual(len(res["profile_N"]), 51)
        self.assertEqual(res["profile_t"][0], 0.0)
        self.assertEqual(res["profile_t"][-1], 600.0)

    def test_reaccion_inexistente_None(self):
        res = be.solve_batch_reactor(
            rxn_ids=['R999_FAKE'],
            N_in={'C2H4': 1.0},
            T_K=300, P_bar=1.0, V_reactor=0.01,
            t_final_s=60, n_steps=10,
        )
        self.assertIsNone(res)

    def test_V_no_positivo_None(self):
        res = be.solve_batch_reactor(
            rxn_ids=['R010'],
            N_in={'C2H4': 1.0, 'H2': 1.0},
            T_K=300, P_bar=1, V_reactor=0.0,
            t_final_s=60, n_steps=10,
        )
        self.assertIsNone(res)


# ─────────────────────────────────────────────────────────────
# time_to_conversion
# ─────────────────────────────────────────────────────────────

class TestTimeToConversion(unittest.TestCase):
    def test_alcanza_conv_objetivo(self):
        # Conv objetivo 30 % de etileno a 300 K, V=10 m³ (cinética
        # rápida pero diluida → conversión intermedia en pocos s).
        t_req = be.time_to_conversion(
            rxn_ids=['R010'],
            N_in={'C2H4': 10.0, 'H2': 10.0},
            T_K=300.0, P_bar=1.0, V_reactor=10.0,
            target_species='C2H4',
            target_conversion=0.30,
            t_max_s=60.0, n_steps_eval=200,
        )
        self.assertIsNotNone(t_req)
        self.assertGreater(t_req, 0)
        self.assertLess(t_req, 60.0)
        # Verifica internamente: integrando hasta t_req se obtiene
        # conversión >= 0.30 ± tolerancia paso
        res = be.solve_batch_reactor(
            rxn_ids=['R010'],
            N_in={'C2H4': 10.0, 'H2': 10.0},
            T_K=300.0, P_bar=1.0, V_reactor=10.0,
            t_final_s=t_req + 1, n_steps=100,
        )
        self.assertGreaterEqual(res["conversion"]["C2H4"], 0.29)

    def test_nunca_alcanza_devuelve_None(self):
        # Cinética muy diluida → no alcanza 99.999 % en 0.1 s
        # (la cinética de R010 es rápida pero el cruce a casi 100 %
        # requiere tiempo cuando hay dilución alta).
        t_req = be.time_to_conversion(
            rxn_ids=['R010'],
            N_in={'C2H4': 10.0, 'H2': 10.0},
            T_K=300.0, P_bar=1.0, V_reactor=1000.0,
            target_species='C2H4',
            target_conversion=0.99999,
            t_max_s=0.1, n_steps_eval=20,
        )
        self.assertIsNone(t_req)


# ─────────────────────────────────────────────────────────────
# Integración con Capa 1 vía ode_hook
# ─────────────────────────────────────────────────────────────

class TestOdeHookCapa1(unittest.TestCase):
    """Conecta Capa 1 (batch_schedule) con Capa 2 (batch_equipment)
    via make_ode_hook + resolve_dynamic_durations.  Caso de prueba:
    receta con una tarea de reacción cuya duración se resuelve por
    integración cinética hasta conversión objetivo."""

    def test_resolve_dynamic_duration_pone_tiempo_real(self):
        hook = be.make_ode_hook(
            rxn_ids=['R010'],
            N_in_per_batch={'C2H4': 10.0, 'H2': 10.0},
            T_K=300.0, P_bar=1.0, V_reactor=10.0,
            target_species='C2H4',
            target_conversion=0.30,
            t_max_s=60.0,
        )
        recipe = BatchRecipe(
            name="rxn_hooked",
            tasks=[
                Task("load",   TaskKind.CARGA,         duration_s=60),
                Task("react",  TaskKind.REACCION,      ode_hook=hook),
                Task("unload", TaskKind.DESCARGA,      duration_s=60),
            ],
            product_mass_kg_per_batch=300.0,
        )
        # Antes de resolver: react no tiene duration → cycle_time
        # lanza ValueError
        with self.assertRaises(ValueError):
            bs.cycle_time_s(recipe)
        # Resolver dinámicas via Capa 2
        bs.resolve_dynamic_durations(recipe)
        # Ahora react tiene duración positiva
        react_task = next(t for t in recipe.tasks if t.name == "react")
        self.assertIsNotNone(react_task.duration_s)
        self.assertGreater(react_task.duration_s, 0)
        # cycle_time se calcula correctamente
        ct = bs.cycle_time_s(recipe)
        self.assertAlmostEqual(ct, 60 + react_task.duration_s + 60, places=2)

    def test_to_schedule_block_post_hook(self):
        # End-to-end: hook + resolve + to_schedule_block.
        # Este es el camino que Capa 3 invoca implícitamente cuando
        # el caller arma una receta con tareas dinámicas.
        hook = be.make_ode_hook(
            rxn_ids=['R010'],
            N_in_per_batch={'C2H4': 5.0, 'H2': 5.0},
            T_K=300.0, P_bar=1.0, V_reactor=10.0,
            target_species='C2H4',
            target_conversion=0.20,
            t_max_s=60.0,
        )
        recipe = BatchRecipe(
            name="e2e",
            tasks=[
                Task("load",  TaskKind.CARGA,    duration_s=120,
                     service="electricity", utility_rate=4.0),
                Task("react", TaskKind.REACCION, ode_hook=hook,
                     service="steam", utility_rate=10.0),
                Task("unload",TaskKind.DESCARGA, duration_s=120,
                     service="electricity", utility_rate=4.0),
            ],
            product_mass_kg_per_batch=150.0,
        )
        bs.resolve_dynamic_durations(recipe)
        blk = bs.to_schedule_block(recipe, availability=0.85)
        self.assertGreater(blk["cycle_time_s"], 240.0)   # > 240 + react
        self.assertGreater(blk["annual_production_kg"], 0)
        # Pico de steam = 10 (de react), de electricity = 4
        self.assertEqual(blk["utility_peaks"]["steam"], 10.0)
        self.assertEqual(blk["utility_peaks"]["electricity"], 4.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
