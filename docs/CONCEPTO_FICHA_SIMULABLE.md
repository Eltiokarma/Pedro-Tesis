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

### Matiz posterior: "¿a ti también te mata ANSYS?"

- Con un agente escribiendo código, **escribir** un solver FEA ya no es la
  barrera. Uno elástico lineal se arma en días, y además se puede envolver
  software libre: gmsh (malla), CalculiX o Code_Aster (sólidos), OpenFOAM (CFD).
- La barrera que queda es la **confianza**: validar contra la realidad, los
  casos borde (contacto, plasticidad, malla mala, turbulencia) y alguien que
  firme. Eso no lo abarata el código rápido.
- Evidencia en este mismo repo: la auditoría del motor
  (`docs/AUDITORIA_MOTOR_2026-11.md`) encontró errores de física en un
  simulador estacionario escrito con agentes. Por ejemplo, la Antoine del CO2
  estaba errada en un factor 100 y la K del flash L-L estaba invertida.
  En FEA, un error así es un recipiente que revienta.
- Porción verificable: geometrías con solución de referencia (cilindro de
  Lamé, fórmulas ASME VIII, benchmarks NAFEMS, WRC 107/537 para boquillas).
  Que el FEA reproduzca esos casos antes de creerle en otros.

### Matiz posterior: equipo comercial existente → bloque del solver

- La idea refinada no es FEA del equipo existente; es su **modelo de
  proceso**: leer el PDF del fabricante y que el equipo aparezca en el
  lienzo con sus corrientes, como una calculadora.
  Caso disparador: un "fermentador centrífugo" cervecero visto por Karma
  (producto exacto aún no identificado).
- Principio: **la física es nuestra, los números son del fabricante**.
  La conservación (masa, energía, estequiometría) la impone el solver
  siempre; el PDF solo fija parámetros (capacidad, tiempo, rendimiento,
  consumo de servicios, envolvente), cada uno con fuente, página y
  estado de certeza.
- Arquitectura: no un bloque Python por equipo, sino una **ficha simulable
  declarativa** (JSON) que compone operaciones que el motor ya tiene
  (reactor + centrífuga + intercambiador…) y mapea los datos del PDF a sus
  parámetros. Sumar un equipo = sumar un archivo, no código.
- Lo que hay hoy en el repo: `data/examples/beer.json` (R-101 fermentador
  agitado), la reacción R007 de fermentación (marcada "⚠ revisar" por
  discrepancia de Hess) y las centrífugas en el catálogo de costos.
- Límite: si la ventaja del equipo nuevo viene de un fenómeno que no se
  descompone en operaciones conocidas, el bloque solo puede repetir lo que
  dice el fabricante, y debe mostrarse así, no como predicción.

## Preguntas abiertas

- ¿Quién paga: el comprador industrial, el fabricante que quiere que su
  equipo sea "simulable" o el diseñador?
- ¿Cabe esto en el alcance de una tesis, o es producto aparte?
- ¿Por qué familia se arrancaría? (Las bombas son el caso mínimo: curva
  H–Q de pocos puntos publicada por casi cualquier fabricante.)
