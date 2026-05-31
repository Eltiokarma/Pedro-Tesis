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
import examples_registry as reg
import dof_audit as da


# Los ejemplos se cargan desde data/examples/<clave>.json vía el registry
# (data-driven); los builders imperativos fueron retirados.  Orden = orden
# del menú (manifest).  Cada entrada es (clave, builder) — el builder se
# conserva como string-key para la whitelist y para mostrar el nombre
# familiar en la tabla.
EXAMPLES = [(e["clave"], e["builder"]) for e in reg.list_examples()]


# ─────────────────────────────────────────────────────────────
# Falsos positivos CONOCIDOS y aceptados de find_conflicts.
#
# find_conflicts usa un residual de energía SIMPLIFICADO
#   (h_out - h_in - duty - m_in·heat_of_reaction)
# que no modela todas las formas de energía.  En estos dos bloques el
# residual no cierra dentro de tolerancia, PERO el solver real cierra el
# balance de energía con 0 errores (verificado en validate_ui.py).  No
# son subespecificación ni overspec reales — se documentan y se ignoran:
#
#   · quimpac_chloralkali / R-201: celda electrolítica.  El `duty` es
#     potencia ELÉCTRICA que alimenta la reacción endotérmica, no calor
#     sensible al fluido (heat_of_reaction=0).  Análogo a la exención que
#     find_conflicts ya hace para bombas/compresores eléctricos.
#   · potato_chips / FR-101: freidora.  El `duty` cubre evaporación de
#     agua del producto (cambio de fase), no contemplada en el residual.
#
# Decisión (auditoría DOF): dejarlos documentados; el solver los resuelve.
KNOWN_CONFLICT_FALSE_POSITIVES = {
    ("_example_quimpac_chloralkali", "R-201"),
    ("_example_potato_chips",        "FR-101"),
}


def audit_one(clave, builder):
    fs = reg.load_example(clave)

    # 1) DOF topológico estructural
    rep = da.analyze_flowsheet(fs)

    # 2) DOF estilo Aspen por bloque (del solver)
    rows = fsv.analyze_dof(fs)
    n_under = sum(1 for r in rows if r["dof"] > 0)
    n_redund = sum(1 for r in rows if r["dof"] < 0)

    # 3) Conflictos numéricos de locks (overspec real).  Separa los
    #    falsos positivos conocidos y aceptados (ver whitelist arriba).
    all_conflicts = fsv.find_conflicts(fs)
    conflicts, known = [], []
    for c in all_conflicts:
        block = c.split(":", 1)[0].strip()
        if (builder, block) in KNOWN_CONFLICT_FALSE_POSITIVES:
            known.append(c)
        else:
            conflicts.append(c)

    return {
        "name": builder,
        "fs": fs,
        "rep": rep,
        "rows": rows,
        "n_under_aspen": n_under,
        "n_redund_aspen": n_redund,
        "conflicts": conflicts,
        "known_conflicts": known,
    }


def main():
    verbose = "--verbose" in sys.argv

    print("=" * 100)
    print("AUDITORÍA DE GRADOS DE LIBERTAD (sistema sudoku) — catálogo de ejemplos")
    print("=" * 100)
    print(f"{'ejemplo':38s} {'topo':>6} {'indet':>6} {'under':>6} {'over':>5} "
          f"{'a-under':>8} {'a-redun':>8} {'confl':>6} {'(fp)':>5}")
    print("-" * 100)

    fully_ok = []
    has_issue = []

    for clave, builder in EXAMPLES:
        try:
            r = audit_one(clave, builder)
        except Exception as e:
            print(f"  ✗ {builder:36s} ERROR carga/audit: {type(e).__name__}: {e}")
            has_issue.append(builder)
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
        (fully_ok if clean else has_issue).append(builder)

        kf = len(r["known_conflicts"])
        print(f"  {mark} {builder:36s} {topo:>6} {rep.n_indeterminable_mass:>6} "
              f"{rep.n_under:>6} {rep.n_over:>5} "
              f"{r['n_under_aspen']:>8} {r['n_redund_aspen']:>8} "
              f"{len(r['conflicts']):>6} {kf:>5}")

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
    print(f"          a-under/a-redun=bloques under/redundant (DOF Aspen) | confl=conflictos reales | "
          f"(fp)=conflictos falsos-positivos conocidos (solver cierra OK)")
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
    for clave, builder in EXAMPLES:
        try:
            r = audit_one(clave, builder)
        except Exception:
            continue
        rep = r["rep"]
        if rep.n_indeterminable_mass == 0 and not r["conflicts"]:
            continue
        any_hard = True
        print(f"\n▶ {builder.replace('_example_','')}")
        if rep.n_indeterminable_mass:
            indet = [ss.name for ss in rep.streams if ss.mass_status == "unknown"]
            print(f"   masa indeterminable ({rep.n_indeterminable_mass}): {', '.join(indet[:12])}")
        for c in r["conflicts"]:
            print(f"   conflicto: {c}")
    if not any_hard:
        print("\n  Ninguna falla dura: todos los ejemplos tienen masa determinable y locks sin conflicto.")

    # Falsos positivos conocidos y aceptados (documentados, no son fallas)
    print()
    print("=" * 100)
    print("FALSOS POSITIVOS CONOCIDOS de find_conflicts (documentados — solver cierra OK)")
    print("=" * 100)
    any_fp = False
    for clave, builder in EXAMPLES:
        try:
            r = audit_one(clave, builder)
        except Exception:
            continue
        for c in r["known_conflicts"]:
            any_fp = True
            print(f"  · {builder.replace('_example_','')}: {c}")
    if not any_fp:
        print("  (ninguno)")


if __name__ == "__main__":
    main()
