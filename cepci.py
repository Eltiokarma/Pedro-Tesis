# ======================================================
# CEPCI — Chemical Engineering Plant Cost Index
# ======================================================
# Ajuste de costos de capital por inflación de plantas
# químicas.  Usado para llevar una estimación hecha en el
# año X al año Y:
#
#     Cost_Y = Cost_X * (CEPCI[Y] / CEPCI[X])
#
# Refs:
#   Turton et al. §7 (Estimation of Capital Costs).
#   Towler & Sinnott §7.3 (Cost Indices).
#
# Los valores hasta 2022 son los publicados oficialmente
# por Chemical Engineering Magazine.  Para años recientes
# (2023+) los valores son los más actuales conocidos al
# momento de escribir esto; verificalo con la publicación
# anual de CE antes de defender tu tesis.
# ======================================================

# Annual average CEPCI values
CEPCI = {
    1985: 325.0,
    1990: 357.6,
    1995: 381.1,
    2000: 394.1,
    2001: 394.3,
    2002: 395.6,
    2003: 402.0,
    2004: 444.2,
    2005: 468.2,
    2006: 499.6,
    2007: 525.4,
    2008: 575.4,
    2009: 521.9,
    2010: 550.8,
    2011: 585.7,
    2012: 584.6,
    2013: 567.3,
    2014: 576.1,
    2015: 556.8,
    2016: 541.7,
    2017: 567.5,
    2018: 603.1,
    2019: 607.5,
    2020: 596.2,
    2021: 708.0,
    2022: 816.0,
    2023: 797.9,
    2024: 800.0,   # estimado preliminar
    2025: 810.0,   # estimado
    2026: 820.0,   # proyectado (placeholder — actualizar)
}


AÑO_BASE_DEFAULT = 2026


def años_disponibles():
    """Lista de años con CEPCI disponible, ascendente."""
    return sorted(CEPCI.keys())


def factor_cepci(año_origen, año_destino):
    """Factor multiplicativo para llevar un costo del año
    origen al año destino.

    Si alguno de los años no está en la tabla, hace
    extrapolación lineal con el año más cercano (warning
    silencioso; revisar la tabla manualmente para precisión).
    """

    if año_origen == año_destino:
        return 1.0

    val_origen  = _valor_cepci(año_origen)
    val_destino = _valor_cepci(año_destino)

    return val_destino / val_origen


def ajustar_costo(costo, año_origen, año_destino):
    """Lleva `costo` del año_origen al año_destino vía CEPCI."""
    return costo * factor_cepci(año_origen, año_destino)


def _valor_cepci(año):
    """Devuelve CEPCI[año].  Si no existe, hace lookup del
    más cercano (sin interpolación lineal entre años
    intermedios)."""

    if año in CEPCI:
        return CEPCI[año]

    # nearest neighbor
    años = años_disponibles()
    if año < años[0]:
        return CEPCI[años[0]]
    if año > años[-1]:
        return CEPCI[años[-1]]
    # interpolación lineal entre años vecinos
    año_lo = max(a for a in años if a < año)
    año_hi = min(a for a in años if a > año)
    val_lo = CEPCI[año_lo]
    val_hi = CEPCI[año_hi]
    return val_lo + (val_hi - val_lo) * (año - año_lo) / (año_hi - año_lo)
