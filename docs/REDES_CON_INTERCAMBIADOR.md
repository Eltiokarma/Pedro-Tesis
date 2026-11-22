# Redes con intercambiadores distribuidos

`dynamic-network/v2` conecta tanques, alimentaciones y uno o varios
intercambiadores en una única integración temporal. Se accede desde
**Simulación → Red transitoria e intercambiadores…**, además de API y CLI.
Los casos anteriores `dynamic-network/v1` siguen siendo válidos.

## Puertos y acoplamiento

| Puerto | Uso permitido |
|---|---|
| `HX1.hot_in` | Destino de corrientes del circuito h |
| `HX1.hot_out` | Origen de corrientes del circuito h |
| `HX1.cold_in` | Destino de corrientes del circuito c |
| `HX1.cold_out` | Origen de corrientes del circuito c |

Cada corriente transfiere masa, energía sensible y trazador desde el estado
actual conjunto. No se intercambian resultados calculados en pasos separados
ni se introduce un retardo de un paso. Varias alimentaciones pueden llegar al
mismo puerto; sus flujos se suman sin crear un tanque de mezcla adicional.

Entrada y salida deben tener el mismo caudal en cada circuito. Se comprueba al
inicio y después de todos los eventos. Al detener un circuito se detiene también
su transporte interno; fluidos y pared siguen intercambiando calor. Se admiten
recirculación, división/unión y conexiones entre varios intercambiadores.

## Inventarios y balance común

Cada tramo contiene dos inventarios líquidos y una masa sólida de pared. Las
masas líquidas son las de la geometría original divididas entre N. La pared usa
su masa física, Cp y densidad propios, sin puertos de materia ni trazador. Su
energía es M_w Cp_w (T_w−273.15 K), no una masa equivalente de líquido.
Capacidades y conductancias proceden del mismo constructor del
[intercambiador independiente](INTERCAMBIADOR_TRANSITORIO.md).

Las celdas líquidas se conectan en el sentido de cada flujo y transfieren calor
a su pared. El ensamblador descuenta cada flujo del donante y lo añade al receptor.
BDF/Radau resuelve todos los estados a la vez, aprovechando la estructura dispersa
de dependencias. Los límites térmicos incluyen las paredes. Los límites de masa
y la cancelación conservan las muestras aceptadas y los perfiles disponibles.

El balance global incluye tanques, líquidos del intercambiador y masa sólida.
La contabilidad externa incluye sólo alimentación, descarga y calor externo;
recirculaciones y transferencias entre equipos no se cuentan como fronteras.
El trazador se transporta por cada circuito líquido sin cruzar la pared.

## Contrato y límites

La estructura v2 mantiene los campos de la [red v1](REDES_TRANSITORIAS.md) y añade
`heat_exchangers`. Cada equipo contiene `id`, `provenance`, `cells`,
`flow_arrangement`, `geometry`, `hot_fluid`, `cold_fluid`, `wall`, `heat_transfer`,
`initial` e `initial_tracer_mass_fraction`. Este último tiene `hot` y `cold`, con
fracciones uniformes o listas de N valores. Los demás campos usan las unidades
del intercambiador independiente.

El componente no acepta `inputs`, `simulation` ni `events` propios: conexiones
y calendario de la red determinan las fronteras y el reloj común. La función
`component_from_case(id, config, hot_tracer=0, cold_tracer=0)` extrae equipo y
estado inicial de un caso independiente. El llamador define expresamente las
conexiones y los eventos de la red.

Esta versión conserva un fluido común de Cp y densidad constantes. Ambos lados
del intercambiador deben coincidir con `fluid`; se rechazan propiedades
incompatibles. La pared mantiene sus propiedades independientes. El modelo
aislado continúa admitiendo fluidos distintos por lado, pero el ensamblador
actual no implementa redes de múltiples fluidos.

Se permiten hasta 8 intercambiadores, 128 celdas de intercambiador en total y
32 tanques. El límite de perfiles es 500000 valores estimados. El prefijo `dx_`
está reservado al ensamblaje interno; el caso público y sus eventos no pueden
referenciarlo. Los resultados muestran los equipos y puertos originales.

