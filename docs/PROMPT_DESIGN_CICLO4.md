# Prompt para la fase Design — ciclo 4 (tablas de libro + deuda tabular)

**Uso:** copiar el prompt de abajo (desde "---PROMPT---") a una sesión de
Claude Design, adjuntando estos archivos del repo:

- `tokens.py` (sistema de diseño vigente: paleta viva light/dark + acentos,
  FONT_DISPLAY/TITLE/UI/VALUE/HINT/LABEL, strokes, severidad única)
- `docs/PLAN_AUDITORIA_LIBROS.md` (el programa de auditoría con libros:
  qué tablas existen, qué identidades se muestran, qué viene)
- `docs/PLAN_CICLO4.md` (bloque A = la deuda ⚡ del bundle ciclo 3 que
  este prompt retoma)
- `docs/REDISENO_CICLO3_2026-07.md` (qué quedó implementado del ciclo 3)
- `inspector_widgets.py` y `dialog_kit.py` (el kit de componentes a
  extender: MetricCard, kicker, kit_table, pills)
- `streams_table.py` y `stream_inspector.py` (las dos superficies sin
  artboard)
- capturas del inspector (light y dark) ya generadas en `outputs/`:
  `design4_stoich_*.png` (tabla estequiométrica sobre el reactor SMR),
  `design4_flash_*.png` (reparto x/y/K sobre el flash de ethanol),
  `design4_pump_*.png` (P-302 de cw_natural: N_s + cavitación),
  `design4_whb_*.png` (WHB field-erected de reformer_whb)

---PROMPT---

Sos el diseñador del frontend de una app de escritorio (PySide6/Qt) de
simulación de procesos químicos con análisis económico, para una tesis de
ingeniería. UI en español. Llevamos tres ciclos auditoría→design→
implementación juntos, todos implementados: tokens + semáforo + topbar
(ciclo 1), capa canvas theme-aware + puertos técnicos + kit de diálogos +
tipografía (ciclo 2), glifos diferenciados + procedencia sudoku +
anotaciones + gradiente térmico (ciclo 3). Después del ciclo 3 nosotros
cerramos por ingeniería: hex=0 en todas las superficies UI (todo respira
tema y acento), figuras matplotlib theme-aware, y un programa nuevo de
**auditoría con ejercicios de libros** que validó el motor contra Fogler,
Seader/Henley, Crane, Perry y Bowman — y parió superficies didácticas
nuevas que hoy están por DEBAJO de tu sistema. Ese es el encargo.

Tu identidad vigente, a respetar: papel cálido (`#f6f3ec`/`#fbfaf6` y su
par sepia-carbón dark), tinta tierra desaturada, acento teal `#0d6e78`
(elegible terracota/cobalto/oliva), IBM Plex Sans/Mono, éxito discreto,
warning/error con color + símbolo (daltónico-safe), export en papel claro.
Como siempre: el mecanismo es nuestro; tu trabajo es **decidir y
especificar valores y comportamientos visuales**.

## Contexto nuevo desde tu último ciclo

1. El set de ejemplos pasó de 58 a **61**: `solvent_rec` (tren de
   condensación de hexano: condensador air-cooled → compresor rotary →
   condensador shell-tube → spiral plate → centrífuga decanter),
   `reformer_whb` (horno reformador → WHB field-erected de 66 t/h →
   U-tube) y `cw_natural` (torre de tiro natural con evaporación/purga,
   splitter, mixer inline, válvula 3-way, bomba reciprocante + PSV,
   coolers double/multiple pipe y flat plate, fan axial). Con esto TODOS
   los eq_types standalone del catálogo tienen instancia real — tus 48
   siluetas del ciclo 3 ahora se ven en escenas de verdad. Usá estos 3
   ejemplos como escenas de prueba de todo lo que especifiques.
2. El inspector ganó **tablas de libro** (evidencia por bloque) que hoy
   salen como texto monoespaciado plano — fieles al libro, pero fuera de
   tu sistema de tarjetas. Abajo van los renders actuales tal cual.
3. La evidencia de equipos ganó **identidades de selección**: N_s con
   tipo de rodete (Perry fig. 10-32) en bombas, C_v de Crane en
   válvulas, Pr del lado proceso en HX, caudal de vapor en WHB.

## Artboards que te pido

### 4a — "Tabla de libro" como componente del sistema (el encargo grande)

Tres tablas viven hoy como `<pre>` monoespaciado dentro de una tarjeta
genérica de evidencia. Te pido UN componente de tabla-de-libro para el
kit (y su spec de uso en las tres instancias), con: jerarquía de columnas
numéricas (¿FONT_VALUE tabular?), encabezado, filas destacables
(limitante/inerte/Σ), chips o footer para los escalares derivados (δ, ε,
V/F), la cita de fuente como pie estándar, y comportamiento en dark.
Renders actuales:

**Tabla estequiométrica (Fogler §3.4)** — en todo reactor con reacción:

```
Reacción    2 SO2 + O2 -> 2 SO3
Base        1 mol de SO2 (limitante)  ·  F_A0 = 82.6 kmol/h

Especie       ν/|νA|      F_i0     θ_i    Cambio    F_i(X)
SO2 (A)        -1.00      82.6   1.000     -41.3      41.3
O2             -0.50      44.6   0.540     -20.6      23.9
N2 (I)         +0.00       168   2.031        +0       168
SO3            +1.00         0   0.000     +41.3      41.3

δ = Σν/|ν_A| = -0.500   ε = y_A0·δ = -0.1400   (y_A0 = 0.280)
X = 0.500  [declarada]
Fuente: Fogler, Elements of CRE 4ª ed., §3.4 (tablas 3-3/3-5)
```

