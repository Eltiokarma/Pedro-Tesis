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

from mc_ui import AbrirVentanaConfigMC, AbrirVentanaResultadosMC

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


# ======================================================
# VENTANA PRINCIPAL
# ======================================================

raiz = Tk()

raiz.title("ANA")
raiz.geometry('720x540+210+20')
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
# IMPORTAR PROYECTO
# ======================================================

def ImportarProyecto():
    """Importa un Excel de proyecto con 3 secciones:
        Capital Costs           (cols A,B,C)
        Fixed Operating Costs   (cols E,F,G)
        Variable Operating Costs (cols I..N)

    Valida unidades en Variable Costs; si hay errores,
    muestra messagebox detallado y aborta el load del
    engine.  Migra streams en formato letra (A..F) a
    nombres legibles (Key Products, etc.).
    """

    global df_capital
    global df_fixed
    global df_variable

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

            "A": "Key Products",
            "B": "By-products",
            "C": "Waste Streams",
            "D": "Raw Materials",
            "E": "Consumables",
            "F": "Utilities"

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

        ConsolaResultados.config(state="disabled")

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

    tablaCapital = ttk.Treeview(
        tabCapital,
        show="headings"
    )

    tablaCapital.pack(
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

    tablaFixed = ttk.Treeview(
        tabFixed,
        show="headings"
    )

    tablaFixed.pack(
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

    tablaVariable = ttk.Treeview(
        tabVariable,
        show="headings"
    )

    tablaVariable.pack(
        fill="both",
        expand=True,
        padx=10,
        pady=10
    )

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
            "units",
            "time basis",
            "price usd/units",
            "stream"
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

ultimo_reporte = {"path": None}

# ======================================================
# ABRIR EL ÚLTIMO REPORTE EXCEL
# ======================================================

def AbrirUltimoReporte():
    """Abre el último .xlsx generado con la app por
    defecto del sistema (xdg-open / open / startfile)."""

    ruta = ultimo_reporte.get("path")

    if not ruta or not os.path.exists(ruta):
        messagebox.showwarning(
            "No report",
            "Run the analysis first."
        )
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


def _recolectar_inputs():

    inputs = {
        "fc_csv":        EntryFC.get(),
        "vcop_csv":      EntryVCOP.get(),
        "project_life":  _leer_entry_float(EntryProjLife, "Project life"),
        "tax_rate":      _leer_entry_float(EntryTaxeRate, "Tax rate"),
        "discount_rate": _leer_entry_float(EntryDiscountRate, "Discount rate"),
        "metodo_dep":    opcionDepre.get(),
        "tipo_macrs":    opcionMACRS.get(),
    }

    if inputs["metodo_dep"] == 0:
        inputs["periodo_dep"] = _leer_entry_float(
            EntryDLineal, "Depreciation period"
        )

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
            "Import a project first (File > Import Project)."
        )
        return

    # 3) destino
    archivo = filedialog.asksaveasfilename(
        title="Save Economic Analysis Report",
        defaultextension=".xlsx",
        initialfile="Economic_Analysis.xlsx",
        filetypes=[("Excel files", "*.xlsx")],
    )

    if not archivo:
        return

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

    BotonReporteEconomico.config(state="normal")

    # 5) consola
    npv = resultado["npv"]
    irr = resultado["irr"]
    fci = resultado["costos"]["FCI"]
    wc = resultado["costos"]["WC"]

    ConsolaResultados.config(state="normal")
    ConsolaResultados.delete(1.0, END)
    ConsolaResultados.insert(END, "Economic Analysis Completed\n\n")
    ConsolaResultados.insert(END, f"FCI  : {fci:>10.2f} MM USD\n")
    ConsolaResultados.insert(END, f"WC   : {wc:>10.2f} MM USD\n")
    ConsolaResultados.insert(END, f"NPV  : {npv:>10.2f} MM USD\n")

    if irr is not None:
        ConsolaResultados.insert(END, f"IRR  : {irr*100:>10.2f} %\n")
    else:
        ConsolaResultados.insert(END, "IRR  :        n/a (no sign change in CF)\n")

    ConsolaResultados.insert(END, f"\nReport saved to:\n{archivo}\n")
    ConsolaResultados.config(state="disabled")

    # 6) Sensitivity analysis (Monte Carlo)
    if VeSensibilidad.get():
        LanzarMonteCarlo(inputs, archivo)


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

        # consola
        s = resultado["mc"]["stats"]
        ConsolaResultados.config(state="normal")
        ConsolaResultados.insert(END, "\nMonte Carlo done.\n")
        ConsolaResultados.insert(
            END,
            f"NPV mean ± std: {s['npv_mean']:.2f} ± {s['npv_std']:.2f}\n"
        )
        ConsolaResultados.insert(
            END,
            f"NPV P10/P50/P90: {s['npv_p10']:.2f} / {s['npv_p50']:.2f} / {s['npv_p90']:.2f}\n"
        )
        ConsolaResultados.insert(
            END,
            f"P(NPV<0): {s['p_npv_neg']*100:.1f}%\n"
        )
        ConsolaResultados.config(state="disabled")

        AbrirVentanaResultadosMC(raiz, resultado)

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
    label='Import Project',
    command=ImportarProyecto
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
# INPUT FRAME
# ======================================================

ContornoDatos = ttk.LabelFrame(
    raiz,
    text="Input Data"
)

ContornoDatos.place(
    x=15,
    y=10,
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
    text='FC :'
)

LabelFC.place(x=25, y=25)

EntryFC = ttk.Entry(
    ContornoDatos,
    width=16,
    justify="right"
)

EntryFC.place(x=120, y=25)

LabelFCuni = ttk.Label(
    ContornoDatos,
    text='Fraction'
)

LabelFCuni.place(x=255, y=25)

# ------------------------------------------------------

LabelVCOP = ttk.Label(
    ContornoDatos,
    text='VCOP :'
)

LabelVCOP.place(x=25, y=65)

EntryVCOP = ttk.Entry(
    ContornoDatos,
    width=16,
    justify="right"
)

EntryVCOP.place(x=120, y=65)

LabelVCOPuni = ttk.Label(
    ContornoDatos,
    text='Fraction'
)

LabelVCOPuni.place(x=255, y=65)

# ------------------------------------------------------

LabelProjLife = ttk.Label(
    ContornoDatos,
    text='Project life :'
)

LabelProjLife.place(x=25, y=105)

EntryProjLife = ttk.Entry(
    ContornoDatos,
    width=16,
    justify="right"
)

EntryProjLife.place(x=120, y=105)

LabelProjLifeUni = ttk.Label(
    ContornoDatos,
    text='Years'
)

LabelProjLifeUni.place(x=255, y=105)

# ------------------------------------------------------

LabelTaxeRate = ttk.Label(
    ContornoDatos,
    text='Tax rate :'
)

LabelTaxeRate.place(x=25, y=145)

EntryTaxeRate = ttk.Entry(
    ContornoDatos,
    width=16,
    justify="right"
)

EntryTaxeRate.place(x=120, y=145)

LabelTaxRateUni = ttk.Label(
    ContornoDatos,
    text='Fraction'
)

LabelTaxRateUni.place(x=255, y=145)

# ------------------------------------------------------

CheckSensibilidad = ttk.Checkbutton(
    ContornoDatos,
    text="Sensitivity analysis",
    variable=VeSensibilidad
)

CheckSensibilidad.place(x=25, y=205)

# ======================================================
# COLUMNA DERECHA
# ======================================================

LabelDEpreciacion = ttk.Label(
    ContornoDatos,
    text='Depreciation :'
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

EntryDLineal.place(x=535, y=60)

LabelDLinealUni = ttk.Label(
    ContornoDatos,
    text='Years'
)

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
    text='Discount rate :'
)

LabelDiscountRate.place(x=395, y=205)

EntryDiscountRate = ttk.Entry(
    ContornoDatos,
    width=12,
    justify="right"
)

EntryDiscountRate.place(x=535, y=205)

LabelDiscountRateUni = ttk.Label(
    ContornoDatos,
    text='Fraction'
)

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
    y=285,
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
    state="disabled"
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
    y=480
)

# ======================================================
# CONFIGURACIÓN INICIAL
# ======================================================

ActualizarDepreciacion()

# ======================================================
# MAINLOOP
# ======================================================

print("ENGINE READY")

raiz.mainloop()