"""TF §3 — fracciones de splitter DENTRO de la iteración de masa (tearing).

Antes, `_solve_mass_iteration` sólo deducía bloques con UNA incógnita: un
splitter con purga y reciclo desconocidos se atascaba, y el Wegstein del
lazo (industrial) leía siempre el valor semilla del tear (f(x)=x vía dos
ecos: la succión del compresor deducida BACKWARD desde el tear inyectado, y
el tear re-deducido en su mixer DESTINO desde internos stale).  El fix tiene
tres piezas:

  · la ecuación del splitter (out_i = frac_i·Σin) vive también en
    `_solve_mass_iteration` (misma semántica/mapeo que solve_splitters);
  · S2-B en el camino MONO de Wegstein + contrato refinado: el tear se
    PRODUCE en su bloque fuente, nunca se deduce en su destino;
  · S2-D: dentro del SCC activo no hay deducción backward (anti-causal
    respecto al lazo → eco del guess);
  · UPDATE-closure: un bloque resuelto pero desbalanceado con UNA salida
    libre se re-deriva (las cadenas pass-through aguas abajo de un lazo
    convergido quedaban stale con masas de iteraciones intermedias).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import examples_registry as reg
import flowsheet_solver as fsv
from flowsheet_model import Flowsheet, Block, Stream


# ── unidad: el splitter distribuye con ≥2 incógnitas ────────────────────
def test_splitter_distribuye_en_mass_iteration():
    fs = Flowsheet()
    b = fs.new_id()
    fs.blocks[b] = Block(id=b, name="SPL", eq_type="Splitter — flow divider",
                         S=1.0, x=0, y=0, splitter_active=True,
                         splitter_fractions=[0.25, 0.75])
    si = Stream(id=fs.new_id(), name="in", src=-1, dst=b, mass_flow=1000.0)
    si.mass_flow_locked = True
    fs.streams[si.id] = si
    o1 = Stream(id=fs.new_id(), name="o1", src=b, dst=-1, mass_flow=0.0)
    fs.streams[o1.id] = o1
    o2 = Stream(id=fs.new_id(), name="o2", src=b, dst=-1, mass_flow=0.0)
    fs.streams[o2.id] = o2

    fsv._solve_mass_iteration(fs)
    assert abs(o1.mass_flow - 250.0) < 1e-6, \
        "con 2 incógnitas la regla de bloque no dispara — el splitter sí"
    assert abs(o2.mass_flow - 750.0) < 1e-6


def test_splitter_respeta_locks():
    """Una salida lockeada del splitter no se pisa.  Si el lock contradice
    la fracción nominal, la CONSERVACIÓN DE MASA gana: la salida libre toma
    el remanente exacto (Σin − lock) vía update-closure, no su fracción."""
    fs = Flowsheet()
    b = fs.new_id()
    fs.blocks[b] = Block(id=b, name="SPL", eq_type="Splitter — flow divider",
                         S=1.0, x=0, y=0, splitter_active=True,
                         splitter_fractions=[0.1, 0.9])
    si = Stream(id=fs.new_id(), name="in", src=-1, dst=b, mass_flow=1000.0)
    si.mass_flow_locked = True
    fs.streams[si.id] = si
    o1 = Stream(id=fs.new_id(), name="o1", src=b, dst=-1, mass_flow=120.0)
    o1.mass_flow_locked = True
    fs.streams[o1.id] = o1
    o2 = Stream(id=fs.new_id(), name="o2", src=b, dst=-1, mass_flow=0.0)
    fs.streams[o2.id] = o2

    fsv._solve_mass_iteration(fs)
    assert o1.mass_flow == 120.0
    assert abs(o2.mass_flow - 880.0) < 1e-6   # 1000 − 120 (masa, no 0.9·Σin)


# ── integración: el lazo de industrial converge VIVO (sin ancla) ────────
def test_industrial_lazo_vivo_converge():
    """El JSON de industrial ya NO ancla el tear: el reciclo con purga
    fraccional (V-203, 9.11%) converge por Wegstein al punto fijo real
    (~278 000 t/a) con balance limpio.  Antes del fix, f(x)=x devolvía la
    semilla (10 000) con convergencia falsa en 1 iteración."""
    fs = reg.load_example("industrial")
    srec = next(s for s in fs.streams.values() if s.name == "S-recycle")
    assert not srec.mass_flow_locked, \
        "el tear de industrial debe estar VIVO (sin ancla sintética)"
    res = fsv.solve(fs)
    assert res.mass_balance_errors == []
    rss = [rs for rs in res.recycle_solutions
           if rs.tear_stream == "S-recycle"]
    assert rss and rss[0].converged
    assert rss[0].iterations > 1, \
        "convergencia en 1 iteración = el eco f(x)=x (RC2), no convergencia"
    assert 250_000 < srec.mass_flow < 310_000, \
        f"punto fijo fuera de rango: {srec.mass_flow}"
    # aguas abajo SIN staleness: el producto sigue al lazo convergido
    meoh = next(s for s in fs.streams.values() if s.name == "S-MeOH")
    vap = next(s for s in fs.streams.values() if s.name == "S-vap")
    assert abs(meoh.mass_flow - vap.mass_flow) < 1.0, \
        "cadena pass-through stale aguas abajo del lazo (update-closure)"
