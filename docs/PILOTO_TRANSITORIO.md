# Primer piloto transitorio: tanque con camisa de líquido

Este módulo incorpora una simulación temporal reproducible de un tanque agitado,
su pared, una camisa de líquido y un circuito de servicio con bomba, tubería y
válvula. Incluye control PI de temperatura, cambios programados y comparación
con series de observaciones. Es un modelo acotado para iniciar la identificación
y validación de un equipo accesible. Los ejemplos incluidos son **sintéticos**.

La simulación vive junto al motor estacionario. Un diagrama existente no se
convierte automáticamente en una planta dinámica: faltan inventarios, geometría,
condiciones iniciales e instrumentación que no pueden deducirse de sus caudales.

## Uso

En el editor Qt: **Simulación → Tanque transitorio…**. El diálogo permite ajustar
condiciones principales, cargar y guardar el caso JSON, ejecutar y cancelar,
consultar curvas/tabla y exportar resultados. La configuración avanzada se
conserva en el archivo del caso.

Sin interfaz gráfica, desde la raíz del repositorio:

```bash
python dynamic_cli.py --write-example mi_tanque.json --measurement-template mediciones.csv
python dynamic_cli.py mi_tanque.json --out corrida.json --csv trayectoria.csv
python dynamic_cli.py mi_tanque.json --measurements mediciones.csv --source-label ensayo-01 --out comparacion.json
```

El primer comando crea un ejemplo y una plantilla **sin filas de datos**. El
tercer comando requiere completar observaciones antes de ejecutarlo. El CSV
`trayectoria.csv` contiene predicciones y no debe presentarse como una medición.
Un `--time-offset-s` explícito permite alinear relojes relativos: tiempo del
modelo = tiempo del CSV + desplazamiento. No se busca automáticamente una
alineación que reduzca artificialmente el error.

Los tres casos incluidos están en
[`data/dynamic_examples`](../data/dynamic_examples/README.md). El control
numérico reproducible se ejecuta con:

```bash
python gate_dynamic_pilot.py --out outputs/dynamic_pilot_gate.json
python -m pytest tests -k dynamic -q
```

API:

```python
from dynamic_tank import default_case, simulate_dynamic_tank
from dynamic_measurements import compare_measurements

case = default_case()
case['inputs']['temperature_setpoint_K'] = 323.15
result = simulate_dynamic_tank(case)
# cancel puede ser una función sin argumentos que devuelve True para detener.
comparison = compare_measurements(result, 'mediciones.csv')
```

El resultado incluye resumen de terminación, configuración/procedencia,
trayectoria, eventos, diagnósticos y residuos de conservación. Un estado `ok`
significa que se completó la integración dentro del alcance declarado; no
certifica precisión de planta. `limit`, `cancelled` y `error` conservan la
trayectoria parcial disponible y no se presentan como una corrida completa.
La CLI devuelve 0 al completar, 1 al detener/fallar, 2 para entradas/IO inválidas
y 130 si se interrumpe con el teclado.

## Física y frontera del sistema

El tanque contiene un líquido bien mezclado de densidad y capacidad calorífica
constantes. El trazador es pasivo: su fracción no cambia esas propiedades. El
caudal de alimentación y el de descarga se especifican; la descarga tiene la
composición y temperatura instantáneas del tanque. La presión y la energía
cinética/potencial del tanque no son estados de este modelo térmico.

Con una referencia común Tref, los estados térmicos son:

- E = M cp (T − Tref), energía sensible del líquido del tanque.
- Ew = Cw (Tw − Tref), energía sensible de la pared.
- Ej = Mj cpj (Tj − Tref), energía sensible de la camisa.

Los balances son:

```text
dM/dt  = min − mout
dMz/dt = min zin − mout z
dE/dt  = min cp (Tin − Tref) − mout cp (T − Tref) + Qtw + Pagitador
dEw/dt = Qjw − Qtw − Qamb
dEj/dt = mj cpj (Tsuministro − Tj) − Qjw + fcalor Pbomba

Qtw  = UA_tanque (Tw − T)
Qjw  = UA_camisa (Tj − Tw)
Qamb = UA_ambiente (Tw − Tambiente)
```

