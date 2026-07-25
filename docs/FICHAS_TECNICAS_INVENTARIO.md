# Fichas Técnicas de equipo — inventario aplanado y contrato propuesto

Barrido completo del código (julio 2026, rama `claude/fichas-tecnicas-equipo-tp1qw5`)
para responder: **¿qué datos por equipo existen ya en el sistema, dónde viven,
y cómo se organizan en una ficha técnica (datasheet) por equipo?**

Método: lectura exhaustiva de `inspector_evidence.py`, `flowsheet_solver.py`,
`equipment_sizing.py`, `equipment_design.py`, `equipment_costs.py`,
`equipment_auxiliaries.py`, `flowsheet_export.py`, `flowsheet_model.py`,
`hydraulic_defaults.py`, `pressure_drop.py`, `econ_defaults.py`,
`flowsheet_units.py`. Nada de lo listado aquí es especulativo: cada dato tiene
función y línea de origen.

---

## 1. Mapa de capas — dónde vive hoy cada dato por equipo

| Capa | Módulo | Qué aporta a la ficha | Forma |
|---|---|---|---|
| Catálogo | `equipment_costs.EQUIPMENT_DATA` (60 eq_types) | categoría, S_param/S_unit, rango de validez, correlación, fuente bibliográfica | dict estático |
| Modelo | `flowsheet_model.Block/Stream` | specs declaradas (T_op, P_op, η, reacciones, LK/HK, fracciones…), corrientes conectadas | dataclass serializada |
| Solver | `flowsheet_solver` | resultados runtime: `_hx_diagnostics`, `_flash_diagnostics`, `_wh_result`, `_column_*`, `_Q_reb/_Q_cond`, `_n_stages`, `_whb_diagnostics`, duty, T/P efectivas | atributos `b._*` (NO serializados) |
| Sizing | `equipment_sizing` (19 sizers) + `equipment_design` (pump/compressor) | parámetro S por tipo + dicts ricos de rotativos | float en `b.S` + dicts |
| Evidencia | `inspector_evidence` (14 familias) | campos etiquetados {key, label, value, unit, state} + tablas de libro | dicts Qt-free (`*_metrics`, `*_book_spec`) |
| Costos | `equipment_costs` | Cp, FP, FM, FBM, CBM, material sugerido con origen | `bare_module_cost()` dict |
| Auxiliares | `equipment_auxiliaries.AUX_STREAMS` | servicios por eq_type (CW, steam, fuel, BFW, aire, blowdown) con puerto/fase/lazo | dataclass specs |
| Hidráulica | `hydraulic_defaults` + `pressure_drop` | ΔP típica por tipo, y por corriente: velocidad, Re, f, régimen | dicts |
| Export | `flowsheet_export.collect_equipment_rows` | precedente: una fila plana por equipo (21 columnas + specs condicionales) | list[dict] |
| Unidades | `flowsheet_units` | conversión/formato de flujo/T/P/energía en 5 sistemas | API global |

**Conclusión estructural**: todos los ingredientes de una ficha existen; lo que
no existe es (a) un agregador único por bloque, (b) la recuperación de los
datos que los sizers calculan y descartan (§3), y (c) una salida (sección del
inspector + export por equipo).

---

## 2. Inventario por capa

### 2.1 Catálogo — los 60 eq_types (`equipment_costs.py`)

Cada entrada Turton: `K1,K2,K3, S_param, S_unit, S_min, S_max, categoria,
correlation, source`. Las dos WHB usan Sinnott: `a,b,n, installation_factor,
P_range_bar, notes` (`Ce = a + b·S^n`, GBP 2010, método de Hand).

