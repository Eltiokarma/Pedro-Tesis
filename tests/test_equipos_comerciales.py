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

RESTRICCIÓN DURA para todo consumidor futuro de este catálogo (hoy este
gate es el único): el S comercial es la ENVOLVENTE del modelo (capacidad
nominal/máxima publicada) y **NUNCA se escribe en Block.S**.  Block.S
sigue viniendo del sizing del simulador; el S comercial entra solo a la
verificación del modo selección (S_requerido <= S_modelo, AND con
P_max/T_max/Q_max/head_max) y a la visualización de la ficha.  Volcarlo
al bloque haría que el costeo Turton use el techo del bastidor y el
CAPEX salga inflado sistemáticamente en toda la planta.

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

_REQUERIDOS = ("marca", "modelo", "eq_type", "fuente", "fecha_consulta")

# ESQUEMA v2: el tamaño es un XOR estricto — exactamente uno de:
#   · "S": capacidad escalar nominal/máxima publicada (verificación escalar
#     + rango del tipo), o
#   · "S_no_publicado": motivo declarado de por qué el fabricante no
#     publica un techo escalar.  Vocabulario CERRADO:
_MOTIVOS_SIN_S = {
    "configurable",         # el tamaño se arma por pedido (PHE: nº placas)
    "punto_de_operacion",   # el escalar depende del duty point (bomba: kW eje)
    "otra_magnitud",        # el fabricante publica otra base no mapeada a S_unit
}
# Sin S, la entrada debe verificar ALGO: al menos una dimensión de
# envolvente de estas (la verificación pasa a ser un AND de desigualdades).
_ENVOLVENTE_MIN = ("Q_max_m3_h", "head_max_m", "P_max_bar", "T_max_C",
                   "n_placas_max")

# Granularidad de la envolvente (obligatoria en toda entrada sin S):
#   · "modelo"  — los límites son del tamaño/bastidor concreto nombrado.
#   · "familia" — los límites son del rango completo de la serie.
# Vocabulario CERRADO.  Prohibida en entradas con S (un S escalar ya es de
# un modelo nombrado; no hay ambigüedad de familia que declarar).
_GRANULARIDADES = {"modelo", "familia"}

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

    def test_xor_S_o_motivo(self):
        """XOR estricto (esquema v2): exactamente uno de S / S_no_publicado.
        Ni ambos ni ninguno — falla ruidosamente, no pasa por omisión."""
        for e in _cargar()["equipos"]:
            etiqueta = f"{e.get('marca')} {e.get('modelo')}"
            tiene_S = "S" in e
            tiene_motivo = "S_no_publicado" in e
            self.assertFalse(
                tiene_S and tiene_motivo,
                f"{etiqueta}: lleva S y S_no_publicado A LA VEZ")
            self.assertTrue(
                tiene_S or tiene_motivo,
                f"{etiqueta}: no lleva NI S NI S_no_publicado")
            if tiene_S:
                self.assertGreater(float(e["S"]), 0.0, etiqueta)
            else:
                self.assertIn(
                    e["S_no_publicado"], _MOTIVOS_SIN_S,
                    f"{etiqueta}: motivo '{e['S_no_publicado']}' fuera del "
                    f"vocabulario cerrado {sorted(_MOTIVOS_SIN_S)}")
                envolvente = [k for k in _ENVOLVENTE_MIN
                              if k in (e.get("params") or {})]
                self.assertTrue(
                    envolvente,
                    f"{etiqueta}: sin S y sin ninguna dimensión de "
                    f"envolvente {_ENVOLVENTE_MIN} — no verifica nada, "
                    f"no entra")

    def test_granularidad(self):
        """Regla de granularidad (va junto con el XOR del esquema v2).

        Motivo: una envolvente de FAMILIA la fija el miembro más grande
        del rango, así que casi cualquier duty la satisface.  La entrada
        pasa el esquema y no verifica nada — falso positivo, que es peor
        que no tener entrada.  El gate no puede detectar esto por formato;
        solo puede exigir que se declare: obligatoria sin S, prohibida con
        S, y si es "familia" las notas deben explicar por qué no se
        consiguió la envolvente del tamaño."""
        for e in _cargar()["equipos"]:
            etiqueta = f"{e.get('marca')} {e.get('modelo')}"
            if "S" in e:
                self.assertNotIn(
                    "granularidad", e,
                    f"{etiqueta}: granularidad PROHIBIDA con S (un S "
                    f"escalar ya es de un modelo nombrado)")
                continue
            if "S_no_publicado" not in e:
                continue    # forma inválida: la reporta test_xor_S_o_motivo
            self.assertIn(
                "granularidad", e,
                f"{etiqueta}: granularidad OBLIGATORIA en toda entrada "
                f"con S_no_publicado")
            self.assertIn(
                e["granularidad"], _GRANULARIDADES,
                f"{etiqueta}: granularidad '{e['granularidad']}' fuera "
                f"del vocabulario cerrado {sorted(_GRANULARIDADES)}")
            if e["granularidad"] == "familia":
                notas = (e.get("params") or {}).get("notas", "")
                self.assertTrue(
                    str(notas).strip(),
                    f"{etiqueta}: granularidad=familia sin params.notas — "
                    f"una cota de familia sin explicación de por qué no "
                    f"se consiguió la del tamaño no entra")

    def test_S_dentro_de_rango_del_tipo(self):
        """S fuera de [S_min, S_max] del eq_type es casi siempre error de
        unidad (kg/h donde va kg/s). El gate viejo sólo pedía S > 0.
        Las entradas sin S (S_no_publicado, esquema v2) se saltean: su
        validación vive en test_xor_S_o_motivo."""
        for e in _cargar()["equipos"]:
            if "S" not in e:
                continue
            etiqueta = f"{e.get('marca')} {e.get('modelo')}"
            spec = ec.EQUIPMENT_DATA.get(e["eq_type"], {})
            s_min = spec.get("S_min")
            s_max = spec.get("S_max")
            if s_min is None or s_max is None:
                continue    # correlaciones sin rango declarado (p.ej. Sinnott)
            S = float(e["S"])
            self.assertGreaterEqual(
                S, s_min,
                f"{etiqueta}: S={S:g} {spec.get('S_unit', '')} < S_min="
                f"{s_min:g} del tipo — ¿error de unidad?")
            self.assertLessEqual(
                S, s_max,
                f"{etiqueta}: S={S:g} {spec.get('S_unit', '')} > S_max="
                f"{s_max:g} del tipo — ¿error de unidad?")

    def test_sin_duplicados(self):
        vistos = set()
        for e in _cargar()["equipos"]:
            clave = (e.get("marca"), e.get("modelo"), e.get("eq_type"))
            self.assertNotIn(clave, vistos, f"duplicado: {clave}")
            vistos.add(clave)


if __name__ == "__main__":
    unittest.main(verbosity=2)
