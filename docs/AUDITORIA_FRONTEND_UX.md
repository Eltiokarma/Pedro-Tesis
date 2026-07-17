# Auditoría UX/UI del frontend — handoff para fase Design

**Fecha:** 2026-07-14 · **Rama:** `claude/frontend-audit-design-k48oko` · **Alcance:** solo lectura, cero cambios de código.

Este documento tiene doble propósito: (1) auditoría técnica con evidencia `archivo:línea` verificable, y (2) brief de diseño para que Claude Design (u otra fase Design) pueda auditar visualmente y proponer mejoras sin tener que redescubrir el código. Las capturas de referencia del estado actual están en `outputs/econ_*.png`.

---

## 0. Resumen ejecutivo

Las cuatro quejas del usuario se confirman con evidencia, y en tres de los cuatro casos **la solución ya está a medio construir dentro del propio código**:

| # | Queja | Veredicto | Hallazgo clave |
|---|-------|-----------|----------------|
| A | "El cuadrado de colores alrededor del equipo es desordenado" | **Confirmado** | El halo es un rect extra dibujado 6 px fuera del símbolo. El mecanismo para tintar el símbolo mismo (`BlockGlyph.draw(stroke, fill)`) **ya existe y ya se usa** para warning/error — solo falta extenderlo a ok/stale/unrun y apagar el halo. |
| B | "Botones de arriba desordenados, algunos obsoletos" | **Confirmado** | Hay **4 superficies de botones** apiladas (2 visibles + 2 toolbars legacy ocultas nunca borradas), 1 botón muerto (✦ Auto-arrange), 1 botón mal etiquetado (▦ "grid" que en realidad alterna el Marco PFD), y acciones triplicadas con 3 etiquetas distintas. |
| C | "Parece que faltan símbolos" | **Confirmado, con matiz** | No faltan mapeos (56/56 tipos mapean), pero **51 de 56 tipos comparten glifo** — equipos distintos se ven idénticos (un splitter se dibuja como mixer). Existen 17 SVGs diferenciados (patch PFD-ICN-002 en `pfd_symbols.py`) que el lienzo **nunca invoca**. |
| D | "La parte económica es un mamarracho" | **Confirmado — y el código lo admite** | Son literalmente **dos UIs completas apiladas** en un mismo diálogo modal. `economics_panel.py:609` se autodescribe: *"Visual feo-pero-correcto; embellecimiento = fase Design posterior."* Esa fase Design es exactamente este handoff. |

Problema transversal: **coexisten dos sistemas de color** (paleta de halos en `flowsheet_qt.py` vs tokens `TOK` de `block_inspector.py`) y **tres lenguajes de iconos** (glifos unicode, SVG `icons.py`, siluetas QPainter). Cualquier mejora debe empezar por unificar tokens.

---

## A. Indicador de estatus de equipos (el "cuadrado de colores")

### A.1 Estado actual

- El cuadrado es `_StatusHaloItem(QGraphicsRectItem)` — `flowsheet_qt.py:2308-2327` — un rect redondeado dibujado a `z=-1` con padding de 6 px alrededor del símbolo (`W+12 × H+12`), creado por bloque en `BlockItem.__init__` (`flowsheet_qt.py:3409-3428`).
- El color/grosor por estado se aplica en `BlockItem.set_status()` (`flowsheet_qt.py:3775-3798`):
  - `error` → rojo sólido 2.5 px · `warning` → ámbar sólido 2.0 px · `ok` → verde sólido 1.2 px · `stale`/`unrun` → punteado 1.2 px.
- Mapa de estados `STATUS_COLORS` (`flowsheet_qt.py:296-303`, constantes en `:263-267`):

| Estado | Color | Hex |
|---|---|---|
| `ok` | verde | `#2e7d32` |
| `warning` | ámbar | `#f9a825` |
| `error` | rojo | `#c62828` |
| `unrun` / `empty` | azul | `#1976d2` |
| `stale` | violeta | `#7b1fa2` |

- Flujo: el solver publica `block_status`/`stream_status` → `_apply_solver_status()` (`flowsheet_qt.py:6911-6931`); cualquier edición degrada todo a `stale` vía `_mark_dirty()` (`:6933-6950`). Estado por defecto: `stale` (`:3414`).
- Visuales de estado adicionales que ya existen: chip "!" de warning/error sobre el símbolo (`editor_chrome.py:1799-1807`), spinner de solving y halo de hover (`:1740-1753`), coloreo de corrientes por estado (`flowsheet_qt.py:4207-4242`), chip global en status bar con iconos ✓⚠✗●◌○ (`:6875-6905`, `STATUS_ICONS :306-313`).

