"""Validate cached writable views and compare real old/new ARM64 emission."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from fex_dispatch_cache import Model, CODE


class CountModel(Model):
    def hook(self, vm, pc, size, user):
        if pc == getattr(self, 'alias', None):
            self.alias_calls = getattr(self, 'alias_calls', 0)+1
        super().hook(vm, pc, size, user)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('dll', type=Path)
    ap.add_argument('--before', type=Path, required=True)
    ap.add_argument('--source', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parents[1]
    header = args.source/'CodeEmitter/CodeEmitter/Buffer.h'
    body = header.read_text().replace('#include "horizon_host.h"', '')
    harness = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <vector>
unsigned calls;
uintptr_t rx, rw;
size_t mapped_size;
void *PES13FexWriteAlias(const void *ptr, uint64_t length) {
  ++calls;
  uintptr_t p = reinterpret_cast<uintptr_t>(ptr);
  if (length > UINTPTR_MAX-p) throw std::runtime_error("overflow");
  if (p >= rx && p-rx < mapped_size) {
    if (length > mapped_size-(p-rx)) throw std::runtime_error("boundary");
    return reinterpret_cast<void*>(rw+(p-rx));
  }
  return const_cast<void*>(ptr);
}
void PES13FexFlushCode(const void *, uint64_t) {}
'''+body+r'''
int main() {
  alignas(64) uint8_t execute[65536]{}, write[65536]{};
  rx = reinterpret_cast<uintptr_t>(execute); rw = reinterpret_cast<uintptr_t>(write);
  mapped_size = sizeof(execute);
  ARMEmitter::Buffer b(execute, sizeof(execute));
  assert(calls == 1);
  for (unsigned i=0; i<4096; ++i) b.dc32(0x14000000+i);
  assert(calls == 1 && b.GetCursorOffset() == 16384);
  assert(b.GetBufferBase() == execute && b.GetCursorAddress<uint8_t*>() == execute+16384);
  for (unsigned i=0; i<4096; ++i) {
    uint32_t word; std::memcpy(&word, write+i*4,4); assert(word == 0x14000000+i);
  }
  for (auto byte: execute) assert(byte == 0); // Never write to the RX view.
  b.SetCursorOffset(3); b.Align(16); assert(b.GetCursorOffset()==16 && calls==1);
  for (unsigned i=3; i<16; ++i) assert(write[i]==0);
  b.EmitString("abc"); assert(std::memcmp(write+16,"abc",3)==0 && calls==1);
  b.SetCursorOffset(sizeof(execute)-4); b.dc32(0x12345678);
  assert(calls==1 && b.GetCursorOffset()==sizeof(execute));
  b.SetCursorOffset(sizeof(execute)-2);
  bool rejected=false; try { b.dc32(0); } catch(const std::runtime_error&) { rejected=true; }
  assert(rejected && calls==2); // Crossing the owned range takes checked fallback.
  b.SetBuffer(write, sizeof(write)); assert(calls==3);
  b.dc64(0x1122334455667788ull); assert(calls==3);
  uint64_t word; std::memcpy(&word,write,8); assert(word==0x1122334455667788ull);
  auto outside = b.Writable(execute+7, 4); // Arbitrary backpatch, not its current view.
  assert(outside==write+7 && calls==4);
  b.SetBuffer(nullptr,0); assert(calls==4 && b.GetBufferSize()==0);
  outside=b.Writable(execute+7,4); assert(outside==write+7 && calls==5);
  rejected=false;try { b.Writable(reinterpret_cast<void*>(UINTPTR_MAX-1),4); }
  catch(const std::runtime_error&) { rejected=true; }
  assert(rejected);
  // Shrinking/replacing a buffer cannot retain the previous cached view.
  b.SetBuffer(execute+8,16); auto before=calls;
  assert(b.Writable(execute+24,1)==write+24 && calls==before+1);
  b.dc8(0x55); assert(write[8]==0x55);
}
'''
    with tempfile.TemporaryDirectory(prefix='fex-emit-') as tmp:
        cpp, exe = Path(tmp)/'test.cpp', Path(tmp)/'test'
        cpp.write_text(harness)
        subprocess.run(['clang++','-std=c++20','-O1','-g','-fsanitize=address,undefined',
                        '-fno-sanitize-recover=all',str(cpp),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True,timeout=30)
    outputs = []
    for path in (args.before, args.dll):
        m = CountModel(path)
        m.emit()
        end = m.readq(m.emitter+8)
        code = bytes(m.vm.mem_read(CODE,end-CODE))
        # Only the trailing CTX/Sleep/CompileBlock/CompileSingleStep literal
        # pool contains pointers into these differently linked DLLs.
        outputs.append((code[:-32], getattr(m,'alias_calls',0)))
    assert outputs[0][0] == outputs[1][0], 'Generated instruction/data stream drift'
    assert outputs[0][1] > 1000 and outputs[1][1] < outputs[0][1]//4, outputs
    report = {'passed':True, 'hardware_tested':False,
              'dll_sha256':hashlib.sha256(args.dll.read_bytes()).hexdigest(),
              'before_sha256':hashlib.sha256(args.before.read_bytes()).hexdigest(),
              'buffer_source_sha256':hashlib.sha256(header.read_bytes()).hexdigest(),
              'dispatcher_alias_callbacks_before':outputs[0][1],
              'dispatcher_alias_callbacks_after':outputs[1][1],
              'normalized_emitted_code_sha256':hashlib.sha256(outputs[1][0]).hexdigest(),
              'checks':['4096 writes use one alias resolution; separate RX/RW and identity mappings',
                        'Cursor addresses, alignment, strings, boundary/overflow and replaced views',
                        'Real old/new ARM64 dispatcher constructors generate identical code except relocated pointer pool'],
              'scope':'ASan/UBSan source body and ARM64 binary execution with modeled host memory; no Switch timing claim',
              'test_sources':{n:hashlib.sha256((root/'tests'/n).read_bytes()).hexdigest()
                              for n in ('fex_emit_buffer.py','fex_dispatch_cache.py','fex_alloc.py')}}
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main()
