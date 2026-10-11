"""Package the original PES13 39-bit HOME forwarder, with fxtmem ABI v1.

Reuses the exact high-native/low-guest hbloader that passed the device probe.
Local packing keys are never copied into the output or printed in errors.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import os
import shutil
import subprocess
from fextendo_low_window import ROOT, descriptor

TARGET = '/switch/pes13-fex/pes13-39bit.nro'
TAG = 'pes13-original-39bit-v1'
NSO_SHA = 'f38ef096a589d3c39848d64101ab37c3488da8ea02c64f3397b06109cb0643e9'
ELF_SHA = '7f4eeaa4525fbb906aea5685a1bfd74b69003b57071ef373db3bfdfec4a758ff'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('work','output','runtime','keys','approved'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--known-forwarder',type=Path,default=Path('/home/blekjek/fextendo-memory-probe-v1'))
    p.add_argument('--packer',type=Path,default=Path('/home/blekjek/sleepingdogs-forwarder-tools/hacbrewpack'))
    a = p.parse_args()
    assert not a.work.exists(),'Use a fresh packaging directory'
    common = module('memory_probe_pack',ROOT/'tools/build-fextendo-memory-probe.py')
    base = module('as39_probe',ROOT/'tools/build-as39-probe.py')
    checks = module('forwarder_checks',ROOT/'tools/build-fextendo-forwarder.py')
    assert common.sha(a.known_forwarder/'forwarder.nso') == NSO_SHA
    assert common.sha(a.known_forwarder/'forwarder.elf') == ELF_SHA
    hbl = a.approved/'source/forwarder/hbl'
    for name,digest in base.HBL_HASHES.items(): assert common.sha(hbl/name) == digest,name
    git = ['git','-c','safe.directory='+str(a.packer),'-C',str(a.packer)]
    assert subprocess.check_output(git+['rev-parse','HEAD'],text=True).strip() == base.PACKER_REV
    assert not subprocess.check_output(git+['diff','HEAD','--'],text=True).strip()
    build = json.loads((a.runtime/'build.json').read_text())
    assert build['built'] and build['edition']=='original-39bit' and build['abi']=='fxtmem-v1'
    nro = a.runtime/build['nro_filename']
    assert common.sha(nro)==build['nro_sha256']
    tid = f'{common.title_id(TAG,TARGET):016x}'
    assert tid not in {'05b0354496b71000','059a3db219b42000','0548eabb35576000',
        '05f4548b34236000','056aa1975fd3d000','053d891f6ec02000','05c87a7fe7cff000'}
    a.work.mkdir(parents=True)
    for folder in ('forwarders','source','licenses'):
        (a.output/folder).mkdir(parents=True,exist_ok=True)
    shutil.copy2(a.known_forwarder/'forwarder.nso',a.work/'forwarder.nso')
    sdk = Path('/opt/devkitpro');env = dict(os.environ,DEVKITPRO=str(sdk))
    icon,nacp = base.extract_assets(nro.read_bytes())
    result = common.pack(TAG,a,sdk,env,hbl,icon,nacp,base,checks,target=TARGET,
        label='PES13 FEXTendo 39-bit',npdm_name='PES13Fxt39',output_name='PES13-FEXTendo-39bit.nsp')
    assert (a.work/TAG/'exefs/fxtmem').read_bytes()==descriptor()
    shutil.copytree(a.known_forwarder/'forwarder-source',a.output/'source/forwarder',dirs_exist_ok=True)
    shutil.copytree(a.approved/'licenses/forwarder',a.output/'licenses/forwarder',dirs_exist_ok=True)
    report = {'forwarder':result,'title_id':tid,'target':TARGET,'abi':'fxtmem-v1',
        'address_space':'39-bit native / low 32-bit guest','descriptor_hex':descriptor().hex(),
        'forwarder_nso_sha256':NSO_SHA,'forwarder_elf_sha256':ELF_SHA,
        'runtime_nro_sha256':build['nro_sha256'],'hardware_tested_pes':False}
    (a.output/'forwarder-build.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Packaged PES13 FEXTendo 39-bit '+tid+' -> '+TARGET,flush=True)


if __name__ == '__main__': main()
