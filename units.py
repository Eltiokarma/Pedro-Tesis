# ======================================================
# LIBRERÍAS
# ======================================================
import pandas as pd

# ======================================================
# UNIDADES FÍSICAS SOPORTADAS
# ======================================================

PHYSICAL_UNITS = {

    # MASS
    "kg": "mass",
    "tm": "mass",
    "lb": "mass",

    # MONEY
    "usd": "money",
    "mmusd": "money",

    # ENERGY
    "kj": "energy",
    "mj": "energy",
    "gj": "energy",

    # ELECTRICITY
    "wh": "electricity",
    "kwh": "electricity",
    "mwh": "electricity"

}

# ======================================================
# BASES DE TIEMPO SOPORTADAS
# ======================================================

TIME_ALIASES = {

    # YEAR
    "y": "year",
    "yr": "year",
    "year": "year",

    # DAY
    "d": "day",
    "day": "day",

    # MONTH
    "m": "month",
    "month": "month",

    # HOUR
    "h": "hour",
    "hr": "hour",
    "hour": "hour"

}


# ======================================================
# FACTORES DE CONVERSIÓN DE MASA
# BASE INTERNA = TM
# ======================================================

MASS_CONVERSIONS = {

    "kg": 0.001,
    "tm": 1.0,
    "lb": 0.000453592

}
# ======================================================
# FACTORES DE PRECIO
# BASE INTERNA:
# USD/kg
# ======================================================

# ======================================================
# FACTORES DE PRECIO
#
# MASS         -> USD/kg
# ENERGY       -> USD/kJ
# ELECTRICITY  -> USD/Wh
# ======================================================

PRICE_CONVERSIONS = {

    # MASS
    "kg": 1000.0,
    "tm": 1.0,
    "lb": 2204.62,

    # ENERGY
    "kj": 1.0,
    "mj": 1 / 1000,
    "gj": 1 / 1_000_000,

    # ELECTRICITY
    "wh": 1.0,
    "kwh": 1 / 1000,
    "mwh": 1 / 1_000_000

}

# ======================================================
# FACTORES DE CONVERSIÓN DE TIEMPO
# BASE INTERNA = year
# ======================================================

TIME_CONVERSIONS = {

    "hour": 8760,

    "day": 365,

    "month": 12,

    "year": 1

}

# ======================================================
# FACTORES DE CONVERSIÓN DE MASA
# BASE INTERNA = TM
# ======================================================

MASS_FACTORS = {

    "kg": 0.001,
    "tm": 1.0,
    "lb": 0.000453592

}

# ======================================================
# FACTORES DE TIEMPO
# BASE INTERNA = year
# ======================================================

TIME_FACTORS = {

    "hour": 8760,
    "day": 365,
    "month": 12,
    "year": 1

}

# ======================================================
# IDENTIFICAR TIPO DE UNIDAD
# ======================================================

def ObtenerTipoUnidad(unidad):

    unidad = unidad.strip().lower()

    return PHYSICAL_UNITS[unidad]

# ======================================================
# VALIDAR UNIDAD FÍSICA
# ======================================================

def EsUnidadFisicaValida(unidad):

    return unidad in PHYSICAL_UNITS

# ======================================================
# VALIDAR BASE TEMPORAL
# ======================================================

def EsUnidadTiempoValida(unidad_tiempo):

    return unidad_tiempo in TIME_ALIASES

# ======================================================

def SugerirTimeBasis(unidad_tiempo):

    sugerencia = get_close_matches(
        unidad_tiempo,
        TIME_UNITS,
        n=1,
        cutoff=0.6
    )

    if sugerencia:
        return sugerencia[0]

    return None

# ======================================================
# VALIDAR DATAFRAME
# ======================================================

