"""Validate real metadata/observer C with platform-only boundary substitutions."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    names = ('horizon_directory_meta.h', 'horizon_directory_meta.c')
    for n in names:
        assert sha(a.source/n) == sha(ROOT/'src/runtime'/n)
    code = (a.source/'horizon_directory_meta.c').read_text().replace('#include <sys/iosupport.h>', '')
    code = code.replace('#include "horizon_directory_meta.h"', (a.source/'horizon_directory_meta.h').read_text())
    fixture = (ROOT/'tests/fextendo_directory_meta_host.c').read_text().replace('/* PRODUCTION_IMPLEMENTATION */', code)
    with tempfile.TemporaryDirectory(prefix='pes13-directory-meta-') as td:
        c = Path(td)/'meta.c';c.write_text(fixture)
        exe = c.with_suffix('')
        subprocess.run(['gcc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-pthread',
                        '-fsanitize=address,undefined','-fno-sanitize-recover=all',str(c),'-o',str(exe)],check=True)
        r = subprocess.run([str(exe)],text=True,capture_output=True)
        print(r.stdout,r.stderr,end='',flush=True);r.check_returncode()
        result = json.loads(r.stdout)
    file = (a.source/'file.c').read_text()
    # Keep all existing Wine attribute and output-layout logic; both legacy
    # wrappers still delegate with no hint. The new client explicitly opts in.
    assert 'return get_file_info_with_stat(path, st, attr, reparse_tag, NULL);' in file
    assert 'return get_dir_data_entry_with_stat(dir_data, info_ptr, io, max_length, class, last_info, NULL);' in file
    assert 'hint ? &known : NULL' in file
    assert 'if (hint == 2 && last_info && info_class != FileNamesInformation)' in file
    for member in ('CreationTime', 'LastAccessTime', 'LastWriteTime', 'ChangeTime'):
        assert 'last_info->dir.'+member+'.QuadPart = 0;' in file
    assert 'horizon_dir_capture_metadata(object->dir_stream' in (a.source/'horizon.c').read_text()
    report = {**result,'hardware_tested':False,'sanitizers':['AddressSanitizer','UndefinedBehaviorSanitizer'],
              'generated':{n:sha(a.source/n) for n in (*names,'file.c','horizon.c')},
              'sources':{n:sha(ROOT/n) for n in ('src/runtime/horizon_directory_meta.h',
                  'src/runtime/horizon_directory_meta.c','tools/fextendo_directory_meta_patches.py',
                  'tests/fextendo_directory_meta_host.py','tests/fextendo_directory_meta_host.c')}}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
