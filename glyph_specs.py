"""glyph_specs.py — geometría de los glifos ISA del ciclo 3 (Design).

Los 48 símbolos del bundle `docs/design_ciclo3/` embebidos VERBATIM
(viewBox 0 0 100 100) + un parser del subset SVG que usan y el
renderer QPainter.  Las clases del spec mapean 1:1 al sistema:

    o    → trazo contorno  (STROKE_OUTLINE, tinta del estado)
    d    → trazo detalle   (STROKE_DETAIL, tinta al 52 % — spec 3a)
    body → fill del estado (bg_elev / green_bg / amber_bg / danger_bg)
    dot  → relleno de tinta-detalle sin trazo

El estado "unrun" puntea los trazos `o` (el caller lo señala con el
pen DashLine, contrato de BlockGlyph.draw); los `stroke-dasharray`
explícitos del spec (lecho catalítico del jacketed no-agitado) se
respetan siempre.

Subset SVG soportado: rect(rx) · circle · ellipse · line ·
path(M L H V Q A Z l) · <g class> de un nivel.  Sin dependencias de
Qt a nivel de módulo salvo en el renderer (lazy).
"""
from __future__ import annotations

import re as _re
from functools import lru_cache

# ─────────────────────────────────────────────────────────────────────
#  GEOMETRÍA (verbatim del bundle de Design — no editar a mano; si
#  Design entrega un refresh, re-extraer de docs/design_ciclo3/)
# ─────────────────────────────────────────────────────────────────────

