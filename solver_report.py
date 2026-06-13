"""
solver_report.py — Reporte visual del resultado del solver.

Reemplaza el viejo QMessageBox con detailedText (texto monoespaciado
escondido tras "Ver detalles") por un diálogo formateado:

  · Banner de estado (convergió / con advertencias / no convergió).
  · Fila de métricas (iteraciones, flujos resueltos, reciclos, etc.).
  · Tarjetas por severidad con explicación humana de cada categoría
    (qué significa y qué revisar), no solo el mensaje crudo.
  · Secciones de info voluminosa (flujos/temperaturas propagados)
    colapsables para no abrumar.

`build_report(result, sem_issues)` es lógica pura (sin Qt) → testeable.
`SolverResultDialog` la renderiza.
"""

try:
    from block_inspector import TOK
except Exception:
    # Fallback headless (sin Qt): permite testear build_report y los
    # helpers de formato sin importar la cadena de PySide6.
    TOK = {
        "bg": "#f6f3ec", "bg_elev": "#ffffff", "bg_mute": "#f1ede4",
        "bg_sunk": "#ece6d8", "line": "#e6e0d0", "line_strong": "#d4ccb8",
        "ink": "#1a1714", "ink_mute": "#6b6256", "accent": "#0d6e78",
        "accent_deep": "#064951", "accent_tint": "#eaf4f5",
        "green": "#4d8742", "green_bg": "#e6f0df", "amber": "#b8841a",
        "amber_bg": "#f4ecd1", "danger": "#b8453a", "danger_bg": "#f3dcd8",
    }

# Metadatos de severidad → color/ícono/etiqueta.
SEV = {
    "error":  {"ink": TOK["danger"], "bg": TOK["danger_bg"], "icon": "✗",
               "label": "Error"},
    "warn":   {"ink": TOK["amber"],  "bg": TOK["amber_bg"],  "icon": "⚠",
               "label": "Advertencia"},
    "info":   {"ink": TOK["accent"], "bg": TOK.get("accent_tint", "#eaf4f5"),
               "icon": "•", "label": "Info"},
    "ok":     {"ink": TOK["green"],  "bg": TOK["green_bg"],   "icon": "✓",
               "label": "OK"},
}

# Banner por estado global.
_HERO = {
    "ok":      ("✓", "Convergió",
                "El balance de masa y energía cierra sin advertencias."),
    "warning": ("⚠", "Convergió con advertencias",
                "El balance cierra, pero hay puntos a revisar más abajo."),
    "error":   ("✗", "No convergió",
                "Hay errores de balance o flujos que el solver no pudo "
                "resolver."),
    "empty":   ("·", "Diagrama vacío",
                "No hay equipos para resolver."),
}

# Explicación humana por categoría de sección.
_EXPLAIN = {
    "mass":      "La masa que entra y sale de estos equipos no cuadra. "
                 "Revisá los flujos declarados o los specs de separación.",
    "unresolved":"El solver no pudo deducir estos flujos: probablemente "
                 "faltan specs o el lazo tiene grados de libertad de más.",
    "energy_err":"El balance de energía no cierra en estos equipos.",
    "recycle":   "Lazos de recirculación resueltos iterativamente (Wegstein). "
                 "El tear es la corriente que se itera hasta converger.",
    "energy_warn":"La temperatura calculada difiere de la declarada — típico "
                 "de cambios de fase o ΔH no capturados por el Cp simple. El "
                 "solver respeta tu T declarada.",
    "component": "Las composiciones declaradas no cierran un balance riguroso "
                 "por componente; el balance de masa total sí cierra.",
    "awareness": "Inconsistencias físicas latentes detectadas por el solver "
                 "(cierre de energía, T de descarga, duty espurio, reactor "
                 "estructural, etc.). Son advertencias de diseño: no frenan el "
                 "cálculo ni cambian el estado, pero conviene revisarlas.",
    "semantic":  "Conexiones que parecen inconsistentes (puerto o rol). No "
                 "frenan el cálculo, pero conviene revisarlas.",
    "mass_prop": "Flujos que el solver dedujo del balance (no estaban fijos).",
    "temp_prop": "Temperaturas que el solver propagó por balance de energía.",
}


def _n_warn(result, sem_issues):
    return (len(result.energy_warnings) + len(result.component_warnings)
            + sum(1 for _, sev, _ in sem_issues if sev == "warn")
            + sum(1 for rs in result.recycle_solutions if not rs.converged))


def _n_err(result, sem_issues):
    return (len(result.mass_balance_errors) + len(result.energy_balance_errors)
            + len(result.unresolved_streams)
            + sum(1 for _, sev, _ in sem_issues if sev != "warn"))


