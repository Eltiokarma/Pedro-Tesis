"""Traceable theoretical cases and an independent linear four-inventory oracle.

No external simulator is executed here. Published parameters, adaptations and
new numerical stress cases are explicitly distinguished in provenance.
"""
from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import numpy as np
from scipy.linalg import expm


ENERGYPLUS_TEST_URL = (
    "https://github.com/NatLabRockies/EnergyPlus/blob/v24.2.0/"
    "tst/EnergyPlus/unit/WaterThermalTanks.unit.cc#L1060"
)
MODELICA_SOURCE_URL = (
    "https://github.com/modelica/ModelicaStandardLibrary/blob/v4.1.0/"
    "Modelica/Fluid/Examples/HeatingSystem.mo"
)
TEMPERATURES = (
    "tank_temperature_K", "wall_temperature_K", "jacket_temperature_K",
    "utility_reservoir_temperature_K",
)
ENERGYPLUS_PARAMETERS = {
    "mass_kg": 148.67, "cp_J_kg_K": 4183.9,
    "initial_temperature_K": 330.37, "ambient_temperature_K": 292.87,
    "return_temperature_K": 287.59, "mass_flow_kg_s": 0.06761,
    "ua_ambient_W_K": 5.0, "heater_heat_W": 0.0, "duration_s": 269.2,
    "published_integral_C_s": 14716.6, "published_tolerance_C_s": 0.1,
    "published_adiabatic_1000W_integral_C_s": 15461.9,
}


def _base():
    from dynamic_tank import default_thermal_loop_case

    case = default_thermal_loop_case()
    case["controller"]["enabled"] = False
    case["instrumentation"]["valve_actuator"]["enabled"] = False
    for sensor in case["instrumentation"]["temperature_sensors"].values():
        sensor.update(time_constant_s=0.0, bias_K=0.0)
    case["inputs"]["agitator_power_W"] = 0.0
    case["simulation"].update(duration_s=1800.0, output_interval_s=10.0,
                              max_step_s=10.0, rtol=1e-8, atol=1e-9)
    case["provenance"] = {
        "data_kind": "synthetic", "source": MODELICA_SOURCE_URL,
        "notes": "Adaptación teórica propia de un circuito cerrado; no reproduce "
                 "curvas de Modelica ni procede de una planta. Parámetros propios.",
    }
    return case


def example_cases():
    """Return JSON-ready inputs; never silently recreate missing source cases."""
    coupled = _base()
    coupled.update(case_id="theoretical-closed-thermal-loop",
                   title="Circuito cerrado: calentador finito y retorno térmico")
    coupled["inputs"].update(heater_power_request_W=4500.0, valve_opening=0.55,
                              feed_flow_kg_s=0.08, outlet_flow_kg_s=0.08)
    coupled["events"] = [
        {"time_s": 600.0, "changes": {"heater_power_request_W": 0.0}},
        {"time_s": 1000.0, "changes": {"pump_speed_fraction": 0.0}},
        {"time_s": 1300.0, "changes": {"pump_speed_fraction": 1.0,
                                             "heater_power_request_W": 4500.0}},
    ]

    heating = _base()
    heating.update(case_id="energyplus-published-adiabatic-heating",
                   title="EnergyPlus: depósito adiabático con 1000 W")
    heating["provenance"] = {
        "data_kind": "synthetic", "source": ENERGYPLUS_TEST_URL,
        "notes": "Reproducción de parámetros de una prueba numérica publicada "
                 "v24.2.0, no comparación ejecutada contra EnergyPlus. Los otros "
                 "inventarios están desacoplados y constantes.",
    }
    heating["utility_loop"].update(mass_kg=148.67, initial_temperature_K=330.37,
        ua_ambient_W_K=0.0, heater_max_power_W=1000.0, heater_efficiency=1.0)
    heating["jacket"]["cp_J_kg_K"] = 4183.9
    heating["inputs"].update(pump_speed_fraction=0.0, heater_power_request_W=1000.0)
    heating["wall"].update(ua_tank_W_K=0.0, ua_jacket_W_K=0.0, ua_ambient_W_K=0.0)
    heating["simulation"].update(duration_s=269.2, output_interval_s=1.0)

    limited = _base()
    limited.update(case_id="theoretical-insufficient-heater-power",
                   title="Potencia insuficiente: equilibrio térmico y saturación")
    limited["provenance"]["source"] = ENERGYPLUS_TEST_URL
    limited["provenance"]["notes"] = (
        "Extensión teórica propia del balance de depósito de EnergyPlus; "
        "masa 10 kg, UA 20 W/K, potencia 100 W y perturbaciones propios. "
        "No representa una instalación publicada ni datos experimentales."
    )
    limited["utility_loop"].update(mass_kg=10.0, initial_temperature_K=298.15,
        ua_ambient_W_K=20.0, heater_max_power_W=100.0, heater_efficiency=1.0)
    limited["inputs"].update(pump_speed_fraction=0.0, heater_power_request_W=1000.0,
                              ambient_temperature_K=298.15, temperature_setpoint_K=323.15)
    limited["wall"].update(ua_tank_W_K=0.0, ua_jacket_W_K=0.0, ua_ambient_W_K=0.0)
    limited["simulation"].update(duration_s=12000.0, output_interval_s=60.0, max_step_s=30.0)
    controlled = _base()
    controlled.update(case_id="theoretical-coupled-capacity-limit",
                      title="Circuito acoplado: PI saturado y capacidad insuficiente")
    controlled["provenance"]["notes"] = (
        "Caso teórico propio de cuatro inventarios acoplados. PI de temperatura "
        "del proceso y calentador saturados; parámetros propios, no datos de planta."
    )
    controlled["tank"].update(initial_mass_kg=10.0, initial_temperature_K=298.15)
    controlled["wall"].update(heat_capacity_J_K=4500.0, initial_temperature_K=298.15)
    controlled["jacket"].update(mass_kg=5.0, initial_temperature_K=298.15)
    controlled["utility_loop"].update(mass_kg=10.0, initial_temperature_K=298.15,
        ua_ambient_W_K=20.0, heater_max_power_W=1000.0, heater_efficiency=0.98)
    controlled["inputs"].update(feed_flow_kg_s=0.05, outlet_flow_kg_s=0.05,
        feed_temperature_K=298.15, ambient_temperature_K=298.15,
        heater_power_request_W=5000.0, valve_opening=1.0, temperature_setpoint_K=323.15)
    controlled["controller"]["enabled"] = True
    controlled["simulation"].update(duration_s=6000.0, output_interval_s=20.0)
    return {"coupled_disturbances.json": coupled, "energyplus_adiabatic.json": heating,
            "insufficient_power.json": limited, "coupled_capacity_limit.json": controlled}