| Familia | eq_types | S (unidad) |
|---|---|---|
| Heat exchangers (13) | fixed tube, U-tube, floating head, kettle reboiler, double pipe, multiple pipe, air cooler, condenser shell-tube, condenser air-cooled, flat plate, spiral plate, WHB packaged†, WHB field erected† | área m² († kg/h vapor) |
| Compressors (4) | centrifugal, axial, reciprocating, rotary | kW |
| Turbines (3) | steam, gas (axial), radial expander — formalizan la convención "compresor con P_out<P_in = turbina"; duty<0 = genera (revenue) | kW (fluid power) |
| Pumps (3) | centrifugal, positive displacement, reciprocating | kW (shaft) |
| Vessels (4) | horizontal, vertical, Tower (column shell), Decanter — gravity | m³ |
| Storage (2) | cone roof, floating roof | m³ |
| Reactors (5) | autoclave, jacketed agitated, jacketed non-agit., PFR, CSTR | m³ |
| Fired heaters (2) | reformer, non-reformer | kW |
| Solids / sep. (6) | Crystallizer m³, Dryer — drum m², Evaporator — vertical m², Filter — belt m², Centrifuge disc stack m³ / decanter m³/h, Cyclone m³/s | varía |
| Fans / blowers (2) | centrifugal radial, axial | m³/s |
| Trays / packing (4) | Tray sieve/valve m², Packing random/structured m³ | varía |
| Mixers / splitters (4) | Mixer impeller kW (agitador, sizer P/V de Walas), inline/static m³, Splitter kg/s | varía |
| Valves (3) | control globe, relief, 3-way | m³/h |
| Utilities (4) | Boiler fire/water tube kg/s vapor, Cooling tower induced/natural MW | varía |

### 2.2 Resultados runtime del solver (atributos `b._*`, no serializados)

| Atributo | Equipo | Contenido |
|---|---|---|
| `_hx_diagnostics` | HX/fired | `U_used, dTlm, F, T_h_in/out, T_c_in/out, approach, dT_min, cross_check, data_source, n_shell, n_tube, service, Pr_process, warnings` |
| `_flash_diagnostics` | vessel flash | `names, z, x, y, K` (por comp.), `V_frac, T_K, P_bar, iterations, nonvolatiles` |
| `_wh_result` | columna WH | `x/T_profile` por etapa, `Q_reb_kW, Q_cond_kW, D, B, F, R, feed_stage, balance_err, converged` |
| `_column_N/_R/_N_feed/_alpha_avg/_q` | columna FUG | etapas, reflujo, feed stage, α promedio, calidad q |
| `_Q_reb_kW` / `_Q_cond_kW` | columna | duties de reboiler/condensador |
| `_n_stages` / `_q_intercool_kW` | compresor | etapas del tren + calor de intercoolers |
| `_whb_diagnostics` | WHB | `steam_rate_kg_h, S_min, scale_mismatch, warning` |
| `_adiabatic_T_final_K` | reactor adiab. | T final convergida |
| `_pfr_profile` / `_batch_profile` | reactor PFR/batch | perfil axial/temporal |
| `_energy_streams_delta` | cualquiera | aporte de energy streams al duty |

Helpers de estado efectivo (para la ficha, NO usar los crudos del bloque):
`effective_temperature(fs,b)` (K), `effective_pressure(fs,b)` (bar, piso 1.0),
`effective_split_fractions(fs,b)`, `is_cross_exchange(fs,b)`
(`flowsheet_solver.py:1703-4004`).

### 2.3 Sizing — qué retorna cada sizer y qué descarta

`equipment_sizing.py`: 19 sizers; solo `size_heat_exchanger` retorna
`(S, diag)`; el resto retorna un float y **descarta** los intermedios
(recuperables re-instrumentando, ver §3). Despacho `SIZER_BY_CAT` /
`SIZER_BY_EQTYPE`; `auto_size_blocks` clampa S al rango Turton y muta `b.S`.

### 2.4 Rotativos — dicts completos de `equipment_design.py`

`pump_sizing` → `W_hyd_kW, W_shaft_kW, W_elec_kW, head_m, Q_m3_h, NPSHa_m,
NPSHr_m_est, cavitation_margin_m, eta_total, Ns_us, impeller_type, N_rpm`.
`compressor_sizing` → `ratio, ratio_per_stage, n_stages(_rec), W_isen_kW,
W_act_kW, T_out_K/C, Q_intercool_kW, Q_in_m3_h, head_kJ_kg, eta_total`.
Hoy `size_pump`/`size_compressor` extraen UN solo número de cada dict.

### 2.5 Capa de evidencia — campos por familia (`inspector_evidence.py`)

Contrato `*_metrics` → `{status[], metrics[{key,label,value,unit,state,sub,
span,flag}], figure, warnings[], gauges?, bars?}`. Estados: `spec` (declarado),
`auto` (solver), `info/alert/orange/ok/warn/danger/accent/sinnott/cool`.
Contrato `*_book_spec` → `{kicker, context, columns, rows, chips, provenance,
note, source}` (renderiza `book_table.BookTable`).

