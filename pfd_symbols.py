"""
PFD SYMBOLS — biblioteca de símbolos ISO 10628 / ISA S5.1.

Origen: handoff del prototipo React (`PFD handoff bundle`, claude.ai/design).
Convertido a Python preservando viewBox, ports y body SVG sin wrapper.

Estructura:
    SYMBOLS[symbol_id] = {
        "name":     str,           # nombre en español
        "category": str,           # categoría ISO 10628
        "standard": str,           # estándar referenciado
        "w": float, "h": float,    # ancho/alto del viewBox
        "ports":    List[Tuple[name:str, x:float, y:float]],
        "body":     str,           # SVG body sin <svg> wrapper
    }

    EQ_TYPE_TO_SYMBOL[eq_type] = symbol_id
        Mapeo desde nuestros eq_type internos (equipment_costs.EQUIPMENT_DATA)
        a los IDs de la biblioteca PFD.

API:
    get(symbol_id)              -> dict | None
    get_for_eq_type(eq_type)    -> dict | None
    wrap_svg(symbol_id, w=None, h=None) -> str   # SVG completo listo para QSvgRenderer
"""

from typing import Dict, List, Optional, Tuple


SYMBOLS: Dict[str, dict] = {
    'blower': {
        'name': 'Soplador / ventilador',
        'category': 'compresores',
        'standard': 'ISO 10628 · ISA S5.1',
        'w': 80.0, 'h': 70.0,
        'ports': [
            ('in', 0, 35.0),
            ('out', 80.0, 35.0),
        ],
        'body': '<circle cx="40" cy="35" r="28" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<path d="M 40 14 Q 52 24 40 35 Q 28 24 40 14 Z" fill="none" stroke="#0d0d0d" stroke-width="1.2"/>\n<path d="M 61 35 Q 51 47 40 35 Q 51 23 61 35 Z" fill="none" stroke="#0d0d0d" stroke-width="1.2"/>\n<path d="M 40 56 Q 28 46 40 35 Q 52 46 40 56 Z" fill="none" stroke="#0d0d0d" stroke-width="1.2"/>\n<path d="M 19 35 Q 29 23 40 35 Q 29 47 19 35 Z" fill="none" stroke="#0d0d0d" stroke-width="1.2"/>\n<circle cx="40" cy="35" r="3" fill="#0d0d0d"/>',
    },
    'centrifuge': {
        'name': 'Centrífuga',
        'category': 'separadores',
        'standard': 'ISO 10628',
        'w': 100.0, 'h': 100.0,
        'ports': [
            ('in', 0, 30.0),
            ('top', 50.0, 0),
            ('bot', 50.0, 100.0),
        ],
        'body': '<circle cx="50" cy="50" r="42" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<circle cx="50" cy="50" r="28" fill="none" stroke="#0d0d0d" stroke-width="1.1"/>\n<path d="M 50 22 A 28 28 0 0 1 78 50" fill="none" stroke="#0d0d0d" stroke-width="1.6"/>\n<polygon points="74,48 82,50 76,56" fill="#0d0d0d"/>',
    },
    'column-packed': {
        'name': 'Columna empacada',
        'category': 'columnas',
        'standard': 'ISO 10628',
        'w': 70.0, 'h': 200.0,
        'ports': [
            ('top', 35.0, 0),
            ('bot', 35.0, 200.0),
            ('feed', 70.0, 90.0),
        ],
        'body': '<path d="M 5 18 A 30 18 0 0 1 65 18 L 65 182 A 30 18 0 0 1 5 182 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="10" y1="42" x2="60" y2="42" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="10" y1="98" x2="60" y2="98" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="10" y1="106" x2="60" y2="106" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="10" y1="162" x2="60" y2="162" stroke="#0d0d0d" stroke-width="1.1"/>\n<g stroke="#0d0d0d" stroke-width="0.6">\n  <line x1="12" y1="46" x2="20" y2="54"/><line x1="20" y1="46" x2="28" y2="54"/>\n  <line x1="28" y1="46" x2="36" y2="54"/><line x1="36" y1="46" x2="44" y2="54"/>\n  <line x1="44" y1="46" x2="52" y2="54"/><line x1="52" y1="46" x2="60" y2="54"/>\n  <line x1="12" y1="56" x2="20" y2="64"/><line x1="20" y1="56" x2="28" y2="64"/>\n  <line x1="28" y1="56" x2="36" y2="64"/><line x1="36" y1="56" x2="44" y2="64"/>\n  <line x1="44" y1="56" x2="52" y2="64"/><line x1="52" y1="56" x2="60" y2="64"/>\n  <line x1="12" y1="66" x2="20" y2="74"/><line x1="20" y1="66" x2="28" y2="74"/>\n  <line x1="28" y1="66" x2="36" y2="74"/><line x1="36" y1="66" x2="44" y2="74"/>\n  <line x1="44" y1="66" x2="52" y2="74"/><line x1="52" y1="66" x2="60" y2="74"/>\n  <line x1="12" y1="76" x2="20" y2="84"/><line x1="20" y1="76" x2="28" y2="84"/>\n  <line x1="28" y1="76" x2="36" y2="84"/><line x1="36" y1="76" x2="44" y2="84"/>\n  <line x1="44" y1="76" x2="52" y2="84"/><line x1="52" y1="76" x2="60" y2="84"/>\n  <line x1="12" y1="86" x2="20" y2="94"/><line x1="20" y1="86" x2="28" y2="94"/>\n  <line x1="28" y1="86" x2="36" y2="94"/><line x1="36" y1="86" x2="44" y2="94"/>\n  <line x1="44" y1="86" x2="52" y2="94"/><line x1="52" y1="86" x2="60" y2="94"/>\n  <line x1="12" y1="112" x2="20" y2="120"/><line x1="20" y1="112" x2="28" y2="120"/>\n  <line x1="28" y1="112" x2="36" y2="120"/><line x1="36" y1="112" x2="44" y2="120"/>\n  <line x1="44" y1="112" x2="52" y2="120"/><line x1="52" y1="112" x2="60" y2="120"/>\n  <line x1="12" y1="122" x2="20" y2="130"/><line x1="20" y1="122" x2="28" y2="130"/>\n  <line x1="28" y1="122" x2="36" y2="130"/><line x1="36" y1="122" x2="44" y2="130"/>\n  <line x1="44" y1="122" x2="52" y2="130"/><line x1="52" y1="122" x2="60" y2="130"/>\n  <line x1="12" y1="132" x2="20" y2="140"/><line x1="20" y1="132" x2="28" y2="140"/>\n  <line x1="28" y1="132" x2="36" y2="140"/><line x1="36" y1="132" x2="44" y2="140"/>\n  <line x1="44" y1="132" x2="52" y2="140"/><line x1="52" y1="132" x2="60" y2="140"/>\n  <line x1="12" y1="142" x2="20" y2="150"/><line x1="20" y1="142" x2="28" y2="150"/>\n  <line x1="28" y1="142" x2="36" y2="150"/><line x1="36" y1="142" x2="44" y2="150"/>\n  <line x1="44" y1="142" x2="52" y2="150"/><line x1="52" y1="142" x2="60" y2="150"/>\n  <line x1="12" y1="152" x2="20" y2="160"/><line x1="20" y1="152" x2="28" y2="160"/>\n  <line x1="28" y1="152" x2="36" y2="160"/><line x1="36" y1="152" x2="44" y2="160"/>\n  <line x1="44" y1="152" x2="52" y2="160"/><line x1="52" y1="152" x2="60" y2="160"/>\n</g>',
    },
    'column-stripper': {
        'name': 'Columna stripper',
        'category': 'columnas',
        'standard': 'ISO 10628',
        'w': 70.0, 'h': 160.0,
        'ports': [
            ('top', 35.0, 0),
            ('bot', 35.0, 160.0),
            ('feed', 70.0, 72.0),
        ],
        'body': '<path d="M 5 16 A 30 16 0 0 1 65 16 L 65 144 A 30 16 0 0 1 5 144 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="10" y1="38" x2="60" y2="38" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="10" y1="56" x2="60" y2="56" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="10" y1="74" x2="60" y2="74" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="10" y1="92" x2="60" y2="92" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="10" y1="110" x2="60" y2="110" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="10" y1="128" x2="60" y2="128" stroke="#0d0d0d" stroke-width="1.1"/>',
    },
    'column-tray': {
        'name': 'Columna de platos',
        'category': 'columnas',
        'standard': 'ISO 10628',
        'w': 70.0, 'h': 200.0,
        'ports': [
            ('top', 35.0, 0.0),
            ('bot', 35.0, 200.0),
            ('feed', 70.0, 90.0),
        ],
        'body': '<path d="M 5 18 A 30 18 0 0 1 65 18 L 65 182 A 30 18 0 0 1 5 182 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="10" y1="38" x2="60" y2="38" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="10" y1="54" x2="60" y2="54" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="10" y1="70" x2="60" y2="70" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="10" y1="86" x2="60" y2="86" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="10" y1="102" x2="60" y2="102" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="10" y1="118" x2="60" y2="118" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="10" y1="134" x2="60" y2="134" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="10" y1="150" x2="60" y2="150" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="10" y1="166" x2="60" y2="166" stroke="#0d0d0d" stroke-width="1.1"/>',
    },
    'compressor-centrifugal': {
        'name': 'Compresor centrífugo',
        'category': 'compresores',
        'standard': 'ISO 10628 · ISA S5.1',
        'w': 100.0, 'h': 70.0,
        'ports': [
            ('in', 0, 35.0),
            ('out', 100.0, 35.0),
        ],
        'body': '<polygon points="5,30 95,10 95,60 5,50" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>',
    },
    'compressor-reciprocating': {
        'name': 'Compresor reciprocante',
        'category': 'compresores',
        'standard': 'ISO 10628 · ISA S5.1',
        'w': 100.0, 'h': 70.0,
        'ports': [
            ('in', 0, 35.0),
            ('out', 100.0, 35.0),
        ],
        'body': '<rect x="10" y="15" width="80" height="40" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<rect x="22" y="22" width="20" height="26" fill="none" stroke="#0d0d0d" stroke-width="1.2"/>\n<rect x="58" y="22" width="20" height="26" fill="none" stroke="#0d0d0d" stroke-width="1.2"/>',
    },
    'crystallizer': {
        'name': 'Cristalizador',
        'category': 'otros',
        'standard': 'ISO 10628',
        'w': 80.0, 'h': 120.0,
        'ports': [
            ('in', 0, 60.0),
            ('out', 80.0, 60.0),
        ],
        'body': '<path d="M 5 22 A 35 14 0 0 1 75 22 L 75 90 L 40 116 L 5 90 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<g fill="none" stroke="#0d0d0d" stroke-width="0.7">\n  <polygon points="22,68 28,62 34,68 28,74"/>\n  <polygon points="42,75 48,69 54,75 48,81"/>\n  <polygon points="28,84 34,78 40,84 34,90"/>\n  <polygon points="50,60 56,54 62,60 56,66"/>\n</g>',
    },
    'cyclone': {
        'name': 'Ciclón',
        'category': 'separadores',
        'standard': 'ISO 10628',
        'w': 80.0, 'h': 120.0,
        'ports': [
            ('in', 0.0, 18.0),
            ('top-out', 40.0, 0.0),
            ('bot-out', 40.0, 120.0),
        ],
        'body': '<path d="M 0 8 L 80 8 L 80 60 L 50 116 L 30 116 L 0 60 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<rect x="32" y="-6" width="16" height="14" fill="#fff" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="40" y1="8" x2="40" y2="44" stroke="#0d0d0d" stroke-width="1.1"/>',
    },
    'decanter': {
        'name': 'Decantador',
        'category': 'separadores',
        'standard': 'ISO 10628',
        'w': 160.0, 'h': 70.0,
        'ports': [
            ('in', 0, 21.0),
            ('top', 80.0, 0),
            ('bot', 80.0, 70.0),
        ],
        'body': '<path d="M 18 0 L 142 0 A 18 35 0 0 1 142 70 L 18 70 A 18 35 0 0 1 18 0 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="18" y1="35" x2="142" y2="35" stroke="#0d0d0d" stroke-width="0.8" stroke-dasharray="3 2"/>',
    },
    'drum-screw': {
        'name': 'Transportador tornillo',
        'category': 'otros',
        'standard': 'ISO 10628',
        'w': 140.0, 'h': 40.0,
        'ports': [
            ('in', 0, 20.0),
            ('out', 140.0, 20.0),
        ],
        'body': '<rect x="0" y="8" width="140" height="24" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<g fill="#0d0d0d">\n  <circle cx="10" cy="20" r="2"/><circle cx="22" cy="20" r="2"/><circle cx="34" cy="20" r="2"/>\n  <circle cx="46" cy="20" r="2"/><circle cx="58" cy="20" r="2"/><circle cx="70" cy="20" r="2"/>\n  <circle cx="82" cy="20" r="2"/><circle cx="94" cy="20" r="2"/><circle cx="106" cy="20" r="2"/>\n  <circle cx="118" cy="20" r="2"/><circle cx="130" cy="20" r="2"/>\n</g>',
    },
    'dryer-rotary': {
        'name': 'Secador rotatorio',
        'category': 'otros',
        'standard': 'ISO 10628',
        'w': 160.0, 'h': 50.0,
        'ports': [
            ('in', 0, 25.0),
            ('out', 160.0, 25.0),
        ],
        'body': '<path d="M 0 10 L 160 22 L 160 40 L 0 28 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="0" y1="19" x2="160" y2="31" stroke="#0d0d0d" stroke-width="0.6" stroke-dasharray="3 2"/>',
    },
    'ejector': {
        'name': 'Eyector / eductor',
        'category': 'otros',
        'standard': 'ISO 10628',
        'w': 100.0, 'h': 60.0,
        'ports': [
            ('in', 0, 30.0),
            ('out', 100.0, 30.0),
        ],
        'body': '<path d="M 0 18 L 30 18 L 50 6 L 70 18 L 100 18 L 100 42 L 70 42 L 50 54 L 30 42 L 0 42 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>',
    },
    'filter-cartridge': {
        'name': 'Filtro de cartucho',
        'category': 'separadores',
        'standard': 'ISO 10628',
        'w': 60.0, 'h': 110.0,
        'ports': [
            ('in', 0, 33.0),
            ('top', 30.0, 0),
            ('bot', 30.0, 110.0),
        ],
        'body': '<rect x="5" y="10" width="50" height="90" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<g stroke="#0d0d0d" stroke-width="0.9" fill="none">\n  <path d="M 14 18 L 22 24 L 14 30 L 22 36 L 14 42 L 22 48 L 14 54 L 22 60 L 14 66 L 22 72 L 14 78 L 22 84 L 14 90"/>\n  <path d="M 46 18 L 38 24 L 46 30 L 38 36 L 46 42 L 38 48 L 46 54 L 38 60 L 46 66 L 38 72 L 46 78 L 38 84 L 46 90"/>\n</g>',
    },
    'fired-heater': {
        'name': 'Horno / calentador a fuego',
        'category': 'reactores',
        'standard': 'ISO 10628',
        'w': 120.0, 'h': 120.0,
        'ports': [
            ('in', 0, 60.0),
            ('out', 120.0, 60.0),
            ('top', 60.0, 0),
        ],
        'body': '<rect x="5" y="10" width="110" height="90" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<path d="M 15 22 L 105 22 L 105 32 L 15 32 L 15 42 L 105 42 L 105 52 L 15 52 L 15 62 L 105 62 L 105 72 L 15 72 L 15 82 L 105 82" fill="none" stroke="#0d0d0d" stroke-width="1.1"/>\n<rect x="50" y="100" width="20" height="14" fill="#fff" stroke="#0d0d0d" stroke-width="1.1"/>\n<path d="M 56 108 L 60 102 L 64 108" fill="none" stroke="#0d0d0d" stroke-width="0.8"/>',
    },
    'flame-arrester': {
        'name': 'Apagallamas',
        'category': 'otros',
        'standard': 'ISO 10628',
        'w': 60.0, 'h': 30.0,
        'ports': [
            ('in', 0, 15.0),
            ('out', 60.0, 15.0),
        ],
        'body': '<rect x="10" y="6" width="40" height="18" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<g stroke="#0d0d0d" stroke-width="0.7">\n  <line x1="14" y1="6" x2="14" y2="24"/><line x1="20" y1="6" x2="20" y2="24"/>\n  <line x1="26" y1="6" x2="26" y2="24"/><line x1="32" y1="6" x2="32" y2="24"/>\n  <line x1="38" y1="6" x2="38" y2="24"/><line x1="44" y1="6" x2="44" y2="24"/>\n</g>',
    },
    'flash-vertical': {
        'name': 'Separador vapor-líquido vertical',
        'category': 'separadores',
        'standard': 'ISO 10628',
        'w': 70.0, 'h': 140.0,
        'ports': [
            ('in', 0.0, 60.0),
            ('vap', 35.0, 0.0),
            ('liq', 35.0, 140.0),
        ],
        'body': '<path d="M 0 22 A 35 22 0 0 1 70 22 L 70 118 A 35 22 0 0 1 0 118 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="6" y1="86" x2="64" y2="86" stroke="#0d0d0d" stroke-width="0.8" stroke-dasharray="3 2"/>\n<path d="M 22 38 L 48 38 L 48 50 L 22 50 Z" fill="none" stroke="#0d0d0d" stroke-width="0.8"/>\n<line x1="22" y1="42" x2="48" y2="42" stroke="#0d0d0d" stroke-width="0.5"/>\n<line x1="22" y1="46" x2="48" y2="46" stroke="#0d0d0d" stroke-width="0.5"/>',
    },
    'flow-venturi': {
        'name': 'Venturi',
        'category': 'otros',
        'standard': 'ISO 5167',
        'w': 80.0, 'h': 40.0,
        'ports': [
            ('in', 0, 20.0),
            ('out', 80.0, 20.0),
        ],
        'body': '<path d="M 0 8 L 30 8 L 40 18 L 80 18 L 80 22 L 40 22 L 30 32 L 0 32 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>',
    },
    'hx-air-cooled': {
        'name': 'Aerorrefrigerante',
        'category': 'intercambiadores',
        'standard': 'ISO 10628 · API 661',
        'w': 140.0, 'h': 100.0,
        'ports': [
            ('in', 0, 50.0),
            ('out', 140.0, 50.0),
        ],
        'body': '<rect x="10" y="40" width="120" height="50" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<g stroke="#0d0d0d" stroke-width="1.1" fill="none">\n  <line x1="20" y1="50" x2="120" y2="50"/>\n  <line x1="20" y1="60" x2="120" y2="60"/>\n  <line x1="20" y1="70" x2="120" y2="70"/>\n  <line x1="20" y1="80" x2="120" y2="80"/>\n</g>\n<circle cx="70" cy="40" r="22" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<path d="M 70 18 Q 80 28 70 40 Q 60 28 70 18 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.1"/>\n<path d="M 92 40 Q 82 50 70 40 Q 82 30 92 40 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.1"/>\n<path d="M 70 62 Q 60 52 70 40 Q 80 52 70 62 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.1"/>\n<path d="M 48 40 Q 58 30 70 40 Q 58 50 48 40 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.1"/>\n<circle cx="70" cy="40" r="3" fill="#0d0d0d"/>',
    },
    'hx-coil-tank': {
        'name': 'Serpentín en tanque',
        'category': 'intercambiadores',
        'standard': 'ISO 10628',
        'w': 100.0, 'h': 120.0,
        'ports': [
            ('in', 0, 60.0),
            ('out', 100.0, 60.0),
        ],
        'body': '<path d="M 5 22 A 25 12 0 0 1 55 22 L 55 98 A 25 12 0 0 1 5 98 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<path d="M 15 32 L 45 32 L 45 42 L 15 42 L 15 52 L 45 52 L 45 62 L 15 62 L 15 72 L 45 72 L 45 82 L 15 82" fill="none" stroke="#0d0d0d" stroke-width="1.1"/>',
    },
    'hx-double-pipe': {
        'name': 'Doble tubo',
        'category': 'intercambiadores',
        'standard': 'ISO 10628',
        'w': 140.0, 'h': 70.0,
        'ports': [
            ('in', 0, 35.0),
            ('out', 140.0, 35.0),
        ],
        'body': '<rect x="0" y="20" width="140" height="30" rx="15" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="14" y1="28" x2="126" y2="28" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="14" y1="42" x2="126" y2="42" stroke="#0d0d0d" stroke-width="1.1"/>',
    },
    'hx-kettle': {
        'name': 'Rehervidor tipo marmita',
        'category': 'intercambiadores',
        'standard': 'ISO 10628 · TEMA K',
        'w': 160.0, 'h': 90.0,
        'ports': [
            ('tube-in', 0.0, 45.0),
            ('tube-out', 160.0, 45.0),
            ('vap-out', 80.0, 0.0),
            ('liq-out', 80.0, 90.0),
        ],
        'body': '<path d="M 0 30 L 160 30 L 160 60 A 20 30 0 0 1 140 90 L 20 90 A 20 30 0 0 1 0 60 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="0" y1="30" x2="0" y2="60" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="160" y1="30" x2="160" y2="60" stroke="#0d0d0d" stroke-width="1.6"/>\n<path d="M 20 50 L 140 50 A 8 8 0 0 1 140 66 L 20 66" fill="none" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="20" y1="70" x2="140" y2="70" stroke="#0d0d0d" stroke-width="0.6" stroke-dasharray="3 2"/>',
    },
    'hx-plate': {
        'name': 'Intercambiador de placas',
        'category': 'intercambiadores',
        'standard': 'ISO 10628',
        'w': 100.0, 'h': 90.0,
        'ports': [
            ('in', 0, 45.0),
            ('out', 100.0, 45.0),
        ],
        'body': '<rect x="0" y="10" width="100" height="70" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="14" y1="10" x2="14" y2="80" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="28" y1="10" x2="28" y2="80" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="42" y1="10" x2="42" y2="80" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="56" y1="10" x2="56" y2="80" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="70" y1="10" x2="70" y2="80" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="84" y1="10" x2="84" y2="80" stroke="#0d0d0d" stroke-width="1.1"/>',
    },
    'hx-shell-tube': {
        'name': 'Intercambiador haz y carcasa',
        'category': 'intercambiadores',
        'standard': 'ISO 10628 · TEMA',
        'w': 140.0, 'h': 60.0,
        'ports': [
            ('shell-in', 0.0, 30.0),
            ('shell-out', 140.0, 30.0),
            ('tube-in', 42.0, 0.0),
            ('tube-out', 98.0, 60.0),
        ],
        'body': '<rect x="0" y="10" width="140" height="40" rx="20" ry="20" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<path d="M 14 20 L 120 20 A 10 10 0 0 1 120 40 L 14 40" fill="none" stroke="#0d0d0d" stroke-width="1.1" stroke-linecap="round"/>\n<line x1="42" y1="10" x2="42" y2="2" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="98" y1="50" x2="98" y2="58" stroke="#0d0d0d" stroke-width="1.1"/>',
    },
    'hx-utube': {
        'name': 'Intercambiador tipo U',
        'category': 'intercambiadores',
        'standard': 'ISO 10628 · TEMA',
        'w': 140.0, 'h': 60.0,
        'ports': [
            ('in', 0, 30.0),
            ('out', 140.0, 30.0),
        ],
        'body': '<rect x="0" y="10" width="140" height="40" rx="20" ry="20" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<path d="M 14 20 L 115 20 A 8 8 0 0 1 115 36 L 14 36" fill="none" stroke="#0d0d0d" stroke-width="1.1"/>\n<path d="M 14 24 L 115 24 A 4 4 0 0 1 115 32 L 14 32" fill="none" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="14" y1="10" x2="14" y2="50" stroke="#0d0d0d" stroke-width="1.6"/>',
    },
    'hydrocyclone': {
        'name': 'Hidrociclón',
        'category': 'separadores',
        'standard': 'ISO 10628',
        'w': 60.0, 'h': 120.0,
        'ports': [
            ('in', 0, 36.0),
            ('top', 30.0, 0),
            ('bot', 30.0, 120.0),
        ],
        'body': '<path d="M 0 8 L 60 8 L 60 42 L 36 116 L 24 116 L 0 42 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<rect x="24" y="-6" width="12" height="14" fill="#fff" stroke="#0d0d0d" stroke-width="1.1"/>',
    },
    'instr-aux-panel': {
        'name': 'Instrumento panel auxiliar',
        'category': 'instrumentos',
        'standard': 'ISA S5.1 · Panel-mounted (aux)',
        'w': 40.0, 'h': 40.0,
        'ports': [
            ('signal', 20.0, 40.0),
        ],
        'body': '<circle cx="20" cy="20" r="16" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="4" y1="17" x2="36" y2="17" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="4" y1="23" x2="36" y2="23" stroke="#0d0d0d" stroke-width="1.4"/>\n<text x="20" y="14" text-anchor="middle" font-family="\'IBM Plex Sans\', sans-serif" font-size="7" font-weight="700" fill="#0d0d0d">FT</text>\n<text x="20" y="30" text-anchor="middle" font-family="\'IBM Plex Mono\', monospace" font-size="7" fill="#0d0d0d">103</text>',
    },
    'instr-computer': {
        'name': 'Función computacional',
        'category': 'instrumentos',
        'standard': 'ISA S5.1 · Computer function',
        'w': 50.0, 'h': 40.0,
        'ports': [
            ('signal', 25.0, 40.0),
        ],
        'body': '<polygon points="6,20 16,4 34,4 44,20 34,36 16,36" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<circle cx="25" cy="20" r="14" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<text x="25" y="18" text-anchor="middle" font-family="\'IBM Plex Sans\', sans-serif" font-size="9" font-weight="700" fill="#0d0d0d">FY</text>\n<text x="25" y="29" text-anchor="middle" font-family="\'IBM Plex Mono\', monospace" font-size="8" fill="#0d0d0d">105</text>',
    },
    'instr-dcs': {
        'name': 'DCS (sistema distribuido)',
        'category': 'instrumentos',
        'standard': 'ISA S5.1 · DCS',
        'w': 40.0, 'h': 40.0,
        'ports': [
            ('signal', 20.0, 40.0),
        ],
        'body': '<rect x="4" y="4" width="32" height="32" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<circle cx="20" cy="20" r="14" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<text x="20" y="18" text-anchor="middle" font-family="\'IBM Plex Sans\', sans-serif" font-size="9" font-weight="700" fill="#0d0d0d">TC</text>\n<text x="20" y="29" text-anchor="middle" font-family="\'IBM Plex Mono\', monospace" font-size="8" fill="#0d0d0d">104</text>',
    },
    'instr-dcs-panel': {
        'name': 'DCS accesible',
        'category': 'instrumentos',
        'standard': 'ISA S5.1 · DCS accessible',
        'w': 40.0, 'h': 40.0,
        'ports': [
            ('signal', 20.0, 40.0),
        ],
        'body': '<rect x="4" y="4" width="32" height="32" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<circle cx="20" cy="20" r="14" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="6" y1="20" x2="34" y2="20" stroke="#0d0d0d" stroke-width="1.4"/>\n<text x="20" y="16" text-anchor="middle" font-family="\'IBM Plex Sans\', sans-serif" font-size="8" font-weight="700" fill="#0d0d0d">TIC</text>\n<text x="20" y="29" text-anchor="middle" font-family="\'IBM Plex Mono\', monospace" font-size="8" fill="#0d0d0d">104</text>',
    },
    'instr-field-local': {
        'name': 'Instrumento local',
        'category': 'instrumentos',
        'standard': 'ISA S5.1 · Locally mounted',
        'w': 40.0, 'h': 40.0,
        'ports': [
            ('signal', 20.0, 40.0),
        ],
        'body': '<circle cx="20" cy="20" r="16" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<text x="20" y="18" text-anchor="middle" font-family="\'IBM Plex Sans\', sans-serif" font-size="9" font-weight="700" fill="#0d0d0d">TI</text>\n<text x="20" y="29" text-anchor="middle" font-family="\'IBM Plex Mono\', monospace" font-size="8" fill="#0d0d0d">101</text>',
    },
    'instr-indicator-light': {
        'name': 'Luz indicadora',
        'category': 'instrumentos',
        'standard': 'ISA S5.1',
        'w': 40.0, 'h': 40.0,
        'ports': [
            ('signal', 20.0, 40.0),
        ],
        'body': '<circle cx="20" cy="20" r="14" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="10" y1="10" x2="30" y2="30" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="30" y1="10" x2="10" y2="30" stroke="#0d0d0d" stroke-width="1.4"/>',
    },
    'instr-panel': {
        'name': 'Instrumento panel principal',
        'category': 'instrumentos',
        'standard': 'ISA S5.1 · Panel-mounted (primary)',
        'w': 40.0, 'h': 40.0,
        'ports': [
            ('signal', 20.0, 40.0),
        ],
        'body': '<circle cx="20" cy="20" r="16" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="4" y1="20" x2="36" y2="20" stroke="#0d0d0d" stroke-width="1.4"/>\n<text x="20" y="16" text-anchor="middle" font-family="\'IBM Plex Sans\', sans-serif" font-size="8" font-weight="700" fill="#0d0d0d">PIC</text>\n<text x="20" y="28" text-anchor="middle" font-family="\'IBM Plex Mono\', monospace" font-size="8" fill="#0d0d0d">102</text>',
    },
    'instr-plc': {
        'name': 'PLC (lógica programable)',
        'category': 'instrumentos',
        'standard': 'ISA S5.1 · PLC',
        'w': 50.0, 'h': 50.0,
        'ports': [
            ('signal', 25.0, 50.0),
        ],
        'body': '<polygon points="25,4 46,25 25,46 4,25" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<circle cx="25" cy="25" r="14" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<text x="25" y="23" text-anchor="middle" font-family="\'IBM Plex Sans\', sans-serif" font-size="9" font-weight="700" fill="#0d0d0d">LSL</text>\n<text x="25" y="33" text-anchor="middle" font-family="\'IBM Plex Mono\', monospace" font-size="8" fill="#0d0d0d">106</text>',
    },
    'mixer-inline': {
        'name': 'Mezclador en línea',
        'category': 'otros',
        'standard': 'ISO 10628',
        'w': 80.0, 'h': 50.0,
        'ports': [
            ('in', 0, 25.0),
            ('out', 80.0, 25.0),
        ],
        'body': '<rect x="0" y="10" width="80" height="30" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="10" y1="10" x2="70" y2="40" stroke="#0d0d0d" stroke-width="1.2"/>\n<line x1="70" y1="10" x2="10" y2="40" stroke="#0d0d0d" stroke-width="1.2"/>',
    },
    'mixer-static': {
        'name': 'Mezclador estático',
        'category': 'otros',
        'standard': 'ISO 10628',
        'w': 120.0, 'h': 50.0,
        'ports': [
            ('in', 0, 25.0),
            ('out', 120.0, 25.0),
        ],
        'body': '<rect x="0" y="15" width="120" height="20" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<path d="M 8 25 Q 18 15 28 25 T 48 25 T 68 25 T 88 25 T 108 25" fill="none" stroke="#0d0d0d" stroke-width="1.2"/>\n<path d="M 8 25 Q 18 35 28 25 T 48 25 T 68 25 T 88 25 T 108 25" fill="none" stroke="#0d0d0d" stroke-width="1.2"/>',
    },
    'orifice-plate': {
        'name': 'Placa de orificio',
        'category': 'otros',
        'standard': 'ISO 5167 · ISA S5.1',
        'w': 50.0, 'h': 30.0,
        'ports': [
            ('in', 0, 15.0),
            ('out', 50.0, 15.0),
        ],
        'body': '<line x1="0" y1="15" x2="50" y2="15" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="25" y1="2" x2="25" y2="28" stroke="#0d0d0d" stroke-width="1.6"/>',
    },
    'pump-centrifugal': {
        'name': 'Bomba centrífuga',
        'category': 'bombas',
        'standard': 'ISA S5.1',
        'w': 80.0, 'h': 70.0,
        'ports': [
            ('in', 0.0, 50.0),
            ('out', 40.0, 0.0),
        ],
        'body': '<circle cx="40" cy="40" r="28" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="40" y1="12" x2="40" y2="0" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="12" y1="50" x2="0" y2="50" stroke="#0d0d0d" stroke-width="1.6"/>\n<polygon points="20,20 60,40 20,60" fill="none" stroke="#0d0d0d" stroke-width="1.4" stroke-linejoin="miter"/>',
    },
    'pump-diaphragm': {
        'name': 'Bomba de diafragma',
        'category': 'bombas',
        'standard': 'ISA S5.1',
        'w': 80.0, 'h': 70.0,
        'ports': [
            ('in', 0, 35.0),
            ('out', 80.0, 35.0),
        ],
        'body': '<circle cx="40" cy="35" r="28" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<path d="M 16 35 Q 40 18 64 35" fill="none" stroke="#0d0d0d" stroke-width="1.4"/>\n<path d="M 16 35 Q 40 52 64 35" fill="none" stroke="#0d0d0d" stroke-width="1.4"/>',
    },
    'pump-gear': {
        'name': 'Bomba de engranajes',
        'category': 'bombas',
        'standard': 'ISA S5.1',
        'w': 80.0, 'h': 70.0,
        'ports': [
            ('in', 0, 35.0),
            ('out', 80.0, 35.0),
        ],
        'body': '<circle cx="40" cy="35" r="28" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<circle cx="30" cy="35" r="10" fill="none" stroke="#0d0d0d" stroke-width="1.2"/>\n<circle cx="50" cy="35" r="10" fill="none" stroke="#0d0d0d" stroke-width="1.2"/>',
    },
    'pump-positive-displacement': {
        'name': 'Bomba desplazamiento positivo',
        'category': 'bombas',
        'standard': 'ISA S5.1',
        'w': 80.0, 'h': 70.0,
        'ports': [
            ('in', 0, 35.0),
            ('out', 80.0, 35.0),
        ],
        'body': '<circle cx="40" cy="35" r="28" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<rect x="22" y="23" width="36" height="24" fill="none" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="40" y1="7" x2="40" y2="0" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="68" y1="35" x2="80" y2="35" stroke="#0d0d0d" stroke-width="1.6"/>',
    },
    'pump-reciprocating': {
        'name': 'Bomba reciprocante',
        'category': 'bombas',
        'standard': 'ISA S5.1',
        'w': 80.0, 'h': 70.0,
        'ports': [
            ('in', 0, 35.0),
            ('out', 80.0, 35.0),
        ],
        'body': '<circle cx="40" cy="35" r="28" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="20" y1="25" x2="60" y2="25" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="20" y1="35" x2="60" y2="35" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="20" y1="45" x2="60" y2="45" stroke="#0d0d0d" stroke-width="1.4"/>',
    },
    'pump-vacuum': {
        'name': 'Bomba de vacío',
        'category': 'bombas',
        'standard': 'ISA S5.1',
        'w': 80.0, 'h': 70.0,
        'ports': [
            ('in', 0, 35.0),
            ('out', 80.0, 35.0),
        ],
        'body': '<circle cx="40" cy="35" r="28" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<text x="40" y="42" text-anchor="middle" font-family="\'IBM Plex Sans\', sans-serif" font-size="18" font-weight="700" fill="#0d0d0d">V</text>',
    },
    'reactor-cstr': {
        'name': 'Reactor agitado (CSTR)',
        'category': 'reactores',
        'standard': 'ISO 10628',
        'w': 70.0, 'h': 120.0,
        'ports': [
            ('in', 35.0, 5.0),
            ('out', 35.0, 115.0),
            ('jacket', 70.0, 60.0),
        ],
        'body': '<path d="M 5 22 A 30 14 0 0 1 65 22 L 65 98 A 30 14 0 0 1 5 98 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<rect x="26" y="0" width="18" height="12" fill="#fff" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="32" y1="6" x2="38" y2="6" stroke="#0d0d0d" stroke-width="0.6"/>\n<line x1="35" y1="12" x2="35" y2="70" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="20" y1="70" x2="50" y2="70" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="20" y1="65" x2="20" y2="75" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="50" y1="65" x2="50" y2="75" stroke="#0d0d0d" stroke-width="1.6"/>',
    },
    'reactor-fixed-bed': {
        'name': 'Reactor lecho fijo',
        'category': 'reactores',
        'standard': 'ISO 10628',
        'w': 70.0, 'h': 120.0,
        'ports': [
            ('in', 0, 60.0),
            ('out', 70.0, 60.0),
            ('top', 35.0, 0),
        ],
        'body': '<path d="M 5 18 A 30 16 0 0 1 65 18 L 65 102 A 30 16 0 0 1 5 102 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="8" y1="40" x2="62" y2="40" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="8" y1="86" x2="62" y2="86" stroke="#0d0d0d" stroke-width="1.1"/>\n<g stroke="#0d0d0d" stroke-width="0.5">\n  <line x1="10" y1="46" x2="20" y2="56"/><line x1="20" y1="46" x2="30" y2="56"/>\n  <line x1="30" y1="46" x2="40" y2="56"/><line x1="40" y1="46" x2="50" y2="56"/>\n  <line x1="50" y1="46" x2="60" y2="56"/><line x1="10" y1="58" x2="20" y2="68"/>\n  <line x1="20" y1="58" x2="30" y2="68"/><line x1="30" y1="58" x2="40" y2="68"/>\n  <line x1="40" y1="58" x2="50" y2="68"/><line x1="50" y1="58" x2="60" y2="68"/>\n  <line x1="10" y1="70" x2="20" y2="80"/><line x1="20" y1="70" x2="30" y2="80"/>\n  <line x1="30" y1="70" x2="40" y2="80"/><line x1="40" y1="70" x2="50" y2="80"/>\n  <line x1="50" y1="70" x2="60" y2="80"/>\n</g>',
    },
    'reactor-fluid-bed': {
        'name': 'Reactor lecho fluidizado',
        'category': 'reactores',
        'standard': 'ISO 10628',
        'w': 70.0, 'h': 120.0,
        'ports': [
            ('in', 0, 60.0),
            ('out', 70.0, 60.0),
            ('top', 35.0, 0),
        ],
        'body': '<path d="M 5 18 A 30 16 0 0 1 65 18 L 65 102 A 30 16 0 0 1 5 102 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="8" y1="78" x2="62" y2="78" stroke="#0d0d0d" stroke-width="1.1"/>\n<g fill="#0d0d0d">\n  <circle cx="14" cy="42" r="1.4"/><circle cx="26" cy="38" r="1.4"/><circle cx="38" cy="44" r="1.4"/>\n  <circle cx="50" cy="40" r="1.4"/><circle cx="58" cy="46" r="1.4"/><circle cx="20" cy="50" r="1.4"/>\n  <circle cx="32" cy="54" r="1.4"/><circle cx="44" cy="50" r="1.4"/><circle cx="56" cy="56" r="1.4"/>\n  <circle cx="12" cy="60" r="1.4"/><circle cx="24" cy="62" r="1.4"/><circle cx="36" cy="66" r="1.4"/>\n  <circle cx="48" cy="62" r="1.4"/><circle cx="58" cy="68" r="1.4"/><circle cx="18" cy="70" r="1.4"/>\n  <circle cx="30" cy="72" r="1.4"/><circle cx="42" cy="74" r="1.4"/><circle cx="52" cy="72" r="1.4"/>\n</g>',
    },
    'reactor-pfr': {
        'name': 'Reactor tubular (PFR)',
        'category': 'reactores',
        'standard': 'ISO 10628',
        'w': 180.0, 'h': 70.0,
        'ports': [
            ('in', 0, 35.0),
            ('out', 180.0, 35.0),
            ('top', 90.0, 0),
        ],
        'body': '<rect x="0" y="20" width="180" height="30" rx="15" ry="15" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="14" y1="20" x2="14" y2="50" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="166" y1="20" x2="166" y2="50" stroke="#0d0d0d" stroke-width="1.1"/>',
    },
    'rotameter': {
        'name': 'Rotámetro',
        'category': 'otros',
        'standard': 'ISO 10628 · ISA S5.1',
        'w': 30.0, 'h': 70.0,
        'ports': [
            ('in', 0, 35.0),
            ('out', 30.0, 35.0),
        ],
        'body': '<path d="M 4 0 L 26 0 L 22 70 L 8 70 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<polygon points="11,40 19,40 17,48 13,48" fill="#0d0d0d"/>',
    },
    'screen': {
        'name': 'Tamiz / criba',
        'category': 'separadores',
        'standard': 'ISO 10628',
        'w': 120.0, 'h': 60.0,
        'ports': [
            ('in', 0, 18.0),
            ('top', 60.0, 0),
            ('bot', 60.0, 60.0),
        ],
        'body': '<path d="M 0 10 L 120 10 L 110 50 L 10 50 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="6" y1="22" x2="114" y2="22" stroke="#0d0d0d" stroke-width="0.7" stroke-dasharray="2 2"/>\n<line x1="8" y1="36" x2="112" y2="36" stroke="#0d0d0d" stroke-width="0.7" stroke-dasharray="2 2"/>',
    },
    'separator-3phase': {
        'name': 'Separador trifásico',
        'category': 'separadores',
        'standard': 'ISO 10628',
        'w': 160.0, 'h': 70.0,
        'ports': [
            ('in', 0, 21.0),
            ('top', 80.0, 0),
            ('bot', 80.0, 70.0),
        ],
        'body': '<path d="M 18 0 L 142 0 A 18 35 0 0 1 142 70 L 18 70 A 18 35 0 0 1 18 0 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="100" y1="14" x2="100" y2="60" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="18" y1="42" x2="100" y2="42" stroke="#0d0d0d" stroke-width="0.7" stroke-dasharray="3 2"/>\n<line x1="18" y1="28" x2="142" y2="28" stroke="#0d0d0d" stroke-width="0.7" stroke-dasharray="3 2"/>',
    },
    'sight-glass': {
        'name': 'Mirilla / sight glass',
        'category': 'otros',
        'standard': 'ISO 10628',
        'w': 50.0, 'h': 30.0,
        'ports': [
            ('in', 0, 15.0),
            ('out', 50.0, 15.0),
        ],
        'body': '<rect x="0" y="8" width="50" height="14" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="0" y1="8" x2="50" y2="22" stroke="#0d0d0d" stroke-width="0.8"/>\n<line x1="0" y1="22" x2="50" y2="8" stroke="#0d0d0d" stroke-width="0.8"/>',
    },
    'silo': {
        'name': 'Silo (fondo cónico)',
        'category': 'recipientes',
        'standard': 'ISO 10628',
        'w': 100.0, 'h': 120.0,
        'ports': [
            ('top', 50.0, 10.0),
            ('bot', 50.0, 110.0),
        ],
        'body': '<path d="M 15 10 L 85 10 L 85 70 L 50 110 L 15 70 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="15" y1="70" x2="85" y2="70" stroke="#0d0d0d" stroke-width="1.1"/>',
    },
    'steam-trap': {
        'name': 'Trampa de vapor',
        'category': 'otros',
        'standard': 'ISO 10628',
        'w': 50.0, 'h': 40.0,
        'ports': [
            ('in', 0, 20.0),
            ('out', 50.0, 20.0),
        ],
        'body': '<circle cx="25" cy="20" r="14" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<text x="25" y="25" text-anchor="middle" font-family="\'IBM Plex Sans\', sans-serif" font-size="12" font-weight="700" fill="#0d0d0d">T</text>',
    },
    'strainer-y': {
        'name': 'Filtro Y',
        'category': 'otros',
        'standard': 'ISO 10628',
        'w': 60.0, 'h': 50.0,
        'ports': [
            ('in', 0, 25.0),
            ('out', 60.0, 25.0),
        ],
        'body': '<line x1="0" y1="20" x2="60" y2="20" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="20" y1="20" x2="40" y2="40" stroke="#0d0d0d" stroke-width="1.6"/>\n<g stroke="#0d0d0d" stroke-width="0.7">\n  <line x1="22" y1="24" x2="38" y2="40"/>\n  <line x1="26" y1="22" x2="38" y2="36"/>\n  <line x1="30" y1="20" x2="38" y2="32"/>\n</g>',
    },
    'tank-cone-roof': {
        'name': 'Tanque techo cónico',
        'category': 'recipientes',
        'standard': 'ISO 10628 · API 650',
        'w': 100.0, 'h': 120.0,
        'ports': [
            ('top', 50.0, 8.0),
            ('side', 90.0, 60.0),
            ('bot', 90.0, 110.0),
        ],
        'body': '<path d="M 10 30 L 50 8 L 90 30 L 90 110 L 10 110 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="10" y1="30" x2="90" y2="30" stroke="#0d0d0d" stroke-width="1.6"/>',
    },
    'tank-dome-roof': {
        'name': 'Tanque techo bóveda',
        'category': 'recipientes',
        'standard': 'ISO 10628 · API 650',
        'w': 100.0, 'h': 120.0,
        'ports': [
            ('top', 50.0, 0),
            ('bot', 50.0, 120.0),
            ('side', 100.0, 60.0),
        ],
        'body': '<path d="M 10 30 L 10 110 L 90 110 L 90 30 A 40 22 0 0 0 10 30 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<line x1="10" y1="30" x2="90" y2="30" stroke="#0d0d0d" stroke-width="1.1"/>',
    },
    'tank-floating-roof': {
        'name': 'Tanque techo flotante',
        'category': 'recipientes',
        'standard': 'ISO 10628 · API 650',
        'w': 100.0, 'h': 120.0,
        'ports': [
            ('top', 50.0, 0),
            ('bot', 50.0, 120.0),
            ('side', 100.0, 60.0),
        ],
        'body': '<rect x="10" y="20" width="80" height="90" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<rect x="14" y="30" width="72" height="10" fill="#fff" stroke="#0d0d0d" stroke-width="1.1"/>\n<line x1="16" y1="35" x2="84" y2="35" stroke="#0d0d0d" stroke-width="0.6" stroke-dasharray="2 2"/>',
    },
    'tank-open': {
        'name': 'Tanque abierto',
        'category': 'recipientes',
        'standard': 'ISO 10628',
        'w': 100.0, 'h': 120.0,
        'ports': [
            ('top', 50.0, 0),
            ('bot', 50.0, 120.0),
            ('side', 100.0, 60.0),
        ],
        'body': '<path d="M 10 20 L 10 110 L 90 110 L 90 20" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>',
    },
    'turbine': {
        'name': 'Turbina',
        'category': 'compresores',
        'standard': 'ISO 10628',
        'w': 100.0, 'h': 70.0,
        'ports': [
            ('in', 0, 35.0),
            ('out', 100.0, 35.0),
        ],
        'body': '<polygon points="5,10 95,30 95,40 5,60" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>',
    },
    'valve-3way': {
        'name': 'Válvula 3 vías',
        'category': 'valvulas',
        'standard': 'ISA S5.1',
        'w': 40.0, 'h': 40.0,
        'ports': [
            ('in', 0, 20.0),
            ('out', 40.0, 20.0),
        ],
        'body': '<polygon points="0,8 20,18 0,28" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<polygon points="40,8 20,18 40,28" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<polygon points="12,40 20,18 28,40" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>',
    },
    'valve-ball': {
        'name': 'Válvula de bola',
        'category': 'valvulas',
        'standard': 'ISA S5.1',
        'w': 40.0, 'h': 26.0,
        'ports': [
            ('in', 0, 13.0),
            ('out', 40.0, 13.0),
        ],
        'body': '<polygon points="0,3 20,13 0,23" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<polygon points="40,3 20,13 40,23" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<circle cx="20" cy="13" r="6" fill="#0d0d0d"/>',
    },
    'valve-butterfly': {
        'name': 'Válvula de mariposa',
        'category': 'valvulas',
        'standard': 'ISA S5.1',
        'w': 40.0, 'h': 26.0,
        'ports': [
            ('in', 0, 13.0),
            ('out', 40.0, 13.0),
        ],
        'body': '<polygon points="0,3 20,13 0,23" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<polygon points="40,3 20,13 40,23" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="20" y1="0" x2="20" y2="26" stroke="#0d0d0d" stroke-width="1.4"/>\n<circle cx="20" cy="13" r="2" fill="#0d0d0d"/>',
    },
    'valve-check': {
        'name': 'Válvula de retención (check)',
        'category': 'valvulas',
        'standard': 'ISA S5.1',
        'w': 40.0, 'h': 26.0,
        'ports': [
            ('in', 0, 13.0),
            ('out', 40.0, 13.0),
        ],
        'body': '<polygon points="0,3 20,13 0,23" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<polygon points="40,3 20,13 40,23" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="20" y1="3" x2="20" y2="23" stroke="#0d0d0d" stroke-width="1.4"/>',
    },
    'valve-control-motor': {
        'name': 'Válvula de control motorizada',
        'category': 'valvulas',
        'standard': 'ISA S5.1',
        'w': 40.0, 'h': 50.0,
        'ports': [
            ('in', 0, 25.0),
            ('out', 40.0, 25.0),
        ],
        'body': '<polygon points="0,30 20,40 0,50" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<polygon points="40,30 20,40 40,50" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="20" y1="40" x2="20" y2="20" stroke="#0d0d0d" stroke-width="1.4"/>\n<circle cx="20" cy="14" r="10" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<text x="20" y="19" text-anchor="middle" font-family="\'IBM Plex Sans\', sans-serif" font-size="11" font-weight="700" fill="#0d0d0d">M</text>',
    },
    'valve-control-pneumatic': {
        'name': 'Válvula de control neumática',
        'category': 'valvulas',
        'standard': 'ISA S5.1',
        'w': 40.0, 'h': 50.0,
        'ports': [
            ('in', 0, 25.0),
            ('out', 40.0, 25.0),
        ],
        'body': '<polygon points="0,30 20,40 0,50" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<polygon points="40,30 20,40 40,50" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="20" y1="40" x2="20" y2="20" stroke="#0d0d0d" stroke-width="1.4"/>\n<path d="M 6 10 A 14 10 0 0 1 34 10 L 34 20 L 6 20 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="6" y1="15" x2="34" y2="15" stroke="#0d0d0d" stroke-width="0.8"/>',
    },
    'valve-gate': {
        'name': 'Válvula de compuerta',
        'category': 'valvulas',
        'standard': 'ISA S5.1',
        'w': 40.0, 'h': 26.0,
        'ports': [
            ('in', 0, 13.0),
            ('out', 40.0, 13.0),
        ],
        'body': '<polygon points="0,3 20,13 0,23" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<polygon points="40,3 20,13 40,23" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>',
    },
    'valve-globe': {
        'name': 'Válvula de globo',
        'category': 'valvulas',
        'standard': 'ISA S5.1',
        'w': 40.0, 'h': 26.0,
        'ports': [
            ('in', 0, 13.0),
            ('out', 40.0, 13.0),
        ],
        'body': '<polygon points="0,3 20,13 0,23" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<polygon points="40,3 20,13 40,23" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<circle cx="20" cy="13" r="5" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>',
    },
    'valve-needle': {
        'name': 'Válvula de aguja',
        'category': 'valvulas',
        'standard': 'ISA S5.1',
        'w': 40.0, 'h': 26.0,
        'ports': [
            ('in', 0, 13.0),
            ('out', 40.0, 13.0),
        ],
        'body': '<polygon points="0,3 20,13 0,23" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<polygon points="40,3 20,13 40,23" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="20" y1="3" x2="20" y2="13" stroke="#0d0d0d" stroke-width="2.2"/>',
    },
    'valve-plug': {
        'name': 'Válvula de macho',
        'category': 'valvulas',
        'standard': 'ISA S5.1',
        'w': 40.0, 'h': 26.0,
        'ports': [
            ('in', 0, 13.0),
            ('out', 40.0, 13.0),
        ],
        'body': '<polygon points="0,3 20,13 0,23" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<polygon points="40,3 20,13 40,23" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<polygon points="14,13 20,7 26,13 20,19" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>',
    },
    'valve-relief': {
        'name': 'Válvula de alivio / seguridad',
        'category': 'valvulas',
        'standard': 'ISA S5.1',
        'w': 40.0, 'h': 50.0,
        'ports': [
            ('in', 0, 25.0),
            ('out', 40.0, 25.0),
        ],
        'body': '<polygon points="0,30 20,40 0,50" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<polygon points="40,30 20,40 40,50" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="20" y1="40" x2="20" y2="22" stroke="#0d0d0d" stroke-width="1.4"/>\n<rect x="14" y="10" width="12" height="12" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="20" y1="22" x2="20" y2="10" stroke="#0d0d0d" stroke-width="0.8" stroke-dasharray="2 1"/>\n<line x1="20" y1="10" x2="34" y2="0" stroke="#0d0d0d" stroke-width="1.4"/>',
    },
    'valve-solenoid': {
        'name': 'Válvula solenoide',
        'category': 'valvulas',
        'standard': 'ISA S5.1',
        'w': 40.0, 'h': 50.0,
        'ports': [
            ('in', 0, 25.0),
            ('out', 40.0, 25.0),
        ],
        'body': '<polygon points="0,30 20,40 0,50" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<polygon points="40,30 20,40 40,50" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<line x1="20" y1="40" x2="20" y2="22" stroke="#0d0d0d" stroke-width="1.4"/>\n<rect x="10" y="10" width="20" height="12" fill="#fff" stroke="#0d0d0d" stroke-width="1.4"/>\n<text x="20" y="20" text-anchor="middle" font-family="\'IBM Plex Sans\', sans-serif" font-size="10" font-weight="700" fill="#0d0d0d">S</text>',
    },
    'vessel-horizontal': {
        'name': 'Recipiente horizontal',
        'category': 'recipientes',
        'standard': 'ISO 10628',
        'w': 140.0, 'h': 60.0,
        'ports': [
            ('in', 0.0, 30.0),
            ('out', 140.0, 30.0),
            ('top', 70.0, 0.0),
            ('bot', 70.0, 60.0),
        ],
        'body': '<path d="M 18 0 L 122 0 A 18 30 0 0 1 122 60 L 18 60 A 18 30 0 0 1 18 0 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>',
    },
    'vessel-jacketed': {
        'name': 'Recipiente encamisado',
        'category': 'recipientes',
        'standard': 'ISO 10628',
        'w': 70.0, 'h': 120.0,
        'ports': [
            ('top', 35.0, 0),
            ('bot', 35.0, 120.0),
            ('side', 70.0, 60.0),
        ],
        'body': '<path d="M 0 22 A 35 22 0 0 1 70 22 L 70 98 A 35 22 0 0 1 0 98 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>\n<path d="M 6 28 A 29 16 0 0 1 64 28 L 64 92 A 29 16 0 0 1 6 92 Z" fill="none" stroke="#0d0d0d" stroke-width="1.1"/>',
    },
    'vessel-sphere': {
        'name': 'Esfera a presión',
        'category': 'recipientes',
        'standard': 'ISO 10628',
        'w': 100.0, 'h': 100.0,
        'ports': [
            ('top', 50.0, 10.0),
            ('bot', 50.0, 90.0),
        ],
        'body': '<circle cx="50" cy="50" r="40" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>',
    },
    'vessel-vertical': {
        'name': 'Recipiente vertical',
        'category': 'recipientes',
        'standard': 'ISO 10628',
        'w': 60.0, 'h': 120.0,
        'ports': [
            ('top', 30.0, 0.0),
            ('bot', 30.0, 120.0),
            ('side', 60.0, 60.0),
        ],
        'body': '<path d="M 0 18 A 30 18 0 0 1 60 18 L 60 102 A 30 18 0 0 1 0 102 Z" fill="#fff" stroke="#0d0d0d" stroke-width="1.6"/>',
    },
}

