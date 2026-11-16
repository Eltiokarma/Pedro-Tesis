# Calibración térmica del tanque transitorio

Este hito añade estimación acotada de parámetros térmicos compartidos entre
ensayos del [piloto transitorio](PILOTO_TRANSITORIO.md), evaluación de ensayos
reservados y un informe reproducible. Está preparado para importar observaciones;
**los datos incluidos son sintéticos y no validan una planta**. No se han
incorporado registros experimentales reales a esta demostración.

El alcance sigue siendo un tanque perfectamente mezclado, pared y camisa de
líquido, con propiedades constantes e hidráulica cuasiestacionaria. Calibrar
coeficientes no añade fases ni mezcla imperfecta. La [versión instrumentada](INSTRUMENTACION_TRANSITORIA.md)
añade respuesta de sensores y actuador con parámetros declarados; la calibración
térmica no identifica automáticamente esos parámetros. Un ajuste puede compensar un error de modelo con un parámetro
incorrecto; por eso se separan ajuste, diagnóstico y contraste reservado.

## Ejecución

Desde la raíz del repositorio, con las dependencias del proyecto instaladas:

```bash
python dynamic_calibration_cli.py data/calibration_examples/study.json --check
python dynamic_calibration_cli.py data/calibration_examples/study.json --out informe_calibracion.json --fitted-case tanque_candidato.json --experiment-id cal_hot
```

`--check` verifica contrato, casos, datos y duplicados entre particiones; no
ajusta parámetros. El segundo comando estima, evalúa los ensayos reservados y
solicita una copia del caso candidato de `cal_hot`. Exportar el caso requiere
convergencia; puede conservar advertencias o criterios incumplidos. Revisar el
informe antes de utilizarlo.

Para generar otra copia reproducible de la demostración:

```bash
python dynamic_calibration_cli.py --write-example mi_estudio_sintetico
```

Las salidas existentes requieren `--overwrite`; las entradas del estudio no
pueden ser destinos de exportación. Las carpetas de salida de informes deben
existir. Antes de exportar, la CLI comprueba que los hashes de las entradas
utilizadas coincidan con los de su comprobación previa.

| Código de salida | Interpretación |
|---|---|
| `0` | Comprobación previa correcta, o ajuste convergido con estimación local utilizable y todos los criterios reservados satisfechos. |
| `1` | Ajuste fallido/inconcluso, diagnóstico desfavorable o criterios reservados excedidos. |
| `2` | Entrada o acceso a archivos inválido. |
| `130` | Cancelación o interrupción. |

Ninguno acredita precisión industrial ni autenticidad de datos.

En Qt: **Simulación → Tanque transitorio… → Calibrar con ensayos.** Abrir un
estudio JSON o la demostración sintética, revisar procedencia, parámetros y
partición, y pulsar **Calibrar**. Las pestañas muestran parámetros, errores por
ensayo y diagnóstico. Se puede cancelar y guardar el informe o una copia del
caso seleccionado. Exportar no modifica el tanque abierto ni las entradas.

API sin interfaz:

```python
from dynamic_study import load_study
from dynamic_calibration import calibrate_study

study = load_study("data/calibration_examples/study.json")
report = calibrate_study("data/calibration_examples/study.json")
# Opcionales: cancel() devuelve True para detener;
# progress(item) recibe fase, evaluaciones y llamadas al simulador.
```

## Contrato del estudio

El manifiesto usa `schema_version: "dynamic-calibration-study/v1"`. Todos los
campos mostrados son obligatorios y se rechazan claves desconocidas. Este
ejemplo ilustra la estructura; requiere sus propios casos y CSV:

```json
{
  "schema_version": "dynamic-calibration-study/v1",
  "study_id": "equipo-01-campana-01",
  "equipment_id": "equipo-01",
  "parameters": [
    {"path": "wall.ua_tank_W_K", "initial": 450, "lower": 100, "upper": 2500}
  ],
  "observables": {
    "tank_temperature_K": {
      "scale_K": 0.05,
      "max_validation_rmse_K": 0.15,
      "max_validation_abs_error_K": 0.3
    }
  },
  "experiments": [
    {
      "experiment_id": "ensayo-ajuste",
      "role": "calibration",
      "case_file": "casos/ensayo-ajuste.json",
      "measurements_file": "datos/ensayo-ajuste.csv",
      "data_kind": "user_supplied",
      "source": "Identificador del registro, instrumentos y responsable",
      "time_offset_s": 0
    },
    {
      "experiment_id": "ensayo-reservado",
      "role": "validation",
      "case_file": "casos/ensayo-reservado.json",
      "measurements_file": "datos/ensayo-reservado.csv",
      "data_kind": "user_supplied",
      "source": "Otro ensayo, reservado antes del ajuste",
      "time_offset_s": 0
    }
  ],
  "options": {"max_evaluations": 100}
}
```

