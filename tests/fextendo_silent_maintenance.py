"""Compare linked worker placement with the diagnostic baseline."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from fex_worker_cores import Model
from fex_balance_stable import CASE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checks = []
    snapshots = []
    for elf in (args.before, args.elf):
        m = Model(elf)
        memory = [(begin, bytes(m.vm.mem_read(begin, end - begin + 1)))
                  for begin, end, _ in m.vm.mem_regions()]
        state = {key: copy.deepcopy(value) for key, value in vars(m).items()
                 if key not in ('vm', 'symbols')}
        snapshots.append((m, memory, state, m.vm.context_save()))

    def reset(snapshot, grant=15):
        m, memory, state, context = snapshot
        for address, data in memory:
            m.vm.mem_write(address, data)
        m.vm.context_restore(context)
        for key, value in state.items():
            setattr(m, key, copy.deepcopy(value))
        m.grant = grant
        m.q(m.symbols['cached_affinity_mask'], grant)
        return m

    for grant in (1, 3, 7, 15):
        results = []
        for snapshot in snapshots:
            m = reset(snapshot, grant)
            m.startup()
            results.append(copy.deepcopy((m.sets, m.follow)))
        assert results[0] == results[1], grant
    checks.append('Worker startup preserves affinity grants 1/3/7/15')
    workloads = [
        [(11+i, 1 << core, load, 0) for i, (load, core) in enumerate(CASE)],
        [(11, 1, 1000, 1), (22, 2, 400, 0), (33, 2, 300, 0), (44, 4, 100, 0)],
        [(11, 1, 800, 1), (22, 2, 100, 1)],
    ]
    for workers in workloads:
        for error in (0, 0xdead):
            results = []
            for snapshot in snapshots:
                m = reset(snapshot)
                m.set_error = error
                m.balance(workers)
                results.append(copy.deepcopy((m.sets, m.follow, m.masks)))
            assert results[0] == results[1], (workers, error)
    checks.append('Balancer preserves baseline placement/publication including fixed threads and failed syscalls')
    report = {'passed': True, 'hardware_tested': False, 'checks': checks,
              'native_elf_sha256': hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              'before_native_elf_sha256': hashlib.sha256(args.before.read_bytes()).hexdigest()}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
