"""
audit_phase2_v3_1.py — Audit Phase 2 v3.1 (bugfix de detección ilustrativos)

DIFF respecto a v3: la regex de "ilustrativo" buscaba en TODO el docstring,
incluyendo el cuerpo. Eso daba falso positivo para `polyethylene` (TIER 1
en su línea principal pero menciona "pedagógica" en una nota interna).

Fix: buscar el marcador SOLO en la primera línea del docstring (el "tier
line"). Esto distingue entre:
  - "TIER 2 — Central Rankine (ILUSTRATIVO)" → match (correcto)
  - "TIER 1 — Polietileno LDPE" (con "pedagógica" en línea 5) → no match

Para el resto, idéntico a v3.
"""
import csv
import inspect
import re
import warnings
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

warnings.filterwarnings("ignore", category=UserWarning,
                         module="equipment_costs")

from flowsheet_model import Flowsheet
from examples_library import ExampleBuilder
import flowsheet_solver as fsv
import equipment_sizing as esz
import equipment_costs as ec


ILLUSTRATIVE_PATTERNS = [
    r'TIER\s*2',
    r'ILUSTRATIVO',
    r'\bpiloto\b',
    r'plant.scale',
    r'bench.scale',
    r'demostraci',
]


def is_illustrative(builder_method_name):
    """v3.1: matcha solo en la PRIMERA LÍNEA del docstring (tier line)."""
    try:
        method = getattr(ExampleBuilder, builder_method_name)
        doc = method.__doc__ or ""
        # Primera línea no vacía
        lines = [ln.strip() for ln in doc.splitlines() if ln.strip()]
        if not lines:
            return False
        first_line = lines[0]
        for pat in ILLUSTRATIVE_PATTERNS:
            if re.search(pat, first_line, re.IGNORECASE):
                return True
    except Exception:
        pass
    return False


def safe_get(obj, attr, default=None):
    try:
        v = getattr(obj, attr, default)
        return v if v is not None else default
    except Exception:
        return default


def count_warnings_by_severity(result):
    return {
        "mass_errors":     len(safe_get(result, "mass_balance_errors", []) or []),
        "energy_errors":   len(safe_get(result, "energy_balance_errors", []) or []),
        "energy_warnings": len(safe_get(result, "energy_warnings", []) or []),
        "component_warns": len(safe_get(result, "component_warnings", []) or []),
        "unresolved":      len(safe_get(result, "unresolved_streams", []) or []),
    }


def compute_capex_opex(fs):
    out = {
        "n_blocks": len(fs.blocks), "n_streams": len(fs.streams),
        "fci_usd": 0.0, "cut_usd_yr": 0.0, "com_usd_yr": 0.0,
        "n_clamped": 0, "n_sized_ok": 0, "n_no_sizer": 0,
        "n_outside_turton": 0, "n_unknown": 0,
    }
    try:
        sizing_results = esz.auto_size_blocks(fs, only_if_unset=False)
        out["n_sized_ok"] = len(sizing_results)
        out["n_clamped"] = sum(1 for r in sizing_results if "clamped" in (r[4] or ""))
    except Exception:
        pass
    sum_cbm = 0.0
    for b in fs.blocks.values():
        try:
            spec = ec.EQUIPMENT_DATA.get(b.eq_type, {})
            if not spec:
                out["n_no_sizer"] += 1
                continue
            S = float(safe_get(b, "S", 0) or 0)
            if S <= 0: continue
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                result = ec.bare_module_cost(b.eq_type, S,
                                              P_op_bar=safe_get(b, "P_op_bar", 1.0))
                if any("fuera del rango Turton" in str(w.message) for w in caught):
                    out["n_outside_turton"] += 1
            if isinstance(result, dict):
                cbm = result.get("CBM", 0) or 0
                if result.get("unknown"): out["n_unknown"] += 1
                if cbm > 0: sum_cbm += cbm
            elif isinstance(result, (int, float)) and result > 0:
                sum_cbm += result
        except Exception:
            pass
    out["fci_usd"] = sum_cbm
    try:
        labor_usd = safe_get(fs, "labor_usd_per_year", 0) or 0.0
        opex_extras_total = 0.0
        for x in safe_get(fs, "opex_extras", []) or []:
            try:
                opex_extras_total += float(x.get("flowrate", 0) or 0) * \
                                      float(x.get("price", 0) or 0)
            except Exception:
                pass
        out["com_usd_yr"] = labor_usd + opex_extras_total
    except Exception:
        pass
    return out


