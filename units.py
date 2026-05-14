# ======================================================
# UNITS — sistema de unidades físicas + validación
# ======================================================
# Internal SI bases per physical type:
#   mass         -> tm     ;  price -> USD/tm
#   energy       -> kJ     ;  price -> USD/kJ
#   electricity  -> Wh     ;  price -> USD/Wh
# Time internal base: year.
# ======================================================

from difflib import get_close_matches

import pandas as pd


# ======================================================
# TABLA ÚNICA DE TIPOS FÍSICOS
# ======================================================
# Para cada tipo: la unidad interna (SI) y el factor que
# convierte CADA alias a esa unidad interna.
#
#     unidad_interna = alias_value * factors_to_internal[alias]
#
# El factor de precio es 1/factor_de_flowrate (porque price
# es por-unidad), por lo que se deriva — no se duplica.
# ======================================================

UNIT_TYPES = {

    "mass": {
        "internal": "tm",
        "factors_to_internal": {
            "kg": 0.001,
            "tm": 1.0,
            "lb": 0.000453592,
        },
    },

    "energy": {
        "internal": "kj",
        "factors_to_internal": {
            "kj": 1.0,
            "mj": 1_000.0,
            "gj": 1_000_000.0,
        },
    },

    "electricity": {
        "internal": "wh",
        "factors_to_internal": {
            "wh": 1.0,
            "kwh": 1_000.0,
            "mwh": 1_000_000.0,
        },
    },

}


# ======================================================
# TABLAS DERIVADAS (no editar a mano)
# ======================================================

PHYSICAL_UNITS = {
    alias: tipo
    for tipo, spec in UNIT_TYPES.items()
    for alias in spec["factors_to_internal"]
}

_FLOWRATE_FACTOR = {
    alias: factor
    for spec in UNIT_TYPES.values()
    for alias, factor in spec["factors_to_internal"].items()
}

_PRICE_FACTOR = {
    alias: 1.0 / factor
    for alias, factor in _FLOWRATE_FACTOR.items()
}


# ======================================================
# BASES DE TIEMPO
# ======================================================

TIME_ALIASES = {

    # YEAR
    "y": "year",
    "yr": "year",
    "year": "year",

    # MONTH
    "m": "month",
    "month": "month",

    # DAY
    "d": "day",
    "day": "day",

    # HOUR
    "h": "hour",
    "hr": "hour",
    "hour": "hour",

}

# Cuántas unidades-tiempo entran en 1 año.
TIME_PER_YEAR = {
    "year":   1,
    "month":  12,
    "day":    365,
    "hour":   8760,
}


# ======================================================
# LOOKUP HELPERS
# ======================================================

def _norm(texto):
    return str(texto).strip().lower()


def ObtenerTipoUnidad(unidad):
    """Devuelve 'mass' | 'energy' | 'electricity' para el
    alias dado.  KeyError si no es válido."""
    return PHYSICAL_UNITS[_norm(unidad)]


def EsUnidadFisicaValida(unidad):
    return _norm(unidad) in PHYSICAL_UNITS


def EsUnidadTiempoValida(unidad_tiempo):
    return _norm(unidad_tiempo) in TIME_ALIASES


def SugerirTimeBasis(unidad_tiempo):
    """Sugiere la time basis más cercana a un input typo'd.
    Devuelve None si no hay match decente."""
    sugerencia = get_close_matches(
        _norm(unidad_tiempo),
        TIME_ALIASES.keys(),
        n=1,
        cutoff=0.6,
    )
    return sugerencia[0] if sugerencia else None


def SugerirUnidadFisica(unidad):
    """Sugiere unidad física cercana.  None si no hay
    match."""
    sugerencia = get_close_matches(
        _norm(unidad),
        PHYSICAL_UNITS.keys(),
        n=1,
        cutoff=0.6,
    )
    return sugerencia[0] if sugerencia else None


# ======================================================
# VALIDACIÓN DEL DATAFRAME DE INPUTS
# ======================================================

def _make_error(codigo, mensaje, nombre_tabla, fila, variable, valor):
    return {
        "codigo":   codigo,
        "mensaje":  mensaje,
        "tabla":    nombre_tabla,
        "fila":     fila,
        "variable": variable,
        "valor":    valor,
    }


def _es_vacio(valor):
    return pd.isna(valor) or str(valor).strip() == ""


