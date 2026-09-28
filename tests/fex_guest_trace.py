"""Check bounded guest-exception diagnostics in the actual ARM64 FEX DLL.

Does not establish guest exception delivery; the original Switch workload is
still required for that. Native logging is mocked and deliberately clobbers x18.
"""
from pathlib import Path
import argparse
import hashlib
import json
from fex_alloc import Model, PARAM, TEB, reg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    model = Model(args.dll, clobber_host_x18=True)
    model.logs.clear()
    stages = ('smc-lock', 'smc-handled', 'classify', 'native-fault', 'reconstruct',
              'guest-context', 'unlock', 'raise', 'raise-return')
    for index in range(40):
        ticket = model.call('PES13FexBeginGuestFaultTrace', 8+index*4, 0x12345678+index, 0xabcdef00+index)
        assert ticket == (index+1 if index < 12 else 0)
        assert not model.trapped and model.vm.reg_read(reg(18)) == TEB
        if ticket:
            assert f'tid=0x{8+index*4:016x}' in model.logs[-1]
            assert f'address=0x{0xabcdef00+index:016x}' in model.logs[-1]
        count = len(model.logs)
        for stage in stages:
            model.vm.mem_write(PARAM+0x100, stage.encode()+b'\0')
            model.call('PES13FexTraceGuestFault', ticket, PARAM+0x100, 0x400040, 0xc0000005)
            assert not model.trapped and model.vm.reg_read(reg(18)) == TEB
        assert len(model.logs) == count+(len(stages) if ticket else 0)
    assert len(model.logs) == 12*(1+len(stages))
    assert all(len(line) < 208 for line in model.logs)
    assert all(line.startswith('[FEX3-GEX] ticket=') for line in model.logs)
    count = len(model.logs)
    for bad in (0, 13, 0xffffffff):
        model.call('PES13FexTraceGuestFault', bad, PARAM+0x100, 0, 0)
    model.call('PES13FexTraceGuestFault', 1, 0, 0, 0)
    assert len(model.logs) == count
    report = {'passed': True, 'dll_sha256': hashlib.sha256(args.dll.read_bytes()).hexdigest(),
              'checks': ['12 unique tickets then saturated suppression', 'all stage fields fit fixed buffers',
                         'zero/invalid tickets and null stage suppressed', 'native logger cannot corrupt Wine x18'],
              'scope': 'actual ARM64 diagnostic functions with modeled logging; not guest exception delivery'}
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
