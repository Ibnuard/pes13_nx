"""Execute shipped ARM64 commits with allocator/kernel failures injected.

The guest mapping tree, backing lifetime, pool recovery and commit transaction
run from the ELF. This models OS calls; it does not reproduce a Switch match.
"""
import argparse, gc, hashlib, json, struct
from pathlib import Path
from fextendo_page_store_binary import Model as Base, reg

MIB = 1024 * 1024
BASE, SIZE, OFFSET, COMMIT = 0x60000000, 6*MIB, MIB, 0x390000


class Model(Base):
    def __init__(self, path):
        super().__init__(path, limit=16*MIB)
        self.serial = 0
        self.reserve_calls = 0
        self.reserve_fail = 0
        self.deny_pages = False
        self.budget = 1 << 40
        self.guard_watch = False
        self.guard_gaps = 0

    def alloc(self, n, aligned=False):
        if (aligned and self.deny_pages) or sum(self.allocations.values()) + n > self.budget:
            self.vm.mem_write(self.data+0x100, struct.pack('<I', 12))
            return 0
        return super().alloc(n, aligned)

    def hook(self, vm, pc, size, user):
        n = self.names.get(pc, '')
        x = lambda i: vm.reg_read(reg(i))
        if n == 'virtmemAddReservation':
            self.reserve_calls += 1
            if self.reserve_calls == self.reserve_fail:
                self.ret(0)
            else:
                self.serial += 1
                token = self.data+0x6000+self.serial*32
                assert token < self.data+0xf000
                self.reservations[token] = (x(0), x(1))
                self.ret(token)
        elif n == 'virtmemRemoveReservation':
            assert x(0) in self.reservations
            self.reservations.pop(x(0))
            if self.guard_watch:
                ranges = list(self.reservations.values()) + [(a, v[1]) for a, v in self.maps.items()]
                at = BASE
                for a, length in sorted(ranges):
                    if a <= at: at = max(at, a+length)
                if at < BASE+SIZE: self.guard_gaps += 1
            self.ret()
        elif n == 'svcQueryMemory':
            vm.mem_write(x(0), struct.pack('<QQ6I', x(2) & -4096, 16*MIB, 0, 0, 0, 0, 0, 0))
            vm.mem_write(x(1), bytes(4))
            self.ret()
        elif n == 'svcGetInfo':
            self.q(x(0), 0)
            self.ret()
        elif n == 'wine_nx_launch_debug_active': self.ret(0)
        else: super().hook(vm, pc, size, user)

    def prepare(self):
        assert self.call('add_reservation_mapping_locked', BASE, SIZE) == 0
        assert len(self.reservations) == 1 and not self.maps
        self.original = dict(self.reservations)
        self.guard_watch = True

    def commit(self):
        return self.call('horizon_mprotect', BASE+OFFSET, COMMIT, 3)

    def clear(self):
        self.guard_watch = False
        assert self.call('unmap_range_locked', BASE, SIZE) == 0
        assert not self.maps and not self.reservations
        # Recover idle arenas via the actual backing-pool callback.
        # The test below handles the callback's external trylock.


def transactions(path, baseline):
    results = []
    for fail in ('pages', 'kernel', 'reservation-left', 'reservation-right', 'reservation-middle'):
        m = Model(path); m.prepare()
        if fail == 'pages': m.deny_pages = True
        elif fail == 'kernel': m.fail_map = 1
        else:
            position = {'reservation-left': 1, 'reservation-right': 2, 'reservation-middle': 3}[fail]
            m.reserve_fail = m.reserve_calls + position
        assert m.commit() & 0xffffffff == 0xffffffff, fail
        preserved = m.reservations == m.original and not m.maps
        m.deny_pages = False; m.fail_map = m.reserve_fail = 0
        retried = m.commit() == 0
        if not baseline:
            assert preserved and retried and not m.guard_gaps, (fail, preserved, retried, m.guard_gaps)
            m.clear()
        results.append(dict(failure=fail, preserved=preserved, retry_ok=retried, guard_gaps=m.guard_gaps))
        del m; gc.collect()
    if baseline:
        assert any(not r['preserved'] and not r['retry_ok'] for r in results)
    return results


def pressure(path, baseline):
    m = Model(path)
    assert m.call('map_backing_at_locked', BASE, 2*MIB, 3, -1, 0, 0, 12) == 0
    assert m.call('map_backing_at_locked', BASE+16*MIB, 4096, 3, -1, 0, 0, 12) == 0
    first, live = m.maps[BASE][0], m.maps[BASE+16*MIB][0]
    m.vm.mem_write(live, b'LIVE')
    assert m.call('unmap_range_locked', BASE, 2*MIB) == 0
    # 2 MiB of occupied arena plus the 3.5625 MiB request fit, but retaining
    # an additional wholly idle 2 MiB arena makes the direct request fail.
    m.budget = 6*MIB
    recovered = m.call('horizon_backing_pages_alloc', COMMIT)
    assert bool(recovered) != baseline
    assert bytes(m.vm.mem_read(live, 4)) == b'LIVE'
    if recovered: m.call('free', recovered)
    assert m.call('unmap_range_locked', BASE+16*MIB, 4096) == 0
    result = dict(recovered=bool(recovered), live_bytes_preserved=True)
    del m; gc.collect()
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf', type=Path); p.add_argument('--before', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); a = p.parse_args()
    checks = []
    for path, baseline in ((a.before, True), (a.elf, False)):
        checks.append(dict(baseline=baseline, passed=True,
            transactions=transactions(path, baseline), pressure=pressure(path, baseline)))
    files = ('tests/fextendo_commit_binary.py', 'tests/fextendo_page_store_binary.py', 'tests/fex_reservations.py')
    report = dict(passed=True, hardware_tested=False, checks=checks,
        native_elf_sha256=hashlib.sha256(a.elf.read_bytes()).hexdigest(),
        baseline_elf_sha256=hashlib.sha256(a.before.read_bytes()).hexdigest(),
        sources={n:hashlib.sha256(Path(n).read_bytes()).hexdigest() for n in files})
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__': main()
