"""Seal the v0.4.2 Fastest-default rebuild without changing runtime DLLs.

Retains v0.4.1's historical device confirmation; this build has host/ARM64
validation only. Includes generated sources and tests bound to this NRO.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
from release_package import ROOT, NRO, NSP, PREFIX, encoded, fingerprints, read_runtime, sha, write_zip

BASE_SHA = '585219b77cd80c5f0cb4a235a6dbdd4a6897b9165e4b358cdf4b2bb6fb0e969d'
BASE_NRO = '8f8d1d32a97bd1c3d7788a1333628c6052b73747985877f8f090fc201b835b07'
AUTO_NSP = 'PES13-FEXTendo.nsp'
CHECKS = ('frame-host','vulkan-host','keyboard-host','keyboard-arm64',
          'capture-arm64','memory-arm64','hid-arm64','dependencies','fastest-default')


def promote(base, build, forwarder, tests, output, lock_output):
    files = read_runtime(base, {'sha256':BASE_SHA})
    assert sha(files[NRO]) == BASE_NRO
    report = json.loads((build/'build.json').read_text())
    assert report['built'] and report['version'] == '0.4.2' and report['build_revision'] == 'fastest-default'
    for n, h in report['input_sources'].items():
        assert sha((ROOT/n).read_bytes()) == h, 'Build source changed: '+n
    nro = (build/report['nro_filename']).read_bytes()
    assert sha(nro) == report['nro_sha256']
    assert sha((build/'native-build/wine-nx-runtime.elf').read_bytes()) == report['elf_sha256']
    for name in CHECKS:
        data = (tests/(name+'.json')).read_bytes()
        receipt = json.loads(data)
        assert receipt['passed'], name
        for key in ('elf_sha256','native_elf_sha256'):
            if key in receipt:
                assert receipt[key] == report['elf_sha256'], name
        for group in ('sources','test_sources'):
            for n, h in receipt.get(group,{}).items():
                assert sha((ROOT/n).read_bytes()) == h, n
        files['evidence/production-v0.4.2/'+name+'.json'] = data
    fastest = json.loads((tests/'fastest-default.json').read_text())
    assert fastest['nro_sha256'] == report['nro_sha256']
    assert fastest['generated_runtime_sha256'] == report['source_changes']['wine-nx-probe/source/runtime.c']
    f_report = json.loads((forwarder/'forwarder-build.json').read_text())
    assert f_report['runtime_nro_sha256'] == report['nro_sha256']
    nsp = (forwarder/'forwarders'/AUTO_NSP).read_bytes()
    spec = importlib.util.spec_from_file_location('metadata', ROOT/'tests/pes13_forwarder_metadata.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    metadata = module.inspect_forwarder(nsp, f_report)
    assert metadata['nacp_version'] == '0.4.2' and metadata['cnmt_version'] == 0x30000
    files[NRO], files[AUTO_NSP] = nro, nsp
    files[PREFIX+'configuration.ini'] = (ROOT/'release/skeleton/switch/pes13-fex/configuration.ini').read_bytes()
    files['evidence/forwarder-auto/build.json'] = encoded(f_report)
    files['evidence/forwarder-auto/metadata.json'] = encoded(metadata)
    for n in ('build.json','prepared.json'):
        files['evidence/production-v0.4.2/'+n] = (build/n).read_bytes()
    for group, folder in (('source_changes','native-source'),('feature_changes','feature')):
        for n, h in report[group].items():
            data = (build/folder/n).read_bytes()
            assert sha(data) == h, n
            files['source/production-v0.4.2/'+folder+'/'+n] = data
    # Include tracked build/release sources plus the new promotion/test scripts.
    names = subprocess.check_output(['git','-C',str(ROOT),'ls-files','-z','tools','tests','docs','release/README.txt'],text=True).split('\0')
    names += ['tools/prepare_production_v042_runtime.py','tests/fextendo_fastest_default.py']
    for n in sorted(set(names)-{''}):
        if (ROOT/n).suffix in ('.py','.c','.cpp','.h','.sh','.md','.txt'):
            files['source/production-v0.4.2/repository/'+n] = (ROOT/n).read_bytes()
    for folder in ('source','licenses'):
        for p in sorted((forwarder/folder).rglob('*')):
            if p.is_file():
                files['source/production-v0.4.2/forwarder/'+p.relative_to(forwarder).as_posix()] = p.read_bytes()
    baseline = json.loads((ROOT/'release/runtime-lock.json').read_text())
    binaries = dict(baseline['binaries'])
    del binaries[NSP]
    binaries.update({NRO:sha(nro),AUTO_NSP:sha(nsp)})
    for n,h in binaries.items():
        assert sha(files[n]) == h, 'Runtime dependency changed: '+n
    promotion = {'baseline_runtime_sha256':BASE_SHA, 'nro_sha256':sha(nro),
        'native_elf_sha256':report['elf_sha256'],'forwarder_sha256':sha(nsp),
        'binary_replacements':[NRO,AUTO_NSP],'checks':CHECKS,'hardware_tested':False,
        'default_fex_profile':'fastest','explicit_ini_opt_out_preserved':True,
        'source_fingerprints':fingerprints()}
    files['evidence/production-v0.4.2/promotion.json'] = encoded(promotion)
    files['runtime-manifest.json'] = encoded({'kind':'production-v0.4.2-runtime',
        'files':{n:sha(d) for n,d in sorted(files.items())}})
    output.parent.mkdir(parents=True,exist_ok=True)
    write_zip(output,files)
    lock = {'schema':1,'tag':'runtime-production-v0.4.2','asset':output.name,
        'sha256':sha(output.read_bytes()),'runtime_version':'0.4.2','release_tag':'v0.4.2',
        'nro_title':'PES13-FEXTendo','forwarder_filename':AUTO_NSP,'forwarder_kind':'fxtauto-v1',
        'binaries':binaries,'source_fingerprints':promotion['source_fingerprints'],
        'default_fex_profile':'fastest','hardware_tested':False}
    read_runtime(output,lock)
    lock_output.write_bytes(encoded(lock))
    print(json.dumps({'archive':str(output),'sha256':lock['sha256'],'nro_sha256':sha(nro)}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('base','build','forwarder','tests','output','lock-output'):
        p.add_argument('--'+name,type=Path,required=True)
    a = p.parse_args()
    promote(a.base,a.build,a.forwarder,a.tests,a.output,a.lock_output)
