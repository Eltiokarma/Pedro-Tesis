<!--
====================================================================
 predicted_compounds_db.md  —  Cache de compuestos predichos por el
 predictor (vacio inicial).

 Cada vez que un template genera un producto nuevo no presente en
 thermo_db, product_builder.register_predicted_compound() lo agrega
 aqui con sus propiedades estimadas (Joback) y flag origin='predicted'.

 NO escribir a mano — este archivo es output del predictor.

 Formato esperado por entrada (ver §9.6 de la arquitectura):

   ## propyl_butanoate (C7H14O2)  [PREDICTED]
   ### IDs
   - SMILES: CCCC(=O)OCCC
   - Formula: C7H14O2
   - MW: 130.18 g/mol
   - Origin: predicted
   - Parent transformation: T01_esterification_fischer
   - Generated from: [1-propanol, butanoic_acid]
   ### Capa 1 — Antoine [estim Joback]
   ...
   ### Capa 3 — Formacion [Joback]
   dH_f_gas_298K = -463.0 ± 12 kJ/mol [Joback]
   ### Confidence
   - mechanism: alta
   - thermo: media (Joback ±12 kJ/mol)
   - structure: alta (RDKit verifico SMILES canonico)
====================================================================
-->

# Compuestos predichos (cache auto-generado)

<!-- Vacio inicial. -->
