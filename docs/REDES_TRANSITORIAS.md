# Redes transitorias de inventarios líquidos

## Qué incorpora este hito

El circuito térmico v3 tenía una topología fija. `dynamic-network/v1` permite
describir varias unidades de mezcla mediante una lista de inventarios y conexiones:
serie, bifurcación, unión con mezcla, recirculación y unidades aisladas. Cada puerto
transporta masa, energía sensible y trazador desde su donante. El motor suma esa
misma transferencia con signos opuestos en los inventarios conectados.

Es una primera implementación de **conexiones dinámicas con caudales impuestos**.
Incluye API de Python, CLI, cuatro casos reproducibles, referencias independientes
y comprobaciones en CI. Los módulos del tanque v1/v2/v3 mantienen su interfaz y
su funcionamiento. Este formato nuevo no se carga en el editor gráfico existente
ni convierte los flowsheets estacionarios en redes dinámicas.

La etapa sigue siendo verificación teórica. Ningún resultado constituye validación
experimental o una recomendación para controlar una instalación.

## Alcance y ecuaciones

Todos los inventarios contienen el mismo líquido incompresible con Cp y densidad
constantes. Se supone mezcla perfecta dentro de cada unidad. El trazador es
pasivo: su fracción no altera las propiedades del líquido. Las conexiones tienen
dirección declarada y caudal no negativo, sin volumen, retardo ni pérdidas propias.

Por inventario se integran tres cantidades extensivas:

\[
M_i,\qquad E_i=M_i C_p(T_i-T_{ref}),\qquad Z_i=M_i z_i,
\qquad T_{ref}=273.15\ \mathrm{K}.
\]

Para una conexión de caudal f desde i hacia j, su transferencia es:

\[
\boldsymbol\Phi_{i\to j}=
\left(f,\ fC_p(T_i-T_{ref}),\ fz_i\right).
\]

Esta transferencia se resta a i y se suma a j. Una alimentación usa su temperatura
y fracción de trazador prescritas; una descarga usa las del inventario que vacía.
No se promedian temperaturas en el puerto. Una bifurcación transporta el mismo
estado del donante por cada rama, con el caudal de esa rama. Una unión mezcla en
un inventario **finito**, con tiempo de residencia; no representa una unión ideal
de volumen nulo.

\[
\frac{dM_i}{dt}=\sum f_{in}-\sum f_{out},\qquad
\frac{dZ_i}{dt}=\sum f_{in}z_{donante}-\sum f_{out}z_i.
\]

El balance energético suma las entalpías sensibles transportadas, una potencia
neta prescrita, pérdidas al ambiente y contactos térmicos entre inventarios:

\[
\frac{dE_i}{dt}=\sum\Phi_{E,in}-\sum\Phi_{E,out}
+Q_i-UA_{i,a}(T_i-T_a)+\sum_j UA_{ij}(T_j-T_i).
\]

`heat_power_W` puede ser positivo o negativo. Representa una potencia neta dada,
no un calentador con capacidad calculada, eficiencia o controlador incorporados.
El equipo limitado del circuito v3 conserva su propio modelo. No se añade trabajo
de presión, energía cinética/potencial, reacción, ebullición ni propiedades variables.

Al sumar todos los inventarios desaparecen los puertos y contactos internos. El
registro de flujos externos integra separadamente las alimentaciones, descargas,
potencias netas y pérdidas al ambiente. Se comparan sus integrales con los cambios
de masa, energía y trazador almacenados. Este balance es una comprobación necesaria;
las soluciones independientes de abajo comprueban además la trayectoria correcta.

## Contrato e inicialización

Los JSON completos están en [data/network_examples](../data/network_examples).
Todas las magnitudes son SI y las temperaturas están en kelvin.

| Sección | Contenido y restricciones |
|---|---|
| `fluid` | Cp en J/(kg·K) y densidad en kg/m³, comunes y positivos. |
| `nodes` | ID, masa inicial/mínima/máxima, temperatura y fracción inicial de trazador, modo de inventario, potencia neta y UA al ambiente. |
| `sources` | Fronteras de alimentación con temperatura y fracción de trazador prescritas. No almacenan masa ni energía dentro de la red. |
| `edges` | ID, origen, destino y caudal en kg/s. `target: null` es una descarga al exterior. |
| `heat_links` | ID, dos inventarios y UA en W/K. La transferencia puede cambiar de signo según las temperaturas. |
| `events` | Tiempo y cambios simultáneos de caudales, condiciones de fuentes o potencias netas. |
| `simulation` | Duración, muestreo, paso máximo, tolerancias, BDF/Radau e intervalo térmico admisible. |
| `provenance` | Clasificación teórica, fuente y notas obligatorias. |

