"""
examples_registry.py — Registry declarativo de ejemplos (Fase 2).

Reemplaza los builders imperativos _example_* por carga desde JSON.  SIN
dependencias de UI (no importa PySide6 ni Qt): lo consumen tanto la UI Qt
como validate_ui, el gate y los tests.

API:
    list_examples()        -> lista de dicts del manifest, EN ORDEN del menú.
    list_categories()      -> [(categoria, [entrada, ...]), ...] agrupado y
                              en orden (para poblar el menú).
    get_metadata(clave)    -> la entrada del manifest de esa clave.
    load_example(clave)    -> Flowsheet (from_dict del JSON correspondiente).

El manifest y los JSON viven en data/examples/.  El formato JSON es el de
Flowsheet.to_dict() — esta capa NO lo modifica, solo lo consume.
"""
import os
import json
import functools

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "data", "examples")
_MANIFEST_PATH = os.path.join(_DATA_DIR, "manifest.json")


@functools.lru_cache(maxsize=1)
def _manifest():
    with open(_MANIFEST_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("examples", [])


def list_examples():
    """Lista de entradas del manifest, en el orden del menú.  Copia
    defensiva para que el caller no mute el cache."""
    return [dict(e) for e in _manifest()]


def list_categories():
    """Agrupa las entradas por categoría preservando el orden de aparición
    (= orden del menú).  Devuelve [(categoria, [entrada, ...]), ...]."""
    groups = []
    index = {}
    for e in _manifest():
        cat = e["categoria"]
        if cat not in index:
            index[cat] = []
            groups.append((cat, index[cat]))
        index[cat].append(dict(e))
    return groups


def get_metadata(clave):
    """Entrada del manifest para `clave`, o None si no existe."""
    for e in _manifest():
        if e["clave"] == clave:
            return dict(e)
    return None


def load_example(clave):
    """Carga el JSON de `clave` y devuelve un Flowsheet (from_dict).

    Lanza KeyError si la clave no está en el manifest, FileNotFoundError si
    el JSON no existe.  Import de flowsheet_model diferido para no acoplar
    el registry al modelo al importar (sigue siendo UI-free)."""
    meta = get_metadata(clave)
    if meta is None:
        raise KeyError(f"ejemplo desconocido: {clave!r}")
    path = os.path.join(_DATA_DIR, meta["archivo"])
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    from flowsheet_model import Flowsheet
    return Flowsheet.from_dict(d)


def builder_name(clave):
    """Nombre del builder _example_* asociado (string-key de
    hydraulic_defaults.EXAMPLE_PRESETS).  Se conserva en el manifest tras
    borrar los builders porque EXAMPLE_PRESETS sigue indexado por él."""
    meta = get_metadata(clave)
    return meta["builder"] if meta else None
