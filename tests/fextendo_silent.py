"""Run production logging boundaries and maintenance in the delivered ARM64 ELF.

Kernel scheduling and registry/balancer callees are modeled. This does not run
PES13 or certify console behavior. Unknown storage calls fail the checks.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

from fex_reservations import Model as NativeModel, arm, reg


class Model(NativeModel):
    def __init__(self, path):
        super().__init__(path)
        self.maintenance = []
        self.starting = False
        self.environment = []
        self.heap_next = self.data + 0x2000
        self.forbidden = {self.symbols[n] for n in (
            'fopen', 'freopen', 'fwrite', 'fprintf', 'fputs', 'fflush',
            'open', 'write', 'rename', 'unlink', 'fsFileWrite',
        ) if n in self.symbols}
        self.vm.mem_write(self.symbols['wine_nx_config_loaded'], struct.pack('<I', 1))

    def hook(self, vm, pc, size, user):
        if pc == self.stop:
            self.returned = True
            vm.emu_stop()
        elif pc in self.forbidden:
            raise AssertionError('Unexpected I/O from a silent boundary: ' + hex(pc))
        elif pc in {self.symbols.get('horizon_registry_flush'),
                    self.symbols.get('wine_nx_thread_balance')}:
            self.maintenance.append('registry' if pc == self.symbols['horizon_registry_flush'] else 'balance')
            self.ret()
        elif pc == self.symbols.get('memset'):
            dest, value, length = [vm.reg_read(reg(i)) for i in range(3)]
            vm.mem_write(dest, bytes([value & 255]) * length)
            self.ret(dest)
        elif self.starting and pc == self.symbols.get('setenv'):
            self.environment.append((self.string(vm.reg_read(reg(0))), self.string(vm.reg_read(reg(1))), vm.reg_read(reg(2))))
            self.ret()
        elif self.starting and pc == self.symbols.get('wine_nx_sd_cache_install'):
            self.returned = True
            vm.emu_stop()
        elif pc in {self.symbols.get('__libc_lock_acquire'), self.symbols.get('__libc_lock_release')}:
            self.ret()
        elif pc == self.symbols.get('malloc'):
            length = vm.reg_read(reg(0))
            dest = self.heap_next
            self.heap_next += (length + 15) & -16
            assert self.heap_next < self.data + 0xf000
            self.ret(dest)
        elif pc == self.symbols.get('free'):
            self.ret()
        elif pc in {self.symbols.get('__getreent'), self.symbols.get('__errno')}:
            self.ret(self.data + 0x1000)
        # Deliberately do not use NativeModel.hook: it mocks the log callbacks
        # that this test must execute, and could hide a logging regression.

    def string(self, pointer):
        data = bytearray()
        while self.vm.mem_read(pointer + len(data), 1) != b'\0':
            data += self.vm.mem_read(pointer + len(data), 1)
            assert len(data) < 8192
        return data.decode()

    def check_stdio(self):
        self.starting = True
        self.call('main', 0, 0)
        self.starting = False
        assert self.environment == [('WINEDEBUG', '-all', 1)]
        for index in (0, 1, 2):
            assert self.uq(self.symbols['devoptab_list'] + index * 8) == self.symbols['fx_null_device']
        # Execute real libc path dispatch/handle allocation/write/read/close.
        # Only allocator and mutex services are modeled; no SD filesystem call
        # is allowed, and message buffers intentionally point to unmapped RAM.
        self.vm.mem_write(self.data, b'fextendo-null:/stdio\0')
        reent = self.data + 0x1000
        for flags in (0, 0x601):
            fd = self.call('_open_r', reent, self.data, flags, 0o666)
            assert 3 <= fd < 1024, fd
            assert self.call('_write_r', reent, fd, 1, 4096) == 4096
            assert self.call('_read_r', reent, fd, 1, 4096) == 0
            assert self.call('_close_r', reent, fd) == 0
        for fd in (1, 2):
            assert self.call('_write_r', reent, fd, 1, 4096) == 4096

    def call(self, name, *args):
        self.returned = False
        self.vm.reg_write(arm.UC_ARM64_REG_SP, self.stack + 0xf000)
        self.vm.reg_write(reg(30), self.stop)
        for i, value in enumerate(args):
            self.vm.reg_write(reg(i), value & 0xffffffffffffffff)
        self.vm.emu_start(self.symbols[name], 0, count=200000)
        assert self.returned, 'Unbounded call: ' + name
        return self.vm.reg_read(reg(0))

    def config(self, key, stored, fallback):
        self.vm.mem_write(self.symbols['wine_nx_config_count'], struct.pack('<I', 1))
        self.vm.mem_write(self.symbols['wine_nx_config_entries'],
                          key.encode().ljust(64, b'\0') + struct.pack('<I', stored))
        self.vm.mem_write(self.data, ('sdmc:/switch/pes13-fex/' + key + '.txt\0').encode())
        return self.call('wine_nx_config_file_bool', self.data, fallback)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--nro', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    m = Model(args.elf)
    m.check_stdio()
    # Even invalid message pointers are ignored, without touching storage.
    m.call('wine_nx_runtime_trace', 1)
    m.call('horizon_trace', 1)
    m.call('wine_nx_runtime_std_write', 2, 1, 1048576)
    m.call('wine_nx_runtime_dump_std_streams')
    m.vm.mem_write(m.data, b'error and warning output\n\0')
    assert m.call('__wine_dbg_output', m.data) == len(b'error and warning output\n')
    for count in (0, 1, 4096, 1048576):
        assert m.call('fx_null_write', 0, 0, 1, count) == count
        assert m.call('fx_null_read', 0, 0, 1, count) == 0
    assert m.call('fx_null_open', 0, 0, 1, 0, 0) == 0
    assert m.call('fx_null_close', 0, 0) == 0
    assert m.call('fx_null_seek', 0, 0, 4096, 0) == 0
    assert m.call('fx_null_fstat', 0, 0, m.data) == 0
    for key in ('run_guest_tests', 'verbose', 'profile', 'controller_trace',
                'controller_test', 'vulkan_probe', 'fex_hot_profile',
                'fex_gap_probe', 'fex_jitlog_sync', 'fex_game_timing', 'fex_event_diagnostic'):
        assert m.config(key, 1, 1) == 0, key
    for key in ('production', 'fex_short_trace_off'):
        assert m.config(key, 0, 0) == 1, key
    for key in ('fex_fast_api', 'fex_diskcache', 'fex_auto_core3'):
        for value in (0, 1):
            assert m.config(key, value, 1 - value) == value, key
    for tick in range(1, 101):
        before = len(m.maintenance)
        m.call('fx_production_maintenance_tick', tick)
        assert m.maintenance[before:] == (['registry'] if tick % 5 == 0 else []) + (['balance'] if tick % 10 == 0 else [])
    blob = args.nro.read_bytes()
    for path in (b'fex-runtime.log', b'horizon-trace.log', b'/stdout.txt', b'/stderr.txt', b'/stdin.txt', b'WINE_FTRACE_FILE'):
        assert path not in blob, path
    for setting in (b'FEXTENDO_TRACE=0', b'DXVK_LOG_LEVEL=none', b'DXVK_LOG_PATH=none', b'WINEDEBUG=-all', b'fextendo-null:/stdio'):
        assert setting in blob, setting
    report = {
        'passed': True, 'hardware_tested': False,
        'native_elf_sha256': hashlib.sha256(args.elf.read_bytes()).hexdigest(),
        'nro_sha256': hashlib.sha256(blob).hexdigest(),
        'checks': [
            'ARM64 runtime/Horizon/Wine log callbacks execute without I/O',
            'ARM64 null device accepts writes, returns EOF, supports open/close/seek/stat',
            'Real ARM64 startup installs the sink before SD setup; libc routes stdio and opened handles to it',
            'Hostile diagnostic INI values cannot enable logs; performance/cache settings preserved',
            '100 maintenance ticks retain registry every second and balancing every two seconds',
            'NRO excludes log file paths and contains silent settings for guest renderers',
        ],
    }
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
