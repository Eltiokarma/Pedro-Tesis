"""Herramienta de anotación (T) — Design ciclo 3, artboard 3c.

Nota de plano, no un editor de texto rico. MVP del bundle:
  · Crear: click con la T activa → caja en edición directa; si queda
    vacía se descarta al blur. Sin modal.
  · Editar: doble-click re-entra; Enter agrega línea; Esc/blur confirma.
  · Mover: drag (undo por snapshot del editor).
  · Borrar: seleccionada + Supr o menú contextual.
  · Guía opcional: línea recta a un punto fijo de la escena (borrarla
    no borra la nota).
  · Estilo SOLO de la escala del sistema: 3 estilos (micro FONT_LABEL /
    rótulo FONT_UI / título FONT_TITLE, peso 600) × 3 tintas (ink /
    ink_soft / danger para revisión) × fondo transparente o pill
    label_bg al 88 %.
  · Escala con el zoom como texto de plano (sin
    ItemIgnoresTransformations) y z=40 — sobre streams, bajo overlays.
  · El export SIEMPRE las incluye (documentación de ingeniería);
    Vista ▸ «Mostrar anotaciones» oculta solo en pantalla.

Persistencia: dicts en Flowsheet.annotations →
  {"id", "x", "y", "text", "style", "tint", "pill", "guide": [x,y]|None}
El undo/redo llega gratis por los snapshots del editor.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPen
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsLineItem, QGraphicsTextItem, QMenu,
)

import tokens as _tokens

Z_ANNOTATION = 40

STYLES = ("micro", "rotulo", "titulo")
TINTS = ("ink", "ink_soft", "danger")

_STYLE_FONT = {
    "micro":  lambda: _tokens.FONT_LABEL,
    "rotulo": lambda: _tokens.FONT_UI,
    "titulo": lambda: _tokens.FONT_TITLE,
}


def _font_for(style: str) -> QFont:
    fam, size, _w = _STYLE_FONT.get(style, _STYLE_FONT["rotulo"])()
    f = QFont(fam, int(size))
    f.setWeight(QFont.DemiBold)      # 600 — peso único del artboard 3c
    return f


def _tint_hex(tint: str) -> str:
    return _tokens.TOK.get(tint if tint in TINTS else "ink",
                           _tokens.TOK["ink"])


class AnnotationItem(QGraphicsTextItem):
    """Nota de plano sobre el lienzo. `data` es el dict del modelo
    (Flowsheet.annotations) — el item escribe ahí sus cambios."""

    def __init__(self, data: dict, editor=None):
        super().__init__(data.get("text", ""))
        self.data = data
        self.editor = editor
        self._guide_item: Optional[QGraphicsLineItem] = None
        self._was_new = not bool(data.get("text"))
        self.setZValue(Z_ANNOTATION)
        self.setFlags(QGraphicsItem.ItemIsMovable
                      | QGraphicsItem.ItemIsSelectable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.setPos(float(data.get("x", 0)), float(data.get("y", 0)))
        self.apply_style()

    # ── estilo ────────────────────────────────────────────────
    def apply_style(self):
        self.setFont(_font_for(self.data.get("style", "rotulo")))
        self.setDefaultTextColor(QColor(_tint_hex(
            self.data.get("tint", "ink"))))
        self.update()
        self._sync_guide()

    def paint(self, painter, option, widget=None):
        if self.data.get("pill"):
            bg = QColor(_tokens.TOK.get("label_bg", _tokens.TOK["bg_elev"]))
            bg.setAlpha(224)         # 88 % — pill label_bg del artboard
            painter.save()
            painter.setPen(Qt.NoPen)
            painter.setBrush(bg)
            painter.drawRoundedRect(self.boundingRect(), 4, 4)
            painter.restore()
        super().paint(painter, option, widget)

    # ── edición ───────────────────────────────────────────────
    def start_edit(self):
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setFocus(Qt.MouseFocusReason)
        cur = self.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        self.setTextCursor(cur)

    def _commit_edit(self):
        self.setTextInteractionFlags(Qt.NoTextInteraction)
        text = self.toPlainText().strip()
        if not text:
            # Nota vacía → se descarta (regla del MVP: sin modal)
            if self.editor is not None:
                self.editor.remove_annotation(self.data, push_undo=False)
            return
        if text != self.data.get("text"):
            before = (self.editor.begin_action()
                      if self.editor is not None and not self._was_new
                      else None)
            self.data["text"] = text
            if self.editor is not None and before is not None:
                self.editor.end_action("editar anotación", before)
        self._was_new = False

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._commit_edit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.clearFocus()        # → focusOut → commit
            return
        super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.start_edit()
        event.accept()

    # ── movimiento / guía ─────────────────────────────────────
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.data["x"] = float(self.pos().x())
            self.data["y"] = float(self.pos().y())
            self._sync_guide()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        if (event.button() == Qt.LeftButton and self.editor is not None
                and getattr(self.editor, "_drag_before_snapshot", None)
                is None):
            self.editor._drag_before_snapshot = self.editor.begin_action()
        super().mousePressEvent(event)

    def _sync_guide(self):
        guide = self.data.get("guide")
        sc = self.scene()
        if not guide or sc is None:
            if self._guide_item is not None:
                if self._guide_item.scene() is not None:
                    self._guide_item.scene().removeItem(self._guide_item)
                self._guide_item = None
            return
        if self._guide_item is None or self._guide_item.scene() is not sc:
            self._guide_item = QGraphicsLineItem()
            self._guide_item.setZValue(Z_ANNOTATION - 1)
            self._guide_item.setAcceptedMouseButtons(Qt.NoButton)
            sc.addItem(self._guide_item)
        pen = QPen(QColor(_tint_hex(self.data.get("tint", "ink"))), 1.0)
        pen.setStyle(Qt.DashLine)
        pen.setCosmetic(True)
        self._guide_item.setPen(pen)
        br = self.sceneBoundingRect()
        self._guide_item.setLine(br.center().x(), br.center().y(),
                                 float(guide[0]), float(guide[1]))

    def remove_guide_item(self):
        if self._guide_item is not None:
            if self._guide_item.scene() is not None:
                self._guide_item.scene().removeItem(self._guide_item)
            self._guide_item = None

    # ── menú contextual ───────────────────────────────────────
    def contextMenuEvent(self, event):
        if self.editor is None:
            return
        menu = QMenu()
        m_style = menu.addMenu("Estilo")
        for st, lbl in (("micro", "Micro"), ("rotulo", "Rótulo"),
                        ("titulo", "Título")):
            act = m_style.addAction(lbl)
            act.setCheckable(True)
            act.setChecked(self.data.get("style", "rotulo") == st)
            act.setData(("style", st))
        m_tint = menu.addMenu("Tinta")
        for tn, lbl in (("ink", "Tinta"), ("ink_soft", "Suave"),
                        ("danger", "Revisión △")):
            act = m_tint.addAction(lbl)
            act.setCheckable(True)
            act.setChecked(self.data.get("tint", "ink") == tn)
            act.setData(("tint", tn))
        act_pill = menu.addAction("Fondo pill")
        act_pill.setCheckable(True)
        act_pill.setChecked(bool(self.data.get("pill")))
        act_pill.setData(("pill", None))
        menu.addSeparator()
        if self.data.get("guide"):
            act_guide = menu.addAction("Quitar guía")
            act_guide.setData(("guide_off", None))
        else:
            act_guide = menu.addAction("Agregar guía (click al destino)")
            act_guide.setData(("guide_on", None))
        menu.addSeparator()
        act_del = menu.addAction("Borrar nota")
        act_del.setData(("delete", None))

        chosen = menu.exec(event.screenPos())
        if chosen is None:
            return
        kind, val = chosen.data()
        ed = self.editor
        if kind == "delete":
            ed.remove_annotation(self.data)
            return
        before = ed.begin_action()
        if kind == "style":
            self.data["style"] = val
        elif kind == "tint":
            self.data["tint"] = val
        elif kind == "pill":
            self.data["pill"] = not self.data.get("pill")
        elif kind == "guide_off":
            self.data["guide"] = None
        elif kind == "guide_on":
            # El próximo click en el canvas fija el destino de la guía
            ed._annotation_awaiting_guide = self
            ed.end_action("guía de anotación", before)
            return
        ed.end_action("editar anotación", before)
        self.apply_style()
