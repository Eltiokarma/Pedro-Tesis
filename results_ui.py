# ======================================================
# RESULTS DASHBOARD — Toplevel con pestañas que reúne
# todos los outputs del análisis económico.
# ======================================================
# Tabs:
#   1) Overview    — KPI cards + tablas resumen
#   2) Cash Flow   — bar chart + curva NPV acumulado +
#                    tabla detallada
#   3) Breakdown   — pies de Capital y costos OPEX
#   4) Sensitivity — histograma NPV + tornado (MC)
#
# Diseño "Stripe-like": cards con border sutil, header
# azul, accent verde para positivo / rojo para negativo,
# fuente clara, padding generoso.
# ======================================================

import os
import subprocess
import sys

from tkinter import (
    Toplevel,
    Frame,
    Label,
    StringVar,
    END,
    BOTH,
    LEFT,
    RIGHT,
    TOP,
    BOTTOM,
    X,
    Y,
    W,
    E,
    N,
    S,
    NSEW,
    VERTICAL,
    HORIZONTAL,
)
from tkinter import ttk
from tkinter import messagebox


# ======================================================
# MATPLOTLIB OPCIONAL
# ======================================================

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    _MATPLOTLIB_OK = True
except ImportError:
    _MATPLOTLIB_OK = False


# ======================================================
# PALETA Y FUENTES
# ======================================================

COLOR_BG       = "#f7f7fa"
COLOR_CARD     = "#ffffff"
COLOR_BORDER   = "#dcdce4"
COLOR_HEADER   = "#1565c0"
COLOR_SUBTLE   = "#5c5c66"
COLOR_POSITIVE = "#2e7d32"
COLOR_NEGATIVE = "#c62828"
COLOR_NEUTRAL  = "#1a1a1a"
COLOR_ACCENT   = "#7b1fa2"

FONT_TITLE = ("Segoe UI", 14, "bold")
FONT_H1    = ("Segoe UI", 12, "bold")
FONT_H2    = ("Segoe UI", 10, "bold")
FONT_KPI_V = ("Segoe UI", 20, "bold")
FONT_KPI_L = ("Segoe UI", 9)
FONT_BODY  = ("Segoe UI", 10)
FONT_TABLE = ("Consolas", 10)


# ======================================================
# DASHBOARD PRINCIPAL
# ======================================================

def AbrirDashboard(
        parent,
        resultado_base,
        resultado_mc=None,
        on_open_excel=None,
        tab_inicial=0,
):
    """Abre el dashboard de resultados.

    resultado_base: dict devuelto por
        pipeline.ejecutar_analisis().
    resultado_mc:   dict devuelto por
        pipeline.ejecutar_montecarlo() (opcional).
    on_open_excel:  callback para abrir el .xlsx, o None.
    tab_inicial:    índice de tab a mostrar al abrir.
    """

    ventana = Toplevel(parent)
    ventana.title("Economic Analysis — Results Dashboard")
    ventana.geometry("1180x720+140+40")
    ventana.configure(bg=COLOR_BG)
    ventana.transient(parent)
    ventana.minsize(960, 600)

    _config_styles()

    # ---- header bar ----
    header = ttk.Frame(ventana, style="Header.TFrame")
    header.pack(fill=X)

    Label(
        header,
        text="ECONOMIC ANALYSIS",
        font=FONT_TITLE, bg=COLOR_HEADER, fg="white",
        padx=18, pady=10,
    ).pack(side=LEFT)

    Label(
        header,
        text=_header_subtitle(resultado_base),
        font=FONT_BODY, bg=COLOR_HEADER, fg="#bbdefb",
        padx=10, pady=10,
    ).pack(side=LEFT)

    if on_open_excel is not None:
        ttk.Button(
            header,
            text="Open Excel report",
            style="Header.TButton",
            command=on_open_excel,
        ).pack(side=RIGHT, padx=10, pady=6)

    # ---- notebook ----
    notebook = ttk.Notebook(ventana)
    notebook.pack(fill=BOTH, expand=True, padx=10, pady=10)

    # tabs
    _construir_tab_overview(notebook, resultado_base)
    _construir_tab_cashflow(notebook, resultado_base)
    _construir_tab_breakdown(notebook, resultado_base)
    _construir_tab_sensitivity(notebook, resultado_mc)

    try:
        notebook.select(tab_inicial)
    except Exception:
        pass