### A.2 Por qué se ve desordenado

1. **Doble caja al seleccionar:** la selección dibuja OTRO rect punteado índigo `#283593` (`set_selected_visual`, `flowsheet_qt.py:3741-3749`) → un equipo seleccionado con error muestra **dos cajas anidadas** (índigo punteada + roja sólida) más el anillo punteado del propio glifo (`editor_chrome.py:1790-1797`). Tres marcos simultáneos.
2. **La selección pisa el color de estado del símbolo:** al seleccionar, el glifo pasa a estado `"selected"` (accent) y pierde su trazo rojo/ámbar (`flowsheet_qt.py:3795-3796`, `:3865-3871`, `:3912-3920`) — el estado solo sobrevive en el halo, lo que obliga a mantener el halo.
3. **Dos paletas en conflicto:** el halo usa `#c62828`/`#f9a825` mientras el glifo usa los tokens `TOK` (`danger=#b8453a`, `amber=#b8841a`, `accent=#0d6e78`, de `block_inspector.py:50-86` vía `ISA_STATE_PEN`, `editor_chrome.py:1643-1650`). El mismo "error" tiene dos rojos distintos a 6 px de distancia.
4. Con muchos equipos, N cajas de N colores compiten con las corrientes y el marco PFD: ruido geométrico puro.

### A.3 Dirección propuesta (para Design)

**Matar el halo y llevar el estado al cuerpo del símbolo.** Factibilidad alta: `BlockGlyph.draw(p, isa, w, h, stroke, fill, stroke_width)` (`editor_chrome.py:136-156`) ya parametriza trazo y relleno de todos los glifos, y warning/error ya tintan el trazo hoy. El comentario en `flowsheet_qt.py:3585` confirma que ok/stale/unrun se dejaron en neutro *porque el halo ya existía* ("el halo verde ya está en status_halo").

Cambios conceptuales (sin implementar aún):
1. `_isa_state_for_status()` (`flowsheet_qt.py:3582`) deja de colapsar ok/stale/unrun a `idle`; `ISA_STATE_PEN` (`editor_chrome.py:1643`) gana esos estados.
2. Estado también en el **relleno** (tinte suave del `fill`, hoy siempre blanco `bg_elev`), no solo el trazo: p. ej. error = trazo danger + fill danger al 8-12 %; ok = trazo neutro (el éxito debe ser silencioso — que el "verde todo bien" no grite); stale = trazo/fill atenuados o desaturados; unrun = trazo punteado en el propio glifo.
3. La **selección se separa del estado**: anillo exterior propio que no reemplace el color de estado (hoy `"selected"` clobbea warning/error).
4. El chip "!" existente queda como refuerzo de warning/error (color + símbolo = accesible para daltonismo; hoy el halo es solo-color).
5. Una sola paleta semántica: unificar `STATUS_COLORS` con `TOK` (ver §E).

---

## B. Toolbar superior

### B.1 Estado actual — cuatro superficies apiladas

| Superficie | Qué es | Dónde | ¿Visible? |
|---|---|---|---|
| A. `EditorTopbar` | QFrame custom 52 px, glifos unicode | `editor_chrome.py:642`, instanciada `flowsheet_qt.py:5862` | Sí |
| B. Menú bar (Archivo/Editar/Vista/Simulación) | QMenuBar con iconos SVG 16 px | `flowsheet_qt.py:6044` | Sí |
| C. Toolbar legacy fila 1 "Archivo y edición" | QToolBar real, SVG 20 px + texto | `flowsheet_qt.py:6525` | **Oculta** (`:5910`) |
| D. Toolbar legacy fila 2 "Cálculo y análisis" | QToolBar real | `flowsheet_qt.py:6603` | **Oculta** |
| E. `EditorPalette` (flotante izq.) | herramientas + bloques | `editor_chrome.py:986` | Sí |
| F. `EditorZoom` (flotante inf-der.) | − / 100% / + / ⤢ | `editor_chrome.py:1330` | Sí |

C y D se construyen SIEMPRE y solo reaparecen vía Vista ▸ "Toolbars legacy" (`flowsheet_qt.py:6198-6203`). El menú es un superset completo de ambas: por eso se ocultaron, pero nunca se borraron.

### B.2 Defectos concretos en la barra visible (EditorTopbar)

