"""Execute linked ARM64 self-suspend using a private condition, not shared herd.

Kernel/transport boundaries modeled. No claim about Switch fairness or gameplay.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

from unicorn import arm64_const as arm
from fex_self_suspend_binary import Model as SharedModel, reg


class Model(SharedModel):
    def hook(self, vm, pc, size, user):
        if pc in {self.symbols.get('pthread_cond_signal'), self.symbols.get('pthread_cond_broadcast')}:
            assert self.locked, 'Notification must hold predicate mutex'
            kind = 'signal' if pc == self.symbols.get('pthread_cond_signal') else 'broadcast'
            self.notifications.append((kind, vm.reg_read(reg(0))))
            self.ret()
        elif pc == self.symbols.get('condvarWaitTimeout'):
            assert self.locked and self.reply is None and self.steps
            condition = vm.reg_read(reg(0))
            assert condition != self.symbols['horizon_server_objects_cond'] + 8, 'Self-suspend still waits on shared broadcast'
            assert self.stack <= condition < self.stack + 0x10000, 'Private waiter must live in blocked handler stack'
            assert vm.reg_read(reg(1)) == self.symbols['horizon_server_objects_mutex'] + 4
            assert vm.reg_read(reg(2)) == 20000000, 'Preserve 20ms safety recheck'
            assert self.uw(self.obj + 40 + 56) == 1
            assert self.uw(self.symbols['horizon_server_sleepers']) == 0, 'Private waiter counted as global sleeper'
            self.locked = False
            count, terminated = self.steps.pop(0)
            self.w(self.obj + 40 + 52, count)
            self.w(self.obj + 40 + 48, terminated)
            self.locked = True
            self.waits += 1
            self.ret()
        else:
            super().hook(vm, pc, size, user)

    def resume(self, count, *, started=1, parked=1, valid=True):
        # Initialize the same real handle/thread wire layouts used by run().
        assert self.run(started=0, self_request=False) == (0, 1, 0)
        self.w(self.obj + 40 + 44, started)
        self.w(self.obj + 40 + 52, count)
        self.w(self.obj + 40 + 56, parked)
        first, second = self.data + 0x2000, self.data + 0x2040
        # Synthetic waiter records exercise real linked notifier traversal.
        # The unrelated record is first; tids/handles do not define identity.
        self.vm.mem_write(first, bytes(128))
        self.q(first, second)
        self.q(first + 8, self.obj + 0x200)
        self.q(second + 8, self.obj)
        self.q(self.symbols['fex_resume_waiters'], first)
        self.w(self.symbols['horizon_server_sleepers'], 1)
        self.w(self.symbols['wine_nx_fex_targeted_wake'], 0)
        self.vm.mem_write(self.request, struct.pack('<6I', 0, 0, 0, 0x100 if valid else 99, 0, 0))
        self.notifications, self.reply, self.returned = [], None, False
        self.vm.reg_write(arm.UC_ARM64_REG_SP, self.stack + 0xf000)
        self.vm.reg_write(reg(30), self.stop)
        self.vm.reg_write(reg(0), self.conn)
        self.vm.reg_write(reg(1), self.request)
        self.vm.emu_start(self.symbols['horizon_server_handle_resume_thread'], 0, count=100000)
        assert self.returned and self.reply is not None and not self.locked
        status, size, previous = struct.unpack('<3I', self.reply[:12])
        assert size == 0 and previous == (count if valid else 0)
        assert status == (0 if valid else 0xc0000008)
        assert self.uw(self.obj + 40 + 52) == (max(count - 1, 0) if valid else count)
        if valid and count == 1 and parked:
            expected = [('signal', second + 16)]
        elif valid and count == 1 and not started:
            expected = [('broadcast', self.symbols['horizon_server_objects_cond'])]
        else:
            expected = []
        assert self.notifications == expected, (self.notifications, expected)
        self.q(self.symbols['fex_resume_waiters'], 0)
        self.w(self.symbols['horizon_server_sleepers'], 0)


def validate(path):
    if not __debug__:
        raise RuntimeError('Resume-gate validation requires assertions; disable -O/-OO and PYTHONOPTIMIZE')
    model = Model(path)
    assert model.run(steps=((1, 0), (2, 0), (1, 0), (0, 0))) == (0, 0, 4)
    assert model.run(handle=0xfffffffe, steps=((0, 0),)) == (0, 0, 1)
    assert model.run(steps=((0, 1),)) == (0xc0000022, 0, 1)
    assert model.run(self_request=False) == (0xc00000bb, 0, 0)
    assert model.run(terminated=1) == (0xc0000022, 0, 0)
    assert model.run(count=127) == (0xc000004a, 127, 0)
    assert model.run(handle=99) == (0xc0000008, 0, 0)
    assert model.run(started=0, self_request=False, count=3) == (0, 4, 0)
    model.resume(1)
    model.resume(2)
    model.resume(0)
    model.resume(1, valid=False)
    model.resume(1, started=0, parked=0)
    model.resume(2, started=0, parked=0)
    model.resume(1, parked=0)
    return {'passed': True, 'hardware_tested': False, 'scenarios': 15,
            'native_elf_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'scope': __doc__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = validate(args.elf)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
