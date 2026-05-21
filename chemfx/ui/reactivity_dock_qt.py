"""Dock Qt para visualizar warnings + sugerencias del predictor.

UI de Fase 8 — Capa 4b §5 de la arquitectura.

Aparece como dock derecho con 2 tabs:
  - Warnings: lista de DangerWarning ordenadas por severidad
  - Suggestions: lista de Suggestion del asistente proactivo

Click en un item → navega al bloque correspondiente en el canvas.

Filosofia: si `chemfx` no esta disponible, el dock simplemente no se
crea (no rompe el resto de la UI). Si esta disponible pero el predictor
no corrio, los tabs estan vacios.
"""
from __future__ import annotations

from typing import Optional

try:
    from PySide6.QtWidgets import (
        QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
        QTabWidget, QTableWidget, QTableWidgetItem, QPushButton,
        QLabel, QHeaderView, QAbstractItemView,
    )
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtGui import QColor, QBrush
    PYSIDE_AVAILABLE = True
except ImportError:
    PYSIDE_AVAILABLE = False


# Esquema de colores por severidad (matching los bocetos)
_SEVERITY_COLOR = {
    "critical": "#c41e3a",   # rojo
    "high":     "#e57c00",   # naranja
    "medium":   "#f4b400",   # amarillo
    "low":      "#9ca3af",   # gris
}

_SEVERITY_ICON = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "⚪",
}