# ======================================================
# TAB 1 — OVERVIEW
# ======================================================

def _construir_tab_overview(notebook, r):

    tab = ttk.Frame(notebook, style="Tab.TFrame")
    notebook.add(tab, text="Overview")

    # --- KPI grid: 2 filas x 3 columnas ---
    npv  = r.get("npv")
    irr  = r.get("irr")
    pbs  = r.get("pbp_simple")
    pbd  = r.get("pbp_descontado")
    roi  = r.get("roi")
    fci  = r["costos"]["FCI"]

    kpis_row1 = [
        ("NPV",         f"{npv:.2f}" if npv is not None else "n/a",   "MM USD",
         COLOR_POSITIVE if npv and npv > 0 else (COLOR_NEGATIVE if npv else COLOR_SUBTLE)),
        ("IRR / DCFROR", f"{irr*100:.2f} %" if irr is not None else "n/a", "",
         COLOR_POSITIVE if irr and irr > r["params"]["tasa_interes"] else (COLOR_NEGATIVE if irr else COLOR_SUBTLE)),
        ("FCI",         f"{fci:.2f}",          "MM USD", COLOR_NEUTRAL),
    ]

    kpis_row2 = [
        ("Payback (simple)",     f"{pbs:.2f}" if pbs is not None else "n/a",    "years", COLOR_NEUTRAL),
        ("Payback (discounted)", f"{pbd:.2f}" if pbd is not None else "n/a",    "years", COLOR_NEUTRAL),
        ("ROI (avg)",            f"{roi*100:.2f} %" if roi is not None else "n/a", "", COLOR_NEUTRAL),
    ]

    kpi_grid = ttk.Frame(tab, style="Tab.TFrame")
    kpi_grid.pack(fill=X, padx=18, pady=(18, 10))

    for col, (titulo, valor, unidad, color) in enumerate(kpis_row1):
        _kpi_card(kpi_grid, titulo, valor, unidad, color)\
            .grid(row=0, column=col, padx=8, pady=6, sticky="nsew")
    for col, (titulo, valor, unidad, color) in enumerate(kpis_row2):
        _kpi_card(kpi_grid, titulo, valor, unidad, color)\
            .grid(row=1, column=col, padx=8, pady=6, sticky="nsew")

    for c in range(3):
        kpi_grid.columnconfigure(c, weight=1, uniform="kpi")

    # --- secciones inferiores: NPV @ rates + Capital + Operating ---
    bottom = ttk.Frame(tab, style="Tab.TFrame")
    bottom.pack(fill=BOTH, expand=True, padx=18, pady=10)

    # NPV @ rates
    npv_card = _section_card(bottom, "NPV at alternative discount rates")
    npv_card.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 8))

    tasa_proy = r["params"]["tasa_interes"]
    rows_npv = []
    for tasa, val in sorted(r.get("npv_at_rates", {}).items()):
        marca = "  ← project" if abs(tasa - tasa_proy) < 1e-9 else ""
        rows_npv.append(
            (f"{tasa*100:5.1f} %", f"{val:>10.2f} MM USD{marca}")
        )
    _two_col_table(npv_card, ("Rate", "NPV"), rows_npv)

    # Capital breakdown
    cap_card = _section_card(bottom, "Capital breakdown")
    cap_card.pack(side=LEFT, fill=BOTH, expand=True, padx=(8, 8))

    c = r["costos"]
    cepci_f = r.get("cepci_factor", 1.0)
    cap_rows = [
        ("ISBL",       f"{c['ISBL']:>10.2f} MM USD"),
        ("OSBL",       f"{c['OSBL']:>10.2f} MM USD"),
        ("Engineering",f"{c['ENG']:>10.2f} MM USD"),
        ("Contingency",f"{c['CONT']:>10.2f} MM USD"),
        ("─" * 12,     "─" * 22),
        ("FCI",        f"{c['FCI']:>10.2f} MM USD"),
        ("Working Cap",f"{c['WC']:>10.2f} MM USD"),
    ]
    if cepci_f != 1.0:
        cap_rows.append(("", ""))
        cap_rows.append((
            f"CEPCI {r.get('cepci_year_basis')}→{r.get('cepci_year_target')}",
            f"factor {cepci_f:.3f}",
        ))
    _two_col_table(cap_card, ("Item", "Value"), cap_rows)

    # Operating summary
    op_card = _section_card(bottom, "Operating costs (yr 1, base)")
    op_card.pack(side=LEFT, fill=BOTH, expand=True, padx=(8, 0))

    op_rows = [
        ("Revenue",      f"{c['Revenue']:>10.2f} MM USD/yr"),
        ("Byproducts",   f"{c['Byproducts']:>10.2f} MM USD/yr"),
        ("Raw materials",f"{c['RawMaterials']:>10.2f} MM USD/yr"),
        ("Consumables",  f"{c['Consumables']:>10.2f} MM USD/yr"),
        ("Utilities",    f"{c['Utilities']:>10.2f} MM USD/yr"),
        ("─" * 14,       "─" * 22),
        ("VCOP",         f"{c['VCOP']:>10.2f} MM USD/yr"),
        ("FCOP",         f"{c['FCOP']:>10.2f} MM USD/yr"),
        ("─" * 14,       "─" * 22),
        ("CCOP",         f"{c['VCOP'] + c['FCOP']:>10.2f} MM USD/yr"),
    ]
    _two_col_table(op_card, ("Item", "Value"), op_rows)


