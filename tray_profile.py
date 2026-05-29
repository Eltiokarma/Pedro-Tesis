"""tray_profile.py — perfil tray-by-tray (T y composición por etapa) de una
columna binaria.  Es el 9º método del widget de destilación: dado un bloque
columna del modelo, arma el perfil de la columna ordenado top→bottom desde
DOS fuentes posibles, con el mismo contrato de salida.

Decisión de arquitectura (acordada con el usuario):
  · FUENTE PRIMARIA = Wang-Henke MESH riguroso si el bloque tiene
    `_wh_result` poblado y convergido (lo persiste solve_columns cuando el
    bloque declara `column_method == "wanghenke"`).
  · FUENTE FALLBACK = derivado del diseño McCabe-Thiele (CMO, binario) que
    ya construye `mccabe_thiele.design_from_block`.  Para cada etapa de la
    escalera computamos T = bubble point del binario LK/HK a esa x_LK vía
    NRTL — esto refleja exactamente la hipótesis CMO (cada etapa es
    líquido saturado en equilibrio).

NUNCA etiquetamos McCabe como Wang-Henke; el badge de procedencia es
explícito.  Si la fuente McCabe truncó (azeótropo, no escalonable), el
perfil incluye las etapas que sí salieron + flag `truncated=True`.
"""
from __future__ import annotations

from typing import Dict, List, Optional


def _wh_comps(block, fs) -> Optional[List[str]]:
    """Reconstruye el orden de componentes con que solve_columns invocó a
    wang_henke: `list(feed.composition.keys())` del feed activo del bloque.
    Mantenemos compatibilidad con tests/mocks que inyectan `_comps` dentro
    del `_wh_result`."""
    wh = getattr(block, "_wh_result", None)
    if wh and isinstance(wh, dict) and wh.get("_comps"):
        return list(wh["_comps"])
    if fs is None:
        return None
    feed = next((s for s in fs.streams.values()
                 if s.dst == block.id and (s.composition or {})), None)
    if feed is None:
        return None
    return list(feed.composition.keys())


