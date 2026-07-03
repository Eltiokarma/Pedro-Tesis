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
# Máquinas que impulsan fluido: SIEMPRE necesitan succión.
_MOVEDORES = ("Pump", "Compressor")

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
                    dst["eq_type"].startswith("Pump"),
                    f"{key}: feed líquido '{s.get('name')}' entra a "
                    f"'{dst['eq_type']}' ({dst['name']}) sin bomba de "
                    f"alimentación")

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
