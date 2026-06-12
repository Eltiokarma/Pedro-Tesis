"""
audit_examples_components.py — Auditoría PERMANENTE de balance de masa
POR COMPONENTE, bloque a bloque, sobre todos los data/examples/*.json.

Para cada ejemplo:
  1. Carga el JSON (from_dict) y lo resuelve headless (flowsheet_solver.solve).
  2. Para cada bloque con ≥1 entrada y ≥1 salida (excluye auxiliares y los
     bordes feed/product que no pueden balancearse):
       · reacción química declarada (b.reactions / reactor_mode cinético /
         heat_of_reaction ≠ 0 / custom_reactions) → SKIP: el solver calcula
         la química, la conservación por componente NO aplica.
       · inline_reaction no vacío → chequeo de ESTEQUIOMETRÍA: el cambio de
         composición observado debe explicarse por extensiones ξ ≥ 0 de las
         reacciones declaradas (residual no explicado < tol).
       · pseudo_cut no vacío → chequeo de masa TOTAL del grupo: la masa de
         los componentes de entrada del grupo debe igualar la suma de la masa
         de los componentes de salida del grupo (cortes de crudo).
       · resto → CONSERVACIÓN POR COMPONENTE estricta (tol 1% relativa):
         cada componente real debe cerrar in = Σ out a través de TODAS las
         salidas del bloque (flash, columna, splitter y separadores
         conservan cada componente; sólo reacción o lumping lo rompen).
  3. Severidad de cada hallazgo:
       · CRITICO  si |in − out| > 5% del flujo total del bloque.
       · MAYOR    el resto (entre la tolerancia de 1% y ese 5%).

Salida:
  · JSON estructurado en outputs/component_balance_audit.json
  · tabla legible a stdout (ejemplo → bloque → componente → in/out/% → sev).

USO:
    python audit_examples_components.py                  # todos los ejemplos
    python audit_examples_components.py gas_sweet hda    # subset por clave
    python audit_examples_components.py --json outputs/x.json   # destino JSON
    python audit_examples_components.py --quiet          # sólo resumen + JSON

Importable: audit_flowsheet_components(fs) y audit_example(key) devuelven
estructuras reutilizadas por flowsheet_consistency_audit (warning) y por
gate_component_balance (ratchet).
"""
from __future__ import annotations

import os
import sys
import json
import glob
from typing import Dict, List, Optional

# Tolerancia de detección: relativa al mayor de (in, out) del componente.
TOL_REL = 0.01
# Umbral de severidad CRITICO: fracción del flujo total del bloque.
CRIT_FRAC = 0.05
# Componentes traza: por debajo de esta fracción del flujo del bloque se
# ignoran (ruido numérico, no balances físicos significativos).
TRACE_FRAC = 0.01

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "examples")
DEFAULT_JSON_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "outputs", "component_balance_audit.json")


# ----------------------------------------------------------------------
# Helpers de modelo
# ----------------------------------------------------------------------
def _stream_component_mass(s) -> Dict[str, float]:
    """{componente: masa (tm/año)} de un stream, desde composition o
    main_component (100% puro)."""
    comp = s.composition or ({s.main_component: 1.0} if s.main_component else {})
    return {c: w * s.mass_flow for c, w in comp.items() if w}


def _has_declared_reaction(b) -> bool:
    """True si el bloque tiene química REAL que el solver resuelve (no
    inline_reaction, que es declarativo para el auditor).  En esos bloques
    la conservación por componente no aplica."""
    if getattr(b, "reactions", None):
        return True
    if getattr(b, "custom_reactions", None):
        return True
    if abs(float(getattr(b, "heat_of_reaction", 0.0) or 0.0)) > 1e-9:
        return True
    mode = (getattr(b, "reactor_mode", "") or "").lower()
    if mode in ("pfr", "cstr", "batch", "stoich"):
        # 'equilibrium' es el default de TODOS los bloques (incluso HX);
        # sólo cuenta como reacción si además es un reactor con rxn ids,
        # lo cual ya lo cubrió b.reactions arriba.
        return True
    return False


def _mw(name) -> Optional[float]:
    try:
        import thermo_db as _td
        c = _td.get(name)
        if c is not None and getattr(c, "mw", 0) and c.mw > 0:
            return float(c.mw)
    except Exception:
        pass
    return None


def _severity(delta: float, block_flow: float) -> str:
    return "CRITICO" if delta > CRIT_FRAC * max(block_flow, 1e-9) else "MAYOR"