El servicio viene de una fuente de temperatura especificada y regresa fuera de
la frontera del modelo. Mantener esa fuente requiere una instalación externa,
cuyo almacenamiento, calentador/enfriador y consumo total no se calculan aquí.
La camisa tiene inventario fijo y caudales iguales de entrada/salida. No se
modela un depósito de servicio de capacidad infinita como si fuese un equipo
industrial gratuito: su temperatura es una **condición de frontera impuesta**.

La fracción de potencia de eje que entra como calor en el volumen de camisa es
explícita (`jacket.pump_heat_fraction`). El ejemplo usa cero: no asigna al
volumen de camisa la disipación del resto del circuito. Para otra disposición
de equipos hay que justificar esta fracción y evitar contar dos veces la energía.

El circuito hidráulico se resuelve cuasiestacionariamente en cada cambio de
apertura. La bomba utiliza H = H0 n² − k Q²; el sistema suma altura estática,
pérdida de tubería y pérdida de válvula. La curva de bomba y su caudal máximo
corresponden a velocidad nominal; el límite de caudal escala con n. La válvula
usa Kv convencional en m³/h, caída de 1 bar y agua de referencia de 1000 kg/m³,
con característica inherente lineal. El caudal instalado es resultado de la
intersección. Un punto fuera del rango especificado de curva detiene la corrida.

## Alcance declarado y límites

- Se admite calentamiento/enfriamiento monofásico, alimentación, descarga y
  trazador; no ebullición, congelamiento, reacciones ni mezcla estratificada.
- El rango de temperatura configurado delimita el uso aceptado de cp y densidad
  constantes. **Ampliar esos números no valida propiedades ni habilita fases**.
  Antes de usar datos reales hay que comprobar fase y propiedades a la presión
  absoluta de la instalación, especialmente a distinta altitud.
- La geometría del primer modelo se reduce a capacidad y masa inicial. No hay
  nivel en metros, mojado parcial de camisa ni UA dependiente del nivel.
  El UA constante se debe validar dentro del intervalo de carga empleado.
- La bomba usa eficiencia constante y válvula antirretorno ideal. No predice
  cavitación, NPSH, viscosidad, golpe de ariete ni transitorios del rotor.
  La potencia nula a caudal cero no estima las pérdidas reales de una bomba
  operando contra una válvula cerrada.
- El PI es muestreado, con saturación 0–1 y anti-windup. No se simulan por ahora
  dinámica de actuador, histéresis ni retraso de sensor. La medida utilizada por
  el controlador es la temperatura calculada del tanque.
- Se detiene al alcanzar masa mínima, capacidad máxima, límite de temperatura,
  límite hidráulico o fallo numérico. No se recortan estados para ocultar una
  pérdida de inventario o de energía. No hay conexión de actuación a una planta.

Los estados de inventario se integran con SciPy BDF o Radau. Los cambios
programados y las actualizaciones del PI delimitan segmentos; las discontinuidades
no se atraviesan como si fueran entradas suaves. Se integran también los flujos
netos externos para auditar masa, trazador y energía total de tanque+pared+camisa.
Un balance cerrado verifica conservación; no identifica por sí solo si el UA,
la mezcla o las condiciones de frontera representan correctamente el equipo.

El trazador cerca de cero puede presentar excursiones numéricas diminutas.
Se conservan y se informan sus extremos y tolerancia en la auditoría; una
excursión mayor que la tolerancia produce un resultado fallido. Los estados
no se recortan para aparentar conservación o positividad exactas.

## Datos para la primera instalación

Antes de ajustar parámetros, documentar:

| Dato | Por qué se necesita |
|---|---|
| Identificador de equipo, geometría y rango de carga | Relacionar modelo y equipo; verificar volumen útil y área mojada. |
| Fluido, composición, presión absoluta y temperatura | Comprobar fase y justificar propiedades. |
| Masa/volumen inicial y temperaturas de líquido, pared y camisa | Definir condiciones iniciales; documentar estimaciones si no se miden. |
| Material/masa de pared, área de intercambio, aislamiento | Acotar capacidad térmica y transferencia. |
| Curva de bomba, velocidad, eficiencia, rango, Kv y tubería | Sustituir el circuito sintético por parámetros contrastables. |
| Instrumentos, ubicación, calibración, incertidumbre, intervalo | Interpretar diferencias y limitaciones de observación. |
| Temperatura/caudal de servicio, alimentación, descarga, apertura y consignas | Reconstruir las entradas que produjeron cada trayectoria. |
| Inicio común del ensayo y registro de acciones | Alinear series sin confundir demora física con relojes desfasados. |

