"""Package PES using the exact forwarder NSO that passed the v1 device probe.

Only metadata, opt-in descriptor and target path differ. The sibling NRO path
preserves the old PES tile/NRO and shares the user's existing game/prefix.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from fextendo_low_window import ROOT
import importlib.util

TARGET = '/switch/pes13-fex/pes13-low-window.nro'
NSO_SHA = 'f38ef096a589d3c39848d64101ab37c3488da8ea02c64f3397b06109cb0643e9'
ELF_SHA = '7f4eeaa4525fbb906aea5685a1bfd74b69003b57071ef373db3bfdfec4a758ff'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--runtime', type=Path, required=True)
    p.add_argument('--keys', type=Path, required=True)
    p.add_argument('--edition', choices=('experimental', 'patch'), default='experimental')
    p.add_argument('--known-forwarder', type=Path, default=Path('/home/blekjek/fextendo-memory-probe-v1'))
    p.add_argument('--packer', type=Path, default=Path('/home/blekjek/sleepingdogs-forwarder-tools/hacbrewpack'))
    a = p.parse_args()
    assert not a.work.exists(), 'Use a fresh work directory'
    common = module('memory_probe_pack', ROOT/'tools/build-fextendo-memory-probe.py')
    base = module('as39_probe', ROOT/'tools/build-as39-probe.py')
    checks = module('forwarder_checks', ROOT/'tools/build-fextendo-forwarder.py')
    assert common.sha(a.known_forwarder/'forwarder.nso') == NSO_SHA
    assert common.sha(a.known_forwarder/'forwarder.elf') == ELF_SHA
    hbl = ROOT/'local/production-input-fix/approved/source/forwarder/hbl'
    for name, digest in base.HBL_HASHES.items(): assert common.sha(hbl/name) == digest
    git = ['git', '-c', 'safe.directory='+str(a.packer), '-C', str(a.packer)]
    assert subprocess.check_output(git+['rev-parse','HEAD'], text=True).strip() == base.PACKER_REV
    assert not subprocess.check_output(git+['diff','HEAD','--'], text=True).strip()
    build = json.loads((a.runtime/'build.json').read_text())
    if a.edition == 'patch':
        from pes_patch_identity import profile, title_id
        identity = profile()
        assert build['built'] and build.get('edition') == 'patch'
        assert build['identity']['profile'] == identity
        target = '/' + identity['prefix'] + identity['nro']
        tag, label, output_name = identity['forwarder_tag'], identity['home_title'], identity['nsp']
        nro = a.runtime / identity['nro']
        npdm_name = 'PES13Patch'
    else:
        assert build['built'] and build['version'] == '0.3.9-lw1'
        target, tag, label = TARGET, 'pes13-low-window-v1', 'PES13 Low Window'
        output_name, npdm_name = 'PES13-Low-Window-v1.nsp', 'PES13LowVA'
        nro = a.runtime / 'pes13-fex.nro'
    assert common.sha(nro) == build['nro_sha256']
    # Ensure this identity differs from all earlier probe and installed game IDs.
    tid = f'{common.title_id(tag, target):016x}'
    assert tid not in {'05b0354496b71000', '059a3db219b42000', '0548eabb35576000',
                       '05f4548b34236000', '056aa1975fd3d000', '053d891f6ec02000'}
    if a.edition == 'patch':
        assert tid == f'{title_id():016x}' and tid != '05c87a7fe7cff000'
    a.work.mkdir(parents=True)
    for folder in ('forwarders', 'source', 'licenses'): (a.output/folder).mkdir(parents=True, exist_ok=True)
    shutil.copy2(a.known_forwarder/'forwarder.nso', a.work/'forwarder.nso')
    sdk = Path('/opt/devkitpro'); env = dict(os.environ, DEVKITPRO=str(sdk))
    icon, nacp = base.extract_assets(nro.read_bytes())
    result = common.pack(tag, a, sdk, env, hbl, icon, nacp, base, checks, target=target,
                         label=label, npdm_name=npdm_name, output_name=output_name)
    shutil.copytree(a.known_forwarder/'forwarder-source', a.output/'source/forwarder', dirs_exist_ok=True)
    shutil.copytree(ROOT/'local/production-input-fix/approved/licenses/forwarder',
                    a.output/'licenses/forwarder', dirs_exist_ok=True)
    report = dict(target=target, forwarder=result, forwarder_nso_sha256=NSO_SHA,
                  forwarder_elf_sha256=ELF_SHA, generic_abi='fxtmem-v1',
                  runtime_nro_sha256=build['nro_sha256'], hardware_tested_pes=False)
    if a.edition == 'patch':
        import hashlib
        report.update(channel='patch', nsp_sha256=result['sha256'],
            icon_sha256=hashlib.sha256(icon).hexdigest(), address_space='39-bit low-window',
            cpu_cores=4, svc_debug=False, nro_path='sdmc:'+target, title_id=tid,
            nca_files={n:hashlib.sha256(d).hexdigest() for n,d in
                       checks.pfs_files((a.output/'forwarders'/output_name).read_bytes()).items()})
    (a.output/'forwarder-build.json').write_text(json.dumps(report, indent=2)+'\n')
    print('Packaged '+label+' forwarder '+tid+' -> '+target, flush=True)


if __name__ == '__main__': main()
