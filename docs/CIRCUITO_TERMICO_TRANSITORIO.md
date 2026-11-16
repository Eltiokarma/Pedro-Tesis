# Circuito térmico transitorio con energía de servicio finita

El objetivo de esta etapa es verificar el solver mediante casos teóricos reproducibles, referencias numéricas publicadas y balances independientes. La validación experimental queda para una etapa posterior. Una integración exitosa y un balance cerrado son condiciones necesarias, pero no demuestran por sí solos que un modelo represente cualquier instalación industrial.

## Física y alcance

El esquema `dynamic-tank/v3` conecta cuatro inventarios: líquido del tanque de proceso, pared, líquido de la camisa y depósito de servicio. La bomba, tubería y válvula establecen el caudal mediante la intersección cuasiestacionaria de la curva de bomba y las resistencias. El servicio retorna desde la camisa al depósito. Su temperatura de suministro es un estado calculado, no una fuente térmica de capacidad ilimitada.

Con capacidades térmicas constantes, las ecuaciones son:

\[
M_t C_{p,t}\dot T_t=\dot m_f C_{p,t}(T_f-T_t)+UA_t(T_w-T_t)+Q_{agit}
\]

para el caso de inventario de proceso constante utilizado por el oráculo; el motor también conserva el inventario variable mediante balances de energía y masa.

\[
C_w\dot T_w=UA_t(T_t-T_w)+UA_j(T_j-T_w)-UA_{w,a}(T_w-T_a)
\]

\[
M_j C_{p,j}\dot T_j=\dot m_u C_{p,j}(T_r-T_j)-UA_j(T_j-T_w)
\]

\[
M_r C_{p,j}\dot T_r=Q_h+Q_p-\dot m_u C_{p,j}(T_r-T_j)-UA_{r,a}(T_r-T_a)
\]

`r` identifica el depósito, `j` la camisa y `w` la pared. El depósito y la camisa comparten Cp y densidad del mismo líquido. La transferencia por recirculación aparece con signos opuestos y desaparece del balance global.

La potencia eléctrica aplicada es `min(solicitada, máxima)`; el calor al líquido es esa potencia multiplicada por la eficiencia. La saturación se informa explícitamente. No hay enfriador reversible ni capacidad negativa escondida en un calentador.

En un circuito cerrado sin elevación neta, el trabajo hidráulico termina disipándose. El calor de bomba contabiliza la potencia hidráulica más la fracción declarada de pérdidas mecánicas que llega al líquido. Se asigna al depósito como aproximación concentrada. No se añade una segunda vez en la camisa. La curva actual no predice las pérdidas reales de bomba a caudal cero.

Se conservan sensores de primer orden, sesgo declarado, actuador y PI del esquema v2. `pump_speed_fraction` es una entrada perturbable; no representa inercia del rotor. El esquema v3 exige altura estática neta cero. La hidráulica no calcula presión absoluta, cavitación, NPSH, golpe de ariete, circulación natural ni flujo inverso.

El modelo supone mezcla perfecta, líquido monofásico y propiedades/UA constantes dentro del intervalo declarado. No predice ebullición, estratificación, transporte distribuido en tuberías ni reacciones. Llegar a un límite térmico debe detener el caso con diagnóstico; no permite extrapolar propiedades indefinidamente.

## Casos y niveles de evidencia

### Parámetros publicados de EnergyPlus

