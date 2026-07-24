"""
datasheet.py — Ficha Técnica de equipo: agregador Qt-free + modo selección.

Fuente única de la ficha por bloque (contrato de
docs/FICHAS_TECNICAS_INVENTARIO.md §4): reúne lo que sizing, solver,
costos y auxiliares YA calculan — no computa física nueva — y monta la
verificación del modo selección contra data/equipos_comerciales.json
(esquema v2: S escalar XOR S_no_publicado + granularidad).

Estados de verificación (artboard 5f + §4.1):
  · "no_aplica"         — el tipo no tiene catálogo comercial (caso
                          dominante: ingeniería a pedido; NO es un hueco).
  · "sin_declarar"      — hay catálogo para el tipo, nada declarado.
  · "desconocido"       — Block.equipo_comercial no matchea el catálogo
                          (entrada retirada o typo) → warning.
  · "escalar"           — el modelo publica S: ratio de utilización
                          S_req/S_modelo + AND de envolvente.
  · "envolvente_modelo" — sin S publicado, límites del modelo concreto:
                          AND de desigualdades, SIN ratio (su ausencia es
                          una propiedad del equipo, no un dato faltante).
  · "debil_familia"     — límites del rango completo de la serie: mismo
                          mecanismo, lectura opuesta — casi cualquier duty
                          entra, el resultado confirma poco.  apto=None
                          SIEMPRE (nunca tilde verde, nunca rojo).

RESTRICCIÓN DURA (ver tests/test_equipos_comerciales.py): el S del
catálogo comercial NUNCA se escribe en Block.S.  Aquí solo se LEE para
verificar y mostrar.
"""
from __future__ import annotations

import json
import os
from typing import List, Optional

import equipment_costs as ec

_CATALOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "data", "equipos_comerciales.json")
_catalogo_cache = None

# Campos mecánicos que el simulador NO determina, por familia gruesa —
# van como lista corta "ingeniería de detalle pendiente", nunca celdas
# vacías (estimación conceptual Class 4/5, AACE).
_PENDIENTE_DETALLE = {
    "Heat exchangers": ["tipo TEMA", "espesores y bridas (ASME)",
                        "corrosion allowance"],
    "Vessels":   ["espesor de pared (ASME VIII)", "bocas y soportes"],
    "Reactors":  ["espesor de pared (ASME VIII)", "internos/agitador de detalle"],
    "Storage":   ["venteo y sello (API 650)", "espesores por virola"],
    "Pumps":     ["sello mecánico (API 682)", "plan de lubricación"],
    "Compressors": ["sellos y lubricación (API 617/618)"],
    "Turbines":  ["gobernador y trip (API 611/612)"],
    "Utilities": ["trim de control y seguridades"],
}


# ────────────────────────────────────────────────────────────
#  Catálogo comercial
# ────────────────────────────────────────────────────────────

def load_catalogo(force: bool = False) -> dict:
    """Carga (cacheada, defensiva) de data/equipos_comerciales.json."""
    global _catalogo_cache
    if _catalogo_cache is None or force:
        try:
            with open(_CATALOGO_PATH, encoding="utf-8") as f:
                _catalogo_cache = json.load(f)
        except Exception:
            _catalogo_cache = {"schema": 1, "equipos": []}
    return _catalogo_cache


def entradas_para(eq_type: str) -> List[dict]:
    """Entradas del catálogo comercial que parametrizan este eq_type."""
    return [e for e in load_catalogo().get("equipos", [])
            if e.get("eq_type") == eq_type]


def clave_de(entrada: dict) -> str:
    """Clave persistible de una entrada: 'marca|modelo' (el eq_type ya
    vive en el propio Block, no se duplica)."""
    return f"{entrada.get('marca', '')}|{entrada.get('modelo', '')}"


def entrada_de(block) -> Optional[dict]:
    """Resuelve Block.equipo_comercial ('marca|modelo') contra el
    catálogo, exigiendo además que el eq_type coincida."""
    ref = (getattr(block, "equipo_comercial", "") or "").strip()
    if not ref or "|" not in ref:
        return None
    marca, modelo = ref.split("|", 1)
    for e in entradas_para(block.eq_type):
        if e.get("marca") == marca and e.get("modelo") == modelo:
            return e
    return None


