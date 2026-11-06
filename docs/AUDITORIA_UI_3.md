# Auditoría UX/UI del frontend — ciclo 3 (escaneo de cierre de la 2)

**Fecha:** 2026-07-25 · **Alcance:** verificación del estado real de
`docs/AUDITORIA_UI_2.md` sobre el código de hoy, más escaneo de las
superficies nacidas después de aquel documento. Evidencia nueva en
`outputs/audit3_*.png`, generada con el mismo camino real que el ciclo 2
(`apply_preferences` + `_PrefsBus.emit` sobre una ventana viva).

---

## 0. Veredicto

**La auditoría 2 está cerrada.** Los 11 ítems de su §H fueron ejecutados
por los ciclos 2 a 5. No se re-implementó nada: se verificó ítem por ítem
contra el código y contra capturas nuevas, y se congeló el resultado en
`tests/test_auditoria_ui3.py` para que no vuelva a abrirse en silencio.

| § de la auditoría 2 | Estado hoy | Evidencia |
|---|---|---|
| A · el lienzo no respira el tema | **CERRADO** | `_refresh_canvas_palette()` + escena suscrita: `canvas_bg` va de `#fbfaf6` a `#221d15` en vivo. Captura `audit3_canvas_dark.png`: papel, grilla, topbar, paleta, leyenda y glifos oscuros a la vez |
| A · puertos con paleta Material | **CERRADO** | Resuelto como *paleta técnica propia con par dark* (artboard 2a): tokens `port_*`, 8 clases frío→cálido, daltónico-safe. La pregunta abierta del backlog quedó decidida |
| B · tokens tipográficos sin consumidores | **CERRADO** | `tokens.qfont()` existe y se consume: 70 usos en `block_inspector`, 34 en `stream_inspector`, 17 en `econ_richview` |
| C · íconos horneados | **CERRADO** | Regeneración por `themeChanged`; el teal literal del type badge murió |
| D.1 · welcome ajena al sistema | **CERRADO** | 0 hex, 0 «Segoe UI», 44 usos de TOK; `audit3_welcome_light/dark.png` ya NO son idénticas |
| D.2 · T·P sin sistema de unidades | **CERRADO** en la tabla | `funits.conv_temp/conv_pressure` + `active_unit` (`streams_table.py:406-430`) — pero ver §2.1: reapareció en el inspector |
| D.3 · `PHASE_DOT` fuera de tokens | **CERRADO** | `_PhaseDot()` theme-aware |
| D.4 · diálogos legacy sin TOK | **CERRADO** | `dialog_kit.py` compartido; `BlockEditDialog` sobrevive pero con 0 hex |
| D.5 · export light-only por accidente | **CERRADO hoy** | Ver §1.3: pasó a ser decisión declarada |
| E · leyenda stub de 3 entradas | **CERRADO** | `_build_legend` (artboard 2c) cubre semáforo, puertos, servicio, roles, fases y procedencia |
| F · pendientes ⚡ del artboard 1g | **CERRADOS** | Chip «átomos ✓» visible; Q_reb/Q_cond separados (artboard 2f.1); dock Propiedades legacy eliminado |
| G · menores | **CERRADOS** | Chip del solver con iteraciones reales; payback en `spec_ink`; sin fallbacks hex |

**Censo actual:** 0 hex hardcodeados en las 10 superficies UI principales
(el único match en `flowsheet_qt.py` es un comentario que documenta el hex
que se eliminó). `tokens.py` es el único archivo que declara color.

---

## 1. Arreglado en este escaneo

Tres defectos que solo aparecen cuando algo se dibuja **encima** de otra
cosa — invisibles para un test de lógica y para la lectura de código.

### 1.1 El control de zoom pisaba la leyenda del plano — ALTA

`_Overlay._reposition` anclaba el zoom abajo-derecha del viewport
(`editor_chrome.py`). Esa esquina es del **documento**: leyenda, cuadro de
título y revisiones △N van ahí por convención de plano, no por gusto. El
chrome flotante se le montaba encima.