Orden actual: `◆ logo · nombre + "v0.4 · sin guardar" ‖ ↶ ↷ | ✦ ▦ ‖ chip solver | Validar DOF · ▶ Resolver` (`editor_chrome.py:661-744`).

1. **✦ Auto-arrange está MUERTO** (`editor_chrome.py:708`): emite `autoArrangeRequested` que no conecta con nada — los guards `hasattr(self, "action_auto_arrange"/"action_autoarrange")` (`flowsheet_qt.py:6408-6411`) buscan métodos que **no existen en ninguna parte**. Clic → nada.
2. **▦ "Toggle grid" está mal etiquetado** (`editor_chrome.py:711`): su handler `_on_topbar_grid_toggle` (`flowsheet_qt.py:6461-6464`) dispara `_paper_action` = **Marco PFD** (Ctrl+M), no una grilla. Nace `checked=True` sin sincronizarse con el estado real del marco → check desincronizable.
3. **Tooltips mentirosos en ↶/↷**: anuncian ⌘Z/⌘⇧Z pero los botones no registran shortcut; los atajos reales viven en las QActions de la toolbar legacy oculta (`flowsheet_qt.py:6585, :6589`).
4. **"v0.4 · sin guardar" hardcodeado** (`editor_chrome.py:691`).

### B.3 Duplicaciones y obsolescencia

- `action_solve` es alcanzable 3 veces con **3 nombres distintos**: "▶ Resolver" (topbar), "Solve balances" (tb2 `:6609`), "Resolver balances" F5 (menú). Lo mismo con DOF ("Validar DOF" / "DOF / Balance…"). Undo/redo ×3, zoom ×3, Marco PFD ×3, Ejemplos ×2, Exportar ×2.
- **"Animación de flujo" existe como DOS QActions checkables independientes** (tb2 `flowsheet_qt.py:6643` y menú Vista `:6131`) → los dos checks pueden quedar en estados opuestos. (Tabla de corrientes sí comparte QAction — ese es el patrón correcto.)
- Herramienta **T (anotación) de la paleta es un stub**: solo cambia el cursor (`flowsheet_qt.py:6499-6502`); no hay código de colocación de texto.
- El menú Vista llama a sus propios docks "Biblioteca (vieja)", "Propiedades (viejo)" (`flowsheet_qt.py:6165-6167`).
- El icono `act-money` se reutiliza para 3 acciones distintas: OPEX extras, Perfil económico y Exportar a Excel (`flowsheet_qt.py:6608, :6652, :6654`).

### B.4 Inconsistencia de lenguaje visual

Tres idiomas de icono conviven: la topbar visible usa **glifos unicode como texto** (↶ ✦ ▦ ▶), los menús y toolbars legacy usan **SVG** (`icons.make_qicon`, gris `#3a3a3a`), y la paleta usa **siluetas ISA pintadas + emoji** (✋, ⚡). Tamaños de botón dispares: 32/28/40 px según superficie.

### B.5 Dirección propuesta (para Design)

1. **Borrar las toolbars legacy C y D** (y el toggle "Toolbars legacy"): el menú ya es superset. Esto elimina de golpe la mayor fuente de duplicación.
2. Topbar reorganizada por zonas de tarea:
   - **Izquierda — identidad/archivo:** logo · nombre de proyecto · estado de guardado real (no hardcode).
   - **Centro — edición del lienzo:** ↶ ↷ (con shortcuts reales) | Marco PFD (bien etiquetado, estado sincronizado) | anim. flujo (una sola QAction compartida).
   - **Derecha — flujo de trabajo de simulación:** chip solver → Validar DOF → ▶ Resolver → **Economía** (hoy el análisis económico no está en la topbar pese a ser el paso final del workflow; está enterrado en el menú Simulación).
3. Eliminar ✦ (o implementar auto-arrange de verdad; mientras no exista, fuera).
4. Un solo verbo por acción en todas las superficies ("Resolver" en todos lados, no 3 nombres).
5. Un solo sistema de iconos (los SVG de `icons.py` ya cubren todo; la topbar debería consumirlos en vez de unicode).
6. Acciones checkables compartidas (una QAction por concepto) para que los checks nunca desincronicen.

---

## C. Símbolos de equipos

### C.1 Estado actual — cobertura formal 100 %, diferenciación 9 %

