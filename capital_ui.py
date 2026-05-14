# ======================================================
# UI — Estimate ISBL from Equipment List
# ======================================================
# Toplevel modal que permite construir una lista de
# equipos, calcular Cp° por equipo via correlación de
# Turton, sumar y aplicar Lang factor para FCI total,
# despejar ISBL implícito según los % del proyecto.
#
# Al confirmar, escribe el ISBL en df_capital[0,2] de la
# app principal y cierra.
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
    StringVar,
    VERTICAL,
)
from tkinter import ttk
from tkinter import messagebox

import equipment_costs as eq
import cepci


# ======================================================
# CONSTANTES UI
# ======================================================

DEFAULT_YEAR = 2026


# ======================================================
# VENTANA PRINCIPAL
# ======================================================

def AbrirVentanaEstimateISBL(parent, df_capital, on_apply=None):
    """Toplevel para estimar ISBL desde lista de equipos.

    df_capital: DataFrame con la tabla Capital Costs del
        proyecto.  Lo necesitamos para:
          (a) leer los % de OSBL/ENG/CONT/WC (filas 1..4)
              y despejar ISBL implícito.
          (b) escribir el ISBL estimado en fila 0, col 2,
              al apretar "Use as ISBL".

    on_apply(): callback opcional invocado después de
        escribir el nuevo ISBL en df_capital (para
        refrescar la UI de proyecto).
    """

    ventana = Toplevel(parent)
    ventana.title("Estimate ISBL from Equipment List — Turton/Lang")
    ventana.geometry("1080x620+200+40")
    ventana.transient(parent)
    ventana.grab_set()

    # ---- header ----
    ttk.Label(
        ventana,
        text=(
            "Build the equipment list, set size S for each item, then read\n"
            "Cp° (Turton Apx A correlation) and FCI (Lang factor)."
        ),
        justify="left",
    ).pack(anchor=W, padx=12, pady=(10, 4))

    # ---- frame parámetros globales ----
    frame_global = ttk.Frame(ventana)
    frame_global.pack(fill=X, padx=12, pady=4)

    ttk.Label(frame_global, text="Plant type:").pack(side=LEFT)
    combo_plant = ttk.Combobox(
        frame_global,
        values=list(eq.LANG_FACTORS.keys()),
        state="readonly",
        width=24,
    )
    combo_plant.set(eq.LANG_DEFAULT)
    combo_plant.pack(side=LEFT, padx=(4, 16))

    ttk.Label(frame_global, text="Target year (CEPCI):").pack(side=LEFT)
    entry_year = ttk.Entry(frame_global, width=8, justify="right")
    entry_year.insert(0, str(DEFAULT_YEAR))
    entry_year.pack(side=LEFT, padx=4)

    # ---- tabla ----
    frame_tabla = ttk.Frame(ventana)
    frame_tabla.pack(fill=BOTH, expand=True, padx=12, pady=6)

    cols = ("equipment", "S", "S_unit", "n", "cp_unit", "cp_total", "warn")
    tabla = ttk.Treeview(frame_tabla, columns=cols, show="headings", height=14)
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

    def _año_target():
        try:
            return int(entry_year.get())
        except ValueError:
            return DEFAULT_YEAR

    def _recompute():
        """Recalcula Cp°/total para cada fila + FCI global."""
        year = _año_target()
        equipos_lista = []

        for iid in tabla.get_children():
            vals = list(tabla.item(iid, "values"))
            nombre = vals[0]
            try:
                S = float(vals[1])
                n = int(vals[3])
            except (ValueError, TypeError):
                vals[4] = ""
                vals[5] = ""
                vals[6] = "?"
                tabla.item(iid, values=vals)
                continue

            if nombre not in eq.EQUIPMENT_DATA or S <= 0 or n <= 0:
                vals[4] = ""
                vals[5] = ""
                vals[6] = "?"
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

        # FCI global
        plant_type = combo_plant.get()
        try:
            resultado = eq.lang_fci(
                equipos_lista,
                plant_type=plant_type,
                year_target=year,
            )
            sum_Cp = resultado["sum_Cp"]
            FCI = resultado["FCI"]
            FCI_mm = resultado["FCI_MMUSD"]
            f_L = resultado["lang_factor"]
            warnings = resultado["warnings"]
        except ValueError as e:
            messagebox.showerror("Plant type error", str(e))
            return

        # ISBL implícito a partir de los % del proyecto
        try:
            OSBL_pct = _pct(df_capital.iloc[1, 2])
            ENG_pct  = _pct(df_capital.iloc[2, 2])
            CONT_pct = _pct(df_capital.iloc[3, 2])
            isbl_mm = eq.isbl_implicito(
                FCI_mm, OSBL_pct, ENG_pct, CONT_pct,
            )
            label_isbl.config(text=f"ISBL implied: {isbl_mm:>10.2f} MM USD")
        except Exception:
            label_isbl.config(text="ISBL implied: (need OSBL/ENG/CONT %)")

        label_sumcp.config(text=f"Σ Cp°: ${sum_Cp:>14,.0f}")
        label_fci.config(text=f"FCI = {f_L:.2f} × Σ Cp° = {FCI_mm:>9.2f} MM USD")

        if warnings:
            label_warn.config(
                text=f"{len(warnings)} warning(s) — hover una fila con ⚠ para ver",
                foreground="darkorange",
            )
        else:
            label_warn.config(text="", foreground="darkorange")

        return FCI_mm

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

        # equipment (#1) = combobox; S (#2) y n (#4) = entry numérico
        if col not in ("#1", "#2", "#4"):
            return

        try:
            x, y, w, h = tabla.bbox(item, col)
        except Exception:
            return

        valor = tabla.set(item, col)

        if col == "#1":
            # combobox de equipos
            combo = ttk.Combobox(tabla, values=nombres_equipos, state="readonly")
            combo.set(valor if valor in nombres_equipos else nombres_equipos[0])
            combo.place(x=x, y=y, width=max(w, 220), height=h)
            editor["widget"] = combo

            def Guardar(_=None):
                nuevo = combo.get()
                tabla.set(item, col, nuevo)
                # update unit
                if nuevo in eq.EQUIPMENT_DATA:
                    tabla.set(item, "S_unit", eq.EQUIPMENT_DATA[nuevo]["S_unit"])
                CerrarEditor()
                _recompute()

            combo.bind("<<ComboboxSelected>>", Guardar)
            combo.bind("<FocusOut>", lambda e: CerrarEditor())
            combo.focus()
            return

        # numeric
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
    frame_tools.pack(fill=X, padx=12, pady=(0, 6))

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
        sel = tabla.selection()
        for iid in sel:
            tabla.delete(iid)
        _recompute()

    def ClearAll():
        CerrarEditor()
        for iid in tabla.get_children():
            tabla.delete(iid)
        _recompute()

    ttk.Button(frame_tools, text="Add row",       command=AddRow).pack(side=LEFT)
    ttk.Button(frame_tools, text="Remove",        command=RemoveRow).pack(side=LEFT, padx=4)
    ttk.Button(frame_tools, text="Clear",         command=ClearAll).pack(side=LEFT, padx=4)

    # year change → recompute
    entry_year.bind("<FocusOut>", lambda e: _recompute())
    entry_year.bind("<Return>",   lambda e: _recompute())
    combo_plant.bind("<<ComboboxSelected>>", lambda e: _recompute())

    # ---- frame resumen ----
    frame_resumen = ttk.LabelFrame(ventana, text="Summary")
    frame_resumen.pack(fill=X, padx=12, pady=4)

    label_sumcp = ttk.Label(frame_resumen, text="Σ Cp°: $0",
                            font=("Consolas", 10))
    label_sumcp.pack(anchor=W, padx=8, pady=2)

    label_fci = ttk.Label(frame_resumen, text="FCI = 4.74 × Σ Cp° = 0.00 MM USD",
                          font=("Consolas", 10))
    label_fci.pack(anchor=W, padx=8, pady=2)

    label_isbl = ttk.Label(frame_resumen, text="ISBL implied: (need OSBL/ENG/CONT %)",
                           font=("Consolas", 10))
    label_isbl.pack(anchor=W, padx=8, pady=2)

    label_warn = ttk.Label(frame_resumen, text="", foreground="darkorange")
    label_warn.pack(anchor=W, padx=8, pady=2)

    # ---- bottom buttons ----
    frame_bottom = ttk.Frame(ventana)
    frame_bottom.pack(fill=X, padx=12, pady=10)

    def ApplyISBL():
        CerrarEditor()
        fci_mm = _recompute()
        if not fci_mm or fci_mm <= 0:
            messagebox.showerror("Nothing to apply", "FCI is zero or invalid.")
            return

        try:
            OSBL_pct = _pct(df_capital.iloc[1, 2])
            ENG_pct  = _pct(df_capital.iloc[2, 2])
            CONT_pct = _pct(df_capital.iloc[3, 2])
        except Exception as e:
            messagebox.showerror(
                "OSBL/ENG/CONT missing",
                f"Need OSBL/ENG/CONT% loaded in Capital Costs first.\n\n{e}",
            )
            return

        isbl_mm = eq.isbl_implicito(fci_mm, OSBL_pct, ENG_pct, CONT_pct)

        if not messagebox.askyesno(
            "Apply ISBL",
            f"Apply ISBL = {isbl_mm:.2f} MM USD to the project?\n\n"
            f"(FCI estimated = {fci_mm:.2f} MM USD;\n"
            f"backed out via OSBL={OSBL_pct*100:.1f}%, "
            f"ENG={ENG_pct*100:.1f}%, CONT={CONT_pct*100:.1f}%)"
        ):
            return

        df_capital.iat[0, 2] = float(isbl_mm)
        if on_apply is not None:
            on_apply()
        ventana.destroy()

    ttk.Button(frame_bottom, text="Use as ISBL in analysis", command=ApplyISBL)\
        .pack(side=RIGHT)
    ttk.Button(frame_bottom, text="Close", command=ventana.destroy)\
        .pack(side=RIGHT, padx=8)

    # arrancamos con una fila para que se vea
    AddRow()


# ======================================================
# HELPERS
# ======================================================

def _pct(valor):
    """Convierte 30 (porcentaje) a 0.30; o deja la fracción
    si ya está en [0,1].  Igual que pipeline._pct pero
    copiado para no introducir dependencias raras."""
    valor = float(valor)
    return valor / 100.0 if valor > 1.0 else valor
