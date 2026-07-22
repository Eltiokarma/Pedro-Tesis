# PLAN — Ciclo 4 (backlog anotado)

**Fecha de anotación:** 2026-07-22
**Estado:** PENDIENTE — este documento junta todo lo que quedó
deliberadamente fuera al cerrar el ciclo 3 y el plan de auditoría
frontend. Es el punto de arranque de la próxima tanda; nada de esto es
urgente ni bloquea la tesis.

## A. ⚡ del bundle de Design ciclo 3 (deuda que el propio Design anotó)

| Artboard | Pendiente | Nota |
|---|---|---|
| 3a | Sieve vs valve al límite a 22 px | A tamaño de badge el rasgo se pierde; diferenciar por downcomer solo si el uso pedagógico lo pide |
| 3a | Mixer — dynamic | No está en el catálogo; si se suma, glifo propio (no dibujar catálogo muerto) |
| 3b | Procedencia POR COMPONENTE | La marca actual es por corriente; marcar qué componente vino declarado vs deducido excede la pill → iría al inspector |
| 3c | Anclaje de nota que sigue al bloque/corriente | Requiere modelo de anclaje; el MVP dejó la guía visual estática |
| 3c | Cuadro de revisiones △N en el export | Bloque formal rev. A/B/C con fecha; el △ manual del estilo "Revisión" cubre el MVP |
| 3d | Gradiente térmico en corrientes de PROCESO | Solo servicio por ahora; proceso necesita un eje de T de referencia acordado, no el par pale/deep de la corriente |

## B. Remanentes ⚡ del ciclo 2 aún vivos

- **`solver_report.py`** duplica una paleta light-only propia (§G.5 de
  `AUDITORIA_UI_2.md`) → unificar con tokens.
- **`hx_edu.py`** (SVG educativo) y las **curvas matplotlib** de
  `inspector_evidence` (~45 hex hardcodeados que derivan en silencio si
  los tokens cambian) → ola de tokenización propia.
- **`streams_table` / `stream_inspector`**: pasada formal de diseño
  (hoy consumen tokens de fase pero nunca tuvieron artboard).
- Menores (§G de la auditoría 2): el chip del solver de la topbar no
  siempre recibe iter/tiempo (`update_solver_chip` — verificar cableado
  en todos los caminos de solve); la anotación de payback de las
  figuras queda tenue en dark; 1 hex suelto en `inspector_widgets.py`.

(La herramienta de anotación y el gradiente térmico, que estaban en
esta lista, se cerraron en el ciclo 3 ✓.)

## C. Del plan de auditoría frontend (fuera de alcance declarado)

- **Viscosidad μ(T) y conductividad k/Prandtl** (Frente 4,
  `CASOS_LIBRO.md`): hoy `pressure_drop` recibe μ por argumento con
  defaults por caso y la U de HX sale de rangos típicos por servicio.
  Poblarlas seguiría el patrón capa-por-compuesto del `.md` (como
  `rho_ref`), NO una tabla paralela.
- **21 eq_types sin instancia en los 58 ejemplos** (variantes: U-tube,
  double/multiple pipe, condensers, spiral/flat plate, WHB field
  erected, rotary, reciprocating pump, reformer, fan axial,
  trays/packing, mixer inline, decanter centrifuge, relief/3-way,
  natural draft): glifo/puertos/sizer están; decidir si ameritan
  mini-fixtures de UI o un par de ejemplos nuevos que los usen.
- **Origin-tagging de reacciones custom nacidas del predictor**
  (Frente 5): `reaction_from_dict` no persiste `origin`/
  `estimation_method` — hoy una reacción aceptada desde "Sugerir
  productos" queda indistinguible de una escrita a mano. Extender el
  esquema del dict es barato y cierra la trazabilidad de procedencia.

## D. Sugerencia de arranque

1. **B** primero (mecánico, sin decisiones de diseño): solver_report +
   hx_edu/matplotlib + menores §G — muere la última clase de hex
   sueltos.
2. **C.3** (origin-tagging) — chico y cierra procedencia end-to-end.
3. **A** requiere o un mini-prompt de Design (procedencia por
   componente, revisiones △N) o decisión propia acotada (anclaje de
   notas).
4. **C.1/C.2** al final — dependen de si el alcance de la tesis pide
   ΔP/U más honestos o más cobertura de catálogo.

**Regla de la casa:** todo cambio pasa por el gate (58/58) + suite +
regresión nueva por hallazgo; los bugs se documentan en
`BUGS_ENCONTRADOS_EJEMPLOS.md` con reproducción mínima.
