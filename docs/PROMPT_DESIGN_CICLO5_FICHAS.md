# Prompt para la fase Design — ciclo 5 (Fichas Técnicas de equipo)

**Uso:** copiar el prompt de abajo (desde "---PROMPT---") a una sesión de
Claude Design, adjuntando estos archivos del repo:

- `tokens.py` (sistema de diseño vigente: paleta viva light/dark + acentos,
  FONT_DISPLAY/TITLE/UI/VALUE/HINT/LABEL, strokes, severidad única)
- `docs/FICHAS_TECNICAS_INVENTARIO.md` (**el insumo central de este ciclo**:
  inventario aplanado de todos los datos por equipo + contrato
  `datasheet_spec` de 8 secciones + cobertura por familia)
- `docs/REDISENO_CICLO4_2026-07.md` (qué quedó implementado del ciclo 4:
  BookTable, MetricCard que fluye, ClassificationScale, vocabulario sudoku)
- `inspector_widgets.py`, `dialog_kit.py` y `book_table.py` (el kit a
  extender: MetricCard, kicker, kit_table, pills, BookTable)
- `block_inspector.py` solo secciones `_sections_for` y `_build_section_content`
  (la superficie donde vive la ficha; el resto del archivo no hace falta)
- capturas de referencia del estado actual en `outputs/`:
  `design4_booktable_{stoich,flash,wh}_{light,dark}.png`,
  `design4_ns_metriccard_{light,dark}.png`,
  `design4_atombalance_smr_{light,dark}.png`

---PROMPT---

Sos el diseñador del frontend de una app de escritorio (PySide6/Qt) de
simulación de procesos químicos con análisis económico, para una tesis de
ingeniería. UI en español. Llevamos cuatro ciclos auditoría→design→
implementación juntos, todos implementados: tokens + semáforo + topbar
(ciclo 1), capa canvas theme-aware + puertos técnicos + kit de diálogos +
tipografía (ciclo 2), glifos diferenciados + procedencia sudoku + anotaciones
+ gradiente térmico (ciclo 3), tablas de libro + identidades ricas + balance
de átomos (ciclo 4: BookTable con columnas medidas, MetricCard que fluye con
ClassificationScale, ▪ declarada / ◦ solver). Este ciclo estrena una
superficie nueva completa: la **Ficha Técnica de equipo** — el datasheet de
ingeniería que cierra el ciclo simular → dimensionar → costear → **emitir**.

Tu identidad vigente, a respetar: papel cálido (`#f6f3ec`/`#fbfaf6` y su par
sepia-carbón dark), tinta tierra desaturada, acento teal `#0d6e78` (elegible
terracota/cobalto/oliva), IBM Plex Sans/Mono, éxito discreto, warning/error
con color + símbolo (daltónico-safe), export en papel claro. Como siempre:
el mecanismo es nuestro; tu trabajo es **decidir y especificar valores y
comportamientos visuales**.

## Contexto nuevo desde tu último ciclo

1. Hicimos el barrido completo del sistema y aplanamos TODO lo que el motor
   sabe de cada equipo en `docs/FICHAS_TECNICAS_INVENTARIO.md` (adjunto).
   Léelo primero: define el contrato `datasheet_spec` de 8 secciones
   (identidad, condiciones, corrientes, diseño, materiales, auxiliares,
   costos, notas), el vocabulario de procedencia por campo (declarado /
   calculado / típico / estimado / pendiente — extiende tu sudoku ▪/◦), y
   la cobertura: 56 eq_types con fallback genérico garantizado, fichas
   ricas en HX/bombas/compresores/columnas/reactores/flash/boilers.
2. La ficha tiene DOS destinos con el mismo contenido: sección nueva del
   inspector (pantalla, light/dark) y **export PDF multipágina** (papel
   claro, una ficha por página, encabezado proyecto/tag/revisión/fecha).
   El export retoma tu deuda ⚡ del ciclo 4d: el cuadro de revisiones △N
   formal (rev. A/B/C con fecha) — este es su lugar natural.
