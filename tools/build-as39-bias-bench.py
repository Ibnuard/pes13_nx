"""Build a copy-ready addressing benchmark using the already tested AS39 forwarder.

Requires devkitPro and the previous AS39 probe package, but no local keyset.
The fixed-bias prototype is isolated from the production Wine/FEX runtime.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from nro_assets import inspect_nro

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.2.0'
TITLE = 'PES13 Address Bias Benchmark'
NRO = 'switch/pes13-as39-probe/pes13-as39-probe.nro'
FORWARDER = 'PES13-AS39-Probe.nsp'
FORWARDER_SHA = '50ca47a560ef0d97fe91550b8c9b619f4be26646fbf10e62a3d4ce59a67e9171'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', type=Path, default=ROOT / 'local/as39-bias-bench-v1')
    p.add_argument('--output', type=Path, default=ROOT / 'dist/pes13-as39-bias-bench-v1')
    p.add_argument('--sdk', type=Path, default=Path(os.getenv('DEVKITPRO', 'C:/devkitPro' if os.name == 'nt' else '/opt/devkitpro')))
    p.add_argument('--probe-package', type=Path, default=ROOT / 'dist/pes13-as39-experiment-v1')
    args = p.parse_args()
    work, out, sdk, old = (getattr(args, n).resolve() for n in ('work', 'output', 'sdk', 'probe_package'))
    if out.exists() and any(out.iterdir()):
        p.error('Output must be empty; refusing to mix builds.')
    forwarder = old / 'forwarders' / FORWARDER
    if sha(forwarder) != FORWARDER_SHA:
        p.error('Previously hardware-tested AS39 forwarder does not match its pinned hash.')
    old_report = json.loads((old / 'build.json').read_text())
    provenance = [x for x in old_report['forwarders'] if x['address_bits'] == 39][0]
    if provenance['sha256'] != FORWARDER_SHA or provenance['target'] != 'sdmc:/' + NRO:
        p.error('Forwarder provenance/target mismatch.')
    env = dict(os.environ, DEVKITPRO=sdk.as_posix())
    suffix = '.exe' if os.name == 'nt' else ''
    cc = sdk / ('devkitA64/bin/aarch64-none-elf-gcc' + suffix)
    work.mkdir(parents=True, exist_ok=True)
    common = ['-O2', '-g', '-march=armv8-a+crc', '-mtune=cortex-a57', '-ffixed-x18',
              '-fPIE', '-ffunction-sections', '-fdata-sections', '-D__SWITCH__',
              '-isystem', sdk / 'libnx/include', '-I', ROOT / 'src/fex',
              '-I', ROOT / 'src/experimental']
    def run(argv, **kwargs):
        return subprocess.run([str(x) for x in argv], env=env, check=True, **kwargs)
    objects = []
    sources = ['src/experimental/as39_bias_bench.c', 'src/experimental/as39_bias_kernels.S',
               'src/fex/horizon_jit.c']
    for source in sources:
        obj = work / (Path(source).stem + '.o')
        flags = ['-std=gnu11', '-Wall', '-Wextra', '-Werror'] if source.endswith('.c') else []
        run([cc, *common, *flags, '-c', ROOT / source, '-o', obj])
        objects.append(obj)
    elf = work / 'pes13-as39-bias-bench.elf'
    run([cc, *common, '-specs=' + (sdk / 'libnx/switch.specs').as_posix(), *objects,
         '-L' + (sdk / 'libnx/lib').as_posix(), '-lnx', '-o', elf])
    # Test the linked instructions and lifecycle before making any SD payload.
    tests = work / 'verification.json'
    run([sys.executable, ROOT / 'tests/as39_bias_binary.py', elf, '--output', tests])
    nacp = work / 'benchmark.nacp'
    run([sdk / ('tools/bin/nacptool' + suffix), '--create', TITLE, 'FEXTendo / AndroSwitch', VERSION, nacp])
    nro = work / 'pes13-as39-probe.nro'
    icon = ROOT / 'assets/fextendo-v3/nro-icon.jpg'
    run([sdk / ('tools/bin/elf2nro' + suffix), elf, nro, '--nacp=' + str(nacp), '--icon=' + str(icon)])
    metadata = inspect_nro(nro.read_bytes(), icon.read_bytes(), expected_title=TITLE, expected_version=VERSION)
    (out / NRO).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(nro, out / NRO)
    (out / 'forwarders').mkdir()
    shutil.copy2(forwarder, out / 'forwarders' / FORWARDER)
    shutil.copy2(tests, out / 'verification.json')
    for name in [*sources, 'src/experimental/as39_bias_address.h', 'src/fex/horizon_host.h',
                 'src/fex/LICENSE', 'src/fex/libnx-LICENSE', 'assets/fextendo-v3/nro-icon.jpg',
                 'tests/as39_bias_binary.py', 'tools/build-as39-bias-bench.py',
                 'tools/analyze-as39-bias-bench.py', 'tools/nro_assets.py', 'docs/AS39-BIAS-BENCHMARK.md']:
        target = out / 'source' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    # Include the already reviewed corresponding source/licenses of the reused NSP.
    shutil.copytree(old / 'source/local/production-input-fix/approved/source/forwarder/hbl',
                    out / 'source/forwarder/hbl')
    shutil.copy2(old / 'source/forwarder-39.json', out / 'source/forwarder/forwarder-39.json')
    shutil.copytree(old / 'licenses', out / 'licenses')
    shutil.copy2(ROOT / 'docs/AS39-BIAS-BENCHMARK.md', out / 'README.md')
    report = {'version': VERSION, 'purpose': 'fixed-bias ARM64 addressing feasibility and microbenchmark',
              'hardware_tested': False, 'game_or_full_fex_core_tested': False,
              'production_runtime_modified': False, 'metadata': metadata,
              'nro_sha256': sha(nro), 'elf_sha256': sha(elf),
              'forwarder': provenance, 'forwarder_reused_unmodified': True,
              'compiler': subprocess.check_output([str(cc), '--version'], text=True).splitlines()[0],
              'compiler_flags': [str(x) for x in common],
              'host_tests': json.loads(tests.read_text())}
    (out / 'build.json').write_text(json.dumps(report, indent=2) + '\n')
    manifest = {p.relative_to(out).as_posix(): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'output': str(out), 'nro_sha256': sha(nro), 'metadata': metadata,
                      'verified_host_cases': report['host_tests']['passed'], 'hardware_tested': False}, indent=2))


if __name__ == '__main__':
    main()
