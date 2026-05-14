# ======================================================
# UI — Estimate ISBL from Equipment List
# ======================================================
# Toplevel independiente para construir una lista de
# equipos y obtener FCI vía Lang + ISBL implícito vía los
# porcentajes OSBL/ENG/CONT (que se editan acá mismo).
#
# La ventana NO necesita un proyecto cargado para abrir.
# Si querés inyectar el ISBL resultante al análisis,
# entonces sí necesitás haber importado el proyecto.
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
from tkinter import scrolledtext

import equipment_costs as eq


# ======================================================
# DEFAULTS (cuando no hay proyecto cargado)
# ======================================================

DEFAULT_YEAR = 2026
DEFAULT_OSBL_PCT = 30.0   # Towler typical
DEFAULT_ENG_PCT  = 10.0
DEFAULT_CONT_PCT = 10.0


# ======================================================
# VENTANA PRINCIPAL
# ======================================================

def AbrirVentanaEstimateISBL(parent, df_capital=None, on_apply=None):
    """Ventana de estimación de capital.

    df_capital: opcional.  Si está dado y tiene los % de
        OSBL/ENG/CONT, los carga como defaults.  Si está
        vacío o es None, usa defaults de Towler.

    on_apply(): callback opcional para cuando el usuario
        aprieta 'Use as ISBL in analysis'.  Requiere
        df_capital no vacío.
    """

    ventana = Toplevel(parent)
    ventana.title("Estimate ISBL from Equipment List — Turton / Lang")
    ventana.geometry("1120x720+180+30")
    ventana.transient(parent)
    ventana.grab_set()

    proyecto_cargado = (df_capital is not None) and (not df_capital.empty)

    # ---- header ----
    ttk.Label(
        ventana,
        text=(
            "1) Build the equipment list  (Add row → pick type, set size S and number of units).\n"
            "2) Read FCI = Lang factor × Σ Cp°.   3) Back-out ISBL using OSBL/ENG/CONT %.\n"
            "Out-of-range items are flagged ⚠ — see the warnings panel below."
        ),
        justify="left",
    ).pack(anchor=W, padx=12, pady=(10, 6))

    # ---- frame parámetros globales (grid) ----
    frame_global = ttk.LabelFrame(ventana, text="Global parameters")
    frame_global.pack(fill=X, padx=12, pady=4)

    # plant type
    ttk.Label(frame_global, text="Plant type:").grid(row=0, column=0, padx=6, pady=4, sticky="w")
    combo_plant = ttk.Combobox(
        frame_global,
        values=list(eq.LANG_FACTORS.keys()),
        state="readonly",
        width=22,
    )
    combo_plant.set(eq.LANG_DEFAULT)
    combo_plant.grid(row=0, column=1, padx=4, pady=4, sticky="w")

    # target year
    ttk.Label(frame_global, text="Target year (CEPCI):").grid(row=0, column=2, padx=(20, 6), pady=4, sticky="w")
    entry_year = ttk.Entry(frame_global, width=7, justify="right")
    entry_year.insert(0, str(DEFAULT_YEAR))
    entry_year.grid(row=0, column=3, padx=4, pady=4, sticky="w")

    # OSBL/ENG/CONT — defaults dependen de si hay proyecto
    osbl_def = _leer_pct(df_capital, 1, DEFAULT_OSBL_PCT) if proyecto_cargado else DEFAULT_OSBL_PCT
    eng_def  = _leer_pct(df_capital, 2, DEFAULT_ENG_PCT)  if proyecto_cargado else DEFAULT_ENG_PCT
    cont_def = _leer_pct(df_capital, 3, DEFAULT_CONT_PCT) if proyecto_cargado else DEFAULT_CONT_PCT

    ttk.Label(frame_global, text="OSBL %:").grid(row=1, column=0, padx=6, pady=4, sticky="w")
    entry_osbl = ttk.Entry(frame_global, width=8, justify="right")
    entry_osbl.insert(0, f"{osbl_def:g}")
    entry_osbl.grid(row=1, column=1, padx=4, pady=4, sticky="w")

    ttk.Label(frame_global, text="Engineering %:").grid(row=1, column=2, padx=(20, 6), pady=4, sticky="w")
    entry_eng = ttk.Entry(frame_global, width=8, justify="right")
    entry_eng.insert(0, f"{eng_def:g}")
    entry_eng.grid(row=1, column=3, padx=4, pady=4, sticky="w")

    ttk.Label(frame_global, text="Contingency %:").grid(row=1, column=4, padx=(20, 6), pady=4, sticky="w")
    entry_cont = ttk.Entry(frame_global, width=8, justify="right")
    entry_cont.insert(0, f"{cont_def:g}")
    entry_cont.grid(row=1, column=5, padx=4, pady=4, sticky="w")

    if not proyecto_cargado:
        ttk.Label(
            frame_global,
            text=(
                "No project loaded — using Towler defaults for OSBL/ENG/CONT. "
                "'Use as ISBL' will be disabled."
            ),
            foreground="darkorange",
        ).grid(row=2, column=0, columnspan=6, padx=6, pady=(2, 4), sticky="w")

    # ---- tabla ----
    frame_tabla = ttk.LabelFrame(ventana, text="Equipment list")
    frame_tabla.pack(fill=BOTH, expand=True, padx=12, pady=6)

    cols = ("equipment", "S", "S_unit", "n", "cp_unit", "cp_total", "warn")
    tabla = ttk.Treeview(frame_tabla, columns=cols, show="headings", height=10)
    tabla.heading("equipment", text="Equipment")
    tabla.heading("S",         text="Size (S)")
    tabla.heading("S_unit",    text="Unit")
    tabla.heading("n",         text="N°")
    tabla.heading("cp_unit",   text="Cp°/unit (USD)")
    tabla.heading("cp_total",  text="Cp° total (USD)")
    tabla.heading("warn",      text="!")

    tabla.column("equipment", width=240, anchor="w")
    tabla.column("S",         width=110, anchor="center")
    tabla.column("S_unit",    width=70,  anchor="center")
    tabla.column("n",         width=60,  anchor="center")
    tabla.column("cp_unit",   width=140, anchor="e")
    tabla.column("cp_total",  width=160, anchor="e")
    tabla.column("warn",      width=40,  anchor="center")

    tabla.pack(side=LEFT, fill=BOTH, expand=True)
    scroll = ttk.Scrollbar(frame_tabla, orient=VERTICAL, command=tabla.yview)
    tabla.configure(yscrollcommand=scroll.set)
    scroll.pack(side=RIGHT, fill=Y)

    # ---- estado ----
    nombres_equipos = eq.listar_equipos()

    # ---- helpers ----

    def _int_or_default(entry, default):
        try:
            return int(entry.get())
        except ValueError:
            return default

    def _float_or_default(entry, default):
        try:
            return float(entry.get())
        except ValueError:
            return default

    def _pct_get(entry, default):
        valor = _float_or_default(entry, default)
        return valor / 100.0 if valor > 1.0 else valor

    def _recompute():
        """Recalcula Cp°/total para cada fila + FCI global +
        ISBL implícito.  Devuelve (FCI_mm, ISBL_mm) o
        (0, 0) si no hay nada."""

        year = _int_or_default(entry_year, DEFAULT_YEAR)
        equipos_lista = []

        for iid in tabla.get_children():
            vals = list(tabla.item(iid, "values"))
            nombre = vals[0]
            try:
                S = float(vals[1])
                n = int(vals[3])
            except (ValueError, TypeError):
                vals[4] = ""; vals[5] = ""; vals[6] = "?"
                tabla.item(iid, values=vals)
                continue

            if nombre not in eq.EQUIPMENT_DATA or S <= 0 or n <= 0:
                vals[4] = ""; vals[5] = ""; vals[6] = "?"
                tabla.item(iid, values=vals)
                continue

            try:
                r = eq.purchased_cost(nombre, S, year_target=year)
            except ValueError:
                vals[4] = ""; vals[5] = ""; vals[6] = "?"
                tabla.item(iid, values=vals)
                continue

            cp_u = r["Cp_target"]
            cp_t = cp_u * n
            vals[2] = r["S_unit"]
            vals[4] = f"{cp_u:,.0f}"
            vals[5] = f"{cp_t:,.0f}"
            vals[6] = "⚠" if r["fuera_rango"] else ""
            tabla.item(iid, values=vals)

            equipos_lista.append({"nombre": nombre, "S": S, "n": n})

        plant_type = combo_plant.get()
        try:
            resultado = eq.lang_fci(
                equipos_lista,
                plant_type=plant_type,
                year_target=year,
            )
        except ValueError as e:
            messagebox.showerror("Plant type error", str(e))
            return 0.0, 0.0

        OSBL_pct = _pct_get(entry_osbl, DEFAULT_OSBL_PCT)
        ENG_pct  = _pct_get(entry_eng,  DEFAULT_ENG_PCT)
        CONT_pct = _pct_get(entry_cont, DEFAULT_CONT_PCT)
        isbl_mm  = eq.isbl_implicito(
            resultado["FCI_MMUSD"], OSBL_pct, ENG_pct, CONT_pct,
        )

        label_sumcp.config(text=f"Σ Cp°       :  $ {resultado['sum_Cp']:>14,.0f}")
        label_fci.config(
            text=f"FCI Lang    :  {resultado['lang_factor']:.2f} × Σ Cp°  =  "
                 f"{resultado['FCI_MMUSD']:>10.2f} MM USD"
        )
        label_isbl.config(
            text=f"ISBL implied:  FCI / [(1+OSBL%)·(1+ENG%+CONT%)]  =  "
                 f"{isbl_mm:>10.2f} MM USD"
        )

        # --- warnings expandidos ---
        text_warnings.config(state="normal")
        text_warnings.delete("1.0", END)
        if resultado["warnings"]:
            text_warnings.insert(END, _explicar_warnings(resultado["warnings"]))
        else:
            text_warnings.insert(END, "No warnings — all equipment within Turton's correlation range.")
        text_warnings.config(state="disabled")

        return resultado["FCI_MMUSD"], isbl_mm

    # ---- edición inline (combobox equipo / numeric S y n) ----
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
        if col not in ("#1", "#2", "#4"):
            return

        try:
            x, y, w, h = tabla.bbox(item, col)
        except Exception:
            return

        valor = tabla.set(item, col)

        if col == "#1":
            combo = ttk.Combobox(tabla, values=nombres_equipos, state="readonly")
            combo.set(valor if valor in nombres_equipos else nombres_equipos[0])
            combo.place(x=x, y=y, width=max(w, 220), height=h)
            editor["widget"] = combo

            def Guardar(_=None):
                nuevo = combo.get()
                tabla.set(item, col, nuevo)
                if nuevo in eq.EQUIPMENT_DATA:
                    tabla.set(item, "S_unit", eq.EQUIPMENT_DATA[nuevo]["S_unit"])
                CerrarEditor()
                _recompute()

            combo.bind("<<ComboboxSelected>>", Guardar)
            combo.bind("<FocusOut>", lambda e: CerrarEditor())
            combo.focus()
            return

        entry = ttk.Entry(tabla, justify="center")
        entry.insert(0, valor)
        entry.place(x=x, y=y, width=w, height=h)
        editor["widget"] = entry
        entry.focus()

        def GuardarNumero(_=None):
            txt = entry.get().strip()
            try:
                if col == "#4":
                    int(txt)
                else:
                    float(txt)
            except ValueError:
                messagebox.showerror("Invalid", "Numeric value required.")
                return
            tabla.set(item, col, txt)
            CerrarEditor()
            _recompute()

        entry.bind("<Return>", GuardarNumero)
        entry.bind("<FocusOut>", lambda e: CerrarEditor())

    tabla.bind("<Double-1>", EditarCelda)

    # ---- frame botones tabla ----
    frame_tools = ttk.Frame(ventana)
    frame_tools.pack(fill=X, padx=12, pady=(0, 4))

    def AddRow():
        CerrarEditor()
        nombre = nombres_equipos[0]
        spec = eq.EQUIPMENT_DATA[nombre]
        S_default = (spec["S_min"] + spec["S_max"]) / 2
        tabla.insert("", END, values=(
            nombre,
            f"{S_default:g}",
            spec["S_unit"],
            "1",
            "", "", "",
        ))
        _recompute()

    def RemoveRow():
        CerrarEditor()
        for iid in tabla.selection():
            tabla.delete(iid)
        _recompute()

    def ClearAll():
        CerrarEditor()
        for iid in tabla.get_children():
            tabla.delete(iid)
        _recompute()

    ttk.Button(frame_tools, text="Add row", command=AddRow).pack(side=LEFT)
    ttk.Button(frame_tools, text="Remove",  command=RemoveRow).pack(side=LEFT, padx=4)
    ttk.Button(frame_tools, text="Clear",   command=ClearAll).pack(side=LEFT, padx=4)

    # global params → recompute
    for w in (entry_year, entry_osbl, entry_eng, entry_cont):
        w.bind("<FocusOut>", lambda e: _recompute())
        w.bind("<Return>",   lambda e: _recompute())
    combo_plant.bind("<<ComboboxSelected>>", lambda e: _recompute())

    # ---- frame resumen ----
    frame_resumen = ttk.LabelFrame(ventana, text="Summary")
    frame_resumen.pack(fill=X, padx=12, pady=4)

    label_sumcp = ttk.Label(frame_resumen, text="Σ Cp°       :  $ 0",
                            font=("Consolas", 10))
    label_sumcp.pack(anchor=W, padx=8, pady=1)

    label_fci = ttk.Label(frame_resumen, text="FCI Lang    :  0.00 MM USD",
                          font=("Consolas", 10))
    label_fci.pack(anchor=W, padx=8, pady=1)

    label_isbl = ttk.Label(frame_resumen, text="ISBL implied:  0.00 MM USD",
                           font=("Consolas", 10))
    label_isbl.pack(anchor=W, padx=8, pady=1)

    # ---- frame warnings ----
    frame_warn = ttk.LabelFrame(ventana, text="Warnings")
    frame_warn.pack(fill=X, padx=12, pady=4)

    text_warnings = scrolledtext.ScrolledText(
        frame_warn, height=6, font=("Consolas", 9),
        wrap="word", state="disabled",
    )
    text_warnings.pack(fill=X, padx=4, pady=4)

    # ---- bottom buttons ----
    frame_bottom = ttk.Frame(ventana)
    frame_bottom.pack(fill=X, padx=12, pady=10)

    def ApplyISBL():
        CerrarEditor()
        if df_capital is None or df_capital.empty:
            messagebox.showinfo(
                "No project loaded",
                "Para aplicar el ISBL al análisis necesitás importar un\n"
                "proyecto primero (File > Import Project).\n\n"
                "Esta ventana se puede usar igual para calcular el FCI."
            )
            return

        fci_mm, isbl_mm = _recompute()
        if not fci_mm or fci_mm <= 0:
            messagebox.showerror("Nothing to apply", "FCI is zero or invalid.")
            return

        if not messagebox.askyesno(
            "Apply ISBL",
            f"Apply ISBL = {isbl_mm:.2f} MM USD to the project?\n\n"
            f"(FCI Lang   = {fci_mm:.2f} MM USD\n"
            f" backed out with OSBL={entry_osbl.get()}%, "
            f"ENG={entry_eng.get()}%, CONT={entry_cont.get()}%)"
        ):
            return

        df_capital.iat[0, 2] = float(isbl_mm)
        if on_apply is not None:
            on_apply()
        ventana.destroy()

    boton_apply = ttk.Button(
        frame_bottom,
        text="Use as ISBL in analysis",
        command=ApplyISBL,
    )
    boton_apply.pack(side=RIGHT)
    if not proyecto_cargado:
        boton_apply.config(state="disabled")

    ttk.Button(frame_bottom, text="Close", command=ventana.destroy)\
        .pack(side=RIGHT, padx=8)

    # arrancamos vacío — el usuario va agregando
    _recompute()


