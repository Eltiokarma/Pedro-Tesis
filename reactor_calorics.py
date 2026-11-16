"""Reference-consistent reaction energy and adiabatic temperature solve.

Stream enthalpy excludes chemical formation enthalpy.  Reaction heat must
therefore be converted to the SAME physical reference before it is added
to H_out - H_in. Adding delta-H(T) to that difference counts delta-Cp twice.
"""
from copy import copy
import math

import reactions_db as rdb
from flowsheet_model import SEC_PER_YEAR, TM_TO_KG
from stream_enthalpy import specific_enthalpy_kJ_kg, stream_enthalpy_kW


def reaction_reference_heat_kW(extents):
    """Chemical heat at the stream reference for extents in mol/s."""
    q = 0.0
    for rid, extent in extents.items():
        rxn = rdb.get(rid)
        if rxn is None or rxn.dh_rxn_298_kJ_mol is None:
            raise ValueError(f"No standard reaction enthalpy for {rid}")
        offset = 0.0
        for sp in rxn.stoich:
            name = sp.thermo_name
            prop = rdb.component_for_mass(name)
            if prop is None:
                raise ValueError(f"No molecular mass for {name or sp.formula}")
            phase = "gas" if sp.phase == "g" else "liquid"
            h = specific_enthalpy_kJ_kg({name: 1.0}, 25.0, phase)
            if h is None:
                raise ValueError(f"No caloric reference for {name}")
            offset += sp.nu * prop.mw / 1000.0 * h
        q += float(extent) * (rxn.dh_rxn_298_kJ_mol - offset)
    if not math.isfinite(q):
        raise ValueError("Nonfinite reaction heat")
    return q


