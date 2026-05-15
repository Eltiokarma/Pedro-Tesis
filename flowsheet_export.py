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

def collect_equipment_rows(fs):
    """Lista de dicts con la info de cada bloque del PFD, para
    escribir como pestaña 'Equipment' en el xlsx."""
    rows = []
    for b in sorted(fs.blocks.values(), key=lambda b: b.name):
        spec = eq.EQUIPMENT_DATA.get(b.eq_type, {})
        rows.append({
            "Tag":        b.name,
            "Type":       b.eq_type,
            "Category":   spec.get("categoria", ""),
            "Size S":     float(b.S),
            "Unit":       spec.get("S_unit", ""),
            "N° units":   int(b.n),
        })
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
                         equipment=None):
    """Escribe un xlsx con las 3 secciones lado a lado:
      cols A-C  → Capital Costs
      col  D    → vacía
      cols E-G  → Fixed Operating Costs
      col  H    → vacía
      cols I-N  → Variable Operating Costs
    Más una pestaña opcional 'Equipment' con la lista de equipos."""
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
        cols = ["Tag", "Type", "Category", "Size S", "Unit", "N° units"]
        for j, name in enumerate(cols):
            ws_eq.cell(row=1, column=j + 1, value=name)
        for i, row in enumerate(equipment):
            for j, key in enumerate(cols):
                ws_eq.cell(row=2 + i, column=j + 1, value=row.get(key, ""))

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

    # append filas (PFD): products, feeds, opex_extras manuales
    new_rows = []
    for s in products:
        new_rows.append({
            "variable operating costs": f"{s.name} (PFD)",
            "units":              "tm",
            "time basis":         "year",
            "flowrate":           float(s.mass_flow),
            "price usd/units":    float(getattr(s, "price_usd_per_tm", 0.0)),
            "stream":             "Key Products",
        })
    for s in feeds:
        new_rows.append({
            "variable operating costs": f"{s.name} (PFD)",
            "units":              "tm",
            "time basis":         "year",
            "flowrate":           float(s.mass_flow),
            "price usd/units":    float(getattr(s, "price_usd_per_tm", 0.0)),
            "stream":             "Raw Materials",
        })
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

    # escribir xlsx con 3 secciones + pestaña Equipment
    equipment_rows = collect_equipment_rows(fs)
    write_3sections_xlsx(path, df_capital, df_fixed, df_variable,
                         equipment=equipment_rows)