# ======================================================
# HELPERS
# ======================================================

def _leer_pct(df, fila, default):
    """Lee valor de df_capital[fila, 2] e interpreta como %."""
    try:
        v = float(df.iloc[fila, 2])
        return v if v > 1.0 else v * 100.0
    except Exception:
        return default


def _explicar_warnings(warnings):
    """Convierte la lista cruda de warnings de
    equipment_costs.lang_fci en un texto explicado
    multi-línea.

    Las dos clases principales:
      - "<equipo>: S=<x> <unit> fuera de rango [a, b]"
        → explica qué significa
      - "<equipo>: <error>"  (otros)
    """
    cabeza = (
        "Some equipment is OUTSIDE the validity range of Turton's\n"
        "Apx A correlation.  The Cp° is computed by EXTRAPOLATION\n"
        "and can be wildly wrong.  Either:\n"
        "  (a) use a different equipment category that covers your\n"
        "      size (e.g. a fan of 1725 m³/s is really a compressor),\n"
        "  (b) split into multiple units in parallel (set N° > 1\n"
        "      with each unit inside the range), or\n"
        "  (c) leave it as is, but treat the FCI estimate as an\n"
        "      educated guess and stress-test it via Monte Carlo.\n"
        "\n"
    )

    detalles = []
    for w in warnings:
        if "fuera de rango" in w:
            detalles.append(f"  ⚠ {w}")
        else:
            detalles.append(f"  ✗ {w}")

    return cabeza + "\n".join(detalles)
