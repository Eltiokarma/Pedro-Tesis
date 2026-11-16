# Auditoría del núcleo termodinámico — 15 noviembre 2026

Base revisada: `349b81729fb00400036bc3a989be5e999b8e27c6`.

## Errores corregidos y evidencia

| Problema | Antes | Corrección y comprobación |
|---|---|---|
| Entalpía de vapor | Se sumaba `Cp_gas(Tmedio)*(T-25) + ΔHvap(T)`. Al calentar agua vapor de 100 a 101 °C, la entalpía aumentaba sólo 0.307 kJ/kg, aunque Cp era ~1.9. | Integra Cp de la fase sobre una referencia fija por especie. Ahora aumenta 1.901 kJ/kg. Se prueba `dh/dT=Cp` para agua, etanol, hidrógeno y óxidos de nitrógeno. |
| Calidad bifásica | Se combinaba Cp líquido con un calor latente variable que no coincidía con la diferencia de entalpías calculadas para las fases. | `h=(1-beta)*h_liq+beta*h_gas`, con **beta másica**. |
| Flash líquido–líquido | La definición de K y las fórmulas de composición estaban invertidas. Agua–benceno oscilaba hasta 100 iteraciones y se devolvía como solución. | Define `K=x_beta/x_alpha=gamma_alpha/gamma_beta`; resuelve la fracción de la segunda fase. Verifica igualdad de actividades y regla de la palanca; el caso converge en pocas iteraciones. |
| Flash PR en borde | La primera estimación Wilson se aceptaba como prueba de una sola fase. | Se siguen refinando los coeficientes de fugacidad. Metano/benceno, z=(0.1,0.9), 250 K, 20 bar: antes V/F=0; ahora ~0.011355 y cierra fugacidades y componentes. |
| Fin de iteraciones | NRTL, PR y LLE devolvían el último resultado aunque no convergiera. | Devuelven `None`; el consumidor debe informar el fallo, sin etiquetar el último intento como solución. |
| Presión de vapor de CO₂ | La curva llegaba a ~7350 bar cerca del crítico, frente a Pc~73.8 bar. | Corrige A de Antoine en dos unidades decimales. Se comprueban los anclajes crítico y triple; ambos alias usan los datos completos. |
| Registros duplicados incompletos | `carbon_dioxide`, `carbon_monoxide`, `hydrogen_sulfide` y `sulfur_dioxide` ocultaban los datos caloríficos completos de CO₂, CO, H₂S y SO₂. Incluso una traza de H₂S dejaba sin entalpía una corriente de Talara. | Ambos nombres de cada molécula resuelven la misma entrada completa. Las 44 corrientes afectadas en la comprobación de Talara recuperaron entalpías resolubles sin cambiar sus fases ni inventar Cp. |
| NO/NO₂ sin capacidad calorífica | Tenían fórmula/MW/entalpía de formación, pero no Cp; no era posible cerrar el calor de sus reactores. | Datos Shomate NIST, dos intervalos 298–1200 y 1200–6000 K, con integración analítica y fuentes declaradas. |
| Coque sin propiedades | `carbon` no tenía MW ni calor sensible. | Carbono sólido aproximado como grafito, MW=12.011, Cp variable de Butland–Maddison compilada por NIST; integral analítica, 250–3000 K. El carbono arrastrado en una corriente gaseosa conserva su contribución térmica sólida. |

## Convención de energía

La entalpía térmica no incluye entalpía de formación ni calor de mezcla.
Para una especie condensable se toma líquido a 25 °C como cero y se
establece una diferencia **fija** entre referencias de gas y líquido,
preferentemente a partir de sus entalpías de formación. Si faltan esas
referencias, se usa el camino líquido hasta Tb, vaporización en Tb y gas
hasta 25 °C. Los gases permanentes con Tc por debajo de 25 °C usan gas a
25 °C como referencia; no se extrapola un líquido inexistente.

El término sensible es la integral de Cp de la fase. DIPPR cuártico se
integra con cuadratura exacta de tres puntos; Shomate y la correlación
del grafito tienen integral analítica. `temperature_for_enthalpy` invierte
el mismo modelo para los balances de energía; devuelve `None` si no hay
solución válida en el intervalo. No realiza un flash presión–entalpía:
la fase y la calidad se mantienen fijas.

Al combinar este modelo con calores de reacción referidos a otras fases,
hay que corregir la diferencia entre referencias de reactivos y productos.
`reference_phase_offset_kJ_kg` y la entalpía de cada especie a 25 °C permiten
hacer esa transformación. Cambiar sólo la entalpía de corriente sin
corregir la referencia de reacción produciría otro error de balance.

Un caudal cero transporta cero energía. Una composición desconocida no
se elimina silenciosamente del cálculo de entalpía; se exige propiedad
resoluble o una especificación manual de Cp.

## Alcance de la validación

Regresiones en `tests/test_thermo_physical_invariants.py`: conservación por
componente, fugacidad/actividad, rechazo de no convergencia y entradas
inválidas, derivada calorífica, calidad, inversión de energía, anclajes
del CO₂ y datos NO/NO₂/grafito. Se mantienen los gates PR existentes.
La comparación con tablas de agua permite 2% en el calor de vaporización
a 100 °C: es una comprobación del modelo calorífico aproximado, no una
implementación de IAPWS.