# ======================================================
# TAB 2 — CASH FLOW
# ======================================================

def _construir_tab_cashflow(notebook, r):

    tab = ttk.Frame(notebook, style="Tab.TFrame")
    notebook.add(tab, text="Cash Flow")

    cf = r["cf"]
    años = cf["años"]
    tasa = r["params"]["tasa_interes"]

    # NPV acumulado por año
    npv_acum = []
    suma = 0.0
    for i in range(len(cf["CF"])):
        suma += cf["CF"][i] / ((1 + tasa) ** años[i])
        npv_acum.append(suma)

    # ---- chart frame ----
    frame_chart = ttk.Frame(tab, style="Tab.TFrame")
    frame_chart.pack(fill=BOTH, expand=True, padx=10, pady=(10, 0))

    if _MATPLOTLIB_OK:
        fig = Figure(figsize=(11.5, 4.6), dpi=100, facecolor=COLOR_BG)

        # Cash flow bars
        ax1 = fig.add_subplot(1, 2, 1, facecolor="white")
        colors = [COLOR_POSITIVE if v >= 0 else COLOR_NEGATIVE for v in cf["CF"]]
        ax1.bar(años, cf["CF"], color=colors, edgecolor="white")
        ax1.axhline(0, color="black", linewidth=0.8)
        ax1.set_title("Annual Cash Flow", fontsize=11, fontweight="bold", color=COLOR_NEUTRAL)
        ax1.set_xlabel("Project year")
        ax1.set_ylabel("CF (MM USD)")
        ax1.grid(True, axis="y", alpha=0.3, linestyle="--")
        for spine in ("top", "right"):
            ax1.spines[spine].set_visible(False)

        # NPV acumulado
        ax2 = fig.add_subplot(1, 2, 2, facecolor="white")
        ax2.plot(años, npv_acum, marker="o", color=COLOR_HEADER, linewidth=2)
        ax2.fill_between(años, npv_acum, 0,
                          where=[v >= 0 for v in npv_acum],
                          interpolate=True, alpha=0.20, color=COLOR_POSITIVE)
        ax2.fill_between(años, npv_acum, 0,
                          where=[v < 0 for v in npv_acum],
                          interpolate=True, alpha=0.20, color=COLOR_NEGATIVE)
        ax2.axhline(0, color="black", linewidth=0.8)
        ax2.set_title("Cumulative NPV (discounted)", fontsize=11, fontweight="bold", color=COLOR_NEUTRAL)
        ax2.set_xlabel("Project year")
        ax2.set_ylabel("Σ PV(CF)  (MM USD)")
        ax2.grid(True, alpha=0.3, linestyle="--")
        for spine in ("top", "right"):
            ax2.spines[spine].set_visible(False)

        # Marcar PBP descontado si existe
        pbd = r.get("pbp_descontado")
        if pbd is not None:
            ax2.axvline(pbd, color=COLOR_ACCENT, linestyle="--", linewidth=1.5,
                        label=f"PBP discntd = {pbd:.2f} yr")
            ax2.legend(loc="best", fontsize=9)

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, master=frame_chart)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=BOTH, expand=True)
    else:
        Label(
            frame_chart, bg=COLOR_BG,
            text="matplotlib no instalado — chart no disponible.\n"
                 "pip install matplotlib",
            font=FONT_BODY, fg=COLOR_NEGATIVE,
        ).pack(padx=20, pady=20, anchor=W)

    # ---- tabla detallada ----
    frame_tabla = ttk.LabelFrame(tab, text=" Yearly detail ")
    frame_tabla.pack(fill=X, padx=10, pady=10)

    cols = ("year", "capex", "rev", "ccop", "gp", "dep", "ti", "tax", "cf", "pv_cf", "npv_cum")
    headers = ("Year", "CapEx", "Revenue", "CCOP", "GP", "Dep", "TI", "Tax", "CF", "PV(CF)", "Σ NPV")
    widths = (60, 90, 90, 90, 90, 80, 90, 80, 90, 90, 90)

    tabla = ttk.Treeview(frame_tabla, columns=cols, show="headings", height=8)
    for c, h, w in zip(cols, headers, widths):
        tabla.heading(c, text=h)
        tabla.column(c, width=w, anchor="e" if c != "year" else "center")

    suma = 0.0
    for i in range(len(años)):
        pv = cf["CF"][i] / ((1 + tasa) ** años[i])
        suma += pv
        tabla.insert("", END, values=(
            int(años[i]),
            f"{cf['CapEx'][i]:.2f}",
            f"{cf['Revenue'][i]:.2f}",
            f"{cf['CCOP'][i]:.2f}",
            f"{cf['GP'][i]:.2f}",
            f"{cf['Dep'][i]:.2f}",
            f"{cf['TI'][i]:.2f}",
            f"{cf['Taxes'][i]:.2f}",
            f"{cf['CF'][i]:.2f}",
            f"{pv:.2f}",
            f"{suma:.2f}",
        ))

    sb = ttk.Scrollbar(frame_tabla, orient=VERTICAL, command=tabla.yview)
    tabla.configure(yscrollcommand=sb.set)
    tabla.pack(side=LEFT, fill=X, expand=True)
    sb.pack(side=RIGHT, fill=Y)


