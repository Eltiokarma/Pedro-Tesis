# Bases y límites de los ejemplos industriales corregidos

Esta revisión sustituye tablas de corrientes congeladas por balances que
responden a la alimentación. La verificación automática demuestra conservación
y coherencia interna; **no equivale a validación con datos de una planta real**.
Los nombres comerciales de los ejemplos identifican una inspiración didáctica,
no un modelo certificado de dichas instalaciones.

## Endulzamiento con MDEA (`gas_sweet`)

- El absorbedor, el desgasificador y la regeneración usan recuperaciones por
  componente declaradas. Se conserva cada especie, incluida la amina. No se
  presenta este modelo como equilibrio electrolítico ni como predicción de
  remoción por cinética o número de platos.
- El gas dulce deja de ser un producto de caudal fijo. Las recuperaciones
  hacia él son 99.9% de metano/etano, 2% del CO2 y 0.01% del H2S alimentados.
  Son especificaciones de desempeño; cambiar presión, concentración o carga
  de ácido no recalibra automáticamente estos factores.
- Hay válvulas explícitas entre absorción (50 bar), desgasificación (5 bar) y
  regeneración (2 bar). El gas ácido y el gas de desgasificación salen a sus
  propias condiciones de batería: ya no se mezclan ficticiamente a presiones
  incompatibles.
- Una circulación de 2.5 millones t/a de solvente es una especificación de
  diseño. El makeup de 2,000 t/a tiene una purga equivalente. El caso antiguo
  introducía solvente sin una salida estacionaria correspondiente.
- El intercambiador rica/pobre conserva separadamente los componentes de
  tubos y carcasa. Tres temperaturas especificadas y calor externo cero
  determinan la cuarta; el calor recuperado no se cobra como una utilidad.
- Quedan fuera: especiación MDEA/H2S/CO2, calor de absorción/desorción
  electrolítico, espuma, corrosión y diseño de transferencia de masa. Por ello,
  las cargas térmicas calculadas son aproximaciones con el paquete disponible,
  no deberes garantizados de un regenerador comercial.

Referencia primaria: Emerson, *Rich Amine Letdown*, describe el absorbedor,
la válvula de reducción y el tanque flash:
https://documentation.emersonprocess.com/intradoc-cgi/groups/publicreadonly/documents/webpage/ad123_gtp.hcsp

## Azúcar (`sugar`)

- La alimentación de 680,000 t/a es jugo, **no caña entera**. No se inventan
  bagazo, molienda o electricidad de cogeneración que no tienen balance en el
  alcance. La impureza suspendida se representa como `limestone` y entra con
  el jugo; el clarificador ya no genera `atmospheric_residue` desde agua y
  azúcar.
- El clarificador tiene recuperaciones especificadas de impureza y arrastre
  de agua/azúcares. En la base nominal produce 20,000 t/a de cachaza mediante
  conservación por especie, y responde proporcionalmente al cambio de feed.
- Los cuatro evaporadores y el tacho final calculan concentrado y vapor de
  agua a partir de sus factores de concentración. Las temperaturas de líquido
  y vapor de cada etapa coinciden. Las presiones corresponden aproximadamente
  a la saturación de agua a 110, 95, 80, 65 y 65 °C.
- Las salidas de vapor son puertos a condensación/recuperación fuera de la
  batería. No se unen vapores a distintas presiones en un único tanque. Este
  caso conserva los balances de una estación de concentración; todavía no
  resuelve el acoplamiento térmico de un múltiple efecto real ni su economía
  de vapor. No se debe interpretar cada carga como vapor vivo independiente
  cuando se diseñe esa recuperación.
- La captura de sacarosa cristalina es un rendimiento declarado de 83% y
  arrastre de fase no sólida de 3% (agua y glucosa, no 3% de agua pura).
  No se predice sobresaturación, crecimiento de cristal
  ni elevación ebulloscópica. La fase de secado mantiene su balance de agua.

