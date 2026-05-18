"""
batch_schedule.py — Modelo del ciclo de operación batch (Capa 1).

Módulo AUTÓNOMO: no importa solver, modelo económico ni cualquier
otra parte del simulador.  Solo conoce el eje temporal de un ciclo
batch (segundos/horas) y produce un bloque de metadata que las
capas superiores consumen.

Conceptos:
  · TaskKind  — categoría de tarea del ciclo (carga, calentamiento,
                reacción, enfriamiento, descarga, CIP, espera).
  · Task      — tarea individual con duración fija + servicio +
                pico de utility + hook ODE opcional (extensión
                para Capa 2 / transitorio futuro).
  · BatchRecipe — receta = lista ORDENADA y LIBRE de tareas + masa
                  de producto por batch.

API:
    cycle_time_s(recipe)           → segundos por batch
    batches_per_year(recipe, av)   → batches/año a disponibilidad av
    annual_production(recipe, av)  → kg/año equivalentes
    utility_peaks(recipe)          → {servicio: pico instantáneo}
    to_schedule_block(recipe, av)  → dict para Capa 3 (puente económico)
    resolve_dynamic_durations(recipe, solver=...)
                                   → llena duraciones via ode_hook
                                     (extensión para Capa 2)

Diseño:
  · La receta es estrictamente una LISTA — generalizar a secuencias
    arbitrarias (recovery loops, paralelo) es gratis si mantenemos
    esta abstracción.
  · El pico de servicios (utility_rate) es INSTANTÁNEO: mientras la
    tarea está activa, el servicio entrega ese caudal/potencia.  El
    sizing de servicios va sobre el pico, NO el promedio anual —
    ese es el punto de la Opción B (modo batch de primera clase).
  · ode_hook permite que Capa 2 (sizing) inserte una función que
    calcule la duración real de la reacción/condicionamiento hasta
    una conversión objetivo.  Capa 1 NO lo invoca automáticamente
    (mantiene el aislamiento); el caller usa
    resolve_dynamic_durations() explícitamente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional


# ─────────────────────────────────────────────────────────────
# Constantes (no dependen de units.py para mantener autonomía)
# ─────────────────────────────────────────────────────────────

SECONDS_PER_HOUR = 3600.0
HOURS_PER_YEAR   = 8760.0


# ─────────────────────────────────────────────────────────────
# Categorías de tarea
# ─────────────────────────────────────────────────────────────

class TaskKind(Enum):
    """Tipos de tarea del ciclo batch.

    Cada tipo es DECLARATIVO: el orden y la lista de tareas es
    libre (no asumimos secuencia carga→reacción→descarga).
    """
    CARGA          = "carga"            # transferencia in
    CALENTAMIENTO  = "calentamiento"    # rampa HEAT
    REACCION       = "reaccion"         # mantener T, dejar reaccionar
    ENFRIAMIENTO   = "enfriamiento"     # rampa COOL
    DESCARGA       = "descarga"         # transferencia out
    LIMPIEZA       = "limpieza"         # CIP / saneamiento
    ESPERA         = "espera"           # tiempo muerto / hold


# ─────────────────────────────────────────────────────────────
# Tarea individual
# ─────────────────────────────────────────────────────────────

@dataclass
class Task:
    """Una tarea del ciclo batch.

    Args:
        name:           identificador legible (e.g. "load_reactor")
        kind:           categoría (TaskKind)
        duration_s:     duración fija en segundos.  None → la
                        resuelve ode_hook (Capa 2).  Si ambos None
                        cycle_time_s() lanza ValueError explícito.
        service:        servicio que consume (e.g. "steam", "CW",
                        "electricity").  None → no consume.
        utility_rate:   PICO instantáneo del servicio mientras la
                        tarea está activa.  Unidades libres
                        (kg/s para vapor, kW para electricidad, etc.)
                        —  el caller las interpreta consistentemente.
        ode_hook:       función opcional invocada por Capa 2 para
                        calcular duración dinámica.  Firma:
                            ode_hook(task) -> float  # segundos
                        Capa 1 NO la invoca automáticamente.
    """
    name:         str
    kind:         TaskKind
    duration_s:   Optional[float] = None
    service:      Optional[str]   = None
    utility_rate: float           = 0.0
    ode_hook:     Optional[Callable[["Task"], float]] = None

    def has_resolved_duration(self) -> bool:
        """True si la tarea tiene duración numérica disponible."""
        return self.duration_s is not None


# ─────────────────────────────────────────────────────────────
# Receta batch
# ─────────────────────────────────────────────────────────────

@dataclass
class BatchRecipe:
    """Receta de ciclo batch.

    Args:
        name:                   identificador (e.g. "esterification_v1")
        tasks:                  lista ORDENADA y LIBRE de Task.
        product_mass_kg_per_batch: kg de producto principal por batch.
                                Es la base para producción anual.
    """
    name: str
    tasks: List[Task] = field(default_factory=list)
    product_mass_kg_per_batch: float = 0.0


# ─────────────────────────────────────────────────────────────
# Funciones core (NO usan ode_hook automáticamente)
# ─────────────────────────────────────────────────────────────

def cycle_time_s(recipe: BatchRecipe) -> float:
    """Tiempo de ciclo total en segundos = Σ duration_s.

    Lanza ValueError EXPLÍCITO si alguna tarea no tiene duration_s
    resuelta.  El caller debe haber corrido resolve_dynamic_durations
    antes si la receta usaba ode_hook.
    """
    if not recipe.tasks:
        raise ValueError(f"BatchRecipe '{recipe.name}' no tiene tareas.")
    total = 0.0
    for t in recipe.tasks:
        if not t.has_resolved_duration():
            raise ValueError(
                f"Tarea '{t.name}' ({t.kind.value}) en receta "
                f"'{recipe.name}' no tiene duration_s.  Definir un "
                f"valor fijo o resolver via ode_hook antes de medir "
                f"cycle_time."
            )
        total += t.duration_s
    return total


def batches_per_year(recipe: BatchRecipe,
                      availability: float = 0.90) -> float:
    """Batches operados por año.

        batches/año = (horas operativas/año) / (tiempo de ciclo en horas)
                    = (8760 × availability) / (cycle_time_s / 3600)

    availability ∈ [0, 1].  Default 0.90 ≈ 8 % downtime industrial
    típico para plantas batch maduras (limpiezas, mantenimiento,
    cambios de receta).
    """
    if availability < 0 or availability > 1:
        raise ValueError(f"availability={availability} fuera de [0,1].")
    ct_s = cycle_time_s(recipe)
    if ct_s <= 0:
        raise ValueError(f"cycle_time={ct_s}s ≤ 0; receta inválida.")
    ct_hr = ct_s / SECONDS_PER_HOUR
    return (HOURS_PER_YEAR * availability) / ct_hr


def annual_production(recipe: BatchRecipe,
                       availability: float = 0.90) -> float:
    """Producción anual equivalente (kg/año).

        kg/año = (batches/año) × kg_por_batch
    """
    return batches_per_year(recipe, availability) * \
           recipe.product_mass_kg_per_batch


def utility_peaks(recipe: BatchRecipe) -> Dict[str, float]:
    """Pico instantáneo por servicio.

    Si dos tareas usan el mismo servicio con caudales distintos,
    devuelve el máximo (NO la suma — no hay solapamiento dentro
    de UN solo equipo; las tareas son secuenciales).  Para
    scheduling multi-unidad ver Capa 4 (fuera de alcance).

    Returns:
        dict {servicio: pico}.  Vacío si la receta no consume
        servicios.
    """
    peaks: Dict[str, float] = {}
    for t in recipe.tasks:
        if t.service and t.utility_rate > 0:
            prev = peaks.get(t.service, 0.0)
            if t.utility_rate > prev:
                peaks[t.service] = t.utility_rate
    return peaks


def to_schedule_block(recipe: BatchRecipe,
                       availability: float = 0.90) -> Dict:
    """Bloque de metadata batch que Capa 3 inyecta en el dict de
    schedule (clave nueva `schedule["batch"]`).  Lectura defensiva:
    los consumidores existentes (CashFlowModel, results_ui, reporte
    Excel) NO leen esta clave — la ignoran completamente.

    Returns:
        dict con:
            cycle_time_s          (float)
            cycle_time_h          (float)
            batches_per_year      (float)
            annual_production_kg  (float)
            utility_peaks         (dict[servicio: pico])
            availability          (float)
            recipe_name           (str)
            n_tasks               (int)
    """
    ct_s = cycle_time_s(recipe)
    bpy  = batches_per_year(recipe, availability)
    ann  = annual_production(recipe, availability)
    return {
        "cycle_time_s":          ct_s,
        "cycle_time_h":          ct_s / SECONDS_PER_HOUR,
        "batches_per_year":      bpy,
        "annual_production_kg":  ann,
        "utility_peaks":         utility_peaks(recipe),
        "availability":          availability,
        "recipe_name":           recipe.name,
        "n_tasks":               len(recipe.tasks),
    }


# ─────────────────────────────────────────────────────────────
# Hook para Capa 2 (extensión, NO invocada por Capa 1)
# ─────────────────────────────────────────────────────────────

def resolve_dynamic_durations(recipe: BatchRecipe,
                               solver: Optional[Callable] = None) -> None:
    """Llena `task.duration_s` para todas las tareas que tengan
    `ode_hook` definido y no tengan duración fija aún.

    Args:
        recipe: BatchRecipe a resolver in-place.
        solver: opcional, callable adicional al que se pasa cada
                task con ode_hook; si None, se invoca task.ode_hook(task)
                directamente.  Capa 2 lo usa para inyectar dependencias
                (reactions_db, etc.) cuando hace falta.

    NOTA — esta función ES el punto de extensión para transitorio:
    Capa 2 implementa ode_hooks que llaman a solve_batch_reactor
    (adaptación de solve_pfr) y devuelven la duración hasta una
    conversión objetivo.  Capa 1 nunca invoca esto por sí sola
    (aislamiento estricto).
    """
    for t in recipe.tasks:
        if t.duration_s is not None:
            continue           # ya tiene duración fija
        if t.ode_hook is None:
            continue           # ni hook ni fija → quedará sin resolver
        if solver is not None:
            t.duration_s = float(solver(t))
        else:
            t.duration_s = float(t.ode_hook(t))
