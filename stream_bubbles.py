"""
STREAM BUBBLES — burbujas flotantes con propiedades de corrientes.

Parche NUEVA_UI_P_SAD_3.  Una burbuja flotante muestra las propiedades
de una corriente (T, P, ṁ, opcionalmente h y composición), conectada
a la corriente por un leader punteado curvado.

Default OFF.  El usuario las activa una por una desde el StreamEditDialog
(sección "Visualización") — un flowsheet con 50+ streams se llenaría de
burbujas si todas estuvieran activas.

Piezas:
  · StreamBubble(QFrame)    — el widget visual de UNA burbuja.
                               Drag por la cabecera, header con grip +
                               name + phase + collapse + close.
  · LeaderOverlay(QWidget)  — capa transparente que pinta las curvas
                               Bézier punteadas entre stream y burbuja.
  · BubbleManager           — orquesta: crea/destruye burbujas según
                               stream.bubble_visible, conecta drag a
                               persistencia en el modelo, actualiza
                               leaders al mover bloques/streams.
  · bubble_attachment(...)  — helper para calcular el punto de
                               aterrizaje del leader en la burbuja.
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import (
    Qt, Signal, QPoint, QPointF, QRectF, QRect, QEvent, QObject, QSize,
)
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QPainterPath, QMouseEvent,
)
from PySide6.QtWidgets import (
    QWidget, QFrame, QHBoxLayout, QVBoxLayout, QGridLayout, QLabel,
    QToolButton, QSizePolicy, QGraphicsView, QCheckBox, QApplication,
)

import pfd_fonts
from block_inspector import TOK


# ════════════════════════════════════════════════════════
#  STREAM BUBBLE — widget de una burbuja
# ════════════════════════════════════════════════════════

class StreamBubble(QFrame):
    """Burbuja flotante con T/P/ṁ (+ opcional h + composición) de un
    stream. Arrastrable por la cabecera.

    Emite señales para que BubbleManager / FlowsheetMainWindow:
      · positionChanged(stream_id, x, y) — al soltar el drag (persistir)
      · positionDragging(stream_id, x, y) — durante el drag (mover leader)
      · closeRequested(stream_id) — click en × (set bubble_visible=False)
      · collapseToggled(stream_id, bool) — click en ▴/▾
    """

    positionChanged   = Signal(int, float, float)
    positionDragging  = Signal(int, float, float)
    closeRequested    = Signal(int)
    collapseToggled   = Signal(int, bool)

    def __init__(self, stream_id: int, parent=None):
        super().__init__(parent)
        self._stream_id = stream_id
        self._collapsed = False
        self._show_composition = False
        self._show_enthalpy = False
        self._drag_offset: Optional[QPoint] = None
        self._is_dragging = False
        # Datos del stream (se refrescan via update_values)
        self._name = ""
        self._phase = ""
        self._T_K = 0.0
        self._P_bar = 0.0
        self._mdot_kg_s = 0.0
        self._h_kJ_kg: Optional[float] = None
        self._composition: List[Tuple[str, float]] = []   # (name, mol_frac)

        self.setObjectName("streamBubble")
        self.setMinimumWidth(156)
        self.setAttribute(Qt.WA_NoSystemBackground, False)
        self._apply_style()

        # Layout: header + body
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._header = self._build_header()
        outer.addWidget(self._header)

        self._body = QFrame(self)
        self._body.setObjectName("bubBody")
        self._body_layout = QGridLayout(self._body)
        self._body_layout.setContentsMargins(8, 6, 8, 8)
        self._body_layout.setHorizontalSpacing(7)
        self._body_layout.setVerticalSpacing(2)
        outer.addWidget(self._body)

        self._refresh_body()

        # Drop shadow
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            sh = QGraphicsDropShadowEffect(self)
            sh.setBlurRadius(18); sh.setOffset(0, 4)
            c = QColor(40, 30, 20); c.setAlphaF(0.18); sh.setColor(c)
            self.setGraphicsEffect(sh)
        except Exception:
            pass

    # ── API pública ─────────────────────────────────────
    def stream_id(self) -> int:
        return self._stream_id

    def update_values(self, name: str, phase: str,
                      T_K: float = 0.0, P_bar: float = 0.0,
                      mdot_kg_s: float = 0.0,
                      h_kJ_kg: Optional[float] = None,
                      composition: Optional[List[Tuple[str, float]]] = None):
        """Refresca los valores numéricos.  Se llama cuando:
          · El stream se editó manualmente
          · El solver terminó y publicó nuevos valores"""
        self._name = name or "?"
        self._phase = (phase or "").lower()
        self._T_K = float(T_K or 0.0)
        self._P_bar = float(P_bar or 0.0)
        self._mdot_kg_s = float(mdot_kg_s or 0.0)
        self._h_kJ_kg = h_kJ_kg
        self._composition = composition or []
        self._name_lbl.setText(self._name)
        # phase chip
        phase_short = {"liquid": "liq", "vapor": "vap", "gas": "gas",
                       "two_phase": "2ph", "solid": "sol"}.get(
                           self._phase, self._phase[:3] if self._phase else "")
        self._phase_lbl.setText(phase_short.upper())
        self._phase_lbl.setVisible(bool(phase_short))
        self._refresh_body()

    def set_collapsed(self, collapsed: bool):
        if collapsed == self._collapsed:
            return
        self._collapsed = bool(collapsed)
        self._collapse_btn.setText("▾" if self._collapsed else "▴")
        self._refresh_body()

    def set_show_composition(self, on: bool):
        self._show_composition = bool(on)
        self._refresh_body()

    def set_show_enthalpy(self, on: bool):
        self._show_enthalpy = bool(on)
        self._refresh_body()

    def is_dragging(self) -> bool:
        return self._is_dragging

    def attachment_point(self, leader_from: QPoint) -> QPoint:
        """Punto de la burbuja donde aterriza el leader: el lado más
        cercano al ancla del stream."""
        x, y = self.x(), self.y()
        w, h = self.width(), self.height()
        cx, cy = x + w/2, y + h/2
        dx, dy = leader_from.x() - cx, leader_from.y() - cy
        if abs(dx) > abs(dy):
            return QPoint(int(x + w if dx > 0 else x), int(cy))
        return QPoint(int(cx), int(y + h if dy > 0 else y))

    # ── Construcción interna ────────────────────────────
    def _apply_style(self):
        bg = TOK["bg_elev"]; border = TOK["line"]
        self.setStyleSheet(
            f"#streamBubble {{ background:{bg}; "
            f"border:1px solid {border}; border-radius:10px; }} "
            f"#bubHeader {{ background:transparent; "
            f"border-bottom:1px solid {border}; }} "
            f"#bubBody {{ background:transparent; }}"
        )

    def _build_header(self) -> QFrame:
        hd = QFrame(self); hd.setObjectName("bubHeader")
        hd.setFixedHeight(32)
        hd.setCursor(Qt.OpenHandCursor)
        lay = QHBoxLayout(hd)
        lay.setContentsMargins(7, 6, 6, 6); lay.setSpacing(6)

        # Grip (6 dots in 2x3)
        grip = QLabel("⋮⋮", hd)
        grip.setFixedSize(8, 14)
        grip.setAlignment(Qt.AlignCenter)
        grip.setStyleSheet(
            f"color:{TOK['ink_mute']}; font-size:10px; "
            f"letter-spacing:-2px;"
        )
        lay.addWidget(grip)

        # Stream name (IBM Plex Mono)
        self._name_lbl = QLabel("?", hd)
        nf = QFont(pfd_fonts.MONO, 9, QFont.DemiBold)
        self._name_lbl.setFont(nf)
        self._name_lbl.setStyleSheet(f"color:{TOK['ink']};")
        self._name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._name_lbl.setMinimumWidth(60)
        lay.addWidget(self._name_lbl, 1)

        # Phase chip
        self._phase_lbl = QLabel("", hd)
        pf = QFont(pfd_fonts.SANS, 7, QFont.Bold)
        self._phase_lbl.setFont(pf)
        self._phase_lbl.setAlignment(Qt.AlignCenter)
        self._phase_lbl.setStyleSheet(
            f"background:{TOK['bg_mute']}; color:{TOK['ink_soft']}; "
            f"padding:1px 5px; border-radius:3px; "
            f"letter-spacing:1px;"
        )
        lay.addWidget(self._phase_lbl)

        # Collapse
        self._collapse_btn = QToolButton(hd)
        self._collapse_btn.setText("▴")
        self._collapse_btn.setFixedSize(18, 18)
        self._collapse_btn.setCursor(Qt.PointingHandCursor)
        self._collapse_btn.setStyleSheet(self._icbtn_style())
        self._collapse_btn.clicked.connect(self._on_collapse_click)
        lay.addWidget(self._collapse_btn)

        # More (•••) — sub-toggles
        self._more_btn = QToolButton(hd)
        self._more_btn.setText("⋯")
        self._more_btn.setFixedSize(18, 18)
        self._more_btn.setCursor(Qt.PointingHandCursor)
        self._more_btn.setToolTip("Más opciones")
        self._more_btn.setStyleSheet(self._icbtn_style())
        self._more_btn.clicked.connect(self._on_more_click)
        lay.addWidget(self._more_btn)

        # Close
        self._close_btn = QToolButton(hd)
        self._close_btn.setText("✕")
        self._close_btn.setFixedSize(18, 18)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.setStyleSheet(self._icbtn_style())
        self._close_btn.clicked.connect(
            lambda: self.closeRequested.emit(self._stream_id))
        lay.addWidget(self._close_btn)
        return hd

    def _icbtn_style(self) -> str:
        return (
            f"QToolButton {{ background:transparent; color:{TOK['ink_soft']}; "
            f"border:0; border-radius:4px; font-size:10px; }} "
            f"QToolButton:hover {{ background:{TOK['bg_mute']}; "
            f"color:{TOK['ink']}; }}"
        )

    def _on_collapse_click(self):
        self.set_collapsed(not self._collapsed)
        self.collapseToggled.emit(self._stream_id, self._collapsed)

    def _on_more_click(self):
        """Popup con sub-toggles: mostrar entalpía, mostrar composición."""
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{TOK['bg_elev']}; color:{TOK['ink']}; "
            f"border:1px solid {TOK['line']}; padding:4px 0; "
            f"font-family:'{pfd_fonts.SANS}'; font-size:9pt; }} "
            f"QMenu::item {{ padding:5px 22px 5px 14px; }} "
            f"QMenu::item:selected {{ background:{TOK['accent_tint']}; "
            f"color:{TOK['accent_deep']}; }}"
        )
        # Mostrar entalpía
        a_h = menu.addAction("Mostrar entalpía")
        a_h.setCheckable(True); a_h.setChecked(self._show_enthalpy)
        # Mostrar composición
        a_c = menu.addAction("Mostrar composición")
        a_c.setCheckable(True); a_c.setChecked(self._show_composition)
        chosen = menu.exec(self._more_btn.mapToGlobal(
            self._more_btn.rect().bottomLeft()))
        if chosen is a_h:
            self.set_show_enthalpy(not self._show_enthalpy)
        elif chosen is a_c:
            self.set_show_composition(not self._show_composition)

    def _refresh_body(self):
        # Limpiar layout
        lay = self._body_layout
        while lay.count():
            it = lay.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None); w.deleteLater()

        if self._collapsed:
            # T + ṁ inline
            T_txt = f"{self._T_K:.0f}" if self._T_K else "—"
            m_txt = f"{self._mdot_kg_s:.2f}" if self._mdot_kg_s else "—"
            inline = QLabel(self._body)
            inline.setTextFormat(Qt.RichText)
            soft = TOK["ink_soft"]; ink = TOK["ink"]; mono = pfd_fonts.MONO
            inline.setText(
                f'<span style="color:{soft};font-size:9px;">T</span> '
                f'<span style="color:{ink};font-size:10pt;font-family:\'{mono}\';">{T_txt}</span>'
                f'<span style="color:{soft};font-size:9px;"> K</span>'
                f'<span style="color:{soft};">  ·  </span>'
                f'<span style="color:{soft};font-size:9px;">ṁ</span> '
                f'<span style="color:{ink};font-size:10pt;font-family:\'{mono}\';">{m_txt}</span>'
            )
            lay.addWidget(inline, 0, 0, 1, 3)
            return

        # Estándar: T, P, ṁ
        row = 0
        for label, value, unit in self._iter_rows():
            self._add_row(lay, row, label, value, unit)
            row += 1

        # Entalpía opcional
        if self._show_enthalpy and self._h_kJ_kg is not None:
            self._add_row(lay, row, "h", f"{self._h_kJ_kg:.0f}", "kJ/kg")
            row += 1

        # Composición (sub-grupo)
        if self._show_composition and self._composition:
            sep = QFrame(self._body); sep.setFixedHeight(1)
            sep.setStyleSheet(
                f"background:transparent; border-top:1px dashed {TOK['line']};"
            )
            lay.addWidget(sep, row, 0, 1, 3)
            row += 1
            title = QLabel("COMPOSICIÓN (mol)", self._body)
            title.setFont(QFont(pfd_fonts.SANS, 7, QFont.Bold))
            title.setStyleSheet(
                f"color:{TOK['ink_soft']}; letter-spacing:1px;"
            )
            lay.addWidget(title, row, 0, 1, 3)
            row += 1
            # Top 4 species, agrupar el resto
            top = self._composition[:4]
            for name, frac in top:
                self._add_comp_row(lay, row, name, frac)
                row += 1

    def _iter_rows(self):
        T_txt = f"{self._T_K:.1f}" if self._T_K else "—"
        P_txt = f"{self._P_bar:.2f}" if self._P_bar else "—"
        m_txt = f"{self._mdot_kg_s:.2f}" if self._mdot_kg_s else "—"
        yield ("T",  T_txt, "K")
        yield ("P",  P_txt, "bar")
        yield ("ṁ",  m_txt, "kg/s")

    def _add_row(self, lay, row, label, value, unit):
        k = QLabel(label, self._body)
        k.setFont(QFont(pfd_fonts.SANS, 8, QFont.Medium))
        k.setStyleSheet(f"color:{TOK['ink_soft']};")
        k.setFixedWidth(18)
        lay.addWidget(k, row, 0)
        v = QLabel(value, self._body)
        v.setFont(QFont(pfd_fonts.MONO, 9, QFont.Medium))
        v.setStyleSheet(f"color:{TOK['ink']};")
        v.setAlignment(Qt.AlignRight | Qt.AlignBaseline)
        # Italic gris si valor vacío
        if value == "—":
            v.setStyleSheet(f"color:{TOK['ink_ghost']}; font-style:italic;")
        lay.addWidget(v, row, 1)
        u = QLabel(unit, self._body)
        u.setFont(QFont(pfd_fonts.MONO, 8))
        u.setStyleSheet(f"color:{TOK['ink_soft']};")
        lay.addWidget(u, row, 2)

    def _add_comp_row(self, lay, row, name, frac):
        nm = QLabel(name, self._body)
        nm.setFont(QFont(pfd_fonts.MONO, 8, QFont.Medium))
        nm.setStyleSheet(f"color:{TOK['ink']};")
        nm.setFixedWidth(56)
        lay.addWidget(nm, row, 0)
        # Bar
        bar = QFrame(self._body); bar.setFixedHeight(4)
        bar.setStyleSheet(
            f"background:{TOK['bg_mute']}; border-radius:2px;"
        )
        bar_lay = QHBoxLayout(bar); bar_lay.setContentsMargins(0,0,0,0)
        bar_lay.setSpacing(0)
        fill = QFrame(bar); fill.setFixedHeight(4)
        fill.setStyleSheet(
            f"background:{TOK['accent']}; border-radius:2px;"
        )
        # Set width proportional via stretch
        pct = max(0.0, min(1.0, float(frac)))
        bar_lay.addWidget(fill, int(pct * 100))
        sp = QFrame(bar); sp.setFixedHeight(4); sp.setStyleSheet("background:transparent;")
        bar_lay.addWidget(sp, int((1 - pct) * 100))
        lay.addWidget(bar, row, 1)
        val = QLabel(f"{pct*100:.1f}%", self._body)
        val.setFont(QFont(pfd_fonts.MONO, 8))
        val.setStyleSheet(f"color:{TOK['ink']};")
        val.setAlignment(Qt.AlignRight)
        val.setFixedWidth(40)
        lay.addWidget(val, row, 2)

    # ── Drag handler ────────────────────────────────────
    def mousePressEvent(self, ev: QMouseEvent):
        if ev.button() == Qt.LeftButton:
            # solo el header inicia el drag
            child = self.childAt(ev.position().toPoint())
            if child is None:
                return super().mousePressEvent(ev)
            # Es del header si su parent (o él mismo) es self._header
            w = child
            while w is not None and w is not self:
                if w is self._header:
                    self._drag_offset = (
                        ev.globalPosition().toPoint() - self.pos()
                    )
                    self._is_dragging = True
                    self._header.setCursor(Qt.ClosedHandCursor)
                    self._apply_style_dragging(True)
                    ev.accept()
                    return
                w = w.parent()
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev: QMouseEvent):
        if self._is_dragging and (ev.buttons() & Qt.LeftButton):
            new_pos = ev.globalPosition().toPoint() - self._drag_offset
            parent = self.parentWidget()
            if parent is not None:
                pr = parent.rect()
                pw, ph = self.width(), self.height()
                x = max(0, min(new_pos.x(), pr.width()  - 30))
                y = max(0, min(new_pos.y(), pr.height() - 30))
                new_pos = QPoint(x, y)
            self.move(new_pos)
            self.positionDragging.emit(
                self._stream_id, float(new_pos.x()), float(new_pos.y())
            )
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev: QMouseEvent):
        if self._is_dragging:
            self._is_dragging = False
            self._header.setCursor(Qt.OpenHandCursor)
            self._apply_style_dragging(False)
            self.positionChanged.emit(
                self._stream_id,
                float(self.x()), float(self.y())
            )
            ev.accept()
            return
        super().mouseReleaseEvent(ev)

    def _apply_style_dragging(self, on: bool):
        if on:
            self.setStyleSheet(
                f"#streamBubble {{ background:{TOK['bg_elev']}; "
                f"border:1.5px solid {TOK['accent_soft']}; "
                f"border-radius:10px; }} "
                f"#bubHeader {{ border-bottom:1px solid {TOK['line']}; }}"
            )
        else:
            self._apply_style()


# ════════════════════════════════════════════════════════
#  LEADER OVERLAY — curvas Bézier punteadas
# ════════════════════════════════════════════════════════

class LeaderOverlay(QWidget):
    """Capa transparente que pinta los leaders entre cada burbuja
    activa y el ancla de su stream.

    Padre: viewport del QGraphicsView.  z-order: detrás de las burbujas
    (que están en otro overlay) pero encima del scene.

    El BubbleManager llama a `set_links(list[(from_pt, to_pt, state)])`
    cuando cambian las posiciones de bloques/streams/burbujas, y el
    overlay re-pinta.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._links: List[Tuple[QPoint, QPoint, str]] = []

    def set_links(self, links: List[Tuple[QPoint, QPoint, str]]):
        """links = [(from_pt, to_pt, state), …]  state ∈ {'idle', 'dragging'}."""
        self._links = list(links)
        self.update()

    def paintEvent(self, ev):
        if not self._links:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        for src, dst, state in self._links:
            self._paint_one(p, src, dst, state)

    def _paint_one(self, p: QPainter, src: QPoint, dst: QPoint, state: str):
        # Anchor dot (en el stream)
        accent = QColor(TOK["accent"])
        bg     = QColor(TOK["bg_elev"])
        p.setBrush(QBrush(bg))
        p.setPen(QPen(accent, 1.5))
        p.drawEllipse(QPointF(src), 4.0, 4.0)
        # Curve Bézier cuadrática suave
        dx = dst.x() - src.x(); dy = dst.y() - src.y()
        import math
        length = math.hypot(dx, dy)
        if length < 1e-6:
            return
        mid_x = (src.x() + dst.x()) / 2.0
        mid_y = (src.y() + dst.y()) / 2.0
        # Perpendicular
        perp_x = -dy / length
        perp_y =  dx / length
        bend = min(20.0, length * 0.15)
        ctrl = QPointF(mid_x + perp_x * bend, mid_y + perp_y * bend)
        path = QPainterPath()
        path.moveTo(QPointF(src))
        path.quadTo(ctrl, QPointF(dst))
        if state == "dragging":
            pen = QPen(accent, 1.4)
            pen.setStyle(Qt.SolidLine)
            pen.setCapStyle(Qt.RoundCap)
            p.setOpacity(0.95)
        else:
            soft = QColor(TOK["ink_soft"])
            pen = QPen(soft, 1.2)
            pen.setStyle(Qt.CustomDashLine)
            pen.setDashPattern([1.5, 4])
            pen.setCapStyle(Qt.RoundCap)
            p.setOpacity(0.8)
        p.setPen(pen); p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.setOpacity(1.0)


