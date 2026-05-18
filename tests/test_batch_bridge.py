"""
tests/test_batch_bridge.py — Tests Capa 3 (puente batch ↔ económico).

OBJETIVO crítico: el puente debe ser ESTRICTAMENTE aditivo.  Un
proyecto NO-batch debe producir un schedule byte-idéntico al
pre-batch (las 8 claves fijas, mismos valores), garantizando
retrocompatibilidad de CashFlowModel + results_ui + reporte Excel.

USO:
    python -m unittest tests.test_batch_bridge -v
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import batch_schedule as bs
import flujoflujoclass as ffc
from batch_schedule import TaskKind, Task, BatchRecipe


# Claves canónicas del schedule existentes (Opción B no las toca)
LEGACY_KEYS = {"FC", "VCOP", "FCOP", "WL",
               "steady_start", "cutoff", "t_start", "años_display"}


def _make_rg():
    """ReportGenerator mínimo solo para invocar construir_schedule.
    El método no consume self (no toca atributos del objeto)."""
    rg = ffc.ReportGenerator.__new__(ffc.ReportGenerator)
    return rg


# ─────────────────────────────────────────────────────────────
# Regresión byte-idéntica: proyecto NO-batch
# ─────────────────────────────────────────────────────────────

class TestNoBatchByteIdentical(unittest.TestCase):
    """Si un proyecto no manda batch_recipe, el dict de retorno
    debe ser EXACTAMENTE el mismo que antes del puente."""

    def test_instantaneo_sin_batch(self):
        rg = _make_rg()
        # Planta instantánea: FC=[0] activa el branch instantaneo
        sched_in = {"FC": [0], "VCOP": [0.5, 1.0]}
        out = rg.construir_schedule(sched_in, vida_operacion=5)

        # Las 8 claves legacy presentes
        self.assertEqual(set(out.keys()) & LEGACY_KEYS, LEGACY_KEYS)
        # NO debe haber clave 'batch' agregada
        self.assertNotIn("batch", out)

        # Forma + valores específicos esperados
        self.assertEqual(out["t_start"], 1)
        self.assertEqual(out["años_display"], [0, 1, 2, 3, 4, 5])
        self.assertEqual(out["FC"], [1, 0, 0, 0, 0, 0])
        self.assertEqual(out["FCOP"], [0, 1, 1, 1, 1, 1])
        self.assertEqual(out["WL"],   [0, 1, 0, 0, 0, 0])
        # VCOP: [0, 0.5, 1.0, 1.0, 1.0, 1.0] (repite el último)
        self.assertEqual(out["VCOP"], [0, 0.5, 1.0, 1.0, 1.0, 1.0])

    def test_construccion_multianno_sin_batch(self):
        rg = _make_rg()
        # 2 años de construcción + ramp-up
        sched_in = {"FC": [0.6, 0.4], "VCOP": [0.8, 1.0]}
        out = rg.construir_schedule(sched_in, vida_operacion=4)
        self.assertNotIn("batch", out)
        self.assertEqual(out["t_start"], 2)
        # 2 construcción + 4 operación = 6 años display [1..6]
        self.assertEqual(out["años_display"], [1, 2, 3, 4, 5, 6])
        self.assertEqual(out["FC"], [0.6, 0.4, 0, 0, 0, 0])
        self.assertEqual(out["FCOP"], [0, 0, 1, 1, 1, 1])
        self.assertEqual(out["WL"],   [0, 0, 1, 0, 0, 0])


# ─────────────────────────────────────────────────────────────
# Modo batch end-to-end: schedule trae batch_recipe
# ─────────────────────────────────────────────────────────────

class TestBatchBridge(unittest.TestCase):
    def _ester_recipe(self):
        """Receta sintética estilo esterificación (Capa 2 reemplazará
        la duración de 'react' por integración cinética real)."""
        return BatchRecipe(
            name="ester_v0",
            tasks=[
                Task("load",   TaskKind.CARGA,         duration_s=300,
                     service="electricity", utility_rate=8.0),
                Task("heat",   TaskKind.CALENTAMIENTO, duration_s=1800,
                     service="steam",       utility_rate=12.0),
                Task("react",  TaskKind.REACCION,      duration_s=10800),
                Task("cool",   TaskKind.ENFRIAMIENTO,  duration_s=1200,
                     service="CW",          utility_rate=18.0),
                Task("unload", TaskKind.DESCARGA,      duration_s=300,
                     service="electricity", utility_rate=8.0),
                Task("CIP",    TaskKind.LIMPIEZA,      duration_s=900,
                     service="steam",       utility_rate=3.0),
            ],
            product_mass_kg_per_batch=800.0,
        )

    def test_schedule_con_batch_recipe(self):
        rg = _make_rg()
        recipe = self._ester_recipe()
        sched_in = {"FC": [0], "VCOP": [1.0],
                    "batch_recipe": recipe,
                    "batch_availability": 0.85}
        out = rg.construir_schedule(sched_in, vida_operacion=10)

        # Legacy keys intactas
        for k in LEGACY_KEYS:
            self.assertIn(k, out)

        # Clave 'batch' agregada con metadata
        self.assertIn("batch", out)
        batch = out["batch"]
        # cycle_time = 300+1800+10800+1200+300+900 = 15300 s = 4.25 h
        self.assertAlmostEqual(batch["cycle_time_s"], 15300.0)
        self.assertAlmostEqual(batch["cycle_time_h"], 4.25)
        # batches/yr = 8760·0.85 / 4.25
        expected_bpy = (8760 * 0.85) / 4.25
        self.assertAlmostEqual(batch["batches_per_year"],
                                  expected_bpy, places=2)
        self.assertAlmostEqual(batch["annual_production_kg"],
                                  expected_bpy * 800.0, places=0)
        # Utility peaks (MAX por servicio, no SUM)
        peaks = batch["utility_peaks"]
        self.assertEqual(peaks["electricity"], 8.0)
        self.assertEqual(peaks["steam"], 12.0)   # MAX(12, 3) = 12
        self.assertEqual(peaks["CW"], 18.0)

    def test_receta_invalida_no_rompe_economico(self):
        """Si la receta tiene una tarea sin duración (ode_hook no
        resuelto), Capa 3 debe NO romper el cash flow estacionario:
        agrega batch={'error': ...} sin alterar FC/VCOP/FCOP/WL."""
        rg = _make_rg()
        bad_recipe = BatchRecipe(
            name="bad",
            tasks=[Task("react_unresolved", TaskKind.REACCION)],
            product_mass_kg_per_batch=500.0,
        )
        sched_in = {"FC": [0], "VCOP": [1.0],
                    "batch_recipe": bad_recipe}
        out = rg.construir_schedule(sched_in, vida_operacion=5)
        # Legacy keys intactas
        for k in LEGACY_KEYS:
            self.assertIn(k, out)
        # batch presente pero con error declarado
        self.assertIn("batch", out)
        self.assertIn("error", out["batch"])


# ─────────────────────────────────────────────────────────────
# Compatibilidad con CashFlowModel
# ─────────────────────────────────────────────────────────────

class TestCashFlowCompatibility(unittest.TestCase):
    """El schedule resultante debe ser consumible por
    CashFlowModel.calcular() sin excepciones, tanto con receta
    batch como sin ella.  No verificamos números (eso es harness
    del cash flow), solo que la integración no rompe."""

    def test_calcular_sin_batch(self):
        rg = _make_rg()
        sched = rg.construir_schedule(
            {"FC": [0], "VCOP": [0.7, 1.0]},
            vida_operacion=5
        )
        # WL.index(1) es el punto crítico: si schedule cambió de
        # forma, esto lanza ValueError.
        self.assertEqual(sched["WL"].index(1), sched["t_start"])
        self.assertEqual(len(sched["FC"]), len(sched["VCOP"]))
        self.assertEqual(len(sched["FC"]), len(sched["WL"]))
        self.assertEqual(len(sched["FC"]), len(sched["FCOP"]))

    def test_calcular_con_batch_preserva_largos(self):
        rg = _make_rg()
        recipe = BatchRecipe(
            name="r",
            tasks=[Task("react", TaskKind.REACCION, duration_s=3600)],
            product_mass_kg_per_batch=100.0,
        )
        sched = rg.construir_schedule(
            {"FC": [0], "VCOP": [0.7, 1.0], "batch_recipe": recipe},
            vida_operacion=5
        )
        self.assertEqual(sched["WL"].index(1), sched["t_start"])
        self.assertEqual(len(sched["FC"]), len(sched["VCOP"]))
        self.assertEqual(len(sched["FC"]), len(sched["WL"]))
        self.assertEqual(len(sched["FC"]), len(sched["FCOP"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
