# Instrumentación y actuador del tanque transitorio

Este hito distingue el estado físico del equipo, la lectura del instrumento y
la orden enviada a una válvula. Añade una aproximación determinista de sensores
térmicos y movimiento del actuador al [piloto](PILOTO_TRANSITORIO.md). Sus
parámetros y ejemplos son sintéticos: no describen una marca ni una planta
caracterizada, y no habilitan control de equipos reales.

## Uso y compatibilidad

Los casos `dynamic-tank/v1` mantienen su comportamiento. Los casos
`dynamic-tank/v2` declaran la instrumentación y posición inicial. La API ofrece:

```python
from dynamic_tank import default_instrumented_case, simulate_dynamic_tank

case = default_instrumented_case()  # Ejemplo sintético editable.
result = simulate_dynamic_tank(case)
```

Un caso v2 guardado en JSON se ejecuta con la CLI existente:
`python dynamic_cli.py caso_v2.json --out corrida.json --csv trayectoria.csv`.
En la serie, `*_temperature_K` conserva la temperatura física,
`*_sensor_temperature_K` es el estado instrumental y `*_indicated_temperature_K`
la lectura sesgada; `valve_command` es la orden y `valve_opening` la posición.
No renombrar un canal físico como indicado ni una orden como posición medida.

En Qt se configura desde **Tanque transitorio → Instrumentación…**. Los casos
sintéticos están en `data/instrumentation_examples/instrumented_heating.json`
y `valve_steps.json`; `calibration/study.json` utiliza tres canales indicados.
El generador `instrumentation_example.py` conserva procedencia sintética.

| Sección de `instrumentation` | Claves obligatorias |
|---|---|
| `temperature_sensors.tank`, `.wall`, `.jacket` | `time_constant_s`, `bias_K`, `initial_temperature_K` |
| `valve_actuator` | `enabled`, `time_constant_s`, `opening_rate_per_s`, `closing_rate_per_s`, `initial_opening` |
| Parámetro del PI | `tracking_time_s` |

## Sensor: temperatura física e indicación

Cada temperatura de tanque, pared y camisa tiene un estado instrumental propio:

$$
\tau_s\frac{dT_s}{dt}=T_{\mathrm{física}}-T_s,
\qquad T_{\mathrm{indicada}}=T_s+b.
$$

La constante `time_constant_s` es no negativa, en segundos. Para valor positivo
se aplica la ecuación anterior; cero selecciona medición ideal algebraica sin
estado dinámico: `T_s = T_física`. El sesgo `bias_K`
es aditivo y puede tener ambos signos. El estado inicial del sensor se declara
separadamente de la temperatura física. El PI usa la indicación del tanque;
los balances y límites térmicos del proceso usan las temperaturas físicas.

Se supone una sonda no invasiva: su intercambio de calor no altera el inventario
energético del tanque. El estado instrumental no se suma a la energía almacenada.
Una sonda cuya masa o pérdidas cambien apreciablemente el proceso requiere otro
modelo térmico.

Ante un escalón constante a $T_f$, la solución independiente es
$T_s(t)=T_f+(T_s(0)-T_f)e^{-t/\tau_s}$. Para un modelo de un polo,
$t_p=-\tau_s\ln(1-p)$: `t90 = tau_s * ln(10)` y `t63.2 ≈ tau_s`.
El 63 % literal corresponde a aproximadamente `0.99425 * tau_s`.
Convertir un `t90` de catálogo en una constante de tiempo supone aceptar esta
aproximación; un termopozo y un sensor pueden tener varios modos térmicos.

WIKA describe ensayos de respuesta con condiciones definidas de medio,
velocidad y escalón de temperatura. El mismo instrumento responde de manera
distinta en aire y agua. Conservar en la ficha la instalación, inmersión, medio,
caudal, temperatura y método de caracterización; no trasladar una constante
de catálogo a una instalación diferente sin contraste.

## Válvula: orden y posición

La orden normalizada $u$ y la posición real $x$ pertenecen a `[0, 1]`.
El actuador combina un seguimiento de primer orden con velocidades máximas:

$$
\frac{dx}{dt}=\operatorname{clip}\left(\frac{u-x}{\tau_v},
-r_{\mathrm{cierre}},r_{\mathrm{apertura}}\right).
$$

La hidráulica utiliza la posición real. Las velocidades tienen unidades de
fracción de carrera por segundo y pueden ser distintas al abrir y cerrar.
La orden permanece constante entre acciones manuales o muestras del PI.
La trayectoria del actuador se evalúa analíticamente por tramos.

