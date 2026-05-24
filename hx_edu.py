"""hx_edu.py — contenido educativo + EducationalPopover (port de hx-content.jsx).

7 topics con prosa técnica, fórmula y diagrama SVG inline (theme-aware via
los tokens TOK del inspector).  El popover es un QDialog modal scrolleable.
"""
from __future__ import annotations

import math
import re

from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import QFont, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QWidget, QSizePolicy,
)

import pfd_fonts
from block_inspector import TOK
import hx_icons as hi


# ── token substitution para los SVG de diagramas ───────────────────
def _subst_tokens(svg: str) -> str:
    def repl(m):
        name = m.group(1).replace("-", "_")
        return TOK.get(name, TOK["ink"])
    return re.sub(r"var\(--([a-z0-9-]+)\)", repl, svg)


def _svg_pixmap(svg: str, w: int, h: int) -> QPixmap:
    svg = _subst_tokens(svg)
    pm = QPixmap(w, h)
    pm.fill(Qt.transparent)
    r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    p = QPainter(pm)
    r.render(p)
    p.end()
    return pm


# ── diagramas (SVG, viewBox 380×150) ────────────────────────────────
def _diag_lmtd() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 380 150">'
        '<line x1="34" y1="14" x2="34" y2="124" stroke="var(--line-strong)" stroke-width="0.8"/>'
        '<line x1="34" y1="124" x2="360" y2="124" stroke="var(--line-strong)" stroke-width="0.8"/>'
        '<text x="18" y="74" font-size="9.5" fill="var(--ink-soft)" transform="rotate(-90 18 74)">T</text>'
        '<text x="195" y="142" font-size="9.5" fill="var(--ink-soft)" text-anchor="middle">longitud del HX</text>'
        '<path d="M 44 26 Q 200 50 350 80" fill="none" stroke="var(--danger)" stroke-width="1.8"/>'
        '<text x="50" y="20" font-size="9.5" fill="var(--danger)" font-family="monospace">T_h,in</text>'
        '<text x="320" y="76" font-size="9.5" fill="var(--danger)" font-family="monospace">T_h,out</text>'
        '<path d="M 44 110 Q 200 88 350 56" fill="none" stroke="var(--spec)" stroke-width="1.8"/>'
        '<text x="46" y="120" font-size="9.5" fill="var(--spec)" font-family="monospace">T_c,out</text>'
        '<text x="316" y="52" font-size="9.5" fill="var(--spec)" font-family="monospace">T_c,in</text>'
        '<line x1="56" y1="28" x2="56" y2="108" stroke="var(--ink-mute)" stroke-width=".6" stroke-dasharray="3 3"/>'
        '<text x="63" y="72" font-size="10" font-weight="600" fill="var(--ink)">&#916;T&#8321;</text>'
        '<line x1="340" y1="82" x2="340" y2="56" stroke="var(--ink-mute)" stroke-width=".6" stroke-dasharray="3 3"/>'
        '<text x="306" y="70" font-size="10" font-weight="600" fill="var(--ink)">&#916;T&#8322;</text>'
        '</svg>'
    )