def ValidarUnidadesDataframe(
        dataframe,
        columna_variable,
        columna_unidad,
        columna_tiempo,
        columna_flowrate,
        columna_price,
        nombre_tabla
):

    errores = []

    for indice, fila in dataframe.iterrows():

        # ==================================================
        # LEER FILA
        # ==================================================

        variable = str(
            fila[columna_variable]
        ).strip()

        unidad = str(
            fila[columna_unidad]
        ).strip().lower()

        tiempo = str(
            fila[columna_tiempo]
        ).strip().lower()

        flowrate = fila[columna_flowrate]

        price = fila[columna_price]

        # ==================================================
        # UNIT-001
        # UNIDAD VACÍA
        # ==================================================

        if pd.isna(unidad) or unidad == "":

            errores.append({

                "codigo": "UNIT-001",

                "mensaje": "Missing physical unit",

                "tabla": nombre_tabla,

                "fila": indice + 1,

                "variable": variable,

                "valor": unidad,

            })

        # ==================================================
        # UNIT-002
        # UNIDAD DESCONOCIDA
        # ==================================================

        elif not EsUnidadFisicaValida(unidad):

            errores.append({

                "codigo": "UNIT-002",

                "mensaje": "Unknown physical unit",

                "tabla": nombre_tabla,

                "fila": indice + 1,

                "variable": variable,

                "valor": unidad,

            })

        # ==================================================
        # TIME-001
        # TIME BASIS VACÍO
        # ==================================================

        if pd.isna(tiempo) or tiempo == "":

            errores.append({

                "codigo": "TIME-001",

                "mensaje": "Missing time basis",

                "tabla": nombre_tabla,

                "fila": indice + 1,

                "variable": variable,

                "valor": tiempo,

            })

        # ==================================================
        # TIME-002
        # TIME BASIS DESCONOCIDO
        # ==================================================

        elif not EsUnidadTiempoValida(tiempo):

            errores.append({

                "codigo": "TIME-002",

                "mensaje": "Unknown time basis",

                "tabla": nombre_tabla,

                "fila": indice + 1,

                "variable": variable,

                "valor": tiempo,


            })

        else:

            tiempo_normalizado = TIME_ALIASES[tiempo]

        # ==================================================
        # NUM-001
        # FLOWRATE VACÍO
        # ==================================================

        if pd.isna(flowrate) or str(flowrate).strip() == "":

            errores.append({

                "codigo": "NUM-001",

                "mensaje": "Missing flowrate",

                "tabla": nombre_tabla,

                "fila": indice + 1,

                "variable": variable,

                "valor": flowrate,

            })

        else:

            try:

                flowrate_num = float(flowrate)

                # ==========================================
                # NUM-002
                # FLOWRATE NEGATIVO
                # ==========================================

                if flowrate_num < 0:

                    errores.append({

                        "codigo": "NUM-002",

                        "mensaje": "Negative flowrate",

                        "tabla": nombre_tabla,

                        "fila": indice + 1,

                        "variable": variable,

                        "valor": flowrate,

                    })

            except:

                # ==========================================
                # NUM-003
                # FLOWRATE NO NUMÉRICO
                # ==========================================

                errores.append({

                    "codigo": "NUM-003",

                    "mensaje": "Non-numeric flowrate",

                    "tabla": nombre_tabla,

                    "fila": indice + 1,

                    "variable": variable,

                    "valor": flowrate,

                })

        # ==================================================
        # MONEY-001
        # PRECIO VACÍO
        # ==================================================

        if pd.isna(price) or str(price).strip() == "":

            errores.append({

                "codigo": "MONEY-001",

                "mensaje": "Missing price",

                "tabla": nombre_tabla,

                "fila": indice + 1,

                "variable": variable,

                "valor": price,

            })

        else:

            try:

                price_num = float(price)

                # ==========================================
                # MONEY-002
                # PRECIO NEGATIVO
                # ==========================================

                if price_num < 0:

                    errores.append({

                        "codigo": "MONEY-002",

                        "mensaje": "Negative price",

                        "tabla": nombre_tabla,

                        "fila": indice + 1,

                        "variable": variable,

                        "valor": price,

                    })

            except:

                # ==========================================
                # MONEY-003
                # PRECIO NO NUMÉRICO
                # ==========================================

                errores.append({

                    "codigo": "MONEY-003",

                    "mensaje": "Non-numeric price",

                    "tabla": nombre_tabla,

                    "fila": indice + 1,

                    "variable": variable,

                    "valor": price,

                })

    return errores