SVG_SRC = {
    'bomba':
        '<circle class="body o" cx="50" cy="46" r="26"/><path class="d" d="M40 34 L66 46 L40 58 Z"/><circle class="dot" cx="50" cy="46" r="2.4"/><line class="o" x1="34" y1="82" x2="66" y2="82"/>',
    'bomba_pd':
        '<circle class="body o" cx="50" cy="46" r="26"/><circle class="d" cx="42" cy="46" r="10"/><circle class="d" cx="58" cy="46" r="10"/><line class="o" x1="34" y1="82" x2="66" y2="82"/>',
    'bomba_recip':
        '<rect class="body o" x="16" y="32" width="42" height="28" rx="3"/><line class="d" x1="38" y1="34" x2="38" y2="58"/><line class="d" x1="46" y1="34" x2="46" y2="58"/><line class="o" x1="46" y1="46" x2="72" y2="46"/><circle class="body o" cx="80" cy="46" r="9"/><circle class="dot" cx="77" cy="43" r="1.8"/><line class="o" x1="30" y1="82" x2="72" y2="82"/>',
    'compresor':
        '<path class="body o" d="M22 24 L78 40 L78 60 L22 76 Z"/><path class="d" d="M32 50 H64 M56 44 L64 50 L56 56"/><line class="o" x1="36" y1="86" x2="64" y2="86"/>',
    'compresor_axial':
        '<rect class="body o" x="20" y="34" width="60" height="32" rx="2"/><path class="d" d="M30 38 L38 62 M42 38 L50 62 M54 38 L62 62 M66 38 L74 62"/><line class="o" x1="34" y1="80" x2="66" y2="80"/>',
    'compresor_rotary':
        '<circle class="body o" cx="50" cy="46" r="27"/><ellipse class="d" cx="43" cy="46" rx="8" ry="14"/><ellipse class="d" cx="57" cy="46" rx="8" ry="14"/><line class="o" x1="34" y1="82" x2="66" y2="82"/>',
    'compresor_recip':
        '<rect class="body o" x="16" y="36" width="42" height="26" rx="3"/><circle class="body o" cx="37" cy="22" r="9"/><line class="d" x1="34" y1="38" x2="34" y2="60"/><line class="d" x1="42" y1="38" x2="42" y2="60"/><line class="o" x1="50" y1="49" x2="72" y2="49"/><circle class="body o" cx="80" cy="49" r="8"/><line class="o" x1="30" y1="82" x2="72" y2="82"/>',
    'valvula_globe':
        '<path class="body o" d="M18 46 L18 70 L50 58 Z"/><path class="body o" d="M82 46 L82 70 L50 58 Z"/><line class="d" x1="50" y1="58" x2="50" y2="32"/><path class="body o" d="M37 32 A13 13 0 0 1 63 32 Z"/><line class="d" x1="37" y1="32" x2="63" y2="32"/>',
    'valvula_3way':
        '<path class="body o" d="M18 30 L18 54 L50 42 Z"/><path class="body o" d="M82 30 L82 54 L50 42 Z"/><path class="body o" d="M38 78 L62 78 L50 42 Z"/>',
    'valvula_relief':
        '<path class="body o" d="M34 82 L58 82 L46 54 Z"/><line class="o" x1="46" y1="54" x2="78" y2="54"/><path class="d" d="M72 48 L80 54 L72 60"/><path class="d" d="M46 54 V44 M40 44 L52 40 L40 36 L52 32 L40 28 L52 24"/>',
    'reactor_cstr':
        '<rect class="body o" x="24" y="20" width="52" height="52" rx="7"/><rect class="dot" x="45" y="6" width="10" height="7"/><line class="d" x1="50" y1="13" x2="50" y2="56"/><line class="o" x1="39" y1="56" x2="61" y2="56"/><line class="d" x1="43" y1="50" x2="57" y2="62"/><line class="d" x1="36" y1="72" x2="36" y2="80"/><line class="d" x1="64" y1="72" x2="64" y2="80"/>',
    'reactor_jacket':
        '<rect class="body o" x="20" y="18" width="60" height="56" rx="7"/><rect class="d" x="27" y="24" width="46" height="44" rx="4"/><rect class="dot" x="45" y="4" width="10" height="7"/><line class="d" x1="50" y1="11" x2="50" y2="54"/><line class="o" x1="40" y1="54" x2="60" y2="54"/>',
    'reactor_jacket_na':
        '<rect class="body o" x="20" y="18" width="60" height="56" rx="7"/><rect class="d" x="27" y="24" width="46" height="44" rx="4"/><line class="d" x1="35" y1="28" x2="35" y2="64" stroke-dasharray="2 3"/><line class="d" x1="43" y1="28" x2="43" y2="64" stroke-dasharray="2 3"/><line class="d" x1="50" y1="28" x2="50" y2="64" stroke-dasharray="2 3"/><line class="d" x1="57" y1="28" x2="57" y2="64" stroke-dasharray="2 3"/><line class="d" x1="65" y1="28" x2="65" y2="64" stroke-dasharray="2 3"/>',
    'reactor_autoclave':
        '<rect class="body o" x="28" y="12" width="44" height="76" rx="21"/><rect class="d" x="35" y="19" width="30" height="62" rx="14"/>',
    'reactor_pfr':
        '<rect class="body o" x="14" y="38" width="72" height="24" rx="11"/><path class="d" d="M22 50 Q30 30 38 50 Q46 70 54 50 Q62 30 70 50"/><path class="d" d="M74 50 H84"/>',
    'caldera_fire':
        '<rect class="body o" x="18" y="30" width="64" height="40" rx="15"/><line class="d" x1="28" y1="42" x2="72" y2="42"/><line class="d" x1="28" y1="50" x2="72" y2="50"/><line class="d" x1="28" y1="58" x2="72" y2="58"/><path class="d" d="M22 74 L26 66 L30 74"/>',
    'caldera_water':
        '<rect class="body o" x="30" y="14" width="40" height="16" rx="8"/><rect class="body o" x="32" y="66" width="36" height="12" rx="6"/><line class="d" x1="38" y1="30" x2="38" y2="66"/><line class="d" x1="46" y1="30" x2="46" y2="66"/><line class="d" x1="54" y1="30" x2="54" y2="66"/><line class="d" x1="62" y1="30" x2="62" y2="66"/><line class="o" x1="50" y1="14" x2="50" y2="6"/><path class="d" d="M42 62 L46 54 L50 62 L54 52 L58 62"/>',
    'platos_sieve':
        '<rect class="body o" x="36" y="12" width="28" height="76" rx="3"/><g class="dot"><circle cx="43" cy="28" r="1.3"/><circle cx="50" cy="28" r="1.3"/><circle cx="57" cy="28" r="1.3"/><circle cx="43" cy="44" r="1.3"/><circle cx="50" cy="44" r="1.3"/><circle cx="57" cy="44" r="1.3"/><circle cx="43" cy="60" r="1.3"/><circle cx="50" cy="60" r="1.3"/><circle cx="57" cy="60" r="1.3"/><circle cx="43" cy="76" r="1.3"/><circle cx="50" cy="76" r="1.3"/><circle cx="57" cy="76" r="1.3"/></g><line class="d" x1="40" y1="28" x2="60" y2="28"/><line class="d" x1="40" y1="44" x2="60" y2="44"/><line class="d" x1="40" y1="60" x2="60" y2="60"/><line class="d" x1="40" y1="76" x2="60" y2="76"/>',
    'platos_valve':
        '<rect class="body o" x="36" y="12" width="28" height="76" rx="3"/><line class="d" x1="40" y1="30" x2="60" y2="30"/><line class="d" x1="40" y1="46" x2="60" y2="46"/><line class="d" x1="40" y1="62" x2="60" y2="62"/><line class="d" x1="40" y1="78" x2="60" y2="78"/><path class="d" d="M43 30 l3 -3.5 l3 3.5 M53 30 l3 -3.5 l3 3.5 M43 46 l3 -3.5 l3 3.5 M53 46 l3 -3.5 l3 3.5 M43 62 l3 -3.5 l3 3.5 M53 62 l3 -3.5 l3 3.5"/>',
    'empaque_rand':
        '<rect class="body o" x="36" y="12" width="28" height="76" rx="3"/><g class="d"><circle cx="44" cy="26" r="3.2"/><circle cx="55" cy="32" r="3.2"/><circle cx="47" cy="42" r="3.2"/><circle cx="57" cy="48" r="3.2"/><circle cx="43" cy="55" r="3.2"/><circle cx="54" cy="63" r="3.2"/><circle cx="45" cy="72" r="3.2"/><circle cx="57" cy="78" r="3.2"/></g>',
    'empaque_struct':
        '<rect class="body o" x="36" y="12" width="28" height="76" rx="3"/><path class="d" d="M40 22 L60 42 M40 42 L60 22 M40 42 L60 62 M40 62 L60 42 M40 62 L60 82 M40 82 L60 62"/>',
    'horno':
        '<rect class="body o" x="20" y="34" width="60" height="46"/><path class="body o" d="M20 34 L44 18 L56 18 L80 34 Z"/><rect class="body o" x="44" y="6" width="12" height="12"/><path class="d" d="M28 46 H62 Q70 46 70 54 H38 Q30 54 30 62 H72"/><path class="d" d="M40 76 L44 66 L48 76 L52 64 L56 76"/>',
    'horno_reformer':
        '<rect class="body o" x="20" y="34" width="60" height="46"/><path class="body o" d="M20 34 L44 18 L56 18 L80 34 Z"/><rect class="body o" x="44" y="6" width="12" height="12"/><line class="d" x1="32" y1="40" x2="32" y2="72"/><line class="d" x1="42" y1="40" x2="42" y2="72"/><line class="d" x1="52" y1="40" x2="52" y2="72"/><line class="d" x1="62" y1="40" x2="62" y2="72"/><line class="d" x1="72" y1="40" x2="72" y2="72"/>',
    'hx':
        '<rect class="body o" x="16" y="38" width="68" height="24" rx="4"/><line class="d" x1="26" y1="38" x2="26" y2="62"/><line class="d" x1="74" y1="38" x2="74" y2="62"/><path class="d" d="M26 45 Q50 38 74 45 M26 50 Q50 44 74 50 M26 55 Q50 50 74 55"/><line class="o" x1="40" y1="38" x2="40" y2="32"/><line class="o" x1="60" y1="62" x2="60" y2="68"/>',
    'hx_placa':
        '<rect class="body o" x="24" y="26" width="52" height="48"/><line class="d" x1="34" y1="30" x2="34" y2="70"/><line class="d" x1="42" y1="30" x2="42" y2="70"/><line class="d" x1="50" y1="30" x2="50" y2="70"/><line class="d" x1="58" y1="30" x2="58" y2="70"/><line class="d" x1="66" y1="30" x2="66" y2="70"/>',
    'hx_espiral':
        '<circle class="body o" cx="50" cy="50" r="30"/><path class="d" d="M50 50 Q57 43 57 51 Q57 62 45 62 Q30 62 30 46 Q30 27 51 27 Q74 27 74 51"/>',
    'hx_kettle':
        '<rect class="body o" x="16" y="42" width="68" height="34" rx="14"/><path class="body o" d="M38 42 A12 10 0 0 1 62 42 Z"/><path class="d" d="M24 56 H70 A6 6 0 0 1 70 64 H24"/><line class="d" x1="24" y1="70" x2="76" y2="70" stroke-dasharray="3 2"/>',
    'hx_whb':
        '<rect class="body o" x="16" y="34" width="68" height="42" rx="8"/><rect class="body o" x="34" y="12" width="32" height="16" rx="8"/><line class="d" x1="42" y1="28" x2="42" y2="34"/><line class="d" x1="58" y1="28" x2="58" y2="34"/><line class="d" x1="24" y1="54" x2="76" y2="54"/><line class="d" x1="24" y1="60" x2="76" y2="60"/><line class="o" x1="50" y1="12" x2="50" y2="4"/>',
    'hx_aircooler':
        '<rect class="body o" x="20" y="42" width="60" height="30"/><line class="d" x1="26" y1="50" x2="74" y2="50"/><line class="d" x1="26" y1="57" x2="74" y2="57"/><line class="d" x1="26" y1="64" x2="74" y2="64"/><circle class="body o" cx="50" cy="30" r="13"/><path class="d" d="M50 30 L50 19 M50 30 L59 36 M50 30 L41 36"/>',
    'hx_cond_air':
        '<path class="body o" d="M22 66 L50 30 L78 66 Z"/><path class="d" d="M34 66 L50 46 M42 66 L58 46 M50 66 L66 66"/><circle class="body o" cx="50" cy="78" r="9"/><path class="d" d="M50 78 L50 71 M50 78 L56 82 M50 78 L44 82"/>',
    'centrifuga_decanter':
        '<path class="body o" d="M16 38 H68 L84 50 L68 62 H16 Z"/><path class="d" d="M22 50 Q30 43 38 50 Q46 57 54 50 Q62 43 70 50"/>',
    'centrifuga_disc':
        '<path class="body o" d="M28 28 H72 L64 76 H36 Z"/><rect class="dot" x="44" y="12" width="12" height="6"/><line class="d" x1="50" y1="18" x2="50" y2="28"/><path class="d" d="M38 40 L50 34 L62 40 M40 50 L50 45 L60 50 M42 60 L50 55 L58 60"/>',
    'tanque_cone':
        '<path class="body o" d="M26 34 L50 16 L74 34 Z"/><rect class="body o" x="26" y="34" width="48" height="46"/><line class="d" x1="30" y1="56" x2="70" y2="56" stroke-dasharray="3 2"/>',
    'tanque_float':
        '<rect class="body o" x="26" y="20" width="48" height="60"/><rect class="dot" x="30" y="28" width="40" height="3.4"/><line class="d" x1="30" y1="56" x2="70" y2="56" stroke-dasharray="3 2"/>',
    'tambor':
        '<rect class="body o" x="12" y="38" width="76" height="24" rx="12"/><line class="d" x1="20" y1="52" x2="80" y2="52" stroke-dasharray="3 2"/><line class="d" x1="34" y1="62" x2="34" y2="72"/><line class="d" x1="66" y1="62" x2="66" y2="72"/>',
    'separador':
        '<rect class="body o" x="34" y="18" width="32" height="64"/><ellipse class="body o" cx="50" cy="18" rx="16" ry="6"/><ellipse class="body o" cx="50" cy="82" rx="16" ry="6"/><line class="d" x1="40" y1="30" x2="60" y2="30"/><line class="d" x1="40" y1="33" x2="60" y2="33"/><line class="d" x1="37" y1="64" x2="63" y2="64" stroke-dasharray="3 2"/>',
    'evaporador':
        '<rect class="body o" x="34" y="20" width="32" height="62" rx="4"/><path class="d" d="M40 14 Q44 10 48 14 M54 14 Q58 10 62 14"/><line class="d" x1="40" y1="34" x2="40" y2="72"/><line class="d" x1="47" y1="34" x2="47" y2="72"/><line class="d" x1="54" y1="34" x2="54" y2="72"/><line class="d" x1="61" y1="34" x2="61" y2="72"/>',
    'mezclador':
        '<path class="o" d="M18 24 L48 48 L18 76 M18 24 L82 48 M18 76 L82 48"/><circle class="body o" cx="50" cy="49" r="5"/>',
    'splitter':
        '<path class="o" d="M18 50 H50 M50 50 L82 22 M50 50 L82 78"/><path class="d" d="M74 22 H82 M82 22 L78 30 M74 78 H82 M82 78 L78 70"/><circle class="body o" cx="50" cy="50" r="5"/>',
    'columna':
        '<rect class="body o" x="38" y="10" width="24" height="80" rx="4"/><line class="d" x1="42" y1="22" x2="58" y2="22"/><line class="d" x1="42" y1="32" x2="58" y2="32"/><line class="d" x1="42" y1="42" x2="58" y2="42"/><line class="d" x1="42" y1="52" x2="58" y2="52"/><line class="d" x1="42" y1="62" x2="58" y2="62"/><line class="d" x1="42" y1="72" x2="58" y2="72"/><line class="o" x1="38" y1="50" x2="30" y2="50"/>',
    'ciclon':
        '<path class="body o" d="M26 20 H74 V40 L56 82 H44 L26 40 Z"/><line class="d" x1="44" y1="8" x2="44" y2="24"/><line class="d" x1="56" y1="8" x2="56" y2="24"/><line class="d" x1="14" y1="26" x2="26" y2="26"/><path class="d" d="M62 38 Q34 48 60 58 Q34 68 52 78"/>',
    'filtro':
        '<rect class="body o" x="20" y="18" width="60" height="60" rx="5"/><line class="d" x1="20" y1="42" x2="80" y2="42"/><line class="d" x1="20" y1="58" x2="80" y2="58"/><path class="d" d="M28 58 L34 42 M40 58 L46 42 M52 58 L58 42 M64 58 L70 42"/>',
    'secador':
        '<rect class="body o" x="12" y="34" width="76" height="32" rx="16"/><path class="d" d="M32 62 L38 40 M48 62 L54 40 M64 62 L70 40"/><circle class="d" cx="30" cy="72" r="4"/><circle class="d" cx="70" cy="72" r="4"/>',
    'cristalizador':
        '<path class="body o" d="M22 30 A28 20 0 0 1 78 30 L64 66 L50 84 L36 66 Z"/><rect class="dot" x="44" y="8" width="12" height="6"/><line class="d" x1="50" y1="14" x2="50" y2="52"/><line class="o" x1="40" y1="52" x2="60" y2="52"/><path class="d" d="M40 56 l3 -3 l3 3 l-3 3 Z M55 62 l3 -3 l3 3 l-3 3 Z"/>',
    'torre_enf':
        '<path class="body o" d="M30 82 Q37 46 34 14 L66 14 Q63 46 70 82 Z"/><circle class="body o" cx="50" cy="14" r="10"/><path class="d" d="M50 14 L50 6 M50 14 L57 19 M50 14 L43 19"/><line class="d" x1="34" y1="70" x2="66" y2="70"/>',
    'torre_nat':
        '<path class="body o" d="M28 84 Q40 48 34 12 L66 12 Q60 48 72 84 Z"/><path class="d" d="M44 12 Q48 6 54 10"/><line class="d" x1="34" y1="72" x2="66" y2="72"/>',
    'ventilador':
        '<circle class="body o" cx="50" cy="50" r="30"/><path class="d" d="M50 50 Q56 30 44 24 M50 50 Q68 56 70 44 M50 50 Q40 70 56 72"/><circle class="dot" cx="50" cy="50" r="3"/>',
    'ventilador_rad':
        '<path class="body o" d="M50 20 A30 30 0 1 0 80 50 L80 34 L64 34"/><circle class="dot" cx="47" cy="52" r="3"/><path class="d" d="M47 52 Q52 38 40 34 M47 52 Q60 56 60 46 M47 52 Q38 66 52 68"/>',
}

