"""
tests/test_examples_start.py — auditoría estructural del INICIO de cada ejemplo.

Regla del catálogo: todo ejemplo inicia con una CORRIENTE de alimentación
(role="feed") que nace en un bloque fuente pasivo (tanque/vessel).  La masa
entra al proceso por corrientes, nunca "nace" dentro de una máquina: toda
bomba/compresor debe tener corriente de succión.

Origen: auditoría 2026-07 — methanol iniciaba con K-101 (compresor) SIN
succión ni tanque de alimentación; era el único ejemplo cuya masa aparecía
dentro del equipo.  Este test congela la regla para todo el catálogo.

USO:
    python -m unittest tests.test_examples_start -v
"""
import os
import sys
import json
import glob
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

_DATA_DIR = os.path.join(_PARENT, "data", "examples")

# Bloques fuente aceptables (pasivos: contienen o reciben, no impulsan).
_FUENTES_OK = ("Storage tank", "Vessel")
# Máquinas que impulsan fluido: SIEMPRE necesitan succión.  Los fans/blowers
# son impulsores de gas (tiro forzado) igual que un compresor de baja carga.
_MOVEDORES = ("Pump", "Compressor", "Fan", "Blower")
# Impulsores válidos de un feed GASEOSO (la P de llegada es trabajo, no dato).
_MOVEDORES_GAS = ("Compressor", "Fan", "Blower")

# Feeds de fase "liquid" que en realidad son sólidos transportados (harina/
# masa, caliza, batch de vidrio, papa entera): van por faja/tornillo, no por
# bomba.  (clave_ejemplo, nombre_feed).
_EXCEPCIONES_SOLIDOS = {
    ("bread", "S-masa-cruda"),
    ("cement", "S-caliza"),
    ("glass", "S-silica"),
    ("glass", "S-soda"),
    ("glass", "S-lime"),
    ("potato_chips", "S-papa-cruda"),
}

# Feeds gaseosos exentos de compresor propio:
#  · urea/S-CO2: entra a M-101 y el K-101 existente comprime la mezcla a la
#    presión del reactor — la elevación ya está maquinada aguas abajo.
#  · gas_sweet/S-gas-acido: condición de frontera — el gas ácido LLEGA del
#    campo a 50 bar (lock explícito origin='user'); comprimir 1 Mtm/a desde
#    1 atm sería una máquina de ~36 MW que no existe en una planta de aminas.
#  · smr_eq/S-vapor: header de vapor (fase "vapor"); el vapor se GENERA a
#    presión en la caldera, nunca se comprime desde 1 atm.
_EXCEPCIONES_GAS = {
    ("urea", "S-CO2"),
    ("gas_sweet", "S-gas-acido"),
}


def _example_keys():
    keys = []
    for p in sorted(glob.glob(os.path.join(_DATA_DIR, "*.json"))):
        name = os.path.splitext(os.path.basename(p))[0]
        if name in ("_golden", "manifest"):
            continue
        keys.append(name)
    return keys


def _load(key):
    with open(os.path.join(_DATA_DIR, f"{key}.json"), encoding="utf-8") as f:
        return json.load(f)


def _reaches_liquid_pump(feed, blocks, streams, max_hops=5):
    """Permit a suction mixing vessel before the pump, never a pressure
    increase or a processing unit before the first mover. Bound traversal
    so a disconnected recycle cannot satisfy the structural contract."""
    pressure = float(feed.get('pressure_bar') or 1.013)

    def walk(stream, seen, depth):
        b = blocks.get(stream.get('dst'))
        if b is None or depth > max_hops or b['id'] in seen:
            return False
        if (stream.get('pressure_locked') and
                float(stream.get('pressure_bar') or pressure) > pressure + 1e-6):
            return False
        if b['eq_type'].startswith('Pump'):
            return True
        if not b['eq_type'].startswith(('Mixer', 'Vessel', 'Storage tank', 'Valve')):
            return False
        if float(b.get('delta_p_bar') or 0) > 1e-6:
            return False
        outlets = [s for s in streams if s.get('src') == b['id']
                   and s.get('stream_kind', 'mass') == 'mass']
        return bool(outlets) and all(walk(s, seen | {b['id']}, depth + 1)
                                    for s in outlets)

    return walk(feed, set(), 0)


