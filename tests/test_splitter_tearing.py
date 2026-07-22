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


# ── keyed fractions: el reparto es ESTABLE ante cambios de topología ────
def _build_split3(insert_tank=False, keyed=False):
    """Splitter con 3 salidas [0.5,0.3,0.2].  Con insert_tank=True se mete
    un tanque pass-through en la primera salida (cambia el orden de
    enumeración de streams).  Con keyed=True las fracciones se anclan por
    salida (split_fraction); si no, se usan posicionales (splitter_fractions)."""
    import copy
    fs = Flowsheet()
    sp = Block(id=fs.new_id(), name="SP-101", eq_type="Splitter — flow divider",
               S=0.0, x=0, y=0, splitter_active=True,
               splitter_fractions=[0.5, 0.3, 0.2])
    fs.blocks[sp.id] = sp
    feed = Stream(id=fs.new_id(), name="S-feed", src=0, dst=sp.id,
                  mass_flow=10000, mass_flow_locked=True, phase="liquid",
                  main_component="water", composition={"water": 1.0})
    fs.streams[feed.id] = feed
    p1 = Stream(id=fs.new_id(), name="S-p1", src=sp.id, dst=0, role="product")
    p2 = Stream(id=fs.new_id(), name="S-p2", src=sp.id, dst=0, role="product")
    p3 = Stream(id=fs.new_id(), name="S-p3", src=sp.id, dst=0, role="product")
    if keyed:
        p1.split_fraction, p2.split_fraction, p3.split_fraction = 0.5, 0.3, 0.2
    for s in (p1, p2, p3):
        fs.streams[s.id] = s
    if insert_tank:
        tk = Block(id=fs.new_id(), name="TK-x",
                   eq_type="Storage tank — cone roof", S=0.0, x=0, y=0)
        fs.blocks[tk.id] = tk
        internal = copy.deepcopy(p1)
        internal.id = fs.new_id()
        internal.name = "S-p1-int"
        internal.role = "internal"
        internal.dst = tk.id
        fs.streams[internal.id] = internal
        p1.src = tk.id
        if keyed:
            internal.split_fraction = 0.5   # el keyed viaja con la salida real
            p1.split_fraction = None        # p1 ya NO es salida del splitter
    return fs


def _products(fs):
    return {s.name: round(s.mass_flow)
            for s in fs.streams.values() if s.role == "product"}


def test_splitter_posicional_rota_al_insertar_bloque():
    """BUG 1 (documentado): con fracciones POSICIONALES, insertar un bloque
    pass-through en una salida ROTA la asignación."""
    fs = _build_split3(insert_tank=False, keyed=False)
    fsv.solve(fs)
    assert _products(fs) == {"S-p1": 5000, "S-p2": 3000, "S-p3": 2000}
    fs = _build_split3(insert_tank=True, keyed=False)
    fsv.solve(fs)
    # posicional: el reparto se desalinea (evidencia del bug)
    assert _products(fs) != {"S-p1": 5000, "S-p2": 3000, "S-p3": 2000}


def test_splitter_keyed_estable_ante_insercion():
    """FIX: con split_fraction anclado por salida, insertar un bloque
    pass-through NO altera el reparto — cada fracción sigue con su salida."""
    esperado = {"S-p1": 5000, "S-p2": 3000, "S-p3": 2000}
    fs = _build_split3(insert_tank=False, keyed=True)
    fsv.solve(fs)
    assert _products(fs) == esperado
    fs = _build_split3(insert_tank=True, keyed=True)
    fsv.solve(fs)
    assert _products(fs) == esperado, \
        "las fracciones keyed deben mantenerse ancladas a su salida"


# ── BUG 12: splitter multi-entrada distribuía solo la PRIMERA entrada ────
def test_splitter_multientrada_distribuye_la_suma():
    """Un splitter con DOS entradas (torre de enfriamiento: retorno caliente
    + makeup) repartía únicamente la primera entrada e ignoraba el resto —
    solve_splitters usaba `feed.mass_flow` mientras el path de tearing y el
    audit W-SPLIT-LOCK ya usaban la SUMA (tres rutas inconsistentes).  El
    ejemplo cw_loop lo reproduce: evap/blowdown salían 1747.6/1165.0 en vez
    de los 1800/1200 de diseño, con el descuadre escondido en el HX."""
    import examples_registry as reg
    fs = reg.load_example("cw_loop")
    fsv.solve(fs)
    byname = {s.name: s for s in fs.streams.values()}
    assert abs(byname["S-evap"].mass_flow - 1800.0) < 1.0, \
        f"evap debe ser 1800 (suma de entradas), got {byname['S-evap'].mass_flow}"
    assert abs(byname["S-blowdown"].mass_flow - 1200.0) < 1.0, \
        f"blowdown debe ser 1200, got {byname['S-blowdown'].mass_flow}"
    # el lazo cierra: retorno = circulación lockeada, sin descuadre en el HX
    assert abs(byname["S-cwwarm"].mass_flow - 100000.0) < 1.0
    for b in fs.blocks.values():
        m_in = sum(s.mass_flow for s in fs.streams.values() if s.dst == b.id)
        m_out = sum(s.mass_flow for s in fs.streams.values() if s.src == b.id)
        assert abs(m_in - m_out) < 1.0, \
            f"{b.name} desbalanceado: in={m_in:.1f} out={m_out:.1f}"
