<!--
====================================================================
 joback_groups.md  —  Tabla Joback (1987) de contribuciones de grupo.

 Referencia: Joback K.G., Reid R.C., 1987 "Estimation of pure-component
 properties from group-contributions". Chem. Eng. Comm. 57:233-243.

 PENDIENTE Fase 2: poblar las 41 contribuciones originales.

 Columnas:
   group:           nombre del grupo (texto humano)
   smarts:          patron SMARTS para deteccion (RDKit)
   dh_f_gas_kJ_mol: contribucion a ΔHf°_gas (298.15 K)
   ds_gas_J_mol_K:  contribucion a ΔS°_gas
   cp_a, cp_b,
   cp_c, cp_d:      coefs Cp(T) = a + b·T + c·T² + d·T³ [J/(mol·K)]
   dtb_K:           contribucion a Tb (Joback eq 1)
   dtc_K:           contribucion a Tc/Tb
   dpc_bar:         contribucion a 1/(Pc^0.5)
   dhv_kJ_mol:      contribucion a ΔH_vap a Tb

 IMPORTANTE para el implementador (Fase 2):
   Si esta tabla no esta disponible al momento de implementar,
   PARAR y pedir las 41 contribuciones al usuario humano antes de
   continuar (§10.4 de la arquitectura).
====================================================================
-->

# Contribuciones Joback (1987)

<!--
TODO Fase 2: agregar las 41 contribuciones aqui.
Formato propuesto (markdown tabla o seccion por grupo):

## -CH3 (metilo terminal)
- smarts: [CX4H3]
- dh_f_gas_kJ_mol:  -76.45
- ds_gas_J_mol_K:    -43.96
- cp_a:               19.5
- cp_b:               -8.08e-3
- cp_c:                1.53e-4
- cp_d:               -9.67e-8
- dtb_K:               23.58
- dtc_K:                0.0141
- dpc_bar:           -0.0012
- dhv_kJ_mol:           2.373

(Repetir para los 40 grupos restantes)
-->