Los números anteriores son ilustrativos, no límites ni tolerancias recomendados
para un equipo real. `user_supplied` significa aportado por el usuario; no
certifica que sea una medición. La procedencia queda declarada, sin verificación
independiente de autenticidad. El otro valor admitido es `synthetic`.

Se admiten entre uno y tres parámetros de esta lista:

| Ruta | Significado | Unidad | Dominio de búsqueda |
|---|---|---|---|
| `wall.ua_tank_W_K` | Conductancia pared–líquido del tanque | W/K | `lower >= 0` |
| `wall.ua_jacket_W_K` | Conductancia camisa–pared | W/K | `lower >= 0` |
| `wall.ua_ambient_W_K` | Conductancia pared–ambiente | W/K | `lower >= 0` |
| `wall.heat_capacity_J_K` | Capacidad térmica total de pared | J/K | `lower > 0` |

Todos requieren valores finitos y `lower < initial < upper`. UA es una
conductancia total, no un coeficiente por unidad de área. Los límites deben
venir de geometría, material, aislamiento o estimaciones independientes y
quedar fijados antes del ajuste. Las demás propiedades se tratan como conocidas.

Los observables admitidos son `tank_temperature_K`, `wall_temperature_K` y
`jacket_temperature_K`; seleccionar solo temperaturas realmente observadas.
Para cada una se requieren escala positiva, RMSE máximo positivo y error
absoluto máximo positivo, en K. Cada ensayo debe aportar al menos una lectura
de cada observable. Debe haber más lecturas numéricas de ajuste que parámetros;
ese mínimo no garantiza que puedan distinguirse sus efectos.

Un estudio contiene de 2 a 12 ensayos, con identificadores únicos y al menos uno
de cada rol. `max_evaluations` es un entero entre 1 y 500. Las referencias son
rutas relativas al manifiesto con `/`, no rutas absolutas. Cada caso debe pasar
`validate_case` y tener `controller.enabled = false`: se reproducen entradas
prescritas y no se ajusta contra un PI ideal que sustituya al controlador real.

Los casos representan el mismo equipo y comparten parámetros físicos fijos.
Pueden variar estados y carga iniciales, entradas, eventos, configuración de
simulación y velocidad de bomba. Los parámetros ajustados tienen un valor común
para todos los ensayos. Cambiar carga exige comprobar que UA constante siga
siendo aplicable: el validador no conoce el área real mojada de la camisa.

## Observaciones e incertidumbre

El CSV usa unidades explícitas, por ejemplo:

```csv
time_s,tank_temperature_K,tank_temperature_K_uncertainty
0,298.15,0.10
7,298.21,0.10
15,,
28,298.64,0.10
```

Los tiempos son finitos, únicos y crecientes. Una celda vacía es una observación
ausente, nunca cero. La incertidumbre estándar es positiva y tiene la unidad de
la lectura. Convertir °C a K antes de importar y documentar la conversión. No
se infieren unidades, desfase de reloj ni retardos del sensor.

El tiempo del modelo es `time_s + time_offset_s`. Todas las lecturas numéricas
seleccionadas deben estar en `[0, duration_s]` y dentro del intervalo de
temperatura declarado por el caso, además de ser positivas. No se recortan ni
descartan silenciosamente lecturas fuera del dominio. Revisar instrumento y
aplicabilidad antes de ampliar límites: el intervalo por sí solo no verifica
fase ni propiedades del fluido real.

```text
r = (temperatura_simulada - temperatura_observada) / s
s = incertidumbre estándar de la lectura, si existe; en otro caso, scale_K
objetivo = suma(r²), solo para role = calibration
```

`scale_K` es una escala declarada, no una incertidumbre inferida. Las
incertidumbres sirven de pesos; no se propaga incertidumbre de entradas,
propiedades o estados iniciales. Tampoco se modela correlación temporal, sesgo
instrumental o discrepancia del modelo. Inflar incertidumbres reduce pesos;
no mejora la física ni modifica los criterios de error en K.

La calibración solicita predicciones en los instantes alineados mediante la
salida densa del integrador. No interpola linealmente una tabla de exportación
gruesa para su objetivo. Las discontinuidades de entradas siguen delimitando
segmentos de integración.

## Partición, optimización y diagnóstico

La partición usa ensayos completos, no filas sorteadas de una misma corrida.
Los residuos reservados no participan en objetivo, Jacobiano, selección de
parámetros ni parada del optimizador. Después se evalúan los criterios para
**cada observable de cada ensayo reservado**. Mejorar entrenamiento no basta.

El cargador utiliza instantáneas y hashes SHA-256 del manifiesto, casos y CSV.
Rechaza contenido repetido entre roles mediante huellas de bytes y de
observaciones seleccionadas normalizadas, antes y después de alinear tiempos.
Detectar renombrados o reformateos no demuestra independencia experimental ni
detecta toda reutilización parcial o transformación posible.

