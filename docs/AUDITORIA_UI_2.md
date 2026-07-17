# Auditoría UX/UI del frontend — ciclo 2

**Fecha:** 2026-07-17 · **Rama:** `claude/second-ui-audit-7uag58` · **Alcance:** solo lectura de código (cero cambios), más capturas offscreen generadas como evidencia (`outputs/audit2_*.png`).

Segundo ciclo de auditoría, arrancado desde `docs/AUDITORIA_UI_2_BACKLOG.md`. Mismo doble propósito que el ciclo 1 (`docs/AUDITORIA_FRONTEND_UX.md`): auditoría técnica con evidencia `archivo:línea` verificable + brief para la fase Design. Donde el backlog resultó impreciso, este documento lo corrige con evidencia.

---

## 0. Resumen ejecutivo

| # | Área (backlog) | Veredicto | Hallazgo clave |
|---|---|---|---|
| A | El lienzo no respira el tema | **Confirmado y peor de lo anotado** | No es solo el canvas: **nada de la capa editor escucha `themeChanged`** (cero `connect` en `flowsheet_qt.py` y `editor_chrome.py`). Al cambiar a dark en vivo solo se re-tintan inspectores/economía; papel, grilla, puertos, labels, **topbar, menús y paleta** quedan claros, mientras los glifos —que sí leen `TOK` en cada `paint()`— se vuelven manchas oscuras sobre papel claro. Capturas: `audit2_canvas_light/dark.png`. |
| B | Tipografía: adopción parcial de tokens | **Confirmado — la adopción no es parcial, es NULA** | `tokens.FONT_TITLE/UI/VALUE/LABEL` tienen **cero consumidores** en toda la app (solo las 4 definiciones, `tokens.py:132-135`). ~350 `QFont`/font-size hardcodeados en 15 archivos, rango 6.5–30. Los kickers de 7 pt marcados en el ciclo 1 siguen en 7 pt. `STROKE_DETAIL` también tiene cero consumidores. |
| C | Íconos no se recolorean al cambiar tema | **Confirmado** | `make_qicon` hornea el color en el bitmap del SVG (`icons.py:209`); `_build_shared_actions` fija `TOK["ink_mute"]` una sola vez (`flowsheet_qt.py:6405`) y nadie regenera. Excepción virtuosa: `_icon_for_eq_type` (`editor_chrome.py:1408`) pinta con `TOK` en vivo. |
| D | Superficies nunca auditadas | **Auditadas — 5 hallazgos por superficie** | Welcome es la única superficie 100 % ajena al sistema de diseño (Segoe UI + hex sueltos, idéntica en light y dark — capturas). La tabla de corrientes tiene 0 hex pero **T y P ignoran el sistema de unidades**. Los diálogos legacy (BlockEdit, DOF, Perfil económico, OPEX) no usan TOK. Los exports renderizan la escena real (regla ortogonal y semáforo heredados ✓) pero en paleta light-only por accidente. |
| E | Leyenda del lenguaje visual | **Corrección al backlog: SÍ existe, pero es un stub** | `_PaperFrame._build_legend` (`flowsheet_qt.py:5417-5450`) dibuja 3 entradas del lenguaje viejo (proceso/producto/utility). No cubre semáforo, 8 clases de puertos, servicio hot/cold ni roles de stream. |
| F | Pendientes heredados (⚡ 1g) | **1 resuelto, 2 parciales, 2 pendientes** | La herramienta T fue retirada limpiamente (resuelto); Q_reb/Q_cond y n_stages/Q_intercool los calcula el solver pero el inspector nuevo no los muestra completos; chip "átomos ✓" sin UI; el dock Propiedades legacy sigue vivo con los perfiles dentro. |
| G | Menores | **Verificados uno a uno** | Chip del solver: parcial (§G.1). Payback en `spec`: pendiente. Nuevo: `solver_report.py` duplica la paleta light entera sin par dark (`:24-29`) y `chemfx/ui/reactivity_dock_qt.py` trae 6 hex de severidad propios. |