EQ_TYPE_TO_SYMBOL: Dict[str, str] = {
    'Heat exch. — fixed tube': 'hx-shell-tube',
    'Heat exch. — U-tube': 'hx-utube',
    'Heat exch. — floating head': 'hx-shell-tube',
    'Heat exch. — kettle reboiler': 'hx-kettle',
    'Heat exch. — double pipe': 'hx-double-pipe',
    'Heat exch. — multiple pipe': 'hx-double-pipe',
    'Heat exch. — air cooler': 'hx-air-cooled',
    'Heat exch. — flat plate': 'hx-plate',
    'Heat exch. — spiral plate': 'hx-plate',
    'Pump — centrifugal': 'pump-centrifugal',
    'Pump — positive displacement': 'pump-positive-displacement',
    'Pump — reciprocating': 'pump-reciprocating',
    'Compressor — centrifugal': 'compressor-centrifugal',
    'Compressor — axial': 'compressor-centrifugal',
    'Compressor — reciprocating': 'compressor-reciprocating',
    'Compressor — rotary': 'compressor-centrifugal',
    'Reactor — autoclave': 'reactor-cstr',
    'Reactor — jacketed agitated': 'reactor-cstr',
    'Reactor — jacketed non-agit.': 'reactor-fixed-bed',
    'Vessel — horizontal': 'vessel-horizontal',
    'Vessel — vertical': 'vessel-vertical',
    'Tower (column shell)': 'column-tray',
    'Storage tank — cone roof': 'tank-cone-roof',
    'Storage tank — floating roof': 'tank-floating-roof',
    'Fired heater — reformer': 'fired-heater',
    'Fired heater — non-reformer': 'fired-heater',
    'Fan — centrifugal radial': 'blower',
    'Fan — axial': 'blower',
    'Crystallizer': 'crystallizer',
    'Dryer — drum': 'dryer-rotary',
    'Evaporator — vertical': 'flash-vertical',
    'Filter — belt': 'filter-cartridge',
    'Tray — sieve': 'column-tray',
    'Tray — valve': 'column-tray',
    # Mixers / splitters / nuevos separadores / válvulas — reuso de
    # SVGs del catálogo lib-symbols (ya parseados arriba).
    'Mixer — inline':                  'mixer-inline',
    'Mixer — static':                  'mixer-static',
    'Splitter — flow divider':         'mixer-inline',     # proxy
    'Centrifuge — disc stack':         'centrifuge',
    'Centrifuge — decanter':           'centrifuge',
    'Cyclone — gas/solid':             'cyclone',
    'Decanter — gravity':              'decanter',
    'Valve — control globe':           'valve-control-pneumatic',
    'Valve — relief':                  'valve-relief',
    'Valve — 3-way':                   'valve-3way',

    # Utilities: reusamos símbolos existentes para no inventar SVGs
    'Boiler — fire tube':              'fired-heater',
    'Boiler — water tube':             'fired-heater',
    'Cooling tower — induced draft':   'column-stripper',
    'Cooling tower — natural draft':   'column-stripper',
}


