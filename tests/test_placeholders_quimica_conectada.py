"""Active chemical reactions replace former catalogue placeholders."""
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
def test_diferidos_ahora_tienen_quimica_activa():
    for clave, blk in [("cement", "R-101"), ("ldpe", "R-101"),
                       ("soap", "R-101"), ("urea", "R-101")]:
        fs = reg.load_example(clave)
        reactor = next(b for b in fs.blocks.values() if b.name == blk)
        assert reactor.reactor_mode == "stoich"
        assert reactor.reactions or reactor.custom_reactions
        assert not any("PLACEHOLDER" in rid for rid in reactor.reactions)
        res = fsv.solve(fs)
        assert res.success, (clave, res.mass_balance_errors, res.energy_balance_errors)
        assert _no_placeholder(res, blk)