# ────────────────────────────────────────────────────────────
#  Verificación (modo selección)
# ────────────────────────────────────────────────────────────

def _eff_T_C(block, fs) -> Optional[float]:
    try:
        from flowsheet_solver import effective_temperature
        t_k = effective_temperature(fs, block)
        return (t_k - 273.15) if t_k and t_k > 0 else None
    except Exception:
        return None


def _eff_P_bar(block, fs) -> Optional[float]:
    try:
        from flowsheet_solver import effective_pressure
        return float(effective_pressure(fs, block))
    except Exception:
        return None


def _T_max_proceso_C(block, fs) -> Optional[float]:
    """T MÁXIMA de las corrientes de proceso del bloque (peor caso).

    La envolvente se verifica contra el peor caso, no contra el promedio:
    una turbina con vapor vivo a 400 °C y descarga a 183 °C promedia
    291 °C — y un límite de T_max se compara contra los 400 de entrada.
    (La presión ya lo hace bien: effective_pressure toma el máximo.)"""
    temps = [float(s.temperature) for s in fs.streams.values()
             if (s.src == block.id or s.dst == block.id)
             and not getattr(s, "auto_aux", False)
             and (s.role or "") not in ("utility", "ambient")
             and s.temperature is not None]
    if temps:
        return max(temps)
    return _eff_T_C(block, fs)


def _q_proceso_m3_h(block, fs) -> Optional[float]:
    """Caudal volumétrico del proceso donde el motor ya lo calcula
    (bomba: Q_m3_h; compresor/fan: Q succión).  None si no computable."""
    eq = (block.eq_type or "").lower()
    try:
        import equipment_design as ed
        if "pump" in eq or "bomba" in eq:
            res = ed.design_pump_for_block(block, fs)
            return float(res["Q_m3_h"]) if res else None
        if "compressor" in eq or "fan" in eq:
            res = ed.design_compressor_for_block(block, fs)
            return float(res["Q_in_m3_h"]) if res else None
    except Exception:
        pass
    return None


def _head_proceso_m(block, fs) -> Optional[float]:
    eq = (block.eq_type or "").lower()
    if "pump" not in eq and "bomba" not in eq:
        return None
    try:
        import equipment_design as ed
        res = ed.design_pump_for_block(block, fs)
        return float(res["head_m"]) if res else None
    except Exception:
        return None


def _checks_envolvente(block, fs, params: dict, familia: bool) -> List[dict]:
    """AND de desigualdades sobre los params de envolvente presentes y
    EVALUABLES (un param sin valor de proceso computable se omite — no
    se inventa el requerido)."""
    candidatos = [
        ("P_max_bar",  "Presión",     "bar",   _eff_P_bar(block, fs)),
        ("T_max_C",    "Temperatura", "°C",    _T_max_proceso_C(block, fs)),
        ("Q_max_m3_h", "Caudal",      "m³/h",  _q_proceso_m3_h(block, fs)),
        ("head_max_m", "Head",        "m",     _head_proceso_m(block, fs)),
    ]
    checks = []
    for key, label, unit, req in candidatos:
        lim = params.get(key)
        if lim is None or req is None:
            continue
        checks.append({
            "param": key, "label": label, "unidad": unit,
            "requerido": round(float(req), 2),
            "limite": round(float(lim), 2),
            "ok": float(req) <= float(lim),
            "familia": familia,
        })
    return checks


