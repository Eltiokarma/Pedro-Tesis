"""hx_inspector.py — componentes Qt del Heat Exchanger riguroso.

Port de hx-components.jsx sobre el sistema base del BlockInspector
(block_inspector.py).  Provee:

  · build_hx_viewmodel(block, fs)  → dict view-model desde _hx_diagnostics
                                      / _whb_diagnostics (refresca on-open).
  · hx_empty_state(vm, block)      → 'streams_unresolved' | 'duty_zero' | None
  · widgets: DiagnosticCard, HXSourceRibbon, WarningPanel, WHBSubcomponent,
    CorrelationBadge, InstallChip, RigorousBlock, y los builders de sección
    que el BlockInspector inserta cuando el bloque es un HX.

El popover educativo vive en hx_edu.py; acá sólo se dispara via callback.
"""
from __future__ import annotations

from typing import Optional, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPainter, QColor, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QSizePolicy,
)

import pfd_fonts
from block_inspector import TOK
import hx_icons as hi


# ════════════════════════════════════════════════════════════════════
#  VIEW-MODEL  — adapta los diagnostics del motor a lo que la UI dibuja
# ════════════════════════════════════════════════════════════════════
def _classify_warning(text: str, F: Optional[float]) -> Optional[dict]:
    """Mapea un warning de texto del motor a {kind, desc} del catálogo UI.
    Devuelve None para notas que no son avisos termodinámicos (ej. fallback)."""
    t = (text or "").lower()
    if t.startswith("fallback:"):
        return None
    if "cruce térmico" in t or "cruce de temperaturas" in t:
        return {"kind": "crossing", "desc": text}
    if "approach mínimo violado" in t:
        return {"kind": "approach_low", "desc": text}
    if "f=" in t or "f no computable" in t or "factor f" in t:
        crit = (F is not None and F <= 0.75) or "no computable" in t
        return {"kind": "f_critical" if crit else "f_low", "desc": text}
    if "utility" in t and "fuera de rango" in t:
        return {"kind": "utility_T_out", "desc": text}
    if "t_proceso" in t or "t promedio" in t:
        return {"kind": "t_avg_out", "desc": text}
    return {"kind": "approach_low", "desc": text}     # genérico (warn)


def _whb_range(eq_type: str):
    """Rango RECOMENDADO de operación Sinnott Table 6.6 (no el ceiling
    de extrapolación del catálogo): packaged 5–50 t/h, field 20–800 t/h."""
    if "field" in eq_type.lower():
        return (20000.0, 800000.0)
    return (5000.0, 50000.0)


def build_hx_viewmodel(block, fs) -> Optional[dict]:
    """Refresca y lee los diagnostics térmicos del HX, devolviendo el
    view-model que consumen los widgets.  None si el bloque no es HX."""
    try:
        import equipment_costs as ec
        import equipment_sizing as es
    except Exception:
        return None
    spec = ec.EQUIPMENT_DATA.get(block.eq_type, {})
    if spec.get("categoria") != "Heat exchangers":
        return None

    # refresca diagnostics on-open (el solve/auto_size pudo no haber corrido)
    try:
        es.size_heat_exchanger(block, fs)
    except Exception:
        pass
    is_whb = block.eq_type in getattr(es, "WHB_STEAM_SIZED", ())
    if is_whb:
        try:
            es.size_whb(block, fs)
        except Exception:
            pass

    diag = dict(getattr(block, "_hx_diagnostics", {}) or {})
    F = diag.get("F")
    raw_warnings = diag.get("warnings", []) or []
    warnings = []
    for w in raw_warnings:
        cw = _classify_warning(w, F)
        if cw:
            warnings.append(cw)

    data_source = diag.get("data_source") or "hardcoded_fallback"

    vm = {
        "dTlm": diag.get("dTlm"),
        "F": F if F is not None else 1.0,
        "U_eff": diag.get("U_used"),
        "approach": diag.get("approach"),
        "dT_min": diag.get("dT_min", 10.0),
        "data_source": data_source,
        "n_shell": diag.get("n_shell", 1),
        "n_tube": diag.get("n_tube", 2),
        "service": diag.get("service"),
        "T_h_in": diag.get("T_h_in"), "T_h_out": diag.get("T_h_out"),
        "T_c_in": diag.get("T_c_in"), "T_c_out": diag.get("T_c_out"),
        "duty": float(getattr(block, "duty", 0.0) or 0.0),
        "warnings": warnings,
        "whb": None,
        "is_cross": False,
    }
    cc = (diag.get("cross_check") or "")
    vm["is_cross"] = cc.startswith("cross-exchange")

    if is_whb:
        wd = getattr(block, "_whb_diagnostics", None)
        if wd:
            steam = float(wd.get("steam_rate_kg_h", 0.0) or 0.0)
            rmin, rmax = _whb_range(block.eq_type)
            fuera = steam < rmin
            mism = bool(wd.get("scale_mismatch", False))
            variant = ("Field erected" if "field" in block.eq_type.lower()
                       else "Packaged")
            steam_t_yr = steam * 8000.0 / 1000.0   # 8000 h/yr operación
            vm["whb"] = {
                "steam_kg_per_h": steam, "range_min": rmin, "range_max": rmax,
                "variant": variant, "scale_mismatch": mism, "fuera_rango": fuera,
                "steam_exported_t_y": steam_t_yr, "revenue_usd_y": None,
            }
            if fuera:
                vm["warnings"].insert(0, {"kind": "sinnott_out",
                                          "desc": wd.get("warning") or
                                          f"steam {steam:.0f} kg/h < {rmin:.0f} kg/h"})
            elif mism:
                vm["warnings"].insert(0, {"kind": "scale_mismatch",
                                          "desc": wd.get("warning") or "scale mismatch"})
    return vm