def _parse_path_endpoints(d: str) -> Tuple[List[float], List[float]]:
    """Parser SVG path command-aware.  Devuelve (xs, ys) con los
    endpoints (x, y) de cada comando.

    Maneja correctamente M/L/H/V/A/C/S/Q/T/Z absolutos y relativos.
    Para Arc (A), también incluye las cotas de los radios (cur ± rx,
    cur ± ry) para aproximar la extensión real del arco.

    Esto evita el bug del parser ingenuo que trata flags de comando
    A (large-arc, sweep) como coords.
    """
    import re
    xs: List[float] = []
    ys: List[float] = []
    # tokens: comando o número
    pattern = re.compile(r'([MmLlHhVvCcSsQqTtAaZz])|(-?\d+(?:\.\d+)?)')
    cur_x = cur_y = 0.0
    cmd: str = ""
    nums: List[float] = []

    def flush_cmd():
        # NOTA: xs.extend() en vez de xs += [...] para evitar que
        # Python trate a xs/ys como locales (closure binding).
        nonlocal cur_x, cur_y
        if not cmd:
            return
        c = cmd.upper()
        rel = cmd.islower()
        if c in ('M', 'L', 'T'):
            # Pares (x, y).  M con múltiples pares = M + Ls implícitos.
            for i in range(0, len(nums) - 1, 2):
                x, y = nums[i], nums[i+1]
                if rel:
                    cur_x += x; cur_y += y
                else:
                    cur_x = x; cur_y = y
                xs.append(cur_x); ys.append(cur_y)
        elif c == 'H':
            for v in nums:
                cur_x = (cur_x + v) if rel else v
                xs.append(cur_x); ys.append(cur_y)
        elif c == 'V':
            for v in nums:
                cur_y = (cur_y + v) if rel else v
                xs.append(cur_x); ys.append(cur_y)
        elif c == 'A':
            # rx ry x-rot large-arc-flag sweep-flag x y  →  7 nums por arc
            for i in range(0, len(nums) - 6, 7):
                rx, ry = nums[i], nums[i+1]
                ex, ey = nums[i+5], nums[i+6]
                if rel:
                    cur_x += ex; cur_y += ey
                else:
                    cur_x = ex; cur_y = ey
                xs.append(cur_x); ys.append(cur_y)
                # cotas aproximadas del arco
                xs.extend([cur_x - rx, cur_x + rx])
                ys.extend([cur_y - ry, cur_y + ry])
        elif c == 'C':
            # x1 y1 x2 y2 x y  →  6 nums por bezier
            for i in range(0, len(nums) - 5, 6):
                x1, y1, x2, y2, ex, ey = nums[i:i+6]
                # incluir control points aproximados
                if rel:
                    xs.extend([cur_x + x1, cur_x + x2])
                    ys.extend([cur_y + y1, cur_y + y2])
                    cur_x += ex; cur_y += ey
                else:
                    xs.extend([x1, x2]); ys.extend([y1, y2])
                    cur_x = ex; cur_y = ey
                xs.append(cur_x); ys.append(cur_y)
        elif c in ('S', 'Q'):
            # 4 nums por segmento
            for i in range(0, len(nums) - 3, 4):
                x1, y1, ex, ey = nums[i:i+4]
                if rel:
                    cur_x += ex; cur_y += ey
                else:
                    cur_x = ex; cur_y = ey
                xs.append(cur_x); ys.append(cur_y)
        # Z: no consume nums, no actualiza cur_*

    for m in pattern.finditer(d):
        if m.group(1):           # nuevo comando → flush el anterior
            flush_cmd()
            cmd = m.group(1)
            nums = []
        elif m.group(2):
            nums.append(float(m.group(2)))
    flush_cmd()
    return xs, ys


