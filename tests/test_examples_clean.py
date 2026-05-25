"""Frente C — ejemplos solver-driven, limpios bajo el auditor.

Verifica que los ejemplos ya reescritos al estilo solver-driven no tengan
hallazgos de consistencia (component_balance / phase / pseudo en
severity warning|error, ni redundant_lock de ninguna severidad).

NOTA: lista incremental.  A medida que el Frente C reescribe más ejemplos
se agregan acá.  Los aún hardcodeados NO se listan todavía.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import flowsheet_model as fm
import flowsheet_solver as fsv
import examples_library as el

# Ejemplos limpios (0 hallazgos warning/error/redundant) tras el Frente C:
# reescritos solver-driven, curación de pseudo-componentes y afinado del
# auditor (locks load-bearing no se marcan como redundantes).
CLEAN_EXAMPLES = [
    # solver-driven / rewrites
    '_example_distillation',
    '_example_ethanol',
    '_example_reactor_flash_column',
    '_example_ethane_cracker_pfr',
    '_example_ethylene_cracking',
    '_example_biodiesel',
    '_example_ammonia',
    '_example_methanol',
    '_example_pasteurizer',
    # evaporadores al vacío / vapor saturado (corrección de P + tolerancia)
    '_example_desalination',
    '_example_leche_gloria',
    '_example_acetic_acid',
    '_example_nuclear_steam',
    # limpios por curación de pseudo-componentes (alimentario/material)
    '_example_pineapple_juice',
    '_example_beer_brewing',
    '_example_bread_baking',
    '_example_penicillin',
    # limpios por afinado del detector redundant_lock (química inorgánica)
    '_example_chloralkali_hcl',
    '_example_quimpac_chloralkali',
    '_example_hno3_ostwald',
    '_example_cement',
    '_example_glass',
    '_example_polyethylene',
    '_example_sulfuric_acid',
    '_example_urea',
    '_example_water_treatment',
]


def _build_fake():
    class _FE:
        def __init__(self):
            self.fs = fm.Flowsheet()
            self.labor_workers = 0
        _add_example_block  = el.ExampleBuilder._add_example_block
        _add_example_stream = el.ExampleBuilder._add_example_stream
        _add_example_extra  = el.ExampleBuilder._add_example_extra
        _set_example_labor  = el.ExampleBuilder._set_example_labor
        _set_block_duty     = el.ExampleBuilder._set_block_duty
    return _FE()


def test_clean_examples():
    for name in CLEAN_EXAMPLES:
        fake = _build_fake()
        getattr(el.ExampleBuilder, name)(fake)
        res = fsv.solve(fake.fs)
        report = res.audit_report
        assert report is not None, f"{name}: audit_report ausente"

        bad_balance = [f for f in report.by_category('component_balance')
                       if f.severity in ('warning', 'error')]
        bad_phase   = [f for f in report.by_category('phase')
                       if f.severity in ('warning', 'error')]
        bad_pseudo  = [f for f in report.by_category('pseudo')
                       if f.severity in ('warning', 'error')]
        bad_redund  = list(report.by_category('redundant_lock'))

        assert not bad_balance, \
            f"{name}: {len(bad_balance)} balance issues: " \
            f"{[f.message[:60] for f in bad_balance[:2]]}"
        assert not bad_phase, \
            f"{name}: {len(bad_phase)} phase issues: " \
            f"{[f.message[:60] for f in bad_phase[:2]]}"
        assert not bad_pseudo, \
            f"{name}: {len(bad_pseudo)} pseudo issues (deben ser cero tras " \
            f"el reemplazo a moléculas reales)"
        assert not bad_redund, \
            f"{name}: {len(bad_redund)} composiciones lockeadas redundantes"
        print(f"  ✓ {name}: limpio")


if __name__ == '__main__':
    print("=" * 70)
    print("Tests de ejemplos solver-driven (Frente C)")
    print("=" * 70)
    test_clean_examples()
    print("\nLos ejemplos reescritos están limpios ✓")