Fuente primaria fijada a [EnergyPlus v24.2.0, `WaterThermalTank_CalcTempIntegral`](https://github.com/NatLabRockies/EnergyPlus/blob/v24.2.0/tst/EnergyPlus/unit/WaterThermalTanks.unit.cc#L1060), blob `dcc74d48ce4f02eb4d465633336f6d24414d13d3`.

El depósito usa 148.67 kg, Cp 4183.9 J/(kg·K), temperatura inicial 57.22 °C, ambiente 19.72 °C, entrada 14.44 °C, caudal 0.06761 kg/s y UA 5 W/K. Sin calefacción, a 269.2 s la integral publicada de temperatura es 14716.6 °C·s, con tolerancia 0.1 °C·s.

La solución independiente da 52.21956227895557 °C y 14716.592986047968 °C·s. El gate integra el **balance de componente de producción** con retorno prescrito y comprueba ambos valores; no afirma que ese caso sea un circuito cerrado.

La variante publicada sin caudales ni pérdidas y con 1000 W tiene integral 15461.9 °C·s ±0.1. Se ejecuta con el motor v3 completo, aislando el depósito. Su temperatura crece linealmente. Las cifras se conservan en `energyplus_reference.json`; la conversión de integral a K·s requiere sumar 273.15 multiplicado por la duración.

La [referencia de ingeniería de EnergyPlus](https://bigladdersoftware.com/epx/docs/26-1/engineering-reference/water-thermal-tanks-includes-water-heaters.html) expone el balance del depósito mezclado y la solución de `dT/dt = a + bT`, incluido el límite `b = 0`. Se reconstruyen esas ecuaciones; no se ha ejecutado el programa externo ni copiado su implementación.

### Circuito acoplado propio

La topología toma como orientación [Modelica HeatingSystem v4.1.0](https://github.com/modelica/ModelicaStandardLibrary/blob/v4.1.0/Modelica/Fluid/Examples/HeatingSystem.mo): depósito, bomba, calentador, tuberías, válvula y retorno. El archivo consultado tiene blob `b739462e8f0c8f1c922391abd67c810ef4758991`.

**Nuestro ejemplo no reproduce sus parámetros ni sus curvas.** Modelica usa otros modelos de fluido y tubería y un quemador con dependencia lineal de temperatura, que no equivale a nuestra potencia limitada. En consecuencia, las magnitudes y perturbaciones del JSON se declaran propias.

El oráculo de `thermal_loop_examples.reference_temperatures` ensambla independientemente una matriz de cuatro temperaturas y una coordenada constante. Evalúa su exponencial por intervalos de entradas constantes. No reutiliza el RHS, Jacobiano, solver hidráulico ni integrador del motor. La curva de bomba se resuelve separadamente mediante su expresión algebraica. Se deshabilitan feedback y retraso de válvula, y se exige inventario de proceso constante para preservar la linealidad.

Se interrumpe el calentador a 600 s, se detiene la bomba a 1000 s y se restablecen a 1300 s. La temperatura permanece continua al cambiar entradas; cambian sus derivadas. Se comparan las cuatro trayectorias, la conservación global y los resultados BDF/Radau. Un segundo BDF con tolerancias y paso más exigentes debe reducir el error contra el oráculo.

### Potencia insuficiente

Un caso propio de depósito aislado de 10 kg, Cp 4180 J/(kg·K), UA 20 W/K, ambiente 298.15 K y calentador máximo de 100 W recibe una solicitud de 1000 W. El equilibrio es 303.15 K. Una temperatura objetivo ilustrativa de 323.15 K no puede alcanzarse con esa capacidad; no hay controlador activo en esta prueba. El setpoint del proceso no gobierna este depósito desacoplado.

La trayectoria se contrasta con `T = T_equilibrio + (T_inicial - T_equilibrio) exp(-t/tau)`, con `tau = M Cp / UA`. El motor debe reportar saturación, respetar la potencia máxima y conservar energía. Esta combinación de parámetros es un ensayo numérico propio, no una ficha de equipo industrial.

Un segundo caso sí conecta todos los equipos y activa el PI de temperatura de proceso: 10 kg de proceso, 5 kg de camisa y 10 kg de servicio; pared de 4500 J/K; alimentación 0.05 kg/s a 298.15 K; calentador limitado a 1000 W eléctricos con eficiencia 0.98. El PI intenta mantener 323.15 K. Debe abrir completamente la válvula y permanecer por debajo de la consigna, pues la potencia útil es insuficiente. La trayectoria se compara con el oráculo independiente en apertura manual máxima —equivalente solo mientras se comprueba que el PI permanece saturado— y el estado final con cuatro balances estacionarios resueltos independientemente.

## Ejecución y criterios

En la interfaz: **Simulación → Tanque transitorio → Nuevo ejemplo: circuito térmico cerrado**. El panel izquierdo permite configurar el depósito, las pérdidas y el calentador. La pestaña **Servicio y potencia** muestra las temperaturas de suministro y retorno y las potencias solicitada, aplicada y transferida al fluido. La curva de suministro muestra la temperatura calculada del depósito.

Para crear un caso editable desde CLI:

```console
python dynamic_cli.py --thermal-loop --write-example circuito.json
```

Después puede ejecutarse el JSON con la misma CLI usada para los casos anteriores. El nuevo formato v3 todavía no está admitido por la calibración: esa función mantiene soporte para v1/v2. El foco actual es comprobar las ecuaciones y el solver del circuito; no se estima automáticamente su configuración a partir de registros.

```console
python gate_dynamic_thermal_loop.py --out outputs/dynamic_thermal_loop_gate.json --overwrite
python -m pytest tests/test_dynamic_thermal_benchmarks.py -q
```

El gate produce siete comprobaciones y devuelve código distinto de cero si alguna falla:

1. Descarga fría de EnergyPlus usando el balance de componente; error de temperatura < 1e-6 K, error de integral contra solución analítica < 1e-4 °C·s y tolerancia publicada 0.1 °C·s.
2. Calentamiento adiabático de EnergyPlus usando el motor completo; mismos límites de temperatura e integral.
3. Cuatro inventarios contra exponencial matricial: error máximo < 2e-4 K.
4. Corte de potencia, parada y restablecimiento de bomba: potencia y caudal coherentes con cada intervalo.
5. Contraste BDF/Radau < 2e-4 K y BDF refinado contra oráculo < 2e-5 K, sin empeorar respecto al error inicial salvo piso de redondeo.
6. Equilibrio con potencia insuficiente: error < 2e-4 K y saturación explícita.
7. Circuito acoplado con PI activo y potencia insuficiente: error contra trayectoria independiente < 2e-4 K, diferencia final al equilibrio < 0.01 K y saturación comprobada durante todo el ensayo.

Todos los casos del motor deben terminar correctamente y tener residuos relativos de masa, trazador y energía < 1e-8. Se registran valores de error, tolerancias, auditorías y hashes de configuración; un indicador booleano solo no es evidencia suficiente.

## Qué sigue después de este hito

Ampliar una colección de casos publicados con parámetros, condiciones iniciales, secuencias de perturbaciones, unidades y resultados de referencia completos. Cada ficha debe distinguir reproducción exacta, adaptación y prueba límite propia. Incorporar nuevas familias físicas solo cuando haya un caso trazable que las exija y permita comprobarlas.

El trabajo pendiente incluye propiedades variables, presión y cambios de fase, transporte distribuido, inicialización de redes más generales y equipos industriales adicionales. Una comparación instalada contra DWSIM/Modelica/IDAES también es pendiente; citar sus modelos no equivale a ejecutarlos. La validación experimental no forma parte del criterio de cierre actual.
