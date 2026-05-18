"""
tests/test_batch_schedule.py — Tests aislados de Capa 1 batch_schedule.

OBJETIVO crítico: este módulo debe ser testeable SIN importar el
resto del sistema (solver, modelo económico, UI).  Si algún test
necesita más módulos, batch_schedule.py se acopla demasiado.

USO:
    python -m unittest tests.test_batch_schedule -v
"""
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

# IMPORT AISLADO — sólo batch_schedule.  Si esto importa algo más,
# Capa 1 perdió su autonomía y hay que revisar.
import batch_schedule as bs
from batch_schedule import TaskKind, Task, BatchRecipe


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _simple_recipe():
    """Receta sintética para tests: 60s carga + 1800s reacción +
    600s enfriamiento + 60s descarga = 2520s = 0.70 h."""
    return BatchRecipe(
        name="test_simple",
        tasks=[
            Task("load",    TaskKind.CARGA,           duration_s=60),
            Task("react",   TaskKind.REACCION,        duration_s=1800),
            Task("cool",    TaskKind.ENFRIAMIENTO,    duration_s=600),
            Task("unload",  TaskKind.DESCARGA,        duration_s=60),
        ],
        product_mass_kg_per_batch=500.0,
    )


# ─────────────────────────────────────────────────────────────
# cycle_time_s
# ─────────────────────────────────────────────────────────────

class TestCycleTime(unittest.TestCase):
    def test_suma_duraciones_fijas(self):
        r = _simple_recipe()
        self.assertEqual(bs.cycle_time_s(r), 2520.0)

    def test_receta_vacia_lanza_error(self):
        r = BatchRecipe(name="empty", tasks=[],
                         product_mass_kg_per_batch=100)
        with self.assertRaises(ValueError):
            bs.cycle_time_s(r)

    def test_tarea_sin_duracion_error_explicito(self):
        # Tarea sin duration_s ni ode_hook → ValueError con nombre
        # de la tarea problemática en el mensaje.
        r = BatchRecipe(
            name="bad",
            tasks=[
                Task("load", TaskKind.CARGA, duration_s=60),
                Task("react_unresolved", TaskKind.REACCION),  # SIN duración
            ],
            product_mass_kg_per_batch=100,
        )
        with self.assertRaises(ValueError) as cm:
            bs.cycle_time_s(r)
        self.assertIn("react_unresolved", str(cm.exception))


# ─────────────────────────────────────────────────────────────
# batches_per_year y annual_production
# ─────────────────────────────────────────────────────────────

class TestBatchesYAnnualProduction(unittest.TestCase):
    def test_disponibilidad_full(self):
        # Receta de 1h, disponibilidad 1.0 → 8760 batches/año
        r = BatchRecipe(
            name="1h_recipe",
            tasks=[Task("react", TaskKind.REACCION, duration_s=3600)],
            product_mass_kg_per_batch=100.0,
        )
        bpy = bs.batches_per_year(r, availability=1.0)
        self.assertAlmostEqual(bpy, 8760.0, places=2)
        self.assertAlmostEqual(bs.annual_production(r, 1.0), 876000.0, places=0)

    def test_disponibilidad_parcial(self):
        # Receta 2520s = 0.70 h, av 0.90:
        # horas_ops/año = 8760·0.90 = 7884 h/año
        # batches/año   = 7884 / 0.70 = 11_262.857...
        r = _simple_recipe()
        bpy = bs.batches_per_year(r, availability=0.90)
        self.assertAlmostEqual(bpy, 7884.0 / (2520/3600), places=2)
        # Producción anual = bpy × 500 kg
        ann = bs.annual_production(r, availability=0.90)
        self.assertAlmostEqual(ann, bpy * 500.0, places=0)

    def test_disponibilidad_fuera_rango_error(self):
        r = _simple_recipe()
        with self.assertRaises(ValueError):
            bs.batches_per_year(r, availability=1.5)
        with self.assertRaises(ValueError):
            bs.batches_per_year(r, availability=-0.1)


# ─────────────────────────────────────────────────────────────
# utility_peaks
# ─────────────────────────────────────────────────────────────