DETAIL_ALPHA = 0.52        # tinta de detalle = ink al 52 % (spec 3a)
DETAIL_W_RATIO = 1.0 / 1.6  # STROKE_DETAIL / STROKE_OUTLINE


# ─────────────────────────────────────────────────────────────────────
#  Parser (SVG subset → primitivas)
# ─────────────────────────────────────────────────────────────────────

_EL = _re.compile(r"<(rect|circle|ellipse|line|path|g)\b([^>]*?)(/?)>")
_AT = _re.compile(r"([\w-]+)=\"([^\"]*)\"")
_NUM = _re.compile(r"[-+]?\d*\.?\d+")


def _attrs(s):
    return dict(_AT.findall(s))


def _parse_path(d):
    """d → lista de subpaths; cada subpath = lista de segmentos
    ('L', x, y) / ('Q', cx, cy, x, y) / ('A', rx, ry, rot, laf, sf,
    x, y) / ('Z',). El primer punto va como ('M', x, y)."""
    toks = _re.findall(r"[MLHVQAZl]|[-+]?\d*\.?\d+", d)
    i, cx, cy = 0, 0.0, 0.0
    subs, cur = [], None
    cmd = None
    while i < len(toks):
        t = toks[i]
        if t in "MLHVQAZl":
            cmd = t
            i += 1
            if cmd == "Z":
                if cur:
                    cur.append(("Z",))
                cmd = None
                continue
        if cmd is None:
            i += 1
            continue
        if cmd == "M":
            cx, cy = float(toks[i]), float(toks[i + 1]); i += 2
            cur = [("M", cx, cy)]
            subs.append(cur)
            cmd = "L"          # coords siguientes sin letra = lineto
        elif cmd == "L":
            cx, cy = float(toks[i]), float(toks[i + 1]); i += 2
            cur.append(("L", cx, cy))
        elif cmd == "l":
            cx += float(toks[i]); cy += float(toks[i + 1]); i += 2
            cur.append(("L", cx, cy))
        elif cmd == "H":
            cx = float(toks[i]); i += 1
            cur.append(("L", cx, cy))
        elif cmd == "V":
            cy = float(toks[i]); i += 1
            cur.append(("L", cx, cy))
        elif cmd == "Q":
            qx, qy = float(toks[i]), float(toks[i + 1])
            cx, cy = float(toks[i + 2]), float(toks[i + 3]); i += 4
            cur.append(("Q", qx, qy, cx, cy))
        elif cmd == "A":
            rx, ry = float(toks[i]), float(toks[i + 1])
            rot = float(toks[i + 2])
            laf, sf = int(float(toks[i + 3])), int(float(toks[i + 4]))
            ex, ey = float(toks[i + 5]), float(toks[i + 6]); i += 7
            cur.append(("A", rx, ry, rot, laf, sf, cx, cy, ex, ey))
            cx, cy = ex, ey
    return subs