**El hallazgo estructural del ciclo:** la app tiene hoy **tres niveles de respiración del tema** — (1) widgets suscritos a `_PrefsBus.themeChanged` que re-tintan en vivo (inspectores, economía, tabla de corrientes a medias); (2) widgets que hornean `TOK` al construirse y solo toman el tema al reiniciar (topbar, paleta, menús, docks — el propio `PreferencesDialog` lo admite: *"el editor toma el nuevo estilo al reiniciar"*, `block_inspector.py:2910-2912`); (3) superficies con paleta propia hardcodeada que jamás lo tomarán (canvas, puertos, labels, welcome, diálogos legacy, `solver_report`). El objetivo del ciclo 2 es colapsar los tres niveles en uno.

---

## A. El lienzo no respira el tema (el hallazgo grande) — ALTA

### A.1 El mecanismo de la "mancha negra" (evidencia visual: `outputs/audit2_canvas_dark.png`)

Dos frentes desalineados:

- **Los glifos SÍ leen TOK en cada repintado** — `IsaGlyphItem.paint()`: stroke `_tokens.status_hex(status)` (`editor_chrome.py:1945`), fill `status_fill_hex(...)` o `TOK["bg_elev"]` (`:1951`), default de `BlockGlyph.draw` `TOK["bg_elev"]` (`:158-159`). En `THEME_DARK`, `bg_elev = #1f1b16` y `green_bg = #1f2a1d` (`tokens.py:203,211`).
- **El papel NO** — `FlowsheetScene.__init__` fija `setBackgroundBrush(QBrush(COLOR_CANVAS_BG))` una sola vez (`flowsheet_qt.py:5508`) con la constante `#fbfaf6` (`:219`); la grilla se crea una vez con `QPen(COLOR_GRID, 0)` (`:5534`, `_draw_grid` `:5533-5557`).

Resultado: bloques con relleno `#1f1b16`/`#1f2a1d` sobre papel `#fbfaf6` — manchas oscuras, detalles internos invisibles. Los glifos no se oscurecen porque "escuchen" el tema: leen `TOK` en vivo por accidente de diseño, mientras todo lo estático quedó claro.

### A.2 Nadie escucha `themeChanged` en la capa editor

- `flowsheet_qt.py`: **cero** referencias a `themeChanged`/`_PrefsBus` (la única mención es un comentario, `:6182`).
- `editor_chrome.py`: **cero** conexiones; topbar (`:909-913`, `:1013-1017`) y paleta (`:1305-1307`, `:1555-1557`, `:1586-1588`) hornean `TOK` en sus QSS al construirse.
- Suscriptores reales hoy (lista completa): `block_inspector.py:935`, `stream_inspector.py:505`, `inspector_widgets.py:92,231,301,373`, `econ_widgets.py:75,165,219`, `econ_richview.py:113,146,196,239,305,389`, `economics_panel.py:89`, `streams_table.py:477`. La emisión: `block_inspector.py:2949`.

Por eso la captura dark muestra topbar/menús/status bar **claros**: en un cambio en vivo solo inspectores y economía respiran. (Al reiniciar la app con prefs dark ya cargadas —`flowsheet_qt.py:5771-5775` corre antes de construir los widgets— la topbar sí nacería oscura… sobre el mismo papel claro.)

### A.3 Inventario de la paleta hardcodeada del canvas (`flowsheet_qt.py`)

**Conteo: 90 hex** en `flowsheet_qt.py` (`grep -c '#[0-9a-fA-F]{6}'`); `editor_chrome.py` tiene **0** (todo vía TOK; único literal: `QColor("white")` del símbolo "!" del chip, `:2030`).

Constantes base (`:219-261`):

| nombre | hex | línea | rol |
|---|---|---|---|
| `COLOR_CANVAS_BG` | `#fbfaf6` | 219 | papel del canvas |
| `COLOR_GRID` | `rgba(13,13,13,18)` | 220 | grilla |
| `COLOR_BLOCK_FILL` | `#ffffff` | 221 | relleno bloque legacy |
| `COLOR_BLOCK_BORDER` | `#5c6bc0` | 222 | borde por defecto (índigo intruso) |
| `COLOR_BLOCK_TEXT` | `#1a1a1a` | 226 | texto de bloque |
| `COLOR_BLOCK_SUB` | `#6c6c70` | 227 | subtexto de bloque |
| `COLOR_LABEL_BG` | `rgba(255,255,255,220)` | 261 | fondo pill de labels |