def _svg_content_bbox(body: str) -> Optional[Tuple[float, float, float, float]]:
    """Parsea el SVG body y devuelve (x_min, y_min, x_max, y_max) del
    bounding box de TODO lo que se dibuja.  Usado para 'apretar' el
    viewBox al contenido visible (eliminar márgenes y hacer que el
    símbolo llene el bloque).

    Cubre <rect>, <line>, <circle>, <ellipse>, <path> (M/L absolutos).
    Path parsing es rough — extrae números como pares x/y alternando.
    """
    import re
    xs, ys = [], []

    def _opt_float(s, key, default=0.0):
        m = re.search(rf'{key}="([^"]+)"', s)
        return float(m.group(1)) if m else default

    # rect
    for m in re.finditer(r'<rect\b[^>]*>', body):
        attrs = m.group()
        x = _opt_float(attrs, 'x'); y = _opt_float(attrs, 'y')
        w = _opt_float(attrs, 'width'); h = _opt_float(attrs, 'height')
        xs += [x, x + w]; ys += [y, y + h]
    # line
    for m in re.finditer(r'<line\b[^>]*>', body):
        attrs = m.group()
        xs += [_opt_float(attrs, 'x1'), _opt_float(attrs, 'x2')]
        ys += [_opt_float(attrs, 'y1'), _opt_float(attrs, 'y2')]
    # circle / ellipse
    for m in re.finditer(r'<(?:circle|ellipse)\b[^>]*>', body):
        attrs = m.group()
        cx = _opt_float(attrs, 'cx'); cy = _opt_float(attrs, 'cy')
        if 'r="' in attrs:
            r = _opt_float(attrs, 'r')
            rx = ry = r
        else:
            rx = _opt_float(attrs, 'rx'); ry = _opt_float(attrs, 'ry')
        xs += [cx - rx, cx + rx]; ys += [cy - ry, cy + ry]
    # polygon / polyline points="x1,y1 x2,y2 …"
    for m in re.finditer(r'<(?:polygon|polyline)\b[^>]*>', body):
        attrs = m.group()
        pm = re.search(r'points="([^"]+)"', attrs)
        if pm:
            nums = re.findall(r'-?\d+(?:\.\d+)?', pm.group(1))
            for i, v_str in enumerate(nums):
                v = float(v_str)
                if i % 2 == 0:
                    xs.append(v)
                else:
                    ys.append(v)
    # path d="..."  — parser command-aware (skip flags de Arc, etc.)
    for m in re.finditer(r'd="([^"]+)"', body):
        path_xs, path_ys = _parse_path_endpoints(m.group(1))
        xs.extend(path_xs)
        ys.extend(path_ys)

    if not xs or not ys:
        return None
    return min(xs), min(ys), max(xs), max(ys)


