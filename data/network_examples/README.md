# Casos de redes transitorias

Todos producen datos teóricos/sintéticos. No se han usado mediciones de planta.

| Archivo | Topología | Referencia |
|---|---|---|
| `cascade.json` | Tres tanques en serie, 100 kg y 1 kg/s por etapa | Respuesta analítica de tres mezcladores con la misma residencia. |
| `split_merge.json` | División 60/40 y mezcla en un cuarto inventario | Fórmulas de etapas con residencia de 100 s. |
| `recirculation.json` | Dos depósitos, contacto térmico, parada y reinicio | Media conservada y diferencia exponencial, con relojes distintos para calor y trazador. |
| `energyplus_mixed_tank.json` | Un depósito con entrada, salida y pérdidas al ambiente | Parámetros y referencia integral publicados en EnergyPlus v24.2.0; no se ejecutó EnergyPlus. |

```console
python dynamic_network_cli.py data/network_examples/split_merge.json --check
python dynamic_network_cli.py data/network_examples/recirculation.json --out corrida.json --csv curva.csv
python gate_dynamic_network.py --out outputs/dynamic_network_gate.json --overwrite
```

Cada JSON puede editarse; las fórmulas independientes del gate corresponden a los
parámetros originales, no a cualquier variante. Caudales en kg/s, masas en kg,
energías en J, potencia en W, UA en W/K, tiempo en s y temperatura en K.
Si se modifican parámetros del caso publicado, debe cambiarse su clasificación a
`documented_adaptation` y explicar las diferencias en las notas de procedencia.

[Modelo, límites, ecuaciones y criterios](../../docs/REDES_TRANSITORIAS.md).

Los casos `coupled_recirculation.json` y `coupled_feed.json` usan v2: conectan
dos tanques y un intercambiador con cuatro puertos. La recirculación incluye
parada a 40 s y reinicio a 70 s. Son casos sintéticos propios; no contienen
datos de planta. Se ejecutan desde el editor o con `--example` usando esos nombres
sin la extensión. [Conexiones y verificación](../../docs/REDES_CON_INTERCAMBIADOR.md).
