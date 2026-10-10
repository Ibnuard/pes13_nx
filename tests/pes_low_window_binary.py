"""Exercise the shipped PES low-window ELF, with OS/heap/services modeled.

The admission preflight runs relocated above 4 GiB, including real generated
ARM64 code at 4 MiB. The separate Wine tests use high native backing pointers.
This is not a Switch gameplay test or a measurement of available physical RAM.
"""
import argparse
import binascii
import gc
import hashlib
import io
import json
from pathlib import Path
import struct

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_INTR
from unicorn import arm64_const as arm
from fextendo_memory_probe_binary import ProbeModel
from fextendo_startup_binary import Model as Startup
from fextendo_virtmem_binary import Model as Virtmem
from fextendo_page_store_binary import Model as PageStore
from fextendo_commit_binary import Model as Commit, BASE, SIZE
from fextendo_production_binary import Model as Production
from fex_reservations import reg

LOW, HIGH, END = 0x200000, 0x100000000, 1 << 39
MIB = 1024 * 1024


class Buffered:
    def __init__(self, data): self.data = data
    def open(self, mode):
        assert mode == 'rb'
        return io.BytesIO(self.data)
    def read_bytes(self): return self.data


class Preflight(ProbeModel):
    def __init__(self, path, failure=None):
        # Fully relocated PIE: the actual admission check rejects low native
        # code/stack/TLS, so a zero-base emulator load would be misleading.
        self.vm = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        self.failure = failure
        self.events, self.allocations, self.maps, self.reservations = [], {}, {}, {}
        self.map_states = {}
        base = 0x4000000000
        elf = ELFFile(io.BytesIO(path.read_bytes()))
        segments = [s for s in elf.iter_segments() if s['p_type'] == 'PT_LOAD']
        end = max(s['p_vaddr'] + s['p_memsz'] for s in segments)
        self.vm.mem_map(base, (end + 4095) & -4096)
        for s in segments: self.vm.mem_write(base + s['p_vaddr'], s.data())
        for r in elf.get_section_by_name('.relr.dyn').iter_relocations():
            at = base + r['r_offset']
            value = struct.unpack('<Q', self.vm.mem_read(at, 8))[0]
            self.vm.mem_write(at, struct.pack('<Q', base + value))
        self.symbols = {s.name: base + s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
        self.names = {v: k for k, v in self.symbols.items()}
        self.stack, self.data, self.stop, self.backing = 0x200000000, 0x300000000, HIGH, 0x800000000
        for address in (self.stack, self.data, self.stop): self.vm.mem_map(address, 0x20000)
        self.vm.reg_write(arm.UC_ARM64_REG_TPIDRRO_EL0, self.data)
        self.vm.mem_write(self.symbols['fake_heap_start'], struct.pack('<Q', self.backing))
        self.vm.mem_write(self.symbols['fake_heap_end'], struct.pack('<Q', self.backing + 3321602048))
        self.info = {2: 0x5000000000, 4: self.backing, 6: 0xcd500000, 12: LOW, 13: END - LOW, 14: self.stack}
        self.info_calls, self.missing_capability, self.locked = [], None, False
        self.vm.hook_add(UC_HOOK_CODE, self.hook)
        self.vm.hook_add(UC_HOOK_INTR, self.unmodeled_svc)
        if '__wrap_aligned_alloc' in self.symbols:
            self.names[self.symbols['__wrap_aligned_alloc']] = 'aligned_alloc'

    def hook(self, vm, pc, size, user):
        name, x = self.names.get(pc), self.reg
        if name == 'svcGetInfo':
            self.info_calls.append(x(1))
            if self.failure == 'info': self.ret(0xf601)
            else: vm.mem_write(x(0), struct.pack('<Q', self.info[x(1)])); self.ret()
        elif name == 'envIsSyscallHinted': self.ret(x(0) != self.missing_capability)
        elif name == 'virtmemLock': assert not self.locked; self.locked = True; self.ret()
        elif name == 'virtmemUnlock': assert self.locked; self.locked = False; self.ret()
        elif name == 'snprintf': vm.mem_write(x(0), b'modeled error\0'); self.ret(13)
        elif name in ('fopen', 'open', 'write', 'fwrite', 'fsFileWrite'):
            raise AssertionError('Preflight attempted storage I/O: ' + name)
        else: super().hook(vm, pc, size, user)

    def run(self):
        self.vm.reg_write(arm.UC_ARM64_REG_SP, self.stack + 0x1f000)
        self.vm.reg_write(reg(30), self.stop)
        self.vm.emu_start(self.symbols['fxt_low_window_preflight'], self.stop, count=2_000_000)
        assert self.vm.reg_read(arm.UC_ARM64_REG_PC) == self.stop
        assert not self.locked
        return self.reg(0)


class Manager(Virtmem):
    def __init__(self, path, optin=True):
        super().__init__(path)
        self.low, self.high = HIGH if optin else 0x8000000, END
        self.stack_end, self.heap_low, self.heap_end = 0x280000000, 0x800000000, 0xa00000000
        self.info = {2: 0x5000000000, 3: 0x1800000000, 4: self.heap_low, 5: self.heap_end-self.heap_low,
                     12: LOW if optin else 0x8000000, 13: END-(LOW if optin else 0x8000000),
                     14: 0x200000000, 15: 0x80000000}
        self.call('virtmemSetup')

    def hook(self, vm, pc, size, user):
        if self.names.get(pc) == 'svcGetInfo':
            key = vm.reg_read(reg(1))
            if key not in self.info: self.ret(0xf601)  # optional alias-extra query
            else: vm.mem_write(vm.reg_read(reg(0)), struct.pack('<Q', self.info[key])); self.ret()
        else: super().hook(vm, pc, size, user)


class Logging(Production):
    def __init__(self, path):
        super().__init__(path)
        self.info.update({12: LOW, 13: END-LOW, 3: 0x1800000000})

    def hook(self, vm, pc, size, user):
        # Preflight was executed separately, fully relocated, above. This
        # fixture keeps the normal production logger's smaller native layout.
        if pc == self.symbols.get('fxt_low_window_preflight'): self.ret(1)
        else: super().hook(vm, pc, size, user)


class PacingLogging(Logging):
    """Run actual report gates, with unavailable or supplied guest memory."""
    def __init__(self, path):
        super().__init__(path)
        self.guest_reads = 0
        self.guest_settings = None

    def hook(self, vm, pc, size, user):
        if pc == self.symbols.get('wine_nx_fex_timing_read'):
            self.guest_reads += 1
            address, dest, length = [vm.reg_read(reg(i)) for i in range(3)]
            if self.guest_settings is not None and address == 0x19db710 and length in (12, 852):
                vm.mem_write(dest, self.guest_settings[:length]); self.ret(1)
            else: self.ret(0)  # unsupported/unmapped: observe, never force reads
        elif pc == self.symbols.get('threadGetCurHandle'): self.ret(0x99)
        else: super().hook(vm, pc, size, user)

    def call(self, name, *args):
        if name != 'fx_low_window_diagnostics': return super().call(name, *args)
        # All reports run real libc formatting/capture (~300k instructions),
        # unlike the single-line logger covered by the parent 200k bound.
        self.returned = False
        self.vm.reg_write(arm.UC_ARM64_REG_SP, self.stack + 0xf000)
        self.vm.reg_write(reg(30), self.stop)
        for i, value in enumerate(args): self.vm.reg_write(reg(i), value)
        self.vm.emu_start(self.symbols[name], 0, count=600000)
        assert self.returned, 'Unbounded diagnostic report'
        return self.vm.reg_read(reg(0))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf', type=Path); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); data = a.elf.read_bytes(); elf = Buffered(data)
    preflights = []
    for failure in (None, 'info', 'backing', 'query', 'occupied', 'map', 'rx', 'rw', 'none', 'restore', 'data', 'unmap'):
        m = Preflight(elf, failure)
        assert m.run() == int(failure is None), failure
        assert bool(m.maps) == (failure == 'unmap') and bool(m.allocations) == (failure == 'unmap')
        previous = (len(m.events), len(m.info_calls))
        assert m.run() == int(failure is None)
        assert previous == (len(m.events), len(m.info_calls)), 'Preflight must run once per launch'
        preflights.append(dict(failure=failure, passed=True))
        del m; gc.collect()
    for key, value in ((12, 0x8000000), (13, (1 << 36)-LOW), (2, 0x80000000), (4, 0x80000000), (14, 0x80000000)):
        m = Preflight(elf); m.info[key] = value; assert m.run() == 0 and not m.events
        del m; gc.collect()
    for capability in (2, 0x73, 0x77, 0x78):
        m = Preflight(elf); m.missing_capability = capability
        assert m.run() == 0 and not m.events
        del m; gc.collect()
    print('PASS: relocated high-native preflight, low RX/RW/top-page, cached rejection and failure cleanup', flush=True)

    startup = []
    for name, base, end, alias, expected in (
        ('32-no-alias', LOW, 1 << 32, 0, False), ('36-bit', 0x8000000, 1 << 36, 1 << 32, False),
        ('ordinary-39', 0x8000000, END, 0x1800000000, False),
        ('low-window-39', LOW, END, 0x1800000000, True)):
        m = Startup(elf, override=(0x800000000, 3321602048), limit=0)
        m.info = {12: base, 13: end-base, 3: alias, 6: 0xcd500000}
        m.boot()
        assert not m.requests and m.exited is None and not m.aborted
        assert bool(m.reserved) == expected and bool(m.call('wine_nx_launch_memory_compatible')) == expected
        assert m.uq(m.symbols['fake_heap_start']) == 0x800000000
        assert m.uq(m.symbols['fake_heap_end']) == 0x800000000 + 3321602048
        startup.append(dict(mode=name, admitted=expected, loader_heap_preserved=True))
        del m; gc.collect()
    print('PASS: actual libnx pre-main keeps the supplied >3 GiB heap and rejects ordinary layouts', flush=True)

    for optin in (False, True):
        m = Manager(elf, optin)
        assert m.uq(m.symbols['g_AslrRegion']) == (HIGH if optin else 0x8000000)
        for kind in ('virtmemFindCodeMemory', 'virtmemFindAslr', 'virtmemFindStack'):
            for rng in (0, 1, 0x22000, 0xffffffffffffffff):
                m.rng = rng; address = m.search(16*MIB, kind)
                assert address >= (HIGH if optin else m.low)
        if optin:
            m.blocked = [(HIGH, END)]
            assert m.search(MIB) == 0, 'Native exhaustion must not consume the free low guest region'
        del m; gc.collect()
    print('PASS: first native allocation and exhaustive recovery stay above 4 GiB for opt-in', flush=True)

    for failure in (None, 'map', 'unmap'):
        m = PageStore(elf); m.next = 0x800000000
        if failure: m.fail_map = 3
        if failure == 'unmap': m.fail_unmap = 1
        assert bool(m.backing()) == bool(failure)
        assert all(src >= HIGH for src, length in m.maps.values())
        if failure is None:
            assert m.call('horizon_mprotect', BASE, 5*MIB, 1) == 0
            assert m.call('horizon_mprotect', BASE, 5*MIB, 3) == 0
            assert m.call('horizon_munmap', BASE, 5*MIB) == 0
        if failure != 'unmap': assert not m.maps and not m.allocations and not m.reservations
        else: assert m.maps and m.allocations and m.reservations
        del m; gc.collect()
    m = PageStore(elf); m.next = 0x800000000; assert m.section() == 0
    assert all(p >= HIGH for p in m.allocations); del m; gc.collect()
    for fail in ('pages', 'kernel', 'metadata'):
        m = Commit(elf); m.next = 0x800000000; m.prepare()
        if fail == 'pages': m.deny_pages = True
        elif fail == 'kernel': m.fail_map = 1
        else: m.reserve_fail = m.reserve_calls + 2
        assert m.commit() & 0xffffffff == 0xffffffff
        assert m.reservations == m.original and not m.maps
        m.deny_pages = False; m.fail_map = m.reserve_fail = 0
        assert m.commit() == 0 and not m.guard_gaps
        assert all(src >= HIGH for src, length in m.maps.values())
        m.clear(); del m; gc.collect()
    print('PASS: Wine high backing/low views, protection, cleanup, section creation and failed-commit retry', flush=True)
    m = Logging(elf); m.check_stdio()
    assert m.sd_started == 1 and not m.notices
    m.call('fxt_low_window_report')
    m.call('wine_nx_runtime_trace', 1); m.call('horizon_trace', 1)
    m.call('wine_nx_runtime_std_write', 2, 1, 1048576)
    m.call('fx_debug_file_tick'); m.call('fx_crash_bootstrap'); m.call('wine_nx_crash_exception', 1, 0xc0000005)
    assert m.call('fx_debug_file_prepare', 1) == 1
    m.call('fx_launch_debug_begin', 1); m.call('fxt_low_window_report')
    ring = bytes(m.vm.mem_read(m.symbols['fx_debug_ring'], 64*109))
    assert b'[PES13-LOWVA]' in ring
    m.call('fx_launch_debug_begin', 0); m.call('fxt_low_window_report')
    assert bytes(m.vm.mem_read(m.symbols['fx_debug_ring'], 64*109)) == ring
    del m; gc.collect()
    print('PASS: normal launch/report/crash paths perform no diagnostic I/O; debug report enters RAM capture only when enabled', flush=True)
    pacing_gate = live_gate = False
    m = PacingLogging(elf)
    if 'fx_low_window_diagnostics' in m.symbols:
        # Even if a stale enable bit is set, normal launch does not enter a
        # read probe, format metrics, flush files or query a thread clock.
        if 'fex_game_timing_enabled' in m.symbols:
            m.vm.mem_write(m.symbols['fex_game_timing_enabled'], struct.pack('<I', 1))
        live = 'pes_vk_work' in m.symbols
        reads_per_tick = 3 if live else 1
        queries = len(m.queries)
        for tick in (1, 5, 25, 50, 100): m.call('fx_low_window_diagnostics', tick)
        assert m.guest_reads == 0 and len(m.queries) == queries
        m.call('fx_launch_debug_begin', 1)
        m.call('fx_low_window_diagnostics', 1); assert m.guest_reads == 0
        m.call('fx_low_window_diagnostics', 25); assert m.guest_reads == reads_per_tick
        m.call('fx_low_window_diagnostics', 50); assert m.guest_reads == 2*reads_per_tick
        ring = bytes(m.vm.mem_read(m.symbols['fx_debug_ring'], 64*109))
        for token in ((b'[LW3-LIVESET]' if live else b'[FEX3-GAME]'), b'[FEX3-PACE]', b'[FEX3-PIPE]', b'[FEX3-WARM]', b'[LW2-IO]'):
            assert token in ring, token
        m.call('fx_launch_debug_begin', 0); m.call('fx_low_window_diagnostics', 100)
        assert m.guest_reads == 2*reads_per_tick and bytes(m.vm.mem_read(m.symbols['fx_debug_ring'], 64*109)) == ring
        if live:
            assert not m.call('wine_nx_wait_probe_begin',2,77,0,0)
            before = bytes(m.vm.mem_read(m.symbols['pes_vk_work'],256*32))
            m.call('wine_nx_wait_probe_end',0,0)
            assert bytes(m.vm.mem_read(m.symbols['pes_vk_work'],256*32)) == before
            settings = bytearray(852)
            struct.pack_into('<IIIHHIIII',settings,0,0x46434557,2,852,0,0x28b,1280,720,1,1)
            struct.pack_into('<H',settings,12,~binascii.crc_hqx(settings,0)&65535)
            m.guest_settings = bytes(settings)
            m.call('fx_launch_debug_begin',1)
            token = m.call('wine_nx_wait_probe_begin',2,77,0,0)
            assert token
            m.call('wine_nx_wait_probe_end',token,0)
            m.call('fx_low_window_diagnostics',25)
            pending = bytes(m.vm.mem_read(m.symbols['fx_debug_pending'],64*1024))
            assert b'layout=1.03' in pending and b'flags=028b' in pending
            assert b'frame_skip=1' in pending and b'crc_valid=1' in pending
            assert b'[LW3-VKWORK] thread=99 code=4d calls=1' in pending
            assert m.guest_settings == bytes(settings)
            m.guest_settings = None
            m.call('fx_low_window_diagnostics',75)
            pending = bytes(m.vm.mem_read(m.symbols['fx_debug_pending'],64*1024))
            assert b'unavailable status_v100=0 status_v103=0 status_v104=0' in pending
            live_gate = True
        pacing_gate = True
        print('PASS: actual diagnostics gated off in normal launch; Debug reports queue only to RAM and reject unmapped guest; LW3 live setting/Vulkan attribution checked='+str(live_gate), flush=True)
    del m; gc.collect()
    report = dict(passed=True, hardware_tested=False, elf_sha256=hashlib.sha256(data).hexdigest(),
        preflight_cases=preflights, startup_cases=startup, native_floor_checked=True, high_backing_checked=True,
        normal_launch_diagnostic_io_disabled=True,
        lw2_pacing_debug_gate_checked=pacing_gate,
        lw3_live_settings_and_vk_attribution_checked=live_gate,
        limitations='Actual ARM64 ELF under Unicorn; heap, services and SVC behavior are modeled. PES/Switch test still required.')
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__': main()
