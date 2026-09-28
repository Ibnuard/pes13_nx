"""Regenerate combined Wine patches in a scratch tree and compare build receipts."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from fex_wine_patches import apply


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    expected = json.loads((ROOT / 'local/fex3/stability-540p/runtime/wine-patches.json').read_text())
    with tempfile.TemporaryDirectory(prefix='fex-stability-integration-') as directory:
        scratch = Path(directory)
        for kind in ('native-source', 'pe-source'):
            shutil.copy2(args.work / (kind + '.json'), scratch / (kind + '.json'))
            shutil.copytree(args.work / (kind + '-originals'), scratch / kind)
        for _ in range(2):
            result = apply(scratch, ROOT, integration=True, stability=True, samecore_yield=True)
            if result != expected:
                raise RuntimeError('Combined generated source differs from tested build')
        try:
            apply(scratch, ROOT, stability=True)
        except ValueError:
            pass
        else:
            raise RuntimeError('Invalid standalone stability accepted')
    report = {'passed': True, 'repeat_generations': 2, 'source_hashes': expected,
              'scope': 'Scratch regeneration of combined runtime, compared with compiled source receipts'}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS combined patches reproduce build and remain idempotent; invalid mode rejected')


if __name__ == '__main__':
    main()
