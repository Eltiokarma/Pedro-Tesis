"""
gate_pressure_source.py — GATE RATCHET de atribución de presión (FASE 5).

Filosofía RATCHET (idéntica a gate_component_balance): el gate falla SÓLO para
los ejemplos ya corregidos, que viven en data/pressure_source_whitelist.json
(versionado, NO hardcodeado).  Un ejemplo entra a la whitelist cuando se
corrige su atribución de presión (FASE 3): la presión la crea un dispositivo
(rotativo/columna), no un horno/HX/mixer/vessel, y los locks de presión tienen
origen declarado (no heurístico).  A partir de ahí el gate exige que SIGA
limpio (cero hallazgos pressure_source).

USO:
    python gate_pressure_source.py        # 0 = verde, 1 = regresión
"""
import os
import sys
import json

WHITELIST_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "data", "pressure_source_whitelist.json")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "examples")


def _load_whitelist():
    with open(WHITELIST_PATH, encoding="utf-8") as f:
        d = json.load(f)
    c = d.get("corrected", [])
    if not isinstance(c, list):
        raise ValueError("whitelist['corrected'] debe ser lista")
    return c


def pressure_source_findings(key):
    """Resuelve el ejemplo headless y devuelve los hallazgos pressure_source."""
    import flowsheet_model as fm
    import flowsheet_solver as fsv
    from flowsheet_consistency_audit import audit_flowsheet
    with open(os.path.join(DATA_DIR, f"{key}.json"), encoding="utf-8") as f:
        fs = fm.Flowsheet.from_dict(json.load(f))
    fsv.solve(fs)
    return audit_flowsheet(fs).by_category('pressure_source')


def run_gate():
    try:
        from export_examples import _headless_mocks
        _headless_mocks()
    except Exception:
        pass
    corrected = _load_whitelist()
    print("=" * 78)
    print(f"GATE RATCHET — atribución de presión ({len(corrected)} ejemplo(s) "
          f"en la whitelist)")
    print("=" * 78)
    if not corrected:
        print("  (whitelist vacía — verde por defecto)")
        print("✓ GATE VERDE: 0/0 ejemplos corregidos.")
        return 0
    fails = []
    for key in sorted(corrected):
        try:
            fnd = pressure_source_findings(key)
        except Exception as e:
            fails.append(key)
            print(f"  ✗ {key:16s} error: {type(e).__name__}: {e}")
            continue
        if fnd:
            fails.append(key)
            print(f"  ✗ {key:16s} REGRESIÓN: {len(fnd)} hallazgo(s)")
            for f in fnd[:6]:
                print(f"        {f.message[:100]}")
        else:
            print(f"  ✓ {key:16s} limpio")
    print("=" * 78)
    if fails:
        print(f"✗ GATE ROJO: {len(fails)}/{len(corrected)} ejemplos regresaron.")
        return 1
    print(f"✓ GATE VERDE: {len(corrected)}/{len(corrected)} ejemplos limpios.")
    return 0


if __name__ == "__main__":
    sys.exit(run_gate())
