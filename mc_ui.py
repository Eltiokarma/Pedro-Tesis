# ======================================================
# UI MONTE CARLO — Ventanas Tkinter para configuración
# y visualización de resultados.
# ======================================================
# Diseño:
#   1) AbrirVentanaConfigMC: Toplevel con tabla editable
#      (Variable, Type, Min, Mode, Max) prellenada a partir
#      del data dict + entries para n_runs y seed.
#   2) AbrirVentanaResultadosMC: muestra histograma de NPV
#      + tornado chart (matplotlib embed) + stats.
#
# Matplotlib es opcional: si no está, se muestra solo
# texto y se confía en el Excel para los gráficos.
# ======================================================

from tkinter import (
    Toplevel,
    StringVar,
    IntVar,
    END,
    BOTH,
    LEFT,
    RIGHT,
    X,
    Y,
    W,
    E,
    N,
    S,
    NSEW,
    HORIZONTAL,
    VERTICAL,
)
from tkinter import ttk
from tkinter import messagebox

from montecarlo import (
    VariableIncierta,
    KIND_PRODUCT_PRICE,
    KIND_RAW_MATERIAL_PRICE,
    KIND_ISBL,
)


# ======================================================
# DETECCIÓN OPCIONAL DE MATPLOTLIB
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
# CONSTRUCCIÓN DE LA LISTA DE VARIABLES POR DEFECTO
# ======================================================

_PCT_DEFAULT = 0.20  # ±20% alrededor del valor base


def _construir_filas_default(data):
    """A partir del dict data (post _construir_data),
    arma la lista de filas para la tabla de la UI.

    Cada fila:
        (kind, indice, nombre, mode, min_default, max_default)
    """

    filas = []

    for i, kp in enumerate(data.get("key_products", [])):
        precio = float(kp.get("price", 0.0))
        filas.append((
            KIND_PRODUCT_PRICE,
            i,
            f"Price: {kp['concept']}",
            precio,
            precio * (1 - _PCT_DEFAULT),
            precio * (1 + _PCT_DEFAULT),
        ))

    for i, rm in enumerate(data.get("raw_materials", [])):
        precio = float(rm.get("price", 0.0))
        filas.append((
            KIND_RAW_MATERIAL_PRICE,
            i,
            f"Price: {rm['concept']}",
            precio,
            precio * (1 - _PCT_DEFAULT),
            precio * (1 + _PCT_DEFAULT),
        ))

    # ISBL ±30% (Towler recomienda para preliminary class 5)
    isbl = float(data.get("ISBL", 0.0))
    filas.append((
        KIND_ISBL,
        0,
        "ISBL",
        isbl,
        isbl * 0.70,
        isbl * 1.30,
    ))

    return filas


# ======================================================
# VENTANA DE CONFIGURACIÓN
# ======================================================

