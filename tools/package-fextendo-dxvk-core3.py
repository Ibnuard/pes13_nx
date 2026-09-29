"""Package a single-variable DXVK role trial, OFF control and exact baseline NRO."""
from pathlib import Path
import hashlib
import importlib.util
import json
import subprocess
import sys
import zipfile
from nro_assets import inspect_nro

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3/dxvk-core3'
BASE = 'pes13-fextendo-short-trace-v1.zip'
BASE_SHA = '7c1a62a919210af9a1fabf89def92004744ef97cecead62150ad9aa250474933'
DLL_SHA = 'a8fc15d13e9f0e6443ccffc8974018bf3167aa8e2844c76cb2fb78e3c1d28e92'
NRO = 'switch/pes13-fex/pes13-fex.nro'
DLL = 'switch/pes13-fex/drive_c/windows/system32/libwow64fex.dll'
FLAG = 'switch/pes13-fex/fex_dxvk_core3'
CHECKS = ('launcher', 'memory', 'budget', 'gap', 'balance', 'yield', 'cores',
          'resume', 'pipeline', 'jit-log', 'unwind', 'short-trace', 'dxvk-core3')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_text())


def checked(path, expected):
    data = path.read_bytes()
    if sha(data) != expected:
        raise ValueError('Hash mismatch: ' + str(path))
    return data