@lru_cache(maxsize=None)
def _primitives(name):
    """[(kind, cls, dashed, datos…)] + bbox (x, y, w, h) del glifo."""
    src = SVG_SRC[name]
    prims = []
    xs, ys = [], []
    g_cls = None
    pos = 0
    for m in _EL.finditer(src):
        el, rest, selfclose = m.group(1), m.group(2), m.group(3)
        a = _attrs(rest)
        cls = a.get("class", g_cls or "")
        dashed = "stroke-dasharray" in a
        if el == "g":
            g_cls = a.get("class", "")
            continue
        if el == "rect":
            x, y = float(a["x"]), float(a["y"])
            w, h = float(a["width"]), float(a["height"])
            rx = float(a.get("rx", 0))
            prims.append(("rect", cls, dashed, x, y, w, h, rx))
            xs += [x, x + w]; ys += [y, y + h]
        elif el == "circle":
            cx, cy, r = float(a["cx"]), float(a["cy"]), float(a["r"])
            prims.append(("circle", cls, dashed, cx, cy, r))
            xs += [cx - r, cx + r]; ys += [cy - r, cy + r]
        elif el == "ellipse":
            cx, cy = float(a["cx"]), float(a["cy"])
            rx, ry = float(a["rx"]), float(a["ry"])
            prims.append(("ellipse", cls, dashed, cx, cy, rx, ry))
            xs += [cx - rx, cx + rx]; ys += [cy - ry, cy + ry]
        elif el == "line":
            x1, y1 = float(a["x1"]), float(a["y1"])
            x2, y2 = float(a["x2"]), float(a["y2"])
            prims.append(("line", cls, dashed, x1, y1, x2, y2))
            xs += [x1, x2]; ys += [y1, y2]
        elif el == "path":
            subs = _parse_path(a["d"])
            prims.append(("path", cls, dashed, tuple(
                tuple(seg for seg in sub) for sub in subs)))
            for sub in subs:
                for seg in sub:
                    if seg[0] in ("M", "L"):
                        xs.append(seg[1]); ys.append(seg[2])
                    elif seg[0] == "Q":
                        xs += [seg[1], seg[3]]; ys += [seg[2], seg[4]]
                    elif seg[0] == "A":
                        xs += [seg[6], seg[8]]; ys += [seg[7], seg[9]]
        # cierre implícito del <g> al encontrar el siguiente elemento
        # top-level: los <g> del spec solo envuelven runs contiguos y
        # el fragmento no anida — detectar '</g>' entre elementos
        tail = src[m.end():]
        nx = _EL.search(tail)
        seg_txt = tail[:nx.start()] if nx else tail
        if "</g>" in seg_txt:
            g_cls = None
    x0, y0 = min(xs), min(ys)
    return tuple(prims), (x0, y0, max(xs) - x0, max(ys) - y0)


