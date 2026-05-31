"""Extrae metadata de ejemplos de flowsheet_qt.py vía AST (sin importar
PySide6).  Dos fuentes:

  · builder_map (en action_load_example): clave_menu -> builder, nombre PFD,
    área (capa), código PFD.  Usado para el marco PFD.
  · EXAMPLE_CATEGORIES (módulo): orden + agrupamiento + label del MENÚ.

El manifest de Fase 2 combina ambas.
"""
import ast


def _find_assign(tree, name):
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == name):
            return node.value
    return None


def extract_menu_map(path="flowsheet_qt.py"):
    """builder_method_name -> (clave_menu, nombre, area, codigo_pfd).

    OJO: la clave NO es nombre[9:] — hay 21 alias.  Tomada del builder_map
    literal de action_load_example."""
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    out = {}
    for node in ast.walk(tree):
        # Buscar la asignación  builder_map = { ... }
        if not isinstance(node, ast.Assign):
            continue
        if not (len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "builder_map"):
            continue
        d = node.value
        if not isinstance(d, ast.Dict):
            continue
        for k_node, v_node in zip(d.keys, d.values):
            key = ast.literal_eval(k_node)          # clave del menú (str)
            # value = (TkEditor._example_X, "nombre", "area", "PFD")
            assert isinstance(v_node, ast.Tuple), key
            first = v_node.elts[0]                   # Attribute: TkEditor._example_X
            builder = first.attr
            strs = [ast.literal_eval(e) for e in v_node.elts[1:]]
            nombre = strs[0] if len(strs) > 0 else ""
            area = strs[1] if len(strs) > 1 else ""
            pfd = strs[2] if len(strs) > 2 else ""
            out[builder] = (key, nombre, area, pfd)
    return out


def extract_categories(path="flowsheet_qt.py"):
    """Devuelve EXAMPLE_CATEGORIES tal cual: lista de (categoria, [(clave,
    label_menu), ...]).  ESTA es la fuente de verdad del orden/agrupamiento
    y de los labels que ve el usuario en el menú."""
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    node = _find_assign(tree, "EXAMPLE_CATEGORIES")
    if node is None:
        raise RuntimeError("EXAMPLE_CATEGORIES no encontrada en " + path)
    return ast.literal_eval(node)


if __name__ == "__main__":
    import json
    m = extract_menu_map()
    cats = extract_categories()
    print(f"builders mapeados: {len(m)}  |  categorías: {len(cats)}")
    print(json.dumps({b: k for b, (k, *_rest) in m.items()},
                     indent=1, ensure_ascii=False))

