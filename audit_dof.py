"""
audit_dof.py — Auditoría de GRADOS DE LIBERTAD ("sistema sudoku")
sobre todos los ejemplos del catálogo.

A diferencia de validate_ui.py (que corre el solver y verifica que
los balances cierren — pero el solver cierra IGUAL usando defaults
aunque el flowsheet esté subespecificado), este script audita la
ESTRUCTURA de specs:

  · dof_audit.analyze_flowsheet  → DOF topológico estructural:
        ¿se puede determinar toda la masa y composición a partir
        de los locks (sudoku) por propagación?  Detecta streams
        cuya masa NO es determinable y bloques under/over.

  · flowsheet_solver.dof_analysis → DOF estilo Aspen por bloque:
        n_vars - n_constr - n_locked.  Reporta bloques underspec
        (faltan specs) / redundant (specs de más).

  · flowsheet_solver.find_conflicts → overspec NUMÉRICO: locks que
        no satisfacen el balance físico (conflicto de sudoku).

Objetivo de la auditoría: cada ejemplo debe ser RESOLUBLE con la
información necesaria — sin masa indeterminable y sin conflictos de
locks.

USO:
    python audit_dof.py            # tabla resumen + detalle de fallas
    python audit_dof.py --verbose  # detalle DOF por bloque de cada ejemplo
"""
import os
import sys

from validate_ui import headless_mocks
headless_mocks()

import flowsheet_model as fm
import flowsheet_solver as fsv
import examples_library as el
import dof_audit as da


class _FakeEditor:
    def __init__(self):
        self.fs = fm.Flowsheet()
        self.labor_workers = 0
    _add_example_block  = el.ExampleBuilder._add_example_block
    _add_example_stream = el.ExampleBuilder._add_example_stream
    _add_example_extra  = el.ExampleBuilder._add_example_extra
    _set_example_labor  = el.ExampleBuilder._set_example_labor
    _set_block_duty     = el.ExampleBuilder._set_block_duty


EXAMPLES = [
    '_example_hda', '_example_methanol', '_example_distillation',
    '_example_ammonia', '_example_ethanol', '_example_biodiesel',
    '_example_crude_distillation', '_example_hda_full',
    '_example_gas_sweetening', '_example_sugar_mill',
    '_example_smr_equilibrium', '_example_ethane_cracker_pfr',
    '_example_haber_recycle', '_example_distillation_ethanol_water',
    '_example_reactor_flash_column', '_example_hydraulic_plant',
    '_example_industrial_complete', '_example_quimpac_chloralkali',
    '_example_hno3_ostwald', '_example_talara_refinery',
    '_example_pasteurizer', '_example_pineapple_juice',
    '_example_potato_chips', '_example_beer_brewing',
    '_example_sulfuric_acid', '_example_acetic_acid',
    '_example_polyethylene', '_example_chloralkali_hcl',
    '_example_cement', '_example_glass', '_example_soap',
    '_example_urea', '_example_leche_gloria',
    '_example_ethylene_cracking', '_example_air_separation',
    '_example_water_treatment', '_example_bread_baking',
    '_example_penicillin', '_example_rankine_cycle',
    '_example_nuclear_steam', '_example_desalination',
]


def audit_one(name):
    fake = _FakeEditor()
    getattr(el.ExampleBuilder, name)(fake)
    fs = fake.fs

    # 1) DOF topológico estructural
    rep = da.analyze_flowsheet(fs)

    # 2) DOF estilo Aspen por bloque (del solver)
    rows = fsv.analyze_dof(fs)
    n_under = sum(1 for r in rows if r["dof"] > 0)
    n_redund = sum(1 for r in rows if r["dof"] < 0)

    # 3) Conflictos numéricos de locks (overspec real)
    conflicts = fsv.find_conflicts(fs)

    return {
        "name": name,
        "fs": fs,
        "rep": rep,
        "rows": rows,
        "n_under_aspen": n_under,
        "n_redund_aspen": n_redund,
        "conflicts": conflicts,
    }


def main():
    verbose = "--verbose" in sys.argv

    print("=" * 100)
    print("AUDITORÍA DE GRADOS DE LIBERTAD (sistema sudoku) — catálogo de ejemplos")
    print("=" * 100)
    print(f"{'ejemplo':38s} {'topo':>6} {'indet':>6} {'under':>6} {'over':>5} "
          f"{'a-under':>8} {'a-redun':>8} {'confl':>6}")
    print("-" * 100)

    fully_ok = []
    has_issue = []

    for name in EXAMPLES:
        try:
            r = audit_one(name)
        except Exception as e:
            print(f"  ✗ {name:36s} ERROR builder/audit: {type(e).__name__}: {e}")
            has_issue.append(name)
            continue

        rep = r["rep"]
        topo = "OK" if (rep.total_dof == 0 and rep.n_indeterminable_mass == 0) else \
               ("UNDER" if rep.total_dof > 0 else "OVER")
        # "clean" = sin masa indeterminable estructural y sin conflictos numéricos.
        # (under/redundant de Aspen no es necesariamente un fallo: redundant=OK si
        #  es consistente; under estructural sí lo es.)
        clean = (rep.n_indeterminable_mass == 0
                 and rep.total_dof == 0
                 and not r["conflicts"])
        mark = "✓" if clean else "⚠"
        (fully_ok if clean else has_issue).append(name)

        print(f"  {mark} {name:36s} {topo:>6} {rep.n_indeterminable_mass:>6} "
              f"{rep.n_under:>6} {rep.n_over:>5} "
              f"{r['n_under_aspen']:>8} {r['n_redund_aspen']:>8} "
              f"{len(r['conflicts']):>6}")

        if verbose and not clean:
            for b in rep.blocks:
                if b.overall != "ok":
                    print(f"        · {b.name} [{b.eq_type}] DOF={b.total_dof:+d}")
                    for n in b.notes:
                        print(f"            - {n}")
            for c in r["conflicts"]:
                print(f"        ⚠ CONFLICTO: {c}")

    print("-" * 100)
    print(f"Leyenda:  topo=status topológico | indet=streams sin masa determinable | "
          f"under/over=bloques DOF topológico")
    print(f"          a-under/a-redun=bloques under/redundant (DOF Aspen) | confl=conflictos numéricos de locks")
    print()
    print(f"RESUMEN:  {len(fully_ok)}/{len(EXAMPLES)} ejemplos limpios "
          f"(masa determinable + DOF=0 + sin conflictos)")
    if has_issue:
        print(f"          {len(has_issue)} con observaciones: {', '.join(n.replace('_example_','') for n in has_issue)}")

    # Detalle de fallas duras (indeterminable o conflicto)
    print()
    print("=" * 100)
    print("DETALLE DE FALLAS DURAS (masa indeterminable o conflicto de locks)")
    print("=" * 100)
    any_hard = False
    for name in EXAMPLES:
        try:
            r = audit_one(name)
        except Exception:
            continue
        rep = r["rep"]
        if rep.n_indeterminable_mass == 0 and not r["conflicts"]:
            continue
        any_hard = True
        print(f"\n▶ {name.replace('_example_','')}")
        if rep.n_indeterminable_mass:
            indet = [ss.name for ss in rep.streams if ss.mass_status == "unknown"]
            print(f"   masa indeterminable ({rep.n_indeterminable_mass}): {', '.join(indet[:12])}")
        for c in r["conflicts"]:
            print(f"   conflicto: {c}")
    if not any_hard:
        print("\n  Ninguna falla dura: todos los ejemplos tienen masa determinable y locks sin conflicto.")


if __name__ == "__main__":
    main()