# ----------------------------------------------------------------------
# Chequeo por componente (default)
# ----------------------------------------------------------------------
def _check_per_component(b, comp_in, comp_out, block_flow) -> List[dict]:
    findings = []
    for c in sorted(set(comp_in) | set(comp_out)):
        ci, co = comp_in.get(c, 0.0), comp_out.get(c, 0.0)
        if max(ci, co) < TRACE_FRAC * block_flow:
            continue                       # traza → ignorar
        d = abs(ci - co)
        rel = d / max(ci, co, 1e-9)
        if rel < TOL_REL:
            continue
        findings.append({
            "mode": "component", "component": c,
            "in": round(ci, 3), "out": round(co, 3), "delta": round(d, 3),
            "rel_pct": round(rel * 100.0, 2),
            "block_flow_pct": round(d / max(block_flow, 1e-9) * 100.0, 2),
            "severity": _severity(d, block_flow),
            "message": (f"{b.name}: componente '{c}' no cierra — "
                        f"in={ci:.1f} out={co:.1f} (Δ={d:.1f} tm/a, "
                        f"{rel*100:.1f}% del componente, "
                        f"{d/max(block_flow,1e-9)*100:.1f}% del flujo)"),
        })
    return findings


# ----------------------------------------------------------------------
# Chequeo de estequiometría (inline_reaction)
# ----------------------------------------------------------------------
def _check_stoichiometry(b, comp_in, comp_out, block_flow) -> List[dict]:
    """El cambio de masa por componente debe explicarse por extensiones de
    las reacciones declaradas en inline_reaction.  Resuelve ξ por mínimos
    cuadrados sobre el balance MOLAR y reporta la masa NO explicada."""
    try:
        import numpy as np
        import reactions_db as rdb
    except Exception:
        # Sin numpy/reactions_db no podemos chequear estequiometría: caer al
        # chequeo de masa total (al menos la masa global debe cerrar).
        return _check_total_only(b, comp_in, comp_out, block_flow,
                                 mode="inline_reaction(sin_numpy)")

    rxn_ids = list(getattr(b, "inline_reaction", []) or [])
    reactions = []
    for rid in rxn_ids:
        r = None
        try:
            r = rdb.get(rid)
        except Exception:
            r = None
        if r is not None:
            reactions.append(r)

    # Componentes involucrados (unión de comp del flowsheet y de reacciones)
    species = set(comp_in) | set(comp_out)
    # Δn molar observado por componente (kmol/año); requiere MW.
    comps = []
    dn_obs = []
    missing_mw = []
    for c in sorted(species):
        if max(comp_in.get(c, 0.0), comp_out.get(c, 0.0)) < TRACE_FRAC * block_flow:
            continue
        mw = _mw(c)
        if mw is None:
            missing_mw.append(c)
            continue
        comps.append(c)
        dn_obs.append((comp_out.get(c, 0.0) - comp_in.get(c, 0.0)) * 1000.0 / mw)

    findings = []
    if not reactions or not comps:
        # No pudimos armar el sistema → al menos exigir masa total.
        return _check_total_only(b, comp_in, comp_out, block_flow,
                                 mode="inline_reaction")

    # Matriz estequiométrica A[comp, rxn] = ν (mol) mapeando por thermo_name.
    A = np.zeros((len(comps), len(reactions)))
    for j, r in enumerate(reactions):
        for sp in r.stoich:
            tname = sp.thermo_name
            if tname in comps:
                A[comps.index(tname), j] += sp.nu
    dn = np.array(dn_obs)
    # ξ por mínimos cuadrados (no forzamos ≥0 aquí; sólo medimos residual).
    try:
        xi, *_ = np.linalg.lstsq(A, dn, rcond=None)
    except Exception:
        xi = np.zeros(len(reactions))
    resid_mol = dn - A.dot(xi)
    # Masa no explicada por componente (tm/año).
    for i, c in enumerate(comps):
        mw = _mw(c) or 0.0
        unexplained = abs(resid_mol[i]) * mw / 1000.0
        if unexplained < TOL_REL * block_flow:
            continue
        findings.append({
            "mode": "inline_reaction", "component": c,
            "delta_unexplained": round(unexplained, 3),
            "block_flow_pct": round(unexplained / max(block_flow, 1e-9) * 100.0, 2),
            "severity": _severity(unexplained, block_flow),
            "xi_per_reaction": [round(float(x), 4) for x in xi],
            "message": (f"{b.name}: '{c}' cambia {resid_mol[i]*mw/1000.0:+.1f} "
                        f"tm/a NO explicado por inline_reaction "
                        f"{rxn_ids} (estequiometría incompleta o comp errónea)"),
        })
    if missing_mw:
        findings.append({
            "mode": "inline_reaction", "component": ",".join(sorted(missing_mw)),
            "severity": "MAYOR",
            "message": (f"{b.name}: sin MW para {sorted(missing_mw)} — "
                        f"estequiometría no verificable para esos componentes "
                        f"(se verificó el resto + masa total)"),
        })
    # Y la masa total siempre debe cerrar (las reacciones conservan masa).
    findings += _check_total_only(b, comp_in, comp_out, block_flow,
                                  mode="inline_reaction")
    return findings


