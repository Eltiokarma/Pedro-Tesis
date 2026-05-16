"""
FLOWSHEET EXPORT — funciones puras para exportar el flowsheet al
formato xlsx que consume ANA.py (análisis económico).

Sin dependencias de UI.  Lo importan tanto el editor Tk como el Qt.

API pública:

  collect_equipment_rows(fs)            → lista de dicts con info de equipos
  compute_utilities_from_duties(fs)     → (rows_para_df_variable, summary)
  read_project_xlsx(path)               → (df_capital, df_fixed, df_variable)
  write_project_xlsx(path, fs, isbl,
                     feeds, products,
                     base_xlsx=None)    → genera xlsx temporal con:
                                            · capital con ISBL inyectado
                                            · fixed con labor Turton o override
                                            · variable con feeds+products+
                                              opex_extras+utilities auto

Las filas inyectadas se marcan con sufijo:
  '(PFD)'      → feeds, products, opex_extras manuales
  '(PFD-util)' → utilities auto-calculadas desde duties

El dedupe regenera ambas categorías cada vez.
"""

import math
import pandas as pd

import equipment_costs as eq
import equipment_ports as ep
import templates as tmpl


# ======================================================
# EQUIPOS DEL PFD
# ======================================================

def collect_equipment_rows(fs, year_target=2026):
    """Lista de dicts con la info de cada bloque del PFD, para
    escribir como pestaña 'Equipment' en el xlsx.

    Incluye specs operacionales (T_op, P_op, duty, ΔP, η) y de unit
    op (reacciones, column LK/HK, flash T/P, splitter fractions) +
    COSTING TURTON por equipo individual (Cp escalado a year_target,
    FBM con factor de presión, CBM = Cp × FBM).

    El analista económico ve TODO el contexto del diseño y puede
    identificar qué equipos dominan el capital sin recomputar nada.
    """
    rows = []
    for b in sorted(fs.blocks.values(), key=lambda b: b.name):
        spec = eq.EQUIPMENT_DATA.get(b.eq_type, {})
        # Costing Turton individual
        cp_usd, fbm, cbm = 0.0, 0.0, 0.0
        fuera_rango = False
        try:
            p_op = float(getattr(b, "P_op_bar", 0.0) or 0.0) or 1.0
            res = eq.bare_module_cost(b.eq_type, b.S, P_op_bar=p_op,
                                       year_target=year_target)
            cp_usd      = res["Cp_target"] * b.n
            cbm         = res["CBM"] * b.n
            fbm         = res["FBM"]
            fuera_rango = res["fuera_rango"]
        except Exception:
            pass

        row = {
            "Tag":        b.name,
            "Type":       b.eq_type,
            "Category":   spec.get("categoria", ""),
            "Size S":     float(b.S),
            "Unit":       spec.get("S_unit", ""),
            "N° units":   int(b.n),
            "Duty kW":    float(getattr(b, "duty", 0.0)),
            "T_op K":     float(getattr(b, "T_op_K", 0.0) or 0.0),
            "P_op bar":   float(getattr(b, "P_op_bar", 0.0) or 0.0),
            "ΔP bar":     float(getattr(b, "delta_p_bar", 0.0) or 0.0),
            "η":          float(getattr(b, "efficiency", 0.0) or 0.0),
            "Reactions":  ",".join(getattr(b, "reactions", []) or []),
            "Heat source": str(getattr(b, "heat_source", "") or ""),
            # ── Costing Turton (CEPCI year_target) ──
            f"Cp USD ({year_target})":  cp_usd,
            "FBM":                      fbm,
            f"CBM USD ({year_target})": cbm,
            "S fuera rango":            "⚠" if fuera_rango else "",
        }
        # Column specs (FUG-resueltos por solve_columns)
        if getattr(b, "column_active", False):
            row["Column LK"]  = str(getattr(b, "column_LK", "") or "")
            row["Column HK"]  = str(getattr(b, "column_HK", "") or "")
            row["Column R"]   = float(getattr(b, "_column_R", 0.0) or 0.0)
            row["Column N"]   = float(getattr(b, "_column_N", 0.0) or 0.0)
            row["Q_reb kW"]   = float(getattr(b, "_column_Q_reb", 0.0) or 0.0)
            row["Q_cond kW"]  = float(getattr(b, "_column_Q_cond", 0.0) or 0.0)
        # Flash specs
        if getattr(b, "flash_active", False):
            row["Flash T K"]  = float(getattr(b, "flash_T_K", 0.0) or 0.0)
            row["Flash P bar"]= float(getattr(b, "flash_P_bar", 0.0) or 0.0)
        # Splitter fractions
        fracs = getattr(b, "splitter_fractions", None) or []
        if fracs:
            row["Splitter fracs"] = ",".join(f"{f:.3f}" for f in fracs)
        rows.append(row)
    return rows


