import os
import subprocess
import sys
import traceback

from tkinter import *
from tkinter import ttk
from tkinter import scrolledtext
from tkinter import filedialog, messagebox
import pandas as pd

from units import (

    ValidarUnidadesDataframe,

    NormalizarFlowrate,

    NormalizarPrecio,

    TIME_ALIASES,

    ConvertirFlowrateVisible,

    ObtenerTipoUnidad,

)

from pipeline import ejecutar_analisis, ejecutar_montecarlo, construir_data_y_params

from mc_ui import AbrirVentanaConfigMC

from capital_ui import AbrirVentanaEstimateISBL

from flowsheet_ui import AbrirVentanaFlowsheet

from results_ui import AbrirDashboard

from tooltip import Tooltip, adjuntar_tooltips
import templates

# ======================================================
# ENGINE CENTRAL (SINGLE SOURCE OF TRUTH)
# ======================================================

class ModelEngine:
    """Single source of truth para el dataset variable.

    Mantiene dos vistas sincronizadas:
        df_variable  — formato visible al usuario (unidades
                       arbitrarias por fila).
        df_internal  — todo normalizado a base SI por año
                       (Flowrate SI, Price SI, Time SI).

    load() reemplaza el dataset; update() modifica una
    celda; ambas disparan recalculate() que reconstruye
    df_internal desde df_variable usando units.NormalizarX.
    """

    def __init__(self):
        self.df_variable = pd.DataFrame()
        self.df_internal = pd.DataFrame()

    def load(self, df):
        """Reemplaza el dataset y recalcula df_internal."""
        self.df_variable = df.copy()
        self.recalculate()

    def update(self, idx, col, value):
        """Modifica una celda y recalcula df_internal."""
        self.df_variable.at[idx, col] = value
        self.recalculate()

    def recalculate(self):
        """Reconstruye df_internal a partir de df_variable
        normalizando flowrates, precios y time basis."""

        flowrates = []
        prices = []
        times = []

        for _, row in self.df_variable.iterrows():

            flow_si = NormalizarFlowrate(
                flowrate=row["flowrate"],
                unidad=row["units"],
                tiempo=row["time basis"]
            )

            price_si = NormalizarPrecio(
                price=row["price usd/units"],
                unidad=row["units"]
            )

            time_si = TIME_ALIASES[
                str(row["time basis"]).strip().lower()
            ]

            flowrates.append(flow_si)
            prices.append(price_si)
            times.append(time_si)

        self.df_internal = pd.DataFrame({

            "Variable": self.df_variable["variable operating costs"],
            "Flowrate SI": flowrates,
            "Price SI": prices,
            "Time SI": times,
            "Stream": self.df_variable["stream"]

        })


# ======================================================
# ENGINE GLOBAL + DATAFRAMES DE PROYECTO
# ======================================================

engine = ModelEngine()

df_capital = pd.DataFrame()
df_fixed = pd.DataFrame()
df_variable = pd.DataFrame()
df_equipment = pd.DataFrame()    # equipos del PFD (si el xlsx viene del flowsheet)
df_streams   = pd.DataFrame()    # corrientes del PFD: masa, T, P, composición wt%
                                  # (si el xlsx viene del flowsheet)


# ======================================================
# VENTANA PRINCIPAL
# ======================================================

raiz = Tk()

raiz.title("ANA")
raiz.geometry('720x620+210+20')
raiz.resizable(0, 0)

# ======================================================
# VARIABLES TKINTER
# ======================================================

opcionDepre = IntVar(value=0)
opcionMACRS = IntVar(value=0)
VeSensibilidad = IntVar()

# ======================================================
# FUNCIONES
# ======================================================

def VentanaDocumentation():
    pass

# ------------------------------------------------------

def VentanaAbout():

    messagebox.showinfo(
        "About ANA",
        "ANA\nEconomic Analysis Software"
    )

# ======================================================
# NUEVO PROYECTO (sin Excel)
# ======================================================

def NuevoProyecto():
    """Inicializa los 3 DataFrames con templates default
    (valores típicos de Turton).  El user después edita
    todo desde Data > View Project Data, sin necesidad de
    ningún archivo Excel."""

    global df_capital, df_fixed, df_variable

    if not df_capital.empty or not df_fixed.empty or not df_variable.empty:
        if not messagebox.askyesno(
            "New Project",
            "Already have a project loaded. Discard it and start fresh?"
        ):
            return

    df_capital = templates.template_capital()
    df_fixed   = templates.template_fixed()
    df_variable = templates.template_variable()

    engine.load(df_variable)

    _limpiar_frame_inputs()
    _actualizar_status_proyecto("New project (templates)")

    ConsolaResultados.config(state="normal")
    ConsolaResultados.delete(1.0, END)
    ConsolaResultados.insert(
        END,
        "New project created with Turton defaults.\n"
        "Inputs cleared — fill them and press Solve.\n"
    )
    ConsolaResultados.config(state="disabled")

    messagebox.showinfo(
        "New Project",
        "Project initialized with typical values.\n\n"
        "Edit Capital, Fixed and Variable Operating Costs\n"
        "from the 'Data > View Project Data' menu."
    )


def _limpiar_frame_inputs():
    """Resetea el frame Input Data a defaults sensatos
    (no a vacío) para que el usuario pueda apretar Solve
    enseguida.  Se llama al hacer 'New Project'."""

    # Entries con valores por defecto razonables
    defaults = (
        (EntryFC,           "1.0"),    # FOC schedule = 100% cada año
        (EntryVCOP,         "1.0"),    # VOC schedule = 100% cada año
        (EntryProjLife,     "10"),     # 10 años (Turton típico)
        (EntryTaxeRate,     "29.5"),   # Perú IR tercera categoría
        (EntryDiscountRate, "12"),     # 12% típico project finance
        (EntryDLineal,      "10"),     # SL igual a la vida del proyecto
    )
    for entry, val in defaults:
        entry.delete(0, END)
        entry.insert(0, val)

    # CEPCI: año actual
    for entry, val in ((EntryCEPCIBasis, "2026"), (EntryCEPCITarget, "2026")):
        entry.delete(0, END)
        entry.insert(0, val)

    # Combobox de unidades
    LabelFCuni.set("Fraction")
    LabelVCOPuni.set("Fraction")
    LabelProjLifeUni.set("Years")
    LabelTaxRateUni.set("Percentage")
    LabelDiscountRateUni.set("Percentage")
    LabelDLinealUni.set("Years")

    # Toggles
    VeSensibilidad.set(0)
    opcionDepre.set(0)   # Straight-line
    opcionMACRS.set(0)
    ActualizarDepreciacion()

    # Botones de reporte se deshabilitan hasta que haya Solve
    BotonReporteEconomico.config(state="disabled")
    BotonReporteSensibilidad.config(state="disabled")
    ultimo_reporte["resultado"] = None
    ultimo_reporte["resultado_mc"] = None
    ultimo_reporte["path"] = None


# ======================================================
# STATUS DEL PROYECTO (label visible)
# ======================================================

def _actualizar_status_proyecto(texto):
    """Actualiza el título del LabelFrame de inputs con el
    estado del proyecto.  ● = cargado, ○ = vacío."""
    if "ContornoDatos" in globals():
        if texto:
            ContornoDatos.config(text=f"Input Data  —  ●  {texto}")
        else:
            ContornoDatos.config(text="Input Data  —  ○  No project loaded")


# ======================================================
# IMPORTAR PROYECTO
# ======================================================

