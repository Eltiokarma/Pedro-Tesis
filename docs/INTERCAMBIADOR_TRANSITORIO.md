# Intercambiador transitorio con inventario distribuido

`dynamic-heat-exchanger/v1` modela dos fluidos monofásicos separados por una pared
con capacidad térmica. Divide la longitud en N volúmenes finitos, tanto en
cocorriente como en contracorriente. El avance incluye API, CLI, perfiles por
celda, auditoría energética y verificación espacial y temporal independiente.

**Estado:** modelo sensible de propiedades constantes y caudales impuestos.
Los resultados son sintéticos. No se ha reproducido un caso publicado completo,
ejecutado otro simulador ni validado contra mediciones. La adaptación de Modelica
descrita abajo conserva explícitamente esa clasificación. Por tanto, el hito
completo de la [ruta de verificación](VERIFICACION_SOLVER_TRANSITORIO.md) sigue
abierto.

## Estados, geometría y orientación

Cada celda tiene tres estados: temperatura del fluido h, del fluido c y de la
pared w. Las letras h/c identifican circuitos; no obligan a que h esté más
caliente. El signo de la transferencia se calcula de las temperaturas.

Las entradas de geometría son **totales del equipo**. Con longitud L, áreas de
sección S_h y S_c y superficies de intercambio A_h y A_c:

\[
M_h=\rho_h S_h L,\quad M_c=\rho_c S_c L,\quad
A_w=(A_h+A_c)/2,\quad M_w=\rho_w A_w s.
\]

La pared se aproxima como una lámina de espesor s y área media A_w; no se deduce
una geometría tubular exacta de las secciones de paso. Cada celda recibe M_h/N,
M_c/N y M_w/N. Refinar N **no multiplica** la masa, el área ni la capacidad del
equipo. Los centros están en x_i=(i+1/2)L/N, con índices desde cero.

El fluido h entra por x=0 y sale por la celda N−1. En cocorriente c también entra
por x=0 y sale por N−1; en contracorriente entra por x=L y sale por la celda 0.
Los tres perfiles se exportan en la misma dirección geométrica x creciente.
Las temperaturas son promedios de celda; la salida se aproxima con la celda
adyacente al puerto correspondiente.

Cada circuito conserva su inventario por separado: su caudal de entrada iguala
su caudal de salida. Los caudales pueden diferir entre circuitos y cambiar por
escalones; no se calculan con presiones ni pueden ser negativos.

## Ecuaciones y balance

Las conductancias totales hacia el centro de la pared incluyen una película y
media pared en serie:

\[
G_h=\left[\frac{1}{h_hA_h}+\frac{s}{2k_w A_w}\right]^{-1},\qquad
G_c=\left[\frac{1}{h_cA_c}+\frac{s}{2k_w A_w}\right]^{-1}.
\]

Si un coeficiente de película es cero, su conductancia es cero. Por celda se
usan g_h=G_h/N, g_c=G_c/N y capacidades C_{h,i}=M_h Cp_h/N,
C_{c,i}=M_c Cp_c/N y C_{w,i}=M_w Cp_w/N:

\[
q_{h,i}=g_h(T_{h,i}-T_{w,i}),\qquad
q_{c,i}=g_c(T_{c,i}-T_{w,i}),
\]
\[
C_{h,i}\dot T_{h,i}=\dot m_h Cp_h(T_{h,up}-T_{h,i})-q_{h,i},
\]
\[
C_{c,i}\dot T_{c,i}=\dot m_c Cp_c(T_{c,up}-T_{c,i})-q_{c,i},
\]
\[
C_{w,i}\dot T_{w,i}=q_{h,i}+q_{c,i}.
\]

El estado aguas arriba es la celda vecina en el sentido del flujo o la frontera
de entrada. Esta discretización upwind es de primer orden. No hay conducción
axial, mezcla entre circuitos, pérdida al ambiente, cambio de fase ni reacción.
Durante una parada de ambos caudales cesa la advección; fluidos y pared siguen
intercambiando calor dentro de cada celda.

Con referencia T_ref=273.15 K, la energía almacenada es la suma de C(T−T_ref)
en ambos fluidos y la pared. La única potencia externa es:

\[
P_{ext}=\dot m_hCp_h(T_{h,in}-T_{h,out})+
\dot m_cCp_c(T_{c,in}-T_{c,out}).
\]

Se integran también la energía externa acumulada y el flujo absoluto de entalpía
de las fronteras. El residuo es E(t)−E(0)−integral(P_ext dt). Su versión relativa
usa max(1 J, |E(0)|, integral de flujo absoluto de entalpía). Se reporta además
el residuo instantáneo entre la suma de tasas de todos los estados y P_ext.
La auditoría se evalúa en las muestras y extremos de los segmentos. Un balance
pequeño por sí solo no demuestra una trayectoria correcta.

## Inicialización, eventos y límites

