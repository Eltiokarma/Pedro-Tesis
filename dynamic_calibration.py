"""Bounded thermal-parameter estimation with experiments reserved for validation.

Only calibration observations enter the weighted least-squares objective.
Validation criteria describe held-out prediction errors; they never certify a
plant model. Sensitivity diagnostics are local, numerical and scale-dependent.
"""
from __future__ import annotations

from collections import OrderedDict
import copy
import hashlib
import json
import math

import numpy as np
import scipy
from scipy.optimize import least_squares

from dynamic_measurements import _metrics
from dynamic_study import PARAMETER_UNITS, load_study
from dynamic_tank import MODEL_VERSION, simulate_dynamic_tank

SCHEMA_VERSION = "dynamic-calibration-result/v1"
JACOBIAN_STEP = 1e-4  # Fraction of each parameter's explicitly declared range.
CONDITION_WARNING = 1e6


class _Stopped(Exception):
    def __init__(self, reason, *, details=None):
        super().__init__(reason)
        self.reason = reason
        self.details = details or {}


def _json_hash(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False
    ).encode("utf-8")).hexdigest()


def _squared_norm(values):
    norm = math.hypot(*(float(value) for value in values))
    objective = norm * norm
    if not math.isfinite(objective):
        raise _Stopped("nonfinite_weighted_objective")
    return objective


def _case_at(experiment, parameters, values):
    case = copy.deepcopy(experiment["case"])
    for parameter, value in zip(parameters, values):
        section, key = parameter["path"].split(".")
        case[section][key] = float(value)
    return case


def _measurement_times(experiment, observables):
    return sorted({float(row["time_s"] + experiment["time_offset_s"])
                   for row in experiment["observations"]
                   if any(row["values"].get(name) is not None for name in observables)})


def _predictions(result, times, observables):
    by_time = {row["time_s"]: row for row in result["series"]}
    try:
        return {time: {name: float(by_time[time][name]) for name in observables}
                for time in times}
    except KeyError as exc:
        # Do not introduce a second, linear interpolation into the fit.
        raise _Stopped("requested_observation_time_missing") from exc


def _residuals(experiment, predicted, observables):
    errors = []
    for row in experiment["observations"]:
        aligned = float(row["time_s"] + experiment["time_offset_s"])
        for name, settings in observables.items():
            measured = row["values"].get(name)
            if measured is None:
                continue
            scale = row["uncertainties"].get(name, settings["scale_K"])
            error = (predicted[aligned][name] - measured) / scale
            if not math.isfinite(error):
                raise _Stopped("nonfinite_weighted_residual")
            errors.append(error)
    return np.asarray(errors, dtype=float)


def _experiment_metrics(experiment, predicted, observables):
    metrics = {}
    for name, settings in observables.items():
        errors, normalized = [], []
        for row in experiment["observations"]:
            measured = row["values"].get(name)
            if measured is None:
                continue
            time = float(row["time_s"] + experiment["time_offset_s"])
            error = predicted[time][name] - measured
            errors.append(error)
            scaled = error / row["uncertainties"].get(name, settings["scale_K"])
            if not math.isfinite(error) or not math.isfinite(scaled):
                raise _Stopped("nonfinite_comparison_metrics", details={"variable": name})
            normalized.append(scaled)
        try:
            metric = _metrics(errors)
            metric.update(unit="K", normalized_rmse=_metrics(normalized)["rmse"])
        except (ValueError, OverflowError) as exc:
            raise _Stopped("nonfinite_comparison_metrics", details={"variable": name}) from exc
        metrics[name] = metric
    return metrics