def AbrirVentanaConfigMC(parent, data, on_run):
    """Abre Toplevel para configurar y disparar MC.

    on_run(variables, n_runs, seed) es invocado cuando el
    usuario aprieta Run.
    """

    ventana = Toplevel(parent)
    ventana.title("Monte Carlo Configuration")
    ventana.geometry("780x520+260+80")
    ventana.transient(parent)
    ventana.grab_set()

    # ---- header ----
    ttk.Label(
        ventana,
        text=(
            "Triangular distribution per variable.\n"
            "Mode = expected value (kept from base inputs)."
            "  Edit Min and Max as needed."
        ),
        justify="left",
    ).pack(anchor=W, padx=12, pady=(10, 4))

    # ---- tabla ----
    frame_tabla = ttk.Frame(ventana)
    frame_tabla.pack(fill=BOTH, expand=True, padx=12, pady=4)

    columnas = ("kind", "nombre", "min", "mode", "max")

    tabla = ttk.Treeview(
        frame_tabla,
        columns=columnas,
        show="headings",
        height=12,
    )

    tabla.heading("kind",   text="Kind")
    tabla.heading("nombre", text="Variable")
    tabla.heading("min",    text="Min")
    tabla.heading("mode",   text="Mode")
    tabla.heading("max",    text="Max")

    tabla.column("kind",   width=170, anchor="w")
    tabla.column("nombre", width=230, anchor="w")
    tabla.column("min",    width=110, anchor="center")
    tabla.column("mode",   width=110, anchor="center")
    tabla.column("max",    width=110, anchor="center")

    tabla.pack(side=LEFT, fill=BOTH, expand=True)

    scroll = ttk.Scrollbar(frame_tabla, orient=VERTICAL, command=tabla.yview)
    tabla.configure(yscrollcommand=scroll.set)
    scroll.pack(side=RIGHT, fill=Y)

    # ---- llenar filas ----
    filas_default = _construir_filas_default(data)

    # Guardamos kind+indice como metadatos por iid del tree.
    metadatos = {}

    for fila in filas_default:
        kind, indice, nombre, mode, vmin, vmax = fila

        iid = tabla.insert(
            "", END,
            values=(
                _kind_label(kind),
                nombre,
                f"{vmin:.6g}",
                f"{mode:.6g}",
                f"{vmax:.6g}",
            ),
        )
        metadatos[iid] = (kind, indice, nombre)

    # ---- edición inline (solo min/max; mode queda fijo) ----
    editor = {"widget": None}

    def CerrarEditor():
        w = editor["widget"]
        if w is not None:
            try:
                w.destroy()
            except Exception:
                pass
            editor["widget"] = None

    def EditarCelda(event):
        CerrarEditor()
        item = tabla.identify_row(event.y)
        col = tabla.identify_column(event.x)
        if not item or col not in ("#3", "#5"):
            return

        try:
            x, y, w, h = tabla.bbox(item, col)
        except Exception:
            return

        valor = tabla.set(item, col)
        entry = ttk.Entry(tabla, justify="center")
        entry.insert(0, valor)
        entry.focus()
        entry.place(x=x, y=y, width=w, height=h)
        editor["widget"] = entry

        def Guardar(_=None):
            txt = entry.get().strip()
            try:
                float(txt)
            except ValueError:
                messagebox.showerror("Invalid", "Numeric value required.")
                return
            tabla.set(item, col, txt)
            CerrarEditor()

        entry.bind("<Return>", Guardar)
        entry.bind("<FocusOut>", lambda e: CerrarEditor())

    tabla.bind("<Double-1>", EditarCelda)

    # ---- inputs n_runs y seed ----
    frame_params = ttk.Frame(ventana)
    frame_params.pack(fill=X, padx=12, pady=6)

    ttk.Label(frame_params, text="Iterations:").pack(side=LEFT)

    entry_n = ttk.Entry(frame_params, width=10, justify="right")
    entry_n.insert(0, "5000")
    entry_n.pack(side=LEFT, padx=(4, 18))

    ttk.Label(frame_params, text="Seed (optional):").pack(side=LEFT)

    entry_seed = ttk.Entry(frame_params, width=10, justify="right")
    entry_seed.insert(0, "42")
    entry_seed.pack(side=LEFT, padx=4)

    # ---- botón Run ----
    frame_botones = ttk.Frame(ventana)
    frame_botones.pack(fill=X, padx=12, pady=10)

    def Ejecutar():
        CerrarEditor()

        variables = []
        for iid in tabla.get_children():
            kind, indice, nombre = metadatos[iid]
            vals = tabla.item(iid, "values")
            try:
                vmin  = float(vals[2])
                vmode = float(vals[3])
                vmax  = float(vals[4])
            except ValueError:
                messagebox.showerror("Invalid", f"Numeric values required in {nombre}.")
                return

            if not (vmin <= vmode <= vmax):
                messagebox.showerror(
                    "Invalid range",
                    f"Se requiere Min ≤ Mode ≤ Max en '{nombre}'.\n"
                    f"Got: min={vmin}, mode={vmode}, max={vmax}",
                )
                return

            if vmin == vmax:
                # variable sin incertidumbre: la salteamos
                continue

            variables.append(VariableIncierta(
                kind=kind,
                indice=indice,
                nombre=nombre,
                valor_min=vmin,
                valor_mode=vmode,
                valor_max=vmax,
            ))

        if not variables:
            messagebox.showerror(
                "Nothing to sample",
                "All variables have min=max (no uncertainty)."
            )
            return

        try:
            n_runs = int(entry_n.get())
            if n_runs < 100:
                raise ValueError("n_runs must be ≥ 100")
        except ValueError as e:
            messagebox.showerror("Invalid", f"Iterations: {e}")
            return

        seed_txt = entry_seed.get().strip()
        seed = int(seed_txt) if seed_txt else None

        ventana.destroy()
        on_run(variables, n_runs, seed)

    ttk.Button(frame_botones, text="Run Monte Carlo", command=Ejecutar)\
        .pack(side=RIGHT)

    ttk.Button(frame_botones, text="Cancel", command=ventana.destroy)\
        .pack(side=RIGHT, padx=8)


# ======================================================
# VENTANA DE RESULTADOS
# ======================================================

