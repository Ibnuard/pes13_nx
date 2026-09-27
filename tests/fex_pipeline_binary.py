"""Check that the linked ARM64 runtime calls every applicable stage observer."""
from pathlib import Path
from elftools.elf.elffile import ELFFile
import argparse
import capstone
import hashlib
import json


def main():
    if not __debug__:
        raise RuntimeError('Pipeline validation requires Python assertions; disable -O/-OO and PYTHONOPTIMIZE')
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('elf', type=Path)
    ap.add_argument('--output', required=True, type=Path)
    args = ap.parse_args()
    checks = []
    with args.elf.open('rb') as f:
        elf = ELFFile(f)
        symbols = {s.name: s for s in elf.get_section_by_name('.symtab').iter_symbols()}
        dis = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        def calls(name, target):
            s = symbols[name]
            section = elf.get_section(s['st_shndx'])
            start = s['st_value'] - section['sh_addr']
            body = section.data()[start:start+s['st_size']]
            ins = list(dis.disasm(body, s['st_value']))
            hits = [i for i in ins if i.mnemonic in ('bl', 'b') and
                    i.op_str == f'#{hex(symbols[target]["st_value"])}']
            assert len(hits) == 1, (name, target, hits)
            checks.append({'function': name, 'observer': target, 'call': hex(hits[0].address)})
        names = ['win32u_vkAcquireNextImageKHR', 'win32u_vkAcquireNextImage2KHR',
                 'win32u_vkQueueSubmit', 'queue_submit']
        for bits in (32, 64):
            for api in ('vkWaitForFences', 'vkWaitSemaphores', 'vkWaitSemaphoresKHR'):
                name = f'thunk{bits}_{api}'
                if bits == 32 or name in symbols:
                    names.append(name)
        for name in names:
            calls(name, 'wine_nx_fex_pipeline_note')
            calls(name, 'wine_nx_fex_frame_tick')
        if 'usd_update_time' in symbols:
            calls('usd_update_time', 'wine_nx_fex_shared_clock_note')
        else:  # Release builds inline this helper into its two real callers.
            calls('usd_clock_thread', 'wine_nx_fex_shared_clock_note')
            calls('wine_nx_start_user_shared_data_clock', 'wine_nx_fex_shared_clock_note')
    report = {'passed': True, 'hardware_tested': False, 'scope': __doc__,
              'native_elf_sha256': hashlib.sha256(args.elf.read_bytes()).hexdigest(),
              'source_sha256': {'tests/fex_pipeline_binary.py': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
              'checks': checks}
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'PASS: {len(checks)} observer/counter bindings in the linked ARM64 runtime')


if __name__ == '__main__':
    main()
