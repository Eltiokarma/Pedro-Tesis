# Prompt para la fase Design — ciclo 2

**Uso:** copiar el prompt de abajo (desde "---PROMPT---") a una sesión de
Claude Design, adjuntando estos archivos del repo:

- `docs/AUDITORIA_UI_2.md` (la auditoría completa, con evidencia archivo:línea)
- `tokens.py` (el sistema de diseño vigente: paleta light/dark, acentos, tipografía)
- `outputs/audit2_canvas_light.png` y `outputs/audit2_canvas_dark.png` (el bug en acción)
- `outputs/audit2_welcome_light.png` (la pantalla de inicio actual)
- `outputs/audit2_econ_kickers.png` (referencia del look del panel económico ya rediseñado)

---PROMPT---

Sos el diseñador del frontend de una app de escritorio (PySide6/Qt) de
simulación de procesos químicos con análisis económico, para una tesis de
ingeniería. UI en español. Ya hicimos un primer ciclo
auditoría→design→implementación juntos: tu propuesta anterior ("Rediseño
Frontend", 7 artboards 1a-1g) está implementada — sistema de tokens único
(`tokens.py`), semáforo del solver en el cuerpo del símbolo, topbar por
zonas de tarea, seis parejas de glifos ISA diferenciadas, panel económico
de una sola UI con Monte Carlo embebido. La identidad visual que definiste
y que hay que respetar: papel cálido (`#f6f3ec`/`#fbfaf6`), tinta tierra
desaturada, acento teal `#0d6e78` (elegible: terracota/cobalto/oliva),
tipografías IBM Plex Sans/Mono, éxito discreto y warning/error con color +
símbolo (daltónico-safe).

Acabamos de cerrar la **segunda auditoría** (adjunta:
`AUDITORIA_UI_2.md` — leela entera antes de diseñar; tiene la evidencia
archivo:línea de todo lo que sigue). Tu encargo es el paquete de artboards
del **ciclo 2**. El hallazgo estructural es este: la app tiene hoy tres
niveles de "respiración" del tema — widgets que se re-tintan en vivo,
widgets que hornean los tokens al construirse, y superficies con paleta
propia hardcodeada que jamás toman el tema. Con tema oscuro activo, el
papel del lienzo queda claro mientras los glifos toman el fill oscuro del
tema: manchas negras sobre papel claro (mirá las capturas
`audit2_canvas_light/dark.png`). Tu trabajo NO es el mecanismo de
suscripción (eso es ingeniería, corre por nuestra cuenta): es **decidir y
especificar todos los valores visuales que faltan** para que el sistema
pueda colapsarse a un solo nivel.

## Artboards que te pido

### 2a — Tokens de la capa canvas (el corazón del ciclo)

El lienzo tiene ~90 colores hardcodeados fuera del sistema (inventario
completo en §A.3 de la auditoría). Definí tokens nuevos con **par
light/dark** para:

1. **Papel y grilla**: hoy `#fbfaf6` y negro al 7 %. El papel oscuro no
   puede ser el `bg` de los paneles (`#16130f`): el lienzo es un plano de
   dibujo, necesita su propia calidez. Decidí si la grilla en dark se
   aclara o desaparece.
2. **Puertos — la decisión grande del ciclo**: hoy 8 clases con paleta
   Material heredada (`process_in #2e7d32`, `process_out #1565c0`,
   `utility_in #ef6c00`, `utility_out #bf360c`, `fuel #5d4037`,
   `vent #9e9e9e`, `drain #455a64`, `aux #7e57c2`). Pregunta abierta de la
   auditoría: ¿los puertos adoptan la paleta TOK semántica o se declaran
   **paleta técnica propia** (armonizada con la identidad tierra, con par
   dark)? Argumentá la decisión. Restricción: las 8 clases deben seguir
   siendo distinguibles entre sí Y contra el semáforo del solver en ambos
   temas.
3. **Servicio por temperatura**: lazo caliente `#ef6c2b→#c4361a`, frío
   `#3fa9dd→#1773aa`, con extremos pálidos/profundos. Par dark que
   conserve la lectura "esto calienta / esto enfría".
4. **Roles de stream**: internal `#0d0d0d`, product `#c41e3a`, utility
   `#1e3a8a`, waste `#6d4c41` (+ variantes seleccionadas). En dark el
   trazo casi negro de las corrientes internas es invisible.
5. **Labels**: pill blanco 220α con texto `#1a1a1a`/`#6b7280`, duty badge
   rojo/azul `#c41e3a`/`#1565c0`, badges de severidad
   `#c41e3a/#e57c00/#f4b400/#9ca3af` — esta escala de severidad está
   TRIPLICADA en el código (canvas, dock de reactividad, chips); definí
   UNA sola con par dark.
6. **Fases** (ya tokenizadas por nosotros como quick win:
   `phase_liq/vap/gas/2ph`, dark ya elegido — validá o corregí los valores
   en `tokens.py`).

Entregá la tabla completa nombre → valor light → valor dark, con los
nombres en el estilo de `tokens.py` (snake_case, mismo archivo adjunto).
Verificá contraste: texto ≥ 4.5:1 contra su fondo, marcas gráficas
≥ 3:1 contra el papel, y los tintes de estado (`green_bg/amber_bg/
danger_bg` dark) legibles sobre el papel oscuro nuevo.

### 2b — El lienzo completo en oscuro (mockup)

Un PFD representativo (usa de referencia la captura light: tanques,
compresor, intercambiadores, reactor, columna, corrientes con labels y
duty badges, puertos de varias clases, Marco PFD con rótulo) renderizado
en **ambos temas** con los tokens de 2a. Es la prueba de que el sistema
cierra: semáforo + puertos + servicio + roles + labels + grilla + marco,
todo legible en dark. Incluí los cuatro estados del semáforo y una
selección activa. Decisión a documentar: la **exportación** (PDF/SVG/PNG)
¿fuerza siempre papel claro (documento imprimible) o sigue el tema
activo? Recomendá y justificá.

### 2c — Leyenda del lenguaje visual (Marco PFD)

Existe un stub de leyenda con 3 entradas del lenguaje viejo (proceso /
producto / utility). El canvas de hoy comunica mucho más: semáforo de 4-5
estados, 8 clases de puertos, servicio caliente/frío, roles de stream,
fases. Diseñá la leyenda completa como parte del Marco PFD (que ya tiene
cuadro de título estilo plano de ingeniería): qué entra, qué se omite por
obvio, jerarquía, tamaño que no compita con el diagrama, y cómo se ve en
ambos temas. Si preferís una card colapsable sobre el lienzo en vez del
marco, proponelo con argumento.

### 2d — Kit de diálogos

Los diálogos secundarios nunca pasaron por diseño (§D.4 de la auditoría):
edición avanzada de bloque, DOF/Balance (QTextEdit Consolas crudo), Perfil
económico, OPEX extras, y "Setpoints" que ni siquiera es un diálogo (es
una cadena de QMessageBox). Definí el **kit**: anatomía de diálogo
(header/cuerpo/footer), tipografía por rol, spacing, inputs, botones
primario/secundario, cómo se muestra salida tabular (para DOF y el preview
del perfil — hoy ASCII monoespaciado), todo con tokens y ambos temas.
Mockup de dos casos concretos: "DOF / Balance" y "Setpoints" (este último
repensado como diálogo real con lista de setpoints y acción de goal-seek).

### 2e — Pantalla de bienvenida

La única superficie 100 % fuera del sistema (captura adjunta: Segoe UI,
grises sueltos, idéntica en light y dark). Rediseñala dentro del sistema:
identidad de la app, Nuevo/Abrir, recientes (con estado vacío), acceso a
ejemplos (hay ~28 ejemplos empaquetados — decidí si se asoman acá), ambos
temas. Es una ventana 720×560 aprox., podés proponer otro tamaño.

### 2f — Inspector: los datos que faltan

Tres datos calculados por el solver que la UI esconde (§F de la
auditoría) + una migración:

1. Columnas de destilación: `Q_reb` y `Q_cond` por separado (hoy solo el
   duty agregado).
2. Compresor multi-etapa: `Q_intercool` como dato numérico (hoy es un
   warning de texto) junto al "Etapas rec." existente.
3. Chip "átomos ✓" por bloque (auditoría elemental C/H/O — backend listo).
   Definí estados: balanceado / desbalanceado / no aplica.
4. **Perfiles al inspector**: los perfiles PFR/batch, McCabe-Thiele y
   tray-by-tray viven en un dock legacy "Propiedades y perfiles" que
   queremos matar. Diseñá dónde y cómo viven dentro del Inspector de
   bloque (¿sección colapsable con la figura? ¿pane?) — esto desbloquea
   borrar el dock, pendiente desde tu propuesta 1g.

### 2g — Mapa tipográfico (spec, no mockup)

Definiste 4 tamaños (`FONT_TITLE 15/600 · FONT_UI 12/400 · FONT_VALUE
11.5/500 mono · FONT_LABEL 10/600`) y la auditoría encontró **cero
consumidores** — hay ~350 fuentes hardcodeadas de 6.5 a 30 pt en 15
archivos. Ya migramos los kickers del panel económico a `FONT_LABEL`
(captura adjunta). Entregá la **tabla de mapeo rol → token** para la
migración mecánica: kicker/cap, valor numérico, título de panel/diálogo,
texto de UI, hint/caption, celda de tabla, label on-canvas (bloque,
stream, leyenda — ojo: on-canvas escala con el zoom), KPI hero (¿26 pt del
NPV se queda como excepción declarada o nace un 5.º token display?). Si un
rol legítimo no cabe en los 4 tamaños, ampliá el sistema explícitamente en
vez de dejar excepciones mudas.

## Restricciones técnicas (no negociables)

- Todo se implementa en **Qt (PySide6 + QGraphicsScene)**: tus CSS/HTML
  son spec y mockup, no runtime. Nada de efectos que Qt no dé barato
  (blur, sombras complejas animadas).
- Nombres de token **1:1 con `tokens.py`** (adjunto) — snake_case, mismo
  estilo; los mockups deben usar exactamente esos nombres como variables
  CSS para que el porteo sea mecánico.
- Cada token nuevo trae **par light + dark**. Hay 4 acentos elegibles ×
  2 temas = 8 combinaciones: nada de lo que definas puede romper con un
  acento distinto de teal (regla práctica: la semántica técnica —
  puertos, servicio, roles, severidad, fases — NO deriva del acento).
- Daltonismo: ningún significado puede vivir SOLO en el color (el patrón
  actual color + símbolo/forma se mantiene).
- El español es el idioma de toda la UI.
- No rediseñes lo que ya funciona: topbar, glifos ISA, panel económico e
  inspectores quedan como están salvo lo pedido en 2f/2g.

## Formato de entrega

Como en el ciclo 1: un bundle de artboards navegable (HTML/CSS con las
variables de token) + por artboard: decisiones razonadas, tabla de tokens
nuevos/cambiados, y al final una sección ⚡ de pendientes/ideas que
excedan el alcance. Si tenés que recortar, la prioridad es
**2a > 2b > 2g > 2c > 2d > 2e > 2f** (sin 2a/2b el tema oscuro sigue
roto; el resto puede ir en olas).

---FIN DEL PROMPT---