_BBOX_CACHE: Dict[str, Optional[Tuple[float, float, float, float]]] = {}


def content_bbox(symbol_id: str) -> Optional[Tuple[float, float, float, float]]:
    """Devuelve el bbox del contenido del símbolo, con cache."""
    if symbol_id in _BBOX_CACHE:
        return _BBOX_CACHE[symbol_id]
    s = SYMBOLS.get(symbol_id)
    if s is None:
        _BBOX_CACHE[symbol_id] = None
        return None
    bbox = _svg_content_bbox(s["body"])
    # Validar: bbox debe estar DENTRO o cerca del viewBox original.
    # Si el parser falla y devuelve algo absurdo, fall-through al viewBox.
    if bbox:
        x_min, y_min, x_max, y_max = bbox
        vb_w, vb_h = s["w"], s["h"]
        # clamp al viewBox (en caso de path con coords fuera)
        x_min = max(0.0, min(x_min, vb_w))
        y_min = max(0.0, min(y_min, vb_h))
        x_max = max(0.0, min(x_max, vb_w))
        y_max = max(0.0, min(y_max, vb_h))
        if x_max - x_min < 5 or y_max - y_min < 5:
            bbox = None  # bbox demasiado chico, descartar
        else:
            bbox = (x_min, y_min, x_max, y_max)
    _BBOX_CACHE[symbol_id] = bbox
    return bbox