def compute_turton_costing(fs, df_variable, df_fixed, fci_musd,
                            year_target=2026):
    """Calcula resumen de costing tipo Turton para escribir como
    pestaña 'Costing Turton' del xlsx.

    Reúne:
      · ΣCBM por categoría (capital bare module breakdown)
      · CRM (Cost of Raw Materials) = Σ price·flowrate de Raw Materials
      · CUT (Cost of Utilities)     = Σ de Utilities
      · CWT (Cost of Waste Treatment) = Σ price·flowrate negativos
                                         o positivos de Waste/Byproduct
      · COL (Cost of Operating Labor) = del df_fixed
      · COM_d / COM Turton Eq 8.2

    Returns:
        dict {summary, by_category, totals} listos para serializar.
    """
    # CBM agregado por categoría
    by_cat = {}     # categoria → (cbm_usd, n_equipos)
    sum_cp = 0.0
    sum_cbm = 0.0
    for b in fs.blocks.values():
        spec = eq.EQUIPMENT_DATA.get(b.eq_type, {})
        cat  = spec.get("categoria", "Otros")
        p_op = float(getattr(b, "P_op_bar", 0.0) or 0.0) or 1.0
        try:
            res = eq.bare_module_cost(b.eq_type, b.S, P_op_bar=p_op,
                                       year_target=year_target)
            cp  = res["Cp_target"] * b.n
            cbm = res["CBM"]      * b.n
            by_cat.setdefault(cat, [0.0, 0])
            by_cat[cat][0] += cbm
            by_cat[cat][1] += 1
            sum_cp  += cp
            sum_cbm += cbm
        except Exception:
            continue

    # CRM, CUT, CWT desde df_variable
    crm = cut = cwt = 0.0
    if df_variable is not None and not df_variable.empty:
        for _, row in df_variable.iterrows():
            stream = str(row.get("stream", "")).strip()
            flow   = float(row.get("flowrate", 0.0) or 0.0)
            price  = float(row.get("price usd/units", 0.0) or 0.0)
            cost   = flow * price
            if stream == "Raw Materials":
                crm += cost
            elif stream == "Utilities":
                cut += cost
            elif stream == "Waste / Byproduct":
                # Convención: price>0 → byproduct vendible (resta como
                # ingreso; en CWT contamos solo treatment cost positivo).
                # Para simplicidad, tomamos |precio|·flow como overhead.
                # Si el user pone price<0, eso ya cuenta como gasto.
                cwt += abs(cost) if price < 0 else 0.0

    # COL desde df_fixed (fila Labor)
    col = 0.0
    if df_fixed is not None and not df_fixed.empty \
       and "Concept" in df_fixed.columns:
        mask = df_fixed["Concept"].astype(str).str.strip() == "Labor"
        if mask.any():
            col = float(df_fixed.loc[mask, "Value"].iloc[0] or 0.0)

    fci_usd = fci_musd * 1e6 if fci_musd else sum_cbm
    com = eq.cost_of_manufacture(
        FCI_usd=fci_usd, COL_usd=col,
        CUT_usd=cut, CRM_usd=crm, CWT_usd=cwt,
    )

    # Build rows
    rows = []
    rows.append(("CAPITAL — Bare Module Cost by Category", "", ""))
    for cat, (cbm, n) in sorted(by_cat.items(),
                                   key=lambda kv: -kv[1][0]):
        rows.append((f"  · {cat}", f"{n} equipo(s)",
                      f"{cbm:>14,.0f} USD"))
    rows.append(("  Σ Cp purchased (FOB)", "",
                  f"{sum_cp:>14,.0f} USD"))
    rows.append(("  Σ CBM bare module",    "",
                  f"{sum_cbm:>14,.0f} USD"))
    rows.append(("  FCI usado",            "",
                  f"{fci_usd:>14,.0f} USD"))
    rows.append(("", "", ""))
    rows.append(("OPEX COMPONENTS (USD/year)", "", ""))
    rows.append(("  CRM (Raw Materials)",   "",
                  f"{crm:>14,.0f} USD/yr"))
    rows.append(("  CUT (Utilities)",       "",
                  f"{cut:>14,.0f} USD/yr"))
    rows.append(("  CWT (Waste Treatment)", "",
                  f"{cwt:>14,.0f} USD/yr"))
    rows.append(("  COL (Operating Labor)", "",
                  f"{col:>14,.0f} USD/yr"))
    rows.append(("", "", ""))
    rows.append(("COST OF MANUFACTURE (Turton Eq 8.2)", "", ""))
    rows.append(("  0.180·FCI",               "",
                  f"{com['0.180·FCI']:>14,.0f}"))
    rows.append(("  2.73·COL",                "",
                  f"{com['2.73·COL']:>14,.0f}"))
    rows.append(("  1.23·(CUT+CRM+CWT)",       "",
                  f"{com['1.23·(CUT+CRM+CWT)']:>14,.0f}"))
    rows.append(("  COM_d (con depreciación)","",
                  f"{com['COM_d']:>14,.0f} USD/yr"))
    rows.append(("  COM   (sin depreciación)","",
                  f"{com['COM']:>14,.0f} USD/yr"))
    rows.append(("", "", ""))
    rows.append(("Año CEPCI", "", str(year_target)))
    rows.append(("Año base Turton", "", "2001 (CEPCI=397)"))

    return {
        "rows":       rows,
        "by_category": by_cat,
        "sum_cp":     sum_cp,
        "sum_cbm":    sum_cbm,
        "fci":        fci_usd,
        "col":        col,
        "crm":        crm,
        "cut":        cut,
        "cwt":        cwt,
        "com":        com,
    }