def _sensitivity_diagnostics(jacobian, n_parameters):
    try:
        singular = np.linalg.svd(jacobian, compute_uv=False)
    except np.linalg.LinAlgError as exc:
        raise _Stopped("sensitivity_decomposition_failed") from exc
    if not np.all(np.isfinite(singular)):
        raise _Stopped("nonfinite_sensitivity_matrix")
    largest = float(singular[0]) if len(singular) else 0.0
    threshold = max(1e-6, largest * 1e-6)
    rank = int(np.count_nonzero(singular > threshold))
    minimum = float(singular[-1]) if len(singular) else 0.0
    condition = float(largest / minimum) if minimum > 0 else None
    if condition is not None and not math.isfinite(condition):
        condition = None
    return {
        "rank": rank,
        "n_parameters": n_parameters,
        "scaled_jacobian_condition": condition,
        "singular_values": [float(value) for value in singular],
        "rank_tolerance": threshold,
        "column_response_norms": [math.hypot(*(float(value) for value in column))
                                  for column in jacobian.T],
        "minimum_scaled_singular_value": minimum,
        "weak_sensitivity": minimum <= 1.0,
        "weak_sensitivity_threshold": 1.0,
        "finite_difference_step_fraction_of_bounds": JACOBIAN_STEP,
        "parameter_scaling": "each_parameter_divided_by_its_declared_bound_width",
        "residual_scaling": "observation_standard_uncertainty_else_declared_scale_K",
        "scope": "local_numerical_sensitivity_not_structural_identifiability",
        "interpretation": (
            "Rank, condition and sensitivity depend on declared bounds and residual scales. "
            "The sensitivity threshold is a heuristic, not a confidence interval or a "
            "proof of parameter identifiability. Correlated errors are not modelled."
        ),
    }


