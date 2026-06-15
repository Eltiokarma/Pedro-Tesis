"""Batch — química real conectada a placeholders con base curada.

De los 9 placeholders con base curada en reactions_db, **1 se conectó** a su
química real (patrón T29a/b): el motor ahora CALCULA la composición de salida
por balance estequiométrico en vez de leerla hardcodeada.

  · chloralkali_hcl/R-201 → R028 (H2 + Cl2 → 2 HCl), conv 0.999

Los otros 8 se DIFIEREN (siguen placeholder honesto, ver
docs/inventario_hardcode.md §6.7):
  · acetic/R-101 (R026), beer/R-101 (R007): el reactor conecta, pero alimenta
    un separador PASIVO aguas abajo (V-101 / separador de beer) cuyo split
    hardcodeado el motor no calcula → al computar la salida del reactor, el
    detector marca esos locks como redundantes (cascada al proyecto de
    separación activa).
  · bread (R007): el placeholder es no-op; conectar mete CO2/etanol que el
    horno H-101 no ventea (cascadea a otro bloque).
  · sulfuric (R006): conectar dispara un [W-ENERGY-BLOCK] nuevo.
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


# ── diferidos: siguen siendo placeholder honesto ────────────────────────
def test_diferidos_siguen_placeholder():
    for clave, blk in [("acetic", "R-101"), ("beer", "R-101"),
                       ("bread", "R-101"), ("sulfuric", "R-101"),
                       ("cement", "R-101"), ("ldpe", "R-101"),
                       ("soap", "R-101"), ("urea", "R-101")]:
        res = fsv.solve(reg.load_example(clave))
        assert any("PLACEHOLDER" in w and blk in w
                   for w in res.awareness_warnings), \
            f"{clave}/{blk} debe seguir disparando W-PLACEHOLDER (diferido)"