Referencia primaria: US EPA, AP-42 9.10.1.1, *Sugarcane Processing*, describe
clarificación, evaporación, tachos al vacío, cristalización y centrifugación:
https://www.epa.gov/sites/default/files/2020-10/documents/c9s10-1a.pdf

## Planta láctea integrada (`leche_gloria`)

- La centrífuga entrega una corriente de crema y una de leche descremada,
  seguidas de divisores para las diferentes líneas. Ya no tiene cuatro
  productos con caudales y composiciones incompatibles fijados por separado.
- La recuperación de grasa se especifica en 99%; la crema queda a 40% de
  grasa y el suero acompaña proporcionalmente a los demás componentes. La
  recombinación entrega aproximadamente 3% de grasa en leche fluida.
- El batido recupera 98.8% de la grasa de la crema hacia mantequilla con 82%
  de grasa. El suero de mantequilla se obtiene por diferencia de **cada
  componente**, sin crear proteína o destruir lactosa.
- Los evaporadores operan a 55 y 50 °C bajo vacío. Los sólidos se conservan
  y el concentrado final llega a 26% de sólidos por balance, sin fijar la
  producción independientemente de la leche alimentada.
- Se añadió reducción explícita de presión tras el homogeneizador y una
  bomba desde el vacío hacia la línea de tratamiento térmico del concentrado.
  El calentamiento a 140 °C y enfriamiento posterior hacen visible la demanda
  energética de un proceso UHT; la presión de 4 bar evita hervir agua a esa
  temperatura. Este balance estacionario **no valida letalidad microbiológica,
  tiempo de retención ni llenado aséptico**.
- Los vapores de cada efecto salen a condensación a su propia presión. No se
  modela la integración de vapor entre efectos ni las propiedades reológicas
  de leche concentrada.

Referencias primarias del fabricante Tetra Pak:

- Separación y estandarización:
  https://dairyprocessinghandbook.tetrapak.com/chapter/centrifugal-separators-and-milk-standardization
- Mantequilla:
  https://dairyprocessinghandbook.tetrapak.com/chapter/butter
- Leche condensada/evaporada y tratamiento térmico:
  https://dairyprocessinghandbook.tetrapak.com/chapter/condensed-milk
- Evaporadores:
  https://dairyprocessinghandbook.tetrapak.com/chapter/evaporators

## HDA completo (`hda_full`)

- La conversión por paso de tolueno se declara en 65% para la reacción
  `toluene + hydrogen -> benzene + methane`. Las salidas responden al reactivo
  limitante y a los reciclos; no permanecen pegadas a la tabla de diseño.
- El condensador/separador usa flash a 45 °C y 28 bar. Se conserva un margen
  de presión hacia compresión y reactor, con compresión hasta 30 bar.
- La purga de gases está en un divisor después del compresor, con 15% de
  purga. Ya no se trata al compresor como dos salidas independientes.
- La separación de gases ligeros tiene recuperaciones explícitas. La columna
  benceno/tolueno usa el método shortcut Fenske–Underwood–Gilliland, con
  objetivos de composición de 99.5% y 0.5% de benceno. No es una columna
  rigurosa MESH. Hay una válvula antes de la estabilización de baja presión y
  recuperación de calor con una temperatura terminal calculada.
- El modelo solo contiene la reacción principal: no produce difenilo. La
  antigua salida de «pesados», que contenía tolueno puro, se identifica como
  purga de tolueno y se usa un divisor; no se afirma una separación de un
  compuesto que nunca se formó. Añadir difenilo requiere una reacción lateral
  y propiedades/validación adicionales.
- Quedan fuera cinética, selectividad lateral, caída de presión calculada
  desde geometría y validación de resultados frente a datos de operación.

Referencias docentes primarias: NPTEL (IIT/IISc), proceso HDA:
https://archive.nptel.ac.in/content/storage2/courses/103103029/module3/lec21/3.html
y Universidad de Edimburgo, caso HDA y necesidad de purga de metano:
https://www.homepages.ed.ac.uk/jwp/control06/controlcourse/restricted/course/fourth/course/casestudy/example2-HDA1.html