No se veía en pantallas grandes, y por eso sobrevivió a dos auditorías.
Medido con los rects reales (leyenda mapeada de escena a viewport contra
la geometría del widget):

| ventana | solape |
|---|---|
| 1920×1080 | — |
| 1400×900 | — |
| **1280×800** | **157×34 px — el control ENTERO dentro de la leyenda** |

1280×800 es un tamaño de laptop corriente. **Corregido:** el zoom pasa a
abajo-izquierda, columna que está libre siempre (la paleta vive
arriba-izquierda). Se movió la esquina en vez de esquivar la leyenda en
caliente: una posición que dependa del scroll haría que el control se
desplace mientras el usuario navega el plano.

### 1.2 El badge de duty quedaba tachado por su propia corriente — MEDIA

`duty_badge` se ancla en `(W+6, H/2)` — exactamente por donde sale la
corriente del puerto derecho — y se dibujaba **sin fondo**, así que el
trazo cruzaba las letras: «↑Q +6.00 MW» aparecía atravesado por su propia
línea (`audit3_canvas_dark.png`, antes/después en la crop de la zona).

**Corregido** con el mismo recurso que ya usan los labels de stream
(`label_bg`), no con uno nuevo: sobre el plano, texto que cae encima de
una línea lleva pill. El pill se mide después de fijar el texto, porque el
ancho depende de si el valor salió en kW o en MW, y se oculta con duty 0
para no dejar un rectángulo flotando.

### 1.3 El legajo de fichas hablaba otra tipografía y otro tema — MEDIA

El export de fichas (tandas 3-4, de este mismo día) entró con
`QFont("Helvetica")` y colores `QColor(26,26,26)` literales:

- **Tipografía:** el Marco PFD sale en `pfd_fonts` (IBM Plex con fallback)
  y el legajo salía en Helvetica. Plano y ficha son dos documentos del
  mismo trabajo; no pueden hablar dos tipografías. Ahora comparten
  `pfd_fonts` con el mismo patrón de fallback.
- **Tema:** los colores literales eran una paleta clara improvisada. Ahora
  salen de `tokens.THEME_LIGHT` **explícitamente, no de `TOK`** — que
  sigue el tema activo y habría impreso el legajo en gris sobre negro con
  tema oscuro. Esto convierte en **decisión declarada** el «export siempre
  en papel claro» que la auditoría 2 §A.4.4 pedía dejar de tratar como
  accidente: el tema es de la pantalla, no del papel.
- Los **tamaños** siguen siendo literales a propósito: son escala de
  documento impreso (A4 a 300 dpi), la misma «excepción 2g» del Marco PFD.
  Antes no estaba anotado; ahora sí.

**Regresión:** `tests/test_auditoria_ui3.py` — los tres arreglos de esta
sección y el cierre de la auditoría 2 (canvas theme-aware, censo hex,
welcome dentro del sistema, export que no sigue el tema de pantalla).

---

## 2. El hallazgo del ciclo: el sistema de unidades — CERRADO

> Se conserva el diagnóstico entero, no solo la solución: explica por qué
> el arreglo tiene la forma que tiene, y por qué terminó tocando el doble
> de superficies de las que el diagnóstico había listado.

### 2.1 Lo que se encontró

`block_inspector.py` **no importa `flowsheet_units` en absoluto** (0
referencias). Toda la ficha muestra unidades canónicas fijas (°C, bar, kW)
mientras el resto de la app respeta la unidad activa del usuario.

Evidencia directa, un solo panel, capturado con unidad **K** activa
(`audit3_ficha_dark.png`):

- burbujas de corriente, arriba: `T 378.1 K`
- ficha, abajo: `T operación 105 °C`

