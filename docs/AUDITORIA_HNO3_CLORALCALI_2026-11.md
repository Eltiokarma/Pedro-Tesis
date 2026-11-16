# Auditoría: ácido nítrico y cloro-álcali

## Qué se corrigió

Los ejemplos declaraban reacciones simbólicas que no estaban en la base de
reacciones y fijaban los productos independientemente de la alimentación.
Por ejemplo, la celda entregaba 602 t/a de Cl2 y 1 073 t/a de NaOH puro:
esa relación no satisface `2 NaCl + 2 H2O -> 2 NaOH + Cl2 + H2`.
Un cambio del caudal de alimentación no recalculaba honestamente la química.

Ahora los productos proceden de reactores estequiométricos y separadores
de recuperación por componente. Los separadores conservan cada especie;
sus recuperaciones son especificaciones de diseño declaradas, no un cálculo
de equilibrio electrolítico ni un modelo cinético de absorción.

## HNO3

El tren incluye vaporización de NH3, compresión de aire, conversión catalítica,
recuperación de calor, condensación de agua, compresión de NOx, oxidación de
NO, absorción oxidativa, separación de gas/líquido, letdown del ácido y
blanqueo. Se añadieron explícitamente la reacción secundaria a N2, el reactor
que representa la absorción neta y la válvula de reducción de presión del
producto. El condensado a baja presión llega al absorbedor mediante bomba.

Base de diseño, no valores medidos de una planta:

- NH3: 1 000 t/a; aire primario: 14 000 t/a; aire secundario: 3 218,7 t/a.
- Selectividad de NH3 hacia NO: 96%; el resto se transforma en N2.
- Conversión de NO a NO2: 99,5%; absorción oxidativa neta: 99,9%.
- La absorción se representa mediante `4 NO2 + O2 + 2 H2O -> 4 HNO3`;
  esta reacción neta suma la absorción y reoxidación del NO formado.
- Oxidación a 4,5 bar y absorción a 11 bar, con el salto en compresores/bombas.
- El producto contiene aproximadamente 58% de HNO3; su concentración se
  calcula con los caudales de entrada y las recuperaciones, no se fija a 60%.
- La pequeña corriente de NO2 de blanqueo se conserva como residuo. El
  tratamiento final de emisiones no se dimensiona en este ejemplo.

Las tres etapas y la formación de ácido débil entre 55–65% son consistentes
con [EPA AP-42 8.8](https://www.epa.gov/sites/default/files/2020-09/documents/8.8_nitric_acid.pdf).
La selectividad elegida de 96% está dentro del intervalo 93–98% descrito allí.
Las recuperaciones individuales y los valores de conversión posteriores
son supuestos de diseño: no proceden de datos de transferencia de masa.

## Cloro-álcali

La base es NaCl purificado. No se fabrican precipitados de Ca/Mg si la
alimentación no contiene Ca/Mg; se retiraron las corrientes y bombas de
reactivos innecesarios de esa base. El equipo de acondicionamiento permanece
como paso de una alimentación idealizada, con lodo nulo.

- Alimentación fresca: 1 000 t/a de NaCl y 1 800 t/a de agua.
- Conversión por pasada: 30%; el NaCl no convertido vuelve con el anolito.
- Los tres coproductos siguen la estequiometría: aproximadamente 1,128 t de
  NaOH puro y 0,0284 t de H2 por cada tonelada de Cl2.
- El reparto de agua de la membrana es una especificación de diseño que
  produce un catolito cercano al 32%; no es un modelo de transporte iónico.
- Trabajo eléctrico calculado por Faraday con 3,2 V y eficiencia de corriente
  de 96%: alrededor de 2,52 MWh/t de Cl2. El trabajo entra por una corriente
  de energía explícita y el balance calcula la refrigeración de la celda.
- Se añadieron válvulas de letdown en el anolito y el catolito, y un
  enfriador final de NaOH. El compresor de Cl2 aumenta 1,5 -> 7 bar.
- La concentración de NaOH se aproxima al 50% mediante evaporación. Se usa
  el punto de diseño de 143 °C a 1,013 bar para el licor concentrado; una
  solución de NaOH al 50% no hierve a 100 °C a presión atmosférica.

El principio de producción simultánea por electrólisis está descrito por
[Euro Chlor](https://eurochlor.org/products/chlorine-cl/). El punto de ebullición
de NaOH al 50% proviene de [Covestro, ficha del producto](https://solutions.covestro.com/en/products/caustic/caustic-soda-50_000000000005452627).
La tensión, eficiencia y recuperaciones son especificaciones del ejemplo.
La elevación del punto de ebullición se fija para este punto de diseño; no
se implementó una correlación de actividad de NaOH para otras concentraciones.

## Validación y alcance

`tests/test_industrial_chemistry_audit.py` verifica balances reportados por el
solver, producción de HNO3 por estequiometría, relaciones de coproductos de
electrólisis, trabajo de Faraday, aumento de producción cuando las
alimentaciones suben 50%, estabilidad al resolver una segunda vez y la
secuencia térmica y de presión de los nuevos equipos.

`tests/test_component_recovery.py` verifica conservación por especie,
respuesta lineal al caudal, limpieza de salidas cuando el feed cae a cero,
validación de fracciones y rechazo de composiciones incompletas.

Los balances ahora son dinámicos respecto de las entradas. Esto no equivale
a validar una planta real: faltan modelos de electrolitos, actividades,
cinética y transferencia de masa, validación de parámetros con datos de
operación, pérdidas térmicas y diseño detallado de emisiones. Las dimensiones
comerciales y los resultados económicos heredados requieren recalibración
antes de emplearlos para una inversión o ingeniería de detalle.
