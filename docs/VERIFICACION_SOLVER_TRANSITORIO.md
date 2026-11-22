# Verificación del solver transitorio

## Objetivo de esta etapa

El objetivo inmediato es construir y verificar el solver mediante casos teóricos
reproducibles de equipos y circuitos. La validación experimental se pospone a una
etapa posterior: no es un requisito para completar los hitos numéricos actuales.
Un caso publicado puede representar una instalación industrial sin contener
mediciones de esa instalación; esa diferencia debe conservarse en su procedencia.

Los PR #151, #152, #153 y #154 se integraron, en ese orden, el 16 de noviembre de
2026 en `claude/understand-document-improve-g8xoM`. La base consolidada es
`a06beb5d92b83b80b104ec97f45c4cfb351269f4`. El circuito térmico finito amplía esa
base; no convierte automáticamente los diagramas estacionarios en dinámicos.

## Evidencia exigida por caso

| Evidencia | Pregunta que responde |
|---|---|
| Fuente primaria, versión, parámetros y unidades | ¿Qué problema estamos reproduciendo? |
| Ecuaciones, condiciones iniciales y perturbaciones | ¿El problema está completamente definido? |
| Inventarios y balances por equipo y conjunto | ¿Se conserva lo que debe conservarse? |
| Solución analítica o cálculo de referencia independiente | ¿Se obtiene la trayectoria correcta? |
| Cambio de método y refinamiento de tolerancias | ¿El resultado depende indebidamente del método numérico? |
| Saturación, arranque, parada y límites de dominio | ¿Qué sucede fuera del punto nominal? |
| Procedencia y simplificaciones visibles | ¿Hasta dónde permite concluir la evidencia? |

Cerrar el balance global es necesario pero insuficiente. Un error de signo puede
aparecer tanto en el balance como en su auditoría y dejar un residuo pequeño; por
eso se contrastan también temperaturas y transferencias con referencias externas
al integrador de producción.

## Clasificación obligatoria

1. **Reproducción publicada:** mismos parámetros, ecuaciones y condiciones de
   contorno. Registrar el resultado publicado y su tolerancia o redondeo.
2. **Adaptación documentada:** se toma una topología o formulación publicada, pero
   se cambian propiedades, geometría, fronteras o control. Enumerar esas diferencias;
   no atribuir sus curvas al trabajo original.
3. **Caso límite analítico:** idealización propia con solución independiente, por
   ejemplo acumulación adiabática o relajación exponencial. Comprueba un aspecto
   preciso del solver y no equivale a una planta industrial completa.
4. **Comparación entre simuladores:** requiere ejecutar ambos modelos equivalentes.
   Leer el código de EnergyPlus, Modelica o DWSIM no constituye esa comparación.
5. **Validación experimental:** exige mediciones independientes y evaluación de
   incertidumbre y aplicabilidad. Queda fuera de la etapa actual.

## Secuencia técnica

| Hito | Condición para avanzar |
|---|---|
| Circuito térmico finito: depósito, calentador, bomba, camisa y retorno | Superar los casos y controles de [circuito térmico](CIRCUITO_TERMICO_TRANSITORIO.md), con capacidad limitada y balance común. |
| Conexiones reutilizables entre unidades dinámicas | Reproducir más de una topología y comprobar inicialización consistente, conservación en cada puerto y diagnóstico de especificaciones incompatibles. |
| Intercambiador con inventario y residencia distribuidos | Reproducir un caso publicado completo; demostrar convergencia espacial y temporal. |
| Reactor con cinética y energía acopladas | Verificar balances elementales, calor de reacción, casos rígidos y estabilidad frente a perturbaciones con una referencia reproducible. |
| Cambio de fase y presión dinámica | Requerir propiedades y derivadas termodinámicas consistentes, referencias de equilibrio y manejo explícito de eventos de fase. |

Cada ampliación necesita un caso que la justifique. Si una publicación omite una
geometría, una condición inicial o una señal de entrada indispensable, el caso se
registra como incompleto o adaptado; no se rellenan esos datos presentándolos como
publicados. Los parámetros ajustados a una trayectoria tampoco sustituyen una
verificación independiente.

Los resultados teóricos y sintéticos deben conservar su etiqueta al exportar o
generar conjuntos de datos para futuros modelos de IA. Los dominios no modelados
no se convierten en datos fiables por producir muchas simulaciones.

## Continuación del 22 de noviembre de 2026

Tras la integración del circuito térmico en `0746172`, la primera implementación
de conexiones reutilizables es [`dynamic-network/v1`](REDES_TRANSITORIAS.md):
inventarios de mezcla conectados por puertos de masa, energía y trazador, con
caudales impuestos. Incluye serie, bifurcación/unión y recirculación, comprobación
de condiciones iniciales y de inventarios fijos en todos los eventos, límites
terminales, API/CLI, exportaciones y cuatro casos verificables independientemente.

El caso de EnergyPlus reproduce parámetros publicados; los otros tres son límites
analíticos propios. El gate contrasta BDF/Radau, refinamiento, conservación y las
trayectorias de temperatura/trazador. No es una comparación ejecutada contra otro
simulador ni validación experimental.

Este avance cubre la conexión dirigida de inventarios finitos. Aún no implementa
un ensamblador gráfico de equipos existentes, la inicialización de redes DAE,
presiones/caudales desconocidos, uniones sin inventario ni transporte distribuido.

### Avance del intercambiador distribuido

[`dynamic-heat-exchanger/v1`](INTERCAMBIADOR_TRANSITORIO.md) incorpora inventarios
de ambos fluidos y pared por volúmenes finitos, cocorriente/contracorriente,
eventos, parada/reinicio, API/CLI y perfiles exportables. Se verifican por
separado la integración temporal contra una exponencial matricial independiente,
la convergencia espacial estacionaria contra efectividad–NTU y el retardo
transitorio contra la respuesta Erlang y el límite de flujo pistón.

La geometría y pared del ejemplo MSL 4.1.0 se usan como **adaptación documentada**,
con propiedades constantes y perturbaciones propias. Se mantienen explícitos
los pendientes: reproducción de un caso publicado completo y conexión del
componente al ensamblador de redes. Este avance numérico no cierra todavía el
hito de intercambiador de la tabla ni representa una comparación ejecutada
contra Modelica o validación experimental.