Es **el mismo dato en dos unidades en la misma pantalla**. Es exactamente
el §D.2 de la auditoría 2 —que se corrigió para `streams_table`—
reapareciendo en una superficie posterior, porque el arreglo fue puntual y
no quedó ninguna regresión que obligara a las superficies nuevas.

Alcance real: no es solo la sección Ficha, es el inspector completo.
Afecta también al export de fichas (`datasheet_rows`), que hereda las
unidades del spec.

**Dirección:** la conversión va en la capa de PRESENTACIÓN, no en el
agregador — `datasheet_spec` debe seguir devolviendo unidades canónicas
(es un contrato de datos que el XLSX y los tests consumen). Formatear con
`funits` en `block_inspector` y en `datasheet_rows`, y agregar un test que
recorra las superficies y falle si alguna imprime una unidad fija.

#### Lo que se hizo

Al arreglarlo apareció que el problema era **más grande y al revés de lo
que decía el diagnóstico**: las burbujas de corriente tampoco respetaban
el sistema. Imprimían K / bar / kg·s⁻¹ **siempre**, porque son las
unidades del solver. Lo que en la captura parecía «la burbuja está bien»
era coincidencia: mostraba K porque muestra K pase lo que pase. Las dos
superficies estaban mal; se veía contradicción solo porque cada una
estaba mal en una unidad distinta.

**El punto que le faltaba al sistema de unidades** (`flowsheet_units.py`):

- `fmt_canonica(value, unit)` — traduce un valor dado en unidad canónica
  a la unidad activa. Es el único punto que una superficie nueva necesita
  llamar. Una magnitud fuera del sistema (m², m³/h, m) sale tal cual: el
  sistema cubre cuatro magnitudes y fingir lo contrario sería peor que no
  convertir.
- `partes_canonica(value, unit)` — igual pero devolviendo (valor, unidad)
  separados, para las superficies que pintan número y unidad con estilos
  distintos. Existe porque partir el string formateado por `split(' ')` se
  rompe con el separador de miles: `'1 001 kPa'`.
- `de_kelvin` / `de_kg_s` — las superficies que guardan K y kg/s entran al
  sistema sin repetir la aritmética en cada una.

**Superficies cableadas** (seis, el doble de las que preveía el
diagnóstico):

1. Sección Ficha del inspector, incluidos los campos de diseño — cada uno
   trae su unidad y `fmt_canonica` decide si participa del sistema.
2. Burbujas de corriente, en sus **tres** modos de render: completo,
   colapsado y degradado por zoom. Los tres imprimían la unidad a mano.
3. Chips de corriente del header del inspector (`StreamPill`) — los que
   se contradecían con la ficha tres centímetros más abajo.
4. Condiciones de operación de la memoria de evidencia.
5. **Tarjetas de métricas** de `inspector_evidence` — ver abajo.
6. Las dos rutas del export de fichas (condiciones y corrientes): XLSX y
   PDF salen en la unidad del usuario porque comparten `datasheet_rows`.

**La 5 la encontró un test, no la lectura.** `test_inspector_metrics`
exige que cada valor de las tarjetas aparezca literal en la memoria
textual: son dos vistas del mismo cálculo y no pueden divergir. Al
convertir la memoria, ese test se puso rojo — porque las tarjetas seguían
en canónicas. Es el mejor tipo de test: no verificaba unidades, verificaba
coherencia, y por eso atrapó una superficie que el diagnóstico no había
listado. Quedó reforzado: ahora la coherencia se comprueba en los tres
sistemas, no solo en el de por defecto.

**Lo que NO se convierte, a propósito:** la memoria de cálculo de
`inspector_evidence` (LMTD, approach, perfiles de temperatura, ΔT_min).
Es la reproducción de cómo se resolvió el equipo, no un dato de lectura:
está tabulada en las unidades en que corrió el cálculo, como en el libro.
Los datos de OPERACIÓN de ese mismo módulo (`T_op`, `P_op`) sí se
convierten, porque son el mismo dato que muestran la ficha y las burbujas
— que era la contradicción original.

