"""PR-G1 — Wegstein VECTORIAL reaction-aware sobre reciclos vivos.

haber_rec deslockea el tear S-recycle (modelado con purga fraccional en
V-102) y el solver debe DERIVAR el caudal del reciclo (≈5000 t/a) iterando
de verdad, no congelarlo.  Verifica:
  - el tear elegido es el back-edge S-recycle (no S-mix);
  - Wegstein converge con iteración REAL (history con varios pasos);
  - el balance global cierra (feeds = sinks) y el balance elemental N/H;
  - no aparece un [W-ENERGY-BLOCK] nuevo en el reactor.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import examples_registry as reg
import flowsheet_solver as fsv


def _solve():
    fs = reg.load_example("haber_rec")
    res = fsv.solve(fs)
    return fs, res


def _stream(fs, name):
    return next(s for s in fs.streams.values() if s.name == name)


def test_tear_es_el_backedge_srecycle():
    fs, res = _solve()
    assert len(res.recycle_solutions) == 1, "el loop de haber_rec no fue a Wegstein"
    rs = res.recycle_solutions[0]
    assert rs.tear_stream == "S-recycle", \
        f"tear esperado S-recycle (back-edge), got {rs.tear_stream}"


def test_wegstein_converge_iterando_de_verdad():
    fs, res = _solve()
    rs = res.recycle_solutions[0]
    assert rs.converged, f"Wegstein no convergió: {rs}"
    # iteración REAL: al menos 3 puntos en la trayectoria (guess + pasos),
    # no convergencia trivial en 1 paso.
    assert len(rs.history) >= 3, f"history demasiado corta: {rs.history}"
    # y la masa se MUEVE de verdad entre el guess y el final.
    assert abs(rs.history[-1] - rs.history[0]) > 1000.0, \
        f"el tear no iteró: {rs.history}"


def test_recycle_converge_a_5000():
    fs, res = _solve()
    rec = _stream(fs, "S-recycle")
    assert abs(rec.mass_flow - 5000.0) < 5.0, \
        f"S-recycle debería derivar ≈5000, got {rec.mass_flow}"
    assert res.overall_status == "ok"
    assert res.mass_balance_errors == []


def test_balance_global_y_elemental_cierran():
    fs, _ = _solve()
    feeds = sum(s.mass_flow for s in fs.streams.values()
                if s.src not in fs.blocks and s.dst in fs.blocks)
    sinks = sum(s.mass_flow for s in fs.streams.values()
                if s.dst not in fs.blocks and s.src in fs.blocks)
    assert abs(feeds - sinks) < 1e-6, f"global no cierra: feeds={feeds} sinks={sinks}"
    # balance elemental N y H sobre el reactor R-101 (mass-weighted comp).
    r101 = next(b for b in fs.blocks.values() if b.name == "R-101")
    ins = [s for s in fs.streams.values() if s.dst == r101.id]
    outs = [s for s in fs.streams.values() if s.src == r101.id]
    # fracción másica de N y H por componente del lazo de amoníaco.
    NH = {"nitrogen": (1.0, 0.0), "hydrogen": (0.0, 1.0),
          "ammonia": (0.824, 0.176)}   # (N, H) por kg
    def elems(streams):
        N = H = 0.0
        for s in streams:
            for c, w in (s.composition or {}).items():
                fn, fh = NH.get(c, (0.0, 0.0))
                N += s.mass_flow * w * fn
                H += s.mass_flow * w * fh
        return N, H
    Nin, Hin = elems(ins)
    Nout, Hout = elems(outs)
    # tolerancia relativa 0.5%: el equilibrio resuelve composición numérica
    # (redondeo) y las fracciones N/H del NH3 son aproximadas; el balance
    # de MASA total cierra exacto (arriba) — esto es sanity elemental.
    assert abs(Nin - Nout) / max(Nin, 1.0) < 0.005, \
        f"N no cierra en R-101: {Nin} vs {Nout}"
    assert abs(Hin - Hout) / max(Hin, 1.0) < 0.005, \
        f"H no cierra en R-101: {Hin} vs {Hout}"


def test_no_nuevo_warning_energia_en_reactor():
    fs, res = _solve()
    r101_energy = [w for w in res.awareness_warnings
                   if "R-101" in w and "W-ENERGY-BLOCK" in w]
    assert r101_energy == [], \
        f"el loop no cierra energéticamente: {r101_energy}"