def hx_empty_state(vm: dict, block) -> Optional[str]:
    """Empty-state honesto en lugar del form vacío con guiones."""
    if vm is None:
        return None
    if vm.get("whb"):
        return None                                  # el WHB tiene su panel
    duty = vm.get("duty", 0.0)
    if abs(duty) <= 1e-9:
        return "duty_zero"
    if (vm.get("data_source") == "hardcoded_fallback"
            and vm.get("dTlm") is None
            and vm.get("T_h_in") is None):
        return "streams_unresolved"
    return None


def hx_block_status(vm: dict) -> str:
    """error > warn > fallback > ok (orden de severidad determinístico)."""
    if not vm:
        return "ok"
    if vm.get("data_source") == "hardcoded_fallback":
        return "fallback"
    ap, dtmin, F = vm.get("approach"), vm.get("dT_min", 10.0), vm.get("F", 1.0)
    if ap is not None and ap < 0:
        return "error"
    if F < 0.75:
        return "error"
    if any(w["kind"] in ("crossing", "f_critical", "sinnott_out")
           for w in vm.get("warnings", [])):
        return "error"
    if ap is not None and ap < dtmin:
        return "warn"
    if F < 0.85:
        return "warn"
    if vm.get("warnings"):
        return "warn"
    return "ok"


# ════════════════════════════════════════════════════════════════════
#  helpers de estilo
# ════════════════════════════════════════════════════════════════════
def _subsect_header(title: str, sub: str = "") -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(8)
    tl = QLabel(title.upper())
    f = QFont(pfd_fonts.SANS, 8, QFont.DemiBold); f.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
    tl.setFont(f)
    tl.setStyleSheet(f"color:{TOK['ink_soft']};")
    lay.addWidget(tl)
    lay.addStretch(1)
    if sub:
        sb = QLabel(sub); sb.setFont(QFont(pfd_fonts.MONO, 8))
        sb.setStyleSheet(f"color:{TOK['ink_soft']};")
        lay.addWidget(sb)
    return w


def _fmt(v, nd: int) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.{nd}f}"
    except Exception:
        return str(v)


def _grp(n: float) -> str:
    return f"{int(round(n)):,}".replace(",", " ")


# ════════════════════════════════════════════════════════════════════
#  HXSourceRibbon — sub-tipo de 'auto': computed / partial / fallback
# ════════════════════════════════════════════════════════════════════
class HXSourceRibbon(QLabel):
    def __init__(self, source: str, parent=None):
        super().__init__(parent)
        kind = {"computed_from_streams": ("computed", TOK["green"], TOK["green_bg"], False),
                "partial_from_utility_range": ("partial", TOK["amber"], TOK["amber_bg"], False),
                }.get(source, ("fallback", TOK["ink_soft"], "transparent", True))
        label, fg, bg, dashed = kind
        self.setText(label)
        f = QFont(pfd_fonts.MONO, 7, QFont.Bold); f.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
        self.setFont(f)
        border = (f"1px dashed {TOK['ink_ghost']}" if dashed else "0")
        self.setStyleSheet(
            f"color:{fg}; background:{bg}; border:{border}; "
            f"border-radius:3px; padding:1px 6px;")
        self.setAlignment(Qt.AlignCenter)


