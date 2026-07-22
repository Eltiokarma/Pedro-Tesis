# Resumen de convergencia — estado actual (los 40 ejemplos)

**Fecha:** 2026-07-18 · **Snapshot tras** todos los fixes (PRs #123-133) incluyendo el detank (feeds/products como corrientes de borde). Cifras económicas al perfil PE_2024, Turton 8.2.

> Este documento es la **fuente única** de las cifras actuales. Las tablas de los 6 docs de análisis por grupo conservan los ISBL **pre-detank** (más altos por el costo de los tanques de borde ya removidos); los **veredictos y conclusiones no cambian**. Para el número vigente, ver acá.


## Introductorios

| Ejemplo | ISBL (M USD) | NPV (M USD) | IRR | γ | Veredicto |
|---|---:|---:|---|---|---|
| hda | 9.70 | -20.99 | — | 1.23 | **INVIABLE** |
| methanol | 5.21 | 12.54 | 34.1% | 1.23 | **VIABLE** |
| distillation | 1.06 | 3.46 | 41.7% | 1.1 | **VIABLE** |
| ammonia | 7.38 | -23.79 | — | 1.23 | **INVIABLE** |
| ethanol | 2.77 | -15.56 | — | 1.23 | **INVIABLE** |
| biodiesel | 0.95 | -5.96 | — | 1.23 | **INVIABLE** |
| cdu | 5.59 | 12.61 | 32.7% | 1.05 | **VIABLE** |

## Reactores y solver avanzado (Capas 4-6)

| Ejemplo | ISBL (M USD) | NPV (M USD) | IRR | γ | Veredicto |
|---|---:|---:|---|---|---|
| smr_eq | 9.56 | -24.59 | — | 1.23 | **INVIABLE** |
| ethane_pfr | 6.22 | -17.60 | — | 1.23 | **INVIABLE** |
| haber_rec | 13.48 | -31.55 | — | 1.23 | **INVIABLE** |
| dist_eth_az | 1.53 | -8.42 | — | 1.23 | **INVIABLE** |
| rxn_flash_col | 3.06 | -13.40 | — | 1.23 | **INVIABLE** |
| hydraulic | 0.58 | -5.60 | — | 1.23 | **INVIABLE** |

## Plantas industriales completas

| Ejemplo | ISBL (M USD) | NPV (M USD) | IRR | γ | Veredicto |
|---|---:|---:|---|---|---|
| hda_full | 30.65 | 8.60 | 13.1% | 1.05 | **VIABLE** |
| gas_sweet | 12.58 | 1.96 | 11.8% | 1.05 | **VIABLE** |
| sugar | 56.14 | -16.37 | 6.6% | 1.1 | **INVIABLE** |
| industrial | 26.95 | 9.03 | 13.7% | 1.23 | **VIABLE** |
| quimpac | 49.23 | -98.20 | — | 1.23 | **INVIABLE** |
| hno3 | 9.73 | -10.88 | -4.6% | 1.23 | **INVIABLE** |
| talara | 41.07 | -12.62 | 6.4% | 1.1 | **INVIABLE** |

## Alimentaria y bioproceso

| Ejemplo | ISBL (M USD) | NPV (M USD) | IRR | γ | Veredicto |
|---|---:|---:|---|---|---|
| pasteurizer | 0.37 | -3.03 | — | 1.23 | **INVIABLE** |
| pineapple | 4.07 | -30.41 | — | 1.23 | **INVIABLE** |
| potato_chips | 0.72 | -2.56 | — | 1.23 | **INVIABLE** |
| bread | 1.64 | 1.22 | 18.0% | 1.23 | **VIABLE** |
| beer | 1.45 | 2.06 | 24.8% | 1.23 | **VIABLE** |
| penicillin | 3.97 | -12.64 | — | 1.23 | **INVIABLE** |
| leche_gloria | 11.18 | -37.95 | — | 1.23 | **INVIABLE** |

## Química

| Ejemplo | ISBL (M USD) | NPV (M USD) | IRR | γ | Veredicto |
|---|---:|---:|---|---|---|
| sulfuric | 0.64 | -6.94 | — | 1.23 | **INVIABLE** |
| acetic | 2.93 | -9.54 | — | 1.23 | **INVIABLE** |
| ldpe | 2.14 | -9.36 | — | 1.23 | **INVIABLE** |
| chloralkali_hcl | 6.29 | -14.70 | — | 1.23 | **INVIABLE** |
| urea | 4.57 | -11.05 | — | 1.23 | **INVIABLE** |
| soap | 0.82 | 1.03 | 23.2% | 1.1 | **VIABLE** |
| ethylene_crk | 6.48 | -17.53 | — | 1.23 | **INVIABLE** |

## Materiales y energía

| Ejemplo | ISBL (M USD) | NPV (M USD) | IRR | γ | Veredicto |
|---|---:|---:|---|---|---|
| cement | 3.84 | -10.99 | — | 1.23 | **INVIABLE** |
| glass | 0.55 | -2.36 | — | 1.23 | **INVIABLE** |
| air_sep | 2.27 | -7.01 | — | 1.23 | **INVIABLE** |
| water_treat | 5.59 | -13.76 | — | 1.23 | **INVIABLE** |
| rankine | 6.52 | -18.74 | — | 1.23 | **INVIABLE** |
| nuclear | 1.52 | -8.28 | — | 1.23 | **INVIABLE** |
| desal | 7.57 | -64.33 | — | 1.23 | **INVIABLE** |

## Totales

- **9 VIABLE / 40**: methanol, distillation, cdu, hda_full, gas_sweet, industrial, bread, beer, soap.
- **31 inviables**, todos con porqué demostrado (ver docs de análisis por grupo).

### Taxonomía de los porqués
1. **γ sectorial mal aplicado** (química standalone 1.23 sobre commodity) → corregido con γ=1.05-1.10: cdu, distillation, hda_full, gas_sweet, soap.
2. **Precios de corriente sin calibrar** → corregidos: hda purga, distillation feed, beer (granel), leche_gloria (vapor ×100), haber_rec (feed sin precio).
3. **Escala de demostración** (viables a escala industrial): urea, glass, ethanol.
4. **Producción pinneada / equipo sobredimensionado** (escalar no ayuda): los 6 del grupo 2, quimpac, hno3, acetic, sulfuric, air_sep, cement.
5. **Topología incompleta (sin reciclo)**: ammonia, ldpe, ethylene_crk.
6. **No es un negocio por diseño**: rankine/nuclear (Tier-2), water_treat/desal (utility pública), penicillin/pasteurizer (piloto).

### Bugs reales encontrados y corregidos en el recorrido
| Bug | Estado |
|---|---|
| Propagación de presión (reactor default + HX 4-puertos) | CORREGIDO |
| haber_rec feed sin precio | CORREGIDO |
| leche_gloria vapor ×100 | CORREGIDO |
| beer precio de granel vs microcervecería | CORREGIDO |
| Compresores de reciclo sin P_op (K-101/K-202) | CORREGIDO |
| Costeo del boiler (124× el WHB validado) | CORREGIDO |
| Expander/turbina cobrado como consumo (generación eléctrica) | CORREGIDO |
| Auto-sizing colapsa ISBL sin S fijado (+ sizers filtro/cristalizador) | CORREGIDO |
| Mega-tanques 7d y feeds/products como tanques (→ day-tank 1d + corrientes de borde) | CORREGIDO |
| talara: splitters FCC redistribuyen flujos al insertar bloque pass-through | PENDIENTE (aislado) |
