"""Execute linked ARM64 yield/delay paths with modeled kernel/time boundaries.

Checks syscall arguments and unchanged delay semantics, not Horizon scheduling
fairness, frame pacing, GPU time, or game performance.
"""
from pathlib import Path
import argparse
import hashlib
import json
import struct

from unicorn import arm64_const as arm
from fex_reservations import Model as NativeModel, reg


class Model(NativeModel):
    def __init__(self, path):
        super().__init__(path)
        self.calls = []
        self.now = 1000000000
        self.tls = self.data + 0x1000

    def hook(self, vm, pc, size, user):
        s = self.symbols
        if pc == s.get('svcSleepThread'):
            raw = vm.reg_read(reg(0))
            nano = raw if raw < 1 << 63 else raw - (1 << 64)
            self.calls.append(nano)
            if nano > 0:
                self.now += (nano + 99) // 100
            self.ret()
        elif pc == s.get('NtQuerySystemTime'):
            vm.mem_write(vm.reg_read(reg(0)), struct.pack('<q', self.now))
            self.ret()
        elif pc == s.get('gettimeofday'):
            # Release builds inline NtQuerySystemTime into NtDelayExecution.
            seconds, remainder = divmod(self.now - 116444736000000000, 10000000)
            vm.mem_write(vm.reg_read(reg(0)), struct.pack('<qq', seconds, remainder // 10))
            self.ret()
        elif pc in {s.get('NtCurrentTeb'), s.get('wine_nx_fex_frame_tick')}:
            self.ret(0)
        elif pc == s.get('__aarch64_read_tp'):
            self.ret(self.tls)
        elif pc == s.get('wine_nx_fex_delay_note'):
            self.ret()
        else:
            super().hook(vm, pc, size, user)

    def run(self, function, timeout=None):
        self.calls, self.returned = [], False
        self.now = 1000000000
        self.vm.reg_write(arm.UC_ARM64_REG_SP, self.stack + 0xf000)
        self.vm.reg_write(reg(30), self.stop)
        self.vm.reg_write(reg(0), 0)
        if function == 'NtDelayExecution':
            self.vm.mem_write(self.data, struct.pack('<q', timeout))
            self.vm.reg_write(reg(1), self.data)
        self.vm.emu_start(self.symbols[function], 0, count=100000)
        assert self.returned, 'Yield/delay did not return in bounded instruction budget'
        status = self.vm.reg_read(reg(0)) & 0xffffffff
        assert status == 0, ('status', hex(status))
        return self.calls


def validate(path, expected):
    # This model and NativeModel rely on assertions for validation safety.
    if not __debug__:
        raise RuntimeError('Same-core validation requires Python assertions; disable -O/-OO and PYTHONOPTIMIZE')
    model = Model(path)
    cases = [('NtYieldExecution', None, [expected]),
             ('NtDelayExecution', 0, [expected]),
             ('NtDelayExecution', -10000, [expected, 1000000]),
             ('NtDelayExecution', -50000, [expected, 5000000]),
             ('NtDelayExecution', 999999999, [expected])]
    checks = []
    for function, timeout, wanted in cases:
        actual = model.run(function, timeout)
        assert actual == wanted, (function, timeout, actual, wanted)
        checks.append({'function': function, 'timeout_100ns': timeout, 'svc_sleep_ns': actual})
    return {'passed': True, 'hardware_tested': False, 'scope': __doc__,
            'expected_yield_ns': expected, 'checks': checks,
            'native_elf_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--expected-yield', type=int, choices=(-1, 0), required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = validate(args.elf, args.expected_yield)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