| Familia | Funciones | Campos clave que ya emite |
|---|---|---|
| Reactor | `reactor_metrics` + `stoich_book_spec` + `atom_balance_book_spec` | modo, conversión, T/P, V, t_batch, ΔH_rx; tabla estequiométrica Fogler (ν, F_i0, θ, F_i(X), δ, ε); balance de átomos por elemento |
| HX | `hx_metrics` + `utility_aux_metrics` | duty, T caliente/frío in→out, ΔTlm, approach vs dT_min, U, F; ṁ de servicio, T sup/ret, W ventilador/bomba circ. |
| Flash | `flash_metrics` + `flash_book_spec` | T/P flash; tabla z/x/y/K por comp. + V/F (ChemSep) |
| Columna | `mccabe_metrics`, `profile_metrics`, `column_duties_metrics`, `wh_stage_book_spec`, `column_design_text` | N/R/x_D/x_B, N_real, Ø (Souders-Brown), Z relleno; Q_reb/Q_cond; tabla etapa-a-etapa T/x/y/L/V; FUG completo (N_min Fenske, R_min Underwood, N_feed Kirkbride, α, q) |
| Bomba | `pump_metrics` | Q, head, W_hyd/shaft/elec, NPSHa/NPSHr, margen cavitación, N_s con escala de rodete Perry |
| Compresor | `compressor_metrics` | ratio, etapas, Q intercool, Q succión, head, T descarga, W_isen/act; caso turbina/expansor |
| Válvula | `valve_metrics` | P in→out, ΔP, T, VF salida (alerta flasheo), C_v Crane |
| Boiler | `boiler_metrics` | vapor t/h @ P, BFW→vapor T, duty, específica kJ/kg, η |
| Tanque | `tank_metrics` | capacidad, τ residencia (h/días, alerta sobredim.) |
| Dryer / Crystallizer / Evaporator | `*_metrics` | humedad in/out, evaporado, producto seco / soluto, yield, cristales, licor madre / factor conc., sólidos %, evaporado, concentrado |
| Mech. sep. (decanter/ciclón/centrífuga/filtro) | `mech_sep_metrics` | tipo, fase objetivo, η recuperación, T/P |
| Mixer / Splitter | `mixer_metrics` / `splitter_metrics` | entradas/salida con T, cierre Σin=out / fracciones efectivas por salida |
| Hidráulica (rotativos) | `hydraulic_breakdown_metrics` | ΔP total + desglose por elemento aguas abajo |
| Balances (todo bloque) | `mass_balance_metrics`, `energy_balance_metrics`, `atom_balance_chip` | Σin/Σout/ΔM con cierre; H_in/H_out/ΔH/Q/W con cierre; chip elemental |

### 2.6 Costos y materiales

`bare_module_cost(eq, S, P, year, material)` → `{Cp_base, Cp_target,
year_base/target, cepci_factor, fuera_rango, S, S_min/max/unit, FBM,
FBM_CS_atm, FP, FM, CBM, unknown, material}`.
`suggested_material(comps, P, eq_type)` → CS…Tantalum vía `CORROSIVE_SPECIES`
(12 especies) + regla H₂/alta P; fired heaters siempre CS. El export ya emite
`Material (origen)` explicando la heurística u override (`b.material`).
Factores: `MATERIAL_FACTORS` (12 FM), `FP_COEFFS_BY_CAT` (7 categorías +
forma recipiente a presión), `B1_B2_BY_CATEGORIA` (22).

### 2.7 Auxiliares por eq_type (`equipment_auxiliaries.AUX_STREAMS`)

| eq_types | Servicios (puerto, dirección, fase, lazo) |
|---|---|
| HX shell-tube (8 tipos) | CW lazo cerrado `shell_in/out` |
| air cooler, condenser air-cooled | aire ambiente in/out (abierto) |
| kettle reboiler | steam_LP in + condensado out (lazo) |
| Reactores jacketed (2) | CW chaqueta lazo cerrado |
| Fired heaters (2) | fuel_gas in + flue gas a chimenea |
| Boilers (2) | BFW in, fuel in, blowdown out, flue gas out |
| Cooling towers (2) | makeup in, blowdown out, evaporación out |

Los lazos llevan bomba de circulación auto_aux (head 20-25 m, η 0.65).
Utilities resolubles (`equipment_ports.UTILITIES`, 11): steam LP/MP/HP,
fuel_gas, cooling_water, refrigeration, bfw_to_steam_*, electricity(_generated)
— con rango de T, Δh y precio (perfil regional `econ_defaults`, default PE_2024).

### 2.8 Export actual (precedente)

