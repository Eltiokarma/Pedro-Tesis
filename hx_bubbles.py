"""hx_bubbles.py — burbujas flotantes de diagnóstico HX, ancladas al bloque.

Análogo a stream_bubbles.StreamBubble pero por BLOQUE: muestra el
diagnóstico térmico del intercambiador (ΔT_lm, F, U_eff, approach, avisos)
en una tarjeta flotante conectada al bloque por un leader Bézier con un
anchor-dot coloreado por estado (ok/warn/error/fallback).

Default OFF — el user la activa con click derecho sobre un HX →
"Mostrar diagnóstico HX".  Persistencia en block.bubble_visible /
bubble_position / bubble_density.

Piezas (espejo de stream_bubbles):
  · HXBubble(QFrame)        — el widget visual (3 densidades).
  · HXLeaderOverlay(QWidget)— capa que pinta leaders + anchor-dot por estado.
  · HXBubbleManager         — orquesta vida/posición/refresh.
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import (
    Qt, Signal, QPoint, QPointF, QEvent, QObject, QSize,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush, QPainterPath, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel,
    QToolButton, QGraphicsView, QLayout,
)

import pfd_fonts
from block_inspector import TOK
import hx_icons as hi
import hx_inspector as hxui


_STATUS_COLOR = lambda s: {
    "ok": TOK["green"], "warn": TOK["amber"], "error": TOK["danger"],
    "fallback": TOK["status_fallback"],
}.get(s, TOK["ink_soft"])

_SOURCE_LABEL = {
    "computed_from_streams": "computed",
    "partial_from_utility_range": "partial",
    "hardcoded_fallback": "fallback",
}

_DENSITY_NEXT = {"collapsed": "standard", "standard": "expanded", "expanded": "collapsed"}


class HXBubble(QFrame):
    positionChanged  = Signal(int, float, float)
    positionDragging = Signal(int, float, float)
    closeRequested   = Signal(int)
    densityChanged   = Signal(int, str)
    openTopic        = Signal(str)

    def __init__(self, block_id: int, parent=None):
        super().__init__(parent)
        self._block_id = block_id
        self._density = "standard"
        self._vm: Optional[dict] = None
        self._tag = "?"
        self._drag_offset: Optional[QPoint] = None
        self._is_dragging = False

        self.setObjectName("hxBubble")
        self.setMinimumWidth(150)
        self._apply_style(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        # SetFixedSize: el widget SIEMPRE se ajusta a su contenido cuando
        # el body se reconstruye (sin resize/adjustSize manual ni lag de tick).
        outer.setSizeConstraint(QLayout.SetFixedSize)
        self._header = self._build_header()
        outer.addWidget(self._header)
        self._body = QFrame(self); self._body.setObjectName("hxbBody")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(10, 7, 10, 8)
        self._body_layout.setSpacing(3)
        outer.addWidget(self._body)

        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            sh = QGraphicsDropShadowEffect(self)
            sh.setBlurRadius(18); sh.setOffset(0, 4)
            c = QColor(40, 30, 20); c.setAlphaF(0.18); sh.setColor(c)
            self.setGraphicsEffect(sh)
        except Exception:
            pass

    # ── API ──────────────────────────────────────────────
    def block_id(self) -> int:
        return self._block_id

    def status(self) -> str:
        return hxui.hx_block_status(self._vm) if self._vm else "fallback"

    def is_dragging(self) -> bool:
        return self._is_dragging

    def update_values(self, tag: str, vm: dict):
        self._tag = tag or "?"
        self._vm = vm
        self._tag_lbl.setText(self._tag)
        st = self.status()
        src = _SOURCE_LABEL.get((vm or {}).get("data_source"), "fallback")
        self._status_lbl.setText(src)
        self._status_lbl.setStyleSheet(
            f"color:{_STATUS_COLOR(st)}; background:{TOK['bg_mute']}; "
            f"font-family:'{pfd_fonts.MONO}'; font-size:7pt; font-weight:700; "
            f"padding:1px 5px; border-radius:3px;")
        self._refresh_body()

    def set_density(self, density: str):
        if density not in _DENSITY_NEXT:
            density = "standard"
        self._density = density
        self._refresh_body()

    def attachment_point(self, leader_from: QPoint) -> QPoint:
        x, y, w, h = self.x(), self.y(), self.width(), self.height()
        cx, cy = x + w / 2, y + h / 2
        dx, dy = leader_from.x() - cx, leader_from.y() - cy
        if abs(dx) > abs(dy):
            return QPoint(int(x + w if dx > 0 else x), int(cy))
        return QPoint(int(cx), int(y + h if dy > 0 else y))

    # ── construcción ─────────────────────────────────────
    def _apply_style(self, dragging: bool):
        border = TOK["accent_soft"] if dragging else TOK["line"]
        bw = "1.5px" if dragging else "1px"
        self.setStyleSheet(
            f"#hxBubble {{ background:{TOK['bg_elev']}; "
            f"border:{bw} solid {border}; border-radius:10px; }} "
            f"#hxbHeader {{ background:{TOK['bg']}; "
            f"border-bottom:1px solid {TOK['line_soft']}; "
            f"border-top-left-radius:10px; border-top-right-radius:10px; }} "
            f"#hxbBody {{ background:transparent; }}")

    def _icbtn_style(self) -> str:
        return (f"QToolButton {{ background:transparent; color:{TOK['ink_soft']}; "
                f"border:0; border-radius:4px; font-size:10px; }} "
                f"QToolButton:hover {{ background:{TOK['bg_mute']}; color:{TOK['ink']}; }}")

    def _build_header(self) -> QFrame:
        hd = QFrame(self); hd.setObjectName("hxbHeader")
        hd.setFixedHeight(28); hd.setCursor(Qt.OpenHandCursor)
        lay = QHBoxLayout(hd); lay.setContentsMargins(7, 5, 6, 5); lay.setSpacing(6)
        grip = QLabel("⋮⋮", hd); grip.setFixedSize(8, 14); grip.setAlignment(Qt.AlignCenter)
        grip.setStyleSheet(f"color:{TOK['ink_ghost']}; font-size:10px; letter-spacing:-2px;")
        lay.addWidget(grip)
        self._tag_lbl = QLabel("?", hd)
        self._tag_lbl.setFont(QFont(pfd_fonts.MONO, 9, QFont.DemiBold))
        self._tag_lbl.setStyleSheet(f"color:{TOK['ink']};")
        lay.addWidget(self._tag_lbl)
        typ = QLabel("HX", hd); typ.setFont(QFont(pfd_fonts.MONO, 7, QFont.Bold))
        typ.setStyleSheet(
            f"color:{TOK['ink_soft']}; background:{TOK['bg_mute']}; "
            f"padding:1px 5px; border-radius:3px; letter-spacing:1px;")
        lay.addWidget(typ)
        self._status_lbl = QLabel("", hd)
        self._status_lbl.setFont(QFont(pfd_fonts.MONO, 7, QFont.Bold))
        lay.addWidget(self._status_lbl)
        lay.addStretch(1)
        self._density_btn = QToolButton(hd); self._density_btn.setFixedSize(18, 18)
        self._density_btn.setText("▾"); self._density_btn.setCursor(Qt.PointingHandCursor)
        self._density_btn.setStyleSheet(self._icbtn_style())
        self._density_btn.clicked.connect(self._on_density_click)
        lay.addWidget(self._density_btn)
        close = QToolButton(hd); close.setFixedSize(18, 18); close.setText("✕")
        close.setCursor(Qt.PointingHandCursor); close.setStyleSheet(self._icbtn_style())
        close.clicked.connect(lambda: self.closeRequested.emit(self._block_id))
        lay.addWidget(close)
        return hd

    def _on_density_click(self):
        self.set_density(_DENSITY_NEXT.get(self._density, "standard"))
        self.densityChanged.emit(self._block_id, self._density)

    def _clear_body(self):
        lay = self._body_layout
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None); w.deleteLater()

    def _refresh_body(self):
        self._clear_body()
        vm = self._vm or {}
        self._density_btn.setText("▴" if self._density == "expanded" else "▾")

        def num(v, nd):
            if v is None:
                return "—"
            try:
                return f"{float(v):.{nd}f}"
            except Exception:
                return str(v)

        if self._density == "collapsed":
            self._body.setVisible(True)
            self._density_btn.setText("▸")
            soft, ink, mono = TOK["ink_soft"], TOK["ink"], pfd_fonts.MONO
            inline = QLabel(self._body); inline.setTextFormat(Qt.RichText)
            inline.setText(
                f'<span style="color:{soft};font-size:8pt;">ΔT_lm</span> '
                f'<span style="color:{ink};font-family:\'{mono}\';font-size:9pt;font-weight:600;">{num(vm.get("dTlm"),1)}</span>'
                f'<span style="color:{soft};">&nbsp;&nbsp;·&nbsp;&nbsp;</span>'
                f'<span style="color:{soft};font-size:8pt;">F</span> '
                f'<span style="color:{ink};font-family:\'{mono}\';font-size:9pt;font-weight:600;">{num(vm.get("F"),2)}</span>')
            self._body_layout.addWidget(inline)
            return
        self._body.setVisible(True)

        ap = vm.get("approach"); dtmin = vm.get("dT_min", 10.0)
        ap_state = ("error" if (ap is None or ap < 0)
                    else "warn" if ap < dtmin else "ok")
        rows = [
            ("ΔT_lm", num(vm.get("dTlm"), 1), "K", None),
            ("F", num(vm.get("F"), 2), "·", None),
            ("U_eff", num(vm.get("U_eff"), 0), "W/m²K", None),
            ("Approach", num(ap, 1), "K", _STATUS_COLOR(ap_state)),
        ]
        for label, val, unit, vcolor in rows:
            self._body_layout.addWidget(self._kv(label, val, unit, vcolor))

        if self._density == "expanded":
            if vm.get("service"):
                self._body_layout.addWidget(
                    self._kv("Servicio", vm["service"], "", None, mono=False))
            self._body_layout.addWidget(
                self._kv("Pasos", f"{vm.get('n_shell',1)}×{vm.get('n_tube',2)}", "", None))
            warns = vm.get("warnings", [])[:2]
            if warns:
                sep = QFrame(self._body); sep.setFixedHeight(1)
                sep.setStyleSheet(f"background:{TOK['line_soft']};")
                self._body_layout.addWidget(sep)
                for w in warns:
                    self._body_layout.addWidget(self._warn_line(w))

    def _kv(self, label, value, unit, vcolor, mono=True) -> QWidget:
        row = QFrame(self._body)
        r = QHBoxLayout(row); r.setContentsMargins(0, 0, 0, 0); r.setSpacing(6)
        k = QLabel(label); k.setFont(QFont(pfd_fonts.SANS, 8))
        k.setStyleSheet(f"color:{TOK['ink_mute']};"); k.setFixedWidth(64)
        r.addWidget(k)
        v = QLabel(value)
        v.setFont(QFont(pfd_fonts.MONO if mono else pfd_fonts.SANS, 8,
                        QFont.Medium if mono else QFont.Normal))
        v.setStyleSheet(f"color:{vcolor or TOK['ink']};")
        v.setAlignment(Qt.AlignRight if mono else Qt.AlignLeft)
        r.addWidget(v, 1)
        if unit:
            u = QLabel(unit); u.setFont(QFont(pfd_fonts.MONO, 7))
            u.setStyleSheet(f"color:{TOK['ink_soft']};"); u.setFixedWidth(38)
            r.addWidget(u)
        return row

    def _warn_line(self, w: dict) -> QWidget:
        glyph, title, topic, severity = hxui.WARN_LIBRARY.get(
            w["kind"], hxui.WARN_LIBRARY["approach_low"])
        c = TOK["danger"] if severity == "error" else TOK["amber"]
        row = QFrame(); lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 1, 0, 1); lay.setSpacing(5)
        lay.addWidget(hi.GlyphLabel(glyph, 12, c, 1.7))
        t = QLabel(title); t.setFont(QFont(pfd_fonts.SANS, 8))
        t.setStyleSheet(f"color:{c};")
        t.setCursor(Qt.PointingHandCursor)
        t.mousePressEvent = lambda e, tp=topic: self.openTopic.emit(tp)
        lay.addWidget(t, 1)
        return row

    # ── drag ─────────────────────────────────────────────
    def mousePressEvent(self, ev: QMouseEvent):
        if ev.button() == Qt.LeftButton:
            child = self.childAt(ev.position().toPoint())
            w = child
            while w is not None and w is not self:
                if w is self._header:
                    self._drag_offset = ev.globalPosition().toPoint() - self.pos()
                    self._is_dragging = True
                    self._header.setCursor(Qt.ClosedHandCursor)
                    self._apply_style(True)
                    ev.accept(); return
                w = w.parent()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev: QMouseEvent):
        if self._is_dragging and (ev.buttons() & Qt.LeftButton):
            new_pos = ev.globalPosition().toPoint() - self._drag_offset
            parent = self.parentWidget()
            if parent is not None:
                pr = parent.rect()
                new_pos = QPoint(max(0, min(new_pos.x(), pr.width() - 30)),
                                 max(0, min(new_pos.y(), pr.height() - 30)))
            self.move(new_pos)
            self.positionDragging.emit(self._block_id, float(new_pos.x()), float(new_pos.y()))
            ev.accept(); return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev: QMouseEvent):
        if self._is_dragging:
            self._is_dragging = False
            self._header.setCursor(Qt.OpenHandCursor)
            self._apply_style(False)
            self.positionChanged.emit(self._block_id, float(self.x()), float(self.y()))
            ev.accept(); return
        super().mouseReleaseEvent(ev)


# ════════════════════════════════════════════════════════
#  LEADER OVERLAY (anchor-dot coloreado por estado)
# ════════════════════════════════════════════════════════
class HXLeaderOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._links: List[Tuple[QPoint, QPoint, str, str]] = []

    def set_links(self, links):
        """links = [(from_pt, to_pt, dragging_state, status), …]."""
        self._links = list(links)
        self.update()

    def paintEvent(self, ev):
        if not self._links:
            return
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing, True)
        for src, dst, state, status in self._links:
            self._paint_one(p, src, dst, state, status)

    def _paint_one(self, p, src, dst, state, status):
        col = QColor(_STATUS_COLOR(status))
        # anchor dot
        p.setBrush(QBrush(QColor(TOK["bg_elev"])))
        p.setPen(QPen(col, 1.5))
        p.drawEllipse(QPointF(src), 4.5, 4.5)
        p.setBrush(QBrush(col)); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(src), 2.2, 2.2)
        dx, dy = dst.x() - src.x(), dst.y() - src.y()
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return
        mid = QPointF((src.x() + dst.x()) / 2.0, (src.y() + dst.y()) / 2.0)
        bend = min(20.0, length * 0.15)
        ctrl = QPointF(mid.x() + (-dy / length) * bend, mid.y() + (dx / length) * bend)
        path = QPainterPath(); path.moveTo(QPointF(src)); path.quadTo(ctrl, QPointF(dst))
        if state == "dragging":
            pen = QPen(col, 1.4); pen.setCapStyle(Qt.RoundCap); p.setOpacity(0.95)
        else:
            pen = QPen(QColor(TOK["ink_soft"]), 1.2)
            pen.setStyle(Qt.CustomDashLine); pen.setDashPattern([1.5, 4])
            pen.setCapStyle(Qt.RoundCap); p.setOpacity(0.8)
        p.setPen(pen); p.setBrush(Qt.NoBrush); p.drawPath(path); p.setOpacity(1.0)


# ════════════════════════════════════════════════════════
#  MANAGER
# ════════════════════════════════════════════════════════
class HXBubbleManager:
    def __init__(self, view: QGraphicsView, get_fs: Callable,
                 get_block_items_iter: Callable, open_topic: Callable = None):
        self.view = view
        self._get_fs = get_fs
        self.get_block_items_iter = get_block_items_iter
        self._open_topic = open_topic or (lambda t: None)
        self._bubbles: Dict[int, HXBubble] = {}

        vp = view.viewport()
        self.leader_overlay = HXLeaderOverlay(vp)
        sz = vp.size()
        if not sz.isValid() or sz.width() < 1:
            sz = QSize(800, 600)
        self.leader_overlay.resize(sz)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._deferred_init)

    def _deferred_init(self):
        vp = self.view.viewport()
        try:
            self.leader_overlay.resize(vp.size()); self.leader_overlay.show()
        except Exception:
            pass
        self._resizer = _OverlayResizer(self)
        vp.installEventFilter(self._resizer)
        try:
            self.view.horizontalScrollBar().valueChanged.connect(self._refresh_leaders)
            self.view.verticalScrollBar().valueChanged.connect(self._refresh_leaders)
        except Exception:
            pass

    @property
    def fs(self):
        try:
            return self._get_fs()
        except Exception:
            return None

    def _is_hx(self, block) -> bool:
        try:
            import equipment_costs as ec
            return ec.EQUIPMENT_DATA.get(block.eq_type, {}).get("categoria") == "Heat exchangers"
        except Exception:
            return False

    def refresh_all(self):
        fs = self.fs
        if fs is None:
            return
        blocks = fs.blocks
        by_id = blocks if isinstance(blocks, dict) else {b.id: b for b in blocks}
        ids = set(by_id.keys())
        for bid in list(self._bubbles.keys()):
            if bid not in ids or not getattr(by_id[bid], "bubble_visible", False):
                self._destroy_bubble(bid)
        for bid, b in by_id.items():
            if getattr(b, "bubble_visible", False) and self._is_hx(b):
                if bid not in self._bubbles:
                    self._create_bubble(b)
                self._refresh_bubble_values(b)
        self._refresh_leaders()

    def _create_bubble(self, block):
        vp = self.view.viewport()
        bub = HXBubble(block.id, parent=vp)
        bub.positionDragging.connect(self._on_dragging)
        bub.positionChanged.connect(self._on_drag_finished)
        bub.closeRequested.connect(self._on_close)
        bub.densityChanged.connect(self._on_density)
        bub.openTopic.connect(self._open_topic)
        bub.set_density(getattr(block, "bubble_density", "standard") or "standard")
        bp = getattr(block, "bubble_position", []) or []
        if len(bp) != 2:
            n = len(self._bubbles)
            block.bubble_position = [90.0, -40.0 + n * 20]
        self._bubbles[block.id] = bub
        self._position_bubble(block, bub)
        bub.show(); bub.raise_()

    def _refresh_bubble_values(self, block):
        bub = self._bubbles.get(block.id)
        if bub is None:
            return
        try:
            vm = hxui.build_hx_viewmodel(block, self.fs)
        except Exception:
            vm = None
        bub.update_values(getattr(block, "name", "?"), vm or {})

    def _position_bubble(self, block, bub: HXBubble):
        vp = self.view.viewport()
        bp = getattr(block, "bubble_position", []) or [90.0, -40.0]
        ox, oy = float(bp[0]), float(bp[1])
        c = self._block_center_viewport(block.id)
        if c is not None:
            x, y = int(c.x() + ox), int(c.y() + oy)
        else:
            n = list(self._bubbles.keys()).index(block.id) if block.id in self._bubbles else 0
            x, y = 180 + n * 24, 120 + n * 24
        x = max(0, min(x, max(0, vp.width() - 30)))
        y = max(0, min(y, max(0, vp.height() - 30)))
        if not bub.is_dragging():
            bub.move(x, y)

    def _destroy_bubble(self, bid: int):
        bub = self._bubbles.pop(bid, None)
        if bub is not None:
            bub.setParent(None); bub.deleteLater()

    def _refresh_leaders(self):
        if not self._bubbles:
            self.leader_overlay.set_links([]); return
        for bid, bub in self._bubbles.items():
            b = self._get_block(bid)
            if b is not None:
                self._position_bubble(b, bub)
        links = []
        for bid, bub in self._bubbles.items():
            c = self._block_center_viewport(bid)
            if c is None:
                continue
            state = "dragging" if bub.is_dragging() else "idle"
            links.append((c, bub.attachment_point(c), state, bub.status()))
        self.leader_overlay.set_links(links)
        self.leader_overlay.raise_()
        for bub in self._bubbles.values():
            bub.raise_()

    def _block_center_viewport(self, bid: int) -> Optional[QPoint]:
        try:
            for b_id, item in self.get_block_items_iter():
                if b_id != bid:
                    continue
                try:
                    br = item.sceneBoundingRect()
                    scene_p = QPointF(br.center())
                except Exception:
                    return None
                view_p = self.view.mapFromScene(scene_p)
                return QPoint(int(view_p.x()), int(view_p.y()))
        except Exception:
            return None
        return None

    # ── callbacks ────────────────────────────────────────
    def _on_dragging(self, bid, x, y):
        self._refresh_leaders()

    def _on_drag_finished(self, bid, x, y):
        b = self._get_block(bid)
        if b is None:
            return
        c = self._block_center_viewport(bid)
        if c is not None:
            b.bubble_position = [float(x - c.x()), float(y - c.y())]
        else:
            b.bubble_position = [float(x), float(y)]
        self._refresh_leaders()

    def _on_close(self, bid):
        b = self._get_block(bid)
        if b is not None:
            b.bubble_visible = False
        self._destroy_bubble(bid)
        self._refresh_leaders()

    def _on_density(self, bid, density):
        b = self._get_block(bid)
        if b is not None:
            b.bubble_density = density
        self._refresh_leaders()

    def _get_block(self, bid):
        fs = self.fs
        if fs is None:
            return None
        blocks = fs.blocks
        if isinstance(blocks, dict):
            return blocks.get(bid)
        for b in blocks:
            if b.id == bid:
                return b
        return None

    def viewport_resized(self):
        vp = self.view.viewport()
        self.leader_overlay.resize(vp.size())
        for bub in self._bubbles.values():
            x = max(0, min(bub.x(), vp.width() - 30))
            y = max(0, min(bub.y(), vp.height() - 30))
            if (x, y) != (bub.x(), bub.y()):
                bub.move(x, y)
        self._refresh_leaders()


class _OverlayResizer(QObject):
    def __init__(self, mgr: "HXBubbleManager"):
        super().__init__()
        self._mgr = mgr

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Resize:
            self._mgr.viewport_resized()
        return False