# ════════════════════════════════════════════════════════════════════
#  DiagnosticCard — card 2×2 clickeable
# ════════════════════════════════════════════════════════════════════
class DiagnosticCard(QFrame):
    clicked = Signal()

    def __init__(self, label, value, unit="", state="ok",
                 source="computed_from_streams", subtext=None,
                 topic=None, corner_icon=None, on_open=None, parent=None):
        super().__init__(parent)
        self._topic = topic
        self._on_open = on_open
        self._state = state
        self.setObjectName("hxDiag")
        self._apply_bg()
        if topic:
            self.setCursor(Qt.PointingHandCursor)

        outer = QHBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        # ribbon lateral
        self._ribbon = QFrame(); self._ribbon.setFixedWidth(3)
        rib = {"ok": TOK["green"], "warn": TOK["amber"], "error": TOK["danger"],
               "fallback": TOK["ink_ghost"]}.get(state, TOK["auto_ribbon"])
        self._ribbon.setStyleSheet(f"background:{rib}; border-radius:0 2px 2px 0;")
        outer.addWidget(self._ribbon)

        col = QVBoxLayout(); col.setContentsMargins(11, 9, 11, 9); col.setSpacing(3)
        # label + corner
        top = QHBoxLayout(); top.setContentsMargins(0, 0, 0, 0); top.setSpacing(5)
        lab = QLabel(label); lab.setFont(QFont(pfd_fonts.SANS, 8))
        lab.setStyleSheet(f"color:{TOK['ink_mute']};")
        top.addWidget(lab); top.addStretch(1)
        if corner_icon:
            ccol = {"warn": TOK["amber"], "error": TOK["danger"]}.get(state, TOK["ink_soft"])
            top.addWidget(hi.GlyphLabel(corner_icon, 13, ccol, 1.7))
        col.addLayout(top)
        # value
        vrow = QHBoxLayout(); vrow.setContentsMargins(0, 0, 0, 0); vrow.setSpacing(4)
        val = QLabel(value)
        vf = QFont(pfd_fonts.MONO, 17, QFont.DemiBold)
        if state == "fallback":
            vf.setItalic(True)
        val.setFont(vf)
        vcol = (TOK["danger"] if state == "error"
                else TOK["ink_mute"] if state == "fallback" else TOK["ink"])
        val.setStyleSheet(f"color:{vcol};")
        vrow.addWidget(val)
        if unit:
            u = QLabel(unit); u.setFont(QFont(pfd_fonts.MONO, 8))
            u.setStyleSheet(f"color:{TOK['ink_soft']};")
            vrow.addWidget(u, 0, Qt.AlignBottom)
        vrow.addStretch(1)
        col.addLayout(vrow)
        # sub
        sub = QHBoxLayout(); sub.setContentsMargins(0, 0, 0, 0); sub.setSpacing(6)
        if subtext is not None:
            st = QLabel(subtext); st.setFont(QFont(pfd_fonts.SANS, 8))
            st.setStyleSheet(f"color:{TOK['ink_mute']};")
            sub.addWidget(st)
        else:
            sub.addWidget(HXSourceRibbon(source))
        sub.addStretch(1)
        col.addLayout(sub)
        outer.addLayout(col, 1)

    def _apply_bg(self):
        bg = {"warn": TOK["amber_bg"], "error": TOK["danger_bg"]}.get(self._state, TOK["bg_elev"])
        border = TOK["line"]
        self.setStyleSheet(
            f"#hxDiag {{ background:{bg}; border:1px solid {border}; "
            f"border-radius:9px; }}")

    def enterEvent(self, e):
        if self._topic:
            bg = {"warn": TOK["amber_bg"], "error": TOK["danger_bg"]}.get(self._state, TOK["bg_elev"])
            self.setStyleSheet(
                f"#hxDiag {{ background:{bg}; border:1px solid {TOK['accent']}; "
                f"border-radius:9px; }}")
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._apply_bg()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if self._topic and self._on_open:
            self._on_open(self._topic)
        self.clicked.emit()
        super().mousePressEvent(e)