La inicialización usa las masas, temperaturas y fracciones **declaradas**. Calcula
energías, masa de trazador y volumen M/rho; no busca un estado estacionario ni
admite imponer además una presión o un volumen incompatible. Los campos no
implementados y las claves desconocidas se rechazan.

En `inventory_mode: fixed`, entradas y salidas deben equilibrarse en t=0 y después
de **cada** evento. Se tolera únicamente una diferencia relativa de 1e-12 respecto
al caudal total para el redondeo de sumas. No se inventa una descarga para cerrar
un balance. En modo `variable`, la diferencia de caudales cambia la masa: el caso
se detiene al llegar a la masa mínima o máxima. La masa inicial debe estar
estrictamente dentro de esos límites y la temperatura inicial dentro del dominio.

Se rechazan IDs repetidos, destinos inexistentes, conexiones de una unidad consigo
misma, alimentaciones conectadas directamente al exterior, caudales negativos,
eventos desordenados o vacíos y escalas numéricas no representables. Una unidad
aislada es válida si su estado está definido: conserva sus cantidades salvo calor
externo. Con caudal cero no hay transporte ni división por el caudal.

Un ciclo de recirculación es válido porque cada unidad aporta estados iniciales y
capacidad finita. Esto no resuelve la inicialización de redes algebraicas generales.
Los caudales deben provenir del usuario o de un cálculo externo adecuado; el
módulo no determina si una bomba puede proporcionarlos.

## Eventos y límites

El solver reinicia la integración en las discontinuidades de entrada. El muestreo
usa interpolación densa y no cambia la dinámica. En el instante del evento se
conservan los estados y se muestran los nuevos flujos: convención continua por la
derecha. Los cambios simultáneos se aplican juntos antes de evaluar la nueva red.

Con caudales constantes por intervalo, la masa varía linealmente; el tiempo de
llegada a su límite se calcula antes de integrar ese intervalo. Los límites de
temperatura se localizan como raíces continuas. Los límites son terminales incluso
si coinciden con un evento programado o con la duración solicitada.

`summary.status` distingue `ok`, `limit`, `cancelled` y `error`. Una parada conserva
las muestras obtenidas y su diagnóstico. Una cancelación durante el integrador
conserva los intervalos completados; no promete conservar las etapas internas de
un intervalo que no terminó. Hay límites de 32 inventarios, 128 conexiones de cada
tipo, 1.000 eventos, 20.000 muestras y 200.000 evaluaciones del RHS. El agotamiento
del presupuesto es un error explícito.

## Casos y soluciones independientes

Los oráculos de `dynamic_network_examples.py` usan fórmulas específicas de cada
caso. No importan el ensamblador de conexiones, RHS ni integrador de producción.
Los parámetros de los tres primeros casos son propios; no se atribuyen a una
planta ni a las curvas de Modelica.

### Tres tanques en serie

Tres inventarios de 100 kg reciben 1 kg/s. Todos parten de 298.15 K y trazador cero;
la alimentación tiene 338.15 K y fracción uno. Cada residencia es tau = 100 s.
Para la etapa k, con x = t/tau:

\[
R_k(t)=1-e^{-x}\sum_{r=0}^{k-1}\frac{x^r}{r!},\quad
T_k=298.15+40R_k,\quad z_k=R_k.
\]

### Bifurcación y mezcla

La alimentación pasa por A y se divide en 0.6 kg/s hacia B y 0.4 kg/s hacia C.
Ambas ramas llegan a D, que descarga 1 kg/s. A y D tienen 100 kg, B tiene 60 kg
y C tiene 40 kg. Así cada inventario tiene residencia de 100 s. A sigue R1, B y C
siguen R2, y D sigue R3. Esta elección permite comprobar separadamente reparto de
caudales, conservación y mezcla usando la fórmula anterior.

### Recirculación, parada y reinicio

A contiene 100 kg a 338.15 K con z=1; B contiene 50 kg a 298.15 K con z=0.
Circula 1 kg/s por cada dirección. Un contacto de UA=200 W/K transmite calor entre
ellos y continúa activo aunque se detenga la circulación. Ambos caudales se cortan
a 100 s y se restablecen a 200 s. Cp=4180 J/(kg·K).

Las medias ponderadas de temperatura y trazador son constantes. Si a(t) es el
tiempo acumulado con circulación encendida, las diferencias obedecen:

\[
\Delta z=e^{-(1/100+1/50)a(t)},\qquad
\Delta T=40e^{-(1/100+1/50)[a(t)+(200/4180)t]}.
\]

A se obtiene sumando un tercio de la diferencia a la media; B restando dos tercios.
Durante la parada el trazador queda constante, mientras el contacto sigue
igualando las temperaturas. El caso comprueba que un caudal cero no desactiva el
calor por conducción ni conserva indebidamente la transferencia advectiva.

### Parámetros publicados de EnergyPlus