def verificacion(block, fs) -> dict:
    """Veredicto del modo selección para un bloque (ver estados arriba).

    Devuelve dict con: estado, apto (True/False/None), S_requerido,
    S_modelo, S_unit, utilizacion, checks[], granularidad, fuente,
    fecha_consulta, mensaje."""
    spec = ec.EQUIPMENT_DATA.get(block.eq_type, {})
    s_unit = spec.get("S_unit", "")
    disponibles = entradas_para(block.eq_type)
    base = {
        "estado": "no_aplica", "apto": None,
        "S_requerido": None, "S_modelo": None, "S_unit": s_unit,
        "utilizacion": None, "checks": [], "granularidad": None,
        "fuente": None, "fecha_consulta": None,
        "n_disponibles": len(disponibles), "mensaje": "",
    }
    if not disponibles and not (getattr(block, "equipo_comercial", "") or ""):
        base["mensaje"] = ("Ingeniería a pedido: ningún fabricante publica "
                          "tamaños de catálogo para este tipo.")
        return base
    entrada = entrada_de(block)
    if entrada is None:
        ref = (getattr(block, "equipo_comercial", "") or "").strip()
        if ref:
            base["estado"] = "desconocido"
            base["mensaje"] = (f"'{ref}' no está en el catálogo comercial "
                              f"para {block.eq_type} — entrada retirada o "
                              f"referencia inválida.")
        else:
            base["estado"] = "sin_declarar"
            base["mensaje"] = "Hay catálogo para este tipo; nada declarado."
        return base

    params = entrada.get("params") or {}
    base.update({
        "marca": entrada.get("marca"), "modelo": entrada.get("modelo"),
        "fuente": entrada.get("fuente"),
        "fecha_consulta": entrada.get("fecha_consulta"),
        "notas_catalogo": params.get("notas", ""),
    })
    s_req = float(getattr(block, "S", 0.0) or 0.0)
    base["S_requerido"] = round(s_req, 3) if s_req > 0 else None

    if "S" in entrada:
        s_mod = float(entrada["S"])
        checks = _checks_envolvente(block, fs, params, familia=False)
        base.update({"estado": "escalar", "S_modelo": s_mod,
                     "checks": checks})
        if s_req > 0:
            base["utilizacion"] = round(s_req / s_mod, 4)
            apto_s = s_req <= s_mod
            base["apto"] = apto_s and all(c["ok"] for c in checks)
            if not apto_s:
                base["mensaje"] = (f"El proceso exige {s_req:g} {s_unit} y "
                                   f"el modelo instala {s_mod:g} {s_unit}.")
            elif base["utilizacion"] < 0.35:
                pct = (1.0 - base["utilizacion"]) * 100.0
                base["mensaje"] = (f"Sobredimensionado: {pct:.0f}% de la "
                                   f"capacidad queda sin usar.")
        else:
            base["apto"] = None
            base["mensaje"] = ("Sin S requerido (bloque sin dimensionar): "
                              "resolver primero para verificar.")
        return base

    gran = entrada.get("granularidad")
    base["granularidad"] = gran
    if gran == "familia":
        checks = _checks_envolvente(block, fs, params, familia=True)
        base.update({"estado": "debil_familia", "checks": checks,
                     "apto": None})
        base["mensaje"] = ("Los límites son de toda la familia, no de este "
                          "tamaño: casi cualquier proceso entra — el "
                          "resultado confirma poco.")
        return base
    checks = _checks_envolvente(block, fs, params, familia=False)
    base.update({"estado": "envolvente_modelo", "checks": checks})
    base["apto"] = all(c["ok"] for c in checks) if checks else None
    base["mensaje"] = ("Sin ratio de utilización: el modelo no publica un "
                      "tamaño escalar; se verifica contra los límites del "
                      "modelo concreto.")
    return base


# ────────────────────────────────────────────────────────────
#  Ficha (contrato §4 — 8 secciones)
# ────────────────────────────────────────────────────────────

def _campo(key, label, value, unit="", origen="calculado", sub=""):
    return {"key": key, "label": label, "value": value, "unit": unit,
            "origen": origen, "sub": sub}


def _streams_de(block, fs, salida: bool):
    lst = []
    for s in fs.streams.values():
        if (s.src if salida else s.dst) != block.id:
            continue
        lst.append({
            "nombre": s.name,
            "puerto": (s.src_port if salida else s.dst_port) or "",
            "rol": s.role or "",
            "mass_flow_tm_a": round(float(s.mass_flow or 0.0), 3),
            "T_C": round(float(s.temperature or 0.0), 2),
            "P_bar": round(float(s.pressure_bar or 0.0), 3),
            "fase": s.phase or "",
            "comp_principal": s.main_component or "",
            "auto_aux": bool(getattr(s, "auto_aux", False)),
        })
    return sorted(lst, key=lambda d: d["nombre"])


