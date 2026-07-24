#!/usr/bin/env python3
"""
tools/preview_catalogo.py — censo del catálogo comercial + impacto en ejemplos.

Helper de solo-lectura para la cosecha del catálogo (Plan 6×): muestra
cuántas opciones y marcas hay por tipo, marca los que aún no llegan a la
meta de ≥6 opciones / ≥2 marcas, y lista qué bloques de qué ejemplos
ganarían selector con el catálogo actual.  NO modifica nada.

USO:
    python tools/preview_catalogo.py
"""
import collections
import glob
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

META_OPCIONES = 6
META_MARCAS = 2


def _cat():
    with open(os.path.join(_ROOT, "data", "equipos_comerciales.json"),
              encoding="utf-8") as f:
        return json.load(f)["equipos"]


def main():
    equipos = _cat()
    por_tipo = collections.defaultdict(list)
    for e in equipos:
        por_tipo[e["eq_type"]].append(e)

    print("=" * 68)
    print(f"CATÁLOGO COMERCIAL — {len(equipos)} entradas · "
          f"meta ≥{META_OPCIONES} opciones y ≥{META_MARCAS} marcas por tipo")
    print("=" * 68)
    for tipo in sorted(por_tipo):
        ents = por_tipo[tipo]
        marcas = sorted({e["marca"] for e in ents})
        con_S = sum(1 for e in ents if "S" in e)
        familia = sum(1 for e in ents if e.get("granularidad") == "familia")
        ok = len(ents) >= META_OPCIONES and len(marcas) >= META_MARCAS
        flag = "✓" if ok else "·"
        extra = []
        if len(ents) < META_OPCIONES:
            extra.append(f"faltan {META_OPCIONES - len(ents)} opciones")
        if len(marcas) < META_MARCAS:
            extra.append(f"faltan {META_MARCAS - len(marcas)} marcas")
        if familia:
            extra.append(f"{familia} en granularidad=familia (reemplazar)")
        tail = f"  ⚠ {' · '.join(extra)}" if extra else ""
        print(f"  {flag} {tipo:34s} {len(ents):2d} ops · "
              f"{len(marcas)} marca(s) [{', '.join(marcas)}]{tail}")

    # Impacto: qué instancias de ejemplos ganan selector
    tipos_cat = set(por_tipo)
    print("\n" + "=" * 68)
    print("INSTANCIAS EN EJEMPLOS QUE HOY TIENEN SELECTOR")
    print("=" * 68)
    data_dir = os.path.join(_ROOT, "data", "examples")
    total_hits = 0
    for p in sorted(glob.glob(os.path.join(data_dir, "*.json"))):
        clave = os.path.splitext(os.path.basename(p))[0]
        if clave in ("_golden", "manifest"):
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        hits = [(b["name"], b["eq_type"]) for b in d.get("blocks", {}).values()
                if b.get("eq_type") in tipos_cat and not b.get("auto_aux")]
        if hits:
            total_hits += len(hits)
            for nombre, et in hits:
                print(f"  {clave:16s} {nombre:10s} {et}")
    print(f"\n  → {total_hits} bloque(s) con selector en {len(tipos_cat)} "
          f"tipo(s) catalogados.")


if __name__ == "__main__":
    main()