Se reproduce el depósito de la prueba numérica
[`WaterThermalTank_CalcTempIntegral`, v24.2.0](https://github.com/NatLabRockies/EnergyPlus/blob/v24.2.0/tst/EnergyPlus/unit/WaterThermalTanks.unit.cc#L1060),
blob `dcc74d48ce4f02eb4d465633336f6d24414d13d3`, consultado el 22 de noviembre de 2026.
Usa 148.67 kg, Cp=4183.9 J/(kg·K), caudal de 0.06761 kg/s, UA=5 W/K, temperatura
inicial 57.22 °C, entrada 14.44 °C y ambiente 19.72 °C, sin calefacción. A 269.2 s
la integral publicada es 14716.6 ± 0.1 °C·s.

El oráculo resuelve el balance escalar afín de forma analítica. La trayectoria
numérica de la red se compara contra él y su integral se obtiene mediante Simpson
sobre las muestras. La integral analítica es 14716.592986047968 °C·s. **No se
ejecutó EnergyPlus**: se reutilizan parámetros y una referencia numérica publicada.

## Criterios reproducibles

Cada uno de los cuatro escenarios se ejecuta con BDF, Radau y BDF refinado
(rtol=1e-10, atol=1e-12 y paso máximo de 1 s). El gate requiere:

- Finalización correcta y los mismos tiempos de salida entre BDF y Radau.
- Error de temperatura frente a la fórmula < 2e-4 K y de trazador < 5e-6.
- Diferencia BDF/Radau < 2e-4 K y mejora al refinar, salvo piso de 1e-9 K.
- Residuo integrado relativo de masa, energía y trazador < 1e-9.
- Caudales de parada/reinicio coherentes en el circuito cerrado.
- Integral del caso EnergyPlus dentro de ±0.1 °C·s de la publicación y a menos
  de 1e-4 °C·s de la integral analítica independiente.

Los errores, tolerancias, hashes, procedencia y auditorías se guardan en
[`outputs/dynamic_network_gate.json`](../outputs/dynamic_network_gate.json).
La primera ejecución con NumPy 2.4.6 y SciPy 1.17.1 obtuvo error máximo BDF de
1.90e-6 K y máximo refinado de 2.33e-8 K; el residuo integrado relativo máximo
fue 9.23e-11. Son cifras de verificación numérica, no incertidumbre de planta.

Las pruebas también cubren llenado/vaciado con fórmula independiente, límites
térmicos, cambios de fuente, cancelación, presupuesto de trabajo, entradas inválidas,
protección de archivos y conservación de etiquetas sintéticas en JSON/CSV.

## Uso

```console
python dynamic_network_cli.py --example split_merge --write-example red.json
python dynamic_network_cli.py red.json --check
python dynamic_network_cli.py red.json --out corrida.json --csv trayectorias.csv
python gate_dynamic_network.py --out outputs/dynamic_network_gate.json --overwrite
python -m pytest tests/test_dynamic_network*.py -q
```

También están disponibles `cascade`, `recirculation` y `energyplus_mixed_tank`.
Desde Python se usan `validate_network(case)` y `simulate_dynamic_network(case,
cancel=callback)` en `dynamic_network`. La exportación JSON contiene configuración,
hash, flujos por puerto, estados por unidad, diagnóstico y auditoría. El CSV usa
una fila por unidad y tiempo, con magnitudes SI y etiquetas de procedencia.

Las salidas existentes requieren `--overwrite`; ni siquiera con esa opción se
permite reemplazar el caso de entrada o un alias suyo. Los códigos de salida son
0 para completar/comprobar, 1 para una parada física o numérica, 2 para entrada/IO
inválida y 130 para interrupción.

## Referencias de conexiones y trabajo pendiente

La [especificación Modelica 3.6, capítulo 15](https://specification.modelica.org/maint/3.6/stream-connectors.html)
explica que las propiedades transportadas dependen del lado donante. Su
[apéndice C](https://specification.modelica.org/maint/3.6/derivation-of-stream-equations.html)
desarrolla balances de masa y entalpía en conexiones, incluyendo división y mezcla.
Ambas fuentes se consultaron el 22 de noviembre de 2026. Aquí se aplica únicamente
el caso dirigido con caudales prescritos y mezcla en inventarios finitos; no se
implementan `inStream`, inversión de flujo, uniones algebraicas ni las ecuaciones
de presión de Modelica. No se copió su código ni se ejecutó ese simulador.

Quedan pendientes el editor de redes, adaptadores explícitos para equipos del
piloto v1/v2/v3, restricciones de presión y determinación de caudales, uniones de
volumen nulo, distintos fluidos, propiedades variables y transporte distribuido.
El siguiente modelo nuevo debe elegirse por una referencia completa y trazable,
según [la ruta de verificación](VERIFICACION_SOLVER_TRANSITORIO.md). La validación
experimental sigue fuera de los criterios de cierre de este hito.
