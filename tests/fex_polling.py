"""Exercise polling bookkeeping and actual linked yield paths, bound to final ELF."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from unicorn import arm64_const as arm
from fex_resume_gate import function
from fextendo_source_normalization import undo_polling
from fex_yield_burst import Model as YieldModel

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(text, name):
    text = text.replace('NTSTATUS WINAPI '+name+'(', 'static NTSTATUS '+name+'(')
    text = text.replace('NTSTATUS '+name+'( ULONG_PTR', 'static NTSTATUS '+name+'( ULONG_PTR')
    return function(text, name)


class Model(YieldModel):
    def __init__(self, elf):
        super().__init__(elf)
        self.clock_reads = 0
        self.metrics_reads = 0
        self.zero_notes = []

    def hook(self, vm, pc, size, user):
        if pc == self.symbols.get('horizon_interrupt_time'):
            self.clock_reads += 1
        elif pc == self.symbols.get('wine_nx_fex_frame_tick'):
            self.metrics_reads += 1
        elif pc == self.symbols.get('wine_nx_fex_delay_zero_note'):
            self.zero_notes.append((vm.reg_read(arm.UC_ARM64_REG_X0), vm.reg_read(arm.UC_ARM64_REG_X1)))
            self.ret();return
        super().hook(vm, pc, size, user)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args();work=args.work.resolve()
    sync_path=args.source/'dlls/ntdll/unix/sync.c';signal_path=args.source/'dlls/ntdll/unix/signal_arm64.c'
    sync=sync_path.read_text();signal=signal_path.read_text()
    normal_sync, scope=undo_polling(sync, ROOT, 'dlls/ntdll/unix/sync.c')
    baseline=json.loads((ROOT/'local/fex3/cpu-balance-v2/runtime/wine-patches.json').read_text())
    assert hashlib.sha256(normal_sync.encode()).hexdigest()==baseline['native-source']['dlls/ntdll/unix/sync.c']
    normal_signal,_=undo_polling(signal, ROOT, 'dlls/ntdll/unix/signal_arm64.c')
    assert hashlib.sha256(normal_signal.encode()).hexdigest()==baseline['native-source']['dlls/ntdll/unix/signal_arm64.c']
    table=(args.source/'dlls/ntdll/ntsyscalls.h').read_text()
    for id,name in [('0031','NtQueryPerformanceCounter'),('0034','NtDelayExecution')]:
        assert f'SYSCALL_ENTRY( 0x{id}, {name}, 16 )' in table
    headers=['fex_polling_counters.h','fex_yield_burst.h','fex_polling_yield.h']
    code='\n'.join('#include "'+str(ROOT/'src/runtime'/name)+'"' for name in headers)
    code+='\n#define TICKSPERSEC 10000000\n'
    for name in ('NtQueryPerformanceCounter','NtYieldExecution','NtDelayExecution'):
        code+=extract(sync,name)+'\n'
    code+='\n#define __atomic_add_fetch(p,v,o) counted_add(p,v,o)\n'+extract(signal,'wine_nx_do_syscall')+'\n#undef __atomic_add_fetch\n'
    template=(ROOT/'tests/fex_polling.c').read_text().replace('/* PRODUCTION_FUNCTIONS */',code)
    checks=[]
    with tempfile.TemporaryDirectory(prefix='fex-polling-') as tmp:
        p=Path(tmp)/'test.c';exe=Path(tmp)/'test';p.write_text(template)
        # Wine's universal syscall function-pointer cast is intentionally ABI
        # polymorphic. Test it separately on ARM64; retain ASan/other UBSan here.
        subprocess.run(['clang','-std=gnu11','-O1','-g','-pthread','-Wall','-Wextra',
            '-Wno-pointer-bool-conversion','-fsanitize=address,undefined','-fno-sanitize=function',
            '-fno-sanitize-recover=all',str(p),'-o',str(exe)],check=True)
        result=subprocess.run([str(exe)],check=True,text=True,capture_output=True,timeout=60)
        checks.append(result.stdout.strip())
    elf=work/'runtime/reference/pes13-fex.elf';m=Model(elf)
    for _ in range(63):m.mono+=100;m.call('NtDelayExecution')
    assert m.calls==[0]*63 and len(m.zero_notes)==63 and m.clock_reads==126 and not m.metrics_reads
    m.call();assert m.calls[-2:]==[0,50000] and m.notes==[(164,50)]
    m.extra_pause=30000
    for _ in range(64):m.call('NtDelayExecution')
    assert m.zero_notes[-1]==(164,3050) and m.notes[-1]==(164,3050)
    m.yield_cost=20;before=len(m.notes)
    for _ in range(128):m.call('NtDelayExecution')
    assert len(m.notes)==before
    # Relative delay stays outside the zero-delay path and keeps kernel args.
    for timeout in (-1,-10000,-166667):
        m.calls=[];m.call('NtDelayExecution',timeout);assert m.calls==[-timeout*100]
    control=Model(elf);control.vm.mem_write(control.symbols['wine_nx_fex_polling'],struct.pack('<I',0))
    for _ in range(63):control.mono+=100;control.call('NtDelayExecution')
    assert control.calls==[0]*63 and not control.zero_notes and control.metrics_reads==63
    checks.append('Final ARM64: optimized Sleep(0) uses two monotonic reads, emits one delay record, shares the 64-yield policy with direct yield; oversleep/productive yield/relative deadlines and OFF routing preserved.')
    checks.append('Strict inverse/replay restores v3.4 sync.c and signal_arm64.c exactly: APC, nonzero/infinite delay, QPC clock/frequency, service validation and argument dispatch preserved.')
    receipt=json.loads((work/'runtime/runtime-build.json').read_text());assert receipt['polling'] and receipt['native_elf_sha256']==sha(elf)
    patches=json.loads((work/'runtime/wine-patches.json').read_text())
    for name in ('dlls/ntdll/unix/sync.c','dlls/ntdll/unix/signal_arm64.c','wine-nx-probe/source/runtime.c'):
        assert patches['native-source'][name]==sha(args.source/name)
    files=['tests/fex_polling.py','tests/fex_polling.c','tests/fex_yield_burst.py','tests/fex_samecore_binary.py',
           'tests/fex_reservations.py','tests/fextendo_source_normalization.py','tools/fex_polling_patches.py',
           *['src/runtime/'+name for name in headers]]
    result={'passed':True,'hardware_tested':False,'native_elf_sha256':sha(elf),'checks':checks,
            'source_hashes':{name:sha(ROOT/name) for name in files},'scope':scope,
            'cold_control':{'shared_atomic_adds_per_qpc_or_delay':2,'normal_zero_delay_clock_reads':4},
            'candidate':{'shared_atomic_adds_per_registered_qpc_or_delay':0,'normal_zero_delay_clock_reads':2,
                         'retained_counter_bytes':256*64,'counter_slots':256},
            'fps_improvement_measured':False}
    (work/'polling.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
