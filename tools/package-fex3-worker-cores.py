"""Package automatic worker placement with the existing emitter/VSync/540p profile."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT/'local/fex3/worker-cores'
NRO = 'switch/pes13-fex/pes13-fex.nro'
INPUT = 'c70e5f21777ed3b96367df8e22f2d9451f56d52d157861cc8b51a8a9ba166782'


def sha(data): return hashlib.sha256(data).hexdigest()
def read(path): return json.loads(path.read_text())


def checked(path, digest):
    data = path.read_bytes()
    if sha(data) != digest:
        raise ValueError('Hash mismatch '+str(path))
    return data


def main():
    spec = importlib.util.spec_from_file_location('stable', ROOT/'tools/package-fex3-stability.py')
    stable = importlib.util.module_from_spec(spec); spec.loader.exec_module(stable)
    base = ROOT/'dist/pes13-fex3-sleep-deadline.zip'
    checked(base, '300b5ee9cb3076206e6279cde520b303008a8e6e186beb3d74d1ba7047e0e279')
    files = {}
    with zipfile.ZipFile(base) as archive:
        if archive.testzip():
            raise ValueError('Corrupt baseline ZIP')
        manifest = json.loads(archive.read('manifest.json'))
        if set(archive.namelist()) != set(manifest['files']) | {'manifest.json'}:
            raise ValueError('Unlisted baseline member')
        for name, digest in manifest['files'].items():
            data = archive.read(name)
            if sha(data) != digest:
                raise ValueError('Baseline member mismatch '+name)
            if name.startswith('switch/'):
                files[name] = data; files['rollback/'+name] = data
            elif name.startswith('evidence/'):
                files['evidence/sleep-deadline/'+name.removeprefix('evidence/')] = data
            elif name.startswith('source/'):
                files['source/sleep-deadline/'+name.removeprefix('source/')] = data
            elif name.startswith('licenses/') or name == 'THIRD_PARTY.md':
                files[name] = data
    new = read(WORK/'runtime/runtime-build.json')
    old = read(ROOT/'local/fex3/sleep-deadline/runtime/runtime-build.json')
    for flag in ('worker_cores', 'sleep_deadline', 'jit_latency', 'warm_audit', 'hang_audit',
                 'stability', 'samecore_yield', 'resume_gate'):
        if new.get(flag) is not True:
            raise ValueError('Missing build flag '+flag)
    for key in ('native_dependencies', 'ntdll_sha256', 'wow64_sha256', 'guest_sha256',
                'toolchain_path', 'adapter_sources'):
        if new[key] != old[key]:
            raise ValueError('Unexpected dependency delta '+key)
    for name, digest in new['patch_sources'].items(): checked(ROOT/name, digest)
    for name, digest in new['adapter_sources'].items(): checked(ROOT/'src/fex'/name, digest)
    np = read(WORK/'runtime/wine-patches.json')
    op = read(ROOT/'local/fex3/sleep-deadline/runtime/wine-patches.json')
    if np['pe-source'] != op['pe-source']:
        raise ValueError('PE source changed')
    delta = sorted(k for k in np['native-source'].keys() | op['native-source'].keys()
                   if np['native-source'].get(k) != op['native-source'].get(k))
    if delta != ['dlls/ntdll/unix/horizon.c', 'wine-nx-probe/source/runtime.c',
                 'wine-nx-probe/source/thread_profile.c']:
        raise ValueError('Unexpected native source delta: '+repr(delta))
    nro = checked(WORK/'runtime/payload/pes13-fex.nro', new['nro_sha256'])
    elf = WORK/'runtime/reference/pes13-fex.elf'
    checked(elf, new['native_elf_sha256']); stable.verify_executable(elf, nro)
    for marker in (b'pes13-fex3-worker-cores', b'[FEX3-CORES] v1',
                   b'[FEX3-COREMAP]', b'[FEX3-SLEEP] v1'):
        if marker not in nro:
            raise ValueError('Missing marker '+str(marker))
    files[NRO] = nro
    if sha(files['rollback/'+NRO]) != old['nro_sha256']:
        raise ValueError('Rollback NRO mismatch')
    files['README.md'] = (ROOT/'docs/FEX3-WORKER-CORES.md').read_bytes()
    checks = {
        'cores.json': {'native_elf_sha256': new['native_elf_sha256'],
                       'before_native_elf_sha256': old['native_elf_sha256']},
        'resume.json': {'native_elf_sha256': new['native_elf_sha256']},
        'pipeline.json': {'native_elf_sha256': new['native_elf_sha256']},
        'unwind.json': {'native_elf_sha256': new['native_elf_sha256'],
                        'fex_sha256': manifest['dll_sha256'],
                        'ntdll_sha256': new['ntdll_sha256'], 'wow64_sha256': new['wow64_sha256']},
    }
    for name, expected in checks.items():
        r = read(WORK/name)
        if r.get('passed') is not True or any(r.get(k) != v for k, v in expected.items()):
            raise ValueError('Invalid/stale receipt '+name)
        for path, digest in r.get('source_hashes', r.get('source_sha256', {})).items():
            checked(ROOT/path, digest)
        for path, digest in r.get('generated_source_hashes', {}).items():
            if np['native-source'].get(path) != digest:
                raise ValueError('Generated test source mismatch '+path)
        files['evidence/'+name] = (WORK/name).read_bytes()
    evidence = ROOT/'local/fex3/worker-placement'/INPUT
    checked(evidence/'fex-runtime.log', INPUT)
    for name in ('pacing.json', 'worker-timeline.json'):
        data = (evidence/name).read_bytes()
        if json.loads(data)['sha256'] != INPUT:
            raise ValueError('Input analysis mismatch')
        files['evidence/input/'+name] = data
    for name in ('runtime-build.json', 'wine-patches.json'):
        files['evidence/runtime/'+name] = (WORK/'runtime'/name).read_bytes()
    for name in (*new['patch_sources'], 'tools/package-fex3-worker-cores.py',
                 'tests/fex_worker_cores.py', 'tests/fex_reservations.py',
                 'tests/fex_resume_gate.py', 'tests/fex_resume_binary.py',
                 'tests/fex_self_suspend_binary.py', 'tests/fex_pipeline_binary.py',
                 'tests/fex_unwind.py', 'tests/fex_alloc.py'):
        files['source/'+name] = (ROOT/name).read_bytes()
    expected = sorted(manifest['replaces'])
    if sorted(n for n in files if n.startswith('switch/')) != expected:
        raise ValueError('Overlay boundary')
    if sorted(n.removeprefix('rollback/') for n in files if n.startswith('rollback/')) != expected:
        raise ValueError('Rollback boundary')
    if len(expected) != 6:
        raise ValueError('Expected six active files')
    for name in expected:
        if name != NRO and files[name] != files['rollback/'+name]:
            raise ValueError('Unexpected payload change '+name)
        if name.endswith('/settings.dat'):
            data = files[name]
            if len(data) != 852 or struct.unpack_from('<HII', data, 14) != (0x288, 960, 540):
                raise ValueError('Settings mismatch '+name)
    result = {'kind': 'Automatic Wine workers prefer cores 0-2; emitter/VSync-off/540p combined',
              'hardware_tested': False, 'slowmo_fix_verified': False, 'stutter_fix_verified': False,
              'requires_existing_build': 'pes13-fex3-sleep-deadline', 'replaces': expected,
              'native_source_delta': delta, 'native_elf_sha256': new['native_elf_sha256'],
              'nro_sha256': new['nro_sha256'], 'dll_sha256': manifest['dll_sha256'],
              'baseline_log_sha256': INPUT, 'files': {n: sha(b) for n, b in sorted(files.items())}}
    files['manifest.json'] = (json.dumps(result, indent=2)+'\n').encode()
    output = ROOT/'dist/pes13-fex3-worker-cores.zip'; folder = output.with_suffix('')
    if output.exists() or folder.exists():
        raise FileExistsError('Preserve existing artifact')
    with tempfile.TemporaryDirectory(prefix='fex-cores-', dir=output.parent) as tmp:
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
              'sha256': sha(output.read_bytes()), 'files': len(files), 'replaces': expected}
    (WORK/'package.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
