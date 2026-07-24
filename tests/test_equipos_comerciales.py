"""
tests/test_equipos_comerciales.py — GATE del catálogo de equipos comerciales.

Valida el esquema de data/equipos_comerciales.json (modo selección de las
Fichas Técnicas: marca/modelo/proveedor por bloque).  El catálogo nace
VACÍO; este gate existe ANTES que los datos para que toda entrada que se
cargue (vía Claude Desktop/Cowork con los PDFs de fabricante, ver
docs/BRIEF_CATALOGO_COMERCIAL.md) llegue bien formada:

  · eq_type debe existir en equipment_costs.EQUIPMENT_DATA (la entrada
    comercial PARAMETRIZA un tipo del catálogo, no inventa uno nuevo);
  · S > 0 en la unidad del tipo (área m², potencia kW, ...);
  · fuente = URL del documento OFICIAL del fabricante + fecha_consulta —
    la regla de la casa: ningún número sin procedencia.

USO:
    python -m unittest tests.test_equipos_comerciales -v
"""
import json
import os
import re
import sys
import unittest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

import equipment_costs as ec

_PATH = os.path.join(_PARENT, "data", "equipos_comerciales.json")

_REQUERIDOS = ("marca", "modelo", "eq_type", "S", "fuente", "fecha_consulta")

# Parámetros opcionales admitidos y su tipo (overrides que el modo
# selección vuelca al Block; deben mapear a ganchos existentes).
_PARAMS_OK = {
    "U_W_m2K": (int, float),        # → U_override
    "eta": (int, float),            # → efficiency
    "material": str,                # → material (clave MATERIAL_FACTORS)
    "P_max_bar": (int, float),
    "T_max_C": (int, float),
    "Q_max_m3_h": (int, float),
    "head_max_m": (int, float),
    "rpm": (int, float),
    "n_placas_max": int,
    "notas": str,
}


def _cargar():
    with open(_PATH, encoding="utf-8") as f:
        return json.load(f)


class TestCatalogoComercial(unittest.TestCase):

    def test_archivo_bien_formado(self):
        d = _cargar()
        self.assertEqual(d.get("schema"), 1)
        self.assertIsInstance(d.get("equipos"), list)

    def test_entradas_validas(self):
        for e in _cargar()["equipos"]:
            etiqueta = f"{e.get('marca')} {e.get('modelo')}"
            for campo in _REQUERIDOS:
                self.assertIn(campo, e, f"{etiqueta}: falta '{campo}'")
                self.assertTrue(e[campo], f"{etiqueta}: '{campo}' vacío")
            self.assertIn(e["eq_type"], ec.EQUIPMENT_DATA,
                          f"{etiqueta}: eq_type '{e['eq_type']}' no existe "
                          f"en el catálogo genérico")
            self.assertGreater(float(e["S"]), 0.0, etiqueta)
            self.assertTrue(str(e["fuente"]).startswith("http"),
                            f"{etiqueta}: fuente debe ser URL del fabricante")
            self.assertRegex(str(e["fecha_consulta"]), r"^\d{4}-\d{2}-\d{2}$",
                             f"{etiqueta}: fecha_consulta AAAA-MM-DD")
            for k, v in (e.get("params") or {}).items():
                self.assertIn(k, _PARAMS_OK,
                              f"{etiqueta}: param desconocido '{k}'")
                self.assertIsInstance(v, _PARAMS_OK[k],
                                      f"{etiqueta}: '{k}' tipo inválido")
            mat = (e.get("params") or {}).get("material")
            if mat:
                self.assertIn(mat, ec.MATERIAL_FACTORS,
                              f"{etiqueta}: material '{mat}' sin FM")

    def test_sin_duplicados(self):
        vistos = set()
        for e in _cargar()["equipos"]:
            clave = (e.get("marca"), e.get("modelo"), e.get("eq_type"))
            self.assertNotIn(clave, vistos, f"duplicado: {clave}")
            vistos.add(clave)


if __name__ == "__main__":
    unittest.main(verbosity=2)