def reference_hydraulics(case, inputs):
    """Elementary curve intersection; deliberately independent of production.

    Restricted to the moderate, positive coefficients used by the reference
    examples, not an extreme-floating-point replacement for the production API.
    """
    pump, circuit = case["pump"], case["circuit"]
    opening, speed = inputs["valve_opening"], inputs["pump_speed_fraction"]
    if opening == 0 or speed == 0:
        return 0.0, 0.0
    if circuit["static_head_m"] != 0:
        raise ValueError("The reference assumes zero net static lift in the closed circuit")
    resistance = pump["curve_coefficient_s2_m5"] + circuit["resistance_s2_m5"]
    resistance += 1e5 / (1000.0 * 9.80665) * (3600.0 / (circuit["valve_kv_m3_h"] * opening)) ** 2
    flow = math.sqrt(pump["shutoff_head_m"] * speed ** 2 / resistance)
    head = pump["shutoff_head_m"] * speed ** 2 - pump["curve_coefficient_s2_m5"] * flow ** 2
    hydraulic = case["jacket"]["density_kg_m3"] * 9.80665 * flow * head
    shaft = hydraulic / pump["efficiency"]
    heat = hydraulic + (shaft - hydraulic) * case["utility_loop"]["pump_loss_to_fluid_fraction"]
    return case["jacket"]["density_kg_m3"] * flow, heat