#### Los campos EDITABLES — **cerrado también (2026-07-25)**

Eran el caso peligroso: se leen de vuelta para guardar, así que convertir
solo la lectura habría sido **peor que no tocar nada** — el usuario ve
`221.0` rotulado °F, escribe `250` pensando en °F, y el modelo se queda
con `250 °C`. Silencioso y corruptor.

Por eso el arreglo agrega la dirección que faltaba y la deja pegada a la
de ida, en el mismo archivo:

- `a_canonica(value, unit)` — inversa exacta de `fmt_canonica`.
- `a_kelvin` / `de_kelvin` — el par para los campos que el modelo guarda
  en kelvin (`Block.T_op_K`, `flash_T_K`), que hacen un viaje más largo:
  K → °C canónico → unidad del usuario, y al revés al guardar.

**Campos cableados** (pintado + guardado, los dos lados):
`stream_inspector` → temperatura, T objetivo, presión, y el flujo por
componente de la tabla de composición (que salía en tm/año crudo, sin
rótulo). `block_inspector` → T de operación, P de operación, ΔP, duty,
T_flash y P_flash.

**La trampa que quedó anotada en el código:** una DIFERENCIA de
temperatura no se convierte como una absoluta — 10 °C de salto son 18 °F,
no 50 °F. `conv_temp`/`a_canonica` aplican el offset porque son para
temperaturas absolutas. Hoy ninguna diferencia pasa por ahí (ΔT_LMTD,
approach y ΔT_min viven en la memoria de cálculo, que no se convierte), y
ΔP sí puede usarlas porque la presión convierte por factor puro. Si algún
día hace falta un ΔT convertido, va una función aparte y no un parámetro
más en esta.

**Un segundo defecto, que apareció al escribir el test:** el display
redondea. `105 °C` se pinta como `378.1` K, y volver de `378.1` da
`104.95 °C` — es decir, **abrir el inspector y guardar sin escribir nada
movía el valor**. Mirar un dato lo cambiaba. La primera versión del test
lo toleraba con `abs=0.06`; tolerarlo estaba mal.

Lo resuelve `a_canonica_editada(texto, actual, unit, fmt)`: antes de
convertir, compara el texto del campo con el que se habría pintado desde
el valor actual del modelo. Si son el mismo, el usuario no editó ese
campo y se devuelve el valor del modelo **intacto**. Solo se convierte lo
que de verdad cambió.

**Regresión:** 9 tests más, entre ellos los tres que importan de verdad —
que escribir `250` en °F guarde `121.11 °C` **y no 250**; que abrir y
guardar sin tocar deje el modelo exacto (sin tolerancia) en los cuatro
sistemas; y que diez aperturas seguidas no corran el valor ni un dígito,
que es la forma en que un redondeo asimétrico corrompe datos de verdad:
de a poco, cada vez que alguien mira la ficha.

**Regresión:** 15 tests nuevos en `tests/test_auditoria_ui3.py`, que
recorren tres sistemas (Modelo, SI estricto, Imperial) y verifican que
cambie **el valor y no solo el rótulo** — un round-trip kg/s → tm/año →
kg/s que tiene que volver al número de partida.

## 3. El backlog del ciclo — CERRADO (2026-11-06)

Los tres menores de §3.1 y la pasada UX de §3.2 se ejecutaron. Cada
arreglo con su test, que falla sin el arreglo y pasa con él; suite
completa en verde (968 passed, 3 skipped).

### 3.1 Los tres menores

- **Chip DOF truncado — CERRADO.** El sidebar mide 186 px fijos y al
  texto le quedaban 140; «Sistema determinado» pide ~154 y
  «N sobre-especificado» ~152. El label ahora parte por palabra y el chip
  crece. No se ensanchó el sidebar: habría movido todo el inspector.
  Test: `tests/test_auditoria_ui3_dof_chip.py`.
