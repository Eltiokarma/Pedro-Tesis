"""Execute the complete catalogue and fail on unresolved physical calculations.

Unlike a golden-value comparison, this gate cannot approve an error merely
because the same error was saved in a reference file. Detailed process and
thermodynamic accuracy checks live in the physics regression tests.
"""
import argparse
import json
import math
from pathlib import Path

import examples_registry
import flowsheet_solver


def audit_example(key):
    fs = examples_registry.load_example(key)
    result = flowsheet_solver.solve(fs)
    errors = list(result.mass_balance_errors) + list(result.energy_balance_errors)
    errors += list(result.consistency_errors)
    errors += [f"Unresolved stream: {name}" for name in result.unresolved_streams]
    errors += [f"Recycle did not converge: {r.tear_stream}"
               for r in result.recycle_solutions if not r.converged]
    for stream in fs.streams.values():
        for field in ('mass_flow', 'temperature', 'pressure_bar'):
            value = getattr(stream, field, None)
            if value is None or not math.isfinite(value):
                errors.append(f"{stream.name}: nonfinite {field}={value}")
    for block in fs.blocks.values():
        if not math.isfinite(block.duty):
            errors.append(f"{block.name}: nonfinite duty")
    unit_mass_residuals = []
    for block in fs.blocks.values():
        ins = [s for s in fs.streams.values() if s.dst == block.id]
        outs = [s for s in fs.streams.values() if s.src == block.id]
        if ins and outs:
            incoming = sum(s.mass_flow for s in ins)
            outgoing = sum(s.mass_flow for s in outs)
            unit_mass_residuals.append(abs(incoming - outgoing) / max(incoming, outgoing, 1e-12))
    audit = getattr(result, 'audit_report', None)
    findings = [{'category': f.category, 'severity': f.severity,
                 'target': getattr(f, 'target_name', ''), 'message': f.message}
                for f in audit.findings] if audit else []
    return {'key': key, 'passed': result.success and not errors,
            'status': result.overall_status, 'blocks': len(fs.blocks),
            'streams': len(fs.streams), 'errors': errors,
            'maximum_unit_mass_relative_error': max(unit_mass_residuals, default=0.0),
            'findings': findings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', type=Path, help='Write the complete audit as JSON')
    args = parser.parse_args()
    manifest = Path(__file__).parent / 'data' / 'examples' / 'manifest.json'
    keys = [item['clave'] for item in json.loads(manifest.read_text(encoding='utf-8'))['examples']]
    rows = []
    for key in keys:
        try:
            row = audit_example(key)
        except Exception as exc:
            row = {'key': key, 'passed': False, 'status': 'exception',
                   'errors': [f'{type(exc).__name__}: {exc}']}
        rows.append(row)
        print(f"{'PASS' if row['passed'] else 'FAIL'} {key}: {row['status']}", flush=True)
        for error in row['errors']:
            print(f'  {error}')
    passed = sum(row['passed'] for row in rows)
    report = {'passed': passed, 'total': len(rows), 'examples': rows}
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(f'Physical execution: {passed}/{len(rows)} passed')
    return 0 if passed == len(rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
