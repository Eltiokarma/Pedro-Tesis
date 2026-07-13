"""Batch — química real conectada a placeholders con base curada.

Historia en dos tandas:

  · T29a/b: chloralkali_hcl/R-201 → R028 (H2 + Cl2 → 2 HCl), conv 0.999.
  · Sesión 3 (2026-07): el triage de conectabilidad (todas las especies con
    MW en reactions_db) marcó 4 reactores más como tratables y se conectaron
    con su cadena downstream re-propagada por-diferencia:
      · acetic/R-101  → R026 (metanol + CO → ácido acético)
      · beer/R-101    → R007 (glucosa → 2 etanol + 2 CO2)
      · bread/R-101   → R007 (fermentación de la masa)
      · sulfuric/R-101 → R006 (2 SO2 + O2 → 2 SO3)

Los otros 4 con base curada se DIFIEREN (siguen placeholder honesto, ver
docs/inventario_hardcode.md §6.7 y docs/AUDITORIA_HARDCODEO_2026.md):
  · cement (R029): mismatch de especie (R029 produce quicklime, no clinker).
  · ldpe (R027), soap (R030), urea (R031): pseudo-componentes sin MW → la
    reacción no dispara en modo stoich.
"""
import examples_registry as reg
import flowsheet_solver as fsv

MW = {"chlorine": 70.90, "hydrogen": 2.016, "hydrogen_chloride": 36.46}


def _reactor_io(clave, blk):
    fs = reg.load_example(clave)
    res = fsv.solve(fs)
    b = next(b for b in fs.blocks.values() if b.name == blk)
    ins = [s for s in fs.streams.values() if s.dst == b.id]
    outs = [s for s in fs.streams.values() if s.src == b.id]
    return fs, res, b, ins, outs


def _moles_delta(ins, outs):
    """Δmol por especie (out − in) usando MW."""
    m = {}
    for s in ins:
        for k, v in (s.composition or {}).items():
            m[k] = m.get(k, 0.0) - v * s.mass_flow
    for s in outs:
        for k, v in (s.composition or {}).items():
            m[k] = m.get(k, 0.0) + v * s.mass_flow
    return {k: m[k] / MW[k] for k in m if k in MW}


def _no_placeholder(res, blk):
    return not any("PLACEHOLDER" in w and blk in w for w in res.awareness_warnings)


# ── conectado: chloralkali H2 + Cl2 → 2 HCl ─────────────────────────────
def test_chloralkali_r028_conectado():
    fs, res, b, ins, outs = _reactor_io("chloralkali_hcl", "R-201")
    assert b.reactions == ["R028"] and b.reactor_mode == "stoich"
    assert _no_placeholder(res, "R-201")
    assert len(res.mass_balance_errors) == 0
    d = _moles_delta(ins, outs)
    # 1 H2 + 1 Cl2 → 2 HCl
    assert abs(d["hydrogen_chloride"] / (-d["hydrogen"]) - 2.0) < 0.05
    assert abs(d["hydrogen"] - d["chlorine"]) / abs(d["hydrogen"]) < 0.05
    assert b.duty < 0          # R028 fuertemente exotérmica (ΔH=−184.6)


# ── conectados sesión 3: acetic/beer/bread/sulfuric ─────────────────────
def test_conectados_sesion3_corren_quimica_real():
    """Los 4 reactores conectados en la sesión 3 declaran su reacción curada,
    corren en modo stoich, ya no disparan W-PLACEHOLDER y su ejemplo cierra
    el balance de masa."""
    for clave, blk, rid in [("acetic", "R-101", "R026"),
                            ("beer", "R-101", "R007"),
                            ("bread", "R-101", "R007"),
                            ("sulfuric", "R-101", "R006")]:
        fs, res, b, ins, outs = _reactor_io(clave, blk)
        assert b.reactions == [rid], \
            f"{clave}/{blk} debe declarar {rid}, tiene {b.reactions}"
        assert b.reactor_mode == "stoich"
        assert _no_placeholder(res, blk), \
            f"{clave}/{blk} ya no debería disparar W-PLACEHOLDER (conectado)"
        assert len(res.mass_balance_errors) == 0, \
            f"{clave}: el balance de masa debe seguir cerrando"


def test_conectados_calor_de_reaccion_calculado():
    """El calor de reacción de los conectados lo computa el solver (no
    heat_of_reaction hardcodeado): los exotérmicos salen con duty < 0."""
    for clave, blk in [("acetic", "R-101"), ("sulfuric", "R-101")]:
        fs0 = reg.load_example(clave)          # declarado, PRE-solve
        b0 = next(b for b in fs0.blocks.values() if b.name == blk)
        assert b0.heat_of_reaction == 0, \
            f"{clave}/{blk}: heat_of_reaction declarado debe ser 0 (calculado)"
        fs, res, b, ins, outs = _reactor_io(clave, blk)
        assert b.duty < 0, \
            f"{clave}/{blk}: la reacción es exotérmica, duty debe ser < 0"


# ── diferidos: siguen siendo placeholder honesto ────────────────────────
def test_diferidos_siguen_placeholder():
    for clave, blk in [("cement", "R-101"), ("ldpe", "R-101"),
                       ("soap", "R-101"), ("urea", "R-101")]:
        res = fsv.solve(reg.load_example(clave))
        assert any("PLACEHOLDER" in w and blk in w
                   for w in res.awareness_warnings), \
            f"{clave}/{blk} debe seguir disparando W-PLACEHOLDER (diferido)"