def ImportarProyecto(archivo=None):
    """Importa un Excel de proyecto con 3 secciones:
        Capital Costs           (cols A,B,C)
        Fixed Operating Costs   (cols E,F,G)
        Variable Operating Costs (cols I..N)

    Si el xlsx fue generado por el flowsheet editor también
    trae una pestaña adicional 'Equipment' con la lista de
    equipos del PFD — se carga en df_equipment para mostrar
    en View / edit data.

    Valida unidades en Variable Costs; si hay errores,
    muestra messagebox detallado y aborta el load del
    engine.  Migra streams en formato letra (A..F) a
    nombres legibles (Key Products, etc.).

    Si `archivo` es None, abre file dialog.  Si se pasa
    explícitamente (caso CLI o launcher), lo usa directo.
    """

    global df_capital
    global df_fixed
    global df_variable
    global df_equipment
    global df_streams

    if archivo is None:
        archivo = filedialog.askopenfilename(
            title="Import Project",
            filetypes=[
                ("Excel files", "*.xlsx *.xls")
            ]
        )

    if not archivo:
        return

    try:

        # ==================================================
        # LEER EXCEL
        # ==================================================

        df_raw = pd.read_excel(
            archivo,
            header=None
        )

        # ==================================================
        # CAPITAL COSTS
        # COLUMNAS A B C
        # ==================================================

        df_capital_temp = df_raw.iloc[:, [0, 1, 2]].copy()

        fila_header = df_capital_temp.dropna(
            how="all"
        ).index[0]

        encabezados_capital = df_capital_temp.iloc[
            fila_header
        ].tolist()

        df_capital_temp.columns = encabezados_capital

        df_capital_temp = df_capital_temp.iloc[
            fila_header + 1:
        ]

        df_capital_temp.dropna(
            how="all",
            inplace=True
        )

        df_capital_temp = df_capital_temp[
            df_capital_temp.iloc[:, 0].notna()
        ]

        df_capital = df_capital_temp.reset_index(
            drop=True
        )

        # ==================================================
        # CONVERTIR VALORES A FLOAT
        # ==================================================

        df_capital.iloc[:, 2] = (
            pd.to_numeric(
                df_capital.iloc[:, 2],
                errors="coerce"
            ).astype(float)
        )

        # ==================================================
        # FIXED OPERATING COSTS
        # COLUMNAS E F G
        # ==================================================

        df_fixed_temp = df_raw.iloc[:, [4, 5, 6]].copy()

        fila_header = df_fixed_temp.dropna(
            how="all"
        ).index[0]

        encabezados_fixed = df_fixed_temp.iloc[
            fila_header
        ].tolist()

        df_fixed_temp.columns = encabezados_fixed

        df_fixed_temp = df_fixed_temp.iloc[
            fila_header + 1:
        ]

        df_fixed_temp.dropna(
            how="all",
            inplace=True
        )

        df_fixed_temp = df_fixed_temp[
            df_fixed_temp.iloc[:, 0].notna()
        ]

        df_fixed = df_fixed_temp.reset_index(
            drop=True
        )

        # ==================================================
        # CONVERTIR VALORES A FLOAT
        # ==================================================

        df_fixed.iloc[:, 2] = (
            pd.to_numeric(
                df_fixed.iloc[:, 2],
                errors="coerce"
            ).astype(float)
        )

        # ==================================================
        # VARIABLE OPERATING COSTS
        # COLUMNAS I J K L M N
        # ==================================================

        df_variable_temp = df_raw.iloc[:, [8, 9, 10, 11, 12, 13]].copy()

        fila_header = df_variable_temp.dropna(
            how="all"
        ).index[0]

        encabezados_variable = df_variable_temp.iloc[
            fila_header
        ].tolist()

        df_variable_temp.columns = encabezados_variable

        # ==================================================
        # NORMALIZAR HEADERS
        # ==================================================

        df_variable_temp.columns = (
            df_variable_temp.columns
            .astype(str)
            .str.strip()
            .str.lower()
        )

        df_variable_temp = df_variable_temp.iloc[
            fila_header + 1:
        ]

        df_variable_temp.dropna(
            how="all",
            inplace=True
        )

        df_variable_temp = df_variable_temp[
            df_variable_temp.iloc[:, 0].notna()
        ]

        df_variable = df_variable_temp.reset_index(
            drop=True
        )

        # ==================================================
        # COLUMNAS NUMÉRICAS A FLOAT
        # ==================================================

        df_variable["flowrate"] = pd.to_numeric(
            df_variable["flowrate"],
            errors="coerce"
        ).astype(float)

        df_variable["price usd/units"] = pd.to_numeric(
            df_variable["price usd/units"],
            errors="coerce"
        ).astype(float)

        # ==================================================
        # MIGRAR STREAMS ANTIGUOS
        # ==================================================

        STREAM_MAP = {
            # Códigos A-F del formato legacy
            "A": "Key Products",
            "B": "By-products",
            "C": "Waste Streams",
            "D": "Raw Materials",
            "E": "Consumables",
            "F": "Utilities",
            # Aliases del export PFD nuevo (write_project_xlsx)
            "Waste / Byproduct": "Waste Streams",   # → bucket byproducts
        }

        df_variable["stream"] = (
            df_variable["stream"]
            .astype(str)
            .str.strip()
            .replace(STREAM_MAP)
        )

        engine.load(df_variable)

        # ==================================================
        # VALIDAR UNIDADES
        # ==================================================

        errores_unidades = ValidarUnidadesDataframe(

            dataframe=df_variable,

            columna_variable="variable operating costs",

            columna_unidad="units",

            columna_tiempo="time basis",

            columna_flowrate="flowrate",

            columna_price="price usd/units",

            nombre_tabla="Variable Operating Costs"

        )

        # ==================================================
        # MOSTRAR ERRORES
        # ==================================================

        if errores_unidades:

            mensaje = (
                "Invalid project data detected:\n\n"
            )

            for error in errores_unidades:

                mensaje += (

                    f"[{error['codigo']}] "
                    f"{error['mensaje']}\n\n"

                    f"Table    : {error['tabla']}\n"
                    f"Row      : {error['fila']}\n"
                    f"Variable : {error['variable']}\n"
                    f"Value    : {error['valor']}\n\n"

                )

            messagebox.showerror(
                "Import Validation Error",
                mensaje
            )

            return

        # ==================================================
        # CONSOLA
        # ==================================================

        ConsolaResultados.config(state="normal")

        ConsolaResultados.insert(
            END,
            "\n----------------------------------------\n"
        )

        ConsolaResultados.insert(
            END,
            "Project imported successfully.\n\n"
        )

        ConsolaResultados.insert(
            END,
            f"File:\n{archivo}\n\n"
        )

        ConsolaResultados.insert(
            END,
            f"Capital Costs Rows : {len(df_capital)}\n"
        )

        ConsolaResultados.insert(
            END,
            f"Fixed Costs Rows   : {len(df_fixed)}\n"
        )

        ConsolaResultados.insert(
            END,
            f"Variable Costs Rows: {len(df_variable)}\n"
        )

        ConsolaResultados.insert(
            END,
            f"Workspace Rows     : {len(engine.df_internal)}\n"
        )

        # ── Breakdown por bucket (sanity check post-import) ─────
        # Antes el user no veía si los productos llegaron como
        # Key Products o si se perdieron en mapping de streams.
        # Acá se muestra el conteo y revenue total por bucket.
        try:
            bucket_count = {}
            bucket_value = {}
            for _, _row in df_variable.iterrows():
                _stream = str(_row.get("stream", "")).strip()
                _flow   = float(_row.get("flowrate", 0) or 0)
                _price  = float(_row.get("price usd/units", 0) or 0)
                bucket_count[_stream] = bucket_count.get(_stream, 0) + 1
                bucket_value[_stream] = bucket_value.get(_stream, 0) + _flow * _price
            ConsolaResultados.insert(
                END, "\nStream buckets imported:\n")
            for _bk in sorted(bucket_count.keys()):
                ConsolaResultados.insert(
                    END,
                    f"  · {_bk:22} {bucket_count[_bk]:>3} rows  "
                    f"= ${bucket_value[_bk]:>14,.0f}/yr\n"
                )
            if "Key Products" not in bucket_count:
                ConsolaResultados.insert(
                    END,
                    "  ⚠ NO 'Key Products' → revenue=0, todos los "
                    "indicadores económicos saldrán negativos.\n",
                )
        except Exception:
            pass

        ConsolaResultados.config(state="disabled")

        # ==================================================
        # PESTAÑAS OPCIONALES (xlsx generado por PFD)
        #   · Equipment: tag, type, S, duty, T_op, P_op, etc.
        #   · Streams:   masa, T, P, fase, composición wt% por comp.,
        #                role, precio, pipe specs, locks.
        # ==================================================
        try:
            xls = pd.ExcelFile(archivo)
            sheet_names = set(xls.sheet_names)
            ConsolaResultados.config(state="normal")
            if "Equipment" in sheet_names:
                df_equipment = pd.read_excel(archivo, sheet_name="Equipment")
                df_equipment = df_equipment.dropna(how="all").reset_index(drop=True)
                ConsolaResultados.insert(
                    END,
                    f"Equipment Rows     : {len(df_equipment)}  (from PFD)\n"
                )
            else:
                df_equipment = pd.DataFrame()
            if "Streams" in sheet_names:
                df_streams = pd.read_excel(archivo, sheet_name="Streams")
                df_streams = df_streams.dropna(how="all").reset_index(drop=True)
                # Componentes únicos (cols con prefix 'wt% ')
                comp_cols = [c for c in df_streams.columns
                             if str(c).startswith("wt% ")]
                ConsolaResultados.insert(
                    END,
                    f"Streams Rows       : {len(df_streams)}  (from PFD, "
                    f"{len(comp_cols)} componentes)\n"
                )
            else:
                df_streams = pd.DataFrame()
            ConsolaResultados.config(state="disabled")
        except Exception:
            df_equipment = pd.DataFrame()
            df_streams = pd.DataFrame()

        _actualizar_status_proyecto(
            f"Imported: {os.path.basename(archivo)}"
        )

        messagebox.showinfo(
            "Import",
            "Project imported successfully."
        )

    except Exception as e:

        messagebox.showerror(
            "Import Error",
            str(e)
        )

# ======================================================
# VISUALIZAR DATA
# ======================================================

