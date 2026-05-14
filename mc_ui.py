# ======================================================
# UI MONTE CARLO — Ventanas Tkinter para configuración,
# correlación y visualización.
# ======================================================
# Ventanas:
#   1) AbrirVentanaConfigMC: tabla editable (Variable,
#      Type, Dist, Min, Mode, Max) + entries para n_runs
#      y seed + botón "Correlation matrix..." + Run.
#   2) AbrirVentanaCorrelacion: matriz NxN editable.
#      Diagonal fija en 1.  Off-diagonal simétrica.
#   3) AbrirVentanaResultadosMC: stats + histograma NPV
#      + tornado chart (matplotlib embed).
# ======================================================

from tkinter import (
    Toplevel,
    END,
    BOTH,
    LEFT,
    RIGHT,
    X,
    Y,
    W,
    VERTICAL,
)
from tkinter import ttk
from tkinter import messagebox

import numpy as np

from montecarlo import (
    VariableIncierta,
    KIND_PRODUCT_PRICE,
    KIND_RAW_MATERIAL_PRICE,
    KIND_ISBL,
    DIST_TRIANGULAR,
    DIST_NORMAL,
    DIST_UNIFORM,
)


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
# FILAS POR DEFECTO
# ======================================================

_PCT_DEFAULT = 0.20
_ISBL_PCT = 0.30


def _construir_filas_default(data):
    filas = []
    for i, kp in enumerate(data.get("key_products", [])):
        precio = float(kp.get("price", 0.0))
        filas.append((
            KIND_PRODUCT_PRICE, i, f"Price: {kp['concept']}", precio,
            precio * (1 - _PCT_DEFAULT), precio * (1 + _PCT_DEFAULT),
        ))
    for i, rm in enumerate(data.get("raw_materials", [])):
        precio = float(rm.get("price", 0.0))
        filas.append((
            KIND_RAW_MATERIAL_PRICE, i, f"Price: {rm['concept']}", precio,
            precio * (1 - _PCT_DEFAULT), precio * (1 + _PCT_DEFAULT),
        ))
    isbl = float(data.get("ISBL", 0.0))
    filas.append((
        KIND_ISBL, 0, "ISBL", isbl,
        isbl * (1 - _ISBL_PCT), isbl * (1 + _ISBL_PCT),
    ))
    return filas


def _kind_label(kind):
    return {
        KIND_PRODUCT_PRICE:      "Product price",
        KIND_RAW_MATERIAL_PRICE: "Raw material price",
        KIND_ISBL:               "ISBL Capital",
    }.get(kind, kind)


# ======================================================
# VENTANA DE CONFIGURACIÓN
# ======================================================

