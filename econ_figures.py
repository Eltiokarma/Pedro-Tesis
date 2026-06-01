"""econ_figures.py — Figuras matplotlib del Panel Económico.  Headless-safe.

Tres figuras, cada una *_figure(...) -> (Figure | None, meta):
  · cashflow_figure   — waterfall de cash flow por año, color por fase
    (constr danger / ramp amber / op green), eje cero, marcador vertical de
    payback en el AÑO del cruce del acumulado.
  · npv_density_figure — densidad de NPV sobre N corridas Monte Carlo, cola
    P(NPV<0) sombreada (danger), marcadores P10/P50/P90 + media.
  · tornado_figure    — barras divergentes por variable (downside danger /
    upside green), ordenadas por swing desc.

Devuelven (None, None) si matplotlib no está o si faltan datos (montecarlo y
tornado son OPCIONALES). Color desde TOK (block_inspector) — mismo sistema que
las figuras del Inspector.

IMPORTANTE (offset confirmado en Fase 0): el vector de cash flow contiene SOLO
años de OPERACIÓN (índice 0 = primer año de operación). El marcador de payback
(payback_yr, en años de operación) se ubica sobre ese eje.
"""
from __future__ import annotations

from typing import Optional, Tuple


def _tok(name, fallback="#000000"):
    """Color de TOK en caliente (mismo dict que el resto del panel)."""
    try:
        import block_inspector as _bi
        return _bi.TOK.get(name, _bi.TOK.get(fallback, fallback))
    except Exception:
        return fallback


def _new_fig(w=4.6, h=3.0):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    fig = Figure(figsize=(w, h), dpi=96)
    fig.patch.set_facecolor(_tok("bg_elev", "#ffffff"))
    return fig


def _style_ax(ax):
    ink = _tok("ink", "#1a1714"); soft = _tok("ink_soft", "#948a7c")
    grid = _tok("line_soft", "#efeadd")
    ax.set_facecolor(_tok("bg_elev", "#ffffff"))
    for sp in ax.spines.values():
        sp.set_color(_tok("line", "#e6e0d0"))
    ax.tick_params(colors=soft, labelsize=7)
    ax.xaxis.label.set_color(ink); ax.yaxis.label.set_color(ink)
    ax.title.set_color(ink)
    ax.grid(True, color=grid, lw=0.6, alpha=0.7)
    ax.set_axisbelow(True)


# ─────────────────────────────────────────────────────────────────────
#  cashflow_figure — waterfall por fase + marcador de payback
# ─────────────────────────────────────────────────────────────────────
def cashflow_figure(cashflow, payback_year=None) -> Tuple[Optional[object], Optional[dict]]:
    """cashflow = [{year, cf, phase}] (de econ_metrics). payback_year en años
    de operación (mismo origen que el vector). Barras por fase + marcador."""
    try:
        if not cashflow:
            return None, None
        fig = _new_fig()
        ax = fig.add_subplot(111)
        _style_ax(ax)
        phase_color = {
            "constr": _tok("danger", "#b8453a"),
            "ramp":   _tok("amber",  "#b8841a"),
            "op":     _tok("green",  "#4d8742"),
        }
        years = [r["year"] for r in cashflow]
        cfs   = [r["cf"] / 1e6 for r in cashflow]
        cols  = [phase_color.get(r.get("phase", "op"), phase_color["op"])
                 for r in cashflow]
        ax.bar(years, cfs, color=cols, width=0.7,
               edgecolor=_tok("line", "#e6e0d0"), linewidth=0.5)
        ax.axhline(0, color=_tok("ink_mute", "#6b6256"), lw=0.8)
        # marcador de payback: payback_year son años de OPERACIÓN; el eje x es
        # el 'year' de cada fila (= índice+1). Ubicar el marcador en el año
        # cuyo acumulado cruza cero — coincide con payback_year del motor.
        marker_x = None
        if payback_year is not None and payback_year != float("inf"):
            # year del primer registro op cuyo índice op >= payback_year-? :
            # el vector es 1-indexado por 'year'; payback_year (op-years) mapea
            # directamente a x = year correspondiente al índice ceil(payback).
            import math
            op_rows = [r for r in cashflow]
            # índice op (0-based) del cruce = floor(payback_year); el 'year'
            # de esa fila es el marcador.
            idx = min(int(math.floor(payback_year)), len(op_rows) - 1)
            marker_x = op_rows[idx]["year"] - 1 + (payback_year - int(payback_year))
            ax.axvline(marker_x, color=_tok("spec", "#3548b4"), lw=1.4,
                       ls="--")
            ax.annotate(f"payback ≈ {payback_year:.1f}",
                        xy=(marker_x, 0),
                        xytext=(4, 6), textcoords="offset points",
                        fontsize=7, color=_tok("spec", "#3548b4"))
        ax.set_xlabel("Año de operación", fontsize=8)
        ax.set_ylabel("Cash flow (M USD)", fontsize=8)
        ax.set_title("Perfil de cash flow", fontsize=9)
        fig.tight_layout()
        return fig, {"n_years": len(cashflow), "marker_x": marker_x}
    except Exception:
        return None, None