La inicialización recibe una temperatura uniforme o una lista de N temperaturas
para cada componente. Se respeta ese estado; no se resuelve una inicialización
estacionaria. Los valores iniciales deben estar estrictamente dentro del rango
térmico declarado y las temperaturas de entrada dentro del rango cerrado.

Los eventos contienen `time_s` y `changes`, con cambios de cualquiera de los
cuatro campos de `inputs`. Sus tiempos son únicos, crecientes, mayores que cero
y como máximo iguales a la duración. La señal inicial pertenece a t=0. Antes de
integrar se comprueba también el dominio de todos los eventos futuros.

La integración BDF o Radau se segmenta en los eventos. Los estados son continuos
y las señales son continuas por la derecha: una fila en el instante del cambio
contiene la temperatura alcanzada y la nueva entrada. También se conserva un
evento que coincide con el tiempo final. Un cambio en `output_interval_s` sólo
cambia el muestreo denso; no añade discontinuidades al integrador.

Los límites térmicos son eventos terminales. En este sistema pasivo, entradas e
iniciales admisibles preservan el rango en la solución exacta; los eventos siguen
siendo una protección numérica. El caso se rechaza si contiene campos ajenos al
modelo, valores no finitos, capacidades no positivas o desbordamientos derivados.
Se admiten de 1 a 128 celdas y hasta 500000 valores de perfil estimados.

Hay cancelación cooperativa y presupuesto de evaluaciones. Si una integración
se interrumpe dentro de un segmento, se devuelven únicamente los segmentos
completados; un resultado parcial nunca lleva `success=true`. La salida explica
el motivo y distingue duración solicitada de tiempo alcanzado. No se conserva
un estado interno a medio paso como si fuera una muestra verificada.

## Casos incluidos y procedencia

| Archivo en `data/heat_exchanger_examples/` | Propósito | Clasificación |
|---|---|---|
| `counter_current.json` | Dos circuitos a contracorriente y pared finita | Límite analítico propio |
| `co_current.json` | Misma geometría en cocorriente | Límite analítico propio |
| `transport.json` | Sin intercambio, retardo de residencia | Límite analítico propio |
| `msl_geometry_adaptation.json` | Geometría y pared basadas en MSL; entradas propias con parada/reinicio | Adaptación documentada |

### Fuente de la adaptación