- **Welcome en ventana grande — CERRADO.** Todo el sobrante se iba entre
  «Recientes» y «Ejemplos» (580 px a 1400×900). El contenido es ahora un
  bloque con tope, centrado y anclado arriba. Midiendo apareció un
  defecto peor: la ventana **nunca medía 720×560**, porque los títulos de
  las tarjetas de ejemplo forzaban un mínimo de 1035 px. Ahora envuelven
  (mínimo 665 px). Queda el hueco propio del diseño (~260 px sin
  recientes), que no crece con la ventana. Test:
  `tests/test_auditoria_ui3_welcome.py`.
- **`BlockEditDialog` — RETIRADO.** El diagnóstico de la auditoría estaba
  corrido: «Opciones avanzadas…» ya no se dibujaba (`_build_advanced_link`
  no tenía llamadores), así que el diálogo era código muerto y cinco campos
  que solo él editaba **ya estaban perdidos para el usuario**. Se migraron
  al inspector (`packing_type`, `tray_efficiency`, `HETP_m` en Sizing de
  torre; `allow_reactions` y `active_reactions` en la sección nueva
  «Predictor rxn») y se borró la clase (~1150 líneas). Test:
  `tests/test_auditoria_ui3_blockedit.py` (tabla campo por campo).

### 3.2 La pasada UX de las cuatro superficies

Diez defectos corregidos, un commit cada uno. Test:
`tests/test_auditoria_ui3_superficies.py`.

| Superficie | Defecto | Sev. |
|---|---|---|
| `hx_inspector` | «Diseño riguroso» rotulaba en K temperaturas que estaban en °C | ALTA |
| `book_table` | Las tablas de libro empujaban el inspector a scroll horizontal (estequiometría pedía 912 px contra ~280); ahora la grilla scrollea sola | ALTA |
| `dialog_kit` | La columna de notas no envolvía: 1221 px en un diálogo de 760 | MEDIA |
| `dialog_kit` | Enter cerraba con el ✕ en vez de aplicar | MEDIA |
| `dialog_kit` (en uso) | Setpoints, goal-seek y Lang ignoraban el sistema de unidades; el Δ ahora se resta en la unidad activa (10 °C → 18 °F, no 50 °F) | MEDIA |
| `hx_inspector` | Approach desconocido anunciado como «cruce térmico imposible» | MEDIA |
| `hx_inspector` | Rótulos WHB cortados a mitad de palabra; «tm/yr» → «tm/año» | MEDIA |
| `hx_inspector` | El QSS cascadeaba parches y bordes a cada rótulo de las tarjetas | MEDIA |
| `book_table` | Contexto del flash y duties de Wang-Henke en unidades fijas | MEDIA |
| `book_table` | El encabezado en caps reescribía la notación («Z_I», «X_LK») | BAJA |

---

## 4. Backlog vivo para el próximo ciclo

### 4.1 Selector de equipo comercial — CERRADO (2026-11-06)

Los seis ítems, más tres que aparecieron midiendo. Test:
`tests/test_auditoria_ui3_selector.py` (TB-101, 12 modelos, viewport de
320 px). La sección pasó de 612 px a 280.

- **ALTA — combo desbordado:** `AdjustToMinimumContentsLengthWithIcon`
  (176 px en vez de 448); el popup abre al ancho de la entrada más larga y
  cada entrada lleva su texto completo de tooltip.
- **ALTA — «· 1 modelo»:** el rótulo va arriba del combo, a todo el
  ancho. De paso: `Turton_2018_AppA` y el link de fuente también envuelven.
- **MEDIA — «Cancelar» no deshacía:** la elección queda pendiente y solo
  `_apply_to_block` la escribe; el veredicto se calcula sobre una copia.