# ----------------------------------------------------------------------
# Chequeo de masa total de grupo (pseudo_cut) y total simple
# ----------------------------------------------------------------------
def _check_pseudo_cut(b, comp_in, comp_out, block_flow) -> List[dict]:
    """Para cada {comp_entrada: [comps_salida]}, la masa del comp de entrada
    debe igualar la suma de la masa de los comps de salida del grupo.  Los
    componentes fuera de cualquier grupo se chequean por conservación normal."""
    findings = []
    pc = getattr(b, "pseudo_cut", {}) or {}
    grouped_in = set(pc.keys())
    grouped_out = set()
    for outs in pc.values():
        grouped_out |= set(outs)
    for in_comp, out_comps in pc.items():
        m_in = comp_in.get(in_comp, 0.0)
        m_out = sum(comp_out.get(oc, 0.0) for oc in out_comps)
        d = abs(m_in - m_out)
        rel = d / max(m_in, m_out, 1e-9)
        if rel < TOL_REL:
            continue
        findings.append({
            "mode": "pseudo_cut", "component": f"{in_comp}→{out_comps}",
            "in": round(m_in, 3), "out": round(m_out, 3), "delta": round(d, 3),
            "rel_pct": round(rel * 100.0, 2),
            "block_flow_pct": round(d / max(block_flow, 1e-9) * 100.0, 2),
            "severity": _severity(d, block_flow),
            "message": (f"{b.name}: grupo pseudo_cut '{in_comp}'→{out_comps} "
                        f"no cierra — in={m_in:.1f} Σout={m_out:.1f} "
                        f"(Δ={d:.1f} tm/a, {rel*100:.1f}%)"),
        })
    # Componentes NO agrupados → conservación normal.
    rest_in = {c: v for c, v in comp_in.items() if c not in grouped_in and c not in grouped_out}
    rest_out = {c: v for c, v in comp_out.items() if c not in grouped_in and c not in grouped_out}
    findings += _check_per_component(b, rest_in, rest_out, block_flow)
    return findings


def _check_total_only(b, comp_in, comp_out, block_flow, mode="total") -> List[dict]:
    in_t = sum(comp_in.values())
    out_t = sum(comp_out.values())
    d = abs(in_t - out_t)
    rel = d / max(in_t, out_t, 1e-9)
    if rel < TOL_REL:
        return []
    return [{
        "mode": mode, "component": "__total__",
        "in": round(in_t, 3), "out": round(out_t, 3), "delta": round(d, 3),
        "rel_pct": round(rel * 100.0, 2),
        "block_flow_pct": round(d / max(block_flow, 1e-9) * 100.0, 2),
        "severity": _severity(d, block_flow),
        "message": (f"{b.name}: masa TOTAL no cierra — in={in_t:.1f} "
                    f"out={out_t:.1f} (Δ={d:.1f} tm/a, {rel*100:.1f}%)"),
    }]


# ----------------------------------------------------------------------
# Auditoría de un bloque y de un flowsheet
# ----------------------------------------------------------------------
def audit_block(fs, b) -> List[dict]:
    if getattr(b, "auto_aux", False):
        return []
    if _has_declared_reaction(b):
        return []                          # química real → no aplica
    ins = [s for s in fs.streams.values()
           if s.dst == b.id and s.src != -1 and s.dst != -1 and s.mass_flow > 0]
    outs = [s for s in fs.streams.values()
            if s.src == b.id and s.src != -1 and s.dst != -1 and s.mass_flow > 0]
    if not ins or not outs:
        return []                          # borde feed/product → no balanceable
    comp_in: Dict[str, float] = {}
    comp_out: Dict[str, float] = {}
    for s in ins:
        for c, m in _stream_component_mass(s).items():
            comp_in[c] = comp_in.get(c, 0.0) + m
    for s in outs:
        for c, m in _stream_component_mass(s).items():
            comp_out[c] = comp_out.get(c, 0.0) + m
    # Sin composición en ningún lado → no hay nada por-componente que chequear
    # (el balance de masa global lo cubre el solver).
    if not comp_in and not comp_out:
        return []
    block_flow = max(sum(comp_in.values()), sum(comp_out.values()))
    if block_flow <= 0:
        return []

    if getattr(b, "inline_reaction", None):
        findings = _check_stoichiometry(b, comp_in, comp_out, block_flow)
    elif getattr(b, "pseudo_cut", None):
        findings = _check_pseudo_cut(b, comp_in, comp_out, block_flow)
    else:
        findings = _check_per_component(b, comp_in, comp_out, block_flow)
        findings += _check_total_only(b, comp_in, comp_out, block_flow)
    for f in findings:
        f["block"] = b.name
        f["block_id"] = b.id
    return findings


