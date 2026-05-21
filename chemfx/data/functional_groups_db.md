<!--
====================================================================
 functional_groups_db.md  —  Asignaciones manuales por compuesto.
 Fallback cuando RDKit no esta disponible o cuando el compuesto no
 tiene SMILES.

 Formato: una seccion por compuesto, con header '## name', y
 una lista 'groups:' con los grupos detectados.

 PENDIENTE Fase 1: poblar para los 108 compuestos del thermo_db.
====================================================================
-->

# Asignaciones de grupos funcionales por compuesto

## ethanol
groups: alcohol_primario

## methanol
groups: alcohol_primario

## water
groups:

## acetic_acid
groups: acido_carboxilico

## acetone
groups: cetona

## acetaldehyde
groups: aldehido

## benzene
groups: aromatico

## phenol
groups: alcohol_aromatico, aromatico

## methane
groups:

## ethylene
groups: alqueno

## hydrogen
groups:

## oxygen
groups:

## carbon_dioxide
groups:

## ammonia
groups: amina_primaria

<!--
TODO (Fase 1): completar para los 108 compuestos. Lista actual
parcial — solo los mas obvios. Los demas se llenan junto con
la asignacion de SMILES en thermo_db.md.
-->
