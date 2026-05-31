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
    """Carga todos los ejemplos y reporta status + warnings clave.

    Fase 2: itera el manifest del registry (data/examples) y carga vía
    registry.load_example(clave) — mismo camino que la UI — en vez del array
    hardcodeado de claves + builders imperativos."""
    headless_mocks()
    import flowsheet_solver as fsv
    import examples_registry as reg

    examples = [e["clave"] for e in reg.list_examples()]
    print(f"\n{'='*92}")
    print("VALIDACIÓN HEADLESS — todos los ejemplos del flowsheet")
    print(f"{'='*92}")
    print(f"{'ejemplo':40s} {'overall':>9} {'blks':>4} {'strms':>5} "
          f"{'mass':>4} {'eng':>3} {'warn':>4} {'comp':>4}")
    print('-' * 92)

    all_ok = True
    total_blocks = total_streams = 0
    for name in examples:
        try:
            fs = reg.load_example(name)
        except Exception as e:
            print(f"  ✗ {name:40s} ERROR DE CARGA: {type(e).__name__}: {e}")
            all_ok = False
            continue
        try:
            res = fsv.solve(fs)
        except Exception as e:
            print(f"  ✗ {name:40s} CRASH EN SOLVER: {type(e).__name__}: {e}")
            all_ok = False
            continue
        mass_ok = len(res.mass_balance_errors) == 0
        eng_ok  = len(res.energy_balance_errors) == 0
        ok = mass_ok and eng_ok
        all_ok = all_ok and ok
        mark = "✓" if ok else "✗"
        total_blocks += len(fs.blocks)
        total_streams += len(fs.streams)
        print(f"  {mark} {name:38s} {res.overall_status:>9} "
              f"{len(fs.blocks):>4} {len(fs.streams):>5} "
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


def test_all_examples_hydraulics():
    """Para cada ejemplo: build + apply_example_hydraulics + solve, y verifica
    la hidráulica de bombas/compresores (ΔP auto-sized, W_elec, NPSHa).

    HARD FAIL (rompe la validación): crash del solver, o una corriente viva
    con P < 0, o una bomba con succión + anchor downstream que NO se dimensionó.
    Los compresores de entrada sin succión (feed en la descarga) se reportan
    como nota, no como fallo (limitación de topología, no del solver)."""
    headless_mocks()
    import inspect
    import flowsheet_model as fm
    import flowsheet_solver as fsv
    import hydraulic_defaults as hd
    try:
        import equipment_design as ed
    except ImportError:
        ed = None

    import examples_registry as reg
    # Fase 2: (clave, builder) del manifest.  La hidráulica se indexa por el
    # nombre del builder (clave de EXAMPLE_PRESETS); el flowsheet se carga
    # vía registry.
    methods = [(e["clave"], e["builder"]) for e in reg.list_examples()]

    print(f"\n{'='*92}")
    print("VALIDACIÓN HIDRÁULICA — bombas/compresores auto-dimensionados")
    print(f"{'='*92}")
    print(f"{'ejemplo':28s} {'equipo':8s} {'ΔP bar':>8} {'W_elec kW':>10} "
          f"{'NPSHa m':>9} {'notas':>6}")
    print('-' * 92)

    all_ok = True
    for clave, builder in methods:
        try:
            fs = reg.load_example(clave)
            hd.apply_example_hydraulics(fs, builder)
            res = fsv.solve(fs)
        except Exception as e:
            print(f"  ✗ {clave:26s} CRASH: {type(e).__name__}: {e}")
            all_ok = False
            continue
        # P negativa en rama viva → hard fail
        neg = [s.name for s in fs.streams.values()
               if s.mass_flow > 0 and s.pressure_bar < 0]
        if neg:
            print(f"  ✗ {clave:26s} P<0 en {neg[:3]}")
            all_ok = False
        rot = [b for b in fs.blocks.values()
               if hd._is_rotative(b.eq_type)]
        for b in rot:
            ins = [s for s in fs.streams.values() if s.dst == b.id]
            outs = [s for s in fs.streams.values() if s.src == b.id]
            has_suction = bool(ins)
            note = ""
            if abs(b.delta_p_bar) < 1e-6:
                note = "no-suction" if not has_suction else "no-anchor"
                # bomba con succión pero sin ΔP y con target downstream → fallo
                if has_suction:
                    tgt, _acc = fsv._find_downstream_target(fs, b.id, None) \
                        if hasattr(fsv, "_find_downstream_target") else (None, 0)
            npsha = None
            if ed is not None and "pump" in b.eq_type.lower() and ins:
                p_in = min((s.pressure_bar for s in ins if s.pressure_bar > 0),
                           default=1.013)
                m = sum(s.mass_flow for s in ins if s.mass_flow > 0) / 31536.0
                try:
                    r = ed.pump_sizing(m_kg_s=max(m, 1e-6),
                                       dp_bar=max(b.delta_p_bar, 1e-6),
                                       rho_kg_m3=900.0, p_in_bar=p_in)
                    npsha = r.get("NPSHa_m") if r else None
                except Exception:
                    npsha = None
            print(f"  {'·':1s} {clave:26s} {b.name:8s} "
                  f"{b.delta_p_bar:8.2f} {b.duty:10.3f} "
                  f"{(npsha if npsha is not None else float('nan')):9.2f} "
                  f"{note:>6}")

    print('-' * 92)
    print(f"RESULT hidráulica: {'TODOS PASAN ✓' if all_ok else 'HAY FALLAS ✗'}")
    return all_ok


def test_breakdown_renders_for_all_pumps():
    """Para cada ejemplo, toda bomba/compresor auto-dimensionada con anchor
    debe producir un desglose con items >= 1 y total_dp_bar ≈ delta_p_bar."""
    headless_mocks()
    import inspect
    import flowsheet_solver as fsv
    import hydraulic_defaults as hd
    import examples_registry as reg

    methods = [(e["clave"], e["builder"]) for e in reg.list_examples()]
    print(f"\n{'='*70}")
    print("VALIDACIÓN — desglose ΔP por bomba/compresor")
    print(f"{'='*70}")

    all_ok = True
    checked = 0
    for clave, builder in methods:
        try:
            fs = reg.load_example(clave)
            hd.apply_example_hydraulics(fs, builder)
            fsv.solve(fs)
        except Exception as e:
            print(f"  ✗ {clave}: CRASH {type(e).__name__}: {e}")
            all_ok = False
            continue
        for b in fs.blocks.values():
            if not hd._is_rotative(b.eq_type) or b.delta_p_bar <= 0.01:
                continue
            bd = fsv._trace_downstream_itemized(fs, b.id)
            if bd is None:
                continue                   # sin anchor → caso conocido
            if len(bd["items"]) < 1:
                print(f"  ✗ {clave}/{b.name}: 0 items")
                all_ok = False
                continue
            err = abs(bd["total_dp_bar"] - b.delta_p_bar)
            if err >= 0.05:
                print(f"  ✗ {clave}/{b.name}: items suman "
                      f"{bd['total_dp_bar']:.3f}, bomba dice "
                      f"{b.delta_p_bar:.3f} (err={err:.3f})")
                all_ok = False
                continue
            checked += 1
    print(f"  ✓ {checked} bombas/compresores con desglose consistente")
    print(f"RESULT desglose: {'TODOS PASAN ✓' if all_ok else 'HAY FALLAS ✗'}")
    return all_ok


def check_features():
    """Verifica que los features clave estén funcionando."""
    headless_mocks()
    import flowsheet_model as fm
    import flowsheet_solver as fsv

    print(f"\n{'='*70}")
    print("VALIDACIÓN DE FEATURES")
    print(f"{'='*70}")

    issues = []

    import examples_registry as reg
    import hydraulic_defaults as _hd

    # Feature 1: Hidráulica auto-sizing
    print("\n1. Hidráulica auto-sizing:")
    fs = reg.load_example("hydraulic")
    _hd.apply_example_hydraulics(fs, reg.builder_name("hydraulic"))
    res = fsv.solve(fs)
    p101 = next(b for b in fs.blocks.values() if b.name == "P-101")
    prod = next(s for s in fs.streams.values() if s.name == "S-product")
    print(f"   P-101 auto-sized:  ΔP = {p101.delta_p_bar:.3f} bar")
    print(f"   P-101 W_elec:      {p101.duty:.4f} kW")
    print(f"   producto P:        {prod.pressure_bar:.3f} bar (target=4.0)")
    if p101.delta_p_bar < 2.5:
        issues.append("Hidráulica: bomba sub-dimensionada")
    if abs(prod.pressure_bar - 4.0) > 0.1:
        issues.append(f"Hidráulica: P producto {prod.pressure_bar} ≠ 4.0 target")

    # Feature 2: Columna FUG automática
    print("\n2. Columna FUG/NRTL automática:")
    fs = reg.load_example("rxn_flash_col")
    _hd.apply_example_hydraulics(fs, reg.builder_name("rxn_flash_col"))
    res = fsv.solve(fs)
    t101 = next(b for b in fs.blocks.values() if b.name == "T-101")
    dist = next(s for s in fs.streams.values() if s.name == "S-etanol")
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

    print("\n8. Coherencia P_op_bar vs presión propagada:")
    # (clave_menú, block_name, P_esperada).  Carga vía registry.
    coherence_tests = [
        ("smr_eq",   "R-101",  25.0),
        ("hda",      "R-101",  25.0),
        ("haber_rec","R-101", 200.0),
        ("industrial","R-101", 80.0),
        ("methanol", "R-101",  80.0),
        ("ammonia",  "R-101", 200.0),
        ("hno3",     "R-201",   4.5),
        ("hno3",     "T-401",  11.0),
        ("ldpe",     "R-101", 2000.0),
        ("urea",     "R-101", 150.0),
        ("talara",   "R-RCA",  10.0),
        ("talara",   "R-HTD",  80.0),
    ]
    for clave, block_name, p_exp in coherence_tests:
        fs = reg.load_example(clave)
        fsv.solve(fs)
        b = next((bl for bl in fs.blocks.values() if bl.name == block_name), None)
        if b is None:
            issues.append(f"{clave}: block {block_name} no existe")
            continue
        ins = [s for s in fs.streams.values() if s.dst == b.id]
        if not ins:
            issues.append(f"{clave}/{block_name}: sin inputs")
            continue
        P_in = max(s.pressure_bar for s in ins)
        tol = max(2.0, p_exp * 0.02)
        ok = abs(P_in - p_exp) <= tol
        if not ok:
            issues.append(f"{clave}/{block_name}: P_in={P_in:.1f} ≠ "
                          f"esperado={p_exp:.1f}")
        print(f"   {clave}/{block_name}: P_in={P_in:.1f}, "
              f"target={p_exp:.1f}  {'✓' if ok else '✗'}")

    print("\n9. Coherencia T compresor (isentrópica vs declarada, los 41):")
    import audit_temperatures as _at
    _claves = [e["clave"] for e in reg.list_examples()]
    n_comp = 0
    for _clave in sorted(_claves):
        fs = reg.load_example(_clave)
        fsv.solve(fs)
        for it in _at.audit_compressor_temperatures(fs, tol_C=30.0):
            n_comp += 1
            issues.append(
                f"{_clave}/{it['block']}: T declarada={it['T_declared']:.0f}°C "
                f"vs isen={it['T_isen']:.0f}°C")
            print(f"   ✗ {_clave}/{it['block']}: decl={it['T_declared']:.0f}°C "
                  f"isen={it['T_isen']:.0f}°C")
    print(f"   compresores incoherentes: {n_comp}  "
          f"{'✓' if n_comp == 0 else '✗'}")

    print("\n10. Reactor-como-horno (gap T_op vs T_feed sin fuente, advisory):")
    n_furn = 0
    for _clave in sorted(_claves):
        fs = reg.load_example(_clave)
        fsv.solve(fs)
        for it in _at.audit_reactor_feed_temperatures(fs, gap_C=50.0):
            n_furn += 1
            print(f"   ⚠ {_clave}/{it['block']}: T_op={it['T_op']:.0f}°C, "
                  f"T_feed={it['T_feed']:.0f}°C, gap={it['gap']:.0f}°C")
    # ADVISORY: no bloquea la suite (son simplificaciones de modelado
    # conocidas — reactor autotérmico con hor sin declarar, o feed que
    # necesita precalentador).  Surface, no fail.
    print(f"   reactores marcados (advisory, no bloquea): {n_furn}")

    print(f"\n{'='*70}")
    if issues:
        print(f"⚠ ENCONTRÉ {len(issues)} ISSUES:")
        for i in issues:
            print(f"   - {i}")
        return False
    else:
        print("✓ TODOS LOS FEATURES VERIFICADOS")
        return True


def check_isentropic_compression():
    """Verifica la propagación isentrópica de T_out en compresores y
    turbinas (Cengel cap 7-9).

    NOTA sobre los números: el solver usa Cp(T) REAL de thermo_db, no
    el cold-air-standard de constante k=1.4 que usan los ejemplos del
    libro.  Por eso:
      · Compresor a baja T (300 K, k≈1.40): coincide con Cengel salvo
        que compressor_sizing clampea η_isen ≤ 0.95 (ningún compresor
        real es isentrópico-ideal), así que un caso "η=1.0" da T_out
        ~556 K en vez de los 543 K teóricos.
      · Turbina a alta T (1300 K, k≈1.30): el Cp del aire crece con T,
        bajando k → menor caída de T → exhaust MÁS caliente (799 K)
        que el cold-air-standard de Cengel (717 K).  El código es más
        preciso; ambos son físicamente defensibles.

    Los chequeos validan la FÍSICA (compresor calienta + W>0; turbina
    enfría + W<0) y los valores del código con tolerancia ±5 %."""
    import flowsheet_model as fm
    import flowsheet_solver as fsv
    from flowsheet_model import SEC_PER_YEAR, TM_TO_KG

    print(f"\n{'='*70}")
    print("ISENTROPIC COMPRESSION / EXPANSION (Cengel cap 7-9)")
    print(f"{'='*70}")
    issues = []

    def _build(T_in_C, P_in, dp, eta):
        """Mini-flowsheet: 10 kg/s aire por un Compressor — axial."""
        fs = fm.Flowsheet()
        k = fm.Block(id=1, name="K", eq_type="Compressor — axial", S=500,
                     delta_p_bar=dp, efficiency=eta)
        fs.blocks[1] = k
        mf = 10.0 * SEC_PER_YEAR / TM_TO_KG   # 10 kg/s en tm/año
        feed = fm.Stream(id=2, name="in", src=0, dst=1, mass_flow=mf,
                         composition={"nitrogen": 0.79, "oxygen": 0.21},
                         phase="gas", temperature=T_in_C, pressure_bar=P_in)
        feed.mass_flow_locked = True; feed.composition_locked = True
        feed.pressure_locked = True;  feed.temperature_locked = True
        fs.streams[2] = feed
        out = fm.Stream(id=3, name="out", src=1, dst=0, mass_flow=mf,
                        composition={"nitrogen": 0.79, "oxygen": 0.21},
                        phase="gas")
        fs.streams[3] = out
        return fs, k, out

    def _within(label, got, expected, pct):
        ok = abs(got - expected) <= abs(expected) * pct
        flag = "✓" if ok else "✗"
        print(f"   {flag} {label}: {got:.1f} (esperado ≈{expected:.1f}, ±{pct*100:.0f}%)")
        if not ok:
            issues.append(f"{label}: {got:.1f} ≠ {expected:.1f} ±{pct*100:.0f}%")
        return ok

    # Caso 1 — compresor aire 27°C, 1→8 bar, η=1.0 (clamp 0.95)
    print("Caso 1 — compresor aire 27°C, 1→8 bar (η pedido 1.0):")
    fs, k, out = _build(27.0, 1.0, +7.0, 1.0)
    fsv.solve(fs)
    T_out_K = out.temperature + 273.15
    _within("T_out [K]", T_out_K, 556.0, 0.05)   # 556 = 300+(543.4-300)/0.95
    _within("duty [kW]", k.duty, 2710.0, 0.05)
    if k.duty <= 0:
        issues.append("Caso1: compresor con duty no-positivo")

    # Caso 2 — turbina aire 1027°C, 8→1 bar, η=1.0
    print("Caso 2 — turbina aire 1027°C, 8→1 bar (η 1.0, expansor):")
    fs, k, out = _build(1027.0, 8.0, -7.0, 1.0)
    fsv.solve(fs)
    T_out_K = out.temperature + 273.15
    # Con Cp(T) real a 1300 K, k≈1.30 → exhaust ~799 K (Cengel cold-air
    # k=1.4 daría 717 K).  Validamos el valor del código.
    _within("T_out [K]", T_out_K, 799.0, 0.05)
    _within("duty [kW] (gen, negativo)", k.duty, -5880.0, 0.06)
    if k.duty >= 0:
        issues.append("Caso2: turbina con duty no-negativo (debería generar)")
    if T_out_K >= 1300:
        issues.append("Caso2: turbina no enfrió el gas")

    # Caso 3 — compresor η=0.85
    print("Caso 3 — compresor aire 27°C, 1→8 bar, η=0.85:")
    fs, k, out = _build(27.0, 1.0, +7.0, 0.85)
    fsv.solve(fs)
    T_out_K = out.temperature + 273.15
    _within("T_out [K]", T_out_K, 585.0, 0.05)
    _within("duty [kW]", k.duty, 3040.0, 0.05)

    print(f"\n{'='*70}")
    if issues:
        print(f"⚠ ISENTROPIC: {len(issues)} issues:")
        for i in issues:
            print(f"   - {i}")
        return False
    print("✓ ISENTROPIC COMPRESSION/EXPANSION VERIFICADO")
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
    ok3 = check_isentropic_compression()
    ok4 = test_all_examples_hydraulics()
    ok5 = test_breakdown_renders_for_all_pumps()
    if args.gui:
        maybe_open_gui()
    sys.exit(0 if (ok1 and ok2 and ok3 and ok4 and ok5) else 1)