class TestUtilityPeaks(unittest.TestCase):
    def test_dos_tareas_mismo_servicio_max(self):
        # Calentamiento usa 20 kg/s vapor; carga usa 5 kg/s vapor.
        # Pico de vapor = 20 (MÁXIMO, no suma — secuenciales).
        r = BatchRecipe(
            name="multi_steam",
            tasks=[
                Task("load",   TaskKind.CARGA,
                     duration_s=60,   service="steam", utility_rate=5.0),
                Task("heat",   TaskKind.CALENTAMIENTO,
                     duration_s=1200, service="steam", utility_rate=20.0),
                Task("react",  TaskKind.REACCION,
                     duration_s=3600, service="electricity", utility_rate=15.0),
                Task("cool",   TaskKind.ENFRIAMIENTO,
                     duration_s=600,  service="CW", utility_rate=30.0),
            ],
            product_mass_kg_per_batch=500.0,
        )
        peaks = bs.utility_peaks(r)
        self.assertEqual(peaks["steam"], 20.0)
        self.assertEqual(peaks["electricity"], 15.0)
        self.assertEqual(peaks["CW"], 30.0)

    def test_receta_sin_servicios(self):
        r = _simple_recipe()       # ningún Task tiene service
        self.assertEqual(bs.utility_peaks(r), {})


# ─────────────────────────────────────────────────────────────
# to_schedule_block (insumo para Capa 3)
# ─────────────────────────────────────────────────────────────

class TestToScheduleBlock(unittest.TestCase):
    def test_estructura_y_valores(self):
        r = _simple_recipe()
        blk = bs.to_schedule_block(r, availability=0.90)
        # Claves obligatorias
        for k in ("cycle_time_s", "cycle_time_h", "batches_per_year",
                   "annual_production_kg", "utility_peaks",
                   "availability", "recipe_name", "n_tasks"):
            self.assertIn(k, blk)
        # Valores numéricos
        self.assertAlmostEqual(blk["cycle_time_s"], 2520.0)
        self.assertAlmostEqual(blk["cycle_time_h"], 0.70)
        self.assertEqual(blk["n_tasks"], 4)
        self.assertEqual(blk["recipe_name"], "test_simple")
        self.assertEqual(blk["availability"], 0.90)


# ─────────────────────────────────────────────────────────────
# resolve_dynamic_durations (extensión para Capa 2)
# ─────────────────────────────────────────────────────────────

class TestResolveDynamicDurations(unittest.TestCase):
    def test_hook_pone_duracion(self):
        # Tarea sin duration_s pero con ode_hook que devuelve 7200s
        def fake_hook(task):
            return 7200.0
        r = BatchRecipe(
            name="hookable",
            tasks=[
                Task("load",  TaskKind.CARGA,    duration_s=60),
                Task("react", TaskKind.REACCION, ode_hook=fake_hook),
                Task("unload",TaskKind.DESCARGA, duration_s=60),
            ],
            product_mass_kg_per_batch=200.0,
        )
        # Antes: cycle_time_s lanza error porque react no tiene duración
        with self.assertRaises(ValueError):
            bs.cycle_time_s(r)
        # Resolver dinámicas:
        bs.resolve_dynamic_durations(r)
        # Ahora suma 60 + 7200 + 60 = 7320s
        self.assertEqual(bs.cycle_time_s(r), 7320.0)

    def test_resolve_no_afecta_fijas(self):
        # Si la tarea tiene duration_s definida, NO se sobreescribe
        def fake_hook(task):
            return 9999.0
        r = BatchRecipe(
            name="hookable",
            tasks=[
                Task("react", TaskKind.REACCION,
                     duration_s=1800, ode_hook=fake_hook),
            ],
            product_mass_kg_per_batch=100.0,
        )
        bs.resolve_dynamic_durations(r)
        self.assertEqual(r.tasks[0].duration_s, 1800.0)


# ─────────────────────────────────────────────────────────────
# Aislamiento — confirmar que Capa 1 NO importa otros módulos
# ─────────────────────────────────────────────────────────────

class TestAislamiento(unittest.TestCase):
    """Si batch_schedule importa solver/economic/UI, Capa 1
    perdió su autonomía.  Test de regresión arquitectural."""

    def test_imports_minimos(self):
        import importlib
        mod = importlib.import_module("batch_schedule")
        imported_modules = set(sys.modules.keys())
        # batch_schedule NO debe forzar la importación de:
        forbidden = ["flowsheet_solver", "flujoflujoclass",
                      "results_ui", "reactions_db", "nrtl",
                      "thermo_db", "flowsheet_model"]
        deps_loaded = [m for m in forbidden if m in imported_modules]
        # Algunos pueden estar cargados por otros tests previos en la
        # misma sesión, así que sólo nos importa que batch_schedule
        # mismo no los liste como dependencia directa:
        mod_source = ""
        with open(mod.__file__) as _fh:
            mod_source = _fh.read()
        for m in forbidden:
            self.assertNotIn(f"import {m}", mod_source,
                f"batch_schedule.py importa {m} (rompe autonomía Capa 1)")
            self.assertNotIn(f"from {m}", mod_source,
                f"batch_schedule.py importa de {m} (rompe autonomía Capa 1)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
