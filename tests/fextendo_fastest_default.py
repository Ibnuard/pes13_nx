"""Execute the generated runtime's INI reader and FEX profile selection on host.

Checks clean installs, absent config and explicit opt-out using the actual
generated launch expression. Does not measure Switch FPS or game speed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def section(text, start, end):
    return text[text.index(start):text.index(end, text.index(start))]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    build = json.loads((a.build/'build.json').read_text())
    runtime = a.build/'native-source/wine-nx-probe/source/runtime.c'
    profile = a.build/'feature/src/fex/horizon_jit.c'
    assert sha(runtime) == build['source_changes']['wine-nx-probe/source/runtime.c']
    assert sha(a.build/build['nro_filename']) == build['nro_sha256']
    prepared = json.loads((a.build/'prepared.json').read_text())
    assert sha(profile) == prepared['feature_after']['src/fex/horizon_jit.c']
    source = runtime.read_text()
    selection = re.search(r'const unsigned fex_profile = (pes13_fex_select_performance_profile\(guest_tests,.*?);', source, re.S)
    assert selection
    expression = selection[1]
    assert 'wine_nx_config_file_bool(RUNTIME_DIR "/fex-fastest.txt", 1)' in expression
    code = section(source, 'static void trim_line( char *line )', '\n/* The program\'s standard')
    code += section(source, 'static int read_first_line(', '\n#include "')
    code += section(source, 'struct wine_nx_config_entry', '\n/* switch/wine/keys.txt:')
    code += section(profile.read_text(), 'unsigned pes13_fex_select_performance_profile(',
                    '\nvoid pes13_fex_set_performance_profile(')
    prefix = '''#include <stdio.h>
#include <string.h>
#include <strings.h>
#define RUNTIME_DIR "."
#define log_line(...) ((void)0)
enum {PES13_FEX_CONTROL=0,PES13_FEX_FAST=1,PES13_FEX_FASTEST=2,PES13_FEX_FAST_VECTOR=3};
'''
    code = prefix + code + '\nint main(int argc,char **argv) { int guest_tests=argc>1; printf("%u\\n",'+expression+'); return 0; }\n'
    ini_path = ROOT/'release/skeleton/switch/pes13-fex/configuration.ini'
    default = ini_path.read_text()
    cases = [
        ('missing-ini', None, {}, False, 2),
        ('missing-key', 'fex_fast=1\n', {}, False, 2),
        ('release-ini', default, {}, False, 2),
        ('stale-fastest-marker', default, {'fex-fastest.txt':'0\n'}, False, 2),
        ('explicit-fast-opt-out', 'fex_fast=1\nfex_fastest=0\n', {'fex-fastest.txt':'1\n'}, False, 1),
        ('explicit-control', 'fex_fast=0\nfex_fastest=0\n', {}, False, 0),
        ('guest-tests-control', default, {}, True, 0),
    ]
    results = []
    with tempfile.TemporaryDirectory(prefix='fextendo-fastest-') as temp:
        root = Path(temp)
        c, exe = root/'test.c', root/'test'
        c.write_text(code)
        subprocess.run(['cc','-std=c11','-O1','-fsanitize=undefined','-fno-sanitize-recover=all',str(c),'-o',str(exe)],check=True)
        for name, ini, markers, guest, expected in cases:
            run = root/name
            run.mkdir()
            if ini is not None:
                (run/'configuration.ini').write_text(ini)
            for n, value in markers.items():
                (run/n).write_text(value)
            actual = int(subprocess.check_output([str(exe)]+(['guest'] if guest else []),cwd=run,text=True))
            assert actual == expected, (name, actual, expected)
            results.append({'case':name,'profile':actual})
    result = {'passed':True,'hardware_tested':False,'nro_sha256':build['nro_sha256'],
        'elf_sha256':build['elf_sha256'],'generated_runtime_sha256':sha(runtime),
        'selection_expression':expression,'cases':results,
        'sources':{str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in (Path(__file__).resolve(),ini_path)},
        'limits':'Generated C reader and launch expression under UBSan. Does not measure hardware FPS or simulation speed.'}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: Fastest default, INI/marker precedence, explicit Fast/control opt-out, guest test control')


if __name__ == '__main__':
    main()
