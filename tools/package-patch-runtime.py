"""Stage and seal an isolated patch runtime from hash-verified build inputs.

stage prepares the runtime-only repair input before compiling the NRO. seal
adds the actual new NRO/forwarder, source receipts and host checks. Neither
command uploads files, copies a user's game/prefix, or marks hardware tested.
"""
import argparse
import binascii
import json
from pathlib import Path
import struct

from pes_patch_identity import ROOT, profile, validate_catalog
from release_package import SETTINGS, encoded, fingerprints, safe_name, sha, verify_payload, write_zip
from patch_release import verify_isolation

OLD = 'switch/pes13-fex/'


def checked(root, name, digest):
    safe_name(name)
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Input escapes its source tree: ' + name)
    data = path.read_bytes()
    if sha(data) != digest:
        raise ValueError('Changed input: ' + str(path))
    return data


def put(root, name, data):
    safe_name(name)
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def preset(data):
    if len(data) != 852 or struct.unpack_from('<III', data) != (0x46434557, 2, 852):
        raise ValueError('Unexpected PES preset')
    result = bytearray(data)
    struct.pack_into('<H', result, 14, (struct.unpack_from('<H', result, 14)[0] & ~2) | 0x0209)
    struct.pack_into('<H', result, 12, 0)
    struct.pack_into('<H', result, 12, ~binascii.crc_hqx(result, 0) & 0xffff)
    return bytes(result)


def stage(base, kit, work):
    if work.exists():
        raise ValueError('Use a fresh staging directory')
    base_manifest = json.loads((base/'runtime-manifest.json').read_text())
    kit_manifest = json.loads((kit/'manifest.json').read_text())
    if not kit_manifest['passed'] or kit_manifest['kind'] != 'kit17-dxvk-memory':
        raise ValueError('Expected the validated Kit17 runtime overlay')
    work.mkdir(parents=True)
    dest = work/'runtime'
    prefix = profile()['prefix']
    for name, digest in base_manifest['files'].items():
        if name.startswith(OLD) and not name.endswith('.nro'):
            target = prefix + name[len(OLD):]
        elif name.startswith(('source/', 'licenses/')):
            target = name
        else:
            continue
        put(dest, target, checked(base, name, digest))
    for name, digest in kit_manifest['files'].items():
        if name.startswith(OLD) and name.endswith('.dll'):
            target = prefix + name[len(OLD):]
        elif name.startswith(('source/', 'licenses/')):
            first, rest = name.split('/', 1)
            target = first + '/kitserver/' + rest
        else:
            continue
        put(dest, target, checked(kit, name, digest))
    put(dest, 'evidence/original-runtime-manifest.json', (base/'runtime-manifest.json').read_bytes())
    put(dest, 'evidence/kit17-manifest.json', (kit/'manifest.json').read_bytes())
    for name in ('configuration.ini',):
        put(dest, prefix+name, (ROOT/'release/skeleton'/OLD/name).read_bytes())
    for path in (ROOT/'config/fextendo/presets').glob('*.dat'):
        put(dest, prefix+'launcher/presets/'+path.name, preset(path.read_bytes()))
    for name in SETTINGS:
        put(dest, prefix+name, preset((ROOT/'config/fextendo/presets/medium-720.dat').read_bytes()))
    put(dest, prefix+'drive_c/PES13/pes2013.wine-nx.txt',
        (ROOT/'config/drive_c/PES13/pes2013.wine-nx.txt').read_bytes())
    # The runtime may be shared as immutable code, never as original-folder data.
    for path in (dest/prefix).rglob('*'):
        if path.is_file():
            data=path.read_bytes()
            if b'switch/pes13-fex' in data or 'switch/pes13-fex'.encode('utf-16le') in data:
                raise ValueError('Rebuild this module with the patch identity: '+str(path))
    report = {'channel':'patch', 'base_manifest_sha256':sha((base/'runtime-manifest.json').read_bytes()),
              'kit17_manifest_sha256':sha((kit/'manifest.json').read_bytes()),
              'files':{p.relative_to(dest).as_posix():sha(p.read_bytes()) for p in sorted(dest.rglob('*')) if p.is_file()}}
    (work/'staged.json').write_bytes(encoded(report))
    print('Staged isolated runtime: '+str(len(report['files']))+' verified files', flush=True)


