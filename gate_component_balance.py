"""
gate_component_balance.py — GATE RATCHET del balance por componente.

Filosofía RATCHET: el gate falla SÓLO para los ejemplos ya corregidos, que
viven en data/component_balance_whitelist.json (versionado, NO hardcodeado
aquí).  Un ejemplo entra a la whitelist cuando se corrige su balance por
componente (Partes 2-4); a partir de ahí, este gate exige que SIGA limpio
(cero hallazgos a tolerancia 1%).  Los ejemplos aún NO corregidos no fallan
el gate — se siguen reportando en audit_examples_components.py (baseline).

Así el progreso es monotónico: cada fix agranda la whitelist y queda
protegido contra regresiones, sin bloquear por la deuda preexistente.

USO:
    python gate_component_balance.py        # 0 = verde, 1 = regresión
    echo $?
"""
import os
import sys
import json

WHITELIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "data", "component_balance_whitelist.json")


def _load_whitelist():
    with open(WHITELIST_PATH, encoding="utf-8") as f:
        d = json.load(f)
    corrected = d.get("corrected", [])
    if not isinstance(corrected, list):
        raise ValueError("whitelist['corrected'] debe ser lista")
    return corrected


def run_gate():
    import audit_examples_components as aec
    aec._headless()

    corrected = _load_whitelist()
    print("=" * 78)
    print(f"GATE RATCHET — balance por componente ({len(corrected)} ejemplo(s) "
          f"en la whitelist)")
    print("=" * 78)

    if not corrected:
        print("  (whitelist vacía — nada que proteger todavía; verde por defecto)")
        print("=" * 78)
        print("✓ GATE VERDE: 0/0 ejemplos corregidos auditan limpio.")
        return 0

    fails = []
    for key in sorted(corrected):
        try:
            rep = aec.audit_example(key)
        except Exception as e:
            fails.append((key, f"error de carga/auditoría: {type(e).__name__}: {e}"))
            print(f"  ✗ {key:18s} {type(e).__name__}: {e}")
            continue
        findings = rep.get("findings", [])
        if findings:
            fails.append((key, f"{len(findings)} hallazgo(s) reaparecieron"))
            nc, nm = rep["n_critico"], rep["n_mayor"]
            print(f"  ✗ {key:18s} REGRESIÓN: {nc} CRÍTICO / {nm} MAYOR")
            for f in findings[:8]:
                print(f"        [{f.get('severity')}] {f.get('message')}")
        else:
            print(f"  ✓ {key:18s} limpio")

    print("=" * 78)
    if fails:
        print(f"✗ GATE ROJO: {len(fails)}/{len(corrected)} ejemplos corregidos "
              f"REGRESARON. El balance por componente debe seguir cerrando.")
        return 1
    print(f"✓ GATE VERDE: {len(corrected)}/{len(corrected)} ejemplos corregidos "
          f"auditan limpio.")
    return 0


if __name__ == "__main__":
    sys.exit(run_gate())