def _campos_diseno(block, fs, categoria: str) -> List[dict]:
    """Campos ricos por categoría — TODOS desde resultados ya calculados
    (atributos runtime del solver / dicts de equipment_design)."""
    campos = []
    eq = (block.eq_type or "").lower()
    ga = lambda n, d=None: getattr(block, n, d)
    try:
        if categoria == "Heat exchangers":
            diag = ga("_hx_diagnostics") or {}
            if diag:
                org_u = ("calculado" if diag.get("data_source") ==
                         "computed_from_streams" else "tipico")
                campos += [
                    _campo("U", "U usado", diag.get("U_used"), "W/m²·K", org_u),
                    _campo("dTlm", "ΔT LMTD", diag.get("dTlm"), "°C"),
                    _campo("F", "F corrección", diag.get("F"), ""),
                    _campo("appr", "Approach", diag.get("approach"), "°C"),
                ]
        elif categoria == "Pumps":
            import equipment_design as ed
            ps = ed.design_pump_for_block(block, fs)
            if ps:
                campos += [
                    _campo("Q", "Caudal", round(ps["Q_m3_h"], 2), "m³/h"),
                    _campo("head", "Head", round(ps["head_m"], 2), "m"),
                    _campo("Welec", "W eléctrica", round(ps["W_elec_kW"], 2), "kW"),
                    _campo("NPSHa", "NPSH disponible", round(ps["NPSHa_m"], 2), "m"),
                ]
                if ps.get("cavitation_margin_m") is not None:
                    campos.append(_campo(
                        "margen", "Margen cavitación",
                        round(ps["cavitation_margin_m"], 2), "m"))
        elif categoria in ("Compressors", "Fans / blowers", "Turbines"):
            import equipment_design as ed
            cs = ed.design_compressor_for_block(block, fs)
            if cs:
                campos += [
                    _campo("ratio", "Ratio P_out/P_in", round(cs["ratio"], 3)),
                    _campo("stages", "Etapas", cs["n_stages"]),
                    _campo("Tout", "T descarga", round(cs["T_out_C"], 1), "°C"),
                    _campo("Wact", "W al eje", round(cs["W_act_kW"], 2), "kW"),
                ]
            elif (ga("duty", 0.0) or 0.0) < 0:
                campos.append(_campo("Wgen", "W generada",
                                     round(-float(block.duty), 2), "kW",
                                     sub="turbina/expansor (duty < 0)"))
        elif categoria == "Vessels" and ("tower" in eq or "column" in eq):
            for attr, key, label, unit in (
                    ("_column_N", "N", "Etapas teóricas", ""),
                    ("_column_R", "R", "Reflujo", ""),
                    ("_column_N_feed", "Nfeed", "Etapa de alimentación", ""),
                    ("_column_alpha_avg", "alpha", "α promedio", ""),
                    ("_Q_reb_kW", "Qreb", "Q reboiler", "kW"),
                    ("_Q_cond_kW", "Qcond", "Q condensador", "kW")):
                v = ga(attr)
                if v is not None:
                    campos.append(_campo(key, label,
                                         round(float(v), 3), unit))
        elif ga("flash_active", False):
            diag = ga("_flash_diagnostics") or {}
            if diag:
                campos.append(_campo("VF", "V/F molar",
                                     round(float(diag.get("V_frac", 0.0)), 4)))
        elif categoria == "Reactors":
            campos += [
                _campo("modo", "Modo", ga("reactor_mode", ""), "",
                       "declarado"),
                _campo("conv", "Conversión",
                       round(float(ga("reactor_conversion", 0.0) or 0.0), 3),
                       "", "declarado"),
            ]
            if (ga("heat_of_reaction", 0.0) or 0.0) != 0.0:
                campos.append(_campo("dHrx", "ΔH reacción",
                                     round(float(block.heat_of_reaction), 2),
                                     "kJ/kg"))
        elif categoria == "Utilities" and "boiler" in eq:
            campos.append(_campo("eta", "η caldera",
                                 ga("efficiency", 0.0) or 0.0, "",
                                 "declarado"))
    except Exception:
        pass
    return [c for c in campos if c["value"] is not None]


