# Auditoría del motor y de las plantas industriales

Revisión iniciada desde `349b81729fb00400036bc3a989be5e999b8e27c6`, rama
predeterminada `claude/understand-document-improve-g8xoM`.

## Qué se encontró

El estado «ok» anterior no demostraba que una planta respetara sus balances.
Había productos fijados independientemente de la alimentación, exclusiones
demasiado amplias del balance por componente, recirculaciones declaradas
convergidas sin comprobar todos sus estados y equipos con puertos de proceso
y servicio mezclados por el solver.

| Problema comprobado | Corrección y comprobación |
|---|---|
| El vapor se calculaba con `Cp(Tprom)*(T-25)+Hvap(T)`. Su derivada no era Cp. | Integración de Cp con referencia fija por especie y fase; pruebas de derivada, cambio de fase y balance de mezclado. |
| El calor de reacción a T se sumaba a una diferencia entálpica que ya contenía el cambio de Cp de los productos. | Conversión de calor de reacción a la referencia térmica de las corrientes; prueba independiente de Kirchhoff y del residual adiabático. |
| La primera especie de cada reacción se utilizaba para inferir extensiones de reacciones simultáneas. | Resolución conjunta del sistema estequiométrico y comprobación del residual. |
| Flash líquido-líquido con el cociente de actividad invertido. | Relación `K=x_beta/x_alpha` consistente con Rachford-Rice y conservación de cada especie. |
| Flash devolvía el último iterado al agotar las iteraciones. | Fallo explícito al no converger; Wilson es una estimación inicial, no prueba de estabilidad. |
| La presión de vapor del CO2 tenía un factor 100 incorrecto. | Corrección de la constante de Antoine y pruebas contra los puntos triple y crítico. |
| Intercambiadores podían mezclar las composiciones de tubos y carcasa. | Balances independientes por circuito y cierre térmico entre los cuatro puertos. |
| Vapor y agua de enfriamiento tenían caudal fijo o un circuito sin carga térmica. | Dimensionamiento de servicios desde la entalpía real que intercambian; pruebas al variar alimentación. |
| Productos de separación estaban fijados en masa y composición. | Recuperación de cada componente y cálculo del remanente, con validación de especificaciones. |
| Inconsistencias, NaN y recirculaciones no resueltas podían quedar como éxito. | Validación numérica, comprobación de residuos y propagación de errores al estado final. |

Las pruebas nuevas se encuentran en `tests/test_*physics*.py`,
`tests/test_industrial_*audit.py`, `tests/test_reactor_energy_audit.py`,
`tests/test_component_recovery.py` y `tests/test_thermo_physical_invariants.py`.
Los controles usan conservación, estequiometría, respuesta a cambios de carga
y ecuaciones independientes; una comparación contra una cifra congelada no
basta para validar física.

## Planta integrada de metanol (`industrial`)