def AbrirVentanaConfigMC(parent, data, on_run):
    """Abre Toplevel para configurar y disparar MC.

    on_run(variables, n_runs, seed, correlacion) es invocado
    cuando el usuario aprieta Run.  correlacion es una
    matriz np.ndarray KxK o None.
    """

    ventana = Toplevel(parent)
    ventana.title("Monte Carlo Configuration")
    ventana.geometry("920x560+220+60")
    ventana.transient(parent)
    ventana.grab_set()

    # ---- header ----
    ttk.Label(
        ventana,
        text=(
            "Per-variable distribution and range.\n"
            "  • Triangular: Min ≤ Mode ≤ Max\n"
            "  • Normal:     Mode = mean,  σ = (Max − Min)/4\n"
            "  • Uniform:    Min, Max  (Mode ignored)"
        ),
        justify="left",
    ).pack(anchor=W, padx=12, pady=(10, 4))

    # ---- tabla ----
    frame_tabla = ttk.Frame(ventana)
    frame_tabla.pack(fill=BOTH, expand=True, padx=12, pady=4)

    columnas = ("kind", "nombre", "dist", "min", "mode", "max")

    tabla = ttk.Treeview(
        frame_tabla, columns=columnas, show="headings", height=12,
    )
    tabla.heading("kind",   text="Kind")
    tabla.heading("nombre", text="Variable")
    tabla.heading("dist",   text="Dist")
    tabla.heading("min",    text="Min")
    tabla.heading("mode",   text="Mode")
    tabla.heading("max",    text="Max")
    tabla.column("kind",   width=170, anchor="w")
    tabla.column("nombre", width=220, anchor="w")
    tabla.column("dist",   width=110, anchor="center")
    tabla.column("min",    width=110, anchor="center")
    tabla.column("mode",   width=110, anchor="center")
    tabla.column("max",    width=110, anchor="center")
    tabla.pack(side=LEFT, fill=BOTH, expand=True)

    scroll = ttk.Scrollbar(frame_tabla, orient=VERTICAL, command=tabla.yview)
    tabla.configure(yscrollcommand=scroll.set)
    scroll.pack(side=RIGHT, fill=Y)

    filas_default = _construir_filas_default(data)

    metadatos = {}
    for fila in filas_default:
        kind, indice, nombre, mode, vmin, vmax = fila
        iid = tabla.insert(
            "", END,
            values=(
                _kind_label(kind), nombre, DIST_TRIANGULAR,
                f"{vmin:.6g}", f"{mode:.6g}", f"{vmax:.6g}",
            ),
        )
        metadatos[iid] = (kind, indice, nombre)

    # ---- edición inline ----
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
        if not item:
            return

        editables_num = ("#4", "#6")   # min, max
        editable_combo = "#3"          # dist

        if col not in editables_num and col != editable_combo:
            return

        try:
            x, y, w, h = tabla.bbox(item, col)
        except Exception:
            return

        valor = tabla.set(item, col)

        if col == editable_combo:
            combo = ttk.Combobox(
                tabla,
                values=[DIST_TRIANGULAR, DIST_NORMAL, DIST_UNIFORM],
                state="readonly",
            )
            combo.set(valor)
            combo.place(x=x, y=y, width=w, height=h)
            editor["widget"] = combo

            def GuardarCombo(_=None):
                tabla.set(item, col, combo.get())
                CerrarEditor()

            combo.bind("<<ComboboxSelected>>", GuardarCombo)
            combo.bind("<FocusOut>", lambda e: CerrarEditor())
            combo.focus()
            return

        # numeric
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

    # ---- estado correlation matrix (compartido con sub-ventana) ----
    correlacion_state = {"matrix": None}  # np.ndarray KxK o None

    # ---- frame inferior: n_runs, seed, botones ----
    frame_params = ttk.Frame(ventana)
    frame_params.pack(fill=X, padx=12, pady=(6, 0))

    ttk.Label(frame_params, text="Iterations:").pack(side=LEFT)
    entry_n = ttk.Entry(frame_params, width=10, justify="right")
    entry_n.insert(0, "5000")
    entry_n.pack(side=LEFT, padx=(4, 18))

    ttk.Label(frame_params, text="Seed (optional):").pack(side=LEFT)
    entry_seed = ttk.Entry(frame_params, width=10, justify="right")
    entry_seed.insert(0, "42")
    entry_seed.pack(side=LEFT, padx=4)

    label_corr_status = ttk.Label(
        frame_params,
        text="(no correlation)",
        foreground="gray",
    )
    label_corr_status.pack(side=LEFT, padx=(18, 0))

    def AbrirCorrelation():
        CerrarEditor()
        variables = _leer_variables(tabla, metadatos)
        if variables is None:
            return
        K = len(variables)
        if K < 2:
            messagebox.showinfo(
                "Correlation",
                "At least 2 valid uncertain variables required."
            )
            return

        def OnSave(matrix):
            correlacion_state["matrix"] = matrix
            if matrix is None or np.allclose(matrix, np.eye(K)):
                label_corr_status.config(text="(no correlation)", foreground="gray")
            else:
                label_corr_status.config(text="(correlation set)", foreground="darkgreen")

        AbrirVentanaCorrelacion(
            ventana, variables, correlacion_state["matrix"], OnSave,
        )

    frame_botones = ttk.Frame(ventana)
    frame_botones.pack(fill=X, padx=12, pady=10)

    ttk.Button(frame_botones, text="Correlation matrix…", command=AbrirCorrelation)\
        .pack(side=LEFT)

    def Ejecutar():
        CerrarEditor()
        variables = _leer_variables(tabla, metadatos)
        if variables is None:
            return
        if not variables:
            messagebox.showerror("Nothing to sample", "All variables have min=max.")
            return

        try:
            n_runs = int(entry_n.get())
            if n_runs < 100:
                raise ValueError("must be ≥ 100")
        except ValueError as e:
            messagebox.showerror("Invalid", f"Iterations: {e}")
            return

        seed_txt = entry_seed.get().strip()
        seed = int(seed_txt) if seed_txt else None

        correlacion = correlacion_state["matrix"]
        # Validamos shape contra variables actuales
        if correlacion is not None and correlacion.shape != (len(variables), len(variables)):
            messagebox.showwarning(
                "Correlation reset",
                "La matriz de correlación no coincide con el número actual "
                "de variables. Se ignora."
            )
            correlacion = None

        ventana.destroy()
        on_run(variables, n_runs, seed, correlacion)

    ttk.Button(frame_botones, text="Run Monte Carlo", command=Ejecutar)\
        .pack(side=RIGHT)
    ttk.Button(frame_botones, text="Cancel", command=ventana.destroy)\
        .pack(side=RIGHT, padx=8)


def _leer_variables(tabla, metadatos):
    """Recorre el Treeview y devuelve lista de
    VariableIncierta válidas.  Salta filas con min=max
    (sin incertidumbre).  None si hay error."""
    variables = []
    for iid in tabla.get_children():
        kind, indice, nombre = metadatos[iid]
        vals = tabla.item(iid, "values")
        try:
            dist  = vals[2]
            vmin  = float(vals[3])
            vmode = float(vals[4])
            vmax  = float(vals[5])
        except (ValueError, IndexError):
            messagebox.showerror("Invalid", f"Numeric values required in {nombre}.")
            return None

        if vmin == vmax:
            continue

        try:
            variables.append(VariableIncierta(
                kind=kind, indice=indice, nombre=nombre,
                valor_min=vmin, valor_mode=vmode, valor_max=vmax,
                dist=dist,
            ))
        except ValueError as e:
            messagebox.showerror("Invalid range", f"'{nombre}': {e}")
            return None

    return variables


