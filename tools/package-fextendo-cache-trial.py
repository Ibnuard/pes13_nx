"""Package reversible FEX cache flags for the already verified core-3 runtime."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'local/fex3/dxvk-core3'
BASE = ROOT / 'dist/pes13-fextendo-dxvk-core3-v1.zip'
BASE_SHA = '5d44615d0315a1dd8dd5562f13c42e695c82887c3717dd00001054c8ea2f4ea3'
DLL_SHA = 'a8fc15d13e9f0e6443ccffc8974018bf3167aa8e2844c76cb2fb78e3c1d28e92'
FLAG = 'switch/pes13-fex/fex_diskcache'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def checked(path, expected):
    data = path.read_bytes()
    if sha(data) != expected:
        raise ValueError('Hash mismatch: ' + str(path))
    return data


def enc(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def main():
    if not __debug__:
        raise RuntimeError('Assertions required by environment verifier')
    target = ROOT / 'dist/pes13-fextendo-cache-trial-v1.zip'
    if target.exists():
        raise FileExistsError('Existing artifact protected: ' + str(target))
    checked(BASE, BASE_SHA)
    with zipfile.ZipFile(BASE) as z:
        baseline = json.loads(z.read('manifest.json'))
        if (z.testzip() or len(z.namelist()) != len(set(z.namelist())) or
                set(z.namelist()) != set(baseline['files']) | {'manifest.json'}):
            raise ValueError('Baseline ZIP inventory')
        for name, expected in baseline['files'].items():
            if sha(z.read(name)) != expected:
                raise ValueError('Baseline member mismatch: ' + name)
        build_bytes = z.read('evidence/runtime/runtime-build.json')
        build = json.loads(build_bytes)
        if build_bytes != (WORK / 'runtime/runtime-build.json').read_bytes():
            raise ValueError('Runtime receipt changed')
        nro = z.read('switch/pes13-fex/pes13-fex.nro')
        if sha(nro) != build['nro_sha256']:
            raise ValueError('NRO mismatch')
        baseline_manifest = z.read('manifest.json')
    elf = WORK / 'runtime/reference/pes13-fex.elf'
    checked(elf, build['native_elf_sha256'])
    checked(WORK / 'module/libwow64fex.dll', DLL_SHA)
    gap_bytes = (WORK / 'gap.json').read_bytes()
    gap = json.loads(gap_bytes)
    if not gap.get('passed') or gap['native_elf_sha256'] != build['native_elf_sha256']:
        raise ValueError('Stale gap/environment verification')
    for name, expected in gap['source_hashes'].items():
        checked(ROOT / name, expected)
    source = Path(build['native_source']).parent
    for name, expected in gap['generated_source_hashes'].items():
        checked(source / name, expected)
    sys.path.insert(0, str(ROOT / 'tests'))
    from fex_gap_probe import environments
    environments(source, elf)

    files = {
        FLAG: b'1\n',
        'control-off/' + FLAG: b'0\n',
        'README.md': (ROOT / 'docs/FEXTENDO-CACHE-TRIAL.md').read_bytes(),
        'FEXTENDO-DXVK-CORE3-ACTIVE-RESULT.md':
            (ROOT / 'docs/FEXTENDO-DXVK-CORE3-ACTIVE-RESULT.md').read_bytes(),
        'evidence/baseline-manifest.json': baseline_manifest,
        'evidence/runtime-build.json': build_bytes,
        'evidence/gap-environment-check.json': gap_bytes,
    }
    files['manifest.json'] = enc({
        'kind': 'fextendo-cache-trial-v1',
        'configuration_only': True,
        'hardware_tested': False,
        'disk_cache_persistence_verified': False,
        'requires_baseline_zip_sha256': BASE_SHA,
        'requires_nro_sha256': build['nro_sha256'],
        'requires_fex_dll_sha256': DLL_SHA,
        'verified_native_elf_sha256': build['native_elf_sha256'],
        'active_files': [FLAG],
        'configuration_precedence': 'configuration.ini key overrides flag file',
        'checks': ['baseline archive and member hashes', 'existing NRO/ELF/DLL hashes',
                   'gap verifier source and generated-runtime hashes',
                   'all four cache ON/OFF environment blocks present in linked ELF'],
        'files': {name: sha(data) for name, data in sorted(files.items())},
    })
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 9, 29, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, data)
    with zipfile.ZipFile(target) as z:
        if z.testzip() or set(z.namelist()) != set(files):
            raise ValueError('Trial ZIP inventory')
        for name, data in files.items():
            if z.read(name) != data:
                raise ValueError('Trial ZIP member: ' + name)
    print(json.dumps({'passed': True, 'path': str(target),
                      'bytes': target.stat().st_size, 'sha256': sha(target.read_bytes()),
                      'configuration_only': True, 'hardware_tested': False}, indent=2))


if __name__ == '__main__':
    main()