- Catálogo canónico: 56 tipos en 12 categorías (`equipment_costs.EQUIPMENT_DATA`, `equipment_costs.py:102-405`).
- Render on-canvas: `IsaGlyphItem` → `BlockGlyph.draw` con **24 glifos QPainter** (`editor_chrome.py:126-628, 1653`); mapeo `EQ_TYPE_TO_ISA` (`editor_chrome.py:1484-1540`). Los 56 tipos mapean; ninguno cae al placeholder.
- **PERO solo 5 tipos tienen glifo único** (ciclón, columna, cristalizador, filtro, secador). Los otros 51 comparten:

| Glifo | Tipos que se ven idénticos |
|---|---|
| `hx` | 6 (fixed tube, U-tube, floating head, double pipe, multiple pipe, condenser) |
| `reactor` | 5 (CSTR, PFR, autoclave, jacketed ×2) |
| `compresor` | 4 (axial, centrifugal, reciprocating, rotary) |
| `platos` | 4 (tray sieve/valve, packing random/structured) |
| `bomba` / `valvula` / `hx_kettle` | 3 c/u |
| `mezclador` | 3 — **incluido el Splitter, que se dibuja como mixer** |
| otros 10 glifos | 2 c/u |

Esto explica el "parece que faltan símbolos": no faltan — **se repiten**.

### C.2 Trabajo ya hecho y desperdiciado

`pfd_symbols.py` contiene **94 símbolos SVG**, incluidos 17 diferenciados del patch PFD-ICN-002 (`pfd_symbols.py:1382-2059`): `reactor-pfr-coiled` vs `reactor-cstr-jacketed`, `compressor-axial`, `boiler-fire-tube` vs `water-tube`, `cooling-tower-induced`/`natural`, `tray-sieve-section`/`tray-valve-section`, `packing-random`/`structured`, `splitter-flow-divider`, `fan-axial`… El lienzo **solo los usa como fallback si falla el import de `editor_chrome`** (`flowsheet_qt.py:3542-3579`), o sea casi nunca. 43 símbolos de `SYMBOLS` no los referencia ningún `eq_type`.

### C.3 Bugs y deuda puntual

- **Badge incorrecto:** `Heat exch. — WHB packaged` y `WHB field erected` no tienen ícono propio y el fallback de `icon_for_eq_type()` les pone **badge de mixer** (`icons.py:186-188`, tras `:460-509`).
- 4 sistemas de símbolos paralelos con tecnologías y proporciones distintas (QPainter 60×60, SVG 130×60 ×2, SVG 24×24) y **anchos de trazo divergentes** (1.5/2.0 por estado en ISA con detalles internos hardcodeados a 1.6/1.2/1.0/0.9, ej. `editor_chrome.py:164-226`; 1.5 en los SVG). No hay token único de stroke.
- `equipment_icons.py:453+` es un docstring gigante con instrucciones de patch "pegar al final" — deuda de limpieza.
- Puertos: consistentes (52/56 tipos con puertos propios; solo trays/packings caen a in/out genérico, razonable; 73/73 puertos clasificados y coloreados — `equipment_ports.py:294-561`, `flowsheet_qt.py:248-256`).

### C.4 Dirección propuesta (para Design)

1. Decidir **un solo sistema de símbolos on-canvas** (los glifos ISA QPainter son el activo) y **matar o degradar explícitamente los otros tres** a su rol (badge 24×24 se queda; `pfd_symbols`/`equipment_icons` como assets de exportación o eliminación).
2. Priorizar diferenciación donde el aliasing confunde de verdad: **splitter ≠ mixer** (crítico, invierte semántica), PFR vs CSTR, compresor recíproco vs centrífugo, kettle vs WHB, boiler fire/water-tube, cooling tower induced/natural, tray vs packing. El patch PFD-ICN-002 ya define la geometría de referencia — portarla a `_draw_*` ISA.
3. Arreglar el badge de los dos WHB.
4. Token único de stroke y proporción para todos los glifos.

---

## D. Panel económico

### D.1 Estado actual — dos UIs apiladas (y el código lo sabe)

Entrada: menú Simulación y tb2 → `action_launch_analysis` (`flowsheet_qt.py:7530`) → `EconomicsPanel` **QDialog modal** 580×640 (`economics_panel.py:83-96`). Adentro:

1. **UI 1 — el formulario "feo-pero-correcto"** (`economics_panel.py`): todo el diálogo es un QScrollArea gigante (`:104-109`) con 4 QGroupBoxes de formularios apilados, dos botones full-width uno encima del otro ("Calcular", "Monte Carlo…", `:248-255`), y un QTextEdit Consolas 10 que imprime resultados como **tablas ASCII con box-drawing** (`:422-447`). Docstrings: *"El diseño visual es responsabilidad de una fase Design posterior"* (`:14-15`), *"Visual feo-pero-correcto; embellecimiento = fase Design posterior"* (`:609`).
2. **UI 2 — `EconRichView`** (`econ_richview.py:314`): una segunda UI completa (header 58 px + hero KPI 64 px + sidebar 150 px + tabs + footer 46 px) que al calcular se **monta dentro del pane 0 de la UI 1**, ocultando el resto (`economics_panel.py:473-508`). Reproduce un mockup de un handoff de diseño anterior (`econ_widgets.py:1-2`).
3. **UI 3 — legacy muerta**: `_render_econ_legacy` (`economics_panel.py:510-598`) se conserva entera "por si EconRichView falla".

### D.2 Defectos concretos (el "mamarracho", cuantificado)

- **KPIs por triplicado simultáneo:** NPV/TIR/Payback/CAPEX se muestran en el HeroStrip (`econ_richview.py:132-163`), otra vez en el Footer dos filas más abajo (`:252-258`), y en el dump ASCII (`economics_panel.py:423-446`). Los CAPEX cards se repiten como tabla en Contabilidad (`econ_richview.py:408-420` vs `:506-524`).
- **Dos tab bars idénticas** "Resultados/Monte Carlo/Contabilidad": la exterior (`economics_panel.py:274`, oculta en runtime `:491` pero construida) y la interior (`econ_richview.py:385`).
- **Sidebar de 7 ítems con solo 3 destinos:** Resumen/CAPEX/OPEX/Cash flow rutean TODOS al tab 0 (`econ_richview.py:355`) — 4 de 7 clics no hacen nada distinguible. La lógica `_set_tab/_on_side/_on_segmented` (`:358-378`) existe solo para que las dos navegaciones redundantes no desincronicen.
- **Scrolls anidados en 3 niveles** (diálogo `:104-109` → panes `:278,295` → panes internos de RichView `econ_richview.py:399`): la rueda del mouse queda atrapada.
- **Cinco formatos de dinero distintos** para la misma magnitud: `"$ X,000"` (`economics_panel.py:29`), `"$ X.XX MM"` (`:39`), `"X.XX"+"M USD"/"M"/"M/a"` (`econ_richview.py:36-42`), `"+X.XX"` con signo forzado (`econ_widgets.py:37-44`), `"MUSD"` (MC `:752`). Payback = "años" o "a" según pantalla. Porcentajes con `.1f` o `.0f` según widget.
- **Fugas de internals a la UI:** `run_economics=True` como subtítulo visible (`economics_panel.py:498-500`, `econ_richview.py:330` — visible en las capturas), `dep_method` crudo `"straight_line"` (`econ_widgets.py:254`), labels en inglés "Tax rate:"/"Discount:" en medio de UI en español (`econ_widgets.py:236-237`), placeholder técnico "ej: 0.6,0.4 (vacío = 1 año, año 0)".
- **Colores fuera del sistema:** errores en rojo `#c0392b` que **no pertenece a la paleta** (danger real: `#b8453a`) — `economics_panel.py:361, 376, 394, 408, 736`; blancos `#ffffff` hardcodeados (`econ_richview.py:286, 464`); las figuras matplotlib duplican los tokens TOK como fallbacks hex hardcodeados que derivarán en silencio (`econ_figures.py:68-99, 129-201` vs `block_inspector.py:80-86`). En dark mode la anotación de payback del gráfico queda ilegible (ver `outputs/econ_dark.png`).
- **Monte Carlo es otra aplicación:** ventana aparte `MonteCarloPanel` (`economics_panel.py:601`) con salida **100 % ASCII** (`:743-770`), alcanzable por **3 botones distintos** (`economics_panel.py:253, :290`; `econ_richview.py:460`) — mientras `econ_figures.py` tiene `npv_density_figure` y `tornado_figure` **implementadas y nunca cableadas** (existen hasta capturas: `outputs/econ_density.png`, `econ_tornado.png`).
- **Cuatro paradigmas de render en un diálogo:** ASCII QTextEdit, QFrames con setStyleSheet por widget, QPainter custom (`econ_widgets.py:79-123`), matplotlib embebido. Tipografías de 7 pt en KPIs (`econ_richview.py:112,139,262`).
- Parámetros económicos repartidos en 3+ lugares: el diálogo, "Perfil económico…" (menú, `flowsheet_qt.py:6221`), "OPEX extras…" (`:6218`) y `econ_defaults.py`.