**Puertos — paleta Material intacta, sin par dark** (`:228-241`, consumida en `PORT_KIND_COLORS :251-260` → `_render_ports :3593-3596`): `process_in #2e7d32`, `process_out/conn #1565c0`, `utility_in #ef6c00`, `utility_out #bf360c`, `fuel #5d4037`, `vent #9e9e9e`, `drain #455a64`, `aux #7e57c2`, `free #bbbbbb`. Es el mismo problema de "dos sistemas de color" que el ciclo 1 mató para el semáforo, vivo para los puertos. El *kind* lo resuelve `equipment_ports.get_port_kind` (`:3592`), pero los colores viven acá.

**Servicio por temperatura** (`:274-285`): `HOT #ef6c2b`/`HOT_SEL #c4541d`/`COLD #3fa9dd`/`COLD_SEL #2b80ab` + extremos de lazo `#f9bd7c/#c4361a/#bfe3f5/#1773aa`.

**Roles de stream** (definidos en `flowsheet_model.py:47-60`, consumidos en `flowsheet_qt.py:4193,4202,4204`): internal/feed `#0d0d0d`/sel `#1f6feb`, product `#c41e3a`/`#7a1428`, utility `#1e3a8a`/`#0f1f4a`, waste `#6d4c41`/`#3e2723`; fallbacks `#c62828`, `#37474f`, dim `#9aa5b1`.

**Inline por elemento:** waypoint handle `#1f6feb`+`#ffffff` (`:2331-2332`), midpoint `rgba(31,111,235,130)` (`:2963`), endpoint `#ffffff`+`#ef6c00` (`:3035-3036`), snap `#2e7d32` (`:3123-3124`), stub de puerto `#0d0d0d` (`:3589`), type badge `#0d6e78` literal (`:3476`), severidad de warnings `#c41e3a/#e57c00/#f4b400/#9ca3af` (`:3658-3662`), duty badge `#c41e3a`/`#1565c0` (`:3744`), label de stream `#ffffff` (`:4064`) + flujo `#6b7280` (`:4077`), tooltip `#5b6f8f` (`:3347`), fase ⚠ `#b8860b` (`:4459`), conversión `#c41e3a`/`#3a3a3a` (`:4491`), leyenda/rótulo `#0d0d0d/#6b7280/#c41e3a/#1e3a8a/#ffffff` (`:5376-5460`), íconos de menú contextual `#3a3a3a` (`:3976,4822,5994`), hint mono `#1565c0` (`:6564`), fondo de export PNG `#ffffff` (`:7444`), curvas matplotlib del dock (`:8665-8817,8959-8961`).

**Lo único del canvas que ya lee TOK:** selección `_selection_qcolor() → TOK["accent"]` (`:224-225`), semáforo `status_qcolor` (`:267-269`), y todo el render del glifo en `editor_chrome` (hover `accent_tint :1957`, ring solving `accent :1963`, anillo selección `accent :2016`, chips `danger/amber :2026`, dot ok `green :2035`).

### A.4 Dirección propuesta (para Design)

1. **Tokenizar la capa canvas**: nuevos tokens (`canvas_bg`, `canvas_grid`, `label_bg`, `block_text`, `block_sub`) con par light/dark en `tokens.py`, y decidir la pregunta abierta del backlog: ¿los puertos adoptan la paleta TOK o se declaran **paleta técnica propia con par dark** (8 clases × 2 temas)? Lo mismo para servicio hot/cold y roles de stream (semántica de color que debe sobrevivir en dark sin perder el código visual).
2. **Suscribir la escena a `themeChanged`**: re-`setBackgroundBrush`, re-tintar grilla, invalidar labels/puertos. Y lo mismo para el chrome (topbar/paleta/menús re-aplican QSS — el patrón `_restyle` de `econ_richview` ya existe como referencia).
3. Alternativa mínima si no hay presupuesto: **bloquear el tema oscuro a solo-paneles** y declararlo en Preferencias — hoy el estado intermedio es el peor de los mundos.
4. Export: dejar el "siempre papel claro" como decisión declarada (hoy es accidente; ver §D.5).

---

## B. Tipografía: los tokens son código muerto — MEDIA

- **Cero consumidores de `FONT_TITLE/FONT_UI/FONT_VALUE/FONT_LABEL`**: grep devuelve solo las definiciones (`tokens.py:132-135`). El backlog decía "adopción parcial"; la realidad es adopción nula.
- La tipografía real es `pfd_fonts.SANS/MONO` + tamaño literal en cada `QFont(...)`. Censo por archivo (referencias con tamaño hardcodeado / rango pt):