def VentanaVisualizarData():
    """Abre Toplevel con 3 tabs (Capital, Fixed, Variable).

    Variable Costs es la única tab con edición inline:
    doble-click abre combobox (units / time basis / stream)
    o entry numérico (price).  Cada edición pasa por
    engine.update/engine.load para mantener df_internal
    sincronizado.  Cambiar units o time basis preserva el
    flowrate SI: se convierte el valor visible para reflejar
    la nueva unidad sin alterar la cantidad física.
    """

    editor_activo = None

    global df_capital
    global df_fixed
    global df_variable

    ventanaData = Toplevel(raiz)

    ventanaData.title("Project Data")

    ventanaData.geometry(
        "980x540+240+60"
    )

    ventanaData.resizable(0, 0)

    ventanaData.transient(raiz)

    ventanaData.grab_set()

    notebook = ttk.Notebook(
        ventanaData
    )

    notebook.pack(
        fill="both",
        expand=True,
        padx=10,
        pady=10
    )

    # ==================================================
    # TAB CAPITAL
    # ==================================================

    tabCapital = ttk.Frame(notebook)

    notebook.add(
        tabCapital,
        text="Capital Costs"
    )

    toolbarCapital = ttk.Frame(tabCapital)
    toolbarCapital.pack(side="bottom", fill="x", padx=10, pady=(0, 8))

    tablaCapital = ttk.Treeview(
        tabCapital,
        show="headings"
    )

    tablaCapital.pack(
        side="top",
        fill="both",
        expand=True,
        padx=10,
        pady=10
    )

    # ==================================================
    # TAB FIXED
    # ==================================================

    tabFixed = ttk.Frame(notebook)

    notebook.add(
        tabFixed,
        text="Fixed Operating Costs"
    )

    toolbarFixed = ttk.Frame(tabFixed)
    toolbarFixed.pack(side="bottom", fill="x", padx=10, pady=(0, 8))

    tablaFixed = ttk.Treeview(
        tabFixed,
        show="headings"
    )

    tablaFixed.pack(
        side="top",
        fill="both",
        expand=True,
        padx=10,
        pady=10
    )

    # ==================================================
    # TAB VARIABLE
    # ==================================================

    tabVariable = ttk.Frame(notebook)

    notebook.add(
        tabVariable,
        text="Variable Operating Costs"
    )

    toolbarVariable = ttk.Frame(tabVariable)
    toolbarVariable.pack(side="bottom", fill="x", padx=10, pady=(0, 8))

    tablaVariable = ttk.Treeview(
        tabVariable,
        show="headings"
    )

    tablaVariable.pack(
        side="top",
        fill="both",
        expand=True,
        padx=10,
        pady=10
    )

    # ==================================================
    # TAB EQUIPMENT  (sólo si el xlsx vino del PFD)
    # ==================================================

    tablaEquipos = None
    if not df_equipment.empty:
        tabEquipos = ttk.Frame(notebook)
        notebook.add(
            tabEquipos,
            text="Equipment (from PFD)"
        )

        # nota explicativa arriba
        ttk.Label(
            tabEquipos,
            text="Lista de equipos del diagrama de proceso (read-only).\n"
                 "Editá los equipos desde el Flowsheet Editor "
                 "(Tools > Open Flowsheet Editor).",
            foreground="#555",
            justify="left",
        ).pack(side="top", anchor="w", padx=10, pady=(10, 4))

        tablaEquipos = ttk.Treeview(
            tabEquipos,
            show="headings",
        )

        cols_eq = list(df_equipment.columns)
        tablaEquipos["columns"] = cols_eq
        for c in cols_eq:
            tablaEquipos.heading(c, text=str(c))
            tablaEquipos.column(c, width=120, anchor="w")

        for _, row in df_equipment.iterrows():
            tablaEquipos.insert(
                "", END,
                values=[row[c] for c in cols_eq],
            )

        tablaEquipos.pack(
            side="top",
            fill="both",
            expand=True,
            padx=10,
            pady=10,
        )

    # ==================================================
    # TAB STREAMS  (sólo si el xlsx vino del PFD)
    # ==================================================
    tablaStreams = None
    if not df_streams.empty:
        tabStreams = ttk.Frame(notebook)
        notebook.add(
            tabStreams,
            text="Streams (from PFD)"
        )
        ttk.Label(
            tabStreams,
            text="Tabla de corrientes del PFD (read-only): masa, T, P, "
                 "fase, composición wt% por componente, role, precio, "
                 "pipe specs.\nEditá las corrientes desde el Flowsheet Editor.",
            foreground="#555",
            justify="left",
        ).pack(side="top", anchor="w", padx=10, pady=(10, 4))
        tablaStreams = ttk.Treeview(tabStreams, show="headings")
        cols_st = list(df_streams.columns)
        tablaStreams["columns"] = cols_st
        for c in cols_st:
            tablaStreams.heading(c, text=str(c))
            # composiciones wt% más angostas, otras anchas
            w = 80 if str(c).startswith("wt% ") else 110
            tablaStreams.column(c, width=w, anchor="w")
        for _, row in df_streams.iterrows():
            tablaStreams.insert(
                "", END,
                values=[row[c] for c in cols_st],
            )
        # Scrollbar horizontal (la tabla es muy ancha)
        hs = ttk.Scrollbar(tabStreams, orient="horizontal",
                            command=tablaStreams.xview)
        tablaStreams.configure(xscrollcommand=hs.set)
        tablaStreams.pack(side="top", fill="both", expand=True,
                            padx=10, pady=(10, 0))
        hs.pack(side="top", fill="x", padx=10, pady=(0, 10))

    # ==================================================
    # BLOQUEAR RESIZE COLUMNAS
    # ==================================================

    def bloquear_resize(event):

        if tablaCapital.identify_region(event.x, event.y) == "separator":
            return "break"

        if tablaFixed.identify_region(event.x, event.y) == "separator":
            return "break"

        if tablaVariable.identify_region(event.x, event.y) == "separator":
            return "break"

    tablaCapital.bind(
        "<Button-1>",
        bloquear_resize
    )

    tablaFixed.bind(
        "<Button-1>",
        bloquear_resize
    )

    tablaVariable.bind(
        "<Button-1>",
        bloquear_resize
    )

    # ==================================================
    # FUNCIÓN CARGAR DATAFRAME
    # ==================================================

    def cargar_dataframe(tree, dataframe, tipo):

        if dataframe.empty:
            return

        dataframe = dataframe.loc[
            :,
            dataframe.columns.notna()
        ]

        tree.delete(
            *tree.get_children()
        )

        columnas = list(
            dataframe.columns
        )

        tree["columns"] = columnas

        if tipo == "capital":

            anchos = [340, 170, 130]

            alineacion = ["w", "w", "center"]

        elif tipo == "fixed":

            anchos = [340, 220, 110]

            alineacion = ["w", "w", "center"]

        else:

            anchos = [220, 100, 100, 120, 120, 100]

            alineacion = [
                "w",
                "center",
                "center",
                "center",
                "center",
                "center"
            ]

        for i, col in enumerate(columnas):

            tree.heading(
                col,
                text=str(col)
            )

            tree.column(
                col,
                width=anchos[i],
                minwidth=anchos[i],
                anchor=alineacion[i],
                stretch=False
            )

        for _, row in dataframe.iterrows():

            fila_visual = []

            for valor in row:

                # ==========================================
                # FORMATEAR FLOATS
                # ==========================================

                if isinstance(valor, float):

                    valor = round(valor, 6)

                    # --------------------------------------
                    # QUITAR CEROS SOBRANTES
                    # --------------------------------------

                    valor = f"{valor:g}"

                fila_visual.append(valor)

            tree.insert(
                "",
                END,
                values=fila_visual
            )

    # ==================================================
    # CARGAR TABLAS
    # ==================================================

    cargar_dataframe(
        tablaCapital,
        df_capital,
        "capital"
    )

    cargar_dataframe(
        tablaFixed,
        df_fixed,
        "fixed"
    )

    cargar_dataframe(
        tablaVariable,
        df_variable,
        "variable"
    )

    # ==================================================
    # ENTRY NUMÉRICO GENÉRICO
    # ==================================================

    def CrearEntryNumerico(
            tree,
            dataframe,
            item,
            columna,
            nombre_columna
    ):

        x, y, width, height = tree.bbox(item, columna)

        valor_actual = tree.set(item, columna)

        entry = ttk.Entry(
            tree,
            justify="center"
        )

        nonlocal editor_activo
        editor_activo = entry

        entry.place(
            x=x,
            y=y,
            width=width,
            height=height
        )

        entry.insert(0, valor_actual)

        entry.focus()

        # ==============================================
        # VALIDACIÓN NUMÉRICA
        # ==============================================

        def ValidarNumero(texto):

            if texto == "":
                return True

            try:
                float(texto)
                return True
            except (ValueError, TypeError):
                return False

        validacion = (
            tree.register(ValidarNumero),
            "%P"
        )

        entry.config(
            validate="key",
            validatecommand=validacion
        )

        # ==============================================
        # GUARDAR
        # ==============================================

        def Guardar(event=None):

            nuevo_valor = entry.get()

            if nuevo_valor == "":
                return

            nuevo_valor = float(nuevo_valor)

            tree.set(
                item,
                columna,
                nuevo_valor
            )

            indice = tree.index(item)

            dataframe.at[
                indice,
                nombre_columna
            ] = nuevo_valor

            entry.destroy()

        entry.bind("<Return>", Guardar)

        entry.bind(
            "<FocusOut>",
            lambda e: entry.destroy()
        )

    # ==================================================
    # LISTAS DESPLEGABLES
    # ==================================================

    UNIDADES_POR_TIPO = {

        "mass": [
            "kg",
            "tm",
            "lb"
        ],

        "energy": [
            "kj",
            "mj",
            "gj"
        ],

        "electricity": [
            "wh",
            "kwh",
            "mwh"
        ]

    }

    TIME_DISPONIBLES = [

        "hour",
        "day",
        "month",
        "year"

    ]

    STREAM_DISPONIBLES = [

        "Key Products",

        "By-products",

        "Waste Streams",

        "Raw Materials",

        "Consumables",

        "Utilities"

    ]


    STREAM_MAP = {

        "A": "Key Products",
        "B": "By-products",
        "C": "Waste Streams",
        "D": "Raw Materials",
        "E": "Consumables",
        "F": "Utilities"

    }

    editor_activo = None
    # ==================================================
    # EDITAR CELDA INLINE
    # ==================================================
    def EditarCeldaVariable(event):

        nonlocal editor_activo

        # ==============================================
        # DESTRUIR EDITOR ANTERIOR
        # ==============================================
        if editor_activo is not None:

            try:
                editor_activo.destroy()
            except TclError:
                pass

            editor_activo = None

        item = tablaVariable.identify_row(event.y)
        columna = tablaVariable.identify_column(event.x)

        if not item:
            return

        columna_index = int(columna.replace("#", "")) - 1
        columnas = list(df_variable.columns)
        nombre_columna = columnas[columna_index]

        # ==============================================
        # COLUMNAS EDITABLES
        # ==============================================
        columnas_editables = [
            "variable operating costs",  # concept name (text)
            "units",
            "time basis",
            "flowrate",                  # numeric
            "price usd/units",
            "stream",
        ]

        if nombre_columna not in columnas_editables:
            return

        # ==============================================
        # POSICIÓN CELDA
        # ==============================================
        x, y, width, height = tablaVariable.bbox(item, columna)

        valor_actual = tablaVariable.set(item, columna)

        # ==============================================
        # CONVERTIR STREAM ANTIGUO
        # ==============================================

        if nombre_columna == "stream":

            valor_actual = STREAM_MAP.get(
                valor_actual,
                valor_actual
            )

        # ==================================================
        # ENTRY TEXTO - concept name
        # ==================================================
        if nombre_columna == "variable operating costs":

            entry = ttk.Entry(tablaVariable, justify="left")
            entry.place(x=x, y=y, width=width, height=height)
            editor_activo = entry
            entry.insert(0, valor_actual)
            entry.focus()

            def GuardarConcept(event):
                nuevo = entry.get().strip()
                if nuevo == "":
                    nuevo = "(no name)"
                indice = tablaVariable.index(item)
                tablaVariable.set(item, columna, nuevo)
                df_variable.at[indice, "variable operating costs"] = nuevo
                engine.load(df_variable)
                entry.destroy()

            entry.bind("<Return>", GuardarConcept)
            entry.bind("<FocusOut>", lambda e: entry.destroy())
            return

        # ==================================================
        # ENTRY NUMÉRICO - flowrate
        # ==================================================
        if nombre_columna == "flowrate":

            def ValidarNum(texto):
                if texto == "":
                    return True
                try:
                    float(texto); return True
                except (ValueError, TypeError):
                    return False

            entry = ttk.Entry(
                tablaVariable,
                justify="center",
                validate="key",
                validatecommand=(tablaVariable.register(ValidarNum), "%P"),
            )
            entry.place(x=x, y=y, width=width, height=height)
            editor_activo = entry
            entry.insert(0, valor_actual)
            entry.focus()

            def GuardarFlow(event):
                txt = entry.get().strip()
                if txt == "":
                    return
                nuevo = float(txt)
                indice = tablaVariable.index(item)
                tablaVariable.set(item, columna, nuevo)
                df_variable.at[indice, "flowrate"] = nuevo
                engine.load(df_variable)
                entry.destroy()

            entry.bind("<Return>", GuardarFlow)
            entry.bind("<FocusOut>", lambda e: entry.destroy())
            return

        # ==================================================
        # COMBOBOX - UNITS
        # ==================================================
        if nombre_columna == "units":

            # ==========================================
            # ÍNDICE DE LA FILA
            # ==========================================

            indice = tablaVariable.index(item)

            # ==========================================
            # UNIDAD ACTUAL
            # ==========================================

            unidad_actual = df_variable.at[
                indice,
                "units"
            ]

            # ==========================================
            # TIPO FÍSICO
            # ==========================================

            tipo_fisico = ObtenerTipoUnidad(
                unidad_actual
            )

            # ==========================================
            # UNIDADES VÁLIDAS
            # ==========================================

            unidades_validas = UNIDADES_POR_TIPO[
                tipo_fisico
            ]

            # ==========================================
            # COMBOBOX
            # ==========================================

            combo = ttk.Combobox(
                tablaVariable,
                values=unidades_validas,
                state="readonly"
            )

            combo.place(x=x, y=y, width=width, height=height)
            editor_activo = combo
            combo.set(valor_actual)

            def GuardarUnits(event):

                nuevo_valor = combo.get()

                indice = tablaVariable.index(item)

                # ==========================================
                # GUARDAR FLOWRATE SI ORIGINAL
                # ==========================================

                flowrate_si_original = engine.df_internal.at[
                    indice,
                    "Flowrate SI"
                ]

                tiempo_actual = df_variable.at[
                    indice,
                    "time basis"
                ]

                # ==========================================
                # CONVERTIR NUEVO FLOWRATE VISUAL
                # ==========================================

                nuevo_flowrate = ConvertirFlowrateVisible(
                    flowrate_si=flowrate_si_original,
                    unidad=nuevo_valor,
                    tiempo=tiempo_actual
                )

                # ==========================================
                # ACTUALIZAR DATAFRAME
                # ==========================================

                df_variable.at[indice, "units"] = nuevo_valor

                df_variable.at[indice, "flowrate"] = (
                    nuevo_flowrate
                )

                # ==========================================
                # ACTUALIZAR TABLA
                # ==========================================

                tablaVariable.set(
                    item,
                    columna,
                    nuevo_valor
                )

                tablaVariable.set(
                    item,
                    "#4",
                    round(nuevo_flowrate, 6)
                )

                # ==========================================
                # RECALCULAR ENGINE
                # ==========================================

                engine.load(df_variable)

                combo.destroy()

            combo.bind("<<ComboboxSelected>>", GuardarUnits)
            return

        # ==================================================
        # COMBOBOX - TIME BASIS
        # ==================================================
        if nombre_columna == "time basis":

            combo = ttk.Combobox(
                tablaVariable,
                values=TIME_DISPONIBLES,
                state="readonly"
            )

            combo.place(x=x, y=y, width=width, height=height)
            editor_activo = combo
            combo.set(valor_actual)

            def GuardarTime(event):

                nuevo_valor = combo.get()

                indice = tablaVariable.index(item)

                # ==========================================
                # FLOWRATE SI ORIGINAL
                # ==========================================

                flowrate_si_original = engine.df_internal.at[
                    indice,
                    "Flowrate SI"
                ]

                unidad_actual = df_variable.at[
                    indice,
                    "units"
                ]

                # ==========================================
                # NUEVO FLOWRATE VISUAL
                # ==========================================

                nuevo_flowrate = ConvertirFlowrateVisible(
                    flowrate_si=flowrate_si_original,
                    unidad=unidad_actual,
                    tiempo=nuevo_valor
                )

                # ==========================================
                # ACTUALIZAR DATAFRAME
                # ==========================================

                df_variable.at[indice, "time basis"] = (
                    nuevo_valor
                )

                df_variable.at[indice, "flowrate"] = (
                    nuevo_flowrate
                )

                # ==========================================
                # ACTUALIZAR TABLA
                # ==========================================

                tablaVariable.set(
                    item,
                    columna,
                    nuevo_valor
                )

                tablaVariable.set(
                    item,
                    "#4",
                    round(nuevo_flowrate, 6)
                )

                # ==========================================
                # RECALCULAR ENGINE
                # ==========================================

                engine.load(df_variable)

                combo.destroy()

            combo.bind("<<ComboboxSelected>>", GuardarTime)
            return

        # ==================================================
        # COMBOBOX - STREAM
        # ==================================================
        if nombre_columna == "stream":

            combo = ttk.Combobox(
                tablaVariable,
                values=STREAM_DISPONIBLES,
                state="readonly"
            )

            combo.place(x=x, y=y, width=width, height=height)
            editor_activo = combo
            combo.set(valor_actual)

            def GuardarStream(event):

                nuevo_valor = combo.get()

                tablaVariable.set(item, columna, nuevo_valor)

                indice = tablaVariable.index(item)

                engine.update(indice, "stream", nuevo_valor)

                combo.destroy()

            combo.bind("<<ComboboxSelected>>", GuardarStream)
            return

        # ==================================================
        # ENTRY - PRICE
        # ==================================================
        if nombre_columna == "price usd/units":

            def ValidarNumero(texto):

                if texto == "":
                    return True

                try:
                    float(texto)
                    return True

                except (ValueError, TypeError):
                    return False


            validacion = (
                tablaVariable.register(ValidarNumero),
                "%P"
            )

            entry = ttk.Entry(
                tablaVariable,
                justify="center",
                validate="key",
                validatecommand=validacion
            )

            entry.place(x=x, y=y, width=width, height=height)
            editor_activo = entry
            entry.insert(0, valor_actual)
            entry.focus()

            def GuardarPrice(event):

                nuevo_valor = entry.get()

                try:
                    nuevo_valor = float(nuevo_valor)
                except (ValueError, TypeError):
                    messagebox.showerror("Invalid Value", "Only numeric values allowed.")
                    return

                tablaVariable.set(item, columna, nuevo_valor)

                indice = tablaVariable.index(item)

                df_variable.at[indice, "price usd/units"] = nuevo_valor

                engine.update(indice, "price usd/units", nuevo_valor)

                entry.destroy()

            entry.bind("<Return>", GuardarPrice)
            entry.bind("<FocusOut>", lambda e: entry.destroy())

            return

    # ==================================================
    # EDITAR CAPITAL COSTS
    # ==================================================


    def EditarCeldaCapital(event):

        nonlocal editor_activo

        if editor_activo is not None:

            try:
                editor_activo.destroy()
            except TclError:
                pass

        editor_activo = None

        item = tablaCapital.identify_row(event.y)
        columna = tablaCapital.identify_column(event.x)

        if not item:
            return

        columna_index = int(
            columna.replace("#", "")
        ) - 1

        columnas = list(df_capital.columns)

        nombre_columna = columnas[columna_index]

        # ==============================================
        # SOLO COLUMNA VALOR
        # ==============================================

        if columna_index != 2:
            return

        CrearEntryNumerico(
            tree=tablaCapital,
            dataframe=df_capital,
            item=item,
            columna=columna,
            nombre_columna=nombre_columna
        )
    # ==================================================
    # EDITAR FIXED COSTS
    # ==================================================

    def EditarCeldaFixed(event):

        nonlocal editor_activo

        if editor_activo is not None:

            try:
                editor_activo.destroy()
            except TclError:
                pass

            editor_activo = None

        item = tablaFixed.identify_row(event.y)
        columna = tablaFixed.identify_column(event.x)

        if not item:
            return

        columna_index = int(
            columna.replace("#", "")
        ) - 1

        columnas = list(df_fixed.columns)

        nombre_columna = columnas[columna_index]

        # ==============================================
        # SOLO COLUMNA VALOR
        # ==============================================

        if columna_index != 2:
            return

        CrearEntryNumerico(
            tree=tablaFixed,
            dataframe=df_fixed,
            item=item,
            columna=columna,
            nombre_columna=nombre_columna
        )
    # ==================================================
    # ACTIVAR DOBLE CLICK
    # ==================================================

    tablaVariable.bind(
        "<Double-1>",
        EditarCeldaVariable
    )

    tablaCapital.bind(
        "<Double-1>",
        EditarCeldaCapital
    )

    tablaFixed.bind(
        "<Double-1>",
        EditarCeldaFixed
    )

    # ==================================================
    # AGREGAR / ELIMINAR FILAS
    # ==================================================

    def AddVariable():
        global df_variable
        nueva = templates.fila_variable_vacia()
        df_variable = pd.concat(
            [df_variable, pd.DataFrame([nueva])],
            ignore_index=True,
        )
        engine.load(df_variable)
        cargar_dataframe(tablaVariable, df_variable, "variable")

    def RemoveVariable():
        global df_variable
        sel = tablaVariable.selection()
        if not sel:
            messagebox.showinfo("Remove row", "Select a row first.")
            return
        idxs = sorted([tablaVariable.index(iid) for iid in sel], reverse=True)
        df_variable = df_variable.drop(df_variable.index[idxs]).reset_index(drop=True)
        engine.load(df_variable)
        cargar_dataframe(tablaVariable, df_variable, "variable")

    # Para Capital y Fixed: el modelo asume filas FIJAS
    # (5 filas Capital, 9 filas Fixed).  No tiene sentido
    # agregar/borrar — solo se editan valores.  Por eso
    # los toolbars de esos tabs muestran nota informativa.

    ttk.Label(
        toolbarCapital,
        text="Capital structure is fixed (5 rows). Edit values by double-click.",
        foreground="#555555",
    ).pack(side=LEFT)

    ttk.Label(
        toolbarFixed,
        text="FCOP structure is fixed (9 rows). Edit values by double-click.",
        foreground="#555555",
    ).pack(side=LEFT)

    ttk.Button(toolbarVariable, text="+ Add row",  command=AddVariable).pack(side=LEFT)
    ttk.Button(toolbarVariable, text="– Remove",   command=RemoveVariable).pack(side=LEFT, padx=6)
    ttk.Label(
        toolbarVariable,
        text="  (double-click a cell to edit)",
        foreground="#555555",
    ).pack(side=LEFT, padx=10)

    # tooltips dentro de la ventana
    Tooltip(tablaCapital,
            "ISBL: capital fijo principal (battery limits).\n"
            "OSBL, ENG, CONT, WC se expresan como % sobre ISBL/FCI.")
    Tooltip(tablaFixed,
            "Fixed Operating Costs según Turton §8:\n"
            "labor + porcentajes sobre Labor/FCI/ISBL+OSBL/WC.\n"
            "El total se calcula al apretar Solve.")
    Tooltip(tablaVariable,
            "Variable Operating Costs: cada fila es un stream\n"
            "(producto, byproduct, raw material, consumable o utility).\n"
            "Doble-click sobre una celda para editar.")