def get(symbol_id: str) -> Optional[dict]:
    """Devuelve los datos del símbolo, o None si no existe."""
    return SYMBOLS.get(symbol_id)


def get_for_eq_type(eq_type: str) -> Optional[dict]:
    """Devuelve los datos del símbolo asociado a un eq_type, o None."""
    sid = EQ_TYPE_TO_SYMBOL.get(eq_type)
    if sid is None:
        return None
    return SYMBOLS.get(sid)


def wrap_svg(symbol_id: str, w: Optional[float] = None,
             h: Optional[float] = None) -> Optional[str]:
    """SVG completo listo para QSvgRenderer.

    Usa el bbox del contenido como viewBox (no el viewBox nominal),
    para que el dibujo LLENE el output rect sin márgenes vacíos.
    Si el bbox no se puede determinar, cae al viewBox original.

    Si w/h se especifican, sobrescriben las dimensiones de salida.
    """
    d = SYMBOLS.get(symbol_id)
    if d is None:
        return None
    # Usar el bbox del contenido como viewBox: el dibujo llena el output.
    bbox = content_bbox(symbol_id)
    if bbox:
        x0, y0, x1, y1 = bbox
        # margen chico (5% de cada lado) para que la stroke no se corte
        mx = (x1 - x0) * 0.04
        my = (y1 - y0) * 0.04
        vb_x = x0 - mx
        vb_y = y0 - my
        vb_w = (x1 - x0) + 2 * mx
        vb_h = (y1 - y0) + 2 * my
    else:
        vb_x = vb_y = 0
        vb_w, vb_h = d["w"], d["h"]
    # Output: si el caller pasó w/h, usar esos.  Si no, usar el bbox dims.
    out_w = w if w is not None else vb_w
    out_h = h if h is not None else vb_h
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{vb_x:g} {vb_y:g} {vb_w:g} {vb_h:g}" '
        f'width="{out_w:g}" height="{out_h:g}">'
        f'{d["body"]}'
        f'</svg>'
    )