| archivo | # refs | rango | flagrantes |
|---|---|---|---|
| `block_inspector.py` | 73 | 7–14 pt (+`font-size:24px` `:1374`) | caps 7 pt `:375,439,690,728,833,999,1018,1358` |
| `hx_edu.py` | 60 (SVG) | 6.5–18 | diagramas SVG monospace |
| `flowsheet_qt.py` | 51 | 7–17 pt | hero 17 pt `:1481`; ~18 hints `#888 font-size:8pt`; 7 pt `:3348,3353,4071,4076,5469` |
| `stream_inspector.py` | 39 | 7–16 pt | hd 7 pt `:245,269,957` |
| `hx_inspector.py` | 31 | 7–17 pt | kicker 7 pt `:229`; rangos 7 pt `:593-596` |
| `streams_table.py` | 25 | 7–11 pt | caps 7 pt `:105,325,420,446` |
| `econ_richview.py` | 19 | **7–26 pt** | KPI kicker 7 pt `:142` (el mismo que marcó el ciclo 1), tag 7 pt `:97`, NPV kicker 7 pt `:169` |
| `editor_chrome.py` | 15 | 8–16 pt | topbar 14 `:907`, título 14 `:833` |
| `solver_report.py` | 13 | 10–30 **px** | KPI 30 px `:254`, kicker 10 px `:292` — única superficie en px |
| `inspector_widgets.py` | 11 | 7–15 pt | cap 7 pt `:125,155,351` |
| `econ_widgets.py` | 7 | 8–9 pt | chip 8 pt `:139` |
| `welcome_qt.py` | 4 | 8–18 pt | **familia "Segoe UI" hardcodeada** `:91,108,162` |

Limpios: `economics_panel.py`, `indicators.py`, `estimated_overlay.py`.

- **Familias hardcodeadas fuera de `pfd_fonts`**: Segoe UI en welcome (`welcome_qt.py:91,108,162`), `Consolas, monospace` en stylesheets de flowsheet_qt (`:6464,6564,6896,6948`), `monospace` en `solver_report.py:415`.
- **Strokes:** solo `editor_chrome.py:1948` consume `STROKE_OUTLINE` (reusado `:1992,2005`); `STROKE_DETAIL` tiene **cero consumidores**. Los ~40 `_draw_*` de glifos pasan pesos a mano (0.9–2.0: `1.2` ×19, `1.0` ×20, `0.9/1.1/1.3/1.5/2.0` dispersos) — exactamente la dispersión que los dos tokens pretendían matar.

**Dirección:** un helper `qfont(FONT_X)` en `tokens.py`/`pfd_fonts` y migración mecánica empezando por los kickers de 7 pt (ilegibles, ya marcados dos veces); cablear `STROKE_OUTLINE/STROKE_DETAIL` en los `_draw_*`.

---

## C. Íconos horneados: no se recolorean al cambiar tema — MEDIA

- `make_qicon` (`icons.py:214`) inyecta el color como atributo estático del SVG (`stroke="{color}"`, `:209`) y rasteriza a QPixmap (`:229-237`) — el color queda quemado en el bitmap.
- `_build_shared_actions` (`flowsheet_qt.py:6393`) fija `_ICON_COLOR = TOK["ink_mute"]` **una vez** (`:6405`, cacheado en `self._icon_color :6407`); consumen ese color stale el menú principal (`_ac :6001` vía `:5994`), los menús contextuales de bloque (`:3977-3979`) y de arista (`:4823-4826`, ambos con `#c41e3a` literal extra), y las shared actions (`:6413-6453`).
- El badge de tipo del bloque usa **teal literal**, ni siquiera token: `make_qicon(icon_id, color="#0d6e78")` (`flowsheet_qt.py:3476`).
- **Referencia buena a replicar:** `_icon_for_eq_type` (`editor_chrome.py:1385`) pinta con `TOK["ink_mute"]/TOK["bg_elev"]` en vivo (`:1408-1409`) y los menús eq-type se reconstruyen en cada popup (`:1464,1491`) — es el único ícono que respeta el tema. El patrón de suscripción correcto ya existe en `econ_richview._restyle` (ver §A.2).

**Dirección:** `_PrefsBus.signal().connect(self._rebuild_icons)` en `_build_shared_actions` + topbar/paleta; eliminar `_icon_color` cacheado y el teal literal.

---

