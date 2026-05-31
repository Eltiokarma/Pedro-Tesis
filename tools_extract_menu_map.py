"""Extrae el builder_map de flowsheet_qt.py vía AST (sin importar PySide6).

Devuelve dict: builder_method_name -> (clave_menu, nombre, categoria, codigo_pfd).
Usado por el exporter de Fase 1 para nombrar los JSON con la CLAVE DEL MENÚ.
"""
import ast


def extract_menu_map(path="flowsheet_qt.py"):
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
            # value = (TkEditor._example_X, "nombre", "categoria", "PFD")
            assert isinstance(v_node, ast.Tuple), key
            first = v_node.elts[0]                   # Attribute: TkEditor._example_X
            builder = first.attr
            strs = [ast.literal_eval(e) for e in v_node.elts[1:]]
            nombre = strs[0] if len(strs) > 0 else ""
            categoria = strs[1] if len(strs) > 1 else ""
            pfd = strs[2] if len(strs) > 2 else ""
            out[builder] = (key, nombre, categoria, pfd)
    return out


if __name__ == "__main__":
    import json
    m = extract_menu_map()
    print(f"builders mapeados: {len(m)}")
    print(json.dumps({b: k for b, (k, *_rest) in m.items()},
                     indent=1, ensure_ascii=False))
