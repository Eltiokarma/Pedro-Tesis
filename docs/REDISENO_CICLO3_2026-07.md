# Rediseño del frontend — ciclo 3, implementación (julio 2026)

Implementación del paquete de Design "Ciclo 3" (glifos · corrientes ·
anotación, `docs/design_ciclo3/`, respuesta a
`docs/PROMPT_DESIGN_CICLO3.md`). Suite completa verde: **610 tests**
en cada artboard. Evidencia visual en `outputs/design3*_*.png`.

## Qué se implementó, por artboard

### 3a — Diferenciación de glifos (`bb934c4`)
- Nace `glyph_specs.py`: los **48 símbolos SVG de Design embebidos
  VERBATIM** + parser del subset (rect/circle/ellipse/line/path
  M·L·H·V·Q·A·Z·l, `<g>` de un nivel) + renderer QPainter.  El
  contrato de clases del spec mapea 1:1 al sistema: `o` →
  STROKE_OUTLINE con tinta del estado, `d` → STROKE_DETAIL a tinta
  52 %, `body` → fill del semáforo, `dot` → tinta-detalle; unrun
  puntea contornos y los dasharray explícitos se respetan.
- `editor_chrome` monta los 48 como `_draw_*` data-driven sobre
  BlockGlyph (los refrescados REEMPLAZAN el QPainter a mano), deriva
  BLOCK_DIMS del bbox de contenido, remapea EQ_TYPE_TO_ISA según la
  tabla de Design y los botones de la paleta muestran el glifo real.
- Resultado medible: **56 tipos pasan de 29 siluetas (11 únicas) a 48
  (44 únicas)** — solo quedan los 4 grupos ◇ compartidos-a-propósito
  con decisión escrita (hx ×6 casco-y-tubo, hx_whb, mezclador,
  tambor).  Mueren los aliasing peligrosos: alivio ≠ globo ≠ 3 vías,
  CSTR ≠ encamisado ≠ autoclave, axial ≠ centrífugo ≠ rotativo…

### 3b — Tabla de corrientes + inspector (`e6912d0`)
- La tabla hi-fi y el inspector ya hablaban el sistema (Design mockeó
  sobre esa implementación — chips de rol, dots de fase, pill, barra
  spec/auto, 5 secciones idénticas).  Deltas reales implementados:
  **subrayado spec 2px** bajo valores declarados de flujo/T/P (el
  spec/auto ya no vive solo en el color de la tinta), **columna de
  composición colapsable** (botón ▾/▸ en la toolbar) y **sincronía
  canvas → tabla** (seleccionar un stream resalta su fila;
  `highlight_stream` con guard anti-ciclo).

### 3c — Herramienta de anotación T (`9546d39`)
- `AnnotationItem`: nota de PLANO con las 6 decisiones del artboard —
  click coloca + edición directa (vacía se descarta), doble-click
  re-edita, drag con undo, estilos solo de la escala del sistema
  (Micro/Rótulo/Título · 600 · Mono), color ink/suave/revisión, pill
  `label_bg`, capa z=40.  Persistencia en `Flowsheet.annotations`
  (undo/redo gratis por snapshot); Vista ▸ Mostrar anotaciones oculta
  en pantalla pero el export SIEMPRE las incluye
  (`_export_palette_ctx`).  La T vuelve a la paleta.

## Divergencias razonadas

1. **Handles laterales de ancho de wrap (3c)** no implementados: el
   ancho se adapta al texto (multilínea con Enter).  Si el uso lo
   pide, el campo `w` del dict ya está previsto en el modelo.
2. **Rotación de anotaciones**: descartada por el propio spec ("texto
   de plano, se lee horizontal").

## Pendientes (sección ⚡ del bundle de Design, no implementados)

- 3a: platos sieve vs valve al límite a 22 px — evaluar diferenciar
  por downcomer si el uso pedagógico lo pide.
- 3a: `Mixer — dynamic` no está en el catálogo; si se suma, glifo
  propio (hoy sería catálogo muerto).
- 3b: columnas configurables por el usuario (persistir en prefs.json)
  y orden/agrupado por sección de proceso.
- 3c: anotación anclada a bloque/stream (requiere modelo de anclaje)
  y cuadro de revisiones △N en el export.
