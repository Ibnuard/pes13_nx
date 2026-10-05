"""Fault-inject real repair filesystem operations and restart recovery."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sha = lambda b: hashlib.sha256(b).hexdigest()
names = ['drive_c/windows/system32/runtime.dll', 'drive_c/windows/syswow64/test.dll', 'launcher/renderers/dxvk-3.1.1/d3d9.dll']
good = {n: (n.encode() + b'\0') * 3000 for n in names}
old = {names[0]: b'corrupt dll', names[2]: b'corrupt renderer'}
keep = {'drive_c/PES13/pes2013.exe': b'game', 'drive_c/PES13/rld.dll': b'private',
        'drive_c/PES13/settings.dat': b'settings', 'user.reg': b'registry',
        'drive_c/KONAMI/save/test': b'save', 'launcher/renderer-choice.txt': b'1\n',
        'pes13-fex.nro': b'installed NRO'}


def main():
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        archive = temp / 'package.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for n, data in good.items():
                z.writestr('switch/pes13-fex/' + n, data)
            z.writestr('switch/pes13-fex/../../escape', b'must never be extracted')
            z.writestr('switch/pes13-fex/drive_c/PES13/pes2013.exe', b'must not replace game')
        raw = archive.read_bytes()
        catalog = ['#define FXR_COUNT 3', '#define FXR_CATALOG_ID "' + 'a' * 64 + '"',
                   '#define FXR_ARCHIVE_SIZE ' + str(len(raw)), '#define FXR_ARCHIVE_SHA "' + sha(raw) + '"']
        # Header included after the production declaration, via a guarded test include.
        catalog += ['#define FXR_TEST_FILES {']
        text = '\n'.join(catalog[:-1]) + '\n'
        (temp / 'fixture_catalog.h').write_text(text)
        source = (ROOT / 'tests/fextendo_runtime_fixer_driver.c').read_text().replace(
            '#include "../src/runtime/fextendo_runtime_fixer.h"',
            '#define FXR_TEST_DEFINE static const struct fxr_file fxr_files[FXR_COUNT] = {' +
            ','.join('{' + json.dumps(n) + ',' + str(len(data)) + ',"' + sha(data) + '"}' for n, data in good.items()) + '};\n' +
            '#include "' + (ROOT / 'src/runtime/fextendo_runtime_fixer.h').as_posix() + '"')
        (temp / 'driver.c').write_text(source)
        binary = temp / 'driver'
        subprocess.run(['gcc', '-std=gnu99', '-g', '-O1', '-Wall', '-Wextra', '-Wno-deprecated-declarations',
                        '-fsanitize=undefined', str(temp / 'driver.c'), '-o', str(binary), '-lminizip', '-lz', '-lcrypto'], check=True)
        counter = 0

        def fixture():
            nonlocal counter
            counter += 1
            root = temp / ('run' + str(counter))
            root.mkdir()
            for n, data in (old | keep).items():
                p = root / n
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
            return root

        def run(root, op, fail=0, crash=0, cancel=-1, package=archive):
            r = subprocess.run([str(binary), str(root), str(package), op, str(fail), str(crash), str(cancel)], capture_output=True, text=True)
            assert 'runtime error:' not in r.stderr, r.stderr
            assert r.returncode in (0, 1, 77), r.stderr
            return r

        def snapshot(root):
            return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file() and '.runtime-fixer' not in p.parts}

        def intact(root):
            state = snapshot(root)
            assert all(state[n] == d for n, d in keep.items()), state
            assert set(state) <= set(keep) | set(good)
            subset = {n: d for n, d in state.items() if n in good}
            assert subset in (old, good), subset.keys()

        root = fixture()
        assert run(root, 'check').returncode == 0
        assert snapshot(root) == old | keep
        assert not (root / '.runtime-fixer').exists(), 'check must be read-only'
        r = run(root, 'repair');assert r.returncode == 0, r.stdout
        assert snapshot(root) == good | keep
        steps = int(re.search(r'steps=(\d+)', r.stdout)[1])
        assert 'changed=0' in run(root, 'check').stdout
        assert run(root, 'recover').returncode == 0
        rollback_point = None
        for mode in ('fail', 'crash'):
            for i in range(1, steps + 1):
                root = fixture()
                r = run(root, 'repair', **{mode: i})
                if mode == 'crash' and (root / '.runtime-fixer/000.old').exists() and (root / '.runtime-fixer/plan').exists():
                    rollback_point = i
                recover = run(root, 'recover')
                assert recover.returncode == 0, (mode, i, r.stdout, recover.stdout)
                intact(root)
                assert run(root, 'recover').returncode == 0
                intact(root)
        assert rollback_point is not None
        root = fixture();run(root, 'repair', crash=rollback_point)
        recovered = run(root, 'recover')
        rollback_steps = int(re.search(r'steps=(\d+)', recovered.stdout)[1])
        for i in range(1, rollback_steps + 1):
            root = fixture();run(root, 'repair', crash=rollback_point)
            run(root, 'recover', crash=i)
            assert run(root, 'recover').returncode == 0
            intact(root)
        root = fixture();run(root, 'repair', crash=rollback_point)
        journal = root / '.runtime-fixer/plan'
        assert journal.exists()
        before = snapshot(root)
        data = bytearray(journal.read_bytes());data[8] ^= 1;journal.write_bytes(data)
        assert run(root, 'recover').returncode == 1
        assert snapshot(root) == before and journal.exists()
        for phase in (0, 2):
            root = fixture()
            assert run(root, 'repair', cancel=phase).returncode == 1
            assert snapshot(root) == old | keep
        damaged = temp / 'bad.zip';damaged.write_bytes(raw[:-1] + bytes([raw[-1] ^ 1]))
        root = fixture();assert run(root, 'repair', package=damaged).returncode == 1
        assert snapshot(root) == old | keep
        root = fixture();outside = temp / 'outside';outside.mkdir()
        (root / 'drive_c/windows/syswow64').mkdir(parents=True)
        (root / 'drive_c/windows/syswow64/test.dll').symlink_to(outside / 'owned')
        assert run(root, 'check').returncode == 1
        assert list(outside.iterdir()) == []
        print(json.dumps({'passed': True, 'hardware_tested': False, 'injected_failures': steps,
                          'power_interruptions': steps, 'recovery_interruptions': rollback_steps,
                          'checks': ['missing and corrupt runtime', 'read-only check', 'damaged journal blocks recovery',
                          'unchanged-file detection', 'idempotent rollback', 'game/save/settings preserved',
                          'checksum rejection', 'cancellation', 'unlisted ZIP paths ignored', 'symlink rejection']}, indent=2))


if __name__ == '__main__':
    main()
