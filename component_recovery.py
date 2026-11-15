"""Conservative fixed-performance component separators.

Recoveries are process specifications, NOT predictions from phase equilibrium.
Every incoming species has an explicit destination; unspecified mass goes to
the default outlet. This makes absorber, dryer and membrane demonstrations
responsive to feed changes without inventing fixed product compositions.
"""
import math


def _canonical(name, *, require_known=False):
    import thermo_db
    obj = thermo_db.get(name)
    if obj is None:
        import components
        obj = components.get(name) or components.get(name.replace(" ", "_"))
    if obj is None:
        if require_known:
            raise ValueError(f"unknown component {name!r}")
        return name
    return obj.name


def component_recovery_outputs(block, inputs, outputs):
    """Return {stream_id: {species: mass}} or raise before any mutation."""
    ports = {}
    for stream in outputs:
        if not stream.src_port or stream.src_port in ports:
            raise ValueError("outlets need distinct, nonempty src_port names")
        ports[stream.src_port] = stream
    default = block.component_recovery_default_port
    if default not in ports:
        raise ValueError("default recovery outlet is not connected")
    specification = block.component_recoveries
    if not isinstance(specification, dict):
        raise ValueError("component_recoveries must be a mapping")
    recovery, sums = {}, {}
    for port, fractions in specification.items():
        if port not in ports:
            raise ValueError(f"recovery outlet {port!r} is not connected")
        if not isinstance(fractions, dict):
            raise ValueError(f"recoveries for {port!r} must be a mapping")
        recovery[port] = {}
        for component, fraction in fractions.items():
            name = _canonical(component, require_known=True)
            if name in recovery[port]:
                raise ValueError(f"duplicate aliases for component {name!r}")
            fraction = float(fraction)
            if not math.isfinite(fraction) or not 0 <= fraction <= 1:
                raise ValueError(f"recovery of {name!r} must be finite and in [0, 1]")
            recovery[port][name] = fraction
            sums[name] = sums.get(name, 0.0) + fraction
    if any(value > 1 + 1e-12 for value in sums.values()):
        raise ValueError("component recoveries across outlets exceed 1")
    masses = {}
    for stream in inputs:
        mass = float(stream.mass_flow)
        if not math.isfinite(mass) or mass < 0:
            raise ValueError("inlet mass must be finite and nonnegative")
        if mass == 0:
            continue
        comp = stream.composition or ({stream.main_component: 1.0}
                                      if stream.main_component else {})
        if not comp or any(not math.isfinite(float(v)) or v < 0 for v in comp.values()):
            raise ValueError("positive feed requires a finite, nonnegative composition")
        total = sum(comp.values())
        if abs(total - 1) > 1e-6:
            raise ValueError("feed composition must sum to 1; missing mass is not normalized away")
        for component, fraction in comp.items():
            name = _canonical(component)
            masses[name] = masses.get(name, 0.0) + mass * fraction
    result = {stream.id: {} for stream in outputs}
    for component, mass in masses.items():
        allocated = 0.0
        last_allocated = None
        for port, fractions in recovery.items():
            amount = mass * fractions.get(component, 0.0)
            if amount:
                result[ports[port].id][component] = amount
                allocated += amount
                last_allocated = ports[port].id
        # A complete recovery split must not create a fictitious trace in the
        # default phase from floating-point subtraction (e.g. H2S in coke).
        # Put only arithmetic roundoff in the last specified destination;
        # actual nonzero unallocated fractions are retained without clipping.
        if last_allocated is not None and abs(sums.get(component, 0.0) - 1) <= 1e-12:
            result[last_allocated][component] += mass - allocated
            remainder = 0.0
        else:
            remainder = max(0.0, mass - allocated)
        target = result[ports[default].id]
        if remainder:
            target[component] = target.get(component, 0.0) + remainder
    return result


def solve_component_recoveries(fs):
    """Apply validated recovery specs atomically; return solver messages."""
    messages = []
    for block in fs.blocks.values():
        if not getattr(block, "component_recovery_active", False):
            continue
        inputs = [s for s in fs.streams.values() if s.dst == block.id
                  and getattr(s, "stream_kind", "mass") == "mass"]
        outputs = [s for s in fs.streams.values() if s.src == block.id
                   and getattr(s, "stream_kind", "mass") == "mass"]
        try:
            if not inputs or len(outputs) < 2:
                raise ValueError("requires feeds and at least two outlets")
            calculated = component_recovery_outputs(block, inputs, outputs)
            # User-fixed outlet mass/composition would over-specify the model.
            # Recycle tear locks are transient solver state, not user specs.
            for stream in outputs:
                if stream.mass_flow_locked or stream.composition_locked:
                    raise ValueError("recovery outputs must have mass/composition unlocked")
            for stream in outputs:
                amounts = calculated[stream.id]
                mass = sum(amounts.values())
                stream.mass_flow = mass
                stream.composition = {k: v / mass for k, v in amounts.items() if v > 0} if mass else {}
                stream.main_component = max(stream.composition, key=stream.composition.get) if mass else ""
            messages.append(f"✓ {block.name}: fixed component recoveries (specified performance, not VLE)")
        except (ValueError, TypeError, OverflowError) as exc:
            messages.append(f"✗ Component recovery {block.name}: {exc}")
    return messages