Decisiones que son tuyas: cómo se marcan (A) limitante e (I) inerte
(¿pills? ¿ribbon de fila?), si "Cambio" negativo usa el rojo semántico o
tinta neutra con signo (ojo: acá negativo NO es error, es consumo), y
cómo se muestra la procedencia de X (declarada vs alcanzada — pariente
del spec/auto que ya definiste).

**Reparto del flash (estilo ChemSep)** — en todo vessel con flash:

```
Flash TP    T = 86.9 °C · P = 1.013 bar · V/F = 0.2685 (molar)

Comp.              z_i     x_i     y_i      K_i
ethanol         0.1934  0.1110  0.4177   3.7620
hexane          0.0295  0.0266  0.0374   1.4040
water           0.7771  0.8623  0.5449   0.6319
Σ               1.0000  1.0000  1.0000

K_i = γ_i(NRTL)·P_sat,i/P · Rachford-Rice C-componente
Fuente: Seader/Henley, Sep. Process Principles §4 · Smith-Van Ness-Abbott §12
```

Decisión tuya: ¿K_i merece codificación visual (>1 sube / <1 baja — el
eje frío/cálido que ya existe)? ¿la fila Σ es footer visual?

**Tabla de etapas de columna (Wang-Henke)** — HOY NO EXISTE, la vas a
estrenar: etapa | T | x_LK | y_LK | L | V, con feed stage marcado,
condensador/reboiler diferenciados, y relación con el perfil gráfico
tray-by-tray que ya existe (¿tabla y figura juntas? ¿toggle?).

### 4b — Identidades de selección como métricas ricas

Hoy son líneas de texto dentro de la evidencia. Especificá cómo entran
al sistema de MetricCard/pills:

```
N_s (US)    8003  @ 3550 rpm  →  rodete Francis / flujo mixto
            (Perry 8ª fig. 10-32: <4000 radial · 4000-9000 mixto · >9000 axial)
C_v (líq.)    41.3 gpm/√psi   — Crane TP-410: C_v = Q[gpm]·√(SG/ΔP[psi])
```

La escena de prueba perfecta es la bomba P-302 de `cw_natural`: N_s=8003
(mixto) CON warning de cavitación al lado (−8.2 m de margen) — ¿cómo
conviven la métrica didáctica y la alerta sin competir?

### 4c — streams_table + stream_inspector (pasada formal pendiente)

Nunca tuvieron artboard: consumen tokens de fase pero su micro-tipografía
de celda (valor 10pt + unidad 8pt) y sus tags de path están anotados como
excepción "hasta que exista artboard". Este es el artboard. Decidí:
escala tipográfica de celda definitiva, jerarquía valor/unidad,
procedencia sudoku en la celda (masa locked/derivada/torn — hoy solo P
spec/auto), y densidades.

### 4d — Deuda ⚡ de tu propio bundle ciclo 3 (bloque A del plan)

- Procedencia POR COMPONENTE (qué componente fue declarado vs deducido)
  — excede la pill; va al inspector. Especificá dónde y cómo.
- Cuadro de revisiones △N formal en el export (rev. A/B/C con fecha).
- Anclaje de notas que siguen al bloque/corriente (hoy la guía es
  estática).
- Gradiente térmico en corrientes de PROCESO (hoy solo servicio): pide
  un eje de T de referencia acordado — decidilo.
- Sieve vs valve a 22 px y mixer dynamic: confirmá tu criterio del
  bundle (diferenciar solo si el uso pedagógico lo pide) o cerralo.

### 4e — Burbujas compactas: ratificar o rediseñar la excepción

`stream_bubbles`/`hx_bubbles` usan micro-tipografía de tarjeta compacta
(7-10pt deliberada, 50+ streams en pantalla) anotada como excepción a tu
escala. Decidí: ¿la excepción se ratifica como "escala de tarjeta
compacta" oficial del sistema (con sus valores documentados), o las
burbujas migran a FONT_LABEL/VALUE con otra estrategia de densidad?

## Defectos observados en las capturas (arreglalos de paso)

1. **Columnas que bailan** (design4_stoich/flash): la tabla
   monoespaciada vive dentro de una tarjeta con fuente proporcional →
   el alineado por espacios tiembla. Es el síntoma central del encargo
   4a (la tabla necesita SER un componente, no un `<pre>`).
2. **Barras de balance recortadas** (design4_pump/flash): las barras
   IN/OUT del balance de masa desbordan y el valor queda cortado
   ("00000.0") al ancho real del panel. Especificá el layout correcto
   (¿valor arriba? ¿barra con ancho máximo?).
3. **Sub de MetricCard recortado** (design4_pump): "Perry fig. 10-32"
   se corta abajo de la tarjeta N_s. Regla de overflow del sub.

## Entregable

Como en los ciclos anteriores: bundle HTML con artboards 4a-4e, specs
dibujables (valores exactos: pt, px, tokens, espaciados), par light/dark
de cada pieza, y la lista ⚡ de lo que decidas dejar fuera con su razón.
Nosotros montamos todo después (evidence_specs, kit, tabla WH incluida).