def build_report(result, sem_issues=None):
    """Lógica pura: arma el reporte como dict (sin tocar Qt).

    Devuelve:
      {status, icon, headline, explain, metrics:[(label,value,kind)],
       sections:[{kind,title,explain,rows,collapsible}]}
    Donde `rows` es list[str] salvo en la sección 'recycle', que usa
    list[dict] con las claves de RecycleSolution.
    """
    sem_issues = sem_issues or []
    status = getattr(result, "overall_status", "ok")
    icon, headline, explain = _HERO.get(status, _HERO["ok"])

    n_warn = _n_warn(result, sem_issues)
    n_err = _n_err(result, sem_issues)
    metrics = [
        ("Iteraciones", str(result.iterations), "info"),
        ("Flujos resueltos", str(len(result.propagated_mass)), "info"),
        ("Reciclos", str(len(result.recycle_solutions)), "info"),
        ("Advertencias", str(n_warn), "warn" if n_warn else "ok"),
        ("Errores", str(n_err), "error" if n_err else "ok"),
    ]

    sections = []

    if result.mass_balance_errors:
        sections.append({"kind": "error", "title": "Errores de balance de masa",
                         "explain": _EXPLAIN["mass"],
                         "rows": list(result.mass_balance_errors),
                         "collapsible": False})

    if result.unresolved_streams:
        sections.append({"kind": "error", "title": "Flujos sin resolver",
                         "explain": _EXPLAIN["unresolved"],
                         "rows": list(result.unresolved_streams),
                         "collapsible": False})

    if result.energy_balance_errors:
        sections.append({"kind": "error",
                         "title": "Errores de balance de energía",
                         "explain": _EXPLAIN["energy_err"],
                         "rows": list(result.energy_balance_errors),
                         "collapsible": False})

    if result.recycle_solutions:
        rows = [{"converged": rs.converged, "tear": rs.tear_stream,
                 "iterations": rs.iterations, "final_value": rs.final_value,
                 "cycle_blocks": list(rs.cycle_blocks),
                 "history": list(rs.history)}
                for rs in result.recycle_solutions]
        any_bad = any(not rs.converged for rs in result.recycle_solutions)
        sections.append({"kind": "warn" if any_bad else "info",
                         "title": "Reciclos (Wegstein)",
                         "explain": _EXPLAIN["recycle"], "rows": rows,
                         "collapsible": False, "is_recycle": True})

    # errores semánticos (no-warn) → sección de error
    sem_err = [f"{name}: {msg.split(chr(10))[0] if msg else ''}"
               for name, sev, msg in sem_issues if sev != "warn"]
    if sem_err:
        sections.append({"kind": "error",
                         "title": "Conexiones inválidas",
                         "explain": _EXPLAIN["semantic"], "rows": sem_err,
                         "collapsible": False})

    if result.energy_warnings:
        sections.append({"kind": "warn", "title": "Advertencias de energía",
                         "explain": _EXPLAIN["energy_warn"],
                         "rows": list(result.energy_warnings),
                         "collapsible": False})

    if result.component_warnings:
        sections.append({"kind": "warn",
                         "title": "Advertencias de balance por componente",
                         "explain": _EXPLAIN["component"],
                         "rows": list(result.component_warnings),
                         "collapsible": False})

    if getattr(result, "awareness_warnings", None):
        sections.append({"kind": "warn",
                         "title": "Conciencia física del solver",
                         "explain": _EXPLAIN["awareness"],
                         "rows": list(result.awareness_warnings),
                         "collapsible": True})

    sem_warn = [f"{name}: {msg.split(chr(10))[0] if msg else ''}"
                for name, sev, msg in sem_issues if sev == "warn"]
    if sem_warn:
        sections.append({"kind": "warn",
                         "title": "Conexiones a revisar",
                         "explain": _EXPLAIN["semantic"], "rows": sem_warn,
                         "collapsible": False})

    if result.propagated_mass:
        rows = [f"{name}  →  {val:.4g} tm/año"
                for name, val in result.propagated_mass]
        sections.append({"kind": "info", "title": "Flujos propagados",
                         "explain": _EXPLAIN["mass_prop"], "rows": rows,
                         "collapsible": True})

    if result.propagated_temp:
        rows = [f"{name}  →  {val:.1f} °C"
                for name, val in result.propagated_temp]
        sections.append({"kind": "info", "title": "Temperaturas propagadas",
                         "explain": _EXPLAIN["temp_prop"], "rows": rows,
                         "collapsible": True})

    return {"status": status, "icon": icon, "headline": headline,
            "explain": explain, "metrics": metrics, "sections": sections}


