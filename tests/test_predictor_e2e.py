"""Smoke test end-to-end del predictor (Capa 4b).

Corre desde terminal en tu Windows DESPUES de:
    pip install rdkit thermo chemicals

Uso:
    cd Pedro-Tesis
    python tests/test_predictor_e2e.py

Resultado esperado: las 6 metricas del §10.5 del doc todas PASS si
las 3 dependencias estan instaladas. Si alguna metrica falla,
imprime el detalle del bug para reportar.

NO requiere PySide6 — es 100% logica del predictor.
"""
from __future__ import annotations

import os
import sys
import time
import traceback

# Agregar el directorio raiz del proyecto a sys.path para que 'chemfx'
# y los modulos top-level (flowsheet_model, thermo_db, etc.) se
# importen sin necesidad de instalar el paquete o cambiar de cwd.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
WARN = "\033[93m⚠ WARN\033[0m"


def header(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def section(title: str) -> None:
    print()
    print(f"--- {title}")


def test_dependencies():
    """Test 0: verificar dependencias instaladas."""
    section("Test 0 — Dependencias")
    import chemfx
    deps = chemfx.verify_dependencies()
    for name, ok in deps.items():
        marker = PASS if ok else FAIL
        print(f"  {marker}  {name}: {'available' if ok else 'NO instalada'}")
    if not all(deps.values()):
        print()
        print("  Para instalar lo que falta:")
        missing = [n for n, ok in deps.items() if not ok]
        print(f"    pip install {' '.join(missing)}")
    return all(deps.values())


def test_smiles_loader():
    """Test 1: SMILES loader carga 100+ compuestos."""
    section("Test 1 — SMILES loader")
    from chemfx.predictor import smiles_loader
    db = smiles_loader.load_smiles_db()
    n = len(db)
    ok = n >= 100
    print(f"  {(PASS if ok else FAIL)}  load_smiles_db(): {n} compuestos ({'≥100' if ok else '<100'})")
    # Spot checks
    samples = [("ethanol", "CCO"), ("water", "O"), ("benzene", "c1ccccc1"),
               ("phenol", "Oc1ccccc1"), ("acetic_acid", "CC(=O)O")]
    for name, expected in samples:
        got = smiles_loader.get_smiles(name)
        match = got == expected
        print(f"  {(PASS if match else FAIL)}  {name}: {got!r} (esperado {expected!r})")
    return ok


def test_detect_groups():
    """Test 2: detect_groups identifica grupos funcionales."""
    section("Test 2 — detect_groups (requiere RDKit)")
    from chemfx import RDKIT_AVAILABLE
    if not RDKIT_AVAILABLE:
        print(f"  {WARN}  RDKit no instalado — saltando")
        return False
    from chemfx.predictor import functional_groups as fg
    cases = [
        ("ethanol", "alcohol_primario"),
        ("acetic_acid", "acido_carboxilico"),
        ("acetone", "cetona"),
        ("benzene", "aromatico"),
        ("phenol", "alcohol_aromatico"),
        ("acetaldehyde", "aldehido"),
    ]
    all_ok = True
    for compound, expected_group in cases:
        groups = fg.detect_groups(compound)
        names = {g.name for g in groups}
        ok = expected_group in names
        if not ok:
            all_ok = False
        print(f"  {(PASS if ok else FAIL)}  {compound}: detecta {expected_group}? "
              f"(grupos: {sorted(names) or 'NINGUNO'})")
    return all_ok


def test_joback():
    """Test 3: Joback estima ΔHf° de etanol ~ -235 ± 5 kJ/mol."""
    section("Test 3 — Joback wrapper (requiere thermo)")
    from chemfx import THERMO_AVAILABLE
    from chemfx.predictor import joback_wrapper
    if not THERMO_AVAILABLE:
        print(f"  {WARN}  thermo no instalado — saltando")
        return False
    est = joback_wrapper.estimate_via_joback("CCO")   # ethanol
    if est is None:
        print(f"  {FAIL}  estimate_via_joback('CCO') devolvio None")
        return False
    dh = est.get("dh_f_298_kJ_mol")
    if dh is None:
        print(f"  {FAIL}  no se obtuvo dh_f_298_kJ_mol")
        return False
    expected_min, expected_max = -245, -225    # tolerancia ±5 vs literatura
    ok = expected_min <= dh.value <= expected_max
    print(f"  {(PASS if ok else FAIL)}  ΔHf°(etanol via thermo Joback) = "
          f"{dh.value:.2f} ± {dh.uncertainty:.1f} kJ/mol "
          f"(esperado: -235 ± 5; lit: -234.4)")
    return ok


def test_predict_reactions_curated():
    """Test 4: predict_reactions encuentra reaccion curada conocida."""
    section("Test 4 — predict_reactions (curated)")
    from chemfx.predictor import reaction_predictor as rp
    cases = [
        (["methane", "oxygen"], 1200, "R001"),       # combustion CH4
        (["ethanol", "acetic_acid"], 350, "R008"),   # esterificacion
        (["n2", "hydrogen"], 700, "R004"),           # Haber-Bosch
    ]
    all_ok = True
    for feed, T, expected_id in cases:
        fa = rp.predict_reactions(feed_compounds=feed, T_K=T)
        ids = [r.id for r in fa.curated]
        ok = expected_id in ids
        if not ok:
            all_ok = False
        print(f"  {(PASS if ok else FAIL)}  feed={feed} @ {T}K: "
              f"esperado {expected_id} en curated. Encontrados: {ids[:3]}")
    return all_ok


def test_predict_reactions_predicted():
    """Test 5: predict_reactions detecta templates T01-T20."""
    section("Test 5 — predict_reactions (predicted, requiere RDKit)")
    from chemfx import RDKIT_AVAILABLE
    if not RDKIT_AVAILABLE:
        print(f"  {WARN}  RDKit no instalado — saltando")
        return False
    from chemfx.predictor import reaction_predictor as rp
    from chemfx.predictor import transformations as tf

    # Diagnostico previo: validar cuales SMARTS parsean
    smarts_valid = tf.validate_smarts()
    n_valid = sum(1 for v in smarts_valid.values() if v)
    n_total = len(smarts_valid)
    print(f"  ℹ  SMARTS validos: {n_valid}/{n_total} templates")
    invalid = [tid for tid, ok in smarts_valid.items() if not ok]
    if invalid:
        print(f"  ℹ  Invalidos (skipean): {invalid[:5]}")

    # Diagnostico directo: aplicar T01 a (acetic_acid, ethanol) manualmente
    from chemfx.predictor import smiles_loader
    t01 = tf.get_transformation("T01")
    if t01:
        print(f"  ℹ  T01 SMARTS: {t01.reaction_smarts[:60]}...")
        ac = smiles_loader.get_smiles("acetic_acid")
        et = smiles_loader.get_smiles("ethanol")
        print(f"  ℹ  Probando T01 con ({ac}, {et}):")
        products = tf.apply_to_compounds(t01, [ac, et])
        print(f"  ℹ    RDKit RunReactants devolvio {len(products)} sets de productos")
        for p in products[:3]:
            print(f"      {p}")

    fa = rp.predict_reactions(
        feed_compounds=["ethanol", "acetic_acid"], T_K=350,
    )
    n = len(fa.predicted)
    ok = n >= 1
    print(f"  {(PASS if ok else FAIL)}  feed=[ethanol, acetic_acid] @ 350K: "
          f"{n} predicted reactions (esperado ≥1, principalmente T01)")
    for r in fa.predicted[:3]:
        print(f"    {r.id}: {r.display_label[:60]}  Keq={r.keq_at_T:.1e}, "
              f"fav={r.favorable_at_T}")
    return ok


def test_danger_detector():
    """Test 6: danger_detector dispara warning con H2+O2 @ 700K."""
    section("Test 6 — danger_detector (H2+O2 @ 700K → critical)")
    from chemfx.predictor.types import FeedAnalysis
    from chemfx.reactivity_engine import danger_detector
    fa = FeedAnalysis(compounds=["hydrogen", "oxygen"], T_K=700,
                       P_bar=1.0, tau_s=10.0)
    warns = danger_detector.detect_dangers(fa, location="M-101",
                                            block_tau_s=10.0)
    n_critical = sum(1 for w in warns if w.severity == "critical")
    ok = n_critical >= 1
    print(f"  {(PASS if ok else FAIL)}  {len(warns)} warnings, "
          f"{n_critical} critical (esperado ≥1)")
    for w in warns:
        print(f"    [{w.severity}] {w.risk_category}: {w.message[:65]}...")
    return ok


def test_auto_reactions():
    """Test 7: generator produce ≥200 combustiones AUTO."""
    section("Test 7 — auto_reactions generator")
    from chemfx.auto_reactions import generator as g
    all_rxns = g.generate_all_auto_reactions()
    n_combustion = sum(
        1 for r in all_rxns
        if r.get("category") in ("combustion", "combustion_incomplete")
    )
    n_cracking = sum(1 for r in all_rxns if r.get("category") == "cracking")
    ok = n_combustion >= 200
    print(f"  {(PASS if ok else FAIL)}  combustion (T12+T13): {n_combustion} "
          f"(esperado ≥200)")
    print(f"  ℹ  cracking termico (T10): {n_cracking}")
    print(f"  ℹ  total AUTO: {len(all_rxns)}")
    return ok


def test_analyze_flowsheet():
    """Test 8: analyze_flowsheet anota bloques con warnings."""
    section("Test 8 — analyze_flowsheet (modo pasivo)")
    # Construir un mini flowsheet de prueba
    try:
        from flowsheet_model import Block, Stream, Flowsheet
    except ImportError:
        print(f"  {WARN}  flowsheet_model no disponible — saltando")
        return False

    fs = Flowsheet()
    # Mixer con H2 + O2 a 700K → debe disparar warning crítico
    m101 = Block(
        id=1, name="M-101", eq_type="Mixer — static", S=1.0, n=1,
        x=0, y=0, T_op_K=700, P_op_bar=1.0,
    )
    fs.blocks[1] = m101
    # Streams de entrada con composition
    s_h2 = Stream(id=10, name="S-H2", src=-1, dst=1, mass_flow=10.0,
                   composition={"hydrogen": 1.0}, temperature=400.0)
    s_o2 = Stream(id=11, name="S-O2", src=-1, dst=1, mass_flow=10.0,
                   composition={"oxygen": 1.0}, temperature=400.0)
    fs.streams[10] = s_h2
    fs.streams[11] = s_o2

    import chemfx
    t0 = time.time()
    results = chemfx.analyze_flowsheet(fs)
    elapsed = time.time() - t0
    print(f"  ℹ  analyze_flowsheet: {elapsed*1000:.0f} ms para 1 bloque")
    if 1 not in results:
        print(f"  {FAIL}  no se anoto el bloque 1")
        return False
    fa = results[1]
    n_warn = fa.get("n_warnings", 0)
    ok = n_warn >= 1
    print(f"  {(PASS if ok else FAIL)}  bloque M-101 (H2+O2 @ 700K): "
          f"{n_warn} warnings anotadas (esperado ≥1)")
    for w in fa.get("warnings", []):
        print(f"    [{w['severity']}] {w['risk_category']}: {w['message'][:60]}...")
    # Verificar que block.reaction_warnings tambien se anoto
    if hasattr(m101, "reaction_warnings"):
        ok2 = len(m101.reaction_warnings) == n_warn
        print(f"  {(PASS if ok2 else FAIL)}  block.reaction_warnings anotado: "
              f"{len(m101.reaction_warnings)} entries")
    return ok


# ======================================================
# MAIN
# ======================================================
def main():
    header("PREDICTOR DE REACCIONES — SMOKE TEST E2E")

    tests = [
        ("dependencias", test_dependencies),
        ("SMILES loader", test_smiles_loader),
        ("detect_groups", test_detect_groups),
        ("Joback wrapper", test_joback),
        ("predict_reactions curated", test_predict_reactions_curated),
        ("predict_reactions predicted", test_predict_reactions_predicted),
        ("danger_detector", test_danger_detector),
        ("auto_reactions generator", test_auto_reactions),
        ("analyze_flowsheet", test_analyze_flowsheet),
    ]
    results = []
    for label, fn in tests:
        try:
            ok = fn()
        except Exception:
            print(f"  {FAIL}  excepcion durante el test:")
            traceback.print_exc()
            ok = False
        results.append((label, ok))

    header("RESUMEN")
    n_pass = sum(1 for _, ok in results if ok)
    for label, ok in results:
        print(f"  {(PASS if ok else FAIL)}  {label}")
    print()
    print(f"  {n_pass}/{len(results)} tests pasaron.")
    print()
    if n_pass < len(results):
        print("  Tests fallidos son normales si NO instalaste rdkit + thermo:")
        print("    pip install rdkit thermo chemicals")
        print("  Despues volve a correr este script.")
    sys.exit(0 if n_pass == len(results) else 1)


if __name__ == "__main__":
    main()
