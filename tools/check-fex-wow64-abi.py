"""Compare this Wine-NX BTCpu export contract with FEX's WOW64 frontend."""

from pathlib import Path
import argparse
import json


def wine_exports(path):
    names = set()
    for line in path.read_text(encoding='utf-8').splitlines():
        words = line.split()
        if len(words) < 3 or words[:2] != ['@', 'stdcall']:
            continue
        entry = next((word for word in words[2:] if '(' in word), None)
        if entry:
            names.add(entry.split('(', 1)[0])
    return names


def fex_exports(path):
    source = path.read_text(encoding='utf-8')
    if 'EXPORTS' not in source:
        raise ValueError('FEX .def has no EXPORTS section')
    return {line.split()[0] for line in source.split('EXPORTS', 1)[1].splitlines()
            if line.strip() and not line.lstrip().startswith(';')}


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wine-spec', type=Path,
                        default=project / 'local/fex-probe/winebox64.spec')
    parser.add_argument('--fex-def', type=Path,
                        default=project / 'local/fex-probe/upstream/Source/Windows/WOW64/libwow64fex.def')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    wine, fex = wine_exports(args.wine_spec), fex_exports(args.fex_def)
    if not wine or not fex:
        raise ValueError('empty or unrecognized export contract')
    report = {
        'wine_spec': str(args.wine_spec), 'fex_def': str(args.fex_def),
        'wine_count': len(wine), 'fex_count': len(fex),
        'common': sorted(wine & fex),
        'wine_only': sorted(wine - fex),
        'fex_only': sorted(fex - wine),
        'interpretation': (
            'Name overlap is only a first ABI check. Signatures, calling convention, '
            'Wine version, exception behavior, memory notifications, and runtime '
            'imports must still be validated before replacing winebox64.dll.'),
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