# ════════════════════════════════════════════════════════
#  BUBBLE MANAGER
# ════════════════════════════════════════════════════════

class BubbleManager:
    """Orquesta la vida de las burbujas: crea/destruye según
    stream.bubble_visible, conecta drag a persistencia en el modelo,
    actualiza leaders cuando se mueven bloques/streams/burbujas.

    NO es un QWidget en sí — usa el viewport del view como parent de
    las burbujas + el LeaderOverlay.  Se instancia una vez en
    FlowsheetMainWindow.
    """

    def __init__(self, view: QGraphicsView, get_fs: Callable,
                 get_stream_items_iter: Callable):
        """
        view: el QGraphicsView del editor.
        get_fs: callable que devuelve la Flowsheet ACTUAL.  Se llama
                cada vez que el manager necesita iterar streams — así
                resiste a swaps de fs por action_new/open/undo.
        get_stream_items_iter: callable que devuelve un iterador de
            (stream_id, StreamItem) — usado para encontrar el midpoint
            del path del stream en coordenadas de scene.
        """
        self.view = view
        self._get_fs = get_fs
        self.get_stream_items_iter = get_stream_items_iter
        self._bubbles: Dict[int, StreamBubble] = {}

        vp = view.viewport()
        # LeaderOverlay primero (z-order más bajo).  NO mostrar ya:
        # al construirse durante __init__ la ventana todavía no tiene
        # surface válida y el primer paintEvent fallaría con
        # "QPainter::begin: Paint device returned engine == 0".
        # En su lugar, diferir el resize+show con QTimer.
        self.leader_overlay = LeaderOverlay(vp)
        sz = vp.size()
        if not sz.isValid() or sz.width() < 1 or sz.height() < 1:
            sz = QSize(800, 600)
        self.leader_overlay.resize(sz)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._deferred_init)

    def _deferred_init(self):
        """Llamado después del primer event loop tick: el viewport ya
        tiene tamaño real."""
        vp = self.view.viewport()
        try:
            self.leader_overlay.resize(vp.size())
            self.leader_overlay.show()
        except Exception:
            pass

        # Hook resize del viewport.  Conservar la ref para que el GC no
        # recoja el filter.
        self._resizer = _OverlayResizer(self)
        vp.installEventFilter(self._resizer)

        # Hook scroll / zoom del view para que los leaders sigan al
        # mapeo scene→viewport.  Los scrollbars se mueven en pan o
        # cuando un wheelEvent dispara zoom anclado al cursor.
        try:
            view.horizontalScrollBar().valueChanged.connect(self._refresh_leaders)
            view.verticalScrollBar().valueChanged.connect(self._refresh_leaders)
        except Exception:
            pass

    # ── API pública ─────────────────────────────────────
    @property
    def fs(self):
        """Lee la Flowsheet actual via callback — resiste swaps."""
        try:
            return self._get_fs()
        except Exception:
            return None

    def refresh_all(self):
        """Sincroniza burbujas visibles con stream.bubble_visible para
        cada stream del fs.  Crea/destruye según haga falta y refresca
        valores."""
        fs = self.fs
        if fs is None:
            return
        streams = fs.streams
        if isinstance(streams, dict):
            ids = set(streams.keys())
            streams_by_id = streams
        else:
            ids = {s.id for s in streams}
            streams_by_id = {s.id: s for s in streams}

        # Cerrar burbujas de streams que ya no existen o que se desactivaron
        for sid in list(self._bubbles.keys()):
            if sid not in ids or not getattr(streams_by_id[sid], "bubble_visible", False):
                self._destroy_bubble(sid)

        # Crear/refrescar burbujas para streams con bubble_visible=True
        for sid, s in streams_by_id.items():
            if getattr(s, "bubble_visible", False):
                if sid not in self._bubbles:
                    self._create_bubble(s)
                self._refresh_bubble_values(s)

        self._refresh_leaders()

    def _create_bubble(self, stream):
        vp = self.view.viewport()
        bub = StreamBubble(stream.id, parent=vp)
        bub.positionDragging.connect(self._on_dragging)
        bub.positionChanged.connect(self._on_drag_finished)
        bub.closeRequested.connect(self._on_close)
        bub.collapseToggled.connect(self._on_collapse)
        # Estado inicial: collapsed / show_*
        bub.set_collapsed(bool(getattr(stream, "bubble_collapsed", False)))
        bub.set_show_composition(bool(getattr(stream, "bubble_show_composition", False)))
        bub.set_show_enthalpy(bool(getattr(stream, "bubble_show_enthalpy", False)))
        # Posición: si stream.bubble_position vacío, usar offset del
        # midpoint del stream.  Si el midpoint tampoco es computable,
        # poner la burbuja cerca del centro del viewport (NO en 40,40
        # porque ahí está la paleta y queda tapada).
        bp = getattr(stream, "bubble_position", []) or []
        if len(bp) == 2:
            x, y = int(bp[0]), int(bp[1])
        else:
            mp = self._stream_midpoint_viewport(stream.id)
            if mp is not None:
                n_visible = len(self._bubbles)
                x = int(mp.x() + 80)
                y = int(mp.y() + 60 + n_visible * 20)
            else:
                # Fallback visible: centro-izquierda del viewport, lejos
                # de la paleta (que está en 14,14, ancho 50).
                n = len(self._bubbles)
                x = 150 + n * 24
                y = 120 + n * 24
        # Clamp al rect del viewport por si la posición persistida
        # quedó fuera tras un resize.
        vw, vh = vp.width(), vp.height()
        # adjustSize antes de mover para obtener width/height real
        bub.adjustSize()
        bw, bh = bub.sizeHint().width(), bub.sizeHint().height()
        x = max(0, min(x, max(0, vw - 30)))
        y = max(0, min(y, max(0, vh - 30)))
        bub.move(x, y)
        bub.show()
        bub.raise_()   # encima del leader_overlay y del chrome
        self._bubbles[stream.id] = bub

    def _destroy_bubble(self, sid: int):
        bub = self._bubbles.pop(sid, None)
        if bub is not None:
            bub.setParent(None)
            bub.deleteLater()

    def _refresh_bubble_values(self, stream):
        bub = self._bubbles.get(stream.id)
        if bub is None:
            return
        # Convertir del modelo a unidades de display (T en K, mdot en kg/s)
        T_C = float(getattr(stream, "temperature", 0.0) or 0.0)
        T_K = T_C + 273.15
        P_bar = float(getattr(stream, "pressure_bar", 0.0) or 0.0)
        tm_yr = float(getattr(stream, "mass_flow", 0.0) or 0.0)
        mdot = (tm_yr * 1000.0) / (8760.0 * 3600.0) if tm_yr > 0 else 0.0
        phase = getattr(stream, "phase", "") or ""
        # Composition: lista (name, mass_frac) — el README dice mol_frac
        # pero como aproximación V1 mostramos mass_frac sin conversión
        # (TODO: agregar conversión mass→mol via thermo_db si hay specs).
        comp = []
        try:
            d = getattr(stream, "composition", {}) or {}
            if isinstance(d, dict):
                # ordenar de mayor a menor
                items = sorted(d.items(), key=lambda kv: -kv[1])
                comp = [(k, float(v)) for k, v in items if v]
        except Exception:
            comp = []
        bub.update_values(
            name=getattr(stream, "name", "?"),
            phase=phase,
            T_K=T_K, P_bar=P_bar, mdot_kg_s=mdot,
            h_kJ_kg=None,    # TODO: cablear si hay h_total
            composition=comp,
        )

    def _refresh_leaders(self):
        """Reconstruye la lista de leaders y la entrega al overlay."""
        if not self._bubbles:
            self.leader_overlay.set_links([])
            return
        links: List[Tuple[QPoint, QPoint, str]] = []
        for sid, bub in self._bubbles.items():
            mp = self._stream_midpoint_viewport(sid)
            if mp is None:
                continue
            state = "dragging" if bub.is_dragging() else "idle"
            attach = bub.attachment_point(mp)
            links.append((mp, attach, state))
        self.leader_overlay.set_links(links)
        # Asegurar z-order: leader_overlay debajo de las burbujas
        self.leader_overlay.raise_()
        for bub in self._bubbles.values():
            bub.raise_()

    def _stream_midpoint_viewport(self, sid: int) -> Optional[QPoint]:
        """Devuelve el midpoint del path del stream en coordenadas del
        viewport (donde viven las burbujas).  None si el stream item
        no existe en la scene actual."""
        try:
            for s_id, item in self.get_stream_items_iter():
                if s_id != sid:
                    continue
                # StreamItem tiene path() (QPainterPath) o pts/polyline
                pts = None
                if hasattr(item, "polyline_points"):
                    pts = item.polyline_points()
                elif hasattr(item, "path"):
                    try:
                        path = item.path()
                        n = path.elementCount()
                        if n >= 2:
                            pts = [(path.elementAt(i).x, path.elementAt(i).y)
                                    for i in range(n)]
                    except Exception:
                        pts = None
                if not pts:
                    # Fallback: usar boundingRect center
                    br = item.sceneBoundingRect()
                    scene_p = QPointF(br.center())
                else:
                    # midpoint del segmento más largo
                    import math
                    max_len = -1; best = (pts[0], pts[-1])
                    for i in range(1, len(pts)):
                        a = pts[i-1]; b = pts[i]
                        l = math.hypot(b[0]-a[0], b[1]-a[1])
                        if l > max_len:
                            max_len = l; best = (a, b)
                    a, b = best
                    scene_p = QPointF((a[0]+b[0])/2, (a[1]+b[1])/2)
                # scene → view → viewport (mismo sistema de coords)
                view_p = self.view.mapFromScene(scene_p)
                return QPoint(view_p.x(), view_p.y())
        except Exception:
            return None
        return None

    # ── Drag callbacks ──────────────────────────────────
    def _on_dragging(self, sid: int, x: float, y: float):
        self._refresh_leaders()

    def _on_drag_finished(self, sid: int, x: float, y: float):
        # Persistir en el modelo
        s = self._get_stream(sid)
        if s is not None:
            s.bubble_position = [float(x), float(y)]
        self._refresh_leaders()

    def _on_close(self, sid: int):
        s = self._get_stream(sid)
        if s is not None:
            s.bubble_visible = False
        self._destroy_bubble(sid)
        self._refresh_leaders()

    def _on_collapse(self, sid: int, collapsed: bool):
        s = self._get_stream(sid)
        if s is not None:
            s.bubble_collapsed = bool(collapsed)
        self._refresh_leaders()

    def _get_stream(self, sid: int):
        fs = self.fs
        if fs is None:
            return None
        streams = fs.streams
        if isinstance(streams, dict):
            return streams.get(sid)
        for s in streams:
            if s.id == sid:
                return s
        return None

    def viewport_resized(self):
        """Hook llamado por _OverlayResizer cuando el viewport cambia."""
        vp = self.view.viewport()
        self.leader_overlay.resize(vp.size())
        # clamp burbujas dentro del nuevo viewport
        for bub in self._bubbles.values():
            x = max(0, min(bub.x(), vp.width()  - 30))
            y = max(0, min(bub.y(), vp.height() - 30))
            if (x, y) != (bub.x(), bub.y()):
                bub.move(x, y)
        self._refresh_leaders()


class _OverlayResizer(QObject):
    """Event filter (QObject) que llama BubbleManager.viewport_resized
    cuando el viewport cambia de tamaño.  NO escucha Paint events —
    eso provocaba un loop de QPainter::begin failures porque
    set_links(...) llama self.update() y Qt no permite repaint de un
    child durante el paint del parent."""

    def __init__(self, mgr: "BubbleManager"):
        super().__init__()
        self._mgr = mgr

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Resize:
            self._mgr.viewport_resized()
        return False
