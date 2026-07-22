# Auditoría del ejemplo `talara` — ¿sirve para explicar la refinería nacional y sus números rojos?

**Sesión:** 2026-07-22 · Cifras del modelo recalculadas con `simulate(run_economics=True)`
(ISBL 41.07 M, NPV −12.62 M, IRR 6.4 %, γ=1.10). Complementa el análisis económico
de `ANALISIS_GRUPO3_PLANTAS_INDUSTRIALES.md` y cierra el pendiente del splitter
(ver §D).

---

## A. Qué modela el ejemplo (38 bloques, 52 streams)

El tren replica la configuración de la Refinería Talara post-PMRT
(Petroperú), unidad por unidad:

| Unidad del ejemplo | Unidad real | Fidelidad |
|---|---|---|
| V-101 desalador (agua de lavado 25 kt/a → salmuera 4.8 %) | Desalado de crudo | ✓ con split keyed y balance de sal |
| F-101 (15 MW) + T-101 CDU, 6 cortes: gas 2 %, nafta 18 %, turbo 13 %, diesel 22 %, gasóleo atm 8 %, residuo 37 % | Destilación primaria | ✓ rendimientos típicos de crudo pesado — el 37 % de residuo es EL dato clave (ver §C) |
| T-201 VDU: VGO 55 % / residuo de vacío 45 % | Destilación al vacío | ✓ |
| R-FCC, 6 cortes: nafta 48 %, GLP 18 %, LCO 14 %, coque 10 %, slurry 7 %, gas seco 3 % | Craqueo catalítico FCC | ✓ yields de libro (Gary & Handwerk) |
| R-FCK: flexigas 40 %, gasóleo 30 %, nafta 25 %, coque 5 % | **Flexicoking** — la unidad emblemática de la PMRT | ✓ conceptual: convierte el residuo de vacío en livianos + flexigas de bajo poder calorífico |
| R-HTN (350 °C) / R-HTD (380 °C) / R-HTF (320 °C), reacción R_HDS | Hidrotratamiento de nafta / diesel / turbo | ✓ el corazón REGULATORIO de la PMRT: producir combustibles de ≤50 ppm de azufre (gasolina y ULSD) |
| R-RCA (520 °C, R_REFORM) → gasolina 97 | Reformado catalítico | ✓ |
| R-SMR (R_SMR, CH₄ 5.4 kt/a → CO₂ 14.7 kt/a) | Planta de hidrógeno | ✓ con el CO₂ como waste explícito |
| WHB en HTD/HTF/RCA (créditos `bfw_to_steam`), K-101, bombas, tanques | Integración térmica y soporte | ✓ parcial |

**Escala:** 500 000 t/a de crudo ≈ 10.6 kBPD — una demo ~1:9 de la Talara
real (95 kBPD). Los rendimientos son razonables a cualquier escala; el
capex NO escala linealmente (§C.3).

**Producto resuelto por el solver** (tras el fix del splitter): gasolina 97
90.8 kt/a, ULSD 151.5 kt/a, turbo 65 kt/a, GLP 18.3 kt/a, nafta FCK
20.8 kt/a, gasóleo FCK 25 kt/a, flexigas 33.3 kt/a + menores.

## B. Guion de 5 minutos ("cómo funciona la refinería")

1. **El crudo llega sucio y salado** → el desalador (V-101) lo lava; la
   salmuera sale como efluente.
2. **La destilación primaria (T-101) no crea nada** — solo corta el crudo
   por temperatura de ebullición. De un crudo pesado, el 37 % sale por el
   fondo como residuo que casi no vale nada.
3. **El negocio está en convertir ese fondo**: la VDU lo re-corta al vacío;
   el VGO va al **FCC** (lo craquea a gasolina y GLP) y el residuo de vacío
   al **Flexicoking** (lo gasifica/craquea — la apuesta grande de la PMRT:
   Talara ya no vende residual, lo convierte).
4. **Nada de eso es vendible sin limpiar el azufre**: los hidrotratadores
   (HTN/HTD/HTF) saturan el H₂S con hidrógeno de la planta SMR — la razón
   de ser regulatoria del proyecto (combustibles Euro-grade).
5. **El reformador** sube el octanaje de la nafta a gasolina 97.
6. Todo el tren corre sobre hornos de fuego y vapor: la refinería es,
   ante todo, **una máquina de consumir energía para ganar un margen
   chico sobre un flujo enorme**.

## C. ¿Explica los números rojos? — SÍ el porqué operativo, NO el financiero

