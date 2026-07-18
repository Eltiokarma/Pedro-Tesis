# Prompt para la fase Design — ciclo 3

**Uso:** copiar el prompt de abajo (desde "---PROMPT---") a una sesión de
Claude Design, adjuntando estos archivos del repo:

- `outputs/audit3_palette_aliasing.png` (la evidencia central: los 56
  tipos de la paleta agrupados por silueta compartida)
- `docs/AUDITORIA_FRONTEND_UX.md` (auditoría 1 — §C es el capítulo de
  símbolos; C.2 lista los assets SVG ya dibujados)
- `docs/TRABAJOS_FUTUROS.md` (§8: la decisión cerrada sobre las
  variantes de HX; §10: el fallback SVG de la paleta)
- `tokens.py` (el sistema de diseño vigente, con la capa canvas del 2a)
- `outputs/design2b_canvas_light.png` y `outputs/design2b_canvas_dark.png`
  (el lienzo actual en ambos temas, para contexto de escala y densidad)

---PROMPT---

Sos el diseñador del frontend de una app de escritorio (PySide6/Qt) de
simulación de procesos químicos con análisis económico, para una tesis de
ingeniería. UI en español. Llevamos dos ciclos
auditoría→design→implementación juntos: el ciclo 1 (tokens, semáforo en
el símbolo, topbar por zonas, panel económico unificado) y el ciclo 2
(capa canvas tokenizada con par dark, leyenda del Marco PFD, kit de
diálogos, bienvenida, inspector completo, migración tipográfica a los 6
tamaños). La identidad visual que definiste y que hay que respetar:
papel cálido (`#f6f3ec`/`#fbfaf6`), tinta tierra desaturada, acento teal
`#0d6e78` (elegible: terracota/cobalto/oliva), IBM Plex Sans/Mono,
éxito discreto y warning/error con color + símbolo (daltónico-safe).

Este ciclo ataca los tres pendientes que los dos anteriores dejaron
explícitamente para una fase Design propia. El hallazgo estructural lo
validó el propio usuario de la app sin leer ninguna auditoría: *"la
barra donde se selecciona para crear equipos tiene varios equipos, pero
no tienen una miniatura que los diferencie — todos se parecen"*.

## Artboards que te pido

### 3a — Diferenciación de glifos (el corazón del ciclo)

Mirá `audit3_palette_aliasing.png` ANTES de leer el resto: son las
miniaturas reales de la paleta, agrupadas por silueta. Estado actual:
**56 tipos de equipo, 29 siluetas — 11 únicas y 18 compartidas**. El
ciclo 1 ya diferenció seis parejas (splitter ≠ mixer, PFR ≠ CSTR,
compresor recíproco, torres de enfriamiento inducida/natural…); esto es
la mitad restante del trabajo, no un arranque de cero.

Los grupos que confunden de verdad, en orden de daño:

1. **`valvula` ×3** (3-way / globo de control / **alivio**): una válvula
   de seguridad que se ve idéntica a una de control es un error
   semántico serio en un PFD.
2. **`reactor` ×4** (CSTR agitado / autoclave / jacketed agitado /
   jacketed no-agitado): la distinción agitado/encamisado es EL
   contenido pedagógico de la lámina de reactores.
3. **`compresor` ×3** (axial / centrífugo / rotativo) y **`bomba` ×3**
   (centrífuga / desplazamiento positivo / recíproca): la familia
   rotativa vs alternativa debería leerse en la silueta.
4. **`caldera` ×2** (fire tube / water tube), **`platos` ×2** (sieve /
   valve) + **`empaque` ×2** (random / estructurado), **`horno` ×2**
   (reformer / no-reformer), **`hx_placa` ×2** (placa plana / espiral),
   **`hx_aircooler` ×2**, **`centrifuga` ×2** (decanter / disc stack).
5. Los pares "de forma" (`tanque` cone/floating roof, `tambor`,
   `separador`, `ventilador`, `mezclador` inline/static, `hx_whb`
   packaged/field): decidí cuáles merecen diferenciarse y cuáles se
   declaran compartidos a propósito — pero que la decisión quede
   escrita, no muda.

Restricciones y activos:

- **La decisión cerrada que se respeta**: las 6 variantes de casco y
  tubo del HX (`hx` ×6: fixed/U-tube/floating/double pipe/multiple/
  condenser) comparten silueta A PROPÓSITO (`TRABAJOS_FUTUROS.md` §8 —
  misma familia geométrica, menos ruido). Si querés reabrirla,
  argumentalo explícitamente; el default es no tocarla.