def seal(work, build_root, forwarder_root, tests, archive, tag, lock_out):
    if archive.exists() or lock_out.exists():
        raise ValueError('Use fresh archive/lock output paths')
    dest=work/'runtime'
    staged=json.loads((work/'staged.json').read_text())
    for name,digest in staged['files'].items(): checked(dest,name,digest)
    p=profile()
    build=json.loads((build_root/'build.json').read_text())
    if not build['built'] or build.get('edition')!='patch':
        raise ValueError('Expected the isolated patch build')
    nro=checked(build_root,p['nro'],build['nro_sha256'])
    if sha((build_root/'native-build/wine-nx-runtime.elf').read_bytes())!=build['elf_sha256']:
        raise ValueError('ELF does not match the build receipt')
    reports={}
    for name in ('low-window', 'settings', 'asset-probe'):
        path=tests/(name+'.json')
        report=json.loads(path.read_text())
        if not report.get('passed') or report.get('elf_sha256',report.get('native_elf_sha256'))!=build['elf_sha256']:
            raise ValueError('Test is not bound to the new ELF: '+name)
        put(dest,'evidence/patch-tests/'+path.name,path.read_bytes())
        reports[name]=report
    if not reports['low-window']['normal_launch_diagnostic_io_disabled']:
        raise ValueError('Normal-launch diagnostic writes have not been checked')
    if reports['settings'].get('root') != 'sdmc:/switch/pes13-patch-fex/drive_c':
        raise ValueError('Settings routing must be tested against the patch prefix')
    put(dest,p['prefix']+p['nro'],nro)
    forwarder=json.loads((forwarder_root/'forwarder-build.json').read_text())
    put(dest,p['nsp'],checked(forwarder_root,'forwarders/'+p['nsp'],forwarder['nsp_sha256']))
    put(dest,'evidence/forwarder/build.json',(forwarder_root/'forwarder-build.json').read_bytes())
    put(dest,'evidence/patch-build.json',(build_root/'build.json').read_bytes())
    put(dest,'evidence/patch-sources.json',(build_root/'prepared.json').read_bytes())
    catalog=(build_root/'feature/src/runtime/fextendo_runtime_catalog.h').read_bytes()
    validate_catalog(catalog)
    put(dest,'source/patch/fextendo_runtime_catalog.h',catalog)
    for kind, field in (('native-source','source_changes'),('feature','feature_changes')):
        for name,digest in build[field].items():
            put(dest,'source/patch/generated/'+kind+'/'+name,checked(build_root/kind,name,digest))
    for name,digest in build['inputs'].items():
        put(dest,'source/patch/'+name,checked(ROOT,name,digest))
    for kind in ('source','licenses'):
        for path in (forwarder_root/kind).rglob('*'):
            if path.is_file(): put(dest,kind+'/patch-forwarder/'+path.relative_to(forwarder_root/kind).as_posix(),path.read_bytes())
    for name in ('LICENSE','THIRD_PARTY.md','docs/PATCH-RELEASE.md','docs/FEXTENDO-MEMORY-ABI-V1.md'):
        put(dest,name,(ROOT/name).read_bytes())
    put(dest,'README.txt',(ROOT/'release/patch/README.txt').read_bytes())
    payload={path.relative_to(dest).as_posix():path.read_bytes() for path in sorted(dest.rglob('*')) if path.is_file()}
    lock={'schema':1,'channel':'patch','approved':True,'profile':p,'tag':tag,'asset':archive.name,
          'runtime_version':build['version'], 'hardware_tested':False, 'prerelease':True,
          'known_issues':['The latest LW6 device run crashed before kick-off. This isolated build requires further Switch testing.'],
          'binaries':{name:sha(data) for name,data in payload.items() if name==p['nsp'] or name.startswith(p['prefix']) and name.endswith(('.nro','.dll','.drv','.acm'))},
          'source_fingerprints':fingerprints()}
    verify_isolation(payload,lock)
    checks=verify_payload(payload,lock,p)
    put(dest,'evidence/patch-release-checks.json',encoded(checks))
    payload['evidence/patch-release-checks.json']=encoded(checks)
    inventory={'channel':'patch','kind':'isolated-patch-runtime','hardware_tested':False,
               'files':{name:sha(data) for name,data in payload.items()}}
    put(dest,'runtime-manifest.json',encoded(inventory))
    payload['runtime-manifest.json']=encoded(inventory)
    archive.parent.mkdir(parents=True,exist_ok=True)
    write_zip(archive,payload)
    lock['sha256']=sha(archive.read_bytes())
    lock_out.write_bytes(encoded(lock))
    print('Sealed patch input: '+str(archive)+' sha256='+lock['sha256'],flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    first=sub.add_parser('stage')
    for name in ('base','kit','work'): first.add_argument('--'+name,type=Path,required=True)
    last=sub.add_parser('seal')
    for name in ('work','build','forwarder','tests','archive','lock-out'): last.add_argument('--'+name,type=Path,required=True)
    last.add_argument('--tag',required=True)
    args=parser.parse_args()
    if args.command=='stage': stage(args.base,args.kit,args.work)
    else: seal(args.work,args.build,args.forwarder,args.tests,args.archive,args.tag,args.lock_out)


if __name__=='__main__': main()