def make_diagnostic_grid(vm: dict, on_open: Callable) -> QWidget:
    """4 DiagnosticCards 2×2 con ΔT_lm · F · U_eff · approach."""
    w = QWidget()
    g = QGridLayout(w); g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(8); g.setVerticalSpacing(8)
    fallback = vm["data_source"] == "hardcoded_fallback"
    cs = (lambda s: "fallback" if fallback else s)

    dTlm, F = vm["dTlm"], vm["F"]
    U, ap, dtmin = vm["U_eff"], vm["approach"], vm["dT_min"]
    crossing = dTlm is None or (ap is not None and ap < 0)
    fState = "error" if F < 0.75 else "warn" if F < 0.85 else "ok"
    aState = "error" if (ap is None or ap < 0) else "warn" if ap < dtmin else "ok"

    c1 = DiagnosticCard("ΔT_lm", _fmt(dTlm, 1), "K",
                        state=cs("error" if crossing else "ok"),
                        source=vm["data_source"], topic="lmtd", on_open=on_open)
    c2 = DiagnosticCard("F (Bowman)", _fmt(F, 2), "",
                        state=cs(fState), source=vm["data_source"],
                        subtext=f"{vm['n_shell']} shell × {vm['n_tube']} tube",
                        corner_icon=("warn-fcorrection" if fState != "ok" else None),
                        topic="f_correction", on_open=on_open)
    c3 = DiagnosticCard("U efectivo", _fmt(U, 0), "W/m²K",
                        state=cs("ok"), source=vm["data_source"],
                        topic="fouling", on_open=on_open)
    asub = (f"≥ ΔT_min {dtmin:.0f} K  ✓" if aState == "ok" else
            f"< ΔT_min {dtmin:.0f} K  ⚠" if aState == "warn" else
            "cruce térmico imposible  ✗")
    c4 = DiagnosticCard("Approach", _fmt(ap, 1), "K",
                        state=cs(aState), source=vm["data_source"], subtext=asub,
                        corner_icon=("warn-approach" if aState != "ok" else None),
                        topic="approach", on_open=on_open)
    for i, c in enumerate((c1, c2, c3, c4)):
        g.addWidget(c, i // 2, i % 2)
    return w


# ════════════════════════════════════════════════════════════════════
#  Empty states
# ════════════════════════════════════════════════════════════════════
def make_empty_state(kind: str) -> QWidget:
    DATA = {
        "streams_unresolved": (
            "empty-streams", "Necesito las temperaturas de los streams",
            "Para calcular ΔT_lm, F y U efectivo, primero resolvé (F5) o "
            "definí las T de los streams conectados al HX.",
            "Revisá que los streams entrantes tengan T fija o herencia."),
        "duty_zero": (
            "empty-duty", "Este intercambiador no está activo",
            "El duty es 0 kW — no hay transferencia de calor. Si es bypass "
            "podés borrarlo; si querés activarlo, definí una T objetivo en "
            "un stream de salida.", None),
        "cross_exchange": (
            "cross-exchange", "Cross-exchange detectado",
            "Este HX intercambia calor entre dos corrientes de proceso, no "
            "consume utility. Revisá Diseño térmico abajo.",
            "Si el ahorro de utility no se refleja en el OPEX, revisá el "
            "heat integration factor."),
    }
    icon, title, body, tip = DATA.get(kind, DATA["streams_unresolved"])
    w = QFrame()
    lay = QVBoxLayout(w); lay.setContentsMargins(20, 20, 20, 6); lay.setSpacing(10)
    lay.setAlignment(Qt.AlignHCenter)
    ic = hi.GlyphLabel(icon, 28, TOK["ink_soft"], 1.4); lay.addWidget(ic, 0, Qt.AlignHCenter)
    tl = QLabel(title); tl.setAlignment(Qt.AlignCenter); tl.setWordWrap(True)
    tl.setFont(QFont(pfd_fonts.SANS, 10, QFont.DemiBold))
    tl.setStyleSheet(f"color:{TOK['ink']};")
    lay.addWidget(tl)
    bd = QLabel(body); bd.setAlignment(Qt.AlignCenter); bd.setWordWrap(True)
    bd.setFont(QFont(pfd_fonts.SANS, 9)); bd.setStyleSheet(f"color:{TOK['ink_mute']};")
    lay.addWidget(bd)
    if tip:
        tp = QLabel("💡  " + tip); tp.setAlignment(Qt.AlignCenter); tp.setWordWrap(True)
        tp.setFont(QFont(pfd_fonts.SANS, 8)); tp.setStyleSheet(f"color:{TOK['ink_soft']};")
        lay.addWidget(tp)
    return w


# ════════════════════════════════════════════════════════════════════
#  WarningRow + WarningPanel
# ════════════════════════════════════════════════════════════════════
WARN_LIBRARY = {
    "approach_low":    ("warn-approach", "Approach bajo", "approach", "warn"),
    "crossing":        ("warn-crossing", "Cruce térmico imposible", "lmtd", "error"),
    "f_low":           ("warn-fcorrection", "F bajo — revisar pasos", "f_correction", "warn"),
    "f_critical":      ("warn-fcorrection", "F crítico — inaceptable", "f_correction", "error"),
    "fouling_extreme": ("warn-fouling", "Fouling extremo", "fouling", "warn"),
    "sinnott_out":     ("warn-range", "Fuera de rango Sinnott", "whb_scale", "error"),
    "scale_mismatch":  ("warn-scale", "Scale mismatch WHB", "whb_scale", "warn"),
    "utility_T_out":   ("warn-utility", "Utility fuera de rango T", "lmtd", "warn"),
    "t_avg_out":       ("warn-tavg", "T promedio fuera de validez", "sinnott_vs_turton", "warn"),
}


class WarningRow(QFrame):
    def __init__(self, kind, desc, on_open=None, parent=None):
        super().__init__(parent)
        glyph, title, topic, severity = WARN_LIBRARY.get(kind, WARN_LIBRARY["approach_low"])
        bg = {"warn": TOK["amber_bg"], "error": TOK["danger_bg"]}.get(severity, TOK["bg_elev"])
        gc = {"warn": TOK["amber"], "error": TOK["danger"]}.get(severity, TOK["ink_soft"])
        tc = TOK["danger"] if severity == "error" else TOK["ink"]
        self.setStyleSheet(
            f"QFrame {{ background:{bg}; border:1px solid {TOK['line']}; "
            f"border-radius:7px; }}")
        lay = QHBoxLayout(self); lay.setContentsMargins(11, 8, 10, 8); lay.setSpacing(10)
        lay.addWidget(hi.GlyphLabel(glyph, 16, gc, 1.6), 0, Qt.AlignTop)
        col = QVBoxLayout(); col.setContentsMargins(0, 0, 0, 0); col.setSpacing(2)
        tl = QLabel(title); tl.setFont(QFont(pfd_fonts.SANS, 9, QFont.DemiBold))
        tl.setStyleSheet(f"color:{tc};")
        col.addWidget(tl)
        dl = QLabel(desc); dl.setWordWrap(True); dl.setFont(QFont(pfd_fonts.SANS, 8))
        dl.setStyleSheet(f"color:{TOK['ink_mute']};")
        col.addWidget(dl)
        lay.addLayout(col, 1)
        cta = QPushButton("Ver explicación"); cta.setCursor(Qt.PointingHandCursor)
        cta.setFont(QFont(pfd_fonts.SANS, 8))
        cta.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{TOK['accent']}; "
            f"border:0; padding:2px 6px; border-radius:4px; }} "
            f"QPushButton:hover {{ background:{TOK['accent_tint']}; "
            f"color:{TOK['accent_deep']}; }}")
        if on_open:
            cta.clicked.connect(lambda: on_open(topic))
        lay.addWidget(cta, 0, Qt.AlignVCenter)


