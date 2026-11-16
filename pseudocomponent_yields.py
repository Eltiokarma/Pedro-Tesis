"""Declared industrial mass-yield models, never molecular equilibrium.

Only petroleum pseudocomponents and approved glass-batch solids may be transformed. Yields are mass fractions
of the selected incoming pseudocomponent, not fixed product flow rates. Real
cofeeds pass through unchanged. A component-recovery specification routes the
resulting mixture to the outlets without losing any species.
"""
from copy import copy
import math

from component_recovery import _canonical, component_recovery_outputs

PETROLEUM_PSEUDOS = {"crude_oil", "atmospheric_residue", "naphtha", "kerosene",
                    "diesel", "gasoline_97"}
GLASS_BATCH_SOLIDS = {"silica", "soda_ash", "limestone"}


def lumped_yield_outputs(block, inputs, outputs):
    if not isinstance(block.lumped_yield_basis, str) or not block.lumped_yield_basis.strip():
        raise ValueError("lumped yields require an explicit basis and limitations")
    if not isinstance(block.lumped_yields, dict) or not block.lumped_yields:
        raise ValueError("lumped yield specification is empty")
    transforms = {}
    for name, products in block.lumped_yields.items():
        if name not in PETROLEUM_PSEUDOS | GLASS_BATCH_SOLIDS:
            raise ValueError(f"only petroleum pseudocomponents or approved industrial solids may have mass yields: {name}")
        if not isinstance(products, dict) or not products:
            raise ValueError(f"missing products for {name}")
        values = {}
        for product, fraction in products.items():
            product = _canonical(product, require_known=True)
            fraction = float(fraction)
            if not math.isfinite(fraction) or not 0 <= fraction <= 1:
                raise ValueError("mass yield must be finite and between 0 and 1")
            if product in values:
                raise ValueError(f"duplicate product alias: {product}")
            values[product] = fraction
        if abs(sum(values.values()) - 1.0) > 1e-10:
            raise ValueError("mass yields must sum to one; no normalization is applied")
        transforms[name] = values
    virtual = []
    for inlet in inputs:
        stream = copy(inlet)
        composition = inlet.composition or ({inlet.main_component: 1.0}
                                           if inlet.main_component else {})
        if inlet.mass_flow > 0 and abs(sum(composition.values()) - 1) > 1e-6:
            raise ValueError("inlet composition must sum to one")
        transformed = {}
        for name, fraction in composition.items():
            if not math.isfinite(fraction) or fraction < 0:
                raise ValueError("invalid inlet composition")
            products = transforms.get(name, {_canonical(name): 1.0})
            for product, value in products.items():
                transformed[product] = transformed.get(product, 0.0) + fraction * value
        stream.composition = transformed
        virtual.append(stream)
    return component_recovery_outputs(block, virtual, outputs)


def solve_lumped_yields(fs):
    messages = []
    for block in fs.blocks.values():
        if not getattr(block, "lumped_yield_active", False):
            continue
        inputs = [s for s in fs.streams.values() if s.dst == block.id
                  and getattr(s, "stream_kind", "mass") == "mass"]
        outputs = [s for s in fs.streams.values() if s.src == block.id
                   and getattr(s, "stream_kind", "mass") == "mass"]
        try:
            if not inputs or len(outputs) < 2:
                raise ValueError("requires at least one inlet and two outlets")
            if any(s.mass_flow_locked or s.composition_locked for s in outputs):
                raise ValueError("lumped yield outlets must have mass/composition unlocked")
            calculated = lumped_yield_outputs(block, inputs, outputs)
            for stream in outputs:
                masses = calculated[stream.id]
                stream.mass_flow = sum(masses.values())
                stream.composition = ({c: m / stream.mass_flow for c, m in masses.items() if m > 0}
                                      if stream.mass_flow else {})
                stream.main_component = (max(stream.composition, key=stream.composition.get)
                                         if stream.composition else "")
            messages.append(f"V {block.name}: declared industrial mass yields; not equilibrium or an elemental assay")
        except (ValueError, TypeError, OverflowError) as exc:
            messages.append(f"? Lumped yield {block.name}: {exc}")
    return messages