def collect_stream_rows(fs):
    """Lista de dicts con TODA la data de cada stream, para pestaña
    'Streams' del xlsx.  Incluye masa, T, P, fase, composiciones,
    pipe specs, role y precio."""
    rows = []
    # Componentes únicos para columnas wt% — solo los que aparecen en
    # ≥ 1 stream con composition_locked o computado por el solver.
    comps = set()
    for s in fs.streams.values():
        comps.update((s.composition or {}).keys())
    comps = sorted(comps)

    for s in sorted(fs.streams.values(), key=lambda x: x.name):
        b_src = fs.blocks.get(s.src)
        b_dst = fs.blocks.get(s.dst)
        row = {
            "Stream":     s.name,
            "From":       b_src.name if b_src else "",
            "From port":  s.src_port or "",
            "To":         b_dst.name if b_dst else "",
            "To port":    s.dst_port or "",
            "Mass kg/h":  float(s.mass_flow),
            "T °C":       float(s.temperature),
            "P bar":      float(getattr(s, "pressure_bar", 0.0) or 0.0),
            "Phase":      s.phase or "",
            "Role":       s.role or "",
            "Price USD/tm": float(getattr(s, "price_usd_per_tm", 0.0) or 0.0),
            "Cp kJ/kg·K": float(getattr(s, "cp", 0.0) or 0.0),
            "Main comp":  s.main_component or "",
            "Locks":      ",".join([
                k.replace("_locked", "")
                for k in ("mass_flow_locked","temperature_locked",
                           "composition_locked","pressure_locked")
                if getattr(s, k, False)
            ]),
            "Pipe L m":   float(getattr(s, "pipe_length_m", 0.0) or 0.0),
            "Pipe D m":   float(getattr(s, "pipe_diameter_m", 0.0) or 0.0),
            "Pipe ΔP bar":float(getattr(s, "delta_p_pipe_bar", 0.0) or 0.0),
        }
        # Composición wt% por componente
        comp = s.composition or {}
        for c in comps:
            row[f"wt% {c}"] = float(comp.get(c, 0.0))
        rows.append(row)
    return rows


# ======================================================
# T PROMEDIO POR BLOQUE (para autoselect de utility)
# ======================================================

def block_avg_temperature(fs, block_id, t_ref=25.0):
    """T promedio (°C) entre entradas y salidas del bloque."""
    ts = []
    for s in fs.streams.values():
        if (s.src == block_id or s.dst == block_id) and s.cp > 0:
            ts.append(s.temperature)
    if not ts:
        return t_ref
    return sum(ts) / len(ts)