### D.3 Dirección propuesta (para Design)

1. **Una sola UI.** EconRichView ya ganó (es el 80 % del camino, ver `outputs/econ_richview_methanol.png`): eliminar el dump ASCII, la tab bar exterior, `_render_econ_legacy`, y el formulario crudo como pantalla inicial.
2. **Entrada/salida integradas:** los parámetros (hoy el formulario de la captura `econ_panel_full.png`) se convierten en el pane "Parámetros" del RichView — el sidebar ya tiene ese ítem; hoy no lleva a ningún lado.
3. **Sidebar honesto:** o 7 ítems → 7 panes reales (Resumen/CAPEX/OPEX/Cash flow/Monte Carlo/Contabilidad/Parámetros), o reducir a los 3 que existen. Eliminar la doble navegación sidebar+tabs.
4. **KPIs una sola vez** (hero); footer para acciones ("Re-correr", exportar), no para repetir números.
5. **Monte Carlo dentro del panel** usando las figuras ya implementadas (density + tornado); matar la ventana ASCII.
6. **Un formateador único de dinero/porcentaje/años** (módulo común) — decisión de formato: `12.5 M USD`, `39.7 %`, `2.4 años`, es de Design, pero debe haber UNO.
7. Figuras matplotlib leyendo tokens del tema en runtime (nada de fallbacks hex duplicados); tema dark coherente.
8. Consolidar dónde viven los parámetros económicos (diálogo vs Perfil vs OPEX extras).

---

## E. Problema transversal: no hay un sistema de diseño único

1. **Dos paletas de color simultáneas:**
   - Semáforo solver (`flowsheet_qt.py:263-267`): verdes/rojos Material (`#2e7d32`, `#c62828`, `#f9a825`, `#1976d2`, `#7b1fa2`).
   - Tokens `TOK` (`block_inspector.py:50-86`): tierra/desaturados (`#b8453a`, `#b8841a`, `#0d6e78`, `#6b6256`, `#efeadd`) — los usa editor_chrome, el inspector y el panel económico.
   - Más intrusos fuera de ambas: `#c0392b`, `#283593`, `#3a3a3a`, `#ffffff`.
2. **Tres lenguajes de iconos** (unicode text-glyphs, SVG `icons.py`, siluetas QPainter + emoji).
3. **Sin tokens de tipografía ni stroke:** fuentes 7-10 pt hardcodeadas por widget, Consolas hardcodeada, strokes 0.9-2.5 dispersos.

**Primera entrega sugerida de la fase Design: un archivo de tokens único** (color semántico: ok/warn/error/stale/unrun/accent/ink/bg; tipografía: 3-4 tamaños; stroke: 2 pesos; spacing) del que consuman canvas, topbar, inspector, economía y figuras matplotlib. Todo lo demás de esta auditoría se apoya en eso.

---

## F. Priorización sugerida

**Quick wins (bajo riesgo, alto efecto, casi sin diseño nuevo):**
1. Eliminar toolbars legacy C/D + toggle (B.5.1).
2. Eliminar botón muerto ✦; re-etiquetar/sincronizar ▦ como "Marco PFD" (B.2).
3. Unificar "Animación de flujo" en una sola QAction (B.3).
4. Badge correcto para WHB ×2 (C.3).
5. Quitar `run_economics=True` y demás fugas técnicas de la UI econ (D.2).
6. Splitter con glifo propio (ya existe `splitter-flow-divider` como referencia) (C.4.2).

**Fase Design (requiere spec visual — el objetivo de este handoff):**
7. Tokens únicos (E).
8. Estado en el símbolo, sin halo; selección separada del estado (A.3).
9. Topbar reorganizada por zonas de tarea con un solo sistema de iconos (B.5).
10. Diferenciación de glifos por familia (C.4).
11. Panel económico consolidado en una sola UI con MC integrado (D.3).

**Evidencia visual del estado actual:** `outputs/econ_panel_full.png` (formulario crudo), `outputs/econ_richview_methanol.png` (rich view), `outputs/econ_tables.png` (contabilidad), `outputs/econ_dark.png` (dark, gráfico incoherente), `outputs/econ_density.png` y `outputs/econ_tornado.png` (figuras MC implementadas y no cableadas).

---

*Auditoría de solo lectura: ningún archivo de código fue modificado. Generada sobre el commit `eefd596`.*