`collect_equipment_rows`: Tag, Type, Category, Size S, Unit, N° units, Duty,
T_op, P_op, ΔP, η, Reactions, Heat source, Material (+origen), FM, FP, FBM,
Cp, CBM, S-fuera-rango + specs condicionales de columna (LK/HK/R/N/Q_reb/
Q_cond/q/method/convergencia WH), flash (T/P) y splitter (fracciones).
Unidades de display dinámicas vía `flowsheet_units` (5 sistemas; canónicas:
tm/año, °C, bar, kW).

### 2.9 Hidráulica

`hydraulic_defaults._DP_RULES`: ΔP típica por tipo (air cooler −0.3 … packed
−1.0; rotativos None = auto). `pressure_drop.stream_pressure_drop` por
corriente-tubería: `delta_P (fric/local), velocity, Re, f_Darcy, regime`
(+ compresible: P_out, velocidades in/out, near_sonic). `K_TYPICAL` con 17
accesorios.

---

## 3. Datos calculados pero DESCARTADOS (recuperación prioritaria)

Los sizers calculan y tiran estos valores (hoy solo retornan el float S).
Recuperarlos es barato (ya están computados) y son datos primarios de ficha:

1. **Bombas** — `size_pump` descarta 11 campos de `pump_sizing` (head, NPSHa/r,
   margen cavitación, Q, N_s, rodete, η, W_hyd/shaft, rpm). *Mitigación actual:
   `pump_metrics` los recomputa llamando a `design_pump_for_block` — duplicado.*
2. **Compresores** — ídem: ratio, T descarga, W_isen, head, Q succión, η.
3. **Columnas** — `size_tower` descarta **D (diámetro), H (altura), N_real,
   v_max Souders-Brown, ρ_v, ρ_l** y solo retorna el volumen. El diámetro y la
   altura son datos primarios de una ficha de columna y hoy se pierden.
4. **HX** — parámetros R y P de Bowman (del factor F) no entran al diag.
5. **Sistemático en sizers volumétricos** — `m_s` (kg/s), `ρ` (kg/m³) y τ
   (residencia) se calculan y descartan en reactor, vessel, tank, crystallizer,
   filter (también Q_m3_h), mixer, centrifuge, cooling tower (ΔT, duty estim.),
   cyclone, fan, valve, evaporator (U y ΔT usados), WHB (Δh_vap, η, utility).
6. **Tuberías** — velocity, Re, f, régimen y desglose fricción/accesorios
   cuando el caller solo lee `delta_P_bar`.

---

## 4. Contrato propuesto — `datasheet_spec(block, fs) -> dict`

Módulo nuevo `datasheet.py`, **Qt-free** (mismo estatus que
`inspector_evidence`), una entrada por bloque. Regla de oro heredada del
proyecto: **cada campo lleva procedencia** y la ficha solo muestra lo que el
sistema respalda.

```python
{
  "schema": 1,
  "identidad":  {tag, nombre, eq_type, categoria, servicio, n_paralelo,
                 marca?, modelo?, proveedor?},   # equipo comercial (§4.1)
  "condiciones":{T_op_C, P_op_bar, duty_kW, delta_p_bar, fases},      # efectivas (solver)
  "corrientes": {"in": [...], "out": [...]},   # por corriente: nombre, puerto, rol,
                                               # ṁ, T, P, fase, comp. principal, wt% top-N
  "diseno":     [ {key, label, value, unit, origen, sub?} ],  # por categoría, ver §4.2
  "materiales": {material, origen_material, FM},
  "auxiliares": [ {utility, puerto, direccion, fase, lazo, consumo?} ],
  "costos":     {correlacion, source, S, S_unit, fuera_rango,
                 Cp_target, year_target, FP, FBM, CBM},
  "notas":      {warnings[], fuentes[], pendiente_detalle[]},
}
```

**Vocabulario `origen` por campo** (extiende la procedencia sudoku existente
▪ declarada / ◦ solver): `declarado` (spec del usuario) · `calculado` (solver/
sizing) · `tipico` (tabla U_TYPICAL, τ, ΔP rules — citando tabla) · `estimado`
(heurística, p. ej. ρ=1000) · `pendiente` (ingeniería de detalle).

**Campos mecánicos que el simulador NO determina** (espesores, bridas, código
ASME, tipo TEMA, corrosion allowance): no se muestran como celdas vacías; van
en `notas.pendiente_detalle` como lista corta fija por categoría — la ficha es
honesta sobre su alcance conceptual (Class 4/5, AACE).