# ======================================================
# UTILITIES AUTO-CALCULADAS DESDE DUTIES
# ======================================================

def compute_utilities_from_duties(fs):
    """Para cada bloque con duty != 0, autoselect de utility +
    consumo + costo, agrupados por tipo.

    Returns:
      (rows, summary)
        rows: list of dicts compatibles con opex_extras
        summary: list of (block_name, util_key, units, cons, cost)
                 para mostrar en el panel de resultados
    """
    rows = []
    summary = []
    agg = {}

    # detección de cross-exchange (HX proceso-proceso) — no carga utility
    try:
        from flowsheet_solver import is_cross_exchange
    except ImportError:
        is_cross_exchange = lambda fs, b: False

    for b in fs.blocks.values():
        if b.duty == 0:
            continue
        if is_cross_exchange(fs, b):
            # heat integration: el calor lo entrega otra corriente del
            # proceso, no una utility.  Reporte informativo, sin costo.
            continue
        T_avg = block_avg_temperature(fs, b.id)
        util_key = b.heat_source or ep.autoselect_heat_source(
            b.eq_type, b.duty, T_avg
        )
        if not util_key or util_key not in ep.UTILITIES:
            continue
        util = ep.UTILITIES[util_key]
        consumption = ep.utility_consumption(util_key, b.duty)
        cost = consumption * util["price"]
        summary.append((b.name, util_key, util["units"],
                        consumption, cost))
        if util_key in agg:
            agg[util_key] = (
                agg[util_key][0] + consumption,
                agg[util_key][1] + cost,
            )
        else:
            agg[util_key] = (consumption, cost)

    for util_key, (cons, _cost) in agg.items():
        util = ep.UTILITIES[util_key]
        rows.append({
            "name":               f"{util['name']} (PFD-util)",
            "units":              util["units"],
            "time_basis":         "year",
            "flowrate":           float(cons),
            "price_usd_per_unit": float(util["price"]),
            "stream":             "Utilities",
        })
    return rows, summary


# ======================================================
# AUTO-SIZING DE BLOQUES UTILITY (boiler / cooling tower)
# ======================================================
# Si el user pone un Boiler block en el flowsheet, se dimensiona
# automáticamente con la suma de todas las demandas de steam del proceso.
# Idem cooling tower con la suma de cooling water duty.
#
# Una vez sizeado, el CAPEX se calcula con la correlación Turton
# (equipment_costs.EQUIPMENT_DATA del eq_type).

def aggregate_utility_demand(fs):
    """Suma duties de todos los bloques del proceso por tipo de utility.

    Returns:
        dict {util_key: total_duty_kw}
        Ej: {'steam_LP': 1500.0, 'cooling_water': -3200.0, 'fuel_gas': 5000.0}
    """
    # local import para evitar ciclo
    from flowsheet_solver import is_cross_exchange
    import equipment_ports as _ep

    agg = {}
    for b in fs.blocks.values():
        # los blocks utility (boiler/cooling tower) NO son demanda, son oferta.
        cat = None
        try:
            import equipment_costs as _eq
            cat = _eq.EQUIPMENT_DATA.get(b.eq_type, {}).get("categoria")
        except ImportError:
            pass
        if cat == "Utilities":
            continue
        if b.duty == 0:
            continue
        if is_cross_exchange(fs, b):
            continue
        T_avg = block_avg_temperature(fs, b.id)
        util_key = b.heat_source or _ep.autoselect_heat_source(
            b.eq_type, b.duty, T_avg
        )
        if not util_key:
            continue
        agg[util_key] = agg.get(util_key, 0.0) + abs(b.duty)
    return agg