def _diag_f() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 380 150">'
        '<line x1="34" y1="14" x2="34" y2="124" stroke="var(--line-strong)" stroke-width="0.8"/>'
        '<line x1="34" y1="124" x2="360" y2="124" stroke="var(--line-strong)" stroke-width="0.8"/>'
        '<text x="14" y="74" font-size="9.5" fill="var(--ink-soft)" transform="rotate(-90 14 74)" font-family="monospace">F</text>'
        '<text x="195" y="142" font-size="9.5" fill="var(--ink-soft)" text-anchor="middle">efectividad P</text>'
        '<text x="22" y="22" font-size="9" fill="var(--ink-soft)" font-family="monospace">1.0</text>'
        '<text x="22" y="74" font-size="9" fill="var(--ink-soft)" font-family="monospace">0.85</text>'
        '<text x="22" y="125" font-size="9" fill="var(--ink-soft)" font-family="monospace">0.75</text>'
        '<line x1="34" y1="70" x2="360" y2="70" stroke="var(--amber)" stroke-width=".8" stroke-dasharray="3 3"/>'
        '<line x1="34" y1="120" x2="360" y2="120" stroke="var(--danger)" stroke-width=".8" stroke-dasharray="3 3"/>'
        '<path d="M 44 22 Q 100 26 180 35 T 280 75 T 355 122" fill="none" stroke="var(--spec)" stroke-width="1.6"/>'
        '<path d="M 44 22 Q 120 30 200 50 T 290 95 T 340 122" fill="none" stroke="var(--green)" stroke-width="1.6"/>'
        '<path d="M 44 22 Q 140 36 220 70 T 280 122" fill="none" stroke="var(--orange)" stroke-width="1.6"/>'
        '<text x="288" y="38" font-size="9" font-family="monospace" fill="var(--spec)">R=0.5</text>'
        '<text x="288" y="50" font-size="9" font-family="monospace" fill="var(--green)">R=1.0</text>'
        '<text x="250" y="100" font-size="9" font-family="monospace" fill="var(--orange)">R=2.0</text>'
        '<text x="220" y="66" font-size="9" fill="var(--amber)">F = 0.85 (m&#237;n. dise&#241;o)</text>'
        '</svg>'
    )


def _diag_table(title: str, rows) -> str:
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 380 150">']
    out.append(f'<text x="190" y="14" font-size="10" font-weight="600" '
               f'fill="var(--ink)" text-anchor="middle">{title}</text>')
    for i, (left, right, col) in enumerate(rows):
        bg = "var(--bg-mute)" if i % 2 else "var(--bg-elev)"
        y = 26 + i * 22
        out.append(f'<rect x="28" y="{y}" width="324" height="20" fill="{bg}" '
                   f'stroke="var(--line-soft)" stroke-width=".5"/>')
        out.append(f'<text x="36" y="{y+14}" font-size="10.5" fill="var(--ink)">{left}</text>')
        out.append(f'<text x="345" y="{y+14}" font-size="11" font-family="monospace" '
                   f'font-weight="700" fill="{col}" text-anchor="end">{right}</text>')
    out.append('</svg>')
    return "".join(out)


def _diag_fouling() -> str:
    return _diag_table(
        "R_f t&#237;picos (m&#178;&#183;K/W &#215; 10&#8315;&#8308;) — TEMA RGP-T-2.4",
        [("Vapor saturado limpio", "1.0", "var(--ink)"),
         ("Agua treated cooling water", "1.7", "var(--ink)"),
         ("Hidrocarburo crudo", "8.8", "var(--ink)"),
         ("Gases sucios (flue gas)", "5.3", "var(--ink)"),
         ("Solventes org&#225;nicos", "2.0", "var(--ink)")])


def _diag_approach() -> str:
    return _diag_table(
        "&#916;T_min t&#237;pico por servicio",
        [("Vapor latente / agua", "5 K", "var(--green)"),
         ("L&#237;quido-l&#237;quido", "10 K", "var(--green)"),
         ("Gas-l&#237;quido", "15 K", "var(--amber)"),
         ("Gas-gas", "20 K", "var(--amber)"),
         ("Refrigerante criog&#233;nico", "3 K", "var(--danger)")])