### 4.1 Modo diseño vs modo selección (equipo comercial)

La ficha soporta DOS posturas del mismo motor — **la matemática existente no
se reemplaza; se invierte qué es entrada y qué es salida**:

- **Modo diseño** (actual): el proceso manda; sizing calcula el equipo
  requerido (S, head, área…). Todos los campos de diseño llevan
  `origen=calculado`.
- **Modo selección (rating)**: el usuario trae un equipo real a la mesa —
  **marca, modelo, proveedor** — y sus parámetros pasan a `origen=declarado`
  (S/área/head/η fijados). El motor pasa a **verificar**: requerido vs
  instalado → % de sobrediseño o warning de subdimensionado. Cambian las
  variables de entrada en la UI del bloque (lo declarado se edita, lo
  verificado se muestra) y cambia el veredicto de la ficha.

Ganchos que YA existen para esto (no requiere tocar el solver): `S_locked`,
`U_override`, `dtlm_override`, `efficiency`, `material` (override),
`duty_locked`, `n`. "Seleccionar equipo comercial" = empaquetar esos
overrides bajo una identidad. Piezas nuevas necesarias:

1. Campos en `Block`: `vendor_brand`, `vendor_model`, `vendor_ref`
   (serializados, opcionales; vacíos = modo diseño, sin cambio de
   comportamiento).
2. Comparador requerido-vs-instalado en `datasheet.py`:
   `sobrediseño = (S_declarado − S_requerido) / S_requerido`, con umbral de
   warning si es negativo (el S_requerido sale del sizer actual, que sigue
   corriendo aunque S esté locked).

   **Semántica del S comercial** (`data/equipos_comerciales.json`): S es la
   **capacidad nominal o máxima publicada del modelo** en la S_unit de su
   eq_type — la ENVOLVENTE, no un punto de operación. Desde el esquema v2
   hay DOS caminos de verificación, y el segundo no es un error ni un caso
   degradado:

   **Con `S`:** verificación escalar. `sobrediseño = (S_declarado −
   S_requerido)/S_requerido`, warning si negativo. Sin cambios. S no
   basta: `P_max_bar`, `T_max_C`, `Q_max_m3_h`, `head_max_m` son
   dimensiones adicionales de la misma envolvente — la verificación
   completa es un AND de desigualdades.

   **Con `S_no_publicado`:** verificación por envolvente. AND de
   desigualdades sobre los params presentes (P_max, T_max, Q_max,
   head_max…). El sobrediseño **NO es calculable** — no hay escalar de
   tamaño contra el cual compararse. Ese es un tercer estado legítimo de
   la ficha: *"verificado por envolvente, sobredimensionamiento no
   determinable"*. No mostrarlo como campo vacío ni como advertencia.

   La verificación por envolvente tiene además DOS calidades, según el
   campo `granularidad` de la entrada, y la ficha debe distinguirlas:

   - `granularidad: "modelo"` → *"verificado por envolvente del modelo"*.
   - `granularidad: "familia"` → *"verificación DÉBIL: la envolvente es
     del rango completo, no de este tamaño. Un resultado APTO aquí no
     confirma que el equipo sea adecuado."* No renderizar como tilde
     verde.

   **Restricción dura**: el S del catálogo comercial NUNCA se escribe en
   `Block.S`. `Block.S` sigue viniendo del sizing del simulador; el S
   comercial entra solo a la verificación y a la ficha. Volcarlo al bloque
   haría que el costeo Turton use el techo del bastidor e infle el CAPEX
   sistemáticamente.
3. Opcional (fase posterior): catálogo `data/equipos_comerciales.json` con
   entradas {marca, modelo, eq_type, parámetros} para poblar la selección
   con un click en lugar de tipear overrides. La ficha solo consume los
   campos del Block, así que el catálogo es aditivo.

En la ficha: la identidad muestra marca/modelo cuando existen; la sección
diseño distingue declarado (▪) de verificado (◦) campo a campo; la sección
notas suma el veredicto de rating.

### 4.2 Campos de `diseno` por categoría (todos ya disponibles o recuperables §3)

