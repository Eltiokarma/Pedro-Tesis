# Rediseño del frontend — ciclo 2, implementación (julio 2026)

Implementación del paquete de Design "Ciclo 2" (7 artboards,
`docs/design_ciclo2/`, respuesta a `docs/AUDITORIA_UI_2.md` vía
`docs/PROMPT_DESIGN_CICLO2.md`). Rama: `claude/second-ui-audit-7uag58`.
Suite completa verde: **610 tests** + `validate_ui` sin regresiones
nuevas. Evidencia visual por artboard en `outputs/design2*_*.png`.

## Qué se implementó, por artboard

### 2a — Tokens de la capa canvas (`102d2c9`)
- Seis familias nuevas en `tokens.py`, cada una con par light/dark:
  papel/grilla (`canvas_bg/canvas_grid/canvas_grid_major` — el papel
  oscuro es un sepia-carbón propio, NO el bg de paneles), **puertos como
  paleta técnica propia** (8 clases, muere la Material heredada),
  servicio por temperatura (el matiz caliente/frío se conserva en dark),
  roles de stream (`stream_internal` se invierte a warm-line claro),
  labels/duty badges, y fases corregidas por Design como set cohesivo.
- **Severidad colapsada a UNA escala**: `SEVERITY_TOKEN`/`severity_hex`
  sobre los tokens semánticos existentes — estaba triplicada (badges del
  canvas, dock de reactividad, chips).
- Tipografía: nacen `FONT_DISPLAY` (26/700, KPI hero) y `FONT_HINT`
  (11/400) — 6 tamaños, dos ampliaciones declaradas en vez de
  excepciones mudas.

### 2b — El lienzo respira el tema (`6820a6c`)
- Toda la paleta del canvas deriva de tokens
  (`_refresh_canvas_palette`); la ventana escucha `themeChanged` y
  re-tinta EN VIVO: escena (papel/grilla/marco, preservando el semáforo
  del solver a través del rebuild), íconos regenerables (muere el color
  horneado de `make_qicon` — cierra el backlog C), QSS de menubar,
  statusbar, scrollbars y docks, y `restyle()` en topbar/paleta/zoom.
  La nota "al reiniciar" del diálogo de Preferencias murió.
- Selección de streams: el hex del rol NO cambia — +peso de trazo +
  halo `accent_soft` (familia 4 del 2a).
- **Export siempre en papel claro** (documento de ingeniería), con
  opción "Exportar como se ve" en Archivo ▸ Exportar (apagada por
  defecto); el tema se restaura sin emitir señales globales.
- Grilla con línea mayor cada 5 pasos (`canvas_grid_major`).

### 2g — Migración tipográfica (`b1acf93`)
- ~200 fuentes hardcodeadas migradas a `qfont(FONT_*)` según el mapa
  rol→token de Design, en los 10 archivos de UI. Mueren los ~18 hints
  `#888 8pt`, las 5 `Consolas` de stylesheets y (de paso) los grises
  `#555/#666` y la paleta Material del badge de balance del editor de
  reacciones.
- Excepciones declaradas con comentario `(excepción 2g)`: pictogramas
  unicode como texto de botón, micro-tipografía de chips de datos en px,
  la escala de plano del rótulo PFD, y el path de la tabla de corrientes
  (a 11.5 pt se recortaba en el ancho de columna).
- Ajustes por el crecimiento 7→10/11 pt: sidebar económico 150→168 px,
  sidebar del inspector 168→186 px.

### 2c — Leyenda del lenguaje visual (`eabce91`)
- El stub de 3 entradas se convierte en la leyenda completa: banda que
  extiende el cuadro de título del Marco PFD con ESTADO (semáforo con
  tinte+trazo reales, stale punteado), PUERTOS (6 clases), SERVICIO
  (caliente↑/frío↓) y CORRIENTE·FASE. Colapsable por chevron (hit-test
  en `FlowsheetScene.mousePressEvent`; estado persistente en la escena).
  Todo tokens → hereda ambos temas y el export.

### 2d — Kit de diálogos (`1392ec6`)
- Nace `dialog_kit.py`: `KitDialog` (header 56 px / cuerpo scrolleable /
  footer 52 px de acciones — nunca repite datos) + `stat_card` /
  `kit_table` / `kicker` / botones primario/secundario/destructivo.