def _diag_hand_fbm() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 380 150">'
        '<rect x="14" y="14" width="170" height="124" rx="6" fill="var(--sinnott-bg)" stroke="var(--sinnott)" stroke-width=".8"/>'
        '<text x="99" y="34" font-size="11" font-weight="700" fill="var(--sinnott-ink)" text-anchor="middle">Hand &#183; Sinnott</text>'
        '<text x="24" y="58" font-size="10" fill="var(--ink)">factor &#250;nico / categor&#237;a</text>'
        '<text x="24" y="76" font-size="10" font-family="monospace" fill="var(--ink-mute)">HX shell&amp;tube &#8594; 3.5</text>'
        '<text x="24" y="92" font-size="10" font-family="monospace" fill="var(--ink-mute)">Vasos / torres &#8594; 4.0</text>'
        '<text x="24" y="108" font-size="10" font-family="monospace" fill="var(--ink-mute)">Bombas / compr. &#8594; 4.0</text>'
        '<text x="24" y="130" font-size="9" font-style="italic" fill="var(--ink-soft)">sin material/presi&#243;n</text>'
        '<rect x="196" y="14" width="170" height="124" rx="6" fill="var(--spec-bg)" stroke="var(--spec)" stroke-width=".8"/>'
        '<text x="281" y="34" font-size="11" font-weight="700" fill="var(--turton-ink)" text-anchor="middle">F_BM &#183; Turton</text>'
        '<text x="206" y="58" font-size="10" font-family="monospace" fill="var(--ink)">B&#8321; + B&#8322; &#183; F_M &#183; F_P</text>'
        '<text x="206" y="78" font-size="10" fill="var(--ink-mute)">corrige material (F_M)</text>'
        '<text x="206" y="94" font-size="10" fill="var(--ink-mute)">corrige presi&#243;n (F_P)</text>'
        '<text x="206" y="110" font-size="10" fill="var(--ink-mute)">B&#8321;,B&#8322; por equipo</text>'
        '<text x="206" y="130" font-size="9" font-style="italic" fill="var(--ink-soft)">m&#225;s fino, pide m&#225;s data</text>'
        '</svg>'
    )


def _diag_catalog() -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 380 150">'
        '<text x="190" y="14" font-size="10" font-weight="600" fill="var(--ink)" text-anchor="middle">Cat&#225;logo mixto del simulador</text>'
        '<rect x="14" y="22" width="170" height="116" rx="6" fill="var(--spec-bg)" stroke="var(--spec)" stroke-width=".8"/>'
        '<text x="99" y="40" font-size="11" font-weight="700" fill="var(--turton-ink)" text-anchor="middle">Turton 2018</text>'
        '<text x="24" y="62" font-size="10" fill="var(--ink)">HX shell&amp;tube &#183; air-cooled</text>'
        '<text x="24" y="78" font-size="10" fill="var(--ink)">Bombas &#183; compresores</text>'
        '<text x="24" y="94" font-size="10" fill="var(--ink)">Torres &#183; vasos</text>'
        '<text x="24" y="110" font-size="10" fill="var(--ink)">Reactores &#183; separadores</text>'
        '<text x="24" y="128" font-size="9" font-style="italic" fill="var(--ink-soft)">amplio &#183; F_BM validado</text>'
        '<rect x="196" y="22" width="170" height="116" rx="6" fill="var(--sinnott-bg)" stroke="var(--sinnott)" stroke-width=".8"/>'
        '<text x="281" y="40" font-size="11" font-weight="700" fill="var(--sinnott-ink)" text-anchor="middle">Sinnott 2019</text>'
        '<text x="206" y="62" font-size="10" fill="var(--ink)">WHB packaged (5&#8211;50 t/h)</text>'
        '<text x="206" y="78" font-size="10" fill="var(--ink)">WHB field-erected</text>'
        '<text x="206" y="94" font-size="10" fill="var(--ink)">Boilers de planta</text>'
        '<text x="206" y="110" font-size="9" font-style="italic" fill="var(--ink-soft)">(Turton no cubre WHB)</text>'
        '<text x="206" y="128" font-size="9" font-style="italic" fill="var(--ink-soft)">llena el gap del cat&#225;logo</text>'
        '</svg>'
    )