# ======================================================
# CONTROL DE DEPRECIACIÓN
# ======================================================

def ActualizarDepreciacion():
    """Habilita el entry de período (lineal) o los radios
    de MACRS según la opción seleccionada."""

    if opcionDepre.get() == 0:

        EntryDLineal.config(state="normal")

        RadioDMACRS5.config(state="disabled")
        RadioDMACRS7.config(state="disabled")
        RadioDMACRS15.config(state="disabled")

    else:

        EntryDLineal.config(state="disabled")

        RadioDMACRS5.config(state="normal")
        RadioDMACRS7.config(state="normal")
        RadioDMACRS15.config(state="normal")

# ======================================================
# ESTADO DEL ÚLTIMO REPORTE
# ======================================================

ultimo_reporte = {
    "path":           None,
    "resultado":      None,   # dict de pipeline.ejecutar_analisis()
    "resultado_mc":   None,   # dict de pipeline.ejecutar_montecarlo()
}

# ======================================================
# ABRIR EL ÚLTIMO REPORTE EXCEL
# ======================================================

def AbrirUltimoReporte(tab_inicial=0):
    """Abre el Dashboard de resultados del último Solve."""

    res = ultimo_reporte.get("resultado")
    if res is None:
        messagebox.showwarning(
            "No analysis",
            "Run the analysis first (Solve)."
        )
        return

    AbrirDashboard(
        raiz,
        resultado_base=res,
        resultado_mc=ultimo_reporte.get("resultado_mc"),
        on_open_excel=AbrirExcelExterno,
        on_save_as=GuardarExcelComo,
        tab_inicial=tab_inicial,
    )