def test_suction_mixer_path_does_not_allow_pressure_creation():
    blocks = {1: {'id': 1, 'eq_type': 'Mixer — static', 'delta_p_bar': 0},
              2: {'id': 2, 'eq_type': 'Pump — centrifugal'}}
    feed = {'dst': 1, 'pressure_bar': 1.013, 'pressure_locked': True}
    suction = {'src': 1, 'dst': 2, 'pressure_bar': 1.013, 'pressure_locked': True}
    assert _reaches_liquid_pump(feed, blocks, [suction])
    suction['pressure_bar'] = 8
    assert not _reaches_liquid_pump(feed, blocks, [suction])
    suction.update(pressure_bar=1.013, dst=1)
    assert not _reaches_liquid_pump(feed, blocks, [suction])


def _is_atmospheric_natural_draft_air(feed, block, streams):
    """Natural convection supplies air without a mechanical compressor.

    This exception needs an active natural-draft tower, an air inlet and
    an atmospheric outlet without pressure gain; it is not a gas-feed
    exemption based on the example name.
    """
    if (block.get('eq_type') != 'Cooling tower — natural draft'
            or not block.get('cooling_tower_active')
            or feed.get('dst_port') != 'aire'
            or feed.get('phase') != 'gas'
            or not feed.get('pressure_locked')):
        return False
    pressure = float(feed.get('pressure_bar') or 0)
    comp = feed.get('composition') or {}
    if (not 0.95 <= pressure <= 1.05
            or float(block.get('delta_p_bar') or 0) > 0
            or float(block.get('P_op_bar') or pressure) > pressure + 1e-6
            or set(comp) - {'nitrogen', 'oxygen', 'water'}
            or not 0.70 <= comp.get('nitrogen', 0) <= 0.82
            or not 0.18 <= comp.get('oxygen', 0) <= 0.25
            or not 0 <= comp.get('water', 0) <= 0.05
            or abs(sum(comp.values()) - 1) > 1e-6):
        return False
    gas_out = [s for s in streams if s.get('src') == block['id']
               and s.get('phase') in ('gas', 'vapor')]
    return bool(gas_out) and all(
        s.get('pressure_locked')
        and 0.95 <= float(s.get('pressure_bar') or 0) <= pressure + 1e-6
        for s in gas_out)


def test_natural_draft_air_exception_is_bounded_by_physics():
    block = {'id': 1, 'eq_type': 'Cooling tower — natural draft',
             'cooling_tower_active': True, 'delta_p_bar': 0, 'P_op_bar': 1.0}
    feed = {'dst': 1, 'dst_port': 'aire', 'phase': 'gas',
            'pressure_bar': 1.013, 'pressure_locked': True,
            'composition': {'nitrogen': 0.76, 'oxygen': 0.23, 'water': 0.01}}
    out = {'src': 1, 'phase': 'gas', 'pressure_bar': 1.013,
           'pressure_locked': True}
    assert _is_atmospheric_natural_draft_air(feed, block, [out])
    assert not _is_atmospheric_natural_draft_air(
        dict(feed, pressure_bar=2.0), block, [out])
    assert not _is_atmospheric_natural_draft_air(
        feed, block, [dict(out, pressure_bar=2.0)])
    assert not _is_atmospheric_natural_draft_air(
        dict(feed, composition={'methane': 1.0}), block, [out])
    assert not _is_atmospheric_natural_draft_air(
        dict(feed, dst_port='agua'), block, [out])
    assert not _is_atmospheric_natural_draft_air(
        feed, dict(block, cooling_tower_active=False), [out])
    assert not _is_atmospheric_natural_draft_air(
        feed, dict(block, eq_type='Cooling tower — forced draft'), [out])