def _diag_whb_scale(marker: float = 31583.0) -> str:
    def pos(kg):
        lo, hi = math.log10(5000), math.log10(200000)
        p = (math.log10(max(1000, kg)) - lo) / (hi - lo)
        return 105 + p * (295 - 105)
    x = pos(marker)
    mk = f"{int(round(marker)):,}".replace(",", " ")
    ticks = "".join(
        f'<line x1="{xp}" y1="100" x2="{xp}" y2="105" stroke="var(--ink-soft)" stroke-width=".6"/>'
        f'<text x="{xp}" y="118" font-size="9.5" font-family="monospace" '
        f'fill="var(--ink-soft)" text-anchor="middle">{lbl}</text>'
        for xp, lbl in ((105, "5 k"), (200, "20 k"), (295, "50 k"), (363, "200 k")))
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 380 150">'
        '<rect x="14" y="44" width="91" height="44" rx="4" fill="var(--danger-bg)" stroke="var(--danger)" stroke-width=".7"/>'
        '<text x="60" y="60" font-size="10" font-weight="700" fill="var(--danger)" text-anchor="middle">fuera de rango</text>'
        '<text x="60" y="76" font-size="9.5" font-family="monospace" fill="var(--danger)" text-anchor="middle">&lt; 5 000 kg/h</text>'
        '<rect x="105" y="44" width="190" height="44" rx="4" fill="var(--sinnott-bg)" stroke="var(--sinnott)" stroke-width=".7"/>'
        '<text x="200" y="60" font-size="10" font-weight="700" fill="var(--sinnott-ink)" text-anchor="middle">SINNOTT &#183; Packaged</text>'
        '<text x="200" y="76" font-size="9.5" font-family="monospace" fill="var(--sinnott-ink)" text-anchor="middle">5 000 &#8211; 50 000 kg/h</text>'
        '<rect x="295" y="44" width="68" height="44" rx="4" fill="var(--spec-bg)" stroke="var(--spec)" stroke-width=".7"/>'
        '<text x="329" y="60" font-size="10" font-weight="700" fill="var(--turton-ink)" text-anchor="middle">Field erected</text>'
        '<text x="329" y="76" font-size="9.5" font-family="monospace" fill="var(--turton-ink)" text-anchor="middle">&gt; 50 000</text>'
        '<line x1="14" y1="100" x2="363" y2="100" stroke="var(--line-strong)" stroke-width=".6"/>'
        f'{ticks}'
        f'<line x1="{x}" y1="34" x2="{x}" y2="98" stroke="var(--ink)" stroke-width="1.3"/>'
        f'<polygon points="{x-4},30 {x+4},30 {x},38" fill="var(--ink)"/>'
        f'<text x="{x}" y="24" font-size="9.5" font-family="monospace" font-weight="700" fill="var(--ink)" text-anchor="middle">{mk} kg/h</text>'
        f'<text x="{x}" y="138" font-size="9" font-style="italic" fill="var(--ink-mute)" text-anchor="middle">tu HX est&#225; ac&#225;</text>'
        '</svg>'
    )