def audit_flowsheet_components(fs) -> dict:
    """Audita TODOS los bloques de un flowsheet ya resuelto.  Devuelve
    {findings: [...], n_critico, n_mayor}."""
    findings: List[dict] = []
    for b in fs.blocks.values():
        findings += audit_block(fs, b)
    return {
        "findings": findings,
        "n_critico": sum(1 for f in findings if f.get("severity") == "CRITICO"),
        "n_mayor": sum(1 for f in findings if f.get("severity") == "MAYOR"),
    }


def audit_example(key: str) -> dict:
    """Carga data/examples/<key>.json, lo resuelve headless y lo audita."""
    import flowsheet_model as fm
    import flowsheet_solver as fsv
    path = os.path.join(DATA_DIR, f"{key}.json")
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    fs = fm.Flowsheet.from_dict(d)
    fsv.solve(fs)
    rep = audit_flowsheet_components(fs)
    rep["example"] = key
    return rep


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def _example_keys() -> List[str]:
    keys = []
    for p in sorted(glob.glob(os.path.join(DATA_DIR, "*.json"))):
        name = os.path.splitext(os.path.basename(p))[0]
        if name in ("_golden", "manifest"):
            continue
        keys.append(name)
    return keys


def _headless():
    try:
        from export_examples import _headless_mocks
        _headless_mocks()
    except Exception:
        pass


def run(keys=None, json_out=DEFAULT_JSON_OUT, quiet=False) -> dict:
    _headless()
    keys = keys or _example_keys()
    all_reports = {}
    total_crit = total_major = 0
    for key in keys:
        try:
            rep = audit_example(key)
        except Exception as e:
            rep = {"example": key, "error": f"{type(e).__name__}: {e}",
                   "findings": [], "n_critico": 0, "n_mayor": 0}
        all_reports[key] = rep
        total_crit += rep.get("n_critico", 0)
        total_major += rep.get("n_mayor", 0)

    if not quiet:
        _print_table(all_reports)

    out = {
        "tol_rel": TOL_REL, "crit_frac": CRIT_FRAC,
        "n_examples": len(keys),
        "total_critico": total_crit, "total_mayor": total_major,
        "examples": all_reports,
    }
    if json_out:
        os.makedirs(os.path.dirname(json_out), exist_ok=True)
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2, sort_keys=True)
        if not quiet:
            print(f"\nJSON escrito en {json_out}")
    return out


def _print_table(reports):
    print("=" * 90)
    print("AUDITORÍA DE BALANCE POR COMPONENTE — bloque a bloque (tol 1% relativa)")
    print("=" * 90)
    clean = []
    for key in sorted(reports):
        rep = reports[key]
        if rep.get("error"):
            print(f"\n■ {key:18s}  ERROR: {rep['error']}")
            continue
        fs_findings = rep.get("findings", [])
        if not fs_findings:
            clean.append(key)
            continue
        nc, nm = rep["n_critico"], rep["n_mayor"]
        print(f"\n■ {key:18s}  {nc} CRÍTICO / {nm} MAYOR")
        for f in fs_findings:
            sev = f.get("severity", "?")
            tag = "‼" if sev == "CRITICO" else "•"
            print(f"   {tag} [{sev:7s}] {f.get('message','')}")
    if clean:
        print("\n" + "-" * 90)
        print(f"✓ Limpios ({len(clean)}): {', '.join(clean)}")
    print("=" * 90)
    tc = sum(r.get("n_critico", 0) for r in reports.values())
    tm = sum(r.get("n_mayor", 0) for r in reports.values())
    print(f"TOTAL: {tc} CRÍTICO, {tm} MAYOR en {len(reports)} ejemplos.")


if __name__ == "__main__":
    args = sys.argv[1:]
    quiet = "--quiet" in args
    args = [a for a in args if a != "--quiet"]
    json_out = DEFAULT_JSON_OUT
    if "--json" in args:
        i = args.index("--json")
        json_out = args[i + 1]
        del args[i:i + 2]
    keys = args or None
    res = run(keys=keys, json_out=json_out, quiet=quiet)
    # exit code informativo (no rompe nada; el gate es aparte)
    sys.exit(0)