def AbrirUltimoReporteSensitivity():
    """Atajo al Dashboard, tab Sensitivity."""
    AbrirUltimoReporte(tab_inicial=4)


def GuardarExcelComo():
    """Copia el Excel temporal a la ruta que elija el user.
    Botón 'Save Excel as…' del header del Dashboard."""

    src = ultimo_reporte.get("path")
    if not src or not os.path.exists(src):
        messagebox.showwarning("No report", "Run Solve first.")
        return

    dst = filedialog.asksaveasfilename(
        title="Save Economic Analysis Report",
        defaultextension=".xlsx",
        initialfile="Economic_Analysis.xlsx",
        filetypes=[("Excel files", "*.xlsx")],
    )
    if not dst:
        return

    try:
        import shutil
        shutil.copy(src, dst)
        messagebox.showinfo("Saved", f"Excel saved to:\n{dst}")
    except OSError as e:
        messagebox.showerror("Save error", str(e))


def AbrirExcelExterno():
    """Abre el .xlsx con el visor por defecto del sistema."""

    ruta = ultimo_reporte.get("path")
    if not ruta or not os.path.exists(ruta):
        messagebox.showwarning("No report", "Excel report not available.")
        return

    try:
        if sys.platform.startswith("win"):
            os.startfile(ruta)
        elif sys.platform == "darwin":
            subprocess.run(["open", ruta], check=False)
        else:
            subprocess.run(["xdg-open", ruta], check=False)
    except OSError as e:
        messagebox.showerror("Open Error", str(e))

# ======================================================
# RECOLECTAR INPUTS ECONÓMICOS DE LA UI
# ======================================================

def _leer_entry_float(entry, nombre):
    texto = entry.get().strip()
    if texto == "":
        raise ValueError(f"{nombre} is required")
    return float(texto)


def _to_fraction(valor, unidad):
    """Convierte valor a fracción según la unidad elegida
    en el Combobox.  'Fraction' lo deja como está;
    'Percentage' divide por 100."""
    return valor / 100.0 if unidad == "Percentage" else valor


def _csv_to_fraction(csv_text, unidad):
    """Convierte un CSV de fracciones/porcentajes a un CSV
    de fracciones según la unidad."""
    if not csv_text.strip():
        return ""
    pieces = [p.strip() for p in csv_text.split(",") if p.strip() != ""]
    if unidad == "Percentage":
        pieces = [str(float(p) / 100.0) for p in pieces]
    return ",".join(pieces)


def _years(valor, unidad):
    """Convierte a años enteros según la unidad
    ('Years' deja como está, 'Months' divide por 12 y
    redondea)."""
    yr = valor / 12.0 if unidad == "Months" else valor
    return max(1, int(round(yr)))


