"""Execute the delivered scratch callbacks, modeling libc and Horizon mutexes.

The contiguous arena itself, host ABI table, bounds checks and telemetry run
as ARM64 instructions. This is not a console allocation or performance test.
"""
import argparse, hashlib, json, struct
from pathlib import Path
from fextendo_silent import Model as Base, arm, reg

BLOCK = 8 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[1]

class Model(Base):
    def __init__(self, path, budget):
        super().__init__(path)
        self.budget = budget
        self.bootstrap = True
        self.deny = False
        self.calls = []
        self.frees = []
        self.locks = []
        self.next = 0x60000000

    def hook(self, vm, pc, size, user):
        # Isolate reserve/ordinary-heap semantics. The separate scratch-pages
        # binary suite executes the real emergency mapping path and failures.
        if pc == self.symbols.get('fx_scratch_pages_take'):
            self.ret(0)
        elif pc == self.symbols.get('fx_scratch_pages_release'):
            self.ret(0)
        elif pc == self.symbols.get('mutexLock'):
            lock = vm.reg_read(reg(0))
            assert lock not in self.locks, 'recursive pool lock'
            self.locks.append(lock)
            self.ret()
        elif pc == self.symbols.get('mutexUnlock'):
            assert self.locks.pop() == vm.reg_read(reg(0))
            self.ret()
        elif pc == self.symbols.get('aligned_alloc'):
            assert not self.locks, 'libc allocation under pool lock'
            alignment, length = [vm.reg_read(reg(i)) for i in range(2)]
            assert alignment == 4096 and length % 4096 == 0
            self.calls.append((alignment, length))
            fail = (self.deny and length >= BLOCK) or (self.bootstrap and length > self.budget * BLOCK)
            if fail:
                vm.mem_write(self.data+0x1000, struct.pack('<I', 12))
                self.ret(0)
            else:
                address = self.next
                self.next += length
                vm.mem_map(address, length)
                self.ret(address)
        elif pc == self.symbols.get('free'):
            assert not self.locks, 'libc free under pool lock'
            self.frees.append(vm.reg_read(reg(0)))
            self.ret()
        else:
            super().hook(vm, pc, size, user)

    def stats(self):
        self.call('pes13_fex_scratch_snapshot', self.data)
        return struct.unpack('<16Q', self.vm.mem_read(self.data, 128))

    def host(self):
        table = self.call('pes13_fex_native_host')
        assert struct.unpack('<4I', self.vm.mem_read(table, 16)) == (0x46455848, 3, 96, 0)
        self.symbols['scratch_allocate'] = self.uq(table+56)
        self.symbols['scratch_release'] = self.uq(table+64)
        return table

    def allocate(self, length):
        return self.call('scratch_allocate', length)

    def release(self, address):
        self.call('scratch_release', address)

    def empty(self):
        stats = self.stats()
        assert stats[0] == stats[9] == self.budget * BLOCK and stats[1:3] == (0, 0), stats


def replay_growth(path):
    """Same workload/pressure on old and new linked ARM64 implementations."""
    m = Model(path, 4)
    m.host()
    m.bootstrap = False
    m.deny = True
    pointers = [m.allocate(BLOCK) for _ in range(4)]
    assert all(pointers) and len(set(pointers)) == 4
    for pointer in pointers:
        m.release(pointer)
    large = m.allocate(2*BLOCK)
    if large:
        m.vm.mem_write(large, b'head')
        m.vm.mem_write(large+2*BLOCK-4, b'tail')
        assert bytes(m.vm.mem_read(large, 4)) == b'head'
        assert bytes(m.vm.mem_read(large+2*BLOCK-4, 4)) == b'tail'
        m.release(large)
    return bool(large)