def glyph_dims(name, pad=2.0):
    """Dims nativas (w, h) del glifo = bbox del contenido + padding.
    La escala interna del set de Design ya armoniza los tamaños
    relativos entre equipos (columna alta, bomba compacta…)."""
    _, (_, _, bw, bh) = _primitives(name)
    return (int(round(bw + 2 * pad)), int(round(bh + 2 * pad)))


GLYPHS = tuple(sorted(SVG_SRC))


# ─────────────────────────────────────────────────────────────────────
#  Renderer QPainter
# ─────────────────────────────────────────────────────────────────────

def _qpath(subs):
    from PySide6.QtGui import QPainterPath
    import math
    path = QPainterPath()
    for sub in subs:
        for seg in sub:
            k = seg[0]
            if k == "M":
                path.moveTo(seg[1], seg[2])
            elif k == "L":
                path.lineTo(seg[1], seg[2])
            elif k == "Q":
                path.quadTo(seg[1], seg[2], seg[3], seg[4])
            elif k == "Z":
                path.closeSubpath()
            elif k == "A":
                rx, ry, _rot, laf, sf, x1, y1, x2, y2 = seg[1:]
                # conversión endpoint→centro (spec SVG F.6.5, rot=0)
                dx, dy = (x1 - x2) / 2.0, (y1 - y2) / 2.0
                lam = (dx * dx) / (rx * rx) + (dy * dy) / (ry * ry)
                if lam > 1:
                    s = math.sqrt(lam); rx *= s; ry *= s
                num = (rx*rx*ry*ry - rx*rx*dy*dy - ry*ry*dx*dx)
                den = (rx*rx*dy*dy + ry*ry*dx*dx)
                co = math.sqrt(max(0.0, num / den)) if den else 0.0
                if laf == sf:
                    co = -co
                cxp, cyp = co * rx * dy / ry, -co * ry * dx / rx
                cx, cy = cxp + (x1 + x2) / 2.0, cyp + (y1 + y2) / 2.0
                a1 = math.degrees(math.atan2((y1 - cy) / ry,
                                             (x1 - cx) / rx))
                a2 = math.degrees(math.atan2((y2 - cy) / ry,
                                             (x2 - cx) / rx))
                sweep = a2 - a1
                if sf == 0 and sweep > 0:
                    sweep -= 360
                elif sf == 1 and sweep < 0:
                    sweep += 360
                # Qt: ángulos en sentido antihorario, eje Y invertido
                path.arcTo(cx - rx, cy - ry, 2 * rx, 2 * ry,
                           -a1, -sweep)
    return path