# ======================================================
# TAB 3 — BREAKDOWN
# ======================================================

def _construir_tab_breakdown(notebook, r):

    tab = ttk.Frame(notebook, style="Tab.TFrame")
    notebook.add(tab, text="Breakdown")

    c = r["costos"]

    if not _MATPLOTLIB_OK:
        Label(
            tab, bg=COLOR_BG,
            text="matplotlib no instalado — pie charts no disponibles.",
            font=FONT_BODY, fg=COLOR_NEGATIVE,
        ).pack(padx=20, pady=20, anchor=W)
        return

    fig = Figure(figsize=(11.5, 5.4), dpi=100, facecolor=COLOR_BG)

    # --- Capital ---
    ax1 = fig.add_subplot(1, 3, 1, facecolor="white")
    cap_labels = ["ISBL", "OSBL", "Engineering", "Contingency", "WC"]
    cap_values = [c["ISBL"], c["OSBL"], c["ENG"], c["CONT"], c["WC"]]
    # filter out zero
    cap_filtered = [(l, v) for l, v in zip(cap_labels, cap_values) if v > 0]
    if cap_filtered:
        labels, values = zip(*cap_filtered)
        ax1.pie(values, labels=labels, autopct="%1.1f%%",
                colors=["#1976d2", "#388e3c", "#fbc02d", "#e64a19", "#7b1fa2"][:len(values)],
                textprops={"fontsize": 9})
    ax1.set_title("Capital structure", fontsize=11, fontweight="bold", color=COLOR_NEUTRAL)

    # --- Operating ---
    ax2 = fig.add_subplot(1, 3, 2, facecolor="white")
    op_labels = ["Raw materials", "Utilities", "Consumables", "FCOP", "− Byproducts"]
    op_values = [c["RawMaterials"], c["Utilities"], c["Consumables"], c["FCOP"], c["Byproducts"]]
    op_filtered = [(l, v) for l, v in zip(op_labels, op_values) if v > 0]
    if op_filtered:
        labels, values = zip(*op_filtered)
        ax2.pie(values, labels=labels, autopct="%1.1f%%",
                colors=["#c62828", "#f57c00", "#fbc02d", "#1976d2", "#388e3c"][:len(values)],
                textprops={"fontsize": 9})
    ax2.set_title("Operating cost structure", fontsize=11, fontweight="bold", color=COLOR_NEUTRAL)

    # --- Revenue waterfall (a year-1 base) ---
    ax3 = fig.add_subplot(1, 3, 3, facecolor="white")
    rev = c["Revenue"]
    bp  = c["Byproducts"]
    rm  = c["RawMaterials"]
    uts = c["Utilities"]
    cons = c["Consumables"]
    fcop = c["FCOP"]
    gp_base = rev + bp - rm - uts - cons - fcop

    items = [
        ("Revenue", rev,    COLOR_POSITIVE),
        ("+BP",     bp,     COLOR_POSITIVE),
        ("-RM",    -rm,     COLOR_NEGATIVE),
        ("-Util",  -uts,    COLOR_NEGATIVE),
        ("-Cons",  -cons,   COLOR_NEGATIVE),
        ("-FCOP",  -fcop,   COLOR_NEGATIVE),
        ("=GP",     gp_base,COLOR_HEADER),
    ]
    xs = list(range(len(items)))
    heights = [v for _, v, _ in items]
    cols = [c_ for _, _, c_ in items]
    ax3.bar(xs, heights, color=cols, edgecolor="white")
    ax3.axhline(0, color="black", linewidth=0.8)
    ax3.set_xticks(xs)
    ax3.set_xticklabels([n for n, _, _ in items], fontsize=8, rotation=15)
    ax3.set_title("Yr-1 income waterfall", fontsize=11, fontweight="bold", color=COLOR_NEUTRAL)
    ax3.set_ylabel("MM USD/yr")
    ax3.grid(True, axis="y", alpha=0.3, linestyle="--")
    for spine in ("top", "right"):
        ax3.spines[spine].set_visible(False)

    fig.tight_layout()
    canvas = FigureCanvasTkAgg(fig, master=tab)
    canvas.draw()
    canvas.get_tk_widget().pack(fill=BOTH, expand=True, padx=10, pady=10)


