"""Exercise the actual Horizon directory handler against a real filesystem.

Extracts production functions; models only server transport/handles and injects
filesystem/allocation failures. Counts real opendir/readdir/closedir calls.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def function(text, anchor):
    start = text.index(anchor)
    return text[start:text.index('\n}\n', start) + 3]


def generate(path, before):
    text = path.read_text()
    fields = text[text.index('    unsigned int dir_enum_index;'):text.index('    int sock_nonblocking;')]
    prefix = (ROOT/'tests/fextendo_directory_host.c').read_text()
    if 'horizon_directory_meta.c' in text:
        header = (path.parent/'horizon_directory_meta.h').read_text()
        start = header.index('struct horizon_directory_file_entry\n')
        struct = header[start:header.index('\n};',start)+3]
        prefix = prefix.replace('struct horizon_directory_file_entry { unsigned name_len; };', struct + '''
#define METADATA_REPLY 1
/* Native batch decoding is separately tested against the actual helper. */
static void horizon_dir_capture_metadata(DIR *stream,const char *path,const char *name,
                                         struct horizon_directory_file_entry *entry) {
    (void)stream;(void)path;
    unsigned id;
    entry->metadata=0;entry->file_size=0;
    if(sscanf(name,"unnamed_%u.bin",&id)==1){entry->metadata=1;entry->file_size=(uint64_t)id*0x100000001ULL;}
}
''')
    prefix = prefix.replace('/* OBJECT_FIELDS */', fields)
    prefix = prefix.replace('/* PRODUCTION_FUNCTIONS */', '\n'.join([
        function(text, 'static unsigned int horizon_server_utf16_name_len('),
        function(text, 'static void horizon_server_write_utf16_name('),
        function(text, 'static int horizon_server_wildcard_match_tail('),
        function(text, 'static int horizon_server_wildcard_match('),
        function(text, 'static char *horizon_server_dir_mask_from_utf16('),
        ('' if before else function(text, 'static void horizon_server_reset_directory(')),
        function(text, 'static int horizon_server_handle_query_directory_file('),
    ]))
    if not before:
        destructor = function(text, 'static void horizon_server_free_object(')
        assert 'horizon_server_reset_directory( object );' in destructor
    return prefix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('before', 'source', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    results = []
    with tempfile.TemporaryDirectory(prefix='pes13-directory-') as td:
        folder = Path(td)/'files'
        folder.mkdir()
        for i in range(14258):
            (folder/f'unnamed_{i:05d}.bin').touch()
        for old, source in ((True, args.before), (False, args.source)):
            c = Path(td)/('before.c' if old else 'candidate.c')
            c.write_text(generate(source, old))
            exe = c.with_suffix('')
            subprocess.run(['gcc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-pthread',
                            '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                            *(['-DBASELINE'] if old else []), str(c), '-o', str(exe)], check=True)
            result = subprocess.run([str(exe), str(folder)], text=True, capture_output=True)
            print(result.stdout, result.stderr, end='', flush=True)
            result.check_returncode()
            results.append({'baseline': old, **json.loads(result.stdout)})
    assert results[0]['ordered_hash'] == results[1]['ordered_hash']
    assert results[0]['files'] == results[1]['files'] == 14260
    assert results[0]['open_calls'] == 14261
    assert results[0]['read_calls'] > 100_000_000
    assert results[1]['open_calls'] == 1 and results[1]['read_calls'] == 14261
    assert results[1]['trace_calls'] < 65
    report = {'passed': True, 'hardware_tested': False, 'checks': results,
              'sanitizers': ['AddressSanitizer', 'UndefinedBehaviorSanitizer'],
              'horizon_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
              'sources': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
                          ('tests/fextendo_directory_host.py', 'tests/fextendo_directory_host.c',
                           'tools/fextendo_directory_patches.py')}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
