"""Create reversible x86 DXVK comparisons from digest-verified official releases."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

import pefile

project = Path(__file__).resolve().parents[1]
inputs = project / 'local/perf10'
legacy = project / 'local/legacy-cleanup/wine'
baseline = legacy / 'drive_c/dxvk/d3d9.dll'
digest = lambda data: hashlib.sha256(data).hexdigest()
assert digest(baseline.read_bytes()) == '4950c79dd762837e86eb3823aabf1512ec6f35da8dd3a743a247e20c94b7873e'
archives = {
    '3.1.1': '40565b4a724aadc4433fa4e010b4b23916d9b1f1baeee64e17186db94f54e608',
    '2.7.1': 'd85ce7c79f57ecd765aaa1b9e7007cb875e6fde9f6d331df799bce73d513ce87',
}
dlls = {'rollback': baseline.read_bytes()}
for version, expected in archives.items():
    archive = inputs / f'dxvk-{version}.tar.gz'
    assert digest(archive.read_bytes()) == expected, 'Release archive hash mismatch'
    with tarfile.open(archive) as tar:
        dlls[version] = tar.extractfile(f'dxvk-{version}/x32/d3d9.dll').read()
    with pefile.PE(data=dlls[version]) as pe:
        assert pe.FILE_HEADER.Machine == 0x14c, 'PES13 requires x86'
        exports = {e.name for e in pe.DIRECTORY_ENTRY_EXPORT.symbols}
        assert {b'Direct3DCreate9', b'Direct3DCreate9Ex'} <= exports

# Check reachable imports against the actual existing Wine DLL payload.
# Copy only DLLs; never modify the reference payload or game files.
with tempfile.TemporaryDirectory(prefix='pes13-perf10-') as temporary:
    root = Path(temporary)
    for folder in ('syswow64', 'system32'):
        dest = root / f'drive_c/windows/{folder}'
        dest.mkdir(parents=True)
        for dll in (legacy / f'drive_c/windows/{folder}').glob('*.dll'):
            shutil.copyfile(dll, dest / dll.name)
    (root / 'drive_c/dxvk').mkdir(parents=True)
    game = root / 'drive_c/PES13'
    game.mkdir(parents=True)
    baseline_deferred = None
    for version, data in dlls.items():
        (game / 'd3d9.dll').write_bytes(data)
        report_path = inputs / f'imports-{version}.json'
        checked = subprocess.run([
            sys.executable, str(project / 'tools/check_payload.py'), str(root),
            '--entry', 'd3d9.dll', '--dxvk', '--output',
            str(report_path),
        ], capture_output=True, text=True)
        if checked.returncode not in (0, 1) or not report_path.exists():
            raise RuntimeError(checked.stdout + checked.stderr)
        report = json.loads(report_path.read_text())
        required = [i for i in report['issues'] if not i.get('deferred', False)]
        assert not required, f'{version}: unresolved required imports: {required}'
        # The known working minimal Wine payload omits optional delay-loaded
        # components. Require alternatives not to add any unresolved ones.
        deferred = {json.dumps(i, sort_keys=True) for i in report['issues']}
        if version == 'rollback':
            baseline_deferred = deferred
        assert not deferred - baseline_deferred, f'{version}: new deferred import failures'
        print(f'{version}: required imports passed; {len(deferred)} existing optional issues')

base_config = 'd3d9.maxFrameRate = -1\n'
# Separate experiment: reduce shader compilation competition and avoid the
# extra transfer for streaming constants. Does not promise steady-state gains.
tuned_config = base_config + '''# PERF10 CPU contention experiment, not a proven optimization.
dxvk.numCompilerThreads = 1
d3d9.deviceLocalConstantBuffers = False
'''
variants = [
    ('dxvk311', '3.1.1', base_config),
    ('dxvk271', '2.7.1', base_config),
    ('dxvk311-cpu', '3.1.1', tuned_config),
    ('rollback', 'rollback', base_config),
]
readme = (project / 'docs/PERF10.md').read_bytes()
result = []
for name, version, config in variants:
    prefix = 'switch/pes13-nx/'
    files = {
        prefix + 'drive_c/PES13/d3d9.dll': dlls[version],
        prefix + 'drive_c/dxvk/d3d9.dll': dlls[version],
        prefix + 'drive_c/PES13/dxvk.conf': config.encode(),
        prefix + 'profile.txt': b'0\n',
        prefix + 'drive_c/PES13/pes2013.wine-nx.txt':
            (project / 'config/drive_c/PES13/pes2013.wine-nx.txt').read_bytes(),
        prefix + 'perf10-package.txt': f'{name}\nDXVK={version}\n'.encode(),
        'PERF10.md': readme,
        'licenses/DXVK-LICENSE.txt': (project / 'licenses/DXVK-LICENSE.txt').read_bytes(),
    }
    assert b'profile=0' in files[prefix + 'drive_c/PES13/pes2013.wine-nx.txt']
    manifest = {
        'experiment': 'PERF10 DXVK x86 comparison', 'variant': name,
        'dxvk_version': version if version != 'rollback' else 'v3.1-17-g878473ba',
        'source': f'https://github.com/doitsujin/dxvk/releases/tag/v{version}'
            if version != 'rollback' else 'original test-build-2 DXVK payload',
        'source_archive_sha256': archives.get(version),
        'd3d9_sha256': digest(dlls[version]), 'architecture': 'x86',
        'required_import_validation': True,
        'new_deferred_import_failures': False, 'hardware_tested': False,
        'nro_box64_wine_ntdll_game_settings_save': 'not changed',
        'files': {path: digest(data) for path, data in files.items()},
    }
    files['PERF10-manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    target = project / f'dist/pes13-perf10-{name}.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        for path, data in files.items():
            z.writestr(path, data)
    with zipfile.ZipFile(target) as z:
        assert z.testzip() is None
        for path, data in files.items():
            assert z.read(path) == data
        assert not any(n.endswith('.nro') or n.endswith('ntdll.dll') or
                       n.endswith('settings.dat') for n in z.namelist())
    result.append({'package': str(target), 'sha256': digest(target.read_bytes()),
                   'd3d9_sha256': digest(dlls[version])})
(inputs / 'packages.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