class WarningPanel(QWidget):
    def __init__(self, warnings, on_open=None, parent=None):
        super().__init__(parent)
        self._warnings = warnings
        self._on_open = on_open
        self._lay = QVBoxLayout(self); self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(5)
        self._expanded = False
        self._rebuild()

    def _rebuild(self):
        while self._lay.count():
            it = self._lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        shown = self._warnings if self._expanded else self._warnings[:3]
        for w in shown:
            self._lay.addWidget(WarningRow(w["kind"], w["desc"], self._on_open))
        more = len(self._warnings) - len(shown)
        if more > 0:
            btn = QPushButton(f"+{more} aviso{'s' if more != 1 else ''} más")
            btn.setCursor(Qt.PointingHandCursor); btn.setFont(QFont(pfd_fonts.SANS, 8))
            btn.setStyleSheet(
                f"QPushButton {{ background:{TOK['bg_mute']}; color:{TOK['ink_mute']}; "
                f"border:0; border-radius:6px; padding:6px 10px; text-align:left; }} "
                f"QPushButton:hover {{ color:{TOK['ink']}; }}")
            btn.clicked.connect(self._expand)
            self._lay.addWidget(btn, 0, Qt.AlignLeft)

    def _expand(self):
        self._expanded = True
        self._rebuild()


