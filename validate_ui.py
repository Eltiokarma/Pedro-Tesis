"""
validate_ui.py — Validación exhaustiva del flowsheet headless.

Carga TODOS los ejemplos, ejecuta solve, y verifica balance + status
+ que los nuevos features (P, columnas auto, flashes auto, splitters,
bombas, etc.) no rompen nada.

USO:
    python validate_ui.py

Salida: tabla resumen + lista de issues encontrados.

Cuando el user tiene PySide6 real, también es posible:
    python validate_ui.py --gui
para arrancar la app con un ejemplo cargado.
"""

import sys
import argparse


def headless_mocks():
    """Setup mocks para correr sin PySide6 instalado."""
    from unittest.mock import MagicMock
    for m in ['PySide6', 'PySide6.QtCore', 'PySide6.QtGui',
               'PySide6.QtWidgets', 'PySide6.QtSvg',
               'tkinter', 'tkinter.ttk', 'tkinter.messagebox',
               'tkinter.filedialog', 'tkinter.simpledialog',
               'tkinter.font']:
        if m not in sys.modules:
            sys.modules[m] = MagicMock()


def run_all_examples():
    """Carga todos los ejemplos y reporta status + warnings clave."""
    headless_mocks()
    import flowsheet_model as fm
    import flowsheet_solver as fsv
    import flowsheet_ui as fu

    class _FakeEditor:
        def __init__(self):
            self.fs = fm.Flowsheet()
            self.labor_workers = 0
        _add_example_block  = fu.FlowsheetEditor._add_example_block
        _add_example_stream = fu.FlowsheetEditor._add_example_stream
        _add_example_extra  = fu.FlowsheetEditor._add_example_extra
        _set_example_labor  = fu.FlowsheetEditor._set_example_labor
        _set_block_duty     = fu.FlowsheetEditor._set_block_duty

    examples = [
        '_example_hda', '_example_methanol', '_example_distillation',
        '_example_ammonia', '_example_ethanol', '_example_biodiesel',
        '_example_crude_distillation', '_example_hda_full',
        '_example_gas_sweetening', '_example_sugar_mill',
        '_example_smr_equilibrium', '_example_ethane_cracker_pfr',
        '_example_haber_recycle', '_example_distillation_ethanol_water',
        '_example_reactor_flash_column', '_example_hydraulic_plant',
        '_example_industrial_complete',
        '_example_quimpac_chloralkali',
        '_example_hno3_ostwald',
        '_example_talara_refinery',
        # ── Catálogo educativo Lote 1 (alimentaria simple) ──
        '_example_pasteurizer',
        '_example_pineapple_juice',
        '_example_potato_chips',
        # ── Catálogo educativo Lote 2 (bioproceso + química gratis) ──
        '_example_beer_brewing',
        '_example_sulfuric_acid',
        # ── Catálogo educativo Lote 3 (química fina + polímeros) ──
        '_example_acetic_acid',
        '_example_polyethylene',
        # ── Catálogo educativo Lote 4a (inorgánica + materiales) ──
        '_example_chloralkali_hcl',
        '_example_cement',
        '_example_glass',
        # ── Catálogo educativo Lote 4b (saponificación + urea) ──
        '_example_soap',
        '_example_urea',
    ]
    print(f"\n{'='*92}")
    print("VALIDACIÓN HEADLESS — todos los ejemplos del flowsheet")
    print(f"{'='*92}")
    print(f"{'ejemplo':40s} {'overall':>9} {'blks':>4} {'strms':>5} "
          f"{'mass':>4} {'eng':>3} {'warn':>4} {'comp':>4}")
    print('-' * 92)

    all_ok = True
    total_blocks = total_streams = 0
    for name in examples:
        fake = _FakeEditor()
        try:
            getattr(fu.FlowsheetEditor, name)(fake)
        except AttributeError as e:
            print(f"  ✗ {name:40s} ATRIBUTO FALTANTE: {e}")
            all_ok = False
            continue
        except Exception as e:
            print(f"  ✗ {name:40s} ERROR EN BUILDER: {type(e).__name__}: {e}")
            all_ok = False
            continue
        try:
            res = fsv.solve(fake.fs)
        except Exception as e:
            print(f"  ✗ {name:40s} CRASH EN SOLVER: {type(e).__name__}: {e}")
            all_ok = False
            continue
        mass_ok = len(res.mass_balance_errors) == 0
        eng_ok  = len(res.energy_balance_errors) == 0
        ok = mass_ok and eng_ok
        all_ok = all_ok and ok
        mark = "✓" if ok else "✗"
        total_blocks += len(fake.fs.blocks)
        total_streams += len(fake.fs.streams)
        print(f"  {mark} {name:38s} {res.overall_status:>9} "
              f"{len(fake.fs.blocks):>4} {len(fake.fs.streams):>5} "
              f"{len(res.mass_balance_errors):>4} "
              f"{len(res.energy_balance_errors):>3} "
              f"{len(res.energy_warnings):>4} "
              f"{len(res.component_warnings):>4}")
        if not ok:
            for e in res.mass_balance_errors[:2]:
                print(f"      M: {e[:80]}")
            for e in res.energy_balance_errors[:2]:
                print(f"      E: {e[:80]}")

    print('-' * 92)
    print(f"TOTAL: {len(examples)} ejemplos, {total_blocks} bloques, "
          f"{total_streams} streams")
    print(f"RESULT: {'TODOS PASAN ✓' if all_ok else 'HAY FALLAS ✗'}")
    return all_ok