# ======================================================
# TAB 4 — SENSITIVITY
# ======================================================

def _construir_tab_sensitivity(notebook, mc_resultado):

    tab = ttk.Frame(notebook, style="Tab.TFrame")
    notebook.add(tab, text="Sensitivity")

    if mc_resultado is None:
        Label(
            tab, bg=COLOR_BG,
            text=(
                "Sensitivity analysis was not run.\n\n"
                "Enable 'Sensitivity analysis' in the main window and\n"
                "re-run Solve to perform a Monte Carlo + tornado study."
            ),
            font=FONT_BODY, fg=COLOR_SUBTLE, justify="left",
        ).pack(padx=30, pady=30, anchor=W)
        return

    mc = mc_resultado["mc"]
    tornado = mc_resultado["tornado"]
    stats = mc["stats"]

    # ---- summary cards ----
    cards_frame = ttk.Frame(tab, style="Tab.TFrame")
    cards_frame.pack(fill=X, padx=18, pady=(18, 6))

    p_neg_color = COLOR_NEGATIVE if stats["p_npv_neg"] > 0.5 else (
        COLOR_POSITIVE if stats["p_npv_neg"] < 0.1 else COLOR_NEUTRAL
    )

    kpis = [
        ("Runs",        f"{stats['n']}", "", COLOR_NEUTRAL),
        ("NPV mean",    f"{stats['npv_mean']:.2f}", "MM USD", COLOR_NEUTRAL),
        ("NPV P10–P90", f"{stats['npv_p10']:.1f} … {stats['npv_p90']:.1f}",  "MM USD", COLOR_NEUTRAL),
        ("P(NPV<0)",    f"{stats['p_npv_neg']*100:.1f} %",  "", p_neg_color),
    ]
    for col, (t, v, u, color) in enumerate(kpis):
        _kpi_card(cards_frame, t, v, u, color)\
            .grid(row=0, column=col, padx=6, pady=4, sticky="nsew")
    for c in range(4):
        cards_frame.columnconfigure(c, weight=1, uniform="mc_kpi")

    # ---- charts ----
    if not _MATPLOTLIB_OK:
        Label(
            tab, bg=COLOR_BG,
            text="matplotlib no instalado — charts no disponibles.",
            font=FONT_BODY, fg=COLOR_NEGATIVE,
        ).pack(padx=20, pady=20, anchor=W)
        return

    fig = Figure(figsize=(11.5, 4.8), dpi=100, facecolor=COLOR_BG)

    # Histograma NPV
    ax1 = fig.add_subplot(1, 2, 1, facecolor="white")
    ax1.hist(mc["npvs"], bins=40, color=COLOR_HEADER, edgecolor="white")
    ax1.axvline(stats["npv_p10"], color="#f57c00", linestyle="--", linewidth=1.2, label="P10")
    ax1.axvline(stats["npv_p50"], color=COLOR_NEGATIVE, linestyle="--", linewidth=1.2, label="P50")
    ax1.axvline(stats["npv_p90"], color=COLOR_POSITIVE, linestyle="--", linewidth=1.2, label="P90")
    ax1.axvline(0, color="black", linewidth=0.8)
    ax1.set_title("NPV distribution", fontsize=11, fontweight="bold", color=COLOR_NEUTRAL)
    ax1.set_xlabel("NPV (MM USD)")
    ax1.set_ylabel("Frequency")
    ax1.legend(loc="upper right", fontsize=8)
    ax1.grid(True, alpha=0.3, linestyle="--")
    for spine in ("top", "right"):
        ax1.spines[spine].set_visible(False)

    # Tornado
    ax2 = fig.add_subplot(1, 2, 2, facecolor="white")
    nombres = [r["nombre"] for r in tornado][::-1]
    deltas_low = [r["delta_low"] for r in tornado][::-1]
    deltas_high = [r["delta_high"] for r in tornado][::-1]
    y = list(range(len(nombres)))
    ax2.barh(y, deltas_low,  color=COLOR_NEGATIVE, label="Min", edgecolor="white")
    ax2.barh(y, deltas_high, color=COLOR_POSITIVE, label="Max", edgecolor="white")
    ax2.set_yticks(y)
    ax2.set_yticklabels(nombres, fontsize=9)
    ax2.axvline(0, color="black", linewidth=0.8)
    ax2.set_title("Tornado — ΔNPV from base", fontsize=11, fontweight="bold", color=COLOR_NEUTRAL)
    ax2.set_xlabel("ΔNPV (MM USD)")
    ax2.legend(loc="lower right", fontsize=8)
    ax2.grid(True, axis="x", alpha=0.3, linestyle="--")
    for spine in ("top", "right"):
        ax2.spines[spine].set_visible(False)

    fig.tight_layout()
    canvas = FigureCanvasTkAgg(fig, master=tab)
    canvas.draw()
    canvas.get_tk_widget().pack(fill=BOTH, expand=True, padx=10, pady=10)