# ════════════════════════════════════════════════════════════════════
#  WHB subcomponent + range bar
# ════════════════════════════════════════════════════════════════════
class _RangeBar(QWidget):
    """Barra log de rango Sinnott con fill + marker."""

    def __init__(self, steam, rmin, rmax, state, parent=None):
        super().__init__(parent)
        self._steam, self._rmin, self._rmax, self._state = steam, rmin, rmax, state
        self.setFixedHeight(18)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _pos(self, kg):
        import math
        lo, hi = math.log10(self._rmin), math.log10(self._rmax)
        p = (math.log10(max(self._rmin * 0.5, kg)) - lo) / (hi - lo)
        return min(1.02, max(-0.02, p))

    def paintEvent(self, e):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        ty, th = 5, 8
        track = QPainterPath(); track.addRoundedRect(0, ty, w, th, 4, 4)
        p.fillPath(track, QColor(TOK["bg_elev"]))
        p.setPen(QColor(TOK["line"])); p.drawPath(track)
        mk = self._pos(self._steam)
        fill_c = {"ok": TOK["sinnott"], "warn": TOK["amber"], "error": TOK["danger"]}[self._state]
        fc = QColor(fill_c); fc.setAlpha(90)
        fill_w = (max(0.0, mk) * w) if self._state == "error" else w
        fpath = QPainterPath(); fpath.addRoundedRect(0, ty, fill_w, th, 4, 4)
        p.fillPath(fpath, fc)
        # marker
        mx = mk * w
        p.setPen(Qt.NoPen)
        p.fillRect(int(mx) - 1, 0, 2, h,
                   QColor(TOK["danger"] if self._state == "error" else TOK["ink"]))
        p.end()


class WHBSubcomponent(QFrame):
    def __init__(self, whb: dict, on_open=None, parent=None):
        super().__init__(parent)
        state = "error" if whb["fuera_rango"] else "warn" if whb["scale_mismatch"] else "ok"
        self.setStyleSheet(
            f"QFrame#whb {{ background:{TOK['sinnott_bg']}; "
            f"border:1px solid {TOK['sinnott']}; border-radius:9px; }}")
        self.setObjectName("whb")
        lay = QVBoxLayout(self); lay.setContentsMargins(12, 11, 12, 11); lay.setSpacing(8)

        # header
        hd = QHBoxLayout(); hd.setSpacing(7)
        ico = QLabel(); ico.setFixedSize(22, 22); ico.setAlignment(Qt.AlignCenter)
        ico.setStyleSheet(f"background:{TOK['sinnott_bg']}; border-radius:5px;")
        ico.setPixmap(hi.glyph_pixmap("topic-whb", 14, TOK["sinnott_ink"], 1.6))
        hd.addWidget(ico)
        tl = QLabel("WHB · Generación de vapor")
        tl.setFont(QFont(pfd_fonts.SANS, 9, QFont.DemiBold))
        tl.setStyleSheet(f"color:{TOK['sinnott_ink']};")
        hd.addWidget(tl); hd.addStretch(1)
        st_txt = {"ok": "dentro de rango", "warn": "scale mismatch",
                  "error": "fuera de rango"}[state]
        st_c = {"ok": TOK["green"], "warn": TOK["amber"], "error": TOK["danger"]}[state]
        pill = QLabel(st_txt); pill.setFont(QFont(pfd_fonts.SANS, 8, QFont.DemiBold))
        pill.setStyleSheet(
            f"color:{st_c}; background:{TOK['bg_elev']}; border:1px solid {st_c}; "
            f"border-radius:9px; padding:2px 8px;")
        hd.addWidget(pill)
        lay.addLayout(hd)

        # rows
        def row(label, value, right_w):
            r = QHBoxLayout(); r.setSpacing(8)
            l = QLabel(label); l.setFont(QFont(pfd_fonts.SANS, 8))
            l.setStyleSheet(f"color:{TOK['ink_mute']};"); l.setFixedWidth(92)
            r.addWidget(l)
            v = QLabel(value); v.setFont(QFont(pfd_fonts.MONO, 9))
            v.setStyleSheet(f"color:{TOK['ink']};")
            r.addWidget(v); r.addStretch(1)
            if right_w:
                r.addWidget(right_w)
            return r
        lay.addLayout(row("Tasa de vapor", f"{_grp(whb['steam_kg_per_h'])} kg/h",
                          HXSourceRibbon("computed_from_streams")))
        src = QLabel("Sinnott '19"); src.setFont(QFont(pfd_fonts.SANS, 8))
        src.setStyleSheet(f"color:{TOK['sinnott_ink']};")
        lay.addLayout(row(f"Rango {whb['variant']}",
                          f"{_grp(whb['range_min'])} – {_grp(whb['range_max'])}", src))
        if whb.get("steam_exported_t_y") is not None:
            lay.addLayout(row("Vapor exportado",
                              f"{_grp(whb['steam_exported_t_y'])} tm/yr", None))

        # range bar
        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{TOK['sinnott']};")
        lay.addWidget(sep)
        lay.addWidget(_RangeBar(whb["steam_kg_per_h"], whb["range_min"],
                                whb["range_max"], state))
        bounds = QHBoxLayout()
        b1 = QLabel(_grp(whb["range_min"])); b1.setFont(QFont(pfd_fonts.MONO, 7))
        b2 = QLabel("↑ " + _grp(whb["steam_kg_per_h"]))
        b2.setFont(QFont(pfd_fonts.MONO, 7, QFont.DemiBold))
        b3 = QLabel(_grp(whb["range_max"])); b3.setFont(QFont(pfd_fonts.MONO, 7))
        for b in (b1, b2, b3):
            b.setStyleSheet(f"color:{TOK['ink_soft']};")
        b2.setStyleSheet(f"color:{TOK['danger'] if state=='error' else TOK['ink']};")
        bounds.addWidget(b1); bounds.addStretch(1); bounds.addWidget(b2)
        bounds.addStretch(1); bounds.addWidget(b3)
        lay.addLayout(bounds)

        msg = {"ok": "Tu HX está bien dimensionado para esta correlación.",
               "warn": "Tu HX está cerca del piso del rango; el factor de instalación queda aproximado.",
               "error": "Tu HX está fuera del rango; considerá un kettle reboiler o un boiler de planta."}[state]
        ml = QLabel(msg); ml.setWordWrap(True); ml.setFont(QFont(pfd_fonts.SANS, 8))
        ml.setStyleSheet(f"color:{TOK['ink_mute']}; font-style:italic;")
        lay.addWidget(ml)
        if state == "error" and on_open:
            why = QPushButton("Por qué →"); why.setCursor(Qt.PointingHandCursor)
            why.setFont(QFont(pfd_fonts.SANS, 8))
            why.setStyleSheet(
                f"QPushButton {{ background:transparent; color:{TOK['accent']}; "
                f"border:0; text-align:left; padding:0; }} "
                f"QPushButton:hover {{ color:{TOK['accent_deep']}; }}")
            why.clicked.connect(lambda: on_open("whb_scale",
                                {"marker": whb["steam_kg_per_h"]}))
            lay.addWidget(why, 0, Qt.AlignLeft)