# ─────────────────────────────────────────────────────────────────────
#  npv_density_figure — densidad NPV + cola P(NPV<0) + percentiles
# ─────────────────────────────────────────────────────────────────────
def npv_density_figure(montecarlo) -> Tuple[Optional[object], Optional[dict]]:
    """montecarlo = {samples:[...], p10, p50, p90, p_neg, n_runs}. None si no
    hay análisis Monte Carlo (opcional)."""
    try:
        if not montecarlo:
            return None, None
        samples = montecarlo.get("samples")
        if not samples:
            return None, None
        import numpy as np
        xs = np.asarray(samples, dtype=float) / 1e6   # M USD
        fig = _new_fig()
        ax = fig.add_subplot(111)
        _style_ax(ax)
        # histograma normalizado como densidad
        n, bins, patches = ax.hist(xs, bins=40, density=True,
                                   color=_tok("accent_soft", "#d9e3c2"),
                                   edgecolor=_tok("accent", "#5f7a30"),
                                   linewidth=0.5)
        # cola P(NPV<0) sombreada en danger
        for patch, left in zip(patches, bins[:-1]):
            if left < 0:
                patch.set_facecolor(_tok("danger_bg", "#f3dcd8"))
                patch.set_edgecolor(_tok("danger", "#b8453a"))
        ax.axvline(0, color=_tok("danger", "#b8453a"), lw=1.0, ls="-")
        # percentiles
        for key, lab in (("p10", "P10"), ("p50", "P50"), ("p90", "P90")):
            v = montecarlo.get(key)
            if v is not None:
                vx = v / 1e6
                ax.axvline(vx, color=_tok("ink_mute", "#6b6256"), lw=0.9,
                           ls=":")
                ax.annotate(lab, xy=(vx, ax.get_ylim()[1] * 0.9),
                            fontsize=6.5, color=_tok("ink_mute", "#6b6256"),
                            ha="center")
        p_neg = montecarlo.get("p_neg")
        title = "Distribución de NPV"
        if p_neg is not None:
            title += f"  ·  P(NPV<0) = {p_neg*100:.0f}%"
        ax.set_xlabel("NPV (M USD)", fontsize=8)
        ax.set_ylabel("Densidad", fontsize=8)
        ax.set_title(title, fontsize=9)
        fig.tight_layout()
        return fig, {"n_runs": montecarlo.get("n_runs"), "p_neg": p_neg}
    except Exception:
        return None, None


# ─────────────────────────────────────────────────────────────────────
#  tornado_figure — barras divergentes ordenadas por swing
# ─────────────────────────────────────────────────────────────────────
def tornado_figure(tornado, base=None) -> Tuple[Optional[object], Optional[dict]]:
    """tornado = [{name, lo, hi}] (NPV con la variable a ±). base = NPV base
    (centro). None si no hay análisis de sensibilidad (opcional)."""
    try:
        if not tornado:
            return None, None
        rows = list(tornado)
        # ordenar por swing |hi-lo| desc, dibujar de abajo hacia arriba
        rows.sort(key=lambda r: abs((r.get("hi", 0) or 0)
                                    - (r.get("lo", 0) or 0)))
        if base is None:
            # estimar base como mediana de los extremos
            vals = [v for r in rows for v in (r.get("lo"), r.get("hi"))
                    if v is not None]
            base = (sorted(vals)[len(vals)//2] if vals else 0.0)
        fig = _new_fig()
        ax = fig.add_subplot(111)
        _style_ax(ax)
        b = base / 1e6
        green = _tok("green", "#4d8742"); danger = _tok("danger", "#b8453a")
        names = []
        for i, r in enumerate(rows):
            lo = (r.get("lo", base) or base) / 1e6
            hi = (r.get("hi", base) or base) / 1e6
            names.append(r.get("name", f"var{i}"))
            # downside (por debajo de base) en danger, upside en green
            lo_d, hi_d = min(lo, hi), max(lo, hi)
            if lo_d < b:
                ax.barh(i, lo_d - b, left=b, color=danger, height=0.6,
                        edgecolor=_tok("line", "#e6e0d0"), linewidth=0.4)
            if hi_d > b:
                ax.barh(i, hi_d - b, left=b, color=green, height=0.6,
                        edgecolor=_tok("line", "#e6e0d0"), linewidth=0.4)
        ax.axvline(b, color=_tok("ink", "#1a1714"), lw=1.0)
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels(names, fontsize=7)
        ax.set_xlabel("NPV (M USD)", fontsize=8)
        ax.set_title("Tornado de sensibilidad", fontsize=9)
        ax.grid(True, axis="x", color=_tok("line_soft", "#efeadd"), lw=0.6)
        ax.grid(False, axis="y")
        fig.tight_layout()
        return fig, {"n_vars": len(rows), "base_musd": b}
    except Exception:
        return None, None


__all__ = ["cashflow_figure", "npv_density_figure", "tornado_figure"]