def run(path, budget, max_units=4):
    m = Model(path, budget)
    table = m.host()
    attempts=[];units=max_units
    while units>budget:attempts.append(units);units//=2
    assert m.stats()[8] == len(attempts)
    m.empty()
    count = len(m.calls)
    assert m.call('pes13_fex_native_host') == table
    assert len(m.calls) == count, 'prewarm ran twice'
    m.bootstrap = False
    m.deny = True
    assert m.allocate(0) == 0
    assert m.allocate(0xffffffffffffffff) == 0
    small = m.allocate(17)
    assert small and m.calls[-1] == (4096, 4096)
    m.release(small)
    m.release(0)
    assert m.frees == [small]
    before = len(m.calls)
    addresses = [m.allocate(BLOCK) for _ in range(budget)]
    assert len(set(addresses)) == budget and all(addresses)
    assert len(m.calls) == before, 'reserved allocation touched libc'
    for i, address in enumerate(addresses):
        m.vm.mem_write(address, bytes([i+1]))
        m.vm.mem_write(address+BLOCK-1, bytes([i+1]))
    assert not m.allocate(BLOCK), 'busy allocation was stolen'
    for i, address in enumerate(addresses):
        assert bytes(m.vm.mem_read(address, 1)) == bytes([i+1])
        assert bytes(m.vm.mem_read(address+BLOCK-1, 1)) == bytes([i+1])
    for address in addresses:
        m.release(address)
    m.empty()
    before = len(m.calls)
    for units in range(1, budget+1):
        address = m.allocate(units*BLOCK)
        assert address
        m.vm.mem_write(address+units*BLOCK-1, b'Z')
        assert m.stats()[1:3] == (units*BLOCK, 1)
        m.release(address)
        m.empty()
    assert len(m.calls) == before and m.frees == [small]
    if budget >= 4:
        addresses = [m.allocate(BLOCK) for _ in range(budget)]
        m.release(addresses[0]); m.release(addresses[2])
        assert m.stats()[9] == BLOCK
        assert not m.allocate(2*BLOCK), 'merged nonadjacent free ranges'
        m.release(addresses[1])
        assert m.stats()[9] == 3*BLOCK
        large = m.allocate(3*BLOCK)
        assert large == addresses[0]
        m.release(large+BLOCK); m.release(large+4096)
        assert m.stats()[15] == 2 and m.stats()[1:3] == (budget*BLOCK, budget-2)
        assert not m.allocate(BLOCK), 'interior free damaged live ownership'
        m.release(large)
        for address in addresses[3:]:m.release(address)
        m.empty()
        first = m.allocate(2*BLOCK); second = m.allocate(2*BLOCK)
        assert second == first+2*BLOCK
        m.vm.mem_write(first+2*BLOCK-1, b'A'); m.vm.mem_write(second, b'B')
        assert bytes(m.vm.mem_read(first+2*BLOCK-1, 2)) == b'AB'
        m.release(first); m.release(second); m.empty()
        odd = m.allocate(BLOCK+4096)
        assert odd and m.stats()[1] == 2*BLOCK
        m.vm.mem_write(odd+BLOCK+4095, b'X')
        m.release(odd); m.empty()
    beyond=(max_units+1)*BLOCK
    assert not m.allocate(beyond)
    assert m.stats()[10:12] == (beyond, beyond)
    m.deny = False
    addresses = [m.allocate(BLOCK) for _ in range(budget)]
    overflow = m.allocate(2*BLOCK)
    assert overflow and overflow not in addresses
    m.release(overflow)
    for address in reversed(addresses):
        m.release(address)
    assert m.frees == [small, overflow]
    m.empty()
    stats = m.stats()
    assert stats[6] == budget*BLOCK and stats[3] == stats[7]
    assert stats[3] == sum(stats[12:15])
    assert not m.locks
    return {'arena_bytes': budget*BLOCK, 'passed': True, 'counters': stats}

def compiler_overlap(path):
    """Replay the failing simultaneous live sizes, not just an empty arena."""
    m=Model(path,8);m.host();m.bootstrap=False;m.deny=True
    sizes=[2*BLOCK,BLOCK,BLOCK];pointers=[m.allocate(n) for n in sizes]
    assert all(pointers)
    for i,(address,n) in enumerate(zip(pointers,sizes)):
        m.vm.mem_write(address,bytes([i+1]));m.vm.mem_write(address+n-1,bytes([i+11]))
    capacity=m.stats()[0];assert m.stats()[1:3]==(4*BLOCK,3)
    extra=m.allocate(BLOCK)
    if extra:
        assert all(extra+BLOCK<=p or extra>=p+n for p,n in zip(pointers,sizes))
        m.vm.mem_write(extra,b'pass');m.vm.mem_write(extra+BLOCK-4,b'tail')
        assert m.stats()[1:3]==(5*BLOCK,4)
        m.release(extra)
    for i,(address,n) in enumerate(zip(pointers,sizes)):
        assert bytes(m.vm.mem_read(address,1))==bytes([i+1])
        assert bytes(m.vm.mem_read(address+n-1,1))==bytes([i+11])
        m.release(address)
    stats=m.stats();assert stats[0]==stats[9]==capacity and stats[1:3]==(0,0)
    return bool(extra)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('elf', type=Path)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--before', type=Path, required=True, help='Previous four-slot reserve ELF')
    p.add_argument('--overlap-before',type=Path,help='Previous 32-MiB live-freeze ELF for the observed 16+8+8+8 overlap')
    p.add_argument('--capacity-mib',type=int,choices=(32,64),default=32)
    a = p.parse_args()
    before = replay_growth(a.before); after = replay_growth(a.elf)
    assert not before and after, 'Expected failure before and successful 16-MiB allocation after'
    result = {'passed': True, 'hardware_tested': False,
              'native_elf_sha256': hashlib.sha256(a.elf.read_bytes()).hexdigest(),
              'before_elf_sha256': hashlib.sha256(a.before.read_bytes()).hexdigest(),
              'replay_growth': {'before_succeeded':before, 'after_succeeded':after},
              'cases': [run(a.elf, count,a.capacity_mib//8) for count in (0, 1, 2, 4,8) if count<=a.capacity_mib//8],
              'checks': ['ABI v3 and actual function pointers', 'One-time bootstrap with full/partial/empty reserve',
                         'Owned buffers are distinct and retain content under pressure',
                         'Released adjacent regions serve 16/24/32 MiB without allocation or I/O',
                         'Nonadjacent holes cannot satisfy contiguous requests; interior frees preserve ownership',
                         'Two simultaneous 16-MiB buffers do not overlap; odd sizes receive sufficient capacity',
                         'Exhaustion fails honestly, normal fallback remains valid',
                         'Normal allocation/free stays outside the reserve lock',
                         'Zero/overflow handling and telemetry match actual ownership'],
              'sources': {'tests/fextendo_scratch_binary.py': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    if a.overlap_before:
        before=compiler_overlap(a.overlap_before);after=compiler_overlap(a.elf)
        assert not before and after
        result['compiler_overlap']={'live_sizes_mib':[16,8,8],'new_request_mib':8,
            'before_succeeded':before,'after_succeeded':after,
            'before_elf_sha256':hashlib.sha256(a.overlap_before.read_bytes()).hexdigest()}
        result['checks'].append('Real failing 16+8+8 live buffers plus new 8 MiB: previous NRO fails, new NRO succeeds without modifying live data')
    a.output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