def _recolectar_inputs():

    project_life_raw = _leer_entry_float(EntryProjLife, "Project life")
    tax_raw          = _leer_entry_float(EntryTaxeRate, "Tax rate")
    discount_raw     = _leer_entry_float(EntryDiscountRate, "Discount rate")

    inputs = {
        "fc_csv":            _csv_to_fraction(EntryFC.get(),   LabelFCuni.get()),
        "vcop_csv":          _csv_to_fraction(EntryVCOP.get(), LabelVCOPuni.get()),
        "project_life":      _years(project_life_raw, LabelProjLifeUni.get()),
        "tax_rate":          _to_fraction(tax_raw,      LabelTaxRateUni.get()),
        "discount_rate":     _to_fraction(discount_raw, LabelDiscountRateUni.get()),
        "metodo_dep":        opcionDepre.get(),
        "tipo_macrs":        opcionMACRS.get(),
        "cepci_year_basis":  int(_leer_entry_float(EntryCEPCIBasis,  "CEPCI basis year")),
        "cepci_year_target": int(_leer_entry_float(EntryCEPCITarget, "CEPCI target year")),
    }

    if inputs["metodo_dep"] == 0:
        period_raw = _leer_entry_float(EntryDLineal, "Depreciation period")
        inputs["periodo_dep"] = _years(period_raw, LabelDLinealUni.get())

    return inputs

# ======================================================
# RESOLVER (BOTÓN SOLVE)
# ======================================================

def EjecutarAnalisis():
    """Botón Solve.  Pipeline completo:
        1) lee inputs económicos de la UI
        2) valida que haya proyecto importado
        3) pide ruta de archivo de reporte
        4) corre pipeline.ejecutar_analisis (CostModel +
           CashFlowModel + ReportGenerator)
        5) muestra FCI/WC/NPV/IRR en la consola
    """

    ConsolaResultados.config(state="normal")
    ConsolaResultados.delete(1.0, END)
    ConsolaResultados.insert(END, "Running economic analysis...\n\n")
    ConsolaResultados.config(state="disabled")
    raiz.update_idletasks()

    # 1) inputs
    try:
        inputs = _recolectar_inputs()
    except (ValueError, TypeError) as e:
        messagebox.showerror("Invalid input", str(e))
        return

    # 2) datos cargados
    if df_capital.empty or df_fixed.empty or engine.df_internal.empty:
        messagebox.showerror(
            "No project",
            "No project loaded yet.\n\n"
            "Choose one of:\n"
            "  • File > New Project (templates)\n"
            "  • File > Import Project (from Excel)"
        )
        return

    # 3) destino — archivo TEMPORAL automático.  El usuario
    # puede después guardarlo con "Save Excel as..." desde
    # el header del Dashboard.  Evita la fricción de pedir
    # filedialog cada Solve.
    import tempfile
    archivo = os.path.join(
        tempfile.gettempdir(),
        f"ANA_report_{os.getpid()}.xlsx",
    )

    # 4) corre pipeline
    try:
        resultado = ejecutar_analisis(
            df_capital=df_capital,
            df_fixed=df_fixed,
            df_internal=engine.df_internal,
            inputs_economicos=inputs,
            archivo_salida=archivo,
        )
    except Exception as e:
        messagebox.showerror(
            "Analysis Error",
            f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"
        )
        return

    ultimo_reporte["path"] = archivo
    ultimo_reporte["resultado"] = resultado
    ultimo_reporte["resultado_mc"] = None  # reset; se setea si MC corre

    BotonReporteEconomico.config(state="normal")

    # 5) resumen breve en la consola principal
    _consola_resumen_base(resultado, archivo)

    # 6) Sensitivity analysis (Monte Carlo)
    if VeSensibilidad.get():
        LanzarMonteCarlo(inputs, archivo)
    else:
        # No MC requested → abrir Dashboard directo (tab Overview)
        AbrirDashboard(
            raiz,
            resultado_base=resultado,
            resultado_mc=None,
            on_open_excel=AbrirExcelExterno,
        on_save_as=GuardarExcelComo,
            tab_inicial=0,
        )


def _consola_resumen_base(r, archivo):
    """Imprime un resumen breve en la consola principal
    (3-4 líneas).  El detalle completo lo da el Dashboard."""
    npv = r["npv"]
    irr = r["irr"]
    pbs = r.get("pbp_simple")

    irr_txt = f"{irr*100:.2f}%" if irr is not None else "n/a"
    pbs_txt = f"{pbs:.2f} yr"   if pbs is not None else "n/a"

    ConsolaResultados.config(state="normal")
    ConsolaResultados.delete(1.0, END)
    ConsolaResultados.insert(END, "Analysis completed — see dashboard for details.\n")
    ConsolaResultados.insert(END,
        f"  NPV {npv:.2f} MM USD   ·   IRR {irr_txt}   ·   PBP {pbs_txt}\n"
    )
    ConsolaResultados.insert(END,
        "  Excel report ready in dashboard (Save Excel as…).\n"
    )
    ConsolaResultados.config(state="disabled")


# ======================================================
# MONTE CARLO LAUNCHER
# ======================================================

def LanzarMonteCarlo(inputs, archivo_excel):
    """Abre la ventana de config MC.  Cuando el usuario
    aprieta Run, ejecuta el MC y abre la ventana de
    resultados (histograma + tornado + stats)."""

    try:
        data, _params = construir_data_y_params(
            df_capital, df_fixed, engine.df_internal, inputs,
        )
    except Exception as e:
        messagebox.showerror("Monte Carlo", f"{type(e).__name__}: {e}")
        return

    def CorrerMC(variables, n_runs, seed, correlacion):

        nota_corr = " correlated" if correlacion is not None else ""
        ConsolaResultados.config(state="normal")
        ConsolaResultados.insert(
            END,
            f"\nRunning Monte Carlo ({n_runs} runs, "
            f"{len(variables)}{nota_corr} vars)...\n"
        )
        ConsolaResultados.config(state="disabled")
        raiz.update_idletasks()

        try:
            resultado = ejecutar_montecarlo(
                df_capital=df_capital,
                df_fixed=df_fixed,
                df_internal=engine.df_internal,
                inputs_economicos=inputs,
                variables_inciertas=variables,
                n_runs=n_runs,
                seed=seed,
                correlacion=correlacion,
                archivo_salida=archivo_excel,
            )
        except Exception as e:
            messagebox.showerror(
                "Monte Carlo Error",
                f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"
            )
            return

        # consola: una línea
        s = resultado["mc"]["stats"]
        ConsolaResultados.config(state="normal")
        ConsolaResultados.insert(
            END,
            f"  MC: NPV P10/P50/P90 = "
            f"{s['npv_p10']:.1f} / {s['npv_p50']:.1f} / {s['npv_p90']:.1f}   "
            f"P(NPV<0) = {s['p_npv_neg']*100:.1f}%\n"
        )
        ConsolaResultados.config(state="disabled")

        ultimo_reporte["resultado_mc"] = resultado
        BotonReporteSensibilidad.config(state="normal")

        # Abrir dashboard en tab Sensitivity
        AbrirDashboard(
            raiz,
            resultado_base=ultimo_reporte["resultado"],
            resultado_mc=resultado,
            on_open_excel=AbrirExcelExterno,
        on_save_as=GuardarExcelComo,
            tab_inicial=4,
        )

    AbrirVentanaConfigMC(raiz, data, CorrerMC)


# ======================================================
# MENU
# ======================================================

menubar = Menu(raiz)

menuFile = Menu(
    menubar,
    tearoff=0
)

menubar.add_cascade(
    label='File',
    menu=menuFile
)

menuFile.add_command(
    label='New Project (templates)',
    command=NuevoProyecto,
)

menuFile.add_command(
    label='Import Project (from Excel)…',
    command=ImportarProyecto,
)

menuFile.add_separator()

menuFile.add_command(
    label='Exit',
    command=raiz.destroy
)

menuData = Menu(
    menubar,
    tearoff=0
)

menubar.add_cascade(
    label='Data',
    menu=menuData
)

menuData.add_command(
    label='View Project Data',
    command=VentanaVisualizarData
)

# ------------------------------------------------------
# TOOLS
# ------------------------------------------------------

def LanzarEstimateISBL():
    """Abre la ventana 'Estimate ISBL from Equipment List'.

    Se puede usar SIN proyecto cargado (sólo para calcular
    FCI Lang).  Para inyectar el ISBL al análisis sí hace
    falta tener proyecto importado — la ventana se encarga
    de habilitar/deshabilitar el botón según corresponda.
    """

    def OnApply():
        ConsolaResultados.config(state="normal")
        ConsolaResultados.insert(
            END,
            f"\nISBL updated from equipment list: "
            f"{float(df_capital.iat[0, 2]):.2f} MM USD\n"
        )
        ConsolaResultados.config(state="disabled")

    AbrirVentanaEstimateISBL(
        raiz,
        df_capital if not df_capital.empty else None,
        on_apply=OnApply,
    )


def LanzarFlowsheet():
    """Abre el editor de flowsheet (block diagram).
    Funciona con o sin proyecto cargado.  Si hay proyecto,
    'Apply ISBL' actualiza el df_capital del análisis."""

    def OnApply():
        ConsolaResultados.config(state="normal")
        ConsolaResultados.insert(
            END,
            f"\nISBL updated from flowsheet: "
            f"{float(df_capital.iat[0, 2]):.2f} MM USD\n"
        )
        ConsolaResultados.config(state="disabled")

    AbrirVentanaFlowsheet(
        raiz,
        df_capital if not df_capital.empty else None,
        on_apply=OnApply,
    )


