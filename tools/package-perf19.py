"""Package the matrix experiment, same-NRO control, diagnostic and rollback."""
from pathlib import Path
import hashlib
import json
import zipfile

p=Path(__file__).resolve().parents[1]
work=p/'local/perf19'
checks=json.loads((work/'matrix-tests.json').read_text())
assert checks['whole_block_bit_identical'] and checks['cases']>=1728
assert (work/'matrix-c-patched.bin').read_bytes()==(work/'matrix-planned.bin').read_bytes()
assert hashlib.sha256((work/'matrix-c-patched.bin').read_bytes()).hexdigest()==checks['patched_sha256']
path=p/'tools/package-perf17.py'
recipe=path.read_text()
replacements={
    "work = p / 'local/perf17'":"work = p / 'local/perf19'",
    "b'pes13-nx-0.2.0-perf17-hotblocks'":"b'pes13-nx-0.2.0-perf19-matrix'",
    "expected_title='PES13-NX PERF17'":"expected_title='PES13-NX PERF19'",
    "control additionally requires PERF17 NRO":"control additionally requires PERF19 NRO",
    "prefix + 'perf17-hotblocks.txt': b'1\\n' if variant == 'hotblocks' else b'0\\n',":
        "prefix + 'perf17-hotblocks.txt': b'0\\n',\n        prefix + 'perf18-roundguard.txt': b'0\\n',\n        prefix + 'perf19-matrix.txt': b'1\\n' if variant == 'hotblocks' else b'0\\n',",
    "'PERF17.md': (p / 'docs/PERF17.md').read_bytes()":
        "'PERF19.md': (p / 'docs/PERF19.md').read_bytes(),\n        'PERF18-RESULT.md': (p / 'docs/PERF18-RESULT.md').read_bytes()",
    "files['PERF17-manifest.json']":"files['PERF19-manifest.json']",
    "'variant': variant,":"'variant': 'matrix' if variant == 'hotblocks' else variant,",
    "'scoped_bigblock': variant == 'hotblocks'":"'scoped_bigblock': False, 'matrix_patch': variant == 'hotblocks'",
    "f'pes13-perf17-{variant}.zip'":"('pes13-perf19-' + ('matrix' if variant == 'hotblocks' else variant) + '.zip')",
}
for old,new in replacements.items():
    assert recipe.count(old)==1,(old,recipe.count(old))
    recipe=recipe.replace(old,new,1)
exec(compile(recipe,str(path),'exec'),{'__file__':str(path),'__name__':'__main__'})
prefix='switch/pes13-nx/'
config=(p/'config/drive_c/PES13/pes2013.wine-nx.txt').read_bytes()
assert config.count(b'profile=0')==1
files={prefix+'profile.txt':b'1\n', prefix+'perf19-matrix.txt':b'1\n',
       prefix+'perf17-hotblocks.txt':b'0\n', prefix+'perf18-roundguard.txt':b'0\n',
       prefix+'perf8-turbo.txt':b'0\n',prefix+'perf17-capture.txt':b'1\n',
       prefix+'drive_c/PES13/pes2013.wine-nx.txt':config.replace(b'profile=0',b'profile=1'),
       'PERF19.md':(p/'docs/PERF19.md').read_bytes()}
sha=lambda b:hashlib.sha256(b).hexdigest()
files['PERF19-manifest.json']=json.dumps({'variant':'diagnostic','requires':'PERF19 main package',
    'sampling_interval_ms':10,'continuous_sampling':True,'hardware_tested':False,
    'files':{k:sha(v) for k,v in files.items()}},indent=2).encode()
target=p/'dist/pes13-perf19-diagnostic.zip'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
    for name,blob in files.items():z.writestr(name,blob)
with zipfile.ZipFile(target) as z:
    assert z.testzip() is None and set(z.namelist())==set(files)
    assert all(z.read(name)==blob for name,blob in files.items())
packages=json.loads((work/'packages.json').read_text())
packages.append({'path':str(target),'sha256':sha(target.read_bytes()),'bytes':target.stat().st_size})
(work/'packages.json').write_text(json.dumps(packages,indent=2)+'\n')
print('Diagnostic overlay:',packages[-1])