- **Trabajo ya dibujado que podés saquear**: `pfd_symbols.py` trae 94
  símbolos SVG, 17 de ellos diferenciados del patch PFD-ICN-002
  (reactor-pfr-coiled, compressor-axial, boiler-fire/water-tube,
  tray-sieve/valve-section, packing-random/structured…) — la geometría
  de referencia existe; tu spec decide cuál se porta y cómo se adapta a
  la familia ISA del canvas (auditoría 1 §C.2).
- **Doble escala obligatoria**: cada glifo debe leerse a 22 px
  (miniatura de paleta/menú) Y a ~60 px (canvas). Si un detalle
  diferenciador desaparece a 22 px, no diferencia nada: pensá el rasgo
  distintivo como macro-forma, no como textura.
- **Tokens de trazo**: `STROKE_OUTLINE 1.6` / `STROKE_DETAIL 1.0`
  existen en `tokens.py` y los `_draw_*` de glifos siguen pasando
  pesos a mano (0.9–2.0 dispersos). Tu spec fija la regla: contorno =
  OUTLINE, detalle interno = DETAIL, excepciones declaradas.
- Los glifos se re-tintan en vivo con el tema (ciclo 2b): definí solo
  geometría + roles de color (ink/fill/detalle), nunca hex propios.

Entregá: por cada grupo, la silueta propuesta por variante (SVG en el
mockup), el rasgo distintivo en una frase, y la tabla
eq_type → glifo con los que quedan compartidos-a-propósito marcados.

### 3b — Tabla de corrientes + inspector de corriente (pasada formal)

Las dos superficies que nunca pasaron por diseño (`streams_table.py`,
dock inferior; `stream_inspector.py`, panel de corriente). Ya consumen
tokens y los 6 tamaños tipográficos — esto no es tokenización, es
**diseño**: jerarquía, densidad, qué se muestra y qué sobra.

- **Tabla de corrientes**: hoy es una QTableWidget plana con ~10
  columnas. Decidí: columnas esenciales vs bajo demanda, cómo se marcan
  los valores spec (declarados) vs auto (deducidos) — el inspector de
  bloque ya tiene ese lenguaje (ribbon spec/auto) —, dots de fase, rol
  de la corriente, sincronía de selección con el canvas (click en fila
  ↔ resalta stream), y estados vacío/stale.
- **Inspector de corriente**: hoy replica al inspector de bloque pero
  con jerarquía propia improvisada. Alineálo a la anatomía del
  inspector de bloque del ciclo 2 (header con chips, secciones, cards
  de evidencia) — o argumentá por qué una corriente merece anatomía
  distinta.

### 3c — Herramienta de anotación (T)

La herramienta de texto se retiró limpiamente de la paleta en el ciclo
1 porque no tenía UX definida. Definila: crear (¿click coloca, doble
click edita?), mover/redimensionar, estilos permitidos (¿solo los
tamaños del sistema? ¿un token de "nota de plano" nuevo?), color
(¿ink/ink_mute o libre?), cómo viven en el export (¿siempre visibles?
son parte del documento de ingeniería), z-order respecto de bloques y
streams, y ambos temas. Restricción: una anotación es texto de PLANO
(rótulos, notas de revisión), no un post-it — que el estilo lo diga.

## Restricciones técnicas (no negociables)

- Todo se implementa en **Qt (PySide6 + QGraphicsScene)**: tus CSS/HTML
  son spec y mockup, no runtime. Los glifos son QPainter paths — nada
  de gradientes/filtros SVG complejos dentro de un glifo.
- Nombres de token **1:1 con `tokens.py`** (adjunto), snake_case. Cada
  token nuevo trae par light + dark. La semántica técnica (glifos,
  puertos, servicio, roles, severidad, fases) NO deriva del acento.
- Daltonismo: ningún significado puede vivir SOLO en el color; en los
  glifos el significado vive en la FORMA (el color del glifo es estado
  del solver, no identidad del equipo).
- El español es el idioma de toda la UI.
- No rediseñes lo que ya funciona: la capa canvas del 2a/2b, la
  leyenda 2c, el kit 2d, la bienvenida 2e y el inspector de bloque 2f
  quedan como están (3b puede REUSAR la anatomía del inspector, no
  cambiarla).

## Formato de entrega

Como en los ciclos anteriores: un bundle de artboards navegable
(HTML/CSS con las variables de token) + por artboard: decisiones
razonadas, tabla de mapeos (eq_type → glifo en 3a), y al final una
sección ⚡ de pendientes/ideas que excedan el alcance. Si tenés que
recortar, la prioridad es **3a > 3b > 3c** (3a es el hallazgo validado
por el usuario; 3b mejora superficies que ya funcionan; 3c es una
feature nueva).

---FIN DEL PROMPT---
