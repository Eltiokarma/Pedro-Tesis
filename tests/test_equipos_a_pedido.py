"""
tests/test_equipos_a_pedido.py — GATE de las explicaciones "a pedido".

Valida data/equipos_a_pedido.json: el texto que la UI muestra, en lugar de
un selector, cuando un tipo de equipo NO tiene catálogo comercial.

POR QUÉ ESTE GATE EXISTE.  Que un tipo no tenga catálogo no es un hueco de
datos que haya que rellenar: es un hecho de la ingeniería de procesos.  Un
recipiente de proceso, una columna o un horno se dimensionan contra el duty
(Souders-Brown, inundación, flux térmico) y se construyen contra un código
(ASME VIII, API 560), no se eligen de una lista de tallas.  El simulador lo
dice FUERTE y CON RAZONES para que el estudiante aprenda el porqué.

Este gate impide las dos formas de que ese mensaje se degrade:
  · que una explicación quede incompleta (sin razones, sin cómo se compra);
  · que quede HUÉRFANA — documentar el "a pedido" de un tipo que mientras
    tanto SÍ consiguió catálogo, con lo que el texto ya nunca se mostraría
    y quedaría mintiendo en el repositorio.

USO:
    python -m unittest tests.test_equipos_a_pedido -v
"""
import json
import os
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import equipment_costs as ec

_PATH = os.path.join(_PARENT, "data", "equipos_a_pedido.json")
_CATALOGO = os.path.join(_PARENT, "data", "equipos_comerciales.json")

# Campos que toda explicación debe traer para ser útil al estudiante.
_REQUERIDOS = ("titulo", "que_fija_el_tamano", "por_que", "como_se_compra")

# Tipos que a propósito NO están en EQUIPMENT_DATA porque no son equipo
# comprable, y aun así necesitan explicación en la UI.
_NO_SON_EQUIPO = {"Ambient"}


def _cargar(path=_PATH):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class TestEquiposAPedido(unittest.TestCase):

    def test_archivo_bien_formado(self):
        d = _cargar()
        self.assertEqual(d.get("schema"), 1)
        self.assertIsInstance(d.get("motivos"), dict)
        self.assertIsInstance(d.get("generico"), dict)

    def test_generico_completo(self):
        """El genérico es la red de seguridad: si un tipo no tiene motivo
        propio, igual debe poder explicarse.  Nunca un mensaje vacío."""
        g = _cargar().get("generico") or {}
        for campo in _REQUERIDOS:
            self.assertIn(campo, g, f"genérico: falta '{campo}'")
            self.assertTrue(g[campo], f"genérico: '{campo}' vacío")

    def test_eq_types_existen(self):
        for et in _cargar()["motivos"]:
            if et in _NO_SON_EQUIPO:
                continue
            self.assertIn(
                et, ec.EQUIPMENT_DATA,
                f"'{et}': eq_type inexistente en el catálogo genérico "
                f"(¿typo?).  Si a propósito no es equipo, declararlo en "
                f"_NO_SON_EQUIPO con su motivo.")

    def test_explicaciones_completas(self):
        for et, m in _cargar()["motivos"].items():
            for campo in _REQUERIDOS:
                self.assertIn(campo, m, f"{et}: falta '{campo}'")
                self.assertTrue(m[campo], f"{et}: '{campo}' vacío")
            self.assertIsInstance(
                m["que_fija_el_tamano"], list,
                f"{et}: 'que_fija_el_tamano' debe ser lista de razones")
            self.assertGreaterEqual(
                len(m["que_fija_el_tamano"]), 1,
                f"{et}: sin ninguna razón de ingeniería — un aviso sin "
                f"porqué no enseña nada")
            self.assertIsInstance(m.get("normas", []), list,
                                  f"{et}: 'normas' debe ser lista")

    def test_no_huerfanas(self):
        """Ningún tipo puede tener catálogo comercial Y explicación de
        'a pedido' a la vez: la UI muestra el aviso sólo cuando no hay
        entradas, así que ese texto nunca se vería y quedaría obsoleto
        afirmando algo que ya dejó de ser cierto."""
        con_catalogo = {e.get("eq_type")
                        for e in _cargar(_CATALOGO).get("equipos", [])}
        for et in _cargar()["motivos"]:
            self.assertNotIn(
                et, con_catalogo,
                f"'{et}' tiene entradas en el catálogo comercial y a la vez "
                f"una explicación de 'a pedido'.  Si ya se consiguió "
                f"catálogo, borrar la explicación: dejó de ser cierta.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