def _from_wanghenke(block, fs) -> Optional[Dict]:
    """Extrae el perfil desde `block._wh_result` si está convergido.
    Devuelve None si falta, no convergió o no se pudo identificar el LK."""
    wh = getattr(block, "_wh_result", None)
    if not (wh and isinstance(wh, dict) and wh.get("converged")):
        return None
    T_K = wh.get("T_profile") or []
    x_prof = wh.get("x_profile") or []
    if not T_K or not x_prof or len(T_K) != len(x_prof):
        return None
    comps = _wh_comps(block, fs)
    LK = getattr(block, "column_LK", "") or "LK"
    lk_idx = comps.index(LK) if (comps and LK in comps) else None
    if lk_idx is None:
        return None
    HK = getattr(block, "column_HK", "") or "HK"
    n_feed = wh.get("feed_stage") or wh.get("N_feed")
    n_total = len(T_K)
    if n_feed is None:
        n_feed = max(1, n_total // 2)
    # Series por etapa (top→bottom; el solver ya las guarda en ese orden)
    stages = []
    for k in range(n_total):
        x_lk = float(x_prof[k][lk_idx]) if (x_prof[k] and lk_idx < len(x_prof[k])) else 0.0
        T_C = float(T_K[k]) - 273.15
        stages.append({"stage": k + 1, "x_LK": x_lk, "T_C": T_C})
    # Otras trazas (composiciones que no son LK) para el modo multicomp
    other_traces: Dict[str, List[float]] = {}
    for j, name in enumerate(comps or []):
        if j == lk_idx or not name:
            continue
        try:
            other_traces[name] = [float(x_prof[k][j])
                                   for k in range(n_total)]
        except Exception:
            pass
    return dict(
        source="wanghenke",
        badge="Wang-Henke (MESH riguroso)",
        LK=LK, HK=HK, n_feed=int(n_feed), n_stages=n_total,
        stages=stages, other_traces=other_traces,
        truncated=False, message="",
    )


def _from_mccabe(block, fs) -> Optional[Dict]:
    """Deriva el perfil del McCabe-Thiele que ya construye
    `mccabe_thiele.design_from_block`.  Para cada x de la escalera computa
    T = bubble point del binario LK/HK vía NRTL (líquido saturado, CMO).
    """
    try:
        import mccabe_thiele as _mt
        import nrtl as _nrtl
    except ImportError:
        return None
    d = _mt.design_from_block(block, fs)
    if d is None:
        return None
    LK = d.get("LK") or getattr(block, "column_LK", "") or "LK"
    HK = d.get("HK") or getattr(block, "column_HK", "") or "HK"
    P = float(d.get("P_bar") or 1.013)

    # ¿Diseño infactible (azeótropo entre x_B y x_D)?  Hacemos lo mejor que
    # podemos: dibujamos el equilibrio sólo, sin escalera.  El panel mostrará
    # el aviso.
    if d.get("feasible") is False:
        azs = d.get("azeotropes") or []
        msg = d.get("message") or (
            f"Specs cruzan el azeótropo ({azs}) — perfil no escalonable.")
        return dict(
            source="mccabe", badge="McCabe-Thiele (CMO, binario)",
            LK=LK, HK=HK, n_feed=0, n_stages=0,
            stages=[], other_traces={},
            truncated=True, message=msg,
        )

    # La escalera mccabe_thiele.design viene como puntos alternados
    # horizontal/vertical desde (x_D,x_D).  Las composiciones LÍQUIDAS de
    # cada etapa son los puntos en los movimientos HORIZONTALES, i.e.
    # stages[1], stages[3], stages[5], … (índices impares).
    raw = d.get("stages") or []
    x_top_to_bot: List[float] = []
    for i in range(1, len(raw), 2):
        x_lk, _y = raw[i]
        x_top_to_bot.append(float(x_lk))
    n_total = len(x_top_to_bot)
    if n_total == 0:
        return None
    n_feed = int(d.get("feed_stage") or max(1, n_total // 2))
    n_feed = max(1, min(n_feed, n_total))

    # T por etapa: bubble point del binario en esa x.  Si NRTL no resuelve
    # un punto (extrapolación rara), interpolamos lineal entre vecinos.
    T_C: List[Optional[float]] = []
    for x_lk in x_top_to_bot:
        bp = _nrtl.bubble_point([LK, HK], [x_lk, 1.0 - x_lk], P)
        T_C.append((bp[0] - 273.15) if bp else None)
    # Rellenar Nones por interpolación lineal entre puntos válidos
    if any(t is None for t in T_C):
        # buscar primer y último válido para extrapolar extremos
        valid = [(k, t) for k, t in enumerate(T_C) if t is not None]
        if valid:
            for k in range(len(T_C)):
                if T_C[k] is None:
                    # interpolar entre los válidos más cercanos
                    prev = next((v for v in reversed(valid) if v[0] < k),
                                valid[0])
                    nxt = next((v for v in valid if v[0] > k), valid[-1])
                    if prev[0] == nxt[0]:
                        T_C[k] = prev[1]
                    else:
                        t = (k - prev[0]) / (nxt[0] - prev[0])
                        T_C[k] = prev[1] + t * (nxt[1] - prev[1])
        else:
            # no hay ningún T válido — perfil sin temperatura
            T_C = [25.0] * n_total

    stages = [{"stage": k + 1, "x_LK": x_top_to_bot[k], "T_C": float(T_C[k])}
              for k in range(n_total)]
    return dict(
        source="mccabe", badge="McCabe-Thiele (CMO, binario)",
        LK=LK, HK=HK, n_feed=n_feed, n_stages=n_total,
        stages=stages, other_traces={},
        truncated=False, message="",
    )


def build_stage_profile(block, fs, fug_res: Optional[Dict] = None
                        ) -> Optional[Dict]:
    """Normaliza el perfil tray-by-tray a UN contrato, eligiendo fuente.

    Returns dict | None (None solo si el bloque no es columna o no se pudo
    determinar siquiera el LK/HK):
        source       : "wanghenke" | "mccabe"
        badge        : str   etiqueta explícita de procedencia
        LK, HK       : str
        n_feed       : int   etapa de alimentación (1-indexed)
        n_stages     : int   total de etapas en el perfil
        stages       : list  ORDEN TOP→BOTTOM (etapa 1 = condensador/tope)
                              cada item: {stage:int, x_LK:float, T_C:float}
        other_traces : dict  {nombre: [val por etapa]} — sólo en WH multicomp
        truncated    : bool  perfil incompleto (azeótropo, no convergencia)
        message      : str   aviso para el panel (vacío si todo OK)

    Si el bloque NO es columna activa o no tiene LK/HK declarados, devuelve
    None (el panel se oculta sin crash, mismo patrón que el PFR).
    """
    if block is None:
        return None
    if not getattr(block, "column_active", False):
        return None
    if not getattr(block, "column_LK", "") or not getattr(block, "column_HK", ""):
        return None

    # Prioridad: Wang-Henke si está y convergió.
    wh = _from_wanghenke(block, fs)
    if wh is not None:
        return wh
    # Fallback: derivar del McCabe-Thiele (CMO, binario).
    return _from_mccabe(block, fs)
