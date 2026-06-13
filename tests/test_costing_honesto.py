"""PR-B — Costing honesto: la tabla de equipos muestra lo que el costing
REALMENTE usó (T_op/P_op efectivos), no el crudo 1.0/0.0 del bloque, y
expone el origen del material.  Solo VISIBILIDAD — el CBM no cambia."""
import math
import pytest

import examples_registry as reg
import flowsheet_export as fx
from flowsheet_solver import effective_pressure, effective_temperature


def _rows(clave="talara"):
    fs = reg.load_example(clave)
    return fs, fx.collect_equipment_rows(fs, 2024)


def test_p_op_columna_es_la_presion_efectiva_del_costing():
    """La columna P_op debe ser la presión EFECTIVA (la que entra a FP),
    no el b.P_op_bar crudo.  Antes 37/42 mostraban 1.0 aunque el costing
    usaba 40-80 bar internamente."""
    fs, rows = _rows()
    byname = {b.name: b for b in fs.blocks.values()}
    for r in rows:
        b = byname[r["Tag"]]
        assert math.isclose(r["P_op [bar]"], effective_pressure(fs, b),
                            rel_tol=1e-6), \
            f"{r['Tag']}: P_op tabla {r['P_op [bar]']} ≠ efectiva " \
            f"{effective_pressure(fs, b)}"
    # Hay bloques cuyo P efectivo (heredado de corrientes) supera su P_op_bar
    # crudo: antes mostraban 1.0; ahora muestran la P real que usó el costing.
    mejorados = [r for r in rows
                 if r["P_op [bar]"] > float(getattr(byname[r["Tag"]],
                                                     "P_op_bar", 0.0) or 0.0) + 1e-6]
    assert mejorados, "ningún bloque hereda P efectiva de sus corrientes (T4)"
    # los hornos HT son el caso testigo (P_op_bar crudo=1.0 → efectiva 40-80)
    tags = {r["Tag"] for r in mejorados}
    assert {"F-HTD", "F-HTF", "F-HTN"} <= tags


def test_t_op_columna_poblada_desde_corrientes_adyacentes():
    """T_op debe poblarse del promedio de Ts de corrientes adyacentes cuando
    el bloque no declara T_op_K, en vez de mostrar 0.0°C."""
    fs, rows = _rows()
    byname = {b.name: b for b in fs.blocks.values()}
    for r in rows:
        b = byname[r["Tag"]]
        t_eff_k = effective_temperature(fs, b)
        esperado = (t_eff_k - 273.15) if t_eff_k else 0.0
        assert math.isclose(r["T_op [°C]"], esperado, abs_tol=1e-6), \
            f"{r['Tag']}: T_op tabla {r['T_op [°C]']} ≠ esperado {esperado}"
    en_cero = sum(1 for r in rows if math.isclose(r["T_op [°C]"], 0.0, abs_tol=1e-9))
    assert en_cero < len(rows) // 2, "demasiadas filas siguen en T_op=0.0"


def test_t_op_unidades_kelvin_vs_celsius():
    """Regresión del bug de unidades: stream.temperature está en °C pero
    block.T_op_K en K.  Un fired heater HT debe dar cientos de °C, no
    decenas (que sería tratar °C como K)."""
    fs, rows = _rows()
    fhtd = next(r for r in rows if r["Tag"] == "F-HTD")
    # C4-hot=370°C, C4-pumped=250°C → promedio 310°C
    assert math.isclose(fhtd["T_op [°C]"], 310.0, abs_tol=1.0)


def test_columna_material_origen_presente_y_al_final():
    fs, rows = _rows()
    assert "Material (origen)" in rows[0]
    assert list(rows[0])[-1] == "Material (origen)"
    # F-HTD: heurística por H2S; F-101: default CS
    by = {r["Tag"]: r for r in rows}
    assert "hydrogen sulfide" in by["F-HTD"]["Material (origen)"]
    assert "default" in by["F-101"]["Material (origen)"].lower()


def test_cbm_no_cambia_es_solo_visibilidad():
    """FASE 1 es presentación: el costing ya usaba la presión efectiva, así
    que los CBM de la tabla deben seguir > 0 y coherentes (sanity)."""
    fs, rows = _rows()
    by = {r["Tag"]: r for r in rows}
    # los 3 hornos HT en SS316 sigue siendo el grueso; F-101/F-RCA en CS baratos
    assert by["F-HTD"]["Material"] == "SS316"
    assert by["F-101"]["Material"] == "CS"
    assert by["F-HTD"]["CBM USD (2024)"] > by["F-101"]["CBM USD (2024)"]
