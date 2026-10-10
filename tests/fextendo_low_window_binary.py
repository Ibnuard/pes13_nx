"""Execute the shipped ARM64 forwarder with the Sleeping Dogs startup model.

The real libnx/newlib allocator, reservations and NRO loading run in Unicorn.
Only Horizon calls are modeled. This does not emulate the kernel or prove that
the custom kernel/loader can boot on a Switch.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--output', type=Path, default=ROOT / 'dist/fextendo-low-window-v1')
    p.add_argument('--reference-model', type=Path, default=ROOT.parent / 'sleepingdogs-fex/tests/check_forwarder_startup_binary.py')
    a = p.parse_args()
    assert sha(a.reference_model) == '266201a512745ef67a7144bdb7da2dc9c15d9ec40fa8098792809df23c0647f1'
    spec = importlib.util.spec_from_file_location('forwarder_startup_reference', a.reference_model)
    ref = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ref)
    ref.NRO_PATH = b'/switch/fextendo-memory-probe/fextendo-memory-probe.nro'
    build = json.loads((a.output / 'probe-build.json').read_text())
    elf = a.work / 'forwarder.elf'
    nro_path = a.output / build['target'].lstrip('/')
    assert sha(elf) == build['forwarder_elf_sha256']
    assert sha(nro_path) == build['nro_sha256']

    class Forwarder(ref.Forwarder):
        def hook(self, vm, pc, size, unused):
            if getattr(self, 'control', False) and self.hooks.get(pc) == 'svcGetInfo' and self.x(1) in (12, 13):
                self.q(self.x(0), 0x8000000 if self.x(1) == 12 else 0x8000000000 - 0x8000000)
                self.ret()
            else:
                super().hook(vm, pc, size, unused)

    cases = []
    for control in (False, True):
        for label, rng in (('low-rng-candidate', [0, 0x100000]), ('high-rng-candidate', 0x4000000)):
            Forwarder.control = control
            model = Forwarder(elf, nro_path.read_bytes(), rng)
            lo, hi = (model.uq(model.symbols[n]) for n in ('fake_heap_start', 'fake_heap_end'))
            assert hi - lo == 16384 and model.bias <= lo < hi <= model.image_end
            model.call('loadNro', handoff=True)
            assert model.abort is None and model.handoff and model.alloc_calls == [32]
            reservation = model.uq(model.symbols['fxt_guest_reservation'])
            assert lo <= reservation and reservation + 32 <= hi
            assert model.uq(reservation + 16) == 0x200000
            assert model.uq(reservation + 24) == 0x100000000
            assert model.handoff[3] == (1, model.heap + model.map_size, model.heap_size - model.map_size)
            assert model.handoff[10][1] == 43
            model.vm.mem_write(model.symbols['g_nextArgv'], ref.NRO_PATH + b'\0')
            model.call('loadNro', handoff=True)
            assert model.abort is None and model.handoff and len(model.maps) == 2 and len(model.unmaps) == 3
            assert model.alloc_calls == [32] and model.uq(model.symbols['fxt_guest_reservation']) == reservation
            assert model.call('__libnx_alloc', 32768) == 0 and model.abort is None
            spare = model.call('__libnx_alloc', 32)
            assert lo <= spare and spare + 32 <= hi
            model.call('__libnx_free', spare)
            assert model.uq(model.symbols['g_Reservations']) == reservation
            cases.append({'control': control, 'case': label, 'native_nro': hex(model.maps[0][1]),
                          'reload': 'PASS', 'allocator_bounds': 'PASS'})
            model.close()
    report = {'status': 'PASS', 'hardware_tested': False, 'cases': cases,
              'forwarder_elf_sha256': sha(elf), 'nro_sha256': sha(nro_path),
              'reference_model_sha256': sha(a.reference_model), 'test_sha256': sha(Path(__file__))}
    (a.output / 'forwarder-tests.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS real ARM64 forwarder: control/opt-in layouts, startup, reload, allocator exhaustion/free')


if __name__ == '__main__': main()
