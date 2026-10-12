"""Package one original PES13 HOME forwarder, with optional fxtauto ABI v1.

Adapts the pinned hbloader for stock 32-bit and patched high-native/low-guest.
Local packing keys are never copied into the output or printed in errors.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import os
import shutil
import subprocess
from fextendo_low_window import ROOT, SOURCE, exact, automatic_descriptor

TARGET = '/switch/pes13-fex/pes13-fex.nro'
TAG = 'pes13-original-39bit-v1'
# Keep the installed tile identity even when its NRO target/display name changes.
TITLE_ID = 0x052d1913f51f5000
# The old packages all used CNMT 0, even when the NACP name/version changed.
# Preserve the title identity but give installers a newer metadata revision.
TITLE_VERSION = 0x30000
NSO_SHA = 'f38ef096a589d3c39848d64101ab37c3488da8ea02c64f3397b06109cb0643e9'
ELF_SHA = '7f4eeaa4525fbb906aea5685a1bfd74b69003b57071ef373db3bfdfec4a758ff'
SOURCE_HASHES = {
    'main.c':'aecbdeedffad6df20be438db69b2c88bd77f4054b89fd4d357d32c20248e803d',
    'trampoline.s':'2f11a79cc9a4a162dcef557274076b66480bb256f353d47cea1ef56ab8e11f4e',
    'forwarder_heap.inc':'f22710cccbf72151357c93b37f49ac1f1079ecbbb51ecd117c0c2c19493bd57b',
    'forwarder_low.inc':'90cef10ab140f49751b6221c8d69d0dbd484a46fed085e29b62307ce989650ab'}


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
    for name,digest in SOURCE_HASHES.items():assert common.sha(a.known_forwarder/'forwarder-source'/name)==digest,name
    hbl = a.approved/'source/forwarder/hbl'
    for name,digest in base.HBL_HASHES.items(): assert common.sha(hbl/name) == digest,name
    git = ['git','-c','safe.directory='+str(a.packer),'-C',str(a.packer)]
    assert subprocess.check_output(git+['rev-parse','HEAD'],text=True).strip() == base.PACKER_REV
    assert not subprocess.check_output(git+['diff','HEAD','--'],text=True).strip()
    build = json.loads((a.runtime/'build.json').read_text())
    assert build['built'] and build['edition']=='original-39bit' and build['abi']=='fxtmem-v1'
    nro = a.runtime/build['nro_filename']
    assert common.sha(nro)==build['nro_sha256']
    tid = f'{TITLE_ID:016x}'
    assert common.title_id(TAG,'/switch/pes13-fex/pes13-39bit.nro')==TITLE_ID
    assert tid not in {'05b0354496b71000','059a3db219b42000','0548eabb35576000',
        '05f4548b34236000','056aa1975fd3d000','053d891f6ec02000','05c87a7fe7cff000'}
    a.work.mkdir(parents=True)
    for folder in ('forwarders','source','licenses'):
        (a.output/folder).mkdir(parents=True,exist_ok=True)
    sdk = Path('/opt/devkitpro');env = dict(os.environ,DEVKITPRO=str(sdk))
    # Start from the known device-tested hbloader, changing only its layout
    # selection and capping the handoff heap to the actual kernel heap region.
    src=a.work/'forwarder-source'
    shutil.copytree(a.known_forwarder/'forwarder-source',src)
    text=(src/'main.c').read_text()
    text=exact(text,'#include "forwarder_low.inc"','#include "forwarder_auto.inc"')
    text=exact(text,'    return size;\n}\n\nstatic void setupHbHeap',
        '    return fxt_limit_heap(size);\n}\n\nstatic void setupHbHeap')
    (src/'main.c').write_text(text)
    shutil.copy2(SOURCE/'forwarder_auto.inc',src/'forwarder_auto.inc')
    cc=sdk/'devkitA64/bin/aarch64-none-elf-gcc'
    flags=['-O2','-g','-march=armv8-a+crc','-mtune=cortex-a57','-ffixed-x18','-fPIE',
        '-ffunction-sections','-fdata-sections','-D__SWITCH__','-isystem',sdk/'libnx/include']
    objects=[]
    for name in ('main.c','trampoline.s'):
        obj=a.work/(name+'.o')
        common.run(cc,*flags,'-DVERSION="3.0.0"','-c',src/name,'-o',obj,env=env);objects.append(obj)
    common.run(cc,*flags,'-specs='+str(sdk/'libnx/switch.specs'),'-Wl,-wrap,exit',*objects,
        '-L'+str(sdk/'libnx/lib'),'-lnx','-o',a.work/'forwarder.elf',env=env)
    common.run(sdk/'tools/bin/elf2nso',a.work/'forwarder.elf',a.work/'forwarder.nso',env=env)
    icon,nacp = base.extract_assets(nro.read_bytes())
    result = common.pack(TAG,a,sdk,env,hbl,icon,nacp,base,checks,target=TARGET,
        label='PES13-FEXTendo',npdm_name='PES13Fxt',output_name='PES13-FEXTendo.nsp',
        fixed_title_id=TITLE_ID,title_version=TITLE_VERSION,automatic=True)
    assert (a.work/TAG/'exefs/fxtauto').read_bytes()==automatic_descriptor()
    shutil.copytree(src,a.output/'source/forwarder',dirs_exist_ok=True)
    shutil.copytree(a.approved/'licenses/forwarder',a.output/'licenses/forwarder',dirs_exist_ok=True)
    shutil.copytree(a.work/TAG/'packer-versioned',a.output/'source/hacbrewpack',
        ignore=shutil.ignore_patterns('*.o','*.a','hacbrewpack'),dirs_exist_ok=True)
    shutil.copy2(a.work/TAG/'packer-cnmt-change.txt',a.output/'source/packer-cnmt-change.txt')
    report = {'forwarder':result,'title_id':tid,'target':TARGET,'name':'PES13-FEXTendo','abi':'fxtmem-v1',
        'address_space':'32-bit no-alias; optional 39-bit low-window via fxtauto-v1',
        'automatic':True,'minimum_automatic_patch':'1.1.0','descriptor_hex':automatic_descriptor().hex(),
        'forwarder_nso_sha256':common.sha(a.work/'forwarder.nso'),'forwarder_elf_sha256':common.sha(a.work/'forwarder.elf'),
        'baseline_forwarder_nso_sha256':NSO_SHA,'baseline_forwarder_elf_sha256':ELF_SHA,
        'runtime_nro_sha256':build['nro_sha256'],'hardware_tested_pes':False}
    (a.output/'forwarder-build.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Packaged PES13-FEXTendo '+tid+' -> '+TARGET,flush=True)


if __name__ == '__main__': main()
