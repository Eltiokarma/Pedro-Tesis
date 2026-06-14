"""PR-E — trazabilidad honesta del thermo_db (origin/quality).

Antes, los 310 compuestos tenían origin='experimental' por DEFAULT del
dataclass — falso: el catálogo nunca pobló la procedencia, y los ~pseudos
no tienen datos experimentales por definición.  PR-E:
  · default honesto 'unverified' (el valor existe y es bueno, pero su fuente
    no está confirmada — no afirmar 'experimental' sin base);
  · los pseudo-componentes (pseudo_components.json) marcados origin='pseudo'.
NO se tocó ningún VALOR numérico: solo el metadato de procedencia."""
import json
import os

import thermo_db as td


def test_default_es_unverified_no_experimental():
    """El default del dataclass es honesto: 'unverified', no 'experimental'."""
    import dataclasses
    from thermo_db import ComponentThermo
    fld = {f.name: f for f in dataclasses.fields(ComponentThermo)}
    assert fld["origin"].default == "unverified"


def test_ningun_compuesto_afirma_experimental_sin_base():
    """Tras PR-E, ningún compuesto queda en 'experimental' por default — o es
    'pseudo' (conocido) o 'unverified' (procedencia no confirmada)."""
    db = td._ensure_loaded()
    origins = {c.origin for c in db.values()}
    assert origins <= {"unverified", "pseudo"}      # nada 'experimental' espurio
    assert "unverified" in origins and "pseudo" in origins


def test_pseudos_marcados_desde_el_catalogo():
    """Cada pseudo de pseudo_components.json que tenga entrada propia en el db
    queda origin='pseudo'/quality='pseudo'."""
    db = td._ensure_loaded()
    pj = json.load(open(os.path.join("data", "pseudo_components.json")))
    listed = set()
    for k in ("industrial_pseudo", "food_pseudo_allowed",
              "material_pseudo_allowed"):
        for n in pj.get(k, []):
            listed.add(td._normalize_name(n))
    marked = {n for n, c in db.items() if c.origin == "pseudo"}
    assert marked, "debería haber pseudos marcados"
    for n in marked:
        assert n in listed                          # todo marcado está en el catálogo
        assert db[n].quality == "pseudo"
    # casos concretos esperados
    for n in ("crude_oil", "syngas", "sucrose", "diesel"):
        assert td.get(n).origin == "pseudo"


def test_alias_no_contamina_la_molecula_real():
    """vegetable_oil es un ALIAS a triolein (molécula real); marcar el pseudo
    NO debe volver pseudo a triolein."""
    assert td.get("vegetable_oil").name == "triolein"
    assert td.get("triolein").origin == "unverified"   # NO 'pseudo'


def test_valores_numericos_intactos():
    """PR-E solo toca metadato: los valores siguen idénticos a los conocidos
    (verificados contra NIST en barridos previos)."""
    casos = {
        "water":    (18.015, 100.0),
        "methanol": (32.04, 64.7),
        "benzene":  (78.11, 80.1),
        "ammonia":  (17.03, -33.3),
    }
    for n, (mw, tb) in casos.items():
        c = td.get(n)
        assert abs(c.mw - mw) < 0.01
        assert abs(c.tb_c - tb) < 0.1


def test_pseudo_conserva_sus_valores():
    """Un pseudo marcado conserva su MW (lo único físico que tiene); solo se
    corrigió la AFIRMACIÓN de procedencia, no el dato."""
    suc = td.get("sucrose")
    assert suc.origin == "pseudo"
    assert abs(suc.mw - 342.3) < 0.1                  # MW real intacto