3. Restricción de honestidad del proyecto: la ficha NO muestra campos que
   el motor no determina (espesores, bridas, código ASME, tipo TEMA).
   Van como lista corta "Ingeniería de detalle pendiente" — nunca celdas
   vacías. Cada valor lleva su procedencia y su fuente (Turton/Sinnott/
   Perry/Crane ya citadas en el motor).

## Artboards que te pido

### 5a — Anatomía de la Ficha Técnica (el encargo grande)

La ficha completa de UN equipo rico, en pantalla (inspector) y su par light/
dark. Escena de prueba: la bomba **P-302 de `cw_natural`** (tiene TODO:
Q/head/NPSH/margen de cavitación NEGATIVO −8.19 m/N_s 8003 con rodete
mixto/η/rpm + material + costo + warning). Decisiones tuyas:

- Jerarquía de las 8 secciones del contrato: ¿orden fijo tipo hoja TEMA
  (identidad arriba, condiciones, corrientes como tabla, diseño como grilla
  de métricas, pie de costos/notas)? ¿qué colapsa y qué no?
- Cómo conviven los átomos existentes dentro de la ficha: MetricCard para
  el diseño, BookTable para corrientes/tablas, ¿o la ficha pide una
  densidad propia más compacta (registro "documento" vs registro "panel")?
- El encabezado de ficha: tag grande + servicio + eq_type + categoría —
  ¿kicker? ¿strip de contexto como BookTable?
- Warnings dentro de la ficha (cavitación, S fuera de rango Turton,
  approach < dT_min): ¿banda semántica, pills en sección notas, ambos?

### 5b — Procedencia de 5 estados por campo

Tu sudoku actual es binario (▪ declarada / ◦ solver). El contrato de ficha
pide CINCO: declarado · calculado · típico (de tabla, citando cuál) ·
estimado (heurística) · pendiente (ingeniería de detalle). Especificá el
sistema visual completo: glifos/pills/tinta por estado, cómo se lee en una
grilla densa sin ruido, y la leyenda (¿pie de ficha? ¿tooltip?). Ojo:
"pendiente" NO es un error — es alcance declarado (estimación Class 4/5);
no puede usar el registro de danger.

### 5c — La ficha mínima honesta

El fallback genérico (mixer, splitter, válvula 3-way): identidad +
condiciones + corrientes + S + material + costo, y nada más. Diseñala para
que se vea **completa y deliberada, no rota**. Escena de prueba: el mixer
estático de `smr_eq` y el splitter de `bypass`. Decisión tuya: ¿la ficha
mínima usa la misma anatomía con secciones ausentes colapsadas, o una
variante de una columna?

### 5d — La ficha como documento: export PDF

La misma P-302 y un HX (E-101 de `hda`) como páginas de PDF en papel claro:
encabezado de documento (proyecto, tag, rev, fecha, página N de M), cuadro
de revisiones △N (tu deuda 4d), pie con fuentes bibliográficas. Decidí:
márgenes/grilla de página, si el PDF comparte tokens con pantalla o tiene
registro documento propio (¿serif para valores? ¿líneas de corte?), y cómo
degrada el color semántico en impresión B/N (símbolo ya presente — ¿basta?).

### 5e — Navegación y export masivo

Cómo se llega: la sección "Ficha" en el sidebar del inspector (orden entre
las secciones existentes: identidad, termo, reactividad, columna, flash,
especial, sizing, utility, economía, diagnóstico — ¿dónde va?), y el flujo
"Exportar fichas técnicas" del proyecto completo (~20-60 equipos en `hda`):
¿diálogo con checklist de equipos? ¿progreso? ¿qué pasa con bloques
auto_aux (excluidos) y con equipos sin resolver (ficha con procedencia
"pendiente" o excluidos)? Especificá el flujo completo.

## Entregable

Como en los ciclos anteriores: bundle HTML con artboards 5a-5e, specs
dibujables (valores exactos: pt, px, tokens, espaciados), par light/dark de
cada pieza de pantalla + versión papel del PDF, y la lista ⚡ de lo que
decidas dejar fuera con su razón. Nosotros montamos todo después
(`datasheet.py` agregador Qt-free ya contratado, sección del inspector,
export XLSX/PDF).