def _AbrirFlowsheetExterno():
    """Abre el editor de diagrama como proceso separado.
    El análisis económico queda corriendo en paralelo."""
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        subprocess.Popen(
            [sys.executable, "flowsheet_main.py"],
            cwd=here,
        )
    except Exception as e:
        messagebox.showerror(
            "No se pudo abrir el diagrama",
            f"{type(e).__name__}: {e}",
        )


menuTools = Menu(menubar, tearoff=0)
menubar.add_cascade(label='Tools', menu=menuTools)
menuTools.add_command(
    label='Estimate Capital from Equipment List (Turton / Lang)…',
    command=LanzarEstimateISBL,
)
menuTools.add_command(
    label='Open Flowsheet Editor…   (process diagram in a separate window)',
    command=_AbrirFlowsheetExterno,
)

menuHelp = Menu(
    menubar,
    tearoff=0
)

menubar.add_cascade(
    label='Help',
    menu=menuHelp
)

menuHelp.add_command(
    label='Documentation',
    command=VentanaDocumentation
)

menuHelp.add_separator()

menuHelp.add_command(
    label='About ANA',
    command=VentanaAbout
)

raiz.config(menu=menubar)

# ======================================================
# QUICK-ACTIONS TOOLBAR (top of window)
# ======================================================
# Botones grandes con los pasos del flujo:
#   1) New / 2) Import / 3) View / 4) Equipment / 5) Solve
# ======================================================

ToolbarFrame = ttk.LabelFrame(raiz, text="Workflow")
ToolbarFrame.place(x=15, y=10, width=820, height=60)

BtnTbNew = ttk.Button(
    ToolbarFrame,
    text="📄  New project",
    width=18,
    command=lambda: NuevoProyecto(),
)
BtnTbNew.place(x=10, y=8)

BtnTbImport = ttk.Button(
    ToolbarFrame,
    text="📂  Import Excel",
    width=18,
    command=lambda: ImportarProyecto(),
)
BtnTbImport.place(x=150, y=8)

BtnTbViewData = ttk.Button(
    ToolbarFrame,
    text="📊  View / edit data",
    width=20,
    command=lambda: VentanaVisualizarData(),
)
BtnTbViewData.place(x=290, y=8)

BtnTbEquipment = ttk.Button(
    ToolbarFrame,
    text="🔧  Estimate capital",
    width=20,
    command=lambda: LanzarEstimateISBL(),
)
BtnTbEquipment.place(x=445, y=8)

BtnTbSolve = ttk.Button(
    ToolbarFrame,
    text="▶  Solve",
    width=12,
    command=lambda: EjecutarAnalisis(),
)
BtnTbSolve.place(x=595, y=8)

BtnTbFlowsheet = ttk.Button(
    ToolbarFrame,
    text="🧩  Flowsheet",
    width=14,
    command=lambda: _AbrirFlowsheetExterno(),
)
BtnTbFlowsheet.place(x=695, y=8)


# ======================================================
# INPUT FRAME
# ======================================================

ContornoDatos = ttk.LabelFrame(
    raiz,
    text="Input Data  —  ○  No project loaded"
)

ContornoDatos.place(
    x=15,
    y=80,
    width=690,
    height=260
)

# ======================================================
# SEPARADOR
# ======================================================

SeparadorVertical = ttk.Separator(
    ContornoDatos,
    orient="vertical"
)

SeparadorVertical.place(
    x=350,
    y=18,
    height=215
)

# ======================================================
# COLUMNA IZQUIERDA
# ======================================================

LabelFC = ttk.Label(
    ContornoDatos,
    text='FOC schedule :'
)

LabelFC.place(x=25, y=25)

EntryFC = ttk.Entry(
    ContornoDatos,
    width=16,
    justify="right"
)

EntryFC.insert(0, "1.0")
EntryFC.place(x=120, y=25)

LabelFCuni = ttk.Combobox(
    ContornoDatos,
    values=["Fraction", "Percentage"],
    state="readonly",
    width=11,
)
LabelFCuni.set("Fraction")

LabelFCuni.place(x=255, y=25)

# tooltip aclaratorio (FOC = Fixed Operating Cost schedule)
Tooltip(
    LabelFC,
    "Fixed Operating Cost schedule.\n"
    "Fracción del costo fijo total aplicada cada año.\n"
    "Formato CSV: año1, año2, ...  (un solo valor = todos los años igual).\n"
    "Default 1.0 = costo fijo al 100% desde el año 1.\n"
    "El costo fijo TOTAL se calcula con Turton desde Fixed Operating Costs."
)

# ------------------------------------------------------

LabelVCOP = ttk.Label(
    ContornoDatos,
    text='VOC schedule :'
)

LabelVCOP.place(x=25, y=65)

EntryVCOP = ttk.Entry(
    ContornoDatos,
    width=16,
    justify="right"
)

EntryVCOP.insert(0, "1.0")
EntryVCOP.place(x=120, y=65)

LabelVCOPuni = ttk.Combobox(
    ContornoDatos,
    values=["Fraction", "Percentage"],
    state="readonly",
    width=11,
)
LabelVCOPuni.set("Fraction")

LabelVCOPuni.place(x=255, y=65)

Tooltip(
    LabelVCOP,
    "Variable Operating Cost schedule.\n"
    "Fracción del costo variable total aplicada cada año.\n"
    "Formato CSV: año1, año2, ...  (un solo valor = todos los años igual).\n"
    "Default 1.0 = planta a producción nominal desde el año 1.\n"
    "El costo variable TOTAL se calcula desde Variable Operating Costs (Σ flujo × precio)."
)

# ------------------------------------------------------

LabelProjLife = ttk.Label(
    ContornoDatos,
    text='Project life * :'
)

LabelProjLife.place(x=25, y=105)

EntryProjLife = ttk.Entry(
    ContornoDatos,
    width=16,
    justify="right"
)

EntryProjLife.insert(0, "10")    # default 10 años (típico Turton)
EntryProjLife.place(x=120, y=105)

LabelProjLifeUni = ttk.Combobox(
    ContornoDatos,
    values=["Years", "Months"],
    state="readonly",
    width=11,
)
LabelProjLifeUni.set("Years")

LabelProjLifeUni.place(x=255, y=105)

# ------------------------------------------------------

LabelTaxeRate = ttk.Label(
    ContornoDatos,
    text='Tax rate * :'
)

LabelTaxeRate.place(x=25, y=145)

EntryTaxeRate = ttk.Entry(
    ContornoDatos,
    width=16,
    justify="right"
)

EntryTaxeRate.insert(0, "29.5")  # Perú impuesto a la renta tercera categoría
EntryTaxeRate.place(x=120, y=145)

LabelTaxRateUni = ttk.Combobox(
    ContornoDatos,
    values=["Fraction", "Percentage"],
    state="readonly",
    width=11,
)
LabelTaxRateUni.set("Percentage")

LabelTaxRateUni.place(x=255, y=145)

# ------------------------------------------------------

LabelCEPCIBasis = ttk.Label(
    ContornoDatos,
    text='CEPCI basis :'
)

LabelCEPCIBasis.place(x=25, y=185)

EntryCEPCIBasis = ttk.Entry(
    ContornoDatos,
    width=6,
    justify="right"
)

EntryCEPCIBasis.insert(0, "2026")
EntryCEPCIBasis.place(x=120, y=185)

LabelCEPCITarget = ttk.Label(
    ContornoDatos,
    text='target :'
)

LabelCEPCITarget.place(x=180, y=185)

EntryCEPCITarget = ttk.Entry(
    ContornoDatos,
    width=6,
    justify="right"
)

EntryCEPCITarget.insert(0, "2026")
EntryCEPCITarget.place(x=240, y=185)

LabelCEPCIUni = ttk.Label(
    ContornoDatos,
    text='Year'
)

LabelCEPCIUni.place(x=300, y=185)

CheckSensibilidad = ttk.Checkbutton(
    ContornoDatos,
    text="Sensitivity analysis",
    variable=VeSensibilidad
)

CheckSensibilidad.place(x=25, y=225)

# ======================================================
# COLUMNA DERECHA
# ======================================================

LabelDEpreciacion = ttk.Label(
    ContornoDatos,
    text='Depreciation * :'
)

LabelDEpreciacion.place(x=395, y=25)

RadioDLineal = ttk.Radiobutton(
    ContornoDatos,
    text="Straight-line",
    variable=opcionDepre,
    value=0,
    command=ActualizarDepreciacion
)

RadioDLineal.place(x=395, y=60)

EntryDLineal = ttk.Entry(
    ContornoDatos,
    width=10,
    justify="right"
)

EntryDLineal.insert(0, "10")     # depreciación SL típica: igual a la vida del proyecto
EntryDLineal.place(x=535, y=60)

LabelDLinealUni = ttk.Combobox(
    ContornoDatos,
    values=["Years", "Months"],
    state="readonly",
    width=8,
)
LabelDLinealUni.set("Years")

LabelDLinealUni.place(x=620, y=60)

RadioDMACRS = ttk.Radiobutton(
    ContornoDatos,
    text="MACRS",
    variable=opcionDepre,
    value=1,
    command=ActualizarDepreciacion
)

RadioDMACRS.place(x=395, y=115)

RadioDMACRS5 = ttk.Radiobutton(
    ContornoDatos,
    text="MACRS 5",
    variable=opcionMACRS,
    value=0,
    state="disabled"
)

