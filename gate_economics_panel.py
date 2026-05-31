"""
gate_economics_panel.py — GATES del panel económico in-process.

  1. AISLAMIENTO: economics_panel no IMPORTA ana_qt/montecarlo/flujoflujoclass.
  2. EQUIVALENCIA: para ejemplos (recycle + economía rica), los números que
     el panel renderiza == simulate(run_economics=True) directo == ruta
     GUI/Save de referencia (compute_turton_costing).  NPV/IRR exactos.
  3. SMOKE Qt: el panel se instancia, calcula y renderiza sin crashear
     (QApplication offscreen).

USO:  QT_QPA_PLATFORM=offscreen python gate_economics_panel.py ; echo $?
"""
import os
import re
import sys

CLAVES = ["hda", "industrial", "methanol"]   # recycle + ricas en economía
_TOL = 1e-6


def gate_isolation():
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "economics_panel.py"), encoding="utf-8").read()
    bad = []
    for line in src.splitlines():
        s = line.strip()
        if s.startswith(("import ", "from ")) and re.search(
                r"\b(ana_qt|montecarlo|flujoflujoclass)\b", s):
            bad.append(s)
    ok = not bad
    print(f"  {'✓' if ok else '✗'} Gate 1 (aislamiento): economics_panel sin "
          f"imports de ana_qt/montecarlo/flujoflujoclass")
    for b in bad:
        print(f"        ✗ {b}")
    return ok


def gate_equivalence_and_smoke():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import pandas as pd
    from PySide6.QtWidgets import QApplication
    import examples_registry as reg
    import flowsheet_solver as fsv
    import flowsheet_export as fexp
    import simulate_engine as se
    from economics_panel import EconomicsPanel

    app = QApplication.instance() or QApplication([])
    fails = []
    for clave in CLAVES:
        fs = reg.load_example(clave)
        panel = EconomicsPanel(fs)
        panel._run()                       # calcula in-process
        out = panel.last_result
        if out is None:
            fails.append((clave, "panel.last_result is None")); continue
        econ = out.get("economics", {})
        npv_panel, irr_panel = econ.get("NPV_usd"), econ.get("IRR_pct")

        # (a) idéntico a simulate() directo con los MISMOS inputs del panel
        out2 = se.simulate(fs.to_dict(), run_economics=True,
                           econ_inputs=panel.collect_econ_inputs())
        npv_sim = out2["economics"]["NPV_usd"]
        if abs((npv_panel or 0) - (npv_sim or 0)) > _TOL:
            fails.append((clave, f"panel NPV={npv_panel} != simulate {npv_sim}"))

        # (b) idéntico a ruta GUI/Save (compute_turton_costing, ISBL desde bloques)
        fs2 = reg.load_example(clave); fsv.solve(fs2)
        feeds=[s for s in fs2.streams.values() if s.role=="feed"]
        products=[s for s in fs2.streams.values() if s.role=="product"]
        rows=fexp._collect_pfd_opex_rows(fs2, feeds, products)
        dfv=(pd.DataFrame(rows) if rows
             else pd.DataFrame(columns=["stream","flowrate","price usd/units"]))
        dff=pd.DataFrame([{"Concept":"Labor","Value":fexp._resolve_labor_usd(fs2)}])
        ct=fexp.compute_turton_costing(fs2, dfv, dff, fci_musd=None)
        npv_ref, irr_ref = ct["profit"]["NPV"], ct["profit"]["IRR %"]
        if abs((npv_panel or 0) - (npv_ref or 0)) > _TOL:
            fails.append((clave, f"panel NPV={npv_panel} != ruta Save {npv_ref}"))
        if isinstance(irr_panel,(int,float)) and isinstance(irr_ref,(int,float)):
            if abs(irr_panel - irr_ref) > _TOL:
                fails.append((clave, f"panel IRR={irr_panel} != Save {irr_ref}"))

        # (c) smoke render: el texto muestra algo y status no quedó en error
        txt = panel.txt_results.toPlainText()
        if "NPV" not in txt:
            fails.append((clave, "render sin 'NPV' en el texto"))

        # (d) MACRS: panel == simulate(macrs).  Seteamos el combo a MACRS 7.
        panel.combo_dep.setCurrentIndex(panel.combo_dep.findText("MACRS 7 años"))
        panel._run()
        npv_macrs_panel = panel.last_result["economics"]["NPV_usd"]
        out_m = se.simulate(fs.to_dict(), run_economics=True,
                            econ_inputs=panel.collect_econ_inputs())
        npv_macrs_sim = out_m["economics"]["NPV_usd"]
        if abs((npv_macrs_panel or 0) - (npv_macrs_sim or 0)) > _TOL:
            fails.append((clave, f"MACRS panel NPV={npv_macrs_panel} != "
                                 f"simulate {npv_macrs_sim}"))
        # MACRS7 debe diferir del lineal (sanity: el método sí se aplica)
        if abs((npv_macrs_panel or 0) - (npv_panel or 0)) < 1.0:
            fails.append((clave, "MACRS7 NPV == lineal (método no aplicado?)"))
        panel.combo_dep.setCurrentIndex(panel.combo_dep.findText("Lineal"))
        print(f"     · {clave}: lineal NPV={npv_panel:,.0f}  "
              f"MACRS7 NPV={npv_macrs_panel:,.0f}  ✓render")

    ok = not fails
    print(f"  {'✓' if ok else '✗'} Gate 2/3 (equivalencia+smoke Qt): "
          f"{len(CLAVES)-len({c for c,_ in fails})}/{len(CLAVES)} ejemplos")
    for c,m in fails[:10]:
        print(f"        ✗ {c}: {m}")
    return ok


def main():
    print("="*70); print("GATES — panel económico in-process"); print("="*70)
    g1 = gate_isolation()
    g2 = gate_equivalence_and_smoke()
    print("="*70)
    if g1 and g2:
        print("✓ GATES DEL PANEL VERDES."); return 0
    print("✗ HAY GATES ROJOS."); return 1


if __name__ == "__main__":
    sys.exit(main())