[Modelica Standard Library v4.1.0, `HeatExchanger.mo`](https://github.com/modelica/ModelicaStandardLibrary/blob/v4.1.0/Modelica/Fluid/Examples/HeatExchanger.mo),
blob `3b9eba772017e52a407d0da383a3de6574abe9ac`, consultado el 22 de noviembre
de 2026. El archivo contiene el ejemplo `HeatExchangerSimulation` y la clase
`BasicHX`. Debe leerse esa versión, sin mezclar valores con documentación de MSL
3.2. Las ecuaciones y referencias analíticas anteriores son nuestra formulación.

| Magnitud | Valor utilizado | Procedencia o diferencia |
|---|---:|---|
| Longitud | 20 m | MSL 4.1.0 |
| Sección de cada circuito | 4.5×10⁻⁴ m² | MSL 4.1.0 |
| Área térmica de cada lado | 1.5 m² | MSL 4.1.0 |
| Celdas del ejemplo adaptado | 20 | MSL 4.1.0 |
| Espesor, densidad, Cp y k de pared | 0.005 m; 900 kg/m³; 500 J/(kg K); 100 W/(m K) | MSL 4.1.0 |
| Densidad y Cp de ambos fluidos | 1000 kg/m³; 4180 J/(kg K) | Supuestos constantes propios |
| Películas h/c | 2000/1000 W/(m² K) | Constantes propias basadas en valores iniciales de MSL |
| Temperaturas iniciales | 300 K en todas las celdas | Inicialización propia |
| Entrada h inicial; cambio a 20 s | 360 K; 340 K | Perturbación propia |
| Entrada c | 300 K | Frontera constante |
| Caudales antes/después de parada | 0.2 kg/s por lado | Impuestos |
| Parada; reinicio | 60 s; 90 s | Perturbaciones propias; ambos caudales llegan a cero |

Se identifica h con el lado 2 de MSL y c con el lado 1. MSL usa propiedades
variables, presión/momento, inicialización estacionaria, transferencia local en
el lado 1 y una rampa con inversión del lado 2. Esas operaciones no se reproducen.
Las curvas generadas aquí no son resultados publicados de Modelica.

## Verificación independiente y convergencia

`dynamic_heat_exchanger_examples.py` contiene referencias que **no llaman** al
RHS, al constructor de coeficientes ni al integrador de producción:

1. **Exponencial matricial por tramos.** Ensambla por separado el sistema afín
   de 3N temperaturas, añade una coordenada constante e integra con `expm`.
   Comprueba perfiles completos, orientaciones, propiedades desiguales, entradas
   no alineadas con la salida, parada y reinicio. No elimina el error espacial:
   es la solución del sistema discreto de N celdas.
2. **Efectividad–NTU estacionaria.** Usa el UA continuo con ambas películas y
   la pared completa. Comprueba las temperaturas de salida cuando el tiempo
   transitorio ya es despreciable, con capacidad de flujo igual o distinta.
3. **Transporte sin intercambio.** Para un escalón uniforme, la salida discreta
   sigue una distribución Erlang de N celdas y tiempo de residencia total M/m.
   Al refinar N se aproxima al escalón retardado del flujo pistón continuo.
4. **Parada cerrada.** La energía de cada celda permanece constante y las tres
   temperaturas convergen al promedio ponderado por sus capacidades.

El gate separa cinco comprobaciones:

| Comprobación | Refinamiento | Criterio |
|---|---|---|
| Tiempo, cocorriente | N=6 fijo; BDF, Radau y BDF refinado | Error de perfil <0.005 K; refinado <5×10⁻⁶ K y reducción mínima ×5 |
| Tiempo, contracorriente | Igual al anterior, con cambio de orientación | Mismos límites |
| Espacio estacionario, cocorriente | N=8,16,32,64,128; geometría total fija | Error decreciente; N=128 <0.2 K; último orden entre 0.8 y 1.2 |
| Espacio estacionario, contracorriente | Misma secuencia | Mismos límites |
| Espacio transitorio, transporte | N=4,16,64 | Error Erlang <2×10⁻⁴ K; error L1 normalizado de retardo decreciente y final <0.11 |

En el refinamiento temporal se pasa de rtol=10⁻⁶, atol=10⁻⁸ y paso máximo 8 s a
rtol=10⁻¹⁰, atol=10⁻¹² y paso máximo 0.25 s. En el espacial estacionario se exige
además deriva de salida <10⁻⁵ K durante los últimos 100 s, para no confundir
error espacial con relajación incompleta. El residuo energético relativo debe
ser <10⁻⁹ en todas las ejecuciones del gate.

Un frente discontinuo de advección presenta ensanchamiento numérico: su error L1
con upwind se reduce aproximadamente como N⁻¹ᐟ². No se exige orden uno a ese
frente. El orden cercano a uno se comprueba en el problema estacionario suave.
Reducir tolerancias temporales por sí solo no corrige este ensanchamiento.

## Uso y evidencia reproducible

Desde la raíz del repositorio, con `requirements.txt` instalado:

```bash
python dynamic_heat_exchanger_cli.py --example counter_current --write-example case.json
python dynamic_heat_exchanger_cli.py case.json --check
python dynamic_heat_exchanger_cli.py case.json --out result.json --csv profiles.csv
python dynamic_heat_exchanger_cli.py --example msl_geometry_adaptation --out adapted.json
python gate_dynamic_heat_exchanger.py --out verification.json
python -m pytest tests/test_dynamic_heat_exchanger*.py -q
```

La API principal es `simulate_heat_exchanger(config, cancel=None)` y la
comprobación previa `validate_heat_exchanger(config)`. La configuración completa
y su SHA-256 normalizado acompañan cada ejecución. JSON conserva perfiles,
entradas, salidas, energía, eventos, auditoría, versiones y supuestos. CSV usa
una fila por celda y tiempo, con la orientación, unidades, identificador de caso,
SHA y procedencia, incluidas las diferencias de la adaptación. El índice de
celda empieza en cero. Las temperaturas de los tres componentes están en kelvin.

Los archivos existentes requieren `--overwrite`. Incluso con esa opción se
impide sobrescribir el caso de entrada o usar el mismo destino para JSON y CSV.
Códigos de salida: 0 éxito, 1 simulación incompleta, 2 entrada/IO inválidos y
130 interrupción por teclado. `--check` no genera trayectorias.

[`outputs/dynamic_heat_exchanger_gate.json`](../outputs/dynamic_heat_exchanger_gate.json)
guarda la evidencia numérica reproducible de esta revisión. CI vuelve a ejecutar
las pruebas, el gate y la regresión completa; conserva sus resultados como
artefactos. El SHA de configuración identifica parámetros, no la revisión de
código: esta queda identificada por el commit y la ejecución de CI.

## Alcance que queda pendiente

El componente está conectado mediante
[`dynamic-network/v2`](REDES_CON_INTERCAMBIADOR.md), con editor de conexiones en
el menú Simulación, API y CLI. La red exige un fluido común y conserva las
propiedades propias de la pared. El adaptador automático del lienzo PFD
estacionario sigue pendiente. No resuelve
presiones, inversión de flujo, propiedades dependientes del estado, cambio de
fase, sensores ni control. El siguiente cierre del hito requiere seleccionar y
reproducir un caso publicado completo, con las mismas ecuaciones, propiedades,
inicialización y perturbaciones, o ampliar el modelo para cubrirlas. La
validación experimental continúa reservada a una etapa posterior.