def draw_glyph(p, name, w, h, ink, fill_brush, sw, dashed=False):
    """Pinta el glifo `name` dentro de (0,0,w,h) con el QPainter dado.

    ink   — tinta del estado (contornos `o`); el detalle deriva al
            52 % de alpha (spec 3a).
    fill_brush — fill de `body` (tinte del semáforo o bg_elev).
    sw    — ancho del contorno YA compensado por la escala del caller
            (contrato de BlockGlyph.draw); el detalle usa el ratio
            STROKE_DETAIL/STROKE_OUTLINE.
    dashed — estado unrun: puntea los trazos `o`.
    """
    from PySide6.QtCore import Qt, QRectF
    from PySide6.QtGui import QPen, QBrush, QColor
    prims, (bx, by, bw, bh) = _primitives(name)
    if bw <= 0 or bh <= 0:
        return
    s = min(w / bw, h / bh)
    p.save()
    p.translate((w - bw * s) / 2.0 - bx * s, (h - bh * s) / 2.0 - by * s)
    p.scale(s, s)

    detail = QColor(ink)
    detail.setAlphaF(ink.alphaF() * DETAIL_ALPHA)

    def pen_for(cls, dash_attr):
        is_detail = "d" in cls.split()
        c = detail if is_detail else QColor(ink)
        width = (sw * DETAIL_W_RATIO if is_detail else sw) / max(s, 1e-6)
        pen = QPen(c, width)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        if dash_attr or (dashed and not is_detail):
            pen.setStyle(Qt.DashLine)
        return pen

    for prim in prims:
        kind, cls, dash_attr = prim[0], prim[1], prim[2]
        classes = cls.split()
        is_dot = "dot" in classes
        has_body = "body" in classes
        stroked = "o" in classes or "d" in classes
        if is_dot:
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(detail))
        else:
            p.setPen(pen_for(cls, dash_attr) if stroked else Qt.NoPen)
            p.setBrush(fill_brush if has_body else Qt.NoBrush)
        if kind == "rect":
            _, _, _, x, y, rw, rh, rx = prim
            if rx:
                p.drawRoundedRect(QRectF(x, y, rw, rh), rx, rx)
            else:
                p.drawRect(QRectF(x, y, rw, rh))
        elif kind == "circle":
            _, _, _, cx, cy, r = prim
            from PySide6.QtCore import QPointF
            p.drawEllipse(QPointF(cx, cy), r, r)
        elif kind == "ellipse":
            _, _, _, cx, cy, rx, ry = prim
            from PySide6.QtCore import QPointF
            p.drawEllipse(QPointF(cx, cy), rx, ry)
        elif kind == "line":
            _, _, _, x1, y1, x2, y2 = prim
            from PySide6.QtCore import QLineF
            p.drawLine(QLineF(x1, y1, x2, y2))
        elif kind == "path":
            path = _qpath(prim[3])
            p.drawPath(path)
    p.restore()