# ======================================================
# COMPONENTES REUSABLES
# ======================================================

def _kpi_card(parent, titulo, valor, unidad, color_valor):
    """Card con label arriba y valor grande abajo."""
    frame = Frame(
        parent, bg=COLOR_CARD,
        highlightbackground=COLOR_BORDER,
        highlightthickness=1, bd=0,
    )
    Label(
        frame, text=titulo.upper(),
        font=FONT_KPI_L, bg=COLOR_CARD, fg=COLOR_SUBTLE,
        padx=14, pady=(10, 2), anchor="w",
    ).pack(fill=X)

    valor_frame = Frame(frame, bg=COLOR_CARD)
    valor_frame.pack(fill=X, padx=14, pady=(0, 12))

    Label(
        valor_frame, text=valor,
        font=FONT_KPI_V, bg=COLOR_CARD, fg=color_valor,
    ).pack(side=LEFT, anchor="w")

    if unidad:
        Label(
            valor_frame, text=f"  {unidad}",
            font=FONT_KPI_L, bg=COLOR_CARD, fg=COLOR_SUBTLE,
        ).pack(side=LEFT, anchor="s", pady=(0, 5))

    return frame


def _section_card(parent, titulo):
    """Card con título h1 + body abajo."""
    frame = Frame(
        parent, bg=COLOR_CARD,
        highlightbackground=COLOR_BORDER,
        highlightthickness=1, bd=0,
    )
    Label(
        frame, text=titulo,
        font=FONT_H1, bg=COLOR_CARD, fg=COLOR_HEADER,
        padx=14, pady=(10, 6), anchor="w",
    ).pack(fill=X)
    return frame