Para un escalón ascendente de amplitud $\Delta=u-x_0$, si
$\Delta\leq r\tau_v$, la respuesta es exponencial. Si es mayor, primero
se mueve a velocidad constante hasta
$t_*=(\Delta-r\tau_v)/r$; después:

$$
x(t)=u-r\tau_v e^{-(t-t_*)/\tau_v},\qquad t\geq t_*.
$$

El tiempo de carrera completa, la constante de tiempo y un tiempo muerto puro
son magnitudes diferentes. La aproximación no representa fricción, stiction,
banda muerta, histéresis ni la dinámica neumática interna. Emerson distingue
estas limitaciones y la dependencia de la respuesta con el tamaño del escalón.

## PI y secuencia causal

El controlador conserva muestras discretas. En la versión instrumentada utiliza
seguimiento de la posición efectiva para descargar el integrador cuando el
actuador no puede cumplir la orden. Con integral expresada como apertura:

$$
u_{\mathrm{raw}}=b_{\mathrm{PI}}+K_pe+I,
\qquad \dot I=K_ie+(x-u_{\mathrm{raw}})/T_t.
$$

La actualización usa el error y la posición retenidos de la muestra anterior
para avanzar el intervalo transcurrido; después calcula el error y la orden
nuevos. Un cambio de consigna no se integra retroactivamente. Si el actuador es
ideal, se retiene su posición efectiva tras aplicar la orden. El término lineal
de tracking se integra de manera exacta para esos valores retenidos, evitando
la inestabilidad artificial de Euler cuando el paso es grande frente a `Tt`.
Esto no garantiza estabilidad de cualquier combinación de ganancias y equipo.

MathWorks recomienda realimentar la salida del actuador para anti-windup cuando
hay dinámica saturada en cascada. El PI anterior conserva su comportamiento
para los casos de la versión previa; no se reinterpretan silenciosamente sus
parámetros como un controlador diferente.

## Mediciones y calibración

Las columnas físicas y las indicadas tienen significados diferentes. Comparar
un termómetro real con su canal indicado, cuando el modelo instrumental sea
aplicable. Una lectura lenta no implica necesariamente que el intercambio
térmico del tanque también lo sea.

La [calibración](CALIBRACION_TRANSITORIA.md) debe conservar parámetros
instrumentales conocidos y entradas prescritas. No identifica automáticamente
constantes de tiempo ni sesgos. Ajustar simultáneamente transferencia térmica,
retardo instrumental y sesgo puede confundir sus efectos. Reservar ensayos
completos y revisar residuos, sensibilidad y rango de aplicación.

Registrar además de las temperaturas: orden y posición de la válvula, tiempos
de acciones y muestreo, estado inicial, condiciones de servicio y procedencia
de cada parámetro. Un desfase entre relojes no equivale a inercia del sensor ni
a movimiento lento del actuador.

## Verificación y alcance

Las pruebas contrastan soluciones analíticas de sensores y actuador, una
referencia por exponencial matricial del sistema térmico acoplado con sensores,
causalidad del PI y conservación de masa, trazador y energía. Los límites de
inventario, temperatura física y dominio de bomba siguen siendo límites del
proceso aunque una indicación instrumental difiera.

Se mantienen las hipótesis de líquido monofásico, mezcla perfecta, propiedades
y UA constantes, pared concentrada y circuito hidráulico cuasiestacionario.
No se añaden ruido aleatorio, tiempo muerto puro, stiction, fallos eléctricos,
cavitación, dinámica de presión, cambio de fase ni conexiones OPC UA.
Conservar balances y recuperar soluciones sintéticas verifica software;
la validación experimental de un equipo permanece pendiente.

## Fuentes primarias

- [WIKA: medición de tiempos de respuesta](https://blog.wika.com/en/knowhow/measuring-the-response-times-of-electrical-thermometers/).
- [Modelica: sistema de primer orden](https://doc.modelica.org/om/Modelica.Blocks.Continuous.FirstOrder.html).
- [Modelica: límite de velocidad de señal](https://doc.modelica.org/om/Modelica.Blocks.Nonlinear.SlewRateLimiter.html).
- [MathWorks: anti-windup y tracking del actuador](https://www.mathworks.com/help/simulink/slref/anti-windup-control-using-a-pid-controller.html).
- [Emerson: respuesta y limitaciones de válvulas](https://www.emersonautomationexperts.com/2019/valves-actuators-regulators/avoid-operational-issues-proper-control-valve-selection/).

Las fuentes orientan los modelos y sus límites; no se copió código ni se afirma
haber ejecutado un benchmark contra Modelica, Simulink o DWSIM.
