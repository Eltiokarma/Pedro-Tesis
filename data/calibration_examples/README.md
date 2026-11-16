# Demostración sintética de calibración térmica

**Todos los CSV de esta carpeta son datos sintéticos, no mediciones de planta.**
El estudio estima dos conductancias térmicas y contrasta un ensayo reservado.
Consulte el [contrato y metodología](../../docs/CALIBRACION_TRANSITORIA.md) antes
de importar datos propios.

## Archivos y partición

| Archivo | Contenido |
|---|---|
| `study.json` | Parámetros, límites, observables, criterios, fuentes y roles. |
| `cal_hot.json` / `cal_hot.csv` | Primer calentamiento para ajuste. |
| `cal_warm.json` / `cal_warm.csv` | Segundo calentamiento para ajuste. |
| `validation_cooling.json` / `validation_cooling.csv` | Enfriamiento reservado; no participa en objetivo ni Jacobiano. |
| `reference.json` | Valores generadores, método, semilla y ruido sintético. |

Cada ensayo dura 600 s, con 13 tiempos de observación no uniformes y temperaturas
de tanque, pared y camisa. El controlador está deshabilitado, las perturbaciones
son prescritas y no hay alimentación ni descarga.

| Ensayo | Masa inicial | Temperatura inicial | Servicio inicial | Apertura inicial | Cambio |
|---|---:|---:|---:|---:|---|
| `cal_hot` | 500 kg | 298.15 K | 353.15 K | 0.60 | Apertura 0.30 a los 200 s. |
| `cal_warm` | 600 kg | 308.15 K | 343.15 K | 0.40 | Servicio 353.15 K a los 260 s. |
| `validation_cooling` | 550 kg | 328.15 K | 288.15 K | 0.50 | Apertura 0.75 a los 200 s. |

La masa varía manteniendo UA constante por hipótesis. Un equipo real requiere
verificar el efecto de carga y área mojada antes de compartir esos parámetros.

## Referencia independiente

`calibration_example.py` resuelve por tramos constantes el sistema térmico afín
de tanque, pared y camisa mediante
[`scipy.linalg.expm`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.linalg.expm.html).
La hidráulica se calcula de forma algebraica independiente. No se llama al
integrador del tanque ni al estimador para generar las temperaturas. Se
comparten las hipótesis físicas: la independencia es de implementación numérica,
no evidencia experimental.

| Parámetro | Valor generador | Inicial del ajuste | Límites |
|---|---:|---:|---:|
| `wall.ua_tank_W_K` | 800 W/K | 450 W/K | 100–2500 W/K |
| `wall.ua_jacket_W_K` | 1200 W/K | 650 W/K | 100–2500 W/K |

El ruido gaussiano independiente tiene desviación estándar de 0.05 K y semilla
`20261116`; las columnas de incertidumbre declaran 0.05 K. El calibrador no usa
`reference.json` como entrada: contiene la verdad sintética para contrastar la
recuperación del ejemplo.

Las tres temperaturas declaran `scale_K = 0.05`, RMSE reservado máximo de 0.15 K
y error absoluto máximo de 0.30 K. **Son criterios de demostración de software,
no tolerancias industriales ni una especificación instrumental.** El presupuesto
es 100 evaluaciones nuevas de residuos, incluidos candidatos del Jacobiano;
no limita a 100 las llamadas totales al simulador.

## Reproducción

Desde la raíz del repositorio:

```bash
python dynamic_calibration_cli.py data/calibration_examples/study.json --check
python dynamic_calibration_cli.py data/calibration_examples/study.json --out informe_calibracion.json
```

Para exportar además una copia del caso candidato convergido:

```bash
python dynamic_calibration_cli.py data/calibration_examples/study.json --out otro_informe.json --fitted-case tanque_candidato.json --experiment-id cal_hot
```

Para regenerar la demostración en otra carpeta:

```bash
python dynamic_calibration_cli.py --write-example mi_estudio_sintetico
```

Las salidas existentes requieren `--overwrite`; exportar no sustituye entradas.
En Qt: **Simulación → Tanque transitorio… → Calibrar con ensayos. → Abrir
demostración sintética**.

Revisar convergencia, parámetros y límites, diagnóstico local, errores reservados
y balances. `synthetic_calibration_only` se mantiene aunque se satisfagan los
criterios. Este ejemplo no acredita incertidumbre paramétrica, identificabilidad
estructural ni desempeño de una instalación real.