def list_categories() -> List[str]:
    """Lista única de categorías presentes."""
    return sorted(set(d["category"] for d in SYMBOLS.values()))


def list_by_category(category: str) -> List[str]:
    """IDs de símbolos de una categoría."""
    return sorted(sid for sid, d in SYMBOLS.items() if d["category"] == category)


# ======================================================
# DIMENSIONES Y PUERTOS POR eq_type
# ======================================================
# Helpers para que el render (BlockItem) y el router (StreamItem) usen
# las dimensiones del símbolo PFD asociado al eq_type, en vez de
# constantes BLOCK_W/BLOCK_H.

# Fallback cuando un eq_type no tiene símbolo en el catálogo.
DEFAULT_W = 130.0
DEFAULT_H = 60.0


def block_dims(eq_type: str) -> Tuple[float, float]:
    """Devuelve (w, h) del bloque para este eq_type.

    Usa el bbox del contenido del símbolo (no el viewBox nominal),
    así el bloque tiene exactamente las dimensiones del dibujo y
    no quedan márgenes vacíos.  Los puertos quedan al borde del
    dibujo.  Fallback al viewBox si el parser no puede determinar
    el bbox.
    """
    s = get_for_eq_type(eq_type)
    if s is None:
        return (DEFAULT_W, DEFAULT_H)
    sid = EQ_TYPE_TO_SYMBOL.get(eq_type)
    if sid:
        bbox = content_bbox(sid)
        if bbox:
            x0, y0, x1, y1 = bbox
            # mismo margen 4% que en wrap_svg para coherencia
            mx = (x1 - x0) * 0.04
            my = (y1 - y0) * 0.04
            return ((x1 - x0) + 2 * mx, (y1 - y0) + 2 * my)
    return (s["w"], s["h"])