class TestIniciosDeEjemplos(unittest.TestCase):
    """Cada ejemplo del catálogo inicia con corriente de alimentación."""

    def test_todos_inician_con_corriente_feed(self):
        """Todo ejemplo tiene ≥1 corriente role='feed' y las corrientes que
        salen de un bloque fuente (sin entradas) están marcadas como feed."""
        for key in _example_keys():
            d = _load(key)
            blocks = {int(k): v for k, v in d.get("blocks", {}).items()}
            streams = list(d.get("streams", {}).values())
            feeds = [s for s in streams if s.get("role") == "feed"]
            self.assertTrue(feeds, f"{key}: sin corriente de alimentación "
                                   f"(ninguna con role='feed')")
            dsts = {s.get("dst") for s in streams}
            for bid, b in blocks.items():
                if bid in dsts:
                    continue                       # tiene entrada → no es fuente
                outs = [s for s in streams if s.get("src") == bid]
                self.assertTrue(
                    outs, f"{key}: bloque fuente {b['name']} no emite corriente")
                for s in outs:
                    self.assertEqual(
                        s.get("role"), "feed",
                        f"{key}: corriente inicial '{s.get('name')}' desde "
                        f"{b['name']} tiene role='{s.get('role')}' "
                        f"(esperado 'feed')")

    def test_fuentes_son_bloques_pasivos(self):
        """Los bloques fuente son tanques/vessels, no máquinas ni equipos
        de proceso: la masa entra por una corriente, no nace en un equipo."""
        for key in _example_keys():
            d = _load(key)
            blocks = {int(k): v for k, v in d.get("blocks", {}).items()}
            streams = list(d.get("streams", {}).values())
            dsts = {s.get("dst") for s in streams}
            for bid, b in blocks.items():
                if bid in dsts:
                    continue
                self.assertTrue(
                    b["eq_type"].startswith(_FUENTES_OK),
                    f"{key}: bloque fuente {b['name']} es '{b['eq_type']}' "
                    f"(debe ser tanque o vessel)")

    def test_feeds_liquidos_pasan_por_bomba(self):
        """Todo feed líquido entra al proceso a través de una bomba (nivel
        DWSIM: nada fluye sin un impulsor).  Los sólidos transportados de
        _EXCEPCIONES_SOLIDOS van por faja/tornillo y quedan exentos."""
        for key in _example_keys():
            d = _load(key)
            blocks = {int(k): v for k, v in d.get("blocks", {}).items()}
            for s in d.get("streams", {}).values():
                if s.get("role") != "feed" or (s.get("phase") or "") != "liquid":
                    continue
                if (key, s.get("name")) in _EXCEPCIONES_SOLIDOS:
                    continue
                dst = blocks.get(s.get("dst"))
                self.assertIsNotNone(
                    dst, f"{key}: feed '{s.get('name')}' sin bloque destino")
                self.assertTrue(
                    _reaches_liquid_pump(s, blocks, list(d.get('streams', {}).values())),
                    f"{key}: feed líquido '{s.get('name')}' entra a "
                    f"'{dst['eq_type']}' ({dst['name']}) sin bomba de "
                    f"alimentación")

    def test_feeds_gaseosos_pasan_por_compresor(self):
        """Todo feed gaseoso entra al proceso a través de un compresor: la
        presión de llegada no es un dato, es trabajo calculado. Fase "vapor"
        (headers de caldera), fronteras declaradas y aire atmosférico de
        una torre activa de tiro natural tienen sus excepciones físicas."""
        for key in _example_keys():
            d = _load(key)
            blocks = {int(k): v for k, v in d.get("blocks", {}).items()}
            for s in d.get("streams", {}).values():
                if s.get("role") != "feed" or (s.get("phase") or "") != "gas":
                    continue
                if (key, s.get("name")) in _EXCEPCIONES_GAS:
                    continue
                dst = blocks.get(s.get("dst"))
                self.assertIsNotNone(
                    dst, f"{key}: feed '{s.get('name')}' sin bloque destino")
                if _is_atmospheric_natural_draft_air(
                        s, dst, list(d.get('streams', {}).values())):
                    continue
                self.assertTrue(
                    dst["eq_type"].startswith(_MOVEDORES_GAS),
                    f"{key}: feed gaseoso '{s.get('name')}' entra a "
                    f"'{dst['eq_type']}' ({dst['name']}) sin impulsor de gas "
                    f"(compresor/fan/blower) de alimentación")

    def test_bombas_y_compresores_tienen_succion(self):
        """Toda bomba/compresor tiene corriente de entrada (succión)."""
        for key in _example_keys():
            d = _load(key)
            blocks = {int(k): v for k, v in d.get("blocks", {}).items()}
            dsts = {s.get("dst") for s in d.get("streams", {}).values()}
            for bid, b in blocks.items():
                if not b["eq_type"].startswith(_MOVEDORES):
                    continue
                self.assertIn(
                    bid, dsts,
                    f"{key}: {b['eq_type']} ({b['name']}) sin corriente de "
                    f"succión — el flujo no puede nacer dentro de la máquina")


if __name__ == "__main__":
    unittest.main(verbosity=2)