La alimentación tiene H2/CO de 2.05 mol/mol, con pequeñas cantidades explícitas
de metano y agua. El reactor opera a 525 K y 80 bar. La conversión corresponde
al modelo de equilibrio disponible, no a una garantía de catalizador o cinética.
La elección de una razón cercana a dos es consistente con la base de gas de
síntesis descrita por [Topsoe](https://www.topsoe.com/hubfs/CAMPAIGNS/Process%20-%20Methanol%20101/Proven%20autothermal%20reforming%20technology%20for%20modern%20large-scale%20methanol%20plant.pdf).

Se reemplazó el uso incorrecto de un recuperador de vapor para enfriar el
efluente hasta 40 °C por enfriamiento con agua. El condensado del flash a alta
presión pasa por una válvula y un segundo separador a 1.5 bar antes de la
purificación. Los gases disueltos tienen una salida explícita. La columna
shortcut incluye sus deberes de condensador y rehervidor; E-201 y E-202
acondicionan los productos, sin cobrar un segundo rehervidor ficticio.

El vapor de 30 bar alimenta el precalentador E-102. Su caudal se calcula a
partir del calor requerido y la condensación del servicio. La caldera
empaquetada incluye su tambor: sus productos son vapor y purga líquida, y
su deber se calcula con ambos. El retorno se enfría antes de reducirlo a
presión atmosférica. La circulación de agua de enfriamiento está conectada
a E-103 y rechaza calor en E-304.

## Alcance de las conclusiones

Los ocho casos principales son `hda_full`, `gas_sweet`, `sugar`, `industrial`,
`quimpac`, `hno3`, `talara` y `leche_gloria`. Las bases de proceso específicas
están en [AUDITORIA_PROCESOS_INDUSTRIALES_2026-11.md](AUDITORIA_PROCESOS_INDUSTRIALES_2026-11.md)
y en los documentos de química/refino incorporados con esta revisión.

| Caso | Cambio principal | Límite que permanece |
|---|---|---|
| HDA | Reactor vivo, purga de gas, flash y separación benceno/tolueno; recompresión y reducción de presión explícitas. | Conversión declarada y columna shortcut. |
| Endulzamiento MDEA | Recuperaciones por especie, regeneración, reposición y purga de solvente. | No predice absorción con equilibrio electrolítico. |
| Azúcar | Base de jugo, sólidos y evaporación conservativos; salidas de vapor explícitas. | No constituye una integración térmica rigurosa de múltiples efectos. |
| Metanol integrado | Equilibrio, reciclo, desgasificación y servicios conectados a su demanda térmica. | Entalpía ideal aproximada a alta presión. |
| QUIMPAC / HCl | Electrólisis estequiométrica, consumo eléctrico y manejo real de coproductos. | Eficiencia de corriente y separaciones especificadas. |
| Ácido nítrico | Oxidación, condensación, absorción y producto calculado desde NH3. | Conversiones y recuperaciones especificadas. |
| Talara | Recuperación por cortes, hidrógeno y coproductos explícitos, válvulas y bombeo coherentes. | Assay y rendimientos FCC/FCK supuestos; no certifica calidad comercial. |
| Leche | Recuperación de grasa/sólidos, ramificación de productos, presión y enfriamiento. | No certifica tratamiento microbiológico. |

También se corrigieron los ejemplos con reacciones ficticias o productos
congelados: ácido sulfúrico, urea, LDPE, jabón, calcinación, vidrio, tratamiento
de agua y recuperación de penicilina. El catálogo distingue ahora cal viva de
cemento completo, recuperación de penicilina de fermentación, y filtración de
agua de potabilización. La estequiometría o el cierre de masa por sí solos no
validan cinética, transferencia de masa, esterilización ni calidad de producto.

Documentos de detalle:

- [Termodinámica y propiedades](AUDITORIA_TERMODINAMICA_2026-11-15.md).
- [Cloroálcali y ácido nítrico](AUDITORIA_HNO3_CLORALCALI_2026-11.md).
- [Talara: modelo y límites](TALARA_MODELO_Y_LIMITES.md).

Se contrastó la arquitectura con el código de DWSIM. Véase
[DWSIM_REFERENCIA_AUDITORIA.md](DWSIM_REFERENCIA_AUDITORIA.md) para el commit,
archivos inspeccionados y diferencias. **No se ejecutó DWSIM** y no se presenta
esta revisión como una equivalencia numérica entre simuladores.

El paquete térmico sigue siendo una aproximación de Cp integrado: no incluye
entalpías residuales de alta presión ni exceso de mezcla electrolítica.
Las recuperaciones de aminas y los rendimientos de pseudocomponentes son
especificaciones declaradas; el programa no los predice a partir de platos,
catalizador o composición de un crudo real. Los ejemplos alimentarios no
certifican letalidad microbiológica. Los resultados económicos heredados no
son una validación física ni una evaluación financiera actualizada.

## Reproducir la validación

```console
python -X utf8 -m pytest -q
python -X utf8 gate_physical_examples.py --json outputs/physical_examples_audit.json
python -X utf8 gate_eos.py
python -X utf8 gate_eos_flash.py
python -X utf8 gate_component_balance.py
python -X utf8 gate_examples.py --registry
python -X utf8 simulate_cli.py data/examples/industrial.json --out industrial.json
```

En Windows se usa `-X utf8` porque algunos tests históricos abren fuentes UTF-8
sin declarar codificación. Los tests opcionales del predictor requieren sus
dependencias adicionales. Las cifras de regresión se deben regenerar solo
tras comprobar las invariantes físicas cuando cambien deliberadamente las
bases del modelo; no se deben conservar resultados antiguos incorrectos.

## Compresores y expansores: cierre energético

El dimensionamiento, la propagación hidráulica y la temperatura de descarga
utilizan ahora el mismo cálculo. La masa molecular de una mezcla expresada
en fracciones másicas es `M = 1/sum(w_i/M_i)`. El estado isentrópico satisface
`integral(Cp(T)/T dT) = R_m ln(P_salida/P_entrada)`; la eficiencia isentrópica
actúa sobre la diferencia de entalpía, y la temperatura real se obtiene
invirtiendo la misma función de entalpía que utiliza el balance de corrientes.

La potencia eléctrica se distingue del trabajo entregado al gas. El cierre
del equipo completo es `H_salida-H_entrada = W_electrica-Q_intercool-Q_perdidas`.
Los campos calculados `Q_intercool_kW` y `Q_mechanical_loss_kW` representan
calor rechazado, y se incluyen en el diagnóstico. Se conserva la convención
de tren con etapas internas e interenfriamiento a la temperatura de entrada
cuando la relación total de compresión supera 4; esas etapas no equivalen a
un único compresor adiabático. La eficiencia mecánica asumida es 0,95.

El modelo general es de gas ideal con Cp variable: **no incluye entalpía ni
entropía residual de presión**, condensación de mezclas durante expansión ni
un mapa real de compresor. A alta presión, especialmente en polimerización de LDPE, el cierre
de la primera ley no constituye una validación de la potencia industrial;
se requiere un paquete de propiedades reales y datos del fabricante.

Las regresiones cubren vapor de agua, etileno, hidrógeno y nitrógeno en una
y varias etapas, un expansor y una mezcla H2/N2. Referencia de ecuaciones:
[NASA, Compressor Thermodynamics](https://www.grc.nasa.gov/www/k-12/BGP/compth.html).

Las turbinas de agua pura utilizan una ruta específica que admite vapor
húmedo: calcula la saturación, el salto de entropía `s_fg=h_fg/T_sat` y la
calidad másica de descarga con la misma referencia de entalpía. Rechaza una
entrada declarada como vapor por debajo de su temperatura de saturación.
Es un modelo aproximado con la curva de Antoine disponible, no tablas IAPWS.
Los ciclos Rankine y nuclear verifican descarga saturada bifásica y primera
ley. El secundario nuclear se especificó a 60 bar y 280 °C; ambos ciclos
utilizan el tipo de equipo turbina de vapor.

En doce ejemplos se liberó la temperatura de descarga de máquinas que estaba
fijada independientemente del trabajo. La máquina calcula esa temperatura;
los enfriadores posteriores conservan sus temperaturas de proceso declaradas.

## Reciclos y servicios térmicos

La descomposición de ciclos considera por separado los circuitos de cada
intercambiador y todos los componentes del bosque de conexiones. La selección
estructural conserva la identidad `E−V+C` y devuelve ciclos cerrados.

Para resolver caudales, las utilidades automáticas y los pares de servicio de
HX con temperaturas especificadas se excluyen del vector de reciclo de
proceso: sus caudales se calculan por demanda térmica. Siguen presentes en el
diagrama y en los balances finales. La demanda de vapor y agua de enfriamiento
se actualiza durante las iteraciones de masa y temperatura; así se evita
tratar una circulación de servicio sin alimentación neta como una incógnita
independiente de masa. Los reciclos de proceso mantienen sus criterios de
convergencia y su auditoría de conservación.

## Criterios y calidad de las propiedades

Los umbrales generales heredados del motor son 0,5% para masa y 5% para
energía; las comprobaciones específicas de reactores, máquinas, servicios y
reciclos son adicionales. Las nuevas pruebas industriales comprueban residuos
más estrictos, conservación por especie y respuesta a cambios de alimentación.
El informe JSON incluye el máximo residuo relativo de masa por equipo para
que el estado «aprobado» no oculte la magnitud de ese residuo.

El barrido existente `gate_eos.py` compara PR y Antoine para 98 compuestos:
mediana de desviación 11,92%, percentil 90 de 63,76% y máximo de 159,38%.
Su criterio general es una mediana menor de 25%, junto con anclas específicas.
**Aprobar ese gate no demuestra precisión industrial para cada sustancia.**
Es una comparación entre correlaciones, no contra mediciones de planta;
los casos polares/asociativos y las propiedades originales sin procedencia
verificada requieren parámetros y datos experimentales adicionales.

La cobertura del catálogo deja explícito que falta un ejemplo dedicado al
compresor axial: los casos que antes aparentaban cubrirlo eran turbinas de
vapor mal identificadas. Los internos de columna siguen representados dentro
de sus torres, en lugar de ser equipos separados.

## Resultado del catálogo completo

La ejecución final de `gate_physical_examples.py` aprobó **64 de 64** ejemplos:
54 con estado `ok` y 10 con estado `warning`, sin errores de cálculo.
El mayor residuo relativo de masa por equipo con entrada y salida fue
`2,6697e-7`, equivalente a **0,0000267%**, en el caso integrado de metanol.

Las advertencias se conservan: incluyen rendimientos especificados, propiedades
aproximadas, diagnósticos térmicos y el caso de centrifugación sin entalpías
resolubles. En ácido nítrico se declara arrastre residual de NO2 en una
corriente líquida; esa asignación se informa como alcance del modelo y no
pretende ser un flash de equilibrio. El estado aprobado significa que el cálculo cumple los controles
implementados, con esas limitaciones visibles.

El detalle reproducible está en
[physical_examples_audit.json](../outputs/physical_examples_audit.json).

## Consistencia económica entre API y exportación

El control final encontró siete discrepancias: la API respetaba el factor
variable de manufactura `econ_overrides.com_gamma` del proyecto, pero el
reporte exportado usaba siempre el valor del perfil económico. Se unificó
su aplicación al caso base, sensibilidad y estado de resultados, y las
etiquetas muestran los coeficientes efectivos. Sin modificar tolerancias ni
referencias del gate, **64/64** ejemplos coinciden en NPV e IRR entre API y
ruta GUI/Save. Las pruebas financieras enfocadas aprobaron **14/14**,
incluida la coherencia del flujo de caja del libro exportado.