def enc(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def main():
    archive = ROOT / 'dist/pes13-fextendo-dxvk-core3-v1.zip'
    folder = archive.with_suffix('')
    if archive.exists() or folder.exists():
        raise FileExistsError('Existing artifact protected')
    checked(ROOT / 'dist' / BASE, BASE_SHA)
    files = {}
    with zipfile.ZipFile(ROOT / 'dist' / BASE) as z:
        baseline = json.loads(z.read('manifest.json'))
        if (z.testzip() or len(z.namelist()) != len(set(z.namelist())) or
                set(z.namelist()) != set(baseline['files']) | {'manifest.json'}):
            raise ValueError('Baseline inventory')
        for name, expected in baseline['files'].items():
            data = z.read(name)
            if sha(data) != expected:
                raise ValueError('Baseline member: ' + name)
            if name.startswith('licenses/'):
                files[name] = data
        if sha(z.read(DLL)) != DLL_SHA:
            raise ValueError('Unexpected baseline FEX module')
        files['rollback/' + NRO] = z.read(NRO)
        files['evidence/baseline/' + BASE + '.manifest.json'] = z.read('manifest.json')
        old = json.loads(z.read('evidence/runtime/runtime-build.json'))
        previous = json.loads(z.read('evidence/runtime/wine-patches.json'))
        for name in ('build.json', 'patches.json'):
            data = z.read('evidence/module/' + name)
            if data != (WORK / 'module' / name).read_bytes():
                raise ValueError('FEX module evidence changed: ' + name)

    new = read(WORK / 'runtime/runtime-build.json')
    patches = read(WORK / 'runtime/wine-patches.json')
    module = read(WORK / 'module/build.json')
    if new.get('dxvk_core3') is not True or new.get('short_trace') is not True:
        raise ValueError('Missing experimental/trace flag')
    for key in ('native_dependencies', 'ntdll_sha256', 'wow64_sha256',
                'guest_sha256', 'toolchain_path', 'adapter_sources'):
        if new[key] != old[key]:
            raise ValueError('Baseline dependency changed: ' + key)
    for key, value in old.items():
        if isinstance(value, bool) and new.get(key) != value:
            raise ValueError('Baseline flag changed: ' + key)
    if patches['pe-source'] != previous['pe-source']:
        raise ValueError('Guest Wine changed')
    delta = sorted(name for name in patches['native-source'].keys() | previous['native-source'].keys()
                   if patches['native-source'].get(name) != previous['native-source'].get(name))
    if delta != ['dlls/ntdll/unix/thread.c', 'wine-nx-probe/source/runtime.c',
                 'wine-nx-probe/source/thread_profile.c']:
        raise ValueError('Unexpected native source delta: ' + repr(delta))
    for name, expected in new['patch_sources'].items():
        checked(ROOT / name, expected)
    for name, expected in new['adapter_sources'].items():
        checked(ROOT / 'src/fex' / name, expected)
    for name, expected in module['adapter_sources'].items():
        checked(ROOT / name, expected)
    if module['sha256'] != DLL_SHA:
        raise ValueError('Module hash changed')
    checked(WORK / 'module/libwow64fex.dll', DLL_SHA)
    files[NRO] = checked(WORK / 'runtime/payload/pes13-fex.nro', new['nro_sha256'])
    files[FLAG] = b'1\n'
    files['control-off/' + FLAG] = b'0\n'
    files['rollback/' + FLAG] = b'0\n'
    elf = WORK / 'runtime/reference/pes13-fex.elf'
    checked(elf, new['native_elf_sha256'])
    spec = importlib.util.spec_from_file_location('stable', ROOT / 'tools/package-fex3-stability.py')
    stable = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stable)
    stable.verify_executable(elf, files[NRO])
    metadata = inspect_nro(files[NRO], (ROOT / 'assets/fextendo-v3/nro-icon.jpg').read_bytes(),
                           expected_title='PES13 - FEXTendo', expected_version='0.3.3')
    if metadata != new['metadata'] or metadata['author'] != 'AndroSwitch Project':
        raise ValueError('NRO metadata')
    for marker in (b'pes13-fextendo-dxvk-core3-v1', b'[FEX3-DXVKCORE]', b'dxvk-cs',
                   b'[FEX3-SHORT-STATS]', b'[FEXTENDO-TIME]', b'first overlay frame submitted'):
        if marker not in files[NRO]:
            raise ValueError('Missing NRO marker: ' + repr(marker))

    sources = set(new['patch_sources']) | {'src/fex/' + n for n in new['adapter_sources']}
    sources |= set(module['adapter_sources'])
    for name in CHECKS:
        path = WORK / (name + '.json')
        result = read(path)
        if result.get('passed') is not True or result['native_elf_sha256'] != new['native_elf_sha256']:
            raise ValueError('Stale or failed check: ' + name)
        if name == 'unwind' and result['fex_sha256'] != DLL_SHA:
            raise ValueError('Unwind used wrong FEX module')
        if name == 'short-trace' and result['dll_sha256'] != DLL_SHA:
            raise ValueError('Trace used wrong FEX module')
        for source, expected in result.get('source_hashes', result.get('source_sha256', {})).items():
            checked(ROOT / source, expected)
            sources.add(source)
        files['evidence/checks/' + name + '.json'] = path.read_bytes()
    metrics = read(WORK / 'jit-metrics.json')
    if metrics.get('passed') is not True:
        raise ValueError('JIT metrics check')
    if metrics['runtime_source_sha256'] != patches['native-source']['wine-nx-probe/source/runtime.c']:
        raise ValueError('Stale JIT metrics source check')
    for name, expected in metrics['sources'].items():
        checked(ROOT / 'src/fex' / name, expected)
        sources.add('src/fex/' + name)
    files['evidence/checks/jit-metrics.json'] = enc(metrics)
    for test in ('fextendo_short_analysis.py', 'fextendo_analysis.py'):
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'tests' / test)],
                                check=True, capture_output=True, text=True)
        files['evidence/checks/' + test + '.txt'] = result.stdout.encode()
        sources.add('tests/' + test)
    for name in ('runtime-build.json', 'wine-patches.json'):
        files['evidence/runtime/' + name] = (WORK / 'runtime' / name).read_bytes()
    for name in ('build.json', 'patches.json'):
        files['evidence/module/' + name] = (WORK / 'module' / name).read_bytes()
    generated = Path(new['native_source']).parent
    for name in delta:
        files['source/generated/wine/' + name] = checked(generated / name, patches['native-source'][name])

    sources |= {'tools/package-fextendo-dxvk-core3.py', 'tools/build-fex-module.py',
                'tests/run_fextendo_checks.py', 'tests/fex_jit_latency.py',
                'tools/nro_assets.py', 'tools/package-fex3-stability.py',
                'tools/analyze-fextendo-run.py', 'tools/analyze-fextendo-short-trace.py',
                'docs/FEXTENDO-DXVK-CORE3.md', 'docs/FEXTENDO-SHORT-TRACE-RESULT.md',
                'docs/FEXTENDO-SHORT-TRACE.md', 'assets/fextendo-v3/nro-icon.jpg'}
    for name in sources:
        files['source/' + name] = (ROOT / name).read_bytes()
    files['README.md'] = (ROOT / 'docs/FEXTENDO-DXVK-CORE3.md').read_bytes()
    files['FEXTENDO-SHORT-TRACE-RESULT.md'] = (ROOT / 'docs/FEXTENDO-SHORT-TRACE-RESULT.md').read_bytes()
    files['THIRD_PARTY.md'] = (ROOT / 'THIRD_PARTY.md').read_bytes()
    review = ROOT / 'local/fex3/review-short-trace-c217f83d39/review.json'
    if read(review)['input_sha256'] != 'c217f83d39bea79e9a464c413e58c3fa62e24bf8be1405ea6c41f0624ecee3d5':
        raise ValueError('Wrong baseline log review')
    files['evidence/baseline/review.json'] = review.read_bytes()
    active = sorted(name for name in files if name.startswith('switch/'))
    if active != sorted((NRO, FLAG)):
        raise ValueError('Unexpected active file')
    manifest = {
        'kind': 'fextendo-dxvk-core3-v1', 'hardware_tested': False, 'stutter_fix_claimed': False,
        'requires': 'working FEXTendo short trace v1 installation, including its unchanged FEX DLL',
        'baseline_zip_sha256': {BASE: BASE_SHA}, 'required_unchanged_dll_sha256': DLL_SHA,
        'native_elf_sha256': new['native_elf_sha256'], 'nro_sha256': new['nro_sha256'],
        'source_default': False, 'package_requested': True, 'control_file': 'fex_dxvk_core3=0',
        'role': 'dxvk-cs', 'core': 3, 'priority': 63, 'game_core_policy': 'unchanged, automatic 0-2',
        'native_changed': delta, 'adapter_changed': [],
        'checks': list(CHECKS) + ['jit-metrics', 'fextendo_short_analysis.py', 'fextendo_analysis.py'],
        'active_files': active, 'rollback_target': 'exact short trace v1 NRO; unchanged diagnostic DLL',
        'files': {name: sha(data) for name, data in sorted(files.items())},
    }
    files['manifest.json'] = enc(manifest)
    for name, data in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 29, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() or len(z.namelist()) != len(files):
            raise ValueError('Final inventory')
        for name, data in files.items():
            if z.read(name) != data:
                raise ValueError('Final member: ' + name)
    report = {'passed': True, 'path': str(archive), 'bytes': archive.stat().st_size,
              'sha256': sha(archive.read_bytes()), 'active_files': len(active),
              'checks': len(manifest['checks'])}
    (WORK / 'package.json').write_bytes(enc(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