def auto_size_utility_blocks(fs):
    """Para cada bloque del tipo Utilities en el flowsheet, asigna su
    `S` (capacidad) en función de la demanda total del proceso.

    - Boiler: total steam demand en kg/s (de steam_LP + MP + HP).
    - Cooling tower: total cooling demand en MW.

    No toca otros campos.  Devuelve dict {block_id: (S, S_unit)}.
    """
    import equipment_costs as _eq
    demand = aggregate_utility_demand(fs)

    # Mapear total demand a las unidades del catálogo
    # Steam: kg/s = kW / (ΔH_vap en kJ/kg).  Promedio ~2200 kJ/kg.
    steam_total_kw = (demand.get("steam_LP", 0)
                      + demand.get("steam_MP", 0)
                      + demand.get("steam_HP", 0)
                      + demand.get("fuel_gas", 0))
    steam_kg_s = steam_total_kw / 2200.0 if steam_total_kw > 0 else 0.0
    # Cooling: MW = kW / 1000
    cooling_mw = demand.get("cooling_water", 0) / 1000.0
    if "refrigeration" in demand:
        cooling_mw += demand["refrigeration"] / 1000.0

    sized = {}
    for b in fs.blocks.values():
        cat = _eq.EQUIPMENT_DATA.get(b.eq_type, {}).get("categoria")
        if cat != "Utilities":
            continue
        S_unit = _eq.EQUIPMENT_DATA[b.eq_type].get("S_unit", "")
        if b.eq_type.startswith("Boiler") and steam_kg_s > 0:
            b.S = max(steam_kg_s, 0.1)
            sized[b.id] = (b.S, S_unit)
        elif b.eq_type.startswith("Cooling tower") and cooling_mw > 0:
            b.S = max(cooling_mw, 0.1)
            sized[b.id] = (b.S, S_unit)
    return sized


# ======================================================
# LEER XLSX EXISTENTE (formato ANA.py)
# ======================================================

def read_project_xlsx(path):
    """Lee un xlsx del análisis económico y devuelve (df_capital,
    df_fixed, df_variable).  Replica la lógica de
    ANA.ImportarProyecto sin sus side-effects de UI."""
    df_raw = pd.read_excel(path, header=None)

    def _section(cols):
        df = df_raw.iloc[:, cols].copy()
        df = df.dropna(how="all")
        if df.empty:
            return df
        df.columns = df.iloc[0].tolist()
        df = df.iloc[1:].reset_index(drop=True)
        df = df[df.iloc[:, 0].notna()].reset_index(drop=True)
        return df

    df_capital  = _section([0, 1, 2])
    df_fixed    = _section([4, 5, 6])
    df_variable = _section([8, 9, 10, 11, 12, 13])
    return df_capital, df_fixed, df_variable


# ======================================================
# ESCRIBIR XLSX (compatible con ANA.ImportarProyecto)
# ======================================================

