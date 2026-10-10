"""Create the patch-only immutable repair input before building its NRO.

This dependency ZIP contains runtime allowlist files, never the NRO, game,
registry, settings or saves. Local NRO delivery can remain a copy-ready folder.
Upload to the named dependency release only after validating it; this tool
does not upload, publish or replace the original repair catalog.
"""
import argparse
import json
from pathlib import Path
import re

from pes_patch_identity import profile, validate_catalog
from release_package import sha, encoded, safe_name, write_zip
from runtime_fixer_catalog import allowed


def prepare(runtime, output, tag, header):
    if (not re.fullmatch(r'runtime-patch-[A-Za-z0-9._-]+', tag)
            or not re.fullmatch(r'[A-Za-z0-9._-]+\.zip', output.name)):
        raise ValueError('Expected a patch dependency tag and ZIP asset name')
    if output.exists() or header.exists():
        raise ValueError('Use fresh dependency/header output paths')
    p = profile()
    files, rows = {}, []
    for path in sorted(runtime.rglob('*')):
        if not path.is_file():
            continue
        rel = path.relative_to(runtime).as_posix()
        safe_name(rel)
        if not allowed(rel):
            continue
        if path.is_symlink() or path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError('Unsupported repair input: ' + rel)
        data = path.read_bytes()
        if b'switch/pes13-fex' in data or 'switch/pes13-fex'.encode('utf-16le') in data:
            raise ValueError('Repair input still accesses the original prefix: ' + rel)
        rows.append((rel, len(data), sha(data)))
        files[p['prefix']+rel] = data
    if not any(n == 'drive_c/windows/system32/libwow64fex.dll' for n,_,_ in rows):
        raise ValueError('Missing patch FEX input')
    files['repair-manifest.json'] = encoded({'channel':'patch', 'prefix':p['prefix'],
        'tag':tag, 'files':{n:sha(d) for n,d in files.items()}})
    output.parent.mkdir(parents=True, exist_ok=True)
    write_zip(output, files)
    raw = output.read_bytes()
    identity = sha(json.dumps(rows, separators=(',', ':')).encode())
    lines = ['/* Generated patch-only Runtime Fixer catalog. */',
        '#define FXR_PACKAGE_PREFIX "'+p['prefix']+'"',
        '#define FXR_COUNT '+str(len(rows)), '#define FXR_CATALOG_ID "'+identity+'"',
        '#define FXR_ARCHIVE_SHA "'+sha(raw)+'"', '#define FXR_ARCHIVE_SIZE '+str(len(raw))+'ull',
        '#define FXR_URL "https://github.com/Ibnuard/pes13_nx/releases/download/'+tag+'/'+output.name+'"',
        'static const struct fxr_file fxr_files[FXR_COUNT] = {']
    lines += ['    {'+json.dumps(n)+','+str(size)+'ull,"'+digest+'"},' for n,size,digest in rows]
    text = ('\n'.join(lines+['};',''])).encode()
    validate_catalog(text)
    header.parent.mkdir(parents=True, exist_ok=True)
    header.write_bytes(text)
    return {'channel':'patch', 'files':len(rows), 'sha256':sha(raw), 'catalog_sha256':sha(text)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True, help='Prepared pes13-patch-fex directory')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--header', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.runtime,args.output,args.tag,args.header), indent=2))