class ReactivityDock(QDockWidget):
    """Dock derecho con tabs de warnings + sugerencias del predictor.

    Args:
        parent: FlowsheetMainWindow.
        editor: reference back to main window (para navegar al bloque
                via editor.scene.block_items[bid].setSelected(True) y
                editor.view.centerOn(item)).

    Signals: ninguna — usa callbacks del parent directamente.
    """

    def __init__(self, parent=None, editor=None):
        super().__init__(" Reactividad (predictor) ", parent)
        self._editor = editor
        self.setAllowedAreas(Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea
                              | Qt.LeftDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetClosable
        )

        # ─── Container with tabs ───
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)

        # Status label
        self._status_label = QLabel("(corré Solve para activar el predictor)")
        self._status_label.setStyleSheet("color: #6b7280; font-size: 8.5pt;")
        layout.addWidget(self._status_label)

        # Tabs
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # ─── Tab Warnings ───
        self._warnings_widget = QWidget()
        wlayout = QVBoxLayout(self._warnings_widget)
        wlayout.setContentsMargins(0, 0, 0, 0)
        self._warnings_table = QTableWidget(0, 4)
        self._warnings_table.setHorizontalHeaderLabels(
            ["Sev", "Bloque", "Categoría", "Mensaje"])
        self._warnings_table.verticalHeader().setVisible(False)
        self._warnings_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._warnings_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._warnings_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.Stretch)
        self._warnings_table.setColumnWidth(0, 50)
        self._warnings_table.setColumnWidth(1, 100)
        self._warnings_table.setColumnWidth(2, 100)
        self._warnings_table.itemDoubleClicked.connect(self._on_warning_clicked)
        wlayout.addWidget(self._warnings_table)
        # Boton "Ir al bloque"
        wbtns = QHBoxLayout()
        self._btn_go_to_block = QPushButton("Ir al bloque")
        self._btn_go_to_block.clicked.connect(self._on_warning_go_to_block)
        wbtns.addWidget(self._btn_go_to_block)
        wbtns.addStretch()
        wlayout.addLayout(wbtns)
        self._tabs.addTab(self._warnings_widget, "⚠ Warnings (0)")

        # ─── Tab Suggestions ───
        self._sugs_widget = QWidget()
        slayout = QVBoxLayout(self._sugs_widget)
        slayout.setContentsMargins(0, 0, 0, 0)
        self._sugs_table = QTableWidget(0, 3)
        self._sugs_table.setHorizontalHeaderLabels(
            ["Bloque", "Acción sugerida", "Razón"])
        self._sugs_table.verticalHeader().setVisible(False)
        self._sugs_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._sugs_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._sugs_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch)
        self._sugs_table.setColumnWidth(0, 100)
        self._sugs_table.setColumnWidth(1, 150)
        self._sugs_table.itemDoubleClicked.connect(self._on_suggestion_clicked)
        slayout.addWidget(self._sugs_table)
        # Botones
        sbtns = QHBoxLayout()
        self._btn_apply_sug = QPushButton("Activar reacciones")
        self._btn_apply_sug.clicked.connect(self._on_suggestion_apply)
        self._btn_apply_sug.setToolTip(
            "Activa allow_reactions en el bloque de la sugerencia "
            "seleccionada y agrega las reacciones sugeridas a "
            "active_reactions.")
        self._btn_ignore_sug = QPushButton("Ignorar")
        self._btn_ignore_sug.clicked.connect(self._on_suggestion_ignore)
        sbtns.addWidget(self._btn_apply_sug)
        sbtns.addWidget(self._btn_ignore_sug)
        sbtns.addStretch()
        slayout.addLayout(sbtns)
        self._tabs.addTab(self._sugs_widget, "💡 Sugerencias (0)")

        self.setWidget(widget)

    # ======================================================
    # REFRESH PUBLIC API
    # ======================================================
    def refresh_from_flowsheet(self, fs) -> None:
        """Lee fs.blocks[*].reaction_warnings y fs.blocks[*].feed_analysis_cache
        y rellena las tablas. Llamar despues de chemfx.analyze_flowsheet(fs)."""
        try:
            import chemfx
        except ImportError:
            self._status_label.setText(
                "chemfx no disponible — predictor deshabilitado")
            return

        # Recolectar warnings de todos los bloques
        all_warnings = []
        for bid, block in fs.blocks.items():
            for w in getattr(block, "reaction_warnings", []) or []:
                if not isinstance(w, dict):
                    continue
                entry = dict(w)
                entry["_block_id"] = bid
                entry["_block_name"] = getattr(block, "name", "")
                all_warnings.append(entry)
        # Ordenar por severidad
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        all_warnings.sort(key=lambda w: severity_order.get(
            w.get("severity", "medium"), 4))

        # Recolectar sugerencias del feed_analysis_cache
        all_sugs = []
        for bid, block in fs.blocks.items():
            fa = getattr(block, "feed_analysis_cache", None) or {}
            for s in fa.get("suggestions", []) or []:
                if not isinstance(s, dict):
                    continue
                entry = dict(s)
                entry["_block_id"] = bid
                entry["_block_name"] = getattr(block, "name", "")
                all_sugs.append(entry)

        # Renderizar warnings
        self._populate_warnings(all_warnings)
        self._populate_suggestions(all_sugs)

        # Status
        n_w = len(all_warnings)
        n_s = len(all_sugs)
        n_critical = sum(1 for w in all_warnings if w.get("severity") == "critical")
        if n_w == 0 and n_s == 0:
            self._status_label.setText(
                "Predictor: 0 warnings, 0 sugerencias (todo OK)")
        else:
            self._status_label.setText(
                f"Predictor: {n_w} warning(s) ({n_critical} crítico) · "
                f"{n_s} sugerencia(s)"
            )
        self._tabs.setTabText(0, f"⚠ Warnings ({n_w})")
        self._tabs.setTabText(1, f"💡 Sugerencias ({n_s})")

    def _populate_warnings(self, warns: list) -> None:
        self._warnings_table.setRowCount(len(warns))
        for r, w in enumerate(warns):
            sev = w.get("severity", "medium")
            icon = _SEVERITY_ICON.get(sev, "•")
            color_hex = _SEVERITY_COLOR.get(sev, "#9ca3af")

            it0 = QTableWidgetItem(icon)
            it0.setData(Qt.UserRole, w)
            it0.setForeground(QBrush(QColor(color_hex)))
            self._warnings_table.setItem(r, 0, it0)

            it1 = QTableWidgetItem(w.get("_block_name", ""))
            self._warnings_table.setItem(r, 1, it1)

            it2 = QTableWidgetItem(w.get("risk_category", ""))
            self._warnings_table.setItem(r, 2, it2)

            msg = w.get("message", "")
            it3 = QTableWidgetItem(msg)
            it3.setToolTip(msg)
            self._warnings_table.setItem(r, 3, it3)

    def _populate_suggestions(self, sugs: list) -> None:
        self._sugs_table.setRowCount(len(sugs))
        for r, s in enumerate(sugs):
            it0 = QTableWidgetItem(s.get("_block_name", ""))
            it0.setData(Qt.UserRole, s)
            self._sugs_table.setItem(r, 0, it0)

            action = s.get("suggested_action", "")
            human = "Activar reacciones" if action == "enable_allow_reactions" else action
            it1 = QTableWidgetItem(human)
            self._sugs_table.setItem(r, 1, it1)

            reason = s.get("reasoning", "")
            it2 = QTableWidgetItem(reason)
            it2.setToolTip(reason)
            self._sugs_table.setItem(r, 2, it2)

    # ======================================================
    # ACCIONES
    # ======================================================
    def _navigate_to_block(self, block_id: int) -> None:
        """Selecciona el bloque y centra el canvas en él."""
        if self._editor is None:
            return
        scene = getattr(self._editor, "scene", None)
        view = getattr(self._editor, "view", None)
        if scene is None or view is None:
            return
        item = scene.block_items.get(block_id)
        if item is None:
            return
        try:
            # Deseleccionar todo, seleccionar solo este
            scene.clearSelection()
            item.setSelected(True)
            view.centerOn(item)
        except Exception:
            pass

    def _on_warning_clicked(self, item: QTableWidgetItem) -> None:
        """Doble-click en una fila de warnings → ir al bloque."""
        w = self._warnings_table.item(item.row(), 0).data(Qt.UserRole)
        if w:
            self._navigate_to_block(w.get("_block_id"))

    def _on_warning_go_to_block(self) -> None:
        """Botón 'Ir al bloque' → selecciona el de la fila actual."""
        row = self._warnings_table.currentRow()
        if row < 0:
            return
        item = self._warnings_table.item(row, 0)
        if item is None:
            return
        w = item.data(Qt.UserRole)
        if w:
            self._navigate_to_block(w.get("_block_id"))

    def _on_suggestion_clicked(self, item: QTableWidgetItem) -> None:
        """Doble-click en una sugerencia → navega al bloque."""
        s = self._sugs_table.item(item.row(), 0).data(Qt.UserRole)
        if s:
            self._navigate_to_block(s.get("_block_id"))

    def _on_suggestion_apply(self) -> None:
        """Aplica la sugerencia: setea block.allow_reactions=True y
        agrega suggested_reactions a active_reactions."""
        if self._editor is None:
            return
        row = self._sugs_table.currentRow()
        if row < 0:
            return
        item = self._sugs_table.item(row, 0)
        if item is None:
            return
        s = item.data(Qt.UserRole)
        if not s:
            return
        bid = s.get("_block_id")
        block = self._editor.fs.blocks.get(bid)
        if block is None:
            return
        block.allow_reactions = True
        # Mergear suggested_reactions en active_reactions sin duplicar
        current = list(getattr(block, "active_reactions", []) or [])
        for rid in s.get("suggested_reactions", []) or []:
            if rid not in current:
                current.append(rid)
        block.active_reactions = current
        # Marcar dirty para reflejar el cambio
        if hasattr(self._editor, "_mark_dirty"):
            self._editor._mark_dirty()
        # Sugerencia procesada — la quitamos de la tabla
        self._sugs_table.removeRow(row)
        # Actualizar contador del tab
        n = self._sugs_table.rowCount()
        self._tabs.setTabText(1, f"💡 Sugerencias ({n})")

    def _on_suggestion_ignore(self) -> None:
        """Ignora la sugerencia (la quita del panel solo en esta sesion)."""
        row = self._sugs_table.currentRow()
        if row < 0:
            return
        self._sugs_table.removeRow(row)
        n = self._sugs_table.rowCount()
        self._tabs.setTabText(1, f"💡 Sugerencias ({n})")