def datasheet_spec(block, fs) -> dict:
    """La ficha completa de UN bloque (contrato §4, Qt-free).

    Nunca lanza: cada sección degrada a su mínimo si falta un dato.  El
    fallback (identidad + condiciones + corrientes + S + costo) existe
    para los 60 tipos del catálogo."""
    spec = ec.EQUIPMENT_DATA.get(block.eq_type, {})
    categoria = spec.get("categoria", "")
    s_unit = spec.get("S_unit", "")
    ent = entrada_de(block)

    identidad = {
        "tag": block.name, "eq_type": block.eq_type,
        "categoria": categoria, "n_paralelo": int(getattr(block, "n", 1) or 1),
        "marca": ent.get("marca") if ent else None,
        "modelo": ent.get("modelo") if ent else None,
    }
    t_c = _eff_T_C(block, fs)
    p_bar = _eff_P_bar(block, fs)
    entradas = _streams_de(block, fs, salida=False)
    salidas = _streams_de(block, fs, salida=True)
    condiciones = {
        "T_op_C": round(t_c, 2) if t_c is not None else None,
        "P_op_bar": round(p_bar, 3) if p_bar is not None else None,
        "duty_kW": round(float(getattr(block, "duty", 0.0) or 0.0), 3),
        "delta_p_bar": float(getattr(block, "delta_p_bar", 0.0) or 0.0),
        "fases": sorted({s["fase"] for s in entradas + salidas if s["fase"]}),
    }

    s_val = float(getattr(block, "S", 0.0) or 0.0)
    diseno = [_campo("S", spec.get("S_param", "Tamaño S"),
                     round(s_val, 3) if s_val else None, s_unit,
                     "declarado" if getattr(block, "S_locked", False)
                     else "calculado")]
    diseno += _campos_diseno(block, fs, categoria)

    material = (getattr(block, "material", "") or "").strip()
    origen_mat = "declarado"
    if not material:
        origen_mat = "estimado"
        try:
            comps = [s.composition or {} for s in fs.streams.values()
                     if s.src == block.id or s.dst == block.id]
            material = ec.suggested_material(comps, p_bar or 1.0,
                                             block.eq_type)
        except Exception:
            material = "CS"
    materiales = {"material": material, "origen": origen_mat,
                  "FM": ec.MATERIAL_FACTORS.get(material, 1.0)}

    auxiliares = []
    try:
        from equipment_auxiliaries import AUX_STREAMS
        for a in AUX_STREAMS.get(block.eq_type, []):
            auxiliares.append({
                "puerto": a.port_name, "direccion": a.direction,
                "fase": a.phase, "utility": a.utility_key or "",
                "rol": a.role, "lazo": a.cycle_id or "",
            })
    except Exception:
        pass

    costos = {}
    try:
        if s_val > 0 and block.eq_type in ec.EQUIPMENT_DATA:
            r = ec.bare_module_cost(block.eq_type, s_val,
                                    P_op_bar=p_bar or 1.0,
                                    material=material)
            costos = {"correlacion": spec.get("correlation", "turton"),
                      "source": spec.get("source", ""),
                      "Cp_target": round(r["Cp_target"], 0),
                      "year_target": r["year_target"],
                      "FBM": round(r["FBM"], 3), "FP": round(r["FP"], 3),
                      "CBM": round(r["CBM"], 0),
                      "fuera_rango": bool(r["fuera_rango"])}
    except Exception:
        pass

    warnings = []
    diag = getattr(block, "_hx_diagnostics", None) or {}
    warnings += list(diag.get("warnings", []) or [])[:3]
    if costos.get("fuera_rango"):
        warnings.append(f"S={s_val:g} {s_unit} fuera del rango de la "
                        f"correlación — costo extrapolado.")
    notas = {
        "warnings": warnings,
        "fuentes": [spec.get("source", "")] if spec.get("source") else [],
        "pendiente_detalle": _PENDIENTE_DETALLE.get(categoria, []),
    }

    return {
        "schema": 1,
        "identidad": identidad,
        "condiciones": condiciones,
        "corrientes": {"in": entradas, "out": salidas},
        "diseno": diseno,
        "materiales": materiales,
        "auxiliares": auxiliares,
        "costos": costos,
        "notas": notas,
        "verificacion": verificacion(block, fs),
    }