## Verificación automatizada

`tests/test_industrial_process_audit.py` comprueba arranque, valores finitos,
cierre de masa global, convergencia de reciclos y respuesta de productos a
una planta escalada 20%. Añade comprobaciones específicas de grasa, sólidos,
purga de amina, presiones de evaporación y ausencia de residuos petrolíferos
inventados en el jugo. No se usan costos o ingresos antiguos como criterio
de exactitud física.

## Casos adicionales que dependían de reacciones inexistentes

### Vidrio sodocálcico (`glass`)

Se elimina `R_FUSION_GLASS`, que no existía en la base de reacciones. La
sílice se retiene en el pseudocomponente vidrio y cada mol de CaCO3/Na2CO3
alimentado libera un mol de CO2, reteniendo el resto de masa como óxido en
el vidrio. Para 720 t/a de sílice y 140 t/a de cada carbonato, resultan
119.689 t/a de CO2 y 880.311 t/a de vidrio. El caudal de CO2 ya no está
fijado a 120 t/a independientemente de la alimentación.

Es un balance de carga seca con conversión completa especificada. No predice
la red vítrea, conversión cinética ni composición por fases. La demanda
adicional de fusión/reacción de 2,200 kJ/kg conserva el parámetro empírico
del ejemplo y **no está validada**; se suma al cambio de entalpía sensible.
Por ello, no se debe usar el resultado para garantizar consumo de un horno.
Referencia primaria sobre liberación de CO2 de los carbonatos durante la
fabricación de vidrio: US EPA, documento de proceso de vidrio plano:
https://nepis.epa.gov/Exe/ZyPURL.cgi?Dockey=10004QJ7.TXT

### Recuperación de penicilina (`penicillin`)

El ejemplo anterior producía penicilina, que contiene nitrógeno y azufre,
desde una alimentación de glucosa y agua. No tenía fuente de N/S, aire,
cinética ni reacción implementada. Se acota explícitamente el caso a
**recuperación downstream desde caldo ya fermentado**, y el menú refleja
este cambio. La fermentación queda fuera de la batería; no se simula una
biosíntesis inexistente.

La alimentación contiene biomasa, penicilina, glucosa residual y agua. Un
filtro retira 99.5% del micelio con torta de 70% de humedad; el líquido
arrastrado lleva su correspondiente fracción de antibiótico. Después, un
bloque agregado de extracción/cristalización recupera 98% de la penicilina
del filtrado con arrastres de glucosa y agua declarados. No es una filtración
de moléculas disueltas. No se modelan las etapas de pH, el equilibrio con
solvente, sus pérdidas ni la cristalización rigurosa; no se asegura pureza
farmacéutica. Se conserva exactamente la penicilina que entra con el caldo.

Referencia docente primaria: NIT Srinagar, *Commercial Production of
Penicillin*, distingue fermentación, filtración del micelio, extracción y
cristalización:
https://nitsri.ac.in/Department/Chemical%20Engineering/BRTL10.pdf

### Clarificación y filtración de agua (`water_treat`)

`R_FLOCULACION` se sustituye por mezcla física, sin transformar especies.
Sedimentador y filtro tienen recuperaciones explícitas de sólidos y agua;
el filtro ahora tiene una salida de retrolavado que evita que los sólidos
simplemente desaparezcan. La salida se llama agua filtrada. El menú dice
«sin desinfección»: remoción de sólidos no demuestra potabilidad.

No se predice dosificación de coagulante, remoción de contaminantes
disueltos ni desinfección. Referencia primaria sobre las etapas distintas
de una planta convencional: CDC, *How Water Treatment Works*:
https://www.cdc.gov/drinking-water/about/how-water-treatment-works.html

## Ácido nítrico y cloro-álcali