# ════════════════════════════════════════════════════════════════════
#  Correlation badge + install chip
# ════════════════════════════════════════════════════════════════════
class CorrelationBadge(QPushButton):
    def __init__(self, which, year, source_full="", on_open=None, parent=None):
        super().__init__(parent)
        is_sinnott = which == "sinnott"
        self.setText(("Sinnott  " if is_sinnott else "Turton  ") + str(year))
        self.setCursor(Qt.PointingHandCursor)
        self.setFont(QFont(pfd_fonts.MONO, 8, QFont.DemiBold))
        if source_full:
            self.setToolTip(source_full)
        bg = TOK["sinnott_bg"] if is_sinnott else TOK["spec_bg"]
        fg = TOK["sinnott_ink"] if is_sinnott else TOK["turton_ink"]
        bd = TOK["sinnott"] if is_sinnott else TOK["spec"]
        self.setStyleSheet(
            f"QPushButton {{ background:{bg}; color:{fg}; border:1px solid {bd}; "
            f"border-radius:6px; padding:3px 9px; }} "
            f"QPushButton:hover {{ background:{bg}; }}")
        if on_open:
            self.clicked.connect(lambda: on_open("sinnott_vs_turton"))


class InstallChip(QLabel):
    def __init__(self, method, factor, sinnott=False, parent=None):
        super().__init__(parent)
        if method == "hand":
            txt = f"Hand {factor:.1f}"
        else:
            txt = "F_BM dinámico"
        self.setText(txt)
        self.setFont(QFont(pfd_fonts.SANS, 8, QFont.Medium))
        if sinnott:
            self.setStyleSheet(
                f"color:{TOK['sinnott_ink']}; background:{TOK['sinnott_bg']}; "
                f"border:1px solid {TOK['sinnott']}; border-radius:6px; padding:2px 8px;")
        else:
            self.setStyleSheet(
                f"color:{TOK['ink_mute']}; background:{TOK['bg_mute']}; "
                f"border:1px solid {TOK['line']}; border-radius:6px; padding:2px 8px;")