# ======================================================
# NORMALIZAR FLOWRATE
# BASE INTERNA:
#
# MASS         -> kg/year
# ENERGY       -> kJ/year
# ELECTRICITY  -> Wh/year
# ======================================================

def NormalizarFlowrate(
        flowrate,
        unidad,
        tiempo
):

    # ----------------------------------------------
    # NORMALIZAR TEXTO
    # ----------------------------------------------

    unidad = unidad.strip().lower()

    tiempo = tiempo.strip().lower()

    tiempo = TIME_ALIASES[tiempo]

    # ----------------------------------------------
    # TIPO DE UNIDAD
    # ----------------------------------------------

    tipo = ObtenerTipoUnidad(unidad)

    # ----------------------------------------------
    # FACTOR TIEMPO
    # ----------------------------------------------

    factor_tiempo = TIME_CONVERSIONS[tiempo]

    valor = float(flowrate)

    # ----------------------------------------------
    # MASS
    # ----------------------------------------------

    if tipo == "mass":

        factor = MASS_CONVERSIONS[unidad]

        return valor * factor * factor_tiempo

    # ----------------------------------------------
    # ENERGY
    # BASE = kJ/year
    # ----------------------------------------------

    elif tipo == "energy":

        ENERGY_CONVERSIONS = {

            "kj": 1.0,
            "mj": 1000.0,
            "gj": 1_000_000.0

        }

        factor = ENERGY_CONVERSIONS[unidad]

        return valor * factor * factor_tiempo

    # ----------------------------------------------
    # ELECTRICITY
    # BASE = Wh/year
    # ----------------------------------------------

    elif tipo == "electricity":

        ELECTRICITY_CONVERSIONS = {

            "wh": 1.0,
            "kwh": 1000.0,
            "mwh": 1_000_000.0

        }

        factor = ELECTRICITY_CONVERSIONS[unidad]

        return valor * factor * factor_tiempo

    # ----------------------------------------------
    # ERROR
    # ----------------------------------------------

    raise ValueError(
        f"Unsupported unit type: {unidad}"
    )


# ======================================================

def NormalizarPrecio(
        price,
        unidad
):

    # ----------------------------------------------
    # NORMALIZAR TEXTO
    # ----------------------------------------------

    unidad = unidad.strip().lower()

    # ----------------------------------------------
    # FACTOR
    # ----------------------------------------------

    factor_precio = PRICE_CONVERSIONS[unidad]

    # ----------------------------------------------
    # CONVERSIÓN
    # ----------------------------------------------

    price_normalizado = (
        float(price)
        * factor_precio
    )

    return price_normalizado

# ======================================================
# CONVERTIR FLOWRATE A UNIDAD VISUAL
# ======================================================

def ConvertirFlowrateVisible(
        flowrate_si,
        unidad,
        tiempo
):

    unidad = unidad.strip().lower()

    tiempo = tiempo.strip().lower()

    tiempo = TIME_ALIASES[tiempo]

    tipo = ObtenerTipoUnidad(unidad)

    factor_tiempo = TIME_CONVERSIONS[tiempo]

    # ==============================================
    # MASS
    # ==============================================

    if tipo == "mass":

        factor = MASS_CONVERSIONS[unidad]

        return flowrate_si / (
            factor * factor_tiempo
        )

    # ==============================================
    # ENERGY
    # ==============================================

    elif tipo == "energy":

        ENERGY_CONVERSIONS = {

            "kj": 1.0,
            "mj": 1000.0,
            "gj": 1_000_000.0

        }

        factor = ENERGY_CONVERSIONS[unidad]

        return flowrate_si / (
            factor * factor_tiempo
        )

    # ==============================================
    # ELECTRICITY
    # ==============================================

    elif tipo == "electricity":

        ELECTRICITY_CONVERSIONS = {

            "wh": 1.0,
            "kwh": 1000.0,
            "mwh": 1_000_000.0

        }

        factor = ELECTRICITY_CONVERSIONS[unidad]

        return flowrate_si / (
            factor * factor_tiempo
        )

    raise ValueError(
        f"Unsupported unit: {unidad}"
    )