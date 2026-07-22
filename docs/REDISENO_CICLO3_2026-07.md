# Rediseño del frontend — ciclo 3, implementación (julio 2026)

Implementación del paquete de Design "Ciclo 3" (4 artboards,
`docs/design_ciclo3/ciclo3_glifos_sudoku_anotacion_gradiente.html`,
respuesta a `docs/PROMPT_DESIGN_CICLO3.md`). Evidencia visual:
`outputs/design3a_glifos_light.png` (los 22 glifos renderizados por el
sistema real). Regresión: `tests/test_ciclo3.py` (13 tests) +
`test_glyph_coverage` actualizado.

## 3a — Diferenciación de glifos por familia

- Nace **`glyph_specs.py`**: transcripción LITERAL del subset SVG del
  bundle (22 specs en caja 100×100, roles `o/d/body/dot`) + parser de
  paths SVG (M/L/H/V/Q/**A**/Z — con conversión endpoint→centro W3C
  para los arcos de kettle/válvula) + renderer QPainter con la regla de
  trazo única: STROKE_OUTLINE 1.6 / STROKE_DETAIL 1.0 (tinta al 52 %),
  **pens cosméticos = non-scaling-stroke** (el zoom no engorda el
  contorno), cap/join redondos.
- `BlockGlyph.draw` **delega primero en glyph_specs**; los `_draw_*`
  legados quedan solo para tipos sin spec nuevo (tanque, ambient,
  horno, ciclón, centrífuga, secador, cristalizador, ventilador,
  separador, hx_aircooler, hx_placa — sin geometría en el bundle).
- **Tres distinciones nuevas de eq_type**:
  · `Boiler — water tube` → `caldera_water` (domo + calderín + bancos
    verticales; fire-tube conserva el casco horizontal con tubos de
    humo),
  · `Tray — valve` → `platos_valve` (cheurones ⌃ sobre cada plato;
    sieve lleva las perforaciones punteadas),
  · `Reactor — jacketed agitated/non-agit.` → `reactor_jacket`
    (camisa de doble pared, familia ◇ del bundle).
- **Badge 24×24 = el MISMO glifo** (`editor_chrome.glyph_pixmap`):
  muere `equipment_icons.py` (tercer lenguaje redundante) y con él el
  badge de mixer que heredaban los WHB (el fallback `eq-mixer` de
  `icon_for_eq_type`). El badge de esquina del bloque también usa el
  glifo. `pfd_symbols` deja de ser fallback del lienzo: su rol es la
  hoja SVG de exportación.
- HX casco-y-tubo ×6 comparten `hx` a propósito (decisión cerrada del
  bundle — diferenciarlas sería textura invisible a 24 px).

## 3b — Estado sudoku en las corrientes

- La pill/burbuja lleva la marca de procedencia de la MASA al **borde
  de arranque**: `▪` declarada (tinta `spec`), `◦` derivada
  (`ink_mute`), `↻` reciclo/torn (`phase_2ph` — violeta frío ya
  existente, cero tokens nuevos). Tooltip con el término + una línea.
  El BubbleManager deriva el estado de la misma fuente que el DOF
  audit (`_recycle_stream_ids` → SCC del solver).
- **Torn tiene marca propia** (decisión argumentada del bundle): es el
  único punto del diagrama donde el número no es exacto sino
  convergido a tolerancia — didáctico, no ruido.
- **Leyenda del Marco PFD**: fila nueva `PROCEDENCIA · masa` (banda
  +22 px) con los mismos tres glifos y términos.
- **Diálogo DOF**: strip "▪ Declaradas N · ◦ Derivadas N · ↻ Reciclo
  (torn) N" bajo el hero — mismo vocabulario en pill, leyenda y DOF.

## 3c — Herramienta de anotación (T)

- Nace **`annotations.py`** (`AnnotationItem`): click con la T activa
  coloca la caja en edición directa (nota vacía se descarta al blur —
  sin modal); doble-click re-edita; Enter multilínea; Esc/blur
  confirma; drag mueve (undo por snapshot); Supr o menú contextual
  borra. Guía opcional recta a un punto (el próximo click la fija;
  borrarla no borra la nota).
- Estilo SOLO de la escala del sistema: 3 estilos (micro `FONT_LABEL` /
  rótulo `FONT_UI` / título `FONT_TITLE`, peso 600) × 3 tintas
  (`ink`/`ink_soft`/`danger` para revisión △) × fondo transparente o
  pill `label_bg` al 88 %. Sin negrita/itálica libre ni color libre.
- **Persistencia**: `Flowsheet.annotations` (to_dict/from_dict, JSONs
  viejos cargan limpio) → undo/redo gratis por snapshot; z=40; escala
  con el zoom como texto de plano.
- La **T volvió a la paleta** (TOOLS) y Vista ▸ "Mostrar anotaciones"
  oculta SOLO en pantalla: el export siempre las incluye
  (`_render_to_painter` las fuerza visibles y restaura).

## 3d — Gradiente térmico en corrientes de servicio

- **Continuo** (decisión 1 del bundle): el trazo va del color de la T
  de ESTA corriente al de la SIGUIENTE del lazo (extremos
  `service_*_pale/deep` del ciclo 2), con **stops interpolados por la
  fracción de longitud acumulada** de cada segmento — un jumper NO
  reinicia el color (decisión 2). Implementado como paint() por
  segmentos con un QLinearGradient cada uno (los arcos de hops ~8 px
  toman el trazo del segmento — invisible a esa escala).
- **Se apaga** a zoom < 0.6 o trazo pintado < 48 px → sólido medio
  (`service_hot/cold`). **El semáforo tiene prioridad**: error/warning
  pintan sólido danger/amber (el gradiente no puede ocultar un
  desbalance). La flecha hereda el color de LLEGADA.
- Export: hereda los tokens light por el mecanismo del ciclo 2
  (`_export_palette_ctx`).

## Divergencias razonadas respecto al bundle

1. La tabla de mapeo del bundle asigna `#g-torre-enf` a `cyclone` —
   error evidente de data del doc (un ciclón no es una torre de
   enfriamiento); el ciclón conserva su glifo previo del ciclo 1d.
2. Los hops (jumpers) dentro de un gradiente se pintan con el gradiente
   del segmento, no con un sub-gradiente propio del arco — a ≤8 px la
   diferencia no existe visualmente y evita duplicar el stroker.

## ⚡ Pendientes que el bundle dejó anotados (sin cambios)

- 3a: sieve vs valve al límite a 22 px (badge); mixer dynamic no está
  en el catálogo.
- 3b: procedencia POR COMPONENTE (excede la pill → inspector).
- 3c: anclaje que sigue al bloque al moverlo; cuadro de revisiones △N
  formal en el export.
- 3d: gradiente en corrientes de PROCESO (necesita eje de T de
  referencia acordado).