def calibrate_study(study_path, *, cancel=None, progress=None):
    """Estimate shared thermal parameters and assess untouched validation trials.

    Invalid study inputs raise ValueError/OSError. Cancellation, budget exhaustion
    and incomplete simulations return a JSON-safe failed/partial report without
    exportable fitted cases. ``max_evaluations`` counts uncached residual evaluations,
    including numerical-Jacobian candidates; ``simulations_count`` counts every
    simulator call, including reporting/validation runs outside that budget.
    """
    study = load_study(study_path)
    parameters = study["parameters"]
    observables = study["observables"]
    experiments = study["experiments"]
    training = [experiment for experiment in experiments if experiment["role"] == "calibration"]
    limit = study["options"]["max_evaluations"]
    lower = np.asarray([parameter["lower"] for parameter in parameters], dtype=float)
    upper = np.asarray([parameter["upper"] for parameter in parameters], dtype=float)
    initial = np.asarray([parameter["initial"] for parameter in parameters], dtype=float)
    width = upper - lower
    if not np.all(np.isfinite(width)) or np.any(width <= 0):
        raise ValueError("Parameter ranges must have finite, positive widths.")
    x_initial = (initial - lower) / width
    times = {experiment["experiment_id"]: _measurement_times(experiment, observables)
             for experiment in experiments}
    all_synthetic = all(experiment["data_kind"] == "synthetic" for experiment in experiments)
    instrumented = experiments[0]["case"]["schema_version"] == "dynamic-tank/v2"
    report = {
        "schema_version": SCHEMA_VERSION,
        "study_id": study["study_id"],
        "equipment_id": study["equipment_id"],
        "summary": {
            "status": "failed", "optimization_converged": False,
            "usable_parameter_estimate": False,
            "evaluations": 0, "max_evaluations": limit, "simulations_count": 0,
            "objective_before": None, "objective_after": None,
            "validation_status": "not_assessed",
        },
        "parameters": [dict(parameter, value=parameter["initial"],
                            unit=PARAMETER_UNITS[parameter["path"]], at_bound=False)
                       for parameter in parameters],
        "diagnostics": {"rank": None, "n_parameters": len(parameters),
                        "scaled_jacobian_condition": None, "singular_values": []},
        "experiments": [],
        "warnings": [],
        "provenance": {
            **study["provenance"], "model_version": MODEL_VERSION,
            "numpy_version": np.__version__, "scipy_version": scipy.__version__,
            "optimization_method": "scipy_least_squares_trf_with_explicit_bounds",
            "objective": "sum_of_squared_scaled_calibration_residuals_only",
            "evaluation_budget": "uncached_residual_evaluations_including_numerical_jacobian",
            "sampling": "integrator_dense_output_at_aligned_observation_times",
            "validation_partition": "explicit_experiment_roles_not_random_row_split",
            "data_authenticity": "declared_by_user_not_independently_verified",
        },
        "validation_state": "synthetic_calibration_only" if all_synthetic else "unverified_against_plant",
        "conclusion": (
            "Numerical calibration and held-out criterion comparison only. Measurement "
            "authenticity, independence of trials, parameter identifiability and plant "
            "applicability require separate assessment. No plant certification is issued."
        ),
    }
    if instrumented:
        # A scope limitation is not a failed local estimate. Keep it distinct
        # from numerical/identification warnings that disable usability.
        report["scope_notes"] = [
            "Las constantes de tiempo, sesgos y límites del actuador son entradas declaradas fijas; "
            "el ajuste térmico no los estima ni valida la instrumentación.",
            "Las temperaturas físicas y las indicaciones del sensor son canales distintos; "
            "los residuos usan únicamente los canales seleccionados explícitamente en el estudio.",
        ]
        report["provenance"]["instrumentation_parameters"] = "declared_fixed_inputs_not_estimated_or_validated"
    experiment_reports = {}
    for experiment in experiments:
        entry = {
            "experiment_id": experiment["experiment_id"], "role": experiment["role"],
            "data_kind": experiment["data_kind"],
            "baseline_metrics": None, "fitted_metrics": None,
            "baseline_series": [], "fitted_series": [], "fitted_case": None,
            "simulation_summary": None,
            "provenance": {key: experiment[key] for key in (
                "case_file", "measurements_file", "source", "time_offset_s",
                "measurement_sha256", "measurement_canonical_sha256",
                "measurement_aligned_sha256", "case_sha256")},
        }
        report["experiments"].append(entry)
        if instrumented:
            entry["instrumentation"] = copy.deepcopy(experiment["case"]["instrumentation"])
        experiment_reports[experiment["experiment_id"]] = entry
    evaluations = simulations_count = 0
    cache = OrderedDict()
    best = {"objective": math.inf, "x": x_initial.copy()}

    def check_cancel():
        if cancel is not None and cancel():
            raise _Stopped("user_cancelled")

    def notify(phase, experiment_id=None, objective=None):
        report["summary"].update(evaluations=evaluations, simulations_count=simulations_count)
        if progress is not None:
            item = {"evaluations": evaluations, "max_evaluations": limit,
                    "simulations_count": simulations_count, "phase": phase,
                    "experiment_id": experiment_id}
            if objective is not None:
                item["objective"] = objective
            progress(item)

    def simulate(experiment, values, phase):
        nonlocal simulations_count
        check_cancel()
        case = _case_at(experiment, parameters, values)
        simulations_count += 1
        notify(phase, experiment["experiment_id"])
        try:
            result = simulate_dynamic_tank(
                case, cancel=cancel, sample_times_s=times[experiment["experiment_id"]]
            )
        except (ValueError, FloatingPointError, OverflowError) as exc:
            raise _Stopped("invalid_candidate_simulation", details={
                "experiment_id": experiment["experiment_id"], "phase": phase,
                "message": str(exc),
            }) from exc
        summary = result["summary"]
        if summary["status"] == "cancelled":
            raise _Stopped("user_cancelled")
        if summary["success"] is not True:
            raise _Stopped("incomplete_candidate_simulation", details={
                "experiment_id": experiment["experiment_id"], "phase": phase,
                "simulation_summary": summary, "diagnostics": result.get("diagnostics", []),
            })
        check_cancel()
        predicted = _predictions(result, times[experiment["experiment_id"]], observables)
        return predicted, result

    def objective(x, phase="calibration"):
        nonlocal evaluations
        check_cancel()
        key = tuple(float(value) for value in x)
        if key in cache:
            cache.move_to_end(key)
            return cache[key].copy()
        if evaluations >= limit:
            raise _Stopped("evaluation_budget_exceeded")
        evaluations += 1
        values = lower + np.asarray(x) * width
        parts = []
        for experiment in training:
            predicted, _ = simulate(experiment, values, phase)
            parts.append(_residuals(experiment, predicted, observables))
        residual = np.concatenate(parts)
        loss = _squared_norm(residual)
        if loss < best["objective"]:
            best.update(objective=loss, x=np.asarray(x).copy())
        cache[key] = residual.copy()
        # Bounded cache: records contain residual vectors, never full trajectories.
        while len(cache) > 8:
            cache.popitem(last=False)
        notify(phase, objective=loss)
        return residual

    def jacobian(x):
        check_cancel()
        columns = []
        for index in range(len(parameters)):
            low, high = np.array(x, copy=True), np.array(x, copy=True)
            low[index] = max(0., float(x[index]) - JACOBIAN_STEP)
            high[index] = min(1., float(x[index]) + JACOBIAN_STEP)
            derivative = ((objective(high, "jacobian") - objective(low, "jacobian"))
                          / (high[index] - low[index]))
            columns.append(derivative)
        result = np.column_stack(columns)
        if not np.all(np.isfinite(result)):
            raise _Stopped("nonfinite_sensitivity_matrix")
        return result

    def as_series(predicted):
        return [dict(time_s=time, **values) for time, values in predicted.items()]

    try:
        check_cancel()
        # Baselines are descriptive; none of these held-out residuals is passed
        # to the optimizer, Jacobian, stopping criterion or candidate selection.
        for experiment in experiments:
            predicted, result = simulate(experiment, initial, "baseline")
            entry = experiment_reports[experiment["experiment_id"]]
            entry["baseline_metrics"] = _experiment_metrics(experiment, predicted, observables)
            entry["baseline_series"] = as_series(predicted)
            entry["baseline_simulation_summary"] = result["summary"]
        baseline_residual = objective(x_initial)
        report["summary"]["objective_before"] = _squared_norm(baseline_residual)
        try:
            fitted = least_squares(
                objective, x_initial, jac=jacobian, bounds=(np.zeros(len(parameters)),
                                                           np.ones(len(parameters))),
                method="trf", x_scale=1.0, loss="linear", max_nfev=limit,
                ftol=1e-8, xtol=1e-8, gtol=1e-8,
            )
        except (ValueError, FloatingPointError, OverflowError, np.linalg.LinAlgError) as exc:
            raise _Stopped("optimization_numerical_failure", details={"message": str(exc)}) from exc
        if not np.all(np.isfinite(fitted.x)) or not np.all(np.isfinite(fitted.jac)):
            raise _Stopped("nonfinite_optimizer_output")
        report["summary"]["optimization_converged"] = bool(fitted.success)
        report["summary"]["objective_after"] = _squared_norm(fitted.fun)
        report["summary"]["optimizer_message"] = str(fitted.message)
        values = lower + fitted.x * width
        for index, entry in enumerate(report["parameters"]):
            entry.update(value=float(values[index]),
                         at_bound=bool(fitted.x[index] <= 1e-5 or fitted.x[index] >= 1 - 1e-5))
        if not fitted.success:
            raise _Stopped("optimizer_did_not_converge", details={"message": str(fitted.message)})
        diagnostics = _sensitivity_diagnostics(fitted.jac, len(parameters))
        report["diagnostics"] = diagnostics
        warnings = report["warnings"]
        if diagnostics["rank"] < len(parameters):
            warnings.append("El Jacobiano local no tiene rango completo; los datos no distinguen todos los parámetros.")
        if diagnostics["weak_sensitivity"]:
            warnings.append("La sensibilidad local frente a las escalas declaradas es débil; ajuste numérico no implica parámetros bien determinados.")
        condition = diagnostics["scaled_jacobian_condition"]
        if condition is None or condition >= CONDITION_WARNING:
            warnings.append("La estimación presenta direcciones poco distinguibles o mal condicionadas.")
        if any(entry["at_bound"] for entry in report["parameters"]):
            warnings.append("Un parámetro alcanza un límite de búsqueda; revisar límites, datos y alcance físico.")
        report["summary"]["usable_parameter_estimate"] = not bool(warnings)
        validation_checks = []
        for experiment in experiments:
            predicted, result = simulate(experiment, values, "validation" if experiment["role"] == "validation" else "fitted_report")
            entry = experiment_reports[experiment["experiment_id"]]
            metrics = _experiment_metrics(experiment, predicted, observables)
            entry.update(fitted_metrics=metrics, fitted_series=as_series(predicted),
                         simulation_summary=result["summary"], balance_audit=result["audit"])
            fitted_case = copy.deepcopy(result["configuration"])
            fitted_case["provenance"]["data_kind"] = "synthetic" if all_synthetic else "mixed"
            fitted_case["provenance"]["notes"] += (
                f" | Parámetros estimados en estudio {study['study_id']}; "
                + ("datos sintéticos, sin validación experimental." if all_synthetic else
                   "observaciones declaradas por el usuario, sin verificación de planta.")
            )
            if instrumented:
                fitted_case["provenance"]["notes"] += (
                    " Instrumentación declarada fija: constantes de tiempo, sesgos y límites "
                    "del actuador no estimados ni validados por este ajuste térmico."
                )
            entry["fitted_case"] = fitted_case
            entry["provenance"]["fitted_case_sha256"] = _json_hash(fitted_case)
            if experiment["role"] == "validation":
                checks = {}
                for name, settings in observables.items():
                    metric = metrics[name]
                    met = bool(metric["n"] > 0 and metric["rmse"] <= settings["max_validation_rmse_K"]
                               and metric["max_abs_error"] <= settings["max_validation_abs_error_K"])
                    checks[name] = {"criteria_met": met,
                                    "max_rmse_K": settings["max_validation_rmse_K"],
                                    "max_abs_error_K": settings["max_validation_abs_error_K"]}
                    validation_checks.append(met)
                entry["validation_criteria"] = checks
        criteria_met = bool(validation_checks) and all(validation_checks)
        report["summary"]["validation_status"] = "criteria_met" if criteria_met else "criteria_exceeded"
        if not criteria_met:
            warnings.append("Las trayectorias reservadas exceden al menos un criterio de error declarado.")
            report["summary"]["usable_parameter_estimate"] = False
        # Warnings belong to the standalone exported cases too, including a
        # failed held-out criterion discovered after fitting otherwise precise
        # training parameters. Recompute provenance after these final notes.
        if warnings:
            for entry in report["experiments"]:
                entry["fitted_case"]["provenance"]["notes"] += (
                    " Advertencias del ajuste: " + " ".join(warnings)
                )
                entry["provenance"]["fitted_case_sha256"] = _json_hash(entry["fitted_case"])
        report["summary"]["status"] = "warning" if warnings else "ok"
        notify("completed")
    except _Stopped as exc:
        report["summary"]["status"] = "cancelled" if exc.reason == "user_cancelled" else "failed"
        report["summary"]["usable_parameter_estimate"] = False
        report["summary"]["validation_status"] = "not_assessed"
        report["failure"] = {"reason": exc.reason, **exc.details}
        if math.isfinite(best["objective"]):
            report["summary"]["best_training_objective_seen"] = float(best["objective"])
        # A partly completed reporting pass is not an exportable fitted study.
        for entry in report["experiments"]:
            entry["fitted_case"] = None
            entry["provenance"].pop("fitted_case_sha256", None)
        notify(report["summary"]["status"])
    report["summary"].update(evaluations=evaluations, simulations_count=simulations_count)
    json.dumps(report, allow_nan=False)
    return report
