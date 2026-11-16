# Casos transitorios teóricos y referencias publicadas

Estos archivos verifican modelos y su integración numérica. No contienen registros de planta ni acreditan validación experimental. `data_kind=synthetic` es la clasificación compatible con el formato de casos; el campo `provenance` distingue una reproducción numérica publicada de una adaptación o caso propio.

| Archivo | Procedencia | Objetivo |
|---|---|---|
| `coupled_disturbances.json` | Circuito propio inspirado en la topología de Modelica HeatingSystem; parámetros y perturbaciones propios | Cuatro inventarios térmicos conectados, corte de potencia, parada y reinicio de bomba |
| `energyplus_adiabatic.json` | Parámetros de una prueba publicada de EnergyPlus v24.2.0 | Depósito desacoplado, 1000 W, solución lineal exacta ejecutada por el motor v3 |
| `insufficient_power.json` | Extensión teórica propia de un balance de depósito | Demanda superior a capacidad, aproximación a equilibrio sin alcanzar una consigna imposible |
| `coupled_capacity_limit.json` | Circuito teórico propio con PI activo | Válvula totalmente abierta, calentador saturado y temperatura de proceso por debajo de su consigna |
| `energyplus_reference.json` | Valores y tolerancias de la prueba publicada, con versión y SHA | Descarga fría con pérdidas: comprobación del componente de depósito con retorno prescrito |

El caso de retorno frío utiliza el mismo balance de componente que el motor, integrado con `solve_ivp`; **no representa el circuito cerrado completo**, porque el retorno se impone externamente para reproducir exactamente la condición de la referencia. El caso adiabático sí recorre el motor completo con los demás inventarios desacoplados.

```console
python gate_dynamic_thermal_loop.py --out outputs/dynamic_thermal_loop_gate.json --overwrite
python dynamic_cli.py --help
```

`python thermal_loop_examples.py` reproduce estos JSON a partir de parámetros explícitos. El gate lee los archivos existentes y falla si faltan; no los regenera silenciosamente. No se ejecuta EnergyPlus ni Modelica y no se presentan sus curvas como si se hubieran comparado entre simuladores.

Fuentes y límites: [guía del circuito](../../docs/CIRCUITO_TERMICO_TRANSITORIO.md).