# ======================================================
# VENTANA DE CORRELACIÓN
# ======================================================

def AbrirVentanaCorrelacion(parent, variables, matrix_actual, on_save):
    """Editor de matriz NxN.

    matrix_actual: np.ndarray KxK o None.  Si None, se
    inicia con la identidad.

    on_save(matrix) recibe la matriz final cuando el user
    aprieta Save.  matrix es np.ndarray KxK; identidad si
    no se editó nada.
    """

    K = len(variables)
    if matrix_actual is None:
        matrix = np.eye(K)
    else:
        matrix = np.array(matrix_actual, dtype=float)

    ventana = Toplevel(parent)
    ventana.title("Correlation matrix")
    ventana.geometry(f"{200 + 95*K}x{220 + 32*K}+260+90")
    ventana.transient(parent)
    ventana.grab_set()

    ttk.Label(
        ventana,
        text=(
            "Edit off-diagonal entries (Pearson ρ).\n"
            "Diagonal is fixed at 1.  Matrix must be positive\n"
            "semi-definite — otherwise Cholesky fails."
        ),
        justify="left",
    ).pack(anchor=W, padx=12, pady=(10, 6))

    frame_grid = ttk.Frame(ventana)
    frame_grid.pack(padx=12, pady=4)

    # header row
    ttk.Label(frame_grid, text="").grid(row=0, column=0)
    for j, v in enumerate(variables):
        ttk.Label(frame_grid, text=v.nombre, font=("TkDefaultFont", 8))\
            .grid(row=0, column=j+1, padx=2, pady=2)

    entries = {}

    def OnChange(i, j, var, event=None):
        try:
            valor = float(var.get())
        except ValueError:
            return
        valor = max(-0.999, min(0.999, valor))
        matrix[i, j] = valor
        matrix[j, i] = valor
        if (j, i) in entries:
            entries[(j, i)].set(f"{valor:.3f}")

    for i, vi in enumerate(variables):
        ttk.Label(frame_grid, text=vi.nombre, font=("TkDefaultFont", 8))\
            .grid(row=i+1, column=0, padx=2, pady=2, sticky="e")

        for j in range(K):
            if i == j:
                lbl = ttk.Label(
                    frame_grid, text="1.000",
                    foreground="gray", anchor="center",
                )
                lbl.grid(row=i+1, column=j+1, padx=2, pady=2)
            else:
                from tkinter import StringVar
                var = StringVar(value=f"{matrix[i,j]:.3f}")
                entry = ttk.Entry(frame_grid, textvariable=var, width=10, justify="center")
                entry.grid(row=i+1, column=j+1, padx=2, pady=2)
                entries[(i, j)] = var
                entry.bind("<FocusOut>", lambda e, i=i, j=j, v=var: OnChange(i, j, v))
                entry.bind("<Return>",   lambda e, i=i, j=j, v=var: OnChange(i, j, v))

    # botones
    frame_botones = ttk.Frame(ventana)
    frame_botones.pack(fill=X, padx=12, pady=10)

    def Reset():
        nonlocal matrix
        matrix = np.eye(K)
        for (i, j), var in entries.items():
            var.set("0.000")

    def Save():
        # validar PSD antes de cerrar
        try:
            np.linalg.cholesky(matrix)
        except np.linalg.LinAlgError:
            messagebox.showerror(
                "Invalid matrix",
                "La matriz no es positive semi-definite. "
                "Reducí algunos coeficientes y volvé a intentar."
            )
            return
        on_save(matrix.copy())
        ventana.destroy()

    ttk.Button(frame_botones, text="Reset (identity)", command=Reset)\
        .pack(side=LEFT)
    ttk.Button(frame_botones, text="Cancel", command=ventana.destroy)\
        .pack(side=RIGHT, padx=8)
    ttk.Button(frame_botones, text="Save", command=Save)\
        .pack(side=RIGHT)


# ======================================================
# VENTANA DE RESULTADOS
# ======================================================

def AbrirVentanaResultadosMC(parent, resultado):
    """Stats + histograma + tornado."""

    mc = resultado["mc"]
    tornado = resultado["tornado"]
    archivo = resultado.get("archivo")
    stats = mc["stats"]

    ventana = Toplevel(parent)
    ventana.title("Monte Carlo Results")
    ventana.geometry("980x660+200+30")
    ventana.transient(parent)

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

    frame_charts = ttk.Frame(ventana)
    frame_charts.pack(fill=BOTH, expand=True, padx=10, pady=6)

    if not _MATPLOTLIB_OK:
        ttk.Label(
            frame_charts,
            text=(
                "matplotlib no instalado — gráficos solo en el Excel.\n"
                "pip install matplotlib para verlos acá."
            ),
            foreground="darkred", justify="left",
        ).pack(padx=20, pady=20, anchor=W)
        return

    fig = Figure(figsize=(9.6, 4.4), dpi=100)

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