- **MEDIA — «30 ≤ 16 bar»:** un chequeo fallido muestra «>».
- **MEDIA — unidades:** veredicto, chequeos, entradas del combo y el
  mensaje de `datasheet.py` pasan por `fmt_canonica`. Efecto: el export
  de la ficha también respeta el sistema activo, y se redondea igual que
  el resto de la ficha («687 kW», no «686.95 kW»).
- **MEDIA (dark) — link azul:** color del token de acento.
- **Extras:** el título «NO ENTRA…» envuelve; los valores en MMBtu/h ya no
  se parten; el texto de cada entrada sale de un solo helper,
  `datasheet.texto_entrada`.

### 4.2 `cake_moisture` — CERRADO (2026-11-06)

La humedad de torta vuelve al modelo unificado como
`mech_sep_cake_moisture`, con la misma semántica que el camino legacy
(torta = sólidos recuperados / (1 − humedad), líquido arrastrado en
proporción a su composición, tope en el líquido disponible). Solo la
aplican filtros y centrífugas; ciclón y decantador la ignoran. Se siembra
desde `cake_moisture` al cargar solo en bloques legacy: `salt_crystal`
FL-101 ya es `mech_sep` con un `cake_moisture` inerte y sembrarlo le
habría cambiado los números. Campo «Humedad de torta» en «Modo especial».

El test de abrir y guardar destapó un bug peor: el campo η mostraba el
default 0.95 de `mech_sep` en vez del valor legacy, así que **abrir y
guardar FL-101 de `sugar.json` le subía la recuperación de 0.75 a 0.95**
sin avisar. Corregido: hoy FL-101 sale idéntico (rel 1e-12) tras abrir,
guardar y re-resolver. Test: `tests/test_cake_moisture.py`; gate de
ejemplos 64/64 sin cambios.

### 4.2b Un segfault que los tests verdes tapaban — CERRADO

Al integrar el ciclo, la suite completa daba «N passed» y el proceso
moría con exit 139 en el apagado. Origen: el bloque de contenido de la
welcome (§3.1) nacía sin padre y PySide lo destruía dos veces. Arreglado
y con test de regresión en subproceso. Lección: correr la suite mirando
el código de salida, no solo el resumen.

### 4.3 Menores

- **MEDIA** — `AtomBalanceCard._element_block` (`book_table.py`): las
  cajas IN/OUT lado a lado piden 300-337 px contra 280; con la grilla de
  métricas (~304 px) el Diagnóstico aún scrollea de costado. *Fix:* apilar
  bajo ~360 px.
- **BAJA** — La nota de Wang-Henke muestra el nombre interno `_wh_result`
  (`inspector_evidence.py`).
- **BAJA** — `hx_inspector`: el badge dice «Sinnott 2024» y la tarjeta WHB
  «Sinnott '19»; el rango WHB «20 000 – 800 000» no tiene unidad; el vapor
  exportado usa 8000 h/año y el sistema de unidades 8760 h.
- **BAJA** — El header colapsable de `RigorousBlock` no es alcanzable por
  teclado ni tiene tooltip.
- **BAJA** — Las fichas de moléculas IN/OUT de `book_table.py` hardcodean
  «IBM Plex Mono» en vez de pasar por los tokens de fuente.
- **BAJA (dark)** — El chip «auto» de los campos del inspector es gris
  sobre gris.
- **BAJA** — El badge de tipo de TB-101 (turbina de vapor) dice «PUMP»
  en el header del inspector.
- **BAJA** — Las entradas del combo comercial no se agrupan por marca.

---

*Arrancó como escaneo de verificación —confirmar que la auditoría 2
estaba cerrada— y terminó con tres colisiones corregidas (§1), el
sistema de unidades cableado en quince campos y superficies (§2), y el
backlog del ciclo cerrado (§3: tres menores y diez defectos de las
superficies nuevas). Cada cambio con su test. Escaneo generado sobre
`55f6c14`; §3 y §4.1-4.2 ejecutadas el 2026-11-06.*