def ValidarUnidadesDataframe(
        dataframe,
        columna_variable,
        columna_unidad,
        columna_tiempo,
        columna_flowrate,
        columna_price,
        nombre_tabla,
):
    """Recorre el dataframe y devuelve lista de errores.

    Códigos:
        UNIT-001  missing physical unit
        UNIT-002  unknown physical unit
        TIME-001  missing time basis
        TIME-002  unknown time basis
        NUM-001   missing flowrate
        NUM-002   negative flowrate
        NUM-003   non-numeric flowrate
        MONEY-001 missing price
        MONEY-002 negative price
        MONEY-003 non-numeric price
    """

    errores = []

    for indice, fila in dataframe.iterrows():

        variable    = str(fila[columna_variable]).strip()
        unidad_raw  = fila[columna_unidad]
        tiempo_raw  = fila[columna_tiempo]
        flowrate    = fila[columna_flowrate]
        price       = fila[columna_price]

        fila_num = indice + 1

        # ---- UNIDAD FÍSICA --------------------------------
        if _es_vacio(unidad_raw):
            errores.append(_make_error(
                "UNIT-001", "Missing physical unit",
                nombre_tabla, fila_num, variable, "",
            ))
        else:
            unidad = _norm(unidad_raw)
            if not EsUnidadFisicaValida(unidad):
                errores.append(_make_error(
                    "UNIT-002", "Unknown physical unit",
                    nombre_tabla, fila_num, variable, unidad,
                ))

        # ---- TIME BASIS -----------------------------------
        if _es_vacio(tiempo_raw):
            errores.append(_make_error(
                "TIME-001", "Missing time basis",
                nombre_tabla, fila_num, variable, "",
            ))
        else:
            tiempo = _norm(tiempo_raw)
            if not EsUnidadTiempoValida(tiempo):
                errores.append(_make_error(
                    "TIME-002", "Unknown time basis",
                    nombre_tabla, fila_num, variable, tiempo,
                ))

        # ---- FLOWRATE -------------------------------------
        if _es_vacio(flowrate):
            errores.append(_make_error(
                "NUM-001", "Missing flowrate",
                nombre_tabla, fila_num, variable, flowrate,
            ))
        else:
            try:
                if float(flowrate) < 0:
                    errores.append(_make_error(
                        "NUM-002", "Negative flowrate",
                        nombre_tabla, fila_num, variable, flowrate,
                    ))
            except (ValueError, TypeError):
                errores.append(_make_error(
                    "NUM-003", "Non-numeric flowrate",
                    nombre_tabla, fila_num, variable, flowrate,
                ))

        # ---- PRICE ----------------------------------------
        if _es_vacio(price):
            errores.append(_make_error(
                "MONEY-001", "Missing price",
                nombre_tabla, fila_num, variable, price,
            ))
        else:
            try:
                if float(price) < 0:
                    errores.append(_make_error(
                        "MONEY-002", "Negative price",
                        nombre_tabla, fila_num, variable, price,
                    ))
            except (ValueError, TypeError):
                errores.append(_make_error(
                    "MONEY-003", "Non-numeric price",
                    nombre_tabla, fila_num, variable, price,
                ))

    return errores


# ======================================================
# CONVERSIONES
# ======================================================

def NormalizarFlowrate(flowrate, unidad, tiempo):
    """Convierte un flowrate (valor + unidad + base
    temporal) a la base interna del tipo físico, por año."""
    unidad = _norm(unidad)
    tiempo = TIME_ALIASES[_norm(tiempo)]
    return float(flowrate) * _FLOWRATE_FACTOR[unidad] * TIME_PER_YEAR[tiempo]


def NormalizarPrecio(price, unidad):
    """Convierte un precio USD/<unidad> a USD/<unidad
    interna del tipo físico>.  El factor temporal NO
    interviene porque price ya es por unidad de cantidad."""
    return float(price) * _PRICE_FACTOR[_norm(unidad)]


def ConvertirFlowrateVisible(flowrate_si, unidad, tiempo):
    """Inversa de NormalizarFlowrate: parte de la base
    interna por año y devuelve el flowrate en (unidad,
    time basis)."""
    unidad = _norm(unidad)
    tiempo = TIME_ALIASES[_norm(tiempo)]
    return flowrate_si / (_FLOWRATE_FACTOR[unidad] * TIME_PER_YEAR[tiempo])