Se usa `scipy.optimize.least_squares`, método TRF, límites explícitos, residuos
cuadrados y parámetros normalizados por la amplitud de sus límites. Es una
búsqueda local; converger no significa óptimo global ni parámetros únicos.
No hay selección automática de modelo ni ajuste mediante IA.

`max_evaluations` limita evaluaciones nuevas de residuos, incluidos los
candidatos del Jacobiano por diferencias finitas. Cada evaluación ejecuta todos
los ensayos de ajuste. Las consultas satisfechas por caché no consumen ese
presupuesto. Las simulaciones para línea base, informes y validación quedan
fuera de ese límite; `simulations_count` cuenta todas las llamadas. Por tanto,
el presupuesto no limita segundos ni simulaciones totales. Agotarlo o cancelar
produce un informe con motivo y sin casos ajustados exportables.

La SVD del Jacobiano numérico local informa rango, valores singulares,
condicionamiento y sensibilidad. Depende de límites, pesos, excitación,
observables y tolerancias elegidos. Rango deficiente, sensibilidad débil, mal
condicionamiento o parámetros en límites producen advertencias. **No se calculan
intervalos de confianza ni se demuestra identificabilidad estructural**. Una
SVD favorable tampoco acredita validez fuera del entorno estudiado.

El informe `dynamic-calibration-result/v1` conserva parámetros, procedencia,
versiones del modelo/NumPy/SciPy, métricas iniciales y ajustadas, trayectorias,
auditoría de balances, criterios y advertencias. Separar estos resultados:

| Campo | Interpretación |
|---|---|
| `optimization_converged` | Terminación numérica favorable del optimizador. |
| `usable_parameter_estimate` | Sin diagnósticos desfavorables implementados ni criterios reservados incumplidos. |
| `validation_status: criteria_met` | Todos los errores reservados cumplen los umbrales declarados. |
| `validation_state: synthetic_calibration_only` | Todos los ensayos se declararon sintéticos. |
| `validation_state: unverified_against_plant` | Hay datos aportados por el usuario; no se acredita validez de planta. |

## Demostración y siguiente ensayo físico

La [demostración incluida](../data/calibration_examples/README.md) genera
trayectorias con una solución afín por tramos mediante `scipy.linalg.expm`,
independiente del integrador de `dynamic_tank`. Ajusta dos UA con calentamientos
y reserva un enfriamiento. Añade ruido con semilla fija. Verifica software con
verdad sintética conocida; comparte las hipótesis físicas del modelo y no es
validación experimental.

Para pasar a datos reales:

1. Elegir un tanque y definir uso previsto, carga, fluido, presión absoluta y
   temperatura. Comprobar fase, propiedades, mezcla y circuito frente al alcance.
2. Levantar la ficha física e instrumental del piloto. Medir o justificar estados
   iniciales, caudal/temperatura de servicio, apertura, agitación, alimentación
   y descarga; sincronizar relojes. Las entradas actuales son por escalones:
   justificar y conservar la conversión de registros continuos a esos eventos.
3. Fijar antes de ajustar parámetros, límites, pesos, ensayos reservados y
   criterios de error según instrumentos y decisión de ingeniería. Preservar
   registros originales y documentar todas sus transformaciones.
4. Registrar ensayos repetibles con perturbaciones acordadas con operación y
   suficientes para distinguir los parámetros. Un primer plan puede incluir
   calentamientos a dos condiciones de servicio y enfriamiento reservado;
   amplitudes y duración dependen del equipo y sus límites reales. Medir pared
   y camisa ayuda a separar sus resistencias e inventarios de la respuesta del
   tanque, cuando la instrumentación lo permita.
5. Ajustar solo con calibración. Revisar balances, residuos, sensibilidad y
   estabilidad numérica. Si se usa el ensayo reservado para cambiar el modelo
   o los criterios, reservar nuevas corridas para el siguiente contraste.
6. Aceptar únicamente el uso y rango evaluados. Discrepancias sistemáticas pueden
   exigir retardo de sensor, UA variable, mezcla imperfecta o servicio con
   inventario propio; añadir física apoyada en evidencia.

El siguiente hito experimental es esa campaña instrumentada. Intervalos
paramétricos, diseño óptimo de ensayos y conexión de adquisición son ampliaciones
posteriores; captar datos no sustituye aplicabilidad y validación.

## Referencias primarias

- [SciPy: `least_squares`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.least_squares.html): mínimos cuadrados locales con límites y Jacobiano.
- [SciPy: `expm`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.expm.html): exponencial matricial de la referencia sintética.
- [Repositorio DWSIM](https://github.com/DanWBR/dwsim): referencia de un simulador estacionario y dinámico más amplio. Este hito no ejecuta un benchmark contra DWSIM ni incorpora su código.

La referencia independiente no equivale a contrastar paquetes termodinámicos,
un flowsheet industrial completo ni una instalación real.
