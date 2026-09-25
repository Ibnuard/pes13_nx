"""Exercise the linked FEX DLL's CodeMemory alias cache through its host ABI."""
from pathlib import Path
import argparse
import hashlib
import json

from unicorn import arm64_const as arm

from fex_abi import AbiModel
from fex_alloc import PARAM, reg


RX = PARAM + 0x6000
RW = PARAM + 0x16000
SIZE = 0x8000


class AliasModel(AbiModel):
    def __init__(self, dll):
        self.alias_calls = []
        super().__init__(dll)

    def hook(self, vm, pc, size, user):
        if pc == self.alias:
            address, length = (vm.reg_read(reg(i)) for i in range(2))
            self.alias_calls.append((address, length))
            if RX <= address < RX + SIZE and length <= RX + SIZE - address:
                result = RW + address - RX
            else:
                result = address
            vm.reg_write(reg(0), result)
            self.host_return()
            return
        super().hook(vm, pc, size, user)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dll', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    model = AliasModel(args.dll)
    assert model.call('PES13FexAllocateCode', SIZE) == RX and not model.trapped
    assert model.alias_calls == [(RX, 1)], model.alias_calls
    for offset in range(0, 0x400, 8):
        assert model.call('PES13FexWriteAlias', RX + offset, 4) == RW + offset
        assert not model.trapped
    assert len(model.alias_calls) == 1, model.alias_calls
    assert model.call('PES13FexWriteAlias', RW + 16, 4) == RW + 16
    assert len(model.alias_calls) == 1
    ordinary = PARAM + 0x200
    assert model.call('PES13FexWriteAlias', ordinary, 4) == ordinary
    assert len(model.alias_calls) == 2
    assert model.call('PES13FexReleaseCode', RX) == 1 and not model.trapped
    assert model.call('PES13FexWriteAlias', RX + 8, 4) == RW + 8
    assert len(model.alias_calls) == 3, 'release must invalidate the PE cache'
    assert model.call('PES13FexAllocateCode', SIZE) == RX and not model.trapped
    assert len(model.alias_calls) == 4, 'reuse must republish the alias'
    assert model.call('PES13FexWriteAlias', RX + 12, 4) == RW + 12
    assert len(model.alias_calls) == 4
    model.call('PES13FexWriteAlias', RX + SIZE - 2, 4)
    assert model.trapped and 'crossed allocation boundary' in model.logs[-1]
    report = {
        'passed': True,
        'dll_sha256': hashlib.sha256(args.dll.read_bytes()).hexdigest(),
        'cache_writes_without_native_lookup': 129,
        'native_alias_callbacks': len(model.alias_calls),
        'checks': ['RX and RW mapping', 'ordinary fallback', 'release invalidation',
                   'same-address reuse', 'cross-boundary rejection'],
        'scope': 'linked ARM64 PE instructions under Unicorn; on-device speed unverified',
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
