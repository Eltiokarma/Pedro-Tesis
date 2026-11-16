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

**Corrección de Karma (sobre el punto anterior):** no quiere armar el
equipo con piezas existentes (fermentador + centrífuga + chaqueta). Quiere
**un bloque que sea el equipo**, con sus propias corrientes (entrada,
salida, purga/waste, servicios) y sus propios parámetros, tal como los
nombra el fabricante.

- Lectura: una caja negra que conserva. Por dentro no hay piezas, hay
  relaciones declaradas: reacciones con conversión, destino de cada
  componente por cada salida, consumos específicos (kWh/hL, etc.) y
  envolvente. El duty sale del balance de energía, no se copia del PDF;
  si el PDF trae uno, sirve para contrastarlo.
- Semilla existente: `component_recovery.py` ya resuelve un bloque con
  salidas de nombre libre declaradas por bloque (`get_block_ports`), donde
  toda especie tiene destino y lo no especificado va a la salida por
  defecto. Falta: entradas y servicios con nombre libre, reacción dentro
  del mismo bloque, procedencia por parámetro y símbolo propio.
- Precio de la caja negra: vale alrededor del punto de operación que
  publica el fabricante. No extrapola (si cambias T, no responde) salvo que
  se declare una sensibilidad. Sirve como calculadora de balances, no para
  optimizar el equipo.

### Matiz posterior: cómo "activar el modo calculado"

Pedido de Karma: que el bloque no sea siempre caja negra; un interruptor
caja negra ↔ calculado.

- El modo calculado **se gana con datos**; no es un interruptor libre. El
  botón existe, pero solo se habilita cuando hay con qué calcular, y si no,
  dice qué falta.
- Mismo bloque, mismos puertos. Lo que cambia es cómo se resuelve cada
  relación por dentro. Escalera por relación (no global):
  0. **Declarado**: el número del PDF tal cual (caja negra).
  1. **Escalado**: una ley de escala anclada en el punto del fabricante
     (proporcional al caudal, Q/Σ en centrífugas, leyes de afinidad).
     Basta con un punto.
  2. **Calculado**: una ley física de la familia (cinética Monod o
     Luedeking-Piret con T, eficiencia por Σ, UA·ΔTlm), con sus parámetros
     ajustados a los puntos disponibles. Requiere tantos puntos
     independientes como parámetros, más al menos uno reservado para validar.
  La interfaz resume: caja negra / mixto / calculado.
- Condiciones para habilitar un nivel:
  1. Existe plantilla física para esa familia de equipo.
  2. Grados de libertad de la calibración ≥ 0, con reserva de validación.
  3. Prueba de consistencia: en el punto del fabricante, el modelo calculado
     reproduce la caja negra dentro de una tolerancia. Si no, no se activa
     y se informa la diferencia.
  4. Fuera del rango calibrado se calcula igual, pero queda marcado como
     "extrapolado" (como `operating_point_valid` en `dynamic_hydraulics`).
- Semillas en el repo: `dynamic_calibration.py` (mínimos cuadrados acotados
  con ensayos reservados), `dynamic_measurements.py` (importar
  observaciones), `dof_audit.py` (grados de libertad antes de resolver).
- Realidad: un PDF casi siempre trae un solo punto, así que alcanza para el
  nivel 1. El nivel 2 requiere datos que el fabricante no publica: los
  lotes del propio cliente. Esa es la puerta de negocio (la planta sube sus
  datos y su equipo pasa a "calculado").

## Preguntas abiertas

- ¿Quién paga: el comprador industrial, el fabricante que quiere que su
  equipo sea "simulable" o el diseñador?
- ¿Cabe esto en el alcance de una tesis, o es producto aparte?
- ¿Por qué familia se arrancaría? (Las bombas son el caso mínimo: curva
  H–Q de pocos puntos publicada por casi cualquier fabricante.)