def check_features():
    """Verifica que los features clave estén funcionando."""
    headless_mocks()
    import flowsheet_model as fm
    import flowsheet_solver as fsv
    import flowsheet_ui as fu

    print(f"\n{'='*70}")
    print("VALIDACIÓN DE FEATURES")
    print(f"{'='*70}")

    issues = []

    # Feature 1: Hidráulica auto-sizing
    print("\n1. Hidráulica auto-sizing:")
    class _FE:
        def __init__(self): self.fs = fm.Flowsheet(); self.labor_workers = 0
        _add_example_block = fu.FlowsheetEditor._add_example_block
        _add_example_stream = fu.FlowsheetEditor._add_example_stream
        _add_example_extra = fu.FlowsheetEditor._add_example_extra
        _set_example_labor = fu.FlowsheetEditor._set_example_labor
        _set_block_duty    = fu.FlowsheetEditor._set_block_duty
    fake = _FE()
    fu.FlowsheetEditor._example_hydraulic_plant(fake)
    res = fsv.solve(fake.fs)
    p101 = next(b for b in fake.fs.blocks.values() if b.name == "P-101")
    prod = next(s for s in fake.fs.streams.values() if s.name == "S-product")
    print(f"   P-101 auto-sized:  ΔP = {p101.delta_p_bar:.3f} bar")
    print(f"   P-101 W_elec:      {p101.duty:.4f} kW")
    print(f"   producto P:        {prod.pressure_bar:.3f} bar (target=4.0)")
    if p101.delta_p_bar < 2.5:
        issues.append("Hidráulica: bomba sub-dimensionada")
    if abs(prod.pressure_bar - 4.0) > 0.1:
        issues.append(f"Hidráulica: P producto {prod.pressure_bar} ≠ 4.0 target")

    # Feature 2: Columna FUG automática
    print("\n2. Columna FUG/NRTL automática:")
    fake = _FE()
    fu.FlowsheetEditor._example_reactor_flash_column(fake)
    res = fsv.solve(fake.fs)
    t101 = next(b for b in fake.fs.blocks.values() if b.name == "T-101")
    dist = next(s for s in fake.fs.streams.values() if s.name == "S-etanol")
    if dist.composition:
        eth_pct = dist.composition.get("ethanol", 0) * 100
        print(f"   T-101 N etapas: {getattr(t101, '_column_N', 0):.1f}")
        print(f"   T-101 R:        {getattr(t101, '_column_R', 0):.2f}")
        print(f"   Etanol en dist: {eth_pct:.1f}%")
        if eth_pct < 30:
            issues.append("Columna: pureza distillate sospechosamente baja")
    else:
        issues.append("Columna: distillate sin composición calculada")

    # Feature 3: NRTL azeotropo
    print("\n3. NRTL detección de azeotropo:")
    try:
        import nrtl
        az = nrtl.find_azeotrope(['ethanol','water'], 1.013)
        if az:
            x = az['x_az']; T = az['T_az_K'] - 273.15
            print(f"   eth-water azeo: x={x:.3f}, T={T:.1f}°C "
                  f"(lit: 0.894, 78.15)")
            if abs(x - 0.894) > 0.05:
                issues.append(f"NRTL: azeo eth-water mal predicho x={x:.3f}")
        else:
            issues.append("NRTL: no detectó azeo eth-water")
    except Exception as e:
        issues.append(f"NRTL: {e}")

    # Feature 4: Pressure drop básico
    print("\n4. Pressure drop Darcy-Weisbach:")
    try:
        import pressure_drop as pd
        res = pd.pipe_pressure_drop(5.0, 997, 8.9e-4, 0.0525, 100.0)
        print(f"   Caso clásico Perry: ΔP={res['delta_P_bar']:.3f} bar")
        if abs(res['delta_P_bar'] - 1.07) > 0.1:
            issues.append(f"ΔP: Perry case off ({res['delta_P_bar']:.2f})")
    except Exception as e:
        issues.append(f"pressure_drop: {e}")

    # Feature 5: Wang-Henke
    print("\n5. Wang-Henke standalone:")
    try:
        import distillation_wanghenke as wh
        res = wh.wang_henke(['methanol','water'], [0.5, 0.5], 1.0, 345.0,
                              1.013, 15, 8, 0.50, 1.5)
        if res:
            top_meoh = res['x_profile'][0][0]
            print(f"   MeOH/water 15 etapas: x_top(MeOH)={top_meoh:.3f}")
            if top_meoh < 0.85:
                issues.append(f"WH: MeOH/water tope bajo ({top_meoh:.2f})")
        else:
            issues.append("WH: no devolvió resultado")
    except Exception as e:
        issues.append(f"WH: {e}")

    # Feature 6: Equipment design
    print("\n6. Dimensionamiento de equipos:")
    try:
        import equipment_design as ed
        res = ed.pump_sizing(5.0, 5.0, 997, 0.75, 0.95, 298, 0.03, 1.013)
        print(f"   Pump 5kg/s @ 5 bar: head={res['head_m']:.1f}m, "
              f"W_elec={res['W_elec_kW']:.2f} kW")
        if abs(res['W_elec_kW'] - 3.52) > 0.5:
            issues.append(f"pump_sizing: W_elec off ({res['W_elec_kW']:.2f})")
    except Exception as e:
        issues.append(f"equipment_design: {e}")

    # Feature 7: Splitter, Flash, Column todos auto
    print("\n7. Unit ops automáticos (sin declarar outputs):")
    # Splitter
    fs = fm.Flowsheet()
    F = fs.new_id(); fs.blocks[F] = fm.Block(id=F, name='F', eq_type='Mixer', S=1)
    S = fs.new_id(); fs.blocks[S] = fm.Block(id=S, name='SP', eq_type='Mixer', S=1,
                                                splitter_active=True,
                                                splitter_fractions=[0.7, 0.3])
    A = fs.new_id(); fs.blocks[A] = fm.Block(id=A, name='A', eq_type='Mixer', S=1)
    B = fs.new_id(); fs.blocks[B] = fm.Block(id=B, name='B', eq_type='Mixer', S=1)
    sid = fs.new_id(); fs.streams[sid] = fm.Stream(id=sid, name='in', src=F, dst=S,
        mass_flow=1000, mass_flow_locked=True,
        composition={'water':0.6, 'ethanol':0.4}, composition_locked=True)
    fs.streams[fs.new_id()] = fm.Stream(id=fs._next_id-1+1, name='main', src=S, dst=A)
    fs.streams[fs.new_id()] = fm.Stream(id=fs._next_id-1+1, name='bypass', src=S, dst=B)
    fsv.solve(fs)
    main = next(s for s in fs.streams.values() if s.name == 'main')
    print(f"   Splitter 70/30: main mass={main.mass_flow:.0f} "
          f"(esperado 700)")
    if abs(main.mass_flow - 700) > 10:
        issues.append(f"Splitter: mass main = {main.mass_flow:.0f} ≠ 700")

    print(f"\n{'='*70}")
    if issues:
        print(f"⚠ ENCONTRÉ {len(issues)} ISSUES:")
        for i in issues:
            print(f"   - {i}")
        return False
    else:
        print("✓ TODOS LOS FEATURES VERIFICADOS")
        return True


def maybe_open_gui():
    """Si PySide6 está disponible, intenta arrancar la app con
    el ejemplo hydraulic_plant cargado."""
    try:
        import PySide6
        print(f"\nPySide6 disponible ({PySide6.__version__}) — arrancando GUI…")
        from PySide6.QtWidgets import QApplication
        import flowsheet_qt
        app = QApplication.instance() or QApplication([])
        win = flowsheet_qt.EditorMainWindow()
        win.action_load_example("hydraulic")
        win.show()
        return app.exec()
    except ImportError:
        print("\n(PySide6 no disponible — saltando GUI)")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gui", action="store_true",
                          help="Abrir GUI (requiere PySide6)")
    args = parser.parse_args()

    ok1 = run_all_examples()
    ok2 = check_features()
    if args.gui:
        maybe_open_gui()
    sys.exit(0 if (ok1 and ok2) else 1)