def _two_col_table(parent, headers, rows):
    """Tabla 2 columnas estilo card-body usando Labels."""

    body = Frame(parent, bg=COLOR_CARD)
    body.pack(fill=BOTH, expand=True, padx=14, pady=(0, 12))

    Label(
        body, text=headers[0],
        font=FONT_H2, bg=COLOR_CARD, fg=COLOR_SUBTLE,
        anchor="w",
    ).grid(row=0, column=0, sticky="w", pady=(0, 4))
    Label(
        body, text=headers[1],
        font=FONT_H2, bg=COLOR_CARD, fg=COLOR_SUBTLE,
        anchor="e",
    ).grid(row=0, column=1, sticky="e", pady=(0, 4))

    for i, (left, right) in enumerate(rows, start=1):
        Label(
            body, text=str(left),
            font=FONT_TABLE, bg=COLOR_CARD, fg=COLOR_NEUTRAL,
            anchor="w",
        ).grid(row=i, column=0, sticky="w", pady=1)
        Label(
            body, text=str(right),
            font=FONT_TABLE, bg=COLOR_CARD, fg=COLOR_NEUTRAL,
            anchor="e",
        ).grid(row=i, column=1, sticky="e", pady=1)

    body.columnconfigure(0, weight=1)
    body.columnconfigure(1, weight=1)


# ======================================================
# STYLES (ttk)
# ======================================================

def _config_styles():
    style = ttk.Style()

    # Si no se invoca con clam/alt no toma colors de fondo en
    # todos los OS — mantenemos el theme actual y solo
    # configuramos los nombres custom que usamos.

    style.configure("Tab.TFrame",     background=COLOR_BG)
    style.configure("Header.TFrame",  background=COLOR_HEADER)
    style.configure("Header.TButton",
                    background=COLOR_HEADER,
                    foreground="white",
                    padding=6)

    style.configure("TNotebook",       background=COLOR_BG, borderwidth=0)
    style.configure("TNotebook.Tab",   padding=(14, 8), font=FONT_H2)


# ======================================================
# UTILS
# ======================================================

def _header_subtitle(r):
    fci = r["costos"]["FCI"]
    tasa = r["params"]["tasa_interes"]
    return (
        f"FCI {fci:.1f} MM USD   ·   "
        f"Discount {tasa*100:.1f}%   ·   "
        f"Life {r['params']['vida']} yr"
    )