def AbrirVentanaResultadosMC(parent, resultado):
    """Abre Toplevel con histograma + tornado + stats."""

    mc = resultado["mc"]
    tornado = resultado["tornado"]
    archivo = resultado.get("archivo")
    stats = mc["stats"]

    ventana = Toplevel(parent)
    ventana.title("Monte Carlo Results")
    ventana.geometry("960x640+220+40")
    ventana.transient(parent)

    # ---- frame superior: stats ----
    frame_top = ttk.LabelFrame(ventana, text="Summary")
    frame_top.pack(fill=X, padx=10, pady=(10, 6))

    lineas = [
        f"Runs            : {stats['n']}",
        f"NPV mean ± std  : {stats['npv_mean']:.2f}  ±  {stats['npv_std']:.2f}  MM USD",
        f"NPV P10 / P50 / P90 : "
        f"{stats['npv_p10']:.2f}  /  {stats['npv_p50']:.2f}  /  {stats['npv_p90']:.2f}",
        f"NPV min / max   : {stats['npv_min']:.2f}  /  {stats['npv_max']:.2f}",
        f"P(NPV < 0)      : {stats['p_npv_neg']*100:.1f} %",
    ]

    if stats["irr_p50"] is not None:
        lineas.append(
            f"IRR P10 / P50 / P90 : "
            f"{stats['irr_p10']*100:.2f} %  /  "
            f"{stats['irr_p50']*100:.2f} %  /  "
            f"{stats['irr_p90']*100:.2f} %   "
            f"(valid: {stats['irr_n_valid']}/{stats['n']})"
        )
    else:
        lineas.append("IRR : no calculable (CF sin cambio de signo)")

    if archivo:
        lineas.append("")
        lineas.append(f"Excel updated: {archivo}")

    for ln in lineas:
        ttk.Label(frame_top, text=ln, font=("Consolas", 10))\
            .pack(anchor=W, padx=10, pady=1)

    # ---- frame medio: charts ----
    frame_charts = ttk.Frame(ventana)
    frame_charts.pack(fill=BOTH, expand=True, padx=10, pady=6)

    if not _MATPLOTLIB_OK:
        ttk.Label(
            frame_charts,
            text=(
                "matplotlib no instalado — gráficos solo en el Excel.\n"
                "Para ver histograma/tornado en la UI: pip install matplotlib"
            ),
            foreground="darkred",
            justify="left",
        ).pack(padx=20, pady=20, anchor=W)
        return

    fig = Figure(figsize=(9.4, 4.2), dpi=100)

    # --- subplot 1: histograma NPV ---
    ax1 = fig.add_subplot(1, 2, 1)
    ax1.hist(mc["npvs"], bins=40, color="#4c72b0", edgecolor="white")
    ax1.axvline(stats["npv_p10"], color="orange", linestyle="--", linewidth=1, label="P10")
    ax1.axvline(stats["npv_p50"], color="red",    linestyle="--", linewidth=1, label="P50")
    ax1.axvline(stats["npv_p90"], color="green",  linestyle="--", linewidth=1, label="P90")
    ax1.axvline(0, color="black", linewidth=1)
    ax1.set_title("NPV distribution")
    ax1.set_xlabel("NPV (MM USD)")
    ax1.set_ylabel("Frequency")
    ax1.legend(loc="upper right", fontsize=8)
    ax1.grid(True, alpha=0.3)

    # --- subplot 2: tornado ---
    ax2 = fig.add_subplot(1, 2, 2)
    nombres = [r["nombre"] for r in tornado][::-1]
    deltas_low = [r["delta_low"] for r in tornado][::-1]
    deltas_high = [r["delta_high"] for r in tornado][::-1]

    y = list(range(len(nombres)))
    ax2.barh(y, deltas_low,  color="#c44e52", label="Min")
    ax2.barh(y, deltas_high, color="#55a868", label="Max")
    ax2.set_yticks(y)
    ax2.set_yticklabels(nombres, fontsize=8)
    ax2.axvline(0, color="black", linewidth=1)
    ax2.set_title("Tornado — ΔNPV from base")
    ax2.set_xlabel("ΔNPV (MM USD)")
    ax2.legend(loc="lower right", fontsize=8)
    ax2.grid(True, axis="x", alpha=0.3)

    fig.tight_layout()

    canvas = FigureCanvasTkAgg(fig, master=frame_charts)
    canvas.draw()
    canvas.get_tk_widget().pack(fill=BOTH, expand=True)


# ======================================================
# HELPERS
# ======================================================

def _kind_label(kind):
    return {
        KIND_PRODUCT_PRICE:      "Product price",
        KIND_RAW_MATERIAL_PRICE: "Raw material price",
        KIND_ISBL:               "ISBL Capital",
    }.get(kind, kind)
