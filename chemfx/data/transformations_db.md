<!--
====================================================================
 transformations_db.md  —  Templates canonicos T01-T20.

 Cada template define:
   - reactant_groups: grupos requeridos por reactante
   - product_groups: grupos esperados en productos
   - stoich_template: patron textual
   - reaction_smarts: SMARTS de reaccion (RDKit RxnSmarts)
   - T_range_K: rango de T donde aplica
   - catalizador requerido (si aplica)
   - confidence del mecanismo

 PENDIENTE Fase 4: poblar las 20 transformaciones completas.
 La tabla resumen esta en §6 de la arquitectura del predictor.
====================================================================
-->

# Transformaciones canonicas T01-T20

## T01_esterification_fischer — Esterificacion de Fischer
- Categoria: equilibrio
- Confidence mecanismo: ALTA
- Referencia: March's Advanced Organic Chemistry 7e §16.64

### Reactantes (grupos requeridos)
- A: acido_carboxilico
- B: alcohol_primario | alcohol_secundario | alcohol_terciario

### Productos
- Principal: ester
- Secundario: agua

### Estequiometria
1 acido + 1 alcohol  →  1 ester + 1 H2O

### Reaction SMARTS
[CX3:1](=[OX1:2])[OX2H:3].[OX2H:4][CX4:5]>>[CX3:1](=[OX1:2])[OX2:5][CX4:5].[OX2H2:4]

### Rango T valido
298 - 450 K (liquido); 450-550 K (vapor con catalizador)

### Catalizador tipico
H+ (H2SO4, p-toluenesulfonic acid, Amberlyst)

### Comentarios
Reaccion de equilibrio (Keq ~ 3-5 a 298 K). Industrial desplazada por
exceso o destilacion reactiva. ΔH típico -3 a -8 kJ/mol (casi atermica).
Con alcoholes terciarios la velocidad es baja y se favorece T08
(deshidratacion) — flagear confidence MEDIA en ese caso.

---

<!--
TODO (Fase 4): completar T02-T20 con el mismo formato.
Referencia: §6 de la arquitectura del predictor.
-->
