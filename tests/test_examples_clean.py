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
import examples_registry as reg

# Ejemplos limpios (0 hallazgos warning/error/redundant) tras el Frente C:
# reescritos solver-driven, curación de pseudo-componentes y afinado del
# auditor (locks load-bearing no se marcan como redundantes).  Claves del
# registry (data/examples/<clave>.json).
CLEAN_EXAMPLES = [
    # solver-driven / rewrites
    'distillation',
    'ethanol',
    'rxn_flash_col',
    'ethane_pfr',
    'ethylene_crk',
    'biodiesel',
    'ammonia',
    'methanol',
    'pasteurizer',
    # evaporadores al vacío / vapor saturado (corrección de P + tolerancia)
    'desal',
    'leche_gloria',
    'acetic',
    'nuclear',
    # limpios por curación de pseudo-componentes (alimentario/material)
    'pineapple',
    'beer',
    'bread',
    'penicillin',
    # limpios por afinado del detector redundant_lock (química inorgánica)
    'chloralkali_hcl',
    'quimpac',
    'hno3',
    'cement',
    'glass',
    'ldpe',
    'sulfuric',
    'urea',
    'water_treat',
]


def test_clean_examples():
    for name in CLEAN_EXAMPLES:
        fs = reg.load_example(name)
        res = fsv.solve(fs)
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
