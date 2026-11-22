# Casos del intercambiador distribuido

Cuatro casos autocontenidos `dynamic-heat-exchanger/v1`, regenerables mediante
`dynamic_heat_exchanger_examples.example_cases()`. Usan unidades SI y parámetros
totales del equipo; el solver divide los inventarios y áreas entre las celdas.

- `counter_current.json`: dos circuitos a contracorriente con pared finita.
- `co_current.json`: misma geometría, con ambos flujos en el mismo sentido.
- `transport.json`: películas nulas, para verificar el retardo de residencia.
- `msl_geometry_adaptation.json`: geometría y pared de Modelica Standard Library
  4.1.0 con propiedades, inicialización y perturbaciones simplificadas propias.

Todos producen datos sintéticos. La adaptación no reproduce el ejemplo completo
de Modelica y no contiene mediciones. Las diferencias viajan en la procedencia
del JSON y también en el CSV de resultados.

```bash
python dynamic_heat_exchanger_cli.py data/heat_exchanger_examples/msl_geometry_adaptation.json --out adapted.json
```

Ecuaciones, orientación de perfiles, referencias, límites y criterios numéricos
en [la documentación del intercambiador](../../docs/INTERCAMBIADOR_TRANSITORIO.md).