def reference_temperatures(case, times):
    """Solve four independently assembled constant-inventory balances exactly.

    Exponential matrices are evaluated per event interval. No production RHS,
    hydraulic solver, derivative, Jacobian or integration routine is reused.
    Feedback and actuator lag are excluded because they break linearity.
    """
    if case["schema_version"] != "dynamic-tank/v3":
        raise ValueError("The four-inventory oracle requires dynamic-tank/v3")
    if case["controller"]["enabled"] or case["instrumentation"]["valve_actuator"]["enabled"]:
        raise ValueError("The linear reference requires manual control and an ideal actuator")
    sample_times = [float(t) for t in times]
    if any(not math.isfinite(t) or t < 0 or t > case["simulation"]["duration_s"] for t in sample_times):
        raise ValueError("Reference sample times must lie within the simulation")
    if sample_times != sorted(set(sample_times)):
        raise ValueError("Reference sample times must be unique and increasing")
    tank, wall, jacket, utility = (case[name] for name in ("tank", "wall", "jacket", "utility_loop"))
    capacities = np.array([tank["initial_mass_kg"] * tank["cp_J_kg_K"], wall["heat_capacity_J_K"],
                          jacket["mass_kg"] * jacket["cp_J_kg_K"], utility["mass_kg"] * jacket["cp_J_kg_K"]])
    state = np.array([tank["initial_temperature_K"], wall["initial_temperature_K"],
                      jacket["initial_temperature_K"], utility["initial_temperature_K"], 1.0])
    inputs = copy.deepcopy(case["inputs"])
    events = iter(sorted(case["events"], key=lambda event: event["time_s"]))
    event = next(events, None)
    current = 0.0
    outputs = []

    def matrix():
        if inputs["feed_flow_kg_s"] != inputs["outlet_flow_kg_s"]:
            raise ValueError("The exponential reference requires a constant process inventory")
        flow, pump_heat = reference_hydraulics(case, inputs)
        fc = flow * jacket["cp_J_kg_K"]
        feed = inputs["feed_flow_kg_s"] * tank["cp_J_kg_K"]
        ut, uj, ua = (wall[name] for name in ("ua_tank_W_K", "ua_jacket_W_K", "ua_ambient_W_K"))
        ur = utility["ua_ambient_W_K"]
        power = min(inputs["heater_power_request_W"], utility["heater_max_power_W"]) * utility["heater_efficiency"]
        a = np.zeros((5, 5))
        a[:4, :4] = [[-ut-feed, ut, 0, 0], [ut, -ut-uj-ua, uj, 0],
                       [0, uj, -uj-fc, fc], [0, 0, fc, -fc-ur]]
        a[:4, 4] = [feed * inputs["feed_temperature_K"] + inputs["agitator_power_W"],
                     ua * inputs["ambient_temperature_K"], 0,
                     power + pump_heat + ur * inputs["ambient_temperature_K"]]
        a[:4] /= capacities[:, None]
        return a

    for time in sample_times:
        while event is not None and event["time_s"] <= time:
            boundary = float(event["time_s"])
            if boundary < current:
                raise ValueError("Reference events must be nonnegative and ordered")
            state = expm(matrix() * (boundary-current)) @ state
            current = boundary
            inputs.update(event["changes"])
            event = next(events, None)
        state = expm(matrix() * (time-current)) @ state
        current = time
        outputs.append(state[:4].copy())
    return np.array(outputs)


def reference_steady_temperatures(case):
    """Independent four-node steady energy balance for fixed manual inputs."""
    if case["controller"]["enabled"] or case["events"]:
        raise ValueError("The equilibrium reference requires fixed manual inputs")
    inputs, wall, utility = case["inputs"], case["wall"], case["utility_loop"]
    if inputs["feed_flow_kg_s"] != inputs["outlet_flow_kg_s"]:
        raise ValueError("The equilibrium reference requires constant inventory")
    flow, pump_heat = reference_hydraulics(case, inputs)
    fc = flow * case["jacket"]["cp_J_kg_K"]
    feed = inputs["feed_flow_kg_s"] * case["tank"]["cp_J_kg_K"]
    ut, uj, ua = (wall[name] for name in ("ua_tank_W_K", "ua_jacket_W_K", "ua_ambient_W_K"))
    ur = utility["ua_ambient_W_K"]
    power = min(inputs["heater_power_request_W"], utility["heater_max_power_W"]) * utility["heater_efficiency"]
    coefficients = np.array([[-ut-feed, ut, 0, 0], [ut, -ut-uj-ua, uj, 0],
                             [0, uj, -uj-fc, fc], [0, 0, fc, -fc-ur]])
    sources = np.array([feed*inputs["feed_temperature_K"] + inputs["agitator_power_W"],
                        ua*inputs["ambient_temperature_K"], 0,
                        power+pump_heat+ur*inputs["ambient_temperature_K"]])
    return np.linalg.solve(coefficients, -sources)


def write_examples(folder=None):
    target = Path(folder) if folder is not None else Path(__file__).resolve().parent / "data/thermal_loop_examples"
    target.mkdir(parents=True, exist_ok=True)
    for filename, case in example_cases().items():
        (target / filename).write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    metadata = {
        "classification": "published_numerical_test_parameters_not_measurements",
        "source_url": ENERGYPLUS_TEST_URL, "source_version": "v24.2.0",
        "source_blob_sha": "dcc74d48ce4f02eb4d465633336f6d24414d13d3",
        "test_name": "WaterThermalTank_CalcTempIntegral", "parameters": ENERGYPLUS_PARAMETERS,
        "note": "Temperatures converted from Celsius; integrals published in Celsius-seconds. No EnergyPlus binary was executed.",
    }
    (target / "energyplus_reference.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    write_examples()
