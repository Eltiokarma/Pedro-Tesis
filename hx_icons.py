"""hx_icons.py — glyphs SVG del Heat Exchanger riguroso (port de hx-icons.jsx).

Cada glyph se define como el *body* interno de un <svg viewBox="0 0 24 24">.
`stroke="currentColor"` y `fill="currentColor"` se sustituyen por el color
pedido al renderizar, así el mismo glyph sirve para light/dark y para tomar
la severidad del row padre (igual que `currentColor` en el mockup CSS).

API:
    glyph_svg(name, color, stroke=1.5) -> str | None
    glyph_pixmap(name, size, color, stroke=1.5) -> QPixmap
    glyph_icon(name, size, color, stroke=1.5)   -> QIcon
    GlyphLabel(name, size, color, stroke)        -> QLabel ya renderizado
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QPixmap, QIcon, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QLabel

# ── glyph bodies (SVG, kebab-case) ──────────────────────────────────
# stroke="currentColor" implícito vía el <svg> padre; sólo se anota
# explícitamente cuando el elemento difiere (fill o stroke-width propio).
_GLYPHS = {
    # ── warnings ──
    "warn-approach": (
        '<path d="M11 4 v9"/>'
        '<circle cx="11" cy="16" r="3"/>'
        '<path d="M11 9 L14 9" opacity=".6"/>'
        '<path d="M17 6 L21 6 M19 4 L21 6 L19 8" opacity=".7"/>'
    ),
    "warn-crossing": (
        '<path d="M8 4 v9"/>'
        '<circle cx="8" cy="16" r="2.6"/>'
        '<path d="M16 4 v9" opacity=".55"/>'
        '<circle cx="16" cy="16" r="2.6" opacity=".55"/>'
        '<path d="M6 6 L18 18" stroke-width="2"/>'
    ),
    "warn-fcorrection": (
        '<circle cx="11" cy="12" r="3.5"/>'
        '<path d="M11 4 v3 M11 17 v3 M3 12 h3 M16 12 h3 '
        'M5.5 6.5 L7.5 8.5 M14.5 15.5 L16.5 17.5 '
        'M5.5 17.5 L7.5 15.5 M14.5 8.5 L16.5 6.5" opacity=".8"/>'
        '<path d="M20 8 v6" opacity=".85"/>'
        '<circle cx="20" cy="16" r=".6" fill="currentColor" stroke="none"/>'
    ),
    "warn-fouling": (
        '<ellipse cx="11" cy="7" rx="6" ry="2"/>'
        '<path d="M5 7 v9 q0 2 6 2 q6 0 6 -2 v-9"/>'
        '<path d="M5 11.5 q6 2 12 0" opacity=".6"/>'
        '<path d="M19 5 q1 1.5 0 2.8 q-1 -1.3 0 -2.8 z M21 8 q.8 1.3 0 2.4 '
        'q-.8 -1.1 0 -2.4 z" fill="currentColor" stroke="none" opacity=".8"/>'
    ),
    "warn-range": (
        '<rect x="3" y="9" width="14" height="6" rx="1"/>'
        '<path d="M6 9 v2 M9 9 v3 M12 9 v2 M15 9 v3" opacity=".7"/>'
        '<path d="M20 6 v6" opacity=".85"/>'
        '<circle cx="20" cy="14.5" r=".6" fill="currentColor" stroke="none"/>'
    ),
    "warn-scale": (
        '<path d="M12 5 v14 M5 19 h14"/>'
        '<path d="M5 11 L8 7 L11 11 q-3 2 -6 0 z"/>'
        '<path d="M13 11 L16 7 L19 11 q-3 2 -6 0 z" opacity=".6"/>'
    ),
    "warn-utility": (
        '<path d="M12 3 q4 5 4 9 q0 4 -4 4 q-4 0 -4 -4 q0 -2 2 -4 q-1 3 2 5"/>'
        '<path d="M9 16 q-2 2 0 4 q3 1.5 6 0 q2 -2 0 -4"/>'
    ),
    "warn-tavg": (
        '<path d="M4 4 v16 h16"/>'
        '<path d="M7 16 L11 12 L14 14 L19 7"/>'
        '<circle cx="11" cy="12" r="1" fill="currentColor" stroke="none" opacity=".7"/>'
    ),
    # ── topics ──
    "topic-lmtd": (
        '<path d="M3 18 q6 -4 9 -7 q3 -3 9 -7"/>'
        '<path d="M3 6 q6 4 9 7 q3 3 9 7" opacity=".55"/>'
        '<circle cx="6" cy="12" r="1" fill="currentColor" stroke="none" opacity=".5"/>'
        '<circle cx="18" cy="12" r="1" fill="currentColor" stroke="none" opacity=".5"/>'
    ),
    "topic-f": (
        '<path d="M4 20 v-16 M4 4 h14 M4 12 h10"/>'
        '<text x="10" y="18" font-size="9" font-family="IBM Plex Mono, monospace" '
        'font-weight="700" fill="currentColor" stroke="none">F</text>'
    ),
    "topic-fouling": (
        '<rect x="3" y="9" width="18" height="6" rx="1"/>'
        '<path d="M3 11 q4 -1 8 0 q4 1 8 0" opacity=".5"/>'
        '<path d="M3 13 q4 -1 8 0 q4 1 8 0" opacity=".4"/>'
        '<path d="M5 9 q1 -3 0 -4 M9 9 q-1 -2 0 -3 M13 9 q1 -2 0 -3 '
        'M17 9 q-1 -3 0 -4" opacity=".55"/>'
    ),
    "topic-hand-vs-fbm": (
        '<rect x="3" y="6" width="8" height="13" rx="1.3"/>'
        '<rect x="13" y="6" width="8" height="13" rx="1.3"/>'
        '<text x="5" y="14" font-size="6.5" font-family="IBM Plex Mono, monospace" '
        'font-weight="700" fill="currentColor" stroke="none">H</text>'
        '<text x="14.5" y="14" font-size="6.5" font-family="IBM Plex Mono, monospace" '
        'font-weight="700" fill="currentColor" stroke="none">FBM</text>'
    ),
    "topic-approach": (
        '<path d="M3 8 q6 0 9 4 q3 4 9 4"/>'
        '<path d="M3 16 q6 0 9 -4 q3 -4 9 -4" opacity=".55"/>'
        '<path d="M11.5 11 v2" stroke-width="1.6"/>'
        '<path d="M11 10.5 L12 10.5 M11 13.5 L12 13.5" opacity=".7" stroke-width="1.2"/>'
    ),
    "topic-catalog": (
        '<rect x="3" y="4" width="8" height="16" rx="1.4"/>'
        '<rect x="13" y="4" width="8" height="16" rx="1.4" opacity=".55"/>'
        '<path d="M5 8 L9 8 M5 11 L9 11 M5 14 L9 14" opacity=".55"/>'
        '<path d="M15 8 L19 8 M15 11 L19 11 M15 14 L19 14" opacity=".4"/>'
    ),
    "topic-whb": (
        '<ellipse cx="12" cy="8" rx="6" ry="2.4"/>'
        '<path d="M6 8 v9 q0 2 6 2 q6 0 6 -2 v-9"/>'
        '<path d="M9 4 v-2 M12 4 v-3 M15 4 v-2" opacity=".7"/>'
        '<path d="M9 12 q3 -1 6 0 q-3 1 -6 0" opacity=".55"/>'
    ),
    # ── HX equipment ──
    "hx-utube": (
        '<rect x="3" y="8" width="18" height="8" rx="1.6"/>'
        '<path d="M5 11 L18 11 q2 0 2 2 L8 13" opacity=".8"/>'
        '<path d="M6 8 L6 5 M18 8 L18 5 M6 16 L6 19 M18 16 L18 19" opacity=".7"/>'
    ),
    "hx-whb-pkg": (
        '<rect x="3" y="6" width="18" height="13" rx="1.6"/>'
        '<path d="M3 11 L21 11" opacity=".55"/>'
        '<path d="M7 8 q3 -1 6 0 q3 1 6 0" opacity=".55"/>'
        '<path d="M7 19 v2 M13 19 v2" opacity=".7"/>'
        '<path d="M11 3 v3 M14 3 v3" opacity=".55"/>'
    ),
    # ── misc ──
    "tri-right": '<path d="M9 6 L15 12 L9 18 z" fill="currentColor" stroke="none"/>',
    "tri-down": '<path d="M6 9 L12 15 L18 9 z" fill="currentColor" stroke="none"/>',
    "cross-exchange": (
        '<path d="M4 8 L20 16 M20 16 L16 14 M20 16 L18 20"/>'
        '<path d="M4 16 L20 8 M20 8 L18 4 M20 8 L16 10" opacity=".7"/>'
    ),
    "steam": (
        '<path d="M6 21 q-1 -3 1 -5 q1 -2 -1 -4 q-1 -2 1 -4 q1 -2 -1 -4"/>'
        '<path d="M12 21 q-1 -3 1 -5 q1 -2 -1 -4 q-1 -2 1 -4 q1 -2 -1 -4" opacity=".55"/>'
        '<path d="M18 21 q-1 -3 1 -5 q1 -2 -1 -4 q-1 -2 1 -4 q1 -2 -1 -4" opacity=".4"/>'
    ),
    "check": '<path d="M5 12.5 L10 17.5 L19 6.5"/>',
    "qmark": (
        '<circle cx="12" cy="12" r="9"/>'
        '<path d="M9.5 9 q0 -3 2.5 -3 q3 0 3 3 q0 1.5 -3 3 v1" opacity=".85"/>'
        '<circle cx="12" cy="17" r=".7" fill="currentColor" stroke="none"/>'
    ),
    "empty-streams": (
        '<path d="M11 4 v9"/>'
        '<circle cx="11" cy="16" r="3"/>'
        '<path d="M11 9 L14 9" opacity=".55"/>'
        '<path d="M4 20 L20 4" opacity=".55" stroke-width="1.8"/>'
    ),
    "empty-duty": (
        '<rect x="3" y="8" width="18" height="8" rx="1.6" opacity=".7"/>'
        '<path d="M3 12 q4 -3 8 0 q4 3 8 0" opacity=".4"/>'
        '<path d="M4 20 L20 4" opacity=".75" stroke-width="1.6"/>'
    ),
    "lightbulb": (
        '<path d="M9 18 h6 M10 21 h4"/>'
        '<path d="M12 3 a6 6 0 0 0 -4 10 q1 1 1.5 3 h5 q.5 -2 1.5 -3 a6 6 0 0 0 -4 -10 z"/>'
    ),
}


def glyph_svg(name: str, color: str, stroke: float = 1.5) -> str | None:
    body = _GLYPHS.get(name)
    if body is None:
        return None
    body = body.replace("currentColor", color)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        f'width="24" height="24" fill="none" stroke="{color}" '
        f'stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    )


def glyph_pixmap(name: str, size: int, color: str, stroke: float = 1.5) -> QPixmap:
    svg = glyph_svg(name, color, stroke)
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    if svg is None:
        return pm
    r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    p = QPainter(pm)
    r.render(p)
    p.end()
    return pm


def glyph_icon(name: str, size: int, color: str, stroke: float = 1.5) -> QIcon:
    return QIcon(glyph_pixmap(name, size, color, stroke))


class GlyphLabel(QLabel):
    """QLabel que muestra un glyph HX renderizado a un tamaño/color dado."""

    def __init__(self, name: str, size: int = 16, color: str = "#000",
                 stroke: float = 1.6, parent=None):
        super().__init__(parent)
        self._name, self._size, self._stroke = name, size, stroke
        self.setFixedSize(size, size)
        self.set_color(color)

    def set_color(self, color: str):
        self._color = color
        self.setPixmap(glyph_pixmap(self._name, self._size, color, self._stroke))

    def set_glyph(self, name: str, color: str | None = None):
        self._name = name
        self.set_color(color or getattr(self, "_color", "#000"))