def port_coords(eq_type: str,
                 w: Optional[float] = None,
                 h: Optional[float] = None
                 ) -> Dict[str, Tuple[float, float]]:
    """Devuelve {port_name: (x, y)} en coordenadas absolutas del bloque,
    combinando los lados+fracciones de equipment_ports.py con el (w, h)
    del símbolo PFD (que en general varía por equipo).

    Si w/h no se especifican, los toma de block_dims(eq_type).
    Si un side no es reconocido, se devuelve (0, h/2) como fallback.
    """
    if w is None or h is None:
        bw, bh = block_dims(eq_type)
        w = bw if w is None else w
        h = bh if h is None else h

    try:
        import equipment_ports as ep
    except ImportError:
        return {}

    out: Dict[str, Tuple[float, float]] = {}
    for name, (side, frac) in ep.get_ports(eq_type).items():
        if side == "left":
            out[name] = (0.0, h * frac)
        elif side == "right":
            out[name] = (w, h * frac)
        elif side == "top":
            out[name] = (w * frac, 0.0)
        elif side == "bottom":
            out[name] = (w * frac, h)
        else:
            out[name] = (0.0, h / 2)
    return out


def port_side(eq_type: str, port_name: str) -> str:
    """Lado del puerto ('left'|'right'|'top'|'bottom'), o 'right' si
    no se encuentra (default).  Útil para el router que decide la
    dirección de salida."""
    try:
        import equipment_ports as ep
    except ImportError:
        return "right"
    ports = ep.get_ports(eq_type)
    info = ports.get(port_name)
    if info is None:
        return "right"
    return info[0]
