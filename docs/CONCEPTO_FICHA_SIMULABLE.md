# CONCEPTO — La ficha técnica como objeto simulable (y el puente al 3D)

> **Estado: concepto guardado.** No es visión, no es plan, no es backlog.
> Es una idea registrada para pensarla después. Nada aquí obliga a
> implementar nada. Fecha de registro: 2026-11-16.

## La idea, en palabras de Karma

1. Una industria se interesa en un equipo: mira la ficha técnica, la hoja
   de seguridad y el resto de la información. Lo que le gustaría es **subir
   esa ficha a una simulación de su proceso** y ver si el equipo encaja.
2. Al revés: los diseñadores quieren pasar rápido de un **diseño
   conceptual 3D a una ficha técnica**.
3. Ese hueco (diseño 3D, simulación, resistencia de materiales, terreno de
   HYSYS y ANSYS) podría caber en este software.

## Lectura técnica (primera pasada)

### El equipo tiene tres caras que hoy viven en herramientas distintas

| Cara | Qué contiene | Dónde vive hoy |
|---|---|---|
| Proceso | duty, corrientes, T/P, η, punto de operación | simulador (HYSYS, DWSIM, este repo) |
| Comercial | marca, modelo, curvas, envolvente, precio | PDF del fabricante |
| Mecánica/geométrica | dimensiones, espesores, material, peso, 3D | CAD/FEA (SolidWorks, ANSYS), Excel |

El hueco real no está dentro de ninguna cara: está en el **traspaso** de una
a otra, que hoy se hace a mano, retipeando.

### Dirección 1: ficha del fabricante → simulación (encaja)

- Hoy el repo hace **modo selección** (`datasheet.py`): verifica
  `S_requerido ≤ S_modelo` contra `data/equipos_comerciales.json`.
  Es un sí o un no.
- Lo que pide la idea es **modo rating**: el equipo es fijo (el del
  fabricante) y el simulador calcula cómo se comporta el proceso con *ese*
  equipo. Ejemplo mínimo: la curva H–Q de una bomba comercial cortada con la
  curva del sistema. La semilla existe: `dynamic_hydraulics.solve_circuit`
  ya intersecta una curva de bomba con el circuito, pero la curva es
  paramétrica y el módulo dice explícitamente que *no* es una certificación
  del fabricante.
- La parte difícil es ingerir PDFs de fabricante, que no traen un formato
  estándar, y sobre todo **verificar** lo extraído. El repo ya tiene esa
  cultura (estados `escalar`, `envolvente_modelo`, `debil_familia`; la regla
  de "verificado contra PDF oficial").
- La hoja de seguridad (SDS) es de la **sustancia**, no del equipo: se
  conecta a `thermo_db`/componentes como restricciones (punto de
  inflamación, incompatibilidades, límites), no a la ficha del equipo.
- Analogía de negocio: los **objetos BIM** en arquitectura, donde el
  fabricante publica su producto en un formato que el proyectista mete
  directo al modelo. Aquí sería el fabricante publicando una "ficha
  simulable".

### Dirección 2: 3D → ficha (hay que partirla en dos)

- **Geometría paramétrica → ficha por correlaciones**: encaja.
  Ejemplos: casco y tubos (D, nº de tubos, L) → área, U, ΔP; recipiente
  (D, L, cabezales) → volumen, espesor ASME VIII Div. 1 por fórmula, peso.
  Esto es terreno de HTRI/Aspen EDR y de las normas: son fórmulas y
  correlaciones, no la resolución de un campo.
  El repo ya lista esos campos como pendientes
  (`datasheet._PENDIENTE_DETALLE`: "espesor de pared (ASME VIII)",
  "tipo TEMA", "bocas y soportes").
- **Geometría libre → esfuerzos/flujo (FEA/CFD)**: no encaja. Es ANSYS:
  décadas de trabajo y miles de ingenieros. Competir ahí no tiene sentido.
- La dirección más natural es la inversa: **proceso → diseño mecánico por
  norma → 3D paramétrico exportable** (STEP/glTF). El 3D sale de la ficha,
  no al revés.

### Referencias para revisar antes de soñar

- DEXPI (intercambio de datos de P&ID), CFIHOS (IOGP, especificación de
  entrega de información de instalaciones), ISO 15926. Ya existen intentos
  de "formato de intercambio de equipo". Revisar qué cubren y qué no.

## Preguntas abiertas

- ¿Quién paga: el comprador industrial, el fabricante que quiere que su
  equipo sea "simulable" o el diseñador?
- ¿Cabe esto en el alcance de una tesis, o es producto aparte?
- ¿Por qué familia se arrancaría? (Las bombas son el caso mínimo: curva
  H–Q de pocos puntos publicada por casi cualquier fabricante.)