## D. Superficies auditadas por primera vez — MEDIA

### D.1 `welcome_qt.py` — la superficie más rezagada (capturas `audit2_welcome_light/dark.png`, idénticas)

- QMainWindow 720×560 (`:66-153`): header, "Empezar" (Nuevo/Abrir), "Recientes" (máx 8, estado vacío correcto `:133`), footer Salir.
- **Cero TOK, cero `_PrefsBus`, cero `pfd_fonts`** — única superficie 100 % ajena al sistema de diseño. `QFont("Segoe UI")` ×3 (`:91,108,162` — en Linux cae a un genérico), grises inline `#666/#888/#999` (`:98,134,181`).
- Registro de texto inconsistente: voseo "Diseñá…, corré…" (`:96`) vs. el neutro del resto de la app. Prefijo redundante "Diagrama · " en cada reciente (`:173`).

### D.2 `streams_table.py` — limpia de hex, sucia de unidades

- **0 hex** — todo TOK; reusa `PHASE_DOT/role_style` del stream inspector. Flujo vía `funits.format_flow` (`:306,430`) ✓.
- **T y P ignoran el sistema de unidades**: f-strings crudos `{T:.1f} °C` / `{P:.2f} bar` (`:363,374`) en vez de `funits.fmt_temp/fmt_pressure` (existen: `flowsheet_units.py:157,171`). Si el usuario cambia a °F/psi, la tabla miente mientras el export sí convierte.
- **Re-tinte parcial**: suscrita a `themeChanged → refresh` (`:477`) pero `refresh()` (`:721`) solo reconstruye filas+chips; los QSS de host/toolbar/header/scroll (`:482,513,702,498`) se fijan en `__init__` → quedan stale al cambiar tema.
- Click de fila dispara un `refresh()` completo solo para repintar el highlight (`:802`) — reconstrucción total por un cambio de selección.
- Export CSV con encabezados en inglés (`:669-671`) en UI española.

### D.3 `stream_inspector.py` — 5 hex, todos en `PHASE_DOT`

- `PHASE_DOT` (`:49-55`): liquid `#3548b4`, vapor `#c26329`, gas `#b8841a`, two_phase `#0d6e78`, "" `#bab2a3` — semántica de fase fuera de `tokens.py`, sin par dark (el cobalto pierde contraste sobre `bg_elev` oscuro). Son exactamente los 5 hex del archivo; el resto respira TOK y reacciona a tema (`_on_prefs_changed :1607`).
- Inglés residual: chip "STREAM" (`:123`), título de dock "Stream Inspector" (`:1641`), "tm/yr" (`:215`) conviviendo con "tm/año" (`:558`) en el mismo panel.
- Flujos con f-strings `{x:,.0f}` (`:214,1072`) en vez del formateador de unidades.

### D.4 Diálogos: solo Preferencias habla TOK

| diálogo | dónde | estado |
|---|---|---|
| `BlockEditDialog` ("Opciones avanzadas…") | `flowsheet_qt.py:358`, invocado `:7521` | Legacy vivo: QFormLayout sin TOK, hints `#555` (`:397`), `#888` (`:418`) |
| Setpoints | `:6956` | Ni siquiera es diálogo: cadena de `QMessageBox` (`:6965,6991,6996`) |
| DOF/Balance | `:6874` | QTextEdit con `Consolas 9pt` hardcodeado (`:6896`), sin TOK |
| Perfil económico | `:7166` | Sin TOK; `Consolas` (`:7219`); preview vuelca claves en inglés `LABOR/FINANCIAL/UTILITY PRICES` (`:7226-7237`) |
| OPEX extras | `:2177` (+row `:2099`) | Sin TOK; categorías internas en inglés mostradas crudas (`:2102-2103`); hints `#888/#555` (`:2153,2194`) |
| Preferencias | `block_inspector.py:2840` | **El único con TOK** (`:2916-2918`); admite honesto que el editor solo toma el tema "al reiniciar" (`:2910-2912`) |

**Dirección:** helper `_style_dialog(dlg)` con QSS TOK compartido; retirar o migrar `BlockEditDialog`; traducir categorías OPEX y claves del preview.

### D.5 Exportación PDF/SVG/PNG — misma escena, paleta light por accidente