El detalle de ecuaciones, valores y alcance está en
[`AUDITORIA_HNO3_CLORALCALI_2026-11.md`](AUDITORIA_HNO3_CLORALCALI_2026-11.md).
Ambos ejemplos dejan de fijar sus productos de manera independiente de los
reactivos: las especies se calculan mediante estequiometría y las salidas
mediante recuperaciones por componente que conservan todo el material.

En **HNO3**, 1 000 t/a de NH3 producen aproximadamente 6 120 t/a de ácido
al 57,7%. Se declara 96% de selectividad hacia NO, se convierte el resto de
NH3 en N2, se oxida 99,5% del NO y se representa la absorción/reoxidación
mediante `4 NO2 + O2 + 2 H2O -> 4 HNO3` con 99,9% de conversión. Se añaden
el bloque de reacción secundaria, la absorción neta y el letdown antes del
blanqueo. Las presiones 4,5/11 bar las producen bombas/compresores reales.
La concentración final se calcula; no se fuerza a 60%.
Referencia del procedimiento y selectividad: [EPA AP-42 8.8](https://www.epa.gov/sites/default/files/2020-09/documents/8.8_nitric_acid.pdf).

El gas de cola se recalienta en E-501 a 350 °C y se expande desde 11 hasta
1,013 bar en TB-501, ahora clasificado como turbina axial de gas. Este
punto de operación está descrito para un proceso de ácido nítrico en
[US7118723B2, descripción del gas de cola](https://patents.google.com/patent/US7118723B2/en).
El ejemplo calcula aproximadamente 99,1 kW recuperados y 123,2 °C en la
descarga. El recalentamiento evita que la referencia isentrópica requiera
extrapolar las correlaciones caloríficas de NO/NO2 por debajo de su rango.
El calor de E-501 se contabiliza como servicio externo; no se afirma una
integración térmica con los gases de oxidación que el PFD no representa.

Las corrientes que contienen gas y líquido declaran la fracción de vapor
por especie: N2/O2/NO/NO2 gaseosos y H2O/HNO3 líquidos. Su fracción global
de vapor se obtiene de la composición calculada. Esto evita exigir un Cp
líquido ficticio de NO en el condensador o el absorbedor. La traza de NO2
que acompaña al ácido crudo se representa como gas arrastrado y se retira
completamente en el desgasificador ideal. Estas asignaciones de fase son
especificaciones del ejemplo, no un equilibrio de disolución/dimerización
de NO2 ni un cálculo predictivo de equilibrio electrolítico.

En **QUIMPAC**, la base explícita es **sal purificada**: no se forman
precipitados Ca/Mg ausentes de los reactivos. Se retiraron dos bombas y sus
corrientes de reactivos nulos. La electrólisis conserva Na/Cl/H/O mediante
`2 NaCl + 2 H2O -> 2 NaOH + Cl2 + H2`, con conversión por pasada 30% y
recirculación de anolito. Se calculan aproximadamente 607 t/a de Cl2 y
1 370 t/a de solución cercana al 50% de NaOH. La electricidad se obtiene
por Faraday con 3,2 V y eficiencia de corriente 96%: aproximadamente
2,52 MWh/t Cl2. El balance incluye ese trabajo y la refrigeración de celda.
Se añaden separador de membrana, válvulas de letdown del anolito/catolito y
enfriador de producto. Las válvulas usan el tipo real del catálogo
`Valve — control globe`. Se comprime el Cl2 de 1,5 a 7 bar antes de licuarlo.
El evaporador de NaOH al 50% opera en el punto de diseño 143 °C/1,013 bar,
no en el punto de ebullición del agua pura.
Referencias: [Euro Chlor](https://eurochlor.org/products/chlorine-cl/) y
[Covestro, propiedades del NaOH 50%](https://solutions.covestro.com/en/products/caustic/caustic-soda-50_000000000005452627).

**Límites:** conversión, selectividad y recuperaciones son especificaciones
de diseño, no ajustes validados con datos de una planta. No se implementa
equilibrio electrolítico ni transporte de membrana ni cinética de absorción.
El punto de ebullición de NaOH corresponde a esta concentración de diseño;
no hay una correlación completa de actividad. Se conserva el gas residual
de NOx, pero su tratamiento final no está dimensionado. Los equipos de
reacción/celda usan familias genéricas del catálogo, por lo que sus costos
y dimensiones comerciales heredados no constituyen un diseño de fabricante.

`tests/test_industrial_chemistry_audit.py` añade cinco verificaciones:
estequiometría de HNO3, relaciones NaOH/Cl2/H2, trabajo de Faraday, productos
que escalan con los feeds e idempotencia, y secuencia de presión/temperatura.
`tests/test_component_recovery.py` añade nueve pruebas de conservación,
validación, caudal cero y tratamiento de redondeo sin especies ficticias.

### Cloro-álcali compacto con HCl

`chloralkali_hcl` usa ahora la misma base electroquímica y de Faraday que
QUIMPAC, con NaCl sólido disuelto en agua, bombeo de salmuera y recirculación
de anolito. El NaOH sale como solución cercana al 32%, no como NaOH puro
líquido a 80 °C. Cloro e hidrógeno se reparten entre coproductos húmedos y
síntesis de HCl; el quemador aplica `H2 + Cl2 -> 2 HCl` con ligero exceso
de H2. El absorbedor mantiene 35 °C, separa el H2 residual en un venteo y
calcula la concentración final, cercana al 33% con 408 t/a de agua fresca.
No hay caudales de productos fijados independientemente de los reactivos.

El calor de absorción se incluye con una transición estequiométrica
`HCl(g) -> HCl(aq)` que conserva la identidad molecular: se especifican
aproximadamente 0,5 kWh/kg HCl, equivalentes a 65,63 kJ/mol, de acuerdo con
la información de equipos de [SGL Carbon](https://www.sglcarbon.com/pdf/SGL-Information-Sheet-PT-HCl-Synthesis-Steam-Generation-EN.pdf).
Es una aproximación industrial declarada, no una correlación de entalpía
parcial contra concentración. El requisito de refrigeración para producir
ácido concentrado bajo 40 °C coincide con
[De Dietrich/QVF](https://qvf.de/en/solutions-and-products/mineral-acid-treatment/hydrochloric-acid-treatment/absorption-hcl).

Se prueban la relación estequiométrica Cl2/HCl, el exceso de H2 en el
venteo, la concentración y temperatura del ácido, la energía eléctrica y
el deber de refrigeración del absorbedor. También se exige que el producto
escale con las alimentaciones y conserve su resultado al volver a resolver.

### Torres de enfriamiento: aire húmedo y calor latente

`cw_loop` y `cw_natural` declaraban una corriente de agua pura en fase vapor
a 32–33 °C, incluso a 3 bar después de propagar la presión de bombeo. Esa
corriente no representa evaporación atmosférica. Se sustituye por entrada
de aire húmedo y salida de aire con el agua evaporada a 1,013 bar. El módulo
`cooling_tower.py` conserva individualmente N2, O2 y H2O y obtiene la masa
evaporada de `H_entrada = H_salida`, con la misma referencia de entalpía
que el resto del motor. La presión parcial del agua se calcula en base
molar: una humedad relativa superior a uno produce un error explícito;
no se recorta la humedad ni se elimina masa para esconder el problema.

Se distinguen dos especificaciones de operación. En `cw_loop` se mantienen
100 000 t/a de circulación y se suministran 6 000 t/a de reposición; la
purga cierra el balance de agua. El intercambiador calcula el retorno a
53,155 °C desde el calor retirado al aceite, en lugar de fijar temperaturas
incompatibles en sus cuatro puertos. Se añade un ventilador axial con
200 000 t/a de aire de entrada a 25 °C y 1% de agua en masa. En
`cw_natural`, la entrada atmosférica es de 8 000 000 t/a de aire con igual
composición; no se utiliza ventilador en una torre de tiro natural. La
purga se especifica como el 1,2% del retorno líquido. Los intercambiadores
laterales conservan sus servicios de enfriamiento externos declarados.

| Magnitud calculada | `cw_loop` | `cw_natural` |
|---|---:|---:|
| Agua evaporada, t/a | 3 702,224 | 126 141,254 |
| Purga líquida, t/a | 2 297,776 | 67 200,000 |
| Agua fría, t/a | 100 000,000 | 5 406 658,746 |
| Aire húmedo de salida, t/a | 203 702,224 | 8 126 141,254 |
| Temperatura del aire de salida, °C | 32 | 33 |
| Humedad relativa del aire de salida | 93,54% | 80,25% |

Ambos casos resuelven sin errores de masa, energía ni consistencia. El
residuo energético de la torre es menor que `1e-9 kW`. Las ocho pruebas
en `tests/test_cooling_tower_physics.py` verifican conservación, escalado,
rechazo de humedad imposible, falta de agua y solutos no soportados, y
los dos ejemplos completos. La regresión original del splitter con dos
entradas se conserva sobre un splitter genérico: sus fracciones fijas no
se interpretan como un cálculo de evaporación.

**Alcance:** es un modelo de punto de operación con temperaturas de salida
y caudal de aire especificados, no una predicción de capacidad mediante
Merkel/NTU, relleno o curvas de fabricante. Se modela agua pura, gas ideal,
purga y evaporación; se desprecia arrastre de gotas y no se predicen ciclos
de concentración ni tratamiento químico. La relación entre intercambio
de entalpía del aire húmedo y evaporación sigue el procedimiento expuesto
en la [referencia de ingeniería de EnergyPlus](https://energyplus.readthedocs.io/en/stable/guides/engineering-reference/16.1-cooling-towers-and-evaporative-fluid-coolers.html),
apartados de balances y consumo de agua. Los datos numéricos de operación
anteriores son supuestos de estos ejemplos y no datos certificados de una
instalación industrial.

## Separación criogénica de aire (`air_sep`)

Se corrige la declaración imposible de N2/O2 líquidos a -95/-90 °C: ambas
temperaturas excedían sus temperaturas críticas. El aire comprimido a 6 bar
se posenfría a 35 °C y pasa por una prepurificación agregada que retira el
agua por recuperación especificada. Su salida de agua es condensado
equivalente de la regeneración; no se simula el ciclo del adsorbente.
CO2, argón e hidrocarburos no están presentes en la alimentación simplificada.

La licuefacción externa entrega aire líquido a 90 K/6 bar. Un bloque
explícitamente agregado de doble columna y subenfriamiento entrega N2
líquido a 75 K/1,3 bar y O2 líquido a 87 K/1,3 bar. La estabilidad líquida
se comprueba mediante flash Peng–Robinson. Las recuperaciones hacia N2
son 99,9% del N2 y 0,1% del O2; el resto sale por O2, conservando especies.
No se calculan platos, reflujo, MESH ni el acoplamiento condensador/reboiler.

Las cargas de licuefacción y subenfriamiento son demandas explícitas de
refrigeración externa; el ciclo, COP y su potencia eléctrica quedan fuera
del alcance. Se desactiva la selección ficticia de refrigerante de -50 °C
y se retira la electricidad fija heredada. Por tanto el costo energético
total de una ASU real no queda validado con este caso.

Fuentes primarias: [Linde, Air separation plants](https://assets.linde.com/-/media/global/engineering/engineering/home/products-and-services/process-plants/air-separation-plants/air-separation-plants-history-and-technological-progress-2019.pdf),
prepurificación, compresión y doble columna; propiedades de fase del
[N2](https://webbook.nist.gov/cgi/cbook.cgi?ID=C7727379&Mask=4) y
[O2](https://webbook.nist.gov/cgi/cbook.cgi?ID=C7782447&Mask=4), NIST.