def make_correlation_badges(block, on_open) -> Optional[QWidget]:
    """Row con CorrelationBadge + InstallChip desde el catálogo del bloque."""
    try:
        import equipment_costs as ec
        spec = ec.EQUIPMENT_DATA.get(block.eq_type, {})
        corr = spec.get("correlation", "turton")
        source = spec.get("source", "")
        pc = ec.bare_module_cost(block.eq_type, float(getattr(block, "S", 0) or 0),
                                 P_op_bar=float(getattr(block, "P_op_bar", 1.0) or 1.0))
    except Exception:
        return None
    year = "2024"
    is_sinnott = corr == "sinnott"
    method = "hand" if is_sinnott else "fbm"
    factor = float(pc.get("FBM", 3.5) or 3.5)
    w = QWidget()
    lay = QHBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(6)
    lay.addStretch(1)
    lay.addWidget(CorrelationBadge(corr, year, source, on_open))
    lay.addWidget(InstallChip(method, factor, sinnott=is_sinnott))
    return w


# ════════════════════════════════════════════════════════════════════
#  RigorousBlock (disclosure colapsable)
# ════════════════════════════════════════════════════════════════════
class RigorousBlock(QFrame):
    def __init__(self, vm: dict, default_open=False, parent=None):
        super().__init__(parent)
        self.setObjectName("rig")
        self.setStyleSheet(
            f"#rig {{ background:{TOK['bg_elev']}; border:1px solid {TOK['line']}; "
            f"border-radius:9px; }}")
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)

        self._hd = QFrame(); self._hd.setCursor(Qt.PointingHandCursor)
        hl = QHBoxLayout(self._hd); hl.setContentsMargins(12, 10, 12, 10); hl.setSpacing(8)
        self._tri = hi.GlyphLabel("tri-right", 10, TOK["ink_soft"], 0)
        hl.addWidget(self._tri)
        tl = QLabel("Diseño riguroso"); tl.setFont(QFont(pfd_fonts.SANS, 9, QFont.DemiBold))
        tl.setStyleSheet(f"color:{TOK['ink']};")
        hl.addWidget(tl)
        sub = QLabel("servicio · pasos · U"); sub.setFont(QFont(pfd_fonts.MONO, 8))
        sub.setStyleSheet(f"color:{TOK['ink_soft']};")
        hl.addWidget(sub); hl.addStretch(1)
        self._hd.mousePressEvent = lambda e: self._toggle()
        root.addWidget(self._hd)

        self._body = QFrame()
        self._body.setStyleSheet(f"border-top:1px solid {TOK['line_soft']};")
        bl = QVBoxLayout(self._body); bl.setContentsMargins(12, 8, 12, 12); bl.setSpacing(6)

        def kv(label, value):
            r = QHBoxLayout(); r.setSpacing(10)
            l = QLabel(label); l.setFont(QFont(pfd_fonts.SANS, 9))
            l.setStyleSheet(f"color:{TOK['ink_mute']};"); l.setMinimumWidth(150)
            r.addWidget(l)
            v = QLabel(value); v.setFont(QFont(pfd_fonts.MONO, 9))
            v.setStyleSheet(f"color:{TOK['ink']};")
            r.addWidget(v); r.addStretch(1)
            return r
        bl.addLayout(kv("Servicio", vm.get("service") or "—"))
        bl.addLayout(kv("Pasos shell × tubos", f"{vm['n_shell']} × {vm['n_tube']}"))
        bl.addLayout(kv("U efectivo", _fmt(vm["U_eff"], 0) + " W/m²K"))
        if vm.get("T_h_in") is not None:
            bl.addLayout(kv("T caliente in/out",
                            f"{_fmt(vm['T_h_in'],0)} / {_fmt(vm['T_h_out'],0)} K"))
            bl.addLayout(kv("T fría in/out",
                            f"{_fmt(vm['T_c_in'],0)} / {_fmt(vm['T_c_out'],0)} K"))
        note = QLabel("El fouling está plegado en el U de servicio (tablas "
                      "Perry/Sinnott por par de fluidos), no se modela R_f por separado.")
        note.setWordWrap(True); note.setFont(QFont(pfd_fonts.SANS, 8))
        note.setStyleSheet(f"color:{TOK['ink_soft']}; font-style:italic;")
        bl.addWidget(note)
        root.addWidget(self._body)

        self._open = default_open
        self._body.setVisible(self._open)
        self._sync_tri()

    def _toggle(self):
        self._open = not self._open
        self._body.setVisible(self._open)
        self._sync_tri()

    def _sync_tri(self):
        self._tri.set_glyph("tri-down" if self._open else "tri-right",
                            TOK["accent"] if self._open else TOK["ink_soft"])