### C.1 Lo que el modelo SÍ enseña (con sus propias cifras)

La cascada anual del modelo (γ=1.10, hurdle 10 %, 10 años):

```
  Ingresos por productos         346.9 M
− Crudo + insumos               −236.0 M   (68 % de los ingresos)
= Margen bruto de refinación     110.9 M   (222 $/t ≈ 30 $/bbl)
− Utilities (hornos, vapor, CW)  −66.2 M   (se come el 60 % del margen)
− Labor + fijos + overhead γ      −43.8 M
= Gross profit                     +0.9 M/a   ≈ CERO
```

Con FCI 69 M y working capital 10.4 M, eso da **IRR 6.4 % < 10 % de
hurdle → NPV −12.6 M: INVIABLE marginal**. Las tres lecciones:

1. **El margen de refinación es finísimo**: se compra el 68 % de los
   ingresos en crudo. Refinar no es producir valor químico (como metanol
   o HNO₃), es capturar un spread de ~30 $/bbl antes de gastos.
2. **La refinería es energía**: 66 M/a de utilities (F-101 de 15 MW, tres
   hornos de HDS, reboilers) contra un margen de 111 M. Cada punto de
   eficiencia térmica es margen directo.
3. **El veredicto es knife-edge al overhead**: γ=1.05 → NPV +50 M;
   γ=1.10 → −12.6 M (`ANALISIS_GRUPO3`). Un swing de ~65 M por 5 puntos
   de G&A corporativo. Una refinería estatal con overhead pesado pierde
   exactamente donde una esbelta gana — **ese ES el porqué estructural**.

### C.2 Lo que el modelo NO captura del rojo real de Petroperú (límites honestos)

El rojo contable de Petroperú es ante todo **financiero**, y un modelo de
proceso Turton es all-equity por construcción:

1. **La deuda de la PMRT**: el proyecto real pasó de ~1.3–1.7 a
   ~6 500 M USD. El servicio de esa deuda (bonos + intereses
   capitalizados) no existe en el modelo — y es el rubro que domina los
   estados financieros reales.
2. **Sobrecosto ≠ correlaciones**: el FCI del modelo (69 M a escala demo)
   sale de correlaciones Turton de equipo genérico; el capex real de la
   PMRT no lo explica ninguna correlación — es historia de gestión de
   proyecto, no de ingeniería de proceso.
3. **Utilización parcial**: el modelo corre al 100 % de diseño; la
   refinería real arrancó por debajo de capacidad (cada punto de
   utilización no usado es margen bruto perdido sobre capital YA gastado).
4. **Crudo importado**: el modelo compra crudo genérico a 470 $/t plano;
   la realidad importa la mayor parte (la producción local declinó) con
   flete y crédito de proveedores — capital de trabajo que el modelo
   apenas toca (10 M).
5. **Ciclo de cracks**: precios fijos; el margen real de refinación es
   cíclico y puede ser negativo por trimestres.
6. **Unidades omitidas**: recuperación de azufre/aminas (el H₂S aparece
   en los cortes pero no la unidad), tratamiento de aguas agrias,
   cogeneración con flexigas.

### C.3 Veredicto didáctico

**SÍ sirve** para explicar (a) el flujo del crudo a los productos con las
unidades emblemáticas de la PMRT (Flexicoking, HDS/ULSD, reformado, planta
de H₂) y (b) la naturaleza económica del negocio: margen bruto delgado,
intensidad energética, sensibilidad al overhead, capital pesado — la
mitad **operativa** de los números rojos.

**NO pretende** contar la mitad **financiera** (deuda del sobrecosto,
utilización, working capital de importación) — al presentarlo, decirlo
explícito: "este modelo muestra por qué una refinería marginal apenas
empata operando bien; los números rojos de Petroperú suman a eso el
servicio de una deuda de 6 500 M".

## D. Fix aplicado de paso (pendiente del splitter)

El pendiente "splitters FCC redistribuyen flujos al insertar bloque
pass-through" quedó CORREGIDO en esta sesión: la regla de reparto vivía
cuadruplicada y era binaria (todas las salidas keyed o reparto posicional
que ROTABA fracciones al insertar un stream nuevo). Ahora
`effective_split_fractions` es la fuente única con soporte keyed parcial
(las salidas nuevas heredan el remanente 1−Σkeyed) y la ruta de inserción
de la UI copia `split_fraction` al stream de reemplazo. Regresión:
`tests/test_talara_passthrough.py` (4 tests, incluye el baseline de los 6
cortes del FCC por diseño exacto).
