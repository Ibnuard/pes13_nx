"""Reproduce rejected lazy L1 commit, then exercise the resident native L1.

Runs shipped ARM64 methods with mocked NT allocation failures and host heap.
The failure injection models the device's c0000022, not its underlying cause.
"""
from pathlib import Path
import argparse
import hashlib
import json

from unicorn import UcError, UC_ERR_READ_PROT
from fex_lookup import LookupModel
from fex_memory import COMMIT, DTOR, MIB


class RejectCommit(LookupModel):
    deny_commits = False

    def allocate(self, base_pointer, size_pointer, flags, params=0, count=0):
        if self.deny_commits and flags & COMMIT:
            self.requests.append((self.readq(base_pointer), self.readq(size_pointer), flags))
            return 0xc0000022
        return super().allocate(base_pointer, size_pointer, flags, params, count)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    guest = 0x01219510  # Guest address from the device's FindBlock fault.
    # Fresh Unicorn instances avoid its paired-load retry artefact after a
    # permission fault. Both execute the real FindBlock instruction; the
    # second performs the rejected commit before its first protected read.
    for attempt in range(2):
        old = RejectCommit(args.before)
        old.setup(eager=False)
        old.deny_commits = True
        base = old.readq(old.obj+0x30)
        fault = base + (guest & 0xffff)*16 + 8
        if attempt:
            assert not old.commit(fault, base, base+MIB)
        try:
            old.find(guest)
        except UcError as error:
            assert error.errno == UC_ERR_READ_PROT
        else:
            raise AssertionError('Old lazy L1 read did not fault')
    assert any('status=0x00000000c0000022' in line for line in old.logs)

    model = RejectCommit(args.dll)
    model.poison_native = True
    model.setup(eager=False)
    model.requests.clear()
    model.deny_commits = True
    base = model.readq(model.obj+0x30)
    assert model.native_regions[base] == MIB and not model.tracked and not model.requests
    assert model.find(guest) == 0  # Zeroed miss, even with a dirty host allocation.
    targets = {guest: 0x70001000, 0xfff19510: 0x70002000, 0xffffffff: 0x70003000}
    for address, host in targets.items():
        model.add(address, host)
    clear = model.method('22ClearThreadLocalCaches')
    for _ in range(16):
        for address, host in targets.items():
            assert model.find(address) == host
        model.call(clear, model.obj, 0)
    assert not model.requests and not model.tracked and not model.trapped
    model.call(DTOR, model.obj)
    assert not model.native_regions and base not in model.regions
    report = {
        'passed': True, 'dll_sha256': digest(args.dll), 'before_sha256': digest(args.before),
        'before_commit_status': 'c0000022', 'before_lookup_read_faults': 2,
        'native_lookup_nt_commits': len(model.requests), 'native_lookup_clears': 16,
        'checks': ['Old L1 read faults and remains protected after a rejected commit',
                   'Native L1 clears poisoned allocation and handles the same high-offset lookup',
                   'Lookup collisions and full invalidation/refill work with all NT commits rejected',
                   'Destruction releases the native L1 allocation'],
        'scope': 'Linked ARM64 instructions; NT status injected and host heap modeled; device untested',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