# ── topics database ─────────────────────────────────────────────────
EDU_TOPICS = {
    "lmtd": {
        "title": "Diferencia de temperatura media logarítmica (ΔT_lm)",
        "icon": "topic-lmtd",
        "body": (
            "<p>Cuando dos corrientes intercambian calor, la fuerza impulsora "
            "<em>ΔT</em> varía a lo largo del equipo: en un extremo es <em>ΔT₁</em> "
            "y en el otro <em>ΔT₂</em>. La media logarítmica es la que verdaderamente "
            "cierra el balance integrado <b>Q = U·A·ΔT_lm</b>.</p>"
            "<p>Si los dos extremos son similares, <b>ΔT_lm</b> coincide con la media "
            "aritmética. Si uno colapsa (close-approach) el área crece "
            "desproporcionadamente — la integral logarítmica castiga ese régimen.</p>"
        ),
        "formula": "ΔT_lm  =  (ΔT₁ − ΔT₂) ⁄ ln(ΔT₁ ⁄ ΔT₂)",
        "diagram": _diag_lmtd,
        "source": "<b>Kern,</b> Process Heat Transfer (McGraw-Hill, 1950), Cap. 7 §7.3 · "
                  "<b>Sinnott &amp; Towler,</b> Chem. Eng. Design 6th ed. §19.6.",
    },
    "f_correction": {
        "title": "Factor F — corrección Bowman para multi-paso",
        "icon": "topic-f",
        "body": (
            "<p>El <em>LMTD</em> canónico asume contracorriente puro. En shell-and-tube "
            "1-2 o 2-4 las pasadas de los tubos generan tramos en contra y a favor del "
            "shell, lo que <b>reduce</b> la fuerza impulsora efectiva.</p>"
            "<p>El factor <b>F &lt; 1</b> de Bowman (1940) escala el LMTD al valor real. "
            "Como guía: <em>F &lt; 0.85</em> sugiere agregar otro shell o cambiar "
            "configuración; <em>F &lt; 0.75</em> es directamente inaceptable.</p>"
        ),
        "formula": "Q = U · A · F · ΔT_lm        F = f(P, R) ∈ [0.75, 1.0] · Bowman 1940",
        "diagram": _diag_f,
        "source": "<b>Bowman, Mueller &amp; Nagle,</b> Trans. ASME 62 (1940) 283–294 · "
                  "<b>TEMA Standards,</b> 10ª ed., Sec. T-3.",
    },
    "fouling": {
        "title": "Fouling resistance — coeficiente efectivo",
        "icon": "topic-fouling",
        "body": (
            "<p>El factor de ensuciamiento <em>R_f</em> agrega una resistencia térmica "
            "al sandwich pared+películas; es lo que el motor usa para pasar de "
            "<em>U_clean</em> (limpio, día 0) a <b>U_ef</b> (efectivo, después de meses "
            "de operación).</p>"
            "<p>El catálogo TEMA da rangos por par de fluidos. Para agua de torre limpia "
            "el valor es bajo; para crudo o gases sucios crece <b>5–10×</b> y puede "
            "consumir más del 30% del U de diseño.</p>"
        ),
        "formula": "1 ⁄ U_ef  =  1 ⁄ U_clean  +  R_f,h  +  R_f,c",
        "diagram": _diag_fouling,
        "source": "<b>TEMA Standards</b> RGP-T-2.4 (Recommended Good Practice on Fouling Factors).",
    },
    "hand_vs_fbm": {
        "title": "Hand (Sinnott) vs F_BM (Turton)",
        "icon": "topic-hand-vs-fbm",
        "body": (
            "<p>Los dos catálogos del simulador usan filosofías distintas para pasar de "
            "<em>equipment cost</em> a <em>installed cost</em>.</p>"
            "<p><b>Hand</b> usa un factor único por categoría de equipo (3.5 para HX, "
            "4.0 para torres y bombas). Es simple; sobreestima ~5–10% en equipos exóticos "
            "y subestima en equipos muy estándar.</p>"
            "<p><b>F_BM</b> parte de un factor base y lo modifica por material y presión. "
            "Más fino, pero pide saber F_M y F_P del equipo concreto.</p>"
        ),
        "formula": "Hand:  C_TIC = C_eq · f_install        F_BM:  F_BM = B₁ + B₂ · F_M · F_P",
        "diagram": _diag_hand_fbm,
        "source": "<b>Sinnott &amp; Towler,</b> Chem. Eng. Design 6th ed. §6.3.3 · "
                  "<b>Turton et al.,</b> 5th ed. App A.5.",
    },
    "approach": {
        "title": "Approach temperature (ΔT_min)",
        "icon": "topic-approach",
        "body": (
            "<p>El <em>approach</em> es la distancia térmica mínima entre las dos "
            "corrientes a lo largo del equipo. Define si el diseño es <b>físicamente "
            "posible</b> (debe ser positivo) y si es <b>económicamente sensato</b> "
            "(≥ regla del servicio).</p>"
            "<p>El motor calcula <b>ΔT_approach = min(T_h,o − T_c,i, T_h,i − T_c,o)</b> "
            "y avisa si baja del piso configurado. Approach negativo = cruce térmico, "
            "imposible sin segundo HX o utility distinta.</p>"
        ),
        "formula": "ΔT_approach = min(T_h,o − T_c,i,   T_h,i − T_c,o)",
        "diagram": _diag_approach,
        "source": "<b>Sinnott &amp; Towler,</b> Chem. Eng. Design 6th ed. §19.6 "
                  "(pinch &amp; ΔT_min) · <b>Linnhoff &amp; Hindmarsh,</b> "
                  "Chem. Eng. Sci. 38(5) (1983) 745–763.",
    },
    "sinnott_vs_turton": {
        "title": "Por qué el simulador mezcla Sinnott y Turton",
        "icon": "topic-catalog",
        "body": (
            "<p>El motor usa <b>Turton 2018</b> como catálogo principal: cubre todo el "
            "equipo clásico de proceso y tiene correlaciones validadas contra el método "
            "F_BM.</p>"
            "<p>Pero Turton <em>no</em> incluye <em>waste-heat boilers</em> a escala "
            "industrial. Por eso se agregó la rama <b>Sinnott 2019 Table 6.6</b> con dos "
            "sub-categorías (Packaged y Field-Erected) que cubren 5–200 t/h de vapor.</p>"
            "<p>Cada bloque sabe qué catálogo usar; el badge <em>Turton</em> o "
            "<em>Sinnott</em> en la sección Economía indica cuál se aplicó.</p>"
        ),
        "formula": None,
        "diagram": _diag_catalog,
        "source": "<b>Repo interno:</b> docs/sinnott_whb_addition_2026-05.md · "
                  "<b>Sinnott &amp; Towler</b> 6th ed. §6.3.",
    },
    "whb_scale": {
        "title": "WHB Sinnott — escala válida",
        "icon": "topic-whb",
        "body": (
            "<p>La correlación Sinnott Packaged está calibrada para steam rates de "
            "<b>5 000 a 50 000 kg/h</b>. Debajo de 5 t/h no existe la unidad comercial "
            "como tal: se compra un boiler de planta o un kettle reboiler pequeño.</p>"
            "<p>Cuando el motor detecta steam rate &lt; 5 000 kg/h marca el bloque con "
            "<b>fuera_rango = True</b> y pinta el anchor rojo. La opción correcta suele "
            "ser <b>cambiar el modelo</b> del bloque, no forzar la correlación.</p>"
        ),
        "formula": "C_eq^Sinnott = a + b · Sⁿ        S ∈ [5 000 ; 50 000] kg/h (Packaged)",
        "diagram": _diag_whb_scale,
        "source": "<b>Repo interno:</b> docs/sinnott_whb_addition_2026-05.md §3.2 · "
                  "<b>Sinnott &amp; Towler</b> 6th ed. Table 6.6.",
    },
}