- Los tres exports (`action_export_pdf :7340`, `_svg :7383`, `_png :7421`) delegan en `_render_to_painter` (`:7459`) → `self.scene.render(...)` (`:7472`): **renderizan la escena real**, así que heredan regla ortogonal, semáforo tokenizado, `_PaperFrame` y labels ✓. La grilla se oculta y restaura correctamente (`:7466-7480`).
- El PNG fuerza fondo `#ffffff` (`:7444`); PDF/SVG van sin fondo. El export sale siempre claro **porque la escena es light-only**, no por decisión declarada. Defendible para un PFD imprimible, pero frágil: si el canvas gana tema oscuro (§A), esto necesita ser una decisión explícita ("exportar siempre en papel claro") o una opción.

---

## E. Leyenda del lenguaje visual — BAJA (corrección al backlog)

El backlog afirmaba que "no existe una leyenda". **Sí existe**: `_PaperFrame._build_legend` (`flowsheet_qt.py:5417-5450`) dibuja un cuadro "LEYENDA" con 3 entradas (proceso negro, producto `#c41e3a`, utility `#1e3a8a`) + 3 notas ("conexión", "tm/año", "S=m², V=m³").

Lo que falta es todo el vocabulario **nuevo**: semáforo del solver (ok/warning/error/stale), las 8 clases de puertos (`PORT_KIND_COLORS :251-260`), servicio caliente/frío con degradado por T (`:274-285`) y roles de stream. El anfitrión natural ya está elegido: el mismo `_PaperFrame` que aloja el cuadro de título (`_build_title_block :5452-5497`). Extender `_build_legend` — con la salvedad de que la leyenda debe pintarse con la paleta que quede tras §A (hoy sus colores están hardcodeados en el mismo bloque `:5376-5460`).

---

## F. Pendientes heredados del rediseño (⚡ artboard 1g) — veredictos

| # | ítem | veredicto | evidencia |
|---|---|---|---|
| 1 | Q_reb/Q_cond por columna en el inspector | **PARCIAL** | El solver los separa (`distillation_fug.py:516-517`; `flowsheet_solver.py:2843-2864` → `b._Q_reb_kW/_Q_cond_kW`) y el **dock legacy** los muestra (`flowsheet_qt.py:8146-8149`), pero el inspector nuevo sigue en `b.duty` agregado (`block_inspector.py:1439-1444`; 0 matches en `inspector_evidence.py`). |
| 2 | n_stages + Q_intercool multi-etapa | **PARCIAL** | `equipment_design.py:208-238` calcula ambos; `n_stages` ya es visible ("Etapas rec." + chip "Multietapa ×N", `inspector_evidence.py:1757-1776`, consumido `block_inspector.py:2221`); `Q_intercool_kW` solo aparece como texto de warning (`inspector_evidence.py:394-395`), nunca como dato numérico. |
| 3 | Chip "átomos ✓" por bloque | **PENDIENTE** | Backend completo (`audit_examples_components.py`, `gate_component_balance.py`) sin ninguna UI: 0 menciones en `block_inspector.py`. |
| 4 | Herramienta de anotación (T) | **RESUELTO** (retirada limpia) | Quitada de `TOOLS` con comentario explícito "se re-agrega cuando exista la colocación de texto real" (`editor_chrome.py:1195-1202`). Sigue siendo feature futura, pero ya no hay stub engañoso. |
| 5 | Perfiles PFR/McCabe/tray al Inspector | **PENDIENTE** | El dock Propiedades legacy sigue vivo (`_build_properties_dock`, `flowsheet_qt.py:6457-6468`, invocado `:5835`, menú "Propiedades y perfiles" `:6087`) y los perfiles se dibujan ahí (`_draw_mccabe_for_block :8734`, `_draw_pfr_curve :8852`, `_draw_batch_curve :8889`). McCabe además está **duplicado** parcialmente en `inspector_evidence.py:250-254,1682`. |

---

## G. Menores — verificados