Seleccionar un equipo disponible y una pregunta concreta; por ejemplo, tiempo
de calentamiento en un intervalo de carga. Usar registros históricos o ensayos
acordados con los responsables de la instalación. Registrar el rango de uso y
las observaciones anómalas, en vez de suprimirlas para mejorar el ajuste.

El CSV de observaciones acepta `time_s` y una o más columnas explícitas:
`tank_temperature_K`, `jacket_temperature_K`, `wall_temperature_K`, `mass_kg`,
`volume_m3`, `tracer_mass_fraction`, `valve_opening`, `utility_flow_kg_s`.
Una columna `<variable>_uncertainty` puede describir incertidumbre estándar
positiva de esa lectura, en las mismas unidades. Temperaturas en K, caudales en
kg/s y fracciones entre 0 y 1. Convertir °C antes de importar; no renombrar
simplemente una columna Celsius como Kelvin.

Los tiempos deben ser únicos, crecientes y finitos. Las celdas vacías son datos
ausentes. Se rechazan nombres de columnas desconocidos, números no finitos y
unidades implícitas. No se extrapola fuera del intervalo simulado. Se usa
interpolación lineal para estados continuos y retención anterior para apertura y
caudal de servicio, que cambian en escalones. El informe conserva hash SHA-256,
alineación, recuentos incluidos/excluidos y RMSE, MAE, sesgo y error absoluto
máximo por variable. Comparar no significa calibrar ni certificar el modelo.

## Criterio para avanzar

1. Verificación numérica: soluciones analíticas, conservación integrada,
   refinamiento temporal, eventos y saturación; errores/entradas inválidas claros.
2. Identificación: escoger parámetros observables, inicialmente pocos (por
   ejemplo un coeficiente térmico), con condiciones de frontera conocidas.
3. Validación: reservar ensayos y condiciones distintos de los usados en ajuste;
   contrastar error y dinámica frente a incertidumbre instrumental y uso previsto.
4. Ampliación justificada: añadir mezcla no ideal, propiedades variables,
   retrasos de sensores, actuadores, depósitos de servicio o reacción únicamente
   cuando lo exijan la decisión y las discrepancias observadas.

La [calibración térmica con ensayos reservados](CALIBRACION_TRANSITORIA.md) ya
permite estimar de uno a tres parámetros con límites, incertidumbres de lectura
como pesos y diagnóstico local de sensibilidad. Se abre con **Calibrar con
ensayos.** en este diálogo o mediante `dynamic_calibration_cli.py`. La
[demostración independiente](../data/calibration_examples/README.md) es
sintética; no constituye validación de planta. La calibración exige el PI
deshabilitado y entradas prescritas para cada ensayo. Su objetivo utiliza la
salida densa del integrador en los tiempos observados; la comparación simple
de CSV descrita arriba conserva su interpolación propia.

Quedan para etapas posteriores los intervalos de incertidumbre paramétrica,
la identificabilidad estructural, generación de modelos por IA y conexión
OPC UA. La prioridad experimental es obtener una ficha real y registros de
ensayos separados para ajuste y contraste, con criterios fijados antes del
ajuste, y comprobar este módulo en un rango definido.

## Referencias de diseño

- [IDAES: balances dinámicos de volumen de control](https://idaes-pse.readthedocs.io/en/stable/reference_guides/core/control_volume_0d.html).
- [IDAES: control PID, saturación y anti-windup](https://idaes-pse.readthedocs.io/en/stable/reference_guides/model_libraries/generic/control/pid.html).
- [IDAES: reconciliación de datos y estimación de parámetros](https://idaes-pse.readthedocs.io/en/stable/how_to_guides/workflow/data_rec_parmest.html).
- [SciPy: solve_ivp, eventos e integradores implícitos](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.solve_ivp.html).

Estas referencias orientan la formulación. No se afirma haber ejecutado una
comparación numérica con IDAES o DWSIM ni incorporado código de esos proyectos.