# ─────────────────────────────────────────────────────────────────────
# Render Qt
# ─────────────────────────────────────────────────────────────────────
def _fmt_recycle_row(d):
    """Texto multi-línea para una RecycleSolution."""
    head = ("✓ convergió" if d["converged"] else "⚠ no convergió")
    head += f"  ·  tear {d['tear']}  ·  {d['iterations']} iter"
    head += f"  ·  {d['final_value']:.4g} tm/año"
    sub = []
    if d["cycle_blocks"]:
        sub.append("ciclo: " + " → ".join(d["cycle_blocks"]))
    hist = d["history"]
    if len(hist) > 1:
        h = " → ".join(f"{v:.1f}" for v in hist[:5])
        if len(hist) > 5:
            h += f" → … → {hist[-1]:.1f}"
        sub.append("trayectoria: " + h)
    return head, sub


def _build_dialog(report, summary_text, parent=None):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QWidget,
        QFrame, QPushButton, QApplication)

    dlg = QDialog(parent)
    dlg.setWindowTitle("Resultado del solver")
    dlg.setMinimumWidth(560)
    dlg.resize(620, 640)
    dlg.setStyleSheet(f"QDialog {{ background: {TOK['bg']}; }}")

    root = QVBoxLayout(dlg)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    sev_hero = {"ok": "ok", "warning": "warn", "error": "error",
                "empty": "info"}.get(report["status"], "info")
    meta = SEV[sev_hero]

    # ── Banner de estado ──
    hero = QFrame()
    hero.setStyleSheet(
        f"background: {meta['bg']}; border-bottom: 2px solid {meta['ink']};")
    hl = QHBoxLayout(hero)
    hl.setContentsMargins(20, 16, 20, 16)
    hl.setSpacing(14)
    ico = QLabel(report["icon"])
    ico.setStyleSheet(
        f"color: {meta['ink']}; font-size: 30px; font-weight: 700;")
    ico.setAlignment(Qt.AlignTop)
    hl.addWidget(ico)
    txt = QVBoxLayout()
    txt.setSpacing(2)
    h1 = QLabel(report["headline"])
    h1.setStyleSheet(
        f"color: {meta['ink']}; font-size: 17px; font-weight: 700;")
    sub = QLabel(report["explain"])
    sub.setWordWrap(True)
    sub.setStyleSheet(f"color: {TOK['ink_mute']}; font-size: 11.5px;")
    txt.addWidget(h1)
    txt.addWidget(sub)
    hl.addLayout(txt, 1)
    root.addWidget(hero)

    # ── Fila de métricas ──
    mrow = QFrame()
    mrow.setStyleSheet(f"background: {TOK['bg_elev']}; "
                       f"border-bottom: 1px solid {TOK['line']};")
    ml = QHBoxLayout(mrow)
    ml.setContentsMargins(14, 10, 14, 10)
    ml.setSpacing(8)
    for label, value, kind in report["metrics"]:
        m = SEV.get(kind, SEV["info"])
        chip = QFrame()
        chip.setStyleSheet(
            f"background: {m['bg']}; border-radius: 8px;")
        cl = QVBoxLayout(chip)
        cl.setContentsMargins(12, 7, 12, 7)
        cl.setSpacing(0)
        v = QLabel(value)
        v.setAlignment(Qt.AlignCenter)
        v.setStyleSheet(
            f"color: {m['ink']}; font-size: 18px; font-weight: 700; "
            f"background: transparent;")
        k = QLabel(label)
        k.setAlignment(Qt.AlignCenter)
        k.setStyleSheet(f"color: {TOK['ink_mute']}; font-size: 10px; "
                        f"background: transparent;")
        cl.addWidget(v)
        cl.addWidget(k)
        ml.addWidget(chip, 1)
    root.addWidget(mrow)

    # ── Cuerpo scrolleable con tarjetas ──
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setStyleSheet("QScrollArea { background: transparent; }")
    body = QWidget()
    bl = QVBoxLayout(body)
    bl.setContentsMargins(16, 14, 16, 14)
    bl.setSpacing(12)

    if not report["sections"]:
        empty = QLabel("Sin observaciones — todo cerró limpio.")
        empty.setStyleSheet(f"color: {TOK['ink_mute']}; font-size: 12px; "
                            f"padding: 8px;")
        bl.addWidget(empty)

    for sec in report["sections"]:
        bl.addWidget(_section_card(sec))
    bl.addStretch(1)
    scroll.setWidget(body)
    root.addWidget(scroll, 1)

    # ── Footer ──
    foot = QFrame()
    foot.setStyleSheet(f"background: {TOK['bg_elev']}; "
                       f"border-top: 1px solid {TOK['line']};")
    fl = QHBoxLayout(foot)
    fl.setContentsMargins(14, 10, 14, 10)
    btn_copy = QPushButton("Copiar resumen")
    btn_copy.setStyleSheet(_btn_style(primary=False))

    def _copy():
        QApplication.clipboard().setText(summary_text)
        btn_copy.setText("Copiado ✓")
    btn_copy.clicked.connect(_copy)
    fl.addWidget(btn_copy)
    fl.addStretch(1)
    btn_close = QPushButton("Cerrar")
    btn_close.setStyleSheet(_btn_style(primary=True))
    btn_close.clicked.connect(dlg.accept)
    btn_close.setDefault(True)
    fl.addWidget(btn_close)
    root.addWidget(foot)

    return dlg


