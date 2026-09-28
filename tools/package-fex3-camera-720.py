"""Package queued JIT statistics and explicit 720p/Medium-candidate benchmarks."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import zipfile

from pes13_benchmark_settings import preset

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT/'local/fex3/camera-720'
NRO = 'switch/pes13-fex/pes13-fex.nro'
INPUT = '6c8901254a777a3fd3fff6cc5346341043034efe48f28eebb7a121dd396ca34b'
BASE = 'e045d30245558b96359bf66052611aa341c86adb653a4479ad704532a190f1f1'


def sha(data): return hashlib.sha256(data).hexdigest()
def read(path): return json.loads(path.read_text())
def encoded(value): return (json.dumps(value, indent=2)+'\n').encode()


def checked(path, digest):
    data = path.read_bytes()
    if sha(data) != digest:
        raise ValueError('Hash mismatch '+str(path))
    return data


def main():
    spec = importlib.util.spec_from_file_location('stable', ROOT/'tools/package-fex3-stability.py')
    stable = importlib.util.module_from_spec(spec); spec.loader.exec_module(stable)
    base = ROOT/'dist/pes13-fex3-worker-cores.zip'
    checked(base, BASE)
    files = {}
    with zipfile.ZipFile(base) as archive:
        if archive.testzip():
            raise ValueError('Corrupt baseline ZIP')
        manifest = json.loads(archive.read('manifest.json'))
        names = archive.namelist()
        if len(names) != len(set(names)) or set(names) != set(manifest['files']) | {'manifest.json'}:
            raise ValueError('Unlisted or duplicate baseline member')
        for name, digest in manifest['files'].items():
            data = archive.read(name)
            if sha(data) != digest:
                raise ValueError('Baseline member mismatch '+name)
            if name.startswith('switch/'):
                files[name] = data; files['rollback/'+name] = data
            elif name.startswith('evidence/'):
                files['evidence/worker-cores/'+name.removeprefix('evidence/')] = data
            elif name.startswith('source/'):
                files['source/worker-cores/'+name.removeprefix('source/')] = data
            elif name.startswith('licenses/') or name == 'THIRD_PARTY.md':
                files[name] = data
        files['evidence/worker-cores/manifest.json'] = archive.read('manifest.json')
    new = read(WORK/'runtime/runtime-build.json')
    old = read(ROOT/'local/fex3/worker-cores/runtime/runtime-build.json')
    if old != json.loads(files['evidence/worker-cores/runtime/runtime-build.json']):
        raise ValueError('Baseline runtime receipt mismatch')
    for flag in ('jit_log_queue', 'worker_cores', 'sleep_deadline', 'jit_latency',
                 'warm_audit', 'hang_audit', 'stability', 'samecore_yield', 'resume_gate'):
        if new.get(flag) is not True:
            raise ValueError('Missing build flag '+flag)
    for key in ('native_dependencies', 'ntdll_sha256', 'wow64_sha256', 'guest_sha256',
                'toolchain_path', 'adapter_sources'):
        if new[key] != old[key]:
            raise ValueError('Unexpected dependency delta '+key)
    for name, digest in new['patch_sources'].items(): checked(ROOT/name, digest)
    for name, digest in new['adapter_sources'].items(): checked(ROOT/'src/fex'/name, digest)
    np = read(WORK/'runtime/wine-patches.json')
    op = json.loads(files['evidence/worker-cores/runtime/wine-patches.json'])
    if np['pe-source'] != op['pe-source']:
        raise ValueError('PE source changed')
    delta = sorted(k for k in np['native-source'].keys() | op['native-source'].keys()
                   if np['native-source'].get(k) != op['native-source'].get(k))
    if delta != ['wine-nx-probe/source/runtime.c']:
        raise ValueError('Unexpected native source delta: '+repr(delta))
    nro = checked(WORK/'runtime/payload/pes13-fex.nro', new['nro_sha256'])
    elf = WORK/'runtime/reference/pes13-fex.elf'
    checked(elf, new['native_elf_sha256']); stable.verify_executable(elf, nro)
    for marker in (b'pes13-fex3-camera-720', b'[FEX3-JITLOG] v1',
                   b'[FEX3-CORES] v1', b'[FEX3-COREMAP]', b'[FEX3-SLEEP] v1'):
        if marker not in nro:
            raise ValueError('Missing marker '+str(marker))
    files[NRO] = nro
    if sha(files['rollback/'+NRO]) != old['nro_sha256']:
        raise ValueError('Rollback NRO mismatch')
    files['README.md'] = (ROOT/'docs/FEX3-CAMERA-720.md').read_bytes()
    checks = {
        'jit-log.json': {'native_elf_sha256': new['native_elf_sha256'],
                         'before_native_elf_sha256': old['native_elf_sha256'],
                         'generated_runtime_sha256': np['native-source']['wine-nx-probe/source/runtime.c']},
        'resume.json': {'native_elf_sha256': new['native_elf_sha256']},
        'pipeline.json': {'native_elf_sha256': new['native_elf_sha256']},
        'unwind.json': {'native_elf_sha256': new['native_elf_sha256'],
                        'fex_sha256': manifest['dll_sha256'],
                        'ntdll_sha256': new['ntdll_sha256'], 'wow64_sha256': new['wow64_sha256']},
    }
    for name, expected in checks.items():
        report = read(WORK/name)
        if report.get('passed') is not True or any(report.get(k) != v for k, v in expected.items()):
            raise ValueError('Invalid/stale receipt '+name)
        for path, digest in report.get('source_hashes', report.get('source_sha256', {})).items():
            checked(ROOT/path, digest)
        files['evidence/'+name] = (WORK/name).read_bytes()
    evidence = ROOT/'local/fex3/camera-feedback'/INPUT
    checked(evidence/'fex-runtime.log', INPUT)
    checked(ROOT/'TEST RESULT/fex-runtime.log', INPUT)
    for name, hash_key in (('pacing.json', 'sha256'), ('summary.json', 'input_sha256')):
        data = (evidence/name).read_bytes()
        if json.loads(data)[hash_key] != INPUT:
            raise ValueError('Input analysis mismatch')
        files['evidence/input/'+name] = data
    for name in ('runtime-build.json', 'wine-patches.json'):
        files['evidence/runtime/'+name] = (WORK/'runtime'/name).read_bytes()
    for name in (*new['patch_sources'], 'tools/package-fex3-camera-720.py',
                 'tools/pes13_benchmark_settings.py', 'tools/make-settings.py',
                 'tools/analyze-fex-pacing.py', 'tools/package-fex3-stability.py',
                 'tests/fex_jit_log_queue.py', 'tests/fex_reservations.py',
                 'tests/fex_resume_gate.py', 'tests/fex_resume_binary.py',
                 'tests/fex_self_suspend_binary.py', 'tests/fex_pipeline_binary.py',
                 'tests/fex_unwind.py', 'tests/fex_alloc.py'):
        files['source/'+name] = (ROOT/name).read_bytes()
    expected = sorted(manifest['replaces'])
    if len(expected) != 6:
        raise ValueError('Expected six active files')
    settings_paths = [name for name in expected if name.endswith('/settings.dat')]
    if len(settings_paths) != 3:
        raise ValueError('Expected three settings paths')
    original = files[settings_paths[0]]
    if sha(original) != '687783dded4ef209a2a3196aee11f111810ed64e663d057661fb7dce3230f4f9':
        raise ValueError('Unexpected baseline settings')
    if any(files[name] != original for name in settings_paths):
        raise ValueError('Baseline settings disagree')
    settings_reports = {}
    variants = [('540-original', 960, 540, False), ('720-original', 1280, 720, False),
                ('720-medium-candidate', 1280, 720, True)]
    for label, width, height, candidate in variants:
        data, report = preset(original, width, height, medium_candidate=candidate)
        settings_reports[label] = report
        for name in settings_paths:
            files['benchmark/'+label+'/'+name] = data
            if candidate:
                files[name] = data
        if label == '540-original' and data != original:
            raise ValueError('540p comparison differs from baseline')
    files['evidence/settings.json'] = encoded(settings_reports)
    (WORK/'settings.json').write_bytes(files['evidence/settings.json'])
    if sorted(n for n in files if n.startswith('switch/')) != expected:
        raise ValueError('Overlay boundary')
    if sorted(n.removeprefix('rollback/') for n in files if n.startswith('rollback/')) != expected:
        raise ValueError('Rollback boundary')
    bench_expected = sorted('benchmark/'+label+'/'+name for label, *_ in variants for name in settings_paths)
    if sorted(n for n in files if n.startswith('benchmark/')) != bench_expected:
        raise ValueError('Benchmark boundary')
    for name in expected:
        if name != NRO and name not in settings_paths and files[name] != files['rollback/'+name]:
            raise ValueError('Unexpected payload change '+name)
    result = {'kind': 'Bounded JIT statistics queue; 720p Medium candidate; VSync off',
              'hardware_tested': False, 'slowmo_fix_verified': False,
              'stutter_fix_verified': False, 'kickoff_fix_verified': False,
              'requires_existing_build': 'pes13-fex3-worker-cores',
              'baseline_package_sha256': BASE, 'replaces': expected,
              'native_source_delta': delta, 'native_elf_sha256': new['native_elf_sha256'],
              'nro_sha256': new['nro_sha256'], 'dll_sha256': manifest['dll_sha256'],
              'active_settings': settings_reports['720-medium-candidate'],
              'baseline_log_sha256': INPUT, 'files': {n: sha(b) for n, b in sorted(files.items())}}
    files['manifest.json'] = encoded(result)
    output = ROOT/'dist/pes13-fex3-camera-720.zip'; folder = output.with_suffix('')
    if output.exists() or folder.exists():
        raise FileExistsError('Preserve existing artifact')
    with tempfile.TemporaryDirectory(prefix='fex-camera-', dir=output.parent) as tmp:
        path = Path(tmp)/'package.zip'
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                if name.startswith('/') or '..' in Path(name).parts:
                    raise ValueError('Unsafe archive path')
                info = zipfile.ZipInfo(name, (2026,9,28,0,0,0)); info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16; archive.writestr(info, data)
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() or set(archive.namelist()) != set(files):
                raise ValueError('ZIP integrity')
            for name, data in files.items():
                if archive.read(name) != data:
                    raise ValueError('ZIP readback '+name)
        with output.open('xb') as stream: stream.write(path.read_bytes())
    folder.mkdir()
    for name, data in files.items():
        path = folder/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        if path.read_bytes() != data:
            raise ValueError('Folder readback '+name)
    report = {'passed': True, 'path': str(output), 'bytes': output.stat().st_size,
              'sha256': sha(output.read_bytes()), 'files': len(files), 'replaces': expected,
              'settings': settings_reports}
    (WORK/'package.json').write_bytes(encoded(report))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