def solve_reactors(fs, *, only_adiabatic=False):
    # Runtime import avoids making the independent caloric helper depend on
    # the solver during import.
    import flowsheet_solver as sv

    messages = []
    for b in fs.blocks.values():
        if not (b.reactions or getattr(b, "custom_reactions", None)):
            continue
        is_adiabatic_block = not b.T_op_K or b.T_op_K < 100
        if only_adiabatic and not is_adiabatic_block:
            continue
        signature = tuple((s.id, s.mass_flow, s.temperature, s.pressure_bar, s.phase,
                           s.vapor_fraction, tuple(sorted((s.composition or {}).items())))
                          for s in fs.streams.values() if s.dst == b.id
                          and not getattr(s, "auto_aux", False))
        if only_adiabatic and signature == getattr(b, "_adiabatic_inlet_signature", None):
            continue
        registered = []
        cache = rdb._ensure_loaded()
        try:
            ids = list(b.reactions)
            unknown = [rid for rid in ids if rdb.get(rid) is None]
            if unknown:
                raise ValueError(f"reacciones desconocidas: {', '.join(unknown)}")
            for i, definition in enumerate(getattr(b, "custom_reactions", []) or []):
                reaction = rdb.reaction_from_dict(definition)
                rid = f"_BLOCK{b.id}_CUSTOM{i}"
                registered.append((rid, cache.get(rid)))
                reaction.id = rid
                cache[rid] = reaction
                ids.append(rid)

            ins = [s for s in fs.streams.values() if s.dst == b.id
                   and not getattr(s, "auto_aux", False)
                   and getattr(s, "stream_kind", "mass") == "mass"]
            outs = [s for s in fs.streams.values() if s.src == b.id
                    and not getattr(s, "auto_aux", False)
                    and getattr(s, "stream_kind", "mass") == "mass"]
            if not ins or not outs:
                raise ValueError("faltan entradas o salidas de proceso")
            mass = sum(s.mass_flow for s in ins)
            if mass <= 0:
                # Upstream values may still be pending during a forward pass.
                continue
            agg = {}
            for s in ins:
                if s.mass_flow <= 0:
                    continue
                comp = s.composition or ({s.main_component: 1.0} if s.main_component else {})
                if not comp or abs(sum(comp.values()) - 1.0) > 1e-6:
                    raise ValueError(f"composición incompleta en {s.name}")
                for c, fraction in comp.items():
                    if fraction < 0 or not math.isfinite(fraction):
                        raise ValueError(f"composición inválida en {s.name}")
                    agg[c] = agg.get(c, 0.0) + s.mass_flow * fraction / mass
            m_kg_s = mass * TM_TO_KG / SEC_PER_YEAR
            fixed = [out for out in outs if sv._is_mass_locked(out)]
            free = [out for out in outs if out not in fixed]
            fixed_mass = sum(out.mass_flow for out in fixed)
            if fixed_mass > mass * (1 + 1e-6) or (
                    not free and abs(fixed_mass - mass) > max(1e-6, mass * 1e-6)):
                raise ValueError("caudales de salida fijados no conservan la masa de entrada")
            residual = max(0.0, mass - fixed_mass)
            free_seed = sum(max(0.0, out.mass_flow) for out in free)
            outlet_mass = {out.id: out.mass_flow for out in fixed}
            for out in free:
                outlet_mass[out.id] = residual * (
                    max(0.0, out.mass_flow) / free_seed if free_seed > 0 else 1 / len(free))
            t_in = sum(s.temperature * s.mass_flow for s in ins) / mass + 273.15
            p = b.P_op_bar if b.P_op_bar > 1.01325 else min(s.pressure_bar for s in ins)
            if not math.isfinite(p) or p <= 0:
                raise ValueError("presión inválida")
            mode = getattr(b, "reactor_mode", "equilibrium") or "equilibrium"
            if mode in ("pfr", "cstr", "batch") and any(
                    not rdb.get(rid).kinetics_available for rid in ids):
                raise ValueError(f"modo {mode} sin cinética disponible")
            if mode == "stoich" and len(ids) != 1:
                raise ValueError("conversión estequiométrica requiere una reacción por bloque")

            def chemistry(t):
                common = dict(rxn_ids=ids, inlet_composition=agg,
                              inlet_mass_kg_s=m_kg_s, T_K=t, P_bar=p)
                if mode == "equilibrium":
                    return rdb.solve_equilibrium_reactor_from_composition(**common)
                if mode == "stoich":
                    conversion = getattr(b, "reactor_conversion", 0.95)
                    if not math.isfinite(conversion) or not 0 <= conversion <= 1:
                        raise ValueError("conversión fuera de [0,1]")
                    return rdb.solve_stoichiometric_reactor(**common, conversion=conversion)
                volume = getattr(b, "reactor_volume_L", 0.0)
                if volume <= 0:
                    raise ValueError("reactor_volume_L debe ser positivo")
                if mode in ("pfr", "cstr"):
                    return rdb.solve_kinetic_reactor_from_composition(
                        **common, mode=mode, V_reactor_L=volume)
                if mode == "batch":
                    return rdb.solve_batch_from_composition(
                        **common, V_reactor_L=volume,
                        t_batch_s=getattr(b, "batch_time_s", 0.0))
                raise ValueError(f"modo desconocido: {mode}")

            inlet_h = [stream_enthalpy_kW(s) for s in ins if s.mass_flow > 0]
            if any(h is None for h in inlet_h):
                raise ValueError("entalpía de alimentación no resoluble")
            h_in = sum(inlet_h)
            is_adiabatic = not b.T_op_K or b.T_op_K < 100
            if is_adiabatic and sv._is_duty_locked(b) and abs(b.duty) > 1e-9:
                raise ValueError("reactor adiabático tiene duty externo no nulo")
            if is_adiabatic and any(sv._is_temp_locked(s) for s in outs):
                raise ValueError("reactor adiabático tiene temperatura de salida fijada")

            def trial(t):
                result = chemistry(t)
                if result is None:
                    raise ValueError(f"química no converge a {t:.2f} K")
                qref = reaction_reference_heat_kW(result["xi"])
                outcomp = result["outlet_composition"]
                # A phase specification is already an independent degree of
                # freedom. Do not solve bubble/dew temperatures thousands of
                # times merely to discard them for locked gas outlets.
                if any(not sv._is_phase_locked(out) for out in outs):
                    phase, vf = sv._infer_phase_from_TP(outcomp, t, p)
                else:
                    phase, vf = "", 0.0
                h_out = 0.0
                # Every reactor outlet represents the same mixed reaction
                # effluent. Selective separation belongs to a separate unit.
                for out in outs:
                    probe = copy(out)
                    probe.mass_flow = outlet_mass[out.id]
                    if probe.mass_flow <= 0:
                        continue
                    probe.composition = dict(outcomp)
                    probe.main_component = max(outcomp, key=outcomp.get)
                    probe.temperature = (out.temperature if sv._is_temp_locked(out)
                                         else t - 273.15)
                    if not sv._is_phase_locked(out) and phase:
                        probe.phase, probe.vapor_fraction = phase, vf
                    h = stream_enthalpy_kW(probe)
                    if h is None:
                        raise ValueError("entalpía de producto no resoluble")
                    h_out += h
                electrical = 0.0
                voltage = getattr(b, "electrolysis_voltage_V", 0.0)
                if voltage:
                    efficiency = getattr(b, "electrolysis_current_efficiency", 1.0)
                    electrons = getattr(b, "electrolysis_electrons_per_extent", 0.0)
                    if not (math.isfinite(voltage) and voltage > 0 and
                            0 < efficiency <= 1 and electrons > 0 and len(ids) == 1):
                        raise ValueError("parámetros electroquímicos inválidos")
                    electrical = result['xi'][ids[0]] * electrons * 96485.33212 * voltage / efficiency / 1000
                result['_electrical_work_kW'] = electrical
                return h_out - h_in + qref - electrical, result, qref, phase, vf

            t = t_in if is_adiabatic else float(b.T_op_K)
            if is_adiabatic:
                # Bracket energy balance; never clamp and declare success.
                candidates = sorted(set([100., 200., 298.15, 400., 600.,
                                         800., 1000., 1400., 1800., 2200.,
                                         2500., t_in]))
                valid = []
                solved = None
                for candidate in candidates:
                    try:
                        evaluated = trial(candidate)
                    except ValueError:
                        continue
                    if abs(evaluated[0]) <= max(1e-5, abs(h_in) * 1e-8):
                        t, solved = candidate, evaluated
                        break
                    valid.append((candidate, evaluated))
                    if len(valid) > 1 and valid[-2][1][0] * evaluated[0] < 0:
                        lo, low = valid[-2]
                        hi = candidate
                        for _ in range(70):
                            mid = (lo + hi) / 2
                            evaluated_mid = trial(mid)
                            if abs(evaluated_mid[0]) <= max(1e-5, abs(h_in) * 1e-8):
                                t, solved = mid, evaluated_mid
                                break
                            if low[0] * evaluated_mid[0] < 0:
                                hi = mid
                            else:
                                lo, low = mid, evaluated_mid
                        break
                if solved is None:
                    raise ValueError("balance adiabático no converge dentro de 100–2500 K")
                energy, result, qref, phase, vf = solved
                b._adiabatic_T_final_K = t
            else:
                energy, result, qref, phase, vf = trial(t)

            outcomp = result["outlet_composition"]
            for out in outs:
                out.mass_flow = outlet_mass[out.id]
                out.composition = dict(outcomp)
                out.main_component = max(outcomp, key=outcomp.get)
                if not sv._is_temp_locked(out):
                    out.temperature = t - 273.15
                if not sv._is_pressure_locked(out):
                    out.pressure_bar = p
                if phase and not sv._is_phase_locked(out):
                    out.phase, out.vapor_fraction = phase, vf
            b.heat_of_reaction = qref / m_kg_s
            b._pfr_profile = result.get("pfr_profile")
            b._batch_profile = result.get("batch_profile")
            if not sv._is_duty_locked(b):
                b.duty = 0.0 if is_adiabatic else energy
            b._reaction_heat_at_T_kW = result["duty_kW"]
            b._electrical_work_kW = result['_electrical_work_kW']
            electrical_inputs = [s for s in fs.streams.values() if s.dst == b.id
                                 and getattr(s, 'stream_kind', 'mass') == 'energy']
            if b._electrical_work_kW:
                if len(electrical_inputs) != 1:
                    raise ValueError("electrólisis requiere una corriente de energía de entrada")
                electrical_inputs[0].energy_kW = b._electrical_work_kW
            if is_adiabatic:
                b._adiabatic_inlet_signature = signature
            messages.append(f"✓ Reactor {b.name}: Q={b.duty:+.3f} kW, T={t:.2f} K")
        except (ValueError, KeyError, ArithmeticError) as exc:
            messages.append(f"❌ Reactor {b.name}: {exc}")
        finally:
            for rid, previous in registered:
                if previous is None:
                    cache.pop(rid, None)
                else:
                    cache[rid] = previous
    return messages


def refresh_adiabatic_reactors(fs):
    """Re-solve only adiabatic reactors whose thermal/material inlet changed.

    Kinetics and equilibrium must be recomputed at the new adiabatic
    temperature; retaining the old extent would violate the coupled model.
    """
    return solve_reactors(fs, only_adiabatic=True)