def audit_one_example(builder_method_name):
    row = {
        "example": builder_method_name.replace("_example_", ""),
        "illustrative": is_illustrative(builder_method_name),
        "build_ok": False, "solve_ok": False,
        "status": "", "success": False,
        "n_blocks": 0, "n_streams": 0,
        "mass_errors": 0, "energy_errors": 0,
        "energy_warnings": 0, "component_warns": 0, "unresolved": 0,
        "n_sized_ok": 0, "n_clamped": 0,
        "n_no_sizer": 0, "n_outside_turton": 0, "n_unknown": 0,
        "fci_M_usd": 0.0, "com_M_usd_yr": 0.0,
        "error_short": "",
    }
    try:
        fs = Flowsheet()
        b = ExampleBuilder(fs)
        getattr(b, builder_method_name)()
        row["build_ok"] = True
        row["n_blocks"] = len(fs.blocks)
        row["n_streams"] = len(fs.streams)
    except Exception as e:
        row["error_short"] = f"BUILD: {type(e).__name__}: {str(e)[:80]}"
        return row
    try:
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            result = fsv.solve(fs)
        row["solve_ok"] = True
        row["status"] = str(safe_get(result, "overall_status", ""))
        row["success"] = bool(safe_get(result, "success", False))
        row.update(count_warnings_by_severity(result))
    except Exception as e:
        row["error_short"] = f"SOLVE: {type(e).__name__}: {str(e)[:80]}"
        return row
    try:
        capex_opex = compute_capex_opex(fs)
        row["n_sized_ok"] = capex_opex["n_sized_ok"]
        row["n_clamped"] = capex_opex["n_clamped"]
        row["n_no_sizer"] = capex_opex["n_no_sizer"]
        row["n_outside_turton"] = capex_opex["n_outside_turton"]
        row["n_unknown"] = capex_opex["n_unknown"]
        row["fci_M_usd"] = capex_opex["fci_usd"] / 1e6
        row["com_M_usd_yr"] = capex_opex["com_usd_yr"] / 1e6
    except Exception as e:
        row["error_short"] = f"COST: {type(e).__name__}: {str(e)[:80]}"
    return row


def main():
    builders = sorted(
        n for n, m in inspect.getmembers(ExampleBuilder)
        if n.startswith("_example_") and callable(m)
    )
    print(f"Encontrados {len(builders)} ejemplos en ExampleBuilder")
    illustrative_list = [n.replace('_example_', '') for n in builders if is_illustrative(n)]
    print(f"v3.1 — Detección por PRIMERA LÍNEA del docstring")
    print(f"Detectados {len(illustrative_list)} ilustrativos: {', '.join(illustrative_list)}")
    print()

    rows = []
    for i, name in enumerate(builders, 1):
        marker = " [ILUS]" if is_illustrative(name) else ""
        print(f"  [{i:2d}/{len(builders)}] {name.replace('_example_', '')}{marker}...",
              end=" ", flush=True)
        try:
            row = audit_one_example(name)
            rows.append(row)
            if row["error_short"]:
                print(f"X {row['error_short'][:50]}")
            else:
                tag = ""
                if row["n_outside_turton"] > 0:
                    tag += f" [Turton:{row['n_outside_turton']}]"
                ew = row.get("energy_warnings", 0)
                if ew > 0:
                    tag += f" [warns:{ew}]"
                print(f"OK  FCI={row['fci_M_usd']:8.2f}M  "
                      f"blocks={row['n_blocks']:2d}{tag}")
        except Exception as e:
            print(f"CRASH: {type(e).__name__}: {str(e)[:100]}")

    if rows:
        fields = list(rows[0].keys())
        with open("audit_phase2_results.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for r in rows: w.writerow(r)
        print(f"\nResultados -> audit_phase2_results.csv  ({len(rows)} filas)")

    tier1 = [r for r in rows if not r["illustrative"]]
    tier2 = [r for r in rows if r["illustrative"]]

    print("\n" + "=" * 75)
    print("RESUMEN — TIER 1 (INDUSTRIAL, costing comparable)")
    print("=" * 75)
    print(f"  Ejemplos:                    {len(tier1)}")
    success_t1 = sum(1 for r in tier1 if r["success"])
    print(f"  success=True:                {success_t1}/{len(tier1)}")
    turton_t1 = sum(1 for r in tier1 if r["n_outside_turton"] > 0)
    print(f"  Con bloques fuera Turton:    {turton_t1}/{len(tier1)}")
    warns_t1 = sum(1 for r in tier1 if r.get("energy_warnings", 0) > 0)
    print(f"  Con energy_warnings nuevos:  {warns_t1}/{len(tier1)}")
    fci_t1 = sum(r["fci_M_usd"] for r in tier1)
    fci_t1_nonzero = [r for r in tier1 if r["fci_M_usd"] > 0]
    avg_t1 = sum(r["fci_M_usd"] for r in fci_t1_nonzero) / len(fci_t1_nonzero) if fci_t1_nonzero else 0
    print(f"  Total FCI agregado:          {fci_t1:8.1f} M USD")
    print(f"  FCI promedio:                {avg_t1:8.1f} M USD")

    print()
    print("  Top 10 TIER 1 por FCI:")
    for r in sorted(tier1, key=lambda r: -r["fci_M_usd"])[:10]:
        ew = f"  warns={r['energy_warnings']:2d}" if r.get("energy_warnings") else ""
        print(f"    {r['example']:30s}  FCI={r['fci_M_usd']:8.2f} M  "
              f"blocks={r['n_blocks']:2d}  status={r['status']}{ew}")

    if tier2:
        print()
        print("=" * 75)
        print("RESUMEN — TIER 2 (ILUSTRATIVO, no agregado al promedio)")
        print("=" * 75)
        for r in sorted(tier2, key=lambda r: -r["fci_M_usd"]):
            tag = ""
            if r["n_outside_turton"] > 0:
                tag = f"  ⚠ {r['n_outside_turton']} bloques fuera Turton"
            print(f"  {r['example']:30s}  FCI={r['fci_M_usd']:8.2f} M  "
                  f"blocks={r['n_blocks']:2d}{tag}")


if __name__ == "__main__":
    main()
