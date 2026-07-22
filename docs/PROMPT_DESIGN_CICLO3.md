# Prompt para la fase Design — ciclo 3

**Uso:** copiar el prompt de abajo (desde "---PROMPT---") a una sesión de
Claude Design, adjuntando estos archivos del repo:

- `docs/AUDITORIA_FRONTEND_UX.md` (auditoría 1 — §C.4 es el encargo grande)
- `docs/AUDITORIA_FRONTEND_EQUIPOS_MATRIZ.md` (matriz por eq_type: qué
  tipos existen, cuáles no aparecen nunca en los ejemplos)
- `tokens.py` (el sistema de diseño vigente tras el ciclo 2: canvas, puertos
  técnicos, servicio por temperatura, roles de stream, severidad única,
  FONT_DISPLAY/FONT_HINT)
- `docs/REDISENO_CICLO2_2026-07.md` (qué quedó implementado del ciclo 2 y
  la lista ⚡ de pendientes que este ciclo retoma)
- `outputs/design2b_canvas_light.png` y `outputs/design2b_canvas_dark.png`
  (el lienzo actual en ambos temas)
- `outputs/design2c_legend_light.png` (la leyenda del lenguaje visual)

---PROMPT---

Sos el diseñador del frontend de una app de escritorio (PySide6/Qt) de
simulación de procesos químicos con análisis económico, para una tesis de
ingeniería. UI en español. Ya hicimos dos ciclos auditoría→design→
implementación juntos y los dos están implementados: del ciclo 1 vienen el
sistema de tokens, el semáforo del solver en el cuerpo del símbolo, la
topbar por zonas y el panel económico unificado; del ciclo 2 (tu paquete
2a-2g) vienen los tokens de la capa canvas con par light/dark, la paleta
técnica propia de puertos, el lienzo que respira el tema en vivo, la
leyenda colapsable del Marco PFD, el kit de diálogos, la bienvenida y la
migración tipográfica completa. La identidad que definiste y que hay que
respetar: papel cálido (`#f6f3ec`/`#fbfaf6` y su par sepia-carbón dark),
tinta tierra desaturada, acento teal `#0d6e78` (elegible:
terracota/cobalto/oliva), IBM Plex Sans/Mono, éxito discreto,
warning/error con color + símbolo (daltónico-safe), export siempre en
papel claro.

Este ciclo cierra la deuda VISUAL que los dos anteriores dejaron anotada.
Como siempre: el mecanismo (suscripción a señales, persistencia, hit-tests)
es ingeniería y corre por nuestra cuenta — tu trabajo es **decidir y
especificar los valores y comportamientos visuales**.

## Artboards que te pido

### 3a — Diferenciación de glifos por familia (el encargo grande, §C.4)

La auditoría 1 lo dejó como "el próximo gran visual" y sigue abierto. Hoy
conviven varios sistemas de símbolos y hay familias donde el aliasing
confunde de verdad. Te pido:

1. **Un solo sistema de símbolos on-canvas** (los glifos ISA QPainter son
   el activo). Decidí explícitamente el rol o la muerte de los otros:
   badge 24×24, `pfd_symbols` (SVG de exportación), `equipment_icons`.
2. **Diferenciación donde invierte semántica o confunde**, en este orden
   de prioridad:
   - splitter ≠ mixer (crítico: hoy pueden leerse igual y significan lo
     contrario),
   - PFR vs CSTR,
   - compresor recíproco vs centrífugo,
   - kettle reboiler vs WHB (y el badge de los DOS WHB, roto),
   - boiler fire-tube vs water-tube,
   - cooling tower induced vs natural draft,
   - tray vs packing (internos de columna).
   La matriz adjunta te dice qué tipos aparecen en los 58 ejemplos y
   cuáles son variantes que solo viven en la paleta (21 tipos sin
   instancia) — para esos alcanza con que la VARIANTE se distinga en la
   paleta y el badge; el glifo on-canvas puede compartir base de familia.
3. **Token único de stroke y proporción** para todos los glifos (hoy hay
   variación accidental). Especificá: grosor de trazo en px a zoom 1.0,
   caja base, radio de esquinas, y cómo escala con zoom.
4. Cada glifo nuevo: mini-spec dibujable (geometría en coordenadas de caja
   100×100 o descripción inequívoca por primitivas), en ambos temas.

### 3b — Estado sudoku en las corrientes

El solver ahora clasifica cada corriente por procedencia de su masa:
**locked** (declarada por el usuario), **propagated** (deducida por
balance), **torn** (reciclo — converge por tearing), más el T/P spec vs
auto que ya existe. Las pills/burbujas hoy muestran solo "P auto vs spec".
Te pido:

1. Cómo muestra la pill/burbuja el estado de la MASA (locked/derivada/
   torn) sin ruido — ¿ícono, tipografía, borde, posición? Recordá el
   principio del ciclo 2: "declarado vs calculado" es una distinción de
   PROCEDENCIA, no de severidad (no puede parecer un warning).
2. El caso **torn** es nuevo y didáctico: una corriente de reciclo no es
   ni declarada ni deducida — converge iterativamente. Decidí si merece
   marca propia o se agrupa con "calculada" (argumentá).
3. Dónde vive la explicación (tooltip, leyenda del Marco PFD — ya tiene
   secciones ESTADO/PUERTOS/SERVICIO/CORRIENTE·FASE — ¿nueva fila?).
4. Coherencia con el diálogo DOF (kit, caso 1) que ya lista streams por
   estado — mismos términos, mismos símbolos.

### 3c — Herramienta de anotación (T)

Se retiró limpia de la paleta en el ciclo 1 esperando UX. Definila:

1. Crear (¿click coloca caja? ¿drag define ancho?), editar (doble-click),
   mover, borrar. ¿Flecha/línea guía opcional a un bloque o corriente?
2. Estilo dentro del sistema: tipografía (¿FONT_HINT/FONT_UI?), color de
   tinta, fondo (¿papel o transparente?), en ambos temas.
3. Comportamiento en el export (documento de ingeniería: ¿las anotaciones
   salen? ¿siempre o toggle?) y frente al zoom.
4. Alcance MVP vs futuro (no diseñes un editor de texto rico).

### 3d — Gradiente térmico en corrientes de servicio

Los extremos pale/deep por temperatura ya existen como tokens (ciclo 2,
familia servicio). Falta decidir el gradiente REAL T_in→T_out a lo largo
del path de la corriente: ¿gradiente continuo sobre el trazo, o dos
tramos con transición en el punto medio? ¿Qué pasa con corrientes
multi-segmento con jumpers? ¿Se apaga a partir de cierta densidad de
diagrama? Especificá para ambos temas y para el export.

## Restricciones y criterios de aceptación

- Ningún valor visual nuevo fuera de `tokens.py`: todo con par light/dark.
- Daltónico-safe: ninguna distinción SOLO por matiz (siempre color +
  forma/símbolo/tipografía).
- Las 8 combinaciones acento×tema no pueden romper nada de lo nuevo (los
  tokens técnicos no derivan del acento — mantené esa regla).
- El export siempre en papel claro hereda todo lo nuevo (glifos, estados
  sudoku, anotaciones si decidís que salen, gradiente).
- Entregá como en los ciclos anteriores: un artboard por sección con
  especificación implementable (valores exactos, no "un gris suave"), más
  la lista ⚡ de lo que decidas dejar fuera y por qué.