1. **Chip del solver: PARCIAL.** Único call site real de `update_solver_chip` (`flowsheet_qt.py:6383-6387`): `action_solve` (`:7036`). F5 y el botón del topbar van por `action_solve` ✓. NO actualizan el chip: los solves internos de `_ensure_hx_auxiliaries` (`:6253,6270`), el goal-seek `solve_setpoints_all` (`:6999`), y `action_load_example` (`:6762-6809`) que ni resuelve ni resetea el chip — al cargar un ejemplo el chip puede mentir "convergido" del diagrama anterior.
2. **Payback tenue en dark: PENDIENTE.** `econ_figures.py:93,98` siguen con `_tok("spec")` (dark: `#92a0ef`, legible pero de bajo peso visual sobre `bg_elev`); decisión de Design si merece token propio.
3. **`inspector_widgets.py`: 1 hex confirmado** — fallback `"#000000"` del helper `_tok` (`:69`). Inofensivo pero contable.
4. **Fill de estado sobre canvas: RESUELTO** (theme-aware vía `tokens.status_fill_hex`, `editor_chrome.py:1950-1951`, `tokens.py:103-123`); su contraste en dark queda condicionado a que exista canvas dark (§A).
5. **Hex residuales en archivos no cubiertos por A-D** (inventario nuevo):

| archivo | # hex | qué son |
|---|---|---|
| `inspector_evidence.py` | ~45 | colores matplotlib de evidencia (`#1f6feb/#d29922/#3fb950 :346-352`, `#8b949e :364`, `#d11 :733-737`) — misma deuda que tenían las figuras econ antes de `_tok()` |
| `solver_report.py` | 7 | **duplica la paleta light entera como TOK propio sin par dark** (`:24-29,38`) — en dark el reporte del solver quedará claro |
| `chemfx/ui/reactivity_dock_qt.py` | 6 | paleta de severidad propia `#c41e3a/#e57c00/#f4b400/#9ca3af` (`:34-37`) + `#6b7280 :77` — tercera copia de la escala de severidad (también en `flowsheet_qt.py:3658-3662`) |
| `hx_icons.py` | 2 | defaults `color="#000"` (`:201,214`) |
| `hx_edu.py` | 0 reales | falsos positivos (entidades HTML); usa `var(--ink)` ✓ |

Limpios: `hx_bubbles.py`, `stream_bubbles.py`, `indicators.py`, `estimated_overlay.py`, `ui_scaling.py`, `econ_figures.py` (todo `_tok()`).

---

## H. Priorización sugerida

**Quick wins (mecánicos, sin diseño nuevo):**
1. T·P de la tabla de corrientes vía `funits.fmt_temp/fmt_pressure` (§D.2 — hoy la tabla desobedece el sistema de unidades).
2. Resetear/actualizar el chip del solver en `action_load_example` y goal-seek (§G.1 — hoy puede mentir).
3. Mover `PHASE_DOT` a `tokens.py` con par dark; matar el teal literal del type badge (`:3476`) y los `#c41e3a` de los menús contextuales (§C, §D.3).
4. Traducciones: "STREAM"/"Stream Inspector"/"tm/yr", categorías OPEX, claves del preview económico, encabezados del CSV (§D).
5. Helper `qfont(FONT_*)` + migración de los kickers de 7 pt (§B — tercera vez que se marcan).

**Fase Design (spec visual requerida):**
6. **Canvas tokenizado + tema oscuro completo** (§A) — el hallazgo estructural del ciclo: tokens de canvas/puertos/servicio/roles con par dark, escena y chrome suscritos a `themeChanged`, o dark declarado solo-paneles como estado intencional.
7. Sistema de re-tinte unificado (los 3 niveles de §0 colapsados a uno; el patrón `_restyle` de `econ_richview` como referencia) — incluye íconos regenerables (§C) y QSS de topbar/paleta/tabla.
8. Diálogos con QSS TOK compartido; retirar `BlockEditDialog` y el dock Propiedades legacy migrando perfiles al inspector (§D.4, §F.5).
9. Leyenda extendida en el `_PaperFrame` (§E) — depende de 6 para pintarse con tokens.
10. Welcome rediseñada dentro del sistema (§D.1).
11. Inspector: Q_reb/Q_cond, Q_intercool numérico, chip "átomos ✓" (§F.1-3).

**Evidencia visual de este ciclo:** `outputs/audit2_canvas_light.png` / `audit2_canvas_dark.png` (metanol resuelto; en dark: glifos-mancha sobre papel claro, topbar sin re-tintar) · `outputs/audit2_welcome_light.png` / `audit2_welcome_dark.png` (idénticas — welcome ciega al tema). Generadas offscreen con el camino real de Preferencias (`apply_preferences` + `_PrefsBus.emit`).

---

*Auditoría de solo lectura: ningún archivo de código fue modificado. Generada sobre el commit `8ee68a8`.*
