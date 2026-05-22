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
# FUENTES de los valores:
#   1985–2022: publicaciones anuales de Chemical Engineering
#              Magazine (https://www.chemengonline.com).
#   2023:      promedio anual oficial publicado en CE Magazine
#              (consultado 2025-02).
#   2024+:     NO hay valor anual oficial publicado al momento.
#              Se utiliza nearest-neighbor (último anual oficial
#              conocido) con warning explícito.  El usuario puede
#              sobreescribir CEPCI[año] con un valor de mercado
#              actualizado.
# ======================================================

import warnings


# Annual average CEPCI values — sólo cifras oficiales publicadas
# por Chemical Engineering Magazine.  Sin estimados/placeholders.
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
    2021: 708.0,    # final anual oficial CE Mag
    2022: 816.0,    # final anual oficial CE Mag
    2023: 797.9,    # final anual oficial CE Mag (consultado 2025-02)
    # 2024+: SIN VALOR OFICIAL DISPONIBLE.  Cuando CE publique el
    # promedio anual, agregar acá.  Mientras tanto _valor_cepci
    # devuelve el último conocido (2023 = 797.9) con warning.
}


# Año por defecto para escalar costos del proyecto.  Si tu
# análisis requiere el año actual, sobreescribir o pasarlo
# como year_target en las funciones de costing.
AÑO_BASE_DEFAULT = 2024


def _valor_cepci(año):
    """Devuelve CEPCI[año] usando lookup directo si existe,
    interpolación lineal entre años vecinos si está dentro del
    rango oficial, o nearest-neighbor con warning si está fuera.

    (Antes el docstring decía "sin interpolación lineal" pero el
    código sí interpolaba — contradicción ahora resuelta:
    interpola por defecto, documenta el comportamiento real, y
    advierte explícitamente cuando hace nearest-neighbor en los
    extremos.  Instrucciones §2.1.)
    """
    if año in CEPCI:
        return CEPCI[año]

    años = sorted(CEPCI.keys())
    if año < años[0]:
        warnings.warn(
            f"CEPCI: año {año} < primer año disponible ({años[0]}).  "
            f"Usando valor de {años[0]} = {CEPCI[años[0]]} "
            f"(nearest-neighbor, NO oficial para {año}).",
            stacklevel=2,
        )
        return CEPCI[años[0]]
    if año > años[-1]:
        warnings.warn(
            f"CEPCI: año {año} > último valor oficial ({años[-1]}).  "
            f"Usando valor de {años[-1]} = {CEPCI[años[-1]]} "
            f"(nearest-neighbor; Chemical Engineering Magazine no ha "
            f"publicado promedio anual para {año} aún).  "
            f"Para precisión, sobreescribir CEPCI[{año}] con un valor "
            f"mensual reciente.",
            stacklevel=2,
        )
        return CEPCI[años[-1]]

    # Interpolación lineal entre años vecinos (caso intermedio:
    # años con valor oficial existente arriba y abajo).
    año_lo = max(a for a in años if a < año)
    año_hi = min(a for a in años if a > año)
    val_lo = CEPCI[año_lo]
    val_hi = CEPCI[año_hi]
    return val_lo + (val_hi - val_lo) * (año - año_lo) / (año_hi - año_lo)
