# Matriz de auditoría frontend por eq_type

Generada por `audit_frontend_matrix.py` — regenerar, no editar.

| eq_type | ejemplo | #inst | evidencia específica | glyph | puertos | sizer |
|---|---|---:|---|:-:|---:|:-:|
| Heat exch. — fixed tube | sugar | 3 | hx_metrics, hx_text | ✓ | 6 | ✓ |
| Heat exch. — U-tube | reformer_whb | 1 | hx_metrics, hx_text | ✓ | 6 | ✓ |
| Heat exch. — floating head | hda | 60 | hx_metrics, hx_text | ✓ | 6 | ✓ |
| Heat exch. — kettle reboiler | hda | 12 | boiler_text, hx_metrics, hx_text | ✓ | 6 | ✓ |
| Heat exch. — double pipe | cw_natural | 1 | hx_metrics, hx_text | ✓ | 6 | ✓ |
| Heat exch. — multiple pipe | cw_natural | 1 | hx_metrics, hx_text | ✓ | 6 | ✓ |
| Heat exch. — air cooler | hda | 16 | hx_metrics, hx_text | ✓ | 6 | ✓ |
| Heat exch. — condenser shell-tube | solvent_rec | 1 | hx_metrics, hx_text | ✓ | 6 | ✓ |
| Heat exch. — condenser air-cooled | solvent_rec | 1 | hx_metrics, hx_text | ✓ | 6 | ✓ |
| Heat exch. — flat plate | cw_natural | 1 | hx_metrics, hx_text | ✓ | 6 | ✓ |
| Heat exch. — spiral plate | solvent_rec | 1 | hx_metrics, hx_text | ✓ | 6 | ✓ |
| Heat exch. — WHB packaged | methanol | 14 | hx_metrics, hx_text | ✓ | 6 | ✓ |
| Heat exch. — WHB field erected | reformer_whb | 1 | hx_metrics, hx_text | ✓ | 6 | ✓ |
| Compressor — centrifugal | hda | 25 | compressor_text, hydraulic_text | ✓ | 5 | ✓ |
| Compressor — axial | hno3 | 3 | compressor_text | ✓ | 5 | ✓ |
| Compressor — reciprocating | ldpe | 1 | compressor_text, hydraulic_text | ✓ | 5 | ✓ |
| Compressor — rotary | solvent_rec | 1 | compressor_text | ✓ | 5 | ✓ |
| Turbine — steam | steam_turbine | 1 | compressor_text | ✓ | 5 | ✓ |
| Turbine — gas (axial) | gas_expander | 1 | compressor_text | ✓ | 5 | ✓ |
| Turbine — radial expander | gas_expander | 1 | compressor_text | ✓ | 5 | ✓ |
| Pump — centrifugal | hda | 70 | hydraulic_text, pump_metrics, pump_text | ✓ | 3 | ✓ |
| Pump — positive displacement | leche_gloria | 1 | hydraulic_text, pump_metrics, pump_text | ✓ | 3 | ✓ |
| Pump — reciprocating | cw_natural | 1 | pump_metrics, pump_text | ✓ | 3 | ✓ |
| Vessel — horizontal | gas_sweet | 4 | splitter_metrics, splitter_text | ✓ | 9 | ✓ |
| Vessel — vertical | hda | 67 | mech_sep_metrics, mech_sep_text | ✓ | 9 | ✓ |
| Tower (column shell) | hda | 20 | column_design_text, column_duties_text, mccabe_text, profile_text | ✓ | 12 | ✓ |
| Storage tank — cone roof | industrial | 6 | tank_metrics, tank_text | ✓ | 6 | ✓ |
| Storage tank — floating roof | talara | 1 | tank_metrics, tank_text | ✓ | 6 | ✓ |
| Reactor — autoclave | quimpac | 11 | reactor_metrics, reactor_text | ✓ | 9 | ✓ |
| Reactor — jacketed agitated | ethanol | 12 | reactor_metrics, reactor_text | ✓ | 9 | ✓ |
| Reactor — jacketed non-agit. | hda | 13 | reactor_metrics, reactor_text | ✓ | 9 | ✓ |
| Reactor — PFR (tubular) | pfr | 3 | reactor_metrics, reactor_text | ✓ | 9 | ✓ |
| Reactor — CSTR (agitado) | parallel | 3 | reactor_metrics, reactor_text | ✓ | 9 | ✓ |
| Fired heater — reformer | reformer_whb | 1 | hx_metrics, hx_text | ✓ | 7 | ✓ |
| Fired heater — non-reformer | hda | 17 | hx_metrics, hx_text | ✓ | 7 | ✓ |
| Crystallizer | sugar | 2 | crystallizer_text | ✓ | 7 | ✓ |
| Dryer — drum | sugar | 2 | dryer_text | ✓ | 7 | ✓ |
| Evaporator — vertical | sugar | 15 | evaporator_text | ✓ | 7 | ✓ |
| Filter — belt | sugar | 5 | mech_sep_metrics, mech_sep_text | ✓ | 7 | ✓ |
| Fan — centrifugal radial | blower | 1 | compressor_text | ✓ | 5 | ✓ |
| Fan — axial | cw_natural | 1 | compressor_text | ✓ | 5 | ✓ |
| Tray — sieve | — | 0 | — | ✓ | 2 | ✗ |
| Tray — valve | — | 0 | — | ✓ | 2 | ✗ |
| Packing — random | — | 0 | — | ✓ | 2 | ✗ |
| Packing — structured | — | 0 | — | ✓ | 2 | ✗ |
| Mixer — impeller | agitated_blend | 1 | mixer_text | ✓ | 8 | ✓ |
| Mixer — inline | cw_natural | 1 | mixer_text | ✓ | 8 | ✓ |
| Mixer — static | smr_eq | 19 | mixer_text | ✓ | 8 | ✓ |
| Splitter — flow divider | bypass | 3 | splitter_metrics, splitter_text | ✓ | 8 | ✓ |
| Centrifuge — disc stack | leche_gloria | 2 | mech_sep_metrics, mech_sep_text | ✓ | 5 | ✓ |
| Centrifuge — decanter | solvent_rec | 1 | mech_sep_metrics, mech_sep_text | ✓ | 5 | ✓ |
| Cyclone — gas/solid | cyclone | 1 | mech_sep_metrics, mech_sep_text | ✓ | 5 | ✓ |
| Decanter — gravity | biodiesel | 2 | mech_sep_metrics, mech_sep_text | ✓ | 6 | ✓ |
| Valve — control globe | letdown | 1 | valve_text | ✓ | 3 | ✓ |
| Valve — relief | cw_natural | 1 | valve_text | ✓ | 3 | ✓ |
| Valve — 3-way | cw_natural | 1 | splitter_metrics, splitter_text, valve_text | ✓ | 8 | ✓ |
| Boiler — fire tube | boiler_ft | 1 | boiler_text | ✓ | 5 | ✓ |
| Boiler — water tube | rankine | 1 | boiler_text | ✓ | 5 | ✓ |
| Cooling tower — induced draft | cooling | 2 | splitter_metrics, splitter_text | ✓ | 5 | ✓ |
| Cooling tower — natural draft | cw_natural | 1 | splitter_metrics, splitter_text | ✓ | 5 | ✓ |