def write_3sections_xlsx(path, df_capital, df_fixed, df_variable,
                         equipment=None, streams=None, costing=None):
    """Escribe un xlsx con las 3 secciones lado a lado:
      cols A-C  → Capital Costs
      col  D    → vacía
      cols E-G  → Fixed Operating Costs
      col  H    → vacía
      cols I-N  → Variable Operating Costs

    Pestañas adicionales:
      'Equipment'  → tag, type, S, duty, T_op, P_op, ΔP, η, reactions,
                     column/flash/splitter specs (cuando aplique)
      'Streams'    → todas las corrientes con mass, T, P, fase,
                     composición wt% por componente, role, precio,
                     pipe specs y locks del user
    Ambas pestañas se generan automáticamente desde el flowsheet,
    así el analista económico ve TODO el contexto del diseño en el
    mismo xlsx."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Project"

    def _write_block(df, col_start):
        if df is None or df.empty:
            return
        for j, name in enumerate(df.columns):
            ws.cell(row=1, column=col_start + j, value=str(name))
        for i in range(len(df)):
            for j in range(len(df.columns)):
                v = df.iat[i, j]
                if v is None:
                    continue
                try:
                    if isinstance(v, float) and math.isnan(v):
                        continue
                except Exception:
                    pass
                ws.cell(row=2 + i, column=col_start + j, value=v)

    _write_block(df_capital,  1)
    _write_block(df_fixed,    5)
    _write_block(df_variable, 9)

    if equipment:
        ws_eq = wb.create_sheet("Equipment")
        # Cols dinámicas: union de todas las keys que aparecen en rows
        # (algunos bloques tienen specs de columna, otros no)
        base_cols = ["Tag", "Type", "Category", "Size S", "Unit", "N° units",
                       "Duty kW", "T_op K", "P_op bar", "ΔP bar", "η",
                       "Reactions", "Heat source"]
        extra_keys = []
        for row in equipment:
            for k in row.keys():
                if k not in base_cols and k not in extra_keys:
                    extra_keys.append(k)
        cols = base_cols + extra_keys
        for j, name in enumerate(cols):
            ws_eq.cell(row=1, column=j + 1, value=name)
        for i, row in enumerate(equipment):
            for j, key in enumerate(cols):
                v = row.get(key, "")
                if isinstance(v, float) and v == 0.0:
                    v = ""    # cell vacío en lugar de 0 ruidoso
                ws_eq.cell(row=2 + i, column=j + 1, value=v)

    if costing and costing.get("rows"):
        ws_c = wb.create_sheet("Costing Turton")
        ws_c.cell(row=1, column=1, value="Concepto")
        ws_c.cell(row=1, column=2, value="Detalle")
        ws_c.cell(row=1, column=3, value="Valor")
        for i, (a, b, c) in enumerate(costing["rows"]):
            ws_c.cell(row=2 + i, column=1, value=a)
            ws_c.cell(row=2 + i, column=2, value=b)
            ws_c.cell(row=2 + i, column=3, value=c)
        ws_c.column_dimensions["A"].width = 38
        ws_c.column_dimensions["B"].width = 18
        ws_c.column_dimensions["C"].width = 28

    if streams:
        ws_s = wb.create_sheet("Streams")
        # Cols dinámicas (wt% por componente varía por proyecto)
        base_cols = ["Stream", "From", "From port", "To", "To port",
                       "Mass kg/h", "T °C", "P bar", "Phase", "Role",
                       "Price USD/tm", "Cp kJ/kg·K", "Main comp", "Locks",
                       "Pipe L m", "Pipe D m", "Pipe ΔP bar"]
        extra_keys = []
        for row in streams:
            for k in row.keys():
                if k not in base_cols and k not in extra_keys:
                    extra_keys.append(k)
        cols = base_cols + extra_keys
        for j, name in enumerate(cols):
            ws_s.cell(row=1, column=j + 1, value=name)
        for i, row in enumerate(streams):
            for j, key in enumerate(cols):
                v = row.get(key, "")
                if isinstance(v, float) and v == 0.0:
                    v = ""
                ws_s.cell(row=2 + i, column=j + 1, value=v)

    wb.save(path)


def write_project_xlsx(path, fs, isbl, feeds, products, base_xlsx=None):
    """Genera el xlsx que ANA.py importa.

      path:         destino del xlsx
      fs:           Flowsheet (para opex_extras, fixed_overrides,
                    equipment list, utilities desde duties)
      isbl:         ISBL en MM USD a inyectar en df_capital[0,2]
      feeds:        lista de Stream con role='feed'
      products:     lista de Stream con role='product'
      base_xlsx:    si se da, se carga ese xlsx como base (preservando
                    filas variables que el user editó a mano)
                    Si None, se usan templates Turton.
    """
    if base_xlsx:
        df_capital, df_fixed, df_variable = read_project_xlsx(base_xlsx)
    else:
        df_capital  = tmpl.template_capital()
        df_fixed    = tmpl.template_fixed()
        df_variable = pd.DataFrame(columns=[
            "variable operating costs", "units", "time basis",
            "flowrate", "price usd/units", "stream",
        ])

    # inyectar ISBL
    if isbl is not None and not df_capital.empty:
        df_capital.iat[0, 2] = float(isbl)

    # fixed overrides (Labor manual del user, etc.)
    if (not df_fixed.empty and "Concept" in df_fixed.columns
            and fs.fixed_overrides):
        for concept, value in fs.fixed_overrides.items():
            mask = df_fixed["Concept"].astype(str).str.strip() == concept
            if mask.any():
                df_fixed.loc[mask, "Value"] = float(value)

    # auto-labor con Turton §8.3 si no hay override
    if (not df_fixed.empty and "Concept" in df_fixed.columns
            and "Labor" not in fs.fixed_overrides
            and fs.blocks):
        labor_info = ep.turton_labor_cost(fs.blocks.values())
        mask = df_fixed["Concept"].astype(str).str.strip() == "Labor"
        if mask.any():
            df_fixed.loc[mask, "Value"] = float(labor_info["labor_usd_yr"])

    # dedupe: borrar filas previas marcadas '(PFD)' o '(PFD-util)'
    if "variable operating costs" in df_variable.columns:
        mask = df_variable["variable operating costs"].astype(str).str.contains(
            r"\(PFD(?:-util)?\)", regex=True, na=False
        )
        df_variable = df_variable[~mask].reset_index(drop=True)

    # append filas (PFD): products, feeds, wastes, utility streams,
    # opex_extras manuales.  TODOS los streams con price != 0 (o role
    # explícito) se contabilizan — antes solo feed/product se exportaban.
    new_rows = []
    seen_ids = set()
    for s in products:
        new_rows.append({
            "variable operating costs": f"{s.name} (PFD)",
            "units":              "tm",
            "time basis":         "year",
            "flowrate":           float(s.mass_flow),
            "price usd/units":    float(getattr(s, "price_usd_per_tm", 0.0)),
            "stream":             "Key Products",
        })
        seen_ids.add(s.id)
    for s in feeds:
        new_rows.append({
            "variable operating costs": f"{s.name} (PFD)",
            "units":              "tm",
            "time basis":         "year",
            "flowrate":           float(s.mass_flow),
            "price usd/units":    float(getattr(s, "price_usd_per_tm", 0.0)),
            "stream":             "Raw Materials",
        })
        seen_ids.add(s.id)
    # Wastes — costos de disposición / byproducts vendibles.
    # En Talara: coque, slurry, gas seco (todos role='product' o
    # 'waste' con price > 0).  Antes los wastes con price>0 se
    # perdían silenciosamente.
    for s in fs.streams.values():
        if s.id in seen_ids:
            continue
        if s.role == "waste":
            new_rows.append({
                "variable operating costs": f"{s.name} (PFD waste)",
                "units":              "tm",
                "time basis":         "year",
                "flowrate":           float(s.mass_flow),
                # waste con price>0: ingreso (subproducto vendible)
                # waste con price<0: gasto (tratamiento)
                # waste con price=0: ignored en NPV pero queda registrado
                "price usd/units":    float(getattr(s, "price_usd_per_tm", 0.0)),
                "stream":             "Waste / Byproduct",
            })
            seen_ids.add(s.id)
    # Utility streams declarados como feed externo (BFW, fuel gas,
    # H2SO4 secado, etc.) — antes se ignoraban si role='utility'.
    for s in fs.streams.values():
        if s.id in seen_ids:
            continue
        if s.role == "utility":
            # Solo si entra al proceso desde un tanque source (no
            # interno) — para evitar doble-conteo con auto-utilities
            # que se calculan desde duty.  Marca con price>0 (compra).
            src_b = fs.blocks.get(s.src)
            is_external_feed = (src_b is not None
                                and "Storage tank" in (src_b.eq_type or ""))
            if is_external_feed and s.price_usd_per_tm > 0:
                new_rows.append({
                    "variable operating costs": f"{s.name} (PFD utility)",
                    "units":              "tm",
                    "time basis":         "year",
                    "flowrate":           float(s.mass_flow),
                    "price usd/units":    float(s.price_usd_per_tm),
                    "stream":             "Utilities",
                })
                seen_ids.add(s.id)
    for ex in fs.opex_extras:
        new_rows.append({
            "variable operating costs": f"{ex.get('name','?')} (PFD)",
            "units":              ex.get("units", "tm"),
            "time basis":         ex.get("time_basis", "year"),
            "flowrate":           float(ex.get("flowrate", 0.0)),
            "price usd/units":    float(ex.get("price_usd_per_unit", 0.0)),
            "stream":             ex.get("stream", "Utilities"),
        })

    # utilities (PFD-util) auto-calculadas desde duties
    auto_rows, _summary = compute_utilities_from_duties(fs)
    for ex in auto_rows:
        new_rows.append({
            "variable operating costs": ex["name"],
            "units":              ex["units"],
            "time basis":         ex["time_basis"],
            "flowrate":           ex["flowrate"],
            "price usd/units":    ex["price_usd_per_unit"],
            "stream":             ex["stream"],
        })

    if new_rows:
        df_variable = pd.concat(
            [df_variable, pd.DataFrame(new_rows)],
            ignore_index=True,
        )

    # escribir xlsx con 3 secciones + pestañas Equipment, Streams,
    # Costing Turton (resumen CBM por categoría + COM Eq 8.2)
    equipment_rows = collect_equipment_rows(fs, year_target=2026)
    stream_rows    = collect_stream_rows(fs)
    costing_data   = compute_turton_costing(
        fs, df_variable, df_fixed, fci_musd=isbl, year_target=2026)
    write_3sections_xlsx(path, df_capital, df_fixed, df_variable,
                         equipment=equipment_rows,
                         streams=stream_rows,
                         costing=costing_data)