class EducationalPopover(QDialog):
    """Modal 480px con prosa + fórmula + diagrama SVG + fuente (scrolleable)."""

    def __init__(self, topic: str, parent=None, ctx: dict | None = None):
        super().__init__(parent)
        t = EDU_TOPICS.get(topic)
        self.setModal(True)
        self.setWindowTitle(t["title"] if t else "Ayuda")
        self.setFixedWidth(480)
        self.setMaximumHeight(620)
        self.setStyleSheet(f"QDialog {{ background: {TOK['bg_elev']}; }}")
        if not t:
            return
        ctx = ctx or {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # header
        hd = QFrame(); hd.setObjectName("eduHd")
        hl = QHBoxLayout(hd); hl.setContentsMargins(16, 14, 12, 14); hl.setSpacing(12)
        ic = QLabel(); ic.setFixedSize(38, 38); ic.setAlignment(Qt.AlignCenter)
        ic.setStyleSheet(
            f"background:{TOK['accent_tint']}; border-radius:10px; "
            f"border:1px solid {TOK['accent_soft']};")
        ic.setPixmap(hi.glyph_pixmap(t["icon"], 22, TOK["accent"], 1.5))
        hl.addWidget(ic)
        tl = QLabel(t["title"]); tl.setWordWrap(True)
        tl.setFont(QFont(pfd_fonts.SANS, 11, QFont.Bold))
        tl.setStyleSheet(f"color:{TOK['ink']};")
        hl.addWidget(tl, 1)
        xb = QPushButton("✕"); xb.setFixedSize(28, 28); xb.setCursor(Qt.PointingHandCursor)
        xb.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TOK['ink_mute']}; "
            f"border:0; border-radius:6px; font-size:14px; }} "
            f"QPushButton:hover {{ background:{TOK['bg_mute']}; color:{TOK['ink']}; }}")
        xb.clicked.connect(self.accept)
        hl.addWidget(xb, 0, Qt.AlignTop)
        hd.setStyleSheet(f"#eduHd {{ background:{TOK['bg_mute']}; "
                         f"border-bottom:1px solid {TOK['line']}; }}")
        root.addWidget(hd)

        # body (scrolleable)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(f"background:{TOK['bg_elev']};")
        body = QWidget(); bl = QVBoxLayout(body)
        bl.setContentsMargins(18, 14, 18, 6); bl.setSpacing(10)

        prose = QLabel(t["body"]); prose.setWordWrap(True)
        prose.setTextFormat(Qt.RichText)
        prose.setFont(QFont(pfd_fonts.SANS, 9))
        prose.setStyleSheet(f"color:{TOK['ink_mute']};")
        bl.addWidget(prose)

        if t.get("formula"):
            fcard = QFrame()
            fl = QVBoxLayout(fcard); fl.setContentsMargins(16, 14, 16, 14)
            flab = QLabel(t["formula"]); flab.setWordWrap(True)
            flab.setAlignment(Qt.AlignCenter)
            flab.setFont(QFont(pfd_fonts.MONO, 11, QFont.Medium))
            flab.setStyleSheet(f"color:{TOK['ink']};")
            fl.addWidget(flab)
            fcard.setStyleSheet(
                f"background:{TOK['bg_mute']}; border:1px solid {TOK['line']}; "
                f"border-radius:9px;")
            bl.addWidget(fcard)

        if t.get("diagram"):
            svg = t["diagram"](ctx["marker"]) if (topic == "whb_scale" and "marker" in ctx) \
                else t["diagram"]()
            dlab = QLabel(); dlab.setAlignment(Qt.AlignCenter)
            dlab.setPixmap(_svg_pixmap(svg, 380, 150))
            dlab.setFixedHeight(154)
            bl.addWidget(dlab)

        bl.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # source
        src = QLabel("<b>Fuente:</b> &nbsp;" + t["source"]); src.setWordWrap(True)
        src.setTextFormat(Qt.RichText)
        src.setFont(QFont(pfd_fonts.SANS, 8))
        src.setStyleSheet(
            f"color:{TOK['ink_soft']}; font-style:italic; "
            f"background:{TOK['bg']}; padding:12px 18px; "
            f"border-top:1px solid {TOK['line']};")
        root.addWidget(src)

        # footer
        ft = QFrame(); fl2 = QHBoxLayout(ft); fl2.setContentsMargins(14, 10, 14, 10)
        fl2.addStretch(1)
        cb = QPushButton("Cerrar"); cb.setCursor(Qt.PointingHandCursor)
        cb.setFont(QFont(pfd_fonts.SANS, 9, QFont.Medium))
        cb.setStyleSheet(
            f"QPushButton {{ background:{TOK['accent']}; color:white; border:0; "
            f"border-radius:7px; padding:6px 16px; }} "
            f"QPushButton:hover {{ background:{TOK['accent_deep']}; }}")
        cb.clicked.connect(self.accept)
        fl2.addWidget(cb)
        ft.setStyleSheet(f"background:{TOK['bg_mute']}; border-top:1px solid {TOK['line']};")
        root.addWidget(ft)


def open_topic(topic: str, parent=None, ctx: dict | None = None):
    """Helper: abre el popover educativo de un topic."""
    if topic not in EDU_TOPICS:
        return
    EducationalPopover(topic, parent=parent, ctx=ctx).exec()
