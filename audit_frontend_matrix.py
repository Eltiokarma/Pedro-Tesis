"""Frente 1 — Matriz de auditoría del frontend por eq_type.

Para CADA tipo del catálogo (equipment_costs.EQUIPMENT_DATA) responde,
de forma headless-compatible (QT_QPA_PLATFORM=offscreen):

  · ¿Hay instancia en los 58 ejemplos? (los tipos sin instancia nunca
    se vieron en la UI real)
  · ¿Qué evidencia específica produce el inspector? (funciones text/
    metrics de inspector_evidence que devuelven algo para un bloque
    real de ese tipo — mass/energy balance son genéricas y no cuentan)
  · ¿Qué secciones declara block_inspector._sections_for?
  · ¿Tiene glyph PFD propio (pfd_symbols) o cae al rectángulo genérico?
  · ¿Tiene puertos catalogados (equipment_ports) con clase por puerto?
  · ¿Tiene sizer (equipment_sizing.SIZER_BY_EQTYPE)?

Uso:
    python audit_frontend_matrix.py            # resumen en consola
    python audit_frontend_matrix.py --md FILE  # además escribe la matriz
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from collections import OrderedDict


# Evidencia ESPECÍFICA por tipo (excluye mass/energy/utility, que son
# genéricas de todos los bloques y no discriminan huecos didácticos).
SPECIFIC_EVIDENCE = [
    ("reactor_text",      lambda ie, b, fs: ie.reactor_text(b)),
    ("reactor_metrics",   lambda ie, b, fs: ie.reactor_metrics(b)),
    ("hx_text",           lambda ie, b, fs: ie.hx_text(b)),
    ("hx_metrics",        lambda ie, b, fs: ie.hx_metrics(b)),
    ("flash_text",        lambda ie, b, fs: ie.flash_text(b)),
    ("flash_metrics",     lambda ie, b, fs: ie.flash_metrics(b)),
    ("mech_sep_text",     lambda ie, b, fs: ie.mech_sep_text(b)),
    ("mech_sep_metrics",  lambda ie, b, fs: ie.mech_sep_metrics(b)),
    ("splitter_text",     lambda ie, b, fs: ie.splitter_text(b, fs)),
    ("splitter_metrics",  lambda ie, b, fs: ie.splitter_metrics(b, fs)),
    ("tank_text",         lambda ie, b, fs: ie.tank_text(b, fs)),
    ("tank_metrics",      lambda ie, b, fs: ie.tank_metrics(b, fs)),
    ("mccabe_text",       lambda ie, b, fs: ie.mccabe_text(b, fs)),
    ("profile_text",      lambda ie, b, fs: ie.profile_text(b, fs)),
    ("column_design_text", lambda ie, b, fs: ie.column_design_text(b, fs)),
    ("column_duties_text", lambda ie, b, fs: ie.column_duties_text(b)),
    ("pump_text",         lambda ie, b, fs: ie.pump_text(b, fs)),
    ("pump_metrics",      lambda ie, b, fs: ie.pump_metrics(b, fs)),
    ("compressor_text",   lambda ie, b, fs: ie.compressor_text(b, fs)),
    ("hydraulic_text",    lambda ie, b, fs: ie.hydraulic_breakdown_text(b, fs)),
    ("dryer_text",        lambda ie, b, fs: ie.dryer_text(b, fs)),
    ("crystallizer_text", lambda ie, b, fs: ie.crystallizer_text(b, fs)),
    ("evaporator_text",   lambda ie, b, fs: ie.evaporator_text(b, fs)),
    ("boiler_text",       lambda ie, b, fs: ie.boiler_text(b, fs)),
    ("valve_text",        lambda ie, b, fs: ie.valve_text(b, fs)),
    ("mixer_text",        lambda ie, b, fs: ie.mixer_text(b, fs)),
]


def build_matrix():
    import equipment_costs as ec
    import equipment_ports as ep
    import pfd_symbols as pfd
    import inspector_evidence as ie
    from examples_registry import list_examples, load_example
    try:
        from equipment_sizing import SIZER_BY_EQTYPE, SIZER_BY_CAT
    except ImportError:
        SIZER_BY_EQTYPE, SIZER_BY_CAT = {}, {}

    def _has_sizer(eq_type):
        # Misma resolución que auto_size_blocks: eq_type específico
        # tiene prioridad; si no, cae a la categoría.
        cat = ec.EQUIPMENT_DATA.get(eq_type, {}).get("categoria", "")
        return (eq_type in SIZER_BY_EQTYPE) or (cat in SIZER_BY_CAT)
    import block_inspector as bi

    # 1. Instancias reales por eq_type en los 58 ejemplos, RESUELTAS —
    # la evidencia del inspector se muestra post-Solve y depende de
    # atributos que computa el solver (duty, VF, split real, etc.).
    import flowsheet_solver as fsv
    instances = {}    # eq_type -> (clave_ejemplo, block, fs)
    counts = {}
    for e in list_examples():
        k = e["clave"]
        fs = load_example(k)
        try:
            fsv.solve(fs)
        except Exception as ex:
            print(f"  (solve de {k} falló: {type(ex).__name__}: {ex})")
        for b in fs.blocks.values():
            counts[b.eq_type] = counts.get(b.eq_type, 0) + 1
            # Hasta 5 instancias por tipo: una sola puede ser un caso
            # degenerado (compresor sin P_op, reactor sin reacciones) y
            # daría un falso hueco didáctico.
            instances.setdefault(b.eq_type, [])
            if len(instances[b.eq_type]) < 5:
                instances[b.eq_type].append((k, b, fs))

    rows = OrderedDict()
    for eq_type in ec.EQUIPMENT_DATA:
        insts = instances.get(eq_type) or []
        evidence = set()
        errors = set()
        for _, b, fs in insts:
            for name, fn in SPECIFIC_EVIDENCE:
                try:
                    if fn(ie, b, fs) is not None:
                        evidence.add(name)
                except Exception as ex:
                    errors.add(f"{name}:ERROR({type(ex).__name__})")
        evidence = sorted(evidence) + sorted(errors)
        sym = pfd.get_for_eq_type(eq_type)
        ports = ep.get_ports(eq_type)
        rows[eq_type] = {
            "example": insts[0][0] if insts else None,
            "n_instances": counts.get(eq_type, 0),
            "evidence": evidence,
            "sections": bi._sections_for(eq_type),
            "glyph": bool(sym),
            "ports": list(ports) if ports else [],
            "port_kinds": {p: ep.get_port_kind(eq_type, p)
                           for p in (ports or [])},
            "sizer": _has_sizer(eq_type),
        }
    return rows


def summarize(rows):
    sin_instancia = [t for t, r in rows.items() if not r["example"]]
    sin_evidencia = [t for t, r in rows.items()
                     if r["example"] and not [e for e in r["evidence"]
                                              if "ERROR" not in e]]
    con_error = [(t, e) for t, r in rows.items()
                 for e in r["evidence"] if "ERROR" in e]
    sin_glyph = [t for t, r in rows.items() if not r["glyph"]]
    sin_ports = [t for t, r in rows.items() if not r["ports"]]
    sin_sizer = [t for t, r in rows.items() if not r["sizer"]]

    print(f"eq_types en catálogo: {len(rows)}")
    print(f"\nSIN instancia en los 58 ejemplos ({len(sin_instancia)}):")
    for t in sin_instancia:
        print(f"  - {t}")
    print(f"\nCON instancia pero SIN evidencia específica "
          f"({len(sin_evidencia)}) — hueco didáctico:")
    for t in sin_evidencia:
        print(f"  - {t}  (ej: {rows[t]['example']})")
    if con_error:
        print(f"\nEvidencia que REVIENTA ({len(con_error)}):")
        for t, e in con_error:
            print(f"  - {t}: {e}")
    print(f"\nSIN glyph PFD propio ({len(sin_glyph)}):")
    for t in sin_glyph:
        print(f"  - {t}")
    print(f"\nSIN puertos catalogados ({len(sin_ports)}):")
    for t in sin_ports:
        print(f"  - {t}")
    print(f"\nSIN sizer ({len(sin_sizer)}):")
    for t in sin_sizer:
        print(f"  - {t}")


def write_md(rows, path):
    lines = [
        "# Matriz de auditoría frontend por eq_type",
        "",
        "Generada por `audit_frontend_matrix.py` — regenerar, no editar.",
        "",
        "| eq_type | ejemplo | #inst | evidencia específica | glyph | puertos | sizer |",
        "|---|---|---:|---|:-:|---:|:-:|",
    ]
    for t, r in rows.items():
        ev = ", ".join(r["evidence"]) or "—"
        lines.append(
            f"| {t} | {r['example'] or '—'} | {r['n_instances']} | {ev} "
            f"| {'✓' if r['glyph'] else '✗'} | {len(r['ports'])} "
            f"| {'✓' if r['sizer'] else '✗'} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nmatriz escrita en {path}")


if __name__ == "__main__":
    rows = build_matrix()
    summarize(rows)
    if "--md" in sys.argv:
        write_md(rows, sys.argv[sys.argv.index("--md") + 1])
