"""Resolve the FEX ARM64 PE module's imports against a specific Wine payload."""
import argparse
import hashlib
import json
from pathlib import Path

import pefile


def audit(module, system32, machine=0xaa64):
    files = {p.name.lower(): p for p in system32.iterdir() if p.is_file()}
    files[module.name.lower()] = module
    cache, checked, issues = {}, {}, []

    def load(name):
        if name not in cache:
            pe = pefile.PE(str(files[name]))
            symbols = {}
            for symbol in getattr(getattr(pe, 'DIRECTORY_ENTRY_EXPORT', None), 'symbols', []):
                forward = symbol.forwarder.decode() if symbol.forwarder else None
                symbols[symbol.ordinal] = forward
                if symbol.name:
                    symbols[symbol.name.decode()] = forward
            cache[name] = pe, symbols
        return cache[name]

    def resolve(name, symbol, chain):
        marker = (name, symbol)
        if marker in chain:
            issues.append({'kind': 'forwarder_cycle', 'chain': chain + [marker]})
            return
        if name not in files:
            issues.append({'kind': 'missing_dll', 'dll': name, 'symbol': symbol})
            return
        pe, exports = load(name)
        visit(name)
        if symbol not in exports:
            issues.append({'kind': 'missing_export', 'dll': name, 'symbol': symbol})
        elif exports[symbol]:
            target, next_symbol = exports[symbol].rsplit('.', 1)
            resolve(target.lower() + '.dll', int(next_symbol[1:]) if next_symbol.startswith('#') else next_symbol,
                    chain + [marker])

    def visit(name):
        if name in checked:
            return
        pe, _ = load(name)
        entry = {'path': str(files[name]), 'machine': hex(pe.FILE_HEADER.Machine),
                 'sha256': hashlib.sha256(files[name].read_bytes()).hexdigest(), 'imports': {}}
        checked[name] = entry
        if pe.FILE_HEADER.Machine != machine:
            issues.append({'kind': 'wrong_machine', 'dll': name, 'machine': entry['machine']})
        for directory in ('DIRECTORY_ENTRY_IMPORT', 'DIRECTORY_ENTRY_DELAY_IMPORT'):
            for dep in getattr(pe, directory, []):
                target = dep.dll.decode().lower()
                symbols = [s.name.decode() if s.name else s.ordinal for s in dep.imports]
                entry['imports'].setdefault(target, []).extend(symbols)
                for symbol in symbols:
                    resolve(target, symbol, [])

    try:
        visit(module.name.lower())
        return {'passed': not issues, 'modules': checked, 'issues': issues,
                'limits': 'Static imports and export forwarders only. Dynamic lookups, ABI semantics, '
                          'Horizon memory/fault handling, and hardware execution are not validated.'}
    finally:
        for pe, _ in cache.values():
            pe.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('module', type=Path)
    parser.add_argument('system32', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.module.resolve(), args.system32.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'modules': list(report['modules']),
                      'issues': report['issues']}, indent=2))
    raise SystemExit(0 if report['passed'] else 1)


if __name__ == '__main__':
    main()