RadioDMACRS5.place(x=490, y=85)

RadioDMACRS7 = ttk.Radiobutton(
    ContornoDatos,
    text="MACRS 7",
    variable=opcionMACRS,
    value=1,
    state="disabled"
)

RadioDMACRS7.place(x=490, y=115)

RadioDMACRS15 = ttk.Radiobutton(
    ContornoDatos,
    text="MACRS 15",
    variable=opcionMACRS,
    value=2,
    state="disabled"
)

RadioDMACRS15.place(x=490, y=145)

LabelDiscountRate = ttk.Label(
    ContornoDatos,
    text='Discount rate * :'
)

LabelDiscountRate.place(x=395, y=205)

EntryDiscountRate = ttk.Entry(
    ContornoDatos,
    width=12,
    justify="right"
)

EntryDiscountRate.insert(0, "12")   # 12% típico project finance
EntryDiscountRate.place(x=535, y=205)

LabelDiscountRateUni = ttk.Combobox(
    ContornoDatos,
    values=["Fraction", "Percentage"],
    state="readonly",
    width=11,
)
LabelDiscountRateUni.set("Percentage")

LabelDiscountRateUni.place(x=635, y=205)

# ======================================================
# RESULTS FRAME
# ======================================================

ContornoResultados = ttk.LabelFrame(
    raiz,
    text="Results"
)

ContornoResultados.place(
    x=15,
    y=365,
    width=690,
    height=170
)

ConsolaResultados = scrolledtext.ScrolledText(
    ContornoResultados,
    width=78,
    height=5,
    bg="white",
    fg="black",
    insertbackground="black",
    font=("Consolas", 10)
)

ConsolaResultados.place(
    x=20,
    y=20
)

ConsolaResultados.insert(
    END,
    "ANA initialized.\nWaiting for economic analysis..."
)

ConsolaResultados.config(state="disabled")

# ======================================================
# BOTONES REPORTES
# ======================================================

BotonReporteEconomico = ttk.Button(
    ContornoResultados,
    text='Economic Analysis Report',
    width=30,
    state="disabled",
    command=AbrirUltimoReporte
)

BotonReporteEconomico.place(
    x=155,
    y=118
)

BotonReporteSensibilidad = ttk.Button(
    ContornoResultados,
    text='Economic Sensitivity Report',
    width=30,
    state="disabled",
    command=AbrirUltimoReporteSensitivity,
)

BotonReporteSensibilidad.place(
    x=405,
    y=118
)

# ======================================================
# BOTON SOLVE
# ======================================================

BotonResolver = ttk.Button(
    raiz,
    text='Solve',
    width=20,
    command=EjecutarAnalisis
)

BotonResolver.place(
    x=285,
    y=555
)

# ======================================================
# LEYENDA "* required"
# ======================================================

LeyendaObligatorios = ttk.Label(
    raiz,
    text="*  required field",
    foreground="#c62828",
    font=("Segoe UI", 8),
)
LeyendaObligatorios.place(x=20, y=345)

# ======================================================
# TOOLTIPS — burbujas informativas sobre los inputs
# ======================================================

adjuntar_tooltips({

    # ---- Toolbar (workflow) ----
    BtnTbNew: (
        "Step 1 — crea un proyecto vacío con valores típicos de Turton.\n"
        "Después editás todo desde 'View / edit data'."
    ),
    BtnTbImport: (
        "Step 1 (alternative) — importa un Excel con 3 secciones:\n"
        "Capital Costs · Fixed Operating · Variable Operating Costs.\n\n"
        "Tolerancia: el parser detecta filas por nombre, así que el\n"
        "orden y el número de filas pueden variar dentro de lo razonable."
    ),
    BtnTbViewData: (
        "Step 2 — abre la tabla del proyecto para editar:\n"
        "• Capital (5 filas fijas)\n"
        "• Fixed Operating (9 filas fijas)\n"
        "• Variable Operating (agregás/eliminás filas)"
    ),
    BtnTbEquipment: (
        "Bonus — estima ISBL desde una lista de equipos.\n"
        "Cp° de Turton Apx A + Lang factor.  Reemplaza el ISBL\n"
        "del proyecto si lo confirmás."
    ),
    BtnTbSolve: (
        "Step 3 — corre el análisis completo y abre el Dashboard\n"
        "(NPV, IRR/DCFROR, Payback, ROI, sensitivity)."
    ),

    EntryFC: (
        "Construction schedule — fracción del CapEx invertido cada año.\n\n"
        "Ej: '0.3,0.7'  → 30% año 1, 70% año 2.\n"
        "Vacío  → planta instantánea (1 año de inversión)."
    ),
    EntryVCOP: (
        "Capacity ramp-up — fracción de capacidad operativa por año.\n\n"
        "Ej: '0.5,1.0'  → 50% el 1er año de operación, 100% en adelante.\n"
        "Vacío  → arranca al 100% desde el inicio."
    ),
    EntryProjLife: (
        "Años de operación de la planta (no incluye construcción).\n"
        "Típico: 15 a 20 años en industria química."
    ),
    EntryTaxeRate: (
        "Tasa impositiva sobre el ingreso operativo gravable.\n\n"
        "Aceptamos ambas convenciones:\n"
        "   0.30   → 30%\n"
        "   30     → 30%\n\n"
        "Los taxes se pagan con desfase de 1 año (Turton §10)."
    ),
    EntryCEPCIBasis: (
        "Año en el que se hizo la estimación original del ISBL.\n"
        "Si tu cotización es de 2018, poné 2018.\n\n"
        "CEPCI = Chemical Engineering Plant Cost Index."
    ),
    EntryCEPCITarget: (
        "Año al que se quiere actualizar el ISBL por inflación.\n"
        "Default 2026.\n\n"
        "El factor multiplica al ISBL:  CEPCI[target] / CEPCI[basis]."
    ),
    EntryDiscountRate: (
        "Tasa de descuento para el NPV.\n"
        "Suele ser el WACC del proyecto o la tasa de retorno requerida.\n\n"
        "Aceptamos ambas convenciones:\n"
        "   0.15   → 15%\n"
        "   15     → 15%"
    ),
    EntryDLineal: (
        "Años para depreciar el FCI en forma lineal.\n"
        "D anual = FCI / N años.\n"
        "Típico: 10 años para plantas químicas (IRS Pub. 946)."
    ),
    RadioDLineal: (
        "Depreciación constante: D = FCI / N años.\n"
        "Más simple; usado para análisis preliminar."
    ),
    RadioDMACRS: (
        "Modified Accelerated Cost Recovery System (US tax law).\n"
        "Depreciación acelerada en los primeros años.\n"
        "Reduce taxes tempranos → mejora NPV."
    ),
    RadioDMACRS5:  ("MACRS de 5 años — usado para vehículos, equipos electrónicos."),
    RadioDMACRS7:  ("MACRS de 7 años — usado para maquinaria industrial standard."),
    RadioDMACRS15: ("MACRS de 15 años — usado para infraestructura, mejoras de planta."),
    CheckSensibilidad: (
        "Si está activado, al apretar Solve después del cálculo base\n"
        "se abre Monte Carlo (sampling sobre precios de productos,\n"
        "raw materials e ISBL) y el dashboard se abre en\n"
        "la pestaña 'Sensitivity'."
    ),
    BotonResolver: (
        "Ejecuta el análisis económico end-to-end:\n"
        "Costos → Cash Flow → NPV, IRR/DCFROR, Payback, ROI.\n"
        "Abre el Dashboard de resultados al terminar."
    ),
    BotonReporteEconomico: (
        "Abre el Dashboard con todos los resultados del último Solve.\n"
        "(Habilitado solo después de ejecutar Solve.)"
    ),
    BotonReporteSensibilidad: (
        "Abre el Dashboard directamente en la pestaña Sensitivity\n"
        "(Habilitado después de un Solve con Monte Carlo)."
    ),
})

# ======================================================
# CONFIGURACIÓN INICIAL
# ======================================================

ActualizarDepreciacion()

# ======================================================
# CLI: --import path.xlsx  [--isbl X]
# Permite lanzar ANA.py desde main.py / flowsheet_main.py
# con el proyecto ya cargado y opcionalmente con el ISBL
# inyectado desde el flowsheet.
# ======================================================

if "--import" in sys.argv:
    _idx = sys.argv.index("--import")
    if _idx + 1 < len(sys.argv):
        _path = sys.argv[_idx + 1]
        try:
            ImportarProyecto(_path)
        except Exception as _e:
            messagebox.showerror(
                "Import failed",
                f"No se pudo abrir {_path}:\n{type(_e).__name__}: {_e}",
            )

if "--isbl" in sys.argv:
    _idx = sys.argv.index("--isbl")
    if _idx + 1 < len(sys.argv):
        try:
            _isbl = float(sys.argv[_idx + 1])
            if not df_capital.empty:
                df_capital.iat[0, 2] = _isbl
                ConsolaResultados.config(state="normal")
                ConsolaResultados.insert(
                    END,
                    f"\nISBL injected from flowsheet: {_isbl:.2f} MM USD\n",
                )
                ConsolaResultados.config(state="disabled")
        except (ValueError, TypeError):
            pass

# ======================================================
# MAINLOOP
# ======================================================

print("ENGINE READY")

raiz.mainloop()