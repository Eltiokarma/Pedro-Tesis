# Instrumentación: ejemplos exclusivamente sintéticos

Los parámetros de sensores y actuadores son didácticos. Ningún archivo de esta
carpeta representa un registro de planta o una ficha de fabricante.

| Archivo | Finalidad |
|---|---|
| `instrumented_heating.json` | Calentamiento con sensor de tanque sesgado, inercia instrumental, actuador limitado y PI con seguimiento de posición. |
| `valve_steps.json` | Escalones manuales: consigna instantánea, posición continua y velocidades distintas de apertura/cierre. |
| `calibration/study.json` | Ajuste térmico con lecturas indicadas: dos ensayos de ajuste y un enfriamiento reservado. |
| `calibration/reference.json` | Verdad sintética, método independiente, semilla y ruido. |

## Ejecutar

Desde la raíz del repositorio:

```bash
python dynamic_cli.py data/instrumentation_examples/valve_steps.json --out valvula.json --csv valvula.csv
python dynamic_calibration_cli.py data/instrumentation_examples/calibration/study.json --out ajuste_instrumentado.json
python gate_dynamic_instrumentation.py --out aceptacion_instrumentacion.json
```

En el diálogo **Tanque transitorio**, cargar el ejemplo instrumentado o editar
explícitamente **Instrumentación…**. Los canales físicos y los indicados se
representan por separado. Una orden de válvula no equivale a posición medida.

## Referencia y límites

`instrumentation_example.py` genera las observaciones de calibración mediante
una exponencial matricial de seis temperaturas: tanque, pared, camisa y tres
sensores. No utiliza el integrador del tanque para generar los CSV. Esta
referencia exige inventario y posición de válvula constantes, entradas térmicas
por escalones y ausencia de calor de bomba. Rechaza los casos fuera de ese dominio.

Los UA generadores son 800 y 1200 W/K; los valores iniciales del ajuste son 450
y 650 W/K. Los sesgos conocidos son +0,4 / −0,2 / +0,1 K; las constantes de
tiempo, 20 / 10 / 10 s para tanque, pared y camisa. No se estiman los parámetros
instrumentales. El ruido sintético es gaussiano, con desviación estándar de
0,05 K y semilla `20261117`, y se añade después de resolver las trayectorias.

El RMSE máximo reservado de 0,15 K y error absoluto máximo de 0,30 K son criterios
de demostración, no tolerancias de aceptación industrial. Para crear otra copia:

```bash
python instrumentation_example.py mi_demostracion
```

El generador y el gate requieren `--overwrite` para reemplazar salidas existentes.
La CLI de simulación conserva su comportamiento de reemplazo de salidas; protege
las entradas y escribe sus resultados mediante reemplazo atómico. La CLI de
calibración requiere `--overwrite` para reemplazar salidas.

Consulte [modelo, fuentes y limitaciones](../../docs/INSTRUMENTACION_TRANSITORIA.md)
y el [protocolo de calibración](../../docs/CALIBRACION_TRANSITORIA.md). Esta
verificación numérica no caracteriza sensores ni valida una instalación real.
