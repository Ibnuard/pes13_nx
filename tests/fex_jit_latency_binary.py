"""Execute shipped ARM64 JIT metrics and check their real compilation callers."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import capstone
import pefile
from unicorn import arm64_const as arm
from fex_alloc import Model as BaseModel, TEB, coff_symbols, reg


class Model(BaseModel):
    tick = 19200000

    def hook(self, vm, pc, size, user):
        # Model only the physical clock register. Metric arithmetic, atomics,
        # rate gate, formatting and the x18-safe PE/native callback all execute.
        if self.base <= pc < self.base + 0x400000:
            word = int.from_bytes(vm.mem_read(pc,4),'little')
            if word & ~31 in (0xd53be000, 0xd53be020):
                vm.reg_write(reg(word & 31), 19200000 if word & ~31 == 0xd53be000 else self.tick)
                vm.reg_write(arm.UC_ARM64_REG_PC, pc+4)
                return
        super().hook(vm,pc,size,user)


def main():
    if not __debug__: raise RuntimeError('Assertions required')
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('dll',type=Path);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    data=args.dll.read_bytes();pe=pefile.PE(data=data)
    symbols=coff_symbols(data,pe)
    addresses=sorted(set(symbols.values()))
    dis=capstone.Cs(capstone.CS_ARCH_ARM64,capstone.CS_MODE_ARM)

    def calls(name):
        start=symbols[name]; end=next(a for a in addresses if a>start)
        ins=list(dis.disasm(pe.get_data(start-pe.OPTIONAL_HEADER.ImageBase,end-start),start))
        return {int(i.op_str[1:],16) for i in ins if i.mnemonic in ('bl','b') and i.op_str.startswith('#')}

    bindings=[]
    scope_end=symbols['_ZN16PES13FexJitScopeD2Ev']
    assert symbols['PES13FexJitEnd'] in calls('_ZN16PES13FexJitScopeD2Ev')
    for fragment in ('ContextImpl11CompileCode','ContextImpl12CompileBlock','InvalidationTracker32InvalidateIntervalInternalLocked'):
        name=next(n for n in symbols if fragment in n)
        refs=calls(name)
        assert symbols['PES13FexJitBegin'] in refs,(name,'begin',refs)
        assert symbols['PES13FexJitEnd'] in refs or scope_end in refs,(name,'end')
        if 'CompileBlock' in name: assert symbols['PES13FexJitReport'] in refs
        bindings.append(name)
    assert symbols['PES13FexJitTimingInit'] in calls('BTCpuProcessInit')
    m=Model(args.dll,clobber_host_x18=True)
    m.call('PES13FexJitTimingInit'); assert not m.trapped
    start=m.call('PES13FexJitBegin'); assert start==19200000
    m.tick=start+960001
    for stage in range(3):
        m.call('PES13FexJitEnd',stage,start);assert not m.trapped
    stats=m.symbols['_ZN12_GLOBAL__N_15StatsE']
    for stage in range(3):
        assert struct.unpack('<5Q',m.vm.mem_read(stats+stage*40,40))==(1,960001,960001,1,1)
    before=len(m.logs)
    m.call('PES13FexJitReport');assert len(m.logs)==before
    m.tick=start+19200000*5
    m.call('PES13FexJitReport');assert not m.trapped
    assert len(m.logs)==before+3
    for line in m.logs[-3:]:
        assert 'uptime_ms=5000 calls=1 total_us=50000 peak_us=50000 over20ms=1 over50ms=1' in line
    m.call('PES13FexJitReport');assert len(m.logs)==before+3
    assert m.vm.reg_read(reg(18))==TEB
    report={'passed':True,'hardware_tested':False,'dll_sha256':hashlib.sha256(data).hexdigest(),
            'bindings':bindings,'counter_threshold_report_gate_x18':True,
            'scope':'Actual ARM64 instructions with modeled physical clock and native logging'}
    args.output.write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report,indent=2))


if __name__=='__main__':main()
