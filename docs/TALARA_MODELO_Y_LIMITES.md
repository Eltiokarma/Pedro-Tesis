# Talara: modelo reproducible y límites de interpretación

El ejemplo reproduce la conexión de las familias de unidades de refino, con una base didáctica de **500 000 t/año de crudo**. No es un modelo calibrado de la Nueva Refinería Talara, ni sus resultados representan capacidades, rendimientos, consumos o especificaciones comerciales de Petroperú. Las capacidades públicas se expresan habitualmente en barriles por día y no justifican convertir esta base arbitraria en producción real sin densidades y disponibilidad de operación.

## Base del cálculo

| Sección | Modelo implementado | Información que falta para una predicción de planta |
|---|---|---|
| Desalado | Agua de lavado y sal de la alimentación salen por la salmuera; hidrocarburos se conservan. Calentador y bombas explícitos. | Emulsiones, arrastre de agua, partición real de sales, eficiencia eléctrica. |
| Destilación atmosférica y vacío | Ensayo de pseudocortes declarado en la alimentación y recuperaciones por componente. Vacío a 0.08 bar absolutos, sistema de extracción de no condensables y bombas de productos explícitos. | Curva TBP, densidad/MW por corte, equilibrio de pseudocomponentes, etapas, reflujo, vapor de stripping y carga real de vacío. |
| FCC | Rendimientos másicos de la fracción `crude_oil` usada como pseudocorte VGO: 48% nafta, 14% LCO, 18% GLP, 3% gas seco, 7% slurry y 10% coque. El módulo convierte masa entrante; no fija caudales de salida. | Ensayo elemental, cinética, regenerador, combustión del coque, circulación de catalizador y calor de craqueo. El coque sale como coproducto contable del límite simplificado. |
| Flexicoking | Rendimientos declarados del residuo: 25% nafta, 30% gasóleo, 45% carbono. De la alimentación, 40% pasa como coque al gasificador y 5% sale como purga. | Rendimientos licenciados y ensayo real de coque. Estos porcentajes son supuestos didácticos, no datos de ExxonMobil ni Petroperú. |
| Gasificación | Reacción global idealizada `4 C + 2 H2O + O2 → 4 CO + 2 H2`, aire explícito con 23.2% másico O2, vapor con 20% de exceso, gas a 900 °C y recuperación de calor. Se conservan C/H/O/N. | Equilibrio multirreacción, metano/CO2/H2S, cenizas, combustión parcial distribuida, temperatura adiabática de gasificador real y recuperación de azufre. |
| Tratamiento de naftas/diésel | Separador especificado retira 99.9% del H2S **ya presente**. El H2 alimentado sale explícitamente con el gas agrio. | Química de azufre orgánico, consumo real de H2, catalizador, cinética y recirculación. No se certifican ppm de azufre ni se presenta el producto como ULSD real. |
| Reformado catalítico | Pasaje térmico del pseudocorte nafta, con horno, enfriamiento y control de presión. | Química aromática/parafínica, producción de H2 y correlación de octano. El producto no se etiqueta como gasolina de 97 octanos. |
| Producción de H2 | Reformado de metano con vapor (R003, 90% de conversión), desplazamiento agua-gas (R002, 98%), enfriamiento, separación de agua y PSA de recuperación H2 especificada al 90%. Compresión a 85 bar, enfriamiento y válvulas hacia los consumidores. | Cinética/equilibrio real, intercambio integrado, purgas/reciclos, recuperación/adsorción PSA y pureza garantizada. Las conversiones son supuestos declarados. |

Los flujos internos y las composiciones de producto están desbloqueados. Las composiciones se calculan a partir de lo que entra; la fracción no recuperada de cada especie tiene un destino. En FCC/FCK solamente se permite transformar los pseudocomponentes declarados: las co-alimentaciones reales se conservan. El `lumped_yield_basis` explica la base y los límites de cada conversión.

La composición de azufre utiliza H2S como trazador explícito de balance. Es una simplificación considerable: el azufre del crudo real se encuentra principalmente en múltiples compuestos orgánicos. Separar ese trazador permite comprobar la conservación de azufre y H2, pero no simula hidrodesulfuración molecular.

Los deberes térmicos de unidades sin reacción declarada proceden de la diferencia de entalpía entre corrientes. En los pseudocortes esto es una aproximación calorimétrica; el cierre numérico no incorpora automáticamente los calores de craqueo/reformado que no están definidos. La válvula hacia la columna atmosférica conserva entalpía y calcula temperatura para una calidad de vapor especificada de 0.5: esa calidad es un supuesto, no una predicción de equilibrio del crudo. El corte lateral de gasóleo se enfría antes de bombearlo como líquido. Las corrientes de suministro y productos señalan el límite de planta; no se duplica una corriente intermedia como venta y como alimentación al mezclador de gasolina.

## Comprobaciones reproducibles

Ejecutar desde la raíz del proyecto:

```text
python -m pytest tests/test_talara_physics_audit.py tests/test_columnas_que_no_separan.py -q
```

Las pruebas verifican masa por unidad y en el límite global, componentes en equipos sin reacción, elementos en SMR/WGS/gasificador, disponibilidad de entalpías, deberes térmicos, trabajo de bombas/compresores, presión de vacío y respuesta de todos los caudales al aumentar las alimentaciones un 25%. También rechazan rendimientos negativos, no finitos, que no suman uno, o conversiones de especies reales fuera del ámbito autorizado.

## Referencias de procedimiento

Se consultaron fuentes primarias para la existencia y finalidad de las unidades, no para validar los supuestos numéricos del ejemplo:

- [Petroperú: Memoria anual 2023](https://www.petroperu.com.pe/Storage/tbl_documentos_varios/fld_1160_Documento_file/651-v2Yh5Wc3Ib9Rp2A.pdf): relación de unidades y capacidades del proyecto real.
- [Petroperú: pruebas de arranque de la Nueva Refinería Talara](https://www.petroperu.com.pe/nueva-refineria-talara-continua-con-pruebas-de-arranque-previas-al-inicio-de-su-operacion-comercial): suministro y uso de la producción de hidrógeno.
- [ExxonMobil: FLEXICOKING technology factsheet](https://www.exxonmobilchemical.com/-/media/media-assets/media-library-assets/2/flexicoking_factsheet_en.pdf): reactor de craqueo y gasificador que emplea aire y vapor para convertir coque en gas combustible. Justifica incorporar esos equipos y alimentaciones, no los rendimientos de este ejemplo.
- [Comparación con el código de DWSIM](DWSIM_REFERENCIA_AUDITORIA.md): balances de mezclador, separación especificada, recirculaciones y referencias entálpicas. Se inspeccionó código; no se ejecutó DWSIM para certificar este caso.