## Límites que siguen vigentes

- El modelo calorífico no incluye entalpía residual por presión de una
  EOS, ni entalpía de exceso, electrolitos o calor de disolución. Un
  balance numéricamente cerrado no elimina estas limitaciones.
- Peng–Robinson usa kij=0. Los sistemas polares/asociativos y las mezclas
  de alta presión necesitan parámetros verificados y un paquete apropiado.
- El flash emplea sustitución sucesiva; no implementa una búsqueda global
  de estabilidad del plano tangente ni equilibrio multifásico general.
- NO₂ se trata como monómero calorífico; su dimerización a N₂O₄ requiere
  una reacción y datos adicionales. Grafito representa sólo la aproximación
  calorífica del coque, no su composición real ni su cinética.
- Muchos parámetros originales del catálogo siguen sin procedencia
  experimental verificada. Los gates de regresión no certifican toda la
  base de propiedades para diseño de una planta.

## Referencias utilizadas

1. NIST SRD69, NO, Cp Shomate: https://webbook.nist.gov/cgi/cbook.cgi?ID=C10102439&Mask=1
2. NIST SRD69, NO₂, Cp Shomate: https://webbook.nist.gov/cgi/cbook.cgi?ID=C10102440&Mask=1
3. NIST SRD69, grafito, Butland y Maddison (1973): https://webbook.nist.gov/cgi/cbook.cgi?ID=C7782425&Mask=2
4. NIST SRD69, CO₂, datos de fase: https://webbook.nist.gov/cgi/cbook.cgi?ID=C124389&Mask=4
5. DWSIM, referencia de implementación abierta, integración sensible/latente: https://github.com/DanWBR/dwsim/blob/windows/DWSIM.Thermodynamics/PropertyPackages/PropertyPackage.vb#L8580
6. DWSIM, flash iterativo y rechazo de no convergencia: https://github.com/DanWBR/dwsim/blob/windows/DWSIM.Thermodynamics/FlashAlgorithms/NestedLoops.vb#L481
7. Thermo, fugacidad y EOS cúbicas: https://thermo.readthedocs.io/thermo.eos_mix.html

La curva Antoine del CO₂ original se conserva como ajuste aproximado
con su escala corregida. **No** se atribuye a NIST: los parámetros Antoine
publicados allí cubren sublimación a 154.26–195.89 K y son otra curva.

## Cierre de calorimetría de mezclas, criogenia y turbinas

- Se corrigió otra suma parcial de Cp: una mezcla de cloro con 4,67 ppm
  másicos de agua devolvía solamente el aporte del agua (~0,0000087
  kJ/kg/K). La resolución ahora consulta cada especie en la base y después
  en el catálogo legacy: el mismo estado devuelve 0,481506 kJ/kg/K. Una
  especie sin dato ni override explícito invalida la mezcla, sin desaparecer
  de la suma. La regresión verifica además que Cp coincide con dh/dT.
- Los líquidos criogénicos de gases permanentes usan la misma referencia
  que su vapor: gas a 25 °C, enfriamiento hasta Tb, condensación en Tb y
  calentamiento/enfriamiento líquido desde Tb. Se elimina la integración
  ficticia de líquido desde 25 °C, por encima del punto crítico. En N₂ a
  Tb, la entalpía líquida pasa de aproximadamente −4988 a −445 kJ/kg.
  Se conservan los calores latentes Antoine aproximados existentes;
  las pruebas permiten su desviación frente a valores tabulados y no
  certifican precisión de licuefacción industrial.
- `steam_expander.py` permite vapor húmedo en turbinas de agua pura.
  Calcula entropía sensible mediante ∫Cp/T, el salto de saturación mediante
  s_fg=h_fg/T y la expansión isentrópica con calidad másica. La eficiencia
  actúa sobre el salto de entalpía; la pérdida mecánica queda explícita.
  A 60 bar, con entradas de 450 y 280 °C y descarga a 0,1 bar, los casos
  de prueba producen mezcla a 45,768 °C, con calidades 0,909 y 0,826 para
  eficiencia isentrópica 0,85. El primer principio cierra con la entalpía
  compartida. Se rechaza una entrada declarada vapor por debajo de Tsat.
- Esta turbina es una aproximación de evaluación preliminar: usa la curva
  Antoine y Cp/entalpías existentes, **no IAPWS**, ni entalpía residual por
  presión. No representa trabajo de líquido comprimido ni ofrece precisión
  cerca del crítico. Referencia de convenciones y tablas independientes:
  https://www.nist.gov/system/files/documents/srd/steam-manual-222.pdf
- Las corrientes heterogéneas pueden declarar
  `component_vapor_fractions`, con fracción vapor másica por especie.
  Todas las especies presentes deben tener asignación finita entre 0 y 1;
  se permiten claves de productos que todavía no aparecen. La entalpía y
  Cp se calculan en la fase de cada especie y la calidad global se deriva
  de su composición real. Esto evita exigir propiedades de líquido de
  NO/NO₂ cuando el gas está arrastrado con ácido acuoso. Es una asignación
  de fases declarada, **no una predicción de VLE**; no incluye disolución,
  dimerización de NO₂ ni calor de mezcla. Las pruebas cubren integridad
  de asignaciones, cambio de alimentación, serialización y derivada Cp.