## Uso desde el editor

1. Abra **Simulación → Red transitoria e intercambiadores…** y cargue uno de
   los dos ejemplos o un caso existente.
2. Edite tanques y alimentaciones. En «Intercambiadores» puede añadir equipos,
   cambiar los tramos y elegir cocorriente/contracorriente. La geometría y los
   perfiles completos se conservan al cargar y guardar el caso.
3. En «Conexiones», indique equipos/puertos, descarga y caudales. Los cuatro
   puertos de cada intercambiador aparecen debajo de las tablas.
4. En «Cambios programados», agrupe por tiempo los cambios simultáneos de caudal,
   temperatura, trazador o potencia. Una parada requiere cambiar entrada y salida
   de cada circuito en el mismo instante.
5. Pulse «Simular red». «Resultados» muestra tanques y temperaturas de salida;
   «Perfiles» permite elegir equipo y muestra temporal para inspeccionar ambos
   fluidos, pared y trazador por posición.

La ejecución ocurre fuera del hilo de la interfaz. Cancelar o cerrar solicita
la terminación y espera al hilo; no destruye un cálculo activo. La tabla muestra
una vista reducida, mientras las exportaciones conservan todas las muestras.
Después de editar, los resultados se identifican como la última corrida. Una
nueva ejecución fallida no exporta el éxito anterior. El caso de entrada está
protegido frente a las exportaciones, incluso si se selecciona su misma ruta.

Los perfiles iniciales uniformes conservan su valor al cambiar N. Los no
uniformes requieren un perfil explícito de la nueva malla; no se interpolan ni
descartan silenciosamente. El editor trabaja con un circuito transitorio
explícito: no deduce automáticamente inventarios ni condiciones iniciales de
los bloques estacionarios del lienzo PFD. Ese adaptador sigue pendiente.

## CLI, exportaciones y verificación

```bash
python dynamic_network_cli.py --example coupled_recirculation --write-example circuit.json
python dynamic_network_cli.py circuit.json --check
python dynamic_network_cli.py circuit.json --out result.json --csv profiles.csv
python dynamic_network_cli.py --example coupled_feed --out feed-result.json
python gate_dynamic_network_components.py --out coupling-evidence.json
python -m pytest tests/test_dynamic_network_components*.py -q
```

La salida v2 añade `series[].heat_exchangers`, con perfiles, salidas, energía,
inventarios y trazador. Mantiene `nodes`, `ports` y auditoría. Los perfiles usan
x creciente; en contracorriente la salida c está en la celda 0. La procedencia y
posiciones están en `metadata.heat_exchangers`. El SHA-256 identifica el caso
público normalizado, sin nombres internos de ensamblaje.

CSV distingue `unit_kind=tank` y `unit_kind=heat_exchanger_cell`. Cada fila incluye
tiempo, equipo, unidades y procedencia. Los campos no aplicables quedan vacíos,
sin inventar ceros. Las filas del intercambiador conservan también la fuente
y diferencias de su componente.

El gate exige error de perfiles <2×10⁻⁴ K contra una exponencial matricial
independiente del ensamblador de producción en ambas orientaciones, con
parada/reinicio. Contrasta BDF/Radau y un refinamiento con reducción de error
mínima de ×5. El transporte se verifica con una respuesta Erlang a través de
cuatro celdas y el tanque de descarga, incluyendo trazador. El residuo global
relativo debe ser <10⁻⁹. Evidencia:
[`outputs/dynamic_network_components_gate.json`](../outputs/dynamic_network_components_gate.json).

Las pruebas incluyen equivalencia con el equipo independiente, mezcla de
entradas, encadenamiento, Cp de pared distinto, límites, cancelación,
exportaciones y ciclo de vida Qt. Son verificaciones teóricas con datos
sintéticos. No reproducen íntegramente el ejemplo publicado de Modelica ni
constituyen validación experimental.