- Caso 1 — **DOF/Balance**: hero de stats + tabla por bloque con
  veredicto y sugerencias + "Copiar reporte" (conserva el formato texto
  para la tesis). Muere el QTextEdit mono.
- Caso 2 — **Setpoints**: diálogo real con tabla de especificaciones y
  goal-seek como acción primaria (deshabilitada si todo está en
  tolerancia). Muere la cadena de QMessageBox.

### 2e — Bienvenida (`7ad7935`)
- Rediseñada dentro del sistema (tokens + qfont + ambos temas; carga las
  prefs del usuario antes de construirse). Dos columnas 760×580:
  identidad + Nuevo/Abrir · Recientes con estado vacío ◇ · Ejemplos
  (3 destacados + catálogo completo de 41 por categoría). Elegir un
  ejemplo devuelve `('example', clave)` y `flowsheet_main_qt` lo carga
  por el mismo camino que el menú. Mueren Segoe UI y los grises sueltos.

### 2f — Inspector completo + muerte del dock legacy (`19a7088`)
- Chip **"átomos ✓/✗/–"** en el header (auditoría elemental C/H/O por
  bloque, color + símbolo, tooltip con el detalle del desbalance).
- **"Columna — Cargas térmicas"**: Q_reb/Q_cond por separado, ligadas al
  eje de servicio; N y R como chips.
- **Q_intercool numérico** en la tarjeta del compresor multi-etapa.
- El dock **"Propiedades y perfiles" MUERE** (~750 líneas): sus perfiles
  ya vivían embebidos en el Inspector; el reporte FUG/Wang-Henke se
  portó VERBATIM a `inspector_evidence.column_design_text` ("Columna —
  Diseño FUG / MESH") y la salida de "Calcular costos" (F9) pasa a un
  diálogo del kit. Cierra el pendiente que la propuesta 1g dejó abierto.

## Fixes reales encontrados por el camino

1. `_apply_active_palette` reconstruía el marco PFD ANTES de
   `_rebuild_scene`, y `clear_flowsheet` poda todo `z>-100` incluidos
   los HIJOS del marco → quedaba destripado al cambiar tema. Orden
   invertido (`eabce91`).
2. Los 3 tests del panel de columnas apuntaban al dock muerto; migrados
   a la fuente nueva (`inspector_evidence.column_design_text`).

## Divergencias razonadas respecto a la propuesta

1. **Excepciones tipográficas declaradas** (2g): Design pedía "ningún
   literal sobrevive"; se conservaron cuatro clases de literales con
   comentario obligatorio `(excepción 2g)` — pictogramas, micro-chips de
   datos en px, escala de plano del rótulo, path de la tabla. La regla
   operativa quedó: *o token, o constante comentada como excepción*.
2. **El chevron de la leyenda** no recibe eventos propios (el marco es
   decorativo, `NoButton`): el hit-test vive en la escena — mismo
   comportamiento, plomería más simple.
3. **"+ Agregar setpoint" del mockup 2d** no se implementó como acción
   del diálogo: los setpoints se declaran en la corriente (doble-click),
   y el diálogo lo explica en su estado vacío.

## Pendientes (sección ⚡ del bundle de Design, no implementados)

- Diferenciación de glifos restante (auditoría 1 §C.4 — el próximo gran
  visual, fuera del alcance del tema).
- Herramienta de anotación (T): definir su UX antes de devolverla a la
  paleta (sigue retirada limpiamente).
- Gradiente de temperatura real T_in→T_out en streams de servicio
  (los extremos pale/deep ya existen como tokens).
- QA visual de las 8 combinaciones acento×tema (cubiertas por
  construcción: ningún token técnico deriva del acento).
- `streams_table`/`stream_inspector`: pasada formal de diseño propia
  (ya consumen tokens de fase).
- `solver_report.py` aún duplica una paleta light-only propia (§G.5 de
  la auditoría) — unificar con tokens.
- `hx_edu.py` (SVG educativo) y las curvas matplotlib de
  `inspector_evidence` (~45 hex) quedan para una ola de tokenización
  posterior.