def _btn_style(primary):
    if primary:
        return (f"QPushButton {{ background: {TOK['accent']}; color: white; "
                f"border: none; border-radius: 7px; padding: 7px 18px; "
                f"font-weight: 600; }}"
                f"QPushButton:hover {{ background: {TOK['accent_deep']}; }}")
    return (f"QPushButton {{ background: {TOK['bg_mute']}; "
            f"color: {TOK['ink']}; border: 1px solid {TOK['line_strong']}; "
            f"border-radius: 7px; padding: 7px 14px; }}"
            f"QPushButton:hover {{ background: {TOK['bg_sunk']}; }}")


def _section_card(sec):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                                   QPushButton, QWidget)
    meta = SEV.get(sec["kind"], SEV["info"])
    card = QFrame()
    card.setStyleSheet(
        f"QFrame#card {{ background: {TOK['bg_elev']}; "
        f"border: 1px solid {TOK['line']}; "
        f"border-left: 4px solid {meta['ink']}; border-radius: 8px; }}")
    card.setObjectName("card")
    cl = QVBoxLayout(card)
    cl.setContentsMargins(14, 11, 14, 12)
    cl.setSpacing(6)

    rows = sec["rows"]
    n = len(rows)

    # Header
    hdr = QHBoxLayout()
    hdr.setSpacing(8)
    badge = QLabel(meta["icon"])
    badge.setStyleSheet(f"color: {meta['ink']}; font-size: 15px; "
                        f"font-weight: 700;")
    hdr.addWidget(badge)
    title = QLabel(f"{sec['title']}  ({n})")
    title.setStyleSheet(f"color: {TOK['ink']}; font-size: 13px; "
                        f"font-weight: 700;")
    hdr.addWidget(title)
    hdr.addStretch(1)
    cl.addLayout(hdr)

    if sec.get("explain"):
        ex = QLabel(sec["explain"])
        ex.setWordWrap(True)
        ex.setStyleSheet(f"color: {TOK['ink_mute']}; font-size: 11px; "
                        f"font-style: italic;")
        cl.addWidget(ex)

    body = QWidget()
    bl = QVBoxLayout(body)
    bl.setContentsMargins(0, 4, 0, 0)
    bl.setSpacing(4)

    if sec.get("is_recycle"):
        for d in rows:
            head, subs = _fmt_recycle_row(d)
            rmeta = SEV["ok"] if d["converged"] else SEV["warn"]
            lh = QLabel(head)
            lh.setWordWrap(True)
            lh.setStyleSheet(f"color: {rmeta['ink']}; font-size: 12px; "
                            f"font-weight: 600;")
            bl.addWidget(lh)
            for s in subs:
                ls = QLabel("    " + s)
                ls.setWordWrap(True)
                ls.setStyleSheet(f"color: {TOK['ink_mute']}; "
                                f"font-size: 11px; font-family: monospace;")
                bl.addWidget(ls)
    else:
        for r in rows:
            lbl = QLabel("·  " + str(r))
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lbl.setStyleSheet(f"color: {TOK['ink']}; font-size: 11.5px;")
            bl.addWidget(lbl)

    if sec.get("collapsible") and n > 0:
        # arranca colapsado: header-botón toggle
        body.setVisible(False)
        toggle = QPushButton(f"▸ Ver {n} corrientes")
        toggle.setCursor(Qt.PointingHandCursor)
        toggle.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; "
            f"color: {TOK['accent']}; font-size: 11.5px; text-align: left; "
            f"padding: 2px 0; }}"
            f"QPushButton:hover {{ color: {TOK['accent_deep']}; }}")

        def _toggle():
            vis = not body.isVisible()
            body.setVisible(vis)
            toggle.setText((f"▾ Ocultar corrientes" if vis
                            else f"▸ Ver {n} corrientes"))
        toggle.clicked.connect(_toggle)
        cl.addWidget(toggle)

    cl.addWidget(body)
    return card


def show_solver_report(result, sem_issues=None, parent=None):
    """Construye y muestra el diálogo modal del resultado del solver."""
    sem_issues = sem_issues or []
    report = build_report(result, sem_issues)
    summary_text = result.summary()
    if sem_issues:
        summary_text += "\n\n─ Validación semántica de conexiones ─\n"
        for name, sev, msg in sem_issues:
            tag = "⚠" if sev == "warn" else "✗"
            first = msg.split("\n")[0] if msg else ""
            summary_text += f"\n{tag} {name}:\n  {first}\n"
    dlg = _build_dialog(report, summary_text, parent=parent)
    dlg.exec()
