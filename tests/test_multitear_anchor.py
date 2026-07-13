"""ANCLA multi-reciclo — flowsheet sintético con DOS reciclos ACOPLADOS.

haber_rec (mono-reciclo) NO protege contra regresiones del motor multi-tear.
Este caso mínimo SÍ: dos reciclos independientes que comparten el tramo
M1→X1 (acoplados, un solo SCC), con estado estacionario calculable A MANO.

Topología
---------
        Feed(100) ┐
            R1 ───┤
            R2 ───┴─> [M1 mixer] --S-a--> [X1 split] --S-fwd--> [X2 split] --Prod-->
                                              │                     │
                                              └──── R1 ─────────────┤  (a M1)
                                                    R2 ─────────────┘  (a M1)

Splits (constantes):  X1 = [S-fwd 0.5, R1 0.5] ;  X2 = [Prod 0.5, R2 0.5]

Circuit rank del SCC {M1,X1,X2}: E_int=4, V=3 → 4−3+1 = 2 reciclos
independientes → requiere 2 tears.  El Wegstein mono-tear actual NO lo
resuelve (colapsa a 0); por eso este test es xfail hasta que aterrice el
motor multi-tear.

Balance de masa cerrado A MANO (exacto)
---------------------------------------
Sea T = caudal de S-a (salida de M1).  Con a1=a2=0.5:
  R1 = 0.5·T
  S-fwd = 0.5·T
  R2 = 0.5·S-fwd = 0.25·T
  Prod = 0.5·S-fwd = 0.25·T
  Balance M1:  T = Feed + R1 + R2 = 100 + 0.5T + 0.25T  →  0.25T = 100  →  T = 400
Por lo tanto:
  S-a = 400 · R1 = 200 · S-fwd = 200 · R2 = 100 · Prod = 100
Cierre global:  entra Feed=100, sale Prod=100  ✓  (y cada bloque balancea).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from flowsheet_model import Flowsheet, Block, Stream
from flowsheet_solver import solve


# Estado estacionario exacto (derivado a mano arriba).
EXPECTED_SS = {
    "Feed": 100.0,
    "S-a": 400.0,
    "S-fwd": 200.0,
    "R1": 200.0,
    "R2": 100.0,
    "Prod": 100.0,
}


def build_dual_recycle_fs():
    """Construye el flowsheet sintético de dos reciclos acoplados.

    Reutilizable por el futuro motor multi-tear como caso de validación.
    """
    fs = Flowsheet()
    M1 = fs.new_id()
    fs.blocks[M1] = Block(id=M1, name="M1", eq_type="Mixer — static",
                          S=1.0, x=0, y=0)
    X1 = fs.new_id()
    fs.blocks[X1] = Block(id=X1, name="X1",
                          eq_type="Splitter — flow divider", S=1.0, x=200, y=0)
    X2 = fs.new_id()
    fs.blocks[X2] = Block(id=X2, name="X2",
                          eq_type="Splitter — flow divider", S=1.0, x=400, y=0)
    fs.blocks[X1].splitter_active = True
    fs.blocks[X1].splitter_fractions = [0.5, 0.5]   # [S-fwd, R1]
    fs.blocks[X2].splitter_active = True
    fs.blocks[X2].splitter_fractions = [0.5, 0.5]   # [Prod, R2]

    W = {"water": 1.0}

    def S(nm, src, dst, m=0.0, lock=False, role="internal"):
        sid = fs.new_id()
        s = Stream(id=sid, name=nm, src=src, dst=dst, mass_flow=m,
                   composition=dict(W), main_component="water",
                   phase="liquid", role=role)
        s.mass_flow_locked = lock
        fs.streams[sid] = s
        return s

    S("Feed", -1, M1, 100.0, lock=True, role="feed")
    S("S-a", M1, X1)                          # tramo compartido
    S("S-fwd", X1, X2)                         # X1 out0 (forward)
    S("R1", X1, M1, role="recycle")           # X1 out1 (reciclo 1)
    S("Prod", X2, -1, role="product")         # X2 out0 (producto)
    S("R2", X2, M1, role="recycle")           # X2 out1 (reciclo 2)
    return fs


def test_handcalc_self_consistent():
    """El SS documentado cierra TODO balance de bloque exactamente.

    Esto NO depende del solver: valida que el ancla en sí es correcta
    (un ancla con balance abierto no sirve).
    """
    ss = EXPECTED_SS
    # M1: Feed + R1 + R2 = S-a
    assert abs((ss["Feed"] + ss["R1"] + ss["R2"]) - ss["S-a"]) < 1e-9
    # X1: S-a = S-fwd + R1  y splits 50/50
    assert abs(ss["S-a"] - (ss["S-fwd"] + ss["R1"])) < 1e-9
    assert abs(ss["R1"] - 0.5 * ss["S-a"]) < 1e-9
    # X2: S-fwd = Prod + R2  y splits 50/50
    assert abs(ss["S-fwd"] - (ss["Prod"] + ss["R2"])) < 1e-9
    assert abs(ss["R2"] - 0.5 * ss["S-fwd"]) < 1e-9
    # Cierre global: Feed entra = Prod sale
    assert abs(ss["Feed"] - ss["Prod"]) < 1e-9


def _solve_and_compare(tol=0.5):
    fs = build_dual_recycle_fs()
    res = solve(fs)
    got = {s.name: s.mass_flow for s in fs.streams.values()}
    ok = (res.overall_status != "error" and
          all(abs(got.get(k, 0.0) - v) < tol for k, v in EXPECTED_SS.items()))
    return ok, got, res


def test_multitear_anchor_converges():
    """CAPA 3 — el motor Broyden converge el loop ACOPLADO al SS exacto.

    Convergencia REAL (no un 'converged' falso a 0): status != error, todos
    los interiores >0, y cada stream en su valor exacto calculado a mano.
    """
    ok, got, res = _solve_and_compare()
    assert ok, f"status={res.overall_status} got={got} exp={EXPECTED_SS}"
    assert res.overall_status != "error"
    # interiores estrictamente > 0 (no colapso)
    for k in ("S-a", "S-fwd", "R1", "R2", "Prod"):
        assert got[k] > 0.0, f"{k} colapsó a {got[k]}"
    # el tear vector convergió (RecycleSolution presente y converged)
    assert any(rs.converged for rs in res.recycle_solutions)
