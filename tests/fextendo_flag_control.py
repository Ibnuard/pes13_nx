"""Check the actual ARM64 Wine environment constructor's optimization policy.

This checks propagation into the guest PEB, not a successful PES launch or a
claim that FEX_O0 is equivalent to Box64 SAFEFLAGS. Kernel/files are modeled.
"""
import argparse
import gc
import hashlib
import json
import struct
from pathlib import Path
from fextendo_process_params_binary import Model as Base, reg


class Model(Base):
    def __init__(self, path, maxinst, disk, debug):
        super().__init__(path)
        self.options = {'fex_jit_large': maxinst == 5000,
                        'fex_jit_small': maxinst == 128,
                        'fex_diskcache': disk}
        self.debug = debug
        # The constructor may inline wine_nx_launch_debug_active().
        self.vm.mem_write(self.symbols['fx_debug_enabled'], struct.pack('<I', int(debug)))

    def hook(self, vm, pc, size, user):
        if pc == self.symbols.get('wine_nx_config_file_bool'):
            key = self.string(vm.reg_read(reg(0))).rsplit('/', 1)[-1]
            self.ret(int(self.options.get(key, vm.reg_read(reg(1)))))
        elif pc == self.symbols.get('wine_nx_launch_debug_active'):
            self.ret(int(self.debug))
        else:
            super().hook(vm, pc, size, user)

    def call(self, name, *args):
        result = super().call(name, *args)
        if name == self.constructor:
            self.params = result
        return result

    def guest_environment(self):
        self.create('C:\\PES13\\pes2013.exe')
        p = self.uq(self.params + 0x80)
        entries = []
        while self.vm.mem_read(p, 2) != b'\0\0':
            text = self.wide(p)
            entries.append(text)
            p += (len(text) + 1) * 2
            assert len(entries) < 100
        assert len({s.split('=', 1)[0] for s in entries}) == len(entries), entries
        return dict(s.split('=', 1) for s in entries)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--expected-o0', choices=('0', '1'), default='0')
    a = p.parse_args()
    cases = []
    for maxinst in (128, 500, 5000):
        for disk in (False, True):
            for debug in (False, True):
                m = Model(a.elf, maxinst, disk, debug)
                env = m.guest_environment()
                assert env['FEX_O0'] == a.expected_o0, env
                assert env['FEX_MAXINST'] == str(maxinst)
                assert env['FEX_DISKCACHE'] == str(int(disk))
                assert env['WINEDEBUG'] == ('err+all,warn+all' if debug else '-all'), (debug, env)
                cases.append({'maxinst': maxinst, 'disk_cache': disk, 'debug': debug})
                del m
                gc.collect()
    report = {'passed': True, 'hardware_tested': False,
              'native_elf_sha256': hashlib.sha256(a.elf.read_bytes()).hexdigest(),
              'cases': cases,
              'expected_o0': a.expected_o0,
              'checks': ['Guest UTF-16 environment contains exactly one FEX_O0=' + a.expected_o0,
                         'All six MaxInst/cache combinations retain their selected settings',
                         'Debug and normal launches retain their different WINEDEBUG policies'],
              'limits': 'Verifies constructor output, not FEX execution or patch compatibility.'}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