| Categoría | Campos de la ficha |
|---|---|
| HX / fired / WHB | A [m²] (o duty), U, ΔTlm, F, approach vs dT_min, n_shell/n_tube, servicio+cross-check, T 4 puntos; WHB: vapor kg/h @ P_range; fired: duty | 
| Bomba | Q, head, W_hyd/shaft/elec, η_total, NPSHa, NPSHr, margen cavitación, N_s + rodete, rpm, ΔP |
| Compresor / fan | ratio (por etapa), n etapas, Q intercool, Q succión, head kJ/kg, T descarga, W_isen/act, η; turbina: W generada |
| Columna | N teór./real, R (y R_min), N_feed, α_avg, q, **D y H (recuperar de size_tower)**, v_max SB, Q_reb/Q_cond, método (FUG/WH), convergencia WH, LK/HK, x_D/x_B |
| Reactor | modo, V, τ, T/P op, conversión, ΔH_rx (exo/endo), perfil (referencia a figura), tabla estequiométrica |
| Flash / vessel | T/P, V/F, V; tabla z/x/y/K |
| Tanque / storage | V, τ residencia, tipo de techo |
| Boiler | vapor t/h @ P, T BFW→vapor, duty, específica, η |
| Evaporator / dryer / crystallizer | factor conc. / humedades / yield + flujos de las salidas especiales, U·ΔT usados |
| Mech. sep. / cyclone / centrifuge / filter | tipo, fase objetivo, η recuperación, Q (filter: A y flux) |
| Valve | ΔP, C_v, VF salida (alerta flasheo) |
| Mixer / splitter | entradas/salidas con cierre / fracciones efectivas |
| Cooling tower | duty MW, makeup/blowdown/evaporación |
| Turbina / expansor | ratio de expansión, T entrada/descarga, W generada, η isentrópica (evidencia `_expander_case` ya cubre los tipos formales Turbine) |
| **Fallback genérico (los 60)** | identidad + condiciones + corrientes + S + material + costo — garantiza cobertura total desde el día uno |

Secciones transversales en toda ficha: balances de masa/energía con cierre
(`mass/energy_balance_metrics`) y, si hay reacción, balance de átomos.

---

## 5. Cobertura esperada por familia

- **Ficha rica** (sección diseño profunda + tablas de libro): HX, bombas,
  compresores, columnas, reactores, flash, boilers, WHB.
- **Ficha media**: tanques, evaporadores, dryers, crystallizers, mech. sep.,
  válvulas, cooling towers, fans.
- **Ficha mínima honesta** (fallback): mixers, splitters, trays/packing
  (componentes de columna, sin sizer propio), relief/3-way.

La despareja profundidad es **deliberada y honesta** — refleja qué modela el
simulador, no un defecto de la ficha.

---

## 6. Plan de implementación (tandas = PRs)

1. **`datasheet.py`** — agregador Qt-free + recuperación de descartados §3
   (los sizers pasan a poblar un diag como ya hace `size_heat_exchanger`) +
   campos `vendor_*` en Block + comparador requerido-vs-instalado (§4.1) +
   test que recorre todos los ejemplos y exige ficha válida para cada bloque.
2. **Sección "Ficha" del inspector** — clave en `_sections_for` + builder,
   render con `SpecField`/`BookTable`/`MetricCard` según el bundle de Design;
   incluye la UI de selección de equipo comercial (variables de entrada
   cambian cuando hay marca/modelo declarados).
3. ✅ **Export XLSX** — HECHO (2026-07-25). Hoja índice + una hoja por
   equipo, en `datasheet_export.write_datasheets_xlsx`. **Desvío del plan:
   NO se extendió `write_project_xlsx`.** Ese libro es el que importa
   ANA.py y tiene su propio contrato (capital/fixed/variable); meterle
   hojas de ficha lo volvería dos documentos en uno y ataría el formato de
   la ficha al del modelo económico. Las fichas viven en su propio libro.
4. ✅ **Export PDF multipágina** — HECHO (2026-07-25).
   `datasheet_export.write_datasheets_pdf`: una ficha por página A4,
   encabezado proyecto · rev △N · fecha, y página final de historial de
   revisiones cuando el flowsheet tiene alguna (deuda 4d del ciclo 4).
   Detalle de implementación: `QPdfWriter` directo en vez del `QPrinter`
   del export de PFD — no hay escena que renderizar, se pinta texto, y así
   el módulo no depende de `QtPrintSupport`.

   Ver `docs/REDISENO_CICLO5_2026-07.md` para las decisiones (contenido
   único compartido por ambos formatos) y para el bug que el export
   destapó en el mensaje del veredicto.

La especificación visual (anatomía de la ficha, jerarquía, papel de export)
la decide Claude Design: ver `docs/PROMPT_DESIGN_CICLO5_FICHAS.md`.
