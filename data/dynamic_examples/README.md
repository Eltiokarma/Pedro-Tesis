# Casos sintéticos del piloto transitorio

Estos parámetros no proceden de un fabricante, laboratorio o planta. Sirven para
ejecutar y verificar el modelo, y deben sustituirse por información contrastable
antes de estudiar un equipo real.

| Caso | Comportamiento |
|---|---|
| `heating_500kg.json` | Calentamiento de 500 kg, pared y camisa con inercia térmica, control PI. |
| `cooling_feed_step.json` | Enfriamiento, cambio de caudal de proceso a 1800 s y de consigna a 2400 s. |
| `fill_drain_tracer.json` | Masa variable, cambios de alimentación/descarga y balance de trazador pasivo. |
| `measurement_template.csv` | Solo encabezados SI; debe completarse con observaciones identificadas. |

Ejecutar desde la raíz:

```bash
python dynamic_cli.py data/dynamic_examples/heating_500kg.json --out corrida.json --csv trayectoria.csv
python gate_dynamic_pilot.py --out outputs/dynamic_pilot_gate.json
```

Ver [formulación, límites y protocolo de datos](../../docs/PILOTO_TRANSITORIO.md).
Los criterios del gate son de consistencia y precisión **numéricas**, no de
error admitido frente a una instalación física.
